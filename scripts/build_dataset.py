"""
Open Laws India — v0.2.0 Dataset Build
======================================
Reads the frozen v0.1.1 tables from --input-dir, runs the enrichment stages
(scripts/enrich/) and writes the 4 parquet tables, the nested jsonl.gz archive
and manifest.json into --output-dir. The output is byte-deterministic for a
given input and --timestamp.

Usage:
  python scripts/extract_inputs.py          # -> .cache/inputs/v0.1.1/
  python scripts/build_dataset.py --input-dir .cache/inputs/v0.1.1 \\
      --output-dir data [--timestamp 2026-01-01T00:00:00+00:00]

Without --timestamp, SOURCE_DATE_EPOCH is used, else the export_timestamp of
--input-dir/manifest.json. The build never stamps itself with the current time.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from enrich import Coverage, Rows
from enrich import acts as acts_stage
from enrich import footnotes as footnotes_stage
from enrich import mappings as mappings_stage
from table_files import ACTS, ARCHIVE, FOOTNOTES, MAPPINGS, SECTIONS

VERSION = "v0.2.0"

STRING, INT32, BOOL = pa.string(), pa.int32(), pa.bool_()
# The v0.1.1 column layout; stages append their FIELDS after these.
V011_SCHEMAS = {
    ACTS: pa.schema([
        ("act_id", STRING), ("title", STRING), ("act_number", STRING), ("enactment_date", STRING),
        ("jurisdiction", STRING), ("category", STRING), ("structure", STRING), ("is_repealed", BOOL),
        ("repealed_by", STRING), ("repeal_reason", STRING), ("chapter_count", INT32),
        ("section_count", INT32), ("footnote_count", INT32), ("source_file", STRING),
    ]),
    SECTIONS: pa.schema([
        ("id", STRING), ("act_id", STRING), ("section_number", STRING), ("slug", STRING),
        ("structural_unit", STRING), ("heading", STRING), ("full_text", STRING), ("chapter_id", STRING),
        ("chapter_name", STRING), ("language", STRING),
    ]),
    FOOTNOTES: pa.schema([
        ("id", STRING), ("act_id", STRING), ("page_or_anchor", STRING), ("footnote_number", INT32),
        ("raw_text", STRING), ("amendment_type", STRING), ("amending_act_citation", STRING),
        ("amending_year", INT32), ("wef_date", STRING),
    ]),
    MAPPINGS: pa.schema([
        ("old_act_id", STRING), ("old_section", STRING), ("new_act_id", STRING), ("new_section", STRING),
        ("mapping_type", STRING), ("notes", STRING),
    ]),
}
OUTPUT_SCHEMAS = {
    ACTS: pa.schema([*V011_SCHEMAS[ACTS], *acts_stage.FIELDS]),
    SECTIONS: V011_SCHEMAS[SECTIONS],
    FOOTNOTES: pa.schema([*V011_SCHEMAS[FOOTNOTES], *footnotes_stage.FIELDS]),
    MAPPINGS: pa.schema([*V011_SCHEMAS[MAPPINGS], *mappings_stage.FIELDS]),
}
# Fixed writer options: the same rows always give the same bytes.
PARQUET_OPTIONS: dict[str, Any] = {
    "compression": "zstd",
    "compression_level": 9,
    "use_dictionary": True,
    "write_statistics": True,
    "version": "2.6",
    "data_page_version": "1.0",
    "row_group_size": 1 << 20,
}


def read_inputs(input_dir: Path) -> dict[str, Rows]:
    return {name: pq.read_table(input_dir / name).to_pylist() for name in V011_SCHEMAS}


def run_stages(inputs: dict[str, Rows]) -> tuple[dict[str, Rows], Coverage]:
    """Run every stage; merge their coverage (distinct keys) for the manifest."""
    acts, acts_cov = acts_stage.enrich(inputs[ACTS])
    footnotes, fn_cov = footnotes_stage.enrich(inputs[FOOTNOTES], inputs[SECTIONS])
    mappings, map_cov = mappings_stage.enrich(inputs[MAPPINGS])
    coverage: Coverage = {}
    for stage_cov in (acts_cov, fn_cov, map_cov):
        if clash := coverage.keys() & stage_cov.keys():
            raise ValueError(f"coverage keys reported by two stages: {sorted(clash)}")
        coverage.update(stage_cov)
    tables = {ACTS: acts, SECTIONS: inputs[SECTIONS], FOOTNOTES: footnotes, MAPPINGS: mappings}
    return tables, coverage


def write_parquet(rows: Rows, schema: pa.Schema, path: Path) -> None:
    for i, row in enumerate(rows):
        if set(row) != set(schema.names):
            raise ValueError(f"{path.name} row {i}: columns {sorted(set(row) ^ set(schema.names))} "
                             "differ from the output schema")
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), path, **PARQUET_OPTIONS)


def write_archive(tables: dict[str, Rows], path: Path) -> None:
    """One line per Act, with its sections and footnotes nested in table order."""
    nested: dict[str, dict[str, Rows]] = {a["act_id"]: {"sections": [], "footnotes": []}
                                          for a in tables[ACTS]}
    for key, name in (("sections", SECTIONS), ("footnotes", FOOTNOTES)):
        for row in tables[name]:
            nested[row["act_id"]][key].append(row)
    with open(path, "wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw,
                                                 compresslevel=9, mtime=0) as gz:
        for act in tables[ACTS]:
            line = json.dumps({**act, **nested[act["act_id"]]}, ensure_ascii=False)
            gz.write((line + "\n").encode("utf-8"))


def file_entry(path: Path, rows: int) -> dict[str, Any]:
    return {
        "size_bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "rows": rows,
    }


def build_manifest(tables: dict[str, Rows], coverage: Coverage, output_dir: Path,
                   timestamp: str) -> dict[str, Any]:
    years = [int(a["act_id"][1:5]) for a in tables[ACTS]]
    files = {name: file_entry(output_dir / name, len(tables[name])) for name in OUTPUT_SCHEMAS}
    files[ARCHIVE] = file_entry(output_dir / ARCHIVE, len(tables[ACTS]))
    return {
        "total_acts": len(tables[ACTS]),
        "total_sections": len(tables[SECTIONS]),
        "total_footnotes": len(tables[FOOTNOTES]),
        "footnotes_with_wef": sum(f["wef_date"] is not None for f in tables[FOOTNOTES]),
        "total_mappings": len(tables[MAPPINGS]),
        "year_range": [min(years), max(years)] if years else [],
        "export_timestamp": timestamp,
        "version": VERSION,
        "coverage": coverage,
        "files": files,
    }


def build(input_dir: Path, output_dir: Path, timestamp: str) -> dict[str, Any]:
    """Build every output file into output_dir; returns the manifest."""
    if input_dir.resolve() == output_dir.resolve():
        raise ValueError("--output-dir must differ from --input-dir (inputs are frozen)")
    tables, coverage = run_stages(read_inputs(input_dir))
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, schema in OUTPUT_SCHEMAS.items():
        write_parquet(tables[name], schema, output_dir / name)
    write_archive(tables, output_dir / ARCHIVE)
    manifest = build_manifest(tables, coverage, output_dir, timestamp)
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def default_timestamp(input_dir: Path) -> str:
    """SOURCE_DATE_EPOCH, else the input manifest's export_timestamp; never the clock."""
    if epoch := os.environ.get("SOURCE_DATE_EPOCH"):
        return datetime.fromtimestamp(int(epoch), timezone.utc).isoformat()
    manifest_path = input_dir / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if timestamp := manifest.get("export_timestamp"):
            return timestamp
    raise SystemExit("No --timestamp, SOURCE_DATE_EPOCH or export_timestamp in "
                     f"{manifest_path}: refusing to stamp the build with the current time")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the Open Laws India v0.2.0 dataset.")
    parser.add_argument("--input-dir", type=Path, required=True, help="v0.1.1 data dir")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--timestamp", help="ISO 8601 export_timestamp (fixes the output bytes)")
    args = parser.parse_args()
    timestamp = args.timestamp or default_timestamp(args.input_dir)
    datetime.fromisoformat(timestamp)  # reject a malformed --timestamp early
    manifest = build(args.input_dir, args.output_dir, timestamp)
    print(f"✅ Built {VERSION} into {args.output_dir}: {manifest['total_acts']:,} Acts, "
          f"{manifest['total_sections']:,} sections, {manifest['total_footnotes']:,} footnotes, "
          f"{manifest['total_mappings']:,} mappings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
