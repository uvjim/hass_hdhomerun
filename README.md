[![GitHub Release][badge_github_release_version]][github_release_link]
![GitHub Downloads (latest release)][badge_github_release_downloads]
[![GitHub Pre-release][badge_github_prerelease_version]][github_prerelease_link]
![GitHub Downloads (pre-release)][badge_github_prerelease_downloads]

# HDHomeRun

Home Assistant integration for the Silicondust HDHomeRun network tuners.

## Installation

The integration can be installed using HACS.  The integrations is not available
in the default repositories, so you will need to add the URL of this repository
as a custom repository to HACS (see here).

Alternatively you can use the button below.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=uvjim&repository=hass_hdhomerun&category=Integration)

## Description

This integration can be used to get basic information on each HDHomeRun
device in the network. The integration can use the UDP broadcast discovery
protocol, the TCP control protocol and the HTTP API.

### Optional XMLTV guide proxy

Enable **XMLTV EPG proxy** in the device's integration options. The default
refresh is six hours; 3, 6, 12 and 24 hours are available. Refreshes are
slightly randomized to avoid fixed-time requests to SiliconDust. The first
background fetch starts within five minutes; use the **Refresh EPG** button
to fetch immediately. This feature is off by default and requires the tuner
to provide `DeviceAuth` in its local `discover.json`, and HA to reach
`https://api.hdhomerun.com/api/xmltv`. The integration requests gzip and reads
the current auth immediately before each download; it never stores the auth.

The **EPG status** sensor exposes `url` and `gzip_url` attributes. Set HA's internal or
external URL to an address UHF can reach (otherwise this attribute is only a
relative path), then enter that full URL as UHF's XMLTV source. No HA bearer
token is needed. A valid cache serves even when the tuner or SiliconDust is
temporarily offline. Until the first successful refresh the URL returns 503;
disabled/unloaded/rotated URLs return 404. The status sensor shows `empty`,
`ready`, `refresh_failed`, or `expired`, plus last fetch time, cache age in
hours, programme/channel counts, earliest start/latest stop, and advisory
lineup-to-XMLTV display-name matches and up to 20 unmatched examples. XMLTV
channel IDs are not rewritten; check mapping in UHF itself. Feed coverage and
lineup can differ from the local device, particularly with multiple tuners.

The normal URL serves XML and uses HTTP gzip compression when the client
advertises `Accept-Encoding: gzip`. The `gzip_url` appends `.xml.gz` and always
serves a gzip file (`application/gzip`, without HTTP `Content-Encoding`). Use
that option only with players that support gzip XMLTV files. Both formats
serve the same validated snapshot and share the same access token. Compression
is prepared off the HA event loop on refresh/restart and reused for requests;
the gzip snapshot adds memory overhead but is not stored as a second disk copy.
Upstream downloads already request gzip; actual compression depends on
SiliconDust's response, and the size limit still applies after decompression.

**Treat the URL as a password:** anyone who obtains it can read the guide.
Tokens contain 128 random bits encoded as 22 URL-safe characters. On updating
from the former 64-character format, the next integration load generates a new
token; copy the new URL into your player. Old URLs are not supported.
Use HTTPS if UHF connects across an untrusted network. The URL is visible to
HA users via entity attributes and may appear in HA history, reverse-proxy
access logs, or UHF configuration. Do not publish it in screenshots or issue
reports. The **Rotate EPG URL** button immediately invalidates the previous
URL; update UHF after rotating. Disabling this option invalidates the URL
while disabled but retains the private HA storage snapshot/token for re-enable.
Removing an entry does not automatically delete its stored guide; remove its
`.storage/hdhomerun/epg_<entry_id>` file manually if retiring the device.
SiliconDust determines the available guide window (typically two days, or
longer with eligible DVR service); this proxy cannot add missing guide data.

The guide is validated as XMLTV (`tv`, uniquely identified channels and
programmes with valid references/times) and capped at 48 MiB decompressed.
The HTTP download is chunked and stops at the cap; validation parses
incrementally rather than retaining a full XML tree. The complete validated
guide is still kept in memory and in HA's private, atomic storage so UHF can
retrieve it while offline; allow additional memory and disk headroom for
serialization and an in-progress refresh. An invalid, oversized or failed
download never replaces the last good cache. The 3.31 MiB two-day guide tested
with this integration suggests roughly 23 MiB at 14 days for a similar lineup, but
real guide size depends on channels and programme detail. A larger entitled
feed may still exceed 48 MiB; check `last_error_type` and the HA logs before
considering a higher limit or a disk-backed streaming cache.

## Entities Provided

Where applicable the sub-items in the list detail the additional attributes
available. All entities may not be available to you depending on how the
device was discovered and what its capabilities are.

### Binary Sensors

| Location | Name | Enabled by default | Additional Information |
|---|---|:---:|---|
| Device | Channel Scanning | ✔️ | Percentage progress of the channel scan |

### Button

| Location | Name | Enabled by default | Comments |
|---|---|:---:|---|
| Device | Channel Scan | ✔️ | Requires the source to be selected first (see [here](#select)) |
| Device | Restart | ✔️ |  |

### Select

| Location | Name | Enabled by default | Comments |
|---|---|:---:|---|
| Device | Channel Sources | ✔️ | Selects the channel source to be used when carrying out a channel scan |

### Sensors

| Location | Name | Enabled by default | Primary value | Additional Information | Comments |
|---|---|:---:|---|---|---|
| Device | Channel Count | ✔️ | Number of channels currently tuned on the device | | |
| Device | Disabled Channels | ✔️ | Number of channels marked as disabled in the channel list | List of channel names | |
| Device | Favourite Channels | ✔️ | Number of channels marked as favorites in the channel list | List of channel names | |
| Device | Tuner Count | ✔️ | Number of tuners the device has | | |
| Tuner | Tuner X | ✔️ | Status of the tuner; `Idle`, `In use`, `Scanning` or the channel being watched | Frequency, signal strength, signal quality, symbol quality, network rate and target IP (as applicable) | X is the tuner number. |
| Tuner | Frequency | ✔️ | | | |
| Tuner | Network Rate | ✔️ | | | |
| Tuner | Signal Quality | ✔️ | | | |
| Tuner | Symbol Strength | ✔️ | | | |
| Tuner | Target IP | ✔️ | | |  |

### Update

| Location | Name | Enabled by default | Comments |
|---|---|:---:|---|
| Device | Firmware | ✔️ | |

# Setup

## `Add Integration` button

If adding the integration by clicking the `Add Integration` button the
following information will be requested.

![Initial Setup Screen](images/step_user.png)

* `Host`: The IP of an HDHomeRun device on the network. Leave
  blank to carry out discovery.

  * If you provide a valid IP address, and you will be prompted for
    a friendly name.

    ![Initial Setup Screen](images/friendly_name.png)

### HTTP/UDP Discovery

This section is only applicable if you did not provide a host in the
[Add Integration](#add-integration-button) section.

![HTTP/UDP Discovery](images/http_udp_discovery.png)

Click `NEXT` and you will be prompted for a friendly name.

![Initial Setup Screen](images/friendly_name.png)

### Setup Complete

On successful set up the following screen will be seen detailing the device.

![Final Setup Screen](images/setup_finish.png)

## SSDP Discovery

The integration can also detect the HDHomeRun devices on the network using
SSDP. When found they will look like this on your devices screen.

![Initial Setup Screen](images/ssdp_discovery.png)

Clicking `CONFIGURE` you will be prompted for a friendly name.

![Initial Setup Screen](images/friendly_name.png)

## Configurable Options

It is possible to configure the following options for the integration.

### Timeouts

![Configure Options](images/config_timeouts.png)

* `Scan Interval`: the frequency of updates for the sensors, default `300s`
* `Tuner status update`: the frequency of updates for tuners, default `10s`

### Options

![Configure Options](images/config_options.png)

* `Channel logo path` - the path to a directory containing channel logos,
  e.g. `/local/channel_logos`. The default is to have no logo. If previously
  set, you can clear this option by just entering a space

You can also select which format should be used for the sensor. The
default is `Channel name`.

_This setting is only effective when a tuner is actively tuned to a channel._

## Troubleshooting

### Debug Logging

Debug logging can be enabled in Home Assistant using the [`logger`
integration](https://www.home-assistant.io/integrations/logger/).

```yaml
logger:
  default: warning
  logs:
    custom_components.hdhomerun: debug
```

### Diagnostics Integration

Starting with Home Assistant 2022.2, a new diagnostics integration can be
used to provide troubleshooting for integrations.

The highlighted area in the image below shows where the link for downloading
diagnostics can be found.

![Diagnostics](images/diagnostics.png)

An [example output](examples/diagnostics_output.json) can be found in this repo.

[badge_github_release_version]: https://img.shields.io/github/v/release/uvjim/hass_hdhomerun?display_name=release&style=for-the-badge&logoSize=auto
[badge_github_release_downloads]: https://img.shields.io/github/downloads/uvjim/hass_hdhomerun/latest/total?style=for-the-badge&label=downloads%40release
[badge_github_prerelease_version]: https://img.shields.io/github/v/release/uvjim/hass_hdhomerun?include_prereleases&display_name=release&style=for-the-badge&logoSize=auto&label=pre-release
[badge_github_prerelease_downloads]: https://img.shields.io/github/downloads-pre/uvjim/hass_hdhomerun/latest/total?style=for-the-badge&label=downloads%40pre-release
[github_release_link]: https://github.com/uvjim/hass_hdhomerun/releases/latest
[github_prerelease_link]: https://github.com/uvjim/hass_hdhomerun/releases
