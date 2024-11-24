"""Select entity."""

# region #-- imports --#
from __future__ import annotations

import dataclasses
from typing import Any, Callable

from homeassistant.components.select import DOMAIN as ENTITY_DOMAIN
from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from . import HDHomerunEntity
from .const import (
    CONF_DATA_COORDINATOR_GENERAL,
    DOMAIN,
    SIGNAL_HDHOMERUN_CHANNEL_SOURCE_CHANGE,
)

# endregion


# region #-- select entity descriptions --#
@dataclasses.dataclass(frozen=True)
class AdditionalSelectDescription:
    """Represent additional options for the select entity."""

    custom_options: Callable[[Any], list[str]] | list[str] = dataclasses.field(
        default_factory=list
    )


# endregion


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the entities."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id][
        CONF_DATA_COORDINATOR_GENERAL
    ]

    selects: list[HDHomeRunSelect] = []

    if coordinator.data.channel_sources:
        selects.append(
            HDHomeRunSelect(
                config_entry=config_entry,
                coordinator=coordinator,
                description=SelectEntityDescription(
                    entity_category=EntityCategory.CONFIG,
                    key="channel_sources",
                    name="Channel Sources",
                    translation_key="channel_sources",
                ),
            )
        )

    async_add_entities(selects)


class HDHomeRunSelect(HDHomerunEntity, SelectEntity):
    """Representation for a select entity."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        config_entry: ConfigEntry,
        description: SelectEntityDescription,
        additional_description: AdditionalSelectDescription | None = None,
    ) -> None:
        """Initialise."""
        self._additional_description: AdditionalSelectDescription | None = (
            additional_description
        )
        self._attr_current_option = None
        self.entity_domain = ENTITY_DOMAIN

        super().__init__(
            config_entry=config_entry,
            coordinator=coordinator,
            description=description,
        )

    async def async_select_option(self, option: str) -> None:
        """Select the option."""
        self._attr_current_option = option
        await self.async_update_ha_state()
        async_dispatcher_send(
            self.hass,
            SIGNAL_HDHOMERUN_CHANNEL_SOURCE_CHANGE,
            self._attr_current_option,
        )

    @property
    def options(self) -> list[str] | None:
        """Build the options for the select."""
        if self.entity_description.key:
            return getattr(self.coordinator.data, self.entity_description.key, None)

        if isinstance(self._additional_description.custom_options, Callable):
            return self._additional_description.custom_options(self.coordinator.data)

        return (
            self._additional_description.custom_options
            or self.entity_description.options
        )
