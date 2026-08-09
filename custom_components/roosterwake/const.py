"""Constants for the Rooster Wake integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "roosterwake"

CONF_BASE_URL: Final = "base_url"
CONF_MACHINES: Final = "machines"
CONF_MACHINE_NAME: Final = "name"
CONF_MACHINE_MAC: Final = "mac"
CONF_CONFIRM_WAKES: Final = "confirm_wakes"

DEFAULT_CONFIRM_WAKES: Final = True

# The server holds no new watchers for us: Home Assistant is just another dashboard
# client, and 60 seconds is a respectful floor for a cloud poll.
UPDATE_INTERVAL_S: Final = 60

# When the service answers 429 without a usable Retry-After, hold off at least this long.
MIN_BACKOFF_S: Final = 60

# Fired on every wake attempt, success or failure, carrying the API's own diagnosis.
EVENT_WAKE_RESULT: Final = "roosterwake_wake_result"
