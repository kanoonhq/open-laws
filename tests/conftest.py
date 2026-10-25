"""
The single test seam: write the v0.1.1-shaped fixture rows as an input dir,
run scripts/build_dataset.py on it, and read back the output dir.

Later tickets extend the fixtures via tests/fixtures/make_fixtures.py, or
derive variants in a test with load_fixture_rows() + write_input_dir().
"""

from __future__ import annotations

import gzip
import hashlib
import json
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "v0.1.1"
BUILD = ROOT / "scripts" / "build_dataset.py"
VALIDATE = ROOT / "scripts" / "validate.py"
FIXED_TIMESTAMP = "2026-01-01T00:00:00+00:00"

# fixture name -> parquet file name (input and output use the same names)
TABLE_FILES = {
    "acts": "indian_central_acts.parquet",
    "sections": "indian_central_act_sections.parquet",
    "footnotes": "central_act_footnotes.parquet",
    "mappings": "criminal_law_mappings.parquet",
}
ARCHIVE = "indian_central_acts_complete.jsonl.gz"

Rows = list[dict[str, Any]]


def load_fixture_rows() -> dict[str, Rows]:
    """The fixture tables as row lists, keyed acts/sections/footnotes/mappings."""
    return {
        name: json.loads((FIXTURES_DIR / f"{name}.json").read_text(encoding="utf-8"))
        for name in TABLE_FILES
    }


def write_input_dir(tables: dict[str, Rows], input_dir: Path) -> Path:
    """Write row lists as a v0.1.1-shaped input dir of parquet tables."""
    input_dir.mkdir(parents=True, exist_ok=True)
    for name, filename in TABLE_FILES.items():
        pq.write_table(pa.Table.from_pylist(tables[name]), input_dir / filename)
    return input_dir


def run_build(
    input_dir: Path, output_dir: Path, timestamp: str = FIXED_TIMESTAMP
) -> subprocess.CompletedProcess[str]:
    """Run the build CLI; raises on a non-zero exit."""
    return subprocess.run(
        [sys.executable, str(BUILD), "--input-dir", str(input_dir),
         "--output-dir", str(output_dir), "--timestamp", timestamp],
        check=True, capture_output=True, text=True,
    )


def run_validator(data_dir: Path) -> subprocess.CompletedProcess[str]:
    """Run scripts/validate.py --data-dir; inspect .returncode."""
    return subprocess.run(
        [sys.executable, str(VALIDATE), "--data-dir", str(data_dir)],
        capture_output=True, text=True, check=False,
    )


@dataclass(frozen=True)
class BuildOutput:
    """A finished build's output dir, with readers for its files."""

    dir: Path

    def table(self, name: str) -> Rows:
        return pq.read_table(self.dir / TABLE_FILES[name]).to_pylist()

    def archive(self) -> Rows:
        with gzip.open(self.dir / ARCHIVE, "rt", encoding="utf-8") as f:
            return [json.loads(line) for line in f]

    def manifest(self) -> dict[str, Any]:
        return json.loads((self.dir / "manifest.json").read_text(encoding="utf-8"))


def build_fixtures(tmp: Path, tables: dict[str, Rows] | None = None) -> BuildOutput:
    """Build the given tables (default: the fixtures) into tmp/out."""
    input_dir = write_input_dir(tables or load_fixture_rows(), tmp / "in")
    run_build(input_dir, tmp / "out")
    return BuildOutput(tmp / "out")


def corrupt_output(
    src: BuildOutput, dst: Path, name: str, mutate: Callable[[Rows], Rows]
) -> BuildOutput:
    """Copy a build to dst, rewrite one table with mutate(rows) and re-seal the
    manifest's checksum for it, so the validator gets past the checksum checks."""
    shutil.copytree(src.dir, dst)
    path = dst / TABLE_FILES[name]
    table = pq.read_table(path)
    rows = mutate(table.to_pylist())
    # A mutate that drops a column from every row drops it from the file.
    schema = pa.schema([f for f in table.schema if not rows or f.name in rows[0]])
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), path)
    manifest = json.loads((dst / "manifest.json").read_text(encoding="utf-8"))
    manifest["files"][path.name] = {
        "size_bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "rows": len(rows),
    }
    (dst / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return BuildOutput(dst)


@pytest.fixture(scope="session")
def built(tmp_path_factory: pytest.TempPathFactory) -> BuildOutput:
    """The fixture inputs built once per session. Read-only: copy before corrupting."""
    return build_fixtures(tmp_path_factory.mktemp("build"))
