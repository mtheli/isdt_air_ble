"""Binary sensor platform for ISDT C4 Air integration."""

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .helpers import slot_device_info

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up ISDT C4 Air binary sensors from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []
    for ch in range(6):
        slot = ch + 1
        entities.append(ISDTC4SlotActiveSensor(coordinator, slot, ch))
        entities.append(ISDTC4BatteryInsertedSensor(coordinator, slot, ch))
        entities.append(ISDTC4SlotErrorSensor(coordinator, slot, ch))

    async_add_entities(entities)


class ISDTC4SlotActiveSensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor indicating whether a slot is actively charging."""

    _attr_device_class = BinarySensorDeviceClass.BATTERY_CHARGING
    _attr_has_entity_name = True
    _attr_translation_key = "slot_charging"

    def __init__(self, coordinator, slot, channel):
        super().__init__(coordinator)
        self._channel = channel
        self._slot = slot
        address = coordinator.address
        model = coordinator.model

        self._attr_unique_id = f"{address}_slot{slot}_active"
        self._attr_device_info = slot_device_info(address, slot, model)

    @property
    def is_on(self):
        """Return True if the slot is actively charging."""
        if self.coordinator.data and self._channel in self.coordinator.data:
            state = self.coordinator.data[self._channel].get("work_state_str")
            return state == "charging"
        return False

    @property
    def icon(self):
        """Dynamic icon based on slot state."""
        if self.coordinator.data and self._channel in self.coordinator.data:
            state = self.coordinator.data[self._channel].get("work_state_str")
            if state == "charging":
                return "mdi:battery-charging"
            elif state == "done":
                return "mdi:battery-check"
            elif state == "error":
                return "mdi:battery-alert"
        return "mdi:battery-outline"

    @property
    def extra_state_attributes(self):
        """Add slot summary data as attributes."""
        if not self.coordinator.data or self._channel not in self.coordinator.data:
            return None

        ch_data = self.coordinator.data[self._channel]
        attrs = {}

        status = ch_data.get("work_state_str")
        if status and status != "idle":
            attrs["status"] = status
            if ch_data.get("battery_type_str"):
                attrs["battery_type"] = ch_data["battery_type_str"]
            if ch_data.get("capacity_percentage") is not None:
                attrs["capacity"] = f"{ch_data['capacity_percentage']}%"
            if ch_data.get("capacity_done") is not None:
                attrs["charged"] = f"{ch_data['capacity_done']} mAh"
            if ch_data.get("work_period_str"):
                attrs["time"] = ch_data["work_period_str"]
            if ch_data.get("ir_mohm") is not None:
                attrs["ir"] = f"{ch_data['ir_mohm']:.0f} mΩ"

        return attrs if attrs else None


class ISDTC4BatteryInsertedSensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor indicating whether a battery is inserted in the slot."""

    _attr_device_class = BinarySensorDeviceClass.PLUG
    _attr_has_entity_name = True
    _attr_translation_key = "battery_inserted"

    def __init__(self, coordinator, slot, channel):
        super().__init__(coordinator)
        self._channel = channel
        self._slot = slot
        address = coordinator.address
        model = coordinator.model

        self._attr_unique_id = f"{address}_slot{slot}_battery_inserted"
        self._attr_device_info = slot_device_info(address, slot, model)

    @property
    def is_on(self):
        """Return True if a battery is present in the slot."""
        if not self.coordinator.data or self._channel not in self.coordinator.data:
            return False
        ch = self.coordinator.data[self._channel]
        state = ch.get("work_state_str")
        if state in ("charging", "done", "error"):
            return True
        output_v = ch.get("output_voltage", 0.0) or 0.0
        capacity = ch.get("capacity_percentage", 0) or 0
        cell_voltages = ch.get("cell_voltages") or []
        has_cell = any(v > 0.1 for v in cell_voltages)
        return output_v > 0.5 or capacity > 0 or has_cell


class ISDTC4SlotErrorSensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor indicating a charging error on the slot."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_has_entity_name = True
    _attr_translation_key = "slot_error"

    def __init__(self, coordinator, slot, channel):
        super().__init__(coordinator)
        self._channel = channel
        self._slot = slot
        address = coordinator.address
        model = coordinator.model

        self._attr_unique_id = f"{address}_slot{slot}_error"
        self._attr_device_info = slot_device_info(address, slot, model)

    @property
    def is_on(self):
        """Return True if the slot has an error."""
        if not self.coordinator.data or self._channel not in self.coordinator.data:
            return False
        ch = self.coordinator.data[self._channel]
        state = ch.get("work_state_str")
        error_code = ch.get("error_code", 0) or 0
        return state == "error" or error_code != 0
