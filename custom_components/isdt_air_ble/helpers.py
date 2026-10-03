"""Shared helpers for ISDT Air integration."""

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import (
    DeviceInfo,
    CONNECTION_BLUETOOTH,
)

from .const import DOMAIN, get_port_labels


def main_device_info(address: str, model: str = "C4 Air") -> DeviceInfo:
    """Device info for the main ISDT device."""
    return DeviceInfo(
        identifiers={(DOMAIN, address)},
        connections={(CONNECTION_BLUETOOTH, address)},
        name=f"ISDT {model}",
        manufacturer="ISDT",
        model=model,
    )


def slot_device_info(address: str, slot: int, model: str = "C4 Air") -> DeviceInfo:
    """Device info for a slot sub-device."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{address}_slot{slot}")},
        name=f"ISDT {model} Slot {slot}",
        manufacturer="ISDT",
        model=model,
    )


def port_device_info(address: str, port: int, model: str = "MASS2") -> DeviceInfo:
    """Device info for an output port sub-device.

    Uses the model's physical port label (USB-C1...USB-A2 on the MASS2,
    Wireless/USB-A/USB-C1..C3 on the Power 200 family), matching the
    port labelling on the device hardware.
    """
    labels = get_port_labels(model)
    if 1 <= port <= len(labels):
        label = labels[port - 1]
    else:
        label = f"Port {port}"
    return DeviceInfo(
        identifiers={(DOMAIN, f"{address}_port{port}")},
        name=f"ISDT {model} {label}",
        manufacturer="ISDT",
        model=model,
    )


def async_get_own_device(
    dev_reg: dr.DeviceRegistry, identifier: str, entry_id: str | None
) -> dr.DeviceEntry | None:
    """Return the device with ``(DOMAIN, identifier)`` owned by this entry.

    async_get_device is deprecated since HA 2026.9 and logs a warning on every
    call: identifiers are only unique within a config entry, so a lookup
    across entries can be ambiguous. async_get_device_by_identifier scopes the
    lookup to the entry. It only exists from 2026.8 on; older cores have no
    split devices, so the plain lookup is correct there.
    """
    if entry_id is not None and hasattr(dev_reg, "async_get_device_by_identifier"):
        return dev_reg.async_get_device_by_identifier((DOMAIN, identifier), entry_id)
    return dev_reg.async_get_device(identifiers={(DOMAIN, identifier)})
