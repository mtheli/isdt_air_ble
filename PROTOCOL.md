# ISDT Charger BLE Protocol

Technical documentation of the BLE protocol used by ISDT chargers (C4 Air, NP2 Air, LP2 Air, etc.).
Reverse-engineered from the ISDT Link Android app and verified against real device communication.

## Overview

The charger exposes a single BLE service (`0000af00-...`) with two GATT characteristics.
Communication follows a simple command/response pattern: the client writes a command and
the charger responds via BLE notifications on the same characteristic.

After connecting, the client performs a **bind handshake** on AF02, optionally queries
**hardware info** on AF02, then enters a continuous **polling loop** on AF01.

## BLE Service & Characteristics

**Service UUID:** `0000af00-0000-1000-8000-00805f9b34fb`

| Characteristic | UUID | Properties | Purpose |
|----------------|------|------------|---------|
| AF01 | `0000af01-0000-1000-8000-00805f9b34fb` | Notify, Write | Data polling (workstate, electric, IR, alarm tone) |
| AF02 | `0000af02-0000-1000-8000-00805f9b34fb` | Notify, Write | Bind handshake & hardware info query |

## Connection Flow

```
Connect
  │
  ├── Enable notifications on AF01
  ├── Wait ~1.0s (let GATT settle)
  │
  ├── Bind Handshake (AF02)
  │     ├── Enable notifications on AF02
  │     ├── Write BindReq
  │     ├── Wait for BindResp
  │     └── Disable notifications on AF02
  │
  ├── Hardware Info Query (AF02, one-time)
  │     ├── Enable notifications on AF02
  │     ├── Write HardwareInfoReq
  │     ├── Wait for HardwareInfoResp
  │     └── Disable notifications on AF02
  │
  └── Polling Loop (AF01)
        ├── Write command
        ├── Wait 100ms
        ├── Write next command
        ├── ... (19 commands per cycle)
        └── Collect & parse notification responses
```

## Bind Handshake (AF02)

After connecting, the client must register itself with the charger. The UUID is generated
once per client instance (random UUID, 16 bytes).

### BindReq (0x18)

Written to AF02. Total length: 19 bytes.

```
Offset  Length  Field
──────  ──────  ─────────────
0       1       Command: 0x18
1       16      Client UUID (random, 16 bytes)
17      1       Reserved: 0x00
18      1       Status: 0x00
```

### BindResp (0x19)

Received via AF02 notification.

```
Offset  Length  Field
──────  ──────  ─────────────
0       1       Command: 0x19
1       1       Bound status (0 = OK)
```

## Hardware Info Query (AF02)

One-time query after connect to retrieve firmware version, hardware version, and serial number.

### HardwareInfoReq (0xE0)

Written to AF02. Single byte.

```
Offset  Length  Field
──────  ──────  ─────────────
0       1       Command: 0xE0
```

### HardwareInfoResp (0xE1)

Received via AF02 notification. Total length: 13 bytes.

```
Offset  Length  Field
──────  ──────  ─────────────
0       1       Command: 0xE1
1       1       HW version major
2       1       HW version minor
3       1       FW version major
4       1       FW version minor
5       8       Device ID (uint64, little-endian) → serial number
```

## Polling Commands (AF01)

All polling commands are written to AF01. Responses arrive as AF01 notifications.
Commands are sent one at a time with a 100ms interval.

### Command Cycle

One full cycle consists of 19 commands:

| # | Command | Channel | Description |
|---|---------|---------|-------------|
| 1 | AlarmToneReq | — | Query alarm tone on/off |
| 2–4 | WorkState, Electric, IR | 0 | Slot 1 data |
| 5–7 | WorkState, Electric, IR | 1 | Slot 2 data |
| 8–10 | WorkState, Electric, IR | 2 | Slot 3 data |
| 11–13 | WorkState, Electric, IR | 3 | Slot 4 data |
| 14–16 | WorkState, Electric, IR | 4 | Slot 5 data |
| 17–19 | WorkState, Electric, IR | 5 | Slot 6 data |

At 100ms per command, one full cycle takes approximately 1.9 seconds.

### AlarmToneReq (0x12 0x92)

Queries the current alarm tone status.

```
Write:    [0x12, 0x92]
Response: [addr, 0x93, state]
```

`state`: 0 = off, non-zero = on.

### AlarmToneSet (0x13 0x9C)

Sets the alarm tone. Append the task type byte.

```
Write:    [0x13, 0x9C, task_type]
```

### ElectricReq (0x12 0xE4)

Queries voltages, currents, and cell voltages for a channel.

```
Write:    [0x12, 0xE4, channel]
Response: [addr, 0xE5, channel, ...]
```

**ElectricResp (0xE5)** — two formats depending on response length:

**Long format (> 35 bytes):** 4-byte voltages, up to 16 cells.

```
Offset  Length  Field               Unit
──────  ──────  ─────────────       ────
0       1       Address byte
1       1       Command: 0xE5
2       1       Channel (0–5)
3       4       Input voltage       mV (LE) → ÷1000 = V
7       4       Input current       mA (LE) → ÷1000 = A
11      4       Output voltage      mV (LE) → ÷1000 = V
15      4       Charging current    mA (LE) → ÷1000 = A
19      32      Cell voltages ×16   mV (LE, 2 bytes each) → ÷1000 = V
```

**Short format (≤ 35 bytes):** 2-byte voltages, up to 8 cells.

```
Offset  Length  Field               Unit
──────  ──────  ─────────────       ────
0       1       Address byte
1       1       Command: 0xE5
2       1       Channel (0–5)
3       2       Input voltage       mV (LE) → ÷1000 = V
5       4       Input current       mA (LE) → ÷1000 = A
9       2       Output voltage      mV (LE) → ÷1000 = V
11      4       Charging current    mA (LE) → ÷1000 = A
15      16      Cell voltages ×8    mV (LE, 2 bytes each) → ÷1000 = V
```

### WorkStateReq (0x13 0xE6)

Queries charge state, capacity, battery type, timing, and error info for a channel.

```
Write:    [0x13, 0xE6, channel]
Response: [addr, 0xE7, channel, ...]
```

**WorkStateResp (0xE7):**

```
Offset  Length  Field                       Unit / Values
──────  ──────  ─────────────               ─────────────
0       1       Address byte
1       1       Command: 0xE7
2       1       Channel (0–5)
3       1       Work state                  See table below
4       1       Capacity percentage         0–100 (%)
5       4       Capacity done               mAh (LE)
9       4       Energy done                 mWh (LE)
13      4       Work period                 ms (LE)
17      1       Battery type                See table below
18      1       Unit serials count
19      1       Link type
20      2       Full charged voltage        mV (LE) → ÷1000 = V
22      4       Work current                mA (LE) → ÷1000 = A
26      2       Battery count (whole)       LE
28      2       Battery count (current)     LE
30      2       Min input voltage           mV (LE) → ÷1000 = V
32      4       Max output power            mW (LE) → ÷1000 = W
36      2       Error code                  LE (0 = no error)
38      1       Parallel state (optional)   0 or 1
```

**Work State values:**

| Value | State | Description |
|-------|-------|-------------|
| 0 | idle | No activity |
| 1 | charging | Pre-charge / trickle phase |
| 2 | charging | CC (constant current) phase |
| 3 | charging | Active charging |
| 4 | charging | CV (constant voltage) / topping phase |
| 5 | error | Charging error |
| 6 | done | Fully charged |

**Battery Type values:**

| Value | Type | Description |
|-------|------|-------------|
| 0 | LiHV | 4.35V Lithium High Voltage |
| 1 | LiIon | 4.20V Standard Lithium-Ion |
| 2 | LiFe | 3.65V Lithium Iron Phosphate (LiFePO4) |
| 3 | NiZn | Nickel-Zinc |
| 4 | NiMH/Cd | Nickel Metal Hydride / Cadmium |
| 5 | LiIon | 1.50V Lithium-Ion (special variant) |
| 6 | Auto | Automatic detection |

### IRReq (0x13 0xFA)

Queries internal resistance per cell for a channel.

```
Write:    [0x13, 0xFA, channel]
Response: [addr, 0xFB, channel, ...]
```

**IRResp (0xFB):**

```
Offset  Length  Field               Unit
──────  ──────  ─────────────       ────
0       1       Address byte
1       1       Command: 0xFB
2       1       Channel (0–5)
3       N×2     IR per cell         0.1 mΩ (LE, 2 bytes each)
```

Number of cells is derived from response length:
- ≥ 20 bytes → 16 cells
- \> 15 bytes → 8 cells
- = 15 bytes → 6 cells
- else → (length − 3) / 2

Values of 0 or ≥ 10000 (1000 mΩ) are treated as invalid / no cell present.

## Device Discovery

ISDT chargers advertise with manufacturer data using company ID `0xABBA` (43962).
The device model is identified from bytes 2–5 of the manufacturer data payload:

| Bytes [2:6] | Model |
|-------------|-------|
| `01010000` | NP2 Air |
| `01020000` | LP2 Air |
| `01030000` | C4 Air |
| `01040000` | C4 EVO |
| `01050000` | 608PD |
| `01060000` | K4 |
| `01070000` | C4 Air |
| `01080000` | Power 200 |
| `01100000` | PB70W |
| `01110000` | EDGE |
| `01120000` | PB100W |

## Timing

| Parameter | Value | Notes |
|-----------|-------|-------|
| Post-connect settle | 1.0s | Wait after GATT connection before bind |
| Post-notification setup | 0.5s | Wait after enabling AF01 notifications |
| Command interval | 100ms | Delay between individual polling commands |
| Full cycle | ~1.9s | 19 commands × 100ms |
| Bind timeout | 3.0s | Max wait for BindResp on AF02 |
| Hardware info timeout | 3.0s | Max wait for HardwareInfoResp on AF02 |

## Known Quirks

- **Disconnect after ~2 minutes:** The charger may randomly disconnect the BLE connection.
  This appears to be a firmware behavior, not caused by the client. The integration handles
  this by automatically reconnecting.

- **Long/short ElectricResp format:** The response length varies by device model. Devices
  supporting more cells (e.g. for multi-cell LiPo packs) use the long format with 4-byte
  voltage fields and 16 cell slots. Single-cell charger modes use the short format.

- **HardwareInfoResp offset:** Some devices include an address prefix byte before the
  command byte (0xE1), others don't. The parser checks both positions.

- **NiMH charging protection:** NiMH/Cd batteries use Delta-Peak detection (-△V) for
  charge termination. The charger monitors for a small voltage drop (configurable 3–12 mV)
  indicating a full battery. An optional capacity limit (1000–4000 mAh) serves as a
  secondary safety cutoff.
