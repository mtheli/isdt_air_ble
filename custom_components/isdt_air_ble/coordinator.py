import asyncio
import logging
from datetime import timedelta

from bleak import BleakClient
from bleak_retry_connector import establish_connection

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.components import bluetooth

_LOGGER = logging.getLogger(__name__)

# WorkState Status Mapping
WORK_STATE_MAP = {
    0: "idle",
    1: "unknown_1",  # Zu bestimmen
    2: "done",
    3: "charging",  # BESTÄTIGT: Orange mit Blitz in App
    4: "unknown_4",  # Zu bestimmen
    5: "error",
}

# Battery Type Mapping (aus C4AirModel.java setChemistryCapacity)
BATTERY_TYPE_MAP = {
    0: "LiHV",  # 4.35V Lithium High Voltage
    1: "LiIon",  # 4.20V Standard Lithium-Ion
    2: "LiFe",  # 3.65V Lithium Iron Phosphate (LiFePO4)
    3: "NiZn",  # Nickel-Zinc
    4: "NiMH/Cd",  # Nickel Metal Hydride / Cadmium
    5: "LiIon",  # 1.50V Lithium-Ion (spezielle Variante)
    6: "Auto",  # Automatische Erkennung
}


class ISDTDataUpdateCoordinator(DataUpdateCoordinator):
    """Klasse zur Verwaltung der Datenabfrage vom C4 Air."""

    def __init__(self, hass, address):
        super().__init__(
            hass,
            _LOGGER,
            name="ISDT C4 Air",
            update_interval=timedelta(seconds=30),
        )
        self.address = address
        self.data = {}  # Struktur: {channel: {key: value, ...}}

    async def _async_update_data(self):
        """Daten vom Lader abrufen – pro Channel abfragen."""
        ble_device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if not ble_device:
            raise UpdateFailed(f"Gerät {self.address} nicht gefunden")

        client: BleakClient | None = None

        try:
            # Establish a connection
            client = await establish_connection(
                BleakClient, ble_device, "ISDT C4 Air", timeout=15
            )

            # Ensure services are discovered
            if not client.services:
                _LOGGER.debug("Services not discovered yet, discovering...")
                await client.get_services()
                _LOGGER.debug(
                    "Services discovered: %d services found",
                    len(client.services.services),
                )

            char_uuid = "0000af01-0000-1000-8000-00805f9b34fb"

            response_queue = asyncio.Queue()

            def callback(sender, data):
                _LOGGER.debug("Notification empfangen: %s", data.hex(" "))
                response_queue.put_nowait(data)

            await client.start_notify(char_uuid, callback)

            # Alle 6 Channels (0–5) abfragen
            for channel in range(6):
                # ElectricReq pro Channel (CMD 0xE4)
                electric_req = bytearray([0x12, 0xE4, channel])
                await client.write_gatt_char(char_uuid, electric_req, response=False)
                await asyncio.sleep(0.4)

                # ChargerWorkStateReq pro Channel (CMD 0xE6)
                workstate_req = bytearray([0x13, 0xE6, channel])
                await client.write_gatt_char(char_uuid, workstate_req, response=False)
                await asyncio.sleep(0.4)

            # Responses sammeln (mit Timeout)
            responses = []
            try:
                while True:
                    data = await asyncio.wait_for(response_queue.get(), timeout=5.0)
                    responses.append(data)
            except asyncio.TimeoutError:
                pass

            await client.stop_notify(char_uuid)

            return self._parse_responses(responses)

        except Exception as err:
            raise UpdateFailed(f"Fehler bei der Kommunikation: {err}")
        finally:
            if client and client.is_connected:
                await client.disconnect()

    def _parse_responses(self, responses):
        """Alle Responses parsen und pro Channel zuordnen."""
        parsed = {ch: {} for ch in range(6)}

        for raw in responses:
            _LOGGER.debug("RAW DATA vom C4 Air: %s", raw.hex(" "))

            if len(raw) < 3:
                continue

            cmd = raw[1]
            ch = raw[2]

            if cmd == 0xE5:  # ElectricResp
                parsed[ch].update(self._parse_electric(raw))
            elif cmd == 0xE7:  # ChargerWorkStateResp
                parsed[ch].update(self._parse_workstate(raw))
            else:
                _LOGGER.debug(
                    "Unbekannter CMD 0x%02x für Channel %d: %s", cmd, ch, raw.hex(" ")
                )

        _LOGGER.info("Geparste Daten: %s", parsed)
        return parsed

    def _parse_electric(self, data):
        """ElectricResp parsen (Input/Output/Charge + Cell Voltages).

        Basierend auf ElectricResp.java:
        - Unterstützt zwei Paketlängen: < 35 Bytes und > 35 Bytes
        - Kurzes Paket: 2-Byte Voltages, 8 Zellen
        - Langes Paket: 4-Byte Voltages, 16 Zellen
        """
        if len(data) < 15:
            _LOGGER.warning("ElectricResp zu kurz: %d Bytes", len(data))
            return {}

        channel_id = data[2]
        _LOGGER.debug(
            "Parse ElectricResp für Channel %d, Länge: %d", channel_id, len(data)
        )

        # Input Voltage (variabel: 2 oder 4 Bytes)
        if len(data) > 35:
            # Langes Paket: 4 Bytes (data[3:7])
            input_v = int.from_bytes(data[3:7], "little") / 1000.0
            pos = 7
        else:
            # Kurzes Paket: 2 Bytes (data[3:5])
            input_v = int.from_bytes(data[3:5], "little") / 1000.0
            pos = 5

        # Input Current (immer 4 Bytes)
        input_a = int.from_bytes(data[pos : pos + 4], "little") / 1000.0
        pos += 4

        # Output Voltage (variabel: 2 oder 4 Bytes)
        if len(data) > 35:
            # Langes Paket: 4 Bytes
            output_v = int.from_bytes(data[pos : pos + 4], "little") / 1000.0
            pos += 4
        else:
            # Kurzes Paket: 2 Bytes
            output_v = int.from_bytes(data[pos : pos + 2], "little") / 1000.0
            pos += 2

        # Charging Current (immer 4 Bytes)
        charge_a = int.from_bytes(data[pos : pos + 4], "little") / 1000.0
        pos += 4

        # Cell Voltages parsen (8 oder 16 Zellen à 2 Bytes)
        cell_voltages = []
        num_cells = 16 if len(data) >= 35 else 8

        for i in range(num_cells):
            if pos + 2 <= len(data):
                cell_v = int.from_bytes(data[pos : pos + 2], "little") / 1000.0
                cell_voltages.append(cell_v)
                pos += 2
            else:
                break

        result = {
            "channel_id": channel_id,
            "input_voltage": input_v,
            "input_current": input_a,
            "output_voltage": output_v,
            "charging_current": charge_a,
            "cell_voltages": cell_voltages,
        }

        _LOGGER.debug(
            "Channel %d: In=%.2fV/%.3fA, Out=%.2fV, Charge=%.3fA, Cells=%d",
            channel_id,
            input_v,
            input_a,
            output_v,
            charge_a,
            len([c for c in cell_voltages if c > 0]),
        )

        return result

    def _parse_workstate(self, data):
        """ChargerWorkStateResp parsen (Status, Kapazität, Zeit, etc.)."""
        if len(data) < 38:
            _LOGGER.warning("WorkStateResp zu kurz: %d Bytes", len(data))
            return {}

        channel_id = data[2]
        _LOGGER.debug("Parse WorkStateResp für Channel %d", channel_id)

        # Status und Prozent
        work_state = data[3]
        capacity_percentage = data[4]

        # Kapazität in mAh (direkt, KEINE Division!)
        capacity_done = int.from_bytes(data[5:9], "little")

        # Energie in mWh
        energy_done = int.from_bytes(data[9:13], "little")

        # Ladezeit in Millisekunden (!) → Sekunden
        work_period_ms = int.from_bytes(data[13:17], "little")
        work_period = work_period_ms // 1000  # Konvertiere zu Sekunden

        # Akkutyp und Konfiguration
        battery_type = data[17]
        unit_serials_num = data[18]
        link_type = data[19]

        # Spannungen und Ströme
        full_charged_volt = int.from_bytes(data[20:22], "little") / 1000.0  # mV → V
        work_current = int.from_bytes(data[22:26], "little") / 1000.0  # mA → A

        # Akkuanzahl
        charging_battery_num_whole = int.from_bytes(data[26:28], "little")
        charging_battery_num_current = int.from_bytes(data[28:30], "little")

        # Limits
        min_input_volt = int.from_bytes(data[30:32], "little") / 1000.0  # mV → V
        max_output_power = int.from_bytes(data[32:36], "little") / 1000.0  # mW → W

        # Fehlercode
        error_code = int.from_bytes(data[36:38], "little")

        # Optional: Parallel State
        parallel_state = None
        if len(data) > 38:
            parallel_state = data[38] == 1

        # Status-String
        work_state_str = WORK_STATE_MAP.get(work_state, f"unknown_{work_state}")
        battery_type_str = BATTERY_TYPE_MAP.get(battery_type, f"unknown_{battery_type}")

        # Zeit formatieren (HH:MM:SS)
        hours = work_period // 3600
        minutes = (work_period % 3600) // 60
        seconds = work_period % 60
        work_period_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

        # Energie in Wh umrechnen
        energy_done_wh = energy_done / 1000.0

        result = {
            "work_state": work_state,
            "work_state_str": work_state_str,
            "capacity_percentage": capacity_percentage,
            "capacity_done": capacity_done,  # mAh
            "energy_done": energy_done,  # mWh
            "energy_done_wh": energy_done_wh,  # Wh
            "work_period": work_period,  # Sekunden
            "work_period_ms": work_period_ms,  # Millisekunden (für Debug)
            "work_period_str": work_period_str,  # HH:MM:SS
            "battery_type": battery_type,
            "battery_type_str": battery_type_str,
            "unit_serials_num": unit_serials_num,
            "link_type": link_type,
            "full_charged_volt": full_charged_volt,
            "work_current": work_current,
            "charging_battery_num_whole": charging_battery_num_whole,
            "charging_battery_num_current": charging_battery_num_current,
            "min_input_volt": min_input_volt,
            "max_output_power": max_output_power,
            "error_code": error_code,
            "parallel_state": parallel_state,
        }

        _LOGGER.debug(
            "Channel %d: State=%s, %d%%, %d mAh, %s (ms=%d), Type=%s",
            channel_id,
            work_state_str,
            capacity_percentage,
            capacity_done,
            work_period_str,
            work_period_ms,
            battery_type_str,
        )

        return result
