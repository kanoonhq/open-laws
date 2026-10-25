"""Act-level dates and repeal fields: assent, commencement, repeal date, savings clause."""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import BuildOutput, build_fixtures, corrupt_output, load_fixture_rows, run_validator


def acts_by_id(output: BuildOutput) -> dict[str, dict]:
    return {a["act_id"]: a for a in output.table("acts")}


def test_assent_date_is_parsed_from_enactment_date(built: BuildOutput) -> None:
    acts = acts_by_id(built)
    assert acts["A1860-45"]["assent_date"] == "1860-10-06"
    assert acts["A1909-7"]["assent_date"] == "1909-10-22"
    assert acts["A2023-45"]["assent_date"] == "2023-12-25"
    assert acts["A1860-45"]["enactment_date"] == "[6th October, 1860.]"


def test_repealed_acts_get_repeal_date_and_savings_clause(built: BuildOutput) -> None:
    acts = acts_by_id(built)
    ipc, iea = acts["A1860-45"], acts["A1872-1"]
    assert (ipc["repeal_date"], ipc["savings_clause"]) == ("2024-07-01", "BNS s. 358")
    assert (iea["repeal_date"], iea["savings_clause"]) == ("2024-07-01", "BSA s. 170")
    # The v0.1.1 repeal columns are carried through unchanged.
    assert (ipc["is_repealed"], ipc["repealed_by"], ipc["category"]) == (True, "A2023-45", "criminal")
    assert ipc["repeal_reason"].startswith("Repealed and replaced by Bharatiya Nyaya Sanhita")


def test_acts_in_force_have_null_repeal_fields_and_commencement(built: BuildOutput) -> None:
    acts = acts_by_id(built)
    for act_id in ("A1909-7", "A2023-45", "A2023-47"):
        assert (acts[act_id]["repeal_date"], acts[act_id]["savings_clause"]) == (None, None)
    assert {a["commencement_date"] for a in acts.values()} == {None}


@pytest.mark.parametrize(
    ("column", "bad_value"),
    [("assent_date", "6th October, 1860"), ("repeal_date", "01-07-2024"),
     ("commencement_date", "1860")],
)
def test_validator_rejects_malformed_date_fields(
    built: BuildOutput, tmp_path: Path, column: str, bad_value: str
) -> None:
    def break_ipc(rows: list[dict]) -> list[dict]:
        return [{**r, column: bad_value} if r["act_id"] == "A1860-45" else r for r in rows]

    broken = corrupt_output(built, tmp_path / "out", "acts", break_ipc)
    result = run_validator(broken.dir)
    assert result.returncode != 0
    assert column in result.stdout or bad_value in result.stdout


def build_with_enactment_dates(tmp: Path, dates: dict[str, str]) -> BuildOutput:
    tables = load_fixture_rows()
    tables["acts"] = [
        {**a, "enactment_date": dates.get(a["act_id"], a["enactment_date"])} for a in tables["acts"]
    ]
    return build_fixtures(tmp, tables)


def test_assent_date_tolerates_irregular_spacing_and_commas(tmp_path: Path) -> None:
    # Shapes seen in v0.1.1: no space after the ordinal, a comma after the day.
    output = build_with_enactment_dates(tmp_path, {
        "A1909-7": "[22ndMay,1993.]",
        "A1872-1": "[14th, September, 2001.]",
        "A2023-47": "[7th March,1913.]",
    })
    acts = acts_by_id(output)
    assert acts["A1909-7"]["assent_date"] == "1993-05-22"
    assert acts["A1872-1"]["assent_date"] == "2001-09-14"
    assert acts["A2023-47"]["assent_date"] == "1913-03-07"


def test_unparseable_enactment_date_gives_null_assent_date(tmp_path: Path) -> None:
    output = build_with_enactment_dates(tmp_path, {
        "A1909-7": "[Date not available.]",
        "A1872-1": "[31st February, 1900.]",
        "A2023-47": "[Smarch 3rd, 1999.]",
    })
    acts = acts_by_id(output)
    assert [acts[i]["assent_date"] for i in ("A1909-7", "A1872-1", "A2023-47")] == [None] * 3
    assert acts["A1909-7"]["enactment_date"] == "[Date not available.]"
    assert output.manifest()["coverage"]["acts_with_assent_date"] == 2
    assert run_validator(output.dir).returncode == 0
