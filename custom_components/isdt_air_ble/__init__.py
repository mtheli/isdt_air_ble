"""The ISDT C4 Air integration."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import ISDTDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SWITCH]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ISDT C4 Air from a config entry."""
    address = entry.data["address"]
    model = entry.data.get("model", "C4 Air")

    coordinator = ISDTDataUpdateCoordinator(hass, address, model)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Start connection in the background (non-blocking)
    async def _async_start_connection():
        try:
            await coordinator.async_start()
            await coordinator.async_refresh()
        except Exception as err:
            _LOGGER.warning(
                "Initial connection failed: %s - Will retry on next update", err
            )

    hass.async_create_task(_async_start_connection())

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()

    return unload_ok
