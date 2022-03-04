""""""

# region #-- imports --#
import logging
from dataclasses import dataclass
from typing import (
    Any,
    Callable,
    Mapping,
    Optional,
)

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntityDescription,
)
from homeassistant.components.sensor import SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import DOMAIN
from .hdhomerun import (
    HDHomeRunDevice,
)

# endregion


_LOGGER = logging.getLogger(__name__)


# region #-- Binary Sensors --#
@dataclass
class OptionalHDHomerunBinarySensorDescription:
    """Represent the required attributes of the binary_sensor description."""

    state_value: Optional[Callable[[Any], bool]] = None


@dataclass
class RequiredHDHomerunBinarySensorDescription:
    """Represent the required attributes of the sensor description."""


@dataclass
class HDHomerunBinarySensorEntityDescription(
    OptionalHDHomerunBinarySensorDescription,
    BinarySensorEntityDescription,
    RequiredHDHomerunBinarySensorDescription,
):
    """Describes binary_sensor entity."""


BINARY_SENSORS: tuple[HDHomerunBinarySensorEntityDescription, ...] = (
    HDHomerunBinarySensorEntityDescription(
        key="",
        name="Update available",
        device_class=BinarySensorDeviceClass.UPDATE,
        state_value=lambda d: bool(d.latest_firmware),
    ),
)
# endregion


# region #-- Sensors --#
@dataclass
class RequiredHDHomerunSensorDescription:
    """Represent the required attributes of the sensor description."""


@dataclass
class OptionalHDHomerunSensorDescription:
    """Represent the optional attributes of the sensor description."""

    extra_state_attributes: Optional[Callable[[Any], Optional[Mapping[str, Any]]]] = None
    state_value: Optional[Callable[[Any], Any]] = None


@dataclass
class HDHomerunSensorEntityDescription(
    OptionalHDHomerunSensorDescription,
    SensorEntityDescription,
    RequiredHDHomerunSensorDescription
):
    """Describes sensor entity."""


SENSORS: tuple[HDHomerunSensorEntityDescription, ...] = (
    HDHomerunSensorEntityDescription(
        key="channels",
        name="Channel Count",
        state_value=lambda d: len(d)
    ),
    HDHomerunSensorEntityDescription(
        key="current_firmware",
        name="Version",
    ),
    HDHomerunSensorEntityDescription(
        key="tuner_count",
        name="Tuner Count",
    ),
    HDHomerunSensorEntityDescription(
        key="",
        name="Newest Version",
        state_value=lambda d: d.latest_firmware or d.current_firmware
    ),
)


class HDHomerunEntity(CoordinatorEntity):
    """"""

    def __init__(self, coordinator: DataUpdateCoordinator, config_entry: ConfigEntry) -> None:
        """Initialize the entity"""

        super().__init__(coordinator)
        self._config: ConfigEntry = config_entry
        self._data: HDHomeRunDevice = self.coordinator.data

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device information of the entity."""

        # noinspection HttpUrlsUsage
        return DeviceInfo(
            configuration_url=f"http://{self._config.data.get('host')}",
            identifiers={(DOMAIN, self._config.unique_id)},
            manufacturer="SiliconDust",
            model=self._data.model if self._data else "",
            name=self._config.title,
            sw_version=self._data.current_firmware if self._data else "",
        )
# endregion
