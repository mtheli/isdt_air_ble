"""Shared helpers for ISDT Air integration."""

from homeassistant.helpers.device_registry import (
    DeviceInfo,
    CONNECTION_BLUETOOTH,
)

from .const import DOMAIN, MASS2_PORT_LABELS


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
    """Device info for a USB port sub-device.

    Uses the physical USB port label (USB-C1...USB-A2) when available,
    matching the port labelling on the device hardware.
    """
    if 1 <= port <= len(MASS2_PORT_LABELS):
        label = MASS2_PORT_LABELS[port - 1]
    else:
        label = f"Port {port}"
    return DeviceInfo(
        identifiers={(DOMAIN, f"{address}_port{port}")},
        name=f"ISDT {model} {label}",
        manufacturer="ISDT",
        model=model,
        via_device=(DOMAIN, address),
    )
