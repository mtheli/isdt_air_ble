#!/usr/bin/env python3
"""ISDT Air8 BLE probe.

Captures raw GATT notifications from an ISDT Air8 (LiPo balance charger,
DeviceModelID 01030000) so the protocol can be implemented in the
isdt_air_ble Home Assistant integration.

Usage
-----

  python3 isdt_air8_probe.py --mac AA:BB:CC:DD:EE:FF \
                             --bind-uuid 9945...61fa \
                             --label "no battery"

The bind UUID is the 16-byte client identifier that was used when the
device was paired the first time. You can read it from a Home Assistant
debug log line like::

    Sending BindReq on AF02: 18 99 45 6a 7c 65 e2 45 8e 83 b9 ac \
                              31 33 56 61 fa 00 01
                                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                                  these 16 bytes are the bind UUID

If --bind-uuid is omitted, a random one is generated and you will be
asked to press the button on the device to confirm pairing.

Before running, **disable** or stop the Home Assistant integration so
that HA releases the BLE connection.

Output goes to stdout and to a JSONL file (one entry per write/notify
event). Attach the JSONL file to the GitHub issue.
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
                            "     Press the button on the Air8 to confirm pairing.\n"
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

    # Alarm tone (read once — same on Air8?)
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
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mac", required=True, help="BLE MAC of the Air8")
    ap.add_argument("--bind-uuid", default=None,
                    help="16-byte bind UUID as hex (with or without spaces). "
                         "Omit to generate a random one (requires button press).")
    ap.add_argument("--channels", default="0-5",
                    help="Channel range to probe (default 0-5, matches Air 8's "
                         "max 6S LiPo). Examples: '0', '0-7', '0,3,5'.")
    ap.add_argument("--settle", type=float, default=1.0,
                    help="Seconds to wait after each request (default 1.0).")
    ap.add_argument("--label", default="run",
                    help="Free-text label saved in the capture (e.g. 'no battery', "
                         "'1S LiPo charging', '6S LiPo done').")
    ap.add_argument("--output", default=None,
                    help="JSONL file to write (default: air8_probe_<label>_<ts>.jsonl).")
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
        bind_uuid = bytes.fromhex(hex_only)
        if len(bind_uuid) != 16:
            sys.exit(f"bind-uuid must be 16 bytes, got {len(bind_uuid)}")
    else:
        bind_uuid = secrets.token_bytes(16)
        print(f"generated random bind UUID: {hexs(bind_uuid)}")

    ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_label = "".join(c if c.isalnum() else "_" for c in args.label)
    out_path = args.output or f"air8_probe_{safe_label}_{ts}.jsonl"
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
