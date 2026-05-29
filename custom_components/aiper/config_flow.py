"""Config flow for Aiper IrriSense integration."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol
from bleak import BleakClient, BleakError
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_ble_device_from_address,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback

from .const import (
    CONF_ACTIVE_POLL_INTERVAL,
    CONF_ADDRESS,
    CONF_IDLE_POLL_INTERVAL,
    CONF_MODEL,
    CONF_SERIAL,
    DOMAIN,
    NUS_TX_UUID,
    POLL_IDLE,
    POLL_IRRIGATING,
)
from .protocol import build_command, parse_response

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
                description_placeholders={
                    "name": self._name or "Unknown",
                    "address": self._address or "Unknown",
                },
            )

        errors: dict[str, str] = {}
        serial = ""
        model = ""

        try:
            serial, model = await self._probe_device()
        except (BleakError, TimeoutError, OSError):
            _LOGGER.debug("Failed to probe device %s", self._address, exc_info=True)
            errors["base"] = "cannot_connect"

        if errors:
            return self.async_show_form(
                step_id="confirm",
                errors=errors,
                description_placeholders={
                    "name": self._name or "Unknown",
                    "address": self._address or "Unknown",
                },
            )

        return self.async_create_entry(
            title=self._name or f"IrriSense {self._address}",
            data={
                CONF_ADDRESS: self._address,
                CONF_SERIAL: serial,
                CONF_MODEL: model,
            },
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

    async def _probe_device(self) -> tuple[str, str]:
        """Connect to device and send DevInfo to get serial/model."""
        assert self._address is not None
        ble_device = async_ble_device_from_address(
            self.hass, self._address.upper(), connectable=True
        )
        if ble_device is None:
            raise BleakError(f"Device {self._address} not found")

        serial = ""
        model = ""
        response_data: dict[str, Any] = {}
        event = asyncio.Event()

        def on_notify(_sender: int, data: bytearray) -> None:
            nonlocal response_data
            try:
                resp = parse_response(bytes(data))
                if resp.get("type") == "DevInfo":
                    response_data = resp.get("data", {})
                    event.set()
            except Exception:
                pass

        client = BleakClient(ble_device)
        try:
            await client.connect()
            await client.start_notify(NUS_TX_UUID, on_notify)
            message = build_command("DevInfo")
            await client.write_gatt_char(
                "6e400002-b5a3-f393-e0a9-e50e24dcca9e", message, response=False
            )
            await asyncio.wait_for(event.wait(), timeout=10.0)
            serial = response_data.get("sn", "")
            model = response_data.get("model", "")
        finally:
            try:
                await client.disconnect()
            except (BleakError, EOFError):
                pass

        return serial, model

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
