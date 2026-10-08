"""Fetching remote includes (`https://…`, `http://…`) and keeping troupe from ever writing to them.

A `Fetcher` lives for one command: each URL is fetched at most once, so every reload during a `set` sees the
same content. The fetch rules (timeout, redirects, status, encoding) are decided here and nowhere else.
"""

import urllib.request
from http.client import HTTPMessage
from typing import IO
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit

from troupe.errors import LoadError

TIMEOUT = 30.0  # seconds, for connecting and for each read
USER_AGENT = "troupe"
SCHEMES = ("http", "https")


class _HttpOnlyRedirects(urllib.request.HTTPRedirectHandler):
    """Follow redirects, but only to http and https URLs (urllib would also follow ftp)."""

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: HTTPMessage,
        newurl: str,
    ) -> urllib.request.Request | None:
        if urlsplit(newurl).scheme not in SCHEMES:
            raise URLError(f"redirected to {newurl}, which is not an http or https URL")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Fetcher:
    """Fetches remote content as text, at most once per URL."""

    def __init__(self) -> None:
        self._texts: dict[str, str] = {}
        self._opener = urllib.request.build_opener(_HttpOnlyRedirects())
        self.requests = 0  # fetches made, for tests and diagnostics

    def text(self, url: str) -> str:
        cached = self._texts.get(url)
        if cached is None:
            cached = self._texts[url] = self._fetch(url)
        return cached

    def _fetch(self, url: str) -> str:
        self.requests += 1
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with self._opener.open(request, timeout=TIMEOUT) as response:
                status: int = response.status
                body: bytes = response.read()
        except HTTPError as e:
            raise LoadError(f"{url}: cannot fetch (HTTP {e.code} {e.reason})") from None
        except URLError as e:
            raise LoadError(f"{url}: cannot fetch ({e.reason})") from None
        except (OSError, ValueError) as e:  # timeouts, resets, malformed URLs
            raise LoadError(f"{url}: cannot fetch ({e})") from None
        if not 200 <= status < 300:
            raise LoadError(f"{url}: cannot fetch (HTTP {status})")
        try:
            return body.decode("utf-8")
        except UnicodeDecodeError as e:
            raise LoadError(f"{url}: not valid UTF-8 ({e.reason})") from None
