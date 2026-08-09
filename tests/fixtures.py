"""Captured response shapes from the Rooster Wake public v1 API.

These dictionaries mirror, field for field, what the live endpoints return — the shapes
were taken from the service's own endpoint code, not invented. MAC addresses are RFC 7042
documentation addresses (00:00:5E:00:53:xx) throughout.

The scenario the fixtures paint, kept coherent across endpoints:

  - Office PC — agent installed and CONNECTED: presence is live truth, power allowed.
  - Study PC  — agent installed but disconnected: presence is dated last-known (an
                accepted sleep), power not allowed right now.
  - Loft PC   — no agent at all: presence unknown, never offered power.
"""

from __future__ import annotations

BASE_URL = "https://app.roosterwake.com"
API_KEY = "rw_live_TESTKEYTESTKEYTESTKEYTESTKEYTESTKEYTESTKEY"

DEVICE_ID = "rw-24a1"
AGENT_OFFICE_ID = "rw-agent-01"
AGENT_STUDY_ID = "rw-agent-02"

MAC_OFFICE = "00:00:5E:00:53:0A"
MAC_STUDY = "00:00:5E:00:53:0B"
MAC_LOFT = "00:00:5E:00:53:0C"

# GET /api/v1/devices — scope `read`. Exactly the fields the endpoint maps.
DEVICES_OK = {
    "devices": [
        {
            "deviceId": DEVICE_ID,
            "name": "Hallway dongle",
            "online": True,
            "lastSeen": 1754700000,
            "board": "pico2w",
            "fw": "1.9.0",
            "permission": "owner",
        },
        {
            "deviceId": AGENT_OFFICE_ID,
            "name": "Office PC agent",
            "online": True,
            "lastSeen": 1754700010,
            "board": "agent",
            "fw": "0.2.0",
            "permission": "owner",
        },
        {
            "deviceId": AGENT_STUDY_ID,
            "name": "Study PC agent",
            "online": False,
            "lastSeen": 1754600000,
            "board": "agent",
            "fw": "0.2.0",
            "permission": "owner",
        },
    ]
}

DEVICES_NONE_ONLINE = {
    "devices": [
        {
            "deviceId": DEVICE_ID,
            "name": "Hallway dongle",
            "online": False,
            "lastSeen": 1754600000,
            "board": "pico2w",
            "fw": "1.9.0",
            "permission": "owner",
        }
    ]
}

# GET /api/v1/machines — scope `read`. The dashboard's own facts, per machines.js:
# agent is {connected} or null, powerAllowed needs the plan AND a connected agent,
# presence is always an object, sighting is positive evidence only.
MACHINES_OK = {
    "machines": [
        {
            "id": 3,
            "name": "Office PC",
            "mac": MAC_OFFICE,
            "site": "Home",
            "active": True,
            "agent": {"connected": True},
            "powerAllowed": True,
            "presence": {"state": "up", "at": None, "live": True},
            "sighting": {
                "deviceName": "Hallway dongle",
                "segment": "192.168.1.x",
                "seenAt": 1754650000,
            },
            "connectUrl": "rdp://office-pc",
        },
        {
            "id": 4,
            "name": "Study PC",
            "mac": MAC_STUDY,
            "site": "Home",
            "active": True,
            "agent": {"connected": False},
            "powerAllowed": False,
            "presence": {"state": "down", "at": 1754700400, "live": False},
            "sighting": None,
            "connectUrl": None,
        },
        {
            "id": 5,
            "name": "Loft PC",
            "mac": MAC_LOFT,
            "site": None,
            "active": True,
            "agent": None,
            "powerAllowed": False,
            "presence": {"state": "unknown", "at": None, "live": False},
            "sighting": None,
            "connectUrl": None,
        },
    ]
}

MACHINES_EMPTY = {"machines": []}

# The same list after the Loft PC gains a connected agent — the dynamic-appearance case.
MACHINES_LOFT_GREW_AGENT = {
    "machines": [
        MACHINES_OK["machines"][0],
        MACHINES_OK["machines"][1],
        {
            **MACHINES_OK["machines"][2],
            "agent": {"connected": True},
            "powerAllowed": True,
            "presence": {"state": "up", "at": None, "live": True},
        },
    ]
}

# POST /api/v1/wake — success, with a confirmation probe started. `id` is the wake_log
# row, the handle GET /api/v1/wake/{id} polls.
WAKE_OK = {
    "ok": True,
    "err": None,
    "id": 203,
    "sent": 12,
    "ifaces": ["192.168.1.255:9", "192.168.1.255:7", "255.255.255.255:9"],
    "target": {"id": 3, "name": "Office PC", "mac": MAC_OFFICE},
    "deliveredBy": {"deviceId": DEVICE_ID, "name": "Hallway dongle"},
    "attempted": 1,
    "latencyMs": 480,
    "diagnosis": {
        "blame": None,
        "headline": "Sent 12 packets.",
        "detail": (
            "They went to the 192.168.1.x network, on ports 9 and 7. Wake-on-LAN packets "
            "are not acknowledged by anything, so this confirms they left the dongle and "
            "not that the machine received them."
        ),
    },
    "probe": {
        "started": True,
        "probes": [{"deviceId": DEVICE_ID, "reqId": "p-0001"}],
        "timeoutSeconds": 90,
    },
}

# The same wake without confirmation asked for.
WAKE_OK_NO_PROBE = {**WAKE_OK, "id": 204, "probe": None}

# POST /api/v1/wake — HTTP 200 with ok:false; the account owns no connected emitter.
WAKE_OFFLINE = {
    "ok": False,
    "err": "offline",
    "id": 205,
    "sent": 0,
    "ifaces": [],
    "target": {"id": 3, "name": "Office PC", "mac": MAC_OFFICE},
    "deliveredBy": None,
    "attempted": 0,
    "latencyMs": None,
    "diagnosis": {
        "blame": "device",
        "headline": "None of your dongles are connected.",
        "detail": (
            "Nothing was sent — no connected dongle was there to send it. Check the dongle "
            "is powered and shows a connection; if it is powered but not connecting, its "
            "Wi-Fi details may have changed."
        ),
    },
    "probe": None,
}

# POST /api/v1/wake — 200 ok:false from the relay's wake budget, with `retryAfter`
# carried in the body (deliberately not a 429: the request itself succeeded).
WAKE_RATE_LIMITED = {
    "ok": False,
    "err": "rate_limited",
    "id": 206,
    "sent": 0,
    "ifaces": [],
    "target": {"id": 3, "name": "Office PC", "mac": MAC_OFFICE},
    "deliveredBy": None,
    "attempted": 1,
    "latencyMs": 120,
    "diagnosis": {
        "blame": "us",
        "headline": "Too many wakes in a short time.",
        "detail": "Wakes are capped at 30 a minute per dongle to protect the network. Wait a moment.",
    },
    "probe": None,
    "retryAfter": 42,
}

# One historyRow, the shape shared by /devices/{id}/history entries, /activity rows and
# GET /wake/{id}'s `entry`.
_WAKE_ROW_BASE = {
    "id": 203,
    "at": 1754700300,
    "deviceId": DEVICE_ID,
    "targetName": "Office PC",
    "targetMac": MAC_OFFICE,
    "requestedBy": "someone@example.com",
    "source": "api",
    "via": "dongle",
    "linkLabel": None,
    "action": "wake",
    "ok": True,
    "err": None,
    "sent": 12,
    "ifaces": ["192.168.1.255:9", "192.168.1.255:7"],
    "latencyMs": 480,
    "connectUrl": None,
    "diagnosis": {
        "blame": None,
        "headline": "Sent 12 packets.",
        "detail": "They went to the 192.168.1.x network, on ports 9 and 7.",
    },
}

# GET /api/v1/wake/{id} — the probe still running, then settled. The connect handoff
# (connectUrl) rides only on CONFIRMED rows, exactly as the service builds them.
WAKE_ENTRY_WAITING = {
    "entry": {**_WAKE_ROW_BASE, "probeState": "waiting", "probeMs": None}
}
WAKE_ENTRY_UP = {
    "entry": {
        **_WAKE_ROW_BASE,
        "probeState": "up",
        "probeMs": 23000,
        "connectUrl": "rdp://office-pc",
    }
}
WAKE_ENTRY_TIMEOUT = {
    "entry": {**_WAKE_ROW_BASE, "probeState": "timeout", "probeMs": None}
}

# GET /api/v1/devices/{id}/history — scope `read`, cursor paged.
HISTORY_OK = {
    "entries": [
        {
            **_WAKE_ROW_BASE,
            "id": 204,
            "at": 1754700400,
            "deviceId": AGENT_STUDY_ID,
            "targetName": "Study PC",
            "targetMac": MAC_STUDY,
            "source": "dashboard",
            "action": "sleep",
            "sent": 0,
            "ifaces": [],
            "latencyMs": 210,
            "probeState": None,
            "probeMs": None,
            "diagnosis": {
                "blame": None,
                "headline": 'Accepted — "Study PC" is going to sleep.',
                "detail": "The agent accepted the command.",
            },
        },
        {**_WAKE_ROW_BASE, "probeState": "up", "probeMs": 23000},
        {
            **_WAKE_ROW_BASE,
            "id": 201,
            "at": 1754700100,
            "targetName": "Loft PC",
            "targetMac": MAC_LOFT,
            "probeState": None,
            "probeMs": None,
        },
    ],
    "nextBefore": 201,
}

HISTORY_EMPTY = {"entries": [], "nextBefore": None}

# POST /api/v1/power — accepted (never "done": the acknowledgement precedes the action,
# because the action destroys the process that would confirm it).
POWER_ACCEPTED = {
    "ok": True,
    "err": None,
    "id": 501,
    "logged": True,
    "action": "sleep",
    "target": {"id": 3, "name": "Office PC", "mac": MAC_OFFICE},
    "latencyMs": 210,
    "agent": {"deviceId": AGENT_OFFICE_ID, "name": "Office PC agent"},
    "diagnosis": {
        "blame": None,
        "headline": 'Accepted — "Office PC" is going to sleep.',
        "detail": "The agent on the machine took the order. Its connection dropping is the only confirmation there ever is.",
    },
}

# POST /api/v1/power — the funnel's refusal, as a 200 with ok:false.
POWER_REFUSED_NO_AGENT = {
    "ok": False,
    "err": "no_agent",
    "id": 502,
    "logged": True,
    "action": "sleep",
    "target": {"id": 5, "name": "Loft PC", "mac": MAC_LOFT},
    "diagnosis": {
        "blame": "config",
        "headline": '"Loft PC" has no agent installed.',
        "detail": "Power actions run through the agent on the machine itself. Install it to enable sleep, restart and shutdown.",
    },
}

# 400 from POST /api/v1/power with an empty body — proof the key HAS the power scope,
# because the scope gate sits in front of the body check.
ERROR_NO_MACHINE = {
    "error": "no_machine",
    "message": "Name the machine — a power command that names none is refused.",
}

# 401 / 403 bodies, as shared/endpoint.js writes them.
ERROR_NO_KEY = {"error": "no_key", "message": "Send an API key as `Authorization: Bearer <key>`."}
ERROR_BAD_KEY = {"error": "bad_key", "message": "That key is not valid."}
ERROR_OUT_OF_SCOPE = {
    "error": "out_of_scope",
    "message": 'This key does not have the "read" permission.',
}
ERROR_OUT_OF_SCOPE_POWER = {
    "error": "out_of_scope",
    "message": 'This key does not have the "power" permission.',
}
