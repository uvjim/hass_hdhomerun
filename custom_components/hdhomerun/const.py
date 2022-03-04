"""Constants for HDHomeRun"""

# region #-- imports --#
from homeassistant.components.binary_sensor import DOMAIN as BINARY_SENSOR_DOMAIN
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
# endregion

DOMAIN: str = "hdhomerun"
ENTITY_SLUG: str = "HDHomeRun"

CONF_DATA_COORDINATOR: str = "data_coordinator"
CONF_HOST: str = "host"

DEF_DISCOVER: str = "discover.json"
DEF_LINEUP: str = "lineup.json"
DEF_TUNER_STATUS: str = "status.json"
DEF_TUNER_STATUS_MIN_FIRMWARE: int = 20190417

DEF_DISCOVER_CURRENT_FIRMWARE: str = "FirmwareVersion"
DEF_DISCOVER_UPGRADE_FIRMWARE: str = "UpgradeAvailable"

PLATFORMS = [
    BINARY_SENSOR_DOMAIN,
    SENSOR_DOMAIN,
]
