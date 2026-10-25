"""WARC/1.1 writer and reader. Each record is its own gzip member, and each
file is named by the SHA-256 of its own bytes, so a file name is a checksum.
Record IDs and dates derive from the inputs, so the same response always
gives the same file."""

from __future__ import annotations

import gzip
import hashlib
import uuid
import zlib
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

CRLF = b"\r\n"
# Headers that describe the wire framing, not the (already de-framed) body.
FRAMING_HEADERS = {"transfer-encoding"}


@dataclass(frozen=True)
class Record:
    headers: dict[str, str]
    block: bytes

    @property
    def type(self) -> str:
        return self.headers["WARC-Type"]


def sha256_label(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def record_id(*parts: str) -> str:
    return f"<urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, '|'.join(parts))}>"


def http_request_block(method: str, path: str, headers: dict[str, str]) -> bytes:
    lines = [f"{method} {path} HTTP/1.1"] + [f"{k}: {v}" for k, v in headers.items()]
    return CRLF.join(line.encode("latin-1") for line in lines) + CRLF + CRLF


def http_response_block(status: int, reason: str, headers: list[tuple[str, str]], body: bytes) -> bytes:
    lines = [f"HTTP/1.1 {status} {reason}".rstrip()]
    lines += [f"{k}: {v}" for k, v in headers if k.lower() not in FRAMING_HEADERS]
    return CRLF.join(line.encode("latin-1") for line in lines) + CRLF + CRLF + body


def encode_record(headers: dict[str, str], block: bytes) -> bytes:
    head = [b"WARC/1.1"] + [f"{k}: {v}".encode() for k, v in headers.items()]
    head.append(f"Content-Length: {len(block)}".encode())
    # mtime=0 keeps the gzip member byte-deterministic.
    return gzip.compress(CRLF.join(head) + CRLF + CRLF + block + CRLF + CRLF, mtime=0)


def write_exchange(warc_dir: Path, *, url: str, date: datetime, request: bytes, response: bytes,
                   payload: bytes) -> Path:
    """Write a request record and its response record to one content-addressed
    .warc.gz file and return its path. payload is the HTTP body."""
    when = date.strftime("%Y-%m-%dT%H:%M:%SZ")
    response_id = record_id("response", url, when, sha256_label(response))
    response_headers = {
        "WARC-Type": "response",
        "WARC-Record-ID": response_id,
        "WARC-Date": when,
        "WARC-Target-URI": url,
        "Content-Type": "application/http;msgtype=response",
        "WARC-Block-Digest": sha256_label(response),
        "WARC-Payload-Digest": sha256_label(payload),
    }
    request_headers = {
        "WARC-Type": "request",
        "WARC-Record-ID": record_id("request", url, when, sha256_label(request)),
        "WARC-Date": when,
        "WARC-Target-URI": url,
        "WARC-Concurrent-To": response_id,
        "Content-Type": "application/http;msgtype=request",
        "WARC-Block-Digest": sha256_label(request),
    }
    data = encode_record(request_headers, request) + encode_record(response_headers, response)
    warc_dir.mkdir(parents=True, exist_ok=True)
    path = warc_dir / f"{hashlib.sha256(data).hexdigest()}.warc.gz"
    if not path.exists():
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)
    return path


def gzip_members(data: bytes) -> Iterator[bytes]:
    while data:
        member = zlib.decompressobj(wbits=31)
        yield member.decompress(data) + member.flush()
        data = member.unused_data


def parse_record(raw: bytes) -> Record:
    head, _, rest = raw.partition(CRLF + CRLF)
    lines = head.split(CRLF)
    if lines[0] != b"WARC/1.1":
        raise ValueError(f"not a WARC/1.1 record: {lines[0][:40]!r}")
    headers = dict(line.decode().split(": ", 1) for line in lines[1:])
    length = int(headers.pop("Content-Length"))
    block = rest[:length]
    if rest[length:] != CRLF + CRLF:
        raise ValueError("WARC record block does not match its Content-Length")
    if (digest := headers.get("WARC-Block-Digest")) and digest != sha256_label(block):
        raise ValueError(f"WARC-Block-Digest mismatch in {headers.get('WARC-Record-ID')}")
    return Record(headers, block)


def read_records(path: Path) -> list[Record]:
    """Every record in a .warc.gz file, one gzip member each, digests checked."""
    return [parse_record(member) for member in gzip_members(path.read_bytes())]


def http_payload(block: bytes) -> bytes:
    """The body of an application/http record block."""
    return block.partition(CRLF + CRLF)[2]
