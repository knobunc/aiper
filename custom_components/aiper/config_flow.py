"""Config flow for Aiper IrriSense integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback

from .const import (
    CONF_ACTIVE_POLL_INTERVAL,
    CONF_ADDRESS,
    CONF_IDLE_POLL_INTERVAL,
    DOMAIN,
    POLL_IDLE,
    POLL_IRRIGATING,
)

_LOGGER = logging.getLogger(__name__)


class AiperConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle config flow for Aiper IrriSense BLE devices."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._address: str | None = None
        self._name: str | None = None

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle Bluetooth discovery."""
        await self.async_set_unique_id(discovery_info.address.upper())
        self._abort_if_unique_id_configured()

        self._discovery_info = discovery_info
        self._address = discovery_info.address
        self._name = discovery_info.name or discovery_info.address

        self.context["title_placeholders"] = {"name": self._name}
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm the discovered device."""
        if user_input is None:
            self._set_confirm_only()
            return self.async_show_form(
                step_id="confirm",
                data_schema=vol.Schema({}),
                description_placeholders={
                    "name": self._name or "Unknown",
                    "address": self._address or "Unknown",
                },
            )

        return self.async_create_entry(
            title=self._name or f"IrriSense {self._address}",
            data={CONF_ADDRESS: self._address},
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle manual user setup."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address.upper())
            self._abort_if_unique_id_configured()
            self._address = address
            self._name = f"IrriSense {address}"
            return await self.async_step_confirm()

        discovered = async_discovered_service_info(self.hass, connectable=True)
        aiper_devices: dict[str, str] = {}
        for info in discovered:
            name = info.name or ""
            if name.lower().startswith("aiper"):
                aiper_devices[info.address] = name

        if not aiper_devices:
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_ADDRESS): vol.In(aiper_devices)}
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return AiperOptionsFlowHandler()


class AiperOptionsFlowHandler(OptionsFlow):
    """Handle options flow for Aiper."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_IDLE_POLL_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_IDLE_POLL_INTERVAL, POLL_IDLE
                        ),
                    ): vol.All(int, vol.Range(min=30, max=300)),
                    vol.Optional(
                        CONF_ACTIVE_POLL_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_ACTIVE_POLL_INTERVAL, POLL_IRRIGATING
                        ),
                    ): vol.All(int, vol.Range(min=5, max=60)),
                }
            ),
        )
