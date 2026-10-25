"""Footnote -> section linkage and w.e.f. dates, observed through the build output."""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import BuildOutput, build_fixtures, corrupt_output, load_fixture_rows, run_validator

METHODS = {"inline_marker", "page_order", "act_level"}


def footnotes_by_id(output: BuildOutput) -> dict[str, dict]:
    return {f["id"]: f for f in output.table("footnotes")}


def link(footnote: dict) -> tuple[str | None, str]:
    return footnote["section_slug"], footnote["linkage_method"]


@pytest.mark.parametrize(
    ("footnote_id", "slug"),
    [
        ("A1909-7:Page 2:1", "1"),     # "India 2***"
        ("A1909-7:Page 2:2", "2"),     # "Anand 3[(commonly known as Anand Karaj)]"
        ("A1860-45:Page 14:2", "1"),   # "shall 3[extend to the whole of India 4***]"
        ("A1860-45:Page 14:3", "1"),
        ("A1860-45:Page 14:5", "2"),   # "within 5[India] 6***"
        ("A1860-45:Page 14:6", "3"),   # "by any 7[Indian law]"
        ("A1860-45:Page 14:7", "3"),   # "beyond 8[India]" (twice, same section)
        ("A1860-45:Page 15:0", "4"),   # "1[Illustration]" after the marker reset
        ("A1860-45:Page 15:5", "4"),   # "6* * * * *"
    ],
)
def test_known_inline_markers_link_to_their_section(built: BuildOutput, footnote_id: str,
                                                    slug: str) -> None:
    assert link(footnotes_by_id(built)[footnote_id]) == (slug, "inline_marker")


@pytest.mark.parametrize(
    "footnote_id",
    [
        "A1860-45:Page 14:4",       # marker 5 appears in sections 2 and 3: ambiguous
        "A1909-7:Page 2:0",         # no marker in any section (the Act's extension)
        "A1860-45:Page 14:0",       # precedes every marker on its page
        "A1860-45:Page 15:6",       # follows the last marker on its page
        "A2023-45:Section 2.:0",    # not a page footnote
    ],
)
def test_footnotes_without_unambiguous_evidence_stay_act_level(built: BuildOutput,
                                                               footnote_id: str) -> None:
    assert link(footnotes_by_id(built)[footnote_id]) == (None, "act_level")


def test_a_lone_marker_from_a_page_outside_the_input_is_not_forced_onto_a_page(
        built: BuildOutput) -> None:
    # Section 302's "1[imprisonment for life]" belongs to a page the fixture lacks;
    # it must not be aligned to Page 15 (8 footnotes) just because it is the only gap.
    linked = {f["section_slug"] for f in built.table("footnotes") if f["act_id"] == "A1860-45"}
    assert "302" not in linked


def test_footnote_between_two_markers_of_one_section_links_by_page_order(tmp_path: Path) -> None:
    tables = load_fixture_rows()
    for section in tables["sections"]:
        if section["id"] == "A1860-45:4":
            section["full_text"] = section["full_text"].replace("3[who is", "[who is")
    footnotes = footnotes_by_id(build_fixtures(tmp_path, tables))
    assert link(footnotes["A1860-45:Page 15:2"]) == ("4", "page_order")
    assert link(footnotes["A1860-45:Page 15:1"]) == ("4", "inline_marker")
    assert link(footnotes["A1860-45:Page 15:3"]) == ("4", "inline_marker")


def wef_variant() -> dict[str, list[dict]]:
    """The fixtures plus the Fatal Accidents Act's Page 2 footnotes (v0.1.1 rows)."""
    tables = load_fixture_rows()
    act = next(a for a in tables["acts"] if a["act_id"] == "A1909-7")
    tables["acts"].append({**act, "act_id": "A1855-13", "title": "The Fatal Accidents Act, 1855",
                           "act_number": "13", "section_count": 0, "footnote_count": 4})
    base = {"act_id": "A1855-13", "page_or_anchor": "Page 2", "amending_year": None,
            "amending_act_citation": None}
    tables["footnotes"] += [
        {**base, "id": "A1855-13:Page 2:2", "footnote_number": 3, "amendment_type": "omission",
         "raw_text": "3. The words “except the State of Jammu and Kashmir” omitted by Act 34 of "
                     "2019, s. 95 and the Fifth Schedule(w.e.f. 31-10- 2019).", "wef_date": None},
        {**base, "id": "A1855-13:Page 2:3", "footnote_number": 4, "amendment_type": "other",
         "raw_text": "4. 1st July, 2024, vide notification (w.e.f. 1st July, 2024).",
         "wef_date": None},
        {**base, "id": "A1855-13:Page 2:4", "footnote_number": 5, "amendment_type": "insertion",
         "raw_text": "5. Ins. by Act 3 of 1951, s. 3 and Sch.", "wef_date": "1951-04-01"},
        # Footnote 7 run into footnote 6's text: its date is not footnote 6's.
        {**base, "id": "A1855-13:Page 2:5", "footnote_number": 6, "amendment_type": "substitution",
         "raw_text": "6. Subs. by Act 24 of 1978, s. 6, for “five years” (w.e.f. 21-7-198).7. Sub-section "
                     "(2) omitted by Act 55 of 1963, s. 2 (w.e.f. 1-2-1964).", "wef_date": None},
    ]
    return tables


def test_wef_dates_are_reparsed_from_raw_text(tmp_path: Path) -> None:
    output = build_fixtures(tmp_path, wef_variant())
    footnotes = footnotes_by_id(output)
    assert footnotes["A1855-13:Page 2:2"]["wef_date"] == "2019-10-31"
    assert footnotes["A1909-7:Page 2:1"]["wef_date"] == "2019-10-31"
    assert footnotes["A1909-7:Page 2:0"]["wef_date"] == "1965-07-01"  # "w.e.f. 1-7-1965"
    assert footnotes["A1855-13:Page 2:3"]["wef_date"] == "2024-07-01"
    # No date in raw_text: the v0.1.1 value is kept.
    assert footnotes["A1855-13:Page 2:4"]["wef_date"] == "1951-04-01"
    assert footnotes["A1855-13:Page 2:5"]["wef_date"] is None
    with_wef = sum(f["wef_date"] is not None for f in footnotes.values())
    assert output.manifest()["footnotes_with_wef"] == with_wef
    assert run_validator(output.dir).returncode == 0


def test_manifest_reports_footnote_linkage_coverage(built: BuildOutput) -> None:
    coverage = built.manifest()["coverage"]
    footnotes = built.table("footnotes")
    by_method = coverage["footnote_links_by_method"]
    assert set(by_method) == METHODS
    assert by_method == {m: sum(f["linkage_method"] == m for f in footnotes) for m in METHODS}
    assert by_method["inline_marker"] >= 9
    linked = len(footnotes) - by_method["act_level"]
    assert coverage["footnote_linkage_rate"] == round(linked / len(footnotes), 4)
    per_act = coverage["footnote_linkage_by_act"]
    assert set(per_act) == {"A1860-45", "A2023-45", "A1909-7"}  # Acts with footnotes
    assert per_act["A2023-45"] == 0.0
    assert per_act["A1909-7"] == 0.5  # 2 of 4


def test_linked_build_passes_the_validator(built: BuildOutput) -> None:
    footnotes = built.table("footnotes")
    assert {f["linkage_method"] for f in footnotes} <= METHODS
    assert all((f["section_slug"] is None) == (f["linkage_method"] == "act_level")
               for f in footnotes)
    result = run_validator(built.dir)
    assert result.returncode == 0, result.stdout


@pytest.mark.parametrize("bad_method", ["guessed", None])
def test_validator_rejects_an_unknown_linkage_method(built: BuildOutput, tmp_path: Path,
                                                     bad_method: str | None) -> None:
    def break_first(rows: list[dict]) -> list[dict]:
        return [{**rows[0], "linkage_method": bad_method}, *rows[1:]]

    broken = corrupt_output(built, tmp_path / "out", "footnotes", break_first)
    result = run_validator(broken.dir)
    assert result.returncode != 0
    assert "central_act_footnotes.parquet row 0" in result.stdout
