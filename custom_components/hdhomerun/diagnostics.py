"""Diagnostics support."""

# region #-- imports --#
import logging
from typing import Any, Dict, List

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_DATA_COORDINATOR_GENERAL,
    CONF_DATA_COORDINATOR_TUNER_STATUS,
    DOMAIN,
)
from .pyhdhr.discover import HDHomeRunDevice

# endregion


_LOGGER = logging.getLogger(__name__)


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> Dict[str, Any]:
    """Diagnostics for the config entry."""
    props_to_remove: List[str] = [
        "_log_formatter",
        "_session",
    ]

    # region #-- get the device details --#
    device: HDHomeRunDevice | None = hass.data[DOMAIN][config_entry.entry_id][
        CONF_DATA_COORDINATOR_GENERAL
    ].data
    # endregion

    # region #-- get the tuner status details --#
    device_tuner_status: HDHomeRunDevice | None = hass.data[DOMAIN][
        config_entry.entry_id
    ][CONF_DATA_COORDINATOR_TUNER_STATUS].data
    # endregion

    diags = device.__dict__.copy()
    diags["tuner_status"] = device_tuner_status.tuner_status
    for prop in props_to_remove:
        diags.pop(prop, None)

    return async_redact_data(diags, to_redact=("_device_auth_str", "_device_id"))
