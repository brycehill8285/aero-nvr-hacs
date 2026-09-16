"""Per-camera recording and detection switches."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import AeroConfigEntry
from .api import AeroError
from .const import SWITCHES
from .entity import AeroCameraEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: AeroConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    entities = [
        AeroSwitch(coordinator, camera_id, key, label)
        for camera_id in coordinator.cameras
        for key, label in SWITCHES.items()
    ]
    async_add_entities(entities)


class AeroSwitch(AeroCameraEntity, SwitchEntity):
    """One Aero setting.

    Toggling these is cheap by design: Aero's analysis worker re-reads them on a
    short interval and the recorder supervisor reconciles recording on each
    pass, so an automation flipping detection on a schedule does not interrupt
    the recording.
    """

    def __init__(self, coordinator, camera_id: str, key: str, label: str):
        super().__init__(coordinator, camera_id, f"switch_{key}")
        self._switch_key = key
        self._attr_name = label

    @property
    def is_on(self) -> bool:
        if self._switch_key == "recording":
            return bool(self.camera.get("recording"))
        return bool(self.camera.get("detection", {}).get(self._switch_key))

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)

    async def _set(self, value: bool) -> None:
        try:
            await self.coordinator.client.set_camera(
                int(self._camera_id), **{self._switch_key: value})
        except AeroError as err:
            raise HomeAssistantError(f"Aero refused the change: {err}") from err

        # The switch state lives in the camera roster, not in /state, so the
        # value is written back locally and the roster re-read. Without the
        # local write the toggle springs back in the UI until the next refresh.
        if self._switch_key == "recording":
            self.camera["recording"] = value
        else:
            self.camera.setdefault("detection", {})[self._switch_key] = value
        self.async_write_ha_state()
        await self.coordinator.async_refresh_cameras()
        self.async_write_ha_state()
