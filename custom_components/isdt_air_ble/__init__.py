"""The ISDT Air BLE integration."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN, CONF_SCAN_INTERVAL, CONF_BIND_UUID, DEFAULT_SCAN_INTERVAL
from .coordinator import ISDTDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SWITCH, Platform.SELECT]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ISDT Air BLE from a config entry."""
    address = entry.data["address"]
    model = entry.data.get("model", "C4 Air")
    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    # Persistent bind UUID — generate once and store in entry data so the
    # device recognizes us across HA restarts. Matches manufacturer app behavior.
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
        hass, address, model, scan_interval, bind_uuid=bind_uuid,
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


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()

    return unload_ok
