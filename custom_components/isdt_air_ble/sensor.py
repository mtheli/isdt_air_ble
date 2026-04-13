"""Sensor platform for ISDT Air BLE integration."""

import logging

from homeassistant.components import bluetooth
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    UnitOfElectricPotential,
    UnitOfElectricCurrent,
    UnitOfEnergy,
    UnitOfPower,
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, DeviceType, MASS2_PORT_COUNT, MASS2_PORT_LABELS
from .helpers import main_device_info, slot_device_info, port_device_info

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up ISDT sensor entities from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [ISDTC4RSSISensor(coordinator)]

    if coordinator.device_type == DeviceType.ADAPTER:
        _setup_adapter_sensors(coordinator, entities)
    else:
        _setup_charger_sensors(coordinator, entities)

    async_add_entities(entities)


def _setup_charger_sensors(coordinator, entities):
    """Set up sensors for charger devices (C4 Air, A8 Air, etc.)."""
    is_a8_air = "A8" in coordinator.model.upper()

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
        ]
    )

    for ch in range(coordinator.channel_count):
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

        # A8 Air doesn't support individual cell voltage monitoring
        if not is_a8_air:
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


def _setup_adapter_sensors(coordinator, entities):
    """Set up sensors for adapter devices (MASS2)."""
    for port in range(MASS2_PORT_COUNT):
        port_num = port + 1
        # Per-port detail sensors → port sub-device
        entities.extend(
            [
                ISDTMASS2VoltageSensor(coordinator, port, port_num),
                ISDTMASS2CurrentSensor(coordinator, port, port_num),
                ISDTMASS2PowerSensor(coordinator, port, port_num),
                ISDTMASS2ProtocolSensor(coordinator, port, port_num),
            ]
        )
        # Port status overview → main device
        entities.append(ISDTMASS2PortStatusSensor(coordinator, port, port_num))

    entities.append(ISDTMASS2TotalPowerSensor(coordinator))


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
    def available(self) -> bool:
        """Return True if coordinator is successfully updating."""
        return self.coordinator.last_update_success

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

    @property
    def available(self) -> bool:
        """Only show battery sensor when a battery is actually connected."""
        if not self.coordinator.last_update_success:
            return False
        
        if not self.coordinator.data or self._channel not in self.coordinator.data:
            return False
        
        ch = self.coordinator.data[self._channel]
        state = ch.get("work_state_str")
        
        # Battery is present if charging, done, or in error state
        if state in ("charging", "done", "error"):
            return True
        
        # For idle state, check if there's actually a battery present
        output_v = ch.get("output_voltage", 0.0) or 0.0
        capacity = ch.get("capacity_percentage", 0) or 0
        
        return output_v > 0.5 or capacity > 0


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
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 2


class ISDTC4TimeSensor(ISDTC4AirSensorBase):
    """Charge time as timestamp (charging start time), live-updating via frontend."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:timer-outline"

    def __init__(self, coordinator, translation_key, data_key, channel, slot=None):
        super().__init__(coordinator, translation_key, data_key, channel, slot=slot)
        self._frozen_start = None

    @property
    def native_value(self):
        """Return charging start time computed from work_period.

        Frozen when status is 'done' so the displayed duration stops at the
        final charge time instead of continuing to count up.
        """
        if not self.coordinator.data or self._channel not in self.coordinator.data:
            return None
        from homeassistant.util import dt as dt_util
        from datetime import timedelta
        ch = self.coordinator.data[self._channel]
        work_period = ch.get("work_period", 0) or 0
        work_state = ch.get("work_state_str")

        if work_period <= 0 or work_state in ("empty", "idle"):
            self._frozen_start = None
            return None

        if work_state == "done":
            if self._frozen_start is None:
                self._frozen_start = dt_util.utcnow() - timedelta(seconds=work_period)
            return self._frozen_start

        # charging / error: live computation, clear any frozen state
        self._frozen_start = None
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


# ---------------------------------------------------------------------------
# MASS2 adapter sensor classes
# ---------------------------------------------------------------------------


class ISDTMASS2SensorBase(CoordinatorEntity, SensorEntity):
    """Base class for MASS2 port sensors."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, translation_key, data_key, channel, port_num):
        super().__init__(coordinator)
        self._data_key = data_key
        self._channel = channel
        address = coordinator.address
        model = coordinator.model

        self._attr_unique_id = f"{address}_port{port_num}_{data_key}"
        self._attr_translation_key = translation_key
        self._attr_device_info = port_device_info(address, port_num, model)

    @property
    def available(self) -> bool:
        service_info = bluetooth.async_last_service_info(
            self.hass, self.coordinator.address, connectable=True
        )
        return service_info is not None

    @property
    def native_value(self):
        if self.coordinator.data and self._channel in self.coordinator.data:
            return self.coordinator.data[self._channel].get(self._data_key)
        return None


class ISDTMASS2VoltageSensor(ISDTMASS2SensorBase):
    """Per-port voltage sensor."""

    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator, channel, port_num):
        super().__init__(coordinator, "port_voltage", "voltage", channel, port_num)


class ISDTMASS2CurrentSensor(ISDTMASS2SensorBase):
    """Per-port current sensor."""

    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 3

    def __init__(self, coordinator, channel, port_num):
        super().__init__(coordinator, "port_current", "current", channel, port_num)


class ISDTMASS2PowerSensor(ISDTMASS2SensorBase):
    """Per-port power sensor (computed V * A)."""

    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator, channel, port_num):
        super().__init__(coordinator, "port_power", "power", channel, port_num)


class ISDTMASS2ProtocolSensor(ISDTMASS2SensorBase):
    """Per-port charging protocol sensor (None/PD/FastCharge)."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["none", "pd", "fast_charge"]
    _attr_icon = "mdi:lightning-bolt"

    def __init__(self, coordinator, channel, port_num):
        super().__init__(coordinator, "port_protocol", "protocol_str", channel, port_num)


class ISDTMASS2PortStatusSensor(CoordinatorEntity, SensorEntity):
    """Per-port status sensor on the main device (overview).

    States:
        off    – no voltage on the port
        idle   – voltage present but no sink drawing power
        active – device-reported active state (status == 1)
    """

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["off", "idle", "active"]
    _attr_has_entity_name = True
    _attr_translation_key = "port_status"

    def __init__(self, coordinator, channel, port_num):
        super().__init__(coordinator)
        self._channel = channel
        self._port_num = port_num
        address = coordinator.address
        model = coordinator.model

        label = MASS2_PORT_LABELS[port_num - 1] if 1 <= port_num <= len(MASS2_PORT_LABELS) else f"Port {port_num}"
        self._attr_unique_id = f"{address}_port{port_num}_status"
        self._attr_translation_placeholders = {"port": label}
        self._attr_device_info = main_device_info(address, model)

    @property
    def available(self) -> bool:
        service_info = bluetooth.async_last_service_info(
            self.hass, self.coordinator.address, connectable=True
        )
        return service_info is not None

    @property
    def native_value(self):
        if not self.coordinator.data or self._channel not in self.coordinator.data:
            return None
        ch = self.coordinator.data[self._channel]

        # Trust the device-reported status byte.
        # status == 1 means actively delivering power to a sink.
        if ch.get("status") == 1:
            return "active"

        # status != 1: distinguish between "voltage present but no sink" (idle)
        # and "no voltage at all" (off)
        voltage = ch.get("voltage", 0) or 0
        if voltage > 0:
            return "idle"
        return "off"

    @property
    def icon(self):
        state = self.native_value
        icons = {
            "off": "mdi:power-plug-off-outline",
            "idle": "mdi:power-plug-outline",
            "active": "mdi:power-plug",
        }
        return icons.get(state, "mdi:power-plug-outline")

    @property
    def extra_state_attributes(self):
        if not self.coordinator.data or self._channel not in self.coordinator.data:
            return None
        ch = self.coordinator.data[self._channel]
        attrs = {}
        protocol = ch.get("protocol_str")
        if protocol and protocol != "none":
            attrs["protocol"] = protocol
        voltage = ch.get("voltage")
        if voltage and voltage > 0:
            attrs["voltage"] = f"{voltage:.2f} V"
        current = ch.get("current")
        if current and current > 0:
            attrs["current"] = f"{current:.3f} A"
        power = ch.get("power")
        if power and power > 0:
            attrs["power"] = f"{power:.1f} W"
        return attrs if attrs else None


class ISDTMASS2TotalPowerSensor(CoordinatorEntity, SensorEntity):
    """Total power across all USB ports.

    Reads the device-reported total (byte 2 of WorkStatusResp). Falls
    back to summing the
    per-port power values if the device value is not yet available.
    """

    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator):
        super().__init__(coordinator)
        address = coordinator.address
        model = coordinator.model
        self._attr_unique_id = f"{address}_total_power"
        self._attr_translation_key = "total_power"
        self._attr_device_info = main_device_info(address, model)

    @property
    def available(self) -> bool:
        service_info = bluetooth.async_last_service_info(
            self.hass, self.coordinator.address, connectable=True
        )
        return service_info is not None

    @property
    def native_value(self):
        if not self.coordinator.data:
            return None
        device_total = self.coordinator.data.get("_total_power")
        if device_total is not None:
            return device_total
        # Fallback for backwards compatibility / older parser data
        total = sum(
            ch_data.get("power", 0.0)
            for ch_data in self.coordinator.data.values()
            if isinstance(ch_data, dict)
        )
        return round(total, 1)


