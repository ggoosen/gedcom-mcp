"""Lossless GEDCOM line tree.

A GEDCOM file is a flat list of ``LEVEL [@XREF@] TAG [VALUE]`` lines. We keep them as a
tree of :class:`GedLine` nodes. Every node remembers its original raw line, and only
nodes that have been mutated are re-rendered on write, so anything we do not touch
(unknown tags, Ancestry ``_APID``s, odd spacing) round-trips byte for byte.

``CONT``/``CONC`` continuation lines are kept as ordinary children; :attr:`GedLine.text`
folds them into one string and :meth:`GedLine.set_text` splits a string back out.
"""

from __future__ import annotations

import io
import re
from collections.abc import Iterator
from dataclasses import dataclass, field

from ged4py.parser import CodecError, guess_codec

# GEDCOM 5.5.1 recommends <= 255 chars per line; keep values comfortably below.
CONC_WIDTH = 240

_LINE_RE = re.compile(r"^\s*(\d+)\s+(?:(@[^@]*@)\s+)?([A-Za-z0-9_]+)(?: (.*))?$")


class GedcomParseError(ValueError):
    pass


class GedLine:
    """One GEDCOM line plus its subordinate lines."""

    __slots__ = ("_level", "_xref", "_tag", "_value", "_raw", "children", "parent")

    def __init__(
        self,
        level: int,
        tag: str,
        value: str = "",
        xref: str | None = None,
        raw: str | None = None,
    ) -> None:
        self._level = level
        self._tag = tag
        self._value = value
        self._xref = xref
        self._raw = raw
        self.children: list[GedLine] = []
        self.parent: GedLine | None = None

    # -- attributes (setters invalidate the cached raw line) -------------------------

    @property
    def level(self) -> int:
        return self._level

    @property
    def tag(self) -> str:
        return self._tag

    @tag.setter
    def tag(self, tag: str) -> None:
        self._tag, self._raw = tag, None

    @property
    def value(self) -> str:
        return self._value

    @value.setter
    def value(self, value: str) -> None:
        self._value, self._raw = value, None

    @property
    def xref(self) -> str | None:
        return self._xref

    @xref.setter
    def xref(self, xref: str | None) -> None:
        self._xref, self._raw = xref, None

    @property
    def is_pointer(self) -> bool:
        v = self._value
        return len(v) > 2 and v.startswith("@") and v.endswith("@") and "@" not in v[1:-1]

    # -- tree navigation ------------------------------------------------------------

    def sub(self, tag: str) -> GedLine | None:
        """First direct child with this tag, or None."""
        for c in self.children:
            if c._tag == tag:
                return c
        return None

    def subs(self, *tags: str) -> list[GedLine]:
        """All direct children whose tag is in ``tags`` (all children if no tags given)."""
        if not tags:
            return list(self.children)
        return [c for c in self.children if c._tag in tags]

    def path(self, dotted: str) -> GedLine | None:
        """Follow a ``TAG/TAG`` path, e.g. ``BIRT/DATE``."""
        node: GedLine | None = self
        for tag in dotted.split("/"):
            if node is None:
                return None
            node = node.sub(tag)
        return node

    def path_value(self, dotted: str) -> str | None:
        node = self.path(dotted)
        return node.text if node is not None else None

    # -- text with continuation lines -----------------------------------------------

    @property
    def text(self) -> str:
        """Value with CONT/CONC children folded in (stray carriage returns dropped)."""
        parts = [self._value]
        for c in self.children:
            if c._tag == "CONT":
                parts.append("\n" + c._value)
            elif c._tag == "CONC":
                parts.append(c._value)
        return "".join(parts).replace("\r", "")

    def set_text(self, text: str) -> None:
        """Replace value and rebuild CONT/CONC children; other children are kept."""
        self.children = [c for c in self.children if c._tag not in ("CONT", "CONC")]
        first, *rest = text.split("\n")
        self.value = first[:CONC_WIDTH]
        cont_children: list[GedLine] = []
        for chunk in _chunks(first[CONC_WIDTH:]):
            cont_children.append(GedLine(self._level + 1, "CONC", chunk))
        for seg in rest:
            cont_children.append(GedLine(self._level + 1, "CONT", seg[:CONC_WIDTH]))
            for chunk in _chunks(seg[CONC_WIDTH:]):
                cont_children.append(GedLine(self._level + 1, "CONC", chunk))
        # continuation lines must come first so they attach to this value
        for i, c in enumerate(cont_children):
            c.parent = self
            self.children.insert(i, c)

    # -- mutation -------------------------------------------------------------------

    def add(self, tag: str, value: str = "", *, index: int | None = None) -> GedLine:
        """Append (or insert) a new child line and return it."""
        child = GedLine(self._level + 1, tag, value)
        child.parent = self
        if index is None:
            self.children.append(child)
        else:
            self.children.insert(index, child)
        return child

    def adopt(self, child: GedLine, *, index: int | None = None) -> GedLine:
        """Attach an existing node (and its subtree), renumbering levels."""
        if child.parent is not None:
            child.parent.children.remove(child)
        child.parent = self
        child._relevel(self._level + 1)
        if index is None:
            self.children.append(child)
        else:
            self.children.insert(index, child)
        return child

    def remove(self) -> None:
        if self.parent is not None:
            self.parent.children.remove(self)
            self.parent = None

    def _relevel(self, level: int) -> None:
        if self._level != level:
            self._level, self._raw = level, None
        for c in self.children:
            c._relevel(level + 1)

    def touch(self) -> None:
        """Force this line to be re-rendered on write."""
        self._raw = None

    # -- rendering ------------------------------------------------------------------

    def render(self) -> str:
        if self._raw is not None:
            return self._raw
        parts = [str(self._level)]
        if self._xref:
            parts.append(self._xref)
        parts.append(self._tag)
        if self._value:
            parts.append(self._value)
        return " ".join(parts)

    def walk(self) -> Iterator[GedLine]:
        yield self
        for c in self.children:
            yield from c.walk()

    def __repr__(self) -> str:  # pragma: no cover
        return f"GedLine({self.render()!r}, {len(self.children)} children)"


def _chunks(s: str) -> list[str]:
    return [s[i : i + CONC_WIDTH] for i in range(0, len(s), CONC_WIDTH)]


@dataclass
class GedDocument:
    """Top-level records plus the byte-level details needed to write the file back."""

    records: list[GedLine] = field(default_factory=list)
    codec: str = "utf-8"
    bom: bytes = b""
    eol: str = "\r\n"
    trailing_eol: bool = True

    # -- lookup ---------------------------------------------------------------------

    def record(self, xref: str) -> GedLine | None:
        for r in self.records:
            if r.xref == xref:
                return r
        return None

    def records_of(self, tag: str) -> list[GedLine]:
        return [r for r in self.records if r.tag == tag]

    @property
    def header(self) -> GedLine | None:
        return next((r for r in self.records if r.tag == "HEAD"), None)

    # -- mutation -------------------------------------------------------------------

    def add_record(self, tag: str, xref: str) -> GedLine:
        rec = GedLine(0, tag, xref=xref)
        # insert before TRLR so the file stays well-formed
        idx = next((i for i, r in enumerate(self.records) if r.tag == "TRLR"), len(self.records))
        self.records.insert(idx, rec)
        return rec

    def remove_record(self, rec: GedLine) -> None:
        self.records.remove(rec)

    def next_xref(self, prefix: str) -> str:
        """Next free ``@<prefix><n>@`` id, e.g. ``@I42@``."""
        pat = re.compile(rf"^@{re.escape(prefix)}(\d+)@$")
        highest = 0
        for r in self.records:
            m = pat.match(r.xref or "")
            if m:
                highest = max(highest, int(m.group(1)))
        return f"@{prefix}{highest + 1}@"

    # -- rendering ------------------------------------------------------------------

    def render(self) -> str:
        lines = [ln.render() for rec in self.records for ln in rec.walk()]
        out = self.eol.join(lines)
        if self.trailing_eol:
            out += self.eol
        return out

    def to_bytes(self) -> bytes:
        return self.bom + self.render().encode(self.codec)


def new_document(source: str = "gedcom-mcp") -> GedDocument:
    """A minimal, valid, empty GEDCOM 5.5.1 document."""
    doc = GedDocument(codec="utf-8", bom=b"", eol="\r\n")
    head = GedLine(0, "HEAD")
    head.add("SOUR", source)
    gedc = head.add("GEDC")
    gedc.add("VERS", "5.5.1")
    gedc.add("FORM", "LINEAGE-LINKED")
    head.add("CHAR", "UTF-8")
    doc.records.append(head)
    doc.records.append(GedLine(0, "TRLR"))
    return doc


def parse_bytes(data: bytes) -> GedDocument:
    try:
        codec, bom_size = guess_codec(io.BytesIO(data), errors="replace", warn=False)
    except CodecError as e:
        raise GedcomParseError(f"Cannot determine file encoding: {e}") from e
    text = data[bom_size:].decode(codec, errors="replace")
    doc = GedDocument(codec=codec, bom=data[:bom_size])
    _parse_text(text, doc)
    return doc


def parse_text(text: str) -> GedDocument:
    doc = GedDocument()
    _parse_text(text, doc)
    return doc


def _detect_eol(text: str) -> str:
    """The dominant line terminator. Stray CRs inside values (Ancestry does this) are ignored."""
    lf = text.count("\n")
    if lf == 0:
        return "\r" if "\r" in text else "\n"
    return "\r\n" if text.count("\r\n") * 2 > lf else "\n"


def _parse_text(text: str, doc: GedDocument) -> None:
    doc.eol = _detect_eol(text)
    doc.trailing_eol = text.endswith(doc.eol)
    if doc.trailing_eol:
        text = text[: -len(doc.eol)]
    stack: list[GedLine] = []
    for lineno, raw in enumerate(text.split(doc.eol), start=1):
        if not raw.strip():
            # Blank lines are not valid GEDCOM. Keep them verbatim under the current line so
            # the file round-trips, but give them no tag so nothing else ever sees them.
            if stack:
                blank = GedLine(stack[-1].level + 1, "", raw=raw)
                blank.parent = stack[-1]
                stack[-1].children.append(blank)
            continue
        m = _LINE_RE.match(raw)
        if not m:
            raise GedcomParseError(f"Line {lineno}: not a GEDCOM line: {raw!r}")
        level = int(m.group(1))
        node = GedLine(level, m.group(3), m.group(4) or "", xref=m.group(2), raw=raw)
        if level == 0:
            doc.records.append(node)
            stack = [node]
            continue
        while stack and stack[-1].level >= level:
            stack.pop()
        if not stack or stack[-1].level != level - 1:
            raise GedcomParseError(f"Line {lineno}: level {level} has no level {level - 1} parent")
        node.parent = stack[-1]
        stack[-1].children.append(node)
        stack.append(node)
