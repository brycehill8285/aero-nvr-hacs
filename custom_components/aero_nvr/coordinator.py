"""One poll for the whole NVR, shared by every entity."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AeroAuthError, AeroClient, AeroError
from .const import DOMAIN, SCAN_INTERVAL_SECONDS

_LOGGER = logging.getLogger(__name__)


class AeroCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls /state for every camera at once.

    One request per interval for the whole NVR, not one per entity: a box with
    eight cameras and a dozen entities each would otherwise put a hundred
    requests a second on a machine whose actual job is writing video to disk.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry,
                 client: AeroClient, cameras: list[dict[str, Any]]) -> None:
        super().__init__(
            hass, _LOGGER, name=DOMAIN,
            update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS),
            config_entry=entry,
        )
        self.client = client
        # The camera roster changes only when someone edits it in Aero, so it is
        # fetched at setup and refreshed lazily rather than on every poll.
        self.cameras = {str(camera["id"]): camera for camera in cameras}

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            payload = await self.client.state()
        except AeroAuthError as err:
            # Triggers Home Assistant's reauth flow rather than just going
            # unavailable, because a revoked token needs the user to act.
            raise ConfigEntryAuthFailed(str(err)) from err
        except AeroError as err:
            raise UpdateFailed(str(err)) from err
        return payload.get("cameras", {})

    def camera_state(self, camera_id: str) -> dict[str, Any]:
        return (self.data or {}).get(camera_id, {})

    async def async_refresh_cameras(self) -> None:
        """Re-read the roster, e.g. after a camera is added in Aero."""
        try:
            payload = await self.client.cameras()
        except AeroError as err:
            _LOGGER.debug("Could not refresh the camera roster: %s", err)
            return
        self.cameras = {str(c["id"]): c for c in payload.get("cameras", [])}
