"""The ISDT Air BLE integration."""

import logging

from homeassistant.components.bluetooth import async_last_service_info
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import (
    CONF_BIND_UUID,
    CONF_PHANTOM_DEBOUNCE,
    CONF_PHANTOM_SUSTAIN,
    CONF_PHANTOM_THRESHOLD,
    CONF_SCAN_INTERVAL,
    DEFAULT_PHANTOM_DEBOUNCE,
    DEFAULT_PHANTOM_SUSTAIN,
    DEFAULT_PHANTOM_THRESHOLD,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    DeviceType,
    ISDT_MANUFACTURER_ID,
    detect_model_from_mfg_data,
    get_channel_count,
    get_device_type,
    is_stale_charger_unique_id,
)
from .coordinator import ISDTDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SWITCH, Platform.SELECT, Platform.UPDATE]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ISDT Air BLE from a config entry."""
    address = entry.data["address"]
    model = entry.data.get("model", "C4 Air")

    # Re-detect model from the cached BLE manufacturer data on every load.
    # Early Air 8 setups were misidentified as "C4 Air" because the device
    # model ID 01030000 used to be mapped there. This silently migrates
    # affected entries without forcing the user to delete & re-add.
    detected_model = _detect_model_from_cache(hass, address)
    if detected_model and detected_model != model:
        _LOGGER.warning(
            "Re-detected device at %s as '%s' (was '%s') — updating config entry",
            address, detected_model, model,
        )
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, "model": detected_model},
        )
        model = detected_model

    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    phantom_threshold = entry.options.get(
        CONF_PHANTOM_THRESHOLD, DEFAULT_PHANTOM_THRESHOLD
    )
    phantom_debounce = entry.options.get(
        CONF_PHANTOM_DEBOUNCE, DEFAULT_PHANTOM_DEBOUNCE
    )
    phantom_sustain = entry.options.get(
        CONF_PHANTOM_SUSTAIN, DEFAULT_PHANTOM_SUSTAIN
    )

    # Persistent bind UUID — generate once and store in entry data so the
    # device recognizes us across HA restarts.
    bind_uuid_hex = entry.data.get(CONF_BIND_UUID)
    if bind_uuid_hex:
        bind_uuid = bytes.fromhex(bind_uuid_hex)
    else:
        import uuid as _uuid
        bind_uuid = _uuid.uuid4().bytes
        hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, CONF_BIND_UUID: bind_uuid.hex()},
        )

    coordinator = ISDTDataUpdateCoordinator(
        hass,
        address,
        model,
        scan_interval,
        bind_uuid=bind_uuid,
        phantom_threshold=phantom_threshold,
        phantom_debounce=phantom_debounce,
        phantom_sustain=phantom_sustain,
    )

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    _async_cleanup_stale_registry(hass, entry, address, model)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Start persistent connection loop in the background
    coordinator.start_live_monitoring()

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


def _async_cleanup_stale_registry(
    hass: HomeAssistant, entry: ConfigEntry, address: str, model: str
) -> None:
    """Remove registry ghosts left behind by earlier model (mis)detection.

    Before a device's model was known — or supported at all — setup fell
    back to a generic 6-channel charger profile and registered entities
    (notably the disabled-by-default cell-voltage sensors) that the real
    device never provides. Entity-registry entries outlive the code that
    created them, so prune anything the current model cannot have.

    This also applies to adapters: a Power 200 added before its model was
    supported went through the same charger fallback, so charger-style
    channel/slot ghosts are pruned there too (channel_count 0 = the model
    has no charger channels at all).
    """
    channel_count = (
        get_channel_count(model)
        if get_device_type(model) == DeviceType.CHARGER
        else 0
    )

    ent_reg = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if is_stale_charger_unique_id(
            entity.unique_id, address, model, channel_count
        ):
            _LOGGER.debug(
                "Removing stale entity %s (unique_id=%s) not provided by %s",
                entity.entity_id,
                entity.unique_id,
                model,
            )
            ent_reg.async_remove(entity.entity_id)

    # Slot sub-devices beyond the model's slot count (their entities were
    # just removed above, but empty devices linger in the registry).
    dev_reg = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
        for domain, identifier in device.identifiers:
            if domain != DOMAIN or not identifier.startswith(f"{address}_slot"):
                continue
            slot_str = identifier.removeprefix(f"{address}_slot")
            if slot_str.isdigit() and int(slot_str) > channel_count:
                _LOGGER.debug(
                    "Removing stale slot device %s (%s)", device.name, identifier
                )
                dev_reg.async_update_device(
                    device.id, remove_config_entry_id=entry.entry_id
                )


def _detect_model_from_cache(hass: HomeAssistant, address: str) -> str | None:
    """Look up the device's current model from cached BLE advertisements."""
    service_info = async_last_service_info(hass, address, connectable=True)
    if service_info is None:
        return None
    return detect_model_from_mfg_data(
        service_info.manufacturer_data.get(ISDT_MANUFACTURER_ID)
    )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()

    return unload_ok
