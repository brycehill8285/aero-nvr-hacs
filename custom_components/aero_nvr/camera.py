"""Live camera entities, fed by Aero's own go2rtc."""
from __future__ import annotations

import logging
from urllib.parse import urlparse

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import AeroConfigEntry
from .api import AeroError
from .const import GO2RTC_RTSP_PORT
from .entity import AeroCameraEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: AeroConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    entities: list[Camera] = []
    for camera_id, camera in coordinator.cameras.items():
        entities.append(AeroCamera(coordinator, camera_id, "main"))
        # A sub stream entity only where one exists. It is the one to put in
        # grids: it is already low-resolution, so a wall of them costs a
        # fraction of the same wall of main streams.
        if (camera.get("streams") or {}).get("sub"):
            entities.append(AeroCamera(coordinator, camera_id, "sub"))
    async_add_entities(entities)


class AeroCamera(AeroCameraEntity, Camera):
    """One Aero stream.

    Video is not proxied through this integration. Aero already runs go2rtc and
    Home Assistant's stream component can read RTSP directly, so the frames go
    straight from the NVR to the player and neither side transcodes.
    """

    _attr_supported_features = CameraEntityFeature.STREAM

    def __init__(self, coordinator, camera_id: str, role: str):
        AeroCameraEntity.__init__(self, coordinator, camera_id, f"camera_{role}")
        Camera.__init__(self)
        self._role = role
        self._attr_name = "Stream" if role == "main" else "Stream (low resolution)"

    @property
    def _stream_name(self) -> str | None:
        return (self.camera.get("streams") or {}).get(self._role)

    @property
    def _needs_transcode(self) -> bool:
        return bool((self.camera.get("needs_transcode") or {}).get(self._role))

    async def stream_source(self) -> str | None:
        name = self._stream_name
        if not name:
            return None
        if self._needs_transcode:
            # This camera's codec (H.265, almost always) is one Home
            # Assistant's own stream component can't decode any more than a
            # browser can -- it would otherwise connect and show nothing, the
            # same silent failure Aero's own web UI had before it grew this
            # same fallback. Ask Aero for its on-demand H.264 transcode and
            # dial that name instead. Best-effort: if Aero can't be reached
            # right now, falling through to the native name is no worse than
            # not trying, and the next stream attempt tries again.
            try:
                result = await self.coordinator.client.compat_stream(
                    self._camera_id, self._role)
                name = result.get("src") or name
            except AeroError as err:
                _LOGGER.debug("Compatibility stream unavailable for camera %s: %s",
                              self._camera_id, err)
        # The host comes from the config entry, which is the address Home
        # Assistant proved it can reach during setup -- not from anything the
        # NVR reports about itself, which is wrong behind a reverse proxy.
        host = urlparse(self.coordinator.client.host).hostname
        return f"rtsp://{host}:{GO2RTC_RTSP_PORT}/{name}"

    async def async_camera_image(self, width: int | None = None,
                                 height: int | None = None) -> bytes | None:
        """A still for the card before the stream starts.

        Served from Aero's saved snapshots rather than decoded on demand: the
        snapshot already exists on disk, and asking the NVR to decode a frame
        every time a dashboard tile scrolls into view is how a thumbnail grid
        turns into real load on the machine recording the video.
        """
        return await self.coordinator.client.snapshot(self._camera_id)

    @property
    def is_recording(self) -> bool:
        return bool(self.camera.get("recording"))

    @property
    def motion_detection_enabled(self) -> bool:
        return bool(self.state_data.get("motion"))
