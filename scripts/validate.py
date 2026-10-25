"""
Open Laws India — Data Integrity Validator
==========================================
Validates the dataset files in data/ against data/manifest.json (SHA-256,
size, row counts), every Parquet row against its schemas/*.schema.json, and
the references between tables, and the dataset invariants (slug collisions,
repealed_by). For a manifest version of v0.2.0 or later it also requires the
v0.2.0 columns and manifest keys and checks their invariants (unique work_id,
footnote section_slug links, calendar dates, repeal_date, manifest coverage); older
versions skip them, so v0.1.1 data still validates. Each derived table
(scripts/enrich/registry.py) listed in the manifest is checked against its
JSON schema, and its coverage is recomputed with its stage's coverage().
A v0.3.0 or later manifest must list every derived table, and the time layer
is checked (PROCUREMENT_PLAN §7.3, §7.6): each section's versions are
contiguous (valid_from <= valid_to, no overlap or gap, the last open-ended),
text is null exactly when unavailable, each later slice is opened by a known
event (unless it follows a slice whose wording is unavailable), each
amendment event has a footnote or is a repeal, no slice is in force after a strike-down or during a
stay (until stay_lifted), and every act_id, central_act_id, section,
jurisdiction code, succession link and ISO alias resolves. v0.2.0 data skips
these checks.

Usage:
  pip install -r requirements.txt
  python scripts/validate.py [--data-dir PATH]
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
from collections import Counter, defaultdict
from itertools import pairwise
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
from enrich import Rows
from enrich import acts as acts_stage
from enrich import events as events_stage
from enrich import footnotes as footnotes_stage
from enrich import judicial_events as judicial_events_stage
from enrich import jurisdictions as jurisdictions_stage
from enrich import mappings as mappings_stage
from enrich import section_versions as section_versions_stage
from enrich import state_amendments as state_amendments_stage
from enrich.dates import calendar_date
from enrich.registry import DERIVED_TABLES
from jsonschema import Draft202012Validator
from table_files import ACTS, FOOTNOTES, MAPPINGS, SECTIONS

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
SCHEMAS_DIR = ROOT / "schemas"

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
# Required when the manifest version is v0.2.0 or later.
V020 = (0, 2, 0)
V020_COLUMNS = {
    ACTS: [f.name for f in acts_stage.FIELDS],
    FOOTNOTES: [f.name for f in footnotes_stage.FIELDS],
    MAPPINGS: [f.name for f in mappings_stage.FIELDS],
}
V020_MANIFEST_KEYS = ("coverage",)
# The time layer (every table in DERIVED_TABLES) is required from v0.3.0.
V030 = (0, 3, 0)
MAX_ERRORS_PER_CHECK = 5
# Parquet file -> (row label column, date columns), checked for v0.2.0 data.
DATE_COLUMNS = {
    ACTS: ("act_id", ("assent_date", "commencement_date", "repeal_date")),
    FOOTNOTES: ("id", ("wef_date",)),
    MAPPINGS: ("old_section", ("effective_from",)),
}


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


def version_of(manifest: dict[str, Any]) -> tuple[int, ...]:
    """The manifest version as a tuple ("v0.2.0" -> (0, 2, 0))."""
    return tuple(int(part) for part in manifest["version"].removeprefix("v").split("."))


def is_v020(manifest: dict[str, Any]) -> bool:
    """True when the manifest version is v0.2.0 or later."""
    return version_of(manifest) >= V020


def is_v030(manifest: dict[str, Any]) -> bool:
    """True when the manifest version is v0.3.0 or later: the time layer is required."""
    return version_of(manifest) >= V030


def check_v030_layout(manifest: dict[str, Any]) -> list[str]:
    """A v0.3.0 manifest promises every derived table."""
    return [f"manifest.json is missing v0.3.0 file {d.file}"
            for d in DERIVED_TABLES if d.file not in manifest["files"]]


def check_v020_layout(manifest: dict[str, Any], columns: dict[str, list[str]]) -> list[str]:
    """A v0.2.0 manifest promises the v0.2.0 manifest keys and table columns."""
    errors = [f"manifest.json is missing v0.2.0 key {key}"
              for key in V020_MANIFEST_KEYS if key not in manifest]
    errors += [f"{filename} is missing v0.2.0 column {column}"
               for filename, required in V020_COLUMNS.items()
               for column in required if column not in columns[filename]]
    return errors


def check_schemas(tables: dict[str, list[dict[str, Any]]], v020: bool) -> list[str]:
    errors = []
    schema_files = {filename: schema_file for filename, (schema_file, _) in TABLES.items()}
    schema_files.update({d.file: d.json_schema for d in DERIVED_TABLES if d.file in tables})
    for filename, schema_file in schema_files.items():
        schema = json.loads((SCHEMAS_DIR / schema_file).read_text(encoding="utf-8"))
        if not v020:  # pre-v0.2.0 tables have none of the v0.2.0 columns
            schema["required"] = [c for c in schema.get("required", [])
                                  if c not in V020_COLUMNS.get(filename, [])]
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


def check_invariants(tables: dict[str, list[dict[str, Any]]], v020: bool) -> list[str]:
    """Every version's invariants, plus the v0.2.0 ones when v020."""
    acts = tables[ACTS]
    act_ids = {a["act_id"] for a in acts}
    slug_keys = [(s["act_id"], s["structural_unit"], s["language"], s["slug"]) for s in tables[SECTIONS]]
    errors = report("Section slugs are unique per (act_id, structural_unit, language)",
                    [f"slug collision {' '.join(map(str, k))}" for k in duplicates(slug_keys)])
    errors += report("repealed_by resolves to a known Act", [
        f"{a['act_id']}: repealed_by {a['repealed_by']} is not a known act_id"
        for a in acts if a["repealed_by"] is not None and a["repealed_by"] not in act_ids])
    if not v020:
        return errors
    errors += report("work_id is unique across Acts",
                     [f"duplicate work_id {w}" for w in duplicates([a["work_id"] for a in acts])])
    errors += report("Footnote section_slugs resolve to a section of the same Act",
                     footnote_link_errors(tables))
    # v0.1.1 carries impossible wef_dates (e.g. 1959-19-01); v0.2.0 nulls them.
    errors += report("Date columns are ISO YYYY-MM-DD dates", date_errors(tables))
    errors += report("repeal_date is set only on repealed Acts", [
        f"{a['act_id']}: repeal_date {a['repeal_date']} but is_repealed is false"
        for a in acts if a["repeal_date"] is not None and not a["is_repealed"]])
    return errors


def check_coverage(manifest: dict[str, Any], tables: dict[str, list[dict[str, Any]]]) -> list[str]:
    """manifest.coverage must equal the build's coverage recomputed from the tables."""
    expected = {**acts_stage.coverage(tables[ACTS]),
                **footnotes_stage.linkage_coverage(tables[FOOTNOTES])}
    for derived in DERIVED_TABLES:
        if derived.file in tables:
            expected.update(derived.coverage(tables[derived.file]))
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
                if value is not None and calendar_date(value) is None:
                    bad.append(f"{row[key]}: {column} {value} is not an ISO YYYY-MM-DD date")
    return bad


def footnote_link_errors(tables: dict[str, list[dict[str, Any]]]) -> list[str]:
    slugs = {(s["act_id"], s["slug"]) for s in tables[SECTIONS]}
    bad = []
    for f in tables[FOOTNOTES]:
        where, slug = f"footnote {f['id']}", f["section_slug"]
        if (f["linkage_method"] == footnotes_stage.ACT_LEVEL) != (slug is None):
            bad.append(f"{where}: linkage_method {f['linkage_method']} but section_slug {slug}")
        elif slug is not None and (f["act_id"], slug) not in slugs:
            bad.append(f"{where}: section_slug {slug} is not a section of {f['act_id']}")
    return bad


# --- v0.3.0 time layer (PROCUREMENT_PLAN §7.3, §7.6) -----------------------------

Chains = dict[tuple[str, str, str], Rows]


def version_chains(versions: Rows) -> Chains:
    """Each provision's slices: (act_id, slug, language) -> rows in version_number order."""
    chains: Chains = defaultdict(list)
    for v in versions:
        chains[(v["act_id"], v["slug"], v["language"])].append(v)
    return {key: sorted(rows, key=lambda v: v["version_number"]) for key, rows in chains.items()}


def interval_errors(chains: Chains) -> list[str]:
    """valid_from <= valid_to, versions numbered 1..n, each ending where the
    next starts (no overlap, no gap), and the last open-ended."""
    bad = []
    for key, chain in chains.items():
        where = " ".join(key)
        numbers = [v["version_number"] for v in chain]
        if numbers != list(range(1, len(chain) + 1)):
            bad.append(f"{where}: version numbers {numbers} are not 1..{len(chain)}")
        for v in chain:
            if v["valid_to"] is not None and v["valid_from"] > v["valid_to"]:
                bad.append(f"{where}: version {v['version_number']} valid_from {v['valid_from']} "
                           f"is after valid_to {v['valid_to']}")
        for a, b in pairwise(chain):
            n, start = a["version_number"], b["valid_from"]
            if a["valid_to"] is None:
                bad.append(f"{where}: version {n} is open-ended but version {n + 1} starts {start}")
            elif a["valid_to"] > start:
                bad.append(f"{where}: version {n} ends {a['valid_to']} after version {n + 1} starts {start}")
            elif a["valid_to"] < start:
                bad.append(f"{where}: gap from {a['valid_to']} to {start} before version {n + 1}")
        if chain[-1]["valid_to"] is not None:
            bad.append(f"{where}: the last version ends {chain[-1]['valid_to']}, not open-ended")
    return bad


def text_status_errors(versions: Rows) -> list[str]:
    """text_status unavailable exactly when full_text is null: wording is never guessed."""
    return [f"{v['id']}: text_status {v['text_status']} but full_text is "
            f"{'set' if v['full_text'] is not None else 'null'}"
            for v in versions if (v["text_status"] == "unavailable") != (v["full_text"] is None)]


def event_link_errors(tables: dict[str, Rows], chains: Chains) -> list[str]:
    """Every slice after the first is opened by an event, except one that
    follows a slice whose wording is unavailable (e.g. an `unknown` span): that
    boundary is the date the source asserts the section from (its latest
    event, or as_of), not a change; every listed event and footnote exists;
    and every amendment event has a source (a footnote, or the Act's repeal)."""
    footnote_ids = {f["id"] for f in tables[FOOTNOTES]}
    event_ids = {e["id"] for e in tables[events_stage.FILE]}
    event_ids |= {j["id"] for j in tables[judicial_events_stage.FILE]}
    bad = []
    for chain in chains.values():
        for previous, v in pairwise(chain):
            if not v["amendment_event_ids"] and previous["text_status"] != "unavailable":
                bad.append(f"{v['id']}: version {v['version_number']} is opened by no event")
        for v in chain:
            bad += [f"{v['id']}: event {e} is not an amendment or judicial event"
                    for e in v["amendment_event_ids"] if e not in event_ids]
            bad += [f"{v['id']}: footnote {f} is not a footnote"
                    for f in v["footnote_references"] if f not in footnote_ids]
    for e in tables[events_stage.FILE]:
        if not e["footnote_ids"] and e["operation"] != "repeal":
            bad.append(f"{e['id']}: {e['operation']} event has no footnote")
        bad += [f"{e['id']}: footnote {f} is not a footnote" for f in e["footnote_ids"] if f not in footnote_ids]
    return bad


# A ruling's window may hold only these statuses (section_versions docstring):
# struck_down is final (only a repeal follows), and a stay lasts until a
# stay_lifted ruling, unless a strike-down or repeal ends it first.
AFTER_RULING = {"struck_down": ("struck_down", "repealed"), "stayed": ("stayed", "struck_down", "repealed")}


def ruling_errors(tables: dict[str, Rows], chains: Chains) -> list[str]:
    """No slice from a strike-down on, or within a stay (its decision_date up
    to the next stay_lifted), is in force: every slice there holds the
    ruling's status, or a later final one."""
    rulings: dict[tuple[str, str], Rows] = defaultdict(list)
    for j in tables[judicial_events_stage.FILE]:
        rulings[(j["act_id"], j["provision_path"])].append(j)
    bad = []
    for (act_id, slug, language), chain in chains.items():
        provision = sorted(rulings.get((act_id, slug), []), key=lambda j: j["decision_date"])
        for j in provision:
            if j["effect"] not in AFTER_RULING:
                continue
            start = j["decision_date"]
            end = next((k["decision_date"] for k in provision if j["effect"] == "stayed"
                        and k["effect"] == "stay_lifted" and k["decision_date"] > start), None)
            for v in chain:
                overlaps = (v["valid_to"] is None or v["valid_to"] > start) and \
                    (end is None or v["valid_from"] < end)
                if overlaps and v["status"] not in AFTER_RULING[j["effect"]]:
                    bad.append(f"{act_id} {slug} {language}: version {v['version_number']} is "
                               f"{v['status']} after the {j['effect']} ruling {j['id']}")
                elif overlaps and v["valid_from"] < start:
                    bad.append(f"{act_id} {slug} {language}: version {v['version_number']} is "
                               f"{v['status']} from {v['valid_from']}, before the ruling {j['id']}")
    return bad


def time_reference_errors(tables: dict[str, Rows]) -> list[str]:
    """Every act_id, central_act_id, section and jurisdiction code the time
    layer names resolves (an ISO alias is not a code: it resolves to one)."""
    act_ids = {a["act_id"] for a in tables[ACTS]}
    slugs = {(s["act_id"], s["slug"]) for s in tables[SECTIONS]}
    section_ids = {s["id"] for s in tables[SECTIONS]}
    codes = {j["code"] for j in tables[jurisdictions_stage.FILE]}
    bad = []

    def act(row_id: str, column: str, value: str | None) -> None:
        if value is not None and value not in act_ids:
            bad.append(f"{row_id}: unknown {column} {value}")

    def section(row_id: str, act_id: str, slug: str) -> None:
        if act_id in act_ids and (act_id, slug) not in slugs:
            bad.append(f"{row_id}: {act_id} has no section {slug}")

    def code(row_id: str, column: str, value: str | None) -> None:
        if value is not None and value not in codes:
            bad.append(f"{row_id}: {column} {value} is not a jurisdiction code")

    for a in tables[ACTS]:
        code(a["act_id"], "jurisdiction", a["jurisdiction"])
    for v in tables[section_versions_stage.FILE]:
        act(v["id"], "act_id", v["act_id"])
        act(v["id"], "amended_by_act_id", v["amended_by_act_id"])
        section(v["id"], v["act_id"], v["slug"])
    for e in tables[events_stage.FILE]:
        act(e["id"], "act_id", e["act_id"])
        act(e["id"], "amending_instrument_id", e["amending_instrument_id"])
        for slug in e["provisions_affected"]:
            section(e["id"], e["act_id"], slug)
    for j in tables[judicial_events_stage.FILE]:
        act(j["id"], "act_id", j["act_id"])
    for s in tables[state_amendments_stage.FILE]:
        act(s["id"], "central_act_id", s["central_act_id"])
        if s["section_id"] not in section_ids:
            bad.append(f"{s['id']}: section_id {s['section_id']} is not a section")
        code(s["id"], "state_jurisdiction", s["state_jurisdiction"])
    return bad


def check_time_layer(tables: dict[str, Rows]) -> list[str]:
    """The v0.3.0 temporal invariants and cross-references of the derived tables."""
    versions = tables[section_versions_stage.FILE]
    chains = version_chains(versions)
    errors = report("Section versions are contiguous: valid_from <= valid_to, no overlap or gap",
                    interval_errors(chains))
    errors += report("text_status is unavailable exactly when full_text is null", text_status_errors(versions))
    errors += report("Every later section version is opened by a known event, and every event has a source",
                     event_link_errors(tables, chains))
    errors += report("No section is in force after a strike-down, or during a stay until stay_lifted",
                     ruling_errors(tables, chains))
    errors += report("Time-layer tables reference known Acts, sections and jurisdiction codes",
                     time_reference_errors(tables))
    # The stage's own rules: unique codes, each alias resolving to one code,
    # succession links that resolve and agree with the validity intervals.
    errors += report("Jurisdiction codes, succession links and ISO aliases resolve",
                     jurisdictions_stage.consistency_errors(tables[jurisdictions_stage.FILE]))
    return errors


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

    v020, v030 = is_v020(manifest), is_v030(manifest)
    errors = check_files(manifest, data_dir)
    if not errors and v020:
        errors += check_v020_layout(
            manifest, {name: pq.read_schema(data_dir / name).names for name in TABLES})
    if not errors and v030:
        errors += check_v030_layout(manifest)
    if not errors:
        # Derived tables are checked when the manifest lists them (v0.2.0 data has none).
        names = [*TABLES, *(d.file for d in DERIVED_TABLES if d.file in manifest["files"])]
        tables = {name: pq.read_table(data_dir / name).to_pylist() for name in names}
        print()
        errors += check_schemas(tables, v020)
        errors += check_references(tables)
        errors += check_invariants(tables, v020)
        if v030:
            errors += check_time_layer(tables)
        if v020:
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
