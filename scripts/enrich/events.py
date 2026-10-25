"""
amendment_events stage (spec #10, ticket #11; PROCUREMENT_PLAN §2.2 Table 1).

One event per amending footnote, plus one `repeal` event per repealed Act:

- operation: the footnote's amendment_type (all six types are operations).
- provisions_affected: [section_slug] when the footnote is linked, else [].
- amending_citation: the first `Act N of YYYY[, s. M]` in the footnote's own
  text (run-in footnotes excluded); amending_instrument_id: that Act's act_id
  when it is in the corpus, and assent_date: that Act's assent_date.
- old_text: the quoted wording in `for "…"` (substitution) or `"…" omitted`,
  only when the footnote quotes exactly one un-nested span; else null.
- publication_date, commencement_date and commencement_notification_id are
  null in v0.3.0 (no gazette sources), so is_retrospective is null too.
- id: {act_id}:ev:{amending act_id | citation slug | uncited}:{sM | fn-...},
  with -2, -3, ... on collision, in table order (stable across rebuilds).
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping

import pyarrow as pa

from enrich import Coverage, DerivedTable, Row, Rows
from enrich.footnotes import own_text
from table_files import ACTS, FOOTNOTES

FILE = "amendment_events.parquet"
OPERATIONS = ("substitution", "insertion", "omission", "renumbering", "extension", "repeal", "other")
STRING, STRINGS = pa.string(), pa.list_(pa.string())
SCHEMA = pa.schema([
    ("id", STRING), ("act_id", STRING), ("provisions_affected", STRINGS), ("operation", STRING),
    ("amending_instrument_id", STRING), ("amending_citation", STRING), ("assent_date", STRING),
    ("publication_date", STRING), ("commencement_date", STRING), ("wef_date", STRING),
    ("is_retrospective", pa.bool_()), ("old_text", STRING), ("footnote_ids", STRINGS),
    ("commencement_notification_id", STRING),
])

# "Act 13 of 2013, s. 9" (spacing as printed varies: "Act  34  of  2019")
CITATION = re.compile(r"\bAct\s+(?:No\.\s*)?(\d+)\s+of\s+(\d{4})(?:\s*,\s*s\.\s*(\d+[A-Z]*)\b)?")
# One quoted span: curly “…” or straight "…".
QUOTED = re.compile(r"“([^“”]*)”|\"([^\"“”]*)\"")
FOR_BEFORE = re.compile(r"\bfor\s*$")
OMITTED_AFTER = re.compile(r"\s*(?:have\s+been\s+|has\s+been\s+)?(?:omitted|rep\.|repealed)\b")


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def citation(text: str) -> tuple[str, str, str | None] | None:
    """(number, year, amending section or None) of the first Act cited in text."""
    m = CITATION.search(text)
    return (str(int(m[1])), m[2], m[3]) if m else None


def old_text(text: str) -> str | None:
    """The replaced wording a footnote quotes; None unless exactly one
    un-nested span stands in a `for "…"` or `"…" omitted` position."""
    spans = list(QUOTED.finditer(text))
    if len(spans) != 1 or sum(text.count(q) for q in "“”\"") != 2:
        return None  # none, several, or unbalanced quotes
    span = spans[0]
    quoted = span[1] if span[1] is not None else span[2]
    if "‘" in quoted or "'" in quoted:
        return None  # a quotation nested inside the quoted wording
    if FOR_BEFORE.search(text[: span.start()]) or OMITTED_AFTER.match(text, span.end()):
        return " ".join(quoted.split()) or None
    return None


def event(act_id: str, operation: str, cited: tuple[str, str, str | None] | None,
          acts: Mapping[str, Row], **fields: object) -> Row:
    instrument = None
    if cited and (candidate := f"A{cited[1]}-{cited[0]}") in acts:
        instrument = candidate
    amending_citation = None
    if cited:
        amending_citation = f"Act {cited[0]} of {cited[1]}" + (f", s. {cited[2]}" if cited[2] else "")
    return {
        "act_id": act_id,
        "operation": operation,
        "amending_instrument_id": instrument,
        "amending_citation": amending_citation,
        "assent_date": acts[instrument]["assent_date"] if instrument else None,
        "publication_date": None,
        "commencement_date": None,
        "is_retrospective": None,  # needs both wef_date and publication_date
        "commencement_notification_id": None,
        **fields,
    }


def instrument_key(e: Row, cited: tuple[str, str, str | None] | None) -> str:
    if e["amending_instrument_id"]:
        return e["amending_instrument_id"]
    return slugify(f"act {cited[0]} of {cited[1]}") if cited else "uncited"


def build(tables: Mapping[str, Rows]) -> Rows:
    acts = {a["act_id"]: a for a in tables[ACTS]}
    drafts: list[tuple[str, Row]] = []  # (id before de-duplication, event)
    for f in tables[FOOTNOTES]:
        text = own_text(f)
        cited = citation(text)
        e = event(f["act_id"], f["amendment_type"], cited, acts,
                  provisions_affected=[f["section_slug"]] if f["section_slug"] else [],
                  wef_date=f["wef_date"], old_text=old_text(text), footnote_ids=[f["id"]])
        where = f"s{cited[2]}" if cited and cited[2] else \
            f"fn-{slugify(f['page_or_anchor'] or '')}-{f['footnote_number']}"
        drafts.append((f"{f['act_id']}:ev:{instrument_key(e, cited)}:{where}", e))
    for a in tables[ACTS]:
        if not a["is_repealed"]:
            continue
        cited = citation(a["repeal_reason"] or "")
        cited = (cited[0], cited[1], None) if cited else None
        e = event(a["act_id"], "repeal", cited, acts, provisions_affected=[],
                  wef_date=a["repeal_date"], old_text=None, footnote_ids=[])
        if e["amending_instrument_id"] is None and a["repealed_by"] in acts:
            e = {**e, "amending_instrument_id": a["repealed_by"],
                 "assent_date": acts[a["repealed_by"]]["assent_date"]}
        drafts.append((f"{a['act_id']}:ev:{instrument_key(e, cited)}:repeal", e))

    used: set[str] = set()
    rows: Rows = []
    for base, e in drafts:
        event_id, n = base, 1
        while event_id in used:
            n += 1
            event_id = f"{base}-{n}"
        used.add(event_id)
        rows.append({"id": event_id, **e})
    return rows


def coverage(rows: Rows) -> Coverage:
    counts = Counter(e["operation"] for e in rows)
    return {"amendment_events_by_operation": {op: counts[op] for op in OPERATIONS}}


TABLE = DerivedTable(file=FILE, schema=SCHEMA, json_schema="amendment_event.schema.json",
                     build=build, coverage=coverage)
