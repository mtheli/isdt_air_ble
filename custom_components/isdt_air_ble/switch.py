"""Switch platform for ISDT Air BLE integration."""

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, AdapterProtocol, DeviceType
from .helpers import main_device_info

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up ISDT switches from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []
    if coordinator.device_type == DeviceType.CHARGER:
        # A8 Air doesn't have alarm tone functionality
        if "A8" not in coordinator.model.upper():
            entities.append(ISDTC4AlarmToneSwitch(coordinator))
    elif coordinator.adapter_protocol == AdapterProtocol.PS200:
        # PS200 adapters use the charger-style alarm-tone command
        entities.append(ISDTC4AlarmToneSwitch(coordinator))
    elif coordinator.device_type == DeviceType.ADAPTER:
        entities.append(ISDTMASS2BeepSwitch(coordinator))

    async_add_entities(entities)


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
        return self.coordinator.alarm_tone_on

    @property
    def available(self) -> bool:
        """Available when we have received at least one alarm tone status."""
        return super().available and self.coordinator.alarm_tone_on is not None

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


class ISDTMASS2BeepSwitch(CoordinatorEntity, SwitchEntity):
    """Switch to toggle the MASS2 buzzer (beep on USB events)."""

    _attr_icon = "mdi:volume-high"
    _attr_has_entity_name = True
    _attr_translation_key = "beep"

    def __init__(self, coordinator):
        super().__init__(coordinator)
        address = coordinator.address
        model = coordinator.model

        self._attr_unique_id = f"{address}_beep"
        self._attr_device_info = main_device_info(address, model)

    @property
    def is_on(self) -> bool | None:
        settings = self.coordinator.mass2_settings
        if settings is None:
            return None
        return settings.get("scheduledMute", 0) != 0

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.mass2_settings is not None

    @property
    def icon(self):
        return "mdi:volume-high" if self.is_on else "mdi:volume-off"

    async def async_turn_on(self, **kwargs):
        try:
            # Use value 1 (Summer) — the default beep mode.
            await self.coordinator.async_set_mass2_beep(1)
            self.async_write_ha_state()
        except Exception as err:
            _LOGGER.error("Failed to enable MASS2 beep: %s", err)

    async def async_turn_off(self, **kwargs):
        try:
            await self.coordinator.async_set_mass2_beep(0)
            self.async_write_ha_state()
        except Exception as err:
            _LOGGER.error("Failed to disable MASS2 beep: %s", err)
