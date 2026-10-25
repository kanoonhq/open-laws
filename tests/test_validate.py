"""Validator invariants for v0.2.0 (ticket #6): corrupt the fixture build,
re-seal its checksums, and expect validate.py to name the broken invariant."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pyarrow.parquet as pq
import pytest
from conftest import (
    TABLE_FILES,
    BuildOutput,
    Rows,
    corrupt_output,
    load_fixture_rows,
    run_validator,
    write_input_dir,
)


def assert_rejected(broken: BuildOutput, message: str) -> None:
    result = run_validator(broken.dir)
    assert result.returncode != 0, result.stdout
    failures = [line for line in result.stdout.splitlines() if line.startswith("❌")]
    assert failures, result.stdout
    assert all(message in line for line in failures), failures


def test_rejects_duplicate_work_id(built: BuildOutput, tmp_path: Path) -> None:
    def duplicate(rows: Rows) -> Rows:
        return [rows[0], {**rows[1], "work_id": rows[0]["work_id"]}, *rows[2:]]

    broken = corrupt_output(built, tmp_path / "out", "acts", duplicate)
    assert_rejected(broken, "duplicate work_id in-central/act/1909/7")


def test_rejects_slug_collision(built: BuildOutput, tmp_path: Path) -> None:
    def collide(rows: Rows) -> Rows:  # no footnote links to A1909-7 section 6
        return [{**s, "slug": "5"} if s["id"] == "A1909-7:6" else s for s in rows]

    broken = corrupt_output(built, tmp_path / "out", "sections", collide)
    assert_rejected(broken, "slug collision A1909-7 section en 5")


def update_footnote(act_id: str, number: int, **changes: object):
    def mutate(rows: Rows) -> Rows:
        target = next(i for i, f in enumerate(rows)
                      if (f["act_id"], f["footnote_number"]) == (act_id, number))
        return [{**f, **changes} if i == target else f for i, f in enumerate(rows)]
    return mutate


def test_rejects_dangling_footnote_slug(built: BuildOutput, tmp_path: Path) -> None:
    # A1909-7 has no section 302 (A1860-45 does: slugs resolve within one Act)
    broken = corrupt_output(built, tmp_path / "out", "footnotes",
                            update_footnote("A1909-7", 2, section_slug="302"))
    assert_rejected(broken, "section_slug 302 is not a section of A1909-7")


def test_rejects_act_level_footnote_with_slug(built: BuildOutput, tmp_path: Path) -> None:
    broken = corrupt_output(built, tmp_path / "out", "footnotes",
                            update_footnote("A1909-7", 1, section_slug="1"))
    assert_rejected(broken, "linkage_method act_level but section_slug 1")


def test_rejects_linked_footnote_without_slug(built: BuildOutput, tmp_path: Path) -> None:
    broken = corrupt_output(built, tmp_path / "out", "footnotes",
                            update_footnote("A1909-7", 2, section_slug=None))
    assert_rejected(broken, "linkage_method inline_marker but section_slug None")


def test_v020_manifest_requires_the_section_slug_column(built: BuildOutput, tmp_path: Path) -> None:
    def drop_section_slug(rows: Rows) -> Rows:
        return [{k: v for k, v in f.items() if k != "section_slug"} for f in rows]

    broken = corrupt_output(built, tmp_path / "out", "footnotes", drop_section_slug)
    assert_rejected(broken, "central_act_footnotes.parquet is missing v0.2.0 column section_slug")


def test_v020_manifest_requires_coverage(built: BuildOutput, tmp_path: Path) -> None:
    shutil.copytree(built.dir, tmp_path / "out")
    manifest_path = tmp_path / "out" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    del manifest["coverage"]
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    assert_rejected(BuildOutput(tmp_path / "out"), "manifest.json is missing v0.2.0 key coverage")


def test_v011_data_still_validates(tmp_path: Path) -> None:
    # The fixture inputs are v0.1.1 tables: no v0.2.0 columns or coverage, and
    # v0.1.1 carries impossible wef_dates (A1950-64:Page 15:4 has 1959-19-01).
    v011 = load_fixture_rows()
    v011["footnotes"][0] = {**v011["footnotes"][0], "wef_date": "1959-19-01"}
    data_dir = write_input_dir(v011, tmp_path / "v011")
    rows = {"total_acts": "acts", "total_sections": "sections",
            "total_footnotes": "footnotes", "total_mappings": "mappings"}
    tables = {name: pq.read_table(data_dir / TABLE_FILES[name]) for name in TABLE_FILES}
    manifest = {
        "version": "v0.1.1",
        **{key: tables[name].num_rows for key, name in rows.items()},
        "footnotes_with_wef": 0,
        "files": {TABLE_FILES[name]: {
            "size_bytes": (data_dir / TABLE_FILES[name]).stat().st_size,
            "sha256": hashlib.sha256((data_dir / TABLE_FILES[name]).read_bytes()).hexdigest(),
            "rows": tables[name].num_rows} for name in TABLE_FILES},
    }
    (data_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    result = run_validator(data_dir)
    assert result.returncode == 0, result.stdout


def update_act(act_id: str, **changes: object):
    def mutate(rows: Rows) -> Rows:
        return [{**a, **changes} if a["act_id"] == act_id else a for a in rows]
    return mutate


def test_rejects_unknown_repealed_by(built: BuildOutput, tmp_path: Path) -> None:
    broken = corrupt_output(built, tmp_path / "out", "acts",
                            update_act("A1860-45", repealed_by="A2023-99"))
    assert_rejected(broken, "A1860-45: repealed_by A2023-99 is not a known act_id")


def test_rejects_impossible_calendar_date(built: BuildOutput, tmp_path: Path) -> None:
    # The schema pattern accepts it; the calendar does not.
    broken = corrupt_output(built, tmp_path / "out", "acts",
                            update_act("A1909-7", commencement_date="1909-02-30"))
    assert_rejected(broken, "A1909-7: commencement_date 1909-02-30 is not an ISO YYYY-MM-DD date")


def test_rejects_impossible_wef_date(built: BuildOutput, tmp_path: Path) -> None:
    broken = corrupt_output(built, tmp_path / "out", "footnotes",
                            update_footnote("A1909-7", 2, wef_date="1959-19-01"))
    assert_rejected(broken, "wef_date 1959-19-01 is not an ISO YYYY-MM-DD date")


def test_rejects_repeal_date_on_act_in_force(built: BuildOutput, tmp_path: Path) -> None:
    broken = corrupt_output(built, tmp_path / "out", "acts",
                            update_act("A1909-7", repeal_date="2024-07-01"))
    assert_rejected(broken, "A1909-7: repeal_date 2024-07-01 but is_repealed is false")


@pytest.mark.parametrize(
    ("key", "value"),
    [("footnote_linkage_rate", 0.99), ("acts_with_assent_date", 4),
     ("footnote_links_by_method", {"inline_marker": 22, "page_order": 0, "act_level": 0})],
)
def test_rejects_tampered_coverage(built: BuildOutput, tmp_path: Path, key: str, value: object) -> None:
    shutil.copytree(built.dir, tmp_path / "out")
    manifest_path = tmp_path / "out" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["coverage"][key] = value
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    assert_rejected(BuildOutput(tmp_path / "out"), f"manifest coverage.{key}")


@pytest.mark.parametrize("count", ["linked", "total"])
def test_rejects_tampered_per_act_footnote_counts(built: BuildOutput, tmp_path: Path,
                                                  count: str) -> None:
    shutil.copytree(built.dir, tmp_path / "out")
    manifest_path = tmp_path / "out" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["coverage"]["footnote_linkage_by_act"]["A1909-7"][count] += 1
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    assert_rejected(BuildOutput(tmp_path / "out"), "manifest coverage.footnote_linkage_by_act")
