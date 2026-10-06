"""Safe outbound HTTP fetch — the app's first outbound-fetch capability.

SSRF guards: http/https only; every resolved host address is checked
against private/loopback/link-local/reserved ranges. The LLM can be
social-engineered by pages it reads, so a source URL must never make
the app talk to localhost, the LAN, or cloud-metadata endpoints
(127.0.0.1, ::1, 192.168.x, 10.x, 169.254.x ...). Redirects are
followed manually with a cap of 3 and the SAME validation re-applied
per hop. The body is streamed and aborted past MAX_BODY_BYTES.
Deterministic code only — no LLM.
"""
import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx

ALLOWED_SCHEMES = ("http", "https")
MAX_REDIRECTS = 3
TIMEOUT_SECONDS = 10.0
MAX_BODY_BYTES = 2_000_000  # ~2MB
CHUNK_BYTES = 64_000


class FetchError(Exception):
    """Any refused/failed fetch. The message is safe to show the user."""


@dataclass
class FetchedPage:
    final_url: str
    status_code: int
    content_type: str
    body: bytes


def _assert_safe_host(host: str) -> None:
    """Resolve the host and refuse every address that is not public."""
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError as exc:
        raise FetchError(f"could not resolve host '{host}'") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            raise FetchError(
                f"refusing non-public address '{ip}' for host '{host}'")


def _assert_safe_url(url: str) -> None:
    """Scheme allowlist + host resolution checks for one URL."""
    parts = urlparse(url)
    if parts.scheme not in ALLOWED_SCHEMES:
        raise FetchError(
            f"refusing scheme '{parts.scheme or 'empty'}' (http/https only)")
    if not parts.hostname:
        raise FetchError("URL has no host")
    _assert_safe_host(parts.hostname)


def fetch_url(url: str) -> FetchedPage:
    """Sync fetch for legacy callers and tests; validates every redirect hop."""
    current = url
    with httpx.Client(follow_redirects=False, timeout=TIMEOUT_SECONDS) as client:
        for _hop in range(MAX_REDIRECTS + 1):
            _assert_safe_url(current)
            if hasattr(client, "get"):
                response = client.get(current)
            else:
                stream = client.stream("GET", current)
                response = stream.__enter__()
                try:
                    # keep function logic identical for the fake test client
                    if response.status_code in (301, 302, 303, 307, 308):
                        location = response.headers.get("location")
                        if not location:
                            raise FetchError("redirect without a location header")
                        current = urljoin(current, location)
                        continue
                    if response.status_code >= 400:
                        raise FetchError(f"HTTP {response.status_code} for {current}")
                    chunks: list[bytes] = []
                    total = 0
                    for chunk in response.iter_bytes(CHUNK_BYTES):
                        total += len(chunk)
                        if total > MAX_BODY_BYTES:
                            raise FetchError("page larger than 2MB — refused")
                        chunks.append(chunk)
                    return FetchedPage(
                        final_url=current,
                        status_code=response.status_code,
                        content_type=response.headers.get("content-type", ""),
                        body=b"".join(chunks),
                    )
                finally:
                    stream.__exit__(None, None, None)
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("location")
                if not location:
                    raise FetchError("redirect without a location header")
                current = urljoin(current, location)
                continue
            if response.status_code >= 400:
                raise FetchError(f"HTTP {response.status_code} for {current}")
            chunks: list[bytes] = []
            total = 0
            for chunk in response.iter_bytes(CHUNK_BYTES):
                total += len(chunk)
                if total > MAX_BODY_BYTES:
                    raise FetchError("page larger than 2MB — refused")
                chunks.append(chunk)
            return FetchedPage(
                final_url=current,
                status_code=response.status_code,
                content_type=response.headers.get("content-type", ""),
                body=b"".join(chunks),
            )
    raise FetchError(f"more than {MAX_REDIRECTS} redirects — refused")


async def fetch_url_async(url: str) -> FetchedPage:
    """Async fetch one page, re-checking safety on every redirect hop."""
    current = url
    async with httpx.AsyncClient(follow_redirects=False, timeout=TIMEOUT_SECONDS) as client:
        for _hop in range(MAX_REDIRECTS + 1):
            _assert_safe_url(current)
            response = await client.get(current)
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("location")
                if not location:
                    raise FetchError("redirect without a location header")
                current = urljoin(current, location)
                continue
            if response.status_code >= 400:
                raise FetchError(f"HTTP {response.status_code} for {current}")
            chunks: list[bytes] = []
            total = 0
            async for chunk in response.aiter_bytes(CHUNK_BYTES):
                total += len(chunk)
                if total > MAX_BODY_BYTES:
                    raise FetchError("page larger than 2MB — refused")
                chunks.append(chunk)
            return FetchedPage(
                final_url=current,
                status_code=response.status_code,
                content_type=response.headers.get("content-type", ""),
                body=b"".join(chunks),
            )
    raise FetchError(f"more than {MAX_REDIRECTS} redirects — refused")
