"""Sensor platform for ISDT C4 Air integration."""

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    UnitOfElectricPotential,
    UnitOfElectricCurrent,
    UnitOfEnergy,
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .helpers import main_device_info, slot_device_info

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up ISDT C4 Air sensors from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []

    # Global sensors → main device
    entities.extend(
        [
            ISDTC4VoltageSensor(
                coordinator,
                "input_voltage",
                "input_voltage",
                channel=0,
            ),
            ISDTC4CurrentSensor(
                coordinator,
                "input_current",
                "input_current",
                channel=0,
            ),
            ISDTC4TotalChargingSensor(coordinator),
            ISDTC4RSSISensor(coordinator),
            ISDTC4LastSeenSensor(coordinator),
        ]
    )

    # Per-slot sensors → slot sub-devices
    for ch in range(6):
        slot = ch + 1

        entities.extend(
            [
                ISDTC4VoltageSensor(
                    coordinator,
                    "output_voltage",
                    "output_voltage",
                    channel=ch,
                    slot=slot,
                ),
                ISDTC4CurrentSensor(
                    coordinator,
                    "charging_current",
                    "charging_current",
                    channel=ch,
                    slot=slot,
                ),
                ISDTC4StatusSensor(
                    coordinator,
                    "status",
                    "work_state_str",
                    channel=ch,
                    slot_number=slot,
                ),
                ISDTC4BatterySensor(
                    coordinator,
                    "capacity",
                    "capacity_percentage",
                    channel=ch,
                    slot=slot,
                ),
                ISDTC4CapacitySensor(
                    coordinator,
                    "capacity_done",
                    "capacity_done",
                    channel=ch,
                    slot=slot,
                ),
                ISDTC4EnergySensor(
                    coordinator,
                    "energy_done",
                    "energy_done_wh",
                    channel=ch,
                    slot=slot,
                ),
                ISDTC4TimeSensor(
                    coordinator,
                    "charge_time",
                    "work_period_str",
                    channel=ch,
                    slot=slot,
                ),
                ISDTC4BatteryTypeSensor(
                    coordinator,
                    "battery_type",
                    "battery_type_str",
                    channel=ch,
                    slot=slot,
                ),
                ISDTC4IRSensor(
                    coordinator,
                    "internal_resistance",
                    "ir_mohm",
                    channel=ch,
                    slot=slot,
                ),
            ]
        )

        # Cell voltage sensors (max 16 cells per slot)
        for cell_idx in range(16):
            entities.append(
                ISDTC4CellVoltageSensor(
                    coordinator,
                    f"cell_{cell_idx + 1}",
                    channel=ch,
                    cell_index=cell_idx,
                    slot=slot,
                )
            )

    async_add_entities(entities)


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------


class ISDTC4AirSensorBase(CoordinatorEntity, SensorEntity):
    """Base class for all ISDT C4 Air sensors."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, translation_key, data_key, channel, slot=None):
        super().__init__(coordinator)
        self._data_key = data_key
        self._channel = channel
        address = coordinator.address
        model = coordinator.model

        self._attr_unique_id = f"{address}_ch{channel}_{data_key}"
        self._attr_translation_key = translation_key

        if slot is not None:
            self._attr_device_info = slot_device_info(address, slot, model)
        else:
            self._attr_device_info = main_device_info(address, model)

    @property
    def native_value(self):
        """Return the current sensor value."""
        if self.coordinator.data and self._channel in self.coordinator.data:
            return self.coordinator.data[self._channel].get(self._data_key)
        return None


# ---------------------------------------------------------------------------
# Sensor classes
# ---------------------------------------------------------------------------


class ISDTC4VoltageSensor(ISDTC4AirSensorBase):
    """Voltage sensor (V)."""

    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2


class ISDTC4CurrentSensor(ISDTC4AirSensorBase):
    """Current sensor (A)."""

    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 3


class ISDTC4StatusSensor(ISDTC4AirSensorBase):
    """Charging status sensor (empty, idle, charging, done, error)."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["empty", "idle", "charging", "done", "error"]

    def __init__(self, coordinator, translation_key, data_key, channel, slot_number):
        # Pass slot=None so it lands on the main device
        super().__init__(coordinator, translation_key, data_key, channel, slot=None)
        self._attr_translation_placeholders = {"slot": str(slot_number)}

    @property
    def native_value(self):
        """Return slot status, distinguishing empty from idle."""
        if not self.coordinator.data or self._channel not in self.coordinator.data:
            return None
        ch = self.coordinator.data[self._channel]
        state = ch.get("work_state_str")
        if state != "idle":
            return state
        # Slot is idle – check if a battery is actually present
        output_v = ch.get("output_voltage", 0.0) or 0.0
        capacity = ch.get("capacity_percentage", 0) or 0
        cell_voltages = ch.get("cell_voltages") or []
        has_cell = any(v > 0.1 for v in cell_voltages)
        if output_v > 0.5 or capacity > 0 or has_cell:
            return "idle"
        return "empty"

    @property
    def icon(self):
        """Dynamic icon based on charging status."""
        icons = {
            "empty": "mdi:battery-off-outline",
            "charging": "mdi:battery-charging",
            "done": "mdi:battery-check",
            "error": "mdi:battery-alert",
            "idle": "mdi:battery-outline",
        }
        return icons.get(self.native_value, "mdi:battery")


class ISDTC4BatterySensor(ISDTC4AirSensorBase):
    """Battery level sensor (0-100 %)."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT


class ISDTC4CapacitySensor(ISDTC4AirSensorBase):
    """Charged capacity sensor (mAh)."""

    _attr_native_unit_of_measurement = "mAh"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:battery-plus"
    _attr_suggested_display_precision = 0


class ISDTC4EnergySensor(ISDTC4AirSensorBase):
    """Charged energy sensor (Wh)."""

    _attr_native_unit_of_measurement = UnitOfEnergy.WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2


class ISDTC4TimeSensor(ISDTC4AirSensorBase):
    """Charge time as timestamp (charging start time), live-updating via frontend."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:timer-outline"

    @property
    def native_value(self):
        """Return charging start time computed from work_period."""
        if not self.coordinator.data or self._channel not in self.coordinator.data:
            return None
        from homeassistant.util import dt as dt_util
        from datetime import timedelta
        ch = self.coordinator.data[self._channel]
        work_period = ch.get("work_period", 0) or 0
        if work_period <= 0:
            return None
        return dt_util.utcnow() - timedelta(seconds=work_period)


class ISDTC4BatteryTypeSensor(ISDTC4AirSensorBase):
    """Battery chemistry sensor (NiMH, LiPo, etc.)."""

    _attr_icon = "mdi:battery-heart-variant"


class ISDTC4IRSensor(ISDTC4AirSensorBase):
    """Internal resistance sensor (mΩ)."""

    _attr_native_unit_of_measurement = "mΩ"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:omega"
    _attr_suggested_display_precision = 0


class ISDTC4CellVoltageSensor(ISDTC4AirSensorBase):
    """Individual cell voltage sensor."""

    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 3
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator, translation_key, channel, cell_index, slot=None):
        super().__init__(
            coordinator,
            translation_key,
            f"cell{cell_index}",
            channel,
            slot=slot,
        )
        self._cell_index = cell_index

    @property
    def native_value(self):
        """Return cell voltage (only if > 0.1 V, i.e. cell present)."""
        if self.coordinator.data and self._channel in self.coordinator.data:
            cell_voltages = self.coordinator.data[self._channel].get(
                "cell_voltages", []
            )
            if self._cell_index < len(cell_voltages):
                voltage = cell_voltages[self._cell_index]
                if voltage > 0.1:
                    return voltage
        return None

    @property
    def available(self):
        """Only available when a cell is actually present."""
        return self.native_value is not None


class ISDTC4TotalChargingSensor(ISDTC4AirSensorBase):
    """Total charging current across all slots."""

    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 3

    def __init__(self, coordinator):
        super().__init__(
            coordinator,
            "total_charging_current",
            "total_charging_current",
            channel=0,
        )

    @property
    def native_value(self):
        """Sum charging current across all channels."""
        if not self.coordinator.data:
            return None

        total = sum(
            ch_data.get("charging_current", 0.0)
            for ch_data in self.coordinator.data.values()
            if isinstance(ch_data, dict)
        )
        return round(total, 3)


class ISDTC4RSSISensor(ISDTC4AirSensorBase):
    """BLE signal strength sensor (dBm)."""

    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator):
        super().__init__(coordinator, "rssi", "rssi", channel=0)

    @property
    def native_value(self):
        """Return RSSI from device-level data."""
        if self.coordinator.data and "_device" in self.coordinator.data:
            return self.coordinator.data["_device"].get("rssi")
        return None


class ISDTC4LastSeenSensor(ISDTC4AirSensorBase):
    """Last successful communication timestamp sensor."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-check-outline"

    def __init__(self, coordinator):
        super().__init__(coordinator, "last_seen", "last_seen", channel=0)

    @property
    def native_value(self):
        """Return last seen timestamp as datetime."""
        if self.coordinator.data and "_device" in self.coordinator.data:
            return self.coordinator.data["_device"].get("last_seen")
        return None
