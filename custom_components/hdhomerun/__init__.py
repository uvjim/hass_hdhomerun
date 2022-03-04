""""""

# region #-- imports --#
import asyncio
import logging
from datetime import timedelta
from typing import (
    List,
    Optional,
)

import aiohttp
from aiohttp import ClientSession
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady, IntegrationError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_DATA_COORDINATOR,
    CONF_HOST,
    DEF_DISCOVER,
    DEF_DISCOVER_CURRENT_FIRMWARE,
    DEF_LINEUP,
    DEF_TUNER_STATUS,
    DEF_TUNER_STATUS_MIN_FIRMWARE,
    DOMAIN,
    PLATFORMS,
)
from .logger import HDHomerunLogger

# endregion

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Setup a config entry"""

    log_formatter = HDHomerunLogger(unique_id=config_entry.unique_id)
    _LOGGER.debug(log_formatter.message_format("entered"))

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault(config_entry.entry_id, {})

    async def _async_get_details(urls: Optional[List] = None) -> dict:
        """Gather all the details required by the coordinator

        :param urls: list of urls that need to be queried
        :return: a dictionary of the results in the following format
                 {
                    url_name: json results as returned by the call
                 }
        """

        if urls is None:
            urls = [
                DEF_DISCOVER,
                DEF_LINEUP,
                DEF_TUNER_STATUS,
            ]

        session: ClientSession = async_get_clientsession(hass=hass)
        tasks: List[asyncio.Task] = []

        for url in urls:
            # noinspection HttpUrlsUsage
            tasks.append(
                asyncio.ensure_future(
                    loop=hass.loop,
                    coro_or_future=session.get(f"http://{config_entry.data.get(CONF_HOST)}/{url}")
                )
            )
        results = await asyncio.gather(*tasks)
        result: aiohttp.ClientResponse
        ret: dict = {}

        # region #-- build response --#
        r: aiohttp.ClientResponse
        for result in [r for r in results if r.ok]:
            ret[result.url.name] = await result.json()
        # endregion

        # region #-- check for errors --#
        url_errors = [result for result in results if not result.ok]
        if len(url_errors) == len(urls):
            raise IntegrationError("No successful response from the device")
        elif len(url_errors):
            for url_err in url_errors:
                msg: str = ""
                if url_err.url.name == DEF_DISCOVER:
                    msg = f"Unable to retrieve information about the device."
                if url_err.url.name == DEF_LINEUP:
                    msg = f"Unable to currently tuned channels."
                if url_err.url.name == DEF_TUNER_STATUS:
                    current_firmware = ret.get(DEF_DISCOVER, {}).get(DEF_DISCOVER_CURRENT_FIRMWARE)
                    msg = f"Unable to retrieve tuner information. Your current firmware level is: {current_firmware}." \
                          f" Support was added in {DEF_TUNER_STATUS_MIN_FIRMWARE}."
                _LOGGER.warning(log_formatter.message_format(msg))
        # endregion

        return ret

    try:
        await _async_get_details(urls=[DEF_DISCOVER])
    except Exception as err:
        raise ConfigEntryNotReady from err

    # region #-- set up the coordinator --#
    coordinator: DataUpdateCoordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=_async_get_details,
        update_interval=timedelta(minutes=5),
    )
    hass.data[DOMAIN][config_entry.entry_id] = {CONF_DATA_COORDINATOR: coordinator}
    # endregion

    # region #-- setup the platforms --#
    setup_platforms: List[str] = list(filter(None, PLATFORMS))
    _LOGGER.debug(log_formatter.message_format("setting up platforms: %s"), setup_platforms)
    hass.config_entries.async_setup_platforms(config_entry, setup_platforms)
    # endregion

    _LOGGER.debug(log_formatter.message_format("exited"))
    return True
