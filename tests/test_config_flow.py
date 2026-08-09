"""Config flow: a valid key, a refused key, an unreachable service, MAC validation."""

from __future__ import annotations

import aiohttp
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.roosterwake.const import (
    CONF_BASE_URL,
    CONF_CONFIRM_WAKES,
    CONF_MACHINES,
    DOMAIN,
)

from .conftest import setup_integration
from .fixtures import (
    API_KEY,
    BASE_URL,
    DEVICES_OK,
    ERROR_BAD_KEY,
    ERROR_OUT_OF_SCOPE,
    MAC_OFFICE,
)


async def _start_user_flow(hass: HomeAssistant):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )


async def test_full_flow_creates_entry(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Valid key, one machine, entry created with the right data and options."""
    aioclient_mock.get(f"{BASE_URL}/api/v1/devices", json=DEVICES_OK)

    result = await _start_user_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_BASE_URL: BASE_URL, "api_key": API_KEY}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "machine"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"name": "Office PC", "mac": "00-00-5e-00-53-0a", "add_another": False},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Rooster Wake"
    assert result["data"] == {CONF_BASE_URL: BASE_URL, "api_key": API_KEY}
    # The MAC is normalised to the service's canonical spelling.
    assert result["options"][CONF_MACHINES] == [{"name": "Office PC", "mac": MAC_OFFICE}]
    assert result["options"][CONF_CONFIRM_WAKES] is True


async def test_refused_key_names_the_plan_gate(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A 401 shows invalid_auth — whose message names the Plus/Pro requirement."""
    aioclient_mock.get(f"{BASE_URL}/api/v1/devices", json=ERROR_BAD_KEY, status=401)

    result = await _start_user_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_BASE_URL: BASE_URL, "api_key": "rw_live_nope"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"api_key": "invalid_auth"}


async def test_key_without_read_scope(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A wake-only key can wake but cannot be set up — it needs read too."""
    aioclient_mock.get(f"{BASE_URL}/api/v1/devices", json=ERROR_OUT_OF_SCOPE, status=403)

    result = await _start_user_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_BASE_URL: BASE_URL, "api_key": API_KEY}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"api_key": "missing_scope"}


async def test_unreachable_service(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{BASE_URL}/api/v1/devices", exc=aiohttp.ClientConnectionError())

    result = await _start_user_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_BASE_URL: BASE_URL, "api_key": API_KEY}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_bad_mac_is_refused_then_recoverable(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Broadcast and multicast addresses are refused; a real one then succeeds."""
    aioclient_mock.get(f"{BASE_URL}/api/v1/devices", json=DEVICES_OK)

    result = await _start_user_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_BASE_URL: BASE_URL, "api_key": API_KEY}
    )

    for bad in ("FF:FF:FF:FF:FF:FF", "01:00:5E:00:00:01", "not-a-mac"):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"name": "Office PC", "mac": bad, "add_another": False}
        )
        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"mac": "invalid_mac"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "Office PC", "mac": MAC_OFFICE, "add_another": False}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_same_key_twice_aborts(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    await setup_integration(hass, aioclient_mock, config_entry)

    result = await _start_user_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_BASE_URL: BASE_URL, "api_key": API_KEY}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_add_machine(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    await setup_integration(hass, aioclient_mock, config_entry)

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["type"] is FlowResultType.MENU

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "add_machine"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"name": "Bench PC", "mac": "00:00:5E:00:53:0D"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    macs = [machine["mac"] for machine in config_entry.options[CONF_MACHINES]]
    assert "00:00:5E:00:53:0D" in macs
