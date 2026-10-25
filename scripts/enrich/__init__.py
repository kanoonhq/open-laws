"""
Enrichment stages for the v0.2.0 build (scripts/build_dataset.py).

Each stage module is a pure function over row lists and declares the columns
it adds:

  FIELDS: list[pa.Field]                      appended to the table's v0.1.1 schema
  enrich(...) -> tuple[Rows, Coverage]        enriched rows + manifest coverage

The build merges every stage's Coverage into manifest["coverage"]; stages
must use distinct top-level keys.

Derived tables (v0.3.0) are new output tables rather than new columns. Each
is one stage module that defines a module-level DerivedTable and is listed
once in enrich/registry.py; the build writes it and validate.py checks it
against its JSON schema and recomputes its coverage, with no other edits.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyarrow as pa

Row = dict[str, Any]
Rows = list[Row]
Coverage = dict[str, Any]
# Hand-maintained inputs (CSV/JSON, one source URL per row), reviewed like code.
CURATED_DIR = Path(__file__).resolve().parents[2] / "curated"
# tables[BUILD_INFO] is one row {"export_timestamp", "version"}: the build's
# fixed --timestamp and version, for derived tables that record provenance.
# It is a build input, not an output table.
BUILD_INFO = "build_info"


@dataclass(frozen=True)
class DerivedTable:
    """One derived output table.

    build(tables) is pure: `tables` maps file name -> rows for the enriched
    v0.2.0 tables (table_files.py names) and every derived table listed before
    this one in the registry. Curated inputs are read from CURATED_DIR.
    coverage(rows) gives the table's manifest coverage from its own rows, so
    the validator can recompute it; its keys must not clash with other stages.
    """

    file: str  # output parquet file name, e.g. amendment_events.parquet
    schema: pa.Schema  # arrow schema: the file's columns, in order
    json_schema: str  # file name in schemas/
    build: Callable[[Mapping[str, Rows]], Rows]
    coverage: Callable[[Rows], Coverage]
