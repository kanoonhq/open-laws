"""
Regenerate the v0.1.1-shaped test fixtures from real v0.1.1 rows.

Edit FIXTURE_ACTS / FIXTURE_MAPPINGS to extend the fixtures, then run:
  python scripts/extract_inputs.py
  python tests/fixtures/make_fixtures.py [--input-dir .cache/inputs/v0.1.1]

Each selected Act keeps the chosen sections (by section_number) and the
footnotes on the chosen pages (by page_or_anchor); None keeps all of them.
section_count/footnote_count are recomputed so the slice stays consistent.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = Path(__file__).resolve().parent / "v0.1.1"

# act_id -> (section_numbers or None for all, footnote pages or None for all)
FIXTURE_ACTS: dict[str, tuple[list[str] | None, list[str] | None]] = {
    # Repealed (by A2023-45); inline markers reset between Page 14 and Page 15.
    "A1860-45": (
        ["Section 1.", "Section 2.", "Section 3.", "Section 4.", "Section 5.", "Section 302."],
        ["Page 14", "Page 15"],
    ),
    "A2023-45": (["Section 103."], None),
    # Small Act with inline markers and an irregular w.e.f. date (31-10- 2019).
    "A1909-7": (None, None),
    # Repealed (by A2023-47); gives a BSA mapping (applies_by proceeding_date).
    "A1872-1": (["Section 8."], []),
    "A2023-47": (["Section 6."], []),
}
# (old_act_id, old_section, new_act_id, new_section)
FIXTURE_MAPPINGS: list[tuple[str, str | None, str, str | None]] = [
    ("A1860-45", "Section 302.", "A2023-45", "Section 103."),
    ("A1872-1", "Section 8.", "A2023-47", "Section 6."),
]
TABLES = {
    "acts": "indian_central_acts.parquet",
    "sections": "indian_central_act_sections.parquet",
    "footnotes": "central_act_footnotes.parquet",
    "mappings": "criminal_law_mappings.parquet",
}


def select_fixture_rows(input_dir: Path) -> dict[str, list[dict[str, Any]]]:
    """Slice the v0.1.1 tables down to the fixture selection, keeping row order."""
    tables = {name: pq.read_table(input_dir / f).to_pylist() for name, f in TABLES.items()}

    def keep(row: dict[str, Any], key: str, index: int) -> bool:
        chosen = FIXTURE_ACTS.get(row["act_id"])
        return chosen is not None and (chosen[index] is None or row[key] in chosen[index])

    sections = [s for s in tables["sections"] if keep(s, "section_number", 0)]
    footnotes = [f for f in tables["footnotes"] if keep(f, "page_or_anchor", 1)]
    acts = [dict(a) for a in tables["acts"] if a["act_id"] in FIXTURE_ACTS]
    for act in acts:
        act["section_count"] = sum(s["act_id"] == act["act_id"] for s in sections)
        act["footnote_count"] = sum(f["act_id"] == act["act_id"] for f in footnotes)
    wanted = set(FIXTURE_MAPPINGS)
    mappings = [
        m
        for m in tables["mappings"]
        if (m["old_act_id"], m["old_section"], m["new_act_id"], m["new_section"]) in wanted
    ]
    return {"acts": acts, "sections": sections, "footnotes": footnotes, "mappings": mappings}


def main() -> None:
    parser = argparse.ArgumentParser(description="Regenerate tests/fixtures/v0.1.1 from v0.1.1 data.")
    parser.add_argument("--input-dir", type=Path, default=ROOT / ".cache" / "inputs" / "v0.1.1")
    input_dir = parser.parse_args().input_dir
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    for name, rows in select_fixture_rows(input_dir).items():
        path = FIXTURES_DIR / f"{name}.json"
        path.write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"{path.relative_to(ROOT)}: {len(rows)} rows")


if __name__ == "__main__":
    main()
