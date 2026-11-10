"""Passive coordinator for BattAir packs and plugins.

Only listens to advertisements, never connects. Packs advertise about once
a second, but the readings change at most once a minute, so listeners are
only notified when a value changes, when availability changes, or at the
latest every HEARTBEAT seconds (for RSSI).
"""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
import time

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
        self.last_seen_at: datetime | None = None
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
        # service_info.time is monotonic; turn it into wall-clock time so a
        # cached advertisement keeps its real age.
        age = max(0.0, time.monotonic() - service_info.time)
        self.last_seen_at = dt_util.utcnow() - timedelta(seconds=age)
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
