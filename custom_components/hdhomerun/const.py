"""Constants for HDHomeRun."""

# region #-- imports --#
from homeassistant.components.binary_sensor import DOMAIN as BINARY_SENSOR_DOMAIN
from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN
from homeassistant.components.select import DOMAIN as SELECT_DOMAIN
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.update import DOMAIN as UPDATE_DOMAIN

from .pyhdhr.const import DiscoverMode

# endregion

DOMAIN: str = "hdhomerun"

CONF_DATA_COORDINATOR_GENERAL: str = "data_coordinator_general"
CONF_DATA_COORDINATOR_TUNER_STATUS: str = "data_coordinaror_tuner_status"
CONF_DEVICE: str = "hdhomerun_device"
CONF_DISCOVERY_MODE: str = "discovery_mode"
CONF_HOST: str = "host"
CONF_SCAN_INTERVAL_TUNER_STATUS: str = "scan_interval_tuner_status"
CONF_TUNER_CHANNEL_ENTITY_PICTURE_PATH: str = "channel_entity_picture_path"
CONF_TUNER_CHANNEL_FORMAT: str = "channel_format"
CONF_TUNER_CHANNEL_NAME: str = "channel_name"
CONF_TUNER_CHANNEL_NUMBER_NAME: str = "channel_number_name"
CONF_TUNER_CHANNEL_NUMBER: str = "channel_number"

DEF_DISCOVERY_MODE: DiscoverMode = DiscoverMode.AUTO
DEF_SCAN_INTERVAL_SECS: int = 300
DEF_SCAN_INTERVAL_TUNER_STATUS_SECS: int = 10
DEF_TUNER_CHANNEL_ENTITY_PICTURE_PATH: str = ""
DEF_TUNER_CHANNEL_FORMAT: str = CONF_TUNER_CHANNEL_NAME

PLATFORMS = [
    BINARY_SENSOR_DOMAIN,
    BUTTON_DOMAIN,
    SELECT_DOMAIN,
    SENSOR_DOMAIN,
    UPDATE_DOMAIN,
]

SIGNAL_HDHOMERUN_CHANNEL_SCANNING_STARTED: str = f"{DOMAIN}_channel_scanning_started"
SIGNAL_HDHOMERUN_CHANNEL_SOURCE_CHANGE: str = f"{DOMAIN}_channel_source_changed"
