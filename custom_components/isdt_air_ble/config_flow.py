"""Config flow for ISDT C4 Air integration."""

from typing import Any
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow, ConfigEntry
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak

from .const import DOMAIN, ISDT_MANUFACTURER_ID, DEVICE_MODEL_MAP, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL


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
                    vol.Coerce(int), vol.Range(min=10, max=300)
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

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle discovery of an ISDT device via Bluetooth."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        self._discovery_info = discovery_info
        self._device_model = _detect_model(discovery_info)

        self.context["title_placeholders"] = {"name": f"ISDT {self._device_model}"}

        return await self.async_step_user()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle user confirmation step."""
        if user_input is not None:
            return self.async_create_entry(
                title=f"ISDT {self._device_model}",
                data={
                    "address": self._discovery_info.address,
                    "model": self._device_model,
                },
            )

        return self.async_show_form(step_id="user")
