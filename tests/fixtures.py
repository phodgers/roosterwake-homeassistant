"""Captured response shapes from the Rooster Wake public v1 API.

These dictionaries mirror, field for field, what the live endpoints return — the shapes
were taken from the service's own endpoint code, not invented. MAC addresses are RFC 7042
documentation addresses (00:00:5E:00:53:xx) throughout.
"""

from __future__ import annotations

BASE_URL = "https://app.roosterwake.com"
API_KEY = "rw_live_TESTKEYTESTKEYTESTKEYTESTKEYTESTKEYTESTKEY"

DEVICE_ID = "rw-24a1"
AGENT_DEVICE_ID = "rw-agent-7f"

MAC_OFFICE = "00:00:5E:00:53:0A"  # presence provable: last row is a confirmed wake
MAC_STUDY = "00:00:5E:00:53:0B"  # presence provable: last row is an accepted sleep
MAC_LOFT = "00:00:5E:00:53:0C"  # unprovable: only an unconfirmed wake

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
            "deviceId": AGENT_DEVICE_ID,
            "name": "NAS agent",
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

# POST /api/v1/wake — success, with a confirmation probe started.
WAKE_OK = {
    "ok": True,
    "err": None,
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

# POST /api/v1/wake — HTTP 200 with ok:false; the account owns no connected emitter.
WAKE_OFFLINE = {
    "ok": False,
    "err": "offline",
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

# POST /api/v1/wake — HTTP 200 with ok:false; the relay's wake budget said no.
WAKE_RATE_LIMITED = {
    "ok": False,
    "err": "rate_limited",
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
}

# GET /api/v1/devices/{id}/history — scope `read`, cursor paged.
HISTORY_OK = {
    "entries": [
        {
            "id": 204,
            "at": 1754700400,
            "deviceId": AGENT_DEVICE_ID,
            "targetName": "Study PC",
            "targetMac": MAC_STUDY,
            "requestedBy": "someone@example.com",
            "source": "dashboard",
            "via": "dongle",
            "linkLabel": None,
            "action": "sleep",
            "ok": True,
            "err": None,
            "sent": 0,
            "ifaces": [],
            "latencyMs": 210,
            "probeState": None,
            "probeMs": None,
            "connectUrl": None,
            "diagnosis": {
                "blame": None,
                "headline": '"Study PC" is going to sleep.',
                "detail": "The agent accepted the command.",
            },
        },
        {
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
            "probeState": "up",
            "probeMs": 23000,
            "connectUrl": None,
            "diagnosis": {
                "blame": None,
                "headline": "Sent 12 packets.",
                "detail": "They went to the 192.168.1.x network, on ports 9 and 7.",
            },
        },
        {
            "id": 201,
            "at": 1754700100,
            "deviceId": DEVICE_ID,
            "targetName": "Loft PC",
            "targetMac": MAC_LOFT,
            "requestedBy": "someone@example.com",
            "source": "api",
            "via": "dongle",
            "linkLabel": None,
            "action": "wake",
            "ok": True,
            "err": None,
            "sent": 12,
            "ifaces": ["192.168.1.255:9", "192.168.1.255:7"],
            "latencyMs": 495,
            "probeState": None,
            "probeMs": None,
            "connectUrl": None,
            "diagnosis": {
                "blame": None,
                "headline": "Sent 12 packets.",
                "detail": "They went to the 192.168.1.x network, on ports 9 and 7.",
            },
        },
        {
            "id": 180,
            "at": 1754600500,
            "deviceId": DEVICE_ID,
            "targetName": "Office PC",
            "targetMac": MAC_OFFICE,
            "requestedBy": None,
            "source": "schedule",
            "via": "dongle",
            "linkLabel": None,
            "action": "shutdown",
            "ok": True,
            "err": None,
            "sent": 0,
            "ifaces": [],
            "latencyMs": 300,
            "probeState": None,
            "probeMs": None,
            "connectUrl": None,
            "diagnosis": {
                "blame": None,
                "headline": '"Office PC" is shutting down.',
                "detail": "The agent accepted the command.",
            },
        },
    ],
    "nextBefore": 180,
}

HISTORY_EMPTY = {"entries": [], "nextBefore": None}

# 401 / 403 bodies, as shared/endpoint.js writes them.
ERROR_NO_KEY = {"error": "no_key", "message": "Send an API key as `Authorization: Bearer <key>`."}
ERROR_BAD_KEY = {"error": "bad_key", "message": "That key is not valid."}
ERROR_OUT_OF_SCOPE = {
    "error": "out_of_scope",
    "message": 'This key does not have the "read" permission.',
}
