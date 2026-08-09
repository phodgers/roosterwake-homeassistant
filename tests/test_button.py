"""Buttons: wake with two-phase events, power with the funnel's honesty, dynamics."""

from __future__ import annotations

from datetime import timedelta

import pytest
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.roosterwake import button as button_mod
from custom_components.roosterwake.const import EVENT_WAKE_RESULT

from .conftest import setup_integration
from .fixtures import (
    BASE_URL,
    DEVICES_OK,
    MAC_OFFICE,
    MACHINES_LOFT_GREW_AGENT,
    POWER_ACCEPTED,
    POWER_REFUSED_NO_AGENT,
    WAKE_ENTRY_UP,
    WAKE_OFFLINE,
    WAKE_OK,
    WAKE_OK_NO_PROBE,
    WAKE_RATE_LIMITED,
)

WAKE_BUTTON = "button.office_pc_wake"
SLEEP_BUTTON = "button.office_pc_sleep"


def _capture_events(hass: HomeAssistant) -> list[Event]:
    events: list[Event] = []

    @callback
    def _listener(event: Event) -> None:
        events.append(event)

    hass.bus.async_listen(EVENT_WAKE_RESULT, _listener)
    return events


async def _press(hass: HomeAssistant, entity_id: str) -> None:
    await hass.services.async_call(
        "button", "press", {"entity_id": entity_id}, blocking=True
    )


@pytest.fixture
def fast_confirm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Collapse the confirmation poll's cadence so tests do not wait real seconds."""
    monkeypatch.setattr(button_mod, "CONFIRM_POLL_INTERVAL_S", 0)
    monkeypatch.setattr(button_mod, "CONFIRM_POLL_DEADLINE_S", 1)


async def test_press_wakes_and_confirmation_lands_as_a_second_event(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    fast_confirm: None,
) -> None:
    """The full confirm flow: POST /wake, then GET /wake/{id} until terminal."""
    await setup_integration(hass, aioclient_mock, config_entry)
    events = _capture_events(hass)

    aioclient_mock.post(f"{BASE_URL}/api/v1/wake", json=WAKE_OK)
    aioclient_mock.get(f"{BASE_URL}/api/v1/wake/203", json=WAKE_ENTRY_UP)
    await _press(hass, WAKE_BUTTON)
    await hass.async_block_till_done(wait_background_tasks=True)

    wake_calls = [
        call for call in aioclient_mock.mock_calls if str(call[1]).endswith("/api/v1/wake")
    ]
    assert wake_calls[-1][0] == "POST"
    assert wake_calls[-1][2] == {"mac": MAC_OFFICE, "confirm": True}

    assert [event.data["phase"] for event in events] == ["sent", "confirmed"]

    sent = events[0].data
    assert sent["ok"] is True
    assert sent["machine"] == "Office PC"
    assert sent["wake_id"] == 203
    assert sent["confirmation_started"] is True
    assert sent["diagnosis"]["headline"] == "Sent 12 packets."

    confirmed = events[1].data
    assert confirmed["wake_id"] == 203
    assert confirmed["came_up"] is True
    assert confirmed["probe_state"] == "up"
    assert confirmed["probe_ms"] == 23000
    # The connect handoff rides only on confirmed rows — and so reaches automations.
    assert confirmed["connect_url"] == "rdp://office-pc"


async def test_confirm_off_sends_plain_and_polls_nothing(
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

    aioclient_mock.post(f"{BASE_URL}/api/v1/wake", json=WAKE_OK_NO_PROBE)
    await _press(hass, WAKE_BUTTON)
    await hass.async_block_till_done(wait_background_tasks=True)

    wake_calls = [
        call for call in aioclient_mock.mock_calls if "/api/v1/wake" in str(call[1])
    ]
    assert wake_calls[-1][2] == {"mac": MAC_OFFICE}
    # No probe was started, so nothing polled /wake/{id}.
    assert not any("/api/v1/wake/" in str(call[1]) for call in aioclient_mock.mock_calls)


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
        await _press(hass, WAKE_BUTTON)
    await hass.async_block_till_done()

    assert len(events) == 1
    data = events[0].data
    assert data["phase"] == "sent"
    assert data["ok"] is False
    assert data["err"] == "offline"
    assert data["diagnosis"]["blame"] == "device"


async def test_wake_budget_refusal_names_the_wait(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    """The relay's budget answers 200 ok:false with retryAfter — surfaced, seconds and all."""
    await setup_integration(hass, aioclient_mock, config_entry)
    events = _capture_events(hass)

    aioclient_mock.post(f"{BASE_URL}/api/v1/wake", json=WAKE_RATE_LIMITED)
    with pytest.raises(HomeAssistantError, match="Try again in 42 s"):
        await _press(hass, WAKE_BUTTON)
    await hass.async_block_till_done()

    assert events[0].data["err"] == "rate_limited"
    assert events[0].data["retry_after"] == 42


async def test_http_429_on_wake_extends_the_shared_hold_off(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    await setup_integration(hass, aioclient_mock, config_entry)
    coordinator = config_entry.runtime_data.coordinator
    assert coordinator.holding_off is False

    aioclient_mock.post(
        f"{BASE_URL}/api/v1/wake",
        status=429,
        headers={"Retry-After": "90"},
        json={"error": "rate_limited"},
    )
    with pytest.raises(HomeAssistantError, match="90 s"):
        await _press(hass, WAKE_BUTTON)

    # The button's 429 silences the coordinator too: one refusal, one hold-off.
    assert coordinator.holding_off is True


async def test_confirmation_poll_respects_the_hold_off(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    fast_confirm: None,
) -> None:
    """While a rate-limit hold-off runs, the poller waits without touching the network."""
    await setup_integration(hass, aioclient_mock, config_entry)
    events = _capture_events(hass)
    config_entry.runtime_data.coordinator.note_rate_limit(3600)

    aioclient_mock.post(f"{BASE_URL}/api/v1/wake", json=WAKE_OK)
    aioclient_mock.get(f"{BASE_URL}/api/v1/wake/203", json=WAKE_ENTRY_UP)
    await _press(hass, WAKE_BUTTON)
    await hass.async_block_till_done(wait_background_tasks=True)

    # The deadline passed inside the hold-off: not one GET went out, and no second
    # event was invented.
    assert not any("/api/v1/wake/203" in str(call[1]) for call in aioclient_mock.mock_calls)
    assert [event.data["phase"] for event in events] == ["sent"]


async def test_power_press_sends_the_action(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    await setup_integration(hass, aioclient_mock, config_entry)

    sleep = hass.states.get(SLEEP_BUTTON)
    assert sleep is not None
    assert sleep.state != "unavailable"

    aioclient_mock.clear_requests()
    aioclient_mock.post(f"{BASE_URL}/api/v1/power", json=POWER_ACCEPTED)
    await _press(hass, SLEEP_BUTTON)

    method, url, body, _ = aioclient_mock.mock_calls[-1]
    assert method == "POST"
    assert str(url).endswith("/api/v1/power")
    assert body == {"mac": MAC_OFFICE, "action": "sleep"}


async def test_power_refusal_surfaces_the_funnel_headline(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    await setup_integration(hass, aioclient_mock, config_entry)

    aioclient_mock.clear_requests()
    aioclient_mock.post(f"{BASE_URL}/api/v1/power", json=POWER_REFUSED_NO_AGENT)
    with pytest.raises(HomeAssistantError, match="no agent installed"):
        await _press(hass, SLEEP_BUTTON)


async def test_power_buttons_follow_the_machine_facts(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    """Agent-carried machines get buttons; a disconnected agent greys them; no agent, none."""
    await setup_integration(hass, aioclient_mock, config_entry)

    # Office PC: agent connected — buttons present and available.
    for action in ("sleep", "restart", "shut_down"):
        state = hass.states.get(f"button.office_pc_{action}")
        assert state is not None
        assert state.state != "unavailable"

    # Study PC: agent installed but disconnected — present, honestly unavailable.
    study_sleep = hass.states.get("button.study_pc_sleep")
    assert study_sleep is not None
    assert study_sleep.state == "unavailable"

    # Loft PC: no agent at all — no power buttons, only Wake.
    assert hass.states.get("button.loft_pc_sleep") is None
    assert hass.states.get("button.loft_pc_wake") is not None


async def test_power_buttons_appear_when_a_machine_grows_an_agent(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    """Dynamic appearance: the coordinator's ordinary refresh brings new buttons."""
    await setup_integration(hass, aioclient_mock, config_entry)
    assert hass.states.get("button.loft_pc_sleep") is None

    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{BASE_URL}/api/v1/devices", json=DEVICES_OK)
    aioclient_mock.get(f"{BASE_URL}/api/v1/machines", json=MACHINES_LOFT_GREW_AGENT)

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61))
    await hass.async_block_till_done()

    loft_sleep = hass.states.get("button.loft_pc_sleep")
    assert loft_sleep is not None
    assert loft_sleep.state != "unavailable"


async def test_no_power_scope_means_no_power_buttons(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    """A key without the power scope: wake works, power buttons simply do not exist."""
    await setup_integration(hass, aioclient_mock, config_entry, power_scope=False)

    assert hass.states.get(WAKE_BUTTON) is not None
    assert hass.states.get(SLEEP_BUTTON) is None
    assert hass.states.get("button.study_pc_sleep") is None
