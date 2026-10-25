"""The derived tables, in build order: each builder also sees the tables listed
before it. A new derived table is one stage module plus one line here."""

from __future__ import annotations

from enrich import DerivedTable
from enrich import events as events_stage

DERIVED_TABLES: list[DerivedTable] = [
    events_stage.TABLE,
    __import__("enrich.jurisdictions").jurisdictions.TABLE,
]
