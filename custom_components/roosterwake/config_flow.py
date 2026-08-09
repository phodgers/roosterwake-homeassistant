"""Config flow: an API key, an instance URL, and which discovered machines to show.

The key IS the gate. Rooster Wake's free plan carries no API keys — keys exist on Plus and
Pro — so a refused key gets an error that says exactly that instead of a shrug.

Machines are DISCOVERED from ``GET /api/v1/machines`` and offered for selection. There is
deliberately no manual name+MAC entry: the server's list is the truth — the wake endpoint
only accepts saved machines anyway — and machines are added on the Rooster Wake dashboard,
not here. A machine added there later shows up in this integration's options.
"""

from __future__ import annotations

import hashlib
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_API_KEY
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    DEFAULT_BASE_URL,
    Machine,
    RoosterWakeAuthError,
    RoosterWakeClient,
    RoosterWakeConnectionError,
    RoosterWakeError,
    RoosterWakeScopeError,
)
from .const import (
    CONF_BASE_URL,
    CONF_CONFIRM_WAKES,
    CONF_MACHINES,
    DEFAULT_CONFIRM_WAKES,
    DOMAIN,
)


def _machine_choices(machines: list[Machine]) -> dict[str, str]:
    """MAC → label, for the selection form."""
    return {
        machine.mac: f"{machine.name} ({machine.mac})"
        + ("" if machine.active else " — past the plan's allowance")
        for machine in machines
    }


class RoosterWakeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up by instance URL and API key, then pick machines from the account."""

    VERSION = 1

    def __init__(self) -> None:
        self._base_url: str = DEFAULT_BASE_URL
        self._api_key: str = ""
        self._discovered: list[Machine] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect and validate the credentials with a real call."""
        errors: dict[str, str] = {}
        if user_input is not None:
            base_url = str(user_input[CONF_BASE_URL]).strip().rstrip("/")
            api_key = str(user_input[CONF_API_KEY]).strip()
            outcome = await self._try_credentials(base_url, api_key)
            if isinstance(outcome, dict):
                errors = outcome
            else:
                # One entry per key. Hashed: a unique id must be stable and comparable,
                # and the key itself has no business appearing anywhere but the header.
                await self.async_set_unique_id(_key_id(api_key))
                self._abort_if_unique_id_configured()
                self._base_url = base_url
                self._api_key = api_key
                self._discovered = outcome
                if not self._discovered:
                    # Nothing to wake. Machines are added on the dashboard; an entry
                    # with no machines would be a service card with nothing on it.
                    return self.async_abort(reason="no_machines")
                return await self.async_step_machines()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_BASE_URL, default=self._base_url): str,
                    vol.Required(CONF_API_KEY): str,
                }
            ),
            errors=errors,
        )

    async def async_step_machines(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose which of the account's machines appear in Home Assistant."""
        errors: dict[str, str] = {}
        choices = _machine_choices(self._discovered)
        if user_input is not None:
            selected = [mac for mac in user_input[CONF_MACHINES] if mac in choices]
            if not selected:
                errors[CONF_MACHINES] = "no_selection"
            else:
                return self.async_create_entry(
                    title="Rooster Wake",
                    data={
                        CONF_BASE_URL: self._base_url,
                        CONF_API_KEY: self._api_key,
                    },
                    options={
                        CONF_MACHINES: selected,
                        CONF_CONFIRM_WAKES: DEFAULT_CONFIRM_WAKES,
                    },
                )

        return self.async_show_form(
            step_id="machines",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_MACHINES, default=list(choices)
                    ): cv.multi_select(choices),
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """The stored key stopped working — collect a fresh one."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            api_key = str(user_input[CONF_API_KEY]).strip()
            outcome = await self._try_credentials(entry.data[CONF_BASE_URL], api_key)
            if isinstance(outcome, dict):
                errors = outcome
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data={**entry.data, CONF_API_KEY: api_key},
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): str}),
            errors=errors,
        )

    async def _try_credentials(
        self, base_url: str, api_key: str
    ) -> dict[str, str] | list[Machine]:
        """Prove the key against the live service.

        Returns the discovered machine list on success — the same call validates and
        discovers, so setup costs one request — or the form errors on failure.
        """
        if not base_url.startswith(("http://", "https://")):
            return {CONF_BASE_URL: "invalid_url"}
        client = RoosterWakeClient(
            session=async_get_clientsession(self.hass),
            base_url=base_url,
            api_key=api_key,
        )
        try:
            return await client.list_machines()
        except RoosterWakeAuthError:
            return {CONF_API_KEY: "invalid_auth"}
        except RoosterWakeScopeError:
            return {CONF_API_KEY: "missing_scope"}
        except (RoosterWakeConnectionError, RoosterWakeError):
            return {"base": "cannot_connect"}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> RoosterWakeOptionsFlow:
        return RoosterWakeOptionsFlow()


class RoosterWakeOptionsFlow(OptionsFlow):
    """Re-pick machines from the live account list, and settings."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(step_id="init", menu_options=["machines", "settings"])

    async def async_step_machines(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """The same discovery the setup flow ran, against the account as it is NOW."""
        errors: dict[str, str] = {}
        client = RoosterWakeClient(
            session=async_get_clientsession(self.hass),
            base_url=self.config_entry.data[CONF_BASE_URL],
            api_key=self.config_entry.data[CONF_API_KEY],
        )
        try:
            discovered = await client.list_machines()
        except RoosterWakeError:
            return self.async_abort(reason="cannot_connect")
        choices = _machine_choices(discovered)

        if user_input is not None:
            selected = [mac for mac in user_input[CONF_MACHINES] if mac in choices]
            if not selected:
                errors[CONF_MACHINES] = "no_selection"
            else:
                return self.async_create_entry(
                    data={**self.config_entry.options, CONF_MACHINES: selected}
                )

        current = [
            mac for mac in self.config_entry.options.get(CONF_MACHINES, []) if mac in choices
        ]
        return self.async_show_form(
            step_id="machines",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_MACHINES, default=current or list(choices)
                    ): cv.multi_select(choices),
                }
            ),
            errors=errors,
        )

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                data={
                    **self.config_entry.options,
                    CONF_CONFIRM_WAKES: user_input[CONF_CONFIRM_WAKES],
                }
            )
        return self.async_show_form(
            step_id="settings",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_CONFIRM_WAKES,
                        default=self.config_entry.options.get(
                            CONF_CONFIRM_WAKES, DEFAULT_CONFIRM_WAKES
                        ),
                    ): bool,
                }
            ),
        )


def _key_id(api_key: str) -> str:
    """A stable, non-secret identity for a key."""
    return hashlib.sha256(api_key.encode()).hexdigest()[:16]
