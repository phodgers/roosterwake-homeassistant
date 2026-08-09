"""Shared fixtures."""

from __future__ import annotations

import hashlib
import sys

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.roosterwake.const import (
    CONF_BASE_URL,
    CONF_CONFIRM_WAKES,
    CONF_MACHINES,
    DOMAIN,
)

from .fixtures import (
    API_KEY,
    BASE_URL,
    DEVICES_OK,
    ERROR_NO_MACHINE,
    ERROR_OUT_OF_SCOPE_POWER,
    MAC_LOFT,
    MAC_OFFICE,
    MAC_STUDY,
    MACHINES_OK,
)

if sys.platform == "win32":
    # The harness disables socket CREATION per test (pytest-socket), exempting only Unix
    # sockets — which is what asyncio's event loop plumbing uses on Linux. Windows has no
    # Unix sockets: the Proactor loop's self-pipe is an AF_INET pair, so the exemption
    # never matches and every test dies before its loop exists. Neutralise the creation
    # guard here, locally: the CONNECT guard (socket_allow_hosts, loopback only) stays in
    # force, so real network access is still refused, and CI on Linux keeps the strict
    # creation guard too.
    import pytest_socket

    pytest_socket.disable_socket = lambda allow_unix_socket=False: None


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load custom_components/ for every test."""
    return


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """A configured account with all three machines selected."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Rooster Wake",
        unique_id=hashlib.sha256(API_KEY.encode()).hexdigest()[:16],
        data={CONF_BASE_URL: BASE_URL, "api_key": API_KEY},
        options={
            CONF_MACHINES: [MAC_OFFICE, MAC_STUDY, MAC_LOFT],
            CONF_CONFIRM_WAKES: True,
        },
    )


def mock_account_reads(
    aioclient_mock: AiohttpClientMocker, *, power_scope: bool = True
) -> None:
    """Mock the reads a setup performs: the two polled lists and the scope probe.

    The scope probe is POST /api/v1/power with an empty body: 400 ``no_machine`` proves
    the scope gate was passed (nothing performed, nothing logged), 403 proves it was not.
    """
    aioclient_mock.get(f"{BASE_URL}/api/v1/devices", json=DEVICES_OK)
    aioclient_mock.get(f"{BASE_URL}/api/v1/machines", json=MACHINES_OK)
    if power_scope:
        aioclient_mock.post(f"{BASE_URL}/api/v1/power", json=ERROR_NO_MACHINE, status=400)
    else:
        aioclient_mock.post(
            f"{BASE_URL}/api/v1/power", json=ERROR_OUT_OF_SCOPE_POWER, status=403
        )


async def setup_integration(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    *,
    power_scope: bool = True,
) -> MockConfigEntry:
    """Set the entry up against mocked reads."""
    mock_account_reads(aioclient_mock, power_scope=power_scope)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry
