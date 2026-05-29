"""Tests for the Aiper IrriSense config flow."""

from unittest.mock import AsyncMock, MagicMock, patch

from bleak import BleakError
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak

from custom_components.aiper.config_flow import (
    AiperConfigFlow,
    AiperOptionsFlowHandler,
)
from custom_components.aiper.const import CONF_ADDRESS

PATCH_BLEAK = "custom_components.aiper.config_flow.BleakClient"
PATCH_DISCO = (
    "custom_components.aiper.config_flow.async_discovered_service_info"
)


def _make_discovery_info(
    address: str = "AA:BB:CC:DD:EE:FF",
    name: str = "Aiper-WR-1234",
) -> BluetoothServiceInfoBleak:
    info = MagicMock(spec=BluetoothServiceInfoBleak)
    info.address = address
    info.name = name
    return info


def _make_flow() -> AiperConfigFlow:
    flow = AiperConfigFlow()
    flow.hass = MagicMock()
    flow.context = {}
    return flow


class TestBluetoothDiscovery:
    async def test_sets_unique_id_and_context(self):
        flow = _make_flow()
        discovery = _make_discovery_info()

        mock_set_uid = AsyncMock()
        with (
            patch.object(flow, "async_set_unique_id", mock_set_uid),
            patch.object(flow, "_abort_if_unique_id_configured"),
            patch.object(
                flow, "async_step_confirm", new_callable=AsyncMock
            ) as confirm,
        ):
            await flow.async_step_bluetooth(discovery)

        mock_set_uid.assert_called_once_with("AA:BB:CC:DD:EE:FF")
        assert flow._address == "AA:BB:CC:DD:EE:FF"
        assert flow._name == "Aiper-WR-1234"
        confirm.assert_called_once()

    async def test_uses_address_when_name_missing(self):
        flow = _make_flow()
        discovery = _make_discovery_info(name=None)

        with (
            patch.object(
                flow, "async_set_unique_id", new_callable=AsyncMock
            ),
            patch.object(flow, "_abort_if_unique_id_configured"),
            patch.object(
                flow, "async_step_confirm", new_callable=AsyncMock
            ),
        ):
            await flow.async_step_bluetooth(discovery)

        assert flow._name == "AA:BB:CC:DD:EE:FF"


class TestConfirmStep:
    async def test_shows_form_on_none_input(self):
        flow = _make_flow()
        flow._name = "Test Device"
        flow._address = "AA:BB:CC:DD:EE:FF"

        with (
            patch.object(flow, "_set_confirm_only"),
            patch.object(
                flow,
                "async_show_form",
                return_value={"type": "form"},
            ),
        ):
            result = await flow.async_step_confirm(None)

        assert result["type"] == "form"

    async def test_creates_entry_on_successful_connect(self):
        flow = _make_flow()
        flow._name = "Test Device"
        flow._address = "AA:BB:CC:DD:EE:FF"

        mock_client = AsyncMock()
        with (
            patch(PATCH_BLEAK, return_value=mock_client),
            patch.object(
                flow,
                "async_create_entry",
                return_value={"type": "create_entry"},
            ),
        ):
            result = await flow.async_step_confirm({"confirm": True})

        mock_client.connect.assert_called_once_with(timeout=10)
        mock_client.disconnect.assert_called_once()
        assert result["type"] == "create_entry"

    async def test_shows_error_on_connect_failure(self):
        flow = _make_flow()
        flow._name = "Test Device"
        flow._address = "AA:BB:CC:DD:EE:FF"

        mock_client = AsyncMock()
        mock_client.connect.side_effect = BleakError("No device")
        error_result = {
            "type": "form",
            "errors": {"base": "cannot_connect"},
        }

        with (
            patch(PATCH_BLEAK, return_value=mock_client),
            patch.object(flow, "_set_confirm_only"),
            patch.object(
                flow, "async_show_form", return_value=error_result
            ),
        ):
            result = await flow.async_step_confirm(
                {"confirm": True}
            )

        assert result["errors"]["base"] == "cannot_connect"

    async def test_shows_error_on_timeout(self):
        flow = _make_flow()
        flow._name = "Test Device"
        flow._address = "AA:BB:CC:DD:EE:FF"

        mock_client = AsyncMock()
        mock_client.connect.side_effect = TimeoutError()
        error_result = {
            "type": "form",
            "errors": {"base": "cannot_connect"},
        }

        with (
            patch(PATCH_BLEAK, return_value=mock_client),
            patch.object(flow, "_set_confirm_only"),
            patch.object(
                flow, "async_show_form", return_value=error_result
            ),
        ):
            result = await flow.async_step_confirm(
                {"confirm": True}
            )

        assert result["errors"]["base"] == "cannot_connect"


class TestUserStep:
    async def test_aborts_when_no_devices(self):
        flow = _make_flow()

        with (
            patch(PATCH_DISCO, return_value=[]),
            patch.object(
                flow, "async_abort", return_value={"type": "abort"}
            ) as mock_abort,
        ):
            await flow.async_step_user(None)

        mock_abort.assert_called_once_with(
            reason="no_devices_found"
        )


class TestReauthStep:
    async def test_reauth_shows_form(self):
        flow = _make_flow()

        with patch.object(
            flow, "async_show_form", return_value={"type": "form"}
        ):
            result = await flow.async_step_reauth(
                {CONF_ADDRESS: "AA:BB:CC:DD:EE:FF"}
            )

        assert result["type"] == "form"
        assert flow._address == "AA:BB:CC:DD:EE:FF"

    async def test_reauth_confirm_updates_entry(self):
        flow = _make_flow()
        flow._address = "AA:BB:CC:DD:EE:FF"

        mock_entry = MagicMock()
        with (
            patch.object(
                flow, "_get_reauth_entry", return_value=mock_entry
            ),
            patch.object(
                flow,
                "async_update_reload_and_abort",
                return_value={"type": "abort"},
            ) as mock_update,
        ):
            await flow.async_step_reauth_confirm({"confirm": True})

        mock_update.assert_called_once_with(
            mock_entry, data={CONF_ADDRESS: "AA:BB:CC:DD:EE:FF"}
        )


class TestOptionsFlow:
    async def test_shows_form_on_none_input(self):
        handler = AiperOptionsFlowHandler()
        mock_entry = MagicMock()
        mock_entry.options = {}
        with patch.object(
            type(handler), "config_entry",
            new_callable=lambda: property(lambda self: mock_entry),
        ):
            with patch.object(
                handler,
                "async_show_form",
                return_value={"type": "form"},
            ):
                result = await handler.async_step_init(None)

        assert result["type"] == "form"

    async def test_creates_entry_with_data(self):
        handler = AiperOptionsFlowHandler()

        with patch.object(
            handler,
            "async_create_entry",
            return_value={"type": "create_entry"},
        ):
            await handler.async_step_init(
                {
                    "idle_poll_interval": 90,
                    "active_poll_interval": 10,
                }
            )
