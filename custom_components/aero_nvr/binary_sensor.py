"""Motion and per-class occupancy."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass, BinarySensorEntity)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import AeroConfigEntry
from .const import OBJECT_CLASSES
from .entity import AeroCameraEntity


async def async_setup_entry(hass: HomeAssistant, entry: AeroConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = []
    for camera_id in coordinator.cameras:
        entities.append(AeroMotion(coordinator, camera_id))
        for label in OBJECT_CLASSES:
            entities.append(AeroObjectPresence(coordinator, camera_id, label))
        entities.append(AeroCameraHealth(coordinator, camera_id))
    async_add_entities(entities)


class AeroMotion(AeroCameraEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.MOTION
    _attr_name = "Motion"

    def __init__(self, coordinator, camera_id):
        super().__init__(coordinator, camera_id, "motion")

    @property
    def is_on(self) -> bool:
        return bool(self.state_data.get("motion"))

    @property
    def extra_state_attributes(self) -> dict:
        return {"last_motion": self.state_data.get("last_motion")}


class AeroObjectPresence(AeroCameraEntity, BinarySensorEntity):
    """On while Aero is tracking at least one object of this class."""

    def __init__(self, coordinator, camera_id, label: str):
        super().__init__(coordinator, camera_id, f"{label}_present")
        self._label = label
        self._attr_name = f"{label.capitalize()} detected"
        self._attr_device_class = BinarySensorDeviceClass(OBJECT_CLASSES[label])

    @property
    def is_on(self) -> bool:
        return bool(self.state_data.get("objects", {}).get(self._label))

    @property
    def available(self) -> bool:
        # A class the user switched off in Aero reports nothing, which is not
        # the same as reporting nothing is there.
        if not super().available:
            return False
        detection = self.camera.get("detection", {})
        enabled = {"person": "people", "car": "cars", "animal": "animals"}[self._label]
        return bool(detection.get(enabled)) and bool(
            self.state_data.get("detection_online", True))

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "count": self.state_data.get("objects", {}).get(self._label, 0),
            "moving": self.state_data.get("moving", {}).get(self._label, 0),
        }


class AeroCameraHealth(AeroCameraEntity, BinarySensorEntity):
    """Whether this camera's analysis worker is running.

    Separate from "recording enabled" on purpose: a camera set to record whose
    worker has stalled is the failure that looks fine on a dashboard and quietly
    writes nothing.
    """

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_name = "Problem"
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator, camera_id):
        super().__init__(coordinator, camera_id, "problem")

    @property
    def is_on(self) -> bool:
        return not self.state_data.get("healthy", True)
