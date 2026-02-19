"""Switch platform for ISDT C4 Air integration."""

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .helpers import main_device_info

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up ISDT C4 Air switches from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ISDTC4AlarmToneSwitch(coordinator)])


class ISDTC4AlarmToneSwitch(CoordinatorEntity, SwitchEntity):
    """Switch to toggle the alarm/beep tone on the charger."""

    _attr_icon = "mdi:volume-high"
    _attr_has_entity_name = True
    _attr_translation_key = "beep"

    def __init__(self, coordinator):
        super().__init__(coordinator)
        address = coordinator.address
        model = coordinator.model

        self._attr_unique_id = f"{address}_alarm_tone"
        self._attr_device_info = main_device_info(address, model)

    @property
    def is_on(self) -> bool | None:
        """Return True if the alarm tone is enabled."""
        return self.coordinator._alarm_tone_on

    @property
    def available(self) -> bool:
        """Available when we have received at least one alarm tone status."""
        return super().available and self.coordinator._alarm_tone_on is not None

    @property
    def icon(self):
        """Dynamic icon based on beep state."""
        if self.is_on:
            return "mdi:volume-high"
        return "mdi:volume-off"

    async def async_turn_on(self, **kwargs):
        """Turn the alarm tone on."""
        try:
            await self.coordinator.async_set_alarm_tone(True)
            self.async_write_ha_state()
        except Exception as err:
            _LOGGER.error("Failed to enable alarm tone: %s", err)

    async def async_turn_off(self, **kwargs):
        """Turn the alarm tone off."""
        try:
            await self.coordinator.async_set_alarm_tone(False)
            self.async_write_ha_state()
        except Exception as err:
            _LOGGER.error("Failed to disable alarm tone: %s", err)
