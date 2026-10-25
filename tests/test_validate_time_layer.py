"""Validator checks for the v0.3.0 time layer (ticket #17; spec #10,
PROCUREMENT_PLAN §7.3 and §7.6): corrupt the fixture build with
corrupt_output() and expect validate.py to exit non-zero naming the broken
invariant. v0.2.0 manifests skip these checks (see test_validate.py)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from conftest import BuildOutput, Rows, build_fixtures, corrupt_output, load_fixture_rows, run_validator
from test_state_amendments import with_blocks

VERSIONS = "indian_act_section_versions.parquet"
EVENTS = "amendment_events.parquet"
JUDICIAL = "judicial_events.parquet"
JURISDICTIONS = "jurisdictions.parquet"
STATE_AMENDMENTS = "state_amendments.parquet"
COVERAGE = "manifest coverage"


def failures(output: BuildOutput) -> list[str]:
    result = run_validator(output.dir)
    assert result.returncode != 0, result.stdout
    return [line for line in result.stdout.splitlines() if line.startswith("❌")]


def assert_rejected(broken: BuildOutput, message: str) -> None:
    bad = failures(broken)
    assert bad, "no ❌ line"
    assert all(message in line for line in bad), bad


def assert_rejected_with_coverage(broken: BuildOutput, message: str) -> None:
    """Rejected for message; a corruption that changes a coverage count also
    (rightly) fails the recomputed coverage, and nothing else."""
    bad = failures(broken)
    assert any(message in line for line in bad), bad
    assert all(message in line or COVERAGE in line for line in bad), bad


def update(key: str, value: str, **changes: object):
    def mutate(rows: Rows) -> Rows:
        assert any(r[key] == value for r in rows), value
        return [{**r, **changes} if r[key] == value else r for r in rows]
    return mutate


def test_build_is_v030_and_validates(built: BuildOutput) -> None:
    assert built.manifest()["version"] == "v0.3.0"
    result = run_validator(built.dir)
    assert result.returncode == 0, result.stdout


def test_v030_manifest_requires_every_derived_table(built: BuildOutput, tmp_path: Path) -> None:
    shutil.copytree(built.dir, tmp_path / "out")
    manifest_path = tmp_path / "out" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    del manifest["files"][VERSIONS]
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    assert_rejected(BuildOutput(tmp_path / "out"), f"manifest.json is missing v0.3.0 file {VERSIONS}")


def test_rejects_overlapping_slices(built: BuildOutput, tmp_path: Path) -> None:
    broken = corrupt_output(built, tmp_path / "out", VERSIONS,
                            update("id", "A1909-7:1:1909-10-22", valid_to="2020-01-01"))
    assert_rejected(broken, "A1909-7 1 en: version 1 ends 2020-01-01 after version 2 starts 2019-10-31")


def test_rejects_gap_between_slices(built: BuildOutput, tmp_path: Path) -> None:
    broken = corrupt_output(built, tmp_path / "out", VERSIONS,
                            update("id", "A1909-7:1:1909-10-22", valid_to="2019-01-01"))
    assert_rejected(broken, "A1909-7 1 en: gap from 2019-01-01 to 2019-10-31 before version 2")


def test_rejects_valid_from_after_valid_to(built: BuildOutput, tmp_path: Path) -> None:
    broken = corrupt_output(built, tmp_path / "out", VERSIONS,
                            update("id", "A1909-7:1:1909-10-22", valid_from="2019-11-30"))
    assert_rejected(broken, "A1909-7 1 en: version 1 valid_from 2019-11-30 is after valid_to 2019-10-31")


def test_rejects_unavailable_slice_with_text(built: BuildOutput, tmp_path: Path) -> None:
    broken = corrupt_output(built, tmp_path / "out", VERSIONS,
                            update("id", "A1909-7:1:1909-10-22", full_text="Guessed wording."))
    assert_rejected(broken, "A1909-7:1:1909-10-22: text_status unavailable but full_text is set")


def test_rejects_asserted_slice_without_text(built: BuildOutput, tmp_path: Path) -> None:
    broken = corrupt_output(built, tmp_path / "out", VERSIONS,
                            update("id", "A1872-1:8:1872-03-15", full_text=None))
    assert_rejected(broken, "A1872-1:8:1872-03-15: text_status verbatim_source but full_text is null")


def test_rejects_later_slice_opened_by_no_event(built: BuildOutput, tmp_path: Path) -> None:
    # The repeal opens A1872-1:8's second slice; the slice before it is in_force, not unknown.
    broken = corrupt_output(built, tmp_path / "out", VERSIONS,
                            update("id", "A1872-1:8:2024-07-01", amendment_event_ids=[]))
    assert_rejected(broken, "A1872-1:8:2024-07-01: version 2 is opened by no event")


def test_rejects_dangling_event_id(built: BuildOutput, tmp_path: Path) -> None:
    broken = corrupt_output(built, tmp_path / "out", VERSIONS, update(
        "id", "A1872-1:8:2024-07-01", amendment_event_ids=["A1872-1:ev:A2099-1:repeal"]))
    assert_rejected(broken, "A1872-1:8:2024-07-01: event A1872-1:ev:A2099-1:repeal is not an "
                            "amendment or judicial event")


def test_rejects_dangling_footnote_reference(built: BuildOutput, tmp_path: Path) -> None:
    broken = corrupt_output(built, tmp_path / "out", VERSIONS, update(
        "id", "A1909-7:1:2019-10-31", footnote_references=["A1909-7:Page 9:99"]))
    assert_rejected(broken, "A1909-7:1:2019-10-31: footnote A1909-7:Page 9:99 is not a footnote")


def test_rejects_event_without_a_source(built: BuildOutput, tmp_path: Path) -> None:
    broken = corrupt_output(built, tmp_path / "out", EVENTS,
                            update("id", "A1909-7:ev:act-34-of-2019:s95", footnote_ids=[]))
    assert_rejected(broken, "A1909-7:ev:act-34-of-2019:s95: other event has no footnote")


def test_rejects_event_citing_unknown_footnote(built: BuildOutput, tmp_path: Path) -> None:
    broken = corrupt_output(built, tmp_path / "out", EVENTS, update(
        "id", "A1909-7:ev:act-34-of-2019:s95", footnote_ids=["A1909-7:Page 9:99"]))
    assert_rejected(broken, "A1909-7:ev:act-34-of-2019:s95: footnote A1909-7:Page 9:99 is not a footnote")


@pytest.fixture(scope="module")
def built_blocks(tmp_path_factory: pytest.TempPathFactory) -> BuildOutput:
    """The fixtures plus the STATE AMENDMENT blocks of test_state_amendments."""
    return build_fixtures(tmp_path_factory.mktemp("blocks"), with_blocks(load_fixture_rows()))


def test_build_with_state_amendments_validates(built_blocks: BuildOutput) -> None:
    assert built_blocks.table(STATE_AMENDMENTS)
    result = run_validator(built_blocks.dir)
    assert result.returncode == 0, result.stdout


def test_rejects_version_of_unknown_section(built: BuildOutput, tmp_path: Path) -> None:
    broken = corrupt_output(built, tmp_path / "out", VERSIONS,
                            update("id", "A1872-1:8:1872-03-15", slug="8a"))
    bad = failures(broken)
    assert any("A1872-1:8:1872-03-15: A1872-1 has no section 8a" in line for line in bad), bad


def test_rejects_event_of_unknown_act(built: BuildOutput, tmp_path: Path) -> None:
    broken = corrupt_output(built, tmp_path / "out", EVENTS,
                            update("id", "A1909-7:ev:act-34-of-2019:s95", act_id="A1909-99"))
    bad = failures(broken)
    assert any("A1909-7:ev:act-34-of-2019:s95: unknown act_id A1909-99" in line for line in bad), bad


def test_rejects_event_affecting_unknown_section(built: BuildOutput, tmp_path: Path) -> None:
    broken = corrupt_output(built, tmp_path / "out", EVENTS,
                            update("id", "A1909-7:ev:act-34-of-2019:s95", provisions_affected=["95"]))
    assert_rejected(broken, "A1909-7:ev:act-34-of-2019:s95: A1909-7 has no section 95")


def test_rejects_unknown_amending_instrument(built: BuildOutput, tmp_path: Path) -> None:
    broken = corrupt_output(built, tmp_path / "out", EVENTS,
                            update("id", "A1909-7:ev:act-34-of-2019:s95", amending_instrument_id="A2019-34"))
    assert_rejected(broken, "A1909-7:ev:act-34-of-2019:s95: unknown amending_instrument_id A2019-34")


def test_rejects_ruling_on_unknown_act(built: BuildOutput, tmp_path: Path) -> None:
    broken = corrupt_output(built, tmp_path / "out", JUDICIAL,
                            update("id", "A1860-45:je:377:2018-09-06", act_id="A1860-99"))
    assert_rejected_with_coverage(broken, "A1860-45:je:377:2018-09-06: unknown act_id A1860-99")


def test_rejects_unknown_act_jurisdiction(built: BuildOutput, tmp_path: Path) -> None:
    broken = corrupt_output(built, tmp_path / "out", "acts", update("act_id", "A1909-7", jurisdiction="IN-XX"))
    assert_rejected(broken, "A1909-7: jurisdiction IN-XX is not a jurisdiction code")


def test_rejects_unknown_state_jurisdiction(built_blocks: BuildOutput, tmp_path: Path) -> None:
    broken = corrupt_output(built_blocks, tmp_path / "out", STATE_AMENDMENTS,
                            update("id", "A1947-14:s2:IN-KL", state_jurisdiction="IN-XX"))
    assert_rejected_with_coverage(broken, "A1947-14:s2:IN-KL: state_jurisdiction IN-XX is not a jurisdiction code")


def test_rejects_former_iso_code_as_state_jurisdiction(built_blocks: BuildOutput, tmp_path: Path) -> None:
    # IN-OR is Odisha's former code: an alias resolves to IN-OD but is not itself a code.
    broken = corrupt_output(built_blocks, tmp_path / "out", STATE_AMENDMENTS,
                            update("id", "A1947-14:s2:IN-OD", state_jurisdiction="IN-OR"))
    assert_rejected_with_coverage(broken, "A1947-14:s2:IN-OD: state_jurisdiction IN-OR is not a jurisdiction code")


def test_rejects_state_amendment_of_unknown_central_act(built_blocks: BuildOutput, tmp_path: Path) -> None:
    broken = corrupt_output(built_blocks, tmp_path / "out", STATE_AMENDMENTS,
                            update("id", "A1947-14:s2:IN-KL", central_act_id="A1947-99"))
    assert_rejected_with_coverage(broken, "A1947-14:s2:IN-KL: unknown central_act_id A1947-99")


def test_rejects_state_amendment_of_unknown_section(built_blocks: BuildOutput, tmp_path: Path) -> None:
    broken = corrupt_output(built_blocks, tmp_path / "out", STATE_AMENDMENTS,
                            update("id", "A1947-14:s2:IN-KL", section_id="A1947-14:99"))
    assert_rejected_with_coverage(broken, "A1947-14:s2:IN-KL: section_id A1947-14:99 is not a section")


def test_rejects_unknown_succession_link(built: BuildOutput, tmp_path: Path) -> None:
    broken = corrupt_output(built, tmp_path / "out", JURISDICTIONS,
                            update("code", "IN-TS", inherited_laws_from=["IN-XX"]))
    assert_rejected_with_coverage(broken, "IN-TS: inherited_laws_from IN-XX is not a jurisdiction code")


def test_rejects_alias_that_resolves_elsewhere(built: BuildOutput, tmp_path: Path) -> None:
    # IN-KL is Kerala's code, so as an alias of Tamil Nadu it cannot resolve to IN-TN.
    broken = corrupt_output(built, tmp_path / "out", JURISDICTIONS,
                            update("code", "IN-TN", iso_aliases=["IN-KL"]))
    assert_rejected_with_coverage(broken, "alias IN-KL is also a jurisdiction code")


# A1872-1:8 (Evidence Act s. 8) is in_force from 1872-03-15 until the Act's
# repeal on 2024-07-01. No curated ruling touches it, so these tests add rulings.
STAYED = "A1872-1:je:8:1990-01-01"
LIFTED = "A1872-1:je:8:1995-01-01"


def ruling(effect: str, date: str) -> dict[str, object]:
    return {"id": f"A1872-1:je:8:{date}", "act_id": "A1872-1", "provision_path": "8",
            "court": "Supreme Court of India", "case_name": "X v. Union of India",
            "neutral_citation": None, "reported_citation": None, "decision_date": date,
            "effect": effect, "scope_note": "Test ruling.", "source_url": "https://example.org/x"}


def add_rulings(*rulings: dict[str, object]):
    def mutate(rows: Rows) -> Rows:
        return [*rows, *rulings]
    return mutate


def test_rejects_in_force_slice_after_strike_down(built: BuildOutput, tmp_path: Path) -> None:
    broken = corrupt_output(built, tmp_path / "out", JUDICIAL, add_rulings(ruling("struck_down", "1990-01-01")))
    assert_rejected_with_coverage(
        broken, "A1872-1 8 en: version 1 is in_force after the struck_down ruling A1872-1:je:8:1990-01-01")


def test_rejects_in_force_slice_during_a_stay(built: BuildOutput, tmp_path: Path) -> None:
    broken = corrupt_output(built, tmp_path / "out", JUDICIAL, add_rulings(ruling("stayed", "1990-01-01")))
    assert_rejected_with_coverage(broken, f"A1872-1 8 en: version 1 is in_force after the stayed ruling {STAYED}")


def stay_then_in_force(rows: Rows) -> Rows:
    """A1872-1:8 as in_force, stayed from 1990, in_force again from 1995, repealed."""
    first = next(v for v in rows if v["id"] == "A1872-1:8:1872-03-15")
    repealed = next(v for v in rows if v["id"] == "A1872-1:8:2024-07-01")
    spans = [("1872-03-15", "1990-01-01", "in_force", []),
             ("1990-01-01", "1995-01-01", "stayed", [STAYED]),
             ("1995-01-01", "2024-07-01", "in_force", [LIFTED])]
    chain = [{**first, "id": f"A1872-1:8:{start}", "version_number": n + 1, "valid_from": start,
              "valid_to": end, "status": status, "amendment_event_ids": ids}
             for n, (start, end, status, ids) in enumerate(spans)]
    return [v for v in rows if v["act_id"] != "A1872-1"] + [*chain, {**repealed, "version_number": 4}]


def test_a_stay_lasts_until_stay_lifted(built: BuildOutput, tmp_path: Path) -> None:
    rulings = corrupt_output(built, tmp_path / "rulings", JUDICIAL,
                             add_rulings(ruling("stayed", "1990-01-01"), ruling("stay_lifted", "1995-01-01")))
    lifted = corrupt_output(rulings, tmp_path / "lifted", VERSIONS, stay_then_in_force)
    bad = failures(lifted)  # the added rulings change the coverage counts, and nothing else fails
    assert all(COVERAGE in line for line in bad), bad


def test_rejects_in_force_slice_after_an_unlifted_stay(built: BuildOutput, tmp_path: Path) -> None:
    rulings = corrupt_output(built, tmp_path / "rulings", JUDICIAL, add_rulings(ruling("stayed", "1990-01-01")))
    broken = corrupt_output(rulings, tmp_path / "out", VERSIONS, stay_then_in_force)
    bad = failures(broken)
    # The 1995 slice is still opened by the (now unknown) stay_lifted id.
    assert f"❌ A1872-1 8 en: version 3 is in_force after the stayed ruling {STAYED}" in bad, bad


@pytest.mark.parametrize("key", [
    "amendment_events_by_operation", "judicial_events_by_effect", "jurisdictions",
    "state_amendments", "section_versions_by_text_status", "section_versions_by_status",
    "section_versions_sections"])
def test_rejects_tampered_time_layer_coverage(built: BuildOutput, tmp_path: Path, key: str) -> None:
    shutil.copytree(built.dir, tmp_path / "out")
    manifest_path = tmp_path / "out" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert key in manifest["coverage"]
    manifest["coverage"][key] = "tampered"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    assert_rejected(BuildOutput(tmp_path / "out"), f"manifest coverage.{key}")
