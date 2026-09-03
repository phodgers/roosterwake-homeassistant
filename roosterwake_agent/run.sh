#!/usr/bin/with-contenv bashio
# shellcheck shell=bash
#
# Map the add-on's options onto the agent image's environment contract, then hand over to the
# same `container` entrypoint the image runs everywhere else:
#
#   email        -> RW_EMAIL          token -> RW_TOKEN        (exactly one, first start only)
#   emitter_only -> RW_EMITTER_ONLY   (default on: a waker that never offers to sleep this box)
#   /data/agent.json is the identity — the supervisor's persistent /data, so a restart, an
#   update or a rebuild keeps the same emitter on the dashboard.
#
# The agent itself checks for host networking and refuses a bridge; config.yaml's host_network
# makes that check pass here, and nothing in this script needs to know about it.
set -e

readonly CONFIG=/data/agent.json
export ROOSTERWAKE_CONFIG="${CONFIG}"

# The options are read from /data/options.json — the file the supervisor writes for every
# add-on before it starts — rather than through bashio::config, which fetches the same values
# over the Supervisor API. The file is the older contract and the one that also holds outside
# a supervisor (the add-on's own build check runs this image under plain Docker with an
# options.json mounted, which is how it was proven), and a wake sender should not need a
# working API round trip before it can read three fields it already has on disk.
readonly OPTIONS=/data/options.json
if [ ! -f "${OPTIONS}" ]; then
  bashio::exit.nok "No options file at ${OPTIONS} — this image is meant to run as a Home Assistant add-on, where the supervisor writes it. For plain Docker use ghcr.io/phodgers/roosterwake-agent directly (RW_EMAIL or RW_TOKEN in the environment)."
fi

option() {
  jq -r --arg key "${1}" '.[$key] // empty' "${OPTIONS}"
}

if [ "$(jq -r '.emitter_only // true' "${OPTIONS}")" = "false" ]; then
  export RW_EMITTER_ONLY=0
else
  export RW_EMITTER_ONLY=1
fi

has_email=false
has_token=false
email="$(option email)"
token="$(option token)"
if [ -n "${email}" ]; then
  has_email=true
  export RW_EMAIL="${email}"
fi
if [ -n "${token}" ]; then
  has_token=true
  export RW_TOKEN="${token}"
fi

# Both is a contradiction whatever state the volume is in; neither is a problem only until an
# identity exists — after the first enrolment the agent ignores the credential, so clearing the
# option later is fine and the add-on keeps running the emitter it already is.
if ${has_email} && ${has_token}; then
  bashio::exit.nok "Set exactly one of 'email' and 'token': an address asks to join your account (approve it on the dashboard's Emitters page), a token joins the account that minted it. Both at once is a contradiction — clear one in the Configuration tab and start again."
fi
if [ ! -f "${CONFIG}" ] && ! ${has_email} && ! ${has_token}; then
  bashio::exit.nok "Nothing to enrol with yet: set 'email' to your account address, or 'token' to an enrolment token from the dashboard's Emitters page — exactly one of the two — in this add-on's Configuration tab, then start it again."
fi

if [ -f "${CONFIG}" ]; then
  bashio::log.info "Identity found at ${CONFIG}; running the existing emitter (the email/token options are not used)."
else
  bashio::log.info "No identity yet; enrolling on first start (emitter_only=${RW_EMITTER_ONLY})."
fi

exec /usr/bin/roosterwake-agent container
