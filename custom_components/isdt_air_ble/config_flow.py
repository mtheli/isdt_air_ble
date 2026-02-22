"""Config flow for ISDT C4 Air integration."""

import asyncio
import logging
from typing import Any

import voluptuous as vol

from bleak import BleakClient
from bleak_retry_connector import establish_connection

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow, ConfigEntry
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_ble_device_from_address,
)

from .const import (
    DOMAIN,
    ISDT_MANUFACTURER_ID,
    DEVICE_MODEL_MAP,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    CHAR_UUID_AF01,
    CHAR_UUID_AF02,
    CMD_HARDWARE_INFO_REQ,
)
from .parser import parse_hardware_info

_LOGGER = logging.getLogger(__name__)


def _detect_model(discovery_info: BluetoothServiceInfoBleak) -> str:
    """Detect device model from BLE manufacturer data.

    The manufacturer_data contains model identification bytes at offset 2-5.
    These are looked up in DEVICE_MODEL_MAP (from MyScanItemModel.java).
    """
    mfr_data = discovery_info.manufacturer_data.get(ISDT_MANUFACTURER_ID)
    if mfr_data and len(mfr_data) >= 6:
        model_id = (
            f"{mfr_data[2]:02x}{mfr_data[3]:02x}{mfr_data[4]:02x}{mfr_data[5]:02x}"
        )
        model = DEVICE_MODEL_MAP.get(model_id)
        if model:
            return model

    return "ISDT Device"


class ISDTOptionsFlow(OptionsFlow):
    """Handle options for ISDT chargers."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the options form."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current_interval = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )

        schema = vol.Schema(
            {
                vol.Required(CONF_SCAN_INTERVAL, default=current_interval): vol.All(
                    vol.Coerce(int), vol.Range(min=3, max=300)
                ),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)


class ISDTConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow for ISDT chargers."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> ISDTOptionsFlow:
        """Return the options flow handler."""
        return ISDTOptionsFlow()

    def __init__(self):
        super().__init__()
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._device_model: str = "ISDT Device"
        self._fetched_hw_version: str | None = None
        self._fetched_sw_version: str | None = None
        self._fetched_serial_number: str | None = None
        self._fetched_characteristics: dict[str, bool] = {}

    async def _async_fetch_device_info(self, address: str) -> None:
        """Connect to the BLE device and read hardware info + characteristics."""
        device = async_ble_device_from_address(self.hass, address)
        if not device:
            raise ConnectionError("BLE device not found")

        client = await establish_connection(
            BleakClient, device, "ISDT Config", timeout=15
        )

        try:
            # Check which characteristics are available
            services = client.services
            has_af01 = services.get_characteristic(CHAR_UUID_AF01) is not None
            has_af02 = services.get_characteristic(CHAR_UUID_AF02) is not None
            self._fetched_characteristics = {
                CHAR_UUID_AF01: has_af01,
                CHAR_UUID_AF02: has_af02,
            }

            # Read hardware info via AF02
            if has_af02:
                hw_response = asyncio.Queue(maxsize=5)

                def hw_callback(sender, data):
                    try:
                        hw_response.put_nowait(data)
                    except asyncio.QueueFull:
                        pass

                await client.start_notify(CHAR_UUID_AF02, hw_callback)
                await asyncio.sleep(0.3)

                await client.write_gatt_char(
                    CHAR_UUID_AF02, CMD_HARDWARE_INFO_REQ, response=False
                )

                try:
                    data = await asyncio.wait_for(hw_response.get(), timeout=3.0)
                    result = parse_hardware_info(data)
                    if result:
                        self._fetched_hw_version, self._fetched_sw_version, self._fetched_serial_number = result
                except asyncio.TimeoutError:
                    _LOGGER.warning("Timeout waiting for hardware info response")

                try:
                    await client.stop_notify(CHAR_UUID_AF02)
                except Exception:
                    pass
        finally:
            await client.disconnect()

    def _get_characteristics_text(self) -> str:
        """Format characteristics status for display."""
        lines = []
        labels = {
            CHAR_UUID_AF01: "AF01 (Polling & Notifications)",
            CHAR_UUID_AF02: "AF02 (Hardware Info)",
        }
        for uuid, found in self._fetched_characteristics.items():
            label = labels.get(uuid, uuid)
            icon = "✅" if found else "❌"
            lines.append(f"{icon} {label}")
        return "\n".join(lines)

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle discovery of an ISDT device via Bluetooth."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        self._discovery_info = discovery_info
        self._device_model = _detect_model(discovery_info)

        self.context["title_placeholders"] = {"name": f"ISDT {self._device_model}"}

        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm discovery and connect to read device info."""
        assert self._discovery_info is not None
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                await self._async_fetch_device_info(self._discovery_info.address)
                return await self.async_step_show_device_info()
            except Exception:
                _LOGGER.error(
                    "Failed to connect to %s", self._discovery_info.address,
                    exc_info=True,
                )
                errors["base"] = "cannot_connect"

        name = self._discovery_info.name or self._discovery_info.address

        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={"name": f"ISDT {self._device_model} ({name})"},
            errors=errors,
        )

    async def async_step_show_device_info(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show detected device info and create entry."""
        if user_input is not None:
            return self.async_create_entry(
                title=f"ISDT {self._device_model}",
                data={
                    "address": self._discovery_info.address,
                    "model": self._device_model,
                    "hw_version": self._fetched_hw_version,
                    "sw_version": self._fetched_sw_version,
                    "serial_number": self._fetched_serial_number,
                },
            )

        name = f"ISDT {self._device_model}"

        return self.async_show_form(
            step_id="show_device_info",
            data_schema=vol.Schema({}),
            description_placeholders={
                "name": name,
                "hw_version": self._fetched_hw_version or "Unknown",
                "fw_version": self._fetched_sw_version or "Unknown",
                "serial_number": self._fetched_serial_number or "Unknown",
                "characteristics": self._get_characteristics_text(),
            },
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a manual user-initiated flow (fallback)."""
        if self._discovery_info:
            return await self.async_step_bluetooth_confirm(user_input)
        return self.async_abort(reason="no_devices_found")
