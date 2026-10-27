"""amendment_events (ticket #11): one event per amending footnote plus one per
Act repeal, built through the derived-table registry and checked by validate.py."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from conftest import BuildOutput, Rows, build_fixtures, corrupt_output, load_fixture_rows, run_validator

EVENTS = "amendment_events.parquet"


def events_by_footnote(output: BuildOutput) -> dict[str, dict]:
    return {e["footnote_ids"][0]: e for e in output.table(EVENTS) if e["footnote_ids"]}


def test_build_writes_one_event_per_footnote_and_per_repeal(built: BuildOutput) -> None:
    events = built.table(EVENTS)
    footnote_events = [e for e in events if e["operation"] != "repeal"]
    assert [e["footnote_ids"] for e in footnote_events] == [[f["id"]] for f in built.table("footnotes")]
    assert sorted(e["act_id"] for e in events if e["operation"] == "repeal") == ["A1860-45", "A1872-1"]
    assert built.manifest()["files"][EVENTS]["rows"] == 22 + 2


def test_fixture_build_with_events_passes_the_validator(built: BuildOutput) -> None:
    result = run_validator(built.dir)
    assert result.returncode == 0, result.stdout
    assert f"{EVENTS} matches amendment_event.schema.json" in result.stdout


def test_substitution_quoting_the_replaced_words(built: BuildOutput) -> None:
    # "1. Subs. by Act 36 of 1957, s. 3 and Schedule II, for “lllustrations”" (no w.e.f.)
    e = events_by_footnote(built)["A1860-45:Page 15:0"]
    assert (e["operation"], e["old_text"], e["provisions_affected"]) == ("substitution", "lllustrations", ["4"])
    assert (e["amending_citation"], e["amending_instrument_id"]) == ("Act 36 of 1957, s. 3", None)
    assert e["id"] == "A1860-45:ev:act-36-of-1957:s3"
    assert e["wef_date"] is None  # undated: no date is assumed


def test_insertion(built: BuildOutput) -> None:
    # "3. Ins. by Act 29 of 2012, s. 2 (w.e.f. 1-11-2013)."
    e = events_by_footnote(built)["A1909-7:Page 2:2"]
    assert (e["operation"], e["old_text"], e["provisions_affected"]) == ("insertion", None, ["2"])
    assert (e["wef_date"], e["id"]) == ("2013-11-01", "A1909-7:ev:act-29-of-2012:s2")


def test_omission_quoting_the_omitted_words(built: BuildOutput) -> None:
    # "4. The words “except the State of Jammu and Kashmir” omitted by Act 34 of 2019, s. 95 ..."
    e = events_by_footnote(built)["A1860-45:Page 14:3"]
    assert (e["operation"], e["provisions_affected"]) == ("omission", ["1"])
    assert e["old_text"] == "except the State of Jammu and Kashmir"
    assert (e["wef_date"], e["amending_citation"]) == ("2019-10-31", "Act 34 of 2019, s. 95")


def test_act_level_footnote_keeps_its_event(built: BuildOutput) -> None:
    # The IPC's extension footnote cites no amending Act and links to no section.
    e = events_by_footnote(built)["A1860-45:Page 14:0"]
    assert (e["operation"], e["provisions_affected"]) == ("extension", [])
    assert (e["amending_citation"], e["amending_instrument_id"]) == (None, None)
    assert e["id"] == "A1860-45:ev:uncited:fn-page-14-1"


def test_quoted_words_not_being_replaced_give_no_old_text(built: BuildOutput) -> None:
    # "The words “British India” have successively been subs. by the A.O. 1948, ..."
    assert events_by_footnote(built)["A1860-45:Page 14:1"]["old_text"] is None


def test_old_text_is_kept_for_a_single_quoted_replacement(built: BuildOutput) -> None:
    # "7. Subs. by the A.O. 1937, for “law passed by the Governor General of India in Council”."
    e = events_by_footnote(built)["A1860-45:Page 14:6"]
    assert e["old_text"] == "law passed by the Governor General of India in Council"


def test_repeal_event_from_the_act_repeal_fields(built: BuildOutput) -> None:
    repeals = {e["act_id"]: e for e in built.table(EVENTS) if e["operation"] == "repeal"}
    ipc = repeals["A1860-45"]
    assert ipc["id"] == "A1860-45:ev:A2023-45:repeal"
    assert (ipc["amending_instrument_id"], ipc["amending_citation"]) == ("A2023-45", "Act 45 of 2023")
    assert (ipc["wef_date"], ipc["assent_date"]) == ("2024-07-01", "2023-12-25")
    assert (ipc["provisions_affected"], ipc["footnote_ids"], ipc["old_text"]) == ([], [], None)
    assert repeals["A1872-1"]["amending_instrument_id"] == "A2023-47"


def test_dates_without_gazette_sources_stay_null(built: BuildOutput) -> None:
    for e in built.table(EVENTS):
        assert (e["publication_date"], e["commencement_date"], e["commencement_notification_id"]) == \
            (None, None, None)
        assert e["is_retrospective"] is None  # needs both wef_date and publication_date


def test_event_ids_are_unique_with_a_suffix_on_collision(built: BuildOutput) -> None:
    # Footnotes 3 and 6 on IPC Page 14 both cite "Act 12 of 1891, s. 2".
    by_footnote = events_by_footnote(built)
    assert by_footnote["A1860-45:Page 14:2"]["id"] == "A1860-45:ev:act-12-of-1891:s2"
    assert by_footnote["A1860-45:Page 14:5"]["id"] == "A1860-45:ev:act-12-of-1891:s2-2"
    ids = [e["id"] for e in built.table(EVENTS)]
    assert len(ids) == len(set(ids))


def with_amending_act(tables: dict[str, Rows]) -> dict[str, Rows]:
    """The fixtures plus a stub Act 34 of 2019 (the J&K Reorganisation Act)."""
    stub = {**tables["acts"][0], "act_id": "A2019-34", "act_number": "ACT NO. 34 OF 2019",
            "title": "THE JAMMU AND KASHMIR REORGANISATION ACT, 2019",
            "enactment_date": "[9th August, 2019.]", "section_count": 0, "footnote_count": 0}
    return {**tables, "acts": [*tables["acts"], stub]}


def test_amending_instrument_resolves_to_a_known_act(tmp_path: Path) -> None:
    output = build_fixtures(tmp_path, with_amending_act(load_fixture_rows()))
    e = events_by_footnote(output)["A1860-45:Page 14:3"]
    assert (e["amending_instrument_id"], e["assent_date"]) == ("A2019-34", "2019-08-09")
    assert e["id"] == "A1860-45:ev:A2019-34:s95"
    # Citations spaced as printed ("Act  34  of  2019") resolve the same way.
    assert events_by_footnote(output)["A1909-7:Page 2:1"]["amending_instrument_id"] == "A2019-34"
    assert run_validator(output.dir).returncode == 0


@pytest.mark.parametrize("raw_text", [
    "7. Subs. by Act 5 of 2005, s. 2, for “the words” and “the figures”.",  # multiple
    "7. Subs. by Act 5 of 2005, s. 2, for “the ‘said’ words”.",  # nested
    "7. Subs. by Act 5 of 2005, s. 2, for “the said words.",  # unbalanced
])
def test_nested_or_multiple_quotes_give_no_old_text(tmp_path: Path, raw_text: str) -> None:
    tables = load_fixture_rows()
    tables["footnotes"] = [{**f, "raw_text": raw_text} if f["id"] == "A1860-45:Page 14:6" else f
                           for f in tables["footnotes"]]
    e = events_by_footnote(build_fixtures(tmp_path, tables))["A1860-45:Page 14:6"]
    assert (e["amending_citation"], e["old_text"]) == ("Act 5 of 2005, s. 2", None)


def test_manifest_counts_events_by_operation(built: BuildOutput) -> None:
    assert built.manifest()["coverage"]["amendment_events_by_operation"] == {
        "substitution": 5, "insertion": 3, "omission": 3, "renumbering": 0,
        "extension": 1, "repeal": 2, "other": 10}


def test_validator_rejects_an_unknown_operation(built: BuildOutput, tmp_path: Path) -> None:
    def corrupt(rows: Rows) -> Rows:
        return [{**rows[0], "operation": "amended"}, *rows[1:]]

    result = run_validator(corrupt_output(built, tmp_path / "out", EVENTS, corrupt).dir)
    assert result.returncode != 0
    assert "'amended' is not one of" in result.stdout


def test_validator_rejects_tampered_event_coverage(built: BuildOutput, tmp_path: Path) -> None:
    shutil.copytree(built.dir, tmp_path / "out")
    manifest_path = tmp_path / "out" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["coverage"]["amendment_events_by_operation"]["repeal"] = 3
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    result = run_validator(tmp_path / "out")
    assert result.returncode != 0
    assert "manifest coverage.amendment_events_by_operation" in result.stdout
