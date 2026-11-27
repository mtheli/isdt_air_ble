"""Base entities for the MASS2 quiet hours and USB-C port schedules."""

from __future__ import annotations

from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .helpers import main_device_info, port_device_info


class QuietHoursEntity(CoordinatorEntity):
    """Base for the quiet hours (mute timer) entities on the main device."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_translation_key = key
        self._attr_unique_id = f"{coordinator.address}_{key}"
        self._attr_device_info = main_device_info(
            coordinator.address, coordinator.model
        )

    @property
    def _settings(self) -> dict | None:
        return self.coordinator.mass2_settings

    @property
    def available(self) -> bool:
        return self.coordinator.connected and self._settings is not None


class PortScheduleEntity(CoordinatorEntity):
    """Base for the per-port schedule entities on the USB-C port devices."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, port: int, key: str) -> None:
        super().__init__(coordinator)
        self._port = port
        self._attr_translation_key = key
        self._attr_unique_id = f"{coordinator.address}_port{port}_{key}"
        self._attr_device_info = port_device_info(
            coordinator.address, port, coordinator.model
        )

    @property
    def _schedule(self) -> dict | None:
        schedules = self.coordinator.mass2_usb_schedules
        if schedules is None:
            return None
        return schedules[self._port - 1]

    @property
    def available(self) -> bool:
        return self.coordinator.connected and self._schedule is not None
