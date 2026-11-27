"""Shared helpers for the MASS2 quiet hours and USB-C port schedules.

Both use the same encoding on the device:
- repeat byte: bit 7 = enabled, bits 0..6 = Monday..Sunday. Switching a
  schedule off only clears bit 7; days and times stay stored.
- times: two bytes [hour, minute], kept here as ``hour | minute << 8``
  (the little-endian word the parser reads).

A window whose start is after its end runs past midnight (the day bit is
the day it starts). Start equal to end means the whole day.

No Home Assistant imports here, so the parser tests can use it.
"""

from __future__ import annotations

from datetime import time

from .const import MASS2_REPEAT_DAYS, MASS2_REPEAT_ENABLED

WEEKDAYS = (
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
)

# Day presets offered by the days select. Any other combination shows as
# "custom" (set in the vendor app); the days are listed in an attribute.
DAY_PRESETS = {
    "every_day": 0x7F,
    "weekdays": 0x1F,
    "weekend": 0x60,
}
DAYS_CUSTOM = "custom"


def word_to_time(word: int) -> time | None:
    """Convert the device time word to a time (None if out of range)."""
    hour = word & 0xFF
    minute = (word >> 8) & 0xFF
    if hour > 23 or minute > 59:
        return None
    return time(hour, minute)


def time_to_word(value: time) -> int:
    """Convert a time to the device time word."""
    return value.hour | (value.minute << 8)


def repeat_enabled(repeat: int) -> bool:
    return bool(repeat & MASS2_REPEAT_ENABLED)


def repeat_days(repeat: int) -> int:
    return repeat & MASS2_REPEAT_DAYS


def days_option(repeat: int) -> str:
    days = repeat_days(repeat)
    for option, mask in DAY_PRESETS.items():
        if days == mask:
            return option
    return DAYS_CUSTOM


def days_list(repeat: int) -> list[str]:
    days = repeat_days(repeat)
    return [name for bit, name in enumerate(WEEKDAYS) if days & (1 << bit)]


def with_enabled(repeat: int, enabled: bool) -> int:
    """Set or clear bit 7. Enabling with no days selects every day.

    Bit 7 without days is a one-shot schedule on the device, which clears
    itself after it ran once; that is not what a switch should do.
    """
    if not enabled:
        return repeat & ~MASS2_REPEAT_ENABLED & 0xFF
    days = repeat_days(repeat) or DAY_PRESETS["every_day"]
    return MASS2_REPEAT_ENABLED | days


def with_days(repeat: int, mask: int) -> int:
    """Replace the day bits, keep bit 7."""
    return (repeat & MASS2_REPEAT_ENABLED) | (mask & MASS2_REPEAT_DAYS)


def mask_from_days(days: list[str]) -> int:
    """Day bits for a list of weekday names (monday..sunday)."""
    mask = 0
    for day in days:
        mask |= 1 << WEEKDAYS.index(day)
    return mask


def build_repeat(current: int, days: list[str], enabled: bool | None) -> int:
    """Repeat byte for a full schedule update: new days, bit 7 as requested
    (or as it was when ``enabled`` is None)."""
    if not days:
        raise ValueError("at least one day is required")
    on = repeat_enabled(current) if enabled is None else enabled
    return (MASS2_REPEAT_ENABLED if on else 0) | mask_from_days(days)
