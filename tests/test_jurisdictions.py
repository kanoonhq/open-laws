"""jurisdictions (ticket #13): the curated jurisdictions + ISO 3166-2:IN alias
sources, built into jurisdictions.parquet through the derived-table registry
and checked by validate.py."""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

import pyarrow.parquet as pq
import pytest
from conftest import ROOT, BuildOutput, Rows, corrupt_output, run_validator

sys.path.insert(0, str(ROOT / "scripts"))
from enrich import CURATED_DIR  # noqa: E402
from enrich.jurisdictions import code_for_name, load, resolve_code  # noqa: E402

JURISDICTIONS = "jurisdictions.parquet"


def by_code(output: BuildOutput) -> dict[str, dict]:
    return {j["code"]: j for j in output.table(JURISDICTIONS)}


def test_bombay_splits_into_maharashtra_and_gujarat_in_1960(built: BuildOutput) -> None:
    rows = by_code(built)
    bombay = rows["IN-HIST-BOMBAY"]
    assert (bombay["name"], bombay["valid_from"], bombay["valid_to"]) == ("Bombay", "1956-11-01", "1960-05-01")
    for code, name in (("IN-MH", "Maharashtra"), ("IN-GJ", "Gujarat")):
        state = rows[code]
        assert (state["name"], state["type"], state["valid_from"], state["valid_to"]) == \
            (name, "state", "1960-05-01", None)
        assert (state["successor_of"], state["inherited_laws_from"]) == (["IN-HIST-BOMBAY"], ["IN-HIST-BOMBAY"])


def test_fixture_build_with_jurisdictions_passes_the_validator(built: BuildOutput) -> None:
    result = run_validator(built.dir)
    assert result.returncode == 0, result.stdout
    assert f"{JURISDICTIONS} matches jurisdiction.schema.json" in result.stdout


def test_andhra_pradesh_splits_into_telangana_and_residuary_andhra_pradesh_in_2014(built: BuildOutput) -> None:
    rows = by_code(built)
    assert (rows["IN-HIST-AP"]["valid_to"], rows["IN-HIST-AP"]["iso_code"]) == ("2014-06-02", None)
    for code in ("IN-TS", "IN-AP"):
        assert (rows[code]["valid_from"], rows[code]["successor_of"]) == ("2014-06-02", ["IN-HIST-AP"])
    assert rows["IN-TS"]["iso_aliases"] == ["IN-TG"]


def test_jammu_and_kashmir_state_becomes_two_union_territories_in_2019(built: BuildOutput) -> None:
    rows = by_code(built)
    state = rows["IN-HIST-JK"]
    assert (state["type"], state["valid_from"], state["valid_to"]) == ("state", None, "2019-10-31")
    for code in ("IN-JK", "IN-LA"):
        ut = rows[code]
        assert (ut["type"], ut["valid_from"], ut["valid_to"]) == ("union_territory", "2019-10-31", None)
        assert ut["successor_of"] == ut["inherited_laws_from"] == ["IN-HIST-JK"]
        assert "A2019-34 s. 95" in ut["legal_basis"]  # Fifth Schedule laws


def test_other_reorganisations(built: BuildOutput) -> None:
    rows = by_code(built)
    for codes, parent, day in ((("IN-PB", "IN-HR", "IN-CH"), "IN-HIST-PUNJAB", "1966-11-01"),
                               (("IN-UP", "IN-UK"), "IN-HIST-UP", "2000-11-09"),
                               (("IN-MP", "IN-CG"), "IN-HIST-MP", "2000-11-01"),
                               (("IN-BR", "IN-JH"), "IN-HIST-BIHAR", "2000-11-15"),
                               (("IN-DH",), "IN-HIST-DD", "2020-01-26"),
                               (("IN-DH",), "IN-HIST-DN", "2020-01-26")):
        assert rows[parent]["valid_to"] == day
        for code in codes:
            assert parent in rows[code]["successor_of"] and rows[code]["valid_from"] == day
    assert rows["IN-HP"]["inherited_laws_from"] == ["IN-HIST-PUNJAB"]  # territories added in 1966


def test_current_list_is_the_36_iso_subdivisions_plus_the_union(built: BuildOutput) -> None:
    current = [j for j in built.table(JURISDICTIONS) if j["valid_to"] is None]
    types = [j["type"] for j in current]
    assert (types.count("state"), types.count("union_territory"), types.count("union")) == (28, 8, 1)
    assert all(j["iso_code"] == j["code"] for j in current if j["type"] != "union")
    assert len(built.table(JURISDICTIONS)) == 47


def test_every_row_pins_the_iso_version_and_verification_date(built: BuildOutput) -> None:
    rows = built.table(JURISDICTIONS)
    assert {(j["iso_version"], j["iso_verified_on"]) for j in rows} == {
        ("ISO 3166-2:IN as last changed by the ISO Online Browsing Platform change of 2023-11-23", "2026-10-25")}
    assert {j["iso_status"] for j in rows if j["iso_code"]} == {"verified"}
    assert all(j["source_url"] for j in rows)


@pytest.mark.parametrize(("code", "expected"), [
    ("IN-TG", "IN-TS"), ("IN-CT", "IN-CG"), ("IN-UT", "IN-UK"), ("IN-UL", "IN-UK"), ("IN-OR", "IN-OD"),
    ("IN-DN", "IN-HIST-DN"), ("IN-DD", "IN-HIST-DD"), ("IN-MH", "IN-MH"), ("IN-CENTRAL", "IN-CENTRAL"),
    ("IN-XX", None),
])
def test_codes_and_former_iso_codes_resolve(built: BuildOutput, code: str, expected: str | None) -> None:
    assert resolve_code(built.table(JURISDICTIONS), code) == expected


@pytest.mark.parametrize(("name", "on", "expected"), [
    ("Madras", None, "IN-TN"), ("Mysore", None, "IN-KA"), ("Bombay", None, "IN-HIST-BOMBAY"),
    ("Orissa", None, "IN-OD"), ("Uttaranchal", None, "IN-UK"), ("Pondicherry", None, "IN-PY"),
    ("KARNATAKA.—", None, "IN-KA"), ("Himachal Pradesh:", None, "IN-HP"), ("State of Bombay", None, "IN-HIST-BOMBAY"),
    ("Punjab", None, "IN-PB"), ("Punjab", "1960-01-01", "IN-HIST-PUNJAB"), ("Punjab", "1966-11-01", "IN-PB"),
    ("Andhra Pradesh", "2000-01-01", "IN-HIST-AP"), ("Jammu and Kashmir", "2019-10-30", "IN-HIST-JK"),
    ("Jammu & Kashmir", None, "IN-JK"), ("Bombay", "1961-01-01", None), ("Atlantis", None, None),
])
def test_names_including_historical_ones_map_to_codes(built: BuildOutput, name: str, on: str | None,
                                                       expected: str | None) -> None:
    assert code_for_name(built.table(JURISDICTIONS), name, on) == expected


def test_legal_basis_cites_acts_in_the_published_corpus() -> None:
    act_ids = set(pq.read_table(ROOT / "data" / "indian_central_acts.parquet", columns=["act_id"])
                  .column("act_id").to_pylist())
    cited = {basis.split(" ")[0] for j in load() for basis in j["legal_basis"]}
    assert cited and cited <= act_ids


def test_manifest_reports_jurisdiction_coverage(built: BuildOutput) -> None:
    assert built.manifest()["coverage"]["jurisdictions"] == {
        "rows": 47, "current": 37, "historical": 10, "iso_verified": 36, "iso_unverified": [],
        "iso_aliases": 7, "inconsistencies": 0}


def test_validator_rejects_a_dangling_succession_link(built: BuildOutput, tmp_path: Path) -> None:
    def corrupt(rows: Rows) -> Rows:
        return [{**j, "successor_of": ["IN-HIST-NOWHERE"]} if j["code"] == "IN-GJ" else j for j in rows]

    result = run_validator(corrupt_output(built, tmp_path / "out", JURISDICTIONS, corrupt).dir)
    assert result.returncode != 0
    assert "manifest coverage.jurisdictions" in result.stdout


def test_validator_rejects_an_unknown_jurisdiction_type(built: BuildOutput, tmp_path: Path) -> None:
    def corrupt(rows: Rows) -> Rows:
        return [{**rows[0], "type": "province"}, *rows[1:]]

    result = run_validator(corrupt_output(built, tmp_path / "out", JURISDICTIONS, corrupt).dir)
    assert result.returncode != 0
    assert "'province' is not one of" in result.stdout


@pytest.mark.parametrize(("file", "old", "new", "error"), [
    ("jurisdictions.csv", "IN-GJ,Gujarat,,state,1960-05-01", "IN-GJ,Gujarat,,state,1960-05-02",
     "IN-GJ: starts 1960-05-02 but its predecessor IN-HIST-BOMBAY ends 1960-05-01"),
    ("jurisdictions.csv", ",IN-HIST-BOMBAY,IN-HIST-BOMBAY,verified,A1960-11 s. 2(a)|A1960-11 s. 3",
     ",IN-HIST-BOMBAY,IN-HIST-BOMBY,verified,A1960-11 s. 2(a)|A1960-11 s. 3",
     "IN-GJ: inherited_laws_from IN-HIST-BOMBY is not a jurisdiction code"),
    ("iso_aliases.csv", "IN-OR,IN-OD", "IN-OR,IN-ODX", "IN-OR resolves to unknown code IN-ODX"),
    ("iso_aliases.csv", "IN-OR,IN-OD", "IN-MH,IN-OD", "alias IN-MH is also a jurisdiction code"),
    ("iso_aliases.csv", "iso_verified_on: 2026-10-25", "iso_verified_on: 2026-10-26",
     "pins a different ISO version or verification date"),
])
def test_inconsistent_curated_sources_fail(tmp_path: Path, file: str, old: str, new: str, error: str) -> None:
    curated = shutil.copytree(CURATED_DIR, tmp_path / "curated")
    text = (curated / file).read_text(encoding="utf-8")
    assert old in text
    (curated / file).write_text(text.replace(old, new), encoding="utf-8")
    with pytest.raises(ValueError, match=re.escape(error)):
        load(curated)
