""""""

# region #-- imports --#
from datetime import (
    date,
    datetime,
)
from typing import (
    List,
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

    async_add_entities(sensors)


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
    def native_value(self) -> Union[StateType, date, datetime]:
        """"""

        if self._data:
            if self.entity_description.state_value:
                if self.entity_description.key:
                    return self.entity_description.state_value(getattr(self._data, self.entity_description.key, None))
                else:
                    return self.entity_description.state_value(self._data)
            else:
                return getattr(self._data, self.entity_description.key, None)
        else:
            return None
    # endregion
