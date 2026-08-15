# ISDT Air BLE – Home Assistant Integration

[![HACS Default](https://img.shields.io/badge/HACS-Default-41BDF5.svg)](https://github.com/hacs/default)
[![GitHub Release](https://img.shields.io/github/v/release/mtheli/isdt_air_ble)](https://github.com/mtheli/isdt_air_ble/releases)
[![License: MIT](https://img.shields.io/github/license/mtheli/isdt_air_ble)](LICENSE)

Custom Home Assistant integration for **ISDT chargers** and the **MASS2** USB power adapter with Bluetooth Low Energy (BLE) connectivity. Communicates directly with the device via a persistent BLE connection — no cloud, no app required.

Supports the **C4 Air** (6-channel charger), **A8 Air** (8-channel charger), **Air 8** (1S–8S LiPo balance charger), and **MASS2** (8-port USB adapter).

![Device Overview](images/device_overview.png)

## Lovelace Card

A matching dashboard card is available: **[ISDT Charger Card](https://github.com/mtheli/isdt_air_card)** — battery-style slots with live charge timer, connection indicator, and full HA theme support.

![ISDT Charger Card](images/lovelace_card.png)

## Supported Devices

> **Note:** This integration has been tested with the **ISDT C4 Air**, **ISDT A8 Air** (round-cell chargers), the **ISDT MASS2** (USB power adapter), and the **ISDT Air 8** (LiPo balance charger). Support for the **K2 Air** was added in v0.9.1 and is currently being validated by a community tester. Other ISDT devices with BLE support may work but are untested.

| Model | Type | Status |
|-------|------|--------|
| ISDT C4 Air | 6-Channel Round-Cell Charger | Tested ✓ ([@mtheli](https://github.com/mtheli)) |
| ISDT A8 Air | 8-Channel Round-Cell Charger | Tested ✓ ([@stuartp44](https://github.com/stuartp44)) |
| ISDT MASS2 | USB Adapter | Tested ✓ ([@mtheli](https://github.com/mtheli)) |
| ISDT Air 8 | 1S–8S LiPo Balance Charger (single channel, 8 A) | Tested ✓ ([@TRES9000](https://github.com/TRES9000), 6S pack, [issue #2](https://github.com/mtheli/isdt_air_ble/issues/2)) |
| ISDT K2 Air | Dual-Channel LiPo Balance Charger (2 × 1S–6S, 20 A per channel) | Testing in progress ([@Mngnt](https://github.com/Mngnt), [issue #3](https://github.com/mtheli/isdt_air_ble/issues/3)) |
| ISDT Power 200 / 200H / 200X | Desktop Power Supply (wireless pad + 4 USB ports) | Tested ✓ ([@Megachip](https://github.com/Megachip), 200H, [issue #5](https://github.com/mtheli/isdt_air_ble/issues/5)) |
| ISDT NP2 Air | Charger | Untested |
| ISDT LP2 Air | Charger | Untested |
| ISDT K4 | Charger | Untested |
| ISDT 608PD | Charger | Untested |

The integration auto-detects the device model from BLE manufacturer data and exposes the appropriate entities (6 slot sub-devices for C4 Air, 8 slot sub-devices for A8 Air, 1 pack sub-device with per-cell voltage sensors for Air 8, 8 USB port sub-devices for MASS2). Other ISDT devices using the same BLE protocol may also work — feedback and reports are welcome.

## Features

- **Auto-discovery** via Bluetooth — the device appears automatically in Home Assistant
- **One-time pairing** — the bind UUID is stored in the config entry, so the device recognises Home Assistant across restarts (no repeated button presses)
- **Persistent BLE connection** with automatic reconnect
- **Slot / port sub-devices** with detailed per-slot or per-port sensors (6 slots for chargers, 8 USB ports for MASS2)
- **Live charge timer** (chargers) using timestamp-based tracking — updates in real-time in the frontend
- **Hardware info** — firmware version, hardware version, serial number in the device registry
- **Configurable poll interval** (3–300 seconds) via options flow

### Chargers (C4 Air, A8 Air)

**Main device:**

| Sensor | Type | Description |
|--------|------|-------------|
| Connected | Binary (Connectivity) | BLE connection active |
| Input Voltage | Voltage (V) | Power supply voltage |
| Input Current | Current (A) | Total input current |
| Total Charging Current | Current (A) | Sum of all slot currents |
| Slot 1–6/1–8 Status | Enum | `empty`, `idle`, `charging`, `done`, `error` (6 slots for C4 Air, 8 slots for A8 Air) |
| Signal Strength | RSSI (dBm) | BLE signal strength (disabled by default) |
| Beep | Switch | Toggle the charger alarm/beep tone (C4 Air only) |

**Per slot (sub-device):**

| Sensor | Type | Description |
|--------|------|-------------|
| Charging | Binary (Charging) | Whether the slot is actively charging |
| Battery Inserted | Binary (Plug) | Whether a battery is present in the slot |
| Error | Binary (Problem) | Whether the slot has a charging error |
| Output Voltage | Voltage (V) | Slot output voltage |
| Charging Current | Current (A) | Slot charging current |
| Capacity | Battery (%) | Current charge level (hidden when no battery inserted) |
| Capacity Charged | mAh | Charged capacity in current session |
| Energy Charged | Energy (Wh) | Charged energy in current session |
| Charging Since | Timestamp | Charge start time (live-updating) |
| Battery Type | Text | Detected chemistry (LiPo, NiMH, LiFe, etc.) |
| Internal Resistance | mOhm | Battery internal resistance |
| Cell 1–16 Voltage | Voltage (V) | Individual cell voltages (C4 Air only, disabled by default) |

### MASS2 USB Adapter

**Main device:**

| Entity | Type | Description |
|--------|------|-------------|
| Connected | Binary (Connectivity) | BLE connection active |
| Total Power | Power (W) | Sum of all port power draw |
| USB-C1…C6 / USB-A1–A2 Status | Enum | `off`, `idle`, `active` |
| Signal Strength | RSSI (dBm) | BLE signal strength (disabled by default) |
| Beep | Switch | Toggle the buzzer for USB events |
| Volume | Select | Buzzer volume — low / medium / high |

**Per USB port (sub-device):**

| Sensor | Type | Description |
|--------|------|-------------|
| Active | Binary (Power) | Whether the port is delivering power |
| Voltage | Voltage (V) | Output voltage |
| Current | Current (A) | Output current |
| Power | Power (W) | Current power draw |
| Protocol | Enum | Charging protocol (`None`, `USB PD`, `Fast Charge`) |

## Screenshots

| Config Flow | Device Overview | Slot Detail |
|:-----------:|:---------------:|:-----------:|
| ![Config Flow](images/config_flow.png) | ![Device Overview](images/device_overview.png) | ![Slot Detail](images/slot_detail.png) |

## Installation

### HACS (recommended)

This integration is available in the **default HACS store** — just click the button below, or search HACS for "ISDT".

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=mtheli&repository=isdt_air_ble&category=integration)

Then restart Home Assistant.

<details>
<summary>Manual installation</summary>

1. Copy the `custom_components/isdt_air_ble` folder into your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant

</details>

## Setup

1. Make sure your Home Assistant has a Bluetooth adapter (built-in or USB)
2. Power on your ISDT device
3. It should be auto-discovered — check **Settings → Devices & Services → Discovered**
4. Click **Configure** and follow the pairing prompt — press any button on the device within 30 seconds to confirm pairing (the MASS2 will beep, chargers wait silently). After the first pairing, subsequent reconnects are silent.

## Configuration

After setup, you can adjust the **poll interval** via the integration options:

1. Go to **Settings → Devices & Services**
2. Find the ISDT device entry
3. Click **Configure**
4. Set the poll interval (default: 5 seconds, range: 3–300)

## BLE Protocol

The integration communicates directly via BLE — no cloud, no account required. All communication is fully local.

Both chargers and the MASS2 adapter use a single GATT service with two characteristics:

- **AF01** – Data polling via continuous command cycling (charger: workstate, electric, IR, alarm tone; MASS2: port status, settings)
- **AF02** – Bind handshake and hardware info query (once after connect, before polling)

Chargers run a 19-command cycle (1 alarm-tone + 6 channels × 3 commands) at 100 ms intervals. The MASS2 uses a single WorkStatus poll per cycle. BLE notifications for the MASS2 are reassembled across fragments to handle the default 23-byte ATT MTU correctly.

For a detailed technical description of the BLE protocol including packet formats, command reference, and timing, see [PROTOCOL.md](PROTOCOL.md).

## Disclaimer

This is an independent community project and is not affiliated with, endorsed by, or sponsored by ISDT. All product names, trademarks, and registered trademarks are property of their respective owners.

## License

[MIT](LICENSE)
