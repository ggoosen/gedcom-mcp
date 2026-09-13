"""Personal-name helpers: GEDCOM ``Given /Surname/ Suffix`` parsing and fuzzy folding."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_NAME_RE = re.compile(r"^(?P<given>[^/]*?)\s*(?:/(?P<surname>[^/]*)/\s*(?P<suffix>.*))?$")


@dataclass(frozen=True)
class ParsedName:
    given: str
    surname: str
    suffix: str

    @property
    def display(self) -> str:
        parts = [p for p in (self.given, self.surname, self.suffix) if p]
        return " ".join(parts) or "(unknown)"

    @property
    def gedcom(self) -> str:
        return f"{self.given} /{self.surname}/{(' ' + self.suffix) if self.suffix else ''}".strip()


def parse_name(value: str) -> ParsedName:
    m = _NAME_RE.match(value.strip())
    if not m:
        return ParsedName(value.strip(), "", "")
    return ParsedName(
        (m.group("given") or "").strip(),
        (m.group("surname") or "").strip(),
        (m.group("suffix") or "").strip(),
    )


def fold(s: str | None) -> str:
    """Lower-case, strip accents and collapse whitespace so 'Müller' matches 'muller'."""
    if not s:
        return ""
    nfkd = unicodedata.normalize("NFKD", s)
    stripped = "".join(ch for ch in nfkd if not unicodedata.combining(ch))
    return " ".join(stripped.lower().split())
