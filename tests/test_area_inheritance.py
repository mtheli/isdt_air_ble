"""Tests for the slot/port area-inheritance rule.

Slot and port sub-devices follow the main device's area so the user does
not have to assign the same area up to nine times. ``should_inherit_area``
is the decision that drives it; the registry plumbing around it lives in
``__init__.py``.
"""

from __future__ import annotations

from isdt_air_ble.const import should_inherit_area

LIVING_ROOM = "living_room"
OFFICE = "office"
GARAGE = "garage"


def test_unassigned_sub_device_inherits():
    """A sub-device without an area takes the main device's area."""
    assert should_inherit_area(None, LIVING_ROOM) is True


def test_matching_area_is_left_alone():
    """Nothing to do when the sub-device is already in the right area."""
    assert should_inherit_area(LIVING_ROOM, LIVING_ROOM) is False


def test_deliberate_placement_survives_setup():
    """A port the user moved elsewhere keeps its area on every reload.

    This is the regression guard for the whole feature: inheriting must
    never overwrite a manual assignment.
    """
    assert should_inherit_area(OFFICE, LIVING_ROOM) is False


def test_follows_main_device_to_new_area():
    """Sub-devices in the main device's previous area move along with it."""
    assert should_inherit_area(LIVING_ROOM, OFFICE, previous_area=LIVING_ROOM) is True


def test_manual_placement_survives_main_device_move():
    """A hand-placed port stays put even when the main device moves."""
    assert should_inherit_area(GARAGE, OFFICE, previous_area=LIVING_ROOM) is False


def test_unassigned_sub_device_inherits_on_move():
    """A move also fills sub-devices that never had an area."""
    assert should_inherit_area(None, OFFICE, previous_area=LIVING_ROOM) is True


def test_main_device_moving_back_to_sub_device_area():
    """No update when the main device moves into the sub-device's area."""
    assert should_inherit_area(OFFICE, OFFICE, previous_area=LIVING_ROOM) is False


def test_previous_area_none_does_not_capture_unset_devices_twice():
    """``previous_area=None`` behaves like the plain setup case."""
    assert should_inherit_area(None, LIVING_ROOM, previous_area=None) is True
    assert should_inherit_area(OFFICE, LIVING_ROOM, previous_area=None) is False
