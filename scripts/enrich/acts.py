"""Acts stage: jurisdiction-qualified work_id and doc_type (PROCUREMENT_PLAN §2.1)."""

from __future__ import annotations

import pyarrow as pa

from enrich import Coverage, Rows

FIELDS = [
    pa.field("work_id", pa.string()),
    pa.field("doc_type", pa.string()),
]


def work_id(act_id: str) -> str:
    """A1860-45 -> in-central/act/1860/45 (no zero-padding)."""
    year, number = act_id.removeprefix("A").split("-")
    return f"in-central/act/{int(year)}/{int(number)}"


def enrich(acts: Rows) -> tuple[Rows, Coverage]:
    """Add work_id and doc_type to every Central Act."""
    return [{**act, "work_id": work_id(act["act_id"]), "doc_type": "act"} for act in acts], {}
