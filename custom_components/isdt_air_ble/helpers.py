"""Shared helpers for ISDT C4 Air integration."""

from homeassistant.helpers.device_registry import (
    DeviceInfo,
    CONNECTION_BLUETOOTH,
)

from .const import DOMAIN


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
