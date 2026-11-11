"""Update entities."""

# region #-- imports --#
from __future__ import annotations

import asyncio
from abc import ABC
from typing import Any

import aiohttp

from homeassistant.components.update import DOMAIN as ENTITY_DOMAIN
from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityDescription,
    UpdateEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from . import HDHomerunEntity
from .const import CONF_DATA_COORDINATOR_GENERAL, DOMAIN
from .pyhdhr.const import DiscoverMode

# Captured on a HDHR5-4DT: ~24 s flashing, then 5-7 s without answering.
# shortcut: one missed probe counts as the restart, so a network blip while
# flashing would fail the install early; require consecutive misses if that bites.
INSTALL_POLL_SECS: int = 2
INSTALL_PROBE_TIMEOUT_SECS: int = 2
# Generous in case the device still has to download the release.
INSTALL_TIMEOUT_SECS: int = 10 * 60

# endregion


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the update entity."""
    coordinator_general: DataUpdateCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ][CONF_DATA_COORDINATOR_GENERAL]

    # region #-- add default sensors --#
    update_entities: list[HDHomerunUpdate] = []

    if coordinator_general.data.discovery_method is DiscoverMode.HTTP:
        update_entities.append(
            HDHomerunUpdate(
                config_entry=config_entry,
                coordinator=coordinator_general,
                description=UpdateEntityDescription(
                    device_class=UpdateDeviceClass.FIRMWARE,
                    key="",
                    name="Update",
                    translation_key="update",
                ),
            )
        )
    # endregion

    async_add_entities(update_entities)


# region #-- update classes --#
class HDHomerunUpdate(HDHomerunEntity, UpdateEntity, ABC):
    """Representation of an HDHomeRun update entity."""

    _attr_supported_features = UpdateEntityFeature.INSTALL

    def __init__(
        self,
        config_entry: ConfigEntry,
        coordinator: DataUpdateCoordinator,
        description: UpdateEntityDescription,
    ) -> None:
        """Initialise."""
        self.entity_domain = ENTITY_DOMAIN
        super().__init__(
            config_entry=config_entry,
            coordinator=coordinator,
            description=description,
        )

    async def async_install(
        self, version: str | None, backup: bool, **kwargs: Any
    ) -> None:
        """Install the pending firmware and wait for the device to report it."""
        device = self.coordinator.data
        target: str | None = device.latest_version
        if not target:
            raise HomeAssistantError("No firmware update is available")

        try:
            await device.async_upgrade_install()
        except aiohttp.ClientError as err:
            raise HomeAssistantError(
                f"The device rejected the install request: {err}"
            ) from err

        # The device keeps serving the old version while it flashes, then stops
        # answering while it restarts. Coordinator refreshes just stall through
        # that gap, so probe with a short timeout to see the restart happen.
        restarted = False
        reported: str | None = None
        try:
            async with asyncio.timeout(INSTALL_TIMEOUT_SECS):
                while reported != target and not (restarted and reported):
                    await asyncio.sleep(INSTALL_POLL_SECS)
                    try:
                        reported = await device.async_get_firmware_version(
                            timeout=INSTALL_PROBE_TIMEOUT_SECS
                        )
                    except (aiohttp.ClientError, TimeoutError):
                        restarted, reported = True, None
        except TimeoutError:
            minutes = INSTALL_TIMEOUT_SECS // 60
            raise HomeAssistantError(
                f"The device restarted but did not come back within {minutes} minutes"
                if restarted
                else f"The device did not restart to install {target} within"
                f" {minutes} minutes"
            ) from None

        # Only once the device answers: a refresh of an unresponsive device can hang.
        await self.coordinator.async_refresh()
        if reported != target:
            raise HomeAssistantError(
                f"The device restarted on firmware {reported} instead of {target}"
            )

    @property
    def installed_version(self) -> str | None:
        """Get the currently installed firmware version."""
        return self.coordinator.data.installed_version

    @property
    def latest_version(self) -> str | None:
        """Get the latest available version of the firmware.

        N.B. this is set to the currently installed version if not found
        """
        return self.coordinator.data.latest_version or self.installed_version

    @property
    def release_url(self) -> str | None:
        """Get the URL to release notes."""
        return "https://www.silicondust.com/support/downloads/firmware-changelog/"


# endregion
