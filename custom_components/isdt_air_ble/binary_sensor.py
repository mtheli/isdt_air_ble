"""Binary sensor platform for ISDT C4 Air integration."""

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
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
    """Set up ISDT C4 Air binary sensors from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []
    for ch in range(6):
        slot = ch + 1
        entities.append(ISDTC4SlotActiveSensor(coordinator, slot, ch))

    async_add_entities(entities)


class ISDTC4SlotActiveSensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor indicating whether a slot is actively charging."""

    _attr_device_class = BinarySensorDeviceClass.BATTERY_CHARGING

    def __init__(self, coordinator, slot, channel):
        super().__init__(coordinator)
        self._channel = channel
        address = coordinator.address
        model = coordinator.model

        self._attr_unique_id = f"{address}_slot{slot}_active"
        self._attr_name = f"ISDT {model} Slot {slot}"
        self._attr_device_info = _main_device_info(address, model)

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
