"""Build pipeline skeleton: identifiers, output shape, validity, determinism."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import (
    ARCHIVE,
    BUILD,
    FIXED_TIMESTAMP,
    BuildOutput,
    build_fixtures,
    corrupt_output,
    load_fixture_rows,
    run_validator,
    write_input_dir,
)


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


def test_manifest_reports_v030_totals_and_timestamp(built: BuildOutput) -> None:
    manifest = built.manifest()
    assert manifest["version"] == "v0.3.0"
    assert manifest["export_timestamp"] == FIXED_TIMESTAMP
    assert (manifest["total_acts"], manifest["total_sections"]) == (5, 15)
    assert (manifest["total_footnotes"], manifest["total_mappings"]) == (22, 2)
    assert manifest["year_range"] == [1860, 2023]
    assert isinstance(manifest["coverage"], dict)


def build_without_timestamp(tmp_path: Path, env: dict[str, str],
                            input_manifest: dict | None) -> subprocess.CompletedProcess[str]:
    input_dir = write_input_dir(load_fixture_rows(), tmp_path / "in")
    if input_manifest is not None:
        (input_dir / "manifest.json").write_text(json.dumps(input_manifest), encoding="utf-8")
    clean = {k: v for k, v in os.environ.items() if k != "SOURCE_DATE_EPOCH"}
    return subprocess.run(
        [sys.executable, str(BUILD), "--input-dir", str(input_dir), "--output-dir",
         str(tmp_path / "out")], env={**clean, **env}, capture_output=True, text=True, check=False)


def test_default_timestamp_is_the_input_manifests_export_timestamp(tmp_path: Path) -> None:
    result = build_without_timestamp(
        tmp_path, {}, {"export_timestamp": "2026-10-24T18:18:57.858255+00:00"})
    assert result.returncode == 0, result.stderr
    assert BuildOutput(tmp_path / "out").manifest()["export_timestamp"] == \
        "2026-10-24T18:18:57.858255+00:00"


def test_source_date_epoch_overrides_the_input_manifest(tmp_path: Path) -> None:
    result = build_without_timestamp(tmp_path, {"SOURCE_DATE_EPOCH": "1767225600"},
                                     {"export_timestamp": "2026-10-24T18:18:57+00:00"})
    assert result.returncode == 0, result.stderr
    assert BuildOutput(tmp_path / "out").manifest()["export_timestamp"] == FIXED_TIMESTAMP


def test_build_refuses_to_use_the_clock_for_a_timestamp(tmp_path: Path) -> None:
    result = build_without_timestamp(tmp_path, {}, None)
    assert result.returncode != 0
    assert not (tmp_path / "out" / "manifest.json").exists()
