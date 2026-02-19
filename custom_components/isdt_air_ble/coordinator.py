"""Data update coordinator for ISDT C4 Air BLE charger."""

import asyncio
import logging
from datetime import timedelta

from bleak import BleakClient
from bleak_retry_connector import establish_connection

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.components import bluetooth
from homeassistant.core import callback
from homeassistant.util import dt as dt_util

from .const import (
    CHAR_UUID_AF01,
    CHAR_UUID_AF02,
    CMD_HARDWARE_INFO_REQ,
    CMD_ALARM_TONE_REQ,
    CMD_ELECTRIC_REQ,
    CMD_WORKSTATE_REQ,
    CMD_IR_REQ,
    DEFAULT_SCAN_INTERVAL,
)
from .parser import parse_responses, parse_hardware_info

_LOGGER = logging.getLogger(__name__)


class ISDTDataUpdateCoordinator(DataUpdateCoordinator):
    """Coordinator for polling data from the ISDT C4 Air via persistent BLE connection."""

    def __init__(self, hass, address, model="C4 Air", scan_interval=DEFAULT_SCAN_INTERVAL):
        super().__init__(
            hass,
            _LOGGER,
            name=f"ISDT {model}",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.address = address
        self.model = model
        self.data = {}  # Structure: {channel: {key: value, ...}, "_device": {...}}

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
        self._response_queue = asyncio.Queue(maxsize=100)
        self._notification_started = False

    async def async_start(self):
        """Called on coordinator start - establish connection."""
        _LOGGER.info("Starting ISDT C4 Air coordinator with persistent connection")
        await self._ensure_connected()

    async def async_shutdown(self):
        """Called on shutdown - disconnect."""
        _LOGGER.info("Shutting down ISDT C4 Air coordinator")
        await self._disconnect()

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    async def _ensure_connected(self):
        """Ensure BLE connection is established."""

        # checking if already connected
        if self._client and self._client.is_connected:
            if self._notification_started:
                _LOGGER.debug("Already connected and notifications active")
                return
            else:
                _LOGGER.warning(
                    "Client says connected but notifications not active - reconnecting"
                )
                await self._disconnect()

        _LOGGER.debug("Establishing persistent connection to %s", self.address)

        # getting device by address
        ble_device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if not ble_device:
            raise UpdateFailed(f"Device {self.address} not found")

        try:
            # Connecting to device
            self._client = await establish_connection(
                BleakClient, ble_device, "ISDT C4 Air", timeout=15
            )
            _LOGGER.debug(
                "Connected, services available: %d",
                len(self._client.services.services),
            )
            await asyncio.sleep(1.0)

            # setup notifications
            await self._setup_notifications()

            self._connected = True
            _LOGGER.info("Persistent connection established to %s", self.address)

            # Fetch hardware info once after connection
            if not self._hw_info_fetched:
                await self._fetch_hardware_info()

        except Exception as err:
            _LOGGER.error("Failed to establish connection: %s", err)
            self._connected = False
            self._client = None
            raise

    async def _setup_notifications(self):
        """Set up BLE notifications for responses."""
        if self._notification_started:
            return

        if not self._client:
            raise UpdateFailed("Client not connected, cannot setup notifications")

        def disconnected_callback(client):
            _LOGGER.warning(
                "BLE device disconnected unexpectedly: %s (was connected: %s)",
                self.address,
                self._connected,
            )
            self._connected = False
            self._notification_started = False

        self._client.set_disconnected_callback(disconnected_callback)

        def notification_callback(sender, data):
            _LOGGER.debug("Notification received: %s", data.hex(" "))
            try:
                self._response_queue.put_nowait(data)
            except asyncio.QueueFull:
                _LOGGER.warning("Response queue full, dropping packet")

        await self._client.start_notify(CHAR_UUID_AF01, notification_callback)
        self._notification_started = True

        await asyncio.sleep(0.5)
        _LOGGER.debug("Notifications started on %s", CHAR_UUID_AF01)

    async def _disconnect(self):
        """Disconnect from BLE device."""
        if self._client and self._client.is_connected:
            try:
                if self._notification_started:
                    await self._client.stop_notify(CHAR_UUID_AF01)
                    self._notification_started = False
                await self._client.disconnect()
                _LOGGER.info("Disconnected from %s", self.address)
            except Exception as err:
                _LOGGER.error("Error disconnecting: %s", err)

        self._client = None
        self._connected = False

    # ------------------------------------------------------------------
    # Hardware info (one-time query after connect)
    # ------------------------------------------------------------------

    async def _fetch_hardware_info(self):
        """Fetch hardware/firmware info from the device (once).

        The manufacturer app sends HardwareInfoReq via characteristic AF02
        (not AF01 which is used for normal polling commands).
        """
        hw_response = asyncio.Queue(maxsize=5)

        def hw_notification_callback(sender, data):
            _LOGGER.debug("AF02 notification (%d bytes): %s", len(data), data.hex(" "))
            try:
                hw_response.put_nowait(data)
            except asyncio.QueueFull:
                pass

        try:
            # Start notifications on AF02
            await self._client.start_notify(
                CHAR_UUID_AF02, hw_notification_callback
            )
            await asyncio.sleep(0.3)

            _LOGGER.debug("Sending HardwareInfoReq on AF02: %s", CMD_HARDWARE_INFO_REQ.hex(" "))
            await self._client.write_gatt_char(
                CHAR_UUID_AF02, CMD_HARDWARE_INFO_REQ, response=False
            )

            # Wait for response
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
            # Stop AF02 notifications - we only need them once
            try:
                await self._client.stop_notify(CHAR_UUID_AF02)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # RSSI / last seen
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

    # ------------------------------------------------------------------
    # Data update
    # ------------------------------------------------------------------

    async def _async_update_data(self):
        """Poll data from the charger via persistent BLE connection."""
        try:
            await self._ensure_connected()

            if not self._client or not self._client.is_connected:
                raise UpdateFailed("Client not connected after ensure_connected")

            # Drain stale responses
            while not self._response_queue.empty():
                try:
                    self._response_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

            await self._client.write_gatt_char(
                CHAR_UUID_AF01, CMD_ALARM_TONE_REQ, response=False
            )
            await asyncio.sleep(0.09)

            # Query all 6 channels (90ms between commands like manufacturer app)
            # Per channel: ElectricReq, WorkStateReq, IRReq (3 commands)
            for channel in range(6):
                if not self._client.is_connected:
                    raise UpdateFailed(f"Connection lost at channel {channel}")

                try:
                    await self._client.write_gatt_char(
                        CHAR_UUID_AF01, CMD_ELECTRIC_REQ + bytearray([channel]), response=False
                    )
                    await asyncio.sleep(0.09)

                    await self._client.write_gatt_char(
                        CHAR_UUID_AF01, CMD_WORKSTATE_REQ + bytearray([channel]), response=False
                    )
                    await asyncio.sleep(0.09)

                    await self._client.write_gatt_char(
                        CHAR_UUID_AF01, CMD_IR_REQ + bytearray([channel]), response=False
                    )
                    await asyncio.sleep(0.09)

                except Exception as write_err:
                    _LOGGER.error(
                        "Write failed on channel %d: %s (is_connected=%s)",
                        channel,
                        write_err,
                        self._client.is_connected if self._client else None,
                    )
                    raise UpdateFailed(f"Write failed: {write_err}")

            # Collect responses (expect 19: 1 alarm tone + 6 channels × 3 commands)
            expected_responses = 19
            responses = []
            try:
                while len(responses) < expected_responses:
                    data = await asyncio.wait_for(
                        self._response_queue.get(), timeout=2.0
                    )
                    responses.append(data)
            except asyncio.TimeoutError:
                _LOGGER.debug(
                    "Response timeout - got %d/%d responses",
                    len(responses),
                    expected_responses,
                )

            _LOGGER.debug("Received %d responses", len(responses))

            parsed, alarm_tone_on = parse_responses(responses)
            self._alarm_tone_on = alarm_tone_on

            # Add device-level data (RSSI, last_seen)
            parsed["_device"] = {
                "rssi": self._get_rssi(),
                "last_seen": dt_util.utcnow().isoformat(),
            }

            # Fetch hardware info if not yet done (e.g. first connect failed)
            if not self._hw_info_fetched:
                await self._fetch_hardware_info()

            # Update device registry once when hw info is available
            if self._hw_info_fetched and not self._device_registry_updated:
                self._update_device_registry()

            return parsed

        except Exception as err:
            _LOGGER.error("Error during update: %s", err)
            self._connected = False
            await self._disconnect()
            raise UpdateFailed(f"Communication error: {err}")

