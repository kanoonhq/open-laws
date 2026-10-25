"""
Open Laws India — Snapshot Recorder
===================================
Fetches a list of URLs into the content-addressed cache and WARC archive
under .cache/{portal}/, under the PROCUREMENT_PLAN §6 politeness policy. Run it
from a machine that can reach the portal; a re-run fetches only what is
missing. Check the portal's terms before crawling it.

Layout of .cache/{portal}/:
  responses/{request sha256}.json   response metadata (status, headers, sha256)
  bodies/{body sha256}              raw response bodies
  warc/{file sha256}.warc.gz        WARC/1.1 request + response records
  index.jsonl                       one line per recorded URL, sorted by URL

Usage:
  python scripts/crawlers/record.py --portal indiacode --urls urls.txt
      [--cache-root .cache] [--user-agent "..."] [--workers 2]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from crawlers.client import (  # noqa: E402
    DEFAULT_USER_AGENT,
    Clock,
    PoliteClient,
    Response,
    RetryExhausted,
    Rng,
    RobotsDisallowed,
)

ROOT = Path(__file__).resolve().parents[2]
PORTAL_NAME = re.compile(r"[a-z0-9][a-z0-9_-]*")


def read_urls(path: Path) -> list[str]:
    """Non-blank, non-comment lines, de-duplicated in order."""
    lines = (line.strip() for line in path.read_text(encoding="utf-8").splitlines())
    return list(dict.fromkeys(line for line in lines if line and not line.startswith("#")))


def index_entry(response: Response) -> dict[str, object]:
    return {
        "url": response.url,
        "status": response.status,
        "source_sha256": response.sha256,
        "retrieved_at": response.retrieved_at,
        "warc_file": response.warc_file,
    }


def write_index(path: Path, entries: list[dict[str, object]]) -> None:
    """Merge entries into index.jsonl, keyed and sorted by URL."""
    merged = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            entry = json.loads(line)
            merged[entry["url"]] = entry
    merged.update((entry["url"], entry) for entry in entries)
    path.write_text("".join(json.dumps(merged[url], ensure_ascii=False) + "\n"
                            for url in sorted(merged)), encoding="utf-8")


def main(argv: list[str] | None = None, clock: Clock | None = None, rng: Rng | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record URLs into the crawl cache and WARC archive.")
    parser.add_argument("--portal", required=True, help="cache name, e.g. indiacode or egazette")
    parser.add_argument("--urls", type=Path, required=True, help="file with one URL per line")
    parser.add_argument("--cache-root", type=Path, default=ROOT / ".cache")
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT,
                        help="must contain the project repo URL; a browser User-Agent is refused")
    parser.add_argument("--workers", type=int, default=2,
                        help="parallel fetches; each host still gets at most 2")
    args = parser.parse_args(argv)
    if not PORTAL_NAME.fullmatch(args.portal):
        parser.error(f"--portal must match {PORTAL_NAME.pattern}")
    if args.workers < 1:
        parser.error("--workers must be at least 1")
    try:
        client = PoliteClient(args.cache_root / args.portal, user_agent=args.user_agent,
                              clock=clock, rng=rng)
    except ValueError as exc:
        parser.error(str(exc))

    def record(url: str) -> tuple[str, Response | str]:
        try:
            return url, client.get(url)
        except RobotsDisallowed:
            return url, "disallowed by robots.txt"
        except (RetryExhausted, ValueError) as exc:
            return url, f"failed: {exc}"

    urls = read_urls(args.urls)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(record, urls))

    entries, fetched, cached, skipped, failed = [], 0, 0, 0, 0
    for url, outcome in results:
        if isinstance(outcome, Response):
            entries.append(index_entry(outcome))
            cached += outcome.from_cache
            fetched += not outcome.from_cache
            print(f"{'♻️ ' if outcome.from_cache else '✅'} {url} ({outcome.status})")
        elif outcome.startswith("disallowed"):
            skipped += 1
            print(f"⛔ {url} ({outcome})")
        else:
            failed += 1
            print(f"❌ {url} ({outcome})")
    if entries:
        write_index(args.cache_root / args.portal / "index.jsonl", entries)
    print(f"\n{len(urls)} URLs: {fetched} fetched, {cached} from cache, "
          f"{skipped} disallowed, {failed} failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
