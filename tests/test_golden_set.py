"""The golden set file format (spec #10 Out of Scope: "This spec only adds the
file format"; PROCUREMENT_PLAN §7.5): hand-verified (provision, date) -> text
pairs, one JSON array of schemas/golden_pair.schema.json objects. No golden
data ships yet; tests/fixtures/golden_set/example.json is a format example."""

from __future__ import annotations

import json
from pathlib import Path

from conftest import ROOT
from jsonschema import Draft202012Validator

SCHEMA = json.loads((ROOT / "schemas" / "golden_pair.schema.json").read_text(encoding="utf-8"))
EXAMPLE = Path(__file__).resolve().parent / "fixtures" / "golden_set" / "example.json"


def errors(pair: dict) -> list[str]:
    return [e.message for e in Draft202012Validator(SCHEMA).iter_errors(pair)]


def test_example_golden_set_file_validates() -> None:
    pairs = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    assert isinstance(pairs, list) and pairs
    assert {i: errors(p) for i, p in enumerate(pairs)} == {i: [] for i in range(len(pairs))}
    assert len({p["id"] for p in pairs}) == len(pairs)


def test_a_pair_needs_its_expected_text_and_who_verified_it() -> None:
    pair = json.loads(EXAMPLE.read_text(encoding="utf-8"))[0]
    for column in ("expected_text", "verified_by", "verified_on", "source_url"):
        assert errors({k: v for k, v in pair.items() if k != column}) == [f"'{column}' is a required property"]


def test_the_date_must_be_a_calendar_style_iso_date() -> None:
    pair = json.loads(EXAMPLE.read_text(encoding="utf-8"))[0]
    assert errors({**pair, "as_of": "1-7-2024"})
