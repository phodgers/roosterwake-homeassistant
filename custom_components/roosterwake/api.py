"""A thin client over the Rooster Wake public v1 REST API.

The whole surface, as of this writing, is three endpoints:

    GET  /api/v1/devices                — the account's emitters (scope: read)
    POST /api/v1/wake                   — wake a saved machine by MAC (scope: wake)
    GET  /api/v1/devices/{id}/history   — recent wake attempts per emitter (scope: read)

Everything this integration shows is built from those three and nothing else. Where the
product knows more than the API exposes (which machine carries an agent, live machine
presence, power actions), this client does not guess — the integration degrades honestly
instead.

The API's contract, preserved here deliberately: a wake answers HTTP 200 with ``ok: false``
for a device-level failure. The request succeeded; the answer is "it did not work, and here
is why". Only transport, authentication and scope problems raise.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import aiohttp

DEFAULT_BASE_URL = "https://app.roosterwake.com"
REQUEST_TIMEOUT_S = 30

# The key prefix the service mints. Checked only to catch obvious paste accidents early —
# the server remains the authority on what a valid key is.
KEY_PREFIX = "rw_live_"


class RoosterWakeError(Exception):
    """Base class for every error this client raises."""


class RoosterWakeConnectionError(RoosterWakeError):
    """The service could not be reached, or answered with a server error."""


class RoosterWakeAuthError(RoosterWakeError):
    """The API key was refused (unknown, revoked or expired — the API does not say which)."""


class RoosterWakeScopeError(RoosterWakeError):
    """The key is valid but does not carry the permission this call needs."""


class RoosterWakeRateLimitError(RoosterWakeError):
    """The service answered 429. Carries when to come back."""

    def __init__(self, retry_after: int) -> None:
        super().__init__(f"Rate limited; retry after {retry_after} seconds")
        self.retry_after = retry_after


@dataclass(slots=True)
class Emitter:
    """One row of GET /api/v1/devices — a dongle or software agent on the account."""

    device_id: str
    name: str | None
    online: bool
    last_seen: int | None
    board: str | None
    fw: str | None
    permission: str | None

    @classmethod
    def from_json(cls, row: dict[str, Any]) -> Emitter:
        return cls(
            device_id=str(row.get("deviceId", "")),
            name=row.get("name"),
            online=row.get("online") is True,
            last_seen=_opt_int(row.get("lastSeen")),
            board=row.get("board"),
            fw=row.get("fw"),
            permission=row.get("permission"),
        )


@dataclass(slots=True)
class Diagnosis:
    """The API's plain-English explanation of an outcome."""

    headline: str
    detail: str
    blame: str | None

    @classmethod
    def from_json(cls, data: dict[str, Any] | None) -> Diagnosis | None:
        if not isinstance(data, dict):
            return None
        return cls(
            headline=str(data.get("headline", "")),
            detail=str(data.get("detail", "")),
            blame=data.get("blame"),
        )


@dataclass(slots=True)
class WakeResult:
    """The answer to POST /api/v1/wake.

    ``ok`` means the packet left an emitter — Wake-on-LAN is fire-and-forget, so it never
    means the machine came up. ``probe_started`` says whether the service began a
    confirmation probe; its outcome lands in the wake history later, not here.
    """

    ok: bool
    err: str | None
    sent: int
    ifaces: list[str]
    target_name: str | None
    target_mac: str | None
    delivered_by_id: str | None
    delivered_by_name: str | None
    attempted: int
    latency_ms: int | None
    diagnosis: Diagnosis | None
    probe_started: bool
    probe_timeout_s: int | None

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> WakeResult:
        target = data.get("target") or {}
        delivered = data.get("deliveredBy") or {}
        probe = data.get("probe") or {}
        return cls(
            ok=data.get("ok") is True,
            err=data.get("err"),
            sent=_opt_int(data.get("sent")) or 0,
            ifaces=[i for i in data.get("ifaces") or [] if isinstance(i, str)],
            target_name=target.get("name"),
            target_mac=target.get("mac"),
            delivered_by_id=delivered.get("deviceId"),
            delivered_by_name=delivered.get("name"),
            attempted=_opt_int(data.get("attempted")) or 0,
            latency_ms=_opt_int(data.get("latencyMs")),
            diagnosis=Diagnosis.from_json(data.get("diagnosis")),
            probe_started=probe.get("started") is True,
            probe_timeout_s=_opt_int(probe.get("timeoutSeconds")),
        )


@dataclass(slots=True)
class HistoryEntry:
    """One row of GET /api/v1/devices/{id}/history.

    ``action`` is ``wake``, ``sleep``, ``restart`` or ``shutdown`` — the log carries power
    actions too, and those rows are what lets us infer a last-known "down". ``probe_state``
    is the wake-confirmation outcome (``up`` / ``timeout`` / ``waiting`` / None), written by
    the service's own sweep, so it arrives even when nobody kept a browser open.
    """

    id: int
    at: int
    action: str
    ok: bool
    err: str | None
    target_mac: str | None
    target_name: str | None
    source: str | None
    probe_state: str | None
    probe_ms: int | None

    @classmethod
    def from_json(cls, row: dict[str, Any]) -> HistoryEntry:
        return cls(
            id=_opt_int(row.get("id")) or 0,
            at=_opt_int(row.get("at")) or 0,
            action=str(row.get("action") or "wake"),
            ok=row.get("ok") is True,
            err=row.get("err"),
            target_mac=row.get("targetMac"),
            target_name=row.get("targetName"),
            source=row.get("source"),
            probe_state=row.get("probeState"),
            probe_ms=_opt_int(row.get("probeMs")),
        )


@dataclass(slots=True)
class RoosterWakeClient:
    """The client. Holds a session it does not own — Home Assistant's, shared."""

    session: aiohttp.ClientSession
    base_url: str = DEFAULT_BASE_URL
    api_key: str = ""
    _headers: dict[str, str] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        self.base_url = self.base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {self.api_key}"}

    async def list_devices(self) -> list[Emitter]:
        """The account's emitters. Also the cheapest call that proves a key works."""
        data = await self._request("GET", "/api/v1/devices")
        return [Emitter.from_json(row) for row in data.get("devices") or []]

    async def wake(
        self, mac: str, *, confirm: bool = False, repeat: int | None = None
    ) -> WakeResult:
        """Wake a saved machine by MAC.

        The MAC must name one of the account's saved machines — the API refuses addresses
        that are not on the list (``unknown_target``), and that refusal comes back as a
        normal ``ok: false`` result, not an exception.
        """
        body: dict[str, Any] = {"mac": mac}
        if confirm:
            body["confirm"] = True
        if repeat is not None:
            body["repeat"] = repeat
        data = await self._request("POST", "/api/v1/wake", json=body)
        return WakeResult.from_json(data)

    async def device_history(
        self, device_id: str, *, limit: int = 25
    ) -> list[HistoryEntry]:
        """Recent wake and power attempts delivered by one emitter, newest first."""
        data = await self._request(
            "GET", f"/api/v1/devices/{device_id}/history", params={"limit": str(limit)}
        )
        return [HistoryEntry.from_json(row) for row in data.get("entries") or []]

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT_S):
                response = await self.session.request(
                    method, url, headers=self._headers, json=json, params=params
                )
                if response.status == 401:
                    raise RoosterWakeAuthError("The API key was refused")
                if response.status == 403:
                    raise RoosterWakeScopeError(
                        "The API key does not carry the permission this call needs"
                    )
                if response.status == 429:
                    raise RoosterWakeRateLimitError(
                        _retry_after(response.headers.get("Retry-After"))
                    )
                if response.status >= 500:
                    raise RoosterWakeConnectionError(
                        f"The service answered {response.status}"
                    )
                if response.status >= 400:
                    detail = await _error_detail(response)
                    raise RoosterWakeError(
                        f"The service refused the request ({response.status}): {detail}"
                    )
                payload = await response.json()
        except TimeoutError as err:
            raise RoosterWakeConnectionError("Timed out talking to the service") from err
        except aiohttp.ClientError as err:
            raise RoosterWakeConnectionError(str(err)) from err
        if not isinstance(payload, dict):
            raise RoosterWakeConnectionError("The service answered with a non-object body")
        return payload


async def _error_detail(response: aiohttp.ClientResponse) -> str:
    try:
        body = await response.json()
    except (aiohttp.ClientError, ValueError):
        return "no detail"
    if isinstance(body, dict):
        return str(body.get("message") or body.get("error") or "no detail")
    return "no detail"


def _retry_after(header: str | None) -> int:
    """Seconds to hold off, from a Retry-After header that may be absent or non-numeric."""
    try:
        value = int(header or "")
    except ValueError:
        return 60
    return max(1, value)


def _opt_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None
