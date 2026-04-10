"""Data update coordinator for ISDT Air BLE charger.

Uses a persistent BLE connection with continuous command cycling (matching
the manufacturer app pattern).  Commands are sent one at a time every 100ms
in an infinite loop.  Data is pushed to Home Assistant at the configured
scan interval.
"""

import asyncio
import logging
import uuid
from collections.abc import Callable

from bleak import BleakClient
from bleak_retry_connector import establish_connection

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import BluetoothCallbackMatcher
from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    BIND_RESULT_OK,
    BIND_RESULT_WAITING,
    BIND_STATUS,
    CHAR_UUID_AF01,
    CHAR_UUID_AF02,
    CMD_ALARM_TONE_REQ,
    CMD_ALARM_TONE_SET,
    CMD_BIND_REQ,
    CMD_ELECTRIC_REQ,
    CMD_HARDWARE_INFO_REQ,
    CMD_IR_REQ,
    CMD_MASS2_SETTINGS_REQ,
    CMD_MASS2_WORK_STATUS_REQ,
    CMD_WORKSTATE_REQ,
    DEFAULT_SCAN_INTERVAL,
    DeviceType,
    MASS2_FRAME_HEADER,
    MASS2_PORT_COUNT,
    RESP_BIND,
    RESP_MASS2_SETTINGS,
    RESP_MASS2_WORK_STATUS,
    get_device_type,
)
from .parser import (
    build_mass2_settings_set_req,
    parse_charger_responses,
    parse_hardware_info,
    parse_mass2_responses,
)

_LOGGER = logging.getLogger(__name__)
TRACE = 5  # HA supports trace level below DEBUG (10)

# Backoff limits for reconnection attempts
_BACKOFF_MIN = 5
_BACKOFF_MAX = 300

# Command interval matching manufacturer app (100ms)
_CMD_INTERVAL = 0.1


def _build_charger_command_list() -> list[bytearray]:
    """Build the circular command list for charger devices.

    Order: AlarmTone, then per channel: WorkState, Electric, IR
    Total: 1 + 6*3 = 19 commands.
    """
    commands = [CMD_ALARM_TONE_REQ]
    for ch in range(6):
        commands.append(CMD_WORKSTATE_REQ + bytearray([ch]))
        commands.append(CMD_ELECTRIC_REQ + bytearray([ch]))
        commands.append(CMD_IR_REQ + bytearray([ch]))
    return commands


def _build_adapter_command_list() -> list[bytearray]:
    """Build the circular command list for adapter devices (MASS2).

    Single command: WorkStatusReq polls all 8 ports at once.
    """
    return [CMD_MASS2_WORK_STATUS_REQ]


class ISDTDataUpdateCoordinator(DataUpdateCoordinator):
    """Coordinator that keeps a persistent BLE connection to an ISDT device."""

    def __init__(self, hass, address, model="C4 Air", scan_interval=DEFAULT_SCAN_INTERVAL, bind_uuid: bytes | None = None):
        super().__init__(
            hass,
            _LOGGER,
            name=f"ISDT {model}",
            update_interval=None,  # no HA-driven polling; live loop handles everything
        )
        self.address = address
        self.model = model
        self.device_type = get_device_type(model)
        self.scan_interval_seconds = scan_interval
        self.data = {}

        # Hardware info (populated once after first connect)
        self.hw_version: str | None = None
        self.sw_version: str | None = None
        self.serial_number: str | None = None
        self._hw_info_fetched = False
        self._device_registry_updated = False

        # Alarm tone state (charger only)
        self._alarm_tone_on: bool | None = None

        # Persistent BLE connection
        self._client: BleakClient | None = None
        self._connected = False
        self._response_queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._notification_started = False

        # Notification reassembly buffer for MASS2 (BLE notifications can be
        # fragmented when MTU is small — a 59-byte WorkStatus response will
        # arrive as 3 notifications with a 23-byte MTU). We accumulate the
        # bytes here and emit complete responses to the queue.
        self._mass2_buffer = bytearray()

        # Cached MASS2 device settings (beep, volume, mute schedule, alarms).
        # Populated once on connect from a SettingsResp (cmd 0xCB).
        self._mass2_settings: dict | None = None
        self._mass2_settings_requested = False

        # Live monitoring
        self._connection_lock = asyncio.Lock()
        self._live_task: asyncio.Task | None = None

        # Circular command list (device-type-specific)
        if self.device_type == DeviceType.ADAPTER:
            self._commands = _build_adapter_command_list()
        else:
            self._commands = _build_charger_command_list()

        # Bind UUID — persistent per device. Must stay stable across restarts
        # so the device recognizes us and doesn't require re-pairing (which
        # would beep and need a button press).
        self._bind_uuid = bind_uuid if bind_uuid else uuid.uuid4().bytes

        # Bluetooth advertisement callback for instant reconnection
        self._device_available = asyncio.Event()
        self._unsub_bluetooth: Callable | None = None

        # Change detection: only push to HA when sensor data actually changed
        self._last_pushed_data: dict | None = None

    @property
    def alarm_tone_on(self) -> bool | None:
        """Return alarm tone state (charger only)."""
        return self._alarm_tone_on

    @property
    def mass2_settings(self) -> dict | None:
        """Return cached MASS2 device settings (adapter only)."""
        return self._mass2_settings

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @callback
    def _async_on_bluetooth_event(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        """Wake the monitoring loop when the device advertises."""
        _LOGGER.debug("Bluetooth event for %s: %s", self.address, change)
        self._device_available.set()

    def start_live_monitoring(self):
        """Start the persistent connection loop as a background task."""
        if self._live_task is None or self._live_task.done():
            self._live_task = self.hass.loop.create_task(
                self._live_monitoring_loop()
            )
        # Register BLE advertisement callback for instant wake-up on reconnect
        if self._unsub_bluetooth is None:
            self._unsub_bluetooth = bluetooth.async_register_callback(
                self.hass,
                self._async_on_bluetooth_event,
                BluetoothCallbackMatcher(address=self.address, connectable=True),
                bluetooth.BluetoothScanningMode.ACTIVE,
            )

    async def async_shutdown(self):
        """Called on unload – cancel live task and disconnect."""
        _LOGGER.info("Shutting down ISDT %s coordinator", self.model)
        if self._unsub_bluetooth:
            self._unsub_bluetooth()
            self._unsub_bluetooth = None
        if self._live_task:
            self._live_task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(self._live_task), timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
        await self._disconnect()

    # ------------------------------------------------------------------
    # Live monitoring loop – continuous command cycling
    # ------------------------------------------------------------------

    async def _live_monitoring_loop(self):
        """Continuous command loop matching the manufacturer app pattern.

        Sends one command every 100ms in a circular fashion.  After each
        full cycle (19 commands ≈ 1.9s), responses are collected, parsed,
        and pushed to HA if enough time has passed since the last push.
        """
        backoff = _BACKOFF_MIN
        cmd_index = 0
        last_push_time = 0.0

        while True:
            try:
                # --- Ensure connection ---
                if not (self._client and self._client.is_connected and self._notification_started):
                    service_info = bluetooth.async_last_service_info(
                        self.hass, self.address, connectable=True
                    )

                    # Waiting for the device to be in range (advertising)
                    if not service_info:
                        _LOGGER.info(
                            "Device %s not in range – waiting for advertisement (max %ds)",
                            self.address,
                            backoff,
                        )
                        self._device_available.clear()
                        try:
                            await asyncio.wait_for(
                                self._device_available.wait(), timeout=backoff
                            )
                            _LOGGER.info("Device advertisement received, reconnecting now")
                        except asyncio.TimeoutError:
                            pass
                        backoff = min(backoff * 2, _BACKOFF_MAX)
                        continue

                    # Connecting to device
                    backoff = _BACKOFF_MIN
                    async with self._connection_lock:
                        await self._connect(service_info.device)
                    cmd_index = 0
                    last_push_time = 0.0

                    # Drain any stale responses after reconnect
                    while not self._response_queue.empty():
                        try:
                            self._response_queue.get_nowait()
                        except asyncio.QueueEmpty:
                            break

                # Send next command in the cycle
                cmd = self._commands[cmd_index]
                await self._client.write_gatt_char(
                    CHAR_UUID_AF01, cmd, response=False
                )
                await asyncio.sleep(_CMD_INTERVAL)

                # Increment command index for next cycle
                cmd_index = (cmd_index + 1) % len(self._commands)

                # After cycle completion, collect responses and push data
                if cmd_index == 0:
                    # Adapter has only 1 command per cycle — wait for
                    # the response before collecting (matches app behavior)
                    if self.device_type == DeviceType.ADAPTER:
                        await asyncio.sleep(0.5)

                    await self._collect_and_push(last_push_time)
                    last_push_time = asyncio.get_event_loop().time()

            except asyncio.CancelledError:
                _LOGGER.debug("Live monitoring cancelled")
                raise
            except Exception as err:
                _LOGGER.warning("Live monitoring error: %s – reconnecting", err)
                await self._disconnect()
                self._device_available.clear()
                try:
                    await asyncio.wait_for(
                        self._device_available.wait(), timeout=backoff
                    )
                    _LOGGER.debug("Device advertisement received, reconnecting now")
                except asyncio.TimeoutError:
                    pass
                backoff = min(backoff * 2, _BACKOFF_MAX)

    async def _collect_and_push(self, last_push_time: float):
        """Collect queued responses, parse, and push to HA."""
        responses = []
        try:
            while not self._response_queue.empty():
                responses.append(self._response_queue.get_nowait())
        except asyncio.QueueEmpty:
            pass

        if not responses:
            return

        # Parsing response (device-type-specific)
        _LOGGER.debug("Received %d responses", len(responses))
        if self.device_type == DeviceType.ADAPTER:
            parsed_ports, parsed_settings = parse_mass2_responses(responses)
            if parsed_settings is not None:
                self._mass2_settings = parsed_settings
                _LOGGER.debug("MASS2 settings updated from device")
            if parsed_ports is None:
                # No complete WorkStatus response — keep existing data
                # instead of overwriting it with empty values. Push current
                # data anyway so settings entities update.
                if parsed_settings is not None and self.data:
                    self.async_set_updated_data(self.data)
                return
            parsed = parsed_ports
        else:
            parsed, alarm_tone_on = parse_charger_responses(responses)
            self._alarm_tone_on = alarm_tone_on

        # Fetch hardware info if not yet done
        if not self._hw_info_fetched:
            await self._fetch_hardware_info()

        # Update device registry once when hw info is available
        if self._hw_info_fetched and not self._device_registry_updated:
            self._update_device_registry()

        # Only push to HA when sensor data actually changed (skip rssi/last_seen)
        if self._last_pushed_data is not None and not self._sensor_data_changed(parsed):
            _LOGGER.debug("Data unchanged, skipping push")
            return

        # Add device-level metadata (not part of change detection)
        parsed["_device"] = {
            "rssi": self._get_rssi(),
        }

        self._last_pushed_data = parsed
        self.async_set_updated_data(parsed)

    def _sensor_data_changed(self, parsed: dict) -> bool:
        """Compare channel sensor data against last push, ignoring _device metadata."""
        if self._last_pushed_data is None:
            return True
        for key in parsed:
            if key == "_device":
                continue
            if parsed[key] != self._last_pushed_data.get(key):
                return True
        return False

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    async def _connect(self, ble_device):
        """Establish BLE connection and set up notifications."""
        if self._client:
            await self._disconnect()

        _LOGGER.debug("Connecting to %s", self.address)

        try:
            self._client = await establish_connection(
                BleakClient, ble_device, f"ISDT {self.model}", timeout=15
            )
            mtu = getattr(self._client, "mtu_size", None)
            _LOGGER.debug(
                "Connected, services available: %d, MTU=%s",
                len(self._client.services.services),
                mtu,
            )
            # Reset reassembly buffer + settings request flag on every (re)connect
            self._mass2_buffer = bytearray()
            self._mass2_settings_requested = False
            await asyncio.sleep(1.0)

            await self._setup_notifications()
            await self._send_bind_request()
            self._connected = True
            _LOGGER.debug("Persistent connection established to %s", self.address)

            # Fetch hardware info once
            if not self._hw_info_fetched:
                await self._fetch_hardware_info()

            # For MASS2 adapters: query settings once after connect.
            # The response (cmd 0xCB) will be picked up by the notification
            # handler and stored in self._mass2_settings.
            if (
                self.device_type == DeviceType.ADAPTER
                and not self._mass2_settings_requested
            ):
                _LOGGER.debug("Sending MASS2 SettingsReq")
                await self._client.write_gatt_char(
                    CHAR_UUID_AF01, CMD_MASS2_SETTINGS_REQ, response=False
                )
                self._mass2_settings_requested = True

        except Exception as err:
            _LOGGER.warning("Failed to connect: %s", err)
            self._connected = False
            self._client = None
            raise

    async def _setup_notifications(self):
        """Set up BLE notifications for responses on AF01."""
        if self._notification_started:
            return

        if not self._client:
            raise UpdateFailed("Client not connected, cannot setup notifications")

        def disconnected_callback(client):
            _LOGGER.debug(
                "BLE device disconnected: %s",
                self.address,
            )
            self._connected = False
            self._notification_started = False
            # Notify entities so connected sensor updates immediately
            self.async_set_updated_data(self.data or {})

        self._client.set_disconnected_callback(disconnected_callback)

        def notification_callback(sender, data):
            _LOGGER.log(TRACE, "Notification received (%d bytes): %s", len(data), data.hex(" "))
            if self.device_type == DeviceType.ADAPTER:
                self._handle_adapter_notification(data)
            else:
                try:
                    self._response_queue.put_nowait(data)
                except asyncio.QueueFull:
                    _LOGGER.warning("Response queue full, dropping packet")

        await self._client.start_notify(CHAR_UUID_AF01, notification_callback)
        self._notification_started = True

        await asyncio.sleep(0.5)
        _LOGGER.debug("Notifications started on %s", CHAR_UUID_AF01)

    def _handle_adapter_notification(self, data: bytes) -> None:
        """Reassemble fragmented MASS2 notifications into complete responses.

        Frame format (verified against MASS2Fragment.onBleByte in the
        manufacturer app):
            byte 0: 0x31 = frame header for normal MASS2 data packets
            byte 1: cmd word (0xC3 = WorkStatusResp, 0xC5/0xC7/0xCB = others)
            byte 2: payload-specific (port_count for WorkStatus)
            byte 3+: payload

        With the default ATT MTU of 23, a 59-byte WorkStatus response arrives
        in 3 notifications and we have to reassemble it. We resync by looking
        for the 0x31 frame header.
        """
        self._mass2_buffer.extend(data)

        while len(self._mass2_buffer) >= 2:
            # Resync: discard everything up to the next 0x31 frame header
            if self._mass2_buffer[0] != MASS2_FRAME_HEADER:
                idx = self._mass2_buffer.find(MASS2_FRAME_HEADER)
                if idx == -1:
                    _LOGGER.debug(
                        "Discarding %d bytes — no MASS2 frame header found: %s",
                        len(self._mass2_buffer),
                        self._mass2_buffer.hex(" "),
                    )
                    self._mass2_buffer.clear()
                    return
                _LOGGER.debug(
                    "Resyncing: dropped %d bytes before frame header", idx,
                )
                del self._mass2_buffer[:idx]

            if len(self._mass2_buffer) < 3:
                return

            cmd = self._mass2_buffer[1]

            if cmd == RESP_MASS2_WORK_STATUS:
                # Always 8 ports (3 header + 8 * 7 = 59 bytes).
                # Byte 2 is total power, not port count.
                expected = 3 + MASS2_PORT_COUNT * 7
            elif cmd == RESP_MASS2_SETTINGS:
                # Settings response: scheduledMute, volume, opSoundRepeat,
                # openingTime[2], closingTime[2], 4 × (switchRepeatDay,
                # openingTime[2]) = 21 bytes
                expected = 21
            else:
                # Unknown cmd word. We don't know the length, so log and
                # try to find the next frame header.
                _LOGGER.debug(
                    "Unknown MASS2 cmd 0x%02x, skipping frame", cmd,
                )
                del self._mass2_buffer[0]
                continue

            if len(self._mass2_buffer) < expected:
                return  # need more data

            response = bytes(self._mass2_buffer[:expected])
            del self._mass2_buffer[:expected]
            try:
                self._response_queue.put_nowait(response)
            except asyncio.QueueFull:
                _LOGGER.warning("Response queue full, dropping packet")

    async def _send_bind_request(self):
        """Send bind request on AF02 (matching manufacturer app protocol).

        Packet: [0x18, uuid[0..15], 0x00, status=1]  (19 bytes)

        The manufacturer app sends BindReq once and then passively waits for
        a BindResp with result=0. The device behavior:
            - If the UUID is already known: device replies with bound=0 immediately
            - If the UUID is unknown: device beeps and waits for the user to
              press a button. After the press, the device sends bound=0
              spontaneously (the app does not retransmit).

        We mirror this: send once, then wait up to 30 seconds for any
        BindResp with bound=0. Any intermediate bound=1 just means "still
        waiting for user".
        """
        bind_response: asyncio.Queue = asyncio.Queue(maxsize=20)

        def af02_callback(sender, data):
            _LOGGER.debug("AF02 bind response (%d bytes): %s", len(data), data.hex(" "))
            try:
                bind_response.put_nowait(data)
            except asyncio.QueueFull:
                pass

        try:
            await self._client.start_notify(CHAR_UUID_AF02, af02_callback)
            await asyncio.sleep(0.3)

            cmd = (
                bytearray([CMD_BIND_REQ])
                + bytearray(self._bind_uuid)
                + bytearray([0x00, BIND_STATUS])
            )
            _LOGGER.debug("Sending BindReq on AF02: %s", cmd.hex(" "))
            await self._client.write_gatt_char(CHAR_UUID_AF02, cmd, response=False)

            # Wait up to 30s for a successful BindResp.
            try:
                async with asyncio.timeout(30.0):
                    while True:
                        data = await bind_response.get()
                        if len(data) < 2 or data[0] != RESP_BIND:
                            _LOGGER.debug(
                                "Non-BindResp on AF02 while pairing: %s", data.hex(" ")
                            )
                            continue
                        if data[1] == BIND_RESULT_OK:
                            _LOGGER.info("Bind successful")
                            return
                        if data[1] == BIND_RESULT_WAITING:
                            _LOGGER.warning(
                                "Device requires pairing — please press a button on the device"
                            )
                            continue
                        _LOGGER.warning("Unknown BindResp result: %d", data[1])
            except asyncio.TimeoutError:
                _LOGGER.warning(
                    "Timeout waiting for BindResp on AF02 — pairing may have failed"
                )

        except Exception as err:
            _LOGGER.warning("Failed to send bind request: %s", err)

        finally:
            try:
                await self._client.stop_notify(CHAR_UUID_AF02)
            except Exception:
                pass

    async def _disconnect(self):
        """Disconnect from BLE device (with timeout to avoid hanging)."""
        if self._client and self._client.is_connected:
            try:
                async with asyncio.timeout(5.0):
                    if self._notification_started:
                        await self._client.stop_notify(CHAR_UUID_AF01)
                        self._notification_started = False
                    await self._client.disconnect()
                    _LOGGER.debug("Disconnected from %s", self.address)
            except (TimeoutError, Exception) as err:
                _LOGGER.debug("Error during disconnect: %s", err)

        self._client = None
        self._connected = False

    # ------------------------------------------------------------------
    # DataUpdateCoordinator override – passive when live connection active
    # ------------------------------------------------------------------

    async def _async_update_data(self):
        """Called by HA's update interval – skip when live loop is active."""
        return self.data or {}

    # ------------------------------------------------------------------
    # Alarm tone control
    # ------------------------------------------------------------------

    async def async_set_alarm_tone(self, enable: bool) -> None:
        """Send alarm tone command to the charger."""
        async with self._connection_lock:
            if not self._client or not self._client.is_connected:
                _LOGGER.warning("Cannot set alarm tone – not connected")
                return
            task_type = 0x01 if enable else 0x00
            cmd = CMD_ALARM_TONE_SET + bytearray([task_type])
            await self._client.write_gatt_char(CHAR_UUID_AF01, cmd, response=False)
            self._alarm_tone_on = enable
            _LOGGER.info("Alarm tone %s", "enabled" if enable else "disabled")

    # ------------------------------------------------------------------
    # MASS2 settings (beep, volume)
    # ------------------------------------------------------------------

    async def _async_send_mass2_settings(self, updates: dict) -> None:
        """Merge updates into the cached settings and send to the device."""
        if self._mass2_settings is None:
            _LOGGER.warning("Cannot set MASS2 settings — not yet read from device")
            return

        async with self._connection_lock:
            if not self._client or not self._client.is_connected:
                _LOGGER.warning("Cannot set MASS2 settings — not connected")
                return

            # Merge: keep all existing fields, override only the updates.
            new_settings = dict(self._mass2_settings)
            new_settings.update(updates)
            cmd = build_mass2_settings_set_req(new_settings)
            _LOGGER.debug("Sending MASS2 SettingsSetReq: %s", cmd.hex(" "))
            await self._client.write_gatt_char(CHAR_UUID_AF01, cmd, response=False)

            # Optimistic local update — the device usually echoes the new
            # state in the next SettingsResp anyway.
            self._mass2_settings = new_settings
            if self.data:
                self.async_set_updated_data(self.data)

    async def async_set_mass2_beep(self, value: int) -> None:
        """Set the MASS2 beep mode (scheduledMute field)."""
        await self._async_send_mass2_settings({"scheduledMute": value})

    async def async_set_mass2_volume(self, value: int) -> None:
        """Set the MASS2 buzzer volume (0=low, 1=medium, 2=high)."""
        await self._async_send_mass2_settings({"volume": value})

    # ------------------------------------------------------------------
    # Hardware info (one-time query after connect)
    # ------------------------------------------------------------------

    async def _fetch_hardware_info(self):
        """Fetch hardware/firmware info from the device (once)."""
        hw_response: asyncio.Queue = asyncio.Queue(maxsize=5)

        def hw_notification_callback(sender, data):
            _LOGGER.debug("AF02 notification (%d bytes): %s", len(data), data.hex(" "))
            try:
                hw_response.put_nowait(data)
            except asyncio.QueueFull:
                pass

        try:
            await self._client.start_notify(
                CHAR_UUID_AF02, hw_notification_callback
            )
            await asyncio.sleep(0.3)

            _LOGGER.debug("Sending HardwareInfoReq on AF02: %s", CMD_HARDWARE_INFO_REQ.hex(" "))
            await self._client.write_gatt_char(
                CHAR_UUID_AF02, CMD_HARDWARE_INFO_REQ, response=False
            )

            try:
                data = await asyncio.wait_for(hw_response.get(), timeout=3.0)
                _LOGGER.debug(
                    "HardwareInfo raw response (%d bytes): %s",
                    len(data),
                    data.hex(" "),
                )
                result = parse_hardware_info(data)
                if result:
                    self.hw_version, self.sw_version, self.serial_number = result
                self._hw_info_fetched = True
                _LOGGER.info(
                    "Hardware info: HW=%s, FW=%s, Serial=%s",
                    self.hw_version,
                    self.sw_version,
                    self.serial_number,
                )
            except asyncio.TimeoutError:
                _LOGGER.warning("Timeout waiting for HardwareInfoResp on AF02")
                self._hw_info_fetched = True

        except Exception as err:
            _LOGGER.warning("Failed to fetch hardware info: %s", err)

        finally:
            try:
                await self._client.stop_notify(CHAR_UUID_AF02)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # RSSI / device registry
    # ------------------------------------------------------------------

    def _get_rssi(self) -> int | None:
        """Get current RSSI from HA bluetooth scanner data."""
        service_info = bluetooth.async_last_service_info(
            self.hass, self.address, connectable=True
        )
        if service_info:
            return service_info.rssi
        return None

    def _update_device_registry(self):
        """Update device registry with hardware/firmware info."""
        from homeassistant.helpers import device_registry as dr

        if not self.hw_version and not self.sw_version:
            return

        registry = dr.async_get(self.hass)
        device = registry.async_get_device(identifiers={("isdt_air_ble", self.address)})
        if device is None:
            return

        updates = {}
        if self.sw_version:
            updates["sw_version"] = self.sw_version
        if self.hw_version:
            updates["hw_version"] = self.hw_version
        if self.serial_number:
            updates["serial_number"] = self.serial_number

        if updates:
            registry.async_update_device(device.id, **updates)
            self._device_registry_updated = True
            _LOGGER.info(
                "Updated device registry: SW=%s, HW=%s, Serial=%s",
                self.sw_version,
                self.hw_version,
                self.serial_number,
            )
