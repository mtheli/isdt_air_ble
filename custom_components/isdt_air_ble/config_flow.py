"""Config flow for ISDT C4 Air integration."""

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak

from .const import DOMAIN, ISDT_MANUFACTURER_ID, DEVICE_MODEL_MAP


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


class ISDTConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow for ISDT chargers."""

    VERSION = 1

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
