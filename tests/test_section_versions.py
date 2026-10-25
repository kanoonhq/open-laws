"""indian_act_section_versions (ticket #15): bi-temporal section slices built
through the derived-table registry. The current slice is verbatim; earlier
slices are reverse-reconstructed only when every footnote is unambiguous,
else unavailable; judicial rulings and Act repeals split the chain."""

from __future__ import annotations

import hashlib
from datetime import date, timedelta
from pathlib import Path

import pytest
from conftest import (
    FIXED_TIMESTAMP,
    BuildOutput,
    Rows,
    build_fixtures,
    corrupt_output,
    load_fixture_rows,
    run_validator,
)

VERSIONS = "indian_act_section_versions.parquet"


def slices(output: BuildOutput, act_id: str, slug: str) -> list[dict]:
    rows = [v for v in output.table(VERSIONS) if (v["act_id"], v["slug"]) == (act_id, slug)]
    return sorted(rows, key=lambda v: v["version_number"])


def test_insertion_is_reversed_in_the_earlier_slice(built: BuildOutput) -> None:
    # Anand Marriage Act s. 2: "Anand 3[(commonly known as Anand Karaj)] shall be, ..."
    # with "3. Ins. by Act 29 of 2012, s. 2 (w.e.f. 1-11-2013)."
    before, current = slices(built, "A1909-7", "2")
    assert (current["valid_from"], current["valid_to"]) == ("2013-11-01", None)
    assert (current["text_status"], current["confidence"]) == ("verbatim_source", 1.0)
    assert "Anand 3[(commonly known as Anand Karaj)] shall be" in current["full_text"]
    assert (before["valid_from"], before["valid_to"]) == ("1909-10-22", "2013-11-01")
    assert before["text_status"] == "reconstructed"
    assert abs(before["confidence"] - 0.8) < 1e-6
    assert before["full_text"].startswith(
        "All marriages which may be or may have been duly solemnized according to the Sikh "
        "marriage ceremony called Anand shall be, and shall be deemed")
    assert current["amendment_event_ids"] == ["A1909-7:ev:act-29-of-2012:s2"]
    assert current["footnote_references"] == ["A1909-7:Page 2:2"]
    assert before["amendment_event_ids"] == []
    assert [v["status"] for v in (before, current)] == ["in_force", "in_force"]


# --- fixture variants ---------------------------------------------------------

IPC_376 = ("(1) Whoever, except in the cases provided for in sub-section (2), commits rape, shall be "
           "punished with rigorous imprisonment of either description for a term which 2[shall not be "
           "less than ten years, but which may extend to imprisonment for life, and shall also be liable "
           "to fine].")
IPC_124A = ("Whoever by words, either spoken or written, or by signs, or by visible representation, or "
            "otherwise, brings or attempts to bring into hatred or contempt, or excites or attempts to "
            "excite disaffection towards, the Government established by law in India, shall be punished "
            "with imprisonment for life, to which fine may be added, or with imprisonment which may "
            "extend to three years, to which fine may be added, or with fine.")
IT_66A = ("Any person who sends, by means of a computer resource or a communication device,–\n(a) any "
          "information that is grossly offensive or has menacing character; or\nshall be punishable with "
          "imprisonment for a term which may extend to three years and with fine.]")


def section(base: dict, act_id: str, number: str, text: str, heading: str) -> dict:
    slug = number.removeprefix("Section ").rstrip(".").lower()
    return {**base, "id": f"{act_id}:{slug}", "act_id": act_id, "section_number": number, "slug": slug,
            "heading": heading, "full_text": text}


def footnote(base: dict, act_id: str, page: str, number: int, text: str, kind: str) -> dict:
    return {**base, "id": f"{act_id}:{page}:{number - 1}", "act_id": act_id, "page_or_anchor": page,
            "footnote_number": number, "raw_text": text, "amendment_type": kind,
            "amending_act_citation": None, "amending_year": None, "wef_date": None}


def variant() -> dict[str, Rows]:
    """The fixtures plus IPC ss. 124A and 376 (s. 376 with a synthetic dated
    substitution quoting the replaced words, modelled on the real 2018
    footnote), a dated substitution footnote for IPC s. 302, and a stub
    Information Technology Act, 2000 with s. 66A."""
    tables = load_fixture_rows()
    s0, f0 = tables["sections"][0], tables["footnotes"][0]
    it_act = {**tables["acts"][0], "act_id": "A2000-21", "act_number": "ACT NO. 21 OF 2000",
              "title": "THE INFORMATION TECHNOLOGY ACT, 2000", "enactment_date": "[9th June, 2000.]",
              "is_repealed": False, "repealed_by": None, "repeal_reason": None,
              "section_count": 1, "footnote_count": 0}
    ipc = next(a for a in tables["acts"] if a["act_id"] == "A1860-45")
    ipc["section_count"] += 2
    ipc["footnote_count"] += 2
    s302 = next(s for s in tables["sections"] if s["id"] == "A1860-45:302")
    at = tables["sections"].index(s302)
    tables["sections"][at:at + 1] = [
        section(s0, "A1860-45", "Section 124A.", IPC_124A, "Sedition."), s302,
        section(s0, "A1860-45", "Section 376.", IPC_376, "Punishment for rape.")]
    tables["sections"].append(section(
        s0, "A2000-21", "Section 66A.", IT_66A,
        "Punishment for sending offensive messages through communication service, etc."))
    tables["footnotes"] += [
        footnote(f0, "A1860-45", "Page 90", 1,
                 "1. Subs. by Act 26 of 1955, s. 117 and the Sch., for “transportation for life” "
                 "(w.e.f. 1-1-1956).", "substitution"),
        footnote(f0, "A1860-45", "Page 90", 2,
                 "2. Subs. by Act 13 of 2013, s. 9, for “shall not be less than seven years, but which "
                 "may extend to imprisonment for life, and shall also be liable to fine” (w.e.f. "
                 "03-02-2013).", "substitution"),
    ]
    tables["acts"].append(it_act)
    return tables


@pytest.fixture(scope="module")
def built_variant(tmp_path_factory: pytest.TempPathFactory) -> BuildOutput:
    return build_fixtures(tmp_path_factory.mktemp("versions"), variant())


def retyped(tables: dict[str, Rows], footnote_id: str, **fields: object) -> dict[str, Rows]:
    tables["footnotes"] = [{**f, **fields} if f["id"] == footnote_id else f for f in tables["footnotes"]]
    return tables


def test_ipc_376_pre_2013_slice_is_reconstructed_from_the_quoted_text(built_variant: BuildOutput) -> None:
    before, current, repealed = slices(built_variant, "A1860-45", "376")
    assert [(v["valid_from"], v["valid_to"]) for v in (before, current, repealed)] == [
        ("1860-10-06", "2013-02-03"), ("2013-02-03", "2024-07-01"), ("2024-07-01", None)]
    assert before["text_status"] == "reconstructed"
    assert before["full_text"].endswith(
        "for a term which shall not be less than seven years, but which may extend to imprisonment for "
        "life, and shall also be liable to fine.")
    assert current["id"] == "A1860-45:376:2013-02-03"
    assert current["amendment_citation"] == "Act 13 of 2013, s. 9"
    assert current["change_summary"] == "Substituted by Act 13 of 2013, s. 9"
    assert current["text_status"] == "verbatim_source"


def test_substitution_reversed_and_marker_stripped(built_variant: BuildOutput) -> None:
    before, current, _ = slices(built_variant, "A1860-45", "302")
    assert before["full_text"] == ("Whoever commits murder shall be punished with death or transportation "
                                   "for life, and shall also be liable to fine.")
    assert (before["valid_to"], current["valid_from"]) == ("1956-01-01", "1956-01-01")


def test_omission_is_restored_from_the_quoted_words(tmp_path: Path) -> None:
    # Anand Marriage Act s. 1 "(2) Its extends to the whole of India 2***." with
    # "2. The words “except the State of Jammu and Kashmir” omitted by Act 34 of
    # 2019 ... (w.e.f. 31-10- 2019)", which v0.1.1 typed `other`; typed omission:
    tables = retyped(load_fixture_rows(), "A1909-7:Page 2:1", amendment_type="omission")
    before, current = slices(build_fixtures(tmp_path, tables), "A1909-7", "1")
    assert before["full_text"].endswith(
        "(2) Its extends to the whole of India except the State of Jammu and Kashmir.")
    assert (before["text_status"], before["valid_to"]) == ("reconstructed", "2019-10-31")
    assert current["full_text"].endswith("the whole of India 2***.")


def test_operation_disagreeing_with_the_marker_is_unavailable(built: BuildOutput) -> None:
    # The same omission as v0.1.1 typed it (`other`): not reversible.
    before, current = slices(built, "A1909-7", "1")
    assert (before["valid_from"], before["valid_to"]) == ("1909-10-22", "2019-10-31")
    assert (before["text_status"], before["full_text"], before["heading"]) == ("unavailable", None, None)
    assert before["confidence"] == 0.0
    assert current["text_status"] == "verbatim_source"


def test_insertion_footnote_quoting_old_words_is_unavailable(tmp_path: Path) -> None:
    # v0.1.1 typed some substitutions `insertion`; the quoted words then disagree with `N[`.
    tables = retyped(load_fixture_rows(), "A1909-7:Page 2:2",
                     raw_text="3. Subs. by Act 29 of 2012, s. 2, for “(Anand)” (w.e.f. 1-11-2013).")
    before, _ = slices(build_fixtures(tmp_path, tables), "A1909-7", "2")
    assert (before["text_status"], before["full_text"]) == ("unavailable", None)


def test_nested_brackets_stay_unavailable(tmp_path: Path) -> None:
    tables = load_fixture_rows()
    tables["sections"] = [
        {**s, "full_text": s["full_text"].replace("Anand 3[(commonly known as Anand Karaj)]",
                                                  "Anand 3[(commonly known as [Anand Karaj])]")}
        if s["id"] == "A1909-7:2" else s for s in tables["sections"]]
    before, current = slices(build_fixtures(tmp_path, tables), "A1909-7", "2")
    assert (before["text_status"], before["full_text"]) == ("unavailable", None)
    assert current["text_status"] == "verbatim_source"


def test_reversal_leaves_no_stray_whitespace(tmp_path: Path) -> None:
    tables = load_fixture_rows()
    tables["sections"] = [{**s, "full_text": "called Anand 3[(commonly known as Anand Karaj)]\n"}
                          if s["id"] == "A1909-7:2" else s for s in tables["sections"]]
    tables = retyped(tables, "A1909-7:Page 2:2", amendment_type="substitution",
                     raw_text="3. Subs. by Act 29 of 2012, s. 2, for “, Karaj” (w.e.f. 1-11-2013).")
    before, _ = slices(build_fixtures(tmp_path / "subs", tables), "A1909-7", "2")
    assert before["full_text"] == "called Anand, Karaj\n"  # no space left before the comma
    tables = retyped(tables, "A1909-7:Page 2:2", amendment_type="insertion",
                     raw_text="3. Ins. by Act 29 of 2012, s. 2 (w.e.f. 1-11-2013).")
    before, _ = slices(build_fixtures(tmp_path / "ins", tables), "A1909-7", "2")
    assert before["full_text"] == "called Anand"  # no trailing space or line


def test_an_undated_event_stops_the_chain(built: BuildOutput) -> None:
    # IPC s. 1 has a dated omission (w.e.f. 31-10-2019) and undated amendments
    # ("3. The Original words have successively been amended by ..."): no slice
    # before 2019-10-31 is emitted, and no date is assumed for the undated ones.
    current, repealed = slices(built, "A1860-45", "1")
    assert (current["valid_from"], current["valid_to"]) == ("2019-10-31", "2024-07-01")
    assert current["version_number"] == 1
    assert repealed["status"] == "repealed"


def test_ipc_gets_a_repealed_slice_from_2024_07_01(built: BuildOutput) -> None:
    *_, last = slices(built, "A1860-45", "302")
    assert (last["valid_from"], last["valid_to"], last["status"]) == ("2024-07-01", None, "repealed")
    assert last["amendment_event_ids"] == ["A1860-45:ev:A2023-45:repeal"]
    assert last["amended_by_act_id"] == "A2023-45"
    assert all(v["status"] == "in_force" for v in slices(built, "A2023-45", "103"))


def test_66a_is_struck_down_from_2015_03_24(built_variant: BuildOutput) -> None:
    enacted, struck = slices(built_variant, "A2000-21", "66a")
    assert (enacted["valid_from"], enacted["valid_to"], enacted["status"]) == (
        "2000-06-09", "2015-03-24", "in_force")
    assert (struck["valid_from"], struck["valid_to"], struck["status"]) == ("2015-03-24", None, "struck_down")
    assert struck["full_text"] == IT_66A
    assert struck["amendment_event_ids"] == ["A2000-21:je:66a:2015-03-24"]
    assert struck["change_summary"] == "Struck down: Shreya Singhal v. Union of India, Supreme Court of India"


def test_124a_is_stayed_from_2022_05_11_until_repeal(built_variant: BuildOutput) -> None:
    assert [(v["valid_from"], v["status"]) for v in slices(built_variant, "A1860-45", "124a")] == [
        ("1860-10-06", "in_force"), ("2022-05-11", "stayed"), ("2024-07-01", "repealed")]


def test_provenance_fields(built: BuildOutput) -> None:
    v = slices(built, "A1909-7", "2")[0]
    text = next(s["full_text"] for s in built.table("sections") if s["id"] == "A1909-7:2")
    assert v["source_sha256"] == hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert v["source_url"] == ("https://github.com/kanoonhq/open-laws/blob/7222593/data/"
                               "indian_central_act_sections.parquet#A1909-7:2")
    assert (v["retrieved_at"], v["parser_version"]) == (FIXED_TIMESTAMP, built.manifest()["version"])
    assert (v["recorded_from"], v["recorded_to"], v["language"]) == ("v0.3.0", None, "en")


def point_in_time(rows: Rows, act_id: str, slug: str, day: str) -> Rows:
    """The PLAN §3 DuckDB query, without its LIMIT 1."""
    return [v for v in rows if v["act_id"] == act_id and v["slug"] == slug and v["valid_from"] <= day
            and (v["valid_to"] is None or v["valid_to"] > day) and v["recorded_to"] is None]


def test_point_in_time_query_returns_exactly_one_row_per_date(built_variant: BuildOutput) -> None:
    rows = built_variant.table(VERSIONS)
    for act_id, slug in {(v["act_id"], v["slug"]) for v in rows}:
        mine = [v for v in rows if (v["act_id"], v["slug"]) == (act_id, slug)]
        first = min(v["valid_from"] for v in mine)
        days = {first, "2000-08-15", "2099-01-01"}
        days |= {d for v in mine for d in (v["valid_from"], v["valid_to"]) if d}
        days |= {(date.fromisoformat(d) - timedelta(days=1)).isoformat() for d in set(days)}
        for day in sorted(d for d in days if d >= first):
            assert len(point_in_time(rows, act_id, slug, day)) == 1, (act_id, slug, day)
    assert point_in_time(rows, "A1860-45", "376", "2000-08-15")[0]["text_status"] == "reconstructed"


def test_manifest_counts_slices_by_text_status_and_status(built: BuildOutput) -> None:
    rows, coverage = built.table(VERSIONS), built.manifest()["coverage"]
    assert coverage["section_versions_sections"] == len(built.table("sections"))
    # 15 current slices, plus the 7 repealed slices (IPC 6, Evidence Act 1) that keep their wording.
    assert coverage["section_versions_by_text_status"] == {
        "verbatim_source": 15 + 7, "reconstructed": 1,  # A1909-7 s. 2
        "unavailable": 1}  # A1909-7 s. 1 before 2019-10-31
    assert coverage["section_versions_by_status"] == {
        "in_force": 17, "not_commenced": 0, "repealed": 7, "omitted": 0, "expired": 0,
        "struck_down": 0, "stayed": 0, "ordinance_lapsed": 0}
    assert len(rows) == 24


def test_section_of_an_act_without_any_date_gets_no_slice(tmp_path: Path) -> None:
    tables = load_fixture_rows()
    tables["acts"] = [{**a, "enactment_date": None} if a["act_id"] == "A1909-7" else a for a in tables["acts"]]
    output = build_fixtures(tmp_path, tables)
    assert slices(output, "A1909-7", "3") == []  # no assent date, no dated event
    assert [v["valid_from"] for v in slices(output, "A1909-7", "2")] == ["2013-11-01"]
    assert output.manifest()["coverage"]["section_versions_sections"] == len(output.table("sections")) - 4


def test_fixture_build_with_versions_passes_the_validator(built_variant: BuildOutput) -> None:
    result = run_validator(built_variant.dir)
    assert result.returncode == 0, result.stdout
    assert f"{VERSIONS} matches section_version.schema.json" in result.stdout


def test_validator_rejects_a_dropped_slice(built: BuildOutput, tmp_path: Path) -> None:
    result = run_validator(corrupt_output(built, tmp_path / "out", VERSIONS, lambda rows: rows[1:]).dir)
    assert result.returncode != 0
    assert "manifest coverage.section_versions_" in result.stdout
