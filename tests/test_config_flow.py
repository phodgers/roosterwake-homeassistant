"""Config flow: a valid key, a refused key, an unreachable service, machine discovery."""

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
    ERROR_BAD_KEY,
    ERROR_OUT_OF_SCOPE,
    MAC_LOFT,
    MAC_OFFICE,
    MAC_STUDY,
    MACHINES_EMPTY,
    MACHINES_OK,
)


async def _start_user_flow(hass: HomeAssistant):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )


async def test_full_flow_discovers_and_selects_machines(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Valid key; machines come from the server, not from typing."""
    aioclient_mock.get(f"{BASE_URL}/api/v1/machines", json=MACHINES_OK)

    result = await _start_user_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_BASE_URL: BASE_URL, "api_key": API_KEY}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "machines"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MACHINES: [MAC_OFFICE, MAC_STUDY]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Rooster Wake"
    assert result["data"] == {CONF_BASE_URL: BASE_URL, "api_key": API_KEY}
    assert result["options"][CONF_MACHINES] == [MAC_OFFICE, MAC_STUDY]
    assert result["options"][CONF_CONFIRM_WAKES] is True


async def test_empty_selection_is_refused(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{BASE_URL}/api/v1/machines", json=MACHINES_OK)

    result = await _start_user_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_BASE_URL: BASE_URL, "api_key": API_KEY}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MACHINES: []}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_MACHINES: "no_selection"}


async def test_account_with_no_machines_aborts(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Machines are added on the dashboard; an entry with none would show nothing."""
    aioclient_mock.get(f"{BASE_URL}/api/v1/machines", json=MACHINES_EMPTY)

    result = await _start_user_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_BASE_URL: BASE_URL, "api_key": API_KEY}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_machines"


async def test_refused_key_names_the_plan_gate(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A 401 shows invalid_auth — whose message names the Plus/Pro requirement."""
    aioclient_mock.get(f"{BASE_URL}/api/v1/machines", json=ERROR_BAD_KEY, status=401)

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
    aioclient_mock.get(f"{BASE_URL}/api/v1/machines", json=ERROR_OUT_OF_SCOPE, status=403)

    result = await _start_user_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_BASE_URL: BASE_URL, "api_key": API_KEY}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"api_key": "missing_scope"}


async def test_unreachable_service(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(
        f"{BASE_URL}/api/v1/machines", exc=aiohttp.ClientConnectionError()
    )

    result = await _start_user_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_BASE_URL: BASE_URL, "api_key": API_KEY}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


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


async def test_options_reselect_machines_from_the_live_list(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    """The options flow re-discovers: the account as it is NOW is the choice offered."""
    await setup_integration(hass, aioclient_mock, config_entry)

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["type"] is FlowResultType.MENU

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "machines"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "machines"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_MACHINES: [MAC_LOFT]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options[CONF_MACHINES] == [MAC_LOFT]


async def test_options_settings_toggle_confirm(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    await setup_integration(hass, aioclient_mock, config_entry)

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "settings"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_CONFIRM_WAKES: False}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options[CONF_CONFIRM_WAKES] is False
    # The machine selection survives a settings change.
    assert config_entry.options[CONF_MACHINES] == [MAC_OFFICE, MAC_STUDY, MAC_LOFT]
