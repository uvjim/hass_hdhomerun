"""HDHomerun device."""

# region #-- imports --#
from __future__ import annotations

import asyncio
import logging
import struct
from enum import Enum, unique
from typing import Any, Dict, List
from urllib.parse import urlparse

import aiohttp

from .const import (
    HDHOMERUN_TAG_BASE_URL,
    HDHOMERUN_TAG_DEVICE_AUTH_STR,
    HDHOMERUN_TAG_DEVICE_ID,
    HDHOMERUN_TAG_DEVICE_TYPE,
    HDHOMERUN_TAG_GETSET_NAME,
    HDHOMERUN_TAG_GETSET_VALUE,
    HDHOMERUN_TAG_LINEUP_URL,
    HDHOMERUN_TAG_TUNER_COUNT,
    DiscoverMode,
)
from .logger import Logger
from .protocol import HDHomeRunProtocol

# endregion

_LOGGER = logging.getLogger(__name__)


class DevicePaths(str, Enum):
    """Available paths on the device."""

    DISCOVER = "discover.json"
    LINEUP = "lineup.json"
    LINEUP_ACTION = "lineup.post"
    LINEUP_STATUS = "lineup_status.json"
    TUNER_STATUS = "status.json"


@unique
class DeviceType(Enum):
    """Device types as defined by the protocol."""

    TUNER = 1
    STORAGE = 5


class HDHomeRunDevice:
    """Representation of a device."""

    def __del__(self) -> None:
        """Cleanup."""
        if self._session:
            asyncio.run_coroutine_threadsafe(
                coro=self._session.close(), loop=asyncio.get_event_loop()
            )

    def __init__(self, host: str) -> None:
        """Initialise."""
        self._discovery_method: DiscoverMode | None = None
        self._host: str = host
        self._log_formatter: Logger = Logger(unique_id=self._host)
        self._processed_datagram: Dict[str, Any]
        self._raw_details: Dict[str, Any] = {}
        self._session: aiohttp.ClientSession = aiohttp.ClientSession()

        self._base_url: str | None = None
        self._device_auth_str: str | None = None
        self._device_id: str | None = None
        self._device_type: str | None = None
        self._lineup_url: str | None = None
        self._sys_hwmodel: str | None = None
        self._sys_model: str | None = None
        self._sys_version: str | None = None
        self._tuner_count: int | None = None
        self._tuner_status: List[Dict[str, Any]] | None = None

    def __repr__(self) -> str:
        """Friendly representation of the device."""
        return f"{self.__class__.__name__} {self._host}"

    def get_from_datagram(self, tag: int) -> str | None:
        """Grab the data from the processed datagram."""
        ret: str | None = None
        value = self._processed_datagram.get("data", {}).get(tag, b"")
        if tag == HDHOMERUN_TAG_BASE_URL:
            ret = value.decode()
        elif tag == HDHOMERUN_TAG_DEVICE_AUTH_STR:
            ret = value.decode()
        elif tag == HDHOMERUN_TAG_DEVICE_ID:
            (property_value,) = struct.unpack(">L", value)
            ret = f"{property_value:04X}"
        elif tag == HDHOMERUN_TAG_DEVICE_TYPE:
            (ret,) = struct.unpack(">L", value)
        elif tag == HDHOMERUN_TAG_LINEUP_URL:
            ret = value.decode()
        elif tag == HDHOMERUN_TAG_TUNER_COUNT:
            (ret,) = struct.unpack(">B", value)

        return ret

    async def _async_gather_details_http(self) -> None:
        """Gather details for an HTTP discovered device."""
        requests: List[aiohttp.ClientRequest] = [
            self._session.get(
                url=f"http://{self.ip}/{DevicePaths.DISCOVER}", raise_for_status=True
            ),
            self._session.get(
                url=f"http://{self.ip}/{DevicePaths.LINEUP}", raise_for_status=True
            ),
            self._session.get(
                url=f"http://{self.ip}/{DevicePaths.LINEUP_STATUS}",
                raise_for_status=True,
            ),
        ]

        responses: List[aiohttp.ClientResponse] = await asyncio.gather(*requests)
        for resp in responses:
            key: str = resp.url.name.split(".")[0]
            self._raw_details[key] = await resp.json()

    async def _async_gather_details_udp(self) -> None:
        """Gather details via TCP/UDP for a UDP discovered device."""
        from .discover import Discover  # pylint: disable=import-outside-toplevel

        # region #-- get the properties available from a discovery --#
        updated_device: List[HDHomeRunDevice] | HDHomeRunDevice = await Discover(
            broadcast_address=self.ip, mode=DiscoverMode.UDP
        ).async_discover()
        if updated_device:
            updated_device = updated_device[0]
            for tag in getattr(updated_device, "_processed_datagram", {}).get("data"):
                value = self.get_from_datagram(tag=tag)
                if tag == HDHOMERUN_TAG_BASE_URL:
                    self._base_url = value
                elif tag == HDHOMERUN_TAG_DEVICE_AUTH_STR:
                    self._device_auth_str = value
                elif tag == HDHOMERUN_TAG_DEVICE_ID:
                    self._device_id = value
                elif tag == HDHOMERUN_TAG_DEVICE_TYPE:
                    self._device_type = value
                elif tag == HDHOMERUN_TAG_LINEUP_URL:
                    self._lineup_url = value
                elif tag == HDHOMERUN_TAG_TUNER_COUNT:
                    self._tuner_count = value
        # endregion

        # region #-- get the details from the control protocol --#
        protocol: HDHomeRunProtocol = HDHomeRunProtocol(host=self.ip)
        supplemental_info = [
            protocol.async_get_version(),
            protocol.async_get_model(),
            protocol.async_get_hwmodel(),
        ]
        info = await asyncio.gather(*supplemental_info)
        prop: Dict[str, Dict[int | str, bytes]]
        for prop in info:
            tcp_prop_name = (
                prop.get("data", {})[HDHOMERUN_TAG_GETSET_NAME].decode().rstrip("\0")
            )
            prop_value = (
                prop.get("data", {})[HDHOMERUN_TAG_GETSET_VALUE].decode().rstrip("\0")
            )
            setattr(self, tcp_prop_name.replace("/", "_"), prop_value)
        # endregion

        return None

    async def _async_get_channel_details_udp(
        self, tuner_index: int
    ) -> Dict[str, int | str]:
        """Gather details about the currently tuned channel."""
        protocol: HDHomeRunProtocol = HDHomeRunProtocol(host=self.ip)
        ret: Dict[str, int | str] = {}

        channel_details = await protocol.async_get_tuner_current_channel(
            tuner_idx=tuner_index
        )
        tuner_channel_id, channel_names, tuner_target = channel_details
        tuner_channel_id = (
            tuner_channel_id.get("data", {})[HDHOMERUN_TAG_GETSET_VALUE]
            .decode()
            .rstrip("\0")
        )
        channel_names = (
            channel_names.get("data", {})[HDHOMERUN_TAG_GETSET_VALUE]
            .decode()
            .rstrip("\0")
            .split("\n")
        )
        channel: str
        channel_name: List[tuple[str, ...]] = [
            tuple(channel.replace(f"{tuner_channel_id}: ", "").split(" ", maxsplit=1))
            for channel in channel_names
            if channel.startswith(f"{tuner_channel_id}: ")
        ]
        if channel_name:
            vct_number, vct_name = channel_name[0]
            ret["VctNumber"] = str(vct_number)
            ret["VctName"] = str(vct_name)
        target_url: str = (
            tuner_target.get("data", {})[HDHOMERUN_TAG_GETSET_VALUE]
            .decode()
            .rstrip("\0")
        )
        if target_url != "none":
            ret["TargetIP"] = urlparse(url=target_url).hostname

        return ret

    async def _async_get_tuner_status_http(self) -> None:
        """Get the current details for the tuners using HTTP."""
        resp: aiohttp.ClientResponse = await self._session.get(
            url=f"http://{self.ip}/{DevicePaths.TUNER_STATUS}",
            raise_for_status=True,
        )
        self._tuner_status = await resp.json()

    async def _async_get_tuner_status_udp(self) -> None:
        """Get the current details for the tuners using the control protocol."""
        protocol: HDHomeRunProtocol = HDHomeRunProtocol(host=self.ip)

        tuners = [
            protocol.async_get_tuner_status(tuner_idx=idx)
            for idx in range(self.tuner_count)
        ]

        # -- process all tuners --#
        tuner_status: List[Dict[str, str]] = []
        for tuner in await asyncio.gather(*tuners):
            if tuner is None:
                continue

            key = tuner.get("data", {})[HDHOMERUN_TAG_GETSET_NAME].decode().rstrip("\0")
            val = (
                tuner.get("data", {})[HDHOMERUN_TAG_GETSET_VALUE].decode().rstrip("\0")
            )
            tuner_info: Dict[str, int | str] = {"Resource": key.split("/")[1]}

            # status details are space delimted; tags are = delimited
            for detail in val.split(" "):
                tag, value = tuple(map(str, detail.split("=")))
                try:
                    value = int(value)
                except ValueError:  # we're only interested in the items that are numbers
                    pass
                else:
                    if value != 0:  # if the value is 0 don't include it
                        if tag == "seq":
                            tuner_info["SymbolQualityPercent"] = value
                        elif tag == "snq":
                            tuner_info["SignalQualityPercent"] = value
                        elif tag == "ss":
                            tuner_info["SignalStrengthPercent"] = value

            # need to get the channel details now
            if "SymbolQualityPercent" in tuner_info:
                channel_details = await self._async_get_channel_details_udp(
                    tuner_index=tuner_info["Resource"].replace("tuner", "")
                )
                tuner_info.update(channel_details)

            tuner_status.append(tuner_info)

        self._tuner_status = tuner_status or None

    async def async_gather_details(self) -> None:
        """Gather the details for the device."""
        if self._discovery_method is DiscoverMode.HTTP:
            await self._async_gather_details_http()

        if self._discovery_method is DiscoverMode.UDP:
            await self._async_gather_details_udp()

    async def async_get_protocol_variable(
        self, name: str, timeout: float = 2.5
    ) -> Dict[str, int | str]:
        """Return a variable from the control protocol."""
        _LOGGER.debug(self._log_formatter.format("entered"))

        ret: Dict[str, int | str] = {}
        proto: HDHomeRunProtocol = HDHomeRunProtocol(host=self.ip)
        if (get_variable_func := getattr(proto, "_get_set_req", None)) is not None:
            ret = await get_variable_func(tag=name, timeout=timeout)

        _LOGGER.debug(self._log_formatter.format("exited"))
        return ret

    async def async_refresh_tuner_status(self) -> None:
        """Get the current details for the tuners."""
        if self._discovery_method is DiscoverMode.HTTP:
            return await self._async_get_tuner_status_http()

        if self._discovery_method is DiscoverMode.UDP:
            return await self._async_get_tuner_status_udp()

    async def async_restart(self) -> None:
        """Restart the device using the control protocol."""
        proto: HDHomeRunProtocol = HDHomeRunProtocol(host=self.ip)
        await proto.async_restart()

    # region #-- properties --#
    @property
    def base_url(self) -> str | None:
        """Get the base URL."""
        return self._raw_details.get("discover", {}).get("BaseURL", self._base_url)

    @property
    def channels(self) -> List[Dict[str, str]]:
        """Get a list of channels as per the HTTP API."""
        return self._raw_details.get("lineup", [])

    @property
    def device_auth_string(self) -> str | None:
        """Get the device auth string."""
        return self._raw_details.get("discover", {}).get(
            "DeviceAuth", self._device_auth_str
        )

    @property
    def device_id(self) -> str | None:
        """Get the device ID."""
        return self._raw_details.get("discover", {}).get("DeviceID", self._device_id)

    @property
    def device_type(self) -> DeviceType | None:
        """Get the device type as defined in the UDP protocol."""
        return self._device_type

    @property
    def discovery_method(self):
        """Return the discovery method."""
        return self._discovery_method

    @property
    def friendly_name(self) -> str | None:
        """Get the friendly name as defined by the HTTP API."""
        return self._raw_details.get("discover", {}).get("FriendlyName", None)

    @property
    def hw_model(self) -> str | None:
        """Get the model number."""
        return self._raw_details.get("discover", {}).get(
            "ModelNumber", self._sys_hwmodel
        )

    @property
    def installed_version(self) -> str | None:
        """Get the installed firmware version."""
        return self._raw_details.get("discover", {}).get(
            "FirmwareVersion", self._sys_version
        )

    @property
    def ip(self) -> str | None:  # pylint: disable=invalid-name
        """Get the IP address."""
        return self._host

    @property
    def latest_version(self) -> str | None:
        """Get the latest available version (HTTP API)."""
        return self._raw_details.get("discover", {}).get("UpgradeAvailable", None)

    @property
    def lineup_url(self) -> str | None:
        """Get the URL for the channel lineup."""
        return self._raw_details.get("discover", {}).get("LineupURL", self._lineup_url)

    @property
    def model(self) -> str | None:
        """Get the firmware name."""
        return self._raw_details.get("discover", {}).get(
            "FirmwareName", self._sys_model
        )

    @property
    def tuner_count(self) -> int | None:
        """Get the number of tuners."""
        return self._raw_details.get("discover", {}).get(
            "TunerCount", self._tuner_count
        )

    @property
    def tuner_status(self) -> List[Dict[str, int | str]] | None:
        """Get the status for all tuners."""
        return self._tuner_status

    # endregion
