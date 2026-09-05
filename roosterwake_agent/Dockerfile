# The agent add-on: the Home Assistant base image (s6 and bashio, for run.sh) plus the one static
# binary, copied out of the published agent image rather than rebuilt here.
#
# The supervisor builds this on the device, so `FROM ghcr.io/phodgers/roosterwake-agent:<v>`
# resolves to the device's own architecture from the multi-arch manifest — a Pi gets the arm64 or
# armv7 binary, an Intel NUC the amd64 one. That package must be PUBLIC on GHCR (it is; the agent
# repo's container workflow says how) or the pull here fails with "denied".
#
# The version pinned below is the add-on's version in config.yaml; validate.yml holds them equal.
ARG BUILD_FROM
FROM ghcr.io/phodgers/roosterwake-agent:0.18.0 AS agent

FROM ${BUILD_FROM}

COPY --from=agent /roosterwake-agent /usr/bin/roosterwake-agent

# chmod here rather than trusting the checkout's mode bits: a repository cloned on Windows, or
# added through the HA UI, carries whatever mode the clone chose.
COPY run.sh /run.sh
RUN chmod a+x /run.sh

CMD ["/run.sh"]
