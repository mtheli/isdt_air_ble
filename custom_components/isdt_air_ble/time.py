"""Time platform for ISDT Air BLE (MASS2 quiet hours and port schedules)."""

from datetime import time

from homeassistant.components.time import TimeEntity

from .const import DOMAIN, MASS2_SCHEDULE_PORT_COUNT, AdapterProtocol
from .mass2_entity import PortScheduleEntity, QuietHoursEntity
from .mass2_schedule import (
    time_to_word,
    word_to_time,
)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up ISDT time entities from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    if coordinator.adapter_protocol != AdapterProtocol.MASS2:
        return

    entities = [
        ISDTMASS2QuietHoursTime(coordinator, "quiet_hours_start", "openingTime"),
        ISDTMASS2QuietHoursTime(coordinator, "quiet_hours_end", "closingTime"),
    ]
    for port in range(1, MASS2_SCHEDULE_PORT_COUNT + 1):
        entities.append(
            ISDTMASS2PortScheduleTime(
                coordinator, port, "scheduled_output_on", "openingTime"
            )
        )
        entities.append(
            ISDTMASS2PortScheduleTime(
                coordinator, port, "scheduled_output_off", "closingTime"
            )
        )
    async_add_entities(entities)


class ISDTMASS2QuietHoursTime(QuietHoursEntity, TimeEntity):
    """Start or end of the quiet hours."""

    _attr_icon = "mdi:clock-outline"

    def __init__(self, coordinator, key: str, field: str):
        super().__init__(coordinator, key)
        self._field = field

    @property
    def native_value(self) -> time | None:
        if self._settings is None:
            return None
        return word_to_time(self._settings.get(self._field, 0))

    async def async_set_value(self, value: time) -> None:
        await self.coordinator.async_set_mass2_quiet_hours(
            **{self._field: time_to_word(value)}
        )
        self.async_write_ha_state()


class ISDTMASS2PortScheduleTime(PortScheduleEntity, TimeEntity):
    """On or off time of one USB-C port's scheduled output."""

    _attr_icon = "mdi:clock-outline"

    def __init__(self, coordinator, port: int, key: str, field: str):
        super().__init__(coordinator, port, key)
        self._field = field

    @property
    def native_value(self) -> time | None:
        if self._schedule is None:
            return None
        return word_to_time(self._schedule[self._field])

    async def async_set_value(self, value: time) -> None:
        await self.coordinator.async_set_mass2_usb_schedule(
            self._port, **{self._field: time_to_word(value)}
        )
        self.async_write_ha_state()
