"""Mapping transition rules: effective_from and applies_by (spec #1, ticket #5)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from conftest import (
    BuildOutput,
    build_fixtures,
    corrupt_output,
    load_fixture_rows,
    run_validator,
)


def mappings_by_new_act(built: BuildOutput) -> dict[str, dict]:
    return {m["new_act_id"]: m for m in built.table("mappings")}


def test_bns_mapping_applies_by_offence_date_from_1_july_2024(built: BuildOutput) -> None:
    bns = mappings_by_new_act(built)["A2023-45"]
    assert bns["effective_from"] == "2024-07-01"
    assert bns["applies_by"] == "offence_date"


def test_bsa_mapping_applies_by_proceeding_date(built: BuildOutput) -> None:
    bsa = mappings_by_new_act(built)["A2023-47"]
    assert bsa["effective_from"] == "2024-07-01"
    assert bsa["applies_by"] == "proceeding_date"


def with_mapping_to(new_act_id: str) -> dict[str, list[dict]]:
    """The fixtures plus a mapping into new_act_id, cloned from the BSA rows."""
    tables = load_fixture_rows()
    bsa_act = next(a for a in tables["acts"] if a["act_id"] == "A2023-47")
    bsa_section = next(s for s in tables["sections"] if s["act_id"] == "A2023-47")
    bsa_mapping = next(m for m in tables["mappings"] if m["new_act_id"] == "A2023-47")
    tables["acts"].append({**bsa_act, "act_id": new_act_id, "source_file": f"{new_act_id}.json"})
    tables["sections"].append(
        {**bsa_section, "act_id": new_act_id, "id": f"{new_act_id}:{bsa_section['section_number']}"}
    )
    tables["mappings"].append({**bsa_mapping, "new_act_id": new_act_id})
    return tables


def test_bnss_mapping_applies_by_proceeding_date(tmp_path: Path) -> None:
    built = build_fixtures(tmp_path, with_mapping_to("A2023-46"))
    bnss = mappings_by_new_act(built)["A2023-46"]
    assert bnss["effective_from"] == "2024-07-01"
    assert bnss["applies_by"] == "proceeding_date"


def test_build_refuses_a_mapping_into_an_act_with_no_transition_rule(tmp_path: Path) -> None:
    with pytest.raises(subprocess.CalledProcessError) as failure:
        build_fixtures(tmp_path, with_mapping_to("A2023-99"))
    assert "A2023-99" in failure.value.stderr


@pytest.mark.parametrize(
    ("column", "bad_value"),
    [
        ("applies_by", "judgment_date"),
        ("applies_by", None),
        ("effective_from", "1-7-2024"),
        ("effective_from", None),
    ],
)
def test_validator_rejects_malformed_transition_fields(
    built: BuildOutput, tmp_path: Path, column: str, bad_value: str | None
) -> None:
    def break_first_mapping(rows: list[dict]) -> list[dict]:
        return [{**rows[0], column: bad_value}, *rows[1:]]

    broken = corrupt_output(built, tmp_path / "out", "mappings", break_first_mapping)
    result = run_validator(broken.dir)
    assert result.returncode != 0
    assert column in result.stdout or str(bad_value) in result.stdout
