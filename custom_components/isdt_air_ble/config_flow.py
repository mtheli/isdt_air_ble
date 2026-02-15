from typing import Any
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
)  # Wichtig: ConfigFlowResult nutzen
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from .const import DOMAIN


class ISDTConfigFlow(ConfigFlow, domain=DOMAIN):
    """Behandelt den Konfigurationsfluss für ISDT C4 Air."""

    VERSION = 1

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:  # Hier ConfigFlowResult statt FlowResult
        """Wird aufgerufen, wenn ein Gerät über Bluetooth entdeckt wird."""

        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        # Speichere die Entdeckungsdaten für den nächsten Schritt
        self._discovery_info = discovery_info

        # Korrekte Zuweisung für den Titel im UI
        self.context["title_placeholders"] = {
            "name": discovery_info.name or "ISDT C4 Air"
        }

        return await self.async_step_user()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:  # Auch hier anpassen
        if user_input is not None:
            return self.async_create_entry(
                title=self._discovery_info.name
                if self._discovery_info
                else "ISDT C4 Air",
                data={
                    "address": self._discovery_info.address,
                },
            )

        return self.async_show_form(step_id="user")
