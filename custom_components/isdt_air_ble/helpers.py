"""Shared helpers for ISDT Air integration."""

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
        via_device=(DOMAIN, address),
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
        via_device=(DOMAIN, address),
    )
