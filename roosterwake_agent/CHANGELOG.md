# Changelog

## 0.29.0

- Follows agent 0.29.0. The SSH set-up now checks with the login service itself whether password
  sign-in really went off, and says so; the dashboard shows whether a machine still takes
  passwords and offers to put password sign-in back exactly as it was found, behind your
  authenticator code. Nothing changes for this add-on: it is a container, and an agent only
  replaces itself where a service manager started it, so this one is still updated by taking a
  new image.

## 0.28.0

- Follows agent 0.28.0. The dashboard now sets an SSH connection up between two machines itself:
  it mints a key on the machine you connect from, installs it on the machine you connect to, and
  removing it from the dashboard leaves that machine refusing it. Every file the agent writes
  inside a home directory goes through a confinement that refuses a link of either kind and
  writes through one open handle. Nothing changes for this add-on: it is a container, and an
  agent only replaces itself where a service manager started it, so this one is still updated by
  taking a new image.

## 0.27.0

- Follows agent 0.27.0. Nothing changes for this add-on: it is a container, and an agent only
  replaces itself where a service manager started it, so this one is still updated by taking a
  new image. The release fixes self-update for agents installed as a service on Linux and
  macOS, which could seldom act on a machine that sleeps.

## 0.26.0

- Follows agent 0.26.0, and skips 0.25.0: an add-on updated from 0.24.0 gets both releases at
  once. Setting SSH up from the dashboard works on a Linux machine the installer manages, a
  file transfer over SSH names the program moving the bytes, and a Windows machine being shut
  down says so rather than looking as though its agent stopped.
- Agents installed as a service on Linux or macOS now keep themselves up to date, checking
  shortly after they start, every few hours, and a minute or three after the machine wakes, so
  one that sleeps between short spells of use no longer misses every check. **This add-on is
  not one of them and does not change**: an agent only replaces itself where the service
  manager started it, which a container image has no part in, so it is updated the way it
  always was -- by taking a new image.

## 0.24.0

- Follows agent 0.24.0 (setting SSH up from the dashboard now works on a Linux machine the
  installer manages: the service stays sandboxed and asks the init system for a transient unit
  to do the privileged work in, and each step reads the machine back instead of trusting a
  command exit code). An upgrade restarts the service so it picks up the new unit.

## 0.23.0

- Follows agent 0.23.0 (from the dashboard the agent can now set SSH up on a machine — server,
  firewall rule, your public key, passwords off — and turn it on and off afterwards; a
  connection serving two SSH channels at once is read the same way on every poll). Nothing
  changes for this add-on's container beyond the image tag.

## 0.22.0

- Follows agent 0.22.0 (on Windows the agent is now a service rather than a scheduled task, so
  a machine that is shut down says so instead of "agent stopped"; a git push or fetch over SSH
  on Windows is read as a transfer named git). Nothing changes for this add-on's Linux
  container beyond the image tag.

## 0.21.0

- Follows agent 0.21.0 (a file transfer over SSH now names the program moving the bytes —
  sftp, scp, rsync or git — so the dashboard and the connector say "rsync over SSH" rather than
  "file transfer over SSH" while it runs).

## 0.20.0

- Follows agent 0.20.0 (a machine now offers its network addresses most-wakeable-first — an
  interface with a link before one without, a burned-in address before a made-up one, a wire
  before a radio — so a machine joins at an address a wake can actually reach instead of at a
  laptop's bridge or a desktop's virtual switch, and where a machine has more than eight
  addresses it is the least wakeable that are dropped. A Windows machine the operating system
  is shutting down now says so, and the dashboard says the machine is shut down rather than
  that its agent stopped. An agent also reports what kind of machine it is — laptop or
  desktop, whether it has a battery, which sleep state it uses, and whether its wireless
  adapter is armed to be woken — each reported only where the machine actually answers, so the
  service can offer a wake where one will work and name the obstacle where it will not. The
  add-on's own emitter-only run in its container reports none of these facts about the Home
  Assistant host and shuts nothing down; its addresses follow the same order).

## 0.19.0

- Follows agent 0.19.0 (an agent sees SSH: a shell over SSH counts as the machine being in
  use and is held open while somebody is working in it, a file transfer over SSH — sftp, scp,
  rsync, sshfs — is held while the bytes move, and both stop counting ten minutes after the
  last activity, so a session left open overnight no longer keeps a machine awake. A machine
  now goes back to sleep ten minutes after the last activity rather than only when a
  keep-awake hold runs out. The add-on's own emitter-only run in its container watches no
  sessions and sleeps nothing).

## 0.18.0

- Follows agent 0.18.0 (Linux and macOS agents read whether the machine's network adapter is
  set to wake on a magic packet and, from the dashboard's "Prepare for wake", set it — and on
  Linux keep it set through every start and wake; the Linux unit runs on systemd releases
  before 240. The add-on's own emitter-only run in its container reports no wake facts and
  changes nothing on the host).

## 0.17.1

- Follows agent 0.17.1 (a Mac says goodbye before it sleeps, through a helper the macOS
  installer package carries, and the agent's loopback beacon names the operating system it
  runs on. The add-on's own emitter-only run in its container carries no helper, never
  sleeps and serves no beacon).

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
