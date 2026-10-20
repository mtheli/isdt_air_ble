
function $parcel$interopDefault(a) {
  return a && a.__esModule ? a.default : a;
}
/**
 * ISDT Air Card – Device-based, HA Theme-Aware
 * Custom Lovelace Card for Home Assistant
 *
 * Selects a device from the isdt_air_ble integration and dynamically
 * discovers all entities via translation_key and sub-device mapping.
 * Supports both chargers (C4 Air etc.) and adapters (MASS2 etc.).
 */ var $76eee68ef692a3c3$exports = {};
$76eee68ef692a3c3$exports = JSON.parse('{"status_empty":"Empty","status_idle":"Idle","status_charging":"Charging","status_done":"Done","status_error":"Error","header_input":"Input","header_current":"Current","header_power":"Power","header_total_charge":"\u03A3 Charge","info_volt":"Volt","info_amp":"Amp","info_time":"Time","info_type":"Type","tooltip_connected":"Connected","tooltip_disconnected":"Disconnected","config_title":"Title (optional \u2013 defaults to device name)","config_show_model":"Show model as subtitle","config_show_header":"Show header with input stats","error_no_device":"Please select a device","section_usbc":"USB-C","section_usba":"USB-A","gauge_of":"of","active_ports":"Active Ports","load":"Load","volume":"Volume","vol_low":"Low","vol_medium":"Med","vol_high":"High","sound_mute":"Muted","sound_low":"Low volume","sound_medium":"Medium volume","sound_high":"High volume","balance_channel":"CH","balance_no_pack":"no pack","outdated_standalone_active":"An outdated standalone copy of this card is active. Remove the standalone ISDT Charger Card (see Settings \u2192 Repairs) to use the up-to-date version bundled with the integration."}');


var $238d401f28c1db46$exports = {};
$238d401f28c1db46$exports = JSON.parse('{"status_empty":"Leer","status_idle":"Bereit","status_charging":"L\xe4dt","status_done":"Fertig","status_error":"Fehler","header_input":"Input","header_current":"Strom","header_power":"Leistung","header_total_charge":"\u03A3 Ladung","info_volt":"Volt","info_amp":"Amp","info_time":"Zeit","info_type":"Typ","tooltip_connected":"Verbunden","tooltip_disconnected":"Getrennt","config_title":"Titel (optional \u2013 Standard ist Ger\xe4tename)","config_show_model":"Modell als Untertitel anzeigen","config_show_header":"Header mit Eingangswerten anzeigen","error_no_device":"Bitte ein Ger\xe4t ausw\xe4hlen","section_usbc":"USB-C","section_usba":"USB-A","gauge_of":"von","active_ports":"Aktive Ports","load":"Auslastung","volume":"Lautst\xe4rke","vol_low":"Leise","vol_medium":"Mittel","vol_high":"Laut","sound_mute":"Stumm","sound_low":"Leise","sound_medium":"Mittel","sound_high":"Laut","balance_channel":"Kanal","balance_no_pack":"kein Akku","outdated_standalone_active":"Eine veraltete separate Kopie dieser Karte ist aktiv. Entferne die separate ISDT Charger Card (siehe Einstellungen \u2192 Reparaturen), um die aktuelle, mit der Integration gelieferte Version zu nutzen."}');


const $d8078e452c66bdbe$var$LOCALES = {
    en: (/*@__PURE__*/$parcel$interopDefault($76eee68ef692a3c3$exports)),
    de: (/*@__PURE__*/$parcel$interopDefault($238d401f28c1db46$exports))
};
function $d8078e452c66bdbe$export$625550452a3fa3ec(hass, key) {
    const lang = hass?.language || 'en';
    const locale = $d8078e452c66bdbe$var$LOCALES[lang] || $d8078e452c66bdbe$var$LOCALES.en;
    return locale[key] || $d8078e452c66bdbe$var$LOCALES.en[key] || key;
}


// Written by the release sync script (isdt_air_ble scripts/sync_card.sh).
const $8ee5ce714273e53b$export$d5e7ce6d07daf10f = "0.11.0-beta.2";
const $8ee5ce714273e53b$export$9b657414b7dffe40 = "bundled";


// Adapter total power limit by model (device-rated, not sum of port maxes).
const $9a3262f48b2f355e$var$ADAPTER_TOTAL_MAX = {
    "MASS2": 200
};
// MASS2 per-port limits (for mini bar showing port load %).
const $9a3262f48b2f355e$var$MASS2_USBC_MAX = 65;
const $9a3262f48b2f355e$var$MASS2_USBA_MAX = 12;
// LiPo balance chargers — render as full-width pack tiles with per-cell
// V + IR chips rather than the AA-style slot grid used for round-cell
// chargers. Stay in sync with BALANCE_CHARGER_MODELS in the integration's
// custom_components/isdt_air_ble/const.py.
const $9a3262f48b2f355e$var$BALANCE_CHARGER_MODELS = new Set([
    "Air 8",
    "K2 Air"
]);
// Maximum number of cells the protocol can report per channel
// (ElectricResp short variant carries 8 cellVoltageList slots).
const $9a3262f48b2f355e$var$MAX_CELLS_PER_CHANNEL = 16;
class $9a3262f48b2f355e$export$fda68d6dc0a4d865 extends HTMLElement {
    constructor(){
        super();
        this.attachShadow({
            mode: "open"
        });
        this._hass = null;
        this._config = null;
        this._entities = null;
        this._timeInterval = null;
        this._lastSlotKey = null;
    }
    static getConfigForm() {
        return {
            schema: [
                {
                    name: "device_id",
                    required: true,
                    selector: {
                        device: {
                            filter: {
                                integration: "isdt_air_ble",
                                entity: [
                                    {
                                        domain: "binary_sensor",
                                        device_class: "connectivity"
                                    }
                                ]
                            },
                            multiple: false
                        }
                    }
                },
                {
                    name: "title",
                    label: (0, $d8078e452c66bdbe$export$625550452a3fa3ec)(null, "config_title"),
                    selector: {
                        text: {}
                    }
                },
                {
                    name: "show_model",
                    label: (0, $d8078e452c66bdbe$export$625550452a3fa3ec)(null, "config_show_model"),
                    selector: {
                        boolean: {}
                    },
                    default: true
                },
                {
                    name: "show_header",
                    label: (0, $d8078e452c66bdbe$export$625550452a3fa3ec)(null, "config_show_header"),
                    selector: {
                        boolean: {}
                    }
                }
            ]
        };
    }
    setConfig(config) {
        this._config = {
            show_header: config.show_header !== false,
            ...config
        };
        if (this._hass && config.device_id) this._entities = this._findEntities(this._hass, config.device_id);
    }
    set hass(hass) {
        this._hass = hass;
        // Rebuild the entity map on every hass update so renames from the
        // HA device registry propagate into the card without a reload.
        // The work is O(n) over the entity registry (once per tick) and
        // the subsequent _render() still falls back to partial updates
        // whenever the structural fingerprint is unchanged.
        if (this._config?.device_id) this._entities = this._findEntities(hass, this._config.device_id);
        this._render();
    }
    /* ── Entity discovery ───────────────────────────────── */ _getDeviceType(hass, deviceId) {
        const dev = hass?.devices?.[deviceId];
        const model = dev?.model || "";
        if (model.toUpperCase().includes("MASS2")) return "adapter";
        if ($9a3262f48b2f355e$var$BALANCE_CHARGER_MODELS.has(model)) return "balance_charger";
        return "charger";
    }
    _findEntities(hass, deviceId) {
        const type = this._getDeviceType(hass, deviceId);
        if (type === "adapter") {
            const entities = this._findAdapterEntities(hass, deviceId);
            entities.type = "adapter";
            return entities;
        }
        if (type === "balance_charger") {
            const entities = this._findChargerEntities(hass, deviceId);
            entities.type = "balance_charger";
            return entities;
        }
        const entities = this._findChargerEntities(hass, deviceId);
        entities.type = "charger";
        return entities;
    }
    _findChargerEntities(hass, deviceId) {
        const main = {
            input_voltage: null,
            input_current: null,
            total_charging_current: null,
            connected: null,
            beep: null
        };
        const slots = {};
        // Find slot sub-devices (via_device_id === main device)
        const slotDeviceMap = {}; // { subDeviceId: slotNumber }
        for (const [devId, device] of Object.entries(hass.devices || {}))if (device.via_device_id === deviceId) {
            const match = device.name.match(/Slot\s+(\d+)/i);
            if (match) slotDeviceMap[devId] = parseInt(match[1]);
        }
        // Map entities by translation_key
        for (const [entityId, entity] of Object.entries(hass.entities || {})){
            const tk = entity.translation_key;
            if (entity.device_id === deviceId) {
                // Main device
                switch(tk){
                    case "input_voltage":
                        main.input_voltage = entityId;
                        break;
                    case "input_current":
                        main.input_current = entityId;
                        break;
                    case "total_charging_current":
                        main.total_charging_current = entityId;
                        break;
                    case "connected":
                        main.connected = entityId;
                        break;
                    case "beep":
                        main.beep = entityId;
                        break;
                    case "status":
                        {
                            // One status sensor per slot — differentiate via entity_id (…_slot_N_status)
                            const m = entityId.match(/_slot_(\d+)_status/);
                            if (m) {
                                const slotNum = parseInt(m[1]);
                                if (!slots[slotNum]) slots[slotNum] = {};
                                slots[slotNum].status = entityId;
                            }
                            break;
                        }
                }
                // Fallback: main-device entities via device_class
                const state = hass.states[entityId];
                const dc = state?.attributes?.device_class;
                if (dc && entity.device_id === deviceId) {
                    if (!main.input_voltage && dc === "voltage") main.input_voltage = entityId;
                    if (!main.input_current && dc === "current") main.input_current = entityId;
                }
            } else if (entity.device_id in slotDeviceMap) {
                // Slot sub-device
                const slotNum = slotDeviceMap[entity.device_id];
                if (!slots[slotNum]) slots[slotNum] = {};
                switch(tk){
                    case "output_voltage":
                        slots[slotNum].output_voltage = entityId;
                        break;
                    case "charging_current":
                        slots[slotNum].charging_current = entityId;
                        break;
                    case "capacity":
                        slots[slotNum].capacity = entityId;
                        break;
                    case "capacity_done":
                        slots[slotNum].capacity_done = entityId;
                        break;
                    case "energy_done":
                        slots[slotNum].energy_done = entityId;
                        break;
                    case "charge_time":
                        slots[slotNum].charge_time = entityId;
                        break;
                    case "battery_type":
                        slots[slotNum].battery_type = entityId;
                        break;
                    case "internal_resistance":
                        slots[slotNum].primary_ir = entityId;
                        break;
                }
                // Per-cell voltage sensors (translation_key "cell_1" .. "cell_16").
                // Used for the balance-charger layout; the IR value lives on the
                // same sensor as an extra attribute (since isdt_air_ble v0.9.2).
                const cellMatch = tk?.match(/^cell_(\d+)$/);
                if (cellMatch) {
                    const cellIdx = parseInt(cellMatch[1]) - 1;
                    if (cellIdx >= 0 && cellIdx < $9a3262f48b2f355e$var$MAX_CELLS_PER_CHANNEL) {
                        slots[slotNum].cells ||= {};
                        slots[slotNum].cells[cellIdx] = entityId;
                    }
                }
                // Fallback: slot entities via device_class
                const slotState = hass.states[entityId];
                const slotDc = slotState?.attributes?.device_class;
                if (slotDc) {
                    if (!slots[slotNum].output_voltage && slotDc === "voltage") slots[slotNum].output_voltage = entityId;
                    if (!slots[slotNum].charging_current && slotDc === "current") slots[slotNum].charging_current = entityId;
                }
            }
        }
        return {
            main: main,
            slots: slots
        };
    }
    _findAdapterEntities(hass, deviceId) {
        const main = {
            total_power: null,
            connected: null,
            beep: null,
            volume: null
        };
        const ports = {};
        // Discover port sub-devices via `device.identifiers`, which the
        // integration sets to `[[DOMAIN, "{mac}_port{N}"]]`. Identifiers
        // are stable against renames and language changes — unlike the
        // device name which the user can customise and which isn't even
        // exposed in every HA version the same way.
        // (entity.unique_id is NOT in the frontend `hass.entities` map,
        //  so we cannot use it here.)
        const portDeviceMap = {}; // { subDeviceId: portNumber }
        for (const [devId, device] of Object.entries(hass.devices || {})){
            if (device.via_device_id !== deviceId) continue;
            for (const ident of device.identifiers || []){
                // `identifiers` comes through as an array of [domain, id] pairs.
                const id = Array.isArray(ident) ? ident[1] : "";
                const m = id.match(/_port(\d+)$/);
                if (!m) continue;
                const portNum = parseInt(m[1]);
                if (portNum < 1 || portNum > 8) continue;
                portDeviceMap[devId] = portNum;
                if (!ports[portNum]) ports[portNum] = {};
                break;
            }
        }
        // Initialise default kind/label for every port slot so the grid
        // always renders 8 tiles (even when some sub-devices are missing).
        for(let n = 1; n <= 8; n++){
            if (!ports[n]) ports[n] = {};
            if (!ports[n].kind) ports[n].kind = n <= 6 ? "C" : "A";
            if (!ports[n].label) ports[n].label = n <= 6 ? `C${n}` : `A${n - 6}`;
        }
        // Pull user-customised display names from the device registry.
        // `name_by_user` is only set when the user explicitly renamed the
        // sub-device in the HA UI — otherwise we keep our short default
        // label ("C1" / "A1") instead of the verbose "ISDT MASS2 USB-C1".
        for (const [devId, n] of Object.entries(portDeviceMap)){
            const device = hass.devices?.[devId];
            const custom = device?.name_by_user;
            if (custom) ports[n].label = custom;
        }
        // Map entities to main-device slots and per-port fields.
        // port_status lives on the MAIN device (not the sub-device) and
        // has no unique_id in the frontend registry, so we differentiate
        // the 8 instances by parsing their entity_id.
        //
        // Two slug formats exist in the wild:
        //   1. Current (from MASS2_PORT_LABELS placeholder): the slug
        //      contains `_usb_c3_status` / `_usb_a1_status`.
        //   2. Legacy (from the `f"Port {n}"` fallback label used in
        //      earlier versions): the slug contains `_port_3_status`.
        // HA never rewrites entity_ids once created, so existing users
        // may still have the legacy form. Support both.
        for (const [entityId, entity] of Object.entries(hass.entities || {})){
            const tk = entity.translation_key;
            if (entity.device_id === deviceId) // Main device entities
            switch(tk){
                case "total_power":
                    main.total_power = entityId;
                    break;
                case "connected":
                    main.connected = entityId;
                    break;
                case "beep":
                    main.beep = entityId;
                    break;
                case "volume":
                    main.volume = entityId;
                    break;
                case "port_status":
                    {
                        let n = null;
                        // New slug: `..._usb_[ca]<N>_status`
                        let m = entityId.match(/_usb_([ca])(\d+)_status$/i);
                        if (m) {
                            const kind = m[1].toLowerCase();
                            const idx = parseInt(m[2]);
                            n = kind === "c" ? idx : 6 + idx;
                        } else {
                            // Legacy slug: `..._port_<N>_status` (or `_port<N>_status`)
                            m = entityId.match(/_port_?(\d+)_status$/i);
                            if (m) n = parseInt(m[1]);
                        }
                        if (n !== null && n >= 1 && n <= 8) {
                            if (!ports[n]) ports[n] = {};
                            ports[n].status = entityId;
                        }
                        break;
                    }
            }
            else if (entity.device_id && entity.device_id in portDeviceMap) {
                const n = portDeviceMap[entity.device_id];
                switch(tk){
                    case "port_voltage":
                        ports[n].voltage = entityId;
                        break;
                    case "port_current":
                        ports[n].current = entityId;
                        break;
                    case "port_power":
                        ports[n].power = entityId;
                        break;
                    case "port_protocol":
                        ports[n].protocol = entityId;
                        break;
                    case "port_active":
                        ports[n].active = entityId;
                        break;
                }
            }
        }
        return {
            main: main,
            ports: ports
        };
    }
    _t(key) {
        return (0, $d8078e452c66bdbe$export$625550452a3fa3ec)(this._hass, key);
    }
    /* ── Entity state helpers ───────────────────────────── */ _st(eid, fb) {
        if (!eid || !this._hass?.states[eid]) return fb ?? "unavailable";
        const s = this._hass.states[eid].state;
        return s === "unknown" || s === "unavailable" ? fb ?? s : s;
    }
    _num(eid, fb = 0) {
        const v = parseFloat(this._st(eid, null));
        return isNaN(v) ? fb : v;
    }
    /* ── Render ─────────────────────────────────────────── */ _render() {
        if (!this._hass || !this._config) return;
        if (!this._entities) this._entities = this._findEntities(this._hass, this._config.device_id);
        if (!this._entities || !this._config.device_id) {
            const root = this.shadowRoot;
            root.innerHTML = "";
            const style = document.createElement("style");
            style.textContent = this._css();
            root.appendChild(style);
            const card = document.createElement("ha-card");
            card.innerHTML = `<div class="unavailable">${this._t("error_no_device")}</div>`;
            root.appendChild(card);
            return;
        }
        // Compute structural key so we re-render the full card only when
        // the visible layout changes (number of slots/ports, type switch,
        // or a port was renamed in the HA device registry).
        let structKey;
        if (this._entities.type === "adapter") structKey = "adapter:" + [
            1,
            2,
            3,
            4,
            5,
            6,
            7,
            8
        ].map((n)=>this._entities.ports[n]?.label || "").join("|");
        else if (this._entities.type === "balance_charger") {
            const slots = Object.keys(this._entities.slots).map(Number).sort((a, b)=>a - b);
            structKey = "balance:" + slots.map((n)=>{
                const s = this._entities.slots[n];
                const status = this._st(s?.status, "empty");
                // Count populated cells so a pack going from 6S to 8S forces a
                // full re-render (the grid layout changes).
                const cells = s?.cells || {};
                let cellCount = 0;
                for(let i = 0; i < $9a3262f48b2f355e$var$MAX_CELLS_PER_CHANNEL; i++){
                    const eid = cells[i];
                    if (!eid) continue;
                    const v = parseFloat(this._hass.states[eid]?.state);
                    if (!isNaN(v) && v > 0.1) cellCount++;
                }
                return `${n}:${status}:${cellCount}`;
            }).join("|");
        } else {
            const visibleSlots = this._visibleSlots();
            structKey = "charger:" + visibleSlots.map((n)=>{
                const s = this._entities.slots[n];
                const status = this._st(s?.status, "empty");
                return `${n}:${status}`;
            }).join("|");
        }
        const needsFull = this._lastSlotKey !== structKey || !this.shadowRoot.querySelector(".isdt-card");
        this._lastSlotKey = structKey;
        if (needsFull) {
            const root = this.shadowRoot;
            root.innerHTML = "";
            const style = document.createElement("style");
            style.textContent = this._css();
            root.appendChild(style);
            const card = document.createElement("ha-card");
            card.innerHTML = this._html();
            root.appendChild(card);
            this._bind(card);
        } else this._updateDynamic();
    }
    _html() {
        if (this._entities.type === "adapter") return this._adapterHTML();
        if (this._entities.type === "balance_charger") return this._balanceChargerHTML();
        return this._chargerHTML();
    }
    /* ────────────────────────────────────────────────────────────────
     Balance-charger layout (Air 8, K2 Air)
     One full-width pack tile per channel with per-cell V + IR chips.
     ──────────────────────────────────────────────────────────────── */ _cellGridDimensions(cellCount) {
        if (cellCount <= 1) return {
            rows: 1,
            cols: 1
        };
        if (cellCount <= 3) return {
            rows: 1,
            cols: cellCount
        };
        if (cellCount === 4) return {
            rows: 2,
            cols: 2
        };
        if (cellCount <= 8) return {
            rows: 2,
            cols: Math.ceil(cellCount / 2)
        };
        if (cellCount <= 12) return {
            rows: 3,
            cols: 4
        };
        return {
            rows: Math.ceil(cellCount / 4),
            cols: 4
        };
    }
    _balanceChargerHTML() {
        const { show_header: show_header } = this._config;
        const device = this._hass.devices[this._config.device_id];
        const customTitle = this._config.title;
        const model = (device?.model || device?.name || "ISDT Charger").replace(/^ISDT\s+/i, "");
        const title = customTitle || model;
        const slots = Object.keys(this._entities.slots).map(Number).sort((a, b)=>a - b);
        let h = '<div class="isdt-card balance-card">';
        if (show_header) h += this._headerHTML(title);
        h += '<div class="pack-wrap">';
        for (const slot of slots)h += this._packTileHTML(slot);
        h += "</div></div>";
        return h;
    }
    _packTileHTML(slot) {
        const e = this._entities.slots[slot];
        const status = this._st(e?.status, "empty");
        const isEmpty = status === "empty";
        const isCharging = status === "charging";
        const pct = this._num(e?.capacity, 0);
        const vol = this._num(e?.output_voltage, 0);
        const cur = this._num(e?.charging_current, 0);
        const btype = this._st(e?.battery_type, "");
        const mah = this._num(e?.capacity_done, 0);
        const wh = this._num(e?.energy_done, 0);
        const since = this._st(e?.charge_time, null);
        let timeStr = "\u2013";
        if (since && ![
            "unavailable",
            "unknown",
            "\u2013"
        ].includes(since)) {
            const d = Math.max(0, Math.floor((Date.now() - new Date(since).getTime()) / 1000));
            const hh = String(Math.floor(d / 3600)).padStart(2, "0");
            const mm = String(Math.floor(d % 3600 / 60)).padStart(2, "0");
            const ss = String(d % 60).padStart(2, "0");
            timeStr = `${hh}:${mm}:${ss}`;
        }
        const fillW = isEmpty ? 0 : Math.max(2, pct);
        const color = isCharging ? this._chargeColor(pct) : null;
        // Collect populated cells (V > 0.1 = cell present)
        const cells = e?.cells || {};
        const populatedCells = [];
        for(let i = 0; i < $9a3262f48b2f355e$var$MAX_CELLS_PER_CHANNEL; i++){
            const entityId = cells[i];
            if (!entityId) continue;
            const st = this._hass.states[entityId];
            const v = parseFloat(st?.state);
            if (!isNaN(v) && v > 0.1) {
                const irAttr = st?.attributes?.ir_mohm;
                populatedCells.push({
                    index: i,
                    voltage: v,
                    ir: typeof irAttr === "number" ? irAttr : null,
                    entityId: entityId
                });
            }
        }
        const { rows: rows, cols: cols } = this._cellGridDimensions(populatedCells.length);
        // Drift detection: any cell deviating > 20 mV from the median is flagged.
        let drift = new Set();
        if (populatedCells.length > 1) {
            const sorted = [
                ...populatedCells.map((c)=>c.voltage)
            ].sort((a, b)=>a - b);
            const median = sorted[Math.floor(sorted.length / 2)];
            populatedCells.forEach((c)=>{
                if (Math.abs(c.voltage - median) > 0.02) drift.add(c.index);
            });
        }
        let cellChipsHTML = "";
        for (const c of populatedCells){
            const driftClass = drift.has(c.index) ? " drift" : "";
            const irHTML = c.ir != null ? `<div class="cell-ir">${c.ir.toFixed(1)}<small> m\u{3A9}</small></div>` : "";
            cellChipsHTML += `
        <div class="cell-cell${driftClass}" data-entity="${c.entityId}">
          <div class="cell-v">${c.voltage.toFixed(2)}<small>V</small></div>
          ${irHTML}
          <span class="cell-no">${c.index + 1}</span>
        </div>`;
        }
        // Pack-info column
        const statusLabel = this._t("status_" + status);
        const btypeText = btype && btype !== "unavailable" && btype !== "\u2013" ? btype : "";
        const sCount = populatedCells.length;
        const btypePill = btypeText && sCount > 0 ? `<span class="btype-label">${btypeText} \xb7 ${sCount}S</span>` : btypeText ? `<span class="btype-label">${btypeText}</span>` : "";
        const accent = color ? color.fill : null;
        const fillStyle = `width:${fillW}%${color ? `;background:linear-gradient(90deg,${color.deep},${color.fill})` : ""}`;
        const bodyStyle = color ? `border-color:${color.glow};box-shadow:0 0 16px ${color.shadow}` : "";
        const badgeStyle = accent ? `style="color:${accent}"` : "";
        let info;
        if (isEmpty) info = `
        <div class="pack-info">
          <span class="status-badge" data-entity="${e?.status || ""}">${statusLabel}</span>
          <div class="pack-empty-icon"><ha-icon icon="mdi:battery-off-outline"></ha-icon></div>
          <span class="pack-empty-hint">${this._t("balance_no_pack")}</span>
        </div>`;
        else info = `
        <div class="pack-info">
          <span class="status-badge ${status}" data-entity="${e?.status || ""}" ${badgeStyle}>${statusLabel}</span>
          <div class="pack-pct" data-entity="${e?.capacity || ""}">
            <span class="pct-num">${Math.round(pct)}</span><span class="pct-sym">%</span>
            ${isCharging ? `<ha-icon icon="mdi:lightning-bolt" class="pack-bolt" style="color:${accent || 'var(--isdt-charging)'}"></ha-icon>` : ""}
          </div>
          ${btypePill}
        </div>`;
        return `
      <div class="pack-slot ${status}" data-slot="${slot}">
        <div class="pack-shell">
          <div class="pack-body" ${bodyStyle ? `style="${bodyStyle}"` : ""}>
            <div class="pack-fill" style="${fillStyle}"></div>
            <span class="channel-badge">${this._t("balance_channel")} ${slot}</span>
            <div class="pack-content">
              <div class="cells-grid" style="grid-template-columns: repeat(${cols}, 1fr); grid-template-rows: repeat(${rows}, auto);">
                ${cellChipsHTML}
              </div>
              ${info}
            </div>
          </div>
        </div>
        <div class="pack-stats ${isEmpty ? "hidden" : ""}">
          <div class="slot-vi">
            <span data-entity="${e?.output_voltage || ""}"><ha-icon icon="mdi:flash"></ha-icon>${vol.toFixed(2)} V</span>
            <span data-entity="${e?.charging_current || ""}"><ha-icon icon="mdi:current-dc"></ha-icon>${cur.toFixed(3)} A</span>
          </div>
          ${status === "charging" || status === "done" ? `
            <div class="slot-session">
              <span class="time-val" data-entity="${e?.charge_time || ""}" ${isCharging ? `data-since="${since || ""}"` : ""}><ha-icon icon="mdi:timer-outline"></ha-icon>${timeStr}</span>
              <span class="session-energy">${mah.toFixed(0)} mAh / ${wh.toFixed(2)} Wh</span>
            </div>` : ""}
        </div>
      </div>`;
    }
    _visibleSlots() {
        const allSlots = Object.keys(this._entities.slots).map(Number).sort((a, b)=>a - b);
        // 6-slot chargers (C4 Air): show slots 5+6 only if active, else 1–4.
        // The C4 Air physically exposes either AA/AAA in 1–4 or larger cells
        // in 5–6 — never all six at once.
        if (allSlots.length === 6) {
            const use56 = [
                5,
                6
            ].some((n)=>{
                const s = this._entities.slots[n];
                return s && this._st(s.status, "empty") !== "empty";
            });
            return use56 ? [
                5,
                6
            ] : [
                1,
                2,
                3,
                4
            ];
        }
        // Every other charger: show exactly the slots the integration created.
        // Air 8 → 1, K2 Air → 2, A4 Air → 4, A8 Air → 8, …
        return allSlots;
    }
    _chargerHTML() {
        const { show_header: show_header } = this._config;
        const device = this._hass.devices[this._config.device_id];
        const customTitle = this._config.title;
        const model = (device?.model || device?.name || "ISDT Charger").replace(/^ISDT\s+/i, "");
        const title = customTitle || model;
        const visibleSlots = this._visibleSlots();
        let h = '<div class="isdt-card">';
        if (show_header) h += this._headerHTML(title);
        h += '<div class="battery-grid">';
        for (const slot of visibleSlots)h += this._slotHTML(slot);
        h += "</div></div>";
        return h;
    }
    _updateDynamic() {
        if (this._entities?.type === "adapter") return this._adapterUpdateDynamic();
        if (this._entities?.type === "balance_charger") return this._balanceChargerUpdateDynamic();
        return this._chargerUpdateDynamic();
    }
    _balanceChargerUpdateDynamic() {
        const root = this.shadowRoot;
        if (!root) return;
        // Update the shared header stats (same fields as the round-cell card).
        const { main: main } = this._entities;
        const iV = this._num(main.input_voltage);
        const iA = this._num(main.input_current);
        const tA = this._num(main.total_charging_current);
        const iW = (iV * iA).toFixed(1);
        this._setField(root, "input-v", `${iV.toFixed(1)}<small>V</small>`);
        this._setField(root, "input-a", `${iA.toFixed(2)}<small>A</small>`);
        this._setField(root, "input-w", `${iW}<small>W</small>`);
        this._setField(root, "total-a", `${tA.toFixed(2)}<small>A</small>`);
        const connected = this._st(main.connected, "off") === "on";
        const connIcon = root.querySelector(".conn-icon");
        if (connIcon) {
            connIcon.classList.toggle("disconnected", !connected);
            connIcon.setAttribute("title", this._t(connected ? "tooltip_connected" : "tooltip_disconnected"));
        }
        const beep = this._st(main.beep, "off") === "on";
        const beepBtn = root.querySelector(".beep-btn");
        if (beepBtn) {
            beepBtn.className = `beep-btn ${beep ? "on" : ""}`;
            const icon = beepBtn.querySelector("ha-icon");
            if (icon) icon.setAttribute("icon", beep ? "mdi:volume-high" : "mdi:volume-off");
        }
        // Update each pack tile in-place. The structKey above triggers a full
        // re-render on status / cell-count change, so here we only refresh
        // numeric values that don't change the layout.
        for (const slot of Object.keys(this._entities.slots).map(Number)){
            const slotEl = root.querySelector(`.pack-slot[data-slot="${slot}"]`);
            if (!slotEl) continue;
            const e = this._entities.slots[slot];
            const status = this._st(e?.status, "empty");
            const isCharging = status === "charging";
            const pct = this._num(e?.capacity, 0);
            const vol = this._num(e?.output_voltage, 0);
            const cur = this._num(e?.charging_current, 0);
            const mah = this._num(e?.capacity_done, 0);
            const wh = this._num(e?.energy_done, 0);
            const fillEl = slotEl.querySelector(".pack-fill");
            if (fillEl) {
                const fillW = status === "empty" ? 0 : Math.max(2, pct);
                const color = isCharging ? this._chargeColor(pct) : null;
                fillEl.style.width = `${fillW}%`;
                if (color) fillEl.style.background = `linear-gradient(90deg,${color.deep},${color.fill})`;
            }
            if (isCharging) {
                const color = this._chargeColor(pct);
                const bodyEl = slotEl.querySelector(".pack-body");
                if (bodyEl) {
                    bodyEl.style.borderColor = color.glow;
                    bodyEl.style.boxShadow = `0 0 16px ${color.shadow}`;
                }
                const bolt = slotEl.querySelector(".pack-bolt");
                if (bolt) bolt.style.color = color.fill;
                const badge = slotEl.querySelector(".status-badge");
                if (badge) badge.style.color = color.fill;
            }
            const pctNum = slotEl.querySelector(".pct-num");
            if (pctNum) pctNum.textContent = Math.round(pct);
            // Per-cell V + IR refresh
            const cells = e?.cells || {};
            const cellEls = slotEl.querySelectorAll(".cell-cell");
            const voltages = [];
            cellEls.forEach((el)=>{
                const eid = el.getAttribute("data-entity");
                if (!eid) return;
                const st = this._hass.states[eid];
                const v = parseFloat(st?.state);
                if (isNaN(v)) return;
                voltages.push(v);
                const vEl = el.querySelector(".cell-v");
                if (vEl) vEl.innerHTML = `${v.toFixed(2)}<small>V</small>`;
                const irAttr = st?.attributes?.ir_mohm;
                const irEl = el.querySelector(".cell-ir");
                if (irEl && typeof irAttr === "number") irEl.innerHTML = `${irAttr.toFixed(1)}<small> m\u{3A9}</small>`;
            });
            // Refresh drift highlighting against the new median.
            if (voltages.length > 1) {
                const sorted = [
                    ...voltages
                ].sort((a, b)=>a - b);
                const median = sorted[Math.floor(sorted.length / 2)];
                cellEls.forEach((el, idx)=>{
                    if (idx >= voltages.length) return;
                    el.classList.toggle("drift", Math.abs(voltages[idx] - median) > 0.02);
                });
            } else cellEls.forEach((el)=>el.classList.remove("drift"));
            // V/A row + session energy
            const vi = slotEl.querySelectorAll(".slot-vi:not(.sub) span");
            if (vi.length >= 2) for (const [i, text] of [
                [
                    0,
                    `${vol.toFixed(2)} V`
                ],
                [
                    1,
                    `${cur.toFixed(3)} A`
                ]
            ]){
                const icon = vi[i].querySelector("ha-icon");
                vi[i].textContent = "";
                if (icon) vi[i].appendChild(icon);
                vi[i].append(text);
            }
            const energyEl = slotEl.querySelector(".session-energy");
            if (energyEl) energyEl.textContent = `${mah.toFixed(0)} mAh / ${wh.toFixed(2)} Wh`;
        }
    }
    _chargerUpdateDynamic() {
        const root = this.shadowRoot;
        if (!root) return;
        // Update header stats
        const { main: main } = this._entities;
        const iV = this._num(main.input_voltage);
        const iA = this._num(main.input_current);
        const tA = this._num(main.total_charging_current);
        const iW = (iV * iA).toFixed(1);
        this._setField(root, "input-v", `${iV.toFixed(1)}<small>V</small>`);
        this._setField(root, "input-a", `${iA.toFixed(2)}<small>A</small>`);
        this._setField(root, "input-w", `${iW}<small>W</small>`);
        this._setField(root, "total-a", `${tA.toFixed(2)}<small>A</small>`);
        // Update connection icon
        const connected = this._st(main.connected, "off") === "on";
        const connIcon = root.querySelector(".conn-icon");
        if (connIcon) {
            connIcon.classList.toggle("disconnected", !connected);
            connIcon.setAttribute("title", this._t(connected ? "tooltip_connected" : "tooltip_disconnected"));
        }
        // Update beep button
        const beep = this._st(main.beep, "off") === "on";
        const beepBtn = root.querySelector(".beep-btn");
        if (beepBtn) {
            beepBtn.className = `beep-btn ${beep ? "on" : ""}`;
            const icon = beepBtn.querySelector("ha-icon");
            if (icon) icon.setAttribute("icon", beep ? "mdi:volume-high" : "mdi:volume-off");
        }
        // Update each slot
        for (const slot of this._visibleSlots()){
            const slotEl = root.querySelector(`[data-slot="${slot}"]`);
            if (!slotEl) continue;
            const e = this._entities.slots[slot];
            const isCharging = this._st(e?.status, "empty") === "charging";
            const pct = this._num(e?.capacity, 0);
            const cur = this._num(e?.charging_current, 0);
            const vol = this._num(e?.output_voltage, 0);
            const btype = this._st(e?.battery_type, "\u2013");
            const mah = this._num(e?.capacity_done, 0);
            const wh = this._num(e?.energy_done, 0);
            // Update fill width and colors
            const fillEl = slotEl.querySelector(".battery-fill");
            if (fillEl) {
                const status = this._st(e?.status, "empty");
                const fillH = status === "empty" ? 0 : Math.max(4, pct);
                const color = isCharging ? this._chargeColor(pct) : null;
                fillEl.style.width = `${fillH}%`;
                if (color) fillEl.style.background = `linear-gradient(90deg,${color.deep},${color.fill})`;
            }
            // Update terminal/body colors when charging
            if (isCharging) {
                const color = this._chargeColor(pct);
                const termEl = slotEl.querySelector(".battery-terminal");
                if (termEl) {
                    termEl.style.background = color.fill;
                    termEl.style.boxShadow = `0 0 8px ${color.glow}`;
                }
                const bodyEl = slotEl.querySelector(".battery-body");
                if (bodyEl) {
                    bodyEl.style.borderColor = color.glow;
                    bodyEl.style.boxShadow = `0 0 16px ${color.shadow}`;
                }
            }
            // Update percentage text
            const pctNum = slotEl.querySelector(".pct-num");
            if (pctNum) pctNum.textContent = Math.round(pct);
            // Update battery type label inside battery
            const btypeEl = slotEl.querySelector(".btype-label");
            if (btypeEl) {
                const btypeText = btype !== "unavailable" && btype !== "\u2013" ? btype : "";
                btypeEl.textContent = btypeText;
            }
            // Update V/A row (preserve leading <ha-icon> inside each span)
            const vi = slotEl.querySelectorAll(".slot-vi:not(.sub) span");
            if (vi.length >= 2) for (const [i, text] of [
                [
                    0,
                    `${vol.toFixed(2)} V`
                ],
                [
                    1,
                    `${cur.toFixed(3)} A`
                ]
            ]){
                const icon = vi[i].querySelector("ha-icon");
                vi[i].textContent = "";
                if (icon) vi[i].appendChild(icon);
                vi[i].append(text);
            }
            // Update session energy (time is handled by timer)
            const energyEl = slotEl.querySelector(".session-energy");
            if (energyEl) energyEl.textContent = `${mah.toFixed(0)} mAh / ${wh.toFixed(2)} Wh`;
        }
    }
    _setField(root, name, html) {
        const el = root.querySelector(`[data-field="${name}"]`);
        if (el) el.innerHTML = html;
    }
    /* ── Adapter rendering (MASS2 etc.) ─────────────────── */ _portMax(port) {
        return port?.kind === "A" ? $9a3262f48b2f355e$var$MASS2_USBA_MAX : $9a3262f48b2f355e$var$MASS2_USBC_MAX;
    }
    _adapterTotalMax() {
        const device = this._hass.devices[this._config.device_id];
        const model = (device?.model || "").replace(/^ISDT\s+/i, "").trim();
        return $9a3262f48b2f355e$var$ADAPTER_TOTAL_MAX[model] || null;
    }
    _portState(port) {
        // Primary source: the binary_sensor `port_active` on the port
        // sub-device. It's mapped via device.identifiers so its lookup is
        // fully reliable, and it follows the coordinator's phantom-filter
        // decisions (same underlying `ch["status"]` override).
        const a = this._st(port?.active, null);
        if (a === "on") return "active";
        if (a === "off") {
            // Port not actively delivering power, but we can still
            // distinguish "nothing plugged in" from "plugged but idle".
            const pwr = this._num(port?.power, 0);
            return pwr > 0.05 ? "idle" : "off";
        }
        // Fallback 1: the main-device `port_status` sensor (three-state
        // off/idle/active). Used if the binary_sensor is unavailable.
        const s = this._st(port?.status, null);
        if (s === "active" || s === "idle" || s === "off") return s;
        // Fallback 2: purely power-based (last resort, e.g. right after a
        // reload before any sensors have reported).
        const p = this._num(port?.power, 0);
        return p > 0.05 ? "active" : "off";
    }
    _protoBadge(port) {
        const proto = this._st(port?.protocol, "none");
        if (proto === "pd") return {
            label: "PD",
            cls: "pd"
        };
        if (proto === "fast_charge") return {
            label: "FAST",
            cls: "fast"
        };
        return {
            label: "OFF",
            cls: "off"
        };
    }
    _adapterHTML() {
        const device = this._hass.devices[this._config.device_id];
        const customTitle = this._config.title;
        const rawModel = (device?.model || device?.name || "ISDT Adapter").replace(/^ISDT\s+/i, "");
        const model = rawModel || "Adapter";
        const title = customTitle || "ISDT";
        let h = '<div class="isdt-card adapter-card">';
        if (this._config.show_header !== false) h += this._adapterHeaderHTML(title, model);
        h += `<div class="section-label">${this._t("section_usbc")}</div>`;
        h += '<div class="port-grid usb-c">';
        for(let n = 1; n <= 6; n++)h += this._portHTML(n);
        h += "</div>";
        h += `<div class="section-label">${this._t("section_usba")}</div>`;
        h += '<div class="port-grid usb-a">';
        for(let n = 7; n <= 8; n++)h += this._portHTML(n);
        h += "</div>";
        h += "</div>";
        return h;
    }
    _adapterHeaderHTML(_title, model) {
        const { main: main } = this._entities;
        const customTitle = this._config.title;
        const showModel = this._config.show_model !== false;
        const connected = this._st(main.connected, "off") === "on";
        const totalW = this._num(main.total_power, 0);
        const totalMax = this._adapterTotalMax();
        const pct = totalMax ? Math.min(100, totalW / totalMax * 100) : 0;
        const R = 36;
        const C = 2 * Math.PI * R;
        const dashOffset = C - pct / 100 * C;
        const volume = this._st(main.volume, "medium"); // low | medium | high
        const beepOn = this._st(main.beep, "off") === "on";
        const soundState = beepOn ? volume : "mute"; // mute | low | medium | high
        const soundIcon = this._soundIcon(soundState);
        const popoverOpts = [
            {
                id: "mute",
                icon: "mdi:volume-off"
            },
            {
                id: "low",
                icon: "mdi:volume-low"
            },
            {
                id: "medium",
                icon: "mdi:volume-medium"
            },
            {
                id: "high",
                icon: "mdi:volume-high"
            }
        ].map((o)=>`
      <button class="sound-opt ${soundState === o.id ? "active" : ""}"
              data-opt="${o.id}"
              title="${this._t("sound_" + o.id)}">
        <ha-icon icon="${o.icon}"></ha-icon>
      </button>`).join("");
        return `
      <div class="header adapter-header">
        <div class="header-top">
          <div class="header-title">
            ${customTitle ? `<span class="title-text">${customTitle}</span>` : `<span class="isdt-logo">ISDT</span>`}
            ${showModel && model ? `<span class="model-name">${model}</span>` : ""}
          </div>
          <div class="header-icons">
            <svg class="conn-icon ${connected ? "" : "disconnected"}" viewBox="0 0 24 24" fill="currentColor" stroke="none"
                 data-entity="${main.connected || ""}"
                 title="${this._t(connected ? "tooltip_connected" : "tooltip_disconnected")}">
              <path d="M17.71 7.71L12 2h-1v7.59L6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 11 14.41V22h1l5.71-5.71-4.3-4.29 4.3-4.29zM13 5.83l1.88 1.88L13 9.59V5.83zm1.88 10.46L13 18.17v-3.76l1.88 1.88z"/>
            </svg>
            <div class="sound-wrap">
              <button class="sound-btn ${soundState !== "mute" ? "on" : ""}"
                      data-beep="${main.beep || ""}"
                      data-volume="${main.volume || ""}"
                      title="${this._t("sound_" + soundState)}">
                <ha-icon class="sound-btn-icon" icon="${soundIcon}"></ha-icon>
              </button>
              <div class="sound-popover">${popoverOpts}</div>
            </div>
            <svg class="more-info-btn" viewBox="0 0 24 24" fill="currentColor" stroke="none">
              <circle cx="12" cy="5" r="1.5"/>
              <circle cx="12" cy="12" r="1.5"/>
              <circle cx="12" cy="19" r="1.5"/>
            </svg>
          </div>
        </div>
        <div class="power-gauge" data-entity="${main.total_power || ""}">
          <div class="gauge-ring">
            <svg class="ring" viewBox="0 0 84 84">
              <circle class="bg-ring" cx="42" cy="42" r="${R}"/>
              <circle class="fg-ring" cx="42" cy="42" r="${R}" stroke-dasharray="${C}" stroke-dashoffset="${dashOffset}"/>
            </svg>
            <div class="gauge-center">
              <span class="gauge-watts" data-field="total-w">${totalW.toFixed(0)}<small>W</small></span>
              ${totalMax ? `<span class="gauge-unit">${this._t("gauge_of")} ${totalMax}W</span>` : ""}
            </div>
          </div>
          <div class="power-details">
            <div class="power-row">
              <span class="lbl">${this._t("active_ports")}</span>
              <span class="val" data-field="active-count">\u{2013}</span>
            </div>
            <div class="power-row">
              <span class="lbl">${this._t("load")}</span>
              <span class="val" data-field="load-pct">${totalMax ? `${pct.toFixed(0)} %` : "\u2013"}</span>
            </div>
            <div class="power-bar"><div class="power-bar-fill" data-field="load-bar" style="width:${pct}%"></div></div>
          </div>
        </div>
      </div>`;
    }
    _soundIcon(state) {
        return ({
            mute: "mdi:volume-off",
            low: "mdi:volume-low",
            medium: "mdi:volume-medium",
            high: "mdi:volume-high"
        })[state] || "mdi:volume-off";
    }
    _portHTML(n) {
        const port = this._entities.ports[n];
        const state = this._portState(port);
        const w = this._num(port?.power, 0);
        const v = this._num(port?.voltage, 0);
        const a = this._num(port?.current, 0);
        const isActive = state === "active";
        const portMax = this._portMax(port);
        const barPct = isActive ? Math.min(100, w / portMax * 100) : 0;
        const kind = port?.kind || (n <= 6 ? "C" : "A");
        const iconName = kind === "C" ? "mdi:usb-c-port" : "mdi:usb-port";
        // Protocol badge: only for USB-C (USB-A has no PD negotiation, so
        // there's nothing meaningful to show).
        let badgeHTML = "";
        if (kind === "C") {
            const badge = this._protoBadge(port);
            badgeHTML = `<span class="proto-badge proto-${badge.cls}" data-entity="${port?.protocol || ""}">${badge.label}</span>`;
        }
        return `
      <div class="port ${state}" data-port="${n}">
        <div class="port-head">
          <div class="port-num">
            <ha-icon class="port-icon" icon="${iconName}"></ha-icon>
            <span>${port?.label || ""}</span>
          </div>
          ${badgeHTML}
        </div>
        <div class="port-watts" data-entity="${port?.power || ""}">${w.toFixed(1)}<small>W</small></div>
        <div class="port-vi">
          <span data-entity="${port?.voltage || ""}">${v.toFixed(2)} V</span>
          <span data-entity="${port?.current || ""}">${a.toFixed(2)} A</span>
        </div>
        <div class="port-bar"><div class="port-bar-fill" style="width:${barPct}%"></div></div>
      </div>`;
    }
    _adapterUpdateDynamic() {
        const root = this.shadowRoot;
        if (!root) return;
        const { main: main, ports: ports } = this._entities;
        // Header: total gauge + volume selector + beep + connection
        const totalW = this._num(main.total_power, 0);
        const totalMax = this._adapterTotalMax();
        const pct = totalMax ? Math.min(100, totalW / totalMax * 100) : 0;
        const R = 36;
        const C = 2 * Math.PI * R;
        this._setField(root, "total-w", `${totalW.toFixed(0)}<small>W</small>`);
        this._setField(root, "load-pct", totalMax ? `${pct.toFixed(0)} %` : "\u2013");
        const loadBar = root.querySelector('[data-field="load-bar"]');
        if (loadBar) loadBar.style.width = `${pct}%`;
        const fg = root.querySelector(".fg-ring");
        if (fg) fg.setAttribute("stroke-dashoffset", `${C - pct / 100 * C}`);
        // Connection icon
        const connected = this._st(main.connected, "off") === "on";
        const connIcon = root.querySelector(".conn-icon");
        if (connIcon) {
            connIcon.classList.toggle("disconnected", !connected);
            connIcon.setAttribute("title", this._t(connected ? "tooltip_connected" : "tooltip_disconnected"));
        }
        // Sound icon (combined mute + volume) — header button + popover
        const beepOn = this._st(main.beep, "off") === "on";
        const volume = this._st(main.volume, "medium");
        const soundState = beepOn ? volume : "mute";
        const soundIcon = this._soundIcon(soundState);
        const soundBtn = root.querySelector(".sound-btn");
        if (soundBtn) {
            soundBtn.classList.toggle("on", soundState !== "mute");
            soundBtn.setAttribute("title", this._t("sound_" + soundState));
            const iconEl = soundBtn.querySelector(".sound-btn-icon");
            if (iconEl) iconEl.setAttribute("icon", soundIcon);
        }
        root.querySelectorAll(".sound-opt").forEach((btn)=>{
            btn.classList.toggle("active", btn.dataset.opt === soundState);
        });
        // Ports
        let activeCount = 0;
        for(let n = 1; n <= 8; n++){
            const portEl = root.querySelector(`[data-port="${n}"]`);
            if (!portEl) continue;
            const port = ports[n];
            const state = this._portState(port);
            if (state === "active") activeCount++;
            portEl.className = `port ${state}`;
            const w = this._num(port?.power, 0);
            const v = this._num(port?.voltage, 0);
            const a = this._num(port?.current, 0);
            const wEl = portEl.querySelector(".port-watts");
            if (wEl) wEl.innerHTML = `${w.toFixed(1)}<small>W</small>`;
            const viSpans = portEl.querySelectorAll(".port-vi span");
            if (viSpans.length >= 2) {
                viSpans[0].textContent = `${v.toFixed(2)} V`;
                viSpans[1].textContent = `${a.toFixed(2)} A`;
            }
            // Protocol badge only exists for USB-C ports (see _portHTML).
            const badgeEl = portEl.querySelector(".proto-badge");
            if (badgeEl) {
                const badge = this._protoBadge(port);
                badgeEl.className = `proto-badge proto-${badge.cls}`;
                badgeEl.textContent = badge.label;
            }
            const isActive = state === "active";
            const portMax = this._portMax(port);
            const barPct = isActive ? Math.min(100, w / portMax * 100) : 0;
            const barFill = portEl.querySelector(".port-bar-fill");
            if (barFill) barFill.style.width = `${barPct}%`;
        }
        this._setField(root, "active-count", `${activeCount} / 8`);
    }
    _navigateToDevice() {
        const deviceId = this._config?.device_id;
        if (!deviceId) return;
        const path = `/config/devices/device/${deviceId}`;
        history.pushState(null, "", path);
        window.dispatchEvent(new CustomEvent("location-changed", {
            detail: {
                replace: false
            }
        }));
    }
    _headerHTML(title) {
        const { main: main } = this._entities;
        const device = this._hass.devices[this._config.device_id];
        const customTitle = this._config.title;
        const model = (device?.model || device?.name || "").replace(/^ISDT\s+/i, "");
        const showModel = this._config.show_model !== false;
        const iV = this._num(main.input_voltage);
        const iA = this._num(main.input_current);
        const tA = this._num(main.total_charging_current);
        const iW = (iV * iA).toFixed(1);
        const beep = this._st(main.beep, "off") === "on";
        const connected = this._st(main.connected, "off") === "on";
        return `
      <div class="header">
        <div class="header-top">
          <div class="header-title">
            ${customTitle ? `<span class="title-text">${customTitle}</span>` : `<span class="isdt-logo">ISDT</span>`}
            ${showModel && model ? `<span class="model-name">${model}</span>` : ""}
          </div>
          <div class="header-icons">
            <svg class="conn-icon ${connected ? "" : "disconnected"}" viewBox="0 0 24 24" fill="currentColor" stroke="none"
                 data-entity="${main.connected || ""}"
                 title="${this._t(connected ? "tooltip_connected" : "tooltip_disconnected")}">
              <path d="M17.71 7.71L12 2h-1v7.59L6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 11 14.41V22h1l5.71-5.71-4.3-4.29 4.3-4.29zM13 5.83l1.88 1.88L13 9.59V5.83zm1.88 10.46L13 18.17v-3.76l1.88 1.88z"/>
            </svg>
            ${main.beep ? `<button class="beep-btn ${beep ? "on" : ""}" data-entity="${main.beep}">
              <ha-icon icon="mdi:${beep ? "volume-high" : "volume-off"}"></ha-icon>
            </button>` : ""}
            <svg class="more-info-btn" viewBox="0 0 24 24" fill="currentColor" stroke="none">
              <circle cx="12" cy="5" r="1.5"/>
              <circle cx="12" cy="12" r="1.5"/>
              <circle cx="12" cy="19" r="1.5"/>
            </svg>
          </div>
        </div>
        <div class="header-stats">
          <div class="stat"><span class="stat-value" data-field="input-v">${iV.toFixed(1)}<small>V</small></span><span class="stat-label">${this._t("header_input")}</span></div>
          <div class="stat-div"></div>
          <div class="stat"><span class="stat-value" data-field="input-a">${iA.toFixed(2)}<small>A</small></span><span class="stat-label">${this._t("header_current")}</span></div>
          <div class="stat-div"></div>
          <div class="stat"><span class="stat-value" data-field="input-w">${iW}<small>W</small></span><span class="stat-label">${this._t("header_power")}</span></div>
          <div class="stat-div"></div>
          <div class="stat"><span class="stat-value" data-field="total-a">${tA.toFixed(2)}<small>A</small></span><span class="stat-label">${this._t("header_total_charge")}</span></div>
        </div>
      </div>`;
    }
    _chargeColor(pct) {
        // Thresholds from ISDT Link app (PublicUIHandling.setProgress)
        if (pct <= 20) return {
            fill: "#ff5555",
            deep: "#cc2222",
            glow: "rgba(255,85,85,0.45)",
            shadow: "rgba(255,85,85,0.12)"
        };
        if (pct < 75) return {
            fill: "#ff9955",
            deep: "#cc6622",
            glow: "rgba(255,153,85,0.45)",
            shadow: "rgba(255,153,85,0.12)"
        };
        if (pct < 90) return {
            fill: "#aad400",
            deep: "#779200",
            glow: "rgba(170,212,0,0.45)",
            shadow: "rgba(170,212,0,0.12)"
        };
        return {
            fill: "#37c871",
            deep: "#1a8a4a",
            glow: "rgba(55,200,113,0.45)",
            shadow: "rgba(55,200,113,0.12)"
        };
    }
    _slotHTML(slot) {
        const e = this._entities.slots[slot];
        const status = this._st(e?.status, "empty");
        const isEmpty = status === "empty";
        const isCharging = status === "charging";
        const isActive = isCharging || status === "done";
        const pct = this._num(e?.capacity, 0);
        const cur = this._num(e?.charging_current, 0);
        const vol = this._num(e?.output_voltage, 0);
        const btype = this._st(e?.battery_type, "\u2013");
        const mah = this._num(e?.capacity_done, 0);
        const wh = this._num(e?.energy_done, 0);
        const since = this._st(e?.charge_time, null);
        let timeStr = "\u2013";
        if (since && ![
            "unavailable",
            "unknown",
            "\u2013"
        ].includes(since)) {
            const d = Math.max(0, Math.floor((Date.now() - new Date(since).getTime()) / 1000));
            const hh = String(Math.floor(d / 3600)).padStart(2, "0");
            const mm = String(Math.floor(d % 3600 / 60)).padStart(2, "0");
            const ss = String(d % 60).padStart(2, "0");
            timeStr = `${hh}:${mm}:${ss}`;
        }
        const fillH = isEmpty ? 0 : Math.max(4, pct);
        // Hybrid color: when charging, fill color reflects charge level
        const color = isCharging ? this._chargeColor(pct) : null;
        const fillStyle = `width:${fillH}%${color ? `;background:linear-gradient(90deg,${color.deep},${color.fill})` : ""}`;
        const terminalStyle = color ? `background:${color.fill};box-shadow:0 0 8px ${color.glow}` : "";
        const bodyStyle = color ? `border-color:${color.glow};box-shadow:0 0 16px ${color.shadow}` : "";
        let bubbles = "";
        for(let i = 0; i < 6; i++){
            const t = 10 + Math.random() * 80;
            const dur = 2.5 + Math.random() * 3;
            const del = Math.random() * 3;
            const sz = 2 + Math.random() * 2;
            bubbles += `<div class="bubble" style="left:3%;top:${t}%;width:${sz}px;height:${sz}px;animation-duration:${dur}s;animation-delay:${del}s"></div>`;
        }
        const accentColor = color?.fill ?? null;
        let center = "";
        if (isEmpty) center = '<ha-icon icon="mdi:battery-off-outline" class="empty-icon-lg"></ha-icon>';
        else if (status === "error") center = `
        <ha-icon icon="mdi:alert-circle" class="error-icon-lg"></ha-icon>
        <div class="battery-pct"><span class="pct-num sm">${Math.round(pct)}</span><span class="pct-sym">%</span></div>`;
        else {
            const pctStyle = accentColor ? `style="color:#fff;text-shadow:0 1px 6px rgba(0,0,0,0.35)"` : "";
            const symStyle = accentColor ? `style="color:rgba(255,255,255,0.75)"` : "";
            const boltStyle = accentColor ? `style="color:#fff"` : "";
            const btypeLabel = !isEmpty && btype !== "unavailable" && btype !== "\u2013" ? btype : "";
            center = `
        <div class="battery-pct">
          <span class="pct-num" ${pctStyle}>${Math.round(pct)}</span><span class="pct-sym" ${symStyle}>%</span>${isCharging ? `<ha-icon icon="mdi:lightning-bolt" class="charging-bolt" ${boltStyle}></ha-icon>` : ""}
        </div>`;
            if (btypeLabel) center += `<span class="btype-label" data-entity="${e?.battery_type || ""}">${btypeLabel}</span>`;
        }
        const badgeStyle = accentColor ? `style="color:${accentColor}"` : "";
        return `
      <div class="battery-slot ${status}" data-slot="${slot}">
        <div class="battery-shell">
          <div class="battery-body" data-entity="${e?.capacity || ""}" ${bodyStyle ? `style="${bodyStyle}"` : ""}>
            <div class="battery-fill" style="${fillStyle}">
              <div class="battery-fill-wave"></div>
              <div class="battery-bubbles">${bubbles}</div>
            </div>
            <div class="battery-content">
              <span class="slot-badge">${slot}</span>
              <span class="status-badge ${status}" data-entity="${e?.status || ""}" ${badgeStyle}>${this._t("status_" + status)}</span>
              ${center}
            </div>
          </div>
          <div class="battery-terminal" ${terminalStyle ? `style="${terminalStyle}"` : ""}></div>
        </div>
        <div class="battery-info ${isEmpty ? "hidden" : ""}">
          <div class="slot-vi">
            <span data-entity="${e?.output_voltage || ""}"><ha-icon icon="mdi:flash"></ha-icon>${vol.toFixed(2)} V</span>
            <span data-entity="${e?.charging_current || ""}"><ha-icon icon="mdi:current-dc"></ha-icon>${cur.toFixed(3)} A</span>
          </div>
          ${isActive ? `
            <div class="slot-session">
              <span class="time-val" data-entity="${e?.charge_time || ""}" ${isCharging ? `data-since="${since || ""}"` : ""}><ha-icon icon="mdi:timer-outline"></ha-icon>${timeStr}</span>
              <span class="session-energy">${mah.toFixed(0)} mAh / ${wh.toFixed(2)} Wh</span>
            </div>` : ""}
        </div>
      </div>`;
    }
    /* ── Events ─────────────────────────────────────────── */ _bind(card) {
        // Charger beep button (binary toggle on the C4 Air header).
        const beepBtn = card.querySelector(".beep-btn");
        if (beepBtn?.dataset.entity) beepBtn.addEventListener("click", (e)=>{
            e.stopPropagation();
            this._hass.callService("switch", "toggle", {
                entity_id: beepBtn.dataset.entity
            });
        });
        const moreBtn = card.querySelector(".more-info-btn");
        if (moreBtn) moreBtn.addEventListener("click", (e)=>{
            e.stopPropagation();
            this._navigateToDevice();
        });
        // Adapter sound control (combined mute + volume popover).
        const soundBtn = card.querySelector(".sound-btn");
        const soundWrap = card.querySelector(".sound-wrap");
        if (soundBtn && soundWrap) {
            soundBtn.addEventListener("click", (e)=>{
                e.stopPropagation();
                soundWrap.classList.toggle("open");
            });
            // Close on any click outside the wrap (within the card).
            card.addEventListener("click", (e)=>{
                if (!soundWrap.contains(e.target)) soundWrap.classList.remove("open");
            });
        }
        card.querySelectorAll(".sound-opt").forEach((btn)=>{
            btn.addEventListener("click", (e)=>{
                e.stopPropagation();
                const opt = btn.dataset.opt;
                const beepEntity = soundBtn?.dataset.beep;
                const volumeEntity = soundBtn?.dataset.volume;
                if (opt === "mute") {
                    if (beepEntity) this._hass.callService("switch", "turn_off", {
                        entity_id: beepEntity
                    });
                } else {
                    // Unmute first (if currently muted) then set volume.
                    if (beepEntity) this._hass.callService("switch", "turn_on", {
                        entity_id: beepEntity
                    });
                    if (volumeEntity) this._hass.callService("select", "select_option", {
                        entity_id: volumeEntity,
                        option: opt
                    });
                }
                soundWrap?.classList.remove("open");
            });
        });
        card.querySelectorAll("[data-entity]").forEach((el)=>{
            if (!el.dataset.entity) return;
            if (el.classList.contains("sound-btn")) return; // handled above
            el.addEventListener("click", (e)=>{
                e.stopPropagation();
                const ev = new Event("hass-more-info", {
                    bubbles: true,
                    composed: true
                });
                ev.detail = {
                    entityId: el.dataset.entity
                };
                this.dispatchEvent(ev);
            });
        });
        this._startTimers(card);
    }
    _startTimers(card) {
        if (this._timeInterval) clearInterval(this._timeInterval);
        this._timeInterval = setInterval(()=>{
            card.querySelectorAll(".time-val").forEach((el)=>{
                const s = el.dataset.since;
                if (!s) return;
                const d = Math.max(0, Math.floor((Date.now() - new Date(s).getTime()) / 1000));
                const timeStr = `${String(Math.floor(d / 3600)).padStart(2, "0")}:${String(Math.floor(d % 3600 / 60)).padStart(2, "0")}:${String(d % 60).padStart(2, "0")}`;
                // Preserve leading <ha-icon> if present
                const icon = el.querySelector("ha-icon");
                if (icon) {
                    el.textContent = "";
                    el.appendChild(icon);
                    el.append(timeStr);
                } else el.textContent = timeStr;
            });
        }, 1000);
    }
    disconnectedCallback() {
        if (this._timeInterval) clearInterval(this._timeInterval);
    }
    getCardSize() {
        return 6;
    }
    /* ── Styles ─────────────────────────────────────────── */ _css() {
        return `
    :host {
      --isdt-charging: #4caf50;
      --isdt-charging-deep: #2e7d32;
      --isdt-done: #42a5f5;
      --isdt-done-deep: #1565c0;
      --isdt-error: #ef5350;
      --isdt-error-deep: #c62828;
    }

    ha-card {
      background: var(--ha-card-background, var(--card-background-color, #fff));
      color: var(--primary-text-color, #212121);
      border-radius: var(--ha-card-border-radius, 12px);
      border: 1px solid var(--ha-card-border-color, var(--divider-color, #e0e0e0));
      overflow: hidden;
      container-type: inline-size;
      font-family: var(--paper-font-body1_-_font-family, -apple-system, 'Segoe UI', sans-serif);
    }

    .isdt-card { padding: 0; }

    /* \u{2550}\u{2550}\u{2550}\u{2550}\u{2550}\u{2550}\u{2550}\u{2550} Header \u{2550}\u{2550}\u{2550}\u{2550}\u{2550}\u{2550}\u{2550}\u{2550} */
    .header {
      padding: 18px 20px 14px;
      border-bottom: 1px solid var(--divider-color, #e0e0e0);
    }
    .header-top {
      display: flex; align-items: center; justify-content: space-between;
      margin-bottom: 14px;
    }
    .header-title { display: flex; align-items: baseline; gap: 8px; min-width: 0; overflow: hidden; }
    .header-icons { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
    .isdt-logo {
      font-weight: 800; font-size: 18px; letter-spacing: 2.5px;
      color: var(--primary-color, #03a9f4);
    }
    .title-text {
      font-weight: 700; font-size: 15px; letter-spacing: -0.01em;
      color: var(--primary-text-color);
      white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }
    .model-name {
      font-size: 13px; font-weight: 500;
      color: var(--secondary-text-color, #727272);
    }
    .conn-icon {
      width: 18px; height: 18px; flex-shrink: 0;
      color: var(--primary-color, #03a9f4);
      fill: currentColor; cursor: pointer;
      opacity: 1; transition: color 0.4s, opacity 0.4s;
    }
    .conn-icon.disconnected {
      color: var(--disabled-text-color, #9ca3af);
      opacity: 0.3;
    }
    .beep-btn {
      background: none; border: none; padding: 4px; cursor: pointer;
      color: var(--secondary-text-color); display: flex; align-items: center;
      opacity: 0.5; transition: opacity 0.2s, color 0.2s;
    }
    .beep-btn:hover { opacity: 1; }
    .beep-btn.on {
      color: var(--primary-color, #03a9f4);
      opacity: 0.85;
    }
    .beep-btn.on:hover { opacity: 1; }
    .beep-btn ha-icon { --mdc-icon-size: 20px; }
    .more-info-btn {
      width: 18px; height: 18px; cursor: pointer;
      opacity: 0.5; transition: opacity 0.2s;
      color: var(--secondary-text-color);
    }
    .more-info-btn:hover { opacity: 1; }
    .header-stats {
      display: flex; align-items: center; justify-content: space-between;
      background: var(--secondary-background-color, rgba(0,0,0,0.04));
      border-radius: 10px; padding: 10px 6px;
    }
    .stat { display: flex; flex-direction: column; align-items: center; flex: 1; }
    .stat-value {
      font-size: 15px; font-weight: 700; font-variant-numeric: tabular-nums;
      color: var(--primary-text-color); line-height: 1.2;
    }
    .stat-value small {
      font-size: 10px; font-weight: 400;
      color: var(--secondary-text-color); margin-left: 2px;
    }
    .stat-label {
      font-size: 9px; text-transform: uppercase; letter-spacing: 1px;
      color: var(--secondary-text-color); margin-top: 3px;
    }
    .stat-div { width: 1px; height: 24px; background: var(--divider-color); }

    /* \u{2550}\u{2550}\u{2550}\u{2550}\u{2550}\u{2550}\u{2550}\u{2550} Grid \u{2550}\u{2550}\u{2550}\u{2550}\u{2550}\u{2550}\u{2550}\u{2550} */
    .battery-grid {
      display: grid; grid-template-columns: repeat(2, 1fr);
      gap: 10px; padding: 12px;
    }

    /* \u{2550}\u{2550}\u{2550}\u{2550}\u{2550}\u{2550}\u{2550}\u{2550} Slot \u{2550}\u{2550}\u{2550}\u{2550}\u{2550}\u{2550}\u{2550}\u{2550} */
    .battery-slot {
      display: flex; flex-direction: column; align-items: stretch;
    }
    .battery-body { cursor: pointer; }

    .battery-shell {
      display: flex; flex-direction: row; align-items: center; width: 100%;
      transition: transform 0.2s;
    }
    .battery-slot:hover .battery-shell { transform: translateX(2px); }
    .battery-terminal {
      width: 7px; height: 40%; min-height: 22px; flex-shrink: 0;
      background: var(--divider-color, #e0e0e0);
      border-radius: 0 3px 3px 0;
      transition: background 0.4s, box-shadow 0.4s;
    }
    .battery-body {
      position: relative; flex: 1; height: 95px;
      background: var(--secondary-background-color, rgba(0,0,0,0.04));
      border: 2px solid var(--divider-color, #e0e0e0);
      border-radius: 10px 4px 4px 10px;
      overflow: hidden; transition: border-color 0.4s, box-shadow 0.4s;
    }
    .battery-fill {
      position: absolute; top: 0; left: 0; bottom: 0;
      transition: width 1.2s cubic-bezier(0.22, 1, 0.36, 1);
    }
    .battery-fill::after {
      content: ''; position: absolute; inset: 0;
      background: linear-gradient(180deg, rgba(255,255,255,0.14) 0%, transparent 55%);
      pointer-events: none;
    }
    .battery-fill-wave { display: none; }
    .charging .battery-fill-wave { display: none; }

    .battery-bubbles {
      position: absolute; inset: 0; overflow: hidden;
      opacity: 0; pointer-events: none;
    }
    .charging .battery-bubbles { opacity: 1; }
    .bubble {
      position: absolute; border-radius: 50%;
      background: rgba(255,255,255,0.2);
      animation: rise linear infinite;
    }
    @keyframes rise {
      from { transform: translateX(0) scale(1); opacity: 0.5; }
      to   { transform: translateX(90px) scale(0.3); opacity: 0; }
    }

    /* charging body/terminal/fill colors are set via inline style (hybrid level-based scheme) */

    .done .battery-body      { border-color: rgba(66,165,245,0.4); box-shadow: 0 0 16px rgba(66,165,245,0.1); }
    .done .battery-terminal  { background: var(--isdt-done); box-shadow: 0 0 8px rgba(66,165,245,0.4); }
    .done .battery-fill      { background: linear-gradient(90deg, var(--isdt-done-deep), var(--isdt-done)); }

    .idle .battery-fill      { background: var(--divider-color, #e0e0e0); opacity: 0.5; }

    .error .battery-body     { border-color: rgba(239,83,80,0.45); box-shadow: 0 0 16px rgba(239,83,80,0.1); animation: err-b 2s ease-in-out infinite; }
    .error .battery-terminal { background: var(--isdt-error); box-shadow: 0 0 8px rgba(239,83,80,0.45); }
    .error .battery-fill     { background: linear-gradient(90deg, var(--isdt-error-deep), var(--isdt-error)); }
    @keyframes err-b {
      0%,100% { border-color: rgba(239,83,80,0.3); }
      50%     { border-color: rgba(239,83,80,0.6); }
    }

    .empty .battery-body     { border-color: var(--divider-color, #e0e0e0); opacity: 0.5; }
    .empty .battery-terminal { opacity: 0.4; }

    .battery-content {
      position: absolute; inset: 0;
      display: flex; flex-direction: column;
      align-items: center; justify-content: center; z-index: 2;
    }
    .slot-badge {
      position: absolute; top: 7px; left: 7px;
      font-size: 11px; font-weight: 700;
      color: var(--secondary-text-color);
      background: var(--card-background-color, rgba(255,255,255,0.85));
      width: 20px; height: 20px;
      display: flex; align-items: center; justify-content: center;
      border-radius: 5px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    .status-badge {
      position: absolute; top: 7px; right: 6px;
      font-size: 7.5px; font-weight: 700;
      text-transform: uppercase; letter-spacing: 1.2px;
      padding: 2px 6px; border-radius: 3px;
      background: var(--card-background-color, rgba(255,255,255,0.85));
      box-shadow: 0 1px 3px rgba(0,0,0,0.1);
      color: var(--secondary-text-color);
    }
    .status-badge.done     { color: var(--isdt-done); }
    .status-badge.error    { color: var(--isdt-error); }

    .battery-pct { display: flex; align-items: center; }
    .pct-num { font-size: 32px; font-weight: 800; line-height: 1; color: var(--primary-text-color); }
    .pct-num.sm { font-size: 24px; }
    .pct-sym { font-size: 13px; font-weight: 500; color: var(--secondary-text-color); margin-left: 1px; }

    .done .pct-num { color: #fff; text-shadow: 0 1px 6px rgba(0,0,0,0.3); }
    .done .pct-sym { color: rgba(255,255,255,0.7); }

    .charging-bolt { --mdc-icon-size: 20px; margin-left: 3px; animation: bolt 1.2s ease-in-out infinite; }
    @keyframes bolt {
      0%,100% { opacity: 0.6; transform: scale(1);    filter: drop-shadow(0 0 0px currentColor); }
      50%     { opacity: 1;   transform: scale(1.3);  filter: drop-shadow(0 0 5px currentColor); }
    }

    .btype-label {
      position: absolute; bottom: 7px;
      font-size: 8px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.8px;
      color: var(--secondary-text-color);
      background: rgba(128,128,128,0.15); padding: 1px 5px; border-radius: 3px;
      cursor: pointer;
    }
    .charging .btype-label, .done .btype-label {
      color: #fff; background: rgba(0,0,0,0.15);
    }
    .empty-icon-lg { --mdc-icon-size: 34px; color: var(--disabled-text-color, #bdbdbd); }
    .error-icon-lg { --mdc-icon-size: 22px; color: #fff; margin-bottom: 4px; }
    .error .pct-num { color: #fff; text-shadow: 0 1px 6px rgba(0,0,0,0.3); }
    .error .pct-sym { color: rgba(255,255,255,0.7); }

    /* \u{2550}\u{2550}\u{2550}\u{2550}\u{2550}\u{2550}\u{2550}\u{2550} Info \u{2550}\u{2550}\u{2550}\u{2550}\u{2550}\u{2550}\u{2550}\u{2550} */
    .battery-info {
      width: calc(100% - 12px); margin-top: 6px;
      display: flex; flex-direction: column; gap: 2px;
      padding: 0 2px;
    }
    .battery-info.hidden { display: none; }
    .slot-vi {
      display: flex; align-items: center; justify-content: space-between;
      font-family: ui-monospace, 'Roboto Mono', monospace;
      font-variant-numeric: tabular-nums; font-size: 11px; font-weight: 600;
      color: var(--primary-text-color);
    }
    .slot-vi span { display: flex; align-items: center; gap: 2px; }
    .slot-vi ha-icon { --mdc-icon-size: 13px; opacity: 0.45; }
    .slot-vi span { cursor: pointer; }
    .slot-vi span:hover { color: var(--accent-color); }
    /* Narrow slots: the energy moves to its own line as a whole instead
       of breaking inside the text ("555 mAh / 0.81" + "Wh"). */
    .slot-session {
      display: flex; flex-wrap: wrap; justify-content: space-between;
      column-gap: 6px;
      font-family: ui-monospace, 'Roboto Mono', monospace;
      font-variant-numeric: tabular-nums; font-size: 9.5px;
      color: var(--secondary-text-color); margin-top: 1px;
    }
    .slot-session span {
      display: flex; align-items: center; gap: 2px; cursor: pointer;
      white-space: nowrap;
    }
    .slot-session .session-energy { margin-left: auto; }
    .slot-session span:hover { color: var(--primary-text-color); }
    .slot-session ha-icon { --mdc-icon-size: 12px; opacity: 0.5; }
    .status-badge { cursor: pointer; }
    .status-badge:hover { filter: brightness(0.85); }

    /* \u{2550}\u{2550}\u{2550}\u{2550}\u{2550}\u{2550}\u{2550}\u{2550} Unavailable \u{2550}\u{2550}\u{2550}\u{2550}\u{2550}\u{2550}\u{2550}\u{2550} */
    .unavailable {
      padding: 32px 16px;
      text-align: center;
      color: var(--secondary-text-color);
      font-size: 14px;
    }

    /* \u{2550}\u{2550}\u{2550}\u{2550}\u{2550}\u{2550}\u{2550}\u{2550} Adapter (MASS2 etc.) \u{2550}\u{2550}\u{2550}\u{2550}\u{2550}\u{2550}\u{2550}\u{2550} */
    .adapter-card { padding: 0; }

    .adapter-header .power-gauge {
      display: flex; align-items: center; gap: 16px;
      padding: 14px 16px; margin-bottom: 12px;
      background: var(--secondary-background-color, rgba(0,0,0,0.04));
      border-radius: 14px; cursor: pointer;
    }
    .gauge-ring { position: relative; width: 86px; height: 86px; flex-shrink: 0; }
    .gauge-ring svg.ring { width: 100%; height: 100%; transform: rotate(-90deg); }
    .gauge-ring .bg-ring {
      fill: none; stroke: var(--divider-color, #e0e0e0); stroke-width: 6;
    }
    .gauge-ring .fg-ring {
      fill: none; stroke: #4caf50; stroke-width: 6; stroke-linecap: round;
      transition: stroke-dashoffset 1s ease;
      filter: drop-shadow(0 0 6px rgba(76,175,80,0.35));
    }
    .gauge-center {
      position: absolute; inset: 0;
      display: flex; flex-direction: column;
      align-items: center; justify-content: center;
    }
    .gauge-watts {
      font-family: ui-monospace, 'Roboto Mono', monospace;
      font-size: 22px; font-weight: 700; line-height: 1;
      font-variant-numeric: tabular-nums;
      color: var(--primary-text-color);
    }
    .gauge-watts small {
      font-size: 11px; font-weight: 500;
      color: var(--secondary-text-color); margin-left: 1px;
    }
    .gauge-unit {
      font-size: 9px; text-transform: uppercase; letter-spacing: 1px;
      color: var(--secondary-text-color); margin-top: 4px; font-weight: 600;
    }
    .power-details { flex: 1; display: flex; flex-direction: column; gap: 8px; }
    .power-row { display: flex; justify-content: space-between; align-items: center; }
    .power-row .lbl {
      color: var(--secondary-text-color);
      text-transform: uppercase; letter-spacing: 0.8px;
      font-size: 9.5px; font-weight: 600;
    }
    .power-row .val {
      font-family: ui-monospace, 'Roboto Mono', monospace;
      font-variant-numeric: tabular-nums;
      font-weight: 600; font-size: 13px;
      color: var(--primary-text-color);
    }
    .power-bar {
      height: 5px; border-radius: 3px;
      background: var(--divider-color, #e0e0e0); overflow: hidden;
    }
    .power-bar-fill {
      height: 100%;
      background: linear-gradient(90deg, #2e7d32, #4caf50);
      border-radius: 3px;
      transition: width 1s ease;
    }

    /* Combined mute + volume control: header icon shows current state,
       click reveals a small popover with the 4 levels (mute/low/med/high). */
    .sound-wrap { position: relative; display: inline-flex; }
    .sound-btn {
      background: none; border: none; padding: 4px; cursor: pointer;
      color: var(--secondary-text-color); display: flex; align-items: center;
      opacity: 0.5; transition: opacity 0.2s, color 0.2s;
    }
    .sound-btn:hover { opacity: 1; }
    .sound-btn.on {
      color: var(--primary-color, #03a9f4);
      opacity: 0.85;
    }
    .sound-btn.on:hover { opacity: 1; }
    .sound-btn ha-icon { --mdc-icon-size: 20px; }
    .sound-popover {
      position: absolute; top: calc(100% + 6px); right: 0;
      display: none;
      flex-direction: row; gap: 2px; padding: 4px;
      background: var(--ha-card-background, var(--card-background-color, #fff));
      border: 1px solid var(--divider-color, #e0e0e0);
      border-radius: 10px;
      box-shadow: 0 4px 16px rgba(0,0,0,0.18);
      z-index: 10;
    }
    .sound-wrap.open .sound-popover { display: flex; }
    .sound-opt {
      background: transparent; border: none; cursor: pointer;
      padding: 6px 8px; border-radius: 6px;
      color: var(--secondary-text-color);
      display: flex; align-items: center; justify-content: center;
      transition: background 0.15s, color 0.15s;
    }
    .sound-opt ha-icon { --mdc-icon-size: 18px; }
    .sound-opt:hover { background: var(--divider-color); color: var(--primary-text-color); }
    .sound-opt.active {
      background: var(--primary-color, #03a9f4);
      color: #fff;
    }
    .sound-opt.active ha-icon { color: #fff; }

    .section-label {
      font-size: 9px; text-transform: uppercase; letter-spacing: 1.5px;
      font-weight: 700; color: var(--secondary-text-color);
      margin: 14px 14px 8px;
      display: flex; align-items: center; gap: 8px;
    }
    .section-label::before { content: ''; width: 12px; height: 1px; background: var(--divider-color); }
    .section-label::after  { content: ''; flex: 1; height: 1px; background: var(--divider-color); }

    .port-grid {
      display: grid; grid-template-columns: repeat(3, 1fr);
      gap: 8px; padding: 0 12px;
    }
    .port-grid.usb-a {
      grid-template-columns: repeat(2, 1fr);
      padding-bottom: 14px;
    }

    .port {
      background: var(--secondary-background-color, rgba(0,0,0,0.04));
      border: 1.5px solid var(--divider-color, #e0e0e0);
      border-radius: 12px;
      padding: 11px 10px 10px;
      display: flex; flex-direction: column;
      cursor: pointer;
      position: relative; overflow: hidden;
      transition: transform 0.2s, border-color 0.2s, box-shadow 0.2s;
    }
    .port:hover { transform: translateY(-1px); }
    .port.active {
      border-color: rgba(76,175,80,0.5);
      box-shadow: 0 0 14px rgba(76,175,80,0.1);
    }
    .port.active::before {
      content: ''; position: absolute;
      top: 0; left: 0; right: 0; height: 2px;
      background: linear-gradient(90deg, transparent, #4caf50, transparent);
      animation: port-flow 2.5s ease-in-out infinite;
    }
    @keyframes port-flow {
      0%, 100% { opacity: 0.3; }
      50% { opacity: 1; }
    }
    .port.off, .port.idle { opacity: 0.6; }
    .port.off .port-vi { visibility: hidden; }
    .port.off .port-watts { color: var(--disabled-text-color, #bdbdbd); }
    .port.idle .port-watts { color: var(--secondary-text-color); }

    .port-head {
      display: flex; align-items: center; justify-content: space-between;
      gap: 6px; min-width: 0;
      margin-bottom: 7px;
    }
    .port-num {
      display: flex; align-items: center; gap: 5px;
      font-size: 10.5px; font-weight: 700;
      color: var(--secondary-text-color);
      min-width: 0; flex: 1;
    }
    .port-num span {
      overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
      min-width: 0;
    }
    .port-num .port-icon { --mdc-icon-size: 15px; color: var(--secondary-text-color); flex-shrink: 0; }
    .port.active .port-num,
    .port.active .port-num .port-icon { color: #4caf50; }

    .proto-badge {
      font-size: 7.5px; font-weight: 700;
      text-transform: uppercase; letter-spacing: 0.6px;
      padding: 2px 5px; border-radius: 3px;
      font-family: ui-monospace, 'Roboto Mono', monospace;
    }
    .proto-pd   { background: rgba(255,152,0,0.15);  color: #ff9800; }
    .proto-fast { background: rgba(171,71,188,0.15); color: #ab47bc; }
    .proto-off  { background: transparent;           color: var(--disabled-text-color); }

    .port-watts {
      font-family: ui-monospace, 'Roboto Mono', monospace;
      font-variant-numeric: tabular-nums;
      font-size: 22px; font-weight: 700;
      color: var(--primary-text-color);
      line-height: 1; margin: 2px 0 1px;
    }
    .port-watts small {
      font-size: 11px; font-weight: 500;
      color: var(--secondary-text-color); margin-left: 2px;
    }

    .port-vi {
      display: flex; gap: 8px;
      font-family: ui-monospace, 'Roboto Mono', monospace;
      font-variant-numeric: tabular-nums;
      font-size: 10px;
      color: var(--secondary-text-color);
      margin-bottom: 6px;
    }
    .port-vi span::before {
      content: ''; display: inline-block;
      width: 3px; height: 3px; border-radius: 50%;
      background: currentColor; vertical-align: middle;
      margin-right: 4px; opacity: 0.5;
    }

    .port-bar {
      height: 3px; border-radius: 2px;
      background: var(--divider-color, #e0e0e0);
      overflow: hidden; margin-top: auto;
    }
    .port-bar-fill {
      height: 100%; background: #4caf50; border-radius: 2px;
      transition: width 0.8s ease;
    }
    .port.off .port-bar-fill { background: var(--disabled-text-color); }

    /* \u{2550}\u{2550}\u{2550}\u{2550}\u{2550}\u{2550}\u{2550}\u{2550} Balance-charger (Air 8, K2 Air) \u{2550}\u{2550}\u{2550}\u{2550}\u{2550}\u{2550}\u{2550}\u{2550} */
    .pack-wrap {
      padding: 12px 12px 16px;
      display: flex; flex-direction: column; gap: 18px;
    }
    .pack-slot { display: flex; flex-direction: column; }
    .pack-shell { display: flex; flex-direction: row; align-items: center; width: 100%; }

    .pack-body {
      position: relative; flex: 1; min-height: 130px;
      background: var(--secondary-background-color, rgba(0,0,0,0.04));
      border: 2px solid var(--divider-color, #e0e0e0);
      border-radius: 14px;
      overflow: hidden;
      transition: border-color 0.4s, box-shadow 0.4s;
    }
    .pack-fill {
      position: absolute; top: 0; left: 0; bottom: 0;
      opacity: 0.18;
      transition: width 1.2s cubic-bezier(0.22, 1, 0.36, 1);
    }

    .channel-badge {
      position: absolute; top: 8px; left: 10px;
      font-size: 10px; font-weight: 700;
      color: var(--secondary-text-color);
      background: var(--card-background-color, #fff);
      padding: 1px 7px; border-radius: 4px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.1);
      z-index: 3;
    }

    .pack-content {
      position: relative; z-index: 2;
      display: grid;
      grid-template-columns: 1fr 110px;
      gap: 10px;
      padding: 14px 12px 16px 14px;
    }

    .cells-grid { display: grid; gap: 4px; }
    .cell-cell {
      background: rgba(255,255,255,0.7);
      border: 1px solid rgba(0,0,0,0.07);
      border-radius: 6px;
      padding: 16px 4px;
      text-align: center;
      position: relative;
    }
    .cell-cell.drift { border-color: rgba(255,153,85,0.55); }
    .cell-v {
      font-size: 12px; font-weight: 700;
      font-variant-numeric: tabular-nums;
      color: var(--primary-text-color);
      line-height: 1.1;
    }
    .cell-v small {
      font-size: 8.5px; font-weight: 400;
      color: var(--secondary-text-color); margin-left: 1px;
    }
    .cell-ir {
      font-size: 10px;
      font-variant-numeric: tabular-nums;
      color: var(--secondary-text-color);
      margin-top: 2px; line-height: 1;
    }
    .cell-ir small { font-size: 8px; }
    .cell-no {
      position: absolute; bottom: 3px; left: 3px;
      font-size: 7px; font-weight: 700;
      color: var(--secondary-text-color);
      background: var(--card-background-color, #fff);
      padding: 1px 5px; border-radius: 3px;
      box-shadow: 0 1px 2px rgba(0,0,0,0.08);
      line-height: 1; letter-spacing: 0.5px;
    }

    .pack-info {
      display: flex; flex-direction: column;
      align-items: center; justify-content: center;
      gap: 4px; text-align: center;
    }
    .pack-pct {
      display: flex; align-items: baseline; line-height: 1;
      font-variant-numeric: tabular-nums;
      margin-top: 2px;
    }
    .pack-pct .pct-num { font-size: 30px; font-weight: 800; color: var(--primary-text-color); }
    .pack-pct .pct-sym { font-size: 12px; font-weight: 500; color: var(--secondary-text-color); margin-left: 1px; }
    .pack-bolt {
      --mdc-icon-size: 18px;
      margin-left: 3px;
      filter: drop-shadow(0 0 4px currentColor);
      animation: bolt 1.2s ease-in-out infinite;
    }
    .pack-empty-icon { --mdc-icon-size: 28px; color: var(--disabled-text-color, #bdbdbd); margin: 4px 0; }
    .pack-empty-hint { font-size: 9px; color: var(--secondary-text-color); opacity: 0.6; }

    /* Done / empty pack-tile colors */
    .pack-slot.done .pack-body {
      border-color: rgba(66,165,245,0.45);
      box-shadow: 0 0 16px rgba(66,165,245,0.1);
    }
    .pack-slot.done .pack-fill {
      background: linear-gradient(90deg, var(--isdt-done-deep), var(--isdt-done));
      opacity: 0.18;
    }
    .pack-slot.done .status-badge { color: var(--isdt-done); }
    .pack-slot.empty .pack-body { opacity: 0.55; }
    .pack-slot.error .pack-body {
      border-color: rgba(239,83,80,0.5);
      box-shadow: 0 0 16px rgba(239,83,80,0.12);
      animation: err-b 2s ease-in-out infinite;
    }

    .pack-stats {
      padding: 0 6px;
      display: flex; flex-direction: column; gap: 4px;
      font-size: 12px;
      font-variant-numeric: tabular-nums;
    }
    .pack-stats.hidden { display: none; }
    .pack-stats .slot-vi {
      display: flex; justify-content: space-between;
      color: var(--primary-text-color);
    }
    .pack-stats .slot-vi span {
      display: inline-flex; align-items: center; gap: 4px;
    }
    .pack-stats .slot-vi ha-icon { --mdc-icon-size: 14px; opacity: 0.55; }
    .pack-stats .slot-session {
      display: flex; justify-content: space-between;
      color: var(--secondary-text-color); font-size: 11px;
    }
    .pack-stats .slot-session ha-icon { --mdc-icon-size: 13px; opacity: 0.55; margin-right: 2px; }

    /* \u{2550}\u{2550}\u{2550}\u{2550}\u{2550}\u{2550}\u{2550}\u{2550} Narrow card \u{2550}\u{2550}\u{2550}\u{2550}\u{2550}\u{2550}\u{2550}\u{2550} */
    @container (max-width: 350px) {
      .battery-info { display: none; }
      .header-stats { padding: 8px 4px; }
      .stat-value { font-size: 13px; }
      .stat-label { font-size: 8px; }
      .battery-grid { gap: 8px; padding: 8px; }
      .port-grid { grid-template-columns: repeat(2, 1fr); gap: 6px; padding: 0 8px; }
      .port-watts { font-size: 18px; }
      .gauge-ring { width: 72px; height: 72px; }
      .gauge-watts { font-size: 18px; }
      .power-row .val { font-size: 11px; }
      .sound-opt { padding: 5px 6px; }
      .sound-opt ha-icon { --mdc-icon-size: 16px; }
      .pack-content { grid-template-columns: 1fr 85px; gap: 8px; padding: 12px 10px 14px 12px; }
      .pack-pct .pct-num { font-size: 24px; }
    }
    `;
    }
}




const $5b8472df96c6a1cc$var$TAG = "isdt-charger-card";
const $5b8472df96c6a1cc$var$BANNER_ID = "isdt-charger-card-outdated-banner";
// Custom elements can only be defined once, so when two copies of the card are
// loaded (bundled with the integration + leftover standalone install) the first
// one wins. If an outdated copy won, this bundled copy patches the winner so
// every rendered card shows a visible hint on top of the console warning and
// the integration's repair issue.
function $5b8472df96c6a1cc$var$markOutdatedCards(WinnerClass) {
    const inject = (card)=>{
        const root = card.shadowRoot;
        if (!root || root.querySelector(`#${$5b8472df96c6a1cc$var$BANNER_ID}`)) return;
        const haCard = root.querySelector("ha-card");
        if (!haCard) return; // not rendered yet — retry on the next render
        const banner = document.createElement("div");
        banner.id = $5b8472df96c6a1cc$var$BANNER_ID;
        banner.style.cssText = "background:var(--warning-color,#ffa600);color:var(--text-primary-color,#fff);padding:6px 12px;font-size:12px;line-height:1.3;font-weight:500;border-radius:var(--ha-card-border-radius,12px) var(--ha-card-border-radius,12px) 0 0;";
        banner.textContent = `\u{26A0}\u{FE0F} ${(0, $d8078e452c66bdbe$export$625550452a3fa3ec)(card._hass, "outdated_standalone_active")}`;
        haCard.prepend(banner);
    };
    // The card is a plain HTMLElement: a full render replaces the shadow root's
    // content, so the banner is added again after every render.
    const origRender = WinnerClass.prototype._render;
    if (typeof origRender !== "function") return;
    WinnerClass.prototype._render = function(...args) {
        const result = origRender.apply(this, args);
        try {
            inject(this);
        } catch (e) {
        // Never break the (old) card over a hint.
        }
        return result;
    };
}
const $5b8472df96c6a1cc$var$winner = customElements.get($5b8472df96c6a1cc$var$TAG);
if ($5b8472df96c6a1cc$var$winner) {
    console.warn(`isdt-charger-card v${(0, $8ee5ce714273e53b$export$d5e7ce6d07daf10f)} [${(0, $8ee5ce714273e53b$export$9b657414b7dffe40)}] was not loaded: ` + "another copy of the card is already registered. The card ships with the " + "ISDT Air BLE integration \u2014 if the standalone card is still installed " + "(HACS or manual resource), remove it to avoid running an outdated version.");
    if ((0, $8ee5ce714273e53b$export$9b657414b7dffe40) === "bundled" && $5b8472df96c6a1cc$var$winner.CARD_ORIGIN !== "bundled") $5b8472df96c6a1cc$var$markOutdatedCards($5b8472df96c6a1cc$var$winner);
} else {
    // Marker for other copies to recognize which variant won the race.
    (0, $9a3262f48b2f355e$export$fda68d6dc0a4d865).CARD_VERSION = (0, $8ee5ce714273e53b$export$d5e7ce6d07daf10f);
    (0, $9a3262f48b2f355e$export$fda68d6dc0a4d865).CARD_ORIGIN = (0, $8ee5ce714273e53b$export$9b657414b7dffe40);
    customElements.define($5b8472df96c6a1cc$var$TAG, (0, $9a3262f48b2f355e$export$fda68d6dc0a4d865));
    window.customCards = window.customCards || [];
    window.customCards.push({
        type: $5b8472df96c6a1cc$var$TAG,
        name: "ISDT Air Card",
        description: "Dashboard card for ISDT Air BLE chargers and adapters (MASS2) \u2014 adapts to your HA theme",
        preview: true,
        documentationURL: "https://github.com/mtheli/isdt_air_ble#lovelace-card",
        // Card picker suggestion (HA 2026.6+): suggest this card for any
        // isdt_air_ble entity. Slot/port entities live on sub-devices linked to
        // the charger via via_device_id — climb to the main device the card expects.
        getEntitySuggestion: (hass, entityId)=>{
            const entity = hass.entities?.[entityId];
            if (!entity || entity.platform !== "isdt_air_ble") return null;
            let deviceId = entity.device_id;
            const parentId = hass.devices?.[deviceId]?.via_device_id;
            if (parentId && hass.devices?.[parentId]) deviceId = parentId;
            return {
                config: {
                    type: `custom:${$5b8472df96c6a1cc$var$TAG}`,
                    device_id: deviceId
                }
            };
        }
    });
    console.info(`%c ISDT-AIR-CARD %c v${(0, $8ee5ce714273e53b$export$d5e7ce6d07daf10f)} [${(0, $8ee5ce714273e53b$export$9b657414b7dffe40)}] `, "color:#4caf50;background:#222;font-weight:bold;padding:2px 6px;border-radius:3px 0 0 3px", "color:#e1e1e1;background:#444;padding:2px 6px;border-radius:0 3px 3px 0");
}


