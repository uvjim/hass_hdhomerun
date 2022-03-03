""""""

# region #-- imports --#
from datetime import (
    date,
    datetime,
)
from typing import (
    Any,
    List,
    Mapping,
    Optional,
    Union,
)

from homeassistant.components.sensor import SensorEntity, StateType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import slugify

from .const import (
    CONF_DATA_COORDINATOR,
    DOMAIN,
    ENTITY_SLUG,
)
from .entity_helpers import (
    HDHomerunEntity,
    HDHomerunSensorEntityDescription,
    SENSORS,
)
# endregion


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the sensor"""

    coordinator = hass.data[DOMAIN][config_entry.entry_id][CONF_DATA_COORDINATOR]

    sensors: List[HDHomerunSensor] = [
        HDHomerunSensor(
            config_entry=config_entry,
            coordinator=coordinator,
            description=description,
        )
        for description in SENSORS
    ]

    async_add_entities(sensors, update_before_add=True)


class HDHomerunSensor(HDHomerunEntity, SensorEntity):
    """"""

    def __init__(
        self,
        config_entry: ConfigEntry,
        coordinator: DataUpdateCoordinator,
        description: HDHomerunSensorEntityDescription
    ) -> None:
        """"""

        super().__init__(coordinator=coordinator, config_entry=config_entry)

        self.entity_description: HDHomerunSensorEntityDescription = description

        self._attr_name = f"{ENTITY_SLUG} {config_entry.title.replace(ENTITY_SLUG, '')}: {self.entity_description.name}"
        self._attr_unique_id = f"{config_entry.unique_id}::sensor::{slugify(self.entity_description.name)}"

    # region #-- properties --#
    @property
    def extra_state_attributes(self) -> Optional[Mapping[str, Any]]:
        """"""

        if self.entity_description.extra_state_attributes:
            if self.coordinator.data:
                data = self.coordinator.data.get(self.entity_description.query_location)
                return self.entity_description.extra_state_attributes(data)
            else:
                return None
        else:
            return None

    @property
    def native_value(self) -> Union[StateType, date, datetime]:
        """"""

        if self.coordinator.data:
            data = self.coordinator.data.get(self.entity_description.query_location)
            if data:
                if self.entity_description.state_value:
                    return self.entity_description.state_value(data)
                else:
                    return data.get(self.entity_description.key)
            else:
                return None
        else:
            return None
    # endregion
