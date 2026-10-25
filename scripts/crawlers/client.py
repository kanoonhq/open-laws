"""Polite, resumable HTTP client (PROCUREMENT_PLAN §6), one policy for every
portal:
- a content-addressed cache keyed by the SHA-256 of the normalised request, so
  an interrupted crawl resumes with zero repeat requests;
- at most 2 concurrent requests per host;
- at least 500ms between request starts per host, plus 200-500ms jitter;
- robots.txt honoured (fetched once per host, through the same policy);
- 429/503/504 and connection failures back off 10s -> 30s -> 60s, with a fresh
  session before each retry;
- an honest User-Agent naming the project repo. A browser User-Agent is
  refused, never spoofed.
Redirects are not followed: a 3xx is returned (and cached) as it is.
The clock and RNG are injectable, so tests run without real sleeps.
"""

from __future__ import annotations

import hashlib
import json
import random
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from crawlers import warc

REPO_URL = "https://github.com/kanoonhq/open-laws"
CRAWLER_VERSION = "0.3.0"
DEFAULT_USER_AGENT = f"open-laws-crawler/{CRAWLER_VERSION} (+{REPO_URL})"
MAX_PER_HOST = 2
MIN_INTERVAL = 0.5
JITTER = (0.2, 0.5)
BACKOFF = (10.0, 30.0, 60.0)
RETRY_STATUSES = {429, 503, 504}
DEFAULT_PORTS = {"http": 80, "https": 443}
TIMEOUT = 60.0


class Clock(Protocol):
    def monotonic(self) -> float: ...
    def sleep(self, seconds: float) -> None: ...
    def now(self) -> datetime: ...


class Rng(Protocol):
    def uniform(self, low: float, high: float) -> float: ...


class SystemClock:
    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def now(self) -> datetime:
        return datetime.now(UTC)


class RobotsDisallowed(Exception):
    """robots.txt forbids this URL for our User-Agent."""


class RetryExhausted(Exception):
    """The URL kept failing (429/503/504 or no connection) after every backoff."""


@dataclass(frozen=True)
class Response:
    url: str
    status: int
    reason: str
    headers: list[tuple[str, str]]
    body: bytes
    sha256: str
    retrieved_at: str
    warc_file: str | None
    from_cache: bool


@dataclass
class HostState:
    slots: threading.BoundedSemaphore
    pace: threading.Lock = field(default_factory=threading.Lock)
    robots: threading.Lock = field(default_factory=threading.Lock)
    last_start: float | None = None
    parser: RobotFileParser | None = None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any) -> None:
        return None


def normalise_url(url: str) -> str:
    """Lower-case scheme and host, drop the default port and the fragment,
    default the path to "/" and sort the query."""
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in DEFAULT_PORTS:
        raise ValueError(f"unsupported URL scheme: {url}")
    host = (parts.hostname or "").lower()
    netloc = host if parts.port in (None, DEFAULT_PORTS[scheme]) else f"{host}:{parts.port}"
    query = urlencode(sorted(parse_qsl(parts.query, keep_blank_values=True)))
    return urlunsplit((scheme, netloc, parts.path or "/", query, ""))


def request_key(method: str, url: str) -> str:
    return hashlib.sha256(f"{method.upper()} {normalise_url(url)}".encode()).hexdigest()


def check_user_agent(user_agent: str) -> str:
    if REPO_URL not in user_agent:
        raise ValueError(f"User-Agent must contain {REPO_URL}: {user_agent!r}")
    if "mozilla" in user_agent.lower():
        raise ValueError(f"User-Agent must not imitate a browser: {user_agent!r}")
    return user_agent


class PoliteClient:
    def __init__(self, cache_dir: Path, *, user_agent: str = DEFAULT_USER_AGENT,
                 clock: Clock | None = None, rng: Rng | None = None,
                 max_per_host: int = MAX_PER_HOST, min_interval: float = MIN_INTERVAL,
                 jitter: tuple[float, float] = JITTER, backoff: tuple[float, ...] = BACKOFF,
                 timeout: float = TIMEOUT) -> None:
        self.cache_dir = Path(cache_dir)
        self.user_agent = check_user_agent(user_agent)
        self.clock = clock or SystemClock()
        self.rng = rng or random.Random()
        self.max_per_host = max_per_host
        self.min_interval = min_interval
        self.jitter = jitter
        self.backoff = backoff
        self.timeout = timeout
        self._hosts: dict[str, HostState] = {}
        self._lock = threading.Lock()
        self._opener = self._new_session()

    def get(self, url: str) -> Response:
        """The response for url: from the cache, else from the network under
        the politeness policy. Raises RobotsDisallowed or RetryExhausted."""
        url = normalise_url(url)
        if (cached := self._from_cache(url)) is not None:
            return cached
        if not self._robots(url).can_fetch(self.user_agent, url):
            raise RobotsDisallowed(url)
        # Fetching robots.txt may have just cached url itself.
        return self._from_cache(url) or self._fetch(url)

    # --- cache -----------------------------------------------------------------

    def _meta_path(self, url: str) -> Path:
        return self.cache_dir / "responses" / f"{request_key('GET', url)}.json"

    def _from_cache(self, url: str) -> Response | None:
        meta_path = self._meta_path(url)
        if not meta_path.exists():
            return None
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        body_path = self.cache_dir / "bodies" / meta["sha256"]
        if not body_path.exists():
            return None
        return Response(url=url, status=meta["status"], reason=meta["reason"],
                        headers=[tuple(h) for h in meta["headers"]], body=body_path.read_bytes(),
                        sha256=meta["sha256"], retrieved_at=meta["retrieved_at"],
                        warc_file=meta["warc_file"], from_cache=True)

    def _store(self, response: Response) -> None:
        body_path = self.cache_dir / "bodies" / response.sha256
        write_atomic(body_path, response.body)
        meta = {
            "url": response.url,
            "method": "GET",
            "status": response.status,
            "reason": response.reason,
            "headers": response.headers,
            "sha256": response.sha256,
            "retrieved_at": response.retrieved_at,
            "warc_file": response.warc_file,
        }
        write_atomic(self._meta_path(response.url),
                     json.dumps(meta, ensure_ascii=False, indent=1).encode("utf-8"))

    # --- politeness ------------------------------------------------------------

    def _host(self, url: str) -> HostState:
        netloc = urlsplit(url).netloc
        with self._lock:
            if netloc not in self._hosts:
                self._hosts[netloc] = HostState(threading.BoundedSemaphore(self.max_per_host))
            return self._hosts[netloc]

    def _robots(self, url: str) -> RobotFileParser:
        host = self._host(url)
        with host.robots:
            if host.parser is None:
                parts = urlsplit(url)
                robots_url = urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))
                response = self._from_cache(robots_url) or self._fetch(robots_url)
                parser = RobotFileParser(robots_url)
                if response.status in (401, 403) or response.status >= 500:
                    parser.disallow_all = True
                elif response.status >= 400:
                    parser.allow_all = True
                else:
                    parser.parse(response.body.decode("utf-8", errors="replace").splitlines())
                host.parser = parser
            return host.parser

    def _pace(self, host: HostState) -> None:
        """Wait until min_interval plus jitter has passed since the host's last start."""
        with host.pace:
            if host.last_start is not None:
                gap = self.min_interval + self.rng.uniform(*self.jitter)
                if (wait := host.last_start + gap - self.clock.monotonic()) > 0:
                    self.clock.sleep(wait)
            host.last_start = self.clock.monotonic()

    def _fetch(self, url: str) -> Response:
        host = self._host(url)
        failure = ""
        for pause in (*self.backoff, None):
            hint = 0.0
            with host.slots:
                self._pace(host)
                try:
                    status, reason, headers, body = self._send(url)
                except (urllib.error.URLError, OSError) as exc:
                    failure = f"no response ({exc})"
                else:
                    if status not in RETRY_STATUSES:
                        return self._record(url, status, reason, headers, body)
                    failure, hint = f"HTTP {status}", retry_after(headers)
            if pause is None:
                break
            self.clock.sleep(max(pause, hint))
            with self._lock:
                self._opener = self._new_session()
        raise RetryExhausted(f"{url}: {failure} after {len(self.backoff)} retries")

    # --- network ---------------------------------------------------------------

    def _new_session(self) -> urllib.request.OpenerDirector:
        return urllib.request.build_opener(NoRedirect())

    def _request_headers(self) -> dict[str, str]:
        return {"User-Agent": self.user_agent, "Accept-Encoding": "identity",
                "Connection": "close"}

    def _send(self, url: str) -> tuple[int, str, list[tuple[str, str]], bytes]:
        request = urllib.request.Request(url, headers=self._request_headers(), method="GET")
        with self._lock:
            opener = self._opener
        try:
            with opener.open(request, timeout=self.timeout) as resp:
                return resp.status, resp.reason, list(resp.headers.items()), resp.read()
        except urllib.error.HTTPError as err:
            with err:
                return err.code, str(err.reason), list(err.headers.items()), err.read()

    def _record(self, url: str, status: int, reason: str, headers: list[tuple[str, str]],
                body: bytes) -> Response:
        """Archive the exchange to WARC and, unless it is a server error, cache it."""
        when = self.clock.now()
        parts = urlsplit(url)
        path = urlunsplit(("", "", parts.path, parts.query, ""))
        request = warc.http_request_block("GET", path, {"Host": parts.netloc,
                                                        **self._request_headers()})
        warc_path = warc.write_exchange(
            self.cache_dir / "warc", url=url, date=when, request=request,
            response=warc.http_response_block(status, reason, headers, body), payload=body)
        response = Response(url=url, status=status, reason=reason, headers=headers, body=body,
                            sha256=hashlib.sha256(body).hexdigest(),
                            retrieved_at=when.strftime("%Y-%m-%dT%H:%M:%SZ"),
                            warc_file=warc_path.relative_to(self.cache_dir).as_posix(),
                            from_cache=False)
        if status < 500:
            self._store(response)
        return response


def retry_after(headers: list[tuple[str, str]]) -> float:
    """A Retry-After given in seconds, else 0 (an HTTP-date is ignored)."""
    for name, value in headers:
        if name.lower() == "retry-after" and value.strip().isdigit():
            return float(value.strip())
    return 0.0


def write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{threading.get_ident()}.tmp")
    tmp.write_bytes(data)
    tmp.replace(path)
