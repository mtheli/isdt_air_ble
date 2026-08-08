"""Tests for the "Charging Since" session-latch rule (issue #7).

The timestamp used to be recomputed as ``now - work_period`` on every poll,
which produced a new state every couple of seconds and let the reported
start time wander by minutes across a single charge. It is now anchored
once per session; ``charge_session_action`` is that decision.
"""

from __future__ import annotations

import pytest

from isdt_air_ble.const import ChargeSessionAction, charge_session_action

ANCHORED = True
NO_ANCHOR = False


@pytest.mark.parametrize("work_state", ["empty", "idle"])
def test_no_battery_clears_the_anchor(work_state):
    """An empty or idle slot reports no timestamp at all."""
    assert (
        charge_session_action(work_state, 1200, 1100, ANCHORED)
        == ChargeSessionAction.CLEAR
    )


def test_unknown_state_keeps_the_anchor():
    """A state the enum maps to "unknown_N" is not evidence of an end.

    A poll with no WorkState frame at all never reaches this function —
    the sensor holds the latch before consulting it.
    """
    assert (
        charge_session_action("unknown_9", 500, 480, ANCHORED)
        == ChargeSessionAction.KEEP
    )


def test_zero_counter_clears():
    """A counter of zero means no session is running."""
    assert (
        charge_session_action("charging", 0, 0, NO_ANCHOR)
        == ChargeSessionAction.CLEAR
    )


def test_first_poll_of_a_session_anchors():
    """The first charging poll computes the start time."""
    assert (
        charge_session_action("charging", 3, 0, NO_ANCHOR)
        == ChargeSessionAction.ANCHOR
    )


def test_running_session_keeps_the_anchor():
    """This is the fix for issue #7: a rising counter must not re-anchor.

    Every poll during a charge advances work_period. Recomputing the start
    time here is exactly what made "Charging Since" drift and write a new
    state every couple of seconds.
    """
    assert (
        charge_session_action("charging", 400, 398, ANCHORED)
        == ChargeSessionAction.KEEP
    )


def test_finished_charge_keeps_the_anchor():
    """A completed charge keeps showing when it started."""
    assert (
        charge_session_action("done", 4200, 4200, ANCHORED)
        == ChargeSessionAction.KEEP
    )


def test_error_state_keeps_the_anchor():
    """An error mid-charge does not reset the session."""
    assert (
        charge_session_action("error", 900, 880, ANCHORED)
        == ChargeSessionAction.KEEP
    )


def test_counter_reset_starts_a_new_session():
    """A backwards jump means the battery was swapped — re-anchor.

    Covers a swap fast enough that no idle poll landed in between, so the
    counter reset is the only evidence of a new session.
    """
    assert (
        charge_session_action("charging", 2, 4200, ANCHORED)
        == ChargeSessionAction.ANCHOR
    )


def test_restart_without_anchor_anchors():
    """After a HA restart mid-charge the start time is re-derived once."""
    assert (
        charge_session_action("charging", 4200, 0, NO_ANCHOR)
        == ChargeSessionAction.ANCHOR
    )


def test_session_survives_a_full_charge_cycle():
    """Walk a whole session: anchor once, then hold until the battery goes."""
    actions = []
    last = 0
    anchored = False
    for state, period in [
        ("idle", 0),
        ("charging", 2),
        ("charging", 120),
        ("charging", 3600),
        ("done", 4000),
        ("done", 4000),
        ("empty", 0),
    ]:
        action = charge_session_action(state, period, last, anchored)
        if action == ChargeSessionAction.CLEAR:
            anchored, last = False, 0
        else:
            if action == ChargeSessionAction.ANCHOR:
                anchored = True
            last = period
        actions.append(action)

    assert actions == [
        ChargeSessionAction.CLEAR,
        ChargeSessionAction.ANCHOR,
        ChargeSessionAction.KEEP,
        ChargeSessionAction.KEEP,
        ChargeSessionAction.KEEP,
        ChargeSessionAction.KEEP,
        ChargeSessionAction.CLEAR,
    ]
