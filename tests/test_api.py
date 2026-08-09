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
    ERROR_OUT_OF_SCOPE,
    HISTORY_OK,
    MAC_OFFICE,
    WAKE_OFFLINE,
    WAKE_OK,
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
    assert [emitter.device_id for emitter in emitters] == [DEVICE_ID, "rw-agent-7f"]
    assert emitters[0].online is True
    assert emitters[0].board == "pico2w"
    assert emitters[1].online is False


async def test_wake_result_parses_success(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(f"{BASE_URL}/api/v1/wake", json=WAKE_OK)
    result = await _client(hass).wake(MAC_OFFICE, confirm=True)
    assert result.ok is True
    assert result.sent == 12
    assert result.target_mac == MAC_OFFICE
    assert result.delivered_by_name == "Hallway dongle"
    assert result.probe_started is True
    assert result.probe_timeout_s == 90
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


async def test_history_parses_actions_and_probe_state(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{BASE_URL}/api/v1/devices/{DEVICE_ID}/history", json=HISTORY_OK)
    rows = await _client(hass).device_history(DEVICE_ID)
    assert [row.action for row in rows] == ["sleep", "wake", "wake", "shutdown"]
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
