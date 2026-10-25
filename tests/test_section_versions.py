"""indian_act_section_versions (ticket #15): bi-temporal section slices built
through the derived-table registry. The current slice is verbatim, valid only
from a date its wording can be shown to stand (assent_date for a clean
section, else the Act's latest amendment, else the source snapshot); earlier
slices are reverse-reconstructed only when every footnote is unambiguous,
else unavailable or `unknown`; judicial rulings and Act repeals split the chain."""

from __future__ import annotations

import hashlib
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
from conftest import (
    FIXED_TIMESTAMP,
    ROOT,
    BuildOutput,
    Rows,
    build_fixtures,
    corrupt_output,
    load_fixture_rows,
    run_build,
    run_validator,
    write_input_dir,
)

sys.path.insert(0, str(ROOT / "scripts"))
from enrich import section_versions  # noqa: E402

VERSIONS = "indian_act_section_versions.parquet"
AS_OF = FIXED_TIMESTAMP[:10]  # the build's export date: the source snapshot


def slices(output: BuildOutput, act_id: str, slug: str) -> list[dict]:
    rows = [v for v in output.table(VERSIONS) if (v["act_id"], v["slug"]) == (act_id, slug)]
    return sorted(rows, key=lambda v: v["version_number"])


def spans(output: BuildOutput, act_id: str, slug: str) -> list[tuple]:
    return [(v["valid_from"], v["valid_to"], v["status"], v["text_status"])
            for v in slices(output, act_id, slug)]


def drop_footnotes(tables: dict[str, Rows], *ids: str) -> dict[str, Rows]:
    tables["footnotes"] = [f for f in tables["footnotes"] if f["id"] not in ids]
    return tables


def anand_only(tables: dict[str, Rows]) -> dict[str, Rows]:
    """The fixtures with the Anand Marriage Act's only amendment the s. 2 insertion
    "3. Ins. by Act 29 of 2012, s. 2 (w.e.f. 1-11-2013)."."""
    return drop_footnotes(tables, "A1909-7:Page 2:0", "A1909-7:Page 2:1", "A1909-7:Page 2:3")


def retyped(tables: dict[str, Rows], footnote_id: str, **fields: object) -> dict[str, Rows]:
    tables["footnotes"] = [{**f, **fields} if f["id"] == footnote_id else f for f in tables["footnotes"]]
    return tables


def with_text(tables: dict[str, Rows], section_id: str, text: str) -> dict[str, Rows]:
    tables["sections"] = [{**s, "full_text": text} if s["id"] == section_id else s for s in tables["sections"]]
    return tables


# --- clean sections -------------------------------------------------------------


def test_clean_section_is_verbatim_from_assent(built: BuildOutput) -> None:
    # BSA s. 6: no inline markers, and the Act has no unlinked amendment.
    (v,) = slices(built, "A2023-47", "6")
    assert (v["valid_from"], v["valid_to"], v["status"], v["text_status"]) == (
        "2023-12-25", None, "in_force", "verbatim_source")
    assert (v["confidence"], v["amendment_event_ids"]) == (1.0, [])


def test_clean_section_of_an_act_without_assent_date_gets_no_slice(tmp_path: Path) -> None:
    tables = load_fixture_rows()
    tables["acts"] = [{**a, "enactment_date": None} if a["act_id"] == "A2023-47" else a for a in tables["acts"]]
    output = build_fixtures(tmp_path, tables)
    assert slices(output, "A2023-47", "6") == []
    assert output.manifest()["coverage"]["section_versions_sections"] == len(output.table("sections")) - 1


# --- sections that unlinked or other events may have changed --------------------


def test_unlinked_undated_event_asserts_text_only_from_the_snapshot(built: BuildOutput) -> None:
    # BNS s. 103 has no markers, but the BNS has an undated act_level footnote.
    assert spans(built, "A2023-45", "103") == [
        ("2023-12-25", AS_OF, "unknown", "unavailable"), (AS_OF, None, "in_force", "verbatim_source")]
    unknown = slices(built, "A2023-45", "103")[0]
    assert (unknown["full_text"], unknown["heading"], unknown["confidence"]) == (None, None, 0.0)


def test_marked_section_is_verbatim_from_the_acts_latest_event(built: BuildOutput) -> None:
    # Anand Marriage Act s. 3 has no event of its own, but the Act's latest
    # amendment (to s. 1, w.e.f. 31-10-2019) bounds every non-clean section.
    assert spans(built, "A1909-7", "3") == [
        ("1909-10-22", "2019-10-31", "unknown", "unavailable"),
        ("2019-10-31", None, "in_force", "verbatim_source")]


def test_unlinked_event_on_the_same_date_blocks_reconstruction(built: BuildOutput) -> None:
    # s. 2's insertion (w.e.f. 1-11-2013) shares its date with an act_level
    # footnote, and the Act was amended again in 2019: no wording before 2019.
    assert spans(built, "A1909-7", "2") == [
        ("1909-10-22", "2019-10-31", "unknown", "unavailable"),
        ("2019-10-31", None, "in_force", "verbatim_source")]


def test_undated_events_of_a_repealed_act_bound_it_at_repeal(built: BuildOutput) -> None:
    # The IPC has undated amendments; its text cannot change after repeal, so
    # the verbatim text stands from 2024-07-01 and nothing before is asserted.
    for slug in ("1", "302"):
        assert spans(built, "A1860-45", slug) == [
            ("1860-10-06", "2024-07-01", "unknown", "unavailable"),
            ("2024-07-01", None, "repealed", "verbatim_source")]


def test_an_undated_event_on_the_section_stops_the_chain(tmp_path: Path) -> None:
    # A clean Act whose only amendment is undated: no date is assumed for it.
    tables = retyped(anand_only(load_fixture_rows()), "A1909-7:Page 2:2", wef_date=None,
                     raw_text="3. Ins. by Act 29 of 2012, s. 2.")
    assert spans(build_fixtures(tmp_path, tables), "A1909-7", "2") == [
        ("1909-10-22", AS_OF, "unknown", "unavailable"), (AS_OF, None, "in_force", "verbatim_source")]


# --- reverse reconstruction ------------------------------------------------------


@pytest.fixture(scope="module")
def built_anand(tmp_path_factory: pytest.TempPathFactory) -> BuildOutput:
    return build_fixtures(tmp_path_factory.mktemp("anand"), anand_only(load_fixture_rows()))


def test_insertion_is_reversed_in_the_earlier_slice(built_anand: BuildOutput) -> None:
    # Anand Marriage Act s. 2: "Anand 3[(commonly known as Anand Karaj)] shall be, ..."
    before, current = slices(built_anand, "A1909-7", "2")
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


def test_omission_is_restored_from_the_quoted_words(tmp_path: Path) -> None:
    # Anand Marriage Act s. 1 "(2) Its extends to the whole of India 2***." with
    # "2. The words “except the State of Jammu and Kashmir” omitted by Act 34 of
    # 2019 ... (w.e.f. 31-10- 2019)", which v0.1.1 typed `other`; typed omission:
    tables = retyped(load_fixture_rows(), "A1909-7:Page 2:1", amendment_type="omission")
    output = build_fixtures(tmp_path, tables)
    unknown, before, current = slices(output, "A1909-7", "1")
    assert before["full_text"].endswith(
        "(2) Its extends to the whole of India except the State of Jammu and Kashmir.")
    # From the Act's previous amendment date (w.e.f. 1-11-2013) only.
    assert (before["text_status"], before["valid_from"], before["valid_to"]) == (
        "reconstructed", "2013-11-01", "2019-10-31")
    assert (unknown["valid_from"], unknown["status"]) == ("1909-10-22", "unknown")
    assert current["full_text"].endswith("the whole of India 2***.")


def test_operation_disagreeing_with_the_marker_is_unavailable(built: BuildOutput) -> None:
    # The same omission as v0.1.1 typed it (`other`): not reversible.
    assert spans(built, "A1909-7", "1") == [
        ("1909-10-22", "2019-10-31", "unknown", "unavailable"),
        ("2019-10-31", None, "in_force", "verbatim_source")]


def test_insertion_footnote_quoting_old_words_is_unavailable(tmp_path: Path) -> None:
    # v0.1.1 typed some substitutions `insertion`; the quoted words then disagree with `N[`.
    tables = retyped(anand_only(load_fixture_rows()), "A1909-7:Page 2:2",
                     raw_text="3. Subs. by Act 29 of 2012, s. 2, for “(Anand)” (w.e.f. 1-11-2013).")
    before, _ = slices(build_fixtures(tmp_path, tables), "A1909-7", "2")
    assert (before["text_status"], before["full_text"]) == ("unavailable", None)


def test_nested_brackets_stay_unavailable(tmp_path: Path) -> None:
    tables = anand_only(load_fixture_rows())
    text = next(s["full_text"] for s in tables["sections"] if s["id"] == "A1909-7:2")
    tables = with_text(tables, "A1909-7:2", text.replace("Anand 3[(commonly known as Anand Karaj)]",
                                                         "Anand 3[(commonly known as [Anand Karaj])]"))
    before, current = slices(build_fixtures(tmp_path, tables), "A1909-7", "2")
    assert (before["text_status"], before["full_text"]) == ("unavailable", None)
    assert current["text_status"] == "verbatim_source"


def test_reversal_leaves_no_stray_whitespace(tmp_path: Path) -> None:
    tables = with_text(anand_only(load_fixture_rows()), "A1909-7:2",
                       "called Anand 3[(commonly known as Anand Karaj)]\n")
    tables = retyped(tables, "A1909-7:Page 2:2", amendment_type="substitution",
                     raw_text="3. Subs. by Act 29 of 2012, s. 2, for “, Karaj” (w.e.f. 1-11-2013).")
    before, _ = slices(build_fixtures(tmp_path / "subs", tables), "A1909-7", "2")
    assert before["full_text"] == "called Anand, Karaj\n"  # no space left before the comma
    tables = retyped(tables, "A1909-7:Page 2:2", amendment_type="insertion",
                     raw_text="3. Ins. by Act 29 of 2012, s. 2 (w.e.f. 1-11-2013).")
    before, _ = slices(build_fixtures(tmp_path / "ins", tables), "A1909-7", "2")
    assert before["full_text"] == "called Anand"  # no trailing space or line


# --- IPC / IT Act variant ----------------------------------------------------------

IPC_376 = ("(1) Whoever, except in the cases provided for in sub-section (2), commits rape, shall be "
           "punished with rigorous imprisonment of either description for a term which 2[shall not be "
           "less than ten years, but which may extend to imprisonment for life, and shall also be liable "
           "to fine].")
IPC_124A = ("Whoever by words, either spoken or written, or by signs, or by visible representation, or "
            "otherwise, brings or attempts to bring into hatred or contempt, or excites or attempts to "
            "excite disaffection towards, the Government established by law in India, shall be punished "
            "with imprisonment for life, to which fine may be added, or with imprisonment which may "
            "extend to three years, to which fine may be added, or with fine.")
# s. 66A as India Code prints it: the marker of the 2009 insertion sits before
# the section, so only its closing bracket is in the text.
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
    """The fixtures with the IPC's (undated) footnote pages replaced by two
    dated substitutions (s. 302, 1956; s. 376, 2013, synthetic, modelled on the
    real 2018 footnote), IPC ss. 124A and 376 added, and a stub Information
    Technology Act, 2000 with s. 66A and no footnotes."""
    tables = load_fixture_rows()
    s0, f0 = tables["sections"][0], tables["footnotes"][0]
    it_act = {**tables["acts"][0], "act_id": "A2000-21", "act_number": "ACT NO. 21 OF 2000",
              "title": "THE INFORMATION TECHNOLOGY ACT, 2000", "enactment_date": "[9th June, 2000.]",
              "is_repealed": False, "repealed_by": None, "repeal_reason": None,
              "section_count": 1, "footnote_count": 0}
    ipc = next(a for a in tables["acts"] if a["act_id"] == "A1860-45")
    ipc["section_count"] += 2
    tables["footnotes"] = [f for f in tables["footnotes"] if f["act_id"] != "A1860-45"]
    ipc["footnote_count"] = 2
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


def test_ipc_376_pre_2013_slice_is_reconstructed_from_the_quoted_text(built_variant: BuildOutput) -> None:
    unknown, before, current, repealed = slices(built_variant, "A1860-45", "376")
    assert [(v["valid_from"], v["valid_to"]) for v in (unknown, before, current, repealed)] == [
        ("1860-10-06", "1956-01-01"), ("1956-01-01", "2013-02-03"), ("2013-02-03", "2024-07-01"),
        ("2024-07-01", None)]
    assert (unknown["status"], unknown["text_status"]) == ("unknown", "unavailable")
    assert before["text_status"] == "reconstructed"
    assert before["full_text"].endswith(
        "for a term which shall not be less than seven years, but which may extend to imprisonment for "
        "life, and shall also be liable to fine.")
    assert current["id"] == "A1860-45:376:2013-02-03"
    assert current["amendment_citation"] == "Act 13 of 2013, s. 9"
    assert current["change_summary"] == "Substituted by Act 13 of 2013, s. 9"
    assert current["text_status"] == "verbatim_source"


def test_another_sections_later_amendment_bounds_the_verbatim_slice(built_variant: BuildOutput) -> None:
    # s. 302's own 1956 substitution is reversible, but the IPC was amended
    # again in 2013 (s. 376): its wording is asserted from 2013-02-03 only.
    assert spans(built_variant, "A1860-45", "302") == [
        ("1860-10-06", "2013-02-03", "unknown", "unavailable"),
        ("2013-02-03", "2024-07-01", "in_force", "verbatim_source"),
        ("2024-07-01", None, "repealed", "verbatim_source")]


def test_ipc_gets_a_repealed_slice_from_2024_07_01(built: BuildOutput) -> None:
    *_, last = slices(built, "A1860-45", "302")
    assert (last["valid_from"], last["valid_to"], last["status"]) == ("2024-07-01", None, "repealed")
    assert last["amendment_event_ids"] == ["A1860-45:ev:A2023-45:repeal"]
    assert last["amended_by_act_id"] == "A2023-45"


def test_66a_shows_no_verbatim_text_before_its_insertion(built_variant: BuildOutput) -> None:
    # The unmatched `]` shows s. 66A was inserted by an amendment the stub Act
    # does not record: nothing is asserted before the snapshot, and the ruling
    # still marks it struck down from 2015-03-24.
    assert spans(built_variant, "A2000-21", "66a") == [
        ("2000-06-09", "2015-03-24", "unknown", "unavailable"),
        ("2015-03-24", AS_OF, "struck_down", "unavailable"),
        (AS_OF, None, "struck_down", "verbatim_source")]
    _, struck, current = slices(built_variant, "A2000-21", "66a")
    assert struck["amendment_event_ids"] == ["A2000-21:je:66a:2015-03-24"]
    assert struck["change_summary"] == "Struck down: Shreya Singhal v. Union of India, Supreme Court of India"
    assert (struck["full_text"], current["full_text"]) == (None, IT_66A)


def test_66a_verbatim_slice_after_the_ruling_stays_struck_down(built_variant: BuildOutput) -> None:
    after = [v for v in slices(built_variant, "A2000-21", "66a") if v["valid_from"] >= "2015-03-24"]
    assert len(after) == 2
    assert all(v["status"] == "struck_down" for v in after)
    assert after[-1]["text_status"] == "verbatim_source"


def ruling(effect: str, day: str) -> tuple[str, str, dict]:
    status = {"struck_down": "struck_down", "stayed": "stayed", "stay_lifted": "in_force"}[effect]
    return day, status, {"id": f"A1860-45:je:124a:{day}", "effect": effect, "case_name": "X", "court": "Y"}


def statuses(changes: list[tuple[str, str, dict]]) -> list[tuple[str, str]]:
    """Status timeline of a chain [1860 unknown, 2013 in_force, 2023 in_force]
    (a text boundary after the rulings) under the given rulings."""
    chain = [section_versions.unknown("1860-10-06"),
             section_versions.verbatim("old", "2013-02-03"), section_versions.verbatim("new", "2023-01-01")]
    return [(s.valid_from, s.status) for s in section_versions.with_status(chain, changes)]


def test_a_stay_persists_across_later_text_slices_until_lifted() -> None:
    assert statuses([ruling("stayed", "2022-05-11")]) == [
        ("1860-10-06", "unknown"), ("2013-02-03", "in_force"), ("2022-05-11", "stayed"),
        ("2023-01-01", "stayed")]
    assert statuses([ruling("stayed", "2022-05-11"), ruling("stay_lifted", "2023-06-01")]) == [
        ("1860-10-06", "unknown"), ("2013-02-03", "in_force"), ("2022-05-11", "stayed"),
        ("2023-01-01", "stayed"), ("2023-06-01", "in_force")]


def test_a_strike_down_never_lifts() -> None:
    assert statuses([ruling("struck_down", "2015-03-24"), ruling("stay_lifted", "2016-01-01")]) == [
        ("1860-10-06", "unknown"), ("2013-02-03", "in_force"), ("2015-03-24", "struck_down"),
        ("2016-01-01", "struck_down"), ("2023-01-01", "struck_down")]


def test_as_of_comes_from_the_build_timestamp(tmp_path: Path) -> None:
    # Same inputs, another --timestamp: the snapshot bound follows it (no clock).
    input_dir = write_input_dir(load_fixture_rows(), tmp_path / "in")
    run_build(input_dir, tmp_path / "out", timestamp="2030-05-06T00:00:00+00:00")
    assert spans(BuildOutput(tmp_path / "out"), "A2023-45", "103")[-1][:2] == ("2030-05-06", None)


def test_124a_is_stayed_from_2022_05_11_until_repeal(built_variant: BuildOutput) -> None:
    # Clean here: no markers, and every IPC amendment in the variant is linked.
    assert spans(built_variant, "A1860-45", "124a") == [
        ("1860-10-06", "2022-05-11", "in_force", "verbatim_source"),
        ("2022-05-11", "2024-07-01", "stayed", "verbatim_source"),
        ("2024-07-01", None, "repealed", "verbatim_source")]


# --- table-wide ----------------------------------------------------------------------


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


@pytest.mark.parametrize("which", ["built", "built_variant", "built_anand"])
def test_point_in_time_query_returns_exactly_one_row_per_date(which: str, request: pytest.FixtureRequest) -> None:
    rows = request.getfixturevalue(which).table(VERSIONS)
    for act_id, slug in {(v["act_id"], v["slug"]) for v in rows}:
        mine = [v for v in rows if (v["act_id"], v["slug"]) == (act_id, slug)]
        first = min(v["valid_from"] for v in mine)
        days = {first, "2000-08-15", "2099-01-01"}
        days |= {d for v in mine for d in (v["valid_from"], v["valid_to"]) if d}
        days |= {(date.fromisoformat(d) - timedelta(days=1)).isoformat() for d in set(days)}
        for day in sorted(d for d in days if d >= first):
            assert len(point_in_time(rows, act_id, slug, day)) == 1, (act_id, slug, day)


def test_point_in_time_query_on_ipc_376(built_variant: BuildOutput) -> None:
    rows = built_variant.table(VERSIONS)
    assert point_in_time(rows, "A1860-45", "376", "2000-08-15")[0]["text_status"] == "reconstructed"
    assert point_in_time(rows, "A1860-45", "376", "1950-01-01")[0]["status"] == "unknown"


def test_manifest_counts_slices_by_text_status_and_status(built: BuildOutput) -> None:
    rows, coverage = built.table(VERSIONS), built.manifest()["coverage"]
    assert coverage["section_versions_sections"] == len(built.table("sections")) == 15
    # Anand 6 x (unknown + verbatim), IPC 6 x (unknown + repealed verbatim),
    # Evidence s. 8 (clean: verbatim + repealed verbatim), BNS s. 103 (unknown +
    # verbatim), BSA s. 6 (clean: verbatim).
    assert len(rows) == 12 + 12 + 2 + 2 + 1
    assert coverage["section_versions_by_text_status"] == {
        "verbatim_source": 16, "reconstructed": 0, "unavailable": 13}
    assert coverage["section_versions_by_status"] == {
        "in_force": 9, "not_commenced": 0, "repealed": 7, "omitted": 0, "expired": 0,
        "struck_down": 0, "stayed": 0, "ordinance_lapsed": 0, "unknown": 13}


def test_fixture_build_with_versions_passes_the_validator(built_variant: BuildOutput) -> None:
    result = run_validator(built_variant.dir)
    assert result.returncode == 0, result.stdout
    assert f"{VERSIONS} matches section_version.schema.json" in result.stdout


def test_validator_rejects_a_dropped_slice(built: BuildOutput, tmp_path: Path) -> None:
    result = run_validator(corrupt_output(built, tmp_path / "out", VERSIONS, lambda rows: rows[1:]).dir)
    assert result.returncode != 0
    assert "manifest coverage.section_versions_" in result.stdout
