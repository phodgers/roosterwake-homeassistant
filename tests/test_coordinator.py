"""Coordinator against captured shapes: live-aware presence, 429 backoff, reauth."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from .conftest import setup_integration
from .fixtures import BASE_URL

OFFICE_PRESENCE = "binary_sensor.office_pc_presence"
STUDY_PRESENCE = "binary_sensor.study_pc_presence"
LOFT_PRESENCE = "binary_sensor.loft_pc_presence"


async def test_entities_reflect_the_poll(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    """The whole pipe: mocked API to entity states, presence straight from the service."""
    await setup_integration(hass, aioclient_mock, config_entry)

    office = hass.states.get(OFFICE_PRESENCE)
    assert office is not None
    assert office.state == "on"
    # live: the agent's open connection IS the machine being up.
    assert office.attributes["live"] is True
    assert office.attributes["kind"] == "live"
    assert "at" not in office.attributes
    assert office.attributes["site"] == "Home"
    # G4.5's dated segment fact rides along.
    assert office.attributes["last_sighting"]["segment"] == "192.168.1.x"

    study = hass.states.get(STUDY_PRESENCE)
    assert study is not None
    assert study.state == "off"
    assert study.attributes["live"] is False
    assert study.attributes["kind"] == "last_known"
    assert study.attributes["at"] == "2025-08-09T00:46:40+00:00"

    loft = hass.states.get(LOFT_PRESENCE)
    assert loft is not None
    assert loft.state == "unknown"
    assert loft.attributes["kind"] == "unknown"

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
    assert coordinator.holding_off is True
    calls_after_429 = len(aioclient_mock.mock_calls)
    assert calls_after_429 == 1

    # The next scheduled poll lands inside the hold-off: no request may go out.
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=122))
    await hass.async_block_till_done()
    assert len(aioclient_mock.mock_calls) == calls_after_429
    assert coordinator.last_update_success is False

    # The machine sensors go unavailable rather than lying with stale certainty.
    office = hass.states.get(OFFICE_PRESENCE)
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
