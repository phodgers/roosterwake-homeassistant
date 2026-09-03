# Rooster Wake agent add-on

The free [Rooster Wake](https://roosterwake.com) agent, running on your Home Assistant box as
your account's **always-on waker**. Your Home Assistant machine is already the computer in the
house that never sleeps; this add-on makes it the thing that puts the Wake-on-LAN magic packet on
your network when you press Wake from the dashboard, the app, the API or Home Assistant itself.

It is **free on every plan**, including the free one. Being an emitter is the job the free plan
includes, and the add-on is the same free agent as everywhere else — nothing here needs an API
key.

## What it does, and what it does not

- Connects **out** to the relay over TLS and stays connected. Nothing listens on the network; no
  port is opened, mapped or forwarded.
- Broadcasts a magic packet on the networks this box is on when the relay asks, and reports
  exactly where it went.
- Enrols **emitter-only** by default: it advertises wake and status and nothing else, so nothing
  can ever ask it to sleep, restart or shut down your Home Assistant box, and the dashboard
  never files the box as a machine to look after. It is a waker.
- Does **not** wake the machine it runs on — nothing could; an agent on a sleeping machine is
  asleep with it. That is why it belongs on the box that stays on.

## Installation

1. **Settings → Add-ons → Add-on store → ⋮** (top right) **→ Repositories**.
2. Paste `https://github.com/phodgers/roosterwake-homeassistant`, press **Add**, close the
   dialog. *Rooster Wake agent* appears in the store (reload the page if it does not).
3. Open it and press **Install**. The add-on is built on your device: it takes the Home Assistant
   base image for your architecture and copies one static binary into it from the published
   agent image — a minute or two on a Pi.
4. On the **Configuration** tab, fill in **exactly one** of `email` and `token` (see below) and
   **Save**.
5. On the **Info** tab, turn on **Start on boot** and press **Start**. The **Log** tab shows it
   enrol.

Within a minute it appears on your dashboard's **Emitters** page as an **Always on** waker.

## Options

| Option | Required | What it does |
|---|---|---|
| `email` | one of the two, **first start only** | Your Rooster Wake account address. The add-on asks to join that account: approve it on the dashboard's Emitters page. An address with no account yet gets an invitation. |
| `token` | one of the two, **first start only** | An enrolment token minted on the dashboard's Emitters page (paid plans). Joins the account that minted it with no approval step. |
| `emitter_only` | no, default on | On: a wake sender only — no power actions, no posture, never listed as a machine. Off: a full agent, which can sleep, restart or shut this box down from the dashboard on the Plus and Pro plans — rarely what a Home Assistant box wants, because a box that sleeps is a waker that is asleep. Chosen at enrolment; changing it means enrolling afresh. |

Setting **both** `email` and `token` is refused as a contradiction. Setting **neither** is refused
only until the first enrolment has happened: after that the identity on the add-on's `/data`
decides, the credential options are ignored, and you may clear them.

## The identity, and starting over

The agent's identity — a device id and a token — lives at `/data/agent.json`, in the add-on's
persistent storage. A restart, an add-on update or a rebuild keeps the same emitter on your
dashboard rather than minting a second one.

To enrol afresh (a different account, say): remove the emitter on the dashboard's Emitters page
to free its slot, **Uninstall** the add-on (which deletes its `/data`), install it again with the
new credential.

## Networking

The add-on runs on the **host's network** (`host_network: true`) — the supervisor arranges that,
and it is not optional. A wake is a broadcast, and a broadcast cannot leave a bridged container
network; the agent checks for this on every start and refuses to run on a bridge with:

> This container is on a bridge network. A wake is a broadcast and cannot leave a bridge, so
> the agent refuses to start — run it with --network host (Docker) or network_mode: host
> (Compose), or tick 'Use the same network as the Docker host' in your NAS's container
> settings.

You should never see that sentence from this add-on. If you do, something has changed the
add-on's network mode; reinstalling restores it.

The packets reach every machine on the network segments your Home Assistant box is on, and none
beyond. A machine on a different VLAN from the box cannot be woken by it — the dashboard's
Emitters page shows exactly which broadcast addresses this emitter sends to, so a wrong-segment
wake is visible rather than a mystery.

## The add-on and the integration are two different things

This repository ships both, and they do different jobs:

- **This add-on** is the **waker**: the free agent, sending the packet. Free on every plan.
- **The integration** (installed through HACS as a custom repository, then *Settings → Devices &
  services*) puts your machines on a Home Assistant dashboard as wake buttons, power buttons and
  presence sensors over the REST API. It signs in with an **API key**, which is a **Plus or Pro**
  feature.

You can run both — the add-on wakes, the integration shows — and neither needs the other.

## Logs and support

The add-on's **Log** tab is the agent's transcript: enrolment, authentication, every wake and
where it went. `RW_LOG=debug` is not exposed as an option; if support asks for a frame-by-frame
transcript, say so and we will walk you through it.

Support: <support@roosterwake.com>. Security issues: <security@roosterwake.com>, never a public
issue.
