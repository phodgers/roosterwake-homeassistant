"""The Wake button, and — where the key and the machine allow it — power buttons.

Sleep / Restart / Shutdown exist only for machines the service says carry an agent, and
only when the API key holds the ``power`` scope (probed at setup; the scope is deliberately
never implied by ``wake`` — the right to switch a machine off must never ride the right to
switch it on). A machine that gains an agent appears with its buttons on the coordinator's
next refresh; an agent that disconnects greys them out (unavailable) rather than deleting
them, because the machine and its history have not gone anywhere.
"""

from __future__ import annotations

import asyncio
import logging
import time

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import RoosterWakeConfigEntry
from .api import (
    Machine,
    RoosterWakeError,
    RoosterWakeRateLimitError,
    WakeResult,
)
from .const import (
    CONF_CONFIRM_WAKES,
    CONF_MACHINES,
    CONFIRM_POLL_DEADLINE_S,
    CONFIRM_POLL_INTERVAL_S,
    DEFAULT_CONFIRM_WAKES,
    EVENT_WAKE_RESULT,
)
from .coordinator import RoosterWakeCoordinator
from .entity import RoosterWakeMachineEntity

_LOGGER = logging.getLogger(__name__)

POWER_ACTIONS = ("sleep", "restart", "shutdown")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RoosterWakeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """A wake button per selected machine; power buttons where they could work.

    Machines and agents are facts the coordinator refreshes, so entity creation follows
    it: a machine that appears server-side later, or grows an agent later, gets its
    entities on the next poll without a reload.
    """
    runtime = entry.runtime_data
    coordinator = runtime.coordinator
    created: set[str] = set()

    @callback
    def _sync_entities() -> None:
        data = coordinator.data
        if data is None:
            return
        new: list[ButtonEntity] = []
        for mac in entry.options.get(CONF_MACHINES, []):
            machine = data.machines.get(mac)
            if machine is None:
                continue
            if mac not in created:
                created.add(mac)
                new.append(RoosterWakeWakeButton(coordinator, entry, machine))
            power_key = f"{mac}:power"
            if (
                runtime.has_power_scope
                and machine.has_agent
                and power_key not in created
            ):
                created.add(power_key)
                new.extend(
                    RoosterWakePowerButton(coordinator, entry, machine, action)
                    for action in POWER_ACTIONS
                )
        if new:
            async_add_entities(new)

    _sync_entities()
    entry.async_on_unload(coordinator.async_add_listener(_sync_entities))


class RoosterWakeWakeButton(RoosterWakeMachineEntity, ButtonEntity):
    """Sends the magic packet through every online entitled emitter on the account."""

    _attr_translation_key = "wake"

    def __init__(
        self,
        coordinator: RoosterWakeCoordinator,
        entry: RoosterWakeConfigEntry,
        machine: Machine,
    ) -> None:
        super().__init__(coordinator, entry.entry_id, machine.name, machine.mac)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}:{machine.mac}:wake"

    async def async_press(self) -> None:
        """Wake the machine, tell automations what happened, surface failures."""
        confirm = self._entry.options.get(CONF_CONFIRM_WAKES, DEFAULT_CONFIRM_WAKES)
        client = self._entry.runtime_data.client
        try:
            result = await client.wake(self.mac, confirm=confirm)
        except RoosterWakeRateLimitError as err:
            self._entry.runtime_data.coordinator.note_rate_limit(err.retry_after)
            raise HomeAssistantError(
                f"Rooster Wake rate limited the request; try again in {err.retry_after} s"
            ) from err
        except RoosterWakeError as err:
            raise HomeAssistantError(f"Wake failed: {err}") from err

        self._fire_sent_event(result)

        if result.probe_started and result.id is not None:
            # The probe's outcome lands on the wake's history row — the service settles
            # it server-side even if nobody polls — and this collects it for automations.
            self._entry.async_create_background_task(
                self.hass,
                _collect_confirmation(
                    self._entry, self.machine_name, self.mac, result.id
                ),
                name=f"roosterwake confirm wake {result.id}",
            )

        if not result.ok:
            headline = (
                result.diagnosis.headline if result.diagnosis else result.err or "unknown"
            )
            if result.err == "rate_limited" and result.retry_after is not None:
                headline = f"{headline} Try again in {result.retry_after} s."
            raise HomeAssistantError(f"Wake did not go out: {headline}")

    def _fire_sent_event(self, result: WakeResult) -> None:
        self.hass.bus.async_fire(
            EVENT_WAKE_RESULT,
            {
                "entry_id": self._entry.entry_id,
                "phase": "sent",
                "machine": self.machine_name,
                "mac": self.mac,
                "wake_id": result.id,
                "ok": result.ok,
                "err": result.err,
                "sent": result.sent,
                "ifaces": result.ifaces,
                "attempted": result.attempted,
                "delivered_by": result.delivered_by_name,
                "latency_ms": result.latency_ms,
                "confirmation_started": result.probe_started,
                **(
                    {"retry_after": result.retry_after}
                    if result.retry_after is not None
                    else {}
                ),
                "diagnosis": {
                    "headline": result.diagnosis.headline if result.diagnosis else None,
                    "detail": result.diagnosis.detail if result.diagnosis else None,
                    "blame": result.diagnosis.blame if result.diagnosis else None,
                },
            },
        )


class RoosterWakePowerButton(RoosterWakeMachineEntity, ButtonEntity):
    """Sleep, restart or shut down, through the agent running ON the machine."""

    def __init__(
        self,
        coordinator: RoosterWakeCoordinator,
        entry: RoosterWakeConfigEntry,
        machine: Machine,
        action: str,
    ) -> None:
        super().__init__(coordinator, entry.entry_id, machine.name, machine.mac)
        self._entry = entry
        self._action = action
        self._attr_translation_key = action
        self._attr_unique_id = f"{entry.entry_id}:{machine.mac}:{action}"

    @property
    def available(self) -> bool:
        """Only offer the press while the service says it could be honoured.

        ``powerAllowed`` is the plan carrying power AND the machine's agent being
        connected right now — the same two facts the dashboard's buttons key off.
        Presentation, never enforcement: the funnel re-derives everything on POST.
        """
        if not super().available:
            return False
        data = self.coordinator.data
        machine = data.machines.get(self.mac) if data else None
        return machine is not None and machine.power_allowed

    async def async_press(self) -> None:
        client = self._entry.runtime_data.client
        try:
            result = await client.power(self.mac, self._action)
        except RoosterWakeRateLimitError as err:
            self._entry.runtime_data.coordinator.note_rate_limit(err.retry_after)
            raise HomeAssistantError(
                f"Rooster Wake rate limited the request; try again in {err.retry_after} s"
            ) from err
        except RoosterWakeError as err:
            raise HomeAssistantError(f"{self._action} failed: {err}") from err

        if not result.ok:
            headline = (
                result.diagnosis.headline if result.diagnosis else result.err or "unknown"
            )
            raise HomeAssistantError(f"The {self._action} was refused: {headline}")


async def _collect_confirmation(
    entry: RoosterWakeConfigEntry, machine_name: str, mac: str, wake_id: int
) -> None:
    """Poll GET /api/v1/wake/{id} until the probe settles, then tell automations.

    Modest cadence, a hard deadline (a probe runs at most 300 s and the service's sweep
    settles abandoned ones, so six minutes bounds every honest outcome), and full respect
    for the coordinator's rate-limit hold-off: while it holds, this waits without touching
    the network.
    """
    coordinator = entry.runtime_data.coordinator
    client = entry.runtime_data.client
    hass = coordinator.hass
    deadline = time.monotonic() + CONFIRM_POLL_DEADLINE_S

    while time.monotonic() < deadline:
        await asyncio.sleep(CONFIRM_POLL_INTERVAL_S)
        if coordinator.holding_off:
            continue
        try:
            row = await client.wake_entry(wake_id)
        except RoosterWakeRateLimitError as err:
            coordinator.note_rate_limit(err.retry_after)
            continue
        except RoosterWakeError as err:
            _LOGGER.debug("Confirmation poll for wake %s failed: %s", wake_id, err)
            continue

        if row is None:
            # The row is gone (retention, or another session's cleanup). Nothing left
            # to learn, and inventing an outcome would be worse than silence.
            _LOGGER.debug("Wake %s no longer exists; giving up on confirmation", wake_id)
            return

        if row.probe_terminal:
            hass.bus.async_fire(
                EVENT_WAKE_RESULT,
                {
                    "entry_id": entry.entry_id,
                    "phase": "confirmed",
                    "machine": machine_name,
                    "mac": mac,
                    "wake_id": wake_id,
                    "ok": row.ok,
                    "probe_state": row.probe_state,
                    "probe_ms": row.probe_ms,
                    "came_up": row.probe_state == "up",
                    "connect_url": row.connect_url,
                    "diagnosis": {
                        "headline": row.diagnosis.headline if row.diagnosis else None,
                        "detail": row.diagnosis.detail if row.diagnosis else None,
                        "blame": row.diagnosis.blame if row.diagnosis else None,
                    },
                },
            )
            # The presence sensor should learn "up" promptly rather than at the next
            # scheduled poll.
            await coordinator.async_request_refresh()
            return

    _LOGGER.debug("Gave up waiting for wake %s to confirm", wake_id)
