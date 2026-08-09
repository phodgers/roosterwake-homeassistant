# Rooster Wake for Home Assistant

Wake your machines from Home Assistant through [Rooster Wake](https://roosterwake.com) —
the cloud wake-on-LAN service with an open-firmware dongle, a free software agent, and a
public, self-hostable relay protocol.

This integration is a thin client over Rooster Wake's public REST API. It gives you:

- a **Wake button** per machine, sending through every online emitter on your account —
  no port forwarding, no VPN, and Home Assistant does not need to be on the same LAN
  (or on any LAN the machine can see) for the wake to land;
- **Sleep / Restart / Shut down buttons** for machines that carry the Rooster Wake agent,
  when your API key holds the Power permission;
- **wake result events** (`roosterwake_wake_result`) for automations: one when the wake is
  sent, carrying the service's own plain-English diagnosis of what happened and where the
  packets went — and a second when the service *confirms* the machine actually came up
  (or ran out its probe), so automations can react to the real outcome;
- a **Presence sensor** per machine: live agent-connected truth where an agent runs on
  the machine, honestly dated last-known state everywhere else, and `unknown` where
  nothing is proved — because a fire-and-forget magic packet proves nothing;
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
  Account → API keys. Add the **Power** permission too if you want sleep, restart and
  shutdown buttons — Power is deliberately a separate permission that Wake never implies,
  because a leaked wake key costs an unexpected boot while a leaked power key can shut
  down a fleet. The key is shown once at creation — paste it straight in here.
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
- **Machines** — discovered from your account and offered as a picker. There is no
  typing of MAC addresses: the machines saved on your Rooster Wake account are the
  truth, and machines are added and edited on the dashboard, not here.

Re-pick machines later via the integration's **Configure** button — the list is fetched
fresh, so a machine added on the dashboard shows up there — which is also where you can
turn off **wake confirmation** if you prefer plain sends.

## Entities

| Entity | What it means |
|---|---|
| `button.<machine>_wake` | Send a wake. The service fans it out across every online entitled emitter on the account; which emitter carries it is the service's problem, not yours. |
| `button.<machine>_sleep` / `_restart` / `_shut_down` | Power actions through the agent running on that machine. Present only for machines that carry an agent and only when your key holds the Power permission; greyed out (unavailable) while the agent is disconnected or the plan does not carry power. `ok` means *accepted*, never done — the acknowledgement precedes the action, because the action destroys the process that would confirm it. |
| `binary_sensor.<machine>_presence` | The service's presence verdict. `live: true` in the attributes means agent-connected truth — the agent's open connection *is* the machine being up. Otherwise it is last-known, dated by the `at` attribute: `on` after a probe-confirmed wake, `off` after an accepted sleep or shutdown, `unknown` where nothing is proved. |
| `binary_sensor.rooster_wake_emitter_online` | Live: is any emitter on the account connected to the relay right now? If this is `off`, a wake has nothing to send it. |

### The wake result events

Every press fires `roosterwake_wake_result` on the event bus with `phase: "sent"`,
success or failure. When wake confirmation is on (the default), a second event with
`phase: "confirmed"` follows once the service's probe settles — the service resolves the
probe server-side even if Home Assistant restarts meanwhile, and the integration collects
the outcome by polling the wake's own record:

```yaml
automation:
  - alias: "Tell me when the office PC is actually up"
    trigger:
      - platform: event
        event_type: roosterwake_wake_result
        event_data:
          mac: "00:00:5E:00:53:0A"
          phase: confirmed
          came_up: true
    action:
      - service: notify.mobile_app_phone
        data:
          title: "{{ trigger.event.data.machine }} is up"
          message: "Answered after {{ (trigger.event.data.probe_ms / 1000) | round }} s"
```

The `sent` event carries the service's `diagnosis` — headline, detail, and which part of
the chain to blame, the same text the dashboard shows. The `confirmed` event carries
`probe_state` (`up` or `timeout`), `probe_ms`, and `connect_url` when the machine's owner
set a connect handoff (the URL only ever rides confirmed rows).

## Sleep, restart and shutdown

Power actions run through the Rooster Wake agent installed on the machine itself, on
plans that carry them. The buttons appear automatically for machines the service reports
an agent on — including a machine that gains its agent after setup — and disappear into
`unavailable` while the agent is not connected, rather than pretending a press could work.

One physics note, because it matters when you plan automations: **an agent on a sleeping
machine is asleep too**. Power actions run through the agent on the machine itself, but a
wake never can — the wake always comes from an *emitter* (a dongle, or an agent on some
other always-on machine) broadcasting onto the sleeping machine's network.

## Polling and rate limits

One coordinator polls the API once a minute — the same data the dashboard reads, at a
respectful interval. If the service ever answers `429 Too Many Requests`, the integration
stops all polling — the minute poll and any running confirmation poll alike — for at
least the time the service asked for before trying again. Wakes themselves are budgeted
server-side per emitter (sustained 30/minute with a burst allowance); a rate-limited wake
comes back as a failed result whose diagnosis says exactly that, along with how many
seconds to wait.

## Troubleshooting

**"That API key was refused."**
The key is unknown, revoked or expired — the service deliberately does not say which.
Check it was pasted whole (keys start with `rw_live_` and are shown only once at
creation), and check the key still shows as live on the dashboard's API keys page. If you
are on the free plan, this is expected: API keys are a Plus and Pro feature.

**"The key works but lacks the Read permission."**
Keys carry chosen permissions. This integration needs **Read** (to list machines and
emitters) and **Wake** (to wake). Create one key carrying both.

**The power buttons never appeared.**
Two possibilities, both by design. If *no* machine has them: your key lacks the **Power**
permission (the log says so at setup) — mint a key that carries it and reconfigure. Power
is a separate permission that Wake never implies. If only some machines lack them: those
machines have no agent installed — power actions run through the agent on the machine
itself, and the dashboard's machine page is where the agent is set up.

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
