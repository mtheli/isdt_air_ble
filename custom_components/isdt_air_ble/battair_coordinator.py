"""Passive coordinator for BattAir packs and plugins.

Only listens to advertisements, never connects. Packs advertise about once
a second, but the readings change at most once a minute, so listeners are
only notified when a value changes, when availability changes, or at the
latest every HEARTBEAT seconds. Home Assistant does not pass on repeated
identical advertisements, so a pack in storage may not trigger a callback
for a long time; last_seen_time() reads the Bluetooth history instead.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
import time

from bluetooth_data_tools import monotonic_time_coarse

from homeassistant.components.bluetooth import (
    BluetoothChange,
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
    async_last_service_info,
)
from homeassistant.components.bluetooth.passive_update_coordinator import (
    PassiveBluetoothDataUpdateCoordinator,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.util import dt as dt_util

from .battair import BATTAIR_MANUFACTURER_ID, BattAirAdvert, decode_advert

_LOGGER = logging.getLogger(__name__)

HEARTBEAT = 60  # seconds


class BattAirCoordinator(PassiveBluetoothDataUpdateCoordinator):
    """Keep the latest advertisement of one BattAir pack or plugin."""

    def __init__(self, hass: HomeAssistant, address: str) -> None:
        super().__init__(
            hass,
            _LOGGER,
            address,
            BluetoothScanningMode.PASSIVE,
            connectable=False,
        )
        self.data: BattAirAdvert | None = None
        self.rssi: int | None = None
        self._last_key: tuple | None = None
        self._last_notify = 0.0
        self._was_available = self._available

        # Start from the cached advertisement so entities have values right
        # after a restart instead of waiting for the next broadcast.
        service_info = async_last_service_info(hass, address, connectable=False)
        if service_info is not None:
            self._store(service_info)

    def _store(self, service_info: BluetoothServiceInfoBleak) -> bool:
        """Decode and store an advertisement. Return True if a value changed."""
        payload = service_info.manufacturer_data.get(BATTAIR_MANUFACTURER_ID)
        advert = decode_advert(payload)
        self.rssi = service_info.rssi
        if advert is None:
            if payload is not None:
                _LOGGER.debug(
                    "%s: ignoring advertisement %s", self.address, payload.hex(" ")
                )
            return False
        key = advert.values_key()
        if key == self._last_key:
            return False
        if self._last_key is None or advert.device_type != self.data.device_type:
            _LOGGER.debug(
                "%s: %s, device type %s, payload %s",
                self.address, advert.model, advert.device_type, payload.hex(" "),
            )
        self._last_key = key
        self.data = advert
        return True

    def last_seen_time(self) -> datetime | None:
        """Wall-clock time of the last advertisement Home Assistant received.

        While the device is in range this comes from the Bluetooth history;
        once it is gone, from the time recorded when it went unavailable.
        """
        info = async_last_service_info(self.hass, self.address, connectable=False)
        monotonic = info.time if info is not None else self._last_unavailable_time
        if not monotonic:
            return None
        age = max(0.0, monotonic_time_coarse() - monotonic)
        return dt_util.utcnow() - timedelta(seconds=age)

    @callback
    def _async_handle_bluetooth_event(
        self,
        service_info: BluetoothServiceInfoBleak,
        change: BluetoothChange,
    ) -> None:
        """Store the advertisement and notify entities when needed."""
        self._available = True
        changed = self._store(service_info)
        now = time.monotonic()
        if (
            changed
            or not self._was_available
            or now - self._last_notify >= HEARTBEAT
        ):
            self._was_available = True
            self._last_notify = now
            self.async_update_listeners()

    @callback
    def _async_handle_unavailable(
        self, service_info: BluetoothServiceInfoBleak
    ) -> None:
        """Mark the device unavailable and notify entities once."""
        self._was_available = False
        super()._async_handle_unavailable(service_info)
