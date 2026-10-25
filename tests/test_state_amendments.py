"""state_amendments (ticket #16): the STATE AMENDMENT blocks in section text,
split into one row per state entry, built through the derived-table registry
and checked by validate.py.

The fixtures add real v0.1.1 section rows, copied verbatim with their Acts
(tests/fixtures/state_amendments/blocks.json):
- Industrial Disputes Act s. 2 (A1947-14:2): three run-in entries on one line.
- CrPC s. 24 (A1974-2:24): six entries under state-name lines, a second
  STATE AMENDMENT header for "Jammu and Kashmir and Ladakh (UTs)", and
  entries that make several kinds of change (kept raw, with a null type).
- CrPC s. 197 (A1974-2:197): a last entry with no [Vide …] reference.
- RFCTLARR Act ss. 24 and 40 (A2013-30): an added proviso, and w.e.f. dates.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import BuildOutput, Rows, build_fixtures, load_fixture_rows, run_validator

STATE_AMENDMENTS = "state_amendments.parquet"
BLOCKS = Path(__file__).resolve().parent / "fixtures" / "state_amendments" / "blocks.json"


def with_blocks(tables: dict[str, Rows]) -> dict[str, Rows]:
    extra = json.loads(BLOCKS.read_text(encoding="utf-8"))
    return {**tables, "acts": [*tables["acts"], *extra["acts"]],
            "sections": [*tables["sections"], *extra["sections"]]}


@pytest.fixture(scope="module")
def built_blocks(tmp_path_factory: pytest.TempPathFactory) -> BuildOutput:
    return build_fixtures(tmp_path_factory.mktemp("state"), with_blocks(load_fixture_rows()))


def by_id(output: BuildOutput) -> dict[str, dict]:
    return {r["id"]: r for r in output.table(STATE_AMENDMENTS)}


def test_run_in_entries_split_into_one_row_per_state(built_blocks: BuildOutput) -> None:
    rows = [r for r in built_blocks.table(STATE_AMENDMENTS) if r["section_id"] == "A1947-14:2"]
    assert [(r["id"], r["state_name"], r["state_jurisdiction"], r["amendment_type"]) for r in rows] == [
        ("A1947-14:s2:IN-KL", "Kerala", "IN-KL", "substitution"),
        ("A1947-14:s2:IN-AS", "Assam", "IN-AS", "insertion"),
        ("A1947-14:s2:IN-OD", "Orissa", "IN-OD", "substitution"),
    ]
    kerala = rows[0]
    assert kerala["central_act_id"] == "A1947-14"
    assert kerala["section_number"] == "2"
    assert kerala["state_act_reference"] == "Kerala Act 12 of 2017, s. 2"
    assert kerala["amended_text"] == (
        "Amendment of section 2.—In section 2 of the Industrial Disputes Act, 1947 (Central Act 14 of "
        "1947), in clause (s), for the words “clerical or supervisory work” the words “clerical, "
        "supervisory work or any work for the promotion of sales” shall be substituted.")
    assert kerala["valid_to"] is None


def crpc_rows(output: BuildOutput) -> Rows:
    return [r for r in output.table(STATE_AMENDMENTS) if r["section_id"] == "A1974-2:24"]


def test_entries_under_state_name_lines_and_a_second_header(built_blocks: BuildOutput) -> None:
    assert [(r["id"], r["state_name"], r["amendment_type"]) for r in crpc_rows(built_blocks)] == [
        ("A1974-2:s24:IN-KA", "Karnataka", None),           # omitted + substituted
        ("A1974-2:s24:IN-MH", "Maharashtra", None),         # deleted + inserted
        ("A1974-2:s24:IN-HIST-MP", "Madhya Pradesh", None),  # substituted + inserted
        ("A1974-2:s24:IN-WB", "West Bengal", "substitution"),
        ("A1974-2:s24:IN-WB-2", "West Bengal", "omission"),
        # One heading naming two Union territories: one row each.
        ("A1974-2:s24:IN-JK", "Jammu and Kashmir", "insertion"),
        ("A1974-2:s24:IN-LA", "Ladakh", "insertion"),
    ]


def test_state_name_maps_to_the_unit_in_existence_in_the_reference_year(built_blocks: BuildOutput) -> None:
    # Madhya Pradesh Act 21 of 1995 amended the undivided State (split 2000-11-01).
    mp = by_id(built_blocks)["A1974-2:s24:IN-HIST-MP"]
    assert (mp["state_jurisdiction"], mp["state_act_reference"]) == (
        "IN-HIST-MP", "Madhya Pradesh Act 21 of 1995, s. 3")


def test_vide_reference_is_kept_as_printed(built_blocks: BuildOutput) -> None:
    rows = by_id(built_blocks)
    assert rows["A1974-2:s24:IN-WB-2"]["state_act_reference"] == "West Bengal Act 25 of 1992, s. 3"
    assert rows["A1974-2:s24:IN-LA"]["state_act_reference"] == (
        "Jammu and Kashmir Reorganization (Adaptation of Central Laws) Order, 2020, "
        "vide notification No. S.O. 1123(E) dated (18-3-2020)")


def test_entry_with_several_kinds_of_change_is_kept_raw_with_a_null_type(built_blocks: BuildOutput) -> None:
    ka = by_id(built_blocks)["A1974-2:s24:IN-KA"]
    assert ka["amendment_type"] is None
    assert ka["state_jurisdiction"] == "IN-KA"
    assert ka["section_number"] == "24"
    assert ka["raw_text"] == (
        "Karnataka\nAmendment of section 24.- In section 24 of the Code of Criminal Procedure, 1973 "
        "(Central Act 2 of 1974) (hereinafter referred to as the principal Act) in sub-section (1),—\n"
        "(i) the words and punctuation mark “or the State Government shall”, shall be omitted; and\n"
        "(ii) for the words “appoint a Public Prosecutor” the words “or the State Government shall "
        "appoint a Public Prosecutor” shall be substituted.\n[Vide Karnataka Act 20 of 1982, s. 2.]")


def test_section_number_where_the_entry_states_it(built_blocks: BuildOutput) -> None:
    assert {r["section_number"] for r in crpc_rows(built_blocks)} == {"24"}


def test_crpc_rows_close_at_the_bnss_transition(built_blocks: BuildOutput) -> None:
    assert {r["valid_to"] for r in crpc_rows(built_blocks)} == {"2024-07-01"}


def test_section_text_is_left_unchanged(built_blocks: BuildOutput) -> None:
    extra = {s["id"]: s for s in json.loads(BLOCKS.read_text(encoding="utf-8"))["sections"]}
    out = {s["id"]: s for s in built_blocks.table("sections") if s["id"] in extra}
    assert {k: s["full_text"] for k, s in out.items()} == {k: s["full_text"] for k, s in extra.items()}


def test_coverage_reports_parsed_and_raw(built_blocks: BuildOutput) -> None:
    c = built_blocks.manifest()["coverage"]["state_amendments"]
    assert (c["rows"], c["parsed"], c["raw"], c["sections"]) == (15, 10, 5, 5)
    assert c["without_reference"] == 1
    assert c["unmapped_state_names"] == []


def test_wef_date_printed_with_the_reference_is_the_effective_date(built_blocks: BuildOutput) -> None:
    mh = by_id(built_blocks)["A2013-30:s40:IN-MH"]
    assert (mh["amendment_type"], mh["section_number"], mh["effective_date"]) == ("insertion", "40", "2018-04-26")
    assert mh["state_act_reference"] == "Maharashtra Act 37 of 2018, sec. 7 (w.e.f. 26.4.2018)"
    assert by_id(built_blocks)["A1947-14:s2:IN-KL"]["effective_date"] is None


def test_an_added_proviso_is_a_proviso_unless_mixed_with_other_changes(built_blocks: BuildOutput) -> None:
    rows = by_id(built_blocks)
    ap, mh = rows["A2013-30:s24:IN-AP"], rows["A2013-30:s24:IN-MH"]
    assert (ap["amendment_type"], ap["effective_date"]) == (None, "2014-01-01")  # substituted + proviso
    # "(26-4-2018)" is printed without "w.e.f.", so it is not taken as the effective date.
    assert (mh["amendment_type"], mh["effective_date"]) == ("proviso", None)


def test_last_entry_without_a_reference_is_kept(built_blocks: BuildOutput) -> None:
    rows = [r for r in built_blocks.table(STATE_AMENDMENTS) if r["section_id"] == "A1974-2:197"]
    assert [(r["id"], r["amendment_type"], r["state_act_reference"]) for r in rows] == [
        ("A1974-2:s197:IN-TR", "insertion", "Tripura Act 6 of 2003, s. 2"),
        ("A1974-2:s197:IN-AS", None, None),  # substituted + inserted, and no [Vide …]
    ]
    assert rows[1]["raw_text"].startswith("Assam.— In Section 197 of the Code. —\n(a) in sub-section (1)")
    assert rows[1]["section_number"] == "197"


def test_validator_accepts_the_build(built_blocks: BuildOutput) -> None:
    result = run_validator(built_blocks.dir)
    assert result.returncode == 0, result.stdout + result.stderr
