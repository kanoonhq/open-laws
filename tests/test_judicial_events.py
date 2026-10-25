"""judicial_events (ticket #14): the four PROCUREMENT_PLAN §2.2 Table 4 seed
rulings from curated/judicial_events.json, resolved against the acts table,
built through the derived-table registry and checked by validate.py."""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import BuildOutput, Rows, build_fixtures, corrupt_output, load_fixture_rows, run_validator

JUDICIAL = "judicial_events.parquet"


def by_id(output: BuildOutput) -> dict[str, dict]:
    return {e["id"]: e for e in output.table(JUDICIAL)}


def with_it_act(tables: dict[str, Rows]) -> dict[str, Rows]:
    """The fixtures plus a stub Information Technology Act, 2000 (Act 21 of 2000)."""
    stub = {**tables["acts"][0], "act_id": "A2000-21", "act_number": "ACT NO. 21 OF 2000",
            "title": "THE INFORMATION TECHNOLOGY ACT, 2000",
            "enactment_date": "[9th June, 2000.]", "section_count": 0, "footnote_count": 0}
    return {**tables, "acts": [*tables["acts"], stub]}


@pytest.fixture(scope="module")
def built_with_it_act(tmp_path_factory: pytest.TempPathFactory) -> BuildOutput:
    return build_fixtures(tmp_path_factory.mktemp("it"), with_it_act(load_fixture_rows()))


def test_all_four_seed_rulings_with_deterministic_ids(built_with_it_act: BuildOutput) -> None:
    assert sorted(by_id(built_with_it_act)) == [
        "A1860-45:je:124a:2022-05-11",
        "A1860-45:je:377:2018-09-06",
        "A1860-45:je:497:2018-09-27",
        "A2000-21:je:66a:2015-03-24",
    ]
    assert built_with_it_act.manifest()["files"][JUDICIAL]["rows"] == 4


def test_rows_carry_case_court_date_effect_and_source(built_with_it_act: BuildOutput) -> None:
    e = by_id(built_with_it_act)["A2000-21:je:66a:2015-03-24"]
    assert (e["act_id"], e["provision_path"], e["effect"]) == ("A2000-21", "66a", "struck_down")
    assert (e["case_name"], e["court"]) == ("Shreya Singhal v. Union of India", "Supreme Court of India")
    assert (e["neutral_citation"], e["reported_citation"]) == (None, "(2015) 5 SCC 1")
    assert e["source_url"] == "https://indiankanoon.org/doc/110813550/"


@pytest.mark.parametrize(("event_id", "case_name", "effect"), [
    ("A1860-45:je:377:2018-09-06", "Navtej Singh Johar v. Union of India", "read_down"),
    ("A1860-45:je:497:2018-09-27", "Joseph Shine v. Union of India", "struck_down"),
    ("A1860-45:je:124a:2022-05-11", "S.G. Vombatkere v. Union of India", "stayed"),
])
def test_ipc_rulings_and_their_effects(built: BuildOutput, event_id: str, case_name: str, effect: str) -> None:
    e = by_id(built)[event_id]
    assert (e["act_id"], e["case_name"], e["effect"]) == ("A1860-45", case_name, effect)


def test_every_ruling_has_a_source_url(built_with_it_act: BuildOutput) -> None:
    assert all(e["source_url"].startswith("https://") for e in built_with_it_act.table(JUDICIAL))


def test_ruling_on_an_act_missing_from_the_corpus_is_left_out(built: BuildOutput) -> None:
    # The fixtures have the IPC but not the IT Act: no act_id is guessed for s. 66A.
    assert all(e["act_id"] == "A1860-45" for e in built.table(JUDICIAL))
    coverage = built.manifest()["coverage"]
    assert coverage["judicial_events_unresolved_act"] == ["Act 21 of 2000, s. 66a (2015-03-24)"]


def test_manifest_counts_rulings_by_effect(built_with_it_act: BuildOutput) -> None:
    coverage = built_with_it_act.manifest()["coverage"]
    assert coverage["judicial_events_by_effect"] == {
        "struck_down": 2, "read_down": 1, "stayed": 1, "stay_lifted": 0, "upheld": 0}
    assert coverage["judicial_events_unresolved_act"] == []


def test_fixture_build_with_judicial_events_passes_the_validator(built_with_it_act: BuildOutput) -> None:
    result = run_validator(built_with_it_act.dir)
    assert result.returncode == 0, result.stdout
    assert f"{JUDICIAL} matches judicial_event.schema.json" in result.stdout


def test_validator_rejects_an_unknown_effect(built: BuildOutput, tmp_path: Path) -> None:
    def corrupt(rows: Rows) -> Rows:
        return [{**rows[0], "effect": "overruled"}, *rows[1:]]

    result = run_validator(corrupt_output(built, tmp_path / "out", JUDICIAL, corrupt).dir)
    assert result.returncode != 0
    assert "'overruled' is not one of" in result.stdout


def test_validator_rejects_a_dropped_ruling(built: BuildOutput, tmp_path: Path) -> None:
    def drop_one(rows: Rows) -> Rows:
        return rows[1:]

    result = run_validator(corrupt_output(built, tmp_path / "out", JUDICIAL, drop_one).dir)
    assert result.returncode != 0
    assert "manifest coverage.judicial_events_by_effect" in result.stdout
