"""Provice UI for configuring the integration"""

# region #-- imports --#
import asyncio
import json
import logging
from typing import Optional
from urllib.parse import urlparse

import aiohttp.client_exceptions
from aiohttp import ClientSession

import voluptuous as vol
from homeassistant import (
    config_entries,
    data_entry_flow,
)
from homeassistant.components import ssdp
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_HOST,
    DEF_DISCOVER,
    DOMAIN,
)
from .logger import HDHomerunLogger

# endregion


_LOGGER = logging.getLogger(__name__)

CONF_FRIENDLY_NAME: str = "friendly_name"
STEP_CONFIRM: str = "confirm"
STEP_DETAILS: str = "details"
STEP_FINISH: str = "finish"
STEP_USER: str = "user"


async def _async_build_schema_with_user_input(step: str, user_input: dict) -> vol.Schema:
    """Build the input and validation schema for the config UI

    :param step: the step we're in for a configuration or installation of the integration
    :param user_input: the data that should be used as defaults
    :return: the schema including necessary restrictions, defaults, pre-selections etc.
    """

    schema = {}
    if step == STEP_USER:
        schema = {
            vol.Optional(
                CONF_FRIENDLY_NAME,
                default=user_input.get(CONF_FRIENDLY_NAME, "")
            ): str,
            vol.Required(
                CONF_HOST,
                default=user_input.get(CONF_HOST, "")
            ): str,
        }

    return vol.Schema(schema)


class HDHomerunConfigFlow(config_entries.ConfigFlow, HDHomerunLogger, domain=DOMAIN):
    """"""

    def __init__(self):
        """"""

        HDHomerunLogger.__init__(self)

        self._errors: dict = {}
        self._error_message: str = ""
        self._friendly_name: str = ""
        self._host: str = ""
        self._serial: str = ""
        self._task_details: Optional[asyncio.Task] = None

    async def _async_get_details(self) -> None:
        """"""

        _LOGGER.debug(self.message_format("entered"))
        session: ClientSession = async_get_clientsession(hass=self.hass)
        try:
            # noinspection HttpUrlsUsage
            async with session.get(f"http://{self._host}/{DEF_DISCOVER}", raise_for_status=True) as resp:
                json_details: dict = await resp.json()
        except OSError as err:
            if err.errno == 113:
                self._errors["base"] = "connection_error"
        except aiohttp.client_exceptions.ClientResponseError as err:
            self._errors["base"] = "client_response_error"
            self._error_message = f"{err.status} - {err.message}"
        except Exception as err:
            self._errors["base"] = str(err)
            _LOGGER.debug(self.message_format("%s"), err)
        else:
            await asyncio.sleep(1)
            _LOGGER.debug(self.message_format("json_details: %s"), json_details)
            if not self._friendly_name:
                self._friendly_name = f"{json_details.get('FriendlyName', '')} {json_details.get('DeviceID', '')}"
            self._serial = json_details.get("DeviceID", "")

            # region #-- raise errors with response --#
            if not self._serial:
                self._errors["base"] = "invalid_serial"
                self._error_message = f"serial={self._serial}"
            # endregion

        self.hass.async_create_task(self.hass.config_entries.flow.async_configure(flow_id=self.flow_id))
        _LOGGER.debug(self.message_format("exited"))

    async def async_step_confirm(self, user_input=None) -> data_entry_flow.FlowResult:
        """Allow the user to confirm adding the device."""

        _LOGGER.debug(self.message_format("entered, user_input: %s"), user_input)

        if user_input is not None:
            return await self.async_step_finish()

        self._set_confirm_only()
        return self.async_show_form(step_id=STEP_CONFIRM)

    async def async_step_details(self, user_input=None) -> data_entry_flow.FlowResult:
        """"""

        _LOGGER.debug(self.message_format("entered, user_input: %s"), user_input)
        if not self._task_details:
            _LOGGER.debug(self.message_format("creating task for gathering details"))
            self._task_details = self.hass.async_create_task(target=self._async_get_details())
            return self.async_show_progress(step_id=STEP_DETAILS, progress_action="_task_details")

        try:
            await self._task_details
        except Exception as err:
            _LOGGER.debug(self.message_format("exception: %s"), err)
            return self.async_abort(reason="abort_details")

        _LOGGER.debug(self.message_format("_errors: %s"), self._errors)
        if self._errors:
            return self.async_show_progress_done(next_step_id=STEP_USER)

        _LOGGER.debug(self.message_format("proceeding to next step"))
        return self.async_show_progress_done(next_step_id=STEP_FINISH)

    async def async_step_finish(self, _=None) -> data_entry_flow.FlowResult:
        """Finalise the configuration entry"""

        _LOGGER.debug(self.message_format("entered"))

        if not self.unique_id:
            await self.async_set_unique_id(unique_id=self._serial, raise_on_progress=False)
            self._abort_if_unique_id_configured(updates={CONF_HOST: self._host})

        data = {CONF_HOST: self._host}

        return self.async_create_entry(title=self._friendly_name or "HDHomerun", data=data)

    async def async_step_ssdp(self, discovery_info: ssdp.SsdpServiceInfo) -> data_entry_flow.FlowResult:
        """"""

        _LOGGER.debug(self.message_format("entered, discovery_info: %s"), discovery_info)

        # region #-- get the important information --#
        self._friendly_name = f"{discovery_info.upnp.get('modelName', '')} " \
                              f"{discovery_info.upnp.get('serialNumber', '')}"
        service_list = discovery_info.upnp.get("serviceList", {}).get("service")
        if service_list:
            _LOGGER.debug(self.message_format("%s"), json.dumps(service_list))
            service = service_list[0]
            self._host = urlparse(url=service.get("controlURL", "")).hostname
        self._serial: str = discovery_info.upnp.get("serialNumber", "")
        # endregion

        # region #-- set a unique_id, update details if device has changed IP --#
        _LOGGER.debug(self.message_format("setting unique_id: %s"), self._serial)
        await self.async_set_unique_id(unique_id=self._serial)
        self._abort_if_unique_id_configured(updates={CONF_HOST: self._host})
        # endregion

        self.context["title_placeholders"] = {"name": self._friendly_name}  # set the name of the flow

        return await self.async_step_confirm()

    async def async_step_user(self, user_input=None) -> data_entry_flow.FlowResult:
        """Handle a flow initiated by the user"""

        _LOGGER.debug(self.message_format("entered, user_input: %s"), user_input)

        if user_input is not None:
            self._errors = {}
            self._friendly_name = user_input.get(CONF_FRIENDLY_NAME, "")
            self._host = user_input.get(CONF_HOST, "")
            self._task_details = None
            return await self.async_step_details()

        return self.async_show_form(
            step_id=STEP_USER,
            data_schema=await _async_build_schema_with_user_input(
                STEP_USER,
                {
                    CONF_FRIENDLY_NAME: self._friendly_name,
                    CONF_HOST: self._host,
                }
            ),
            errors=self._errors,
            description_placeholders={
                "error_message": self._error_message
            }
        )
