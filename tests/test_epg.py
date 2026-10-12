"""Tests for the optional XMLTV cache, validation and capability endpoint."""

import gzip
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from homeassistant.components.http import KEY_HASS

from custom_components.hdhomerun import epg

GUIDE = (
    b'<tv><channel id="7"><display-name>7.1</display-name></channel>'
    b'<programme channel="7" start="20261004080000 -0500" '
    b'stop="20261004090000 -0500"><title>News</title></programme></tv>'
)


def test_xmltv_validation():
    """Reject wrong roots, broken references/times and DTDs."""
    summary = epg.inspect_xmltv(GUIDE)
    assert (summary["channels"], summary["programmes"]) == (1, 1)
    assert summary["coverage_start"] == "2026-10-04T08:00:00-05:00"
    assert summary["channel_names"] == ["7.1"]
    for invalid in (
        b"<html>Forbidden</html>",
        b"<tv><channel id='7'/></tv>",
        GUIDE.replace(b'channel="7" start', b'channel="8" start'),
        GUIDE.replace(b"20261004090000", b"20261004070000"),
        b'<!DOCTYPE tv [<!ENTITY x "oops">]>' + GUIDE,
    ):
        with pytest.raises(ValueError):
            epg.inspect_xmltv(invalid)


def test_incremental_validation_handles_order_and_size_boundary(monkeypatch):
    """Channel references may precede definitions; the cap is inclusive."""
    channel = b'<channel id="7"><display-name>7.1</display-name></channel>'
    programme = GUIDE.split(b"</channel>", 1)[1].removesuffix(b"</tv>")
    reordered = b"<tv>" + programme + channel + b"</tv>"
    assert epg.inspect_xmltv(reordered)["programmes"] == 1
    monkeypatch.setattr(epg, "_MAX_XML", len(reordered))
    assert epg.inspect_xmltv(reordered)["channels"] == 1
    monkeypatch.setattr(epg, "_MAX_XML", len(reordered) - 1)
    with pytest.raises(ValueError):
        epg.inspect_xmltv(reordered)


def test_14_day_feed_larger_than_old_limit():
    """A plausible 14-day guide must pass the new bounded parser."""
    first = datetime(2026, 10, 5, tzinfo=timezone.utc)
    description = b"x" * 1_600_000
    programmes = []
    for day in range(14):
        start = first + timedelta(days=day)
        stop = start + timedelta(days=1)
        programmes.append(
            b'<programme channel="7" start="'
            + start.strftime("%Y%m%d%H%M%S +0000").encode()
            + b'" stop="'
            + stop.strftime("%Y%m%d%H%M%S +0000").encode()
            + b'"><desc>'
            + description
            + b"</desc></programme>"
        )
    guide = b'<tv><channel id="7"/>' + b"".join(programmes) + b"</tv>"
    assert 20 * 1024 * 1024 < len(guide) < epg._MAX_XML
    summary = epg.inspect_xmltv(guide)
    assert summary["programmes"] == 14
    assert summary["coverage_end"] == "2026-10-19T00:00:00+00:00"


class Store:
    def __init__(self, data=None):
        self.data = data
        self.fail = False

    async def async_load(self):
        return self.data

    async def async_save(self, data):
        if self.fail:
            raise OSError("disk full")
        self.data = data


class Response:
    def __init__(self, body):
        self.body = body
        self.content = self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    def raise_for_status(self):
        pass

    async def read(self, _):
        return self.body

    async def iter_chunked(self, _):
        yield self.body


class Session:
    def __init__(self, xml):
        self.xml = xml
        self.requests = []

    def get(self, url, **kwargs):
        self.requests.append((url, kwargs))
        if url.endswith("discover.json"):
            return Response(json.dumps({"DeviceAuth": "fresh-secret"}).encode())
        return Response(self.xml)


class Hass:
    async def async_add_executor_job(self, func, *args):
        return func(*args)


@pytest.mark.asyncio
async def test_refresh_failure_retains_snapshot_and_rotation_revokes(monkeypatch):
    session = Session(GUIDE)
    monkeypatch.setattr(epg, "async_get_clientsession", lambda _: session)
    monkeypatch.setattr(epg, "Store", lambda *args, **kwargs: Store())
    proxy = epg.EPGProxy(Hass(), "entry", "192.0.2.1", 6)
    await proxy.load()
    old_token = proxy.token
    await proxy.refresh()
    assert session.requests[0][0] == "http://192.0.2.1/discover.json"
    assert session.requests[1][1]["params"] == {"DeviceAuth": "fresh-secret"}
    assert all(kwargs["allow_redirects"] is False for _, kwargs in session.requests)
    assert session.requests[1][1]["headers"]["Accept-Encoding"] == "gzip"
    assert "fresh-secret" not in repr(proxy.store.data)
    assert proxy.xml == GUIDE.decode()
    session.xml = b"Forbidden"
    await proxy.refresh()
    assert proxy.xml == GUIDE.decode() and proxy.error == "ParseError"
    assert gzip.decompress(proxy.xml_gzip) == GUIDE
    assert proxy.store.data["xml"] == GUIDE.decode()
    session.xml = GUIDE.replace(b"News", b"Weather")
    proxy.store.fail = True
    assert not await proxy.refresh()
    assert proxy.xml == GUIDE.decode()
    assert gzip.decompress(proxy.xml_gzip) == GUIDE
    proxy.store.fail = False

    tokens = {old_token: proxy}
    await proxy.rotate(tokens)
    assert old_token not in tokens and tokens[proxy.token] is proxy
    request = SimpleNamespace(
        app={KEY_HASS: SimpleNamespace(data={"hdhomerun": {"_epg_tokens": tokens}})},
        path=f"/api/hdhomerun/xmltv/{proxy.token}",
        headers={},
    )
    with pytest.raises(web.HTTPNotFound):
        await epg.XMLTVView().get(request, old_token)
    result = await epg.XMLTVView().get(request, proxy.token)
    assert result.text == GUIDE.decode()
    assert result.headers["Cache-Control"] == "no-store"

    latest = proxy.token
    proxy.store.fail = True
    with pytest.raises(OSError):
        await proxy.rotate(tokens)
    assert proxy.token == latest and latest in tokens


@pytest.mark.asyncio
async def test_oversize_and_restart_keep_good_cache(monkeypatch):
    """Do not replace a good snapshot with an oversized feed; restore it on restart."""
    session = Session(GUIDE)
    monkeypatch.setattr(epg, "async_get_clientsession", lambda _: session)
    stored = Store()
    monkeypatch.setattr(epg, "Store", lambda *args, **kwargs: stored)
    proxy = epg.EPGProxy(Hass(), "entry", "192.0.2.1", 6)
    await proxy.load()
    assert await proxy.refresh()
    monkeypatch.setattr(epg, "_MAX_XML", len(GUIDE) + 1)
    session.xml = GUIDE + b"extra"
    assert not await proxy.refresh()
    assert proxy.xml == GUIDE.decode()
    restored = epg.EPGProxy(Hass(), "entry", "192.0.2.1", 6)
    await restored.load()
    assert restored.token == proxy.token
    assert restored.xml == GUIDE.decode()
    assert restored.fetched_at == proxy.fetched_at
    assert gzip.decompress(restored.xml_gzip) == GUIDE


@pytest.mark.asyncio
async def test_short_tokens_and_compressed_http_formats(monkeypatch):
    """Serve identical guides with negotiated gzip or explicit gzip-file URLs."""
    stored = Store({"token": "a" * 64, "xml": GUIDE.decode()})
    monkeypatch.setattr(epg, "Store", lambda *args, **kwargs: stored)
    proxy = epg.EPGProxy(Hass(), "entry", "192.0.2.1", 6)
    await proxy.load()
    assert len(proxy.token) == 22
    assert stored.data["token"] == proxy.token
    restored = epg.EPGProxy(Hass(), "entry", "192.0.2.1", 6)
    await restored.load()
    assert restored.token == proxy.token
    tokens = {proxy.token: proxy}
    app = web.Application()
    app[KEY_HASS] = SimpleNamespace(data={"hdhomerun": {"_epg_tokens": tokens}})
    view = epg.XMLTVView()

    async def serve(request):
        return await view.get(request, request.match_info["token"])

    for route in [view.url, *view.extra_urls]:
        app.router.add_get(route, serve)
    async with TestClient(TestServer(app), auto_decompress=False) as client:
        path = f"/api/hdhomerun/xmltv/{proxy.token}"
        for encoding, compressed in (
            ("identity", False),
            ("gzip", True),
            ("br, gzip;q=0.5", True),
            ("gzip;q=0.5, identity;q=1", False),
            ("*;q=1, gzip;q=0", False),
            ("*;q=0.5", True),
            ("gzip;q=invalid", False),
        ):
            response = await client.get(path, headers={"Accept-Encoding": encoding})
            assert response.status == 200
            body = await response.read()
            assert (gzip.decompress(body) if compressed else body) == GUIDE
            assert response.headers.get("Content-Encoding") == ("gzip" if compressed else None)
            assert response.headers["Vary"] == "Accept-Encoding"
        for encoding in ("gzip;q=0, identity;q=0", "*;q=0"):
            response = await client.get(path, headers={"Accept-Encoding": encoding})
            assert response.status == 406
        response = await client.get(path + ".xml.gz")
        assert response.status == 200
        assert response.content_type == "application/gzip"
        assert "Content-Encoding" not in response.headers
        assert gzip.decompress(await response.read()) == GUIDE
        assert (await client.get("/api/hdhomerun/xmltv/" + "a" * 64)).status == 404
        await proxy.rotate(tokens)
        assert len(proxy.token) == 22
        assert (await client.get(path)).status == 404
        assert (await client.get(path + ".xml.gz")).status == 404
        proxy.xml = None
        assert (await client.get(f"/api/hdhomerun/xmltv/{proxy.token}.xml.gz")).status == 503
