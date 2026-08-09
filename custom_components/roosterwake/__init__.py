"""The Rooster Wake integration: wake your machines through the Rooster Wake cloud.

A thin client over the public v1 REST API — the same API any script can use, spoken with an
ordinary account API key. The relay protocol is public and self-hosting is a first-class
path, so the instance URL is configurable; the hosted service is only the default.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import RoosterWakeClient
from .const import CONF_BASE_URL
from .coordinator import RoosterWakeCoordinator

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.BUTTON]

type RoosterWakeConfigEntry = ConfigEntry[RoosterWakeRuntimeData]


@dataclass(slots=True)
class RoosterWakeRuntimeData:
    """What a set-up entry carries."""

    client: RoosterWakeClient
    coordinator: RoosterWakeCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: RoosterWakeConfigEntry) -> bool:
    """Set up a Rooster Wake account from a config entry."""
    client = RoosterWakeClient(
        session=async_get_clientsession(hass),
        base_url=entry.data[CONF_BASE_URL],
        api_key=entry.data[CONF_API_KEY],
    )
    coordinator = RoosterWakeCoordinator(hass, entry, client)

    # Raises ConfigEntryAuthFailed on a refused key (starting reauth) and ConfigEntryNotReady
    # on an unreachable service — both the behaviour the coordinator base class provides.
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = RoosterWakeRuntimeData(client=client, coordinator=coordinator)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: RoosterWakeConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_options_updated(
    hass: HomeAssistant, entry: RoosterWakeConfigEntry
) -> None:
    """Machines were added or removed, or a setting changed — rebuild the entities."""
    await hass.config_entries.async_reload(entry.entry_id)
