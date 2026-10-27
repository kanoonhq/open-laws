"""Acts stage: work_id, doc_type and Act-level dates (PROCUREMENT_PLAN §2.1)."""

from __future__ import annotations

import re

import pyarrow as pa

from enrich import Coverage, Row, Rows
from enrich.dates import MONTHS, iso_date

FIELDS = [
    pa.field("work_id", pa.string()),
    pa.field("doc_type", pa.string()),
    pa.field("assent_date", pa.string()),
    pa.field("commencement_date", pa.string()),
    pa.field("repeal_date", pa.string()),
    pa.field("savings_clause", pa.string()),
]

# "[27th March, 1855.]": ordinal day, month name, year. Spaces and commas
# between the parts are optional ("[22ndMay,1993.]", "[14th, September, 2001.]").
ENACTMENT_DATE = re.compile(r"(\d{1,2})(?:st|nd|rd|th)?[\s,]*([A-Za-z]+)[\s,]*(\d{4})")
# repeal_reason: "Repealed and replaced by Bharatiya Nyaya Sanhita, 2023 (Act No. 45
# of 2023) w.e.f. 01-07-2024 (with savings under s. 358)"
REPEAL_WEF = re.compile(r"w\.\s*e\.\s*f\.?\s*(\d{1,2})\s*-\s*(\d{1,2})\s*-\s*(\d{4})")
SAVINGS = re.compile(r"savings\s+under\s+s(?:ection|\.)\s*(\d+[A-Z]*)")
REPLACED_BY = re.compile(r"replaced\s+by\s+(?:the\s+)?([^,(]+?),?\s+\d{4}")


def act_id_for(year: str | int, number: str | int) -> str:
    """Act {number} of {year} -> its act_id, e.g. (1860, 45) -> A1860-45."""
    return f"A{int(year)}-{int(number)}"


def work_id(act_id: str) -> str:
    """A1860-45 -> in-central/act/1860/45 (no zero-padding)."""
    year, number = act_id.removeprefix("A").split("-")
    return f"in-central/act/{int(year)}/{int(number)}"


def assent_date(enactment_date: str | None) -> str | None:
    """'[6th October, 1860.]' -> '1860-10-06'; None when unparseable."""
    match = ENACTMENT_DATE.search(enactment_date or "")
    if not match or (month := MONTHS.get(match[2].lower())) is None:
        return None
    return iso_date(match[3], month, match[1])


def repeal_date(repeal_reason: str | None) -> str | None:
    """'... w.e.f. 01-07-2024 ...' -> '2024-07-01'."""
    match = REPEAL_WEF.search(repeal_reason or "")
    return iso_date(match[3], match[2], match[1]) if match else None


def savings_clause(repeal_reason: str | None) -> str | None:
    """'replaced by Bharatiya Nyaya Sanhita, 2023 ... (with savings under s. 358)'
    -> 'BNS s. 358': the replacing Act's initials plus the savings section."""
    savings = SAVINGS.search(repeal_reason or "")
    if not savings:
        return None
    replaced_by = REPLACED_BY.search(repeal_reason or "")
    if not replaced_by:
        return f"s. {savings[1]}"
    initials = "".join(word[0] for word in replaced_by[1].split() if word[0].isupper())
    return f"{initials} s. {savings[1]}"


def date_fields(act: Row) -> Row:
    repealed = act["is_repealed"]
    return {
        "assent_date": assent_date(act["enactment_date"]),
        "commencement_date": None,  # populated by the source census, not v0.2.0
        "repeal_date": repeal_date(act["repeal_reason"]) if repealed else None,
        "savings_clause": savings_clause(act["repeal_reason"]) if repealed else None,
    }


def enrich(acts: Rows) -> tuple[Rows, Coverage]:
    """Add work_id, doc_type and the Act-level dates to every Central Act."""
    rows = [
        {**act, "work_id": work_id(act["act_id"]), "doc_type": "act", **date_fields(act)}
        for act in acts
    ]
    return rows, coverage(rows)


def coverage(rows: Rows) -> Coverage:
    """The Acts stage's manifest coverage, from enriched Act rows."""
    return {"acts_with_assent_date": sum(r["assent_date"] is not None for r in rows)}
