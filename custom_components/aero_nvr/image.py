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
    entities: list[ImageEntity] = []
    for camera_id in coordinator.cameras:
        entities.append(AeroLastEventImage(hass, coordinator, camera_id))
        entities.append(AeroLastRecognizedFaceImage(hass, coordinator, camera_id))
        entities.append(AeroLastPlateReadImage(hass, coordinator, camera_id))
    async_add_entities(entities)


class _AeroEventBoundImage(AeroCameraEntity, ImageEntity):
    """Shared machinery for an image tied to a specific, changing event id.

    Bound to a specific event id rather than "latest": the bytes are
    re-fetched only when the event changes, so a notification that arrives
    late still shows the thing it was sent about rather than whatever has
    happened since. Subclasses just say which state_data key holds their
    event and what to name the entity.
    """

    _state_key: str

    def __init__(self, hass: HomeAssistant, coordinator, camera_id: str, key: str):
        AeroCameraEntity.__init__(self, coordinator, camera_id, key)
        ImageEntity.__init__(self, hass)
        self._event_id: int | None = None
        self._cached: bytes | None = None

    @property
    def _current(self) -> dict:
        return self.state_data.get(self._state_key) or {}

    def _handle_coordinator_update(self) -> None:
        current = self._current
        event_id = current.get("event_id", current.get("id"))
        if event_id != self._event_id and current.get("has_image"):
            self._event_id = event_id
            self._cached = None
            at = current.get("at", current.get("started"))
            self._attr_image_last_updated = (
                datetime.fromtimestamp(at, tz=timezone.utc) if at
                else datetime.now(timezone.utc))
        super()._handle_coordinator_update()

    async def async_image(self) -> bytes | None:
        if self._event_id is None:
            return None
        if self._cached is None:
            self._cached = await self.coordinator.client.event_image(self._event_id)
        return self._cached


class AeroLastEventImage(_AeroEventBoundImage):
    """The crop Aero saved for the latest event on this camera."""

    _attr_name = "Last event image"
    _attr_content_type = "image/jpeg"
    _state_key = "last_event"

    def __init__(self, hass: HomeAssistant, coordinator, camera_id: str):
        super().__init__(hass, coordinator, camera_id, "last_event_image")

    @property
    def extra_state_attributes(self) -> dict:
        event = self._current
        return {"event_id": event.get("id"), "label": event.get("label")}


class AeroLastRecognizedFaceImage(_AeroEventBoundImage):
    """The photo behind sensor.*_last_recognized_person."""

    _attr_name = "Last recognized person image"
    _attr_content_type = "image/jpeg"
    _attr_entity_registry_enabled_default = False
    _state_key = "last_recognized_face"

    def __init__(self, hass: HomeAssistant, coordinator, camera_id: str):
        super().__init__(hass, coordinator, camera_id, "last_recognized_face_image")


class AeroLastPlateReadImage(_AeroEventBoundImage):
    """The photo behind sensor.*_last_plate_read."""

    _attr_name = "Last plate read image"
    _attr_content_type = "image/jpeg"
    _attr_entity_registry_enabled_default = False
    _state_key = "last_plate_read"

    def __init__(self, hass: HomeAssistant, coordinator, camera_id: str):
        super().__init__(hass, coordinator, camera_id, "last_plate_read_image")
