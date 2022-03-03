""""""

# region #-- imports --#
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

from .const import (
    DEF_DISCOVER,
    DEF_LINEUP,
    DOMAIN,
)
# endregion


# region #-- Binary Sensors --#
@dataclass
class OptionalHDHomerunBinarySensorDescription:
    """Represent the required attributes of the binary_sensor description."""

    state_value: Optional[Callable[[Any], bool]] = None


@dataclass
class RequiredHDHomerunBinarySensorDescription:
    """Represent the required attributes of the sensor description."""

    query_location: str


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
        query_location=DEF_DISCOVER,
        state_value=lambda d: bool(d.get("UpgradeAvailable")),
    ),
)
# endregion


# region #-- Sensors --#
@dataclass
class RequiredHDHomerunSensorDescription:
    """Represent the required attributes of the sensor description."""

    query_location: str


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
        query_location=DEF_LINEUP,
        key="",
        name="Channel Count",
        state_value=lambda d: len(d)
    ),
    HDHomerunSensorEntityDescription(
        query_location=DEF_DISCOVER,
        key="FirmwareVersion",
        name="Version",
    ),
    HDHomerunSensorEntityDescription(
        query_location=DEF_DISCOVER,
        key="TunerCount",
        name="Tuner Count",
    ),
    HDHomerunSensorEntityDescription(
        query_location=DEF_DISCOVER,
        key="",
        name="Newest Version",
        state_value=lambda d: d.get("UpgradeAvailable", d.get("FirmwareVersion"))
    ),
)


class HDHomerunEntity(CoordinatorEntity):
    """"""

    def __init__(self, coordinator: DataUpdateCoordinator, config_entry: ConfigEntry) -> None:
        """Initialize a Pi-hole entity."""
        super().__init__(coordinator)
        self._config: ConfigEntry = config_entry

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device information of the entity."""

        discover_data: dict = {}
        if self.coordinator.data:
            discover_data = self.coordinator.data.get(DEF_DISCOVER, {})

        # noinspection HttpUrlsUsage
        return DeviceInfo(
            configuration_url=f"http://{self._config.data.get('host')}",
            identifiers={(DOMAIN, self._config.unique_id)},
            manufacturer="SiliconDust",
            model=discover_data.get("ModelNumber"),
            name=self._config.title,
            sw_version=discover_data.get("FirmwareVersion"),
        )
# endregion
