""""""

# region #-- imports --#
import logging
from datetime import timedelta
from typing import (
    List,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_DATA_COORDINATOR,
    CONF_HOST,
    DOMAIN,
    PLATFORMS,
)
from .hdhomerun import (
    DEF_DISCOVER,
    HDHomeRunDevice,
    HDHomeRunExceptionOldFirmware,
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

    hdhomerun_device = HDHomeRunDevice(
        host=config_entry.data.get(CONF_HOST),
        loop=hass.loop,
        session=async_get_clientsession(hass=hass),
    )
    try:
        await hdhomerun_device.get_details(include_discover=True)
    except Exception as err:
        raise ConfigEntryNotReady from err

    # region #-- set up the coordinator --#
    async def _async_data_coordinator_update() -> HDHomeRunDevice:
        """"""

        try:
            await hdhomerun_device.get_details(
                include_discover=True,
                include_lineups=True,
                include_tuner_status=True,
            )
        except HDHomeRunExceptionOldFirmware as exc:
            _LOGGER.warning(log_formatter.message_format("%s"), exc)

        return hdhomerun_device

    coordinator: DataUpdateCoordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=_async_data_coordinator_update,
        update_interval=timedelta(minutes=5),
    )
    hass.data[DOMAIN][config_entry.entry_id] = {CONF_DATA_COORDINATOR: coordinator}
    await coordinator.async_config_entry_first_refresh()
    # endregion

    # region #-- setup the platforms --#
    setup_platforms: List[str] = list(filter(None, PLATFORMS))
    _LOGGER.debug(log_formatter.message_format("setting up platforms: %s"), setup_platforms)
    hass.config_entries.async_setup_platforms(config_entry, setup_platforms)
    # endregion

    _LOGGER.debug(log_formatter.message_format("exited"))
    return True
