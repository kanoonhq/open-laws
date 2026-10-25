"""
indian_act_section_versions stage (spec #10, ticket #15; PROCUREMENT_PLAN §2.2
Table 2). Bi-temporal slices of each section (language `en`), built from the
sections, amendment_events and judicial_events tables. Wording and dates are
never guessed:

- Current slice: the section text verbatim (`verbatim_source`, confidence 1.0),
  valid from the latest dated event linked to the section, else the Act's
  assent_date. A section with neither gets no slice.
- Earlier slices: one per earlier event date, walking back to assent_date; each
  ends where the next begins and lists the events that opened it. The chain
  stops (no earlier slice) at an undated event, since it cannot be placed in
  time, at an event dated on or before assent_date, and where reversing an
  insertion leaves no text (the section did not exist before it).
- Reverse reconstruction, one level: the slice just before the current one is
  `reconstructed` (confidence 0.8) only when every event that opened the
  current slice is reversible, and every older slice is `unavailable` (null
  text and heading). An event is reversible only when its single footnote is
  `inline_marker`-linked, its number marks the section text exactly once, the
  marked span is not nested in, and does not contain, any other bracket or
  marker, and the operation, the footnote's verb, the quoted old_text and the
  marker kind agree:
    `N[new]` + `Ins.` insertion, no quoted text  -> the span is removed
    `N[new]` + `Subs.` substitution, old_text    -> the span becomes old_text
    `N***`   + omission quoting the omitted words -> the stars become old_text
  Anything else (v0.1.1 misclassified some footnotes, e.g. insertions that
  quote replaced words) leaves the slice `unavailable`. Reversed spans lose
  their markers; markers of other footnotes stay.
- Status: judicial_events split the chain at decision_date (`struck_down`,
  `stayed`; `stay_lifted` restores `in_force`; `read_down` and `upheld` never
  change it), and a repealed Act gets a final `repealed` slice from its
  repeal_date. Such slices list the ruling's or the repeal event's id in
  amendment_event_ids.
- Provenance: source_url is a permalink to the frozen v0.1.1 sections table the
  text was read from (India Code handles are not in the act data; they replace
  it once the crawler records India Code pages), source_sha256 the SHA-256 of
  the section's full_text as read (UTF-8; "" when null), retrieved_at the
  build's fixed export timestamp, parser_version the build version, and
  recorded_from v0.3.0 with recorded_to null.
- id: {act_id}:{slug}:{valid_from}.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, replace
from itertools import pairwise

import pyarrow as pa
from extract_inputs import V011_COMMIT

from enrich import BUILD_INFO, Coverage, DerivedTable, Row, Rows
from enrich import events as events_stage
from enrich import judicial_events as judicial_stage
from enrich.footnotes import BRACKET_OR_STARS, INLINE, OMITTED, markers, own_text
from table_files import ACTS, FOOTNOTES, SECTIONS

FILE = "indian_act_section_versions.parquet"
RECORDED_FROM = "v0.3.0"
RECONSTRUCTED_CONFIDENCE = 0.8
TEXT_STATUSES = ("verbatim_source", "reconstructed", "unavailable")
STATUSES = ("in_force", "not_commenced", "repealed", "omitted", "expired", "struck_down", "stayed",
            "ordinance_lapsed")
# Judicial effect -> the status it opens; read_down and upheld change nothing.
RULING_STATUS = {"struck_down": "struck_down", "stayed": "stayed", "stay_lifted": "in_force"}
SOURCE_URL = (f"https://github.com/kanoonhq/open-laws/blob/{V011_COMMIT}/data/{SECTIONS}"
              "#{section_id}")
STRING, STRINGS = pa.string(), pa.list_(pa.string())
SCHEMA = pa.schema([
    ("id", STRING), ("act_id", STRING), ("section_number", STRING), ("slug", STRING),
    ("structural_unit", STRING), ("version_number", pa.int32()), ("heading", STRING),
    ("full_text", STRING), ("valid_from", STRING), ("valid_to", STRING), ("status", STRING),
    ("text_status", STRING), ("confidence", pa.float32()), ("amendment_event_ids", STRINGS),
    ("amended_by_act_id", STRING), ("amendment_citation", STRING), ("change_summary", STRING),
    ("footnote_references", STRINGS), ("source_url", STRING), ("source_sha256", STRING),
    ("retrieved_at", STRING), ("parser_version", STRING), ("recorded_from", STRING),
    ("recorded_to", STRING), ("language", STRING),
])

# The footnote's own verb, which must agree with the event's operation.
VERB = {"insertion": re.compile(r"^\s*\d+\.\s*Ins\."), "substitution": re.compile(r"^\s*\d+\.\s*Subs\.")}
PAST_TENSE = {"substitution": "Substituted", "insertion": "Inserted", "omission": "Omitted",
              "renumbering": "Renumbered", "extension": "Extended", "repeal": "Repealed",
              "other": "Amended"}
RULING_TENSE = {"struck_down": "Struck down", "stayed": "Stayed", "stay_lifted": "Stay lifted"}


@dataclass(frozen=True)
class Slice:
    valid_from: str
    full_text: str | None
    text_status: str
    confidence: float
    events: tuple[Row, ...] = ()  # amendment events that opened the slice
    changes: tuple[Row, ...] = ()  # rulings / repeal events that opened it
    status: str = "in_force"
    heading_known: bool = True


# --- reverse reconstruction -------------------------------------------------


def enclosed(text: str, offset: int) -> bool:
    """True unless the brackets before offset are balanced (offset at depth 0)."""
    depth = 0
    for ch in text[:offset]:
        depth += (ch == "[") - (ch == "]")
        if depth < 0:
            return True
    return depth != 0


def reversal(text: str, event: Row, footnotes: Mapping[str, Row]) -> tuple[int, int, str] | None:
    """(start, end, earlier wording) undoing one event in text, or None when it
    is not unambiguously reversible."""
    if len(event["footnote_ids"]) != 1:
        return None
    footnote = footnotes[event["footnote_ids"][0]]
    if footnote["linkage_method"] != INLINE:
        return None
    found = [(o, kind) for o, n, kind in markers(text) if n == footnote["footnote_number"]]
    if len(found) != 1 or enclosed(text, found[0][0]):
        return None
    start, kind = found[0]
    operation, old, verb_text = event["operation"], event["old_text"], own_text(footnote)
    if kind == "bracket":
        opening = BRACKET_OR_STARS.match(text, start).end()
        close = text.find("]", opening)
        if close < 0:
            return None  # unmatched
        inner = text[opening:close]
        if "[" in inner or markers(inner):
            return None  # nested
        if operation == "insertion" and old is None and VERB["insertion"].search(verb_text):
            return start, close + 1, ""
        if operation == "substitution" and old is not None and VERB["substitution"].search(verb_text):
            return start, close + 1, old
        return None
    if kind == "stars" and operation == "omission" and old is not None and OMITTED.search(verb_text):
        return start, BRACKET_OR_STARS.match(text, start).end(), old
    return None


def splice(left: str, middle: str, right: str) -> str:
    """left + middle + right; a removed span leaves no doubled, trailing or
    pre-punctuation space or line (whitespace only: wording is never changed)."""
    if middle[:1] in (",", ";", ":", "."):
        return left.rstrip(" ") + middle + right
    if middle:
        return left + middle + right
    if not right.strip():
        return left.rstrip()
    if left.endswith("\n") and right.startswith("\n"):
        return left + right[1:]
    if left[-1:] in (" ", "\n") and right[:1] in (" ", ",", ";", ":", ".", ")"):
        return left.rstrip(" ") + right
    return left + right


def reverse(text: str, events: tuple[Row, ...], footnotes: Mapping[str, Row]) -> str | None:
    """text before all of events took effect, or None when any is irreversible."""
    edits = []
    for event in events:
        if (edit := reversal(text, event, footnotes)) is None:
            return None
        edits.append(edit)
    edits.sort()
    if any(b[0] < a[1] for a, b in pairwise(edits)):
        return None  # overlapping spans
    for start, end, earlier in reversed(edits):
        text = splice(text[:start], earlier, text[end:])
    return text


# --- slices -----------------------------------------------------------------


def text_chain(section: Row, assent: str | None, events: Rows,
               footnotes: Mapping[str, Row]) -> list[Slice]:
    """The section's wording slices, oldest first (statuses still in_force)."""
    by_date: dict[str, list[Row]] = defaultdict(list)
    for e in events:
        if e["wef_date"] is not None:
            by_date[e["wef_date"]].append(e)
    dates = sorted(by_date)
    text = section["full_text"]
    if dates:
        current = Slice(dates[-1], text, "verbatim_source" if text else "unavailable",
                        1.0 if text else 0.0, tuple(by_date[dates[-1]]))
    elif assent is not None:
        current = Slice(assent, text, "verbatim_source" if text else "unavailable", 1.0 if text else 0.0)
    else:
        return []  # valid_from is unknown
    undated = any(e["wef_date"] is None for e in events)
    if not dates or undated or (assent is not None and dates[0] <= assent):
        return [current]
    starts = ([assent] if assent is not None else []) + dates[:-1]
    if not starts:
        return [current]  # no assent date: nothing is known before the event
    earlier = [Slice(start, None, "unavailable", 0.0, tuple(by_date.get(start, ())), heading_known=False)
               for start in starts]
    previous = reverse(text, current.events, footnotes) if text else None
    if previous is not None:
        if not previous.strip():
            return [current]  # the section did not exist before the insertion
        earlier[-1] = replace(earlier[-1], full_text=previous, text_status="reconstructed",
                              confidence=RECONSTRUCTED_CONFIDENCE, heading_known=True)
    return [*earlier, current]


def with_status(chain: list[Slice], changes: list[tuple[str, str, Row]]) -> list[Slice]:
    """Split chain at each (date, status, source) change after its start, in
    date order; a repeal is final."""
    if not chain:
        return []
    out = list(chain)
    for date, status, source in sorted(changes, key=lambda c: c[0]):
        at = next((i for i, s in enumerate(out) if s.valid_from >= date), len(out))
        if at < len(out) and out[at].valid_from == date:
            out[at] = replace(out[at], changes=(*out[at].changes, source))
        elif at > 0:
            out.insert(at, replace(out[at - 1], valid_from=date, events=(), changes=(source,)))
        else:
            continue  # before the first slice: nothing is known there
        for i in range(at, len(out)):
            if out[i].status != "repealed":
                out[i] = replace(out[i], status=status)
    return out


def summary(s: Slice) -> tuple[str | None, str | None, str | None]:
    """(amended_by_act_id, amendment_citation, change_summary) of a slice."""
    instruments = {e["amending_instrument_id"] for e in s.events + s.changes if "operation" in e}
    citations = list(dict.fromkeys(e["amending_citation"] for e in s.events + s.changes
                                   if e.get("amending_citation")))
    parts = []
    for e in s.events + s.changes:
        if "operation" in e:
            parts.append(f"{PAST_TENSE[e['operation']]} by {e['amending_citation'] or 'an uncited instrument'}")
        else:
            parts.append(f"{RULING_TENSE[e['effect']]}: {e['case_name']}, {e['court']}")
    by = next(iter(instruments)) if len(instruments) == 1 else None
    return by, "; ".join(citations) or None, "; ".join(parts) or None


def rows_for(section: Row, chain: list[Slice], info: Row) -> Rows:
    text = section["full_text"]
    common = {
        "act_id": section["act_id"], "section_number": section["section_number"], "slug": section["slug"],
        "structural_unit": section["structural_unit"],
        "source_url": SOURCE_URL.format(section_id=section["id"]),
        "source_sha256": hashlib.sha256((text or "").encode("utf-8")).hexdigest(),
        "retrieved_at": info["export_timestamp"], "parser_version": info["version"],
        "recorded_from": RECORDED_FROM, "recorded_to": None, "language": section["language"],
    }
    rows: Rows = []
    for n, s in enumerate(chain):
        by, cited, change = summary(s)
        row = {
            "id": f"{section['act_id']}:{section['slug']}:{s.valid_from}",
            "version_number": n + 1,
            "heading": section["heading"] if s.heading_known else None,
            "full_text": s.full_text, "valid_from": s.valid_from,
            "valid_to": chain[n + 1].valid_from if n + 1 < len(chain) else None,
            "status": s.status, "text_status": s.text_status, "confidence": s.confidence,
            "amendment_event_ids": [e["id"] for e in s.events + s.changes],
            "amended_by_act_id": by, "amendment_citation": cited, "change_summary": change,
            "footnote_references": [fid for e in s.events for fid in e["footnote_ids"]],
            **common,
        }
        rows.append({name: row[name] for name in SCHEMA.names})
    return rows


def build(tables: Mapping[str, Rows]) -> Rows:
    acts = {a["act_id"]: a for a in tables[ACTS]}
    footnotes = {f["id"]: f for f in tables[FOOTNOTES]}
    events: dict[tuple[str, str], Rows] = defaultdict(list)
    repeals: dict[str, Row] = {}
    for e in tables[events_stage.FILE]:
        if e["operation"] == "repeal":
            repeals[e["act_id"]] = e
        for slug in e["provisions_affected"]:
            events[(e["act_id"], slug)].append(e)
    rulings: dict[tuple[str, str], Rows] = defaultdict(list)
    for j in tables[judicial_stage.FILE]:
        rulings[(j["act_id"], j["provision_path"])].append(j)
    info = tables[BUILD_INFO][0]

    rows: Rows = []
    for section in tables[SECTIONS]:
        key = (section["act_id"], section["slug"])
        act = acts[section["act_id"]]
        changes = [(j["decision_date"], RULING_STATUS[j["effect"]], j)
                   for j in rulings[key] if j["effect"] in RULING_STATUS]
        if act["is_repealed"] and act["repeal_date"] and section["act_id"] in repeals:
            changes.append((act["repeal_date"], "repealed", repeals[section["act_id"]]))
        chain = with_status(text_chain(section, act["assent_date"], events[key], footnotes), changes)
        rows += rows_for(section, chain, info)
    return rows


def coverage(rows: Rows) -> Coverage:
    text_statuses = Counter(v["text_status"] for v in rows)
    statuses = Counter(v["status"] for v in rows)
    return {
        "section_versions_by_text_status": {t: text_statuses[t] for t in TEXT_STATUSES},
        "section_versions_by_status": {s: statuses[s] for s in STATUSES},
        # Sections without a slice = total_sections minus this.
        "section_versions_sections": len({(v["act_id"], v["slug"], v["language"]) for v in rows}),
    }


TABLE = DerivedTable(file=FILE, schema=SCHEMA, json_schema="section_version.schema.json",
                     build=build, coverage=coverage)
