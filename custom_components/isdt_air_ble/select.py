"""Select platform for ISDT Air BLE integration."""

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, DeviceType
from .helpers import main_device_info

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up ISDT select entities from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []
    if coordinator.device_type == DeviceType.ADAPTER:
        entities.append(ISDTMASS2VolumeSelect(coordinator))

    async_add_entities(entities)


class ISDTMASS2VolumeSelect(CoordinatorEntity, SelectEntity):
    """Select entity for the MASS2 buzzer volume."""

    _attr_has_entity_name = True
    _attr_translation_key = "volume"
    _attr_options = ["low", "medium", "high"]
    _attr_icon = "mdi:volume-medium"

    _VALUE_TO_OPTION = {0: "low", 1: "medium", 2: "high"}
    _OPTION_TO_VALUE = {v: k for k, v in _VALUE_TO_OPTION.items()}

    def __init__(self, coordinator):
        super().__init__(coordinator)
        address = coordinator.address
        model = coordinator.model

        self._attr_unique_id = f"{address}_volume"
        self._attr_device_info = main_device_info(address, model)

    @property
    def current_option(self) -> str | None:
        settings = self.coordinator.mass2_settings
        if settings is None:
            return None
        return self._VALUE_TO_OPTION.get(settings.get("volume", 0))

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.mass2_settings is not None

    async def async_select_option(self, option: str) -> None:
        value = self._OPTION_TO_VALUE.get(option)
        if value is None:
            return
        try:
            await self.coordinator.async_set_mass2_volume(value)
            self.async_write_ha_state()
        except Exception as err:
            _LOGGER.error("Failed to set MASS2 volume: %s", err)
