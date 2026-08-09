"""Constants for the Rooster Wake integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "roosterwake"

CONF_BASE_URL: Final = "base_url"
# The SELECTED machines: a list of MAC strings, chosen from the server's discovered list.
CONF_MACHINES: Final = "machines"
CONF_CONFIRM_WAKES: Final = "confirm_wakes"

DEFAULT_CONFIRM_WAKES: Final = True

# The server holds no new watchers for us: Home Assistant is just another dashboard
# client, and 60 seconds is a respectful floor for a cloud poll.
UPDATE_INTERVAL_S: Final = 60

# When the service answers 429 without a usable Retry-After, hold off at least this long.
MIN_BACKOFF_S: Final = 60

# Fired on every wake attempt, success or failure, carrying the API's own diagnosis.
# Fired twice for a confirmed wake: phase "sent" with the immediate answer, then phase
# "confirmed" with the settled historyRow once the probe's outcome is known.
EVENT_WAKE_RESULT: Final = "roosterwake_wake_result"

# The confirmation poll: GET /api/v1/wake/{id} until terminal. A probe runs for at most
# 300 s and the service's own sweep settles abandoned ones, so six minutes bounds every
# honest outcome; past it we stop asking rather than poll for ever.
CONFIRM_POLL_INTERVAL_S: Final = 15
CONFIRM_POLL_DEADLINE_S: Final = 360
