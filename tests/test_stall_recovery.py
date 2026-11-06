"""Tests for dropping and re-establishing a link after the device stalls.

When the MASS2 stops answering, it still accepts connections but leaves
GATT requests unanswered for about two minutes. Unsubscribing while a
subscribe is still pending makes BlueZ 5.85 abort and restart bluetoothd,
and fast retries only add connects whose requests BlueZ has to abort.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")

from isdt_air_ble import coordinator as coord  # noqa: E402
from isdt_air_ble.const import DeviceType  # noqa: E402
from isdt_air_ble.watchdog import ResponseStall  # noqa: E402


def _make_coordinator():
    c = object.__new__(coord.ISDTDataUpdateCoordinator)
    c.address = "AA:BB:CC:DD:EE:FF"
    c.model = "MASS2"
    c.device_type = DeviceType.ADAPTER
    c._client = None
    c._connected = False
    c._notification_started = False
    c._connect_time = None
    c._bind_uuid = bytes(16)
    return c


def _make_client(calls, hang_start_notify=False):
    async def start_notify(char, callback):
        calls.append(("start_notify", char))
        if hang_start_notify:
            await asyncio.Event().wait()

    async def stop_notify(char):
        calls.append(("stop_notify", char))

    async def disconnect():
        calls.append(("disconnect", None))

    async def write_gatt_char(char, data, response):
        calls.append(("write", char))

    return SimpleNamespace(
        is_connected=True,
        start_notify=start_notify,
        stop_notify=stop_notify,
        disconnect=disconnect,
        write_gatt_char=write_gatt_char,
    )


@pytest.mark.parametrize("notifying", [True, False])
def test_disconnect_unsubscribes_only_after_a_completed_subscribe(notifying):
    async def run():
        c = _make_coordinator()
        calls = []
        c._client = _make_client(calls)
        c._notification_started = notifying
        await c._disconnect()
        stops = [x for x in calls if x[0] == "stop_notify"]
        assert stops == ([("stop_notify", coord.CHAR_UUID_AF01)] if notifying else [])
        assert calls[-1] == ("disconnect", None)
        assert c._client is None

    asyncio.run(run())


@pytest.mark.parametrize("method", ["_send_bind_request", "_fetch_hardware_info"])
def test_stalled_af02_subscribe_is_not_unsubscribed(monkeypatch, method):
    async def run():
        c = _make_coordinator()
        calls = []
        c._client = _make_client(calls, hang_start_notify=True)
        monkeypatch.setattr(coord, "_GATT_OP_TIMEOUT", 0.05)
        with pytest.raises(ResponseStall):
            await getattr(c, method)()
        assert ("start_notify", coord.CHAR_UUID_AF02) in calls
        assert not [x for x in calls if x[0] == "stop_notify"]

    if not hasattr(coord.ISDTDataUpdateCoordinator, method):
        pytest.skip(f"{method} not present")
    asyncio.run(run())


def test_stall_cooldown_grows_and_caps():
    c = _make_coordinator()
    c._stall_streak = 0
    waits = [c._next_stall_cooldown() for _ in range(5)]
    assert waits == [10.0, 30.0, 60.0, 60.0, 60.0]
    # A completed command cycle resets the streak in the live loop.
    c._stall_streak = 0
    assert c._next_stall_cooldown() == 10.0
