"""Sensor and binary sensor entities for BattAir packs and plugins."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.components.bluetooth.passive_update_coordinator import (
    PassiveBluetoothCoordinatorEntity,
)
from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfElectricPotential,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from .battair import BATTERY_TYPES, MODEL_PACK, BattAirAdvert
from .battair_coordinator import BattAirCoordinator
from .const import DOMAIN

# "Last seen" is written at most this often while the pack is in range, and
# exactly once when it goes out of range.
LAST_SEEN_WRITE_INTERVAL = timedelta(minutes=15)


def _device_info(coordinator: BattAirCoordinator, entry: ConfigEntry) -> DeviceInfo:
    advert = coordinator.data
    model = advert.model if advert is not None else entry.data.get("model", MODEL_PACK)
    return DeviceInfo(
        identifiers={(DOMAIN, coordinator.address)},
        connections={(dr.CONNECTION_BLUETOOTH, coordinator.address)},
        manufacturer="ISDT",
        model=model,
        name=entry.title,
    )


class BattAirEntity(PassiveBluetoothCoordinatorEntity[BattAirCoordinator]):
    """Common base: one device per pack, entity name from translation key."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: BattAirCoordinator, entry: ConfigEntry, key: str
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_{key}"
        self._attr_translation_key = f"battair_{key}"
        self._attr_device_info = _device_info(coordinator, entry)

    @property
    def available(self) -> bool:
        return self.coordinator.available and self.coordinator.data is not None


# ---------------------------------------------------------------------------
# Sensors
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class BattAirSensorDescription(SensorEntityDescription):
    value_fn: Callable[[BattAirAdvert], float | int | str | None]


SENSORS: tuple[BattAirSensorDescription, ...] = (
    BattAirSensorDescription(
        key="voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda a: a.voltage,
    ),
    BattAirSensorDescription(
        key="cell_voltage_avg",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
        value_fn=lambda a: a.cell_voltage_avg,
    ),
    BattAirSensorDescription(
        key="battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda a: a.percentage,
    ),
    BattAirSensorDescription(
        key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda a: a.temperature,
    ),
    BattAirSensorDescription(
        key="cycles",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda a: a.cycles,
    ),
    BattAirSensorDescription(
        key="cells",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda a: a.cells,
    ),
    BattAirSensorDescription(
        key="capacity",
        native_unit_of_measurement="mAh",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda a: a.capacity_mah,
    ),
    BattAirSensorDescription(
        key="battery_type",
        device_class=SensorDeviceClass.ENUM,
        options=list(BATTERY_TYPES.values()),
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda a: a.battery_type,
    ),
)


class BattAirSensor(BattAirEntity, SensorEntity):
    """A value from the advertisement."""

    entity_description: BattAirSensorDescription

    def __init__(self, coordinator, entry, description: BattAirSensorDescription):
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description

    @property
    def native_value(self):
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)


class BattAirRSSISensor(BattAirEntity, SensorEntity):
    """Signal strength, updated about once a minute."""

    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "rssi")

    @property
    def native_value(self):
        return self.coordinator.rssi


class BattAirLastSeenSensor(BattAirEntity, RestoreSensor):
    """When the pack was last heard.

    Stays available while the pack is out of range, which is when it
    matters. A pack that stays silent for a long time may have shut down
    because of a low cell.
    """

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "last_seen")
        self._value: datetime | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_sensor_data()) is not None:
            if isinstance(last.native_value, datetime):
                self._value = last.native_value
        self._update_value()
        # Repeated identical advertisements do not reach the coordinator, so
        # refresh from the Bluetooth history on a timer.
        self.async_on_remove(
            async_track_time_interval(
                self.hass, self._async_refresh, LAST_SEEN_WRITE_INTERVAL
            )
        )

    @callback
    def _async_refresh(self, _now: datetime) -> None:
        before = self._value
        self._update_value(force=True)
        if self._value != before:
            self.async_write_ha_state()

    @property
    def available(self) -> bool:
        return self._value is not None

    @property
    def native_value(self) -> datetime | None:
        return self._value

    def _update_value(self, force: bool = False) -> None:
        seen = self.coordinator.last_seen_time()
        if seen is None:
            return
        # Only move forward: the restored value may be newer than a cached
        # advertisement after a restart.
        if self._value is not None and seen <= self._value:
            return
        if (
            force
            or self._value is None
            or not self.coordinator.available
            or seen - self._value >= LAST_SEEN_WRITE_INTERVAL
        ):
            self._value = seen

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_value()
        super()._handle_coordinator_update()


# ---------------------------------------------------------------------------
# Binary sensors
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class BattAirBinarySensorDescription(BinarySensorEntityDescription):
    value_fn: Callable[[BattAirAdvert], bool | None]
    exists_fn: Callable[[BattAirAdvert | None], bool] = lambda a: True


BINARY_SENSORS: tuple[BattAirBinarySensorDescription, ...] = (
    BattAirBinarySensorDescription(
        key="cell_voltage_low",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda a: a.cell_voltage_low,
        # Only for chemistries with a known threshold; a pack whose type is
        # not known yet gets the entity and reports unknown.
        exists_fn=lambda a: a is None or a.low_cell_voltage_threshold is not None,
    ),
    BattAirBinarySensorDescription(
        key="error_log",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda a: a.error_log,
    ),
    BattAirBinarySensorDescription(
        key="storage_discharge",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda a: a.storage_discharge,
    ),
    BattAirBinarySensorDescription(
        key="transport_mode",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda a: a.transport_mode,
    ),
)


class BattAirBinarySensor(BattAirEntity, BinarySensorEntity):
    """A status flag from the advertisement."""

    entity_description: BattAirBinarySensorDescription

    def __init__(
        self, coordinator, entry, description: BattAirBinarySensorDescription
    ):
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)


# ---------------------------------------------------------------------------
# Platform setup
# ---------------------------------------------------------------------------


async def async_setup_sensors(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: BattAirCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = [
        BattAirSensor(coordinator, entry, description) for description in SENSORS
    ]
    entities.append(BattAirRSSISensor(coordinator, entry))
    entities.append(BattAirLastSeenSensor(coordinator, entry))
    async_add_entities(entities)


async def async_setup_binary_sensors(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: BattAirCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        BattAirBinarySensor(coordinator, entry, description)
        for description in BINARY_SENSORS
        if description.exists_fn(coordinator.data)
    )
