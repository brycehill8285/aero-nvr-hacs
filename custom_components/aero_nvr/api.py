"""Thin client for Aero NVR's integration API."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
from yarl import URL

from .const import API_BASE

_LOGGER = logging.getLogger(__name__)


class AeroError(Exception):
    """Any failure talking to Aero."""


class AeroAuthError(AeroError):
    """The token was rejected -- expired, revoked, or the add-on was removed."""


class AeroUnavailable(AeroError):
    """Aero is reachable but not serving the integration API."""


class AeroClient:
    """Calls the integration API. One instance per config entry."""

    def __init__(self, session: aiohttp.ClientSession, host: str, token: str,
                 verify_ssl: bool = True) -> None:
        self._session = session
        self._base = URL(host.rstrip("/"))
        self._token = token
        self._verify_ssl = verify_ssl

    @property
    def host(self) -> str:
        return str(self._base)

    def url(self, path: str) -> URL:
        return self._base.join(URL(f"{API_BASE}{path}"))

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = self.url(path)
        try:
            async with self._session.request(
                method, url, headers=self.headers, ssl=self._verify_ssl,
                timeout=aiohttp.ClientTimeout(total=15), **kwargs
            ) as response:
                if response.status in (401, 403):
                    raise AeroAuthError(
                        "Aero rejected the token. Generate a new one in "
                        "Settings -> Add-ons -> Home Assistant.")
                if response.status == 409:
                    # The add-on was uninstalled. Distinct from "server is down"
                    # because the fix is different and the user should be told
                    # which one it is.
                    raise AeroUnavailable(
                        "The Home Assistant add-on is not installed on Aero.")
                if response.status >= 400:
                    raise AeroError(f"{method} {path} returned {response.status}")
                if response.content_type == "application/json":
                    return await response.json()
                return await response.read()
        except aiohttp.ClientError as err:
            raise AeroError(f"Could not reach Aero at {url}: {err}") from err

    async def info(self) -> dict[str, Any]:
        return await self._request("GET", "/info")

    async def cameras(self) -> dict[str, Any]:
        return await self._request("GET", "/cameras")

    async def state(self) -> dict[str, Any]:
        return await self._request("GET", "/state")

    async def set_camera(self, camera_id: int, **fields: bool) -> dict[str, Any]:
        return await self._request("PATCH", f"/cameras/{camera_id}", json=fields)

    async def snapshot(self, camera_id: int | str) -> bytes | None:
        try:
            return await self._request("GET", f"/cameras/{camera_id}/snapshot")
        except AeroError as err:
            # A camera that has not captured yet, or one that is down, has no
            # snapshot. That is a missing picture, not a broken integration.
            _LOGGER.debug("No snapshot for camera %s: %s", camera_id, err)
            return None

    async def compat_stream(self, camera_id: int | str, role: str = "main") -> dict[str, Any]:
        """Ask Aero to register the H.264 fallback for a camera it can't decode.

        Idempotent on Aero's side -- go2rtc keeps the definition once made and
        only runs ffmpeg while something is connected to it -- so this is safe
        to call every time a stream is about to start rather than only once.
        """
        return await self._request(
            "POST", f"/cameras/{camera_id}/compat-stream", params={"role": role})

    def event_image_url(self, event_id: int) -> str:
        return str(self.url(f"/events/{event_id}/image"))

    async def event_image(self, event_id: int) -> bytes | None:
        try:
            return await self._request("GET", f"/events/{event_id}/image")
        except AeroError as err:
            # A crop can be pruned by the storage cleaner between the event
            # appearing in state and the image being fetched; that is normal
            # and must not take the entity unavailable.
            _LOGGER.debug("No image for event %s: %s", event_id, err)
            return None
