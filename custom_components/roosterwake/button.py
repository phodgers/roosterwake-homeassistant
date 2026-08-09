"""The Wake button — the entity this integration exists for.

There are deliberately NO sleep, restart or shutdown buttons. The product has power
actions (through its installed agent, on plans that carry them), but the public v1 API has
no power endpoint yet, and a button that always fails is worse than no button. They will
appear here the day the API can honour them.
"""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_call_later

from . import RoosterWakeConfigEntry
from .api import RoosterWakeError, RoosterWakeRateLimitError, WakeResult
from .const import (
    CONF_CONFIRM_WAKES,
    CONF_MACHINE_MAC,
    CONF_MACHINE_NAME,
    CONF_MACHINES,
    DEFAULT_CONFIRM_WAKES,
    EVENT_WAKE_RESULT,
)
from .entity import RoosterWakeMachineEntity

_LOGGER = logging.getLogger(__name__)

# After a confirmation probe starts, refresh once more shortly after its window closes, so
# the presence sensor picks the outcome up without tightening the ordinary poll.
PROBE_REFRESH_MARGIN_S = 20


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RoosterWakeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """One wake button per configured machine."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        RoosterWakeWakeButton(
            coordinator,
            entry,
            machine[CONF_MACHINE_NAME],
            machine[CONF_MACHINE_MAC],
        )
        for machine in entry.options.get(CONF_MACHINES, [])
    )


class RoosterWakeWakeButton(RoosterWakeMachineEntity, ButtonEntity):
    """Sends the magic packet through every online entitled emitter on the account."""

    _attr_translation_key = "wake"

    def __init__(
        self,
        coordinator,
        entry: RoosterWakeConfigEntry,
        name: str,
        mac: str,
    ) -> None:
        super().__init__(coordinator, entry.entry_id, name, mac)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}:{mac}:wake"

    async def async_press(self) -> None:
        """Wake the machine, tell automations what happened, surface failures."""
        confirm = self._entry.options.get(CONF_CONFIRM_WAKES, DEFAULT_CONFIRM_WAKES)
        client = self._entry.runtime_data.client
        try:
            result = await client.wake(self.mac, confirm=confirm)
        except RoosterWakeRateLimitError as err:
            raise HomeAssistantError(
                f"Rooster Wake rate limited the request; try again in {err.retry_after} s"
            ) from err
        except RoosterWakeError as err:
            raise HomeAssistantError(f"Wake failed: {err}") from err

        self._fire_event(result)

        if result.probe_started and result.probe_timeout_s:
            # The service's probe outcome lands in the wake history; one extra refresh
            # after the window closes is how the presence sensor learns it promptly.
            async_call_later(
                self.hass,
                result.probe_timeout_s + PROBE_REFRESH_MARGIN_S,
                self._refresh_after_probe,
            )

        if not result.ok:
            headline = (
                result.diagnosis.headline if result.diagnosis else result.err or "unknown"
            )
            raise HomeAssistantError(f"Wake did not go out: {headline}")

    def _fire_event(self, result: WakeResult) -> None:
        self.hass.bus.async_fire(
            EVENT_WAKE_RESULT,
            {
                "entry_id": self._entry.entry_id,
                "machine": self.machine_name,
                "mac": self.mac,
                "ok": result.ok,
                "err": result.err,
                "sent": result.sent,
                "ifaces": result.ifaces,
                "attempted": result.attempted,
                "delivered_by": result.delivered_by_name,
                "latency_ms": result.latency_ms,
                "confirmation_started": result.probe_started,
                "diagnosis": {
                    "headline": result.diagnosis.headline if result.diagnosis else None,
                    "detail": result.diagnosis.detail if result.diagnosis else None,
                    "blame": result.diagnosis.blame if result.diagnosis else None,
                },
            },
        )

    async def _refresh_after_probe(self, _now) -> None:
        await self.coordinator.async_request_refresh()
