"""Firmware update entity for ISDT Air BLE devices.

Periodically checks the public ISDT OTA API for newer BLE firmware
and exposes the result as a passive HA update entity (no install).
"""

import logging
from datetime import timedelta

from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityFeature,
)
from homeassistant.const import EntityCategory
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, MODEL_OTA_NAME_MAP, OTA_BLE_URL
from .helpers import main_device_info

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(hours=24)


def _normalize_ota_version(version_str: str) -> str:
    """Convert 4-part OTA version to 2-part BLE version.

    The OTA JSON uses "1.0.1.23" but the device reports "1.23"
    (sw_main.sw_sub from the HardwareInfoResp).  We take the last
    two components so versions are directly comparable.

    "1.0.1.23" → "1.23"
    "2.1"      → "2.1"  (already short)
    """
    parts = version_str.split(".")
    if len(parts) >= 4:
        return f"{parts[-2]}.{parts[-1]}"
    return version_str


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ISDT firmware update entity."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    model = entry.data.get("model", "C4 Air")
    address = entry.data["address"]

    ota_name = MODEL_OTA_NAME_MAP.get(model)
    if not ota_name:
        _LOGGER.debug("No OTA mapping for model %s, skipping update entity", model)
        return

    async_add_entities([ISDTFirmwareUpdate(coordinator, address, model, ota_name)])


class ISDTFirmwareUpdate(UpdateEntity):
    """Firmware update check for ISDT BLE devices."""

    _attr_has_entity_name = True
    _attr_device_class = UpdateDeviceClass.FIRMWARE
    _attr_entity_category = EntityCategory.CONFIG
    _attr_supported_features = UpdateEntityFeature(0)
    _attr_translation_key = "firmware"

    def __init__(self, coordinator, address: str, model: str, ota_name: str) -> None:
        """Initialize the firmware update entity."""
        self._coordinator = coordinator
        self._address = address
        self._model = model
        self._ota_name = ota_name
        self._attr_unique_id = f"{address}_firmware_update"
        self._attr_device_info = main_device_info(address, model)

        self._latest_version: str | None = None
        self._release_summary: str | None = None
        self._release_url: str | None = None
        self._last_installed: str | None = None

    async def async_added_to_hass(self) -> None:
        """Fetch OTA manifest on first load and listen for coordinator updates."""
        await super().async_added_to_hass()
        await self.async_update()

        def _on_coordinator_update() -> None:
            """Re-write state only when installed_version actually changes."""
            current = self._coordinator.sw_version
            if current != self._last_installed:
                self._last_installed = current
                self.async_write_ha_state()

        self.async_on_remove(
            self._coordinator.async_add_listener(_on_coordinator_update)
        )

    @property
    def installed_version(self) -> str | None:
        """Version currently running on the device."""
        return self._coordinator.sw_version

    @property
    def latest_version(self) -> str | None:
        """Latest version available from ISDT OTA server."""
        return self._latest_version

    @property
    def release_summary(self) -> str | None:
        """Release notes from the OTA manifest."""
        return self._release_summary

    @property
    def release_url(self) -> str | None:
        """Download URL for the firmware file."""
        return self._release_url

    async def async_update(self) -> None:
        """Fetch the OTA manifest and check for updates."""
        session = async_get_clientsession(self.hass)
        try:
            resp = await session.get(OTA_BLE_URL, timeout=30)
            resp.raise_for_status()
            data = await resp.json(content_type=None)
        except Exception as err:
            _LOGGER.debug("Failed to fetch OTA manifest: %s", err)
            return

        download_list = data.get("downloadList", {})
        for _category, devices in download_list.items():
            if not isinstance(devices, list):
                continue
            for device in devices:
                if device.get("deviceName") == self._ota_name:
                    raw_version = device.get("versionNumber", "")
                    self._latest_version = _normalize_ota_version(raw_version)
                    self._release_summary = device.get("informationEn", "").strip()
                    self._release_url = device.get("firmwareUrl")
                    _LOGGER.debug(
                        "OTA check for %s: installed=%s, latest=%s",
                        self._ota_name,
                        self.installed_version,
                        self._latest_version,
                    )
                    return

        _LOGGER.debug("Device %s not found in OTA manifest", self._ota_name)
