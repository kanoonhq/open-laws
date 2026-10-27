"""
judicial_events stage (spec #10, ticket #14; PROCUREMENT_PLAN §2.2 Table 4).

One row per court ruling that changes whether a provision is enforceable,
from the hand-maintained curated/judicial_events.json (the four PLAN seed
rulings):

- act_id: the curated `Act N of YYYY` citation resolved against the acts
  table (A{YYYY}-{N}); a ruling whose Act is not in the corpus is left out
  and listed in coverage, never given a guessed act_id.
- provision_path: the section slug as in the sections table (e.g. 66a).
- neutral_citation is null for rulings before Supreme Court neutral citations
  (2023); reported_citation is the SCC report only where certain, else null.
- id: {act_id}:je:{provision_path}:{decision_date}.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping

import pyarrow as pa

from enrich import CURATED_DIR, Coverage, DerivedTable, Row, Rows
from enrich.acts import act_id_for
from enrich.events import citation
from table_files import ACTS

FILE = "judicial_events.parquet"
SOURCE = CURATED_DIR / "judicial_events.json"
EFFECTS = ("struck_down", "read_down", "stayed", "stay_lifted", "upheld")
STRING = pa.string()
SCHEMA = pa.schema([
    ("id", STRING), ("act_id", STRING), ("provision_path", STRING), ("court", STRING),
    ("case_name", STRING), ("neutral_citation", STRING), ("reported_citation", STRING),
    ("decision_date", STRING), ("effect", STRING), ("scope_note", STRING), ("source_url", STRING),
])


def curated() -> Rows:
    return json.loads(SOURCE.read_text(encoding="utf-8"))


def ruling_act_id(ruling: Row) -> str:
    """The act_id the ruling's `Act N of YYYY` citation names."""
    cited = citation(ruling["act_citation"])
    if cited is None:
        raise ValueError(f"{SOURCE.name}: unparseable act_citation {ruling['act_citation']!r}")
    return act_id_for(cited[1], cited[0])


def build(tables: Mapping[str, Rows]) -> Rows:
    acts = {a["act_id"] for a in tables[ACTS]}
    rows: Rows = []
    for ruling in curated():
        resolved = ruling_act_id(ruling)
        if resolved not in acts:
            continue
        fields = {k: v for k, v in ruling.items() if k != "act_citation"}
        row = {"id": f"{resolved}:je:{ruling['provision_path']}:{ruling['decision_date']}",
               "act_id": resolved, **fields}
        rows.append({name: row[name] for name in SCHEMA.names})
    return rows


def coverage(rows: Rows) -> Coverage:
    counts = Counter(e["effect"] for e in rows)
    emitted = {(e["act_id"], e["provision_path"], e["decision_date"]) for e in rows}
    unresolved = sorted(
        f"{r['act_citation']}, s. {r['provision_path']} ({r['decision_date']})" for r in curated()
        if (ruling_act_id(r), r["provision_path"], r["decision_date"]) not in emitted)
    return {"judicial_events_by_effect": {effect: counts[effect] for effect in EFFECTS},
            "judicial_events_unresolved_act": unresolved}


TABLE = DerivedTable(file=FILE, schema=SCHEMA, json_schema="judicial_event.schema.json",
                     build=build, coverage=coverage)
