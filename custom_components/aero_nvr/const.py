"""Shared constants for the Aero NVR integration."""

DOMAIN = "aero_nvr"

CONF_SERVER_ID = "server_id"
CONF_VERIFY_SSL = "verify_ssl"

# The integration API contract this client was written against. Aero reports its
# own in /info; a newer major there means the server has changed shapes we would
# misread, so setup refuses rather than inventing entities out of guesswork.
API_VERSION = 1
API_BASE = f"/api/integration/v{API_VERSION}"

# Aero's state endpoint is deliberately cheap -- two in-memory dicts and one
# indexed query per camera -- so this can be short enough that motion is useful.
# It must stay below the server's own motion window or motion between two polls
# is never seen.
SCAN_INTERVAL_SECONDS = 2

DEFAULT_PORT = 2525
GO2RTC_RTSP_PORT = 8554

# The object classes Aero detects, and the Home Assistant device class each maps
# to. "animal" has no device class of its own, so it stays a plain occupancy.
OBJECT_CLASSES = {
    "person": "motion",
    "car": "motion",
    "animal": "occupancy",
}

# Per-camera switches: the key Aero's PATCH accepts, and how it reads in the UI.
SWITCHES = {
    "recording": "Recording",
    "people": "Detect people",
    "cars": "Detect vehicles",
    "animals": "Detect animals",
    "faces": "Detect faces",
    "plates": "Detect plates",
    "semantic": "Event search indexing",
}
