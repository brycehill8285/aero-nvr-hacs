"""The picture from the most recent event on each camera."""
from __future__ import annotations

from datetime import datetime, timezone

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import AeroConfigEntry
from .entity import AeroCameraEntity


async def async_setup_entry(hass: HomeAssistant, entry: AeroConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        AeroLastEventImage(hass, coordinator, camera_id)
        for camera_id in coordinator.cameras
    )


class AeroLastEventImage(AeroCameraEntity, ImageEntity):
    """The crop Aero saved for the latest event on this camera.

    Bound to a specific event id rather than "latest": the bytes are re-fetched
    only when the event changes, so a notification that arrives late still shows
    the thing it was sent about rather than whatever has happened since.
    """

    _attr_name = "Last event image"
    _attr_content_type = "image/jpeg"

    def __init__(self, hass: HomeAssistant, coordinator, camera_id: str):
        AeroCameraEntity.__init__(self, coordinator, camera_id, "last_event_image")
        ImageEntity.__init__(self, hass)
        self._event_id: int | None = None
        self._cached: bytes | None = None

    @property
    def _current_event(self) -> dict:
        return self.state_data.get("last_event") or {}

    def _handle_coordinator_update(self) -> None:
        event = self._current_event
        event_id = event.get("id")
        if event_id != self._event_id and event.get("has_image"):
            self._event_id = event_id
            self._cached = None
            started = event.get("started")
            self._attr_image_last_updated = (
                datetime.fromtimestamp(started, tz=timezone.utc) if started
                else datetime.now(timezone.utc))
        super()._handle_coordinator_update()

    async def async_image(self) -> bytes | None:
        if self._event_id is None:
            return None
        if self._cached is None:
            self._cached = await self.coordinator.client.event_image(self._event_id)
        return self._cached

    @property
    def extra_state_attributes(self) -> dict:
        event = self._current_event
        return {"event_id": event.get("id"), "label": event.get("label")}
