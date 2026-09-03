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

if bashio::config.true 'emitter_only'; then
  export RW_EMITTER_ONLY=1
else
  export RW_EMITTER_ONLY=0
fi

has_email=false
has_token=false
if bashio::config.has_value 'email'; then
  has_email=true
  RW_EMAIL="$(bashio::config 'email')"
  export RW_EMAIL
fi
if bashio::config.has_value 'token'; then
  has_token=true
  RW_TOKEN="$(bashio::config 'token')"
  export RW_TOKEN
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
