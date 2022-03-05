"""Constants for HDHomeRun"""

# region #-- imports --#
from homeassistant.components.binary_sensor import DOMAIN as BINARY_SENSOR_DOMAIN
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
# endregion

DOMAIN: str = "hdhomerun"
ENTITY_SLUG: str = "HDHomeRun"

DEF_SCAN_INTERVAL_SECS: int = 300
DEF_SCAN_INTERVAL_TUNER_STATUS_SECS: int = 10

CONF_DATA_COORDINATOR_GENERAL: str = "data_coordinator_general"
CONF_DATA_COORDINATOR_TUNER_STATUS: str = "data_coordinaror_tuner_status"
CONF_HOST: str = "host"
CONF_SCAN_INTERVAL_TUNER_STATUS: str = "scan_interval_tuner_status"

PLATFORMS = [
    BINARY_SENSOR_DOMAIN,
    SENSOR_DOMAIN,
]
