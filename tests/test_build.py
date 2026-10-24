"""Build pipeline skeleton: identifiers, output shape, validity, determinism."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from conftest import ARCHIVE, FIXED_TIMESTAMP, BuildOutput, build_fixtures, corrupt_output, run_validator


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_acts_get_work_id_and_doc_type(built: BuildOutput) -> None:
    acts = {a["act_id"]: a for a in built.table("acts")}
    assert acts["A1860-45"]["work_id"] == "in-central/act/1860/45"
    assert acts["A2023-45"]["work_id"] == "in-central/act/2023/45"
    assert acts["A1909-7"]["work_id"] == "in-central/act/1909/7"
    assert {a["doc_type"] for a in acts.values()} == {"act"}


def test_fixture_build_passes_the_validator(built: BuildOutput) -> None:
    result = run_validator(built.dir)
    assert result.returncode == 0, result.stdout


@pytest.mark.parametrize(
    ("column", "bad_value"),
    [("work_id", "central/1860/45"), ("doc_type", "statute")],
)
def test_validator_rejects_malformed_identifiers(
    built: BuildOutput, tmp_path: Path, column: str, bad_value: str
) -> None:
    def break_first_act(rows: list[dict]) -> list[dict]:
        return [{**rows[0], column: bad_value}, *rows[1:]]

    broken = corrupt_output(built, tmp_path / "out", "acts", break_first_act)
    result = run_validator(broken.dir)
    assert result.returncode != 0
    assert column in result.stdout or bad_value in result.stdout


def test_two_builds_are_byte_identical(built: BuildOutput, tmp_path: Path) -> None:
    again = build_fixtures(tmp_path)
    names = sorted(p.name for p in built.dir.iterdir())
    assert names == sorted(p.name for p in again.dir.iterdir())
    assert {n: sha256(built.dir / n) for n in names} == {n: sha256(again.dir / n) for n in names}
    # Builds within the same second would hide a wall-clock gzip mtime.
    assert (built.dir / ARCHIVE).read_bytes()[4:8] == b"\0\0\0\0"


def test_archive_nests_sections_and_footnotes_per_act(built: BuildOutput) -> None:
    archive = {a["act_id"]: a for a in built.archive()}
    assert list(archive) == [a["act_id"] for a in built.table("acts")]
    anand = archive["A1909-7"]
    assert anand["work_id"] == "in-central/act/1909/7"
    assert [s["id"] for s in anand["sections"]] == [f"A1909-7:{n}" for n in range(1, 7)]
    assert [f["footnote_number"] for f in anand["footnotes"]] == [1, 2, 3, 4]
    assert archive["A1872-1"]["footnotes"] == []


def test_manifest_reports_v020_totals_and_timestamp(built: BuildOutput) -> None:
    manifest = built.manifest()
    assert manifest["version"] == "v0.2.0"
    assert manifest["export_timestamp"] == FIXED_TIMESTAMP
    assert (manifest["total_acts"], manifest["total_sections"]) == (5, 15)
    assert (manifest["total_footnotes"], manifest["total_mappings"]) == (22, 2)
    assert manifest["year_range"] == [1860, 2023]
    assert isinstance(manifest["coverage"], dict)
