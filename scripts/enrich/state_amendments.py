"""
state_amendments stage (spec #10, ticket #16; PROCUREMENT_PLAN §2.2 Table 7,
§5 Phase 3 bootstrap).

Parses the "STATE AMENDMENT(S)" blocks printed inside Central Act section text
into one row per state entry. Section text is left unchanged.

- Block: from the first "STATE AMENDMENT" header to the end of the section.
- Entries: each `[Vide …]` reference closes one entry. A later header inside
  an entry's text drops the host-section text printed before it. Text after
  the last reference is an entry (with a null reference) only when it starts
  with a header or a state name; otherwise it is host text (e.g. the next
  section's heading) and is not a row.
- State: the state-name heading that opens the entry ("Kerala", "Orissa.—",
  "Union territories of A, B and C"), one row per named jurisdiction; with no
  heading, the State named in the reference ("[Vide Orissa Act 21 of 1958]").
  Names map through the jurisdictions table, only to a unit that existed for
  the whole year of the reference (so "Madhya Pradesh" in 1995 is the
  undivided State); with no year, only a name borne by one unit maps.
  An unknown or ambiguous name gives a null state_jurisdiction.
- amendment_type: from the verbs of the instruction (text before "namely",
  quotations removed): substitution, insertion, omission, or proviso for an
  inserted proviso. No verb, or verbs of several kinds, gives null.
- section_number: the section the entry names in its heading ("Amendment of
  section 24", "Section 24.—") or opening words ("In sub-section (6) of
  section 24"), else null.
- effective_date: a `(w.e.f. …)` date in or just after the reference, else null.
- valid_to: 2024-07-01 for CrPC rows (closed at the BNSS transition), else null.
- id: {central_act_id}:s{section slug}:{code | unmapped}, -2, -3, ... on collision.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping

import pyarrow as pa

from enrich import Coverage, DerivedTable, Row, Rows
from enrich import jurisdictions as jurisdictions_stage
from enrich.dates import MONTHS, iso_date
from enrich.jurisdictions import code_for_name, normalise_name
from table_files import SECTIONS

FILE = "state_amendments.parquet"
TYPES = ("substitution", "insertion", "omission", "proviso")
CLOSED_AT_TRANSITION = {"A1974-2": "2024-07-01"}  # CrPC -> BNSS
STRING = pa.string()
SCHEMA = pa.schema([
    ("id", STRING), ("central_act_id", STRING), ("section_id", STRING), ("section_slug", STRING),
    ("section_number", STRING), ("state_name", STRING), ("state_jurisdiction", STRING),
    ("state_act_reference", STRING), ("amendment_type", STRING), ("amended_text", STRING),
    ("raw_text", STRING), ("effective_date", STRING), ("valid_to", STRING), ("source_url", STRING),
])

HEADER = re.compile(r"STATE AMENDMENTS?\b")
# A reference, with a trailing "." and "(w.e.f. …)" printed after it.
REFERENCE = re.compile(r"\[\s*vide\b\s*([^\]]*)\]\s*\.?(?:\s*\((w\.e\.f\.[^)]*)\))?", re.I)
WEF = re.compile(r"w\.e\.f\.?\s*([^)\]]+)", re.I)
NUMERIC_DATE = re.compile(r"(\d{1,2})\s*[./-]\s*(\d{1,2})\s*[./-]\s*(\d{4})")
WORDS_DATE = re.compile(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+),?\s+(\d{4})")
YEAR = re.compile(r"\b(1[89]\d\d|20\d\d)\b")
LEADING_JUNK = re.compile(r"^[\s\d]*\[|^[\s.―“\"]+")
QUOTATION = re.compile(r"“[^“”]*”|―[^―‖]*‖|\"[^\"]*\"|‘[^‘’]*’")
UNIT_PREFIX = r"(?:the\s+)?(?:union\s+territor(?:y|ies)|state)\s+of\s+"
UNIT_SUFFIX = r"(?:\s*\((?:UTs?|U\.T\.)\)|\s+U\.T\.?)?"
SEPARATOR = re.compile(r"\s*(?:,\s*(?:and\s+)?|\s+and\s+|\s*&\s*)", re.I)
# What may follow a heading: punctuation, a line break, or a capitalised word.
HEADING_END = re.compile(r"\s*(?:$|[.:,;—–-]|\n|\s+(?=[A-Z(\[―“\"]))")
VERBS = {
    "substitution": re.compile(r"\bsubstitut(?:ed|e|ion)\b", re.I),
    "insertion": re.compile(r"\b(?:insert(?:ed|ion)?|add(?:ed|ition)?)\b", re.I),
    "omission": re.compile(r"\b(?:omit(?:ted)?|omission|delet(?:ed|e|ion))\b", re.I),
}
INSERTED_PROVISO = re.compile(
    r"\b(?:following|new)\s+provisos?\b|\bprovisos?\s+(?:shall\s+be\s+)?(?:inserted|added)\b", re.I)
SECTION = r"section\s+(\d+[A-Z]*(?:-[A-Z]+)?)\b(?!\s*(?:,|and|to)\s*\d)"
HEADING_SECTION = re.compile(
    r"^(?:(?:Amendments?|Substitution|Insertion|Omission|Addition)\s+(?:of\s+)?(?:in\s+)?(?:a\s+)?"
    r"(?:new\s+)?" + SECTION + r"|Section\s+(\d+[A-Z]*(?:-[A-Z]+)?)\s*\.?\s*[—–-])", re.I)
OPENING_SECTION = re.compile(
    r"^(?:In|For|To)\s+(?:the\s+)?(?:(?:first\s+|second\s+)?(?:proviso|clause|sub-?\s?section|"
    r"explanation)\b[^,;:—]*?\s+of\s+)?" + SECTION, re.I)
PRINCIPAL_ACT = re.compile(r"^In\s+the\s+(?:principal\s+Act|Code|said\s+Act)\s*,\s*(?=(?:in|for)\b)", re.I)


def name_pattern(jurisdictions: Rows) -> re.Pattern[str]:
    """Any State/UT name or other name, longest first, case- and space-insensitive."""
    names = {n for j in jurisdictions if j["type"] != "union" for n in [j["name"], *j["other_names"]]}
    alternatives = [r"\s+".join(map(re.escape, n.split())) for n in sorted(names, key=len, reverse=True)]
    return re.compile(rf"(?:{UNIT_PREFIX})?({'|'.join(alternatives)}){UNIT_SUFFIX}", re.I)


def heading(text: str, names: re.Pattern[str]) -> tuple[list[str], int]:
    """(the jurisdiction names that open text, where the heading ends) or ([], 0)."""
    found, pos = [], 0
    while m := names.match(text, pos):
        found.append(" ".join(m[1].split()))
        pos = m.end()
        sep = SEPARATOR.match(text, pos)
        if not (sep and names.match(text, sep.end())):
            break
        pos = sep.end()
    if not found or not HEADING_END.match(text, pos):
        return [], 0
    return found, pos


def resolve(jurisdictions: Rows, name: str, reference: str | None) -> str | None:
    """The code of `name`, valid for the whole year the reference cites; with no
    year, only when one unit bears the name."""
    year = YEAR.search(reference or "")
    if year:
        first = code_for_name(jurisdictions, name, on=f"{year[1]}-01-01")
        return first if first == code_for_name(jurisdictions, name, on=f"{year[1]}-12-31") else None
    key = normalise_name(name)
    units = [j["code"] for j in jurisdictions
             if key in {normalise_name(n) for n in [j["name"], *j["other_names"]]}]
    return units[0] if len(units) == 1 else None


def amendment_type(text: str) -> str | None:
    instruction = QUOTATION.sub(" ", re.split(r"\bnamely\b", text, maxsplit=1)[0])
    kinds = [kind for kind, verb in VERBS.items() if verb.search(instruction)]
    if len(kinds) != 1:
        return None
    insertions = len(VERBS["insertion"].findall(instruction))
    if kinds == ["insertion"] and len(INSERTED_PROVISO.findall(instruction)) == insertions:
        return "proviso"  # every insertion is of a proviso
    return kinds[0]


def section_number(text: str) -> str | None:
    text = text.lstrip("―“\"‘ ")
    rest = PRINCIPAL_ACT.sub("", text)  # "In the principal Act, in section 5, ..."
    m = HEADING_SECTION.match(text) or OPENING_SECTION.match(rest)
    return next((g.upper() for g in m.groups() if g), None) if m else None


def effective_date(reference: str, after: str | None) -> str | None:
    wef = WEF.search(reference) or (WEF.search(after) if after else None)
    if not wef:
        return None
    if m := NUMERIC_DATE.search(wef[1]):
        return iso_date(m[3], m[2], m[1])
    if (m := WORDS_DATE.search(wef[1])) and m[2].lower() in MONTHS:
        return iso_date(m[3], MONTHS[m[2].lower()], m[1])
    return None


def entries(text: str, names: re.Pattern[str]) -> list[tuple[str, re.Match[str] | None, str]]:
    """(entry text, its reference match or None, the entry as printed) for each
    entry of the block."""
    start = HEADER.search(text)
    if not start:
        return []
    block = text[start.start():]
    spans, pos = [], 0  # (start, end of text, reference)
    for ref in REFERENCE.finditer(block):
        spans.append((pos, ref.start(), ref))
        pos = ref.end()
    body = LEADING_JUNK.sub("", block[pos:].strip())
    if HEADER.match(body) or heading(body, names)[0]:
        spans.append((pos, len(block), None))
    out = []
    for begin, end, ref in spans:
        headers = list(HEADER.finditer(block, begin, end))
        if headers:
            begin = headers[-1].end()
        out.append((block[begin:end], ref, block[begin:ref.end() if ref else end].strip()))
    return out


def rows_for_section(section: Row, jurisdictions: Rows, names: re.Pattern[str]) -> Rows:
    rows = []
    for body, ref, raw in entries(section["full_text"] or "", names):
        text = LEADING_JUNK.sub("", body.strip())
        reference = " ".join(ref[1].split()).rstrip(". ") if ref else None
        if reference and reference.lower().startswith("the "):
            reference = reference[4:]
        state_names, end = heading(text, names)
        amended = text[end:].lstrip(" \n.:,;—–-") if state_names else text
        if not state_names and reference:
            state_names = heading(reference, names)[0][:1]
        common = {
            "central_act_id": section["act_id"],
            "section_id": section["id"],
            "section_slug": section["slug"],
            "section_number": section_number(amended),
            "state_act_reference": reference or None,
            "amendment_type": amendment_type(amended),
            "amended_text": amended.strip() or None,
            "raw_text": raw,
            "effective_date": effective_date(ref[1], ref[2]) if ref else None,
            "valid_to": CLOSED_AT_TRANSITION.get(section["act_id"]),
            "source_url": None,  # the v0.1.1 corpus records no per-section URL
        }
        for name in state_names or [None]:
            code = resolve(jurisdictions, name, reference) if name else None
            rows.append({"state_name": name, "state_jurisdiction": code, **common})
    return rows


def build(tables: Mapping[str, Rows]) -> Rows:
    jurisdictions = tables[jurisdictions_stage.FILE]
    names = name_pattern(jurisdictions)
    used: set[str] = set()
    out: Rows = []
    for section in tables[SECTIONS]:
        for row in rows_for_section(section, jurisdictions, names):
            base = f"{row['central_act_id']}:s{row['section_slug']}:{row['state_jurisdiction'] or 'unmapped'}"
            row_id, n = base, 1
            while row_id in used:
                n += 1
                row_id = f"{base}-{n}"
            used.add(row_id)
            out.append({name: ({"id": row_id, **row})[name] for name in SCHEMA.names})
    return out


def parsed(row: Row) -> bool:
    return all(row[k] is not None for k in ("state_jurisdiction", "state_act_reference", "amendment_type"))


def coverage(rows: Rows) -> Coverage:
    states = Counter(r["state_jurisdiction"] or "unmapped" for r in rows)
    types = Counter(r["amendment_type"] or "untyped" for r in rows)
    return {"state_amendments": {
        "rows": len(rows),
        "parsed": sum(map(parsed, rows)),
        "raw": sum(not parsed(r) for r in rows),
        "sections": len({r["section_id"] for r in rows}),
        "without_reference": sum(r["state_act_reference"] is None for r in rows),
        "by_state": dict(sorted(states.items())),
        "by_type": {t: types[t] for t in (*TYPES, "untyped")},
        "unmapped_state_names": sorted({r["state_name"] for r in rows
                                        if r["state_jurisdiction"] is None and r["state_name"]}),
    }}


TABLE = DerivedTable(file=FILE, schema=SCHEMA, json_schema="state_amendment.schema.json",
                     build=build, coverage=coverage)
