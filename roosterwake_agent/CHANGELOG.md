# Changelog

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
