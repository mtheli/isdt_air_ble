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
    UnitOfTime,
    PERCENTAGE,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []

    # Globale Sensoren
    entities.extend(
        [
            ISDTC4VoltageSensor(
                coordinator, "Input Voltage", "input_voltage", channel=0
            ),
            ISDTC4CurrentSensor(
                coordinator, "Input Current", "input_current", channel=0
            ),
        ]
    )

    # Gesamt-Ladestrom über alle Slots
    entities.append(ISDTC4TotalChargingSensor(coordinator))

    # Pro Slot (Channel 0–5)
    for ch in range(6):
        slot = ch + 1

        # Elektrische Sensoren
        entities.extend(
            [
                ISDTC4VoltageSensor(
                    coordinator,
                    f"Slot {slot} Output Voltage",
                    "output_voltage",
                    channel=ch,
                ),
                ISDTC4CurrentSensor(
                    coordinator,
                    f"Slot {slot} Charging Current",
                    "charging_current",
                    channel=ch,
                ),
            ]
        )

        # WorkState Sensoren (NEU!)
        entities.extend(
            [
                # Status
                ISDTC4StatusSensor(coordinator, f"Slot {slot} Status", channel=ch),
                # Kapazität Prozent
                ISDTC4PercentageSensor(
                    coordinator,
                    f"Slot {slot} Capacity",
                    "capacity_percentage",
                    channel=ch,
                ),
                # Kapazität mAh
                ISDTC4CapacitySensor(
                    coordinator, f"Slot {slot} Capacity Done", channel=ch
                ),
                # Energie Wh
                ISDTC4EnergySensor(coordinator, f"Slot {slot} Energy Done", channel=ch),
                # Ladezeit
                ISDTC4TimeSensor(coordinator, f"Slot {slot} Charge Time", channel=ch),
                # Akkutyp
                ISDTC4BatteryTypeSensor(
                    coordinator, f"Slot {slot} Battery Type", channel=ch
                ),
            ]
        )

        # Cell Voltage Sensoren (max 16 Zellen pro Slot)
        for cell_idx in range(16):
            entities.append(
                ISDTC4CellVoltageSensor(
                    coordinator,
                    f"Slot {slot} Cell {cell_idx + 1}",
                    channel=ch,
                    cell_index=cell_idx,
                )
            )

    async_add_entities(entities)


class ISDTC4AirSensorBase(CoordinatorEntity, SensorEntity):
    """Basis-Klasse für ISDT C4 Air Sensoren."""

    def __init__(self, coordinator, name_suffix, data_key, channel):
        super().__init__(coordinator)
        self._data_key = data_key
        self._channel = channel
        address = coordinator.address

        self._attr_unique_id = f"{address}_ch{self._channel}_{self._data_key}"
        self._attr_name = f"ISDT C4 Air {name_suffix}"

        self._attr_device_info = {
            "identifiers": {(DOMAIN, address)},
            "name": "ISDT C4 Air",
            "manufacturer": "ISDT",
            "model": "C4 Air",
        }

    @property
    def native_value(self):
        """Gibt den aktuellen Sensorwert zurück."""
        if self.coordinator.data and self._channel in self.coordinator.data:
            return self.coordinator.data[self._channel].get(self._data_key)
        return None


class ISDTC4VoltageSensor(ISDTC4AirSensorBase):
    """Spannungssensor."""

    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2  # Zeige 2 Nachkommastellen (z.B. 1.39V)


class ISDTC4CurrentSensor(ISDTC4AirSensorBase):
    """Stromsensor."""

    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 3  # Zeige 3 Nachkommastellen (z.B. 0.958A)


class ISDTC4StatusSensor(CoordinatorEntity, SensorEntity):
    """Status-Sensor (idle, charging, done, error, etc.)."""

    def __init__(self, coordinator, name_suffix, channel):
        super().__init__(coordinator)
        self._channel = channel
        address = coordinator.address

        self._attr_unique_id = f"{address}_ch{channel}_status"
        self._attr_name = f"ISDT C4 Air {name_suffix}"
        self._attr_icon = "mdi:battery-charging"

        self._attr_device_info = {
            "identifiers": {(DOMAIN, address)},
            "name": "ISDT C4 Air",
            "manufacturer": "ISDT",
            "model": "C4 Air",
        }

    @property
    def native_value(self):
        """Gibt den Status-String zurück."""
        if self.coordinator.data and self._channel in self.coordinator.data:
            return self.coordinator.data[self._channel].get("work_state_str")
        return None

    @property
    def icon(self):
        """Icon basierend auf Status."""
        state = self.native_value
        if state == "charging":
            return "mdi:battery-charging"
        elif state == "done":
            return "mdi:battery-check"
        elif state == "error":
            return "mdi:battery-alert"
        elif state == "idle":
            return "mdi:battery-outline"
        return "mdi:battery"


class ISDTC4PercentageSensor(ISDTC4AirSensorBase):
    """Prozent-Sensor (0-100%)."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:battery-charging-50"


class ISDTC4CapacitySensor(CoordinatorEntity, SensorEntity):
    """Kapazitäts-Sensor (mAh)."""

    _attr_native_unit_of_measurement = "mAh"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:battery-plus"
    _attr_suggested_display_precision = 0  # Ganze Zahlen (269 mAh)

    def __init__(self, coordinator, name_suffix, channel):
        super().__init__(coordinator)
        self._channel = channel
        address = coordinator.address

        self._attr_unique_id = f"{address}_ch{channel}_capacity_done"
        self._attr_name = f"ISDT C4 Air {name_suffix}"

        self._attr_device_info = {
            "identifiers": {(DOMAIN, address)},
            "name": "ISDT C4 Air",
            "manufacturer": "ISDT",
            "model": "C4 Air",
        }

    @property
    def native_value(self):
        """Gibt die Kapazität in mAh zurück."""
        if self.coordinator.data and self._channel in self.coordinator.data:
            return self.coordinator.data[self._channel].get("capacity_done")
        return None


class ISDTC4EnergySensor(CoordinatorEntity, SensorEntity):
    """Energie-Sensor (Wh)."""

    _attr_native_unit_of_measurement = UnitOfEnergy.WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 2  # 2 Nachkommastellen (0.38 Wh)

    def __init__(self, coordinator, name_suffix, channel):
        super().__init__(coordinator)
        self._channel = channel
        address = coordinator.address

        self._attr_unique_id = f"{address}_ch{channel}_energy_done"
        self._attr_name = f"ISDT C4 Air {name_suffix}"

        self._attr_device_info = {
            "identifiers": {(DOMAIN, address)},
            "name": "ISDT C4 Air",
            "manufacturer": "ISDT",
            "model": "C4 Air",
        }

    @property
    def native_value(self):
        """Gibt die Energie in Wh zurück."""
        if self.coordinator.data and self._channel in self.coordinator.data:
            return self.coordinator.data[self._channel].get("energy_done_wh")
        return None


class ISDTC4TimeSensor(CoordinatorEntity, SensorEntity):
    """Ladezeit-Sensor (HH:MM:SS)."""

    _attr_icon = "mdi:timer-outline"

    def __init__(self, coordinator, name_suffix, channel):
        super().__init__(coordinator)
        self._channel = channel
        address = coordinator.address

        self._attr_unique_id = f"{address}_ch{channel}_work_period"
        self._attr_name = f"ISDT C4 Air {name_suffix}"

        self._attr_device_info = {
            "identifiers": {(DOMAIN, address)},
            "name": "ISDT C4 Air",
            "manufacturer": "ISDT",
            "model": "C4 Air",
        }

    @property
    def native_value(self):
        """Gibt die Ladezeit als String zurück (HH:MM:SS)."""
        if self.coordinator.data and self._channel in self.coordinator.data:
            return self.coordinator.data[self._channel].get("work_period_str")
        return None


class ISDTC4BatteryTypeSensor(CoordinatorEntity, SensorEntity):
    """Akkutyp-Sensor (NiMH, LiPo, etc.)."""

    _attr_icon = "mdi:battery-heart-variant"

    def __init__(self, coordinator, name_suffix, channel):
        super().__init__(coordinator)
        self._channel = channel
        address = coordinator.address

        self._attr_unique_id = f"{address}_ch{channel}_battery_type"
        self._attr_name = f"ISDT C4 Air {name_suffix}"

        self._attr_device_info = {
            "identifiers": {(DOMAIN, address)},
            "name": "ISDT C4 Air",
            "manufacturer": "ISDT",
            "model": "C4 Air",
        }

    @property
    def native_value(self):
        """Gibt den Akkutyp als String zurück."""
        if self.coordinator.data and self._channel in self.coordinator.data:
            return self.coordinator.data[self._channel].get("battery_type_str")
        return None


class ISDTC4CellVoltageSensor(CoordinatorEntity, SensorEntity):
    """Sensor für eine einzelne Zellspannung."""

    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 3  # Zeige 3 Nachkommastellen (z.B. 1.400V)

    def __init__(self, coordinator, name_suffix, channel, cell_index):
        super().__init__(coordinator)
        self._channel = channel
        self._cell_index = cell_index
        address = coordinator.address

        self._attr_unique_id = f"{address}_ch{channel}_cell{cell_index}"
        self._attr_name = f"ISDT C4 Air {name_suffix}"

        self._attr_device_info = {
            "identifiers": {(DOMAIN, address)},
            "name": "ISDT C4 Air",
            "manufacturer": "ISDT",
            "model": "C4 Air",
        }

        # Entity standardmäßig deaktiviert, wird nur sichtbar wenn Zelle vorhanden
        self._attr_entity_registry_enabled_default = False

    @property
    def native_value(self):
        """Gibt die Zellspannung zurück (nur wenn > 0)."""
        if self.coordinator.data and self._channel in self.coordinator.data:
            cell_voltages = self.coordinator.data[self._channel].get(
                "cell_voltages", []
            )
            if self._cell_index < len(cell_voltages):
                voltage = cell_voltages[self._cell_index]
                # Nur Wert zurückgeben wenn Zelle vorhanden (Spannung > 0.1V)
                if voltage > 0.1:
                    return voltage
        return None

    @property
    def available(self):
        """Sensor ist nur verfügbar wenn eine Zelle vorhanden ist."""
        return self.native_value is not None


class ISDTC4TotalChargingSensor(CoordinatorEntity, SensorEntity):
    """Sensor für den Gesamt-Ladestrom über alle Slots."""

    _attr_name = "ISDT C4 Air Total Charging Current"
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 3  # Zeige 3 Nachkommastellen (z.B. 1.914A)

    def __init__(self, coordinator):
        super().__init__(coordinator)
        address = coordinator.address
        self._attr_unique_id = f"{address}_total_charging_current"

        self._attr_device_info = {
            "identifiers": {(DOMAIN, address)},
            "name": "ISDT C4 Air",
            "manufacturer": "ISDT",
            "model": "C4 Air",
        }

    @property
    def native_value(self):
        """Summiert den Ladestrom aller Channels."""
        if not self.coordinator.data:
            return 0.0

        total = sum(
            ch_data.get("charging_current", 0.0)
            for ch_data in self.coordinator.data.values()
            if isinstance(ch_data, dict)
        )
        return round(total, 3)
