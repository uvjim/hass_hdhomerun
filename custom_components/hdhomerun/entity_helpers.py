""""""

# region #-- imports --#
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import DOMAIN
from .hdhomerun import HDHomeRunDevice
# endregion


# region #-- base entity --#
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
