import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import Platform

from .const import DOMAIN
from .coordinator import ISDTDataUpdateCoordinator  # Diese Datei erstellen wir gleich

_LOGGER = logging.getLogger(__name__)

# Liste der Plattformen, die wir unterstützen (vorerst nur Sensoren)
PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Setzt die Integration nach erfolgreichem Config Flow auf."""
    address = entry.data["address"]

    # 1. Den Coordinator erstellen (das Herzstück der Kommunikation)
    coordinator = ISDTDataUpdateCoordinator(hass, address)

    # 2. Den ersten Datenabruf versuchen
    await coordinator.async_config_entry_first_refresh()

    # 3. Den Coordinator zentral speichern, damit sensor.py darauf zugreifen kann
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # 4. Die Plattformen (sensor.py) laden
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Wird aufgerufen, wenn die Integration entfernt oder deaktiviert wird."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
