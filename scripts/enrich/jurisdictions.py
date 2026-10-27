"""
jurisdictions stage (spec #10, ticket #13; PROCUREMENT_PLAN §2.2 Table 6).

Built from two curated sources, not from the corpus:

- curated/jurisdictions.csv: one row per jurisdiction with validity interval,
  succession links and the corpus provisions that establish it.
- curated/iso_aliases.csv: former ISO 3166-2:IN codes, each resolving to one
  jurisdiction; folded into that row's iso_aliases.

Both files pin the ISO 3166-2:IN version and the verification date in their
`# key: value` header; every row carries them as iso_version/iso_verified_on.
Inconsistent sources (unknown link, overlapping alias, a successor that does not
start the day its predecessor ends) fail the build.

Later stages map names and codes with code_for_name() and resolve_code() over
the built rows (tables[FILE]), e.g. a STATE AMENDMENT heading "Madras" -> IN-TN.
"""

from __future__ import annotations

import csv
import re
from collections.abc import Iterable, Mapping
from pathlib import Path

import pyarrow as pa

from enrich import CURATED_DIR, Coverage, DerivedTable, Row, Rows

FILE = "jurisdictions.parquet"
JURISDICTIONS_CSV = "jurisdictions.csv"
ALIASES_CSV = "iso_aliases.csv"
TYPES = ("union", "state", "union_territory")
ISO_STATUSES = ("verified", "unverified", "none")
STRING, STRINGS = pa.string(), pa.list_(pa.string())
SCHEMA = pa.schema([
    ("code", STRING), ("name", STRING), ("other_names", STRINGS), ("type", STRING),
    ("valid_from", STRING), ("valid_to", STRING), ("successor_of", STRINGS),
    ("inherited_laws_from", STRINGS), ("iso_code", STRING), ("iso_status", STRING),
    ("iso_aliases", STRINGS), ("iso_version", STRING), ("iso_verified_on", STRING),
    ("legal_basis", STRINGS), ("source_url", STRING), ("notes", STRING),
])
LIST_COLUMNS = ("other_names", "successor_of", "inherited_laws_from", "legal_basis")
HEADER = re.compile(r"#\s*([a-z0-9_]+):\s*(.+?)\s*$")


def read_curated(path: Path) -> tuple[dict[str, str], list[dict[str, str]]]:
    """(the `# key: value` header, the CSV rows) of a curated file."""
    lines = path.read_text(encoding="utf-8").splitlines()
    header = {m[1]: m[2] for line in lines if (m := HEADER.match(line))}
    body = [line for line in lines if not line.startswith("#")]
    return header, list(csv.DictReader(body))


def split(value: str) -> list[str]:
    return [v.strip() for v in value.split("|") if v.strip()]


def load(curated_dir: Path = CURATED_DIR) -> Rows:
    """The jurisdictions rows from the curated sources; raises ValueError when
    the sources are inconsistent."""
    header, records = read_curated(curated_dir / JURISDICTIONS_CSV)
    alias_header, alias_records = read_curated(curated_dir / ALIASES_CSV)
    version, verified_on = header["iso_3166_2_version"], header["iso_verified_on"]
    if (alias_header["iso_3166_2_version"], alias_header["iso_verified_on"]) != (version, verified_on):
        raise ValueError(f"{ALIASES_CSV} pins a different ISO version or verification date")

    aliases: dict[str, list[str]] = {}
    for a in alias_records:
        aliases.setdefault(a["code"], []).append(a["alias"])
    rows = []
    for r in records:
        row: Row = {k: (v or None) for k, v in r.items()}
        row.update({k: split(r[k]) for k in LIST_COLUMNS})
        row["iso_code"] = r["code"] if r["iso_status"] != "none" else None
        row["iso_aliases"] = aliases.get(r["code"], [])
        row["iso_version"], row["iso_verified_on"] = version, verified_on
        rows.append({name: row[name] for name in SCHEMA.names})
    codes = {j["code"] for j in rows}
    errors = [f"{ALIASES_CSV}: {a['alias']} resolves to unknown code {a['code']}"
              for a in alias_records if a["code"] not in codes]
    errors += consistency_errors(rows)
    if errors:
        raise ValueError("curated jurisdictions: " + "; ".join(errors))
    return rows


def repeated_values(values: Iterable[str]) -> list[str]:
    """The values that occur more than once, sorted."""
    seen: set[str] = set()
    return sorted({v for v in values if v in seen or seen.add(v)})


def consistency_errors(rows: Rows) -> list[str]:
    """Codes or aliases that clash, links that do not resolve, and intervals
    that contradict a succession link."""
    by_code = {j["code"]: j for j in rows}
    errors = [f"duplicate code {c}" for c in repeated_values(j["code"] for j in rows)]
    aliases = [a for j in rows for a in j["iso_aliases"]]
    errors += [f"alias {a} is given twice" for a in repeated_values(aliases)]
    errors += [f"alias {a} is also a jurisdiction code" for a in sorted(set(aliases) & by_code.keys())]
    for j in rows:
        if j["valid_from"] and j["valid_to"] and j["valid_from"] >= j["valid_to"]:
            errors.append(f"{j['code']}: valid_from {j['valid_from']} is not before valid_to {j['valid_to']}")
        for column in ("successor_of", "inherited_laws_from"):
            errors += [f"{j['code']}: {column} {c} is not a jurisdiction code"
                       for c in j[column] if c not in by_code]
        for c in j["successor_of"]:
            if c in by_code and by_code[c]["valid_to"] != j["valid_from"]:
                errors.append(f"{j['code']}: starts {j['valid_from']} but its predecessor {c} "
                              f"ends {by_code[c]['valid_to']}")
    return errors


def build(tables: Mapping[str, Rows]) -> Rows:
    return load()


def normalise_name(name: str) -> str:
    """'KARNATAKA.—', 'State of Bombay', 'Union territory of Delhi:' -> the bare
    lower-case name, for matching STATE AMENDMENT headings."""
    text = " ".join(name.replace("&", " and ").split()).casefold()
    text = re.sub(r"^(?:the\s+)?(?:state|union\s+territory)\s+of\s+", "", text)
    return text.strip(" .,:;-—–")


def names_of(jurisdiction: Row) -> list[str]:
    """Its name and other_names."""
    return [jurisdiction["name"], *jurisdiction["other_names"]]


def named(rows: Rows, name: str) -> Rows:
    """The jurisdictions whose name or one of whose other_names is `name`
    (compared by normalise_name), in table order."""
    key = normalise_name(name)
    return [j for j in rows if key in {normalise_name(n) for n in names_of(j)}]


def code_for_name(rows: Rows, name: str, on: str | None = None) -> str | None:
    """The code of the jurisdiction called `name` (its name or one of its
    other_names, see normalise_name), or None.

    With `on` (YYYY-MM-DD), only a jurisdiction valid on that date matches, so
    "Punjab" gives IN-HIST-PUNJAB on 1960-01-01 and IN-PB on 1970-01-01. Without
    it a name shared by a current and a historical unit gives the current one;
    a name only historical units bear (Bombay) gives that unit."""
    matches = named(rows, name)
    if on is not None:
        matches = [j for j in matches
                   if (j["valid_from"] is None or j["valid_from"] <= on)
                   and (j["valid_to"] is None or on < j["valid_to"])]
    elif len(matches) > 1:
        matches = [j for j in matches if j["valid_to"] is None]
    return matches[0]["code"] if len(matches) == 1 else None


def resolve_code(rows: Rows, code: str) -> str | None:
    """A jurisdiction code, or a former ISO code via iso_aliases, -> its code."""
    for j in rows:
        if code == j["code"] or code in j["iso_aliases"]:
            return j["code"]
    return None


def coverage(rows: Rows) -> Coverage:
    return {"jurisdictions": {
        "rows": len(rows),
        "current": sum(j["valid_to"] is None for j in rows),
        "historical": sum(j["valid_to"] is not None for j in rows),
        "iso_verified": sum(j["iso_status"] == "verified" for j in rows),
        "iso_unverified": sorted(j["code"] for j in rows if j["iso_status"] == "unverified"),
        "iso_aliases": sum(len(j["iso_aliases"]) for j in rows),
        "inconsistencies": len(consistency_errors(rows)),
    }}


TABLE = DerivedTable(file=FILE, schema=SCHEMA, json_schema="jurisdiction.schema.json",
                     build=build, coverage=coverage)
