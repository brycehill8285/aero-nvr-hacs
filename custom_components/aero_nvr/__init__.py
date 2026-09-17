"""The Aero NVR integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_TOKEN, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceEntryType

from .api import AeroAuthError, AeroClient, AeroError
from .const import CONF_SERVER_ID, CONF_VERIFY_SSL, DOMAIN
from .coordinator import AeroCoordinator
from .media_proxy import AeroMediaProxyView

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.CAMERA,
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.IMAGE,
]

AeroConfigEntry = ConfigEntry[AeroCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: AeroConfigEntry) -> bool:
    client = AeroClient(
        async_get_clientsession(hass), entry.data[CONF_HOST], entry.data[CONF_TOKEN],
        entry.data.get(CONF_VERIFY_SSL, True))

    try:
        info = await client.info()
        cameras = (await client.cameras()).get("cameras", [])
    except AeroAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except AeroError as err:
        raise ConfigEntryNotReady(str(err)) from err

    coordinator = AeroCoordinator(hass, entry, client, cameras)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    # The NVR itself, so its diagnostics have somewhere to live and every camera
    # device can point at it as their parent.
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.data[CONF_SERVER_ID])},
        manufacturer="Aero NVR",
        name=info.get("name") or "Aero NVR",
        sw_version=info.get("version"),
        entry_type=DeviceEntryType.SERVICE,
        configuration_url=entry.data[CONF_HOST],
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))

    # One view serves every config entry (it takes entry_id in the URL), so it
    # is only ever registered once even with more than one Aero server added.
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}
    if not hass.data[DOMAIN].get("media_proxy_registered"):
        hass.http.register_view(AeroMediaProxyView(hass))
        hass.data[DOMAIN]["media_proxy_registered"] = True

    return True


async def _async_reload(hass: HomeAssistant, entry: AeroConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: AeroConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
