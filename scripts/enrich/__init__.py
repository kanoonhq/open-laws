"""
Enrichment stages for the v0.2.0 build (scripts/build_dataset.py).

Each stage module is a pure function over row lists and declares the columns
it adds:

  FIELDS: list[pa.Field]                      appended to the table's v0.1.1 schema
  enrich(...) -> tuple[Rows, Coverage]        enriched rows + manifest coverage

The build merges every stage's Coverage into manifest["coverage"]; stages
must use distinct top-level keys.
"""

from __future__ import annotations

from typing import Any

Row = dict[str, Any]
Rows = list[Row]
Coverage = dict[str, Any]
