"""Presence, told honestly — now straight from the service's own verdict.

Two kinds of sensor:

  - Per machine: the machines list's ``presence`` object. ``live: true`` is
    agent-connected truth — for an agent-carried machine, the agent's open connection IS
    the machine being up. ``live: false`` with a state is LAST-KNOWN, timestamped: the
    newest thing the wake log proves (a probe-confirmed wake, or an accepted sleep or
    shutdown). ``unknown`` claims nothing, and the sensor says ``unknown`` too.

  - Per account: whether any emitter (dongle or agent) is connected to the relay right
    now — the honest proxy for "will pressing Wake do anything at all".
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import RoosterWakeConfigEntry
from .api import Machine, MachinePresenceInfo
from .const import CONF_MACHINES
from .coordinator import RoosterWakeCoordinator
from .entity import RoosterWakeMachineEntity, account_device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RoosterWakeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """A presence sensor per selected machine, one emitter sensor for the account."""
    coordinator = entry.runtime_data.coordinator
    created: set[str] = set()

    @callback
    def _sync_entities() -> None:
        data = coordinator.data
        if data is None:
            return
        new: list[BinarySensorEntity] = []
        for mac in entry.options.get(CONF_MACHINES, []):
            machine = data.machines.get(mac)
            if machine is None or mac in created:
                continue
            created.add(mac)
            new.append(RoosterWakeMachinePresenceSensor(coordinator, entry, machine))
        if new:
            async_add_entities(new)

    async_add_entities([RoosterWakeEmitterOnlineSensor(coordinator, entry)])
    _sync_entities()
    entry.async_on_unload(coordinator.async_add_listener(_sync_entities))


class RoosterWakeMachinePresenceSensor(RoosterWakeMachineEntity, BinarySensorEntity):
    """The service's presence verdict: live where an agent answers, last-known otherwise."""

    _attr_translation_key = "presence"

    def __init__(
        self,
        coordinator: RoosterWakeCoordinator,
        entry: RoosterWakeConfigEntry,
        machine: Machine,
    ) -> None:
        super().__init__(coordinator, entry.entry_id, machine.name, machine.mac)
        self._attr_unique_id = f"{entry.entry_id}:{machine.mac}:presence"

    @property
    def _machine(self) -> Machine | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.machines.get(self.mac)

    @property
    def _presence(self) -> MachinePresenceInfo | None:
        machine = self._machine
        return machine.presence if machine else None

    @property
    def is_on(self) -> bool | None:
        presence = self._presence
        if presence is None or presence.state == "unknown":
            # Honest: nothing is proved either way right now.
            return None
        return presence.state == "up"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        presence = self._presence
        machine = self._machine
        attributes: dict[str, Any] = {"mac": self.mac}
        if presence is None:
            return attributes
        attributes["live"] = presence.live
        attributes["kind"] = (
            "live"
            if presence.live
            else "last_known"
            if presence.state != "unknown"
            else "unknown"
        )
        if presence.at is not None:
            attributes["at"] = datetime.fromtimestamp(
                presence.at, tz=timezone.utc
            ).isoformat()
        if machine is not None:
            if machine.site is not None:
                attributes["site"] = machine.site
            if machine.sighting is not None:
                # G4.5's dated segment fact: what a user-triggered scan proved, when.
                attributes["last_sighting"] = machine.sighting
        return attributes


class RoosterWakeEmitterOnlineSensor(
    CoordinatorEntity[RoosterWakeCoordinator], BinarySensorEntity
):
    """Is anything connected that could carry a wake packet right now?"""

    _attr_has_entity_name = True
    _attr_translation_key = "emitter_online"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(
        self, coordinator: RoosterWakeCoordinator, entry: RoosterWakeConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}:emitter_online"
        self._attr_device_info = account_device_info(entry.entry_id)

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.any_emitter_online

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if self.coordinator.data is None:
            return {}
        return {
            "emitters": [
                {
                    "name": emitter.name,
                    "online": emitter.online,
                    "board": emitter.board,
                    "fw": emitter.fw,
                }
                for emitter in self.coordinator.data.emitters
            ]
        }
