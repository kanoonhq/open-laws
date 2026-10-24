"""Mappings stage: transition rules on criminal-law mappings (identity for now)."""

from __future__ import annotations

import pyarrow as pa

from enrich import Coverage, Rows

FIELDS: list[pa.Field] = []


def enrich(mappings: Rows) -> tuple[Rows, Coverage]:
    """Mappings in, mappings out."""
    return [dict(m) for m in mappings], {}
