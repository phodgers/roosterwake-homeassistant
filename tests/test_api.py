"""The API client alone: parsing the captured shapes, and the error ladder."""

from __future__ import annotations

import aiohttp
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.roosterwake.api import (
    RoosterWakeAuthError,
    RoosterWakeClient,
    RoosterWakeConnectionError,
    RoosterWakeRateLimitError,
    RoosterWakeScopeError,
    WakeResult,
)

from .fixtures import (
    API_KEY,
    BASE_URL,
    DEVICE_ID,
    DEVICES_OK,
    ERROR_BAD_KEY,
    ERROR_NO_MACHINE,
    ERROR_OUT_OF_SCOPE,
    ERROR_OUT_OF_SCOPE_POWER,
    HISTORY_OK,
    MAC_OFFICE,
    MACHINES_OK,
    POWER_ACCEPTED,
    POWER_REFUSED_NO_AGENT,
    WAKE_ENTRY_UP,
    WAKE_ENTRY_WAITING,
    WAKE_OFFLINE,
    WAKE_OK,
    WAKE_RATE_LIMITED,
)


def _client(hass: HomeAssistant) -> RoosterWakeClient:
    return RoosterWakeClient(
        session=async_get_clientsession(hass), base_url=BASE_URL, api_key=API_KEY
    )


async def test_list_devices_parses_the_v1_shape(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{BASE_URL}/api/v1/devices", json=DEVICES_OK)
    emitters = await _client(hass).list_devices()
    assert [emitter.device_id for emitter in emitters] == [
        DEVICE_ID,
        "rw-agent-01",
        "rw-agent-02",
    ]
    assert emitters[0].online is True
    assert emitters[0].board == "pico2w"
    assert emitters[2].online is False


async def test_list_machines_parses_the_v1_shape(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Every fact the machines endpoint carries survives parsing."""
    aioclient_mock.get(f"{BASE_URL}/api/v1/machines", json=MACHINES_OK)
    machines = await _client(hass).list_machines()

    office, study, loft = machines
    assert office.name == "Office PC"
    assert office.mac == MAC_OFFICE
    assert office.site == "Home"
    assert office.active is True
    assert office.has_agent is True
    assert office.agent_connected is True
    assert office.power_allowed is True
    assert office.presence.state == "up"
    assert office.presence.live is True
    assert office.presence.at is None
    assert office.sighting == {
        "deviceName": "Hallway dongle",
        "segment": "192.168.1.x",
        "seenAt": 1754650000,
    }
    assert office.connect_url == "rdp://office-pc"

    assert study.has_agent is True
    assert study.agent_connected is False
    assert study.power_allowed is False
    assert study.presence.state == "down"
    assert study.presence.live is False
    assert study.presence.at == 1754700400

    assert loft.has_agent is False
    assert loft.agent_connected is None
    assert loft.presence.state == "unknown"
    assert loft.sighting is None


async def test_wake_result_parses_success(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(f"{BASE_URL}/api/v1/wake", json=WAKE_OK)
    result = await _client(hass).wake(MAC_OFFICE, confirm=True)
    assert result.ok is True
    assert result.id == 203
    assert result.sent == 12
    assert result.target_mac == MAC_OFFICE
    assert result.delivered_by_name == "Hallway dongle"
    assert result.probe_started is True
    assert result.probe_timeout_s == 90
    assert result.retry_after is None
    assert result.diagnosis is not None
    assert result.diagnosis.headline == "Sent 12 packets."


async def test_device_failure_is_a_result_not_an_exception(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """The API contract: 200 with ok:false is an answer, and the client keeps it one."""
    aioclient_mock.post(f"{BASE_URL}/api/v1/wake", json=WAKE_OFFLINE)
    result = await _client(hass).wake(MAC_OFFICE)
    assert isinstance(result, WakeResult)
    assert result.ok is False
    assert result.err == "offline"
    assert result.diagnosis is not None
    assert result.diagnosis.blame == "device"


async def test_wake_budget_refusal_carries_retry_after_in_the_body(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """err rate_limited rides a 200 with `retryAfter` — deliberately not a 429."""
    aioclient_mock.post(f"{BASE_URL}/api/v1/wake", json=WAKE_RATE_LIMITED)
    result = await _client(hass).wake(MAC_OFFICE)
    assert result.ok is False
    assert result.err == "rate_limited"
    assert result.retry_after == 42


async def test_power_accepted(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(f"{BASE_URL}/api/v1/power", json=POWER_ACCEPTED)
    result = await _client(hass).power(MAC_OFFICE, "sleep")

    _, _, body, headers = aioclient_mock.mock_calls[-1]
    assert body == {"mac": MAC_OFFICE, "action": "sleep"}
    assert headers["Authorization"] == f"Bearer {API_KEY}"

    assert result.ok is True
    assert result.action == "sleep"
    assert result.agent_name == "Office PC agent"
    assert result.diagnosis is not None
    assert result.diagnosis.headline.startswith("Accepted")


async def test_power_refusal_is_a_result(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(f"{BASE_URL}/api/v1/power", json=POWER_REFUSED_NO_AGENT)
    result = await _client(hass).power("00:00:5E:00:53:0C", "sleep")
    assert result.ok is False
    assert result.err == "no_agent"
    assert result.diagnosis is not None
    assert "no agent installed" in result.diagnosis.headline


async def test_wake_entry_waiting_then_terminal(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{BASE_URL}/api/v1/wake/203", json=WAKE_ENTRY_WAITING)
    row = await _client(hass).wake_entry(203)
    assert row is not None
    assert row.probe_state == "waiting"
    assert row.probe_terminal is False

    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{BASE_URL}/api/v1/wake/203", json=WAKE_ENTRY_UP)
    row = await _client(hass).wake_entry(203)
    assert row is not None
    assert row.probe_terminal is True
    assert row.probe_state == "up"
    assert row.probe_ms == 23000
    # The connect handoff rides only on confirmed rows.
    assert row.connect_url == "rdp://office-pc"


async def test_wake_entry_404_is_none(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """The endpoint's byte-identical miss: not-mine and never-issued read the same."""
    aioclient_mock.get(
        f"{BASE_URL}/api/v1/wake/999",
        status=404,
        json={"error": "not_found", "message": "No such wake on this account."},
    )
    assert await _client(hass).wake_entry(999) is None


async def test_has_power_scope_true_and_false(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """The side-effect-free probe: the scope gate sits in front of the body check."""
    aioclient_mock.post(f"{BASE_URL}/api/v1/power", json=ERROR_NO_MACHINE, status=400)
    assert await _client(hass).has_power_scope() is True

    aioclient_mock.clear_requests()
    aioclient_mock.post(
        f"{BASE_URL}/api/v1/power", json=ERROR_OUT_OF_SCOPE_POWER, status=403
    )
    assert await _client(hass).has_power_scope() is False


async def test_history_parses_actions_and_probe_state(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{BASE_URL}/api/v1/devices/{DEVICE_ID}/history", json=HISTORY_OK)
    rows = await _client(hass).device_history(DEVICE_ID)
    assert [row.action for row in rows] == ["sleep", "wake", "wake"]
    assert rows[1].probe_state == "up"
    assert rows[1].probe_ms == 23000
    assert rows[2].probe_state is None


async def test_401_raises_auth_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{BASE_URL}/api/v1/devices", json=ERROR_BAD_KEY, status=401)
    with pytest.raises(RoosterWakeAuthError):
        await _client(hass).list_devices()


async def test_403_raises_scope_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{BASE_URL}/api/v1/devices", json=ERROR_OUT_OF_SCOPE, status=403)
    with pytest.raises(RoosterWakeScopeError):
        await _client(hass).list_devices()


async def test_429_carries_retry_after(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(
        f"{BASE_URL}/api/v1/devices",
        status=429,
        headers={"Retry-After": "17"},
        json={"error": "rate_limited"},
    )
    with pytest.raises(RoosterWakeRateLimitError) as raised:
        await _client(hass).list_devices()
    assert raised.value.retry_after == 17


async def test_429_without_header_defaults_sanely(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{BASE_URL}/api/v1/devices", status=429, json={})
    with pytest.raises(RoosterWakeRateLimitError) as raised:
        await _client(hass).list_devices()
    assert raised.value.retry_after == 60


async def test_5xx_and_transport_faults_are_connection_errors(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{BASE_URL}/api/v1/devices", status=502, json={})
    with pytest.raises(RoosterWakeConnectionError):
        await _client(hass).list_devices()

    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{BASE_URL}/api/v1/devices", exc=aiohttp.ClientConnectionError())
    with pytest.raises(RoosterWakeConnectionError):
        await _client(hass).list_devices()
