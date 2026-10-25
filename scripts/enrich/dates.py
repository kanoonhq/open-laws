"""Calendar dates shared by the stages and the validator. Never guessed: an
impossible date (v0.1.1 carries some, such as 1959-19-01) gives None."""

from __future__ import annotations

from datetime import date

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], start=1)}


def iso_date(year: int | str, month: int | str, day: int | str) -> str | None:
    """YYYY-MM-DD for a real calendar date, else None."""
    try:
        return date(int(year), int(month), int(day)).isoformat()
    except ValueError:
        return None


def calendar_date(value: str | None) -> str | None:
    """value when it is a real calendar date written YYYY-MM-DD, else None."""
    try:
        return value if value and date.fromisoformat(value).isoformat() == value else None
    except ValueError:
        return None
