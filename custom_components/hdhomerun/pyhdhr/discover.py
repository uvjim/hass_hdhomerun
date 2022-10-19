"""Discovery for HDHomeRun devices."""

# region #-- imports --#
from __future__ import annotations

import asyncio
import logging
import socket
import struct
from enum import Enum, unique
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse, urlunparse

import aiohttp

from .const import (
    HDHOMERUN_DEVICE_ID_WILDCARD,
    HDHOMERUN_DEVICE_TYPE_TUNER,
    HDHOMERUN_DISCOVER_UDP_PORT,
    HDHOMERUN_TAG_BASE_URL,
    HDHOMERUN_TAG_DEVICE_AUTH_STR,
    HDHOMERUN_TAG_DEVICE_ID,
    HDHOMERUN_TAG_DEVICE_TYPE,
    HDHOMERUN_TAG_GETSET_NAME,
    HDHOMERUN_TAG_GETSET_VALUE,
    HDHOMERUN_TAG_LINEUP_URL,
    HDHOMERUN_TAG_TUNER_COUNT,
    HDHOMERUN_TYPE_DISCOVER_REQ,
    HDHOMERUN_TYPE_DISCOVER_RPY,
)
from .exceptions import HDHomeRunHTTPDiscoveryNotAvailableError
from .logger import Logger
from .protocol import HDHomeRunProtocol

# endregion

_LOGGER = logging.getLogger(__name__)


@unique
class DeviceType(Enum):
    """Device types as defined by the protocol."""

    TUNER = 1
    STORAGE = 5


@unique
class DiscoverMode(Enum):
    """Available discovery modes."""

    AUTO = 0
    HTTP = 1
    UDP = 2


class Discover:
    """Generic discovery representation."""

    def __init__(self, mode: DiscoverMode = DiscoverMode.AUTO) -> None:
        """Initialise."""
        self._log_formatter: Logger = Logger()
        self._mode: DiscoverMode = DiscoverMode(mode)

    async def discover(
        self, broadcast_address: Optional[str] = "255.255.255.255"
    ) -> List[HDHomeRunDevice]:
        """Carry out a discovery for devices.

        N.B. when the mode is set to AUTO HTTP is discovery is attempted first and then UDP.
        The device lists are merged with the settings from UDP winning if they are not None.
        A request is then made to the discover_url to attempt to get more friendly information.

        :param broadcast_address: the address to broadcast to when using the UDP protocol
        :return: a list of device objects for those found
        """
        _LOGGER.debug(
            self._log_formatter.format("entered, broadcast_address: %s"),
            broadcast_address,
        )
        _LOGGER.debug(self._log_formatter.format("mode: %s"), self._mode)

        devices: Dict[str, HDHomeRunDevice] = {}

        # region #-- get the devices from HTTP --#
        if self._mode in (DiscoverMode.AUTO, DiscoverMode.HTTP):
            try:
                discovered_devices: List[
                    HDHomeRunDevice
                ] = await DiscoverHTTP.discover()
            except HDHomeRunHTTPDiscoveryNotAvailableError as err:
                _LOGGER.debug(self._log_formatter.format("%s"), err)
            else:
                for dev in discovered_devices:
                    setattr(dev, "_discovery_method", DiscoverMode.HTTP)
                    devices[dev.device_id] = dev
        # endregion

        # region #-- get the devices from UDP --#
        if self._mode in (DiscoverMode.AUTO, DiscoverMode.UDP):
            discovered_devices: List[HDHomeRunDevice] = await DiscoverUDP.discover(
                target=broadcast_address
            )
            for dev in discovered_devices:
                if dev.device_id not in devices:
                    setattr(dev, "_discovery_method", DiscoverMode.UDP)
                    devices[dev.device_id] = dev
                else:
                    for _, property_name in _DiscoverProtocol.TAG_PROPERTY_MAP.items():
                        if (
                            property_value := getattr(dev, property_name, None)
                        ) is not None:
                            setattr(
                                devices.get(dev.device_id),
                                property_name,
                                property_value,
                            )
        # endregion

        # region #-- try and rediscover via HTTP to get further details (UDP won't offer any more) --#
        if len(devices):
            _LOGGER.debug(
                self._log_formatter.format("attempting targeted rediscover via HTTP")
            )
        for _, dev in devices.items():
            await DiscoverHTTP.rediscover(target=dev)
        # endregion

        _LOGGER.debug(
            self._log_formatter.format("exited, %i devices found"), len(devices)
        )
        return list(devices.values())

    @staticmethod
    async def rediscover(target: HDHomeRunDevice) -> HDHomeRunDevice:
        """Get updated information for the given target.

        :param target: the device to refresh information for
        :return: the updated device
        """
        log_formatter: Logger = Logger(unique_id=target.ip)
        _LOGGER.debug(log_formatter.format("entered"))

        ret: HDHomeRunDevice
        if getattr(target, "_discovery_mode", None) is None:
            discovered_devices: List[HDHomeRunDevice] = await Discover().discover()
            for dev in discovered_devices:
                if dev.ip == target.ip:
                    device: HDHomeRunDevice = dev
                    break
        else:
            if getattr(target, "_discover_url", None) is not None:
                device: HDHomeRunDevice = await DiscoverHTTP.rediscover(target=target)
            else:
                device: List[HDHomeRunDevice] = await DiscoverUDP.rediscover(
                    target=target.ip
                )

        if not device:
            ret = target
            setattr(ret, "_is_online", False)
        else:
            ret = device[0] if isinstance(device, List) else device
            setattr(ret, "_is_online", True)

        _LOGGER.debug(log_formatter.format("_is_online: %s"), ret.online)
        _LOGGER.debug(log_formatter.format("exited"))
        return ret


class DiscoverHTTP:
    """Discover a device over HTTP."""

    JSON_PROPERTIES_MAP: Dict[str, str] = {
        "BaseURL": "_base_url",
        "DeviceAuth": "_device_auth_str",
        "DeviceID": "_device_id",
        "DiscoverURL": "_discover_url",
        "FirmwareName": "_sys_model",
        "FirmwareVersion": "_sys_version",
        "FriendlyName": "_friendly_name",
        "LineupURL": "_lineup_url",
        "LocalIP": "_host",
        "ModelNumber": "_sys_hwmodel",
        "TunerCount": "_tuner_count",
        "UpgradeAvailable": "_available_firmware",
    }

    @staticmethod
    async def discover(
        discover_url: str = "https://ipv4-api.hdhomerun.com/discover",
        session: Optional[aiohttp.ClientSession] = None,
        timeout: float = 2.5,
    ) -> List[HDHomeRunDevice]:
        """Issue a request to get known devices or updated information about a device.

        :param discover_url: the URL to query
        :param session: an existing session to use
        :param timeout: timeout for the query
        :return: list of devices found or with refreshed information
        """
        log_formatter: Logger = Logger(prefix=f"{__class__.__name__}.")
        _LOGGER.debug(
            log_formatter.format(
                "entered, discover_url: %s, session: %s, timeout: %.2f"
            ),
            discover_url,
            session,
            timeout,
        )

        ret: List[HDHomeRunDevice] = []
        created_session: bool = False

        if session is None:
            _LOGGER.debug(log_formatter.format("creating session"))
            created_session = True
            session = aiohttp.ClientSession()

        try:
            response = await session.get(
                url=discover_url, timeout=timeout, raise_for_status=True
            )
        except Exception as err:
            _LOGGER.debug(
                log_formatter.format("error in HTTP discovery, %s: %s"), type(err), err
            )
            raise HDHomeRunHTTPDiscoveryNotAvailableError(
                device=urlparse(discover_url).hostname
            ) from None
        else:
            resp_json = await response.json()
            if resp_json:  # we didn't just get an empty list or dictionary
                if not isinstance(resp_json, list):  # single result received
                    resp_json = [resp_json]
                for device in resp_json:
                    discovered_device = HDHomeRunDevice(
                        host=device.get("LocalIP") or urlparse(discover_url).hostname
                    )
                    for (
                        json_prop_name,
                        property_value,
                    ) in device.items():  # use the mappings to set properties
                        if (
                            property_name := DiscoverHTTP.JSON_PROPERTIES_MAP.get(
                                json_prop_name, None
                            )
                        ) is not None:
                            setattr(discovered_device, property_name, property_value)
                    ret.append(discovered_device)
        finally:
            if created_session:
                await session.close()

        _LOGGER.debug(log_formatter.format("exited, %i devices found"), len(ret))
        return ret

    @staticmethod
    async def rediscover(
        target: HDHomeRunDevice,
        session: Optional[aiohttp.ClientSession] = None,
        timeout: float = 2.5,
    ) -> HDHomeRunDevice:
        """Gather updated information about a device.

        N.B. the discover_url will be used if available. If not, one is built (UDP discovered devices
        won't have one).

        :param target: the device to refresh information for
        :param session: existing session
        :param timeout: timeout for the query
        :return: the updated device
        """
        log_formatter: Logger = Logger(prefix=f"{__class__.__name__}.")
        _LOGGER.debug(
            log_formatter.format("entered, target: %s, session: %s, timeout: %.2f"),
            target,
            session,
            timeout,
        )

        discover_url: str = getattr(target, "_discover_url", None)
        if discover_url is None:
            _LOGGER.debug(log_formatter.format("building discover_url"))
            discover_url = f"http://{target.ip}/discover.json"

        try:
            _LOGGER.debug(log_formatter.format("discover_url, %s"), discover_url)
            updated_device = await DiscoverHTTP.discover(
                discover_url=discover_url, session=session, timeout=timeout
            )
        except HDHomeRunHTTPDiscoveryNotAvailableError as err:
            _LOGGER.debug(
                log_formatter.format("error in HTTP discovery, %s: %s"), type(err), err
            )
        else:
            setattr(target, "_discover_url", discover_url)
            setattr(target, "_discovery_method", DiscoverMode.HTTP)
            updated_device = updated_device[0]
            for (
                _,
                property_name,
            ) in DiscoverHTTP.JSON_PROPERTIES_MAP.items():  # set the properties
                if (
                    property_value := getattr(updated_device, property_name, None)
                ) is not None:
                    setattr(target, property_name, property_value)

        _LOGGER.debug(log_formatter.format("exited"))
        return target


class DiscoverUDP:
    """Representation of using UDP for discovery."""

    DISCOVER_PORT: int = HDHOMERUN_DISCOVER_UDP_PORT

    @staticmethod
    async def discover(
        interface: Optional[str] = None,
        target: str = "255.255.255.255",
        timeout: float = 1,
    ) -> List[HDHomeRunDevice]:
        """Use the UDP protocol to broadcast for discovery.

        :param interface: the interface to use
        :param target: the broadcast address to use (this can also be an individual IP)
        :param timeout: timeout for the query
        :return: list of discovered devices
        """
        log_formatter: Logger = Logger(prefix=f"{__class__.__name__}.")
        _LOGGER.debug(
            log_formatter.format("entered, interface: %s, target: %s, timeout: %.2f"),
            interface,
            target,
            timeout,
        )
        loop = asyncio.get_event_loop()
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: _DiscoverProtocol(
                target=target,
                interface=interface,
            ),
            local_addr=("0.0.0.0", 0),
        )

        try:
            _LOGGER.debug(
                log_formatter.format("waiting %s second%s for responses"),
                timeout,
                "s" if timeout != 1 else "",
            )
            await asyncio.sleep(timeout)
        finally:
            transport.close()

        _LOGGER.debug(
            log_formatter.format("exited, %i devices found"),
            len(protocol.discovered_devices),
        )
        return protocol.discovered_devices

    rediscover = discover  # rediscover is essentially the same as discover you just need to provide a specific IP


class _DiscoverProtocol(asyncio.DatagramProtocol):
    """Internal implementation of the discovery protocol."""

    discovered_devices: List[HDHomeRunDevice] = []

    TAG_PROPERTY_MAP: Dict[int, str] = {
        HDHOMERUN_TAG_BASE_URL: "_base_url",
        HDHOMERUN_TAG_DEVICE_AUTH_STR: "_device_auth_str",
        HDHOMERUN_TAG_DEVICE_ID: "_device_id",
        HDHOMERUN_TAG_DEVICE_TYPE: "_device_type",
        HDHOMERUN_TAG_LINEUP_URL: "_lineup_url",
        HDHOMERUN_TAG_TUNER_COUNT: "_tuner_count",
    }

    def __init__(
        self,
        port: int = DiscoverUDP.DISCOVER_PORT,
        interface: Optional[str] = None,
        target: str = "255.255.255.255",
    ) -> None:
        """Initialise."""
        self._interface: Optional[str] = interface
        self._log_formatter: Logger = Logger(prefix=f"{__class__.__name__}.")
        self._target = (target, port)
        self._transport: Optional[asyncio.DatagramTransport] = None

        self.discovered_devices = []

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        """Respond when a conection is made.

        :param transport: UDP transport
        :return: None
        """
        # region #-- initialise the socket --#
        self._transport = transport
        sock: Optional[socket.socket] = self._transport.get_extra_info("socket")
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        # endregion

        # bind to an interface if necessary
        if self._interface is not None:
            sock.setsockopt(
                socket.SOL_SOCKET, socket.SO_BINDTODEVICE, self._interface.encode()
            )

        self.do_discover()

    def connection_lost(self, exc: Exception | None) -> None:
        """React to the connection being lost."""

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        """Process the data received.

        :param data: data received in response to the message
        :param addr: where the data came from
        :return: None
        """
        ip_address, _ = addr

        # region #-- initialise the device object --#
        discovered_device: HDHomeRunDevice = HDHomeRunDevice(host=ip_address)
        response = HDHomeRunProtocol.parse_response(data)
        # endregion

        # region #-- check that the tuner was initialised with a discovery response --#
        if response.get("header") != HDHOMERUN_TYPE_DISCOVER_RPY:
            raise ValueError
        # endregion

        # region #-- build the properties --#
        for tag in response.get("data", {}).keys():
            property_value: Optional[int | str] = None
            if tag == HDHOMERUN_TAG_BASE_URL:
                property_value = (
                    response.get("data", {}).get(HDHOMERUN_TAG_BASE_URL, b"").decode()
                )
            elif tag == HDHOMERUN_TAG_DEVICE_AUTH_STR:
                property_value = (
                    response.get("data", {})
                    .get(HDHOMERUN_TAG_DEVICE_AUTH_STR, b"")
                    .decode()
                )
            elif tag == HDHOMERUN_TAG_DEVICE_ID:
                (property_value,) = struct.unpack(
                    ">L", response.get("data", {}).get(HDHOMERUN_TAG_DEVICE_ID, b"")
                )
                property_value = f"{property_value:04X}"
            elif tag == HDHOMERUN_TAG_DEVICE_TYPE:
                (property_value,) = struct.unpack(
                    ">L", response.get("data", {}).get(HDHOMERUN_TAG_DEVICE_TYPE, b"")
                )
            elif tag == HDHOMERUN_TAG_LINEUP_URL:
                property_value = (
                    response.get("data", {}).get(HDHOMERUN_TAG_LINEUP_URL, b"").decode()
                )
            elif tag == HDHOMERUN_TAG_TUNER_COUNT:
                (property_value,) = struct.unpack(
                    ">B", response.get("data", {}).get(HDHOMERUN_TAG_TUNER_COUNT, b"")
                )

            if property_value:
                if property_name := _DiscoverProtocol.TAG_PROPERTY_MAP.get(tag, None):
                    setattr(discovered_device, property_name, property_value)
        # endregion

        self.discovered_devices.append(discovered_device)

    def do_discover(self) -> None:
        """Send the packets."""
        _LOGGER.debug(self._log_formatter.format("entered"))

        pkt_type: bytes = struct.pack(">H", HDHOMERUN_TYPE_DISCOVER_REQ)
        payload_data: List[Tuple[int, bytes]] = [
            (HDHOMERUN_TAG_DEVICE_TYPE, struct.pack(">I", HDHOMERUN_DEVICE_TYPE_TUNER)),
            (HDHOMERUN_TAG_DEVICE_ID, struct.pack(">I", HDHOMERUN_DEVICE_ID_WILDCARD)),
        ]
        req = HDHomeRunProtocol.build_request(
            packet_payload=payload_data, packet_type=pkt_type
        )

        _LOGGER.debug(
            self._log_formatter.format("sending discovery packet: %s, %s"),
            self._target,
            req.hex(),
        )
        self._transport.sendto(req, self._target)

        _LOGGER.debug(self._log_formatter.format("exited"))

    def error_received(self, exc: Exception) -> None:
        """React to an error being received."""


class HDHomeRunDevice:
    """Representation of a device."""

    def __del__(self) -> None:
        """Close the session if necessary."""
        if self._session and self._created_session:
            asyncio.run_coroutine_threadsafe(
                coro=self._session.close(), loop=asyncio.get_event_loop()
            )

    def __init__(self, host: str) -> None:
        """Initialise."""
        self._host: str = host
        self._log_formatter: Logger = Logger(unique_id=self._host)

        self._created_session: bool = False
        self._session: Optional[aiohttp.ClientSession] = None

        self._available_firmware: Optional[str] = None
        self._base_url: Optional[str] = None
        self._channels: List[Dict[str, str]] = []
        self._device_auth_str: Optional[str] = None
        self._device_id: Optional[str] = None
        self._device_type: Optional[DeviceType] = None
        self._discover_url: Optional[str] = None
        self._discovery_method = None
        self._friendly_name: Optional[str] = None
        self._is_online: bool = True
        self._lineup_url: Optional[str] = None
        self._sys_hwmodel: Optional[str] = None
        self._sys_model: Optional[str] = None
        self._sys_version: Optional[str] = None
        self._tuner_count: Optional[int] = None
        self._tuner_status: Optional[List[Dict[str, int | str]]] = None

    def __repr__(self) -> str:
        """Friendly representation of the device."""
        return f"{self.__class__.__name__} {self._host}"

    async def _async_tuner_refresh_http(self, timeout: Optional[float] = 2.5) -> None:
        """Refresh the tuner data using HTTP.

        :param timeout: timeout for the query
        :return: None
        """
        # region #-- build the URL and create a session if needed --#
        tuner_status_url: List[str] | str = list(urlparse(self._discover_url))
        tuner_status_url[2] = "/status.json"
        tuner_status_url = urlunparse(tuner_status_url)
        if not self._session:
            self._created_session = True
            self._session = aiohttp.ClientSession()
        # endregion

        try:
            resp: aiohttp.ClientResponse = await self._session.get(
                url=tuner_status_url, timeout=timeout, raise_for_status=True
            )
        except aiohttp.ClientResponseError as err:
            _LOGGER.error("ClientResponseError --> %s", err)
        except asyncio.TimeoutError:
            self._is_online = False
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.error("%s type: %s", err, type(err))
        else:
            self._is_online = True
            resp_json = await resp.json()
            self._tuner_status = resp_json

    async def _async_tuner_refresh_tcp(self) -> None:
        """Refresh the tuner information using the TCP control protocol.

        N.B. this tries to closely mimic the response from the HTTP response

        :return: None
        """
        proto: HDHomeRunProtocol = HDHomeRunProtocol(host=self.ip)

        tuners = [
            proto.get_tuner_status(tuner_idx=idx) for idx in range(self.tuner_count)
        ]
        tuner_status_info = await asyncio.gather(*tuners)

        # -- process all tuners --#
        tuner_status: List[Dict[str, str]] = []
        for tuner in tuner_status_info:
            if tuner is None:
                self._is_online = False
                continue

            self._is_online = True
            key = tuner.get("data", {})[HDHOMERUN_TAG_GETSET_NAME].decode().rstrip("\0")
            val = (
                tuner.get("data", {})[HDHOMERUN_TAG_GETSET_VALUE].decode().rstrip("\0")
            )
            tuner_info: Dict[str, int | str] = {"Resource": key.split("/")[1]}
            status_details = val.split(" ")  # status details are space delimited
            for detail in status_details:  # tags are = delimited
                tag, value = tuple(map(str, detail.split("=")))
                try:
                    value = int(value)
                except ValueError:  # we're onlhy interested in the items that are numbers
                    pass
                else:
                    if value != 0:  # if the value is 0 don't include it
                        if tag == "seq":
                            tuner_info["SymbolQualityPercent"] = value
                        elif tag == "snq":
                            tuner_info["SignalQualityPercent"] = value
                        elif tag == "ss":
                            tuner_info["SignalStrengthPercent"] = value

            if (
                "SymbolQualityPercent" in tuner_info
            ):  # need to get the channel details now
                channel_details = await proto.get_tuner_current_channel(
                    tuner_idx=tuner_info["Resource"].replace("tuner", "")
                )
                tuner_channel_id, channel_names, tuner_target = channel_details
                tuner_channel_id = (
                    tuner_channel_id.get("data", {})[HDHOMERUN_TAG_GETSET_VALUE]
                    .decode()
                    .rstrip("\0")
                )
                if int(tuner_channel_id):
                    channel_names = (
                        channel_names.get("data", {})[HDHOMERUN_TAG_GETSET_VALUE]
                        .decode()
                        .rstrip("\0")
                        .split("\n")
                    )
                    channel: str
                    channel_name: List[Tuple[str, ...]] = [
                        tuple(
                            channel.replace(f"{tuner_channel_id}: ", "").split(
                                " ", maxsplit=1
                            )
                        )
                        for channel in channel_names
                        if channel.startswith(f"{tuner_channel_id}: ")
                    ]
                    if channel_name:
                        vct_number, vct_name = channel_name[0]
                        tuner_info["VctNumber"] = str(vct_number)
                        tuner_info["VctName"] = str(vct_name)
                    tuner_info["TargetIP"] = urlparse(
                        tuner_target.get("data", {})[HDHOMERUN_TAG_GETSET_VALUE]
                    ).hostname.decode()

            if not tuner_status:
                tuner_status = []
            tuner_status.append(tuner_info)

        if tuner_status:
            self._tuner_status = tuner_status

    async def async_get_variable(
        self, variable: str, timeout: float = 2.5
    ) -> Dict[str, int | str]:
        """Retrieve the given variable from the device.

        :param variable: variable name
        :param timeout: timeout for the request
        :return: a dictionary in the form
            {
                "header": Any,
                "length": Any,
                "data": {
                    "raw": <the data from the response sent by the device>
                    "tag": <data> ...
                }
            }
        """
        _LOGGER.debug(
            self._log_formatter.format("entered, variable: %s, timeout: %.2f"),
            variable,
            timeout,
        )
        ret: Dict[str, int | str] = {}
        proto: HDHomeRunProtocol = HDHomeRunProtocol(host=self.ip)
        if (get_variable_func := getattr(proto, "_get_set_req", None)) is not None:
            ret = await get_variable_func(tag=variable, timeout=timeout)

        _LOGGER.debug(self._log_formatter.format("exited"))
        return ret

    async def async_tuner_refresh(self, timeout: float = 2.5) -> None:
        """Genric function refreshing tuners.

        N.B. assumes that a discover_url means that the device will respond to HTTP

        :param timeout: timeout for the query (ignored for TCP Control protocol)
        :return: None
        """
        if self._discover_url is not None:
            await self._async_tuner_refresh_http(timeout=timeout)
        else:
            await self._async_tuner_refresh_tcp()

    async def async_rediscover(self, timeout: float = 2.5) -> HDHomeRunDevice:
        """Refresh the information for a device.

        :param timeout: timeout for the query
        :return: None
        """
        tcp_property_map: Dict[str, str] = {
            "/sys/version": "_sys_version",
            "/sys/model": "_sys_model",
            "/sys/hwmodel": "_sys_hwmodel",
        }

        device: HDHomeRunDevice = await Discover.rediscover(target=self)
        if device.discovery_method is not DiscoverMode.HTTP and device.online:
            proto: HDHomeRunProtocol = HDHomeRunProtocol(host=self.ip)
            supplemental_info = [
                proto.get_version(),
                proto.get_model(),
                proto.get_hwmodel(),
            ]
            info = await asyncio.gather(*supplemental_info)
            prop: Dict[str, Dict[int | str, bytes]]
            for prop in info:
                tcp_prop_name = (
                    prop.get("data", {})[HDHOMERUN_TAG_GETSET_NAME]
                    .decode()
                    .rstrip("\0")
                )
                prop_value = (
                    prop.get("data", {})[HDHOMERUN_TAG_GETSET_VALUE]
                    .decode()
                    .rstrip("\0")
                )
                if (prop_name := tcp_property_map.get(tcp_prop_name, None)) is not None:
                    setattr(device, prop_name, prop_value)

        # region #-- get the channels from the lineup_url --#
        if device.lineup_url and device.online:
            if self._session is None:
                self._created_session: bool = True
                self._session = aiohttp.ClientSession()

            try:
                response = await self._session.get(
                    url=device.lineup_url, timeout=timeout, raise_for_status=True
                )
            except asyncio.TimeoutError:
                setattr(device, "_is_online", False)
                _LOGGER.error("Timeout experienced reaching %s", device.lineup_url)
            except aiohttp.ClientConnectorError:
                setattr(device, "_is_online", False)
            except Exception as err:
                raise err from None
            else:
                resp_json = await response.json()
                setattr(device, "_channels", resp_json)
        # endregion

        return device

    async def async_restart(self) -> None:
        """Restart the device."""
        proto: HDHomeRunProtocol = HDHomeRunProtocol(host=self.ip)

        await proto.async_restart()

    # region #-- properties --#
    @property
    def base_url(self) -> Optional[str]:
        """Get the base URL."""
        return self._base_url

    @property
    def channels(self) -> List[Dict[str, str]]:
        """Get a list of channels as per the HTTP API."""
        return self._channels

    @property
    def device_auth_string(self) -> Optional[str]:
        """Get the device auth string."""
        return self._device_auth_str

    @property
    def device_id(self) -> Optional[str]:
        """Get the device ID."""
        return self._device_id

    @property
    def device_type(self) -> Optional[DeviceType]:
        """Get the device type as defined in the UDP protocol."""
        return self._device_type

    @property
    def discovery_method(self):
        """Return the discovery method."""
        return self._discovery_method

    @property
    def friendly_name(self) -> Optional[str]:
        """Get the friendly name as defined by the HTTP API."""
        return self._friendly_name

    @property
    def hw_model(self) -> Optional[str]:
        """Get the model number."""
        return self._sys_hwmodel

    @property
    def installed_version(self) -> Optional[str]:
        """Get the installed firmware version."""
        return self._sys_version

    @property
    def ip(self) -> Optional[str]:  # pylint: disable=invalid-name
        """Get the IP address."""
        return self._host

    @property
    def latest_version(self) -> Optional[str]:
        """Get the atest available version (HTTP API)."""
        return self._available_firmware

    @property
    def lineup_url(self) -> Optional[str]:
        """Get the URL for the channel lineup."""
        return self._lineup_url

    @property
    def model(self) -> Optional[str]:
        """Get the firmware name."""
        return self._sys_model

    @property
    def online(self) -> bool:
        """Get whether the device is online or not."""
        return self._is_online

    @property
    def tuner_count(self) -> Optional[int]:
        """Get the number of tuners."""
        return self._tuner_count

    @property
    def tuner_status(self) -> Optional[List[Dict[str, int | str]]]:
        """Get the status for all tuners."""
        return self._tuner_status

    # endregion
