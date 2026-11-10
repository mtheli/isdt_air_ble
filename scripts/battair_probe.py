#!/usr/bin/env python3
"""ISDT BattAir probe.

Captures what BattAir smart packs and BattAir Plugins send over BLE, so the
data can be checked and later used as test fixtures for the isdt_air_ble
Home Assistant integration.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as _dt
import json
import re
import sys

try:
    from bleak import BleakClient, BleakScanner
except ImportError:
    sys.exit("bleak is required: pip install bleak")


DESCRIPTION = (
    "Capture advertisements (scan) or query a single pack over a connection "
    "(connect) from ISDT BattAir packs and BattAir Plugins."
)

EPILOG = """\
Examples
--------

  # Listen to all BattAir devices nearby for 2 minutes (no connection):
  battair_probe.py scan --time 120 --label "4s_and_6s_storage"

  # Connect to one pack and read cell voltages, currents, cycles, ...:
  battair_probe.py connect --mac AA:BB:CC:DD:EE:FF --label "6s_plugin"

  # Same, repeated every 60 s for 10 minutes:
  battair_probe.py connect --mac AA:BB:CC:DD:EE:FF --every 60 --time 600


Before running
--------------

Disconnect the packs from your phone first, a connected pack stops
advertising and only accepts one connection. The scan prints each
device's address; use it for --mac.

The connect mode needs the real MAC address of the pack. Windows and
Linux show it during the scan. macOS hides it behind a random ID; in
that case pass the real MAC with --real-mac (it is printed on the
pack's label or shown in a BLE scanner app on a phone).

The connect mode only sends read requests. It does not change any
setting on the pack.

Output is written to stdout and to a JSONL file -- attach that file to
the GitHub issue.
"""

NAME_PREFIXES = ("BATAIR", "OTAOTA")
SERVICE_UUID = "0000ba00-0000-1000-8000-00805f9b34fb"
CHAR_UUID_BA01 = "0000ba01-0000-1000-8000-00805f9b34fb"

BATTERY_TYPES = {
    0: "LiHv",
    1: "LiPo",
    2: "LiIon",
    3: "LiFe",
    4: "Pb",
    5: "NiMH/NiCd",
    6: "LiUHv",
}

# Read-only requests: (command, extra payload bytes, label).
# The response command is always the request command + 1.
QUERIES = [
    (0x02, b"", "HardwareInfo"),
    (0x0A, b"", "BleName"),
    (0x16, b"", "OEMName"),
    (0x10, b"\x00", "CellVoltages"),
    (0x12, b"", "RealTime"),
    (0x04, b"", "AbnormalStatistics"),
    (0x0E, b"", "UserParameter"),
    (0x14, b"", "OEMParameter"),
    (0x1A, b"", "GSensor"),
    (0x1E, b"", "Filter"),
    (0x26, b"", "Transportation"),
    (0x28, b"", "ActivationDays"),
]

MAC_RE = re.compile(r"^[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}$")


def now() -> str:
    return _dt.datetime.now().isoformat(timespec="milliseconds")


def hexs(data: bytes) -> str:
    return data.hex(" ")


def u16(data: bytes, offset: int):
    if len(data) < offset + 2:
        return None
    return data[offset] | (data[offset + 1] << 8)


def u32(data: bytes, offset: int):
    if len(data) < offset + 4:
        return None
    return int.from_bytes(data[offset:offset + 4], "little")


def s8(data: bytes, offset: int):
    if len(data) <= offset:
        return None
    value = data[offset]
    return value - 256 if value > 127 else value


class Capture:
    def __init__(self, path: str):
        self.path = path
        self.fp = open(path, "w", encoding="utf-8")

    def log(self, kind: str, **fields) -> None:
        entry = {"t": now(), "kind": kind, **fields}
        self.fp.write(json.dumps(entry) + "\n")
        self.fp.flush()

    def close(self) -> None:
        self.fp.close()


# --------------------------------------------------------------------------
# Advertisement
# --------------------------------------------------------------------------

def decode_advert(payload: bytes) -> dict:
    """Decode manufacturer data (company ID already stripped)."""
    out = {}
    if len(payload) >= 1:
        battery = (payload[0] >> 4) & 0x0F
        out["device_type"] = payload[0] & 0x0F
        out["battery_type"] = BATTERY_TYPES.get(battery, f"unknown({battery})")
    if len(payload) >= 4:
        out["status_bits"] = f"0x{payload[3]:02x}"
    voltage = u16(payload, 4)
    if voltage is not None:
        out["voltage_v"] = round(voltage / 100, 2)
    if len(payload) >= 7:
        out["percentage"] = payload[6]
    out["temperature_c"] = s8(payload, 7)
    out["cycles"] = u16(payload, 8)
    if len(payload) >= 11:
        out["cells"] = payload[10]
    out["field_11_12"] = u16(payload, 11)
    if len(payload) >= 14:
        out["byte_13"] = payload[13]
    if len(payload) > 14:
        out["tail_ascii"] = payload[14:].decode("ascii", errors="replace").rstrip("\x00 ")
    return {k: v for k, v in out.items() if v is not None}


def is_battair(device, adv) -> bool:
    name = (adv.local_name or device.name or "").upper()
    if name.startswith(NAME_PREFIXES):
        return True
    return SERVICE_UUID in [u.lower() for u in adv.service_uuids or []]


async def run_scan(args, cap: Capture) -> None:
    last = {}

    def on_advert(device, adv):
        if not is_battair(device, adv):
            return
        mfr = {f"0x{cid:04x}": hexs(bytes(d)) for cid, d in adv.manufacturer_data.items()}
        svc = {u: hexs(bytes(d)) for u, d in adv.service_data.items()}
        key = (adv.local_name, tuple(sorted(mfr.items())), tuple(sorted(svc.items())))
        if last.get(device.address) == key:
            return
        last[device.address] = key

        decoded = {cid: decode_advert(bytes(d)) for cid, d in
                   ((f"0x{c:04x}", d) for c, d in adv.manufacturer_data.items())}
        cap.log("advert", address=device.address, name=adv.local_name or device.name,
                rssi=adv.rssi, service_uuids=adv.service_uuids, manufacturer_data=mfr,
                service_data=svc, decoded=decoded)

        print("=" * 72)
        print(f"{now()[11:19]}  {device.address}  name={adv.local_name or device.name!r}  rssi={adv.rssi}")
        for cid, raw in mfr.items():
            print(f"  manufacturer_data {cid}: {raw}")
            for field, value in decoded[cid].items():
                print(f"      {field:<14} {value}")
        for uuid, raw in svc.items():
            print(f"  service_data {uuid}: {raw}")
        if not mfr:
            print("  manufacturer_data: (none)")
        sys.stdout.flush()

    print(f"Scanning for BattAir devices for {args.time} s ... (Ctrl+C to stop)")
    scanner = BleakScanner(detection_callback=on_advert)
    await scanner.start()
    try:
        await asyncio.sleep(args.time)
    finally:
        await scanner.stop()
    print("=" * 72)
    print(f"Found {len(last)} BattAir device(s).")
    cap.log("summary", devices=sorted(last))


# --------------------------------------------------------------------------
# Connection
# --------------------------------------------------------------------------

def decode_response(data: bytes) -> dict:
    """Decode the parts of a response that are understood so far."""
    cmd = data[0]
    out = {}
    if cmd == 0x11 and len(data) > 4:
        cells = [u16(data, i) for i in range(4, len(data) - 1, 2)]
        out["cell_group"] = 0 if data[3] == 0x80 else data[3]
        out["cells_mv"] = [c for c in cells if c]
    elif cmd == 0x13:
        out["temperature_c"] = s8(data, 3)
        out["discharge_current_raw"] = u32(data, 4)
        out["charge_current_raw"] = u32(data, 8)
        if len(data) > 12:
            out["level"] = data[12]
    elif cmd == 0x05:
        out["cycles"] = u16(data, 3)
    elif cmd in (0x0B, 0x17):
        out["text"] = data[3:].decode("ascii", errors="replace").rstrip("\x00 ")
    return {k: v for k, v in out.items() if v is not None}


async def query_once(client: BleakClient, key: int, cap: Capture, queue: asyncio.Queue,
                     timeout: float) -> int:
    answered = 0
    for cmd, extra, label in QUERIES:
        plain = bytes([cmd, 0x00, 0x00]) + extra
        wire = bytes(b ^ key for b in plain)
        while not queue.empty():
            queue.get_nowait()
        cap.log("write", char="BA01", purpose=label, plain=hexs(plain), wire=hexs(wire))
        await client.write_gatt_char(CHAR_UUID_BA01, wire, response=False)
        try:
            while True:
                data = await asyncio.wait_for(queue.get(), timeout)
                if data[0] == cmd + 1:
                    break
        except asyncio.TimeoutError:
            cap.log("timeout", purpose=label)
            print(f"  {label:<20} (no answer)")
            continue
        answered += 1
        decoded = decode_response(data)
        cap.log("response", purpose=label, plain=hexs(data), decoded=decoded)
        print(f"  {label:<20} {hexs(data)}")
        if decoded:
            print(f"  {'':<20} {decoded}")
    return answered


async def run_connect(args, cap: Capture) -> None:
    real_mac = args.real_mac or args.mac
    key = int(real_mac[-2:], 16)
    mac_bytes = bytes(int(p, 16) for p in real_mac.split(":"))
    cap.log("meta_connect", address=args.mac, real_mac=real_mac, key=f"0x{key:02x}")

    print(f"Looking for {args.mac} ...")
    device = await BleakScanner.find_device_by_address(args.mac, timeout=20)
    if device is None:
        sys.exit("Device not found. Is it disconnected from the phone and in range?")

    queue: asyncio.Queue = asyncio.Queue()

    def on_notify(_sender, data: bytearray):
        wire = bytes(data)
        plain = bytes(b ^ key for b in wire)
        cap.log("notify", char="BA01", wire=hexs(wire), plain=hexs(plain))
        if plain:
            queue.put_nowait(plain)

    async with BleakClient(device) as client:
        cap.log("connect", mtu=client.mtu_size)
        print(f"Connected (MTU {client.mtu_size}).")
        await client.start_notify(CHAR_UUID_BA01, on_notify)

        # Handshake with the pack's own MAC before reading.
        if args.handshake:
            plain = b"\x00\x00\x00" + mac_bytes[::-1] + b"\x01\x00"
            wire = bytes(b ^ key for b in plain)
            cap.log("write", char="BA01", purpose="Handshake", plain=hexs(plain), wire=hexs(wire))
            await client.write_gatt_char(CHAR_UUID_BA01, wire, response=False)
            await asyncio.sleep(1.0)

        loop = asyncio.get_running_loop()
        end = loop.time() + args.time
        round_no = 0
        while True:
            round_no += 1
            print(f"--- round {round_no} ({now()[11:19]})")
            cap.log("round", n=round_no)
            answered = await query_once(client, key, cap, queue, args.timeout)
            if round_no == 1 and answered == 0:
                hint = "--no-handshake" if args.handshake else "without --no-handshake"
                print(f"No answers. Try again {hint}.")
                break
            if not args.every or loop.time() + args.every > end:
                break
            await asyncio.sleep(args.every)
        await client.stop_notify(CHAR_UUID_BA01)


# --------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=DESCRIPTION, epilog=EPILOG,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="mode", required=True)

    sp = sub.add_parser("scan", help="listen to advertisements, no connection")
    sp.add_argument("--time", type=int, default=60, help="scan duration in seconds (default 60)")

    cp = sub.add_parser("connect", help="connect to one pack and read its data")
    cp.add_argument("--mac", required=True, help="address shown by the scan")
    cp.add_argument("--real-mac", default=None, help="real MAC, only needed on macOS")
    cp.add_argument("--no-handshake", dest="handshake", action="store_false",
                    help="skip the handshake before reading")
    cp.add_argument("--every", type=int, default=0, help="repeat the reading every N seconds")
    cp.add_argument("--time", type=int, default=600, help="total time when repeating (default 600)")
    cp.add_argument("--timeout", type=float, default=2.0, help="answer timeout per request")

    for p in (sp, cp):
        p.add_argument("--label", default="run", help="short description, used in the file name")
        p.add_argument("--output", default=None, help="output file (default battair_probe_<mode>_<label>_<ts>.jsonl)")

    args = ap.parse_args()
    if args.mode == "connect" and not MAC_RE.match(args.real_mac or args.mac):
        sys.exit("The connect mode needs the real MAC (AA:BB:CC:DD:EE:FF). "
                 "On macOS pass it with --real-mac.")
    safe_label = re.sub(r"[^A-Za-z0-9_-]+", "_", args.label)
    ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = args.output or f"battair_probe_{args.mode}_{safe_label}_{ts}.jsonl"

    cap = Capture(path)
    cap.log("meta", mode=args.mode, label=args.label, platform=sys.platform)
    try:
        if args.mode == "scan":
            asyncio.run(run_scan(args, cap))
        else:
            asyncio.run(run_connect(args, cap))
    except KeyboardInterrupt:
        pass
    finally:
        cap.close()
        print(f"Capture written to {path}")


if __name__ == "__main__":
    main()
