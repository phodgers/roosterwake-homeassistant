"""The Rooster Wake integration: wake your machines through the Rooster Wake cloud.

A thin client over the public v1 REST API — the same API any script can use, spoken with an
ordinary account API key. The relay protocol is public and self-hosting is a first-class
path, so the instance URL is configurable; the hosted service is only the default.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import RoosterWakeClient, RoosterWakeError, RoosterWakeScopeError
from .const import CONF_BASE_URL, DOMAIN
from .coordinator import RoosterWakeCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.BUTTON]

type RoosterWakeConfigEntry = ConfigEntry[RoosterWakeRuntimeData]


@dataclass(slots=True)
class RoosterWakeRuntimeData:
    """What a set-up entry carries."""

    client: RoosterWakeClient
    coordinator: RoosterWakeCoordinator
    # Whether the key carries the `power` scope. Probed once per setup, side-effect free.
    # Without it the power buttons are simply not created — never a failed setup.
    has_power_scope: bool


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

    try:
        has_power_scope = await client.has_power_scope()
    except RoosterWakeScopeError:  # pragma: no cover — has_power_scope maps this to False
        has_power_scope = False
    except RoosterWakeError as err:
        # The first refresh just worked, so this is a blip — retry the whole setup rather
        # than guess about a scope and build the wrong set of buttons.
        raise ConfigEntryNotReady(f"Could not determine the key's permissions: {err}") from err
    if not has_power_scope:
        _LOGGER.info(
            "The API key does not carry the 'power' permission; sleep/restart/shutdown "
            "buttons will not be created. Mint a key with the power scope to enable them"
        )

    entry.runtime_data = RoosterWakeRuntimeData(
        client=client, coordinator=coordinator, has_power_scope=has_power_scope
    )

    # The account (service) device, registered before any platform loads: every machine
    # device points at it via `via_device`, and a parent referenced before it exists is
    # an error from HA 2025.12.
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, f"{entry.entry_id}:account")},
        name="Rooster Wake",
        manufacturer="Rooster Wake",
        model="Cloud account",
        entry_type=dr.DeviceEntryType.SERVICE,
    )
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
