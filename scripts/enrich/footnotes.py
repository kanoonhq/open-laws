"""Footnotes stage: footnote -> section linkage and w.e.f. parsing (identity for now)."""

from __future__ import annotations

import pyarrow as pa

from enrich import Coverage, Rows

FIELDS: list[pa.Field] = []


def enrich(footnotes: Rows, sections: Rows) -> tuple[Rows, Coverage]:
    """Footnotes in, footnotes out; `sections` arrive in document order per Act."""
    return [dict(f) for f in footnotes], {}
