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
    CHAR_UUID_AF01,
    CHAR_UUID_AF02,
    CMD_ALARM_TONE_REQ,
    CMD_ALARM_TONE_SET,
    CMD_BIND_REQ,
    CMD_ELECTRIC_REQ,
    CMD_HARDWARE_INFO_REQ,
    CMD_IR_REQ,
    CMD_WORKSTATE_REQ,
    DEFAULT_SCAN_INTERVAL,
    RESP_BIND,
)
from .parser import parse_hardware_info, parse_responses

_LOGGER = logging.getLogger(__name__)
TRACE = 5  # HA supports trace level below DEBUG (10)

# Backoff limits for reconnection attempts
_BACKOFF_MIN = 5
_BACKOFF_MAX = 300

# Command interval matching manufacturer app (100ms)
_CMD_INTERVAL = 0.1


def _build_command_list() -> list[bytearray]:
    """Build the circular command list (like manufacturer app).

    Order: AlarmTone, then per channel: WorkState, Electric, IR
    Total: 1 + 6*3 = 19 commands.
    """
    commands = [CMD_ALARM_TONE_REQ]
    for ch in range(6):
        commands.append(CMD_WORKSTATE_REQ + bytearray([ch]))
        commands.append(CMD_ELECTRIC_REQ + bytearray([ch]))
        commands.append(CMD_IR_REQ + bytearray([ch]))
    return commands


class ISDTDataUpdateCoordinator(DataUpdateCoordinator):
    """Coordinator that keeps a persistent BLE connection to an ISDT charger."""

    def __init__(self, hass, address, model="C4 Air", scan_interval=DEFAULT_SCAN_INTERVAL):
        super().__init__(
            hass,
            _LOGGER,
            name=f"ISDT {model}",
            update_interval=None,  # no HA-driven polling; live loop handles everything
        )
        self.address = address
        self.model = model
        self.scan_interval_seconds = scan_interval
        self.data = {}

        # Hardware info (populated once after first connect)
        self.hw_version: str | None = None
        self.sw_version: str | None = None
        self.serial_number: str | None = None
        self._hw_info_fetched = False
        self._device_registry_updated = False

        # Alarm tone state
        self._alarm_tone_on: bool | None = None

        # Persistent BLE connection
        self._client: BleakClient | None = None
        self._connected = False
        self._response_queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._notification_started = False

        # Live monitoring
        self._connection_lock = asyncio.Lock()
        self._live_task: asyncio.Task | None = None

        # Circular command list
        self._commands = _build_command_list()

        # Bind UUID (random per instance, like manufacturer app)
        self._bind_uuid = uuid.uuid4().bytes

        # Bluetooth advertisement callback for instant reconnection
        self._device_available = asyncio.Event()
        self._unsub_bluetooth: Callable | None = None

        # Change detection: only push to HA when sensor data actually changed
        self._last_pushed_data: dict | None = None

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

        # Parsing response
        _LOGGER.debug("Received %d responses", len(responses))
        parsed, alarm_tone_on = parse_responses(responses)
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
            _LOGGER.debug(
                "Connected, services available: %d",
                len(self._client.services.services),
            )
            await asyncio.sleep(1.0)

            await self._setup_notifications()
            await self._send_bind_request()
            self._connected = True
            _LOGGER.debug("Persistent connection established to %s", self.address)

            # Fetch hardware info once
            if not self._hw_info_fetched:
                await self._fetch_hardware_info()

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
            _LOGGER.log(TRACE, "Notification received: %s", data.hex(" "))
            try:
                self._response_queue.put_nowait(data)
            except asyncio.QueueFull:
                _LOGGER.warning("Response queue full, dropping packet")

        await self._client.start_notify(CHAR_UUID_AF01, notification_callback)
        self._notification_started = True

        await asyncio.sleep(0.5)
        _LOGGER.debug("Notifications started on %s", CHAR_UUID_AF01)

    async def _send_bind_request(self):
        """Send bind request on AF02 (matching manufacturer app protocol).

        Packet: [0x18, uuid[0..15], 0x00, status=0x00]  (19 bytes)
        Response: [0x19, bound_status]  (bound_status 0=ok)
        """
        bind_response: asyncio.Queue = asyncio.Queue(maxsize=5)

        def af02_callback(sender, data):
            _LOGGER.debug("AF02 bind response (%d bytes): %s", len(data), data.hex(" "))
            try:
                bind_response.put_nowait(data)
            except asyncio.QueueFull:
                pass

        try:
            await self._client.start_notify(CHAR_UUID_AF02, af02_callback)
            await asyncio.sleep(0.3)

            cmd = bytearray([CMD_BIND_REQ]) + bytearray(self._bind_uuid) + bytearray([0x00, 0x00])
            _LOGGER.debug("Sending BindReq on AF02: %s", cmd.hex(" "))
            await self._client.write_gatt_char(CHAR_UUID_AF02, cmd, response=False)

            try:
                data = await asyncio.wait_for(bind_response.get(), timeout=3.0)
                if len(data) >= 2 and data[0] == RESP_BIND:
                    bound_status = data[1]
                    if bound_status == 0:
                        _LOGGER.info("Bind successful")
                    else:
                        _LOGGER.warning("Bind response status: %d", bound_status)
                else:
                    _LOGGER.debug("Unexpected AF02 response: %s", data.hex(" "))
            except asyncio.TimeoutError:
                _LOGGER.warning("Timeout waiting for BindResp on AF02")

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
