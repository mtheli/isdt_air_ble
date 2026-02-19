"""Switch platform for ISDT C4 Air integration."""

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.device_registry import (
    DeviceInfo,
    CONNECTION_BLUETOOTH,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def _main_device_info(address: str, model: str = "C4 Air") -> DeviceInfo:
    """Device info for the main ISDT device."""
    return DeviceInfo(
        identifiers={(DOMAIN, address)},
        connections={(CONNECTION_BLUETOOTH, address)},
        name=f"ISDT {model}",
        manufacturer="ISDT",
        model=model,
    )


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up ISDT C4 Air switches from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ISDTC4AlarmToneSwitch(coordinator)])


class ISDTC4AlarmToneSwitch(CoordinatorEntity, SwitchEntity):
    """Switch to toggle the alarm/beep tone on the charger."""

    _attr_icon = "mdi:volume-high"

    def __init__(self, coordinator):
        super().__init__(coordinator)
        address = coordinator.address
        model = coordinator.model

        self._attr_unique_id = f"{address}_alarm_tone"
        self._attr_name = f"ISDT {model} Beep"
        self._attr_device_info = _main_device_info(address, model)

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
        await self._send_alarm_tone_command(True)

    async def async_turn_off(self, **kwargs):
        """Turn the alarm tone off."""
        await self._send_alarm_tone_command(False)

    async def _send_alarm_tone_command(self, enable: bool):
        """Send AlarmToneTaskReq: [0x13, 0x9C, task_type].

        task_type: 0x01 = on, 0x00 = off.
        Response CMD 0x9D, data[2] == 0xFF means success.
        """
        coordinator = self.coordinator
        task_type = 0x01 if enable else 0x00
        cmd = bytearray([0x13, 0x9C, task_type])

        try:
            await coordinator._ensure_connected()
            await coordinator._client.write_gatt_char(
                coordinator._char_uuid_af01, cmd, response=False
            )
            # Optimistically update local state
            coordinator._alarm_tone_on = enable
            self.async_write_ha_state()
            _LOGGER.info("Alarm tone %s", "enabled" if enable else "disabled")
        except Exception as err:
            _LOGGER.error("Failed to send alarm tone command: %s", err)
