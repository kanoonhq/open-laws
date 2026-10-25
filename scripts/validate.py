"""
Open Laws India — Standalone Data Integrity Validator
=====================================================
Validates the dataset files in data/ against data/manifest.json (SHA-256,
size, row counts), every Parquet row against its schemas/*.schema.json, and
the references between tables. The v0.2.0 invariants (unique work_id, slug
collisions, footnote section_slug links, repealed_by, dates, manifest coverage)
run only when their columns or manifest keys are present, so v0.1.1 data still
validates.

Usage:
  pip install -r requirements.txt
  python scripts/validate.py [--data-dir PATH]
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
from enrich import acts as acts_stage
from enrich import footnotes as footnotes_stage
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
SCHEMAS_DIR = ROOT / "schemas"

ACTS = "indian_central_acts.parquet"
SECTIONS = "indian_central_act_sections.parquet"
FOOTNOTES = "central_act_footnotes.parquet"
MAPPINGS = "criminal_law_mappings.parquet"
ARCHIVE = "indian_central_acts_complete.jsonl.gz"

# Parquet file -> (schema file, manifest total key)
TABLES = {
    ACTS: ("act.schema.json", "total_acts"),
    SECTIONS: ("section.schema.json", "total_sections"),
    FOOTNOTES: ("footnote.schema.json", "total_footnotes"),
    MAPPINGS: ("mapping.schema.json", "total_mappings"),
}
REQUIRED_MANIFEST_KEYS = (
    "version",
    "total_acts",
    "total_sections",
    "total_footnotes",
    "footnotes_with_wef",
    "total_mappings",
    "files",
)
MAX_ERRORS_PER_CHECK = 5
# Parquet file -> (row label column, date columns; absent columns are skipped).
# The build nulls the impossible wef_dates v0.1.1 carries (e.g. 1959-19-01).
DATE_COLUMNS = {
    ACTS: ("act_id", ("assent_date", "commencement_date", "repeal_date")),
    FOOTNOTES: ("id", ("wef_date",)),
    MAPPINGS: ("old_section", ("effective_from",)),
}
ISO_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def sha256_of(path: Path) -> str:
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            sha.update(chunk)
    return sha.hexdigest()


def count_rows(path: Path) -> int:
    if path.name.endswith(".jsonl.gz"):
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return sum(1 for _ in f)
    return pq.read_metadata(path).num_rows


def check_files(manifest: dict[str, Any], data_dir: Path) -> list[str]:
    errors = []
    for filename, meta in manifest["files"].items():
        path = data_dir / filename
        if not path.exists():
            errors.append(f"Missing file: {filename}")
            continue
        file_errors = []
        if (actual := sha256_of(path)) != meta["sha256"]:
            file_errors.append(f"Checksum mismatch: {filename} (expected {meta['sha256']}, got {actual})")
        if (size := path.stat().st_size) != meta["size_bytes"]:
            file_errors.append(f"Size mismatch: {filename} (expected {meta['size_bytes']}, got {size})")
        if (rows := count_rows(path)) != meta.get("rows"):
            file_errors.append(f"Row count mismatch: {filename} (expected {meta.get('rows')}, got {rows})")
        if not file_errors:
            print(f"✅ {filename} ({size / (1024 * 1024):.2f} MB, {rows:,} rows)")
        errors += file_errors

    for filename, (_, total_key) in TABLES.items():
        if manifest["files"].get(filename, {}).get("rows") != manifest[total_key]:
            errors.append(f"manifest {total_key} disagrees with files.{filename}.rows")
    return errors


def check_schemas(tables: dict[str, list[dict[str, Any]]]) -> list[str]:
    errors = []
    for filename, (schema_file, _) in TABLES.items():
        schema = json.loads((SCHEMAS_DIR / schema_file).read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)
        bad = [
            f"{filename} row {i}: {err.message}"
            for i, row in enumerate(tables[filename])
            for err in validator.iter_errors(row)
        ]
        errors.extend(bad[:MAX_ERRORS_PER_CHECK])
        if len(bad) > MAX_ERRORS_PER_CHECK:
            errors.append(f"{filename}: {len(bad) - MAX_ERRORS_PER_CHECK} more schema errors")
        if not bad:
            print(f"✅ {filename} matches {schema_file}")
    return errors


def check_references(tables: dict[str, list[dict[str, Any]]]) -> list[str]:
    act_ids = {a["act_id"] for a in tables[ACTS]}
    section_keys = {(s["act_id"], s["section_number"]) for s in tables[SECTIONS]}
    sections_per_act: dict[str, int] = {}
    for s in tables[SECTIONS]:
        sections_per_act[s["act_id"]] = sections_per_act.get(s["act_id"], 0) + 1

    errors = []
    for filename in (SECTIONS, FOOTNOTES):
        unknown = {r["act_id"] for r in tables[filename]} - act_ids
        if unknown:
            errors.append(f"{filename}: unknown act_id {sorted(unknown)[:MAX_ERRORS_PER_CHECK]}")

    for act in tables[ACTS]:
        if act["section_count"] != sections_per_act.get(act["act_id"], 0):
            errors.append(
                f"{act['act_id']}: section_count {act['section_count']} "
                f"but {sections_per_act.get(act['act_id'], 0)} sections"
            )

    for m in tables[MAPPINGS]:
        for side in ("old", "new"):
            act_id, section = m[f"{side}_act_id"], m[f"{side}_section"]
            if act_id not in act_ids:
                errors.append(f"mapping {m['old_section']}: unknown {side}_act_id {act_id}")
                continue
            if section is None:
                continue
            # "Section 103(2)." refers to sub-section (2) of "Section 103."
            base_section = section.split("(")[0].rstrip(".") + "."
            if (act_id, base_section) not in section_keys:
                errors.append(f"mapping {m['old_section']}: {act_id} {section} has no section text")

    if not errors:
        print("✅ Acts, sections, footnotes and mappings reference each other consistently")
    return errors[: MAX_ERRORS_PER_CHECK * 4]


def report(name: str, bad: list[str]) -> list[str]:
    """Cap one invariant's errors at MAX_ERRORS_PER_CHECK, or print its ✅."""
    if not bad:
        print(f"✅ {name}")
    extra = [f"{name}: {len(bad) - MAX_ERRORS_PER_CHECK} more errors"] if len(bad) > MAX_ERRORS_PER_CHECK else []
    return bad[:MAX_ERRORS_PER_CHECK] + extra


def duplicates(values: list[Any]) -> list[Any]:
    counts = Counter(values)
    return [v for v, n in counts.items() if n > 1]


# Each v0.2.0 invariant runs only when its column is present, so the v0.1.1
# tables in data/ still validate.
def check_invariants(tables: dict[str, list[dict[str, Any]]]) -> list[str]:
    acts = tables[ACTS]
    errors = []
    if has_column(acts, "work_id"):
        errors += report("work_id is unique across Acts",
                         [f"duplicate work_id {w}" for w in duplicates([a["work_id"] for a in acts])])
    slug_keys = [(s["act_id"], s["structural_unit"], s["language"], s["slug"]) for s in tables[SECTIONS]]
    errors += report("Section slugs are unique per (act_id, structural_unit, language)",
                     [f"slug collision {' '.join(map(str, k))}" for k in duplicates(slug_keys)])
    if has_column(tables[FOOTNOTES], "section_slug"):
        errors += report("Footnote section_slugs resolve to a section of the same Act",
                         footnote_link_errors(tables))
    act_ids = {a["act_id"] for a in acts}
    errors += report("repealed_by resolves to a known Act", [
        f"{a['act_id']}: repealed_by {a['repealed_by']} is not a known act_id"
        for a in acts if a["repealed_by"] is not None and a["repealed_by"] not in act_ids])
    errors += report("Date columns are ISO YYYY-MM-DD dates", date_errors(tables))
    if has_column(acts, "repeal_date"):
        errors += report("repeal_date is set only on repealed Acts", [
            f"{a['act_id']}: repeal_date {a['repeal_date']} but is_repealed is false"
            for a in acts if a["repeal_date"] is not None and not a["is_repealed"]])
    return errors


def check_coverage(manifest: dict[str, Any], tables: dict[str, list[dict[str, Any]]]) -> list[str]:
    """manifest.coverage must equal the build's coverage recomputed from the tables."""
    if "coverage" not in manifest:
        return []
    expected = {**acts_stage.coverage(tables[ACTS]),
                **footnotes_stage.linkage_coverage(tables[FOOTNOTES])}
    actual = manifest["coverage"]
    return report("manifest coverage matches the tables", [
        f"manifest coverage.{key} is {actual.get(key)!r} but the tables give {expected.get(key)!r}"
        for key in sorted(expected.keys() | actual.keys()) if actual.get(key) != expected.get(key)])


def date_errors(tables: dict[str, list[dict[str, Any]]]) -> list[str]:
    bad = []
    for filename, (key, columns) in DATE_COLUMNS.items():
        for row in tables[filename]:
            for column in columns:
                value = row.get(column)
                if value is not None and not is_iso_date(value):
                    bad.append(f"{row[key]}: {column} {value} is not an ISO YYYY-MM-DD date")
    return bad


def is_iso_date(value: str) -> bool:
    try:
        return ISO_DATE.fullmatch(value) is not None and date.fromisoformat(value) is not None
    except ValueError:
        return False


def footnote_link_errors(tables: dict[str, list[dict[str, Any]]]) -> list[str]:
    slugs = {(s["act_id"], s["slug"]) for s in tables[SECTIONS]}
    bad = []
    for f in tables[FOOTNOTES]:
        where, slug = f"footnote {f['id']}", f["section_slug"]
        if (f["linkage_method"] == "act_level") != (slug is None):
            bad.append(f"{where}: linkage_method {f['linkage_method']} but section_slug {slug}")
        elif slug is not None and (f["act_id"], slug) not in slugs:
            bad.append(f"{where}: section_slug {slug} is not a section of {f['act_id']}")
    return bad


def has_column(rows: list[dict[str, Any]], column: str) -> bool:
    return bool(rows) and column in rows[0]


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the Open Laws India dataset.")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    data_dir = parser.parse_args().data_dir

    manifest_path = data_dir / "manifest.json"
    if not manifest_path.exists():
        print(f"ERROR: manifest.json not found in {data_dir}")
        return 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    missing = [k for k in REQUIRED_MANIFEST_KEYS if k not in manifest]
    if missing:
        print(f"ERROR: manifest.json is missing {missing}")
        return 1

    print("=" * 60)
    print("Open Laws India — Dataset Verification")
    print(f"Version:            {manifest['version']}")
    print(f"Total Acts:         {manifest['total_acts']:,}")
    print(f"Total Sections:     {manifest['total_sections']:,}")
    print(f"Total Footnotes:    {manifest['total_footnotes']:,}")
    print(f"Footnotes w/ w.e.f: {manifest['footnotes_with_wef']:,}")
    print(f"Criminal Mappings:  {manifest['total_mappings']:,}")
    print("=" * 60)

    errors = check_files(manifest, data_dir)
    if not errors:
        tables = {name: pq.read_table(data_dir / name).to_pylist() for name in TABLES}
        print()
        errors += check_schemas(tables)
        errors += check_references(tables)
        errors += check_invariants(tables)
        errors += check_coverage(manifest, tables)

    if errors:
        print()
        for err in errors:
            print(f"❌ {err}")
        print("\nDATASET VERIFICATION FAILED.")
        return 1
    print("\nALL INTEGRITY CHECKS PASSED SUCCESSFULLY.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
