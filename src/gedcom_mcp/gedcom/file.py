"""A GEDCOM file on disk: load, index, stamp changes, save with backup."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from .dates import now_gedcom_time, today_gedcom
from .lines import GedDocument, GedLine, new_document, parse_bytes

if TYPE_CHECKING:
    from .model import Family, Person, Source


class GedcomFile:
    def __init__(self, path: Path, doc: GedDocument) -> None:
        self.path = path
        self.doc = doc
        self._index: dict[str, GedLine] = {}
        self.reindex()

    # -- construction ---------------------------------------------------------------

    @classmethod
    def load(cls, path: Path) -> GedcomFile:
        return cls(path, parse_bytes(path.read_bytes()))

    @classmethod
    def create(cls, path: Path, source: str = "gedcom-mcp") -> GedcomFile:
        f = cls(path, new_document(source))
        f.save(backup=False)
        return f

    # -- index ----------------------------------------------------------------------

    def reindex(self) -> None:
        self._index = {r.xref: r for r in self.doc.records if r.xref}

    def record(self, xref: str) -> GedLine | None:
        return self._index.get(xref)

    def records_of(self, tag: str) -> list[GedLine]:
        return self.doc.records_of(tag)

    def resolve(self, node: GedLine | None) -> GedLine | None:
        """If ``node`` holds a pointer value, return the record it points to."""
        if node is None:
            return None
        if node.is_pointer:
            return self._index.get(node.value)
        return node

    @property
    def source_software(self) -> str | None:
        head = self.doc.header
        if head is None:
            return None
        sour = head.sub("SOUR")
        if sour is None:
            return None
        name = sour.path_value("NAME")
        vers = sour.path_value("VERS")
        base = name or sour.value
        return f"{base} {vers}".strip() if vers else base

    # -- semantic views (see model.py) ------------------------------------------------

    def person(self, xref: str) -> Person | None:
        from .model import Person

        rec = self.record(xref)
        return Person(self, rec) if rec is not None and rec.tag == "INDI" else None

    def family(self, xref: str) -> Family | None:
        from .model import Family

        rec = self.record(xref)
        return Family(self, rec) if rec is not None and rec.tag == "FAM" else None

    def source(self, xref: str) -> Source | None:
        from .model import Source

        rec = self.record(xref)
        return Source(self, rec) if rec is not None and rec.tag == "SOUR" else None

    def persons(self) -> list[Person]:
        from .model import Person

        return [Person(self, r) for r in self.records_of("INDI")]

    def families(self) -> list[Family]:
        from .model import Family

        return [Family(self, r) for r in self.records_of("FAM")]

    # -- mutation support -----------------------------------------------------------

    def new_record(self, tag: str, prefix: str) -> GedLine:
        rec = self.doc.add_record(tag, self.doc.next_xref(prefix))
        self._index[rec.xref or ""] = rec
        return rec

    def delete_record(self, rec: GedLine) -> None:
        self.doc.remove_record(rec)
        if rec.xref:
            self._index.pop(rec.xref, None)

    def stamp(self, rec: GedLine) -> None:
        """Set/refresh the ``CHAN`` sub-record on a top-level record."""
        chan = rec.sub("CHAN")
        if chan is None:
            chan = rec.add("CHAN")
        date = chan.sub("DATE")
        if date is None:
            date = chan.add("DATE")
        date.value = today_gedcom()
        time = date.sub("TIME")
        if time is None:
            time = date.add("TIME")
        time.value = now_gedcom_time()

    # -- persistence ----------------------------------------------------------------

    def save(self, *, backup: bool = True) -> Path | None:
        """Write atomically. Returns the backup path if one was made."""
        bak: Path | None = None
        if backup and self.path.exists():
            bak = self.path.with_name(self.path.name + ".bak")
            shutil.copy2(self.path, bak)
        data = self.doc.to_bytes()
        fd, tmp = tempfile.mkstemp(prefix=self.path.stem + ".", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            os.replace(tmp, self.path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        return bak
