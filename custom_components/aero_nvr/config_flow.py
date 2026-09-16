"""Setup and reauth flow."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_TOKEN
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AeroAuthError, AeroClient, AeroError, AeroUnavailable
from .const import API_VERSION, CONF_SERVER_ID, CONF_VERIFY_SSL, DEFAULT_PORT, DOMAIN

_LOGGER = logging.getLogger(__name__)

SCHEMA = vol.Schema({
    vol.Required(CONF_HOST): str,
    vol.Required(CONF_TOKEN): str,
    vol.Optional(CONF_VERIFY_SSL, default=True): bool,
})


def _normalise(host: str) -> str:
    """Accept what people actually paste: bare IPs, hosts, or full URLs."""
    host = host.strip().rstrip("/")
    if not host.startswith(("http://", "https://")):
        host = f"http://{host}"
    # A bare host with no port means the Aero default rather than 80, because
    # that is where it serves and typing the port is the step people forget.
    remainder = host.split("://", 1)[1]
    if ":" not in remainder.split("/")[0]:
        host = f"{host}:{DEFAULT_PORT}"
    return host


class AeroConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._reauth_entry = None

    async def _validate(self, user_input: dict[str, Any]) -> tuple[dict, dict]:
        """Returns (info, errors)."""
        host = _normalise(user_input[CONF_HOST])
        client = AeroClient(
            async_get_clientsession(self.hass), host, user_input[CONF_TOKEN],
            user_input.get(CONF_VERIFY_SSL, True))
        try:
            info = await client.info()
        except AeroAuthError:
            return {}, {"base": "invalid_auth"}
        except AeroUnavailable:
            return {}, {"base": "addon_missing"}
        except AeroError:
            return {}, {"base": "cannot_connect"}

        if info.get("api_version") != API_VERSION:
            return info, {"base": "unsupported_version"}
        if not info.get("server_id"):
            return info, {"base": "cannot_connect"}
        return info, {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None
                              ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            info, errors = await self._validate(user_input)
            if not errors:
                # Identity comes from Aero, not the address, so re-adding the
                # same NVR by hostname when it was added by IP is caught here
                # instead of producing a duplicate set of every entity.
                await self.async_set_unique_id(info["server_id"])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=info.get("name") or "Aero NVR",
                    data={
                        CONF_HOST: _normalise(user_input[CONF_HOST]),
                        CONF_TOKEN: user_input[CONF_TOKEN],
                        CONF_VERIFY_SSL: user_input.get(CONF_VERIFY_SSL, True),
                        CONF_SERVER_ID: info["server_id"],
                    },
                )
        return self.async_show_form(step_id="user", data_schema=SCHEMA, errors=errors)

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"])
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None
                                        ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._reauth_entry
        if user_input is not None and entry is not None:
            candidate = {**entry.data, CONF_TOKEN: user_input[CONF_TOKEN]}
            info, errors = await self._validate(candidate)
            if not errors:
                if info.get("server_id") != entry.data.get(CONF_SERVER_ID):
                    # A token for a *different* NVR would silently repoint every
                    # entity at another box's cameras.
                    errors = {"base": "wrong_server"}
                else:
                    return self.async_update_reload_and_abort(entry, data=candidate)
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_TOKEN): str}),
            errors=errors,
        )
