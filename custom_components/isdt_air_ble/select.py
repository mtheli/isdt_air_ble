"""Select platform for ISDT Air BLE integration."""

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MASS2_SCHEDULE_PORT_COUNT, AdapterProtocol
from .helpers import main_device_info
from .mass2_entity import PortScheduleEntity, QuietHoursEntity
from .mass2_schedule import (
    DAY_PRESETS,
    DAYS_CUSTOM,
    days_list,
    days_option,
    with_days,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up ISDT select entities from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []
    # Volume control is a MASS2 settings feature; PS200 adapters only
    # have the plain alarm-tone switch.
    if coordinator.adapter_protocol == AdapterProtocol.MASS2:
        entities.append(ISDTMASS2VolumeSelect(coordinator))
        entities.append(ISDTMASS2QuietHoursDaysSelect(coordinator))
        for port in range(1, MASS2_SCHEDULE_PORT_COUNT + 1):
            entities.append(ISDTMASS2PortScheduleDaysSelect(coordinator, port))

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
        return self.coordinator.connected and self.coordinator.mass2_settings is not None

    async def async_select_option(self, option: str) -> None:
        value = self._OPTION_TO_VALUE.get(option)
        if value is None:
            return
        try:
            await self.coordinator.async_set_mass2_volume(value)
            self.async_write_ha_state()
        except Exception as err:
            _LOGGER.error("Failed to set MASS2 volume: %s", err)


class _DaysSelectMixin:
    """Day presets; "custom" is listed only while the device has another
    combination (set in the vendor app or with the set_schedule action)."""

    _attr_icon = "mdi:calendar-week"

    def _repeat_value(self) -> int | None:
        raise NotImplementedError

    @property
    def options(self) -> list[str]:
        repeat = self._repeat_value()
        if repeat is not None and days_option(repeat) == DAYS_CUSTOM:
            return [*DAY_PRESETS, DAYS_CUSTOM]
        return list(DAY_PRESETS)

    @property
    def current_option(self) -> str | None:
        repeat = self._repeat_value()
        return None if repeat is None else days_option(repeat)

    @property
    def extra_state_attributes(self):
        repeat = self._repeat_value()
        return None if repeat is None else {"days": days_list(repeat)}


class ISDTMASS2QuietHoursDaysSelect(_DaysSelectMixin, QuietHoursEntity, SelectEntity):
    """Days of the quiet hours."""

    def __init__(self, coordinator):
        super().__init__(coordinator, "quiet_hours_days")

    def _repeat_value(self) -> int | None:
        if self._settings is None:
            return None
        return self._settings.get("operationSoundRepeatDay", 0)

    async def async_select_option(self, option: str) -> None:
        if option not in DAY_PRESETS:
            return  # "custom" just shows the current combination
        await self.coordinator.async_set_mass2_quiet_hours(
            operationSoundRepeatDay=with_days(self._repeat_value(), DAY_PRESETS[option])
        )
        self.async_write_ha_state()


class ISDTMASS2PortScheduleDaysSelect(_DaysSelectMixin, PortScheduleEntity, SelectEntity):
    """Days of one USB-C port's scheduled output."""

    def __init__(self, coordinator, port: int):
        super().__init__(coordinator, port, "scheduled_output_days")

    def _repeat_value(self) -> int | None:
        if self._schedule is None:
            return None
        return self._schedule["repeat"]

    async def async_select_option(self, option: str) -> None:
        if option not in DAY_PRESETS:
            return  # "custom" just shows the current combination
        await self.coordinator.async_set_mass2_usb_schedule(
            self._port, repeat=with_days(self._repeat_value(), DAY_PRESETS[option])
        )
        self.async_write_ha_state()
