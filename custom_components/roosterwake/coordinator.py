"""One coordinator for the whole config entry.

Polls the two account-level reads — the emitter list and the machines list — and derives
everything the entities show. One cycle, two requests, whatever the machine count: the
server holds no watchers for us, so Home Assistant behaves like any other dashboard client,
on a respectful interval, and backs off hard when told to.

Presence now comes straight from the machines list: the service answers with its own
honest verdict per machine — live agent-connected truth where an agent runs on the
machine, dated last-known state from the wake log otherwise, and ``unknown`` where nothing
is proved. Nothing is derived client-side any more.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import timedelta
import logging
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    Emitter,
    Machine,
    RoosterWakeAuthError,
    RoosterWakeClient,
    RoosterWakeConnectionError,
    RoosterWakeError,
    RoosterWakeRateLimitError,
)
from .const import DOMAIN, MIN_BACKOFF_S, UPDATE_INTERVAL_S

if TYPE_CHECKING:
    from . import RoosterWakeConfigEntry

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class RoosterWakeData:
    """What one poll cycle learned."""

    emitters: list[Emitter] = field(default_factory=list)
    machines: dict[str, Machine] = field(default_factory=dict)  # keyed by MAC, uppercase

    @property
    def any_emitter_online(self) -> bool:
        return any(emitter.online for emitter in self.emitters)


class RoosterWakeCoordinator(DataUpdateCoordinator[RoosterWakeData]):
    """The one poller for a config entry."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: RoosterWakeConfigEntry,
        client: RoosterWakeClient,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL_S),
        )
        self.client = client
        self._backoff_until: float = 0.0

    @property
    def holding_off(self) -> bool:
        """Inside a rate-limit hold-off: nothing may touch the network."""
        return time.monotonic() < self._backoff_until

    def note_rate_limit(self, retry_after: int) -> None:
        """Extend the hold-off.

        Any caller who saw a 429 reports it here, so one refusal silences every poller
        this integration runs — the coordinator and the confirmation poll alike.
        """
        until = time.monotonic() + max(retry_after, MIN_BACKOFF_S)
        self._backoff_until = max(self._backoff_until, until)

    async def _async_update_data(self) -> RoosterWakeData:
        # Respect a 429 for its full stated duration WITHOUT touching the network again —
        # a backoff that still polls to check is not a backoff.
        if self.holding_off:
            raise UpdateFailed(
                f"Holding off after a rate limit for another "
                f"{int(self._backoff_until - time.monotonic())} s"
            )

        try:
            emitters = await self.client.list_devices()
            machines = await self.client.list_machines()
        except RoosterWakeAuthError as err:
            raise ConfigEntryAuthFailed(
                "The API key was refused — it may have been revoked or expired"
            ) from err
        except RoosterWakeRateLimitError as err:
            self.note_rate_limit(err.retry_after)
            raise UpdateFailed(
                f"Rate limited; backing off for {max(err.retry_after, MIN_BACKOFF_S)} s"
            ) from err
        except (RoosterWakeConnectionError, RoosterWakeError) as err:
            raise UpdateFailed(str(err)) from err

        return RoosterWakeData(
            emitters=emitters,
            machines={machine.mac: machine for machine in machines},
        )
