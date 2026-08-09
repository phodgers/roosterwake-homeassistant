# Rooster Wake for Home Assistant

Wake your machines from Home Assistant through [Rooster Wake](https://roosterwake.com) —
the cloud wake-on-LAN service with an open-firmware dongle, a free software agent, and a
public, self-hostable relay protocol.

This integration is a thin client over Rooster Wake's public REST API. It gives you:

- a **Wake button** per machine, sending through every online emitter on your account —
  no port forwarding, no VPN, and Home Assistant does not need to be on the same LAN
  (or on any LAN the machine can see) for the wake to land;
- a **wake result event** (`roosterwake_wake_result`) for automations, carrying the
  service's own plain-English diagnosis of what happened and where the packets went;
- a **last-known state sensor** per machine, derived honestly from the account's wake and
  power history — a wake the service *confirmed* (its probe saw the machine answer) proves
  "up"; an accepted sleep or shutdown proves "down"; anything else reads as unknown,
  because a fire-and-forget magic packet proves nothing;
- an **Emitter online sensor**: whether anything on your account — dongle or agent — is
  connected right now and able to carry a wake at all.

## Requirements

- A Rooster Wake account on the **Plus or Pro plan**. The integration authenticates with
  an ordinary Rooster Wake API key, and the free plan does not include API keys — that is
  the whole gate, stated plainly. (If you are on the free plan, Home Assistant's built-in
  [`wake_on_lan`](https://www.home-assistant.io/integrations/wake_on_lan/) integration
  covers LAN-local wake perfectly well; what Rooster Wake adds is wake from anywhere,
  confirmation that it worked, schedules, and history.)
- An API key with the **Wake** and **Read** permissions, created on the dashboard under
  Account → API keys. The key is shown once at creation — paste it straight in here.
- At least one emitter claimed on your account: a Rooster Wake dongle, or the free agent
  running on an always-on machine.

## Installation

Until this repository is listed in the HACS default store:

1. In HACS, open **Custom repositories** (three-dot menu).
2. Add `https://github.com/phodgers/roosterwake-homeassistant` with type **Integration**.
3. Install **Rooster Wake**, then restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration** and search for
   *Rooster Wake*.

Manual alternative: copy `custom_components/roosterwake/` into your Home Assistant
`config/custom_components/` directory and restart.

## Configuration

The config flow asks for:

- **Instance URL** — leave the default (`https://app.roosterwake.com`) for the hosted
  service. The relay protocol is public and self-hosting is a first-class path; if you run
  your own deployment, point this at it. The integration speaks only the REST API.
- **API key** — validated with a real call before the flow continues.
- **Machines** — name and MAC address, one or more. Each must be a machine already saved
  on your Rooster Wake account: the API only wakes saved machines, and it refuses
  addresses that are not on the list. (The public API cannot yet enumerate your saved
  machines, so they are entered here by hand; when it can, this step will become a
  picker.)

Add or remove machines later via the integration's **Configure** button, which is also
where you can turn off **wake confirmation** if you prefer plain sends.

## Entities

| Entity | What it means |
|---|---|
| `button.<machine>_wake` | Send a wake. The service fans it out across every online entitled emitter on the account; which emitter carries it is the service's problem, not yours. |
| `binary_sensor.<machine>_last_known_state` | Last-known machine state: `on` after a confirmed wake, `off` after an accepted sleep/shutdown, `unknown` otherwise. Attributes say when and how the fact was established. This is a record, not a live probe. |
| `binary_sensor.rooster_wake_emitter_online` | Live: is any emitter on the account connected to the relay right now? If this is `off`, a wake has nothing to send it. |

### The wake result event

Every press fires `roosterwake_wake_result` on the event bus, success or failure:

```yaml
automation:
  - alias: "Tell me when the office PC wake fails"
    trigger:
      - platform: event
        event_type: roosterwake_wake_result
        event_data:
          mac: "00:00:5E:00:53:0A"
          ok: false
    action:
      - service: notify.mobile_app_phone
        data:
          title: "Wake failed: {{ trigger.event.data.machine }}"
          message: "{{ trigger.event.data.diagnosis.headline }}"
```

The `diagnosis` object is the service's own explanation — headline, detail, and which
part of the chain to blame — the same text the Rooster Wake dashboard shows.

## What about sleep, restart and shutdown?

Rooster Wake's paid plans can sleep, restart and shut machines down through its installed
agent — but the public v1 API does not expose power actions yet, so this integration does
not offer those buttons. A button that always fails is worse than no button; they will
appear here the day the API carries them.

One physics note, because it matters when you plan automations: **an agent on a sleeping
machine is asleep too**. Power actions run through the agent on the machine itself, but a
wake never can — the wake always comes from an *emitter* (a dongle, or an agent on some
other always-on machine) broadcasting onto the sleeping machine's network.

## Polling and rate limits

One coordinator polls the API once a minute — the same data the dashboard reads, at a
respectful interval. If the service ever answers `429 Too Many Requests`, the integration
stops polling for at least the time the service asked for before trying again. Wakes
themselves are budgeted server-side per emitter (sustained 30/minute with a burst
allowance); a rate-limited wake comes back as a failed result with a diagnosis saying
exactly that.

## Troubleshooting

**"That API key was refused."**
The key is unknown, revoked or expired — the service deliberately does not say which.
Check it was pasted whole (keys start with `rw_live_` and are shown only once at
creation), and check the key still shows as live on the dashboard's API keys page. If you
are on the free plan, this is expected: API keys are a Plus and Pro feature.

**"The key works but lacks the Read permission."**
Keys carry chosen permissions. This integration needs **Read** (to list emitters and
history) and **Wake** (to wake). Create one key carrying both.

**Wake button reports "None of your dongles are connected."**
The `Emitter online` sensor will be `off` too. Check the dongle has power and Wi-Fi, or
that the machine running the agent is up. Nothing was sent — there was nothing to send
with.

**Wake goes out but the machine never comes up.**
Read the event's `diagnosis.detail` — it names the network segments the packets actually
went to, which is the usual culprit (an emitter on a different subnet cannot reach the
machine). After that it is machine configuration: Wake-on-LAN enabled in the BIOS, the
adapter allowed to wake the machine, and on Windows, Fast Startup turned off.

**Everything is `unavailable` and the log mentions rate limiting.**
The integration is backing off after a `429`. It resumes by itself; if it happens
persistently, check nothing else is hammering the API with the same key.

## Development

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements_test.txt
pytest
```

Tests use [pytest-homeassistant-custom-component](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component)
and run against captured response shapes from the real v1 API. MAC addresses in tests and
examples are RFC 7042 documentation addresses (`00:00:5E:00:53:xx`).

The harness targets Linux (CI runs on Ubuntu). It can be coaxed into running on Windows,
but that needs pure-Python stand-ins for three Unix-only modules (`lru-dict`, `fcntl`,
`resource`) in the virtual environment; `tests/conftest.py` handles the remaining
socket-guard difference itself.

## Licence and trademarks

Code is MIT licensed. "Rooster Wake" is a trademark of Puresoft Ltd; this repository uses
the word mark only, and the licence grants no rights to the name or logo — see the
trademark policy in the [Rooster Wake firmware repository](https://github.com/phodgers/roosterwake).
