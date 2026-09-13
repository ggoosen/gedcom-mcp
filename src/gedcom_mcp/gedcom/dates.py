"""Date helpers built on ged4py's GEDCOM date parser."""

from __future__ import annotations

import datetime as _dt
import re

from ged4py.date import DateValue

_YEAR_RE = re.compile(r"\b(\d{4})\b")
_MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


def year_of(value: str | None) -> int | None:
    """Best-effort year for a GEDCOM DATE value (first year of a range/period)."""
    if not value:
        return None
    try:
        d = DateValue.parse(value)
    except Exception:  # ged4py is lenient, but be safe
        d = None
    if d is not None:
        for attr in ("date", "date1"):
            cal = getattr(d, attr, None)
            if cal is not None and getattr(cal, "year", None):
                return int(cal.year)
    m = _YEAR_RE.search(value)
    return int(m.group(1)) if m else None


def normalize(value: str) -> str:
    """Canonical GEDCOM rendering of a date value (``12 MAR 1840``), or the input if unparsable."""
    try:
        d = DateValue.parse(value)
    except Exception:
        return value.strip()
    if getattr(d, "phrase", None) is not None:
        return value.strip()
    s = str(d)
    # ged4py spells modifiers out ("ABOUT", "BETWEEN"); GEDCOM wants the 3-letter forms.
    for long, short in (
        ("BETWEEN ", "BET "),
        ("ABOUT ", "ABT "),
        ("BEFORE ", "BEF "),
        ("AFTER ", "AFT "),
        ("CALCULATED ", "CAL "),
        ("ESTIMATED ", "EST "),
    ):
        if s.startswith(long):
            s = short + s[len(long) :]
    return s


def today_gedcom() -> str:
    t = _dt.date.today()
    return f"{t.day} {_MONTHS[t.month - 1]} {t.year}"


def now_gedcom_time() -> str:
    return _dt.datetime.now().strftime("%H:%M:%S")
