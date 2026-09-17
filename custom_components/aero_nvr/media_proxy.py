"""Streams Aero's recorded clips into Home Assistant's frontend.

The browser tab showing Home Assistant's Media Browser has a session cookie
for Home Assistant, not for Aero, and a plain <video>/hls.js fetch can't
attach the bearer token Aero's integration API wants. So playback goes
through this view instead: the frontend fetches from Home Assistant's own
origin (ordinary HA auth), and this view fetches the real bytes from Aero
using the token, entirely server-side.

Mounted at a wildcard path rather than one route per file kind (playlist,
init segment, media segment) because build_timeline_m3u8's playlists are
generated with `relative=True` specifically so their internal URIs are bare
paths that resolve against wherever the playlist itself was fetched from --
see that function's docstring in Aero's main.py. Whatever suffix the player
asks for next, this forwards to the same suffix on Aero's integration API.
"""
from __future__ import annotations

import logging

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .api import AeroError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class AeroMediaProxyView(HomeAssistantView):
    url = "/api/aero_nvr/{entry_id}/media/{path:.*}"
    name = "api:aero_nvr:media"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def get(self, request: web.Request, entry_id: str, path: str) -> web.Response:
        entry = self.hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN:
            return web.Response(status=404, text="No such Aero NVR entry")
        coordinator = entry.runtime_data
        try:
            body, content_type = await coordinator.client.raw_get(
                f"/{path}", params=dict(request.query))
        except AeroError as err:
            _LOGGER.debug("Media proxy fetch failed for %s: %s", path, err)
            return web.Response(status=502, text=str(err))
        return web.Response(body=body, content_type=content_type)
