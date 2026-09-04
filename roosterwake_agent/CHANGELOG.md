# Changelog

## 0.17.0

- Follows agent 0.17.0 (macOS and Linux agents gain keep-awake, the sleep judge, the farewell
  before a Linux suspend and the wake-adapter inventory; a Claude Code remote-control session
  counts as the machine being in use on every platform. The add-on's own emitter-only run in
  its container advertises none of that: it holds no lock, judges nothing and sends no
  farewell, exactly as before).

## 0.16.7

- Follows agent 0.16.7 (a Windows agent whose first read after a boot finds no network
  adapters re-reads a minute later instead of trusting the empty answer for a quarter of an
  hour; the add-on's own emitter-only run reports no adapters and is unaffected).

## 0.16.6

- Follows agent 0.16.6 (a Windows agent that starts within minutes of the machine booting
  puts ten minutes on the keep-awake meter, so a machine switched on by its plug is judged
  like one woken by a packet; the add-on's own emitter-only run stakes nothing).

## 0.16.5

- Follows agent 0.16.5 (an agent handed a shutdown or restart no longer reconnects in the
  seconds before the process ends, so its farewell stands; the add-on's own emitter-only run
  is unaffected).

## 0.16.4

- Follows agent 0.16.4 (a Windows agent puts its machine back to sleep, or shuts it down
  cleanly, when a keep-awake hold runs out and nobody is using it; the add-on's own
  emitter-only run holds nothing and is unaffected).

## 0.16.3

- Follows agent 0.16.3 (Windows agents watch their remote session and report changes at
  once; the add-on's own emitter-only run is unaffected).

## 0.16.2

- Follows agent 0.16.2 (the connect report names the kind of remote session keeping a
  Windows machine awake; nothing changes for the add-on's own emitter-only run).

## 0.16.1

- Follows agent 0.16.1: the machine's wake-from-off verdict now rides the connect report (a
  Windows-side fact; the add-on's own emitter-only run is unaffected). The options file is
  read from `/data/options.json` directly rather than through the Supervisor API.

## 0.16.0

- First release. The Rooster Wake agent 0.16.0 as an add-on: the free agent, emitter-only by
  default, on the host's network, as the account's always-on waker. Options `email` or `token`
  (exactly one, first start only) and `emitter_only`. The identity lives in the add-on's `/data`
  and survives restarts and updates.
- The version follows the agent image the add-on is built from
  (`ghcr.io/phodgers/roosterwake-agent`).
