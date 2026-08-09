"""Presence, told honestly.

Two kinds of sensor:

  - Per machine: LAST-KNOWN presence derived from the account's wake and power history —
    a confirmed wake proves "up" at that moment, an accepted sleep or shutdown proves
    "down" at that moment, and anything else is ``unknown``. The API does not report live
    machine state, so neither does this sensor; its attributes say when and how the last
    fact was established.

  - Per account: whether any emitter (dongle or agent) is connected to the relay right
    now. This one IS live — it is the relay's own presence record — and it is the honest
    proxy for "will pressing Wake do anything at all".
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import RoosterWakeConfigEntry
from .const import CONF_MACHINE_MAC, CONF_MACHINE_NAME, CONF_MACHINES
from .coordinator import MachinePresence, RoosterWakeCoordinator
from .entity import RoosterWakeMachineEntity, account_device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RoosterWakeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """A presence sensor per machine, one emitter sensor for the account."""
    coordinator = entry.runtime_data.coordinator
    entities: list[BinarySensorEntity] = [
        RoosterWakeMachinePresenceSensor(
            coordinator,
            entry,
            machine[CONF_MACHINE_NAME],
            machine[CONF_MACHINE_MAC],
        )
        for machine in entry.options.get(CONF_MACHINES, [])
    ]
    entities.append(RoosterWakeEmitterOnlineSensor(coordinator, entry))
    async_add_entities(entities)


class RoosterWakeMachinePresenceSensor(RoosterWakeMachineEntity, BinarySensorEntity):
    """Last-known machine state. ``unknown`` whenever the history proves nothing."""

    _attr_translation_key = "presence"

    def __init__(
        self,
        coordinator: RoosterWakeCoordinator,
        entry: RoosterWakeConfigEntry,
        name: str,
        mac: str,
    ) -> None:
        super().__init__(coordinator, entry.entry_id, name, mac)
        self._attr_unique_id = f"{entry.entry_id}:{mac}:presence"

    @property
    def _presence(self) -> MachinePresence | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.presence.get(self.mac)

    @property
    def is_on(self) -> bool | None:
        presence = self._presence
        if presence is None or presence.state == "unknown":
            # Honest: the history proves nothing either way right now.
            return None
        return presence.state == "up"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        presence = self._presence
        attributes: dict[str, Any] = {
            "kind": "last_known",
            "mac": self.mac,
        }
        if presence and presence.since:
            attributes["since"] = datetime.fromtimestamp(
                presence.since, tz=timezone.utc
            ).isoformat()
        if presence and presence.derived_from:
            attributes["derived_from"] = presence.derived_from
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
