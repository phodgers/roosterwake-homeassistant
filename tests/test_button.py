"""The wake button: correct API call, the wake result event, honest failure."""

from __future__ import annotations

import pytest
from homeassistant.core import Event, HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.roosterwake.const import EVENT_WAKE_RESULT

from .conftest import setup_integration
from .fixtures import BASE_URL, MAC_OFFICE, WAKE_OFFLINE, WAKE_OK, WAKE_RATE_LIMITED

BUTTON = "button.office_pc_wake"


def _capture_events(hass: HomeAssistant) -> list[Event]:
    events: list[Event] = []
    hass.bus.async_listen(EVENT_WAKE_RESULT, events.append)
    return events


async def _press(hass: HomeAssistant) -> None:
    await hass.services.async_call(
        "button", "press", {"entity_id": BUTTON}, blocking=True
    )


async def test_press_wakes_with_confirmation(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    """A press POSTs the saved MAC with confirm on, and fires the result event."""
    await setup_integration(hass, aioclient_mock, config_entry)
    events = _capture_events(hass)

    aioclient_mock.post(f"{BASE_URL}/api/v1/wake", json=WAKE_OK)
    await _press(hass)
    await hass.async_block_till_done()

    method, url, body, headers = aioclient_mock.mock_calls[-1]
    assert method == "POST"
    assert str(url).endswith("/api/v1/wake")
    assert body == {"mac": MAC_OFFICE, "confirm": True}
    assert headers["Authorization"].startswith("Bearer rw_live_")

    assert len(events) == 1
    data = events[0].data
    assert data["ok"] is True
    assert data["machine"] == "Office PC"
    assert data["mac"] == MAC_OFFICE
    assert data["sent"] == 12
    assert data["delivered_by"] == "Hallway dongle"
    assert data["confirmation_started"] is True
    assert data["diagnosis"]["headline"] == "Sent 12 packets."
    assert data["diagnosis"]["blame"] is None


async def test_confirm_can_be_turned_off(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    config_entry = await setup_integration(hass, aioclient_mock, config_entry)
    hass.config_entries.async_update_entry(
        config_entry,
        options={**config_entry.options, "confirm_wakes": False},
    )
    await hass.async_block_till_done()

    aioclient_mock.post(f"{BASE_URL}/api/v1/wake", json=WAKE_OK)
    await _press(hass)
    await hass.async_block_till_done()

    _, _, body, _ = aioclient_mock.mock_calls[-1]
    assert body == {"mac": MAC_OFFICE}


async def test_failed_wake_raises_and_still_fires_the_event(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    """ok:false is an accurate answer, not an outage — event fired, error surfaced."""
    await setup_integration(hass, aioclient_mock, config_entry)
    events = _capture_events(hass)

    aioclient_mock.post(f"{BASE_URL}/api/v1/wake", json=WAKE_OFFLINE)
    with pytest.raises(HomeAssistantError, match="None of your dongles are connected"):
        await _press(hass)
    await hass.async_block_till_done()

    assert len(events) == 1
    data = events[0].data
    assert data["ok"] is False
    assert data["err"] == "offline"
    assert data["diagnosis"]["blame"] == "device"


async def test_wake_budget_refusal_is_named(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    """The relay's wake budget answers 200 ok:false err:rate_limited — surfaced as such."""
    await setup_integration(hass, aioclient_mock, config_entry)
    events = _capture_events(hass)

    aioclient_mock.post(f"{BASE_URL}/api/v1/wake", json=WAKE_RATE_LIMITED)
    with pytest.raises(HomeAssistantError, match="Too many wakes"):
        await _press(hass)
    await hass.async_block_till_done()

    assert events[0].data["err"] == "rate_limited"


async def test_http_429_on_wake_is_surfaced_with_retry_after(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    await setup_integration(hass, aioclient_mock, config_entry)

    aioclient_mock.post(
        f"{BASE_URL}/api/v1/wake",
        status=429,
        headers={"Retry-After": "42"},
        json={"error": "rate_limited"},
    )
    with pytest.raises(HomeAssistantError, match="42 s"):
        await _press(hass)
