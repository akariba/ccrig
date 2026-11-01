"""Hardened retrieval for approved sources. https only, approved hosts only, public addresses only, size/time limits, bounded redirects.

Network access is OFF unless CCRIG_DISCOVERY_NETWORK=1 (an operator decision). Tests and offline use inject a Transport that never touches the network.
"""
from __future__ import annotations

import http.client
import ipaddress
import os
import socket
import ssl
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional, Protocol
from urllib.parse import urljoin, urlsplit

MAX_BYTES = 6_000_000
TIMEOUT = 20
MAX_REDIRECTS = 3
ALLOWED_TYPES = ("text/html", "text/xml", "application/xml", "application/rss+xml", "application/atom+xml", "application/json", "text/plain")


class FetchRefused(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


@dataclass
class FetchResult:
    url: str
    final_url: str
    status: int
    content_type: str
    body: bytes
    fetched_at: str = field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))


class Transport(Protocol):
    def get(self, url: str, accept: str = "*/*") -> FetchResult: ...


def network_enabled() -> bool:
    return os.environ.get("CCRIG_DISCOVERY_NETWORK", "").strip().lower() in ("1", "true", "yes", "on")


def user_agent() -> str:
    contact = os.environ.get("CCRIG_DISCOVERY_CONTACT", "").strip()
    return "CCRIG-event-discovery/0.1" + (f" ({contact})" if contact else "")


def check_url(url: str, host_ok: Callable[[str], bool]) -> str:
    """Return the lowercase host or raise FetchRefused. https, no credentials, default port, not an IP literal, host approved."""
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise FetchRefused("NOT_HTTPS", "only https URLs are retrieved")
    if parts.username or parts.password or "@" in parts.netloc:
        raise FetchRefused("CREDENTIALS_IN_URL", "URLs with credentials are refused")
    if parts.port not in (None, 443):
        raise FetchRefused("BAD_PORT", "only the default https port is allowed")
    host = (parts.hostname or "").lower()
    if not host:
        raise FetchRefused("NO_HOST", "the URL has no host")
    try:
        ipaddress.ip_address(host)
        raise FetchRefused("IP_LITERAL", "IP addresses are not accepted as hosts")
    except ValueError:
        pass
    if not host_ok(host):
        raise FetchRefused("HOST_NOT_APPROVED", f"'{host}' is not on an approved source domain")
    return host


def check_addresses(addresses) -> list:
    """Every resolved address must be globally routable (no loopback, private, link-local, multicast, reserved)."""
    ips = []
    for a in addresses:
        ip = ipaddress.ip_address(a)
        if not ip.is_global:
            raise FetchRefused("PRIVATE_ADDRESS", f"the host resolves to a non-public address ({ip})")
        ips.append(str(ip))
    if not ips:
        raise FetchRefused("NO_ADDRESS", "the host did not resolve")
    return ips


class _Pinned(http.client.HTTPSConnection):
    """Connects to an address we already vetted (so DNS cannot change between the check and the connection), verifying TLS for the real host name."""

    def __init__(self, host, ip, **kw):
        super().__init__(host, timeout=TIMEOUT, context=ssl.create_default_context(), **kw)
        self._ip = ip

    def connect(self):
        sock = socket.create_connection((self._ip, 443), TIMEOUT)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class HttpTransport:
    def __init__(self, host_ok: Callable[[str], bool]):
        self.host_ok = host_ok

    def get(self, url: str, accept: str = "*/*") -> FetchResult:
        if not network_enabled():
            raise FetchRefused("NETWORK_DISABLED", "network discovery is not enabled (set CCRIG_DISCOVERY_NETWORK=1 on an operator machine)")
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            host = check_url(current, self.host_ok)
            try:
                infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            except socket.gaierror as exc:
                raise FetchRefused("DNS_FAILED", str(exc)) from None
            ip = check_addresses(sorted({i[4][0] for i in infos}))[0]
            parts = urlsplit(current)
            conn = _Pinned(host, ip)
            try:
                conn.request("GET", parts.path + (f"?{parts.query}" if parts.query else "") or "/", headers={"User-Agent": user_agent(), "Accept": accept, "Accept-Encoding": "identity"})
                resp = conn.getresponse()
                if resp.status in (301, 302, 303, 307, 308):
                    loc = resp.getheader("Location")
                    if not loc:
                        raise FetchRefused("BAD_REDIRECT", "redirect without a location")
                    current = urljoin(current, loc)
                    continue
                ctype = (resp.getheader("Content-Type") or "").split(";")[0].strip().lower()
                if ctype and not any(ctype == t or ctype.endswith("+xml") or ctype.endswith("+json") for t in ALLOWED_TYPES):
                    raise FetchRefused("CONTENT_TYPE", f"content type '{ctype}' is not accepted")
                body = resp.read(MAX_BYTES + 1)
                if len(body) > MAX_BYTES:
                    raise FetchRefused("OVERSIZE", f"the response exceeds {MAX_BYTES:,} bytes")
                return FetchResult(url, current, resp.status, ctype, body)
            except (OSError, http.client.HTTPException, ssl.SSLError) as exc:
                raise FetchRefused("NETWORK_ERROR", f"{type(exc).__name__}: {str(exc)[:120]}") from None
            finally:
                conn.close()
        raise FetchRefused("TOO_MANY_REDIRECTS", f"more than {MAX_REDIRECTS} redirects")


class FixtureTransport:
    """Serves recorded responses, never touching the network (tests, offline demos). Unknown URLs raise FetchRefused like a closed network would."""

    def __init__(self, responses: dict, host_ok: Optional[Callable[[str], bool]] = None):
        self.responses, self.host_ok, self.requested = responses, host_ok, []

    def get(self, url: str, accept: str = "*/*") -> FetchResult:
        if self.host_ok:
            check_url(url, self.host_ok)
        self.requested.append(url)
        if url not in self.responses:
            raise FetchRefused("NOT_RECORDED", f"no recorded response for {url}")
        status, ctype, body = self.responses[url]
        return FetchResult(url, url, status, ctype, body if isinstance(body, bytes) else body.encode("utf-8"), "2026-11-01T10:00:00Z")
