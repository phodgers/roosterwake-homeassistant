"""Coordinator parsing against captured shapes, honest presence, and 429 backoff."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.roosterwake.api import HistoryEntry
from custom_components.roosterwake.coordinator import derive_presence

from .conftest import setup_integration
from .fixtures import (
    BASE_URL,
    HISTORY_OK,
    MAC_LOFT,
    MAC_OFFICE,
    MAC_STUDY,
)


def _rows() -> list[HistoryEntry]:
    return [HistoryEntry.from_json(row) for row in HISTORY_OK["entries"]]


def test_confirmed_wake_proves_up() -> None:
    presence = derive_presence(_rows(), MAC_OFFICE)
    assert presence.state == "up"
    assert presence.derived_from == "wake_confirmed"
    assert presence.since == 1754700300


def test_accepted_sleep_proves_down() -> None:
    presence = derive_presence(_rows(), MAC_STUDY)
    assert presence.state == "down"
    assert presence.derived_from == "sleep"


def test_unconfirmed_wake_proves_nothing() -> None:
    """A sent packet is not a machine that came up. Honest unknown."""
    presence = derive_presence(_rows(), MAC_LOFT)
    assert presence.state == "unknown"
    assert presence.since is None


def test_newest_proof_wins() -> None:
    """Office PC has an older shutdown row (id 180) and a newer confirmed wake (id 203)."""
    presence = derive_presence(_rows(), MAC_OFFICE)
    assert presence.state == "up"


def test_case_insensitive_mac_match() -> None:
    presence = derive_presence(_rows(), MAC_OFFICE.lower())
    assert presence.state == "up"


async def test_entities_reflect_the_poll(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    """The whole pipe: mocked API to entity states."""
    await setup_integration(hass, aioclient_mock, config_entry)

    office = hass.states.get("binary_sensor.office_pc_last_known_state")
    assert office is not None
    assert office.state == "on"
    assert office.attributes["kind"] == "last_known"
    assert office.attributes["derived_from"] == "wake_confirmed"

    study = hass.states.get("binary_sensor.study_pc_last_known_state")
    assert study is not None
    assert study.state == "off"

    loft = hass.states.get("binary_sensor.loft_pc_last_known_state")
    assert loft is not None
    assert loft.state == "unknown"

    emitter = hass.states.get("binary_sensor.rooster_wake_emitter_online")
    assert emitter is not None
    assert emitter.state == "on"
    assert emitter.attributes["emitters"][0]["name"] == "Hallway dongle"


async def test_429_backs_off_without_touching_the_network(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    """After a 429, the coordinator refuses to poll again until the hold-off passes."""
    await setup_integration(hass, aioclient_mock, config_entry)
    coordinator = config_entry.runtime_data.coordinator

    aioclient_mock.clear_requests()
    aioclient_mock.get(
        f"{BASE_URL}/api/v1/devices",
        status=429,
        headers={"Retry-After": "300"},
        json={"error": "rate_limited"},
    )

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61))
    await hass.async_block_till_done()
    assert coordinator.last_update_success is False
    calls_after_429 = len(aioclient_mock.mock_calls)
    assert calls_after_429 == 1

    # The next scheduled poll lands inside the hold-off: no request may go out.
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=122))
    await hass.async_block_till_done()
    assert len(aioclient_mock.mock_calls) == calls_after_429
    assert coordinator.last_update_success is False

    # The machine sensors go unavailable rather than lying with stale certainty.
    office = hass.states.get("binary_sensor.office_pc_last_known_state")
    assert office is not None
    assert office.state == "unavailable"


async def test_refused_key_starts_reauth(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    """A 401 mid-life means the key was revoked or expired — reauth, not a crash loop."""
    await setup_integration(hass, aioclient_mock, config_entry)

    aioclient_mock.clear_requests()
    aioclient_mock.get(
        f"{BASE_URL}/api/v1/devices",
        status=401,
        json={"error": "bad_key", "message": "That key is not valid."},
    )

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61))
    await hass.async_block_till_done()

    flows = hass.config_entries.flow.async_progress()
    assert any(
        flow["handler"] == "roosterwake" and flow["context"]["source"] == "reauth"
        for flow in flows
    )
