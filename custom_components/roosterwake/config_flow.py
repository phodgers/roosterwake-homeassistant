"""Config flow: an API key, an instance URL, and the machines to show.

The key IS the gate. Rooster Wake's free plan carries no API keys — keys exist on Plus and
Pro — so a refused key gets an error that says exactly that instead of a shrug.

Machines are entered by hand (name + MAC) because the public v1 API has no machine-list
endpoint yet: a wake names a MAC that must already be one of the account's saved machines,
but nothing lets a client enumerate them. The moment the API grows one, this flow should
switch to discovery. Until then, honesty over invention.
"""

from __future__ import annotations

import hashlib
import re
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
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    DEFAULT_BASE_URL,
    RoosterWakeAuthError,
    RoosterWakeClient,
    RoosterWakeConnectionError,
    RoosterWakeError,
    RoosterWakeScopeError,
)
from .const import (
    CONF_BASE_URL,
    CONF_CONFIRM_WAKES,
    CONF_MACHINE_MAC,
    CONF_MACHINE_NAME,
    CONF_MACHINES,
    DEFAULT_CONFIRM_WAKES,
    DOMAIN,
)

MAC_SEPARATORS = re.compile(r"[:\-. ]")


def normalise_mac(value: str) -> str | None:
    """AA:BB:CC:DD:EE:FF from any common spelling, or None.

    The same rules the service applies (its shared/mac.js): twelve hex digits however
    separated, refusing broadcast, all-zero and multicast/group addresses — a group is not
    an interface, so no machine can be woken by naming one.
    """
    hexdigits = MAC_SEPARATORS.sub("", value.strip())
    if not re.fullmatch(r"[0-9a-fA-F]{12}", hexdigits):
        return None
    mac = ":".join(hexdigits[i : i + 2] for i in range(0, 12, 2)).upper()
    octets = [int(pair, 16) for pair in mac.split(":")]
    if all(octet == 0xFF for octet in octets):
        return None
    if all(octet == 0x00 for octet in octets):
        return None
    if octets[0] & 0x01:
        return None
    return mac


class RoosterWakeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up by instance URL and API key, then name the first machine."""

    VERSION = 1

    def __init__(self) -> None:
        self._base_url: str = DEFAULT_BASE_URL
        self._api_key: str = ""
        self._machines: list[dict[str, str]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect and validate the credentials with a real call."""
        errors: dict[str, str] = {}
        if user_input is not None:
            base_url = str(user_input[CONF_BASE_URL]).strip().rstrip("/")
            api_key = str(user_input[CONF_API_KEY]).strip()
            errors = await self._try_credentials(base_url, api_key)
            if not errors:
                # One entry per key. Hashed: a unique id must be stable and comparable,
                # and the key itself has no business appearing anywhere but the header.
                await self.async_set_unique_id(_key_id(api_key))
                self._abort_if_unique_id_configured()
                self._base_url = base_url
                self._api_key = api_key
                return await self.async_step_machine()

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

    async def async_step_machine(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a machine by name and MAC; repeat while asked to."""
        errors: dict[str, str] = {}
        if user_input is not None:
            mac = normalise_mac(str(user_input[CONF_MACHINE_MAC]))
            name = str(user_input[CONF_MACHINE_NAME]).strip()
            if mac is None:
                errors[CONF_MACHINE_MAC] = "invalid_mac"
            elif any(machine[CONF_MACHINE_MAC] == mac for machine in self._machines):
                errors[CONF_MACHINE_MAC] = "duplicate_mac"
            elif not name:
                errors[CONF_MACHINE_NAME] = "invalid_name"
            else:
                self._machines.append(
                    {CONF_MACHINE_NAME: name, CONF_MACHINE_MAC: mac}
                )
                if user_input.get("add_another"):
                    return await self.async_step_machine()
                return self.async_create_entry(
                    title="Rooster Wake",
                    data={
                        CONF_BASE_URL: self._base_url,
                        CONF_API_KEY: self._api_key,
                    },
                    options={
                        CONF_MACHINES: self._machines,
                        CONF_CONFIRM_WAKES: DEFAULT_CONFIRM_WAKES,
                    },
                )

        return self.async_show_form(
            step_id="machine",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_MACHINE_NAME): str,
                    vol.Required(CONF_MACHINE_MAC): str,
                    vol.Optional("add_another", default=False): bool,
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
            errors = await self._try_credentials(entry.data[CONF_BASE_URL], api_key)
            if not errors:
                return self.async_update_reload_and_abort(
                    entry,
                    data={**entry.data, CONF_API_KEY: api_key},
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): str}),
            errors=errors,
        )

    async def _try_credentials(self, base_url: str, api_key: str) -> dict[str, str]:
        """Prove the key against the live service. Empty dict means it worked."""
        if not base_url.startswith(("http://", "https://")):
            return {CONF_BASE_URL: "invalid_url"}
        client = RoosterWakeClient(
            session=async_get_clientsession(self.hass),
            base_url=base_url,
            api_key=api_key,
        )
        try:
            await client.list_devices()
        except RoosterWakeAuthError:
            return {CONF_API_KEY: "invalid_auth"}
        except RoosterWakeScopeError:
            return {CONF_API_KEY: "missing_scope"}
        except (RoosterWakeConnectionError, RoosterWakeError):
            return {"base": "cannot_connect"}
        return {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> RoosterWakeOptionsFlow:
        return RoosterWakeOptionsFlow()


class RoosterWakeOptionsFlow(OptionsFlow):
    """Manage the machine list and the confirm-wakes setting after setup."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        menu = ["add_machine", "settings"]
        if self.config_entry.options.get(CONF_MACHINES):
            menu.insert(1, "remove_machine")
        return self.async_show_menu(step_id="init", menu_options=menu)

    async def async_step_add_machine(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        machines = list(self.config_entry.options.get(CONF_MACHINES, []))
        if user_input is not None:
            mac = normalise_mac(str(user_input[CONF_MACHINE_MAC]))
            name = str(user_input[CONF_MACHINE_NAME]).strip()
            if mac is None:
                errors[CONF_MACHINE_MAC] = "invalid_mac"
            elif any(machine[CONF_MACHINE_MAC] == mac for machine in machines):
                errors[CONF_MACHINE_MAC] = "duplicate_mac"
            elif not name:
                errors[CONF_MACHINE_NAME] = "invalid_name"
            else:
                machines.append({CONF_MACHINE_NAME: name, CONF_MACHINE_MAC: mac})
                return self.async_create_entry(
                    data={**self.config_entry.options, CONF_MACHINES: machines}
                )
        return self.async_show_form(
            step_id="add_machine",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_MACHINE_NAME): str,
                    vol.Required(CONF_MACHINE_MAC): str,
                }
            ),
            errors=errors,
        )

    async def async_step_remove_machine(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        machines = list(self.config_entry.options.get(CONF_MACHINES, []))
        if user_input is not None:
            keep = [
                machine
                for machine in machines
                if machine[CONF_MACHINE_MAC] not in user_input["macs"]
            ]
            return self.async_create_entry(
                data={**self.config_entry.options, CONF_MACHINES: keep}
            )
        return self.async_show_form(
            step_id="remove_machine",
            data_schema=vol.Schema(
                {
                    vol.Required("macs", default=[]): vol.All(
                        [
                            vol.In(
                                {
                                    machine[CONF_MACHINE_MAC]: (
                                        f"{machine[CONF_MACHINE_NAME]}"
                                        f" ({machine[CONF_MACHINE_MAC]})"
                                    )
                                    for machine in machines
                                }
                            )
                        ]
                    )
                }
            ),
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
