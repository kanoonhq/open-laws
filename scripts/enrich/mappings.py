"""Mappings stage: transition rules on criminal-law mappings (PROCUREMENT_PLAN §5 Phase 0)."""

from __future__ import annotations

import pyarrow as pa

from enrich import Coverage, Rows

FIELDS = [
    pa.field("effective_from", pa.string()),
    pa.field("applies_by", pa.string()),
]

# The three 2023 codes all commenced on 1 July 2024.
EFFECTIVE_FROM = "2024-07-01"

# new_act_id -> which date picks the old or the new code
APPLIES_BY = {
    "A2023-45": "offence_date",  # BNS: substantive law, Art. 20(1)
    "A2023-46": "proceeding_date",  # BNSS: savings in s. 531
    "A2023-47": "proceeding_date",  # BSA: savings in s. 170
}


def applies_by(new_act_id: str) -> str:
    """The transition rule for a mapping into new_act_id; refuses to guess."""
    if new_act_id not in APPLIES_BY:
        raise ValueError(f"no applies_by rule for mappings into {new_act_id}")
    return APPLIES_BY[new_act_id]


def enrich(mappings: Rows) -> tuple[Rows, Coverage]:
    """Add effective_from and applies_by to every mapping."""
    return [
        {**m, "effective_from": EFFECTIVE_FROM, "applies_by": applies_by(m["new_act_id"])}
        for m in mappings
    ], {}
