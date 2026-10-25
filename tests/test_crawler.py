"""Seam 2 (ticket #12): the crawler framework against a local http.server that
serves scripted responses. Tests assert on the requests the server saw, the
sleeps taken on an injected clock, and the WARC records written. No test makes
a request to any real portal."""

from __future__ import annotations

import hashlib
import json
import socket
import subprocess
import sys
import threading
import time
import zlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from crawlers import record, warc  # noqa: E402
from crawlers.client import (  # noqa: E402
    REPO_URL,
    PoliteClient,
    RetryExhausted,
    RobotsDisallowed,
)

Scripted = tuple[int, dict[str, str], bytes]
NOT_FOUND: Scripted = (404, {}, b"not found")


@dataclass
class Seen:
    path: str
    headers: dict[str, str]


@dataclass
class FixtureServer:
    """Serves script[path] responses in order (the last one repeats) and
    records every request; `delay` holds each response open, in real seconds."""

    script: dict[str, list[Scripted]] = field(default_factory=dict)
    seen: list[Seen] = field(default_factory=list)
    delay: float = 0.0
    in_flight: int = 0
    max_in_flight: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)
    base: str = ""

    def respond(self, path: str) -> Scripted:
        with self.lock:
            queue = self.script.get(path) or [NOT_FOUND]
            return queue.pop(0) if len(queue) > 1 else queue[0]

    def paths(self) -> list[str]:
        return [s.path for s in self.seen]


@pytest.fixture
def server() -> Iterator[FixtureServer]:
    state = FixtureServer()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            with state.lock:
                state.seen.append(Seen(self.path, dict(self.headers)))
                state.in_flight += 1
                state.max_in_flight = max(state.max_in_flight, state.in_flight)
            try:
                if state.delay:
                    time.sleep(state.delay)
                status, headers, body = state.respond(self.path)
                self.send_response(status)
                for name, value in headers.items():
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            finally:
                with state.lock:
                    state.in_flight -= 1

        def log_message(self, *args: object) -> None:
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    state.base = f"http://127.0.0.1:{httpd.server_address[1]}"
    thread = threading.Thread(target=httpd.serve_forever, args=(0.05,), daemon=True)
    thread.start()
    yield state
    httpd.shutdown()
    httpd.server_close()


class FakeClock:
    """Time moves only when the crawler sleeps (or a test advances it)."""

    def __init__(self) -> None:
        self.t = 1000.0
        self.sleeps: list[float] = []
        self.lock = threading.Lock()

    def monotonic(self) -> float:
        with self.lock:
            return self.t

    def sleep(self, seconds: float) -> None:
        with self.lock:
            self.sleeps.append(round(seconds, 6))
            self.t += seconds

    def now(self) -> datetime:
        return datetime(2026, 1, 1, tzinfo=UTC)


class StubRng:
    """Returns the scripted jitter values in turn and records the ranges asked."""

    def __init__(self, *values: float) -> None:
        self.values = list(values) or [0.2]
        self.ranges: list[tuple[float, float]] = []

    def uniform(self, low: float, high: float) -> float:
        self.ranges.append((low, high))
        return self.values.pop(0) if len(self.values) > 1 else self.values[0]


def make_client(tmp_path: Path, clock: FakeClock | None = None,
                rng: StubRng | None = None, **kwargs: object) -> PoliteClient:
    return PoliteClient(tmp_path / "cache", clock=clock or FakeClock(),
                        rng=rng or StubRng(), **kwargs)


def ok(body: bytes, content_type: str = "text/html") -> list[Scripted]:
    return [(200, {"Content-Type": content_type}, body)]


def test_rerun_is_served_from_cache_with_zero_requests(server: FixtureServer, tmp_path: Path) -> None:
    server.script["/act/1"] = ok(b"<p>Section 1</p>")

    first = make_client(tmp_path).get(server.base + "/act/1")
    assert (first.status, first.body, first.from_cache) == (200, b"<p>Section 1</p>", False)
    assert server.paths() == ["/robots.txt", "/act/1"]

    server.seen.clear()
    again = make_client(tmp_path).get(server.base + "/act/1")
    assert (again.status, again.body, again.from_cache) == (200, b"<p>Section 1</p>", True)
    assert server.paths() == []


def test_cache_key_normalises_the_request(server: FixtureServer, tmp_path: Path) -> None:
    server.script["/s?a=1&b=2"] = ok(b"one")
    client = make_client(tmp_path)
    client.get(server.base + "/s?a=1&b=2")
    assert client.get(server.base.replace("http:", "HTTP:") + "/s?b=2&a=1#frag").from_cache
    assert server.paths().count("/s?a=1&b=2") == 1


def test_user_agent_names_the_repo_and_is_not_a_browser(server: FixtureServer, tmp_path: Path) -> None:
    server.script["/a"] = ok(b"a")
    make_client(tmp_path).get(server.base + "/a")
    agents = {s.headers["User-Agent"] for s in server.seen}
    assert len(agents) == 1
    (agent,) = agents
    assert REPO_URL == "https://github.com/kanoonhq/open-laws"
    assert REPO_URL in agent
    assert "@" not in agent and "Mozilla" not in agent


@pytest.mark.parametrize("agent", ["my-crawler/1.0", "Mozilla/5.0 (+https://github.com/kanoonhq/open-laws)"])
def test_user_agent_without_repo_url_or_spoofing_a_browser_is_refused(tmp_path: Path, agent: str) -> None:
    with pytest.raises(ValueError):
        make_client(tmp_path, user_agent=agent)


def test_requests_to_a_host_are_spaced_by_interval_plus_jitter(server: FixtureServer, tmp_path: Path) -> None:
    for name in ("a", "b"):
        server.script[f"/{name}"] = ok(name.encode())
    clock, rng = FakeClock(), StubRng(0.3, 0.45)
    client = make_client(tmp_path, clock, rng)

    client.get(server.base + "/a")
    client.get(server.base + "/b")

    assert server.paths() == ["/robots.txt", "/a", "/b"]
    # robots.txt goes first with no wait; then 500ms + 300ms, then 500ms + 450ms.
    assert clock.sleeps == [0.8, 0.95]
    assert rng.ranges == [(0.2, 0.5), (0.2, 0.5)]


def test_no_wait_once_the_interval_has_already_passed(server: FixtureServer, tmp_path: Path) -> None:
    server.script["/a"] = ok(b"a")
    clock = FakeClock()
    client = make_client(tmp_path, clock, StubRng(0.5))
    client.get(server.base + "/robots.txt")
    clock.t += 1.0
    client.get(server.base + "/a")
    assert clock.sleeps == []


def test_at_most_two_concurrent_requests_per_host(server: FixtureServer, tmp_path: Path) -> None:
    for i in range(6):
        server.script[f"/p{i}"] = ok(b"p")
    client = make_client(tmp_path)
    client.get(server.base + "/robots.txt")
    server.delay = 0.05

    threads = [threading.Thread(target=client.get, args=(f"{server.base}/p{i}",)) for i in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(server.paths()[1:]) == [f"/p{i}" for i in range(6)]
    assert server.max_in_flight == 2


def test_robots_txt_disallow_is_honoured(server: FixtureServer, tmp_path: Path) -> None:
    server.script["/robots.txt"] = ok(b"User-agent: *\nDisallow: /private\n", "text/plain")
    server.script["/public"] = ok(b"open")
    client = make_client(tmp_path)

    with pytest.raises(RobotsDisallowed):
        client.get(server.base + "/private/act")
    assert client.get(server.base + "/public").body == b"open"
    assert server.paths() == ["/robots.txt", "/public"]


def test_robots_txt_forbidden_disallows_everything(server: FixtureServer, tmp_path: Path) -> None:
    server.script["/robots.txt"] = [(403, {}, b"forbidden")]
    with pytest.raises(RobotsDisallowed):
        make_client(tmp_path).get(server.base + "/a")
    assert server.paths() == ["/robots.txt"]


@pytest.mark.parametrize("status", [429, 503, 504])
def test_throttling_backs_off_10_30_60_then_succeeds(server: FixtureServer, tmp_path: Path,
                                                     status: int) -> None:
    server.script["/slow"] = [(status, {}, b"busy")] * 3 + ok(b"done")
    clock = FakeClock()
    response = make_client(tmp_path, clock, StubRng(0.2)).get(server.base + "/slow")

    assert response.body == b"done"
    assert server.paths() == ["/robots.txt"] + ["/slow"] * 4
    # 700ms pacing after robots.txt, then the three backoffs.
    assert clock.sleeps == [0.7, 10.0, 30.0, 60.0]


def test_throttling_that_never_ends_raises_and_is_not_cached(server: FixtureServer,
                                                             tmp_path: Path) -> None:
    server.script["/down"] = [(503, {}, b"busy")]
    clock = FakeClock()
    with pytest.raises(RetryExhausted):
        make_client(tmp_path, clock).get(server.base + "/down")
    assert server.paths().count("/down") == 4
    assert clock.sleeps[-3:] == [10.0, 30.0, 60.0]

    server.seen.clear()
    with pytest.raises(RetryExhausted):
        make_client(tmp_path).get(server.base + "/down")
    assert server.paths().count("/down") == 4


def test_retry_after_longer_than_the_backoff_is_respected(server: FixtureServer, tmp_path: Path) -> None:
    server.script["/slow"] = [(429, {"Retry-After": "120"}, b"")] + ok(b"done")
    clock = FakeClock()
    make_client(tmp_path, clock, StubRng(0.2)).get(server.base + "/slow")
    assert clock.sleeps == [0.7, 120.0]


def test_warc_round_trips_the_exact_bytes_and_sha256(server: FixtureServer, tmp_path: Path) -> None:
    body = "<p>धारा 1 — Section 1</p>\r\n".encode()
    server.script["/act/1"] = ok(body, "text/html; charset=utf-8")
    response = make_client(tmp_path).get(server.base + "/act/1")

    assert response.sha256 == hashlib.sha256(body).hexdigest()
    path = tmp_path / "cache" / response.warc_file
    data = path.read_bytes()
    assert path.name == hashlib.sha256(data).hexdigest() + ".warc.gz"
    assert gzip_member_count(data) == 2

    request, resp = warc.read_records(path)
    assert (request.type, resp.type) == ("request", "response")
    assert resp.headers["WARC-Target-URI"] == server.base + "/act/1"
    assert resp.headers["WARC-Payload-Digest"] == "sha256:" + hashlib.sha256(body).hexdigest()
    assert resp.headers["WARC-Date"] == "2026-01-01T00:00:00Z"
    assert request.headers["WARC-Concurrent-To"] == resp.headers["WARC-Record-ID"]
    assert resp.block.startswith(b"HTTP/1.1 200 OK\r\n")
    assert b"Content-Type: text/html; charset=utf-8\r\n" in resp.block
    assert warc.http_payload(resp.block) == body
    assert request.block.startswith(b"GET /act/1 HTTP/1.1\r\n")


def test_tampered_warc_record_is_rejected(server: FixtureServer, tmp_path: Path) -> None:
    server.script["/a"] = ok(b"original")
    response = make_client(tmp_path).get(server.base + "/a")
    _, resp = warc.read_records(tmp_path / "cache" / response.warc_file)
    tampered = tmp_path / "tampered.warc.gz"
    tampered.write_bytes(warc.encode_record(resp.headers, resp.block.replace(b"original", b"tampered")))
    with pytest.raises(ValueError, match="Block-Digest"):
        warc.read_records(tampered)


def test_unreachable_host_backs_off_then_raises(tmp_path: Path) -> None:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    clock = FakeClock()
    with pytest.raises(RetryExhausted, match="no response"):
        make_client(tmp_path, clock, timeout=2).get(f"http://127.0.0.1:{port}/a")
    assert clock.sleeps == [10.0, 30.0, 60.0]


def test_record_cli_fetches_a_url_list_into_the_portal_cache(server: FixtureServer, tmp_path: Path,
                                                             capsys: pytest.CaptureFixture[str]) -> None:
    server.script["/robots.txt"] = ok(b"User-agent: *\nDisallow: /private\n", "text/plain")
    server.script["/act/1"] = ok(b"one")
    server.script["/act/2"] = ok(b"two")
    urls = tmp_path / "urls.txt"
    urls.write_text(f"# Central Acts\n{server.base}/act/1\n\n{server.base}/act/2\n"
                    f"{server.base}/act/1\n{server.base}/private/x\n", encoding="utf-8")
    argv = ["--portal", "indiacode", "--urls", str(urls), "--cache-root", str(tmp_path / ".cache")]

    assert record.main(argv, clock=FakeClock(), rng=StubRng()) == 0
    assert sorted(server.paths()) == ["/act/1", "/act/2", "/robots.txt"]
    assert "2 fetched, 0 from cache, 1 disallowed, 0 failed" in capsys.readouterr().out

    portal = tmp_path / ".cache" / "indiacode"
    index = [json.loads(line) for line in (portal / "index.jsonl").read_text().splitlines()]
    assert [(e["url"], e["status"]) for e in index] == [
        (server.base + "/act/1", 200), (server.base + "/act/2", 200)]
    assert index[1]["source_sha256"] == hashlib.sha256(b"two").hexdigest()
    assert warc.http_payload(warc.read_records(portal / index[1]["warc_file"])[1].block) == b"two"

    server.seen.clear()
    assert record.main(argv, clock=FakeClock(), rng=StubRng()) == 0
    assert server.paths() == []
    assert "0 fetched, 2 from cache, 1 disallowed, 0 failed" in capsys.readouterr().out


def test_record_cli_exits_non_zero_when_a_url_fails(server: FixtureServer, tmp_path: Path) -> None:
    server.script["/down"] = [(503, {}, b"busy")]
    urls = tmp_path / "urls.txt"
    urls.write_text(server.base + "/down\n", encoding="utf-8")
    argv = ["--portal", "egazette", "--urls", str(urls), "--cache-root", str(tmp_path)]
    assert record.main(argv, clock=FakeClock(), rng=StubRng()) == 1


def test_record_cli_refuses_a_browser_user_agent(tmp_path: Path) -> None:
    urls = tmp_path / "urls.txt"
    urls.write_text("", encoding="utf-8")
    with pytest.raises(SystemExit) as exit_info:
        record.main(["--portal", "indiacode", "--urls", str(urls), "--cache-root", str(tmp_path),
                     "--user-agent", "Mozilla/5.0"])
    assert exit_info.value.code == 2


def test_record_cli_runs_as_a_script() -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "crawlers" / "record.py"
    result = subprocess.run([sys.executable, str(script), "--help"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "--portal" in result.stdout


def gzip_member_count(data: bytes) -> int:
    count = 0
    while data:
        member = zlib.decompressobj(wbits=31)
        member.decompress(data)
        data = member.unused_data
        count += 1
    return count
