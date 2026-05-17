#!/usr/bin/env python3
"""ISDT charger BLE probe.

Captures raw GATT notifications from any ISDT BLE charger so the
response payloads can be inspected and fed into the isdt_air_ble
Home Assistant integration as test fixtures.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as _dt
import json
import os
import secrets
import sys
import time

try:
    from bleak import BleakClient, BleakScanner
except ImportError:
    sys.exit("bleak is required: pip install bleak")


DESCRIPTION = (
    "Capture raw GATT notifications from any ISDT BLE charger "
    "(C4 Air, A8 Air, Air 8, A4 Air, K2 Air, ...) for inclusion as "
    "test fixtures in the isdt_air_ble Home Assistant integration."
)

EPILOG = """\
Examples
--------

  # C4 Air (6 slots), all slots empty:
  isdt_charger_probe.py --mac AA:BB:CC:DD:EE:FF --channels 0-5 \\
                        --bind-uuid 9945...61fa \\
                        --label "c4air_empty"

  # K2 Air (2 slots), one cell charging:
  isdt_charger_probe.py --mac AA:BB:CC:DD:EE:FF --channels 0-1 \\
                        --label "k2air_1cell_charging"

  # Air 8 (single LiPo channel), 4S pack:
  isdt_charger_probe.py --mac AA:BB:CC:DD:EE:FF --channels 0 \\
                        --label "air8_4s_charging"


Bind UUID
---------

The bind UUID is the 16-byte client identifier used when the device
was paired the first time. You can read it from a Home Assistant
debug log line like:

  Sending BindReq on AF02: 18 99 45 6a 7c 65 e2 45 8e 83 b9 ac \\
                              31 33 56 61 fa 00 01
                              \\___________________________/
                               these 16 bytes are the bind UUID

Omit --bind-uuid to generate a random one; the device will then ask
you to press its button within ~30 s to confirm pairing.


Before running
--------------

Stop or disable the isdt_air_ble integration in Home Assistant so
HA releases the BLE connection. Output is written to stdout and to a
JSONL file -- attach that file to the GitHub issue or share it with
the maintainer.
"""


CHAR_UUID_AF01 = "0000af01-0000-1000-8000-00805f9b34fb"
CHAR_UUID_AF02 = "0000af02-0000-1000-8000-00805f9b34fb"

CMD_BIND_REQ = 0x18
RESP_BIND = 0x19
BIND_STATUS = 0x01

CMD_HARDWARE_INFO_REQ = bytes([0xE0])
CMD_ALARM_TONE_REQ = bytes([0x12, 0x92])
CMD_ELECTRIC_REQ = bytes([0x12, 0xE4])
CMD_WORKSTATE_REQ = bytes([0x13, 0xE6])
CMD_IR_REQ = bytes([0x13, 0xFA])

RESP_HARDWARE_INFO = 0xE1
RESP_ELECTRIC = 0xE5
RESP_WORKSTATE = 0xE7
RESP_IR = 0xFB
RESP_ALARM_TONE = 0x93

RESP_NAMES = {
    RESP_BIND: "BindResp",
    RESP_HARDWARE_INFO: "HardwareInfoResp",
    RESP_ELECTRIC: "ElectricResp",
    RESP_WORKSTATE: "WorkStateResp",
    RESP_IR: "IRResp",
    RESP_ALARM_TONE: "AlarmToneResp",
}


def now() -> str:
    return _dt.datetime.now().isoformat(timespec="milliseconds")


def hexs(data: bytes) -> str:
    return " ".join(f"{b:02x}" for b in data)


def classify(data: bytes) -> str:
    if len(data) >= 1 and data[0] in RESP_NAMES:
        return RESP_NAMES[data[0]]
    if len(data) >= 2 and data[1] in RESP_NAMES:
        return f"frame({RESP_NAMES[data[1]]})"
    return "unknown"


class Capture:
    def __init__(self, path: str | None) -> None:
        self.path = path
        self.fp = open(path, "w", encoding="utf-8") if path else None
        self.events: list[dict] = []

    def write(self, kind: str, **fields) -> None:
        entry = {"t": now(), "kind": kind, **fields}
        self.events.append(entry)
        if self.fp is not None:
            self.fp.write(json.dumps(entry) + "\n")
            self.fp.flush()
        print(f"[{entry['t']}] {kind}: " + ", ".join(
            f"{k}={v}" for k, v in fields.items()
        ))

    def close(self) -> None:
        if self.fp is not None:
            self.fp.close()


async def find_device(mac: str, timeout: float = 10.0):
    print(f"scanning for {mac} (timeout {timeout:.0f}s)…")
    return await BleakScanner.find_device_by_address(mac, timeout=timeout)


async def do_bind(client: BleakClient, bind_uuid: bytes, capture: Capture) -> bool:
    queue: asyncio.Queue = asyncio.Queue()

    def af02_cb(_sender, data: bytearray) -> None:
        b = bytes(data)
        capture.write(
            "notify",
            char="AF02",
            cls=classify(b),
            len=len(b),
            hex=hexs(b),
        )
        try:
            queue.put_nowait(b)
        except asyncio.QueueFull:
            pass

    await client.start_notify(CHAR_UUID_AF02, af02_cb)
    await asyncio.sleep(0.3)

    packet = bytes([CMD_BIND_REQ]) + bind_uuid + bytes([0x00, BIND_STATUS])
    capture.write("write", char="AF02", purpose="BindReq", len=len(packet), hex=hexs(packet))
    await client.write_gatt_char(CHAR_UUID_AF02, packet, response=False)

    try:
        async with asyncio.timeout(60.0):
            while True:
                data = await queue.get()
                if len(data) >= 2 and data[0] == RESP_BIND:
                    if data[1] == 0:
                        capture.write("bind", status="ok")
                        return True
                    if data[1] == 1:
                        print(
                            "\n  ⚠  Device is waiting for the button press.\n"
                            "     Press the button on the charger to confirm "
                            "pairing.\n"
                        )
                        capture.write("bind", status="waiting_for_button")
                        continue
                    capture.write("bind", status=f"unknown:{data[1]}")
                    return False
    except asyncio.TimeoutError:
        capture.write("bind", status="timeout")
        return False
    finally:
        try:
            await client.stop_notify(CHAR_UUID_AF02)
        except Exception:
            pass


async def probe_once(
    client: BleakClient,
    capture: Capture,
    *,
    channels: list[int],
    settle: float,
) -> None:
    af01_queue: asyncio.Queue = asyncio.Queue()
    af02_queue: asyncio.Queue = asyncio.Queue()

    def make_cb(name: str, queue: asyncio.Queue):
        def cb(_sender, data: bytearray) -> None:
            b = bytes(data)
            capture.write(
                "notify",
                char=name,
                cls=classify(b),
                len=len(b),
                hex=hexs(b),
            )
            try:
                queue.put_nowait(b)
            except asyncio.QueueFull:
                pass
        return cb

    await client.start_notify(CHAR_UUID_AF01, make_cb("AF01", af01_queue))
    await client.start_notify(CHAR_UUID_AF02, make_cb("AF02", af02_queue))
    await asyncio.sleep(0.3)

    # Hardware info (read once)
    capture.write("write", char="AF02", purpose="HardwareInfoReq",
                  len=len(CMD_HARDWARE_INFO_REQ), hex=hexs(CMD_HARDWARE_INFO_REQ))
    await client.write_gatt_char(CHAR_UUID_AF02, CMD_HARDWARE_INFO_REQ, response=False)
    await asyncio.sleep(settle)

    # Alarm tone (read once)
    capture.write("write", char="AF01", purpose="AlarmToneReq",
                  len=len(CMD_ALARM_TONE_REQ), hex=hexs(CMD_ALARM_TONE_REQ))
    await client.write_gatt_char(CHAR_UUID_AF01, CMD_ALARM_TONE_REQ, response=False)
    await asyncio.sleep(settle)

    # Per channel: WorkState, Electric, IR
    for ch in channels:
        capture.write("section", channel=ch)

        for name, base in (("WorkStateReq", CMD_WORKSTATE_REQ),
                           ("ElectricReq",  CMD_ELECTRIC_REQ),
                           ("IRReq",        CMD_IR_REQ)):
            pkt = base + bytes([ch])
            capture.write("write", char="AF01", purpose=name, channel=ch,
                          len=len(pkt), hex=hexs(pkt))
            await client.write_gatt_char(CHAR_UUID_AF01, pkt, response=False)
            await asyncio.sleep(settle)

    await asyncio.sleep(1.0)
    try:
        await client.stop_notify(CHAR_UUID_AF01)
    except Exception:
        pass
    try:
        await client.stop_notify(CHAR_UUID_AF02)
    except Exception:
        pass


async def main() -> int:
    ap = argparse.ArgumentParser(
        description=DESCRIPTION,
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--mac", required=True, help="BLE MAC address of the charger")
    ap.add_argument("--bind-uuid", default=None,
                    help="16-byte bind UUID as hex (with or without spaces). "
                         "Omit to generate a random one (requires button press).")
    ap.add_argument("--channels", default="0-5",
                    help="Channel range to probe (default 0-5 = C4 Air). "
                         "Examples: '0' (Air 8 single channel), '0-7' (A8 Air), "
                         "'0,3,5'.")
    ap.add_argument("--settle", type=float, default=1.0,
                    help="Seconds to wait after each request (default 1.0).")
    ap.add_argument("--label", default="run",
                    help="Free-text label saved in the capture (e.g. 'c4air_empty', "
                         "'c4air_1cell_charging', 'air8_6s_idle').")
    ap.add_argument("--output", default=None,
                    help="JSONL file to write (default: "
                         "isdt_probe_<label>_<ts>.jsonl).")
    args = ap.parse_args()

    channels: list[int] = []
    for part in args.channels.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            channels.extend(range(int(a), int(b) + 1))
        else:
            channels.append(int(part))

    if args.bind_uuid:
        hex_only = args.bind_uuid.replace(" ", "").replace(":", "")
        try:
            bind_uuid = bytes.fromhex(hex_only)
        except ValueError:
            sys.exit(
                f"--bind-uuid must be 32 hex characters (16 bytes), "
                f"got {len(hex_only)} characters including non-hex content "
                f"({args.bind_uuid!r}). Omit --bind-uuid to generate a "
                f"random one and confirm pairing with the device button."
            )
        if len(bind_uuid) != 16:
            sys.exit(
                f"--bind-uuid must be 16 bytes (32 hex chars), got "
                f"{len(bind_uuid)} bytes from {hex_only!r}."
            )
    else:
        bind_uuid = secrets.token_bytes(16)
        print(f"generated random bind UUID: {hexs(bind_uuid)}")

    ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_label = "".join(c if c.isalnum() else "_" for c in args.label)
    out_path = args.output or f"isdt_probe_{safe_label}_{ts}.jsonl"
    capture = Capture(out_path)
    capture.write("meta", mac=args.mac, label=args.label, channels=str(channels),
                  bind_uuid=hexs(bind_uuid))

    device = await find_device(args.mac, timeout=15.0)
    if device is None:
        capture.write("error", reason="device not found")
        capture.close()
        return 1

    print(f"connecting to {device.address} ({device.name or '?'})…")
    async with BleakClient(device) as client:
        try:
            mtu = getattr(client, "mtu_size", None)
            capture.write("connect", mtu=mtu)
        except Exception:
            capture.write("connect", mtu="?")

        ok = await do_bind(client, bind_uuid, capture)
        if not ok:
            capture.write("error", reason="bind failed")
            capture.close()
            return 2

        await probe_once(client, capture, channels=channels, settle=args.settle)

    capture.write("done", events=len(capture.events))
    capture.close()
    print(f"\ncapture written to {os.path.abspath(out_path)}")
    print("Attach this file to the GitHub issue.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
