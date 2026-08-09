"""One coordinator for the whole config entry.

Polls the two readable v1 endpoints — the emitter list, and each emitter's recent history —
and derives everything the entities show. One poll cycle, whatever the machine count: the
server holds no watchers for us, so Home Assistant behaves like any other dashboard client,
on a respectful interval, and backs off when told to.

── What "presence" honestly means here ─────────────────────────────────────────────────────

The public API does not report whether a machine is up. What it does expose is the wake and
power history, including the wake-confirmation outcome the service's own probe recorded
(``probeState``) and accepted power actions. So presence is LAST-KNOWN, derived from the
newest row that proves something:

  - a wake whose probe answered ``up``          → the machine was up at that moment;
  - an accepted ``sleep`` or ``shutdown``       → the machine was going down at that moment.

A wake that merely sent packets proves nothing — Wake-on-LAN is unacknowledged — and rows
like that are deliberately ignored. A machine nobody has woken or slept through Rooster Wake
recently is honestly ``unknown``.
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
    HistoryEntry,
    RoosterWakeAuthError,
    RoosterWakeClient,
    RoosterWakeConnectionError,
    RoosterWakeError,
    RoosterWakeRateLimitError,
)
from .const import CONF_MACHINE_MAC, CONF_MACHINES, DOMAIN, MIN_BACKOFF_S, UPDATE_INTERVAL_S

if TYPE_CHECKING:
    from . import RoosterWakeConfigEntry

_LOGGER = logging.getLogger(__name__)

HISTORY_PAGE_SIZE = 25


@dataclass(slots=True)
class MachinePresence:
    """Last-known state of one machine, and how we know."""

    state: str  # "up", "down" or "unknown"
    since: int | None = None  # unix seconds of the row that proved it
    derived_from: str | None = None  # "wake_confirmed", "sleep", "shutdown"


@dataclass(slots=True)
class RoosterWakeData:
    """What one poll cycle learned."""

    emitters: list[Emitter] = field(default_factory=list)
    presence: dict[str, MachinePresence] = field(default_factory=dict)

    @property
    def any_emitter_online(self) -> bool:
        return any(emitter.online for emitter in self.emitters)


def derive_presence(rows: list[HistoryEntry], mac: str) -> MachinePresence:
    """Last-known presence for one machine from merged history rows.

    ``rows`` may span several emitters; the newest proving row wins. Pure so the parsing
    rules are testable against captured response shapes without a Home Assistant instance.
    """
    wanted = mac.upper()
    best: MachinePresence | None = None
    for row in rows:
        if (row.target_mac or "").upper() != wanted:
            continue
        proved: MachinePresence | None = None
        if row.action == "wake" and row.probe_state == "up":
            proved = MachinePresence(state="up", since=row.at, derived_from="wake_confirmed")
        elif row.action in ("sleep", "shutdown") and row.ok:
            # "Accepted" — the protocol acknowledges before acting, because the action
            # destroys the process that would confirm it. Down-ish is the honest reading.
            proved = MachinePresence(state="down", since=row.at, derived_from=row.action)
        if proved and (best is None or (proved.since or 0) > (best.since or 0)):
            best = proved
    return best or MachinePresence(state="unknown")


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
    def machine_macs(self) -> list[str]:
        return [
            machine[CONF_MACHINE_MAC]
            for machine in self.config_entry.options.get(CONF_MACHINES, [])
        ]

    async def _async_update_data(self) -> RoosterWakeData:
        # Respect a 429 for its full stated duration WITHOUT touching the network again —
        # a backoff that still polls to check is not a backoff.
        now = time.monotonic()
        if now < self._backoff_until:
            raise UpdateFailed(
                f"Holding off after a rate limit for another {int(self._backoff_until - now)} s"
            )

        try:
            emitters = await self.client.list_devices()
            rows: list[HistoryEntry] = []
            if self.machine_macs:
                for emitter in emitters:
                    rows.extend(
                        await self.client.device_history(
                            emitter.device_id, limit=HISTORY_PAGE_SIZE
                        )
                    )
        except RoosterWakeAuthError as err:
            raise ConfigEntryAuthFailed(
                "The API key was refused — it may have been revoked or expired"
            ) from err
        except RoosterWakeRateLimitError as err:
            self._backoff_until = time.monotonic() + max(err.retry_after, MIN_BACKOFF_S)
            raise UpdateFailed(
                f"Rate limited; backing off for {max(err.retry_after, MIN_BACKOFF_S)} s"
            ) from err
        except (RoosterWakeConnectionError, RoosterWakeError) as err:
            raise UpdateFailed(str(err)) from err

        presence = {mac: derive_presence(rows, mac) for mac in self.machine_macs}
        return RoosterWakeData(emitters=emitters, presence=presence)
