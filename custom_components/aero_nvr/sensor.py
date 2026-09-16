"""Counts, last event, and per-camera diagnostics."""
from __future__ import annotations

from datetime import datetime, timezone

from homeassistant.components.sensor import (
    SensorDeviceClass, SensorEntity, SensorStateClass)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import AeroConfigEntry
from .const import OBJECT_CLASSES
from .entity import AeroCameraEntity


async def async_setup_entry(hass: HomeAssistant, entry: AeroConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = []
    for camera_id in coordinator.cameras:
        for label in OBJECT_CLASSES:
            entities.append(AeroObjectCount(coordinator, camera_id, label))
        entities.append(AeroLastEvent(coordinator, camera_id))
        entities.append(AeroLastEventTime(coordinator, camera_id))
        entities.append(AeroDecoder(coordinator, camera_id))
    async_add_entities(entities)


class AeroObjectCount(AeroCameraEntity, SensorEntity):
    """How many of this class are on camera now.

    A count rather than a boolean because "two people" and "someone" are
    different automations, and a binary sensor can be derived from this while
    the reverse throws the information away.
    """

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, camera_id, label: str):
        super().__init__(coordinator, camera_id, f"{label}_count")
        self._label = label
        self._attr_name = f"{label.capitalize()} count"

    @property
    def native_value(self) -> int:
        return self.state_data.get("objects", {}).get(self._label, 0)


class AeroLastEvent(AeroCameraEntity, SensorEntity):
    """What Aero last recorded on this camera."""

    _attr_name = "Last event"

    def __init__(self, coordinator, camera_id):
        super().__init__(coordinator, camera_id, "last_event")

    @property
    def native_value(self) -> str | None:
        event = self.state_data.get("last_event")
        return event.get("label") if event else None

    @property
    def extra_state_attributes(self) -> dict:
        event = self.state_data.get("last_event") or {}
        return {
            "event_id": event.get("id"),
            "confidence": event.get("confidence"),
            "in_progress": event.get("in_progress"),
            "plate": event.get("plate"),
            "started": event.get("started"),
            "ended": event.get("ended"),
        }


class AeroLastEventTime(AeroCameraEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_name = "Last event time"

    def __init__(self, coordinator, camera_id):
        super().__init__(coordinator, camera_id, "last_event_time")

    @property
    def native_value(self) -> datetime | None:
        event = self.state_data.get("last_event")
        if not event or not event.get("started"):
            return None
        return datetime.fromtimestamp(event["started"], tz=timezone.utc)


class AeroDecoder(AeroCameraEntity, SensorEntity):
    """Which decoder this camera's main stream actually got.

    Diagnostic and off by default: it matters when a box silently falls back to
    software decode and the CPU climbs, and not at all otherwise.
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False
    _attr_name = "Decoder"

    def __init__(self, coordinator, camera_id):
        super().__init__(coordinator, camera_id, "decoder")

    @property
    def native_value(self) -> str | None:
        decode = self.camera.get("decode") or {}
        main = decode.get("main") or {}
        return main.get("decoder")

    @property
    def extra_state_attributes(self) -> dict:
        decode = self.camera.get("decode") or {}
        return {"on_gpu": (decode.get("main") or {}).get("on_gpu")}
