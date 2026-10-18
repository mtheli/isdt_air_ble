"""Tests for entity availability.

Entities are available while the BLE link is up. They used to check
whether the device had advertised recently, which a connected ISDT device
does not do: behind an ESPHome Bluetooth proxy the last advertisement
expires after a few minutes and every port sensor went unavailable while
data kept arriving.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")

from isdt_air_ble.binary_sensor import (  # noqa: E402
    ISDTC4ConnectedSensor,
    ISDTC4SlotActiveSensor,
    ISDTMASS2PortActiveSensor,
)
from isdt_air_ble.select import ISDTMASS2VolumeSelect  # noqa: E402
from isdt_air_ble.sensor import (  # noqa: E402
    ISDTC4VoltageSensor,
    ISDTMASS2PortStatusSensor,
    ISDTMASS2TotalPowerSensor,
)
from isdt_air_ble.switch import ISDTC4AlarmToneSwitch, ISDTMASS2BeepSwitch  # noqa: E402

ADDRESS = "AA:BB:CC:DD:EE:FF"


def _coordinator(model: str, connected: bool) -> SimpleNamespace:
    """A coordinator stand-in that has received data but may be disconnected.

    ``last_update_success`` stays True, as it does on the real coordinator
    once the first packet arrived.
    """
    return SimpleNamespace(
        address=ADDRESS,
        model=model,
        connected=connected,
        last_update_success=True,
        data={0: {"status": 1}, 1: {"status": 1}},
        alarm_tone_on=True,
        mass2_settings={"volume": 1, "scheduledMute": 1},
    )


def _adapter_entities(coordinator):
    return [
        ISDTMASS2PortStatusSensor(coordinator, 0, 1),
        ISDTMASS2TotalPowerSensor(coordinator),
        ISDTMASS2PortActiveSensor(coordinator, 1, 0),
        ISDTMASS2BeepSwitch(coordinator),
        ISDTMASS2VolumeSelect(coordinator),
    ]


def _charger_entities(coordinator):
    return [
        ISDTC4VoltageSensor(coordinator, "voltage", "output_voltage", 0, 1),
        ISDTC4SlotActiveSensor(coordinator, 1, 0),
        ISDTC4AlarmToneSwitch(coordinator),
    ]


@pytest.mark.parametrize(
    ("model", "build"),
    [("MASS2", _adapter_entities), ("C4 Air", _charger_entities)],
)
def test_available_while_connected(model, build):
    """Connected means available, whether or not HA still lists an advertisement."""
    for entity in build(_coordinator(model, connected=True)):
        assert entity.available is True, type(entity).__name__


@pytest.mark.parametrize(
    ("model", "build"),
    [("MASS2", _adapter_entities), ("C4 Air", _charger_entities)],
)
def test_unavailable_after_disconnect(model, build):
    """Old values are not shown as current once the link is gone."""
    for entity in build(_coordinator(model, connected=False)):
        assert entity.available is False, type(entity).__name__


@pytest.mark.parametrize("connected", [True, False])
def test_connected_sensor_stays_available(connected):
    """The connection sensor reports the drop instead of going unavailable."""
    sensor = ISDTC4ConnectedSensor(_coordinator("C4 Air", connected))
    assert sensor.available is True
    assert sensor.is_on is connected
