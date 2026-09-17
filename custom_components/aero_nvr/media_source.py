"""Browse and play back Aero's recorded footage from Home Assistant.

Tree: (server, only shown when more than one Aero is configured) -> camera ->
day -> clip. Days are the last 14 calendar days, generated locally rather than
asked of Aero -- a day with nothing recorded just shows an empty folder, which
is simpler than a second backend endpoint just to learn which days exist, and
a fine trade for a first version.

Playback goes through this integration's own proxy view (media_proxy.py)
rather than Aero's URL directly: the browser has no session cookie for Aero
and can't attach the bearer token to a plain video fetch, so the proxy fetches
the bytes server-side, where the token lives.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import logging
from urllib.parse import parse_qs, urlsplit

from homeassistant.components.media_player import MediaClass, MediaType
from homeassistant.components.media_source import (
    BrowseMediaSource, MediaSource, MediaSourceItem, PlayMedia)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .api import AeroError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

DAYS_SHOWN = 14


async def async_get_media_source(hass: HomeAssistant) -> MediaSource:
    return AeroMediaSource(hass)


def _entries(hass: HomeAssistant):
    return hass.config_entries.async_entries(DOMAIN)


class AeroMediaSource(MediaSource):
    name = "Aero NVR"

    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__(DOMAIN)
        self.hass = hass

    def _folder(self, identifier: str, title: str) -> BrowseMediaSource:
        """A browsable, non-playable node: a server, camera, or day."""
        return BrowseMediaSource(
            domain=DOMAIN, identifier=identifier, media_class=MediaClass.DIRECTORY,
            media_content_type="", title=title, can_play=False, can_expand=True)

    async def async_browse_media(self, item: MediaSourceItem) -> BrowseMediaSource:
        parts = (item.identifier or "").split("/") if item.identifier else []

        if not parts or parts == [""]:
            entries = _entries(self.hass)
            if len(entries) == 1:
                return await self._browse_cameras(entries[0].entry_id)
            root = self._folder("", "Aero NVR")
            root.children = [
                self._folder(entry.entry_id, entry.title or "Aero NVR")
                for entry in entries
            ]
            return root

        entry_id = parts[0]
        entry = self.hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN:
            raise HomeAssistantError(f"No such Aero NVR server: {entry_id}")

        if len(parts) == 1:
            return await self._browse_cameras(entry_id)

        # Every deeper identifier this integration hands out looks like
        # [entry_id, "cam", camera_id, ...] -- see _folder()'s callers below.
        if len(parts) < 3 or parts[1] != "cam":
            raise HomeAssistantError("Malformed Aero NVR media identifier")
        camera_id = parts[2]
        coordinator = entry.runtime_data
        camera = coordinator.cameras.get(camera_id, {})
        camera_name = camera.get("name") or f"Camera {camera_id}"

        if len(parts) == 3:
            return self._browse_days(entry_id, camera_id, camera_name)

        if len(parts) == 5 and parts[3] == "day":
            return await self._browse_clips(entry_id, camera_id, camera_name, parts[4])

        raise HomeAssistantError("Malformed Aero NVR media identifier")

    async def _browse_cameras(self, entry_id: str) -> BrowseMediaSource:
        entry = self.hass.config_entries.async_get_entry(entry_id)
        coordinator = entry.runtime_data
        node = self._folder(entry_id, entry.title or "Aero NVR")
        node.children = [
            self._folder(f"{entry_id}/cam/{camera_id}",
                      camera.get("name") or f"Camera {camera_id}")
            for camera_id, camera in coordinator.cameras.items()
        ]
        return node

    def _browse_days(self, entry_id: str, camera_id: str,
                     camera_name: str) -> BrowseMediaSource:
        node = self._folder(f"{entry_id}/cam/{camera_id}", camera_name)
        today = datetime.now().date()
        children = []
        for offset in range(DAYS_SHOWN):
            day = today - timedelta(days=offset)
            label = "Today" if offset == 0 else (
                "Yesterday" if offset == 1 else day.strftime("%A, %b %-d"))
            children.append(self._folder(
                f"{entry_id}/cam/{camera_id}/day/{day.isoformat()}", label))
        node.children = children
        return node

    async def _browse_clips(self, entry_id: str, camera_id: str, camera_name: str,
                            date_str: str) -> BrowseMediaSource:
        entry = self.hass.config_entries.async_get_entry(entry_id)
        coordinator = entry.runtime_data
        day = datetime.fromisoformat(date_str)
        day_start = day.timestamp()
        day_end = (day + timedelta(days=1)).timestamp()

        node = self._folder(f"{entry_id}/cam/{camera_id}/day/{date_str}",
                            f"{camera_name} — {day.strftime('%b %-d, %Y')}")
        try:
            clips = await coordinator.client.recordings(camera_id, start=day_start, end=day_end)
        except AeroError as err:
            _LOGGER.debug("Could not list recordings for camera %s on %s: %s",
                          camera_id, date_str, err)
            clips = []

        children = []
        # Newest first, matching Aero's own recordings list.
        for clip in sorted(clips, key=lambda c: c.get("start_epoch") or 0, reverse=True):
            start_epoch = clip.get("start_epoch")
            if start_epoch is None:
                continue
            query = parse_qs(urlsplit(clip.get("filepath") or "").query)
            stream = (query.get("stream") or ["main"])[0]
            started = datetime.fromtimestamp(start_epoch)
            duration = clip.get("duration_sec") or 0
            title = f"{started.strftime('%-I:%M %p')} · {round(duration / 60)} min"
            children.append(BrowseMediaSource(
                domain=DOMAIN,
                identifier=f"{entry_id}/cam/{camera_id}/clip/{int(start_epoch)}/{stream}",
                media_class=MediaClass.VIDEO, media_content_type=MediaType.VIDEO,
                title=title, can_play=True, can_expand=False))
        node.children = children
        return node

    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        # identifier: "{entry_id}/cam/{camera_id}/clip/{start_epoch}/{stream}"
        parts = item.identifier.split("/")
        if len(parts) != 6 or parts[1] != "cam" or parts[3] != "clip":
            raise HomeAssistantError("Malformed Aero NVR media identifier")
        entry_id, camera_id, start_epoch, stream = parts[0], parts[2], parts[4], parts[5]

        url = (f"/api/aero_nvr/{entry_id}/media/cameras/{camera_id}/timeline.m3u8"
              f"?start={start_epoch}&stream={stream}")
        return PlayMedia(url, "application/x-mpegURL")
