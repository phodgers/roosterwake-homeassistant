"""Shared entity bases: one device per configured machine, plus one for the account.

Word mark only throughout — the brand appears as the words "Rooster Wake", never as
artwork, matching the trademark policy of the open firmware repository.
"""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import RoosterWakeCoordinator


def account_device_info(entry_id: str) -> DeviceInfo:
    """The service-level device the emitter sensor hangs off."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry_id}:account")},
        name="Rooster Wake",
        manufacturer="Rooster Wake",
        model="Cloud account",
        entry_type=DeviceEntryType.SERVICE,
    )


def machine_device_info(entry_id: str, name: str, mac: str) -> DeviceInfo:
    """One device per Rooster Wake machine."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry_id}:machine:{mac}")},
        name=name,
        manufacturer="Rooster Wake",
        model="Wakeable machine",
        via_device=(DOMAIN, f"{entry_id}:account"),
    )


class RoosterWakeMachineEntity(CoordinatorEntity[RoosterWakeCoordinator]):
    """Base for entities that belong to one configured machine."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: RoosterWakeCoordinator,
        entry_id: str,
        name: str,
        mac: str,
    ) -> None:
        super().__init__(coordinator)
        self.machine_name = name
        self.mac = mac
        self._attr_device_info = machine_device_info(entry_id, name, mac)
