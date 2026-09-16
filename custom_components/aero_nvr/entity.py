"""Shared entity base: device grouping and availability."""
from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AeroCoordinator


class AeroCameraEntity(CoordinatorEntity[AeroCoordinator]):
    """An entity belonging to one camera.

    Every camera is its own device, hung off the NVR device via `via_device`, so
    a dashboard can show one camera's entities together and removing a camera in
    Aero takes its whole device with it.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator: AeroCoordinator, camera_id: str, key: str) -> None:
        super().__init__(coordinator)
        self._camera_id = camera_id
        self._key = key
        server_id = coordinator.config_entry.data["server_id"]
        # Keyed on Aero's own server_id and camera id, never on host or name:
        # the box changing address or a camera being renamed must not orphan
        # entities the user has already put on dashboards.
        self._attr_unique_id = f"{server_id}_{camera_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{server_id}_camera_{camera_id}")},
            name=self.camera.get("name") or f"Camera {camera_id}",
            manufacturer="Aero NVR",
            model="Camera",
            via_device=(DOMAIN, server_id),
        )

    @property
    def camera(self) -> dict[str, Any]:
        return self.coordinator.cameras.get(self._camera_id, {})

    @property
    def state_data(self) -> dict[str, Any]:
        return self.coordinator.camera_state(self._camera_id)

    @property
    def available(self) -> bool:
        # Two different failures, deliberately kept apart: the poll failing means
        # the NVR is unreachable, while `healthy` false means the NVR is fine and
        # this one camera's analysis worker has stalled. Reporting the second as
        # "off" would be a lie -- nothing is known, so the entity is unavailable.
        if not self.coordinator.last_update_success:
            return False
        return bool(self.state_data)
