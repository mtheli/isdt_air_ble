"""Switch platform for ISDT Air BLE integration."""

import logging
from datetime import time

import voluptuous as vol

from homeassistant.components.switch import SwitchEntity
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    MASS2_SCHEDULE_PORT_COUNT,
    MASS2_SCHEDULE_STATE_FORCED,
    AdapterProtocol,
    DeviceType,
)
from .helpers import main_device_info
from .mass2_entity import PortScheduleEntity, QuietHoursEntity
from .mass2_schedule import (
    WEEKDAYS,
    build_repeat,
    time_to_word,
    repeat_enabled,
    with_enabled,
)

_LOGGER = logging.getLogger(__name__)

SERVICE_SET_SCHEDULE = "set_schedule"
SET_SCHEDULE_SCHEMA = {
    vol.Required("days"): vol.All(
        cv.ensure_list, [vol.In(WEEKDAYS)], vol.Length(min=1)
    ),
    vol.Optional("start_time"): cv.time,
    vol.Optional("end_time"): cv.time,
    vol.Optional("enabled"): cv.boolean,
}


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
        if coordinator.adapter_protocol == AdapterProtocol.MASS2:
            entities.append(ISDTMASS2QuietHoursSwitch(coordinator))
            for port in range(1, MASS2_SCHEDULE_PORT_COUNT + 1):
                entities.append(ISDTMASS2PortScheduleSwitch(coordinator, port))
                entities.append(ISDTMASS2PortForceOnSwitch(coordinator, port))
            # Set days, times and on/off of one schedule in a single write.
            # Targets the "Quiet hours" and "Scheduled output" switches.
            entity_platform.async_get_current_platform().async_register_entity_service(
                SERVICE_SET_SCHEDULE,
                SET_SCHEDULE_SCHEMA,
                "async_set_schedule",
            )

    async_add_entities(entities)


class _NoScheduleMixin:
    """For switches that are not a schedule: reject set_schedule clearly."""

    async def async_set_schedule(self, **kwargs) -> None:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="not_a_schedule",
            translation_placeholders={"entity_id": self.entity_id},
        )


class ISDTC4AlarmToneSwitch(_NoScheduleMixin, CoordinatorEntity, SwitchEntity):
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
        return self.coordinator.connected and self.coordinator.alarm_tone_on is not None

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


class ISDTMASS2BeepSwitch(_NoScheduleMixin, CoordinatorEntity, SwitchEntity):
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
        return self.coordinator.connected and self.coordinator.mass2_settings is not None

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


class ISDTMASS2QuietHoursSwitch(QuietHoursEntity, SwitchEntity):
    """Quiet hours (mute timer) on/off; days and times are kept."""

    _attr_icon = "mdi:bell-sleep"

    def __init__(self, coordinator):
        super().__init__(coordinator, "quiet_hours")

    @property
    def is_on(self) -> bool | None:
        if self._settings is None:
            return None
        return repeat_enabled(self._settings.get("operationSoundRepeatDay", 0))

    async def _async_set(self, enabled: bool) -> None:
        repeat = self._settings.get("operationSoundRepeatDay", 0)
        await self.coordinator.async_set_mass2_quiet_hours(
            operationSoundRepeatDay=with_enabled(repeat, enabled)
        )
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs):
        await self._async_set(True)

    async def async_turn_off(self, **kwargs):
        await self._async_set(False)

    async def async_set_schedule(
        self,
        days: list[str],
        start_time: time | None = None,
        end_time: time | None = None,
        enabled: bool | None = None,
    ) -> None:
        updates = {
            "operationSoundRepeatDay": build_repeat(
                self._settings.get("operationSoundRepeatDay", 0), days, enabled
            )
        }
        if start_time is not None:
            updates["openingTime"] = time_to_word(start_time)
        if end_time is not None:
            updates["closingTime"] = time_to_word(end_time)
        await self.coordinator.async_set_mass2_quiet_hours(**updates)
        self.async_write_ha_state()


class ISDTMASS2PortScheduleSwitch(PortScheduleEntity, SwitchEntity):
    """Scheduled output of one USB-C port on/off; days and times are kept."""

    _attr_icon = "mdi:timer-outline"

    def __init__(self, coordinator, port: int):
        super().__init__(coordinator, port, "scheduled_output")

    @property
    def is_on(self) -> bool | None:
        if self._schedule is None:
            return None
        return repeat_enabled(self._schedule["repeat"])

    async def _async_set(self, enabled: bool) -> None:
        await self.coordinator.async_set_mass2_usb_schedule(
            self._port, repeat=with_enabled(self._schedule["repeat"], enabled)
        )
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs):
        await self._async_set(True)

    async def async_turn_off(self, **kwargs):
        await self._async_set(False)

    async def async_set_schedule(
        self,
        days: list[str],
        start_time: time | None = None,
        end_time: time | None = None,
        enabled: bool | None = None,
    ) -> None:
        updates = {"repeat": build_repeat(self._schedule["repeat"], days, enabled)}
        if start_time is not None:
            updates["openingTime"] = time_to_word(start_time)
        if end_time is not None:
            updates["closingTime"] = time_to_word(end_time)
        await self.coordinator.async_set_mass2_usb_schedule(self._port, **updates)
        self.async_write_ha_state()


class ISDTMASS2PortForceOnSwitch(_NoScheduleMixin, PortScheduleEntity, SwitchEntity):
    """Keep a USB-C port on while its schedule would switch it off.

    On: force-on command. The device clears it by itself on the next day
    (same-day windows) or on reboot, so the state comes from the device's
    per-port schedule state, not from what was last sent.
    Off: the firmware has no command for this; the schedule is switched off
    and on again, which clears the flag (two flash writes on the device).
    Only available while the port's schedule is on.
    """

    _attr_icon = "mdi:power-plug-outline"

    def __init__(self, coordinator, port: int):
        super().__init__(coordinator, port, "force_on")

    @property
    def _state(self) -> int | None:
        data = self.coordinator.data
        if not data or (self._port - 1) not in data:
            return None
        return data[self._port - 1].get("schedule_state")

    @property
    def available(self) -> bool:
        return (
            super().available
            and repeat_enabled(self._schedule["repeat"])
            and self._state is not None
        )

    @property
    def is_on(self) -> bool | None:
        state = self._state
        if state is None:
            return None
        return state == MASS2_SCHEDULE_STATE_FORCED

    async def async_turn_on(self, **kwargs):
        await self.coordinator.async_mass2_force_on(self._port)

    async def async_turn_off(self, **kwargs):
        await self.coordinator.async_mass2_end_force_on(self._port)
