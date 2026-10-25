"""
Footnotes stage: footnote -> section linkage and w.e.f. parsing (spec #1, ticket #4).

India Code numbers footnotes from 1 on every PDF page, and the section text
carries the matching inline markers: `N[` (inserted/substituted text), `N***`
(omitted text) and a trailing `N` glued to a word (`on such date3`). Sections
carry no page numbers, so each Act is aligned in three steps:

1. Marker runs: the Act's markers in section order, split wherever the
   numbering resets (a drop to 1, or to a number not yet seen in the run; a
   drop to a number already seen is a repeated reference to that footnote).
2. Page alignment: runs are matched monotonically to the Act's footnote pages
   by dynamic programming, scoring the footnote numbers each run explains (a
   marker whose kind agrees with the footnote's amendment counts double). A run
   is only kept when its page is the same in every best alignment.
3. Links: a footnote whose number has markers in exactly one section of its
   page's run is `inline_marker`; an unlinked footnote between two
   `inline_marker` links to the same section on the same page is `page_order`. Everything else is `act_level` with no slug.

Never guess: any ambiguity (a tie between pages, a number marked in two
sections) leaves the footnote at `act_level`.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date
from typing import Any

import pyarrow as pa

from enrich import Coverage, Row, Rows

FIELDS = [
    pa.field("section_slug", pa.string()),
    pa.field("linkage_method", pa.string()),
]
INLINE, PAGE_ORDER, ACT_LEVEL = "inline_marker", "page_order", "act_level"
METHODS = (INLINE, PAGE_ORDER, ACT_LEVEL)

# --- w.e.f. dates -----------------------------------------------------------

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], start=1)}
_WEF = r"w\s*\.?\s*e\s*\.?\s*f\s*[.,]*[\s.,]*(?:dated\s+)?"
WEF_NUMERIC = re.compile(_WEF + r"(\d{1,2})\s*[-./]\s*(\d{1,2})\s*[-./]\s*(\d{4})(?!\d)", re.I)
WEF_WORDS = re.compile(_WEF + r"(\d{1,2})(?:st|nd|rd|th)?\s+(?:day\s+of\s+)?([A-Za-z]+)\.?,?\s*(\d{4})(?!\d)",
                       re.I)


def run_in_footnotes(footnote: Row) -> list[int]:
    """Offsets in raw_text where later footnotes run into this one start
    ("9. Subs. ... (w.e.f. 21-7-1978).10. Ins. ..." gives the offset of "10.")."""
    starts: list[int] = []
    text, pos = footnote["raw_text"], 0
    while m := re.compile(rf"(?<!\d){footnote['footnote_number'] + len(starts) + 1}\.\s*"
                          r"(?=[A-Z“\"‘])").search(text, pos):
        starts.append(m.start())
        pos = m.end()
    return starts


def own_text(footnote: Row) -> str:
    """raw_text without the later footnotes run into it."""
    starts = run_in_footnotes(footnote)
    return footnote["raw_text"][: starts[0]] if starts else footnote["raw_text"]


def parse_wef(text: str) -> str | None:
    """The first valid w.e.f. date in text as YYYY-MM-DD, tolerating spaces and
    separators inside it: `w.e.f. 31-10- 2019`, `w.e.f. 1-7-2024`, `w.e.f. 1st July, 2024`."""
    found = []
    for m in WEF_NUMERIC.finditer(text):
        found.append((m.start(), int(m.group(3)), int(m.group(2)), int(m.group(1))))
    for m in WEF_WORDS.finditer(text):
        if (month := MONTHS.get(m.group(2).lower())) is not None:
            found.append((m.start(), int(m.group(3)), month, int(m.group(1))))
    for _, year, month, day in sorted(found):
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            continue
    return None


def calendar_date(value: str | None) -> str | None:
    """value when it is a real YYYY-MM-DD calendar date, else None (never guessed:
    v0.1.1 carries a few such as 1959-19-01)."""
    try:
        return value if value and date.fromisoformat(value).isoformat() == value else None
    except ValueError:
        return None


# --- inline markers ---------------------------------------------------------

BRACKET_OR_STARS = re.compile(r"(?<![\w.(/-])(\d{1,3})(\[|\s?\*(?:\s?\*){2,})")
# A footnote number glued to a word or closing bracket: "on such date3 as".
TRAILING = re.compile(r"(?:(?<![A-Za-z])([a-z]{3,})|[\])”])(\d{1,2})(?=[\s,;:\])”’—]|\.(?!\d)|$)")
# Words a glued number usually belongs to ("section73" is section 73).
NOT_A_MARKER = {
    "act", "annexure", "appendix", "article", "articles", "chapter", "clause", "clauses",
    "column", "entries", "entry", "explanation", "form", "item", "items", "list", "note",
    "order", "page", "paragraph", "part", "regulation", "rule", "schedule", "section",
    "sections", "serial", "table", "vol",
}
# A Schedule run into a section's text: "THE FIRST SCHEDULE", "1[THE SCHEDULE".
SCHEDULE_HEADING = re.compile(r"^\s*(?:\d+\[)?\s*(?:THE\s+)?(?:[A-Z]+\s+)?SCHEDULE\b", re.M)
# (section index, or None for text after a Schedule heading; footnote number; kind)
Marker = tuple[int | None, int, str]


def markers(text: str) -> list[tuple[int, int, str]]:
    """(offset, number, kind) of every inline footnote marker in text, in text order."""
    found = [(m.start(), int(m.group(1)), "stars" if "*" in m.group(2) else "bracket")
             for m in BRACKET_OR_STARS.finditer(text)]
    found += [(m.start(2), int(m.group(2)), "trailing") for m in TRAILING.finditer(text)
              if m.group(1) not in NOT_A_MARKER]
    return [marker for marker in sorted(found) if marker[1] > 0]


def marker_runs(sections: Rows, max_number: int) -> list[list[Marker]]:
    """The Act's markers in section order, split where the page numbering resets."""
    runs: list[list[Marker]] = []
    run: list[Marker] = []
    seen: set[int] = set()
    for index, section in enumerate(sections):
        text = section["full_text"] or ""
        schedule = SCHEDULE_HEADING.search(text)
        for offset, number, kind in markers(text):
            if number > max_number:  # no page has that many footnotes: not a marker
                continue
            if run and number < run[-1][1] and (number == 1 or number not in seen):
                runs.append(run)
                run, seen = [], set()
            # Markers in a Schedule still pace the pages but link to no section.
            run.append((None if schedule and offset > schedule.start() else index, number, kind))
            seen.add(number)
    return [*runs, run] if run else runs


# --- page alignment ---------------------------------------------------------

OMITTED = re.compile(r"\b(?:omitted|rep\.|repealed)\b", re.I)
INSERTED = re.compile(r"^\s*\d+\.\s*(?:Ins|Subs)\.")


class Page:
    """One PDF page of an Act's footnotes, numbered from 1."""

    def __init__(self, footnotes: list[tuple[int, Row]]) -> None:
        numbers = [f["footnote_number"] for _, f in footnotes]
        self.usable = len(set(numbers)) == len(numbers)
        self.by_number = {f["footnote_number"]: (i, f) for i, f in footnotes}
        self.count = max(numbers)
        # Footnotes run into the last one's text still have markers in the sections.
        self.capacity = self.count + len(run_in_footnotes(self.by_number[self.count][1]))


def agreement(kind: str, raw_text: str) -> int:
    """Evidence weight of a marker for a footnote: 2 agree, 1 neutral, 0 conflict."""
    inserted = bool(INSERTED.search(raw_text))
    if kind == "stars":
        return 0 if inserted else 2 if OMITTED.search(raw_text) else 1
    if kind == "bracket":
        return 2 if inserted else 1
    return 1


def score(run: list[Marker], page: Page) -> float:
    """How well a run explains a page; -inf when it cannot be that page's run."""
    top = max(number for _, number, _ in run)
    # A run must stay within the page and reach at least half of its footnotes.
    if not page.usable or top > page.capacity or 2 * top < page.count:
        return float("-inf")
    best: dict[int, int] = {}
    for _, number, kind in run:
        if number in page.by_number:
            weight = agreement(kind, page.by_number[number][1]["raw_text"])
            best[number] = max(best.get(number, 0), weight)
    return sum(best.values())


def align(runs: list[list[Marker]], pages: list[Page]) -> dict[int, int]:
    """run index -> page index, for each run whose page is the same in every
    best monotonic alignment (a run may also be left out, and so may a page)."""
    r, k = len(runs), len(pages)
    s = [[score(run, page) for page in pages] for run in runs]
    # fwd[i][j]: best total for runs[:i] on pages[:j]; bwd[i][j]: runs[i:] on pages[j:].
    fwd = [[0.0] * (k + 1) for _ in range(r + 1)]
    for i in range(1, r + 1):
        for j in range(1, k + 1):
            fwd[i][j] = max(fwd[i - 1][j], fwd[i][j - 1], fwd[i - 1][j - 1] + s[i - 1][j - 1])
    bwd = [[0.0] * (k + 1) for _ in range(r + 1)]
    for i in range(r - 1, -1, -1):
        for j in range(k - 1, -1, -1):
            bwd[i][j] = max(bwd[i + 1][j], bwd[i][j + 1], bwd[i + 1][j + 1] + s[i][j])
    best = fwd[r][k]
    aligned = {}
    for i in range(r):
        placements = [j for j in range(k)
                      if s[i][j] > 0 and fwd[i][j] + s[i][j] + bwd[i + 1][j + 1] == best]
        left_out = max(fwd[i][t] + bwd[i + 1][t] for t in range(k + 1)) == best
        if len(placements) == 1 and not left_out:
            aligned[i] = placements[0]
    return aligned


def link_act(footnotes: list[tuple[int, Row]], sections: Rows) -> dict[int, tuple[str, str]]:
    """footnote index -> (section_slug, method) for one Act's linkable footnotes."""
    by_page: dict[int, list[tuple[int, Row]]] = defaultdict(list)
    for i, f in footnotes:
        if m := re.fullmatch(r"Page (\d+)", f["page_or_anchor"] or ""):
            by_page[int(m.group(1))].append((i, f))
    pages = [Page(by_page[number]) for number in sorted(by_page)]
    if not pages:
        return {}
    runs = marker_runs(sections, max(page.capacity for page in pages))
    links: dict[int, tuple[str, str]] = {}
    aligned = align(runs, pages)
    for run_index, page_index in aligned.items():
        marked: dict[int, set[int | None]] = defaultdict(set)
        for section_index, number, _ in runs[run_index]:
            marked[number].add(section_index)
        for number, (i, _) in pages[page_index].by_number.items():
            where = marked.get(number, set())
            if len(where) == 1 and (section_index := next(iter(where))) is not None:
                links[i] = (sections[section_index]["slug"], INLINE)
    # page_order: footnotes between two inline links to the same section on the
    # same aligned page. Never across a page break: when unsure, no link.
    for page_index in sorted(set(aligned.values())):
        order = [i for _, (i, _) in sorted(pages[page_index].by_number.items())]
        linked = [pos for pos, i in enumerate(order) if i in links]
        for a, b in zip(linked, linked[1:]):
            slug = links[order[a]][0]
            if links[order[b]][0] == slug:
                for pos in range(a + 1, b):
                    links[order[pos]] = (slug, PAGE_ORDER)
    return links


# --- stage ------------------------------------------------------------------


def linkage_coverage(rows: Rows) -> Coverage:
    def linked(group: Rows) -> int:
        return sum(f["linkage_method"] != ACT_LEVEL for f in group)

    by_act: dict[str, Rows] = defaultdict(list)
    for f in rows:
        by_act[f["act_id"]].append(f)
    return {
        "footnote_linkage_rate": round(linked(rows) / len(rows), 4) if rows else 0.0,
        "footnote_links_by_method": {m: sum(f["linkage_method"] == m for f in rows)
                                     for m in METHODS},
        "footnote_linkage_by_act": {
            act_id: {"linked": linked(group), "total": len(group),
                     "rate": round(linked(group) / len(group), 4)}
            for act_id, group in by_act.items()},
    }


def enrich(footnotes: Rows, sections: Rows) -> tuple[Rows, Coverage]:
    """Link footnotes to sections and re-derive wef_date; `sections` arrive in
    document order per Act."""
    sections_by_act: dict[str, Rows] = defaultdict(list)
    for s in sections:
        sections_by_act[s["act_id"]].append(s)
    footnotes_by_act: dict[str, list[tuple[int, Row]]] = defaultdict(list)
    for i, f in enumerate(footnotes):
        footnotes_by_act[f["act_id"]].append((i, f))
    links: dict[int, tuple[str, str]] = {}
    for act_id, act_footnotes in footnotes_by_act.items():
        links.update(link_act(act_footnotes, sections_by_act.get(act_id, [])))

    rows: Rows = []
    for i, f in enumerate(footnotes):
        slug, method = links.get(i, (None, ACT_LEVEL))
        row: dict[str, Any] = {**f, "wef_date": parse_wef(own_text(f)) or calendar_date(f["wef_date"])}
        rows.append({**row, "section_slug": slug, "linkage_method": method})
    return rows, linkage_coverage(rows)
