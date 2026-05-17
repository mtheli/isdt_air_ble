"""The ISDT Air BLE integration."""

import logging

from homeassistant.components.bluetooth import async_last_service_info
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

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
    ISDT_MANUFACTURER_ID,
    detect_model_from_mfg_data,
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

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Start persistent connection loop in the background
    coordinator.start_live_monitoring()

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


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
