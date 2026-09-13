"""Read-only semantic views (Person, Family, Event, ...) over the GedLine tree.

Views hold a reference to the underlying record, so they are cheap to build and always
reflect the current state of the document. Edits live in :mod:`.edit`.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property

from .dates import year_of
from .file import GedcomFile
from .lines import GedLine
from .names import ParsedName, parse_name

INDI_EVENT_TAGS = {
    "BIRT": "Birth",
    "CHR": "Christening",
    "BAPM": "Baptism",
    "DEAT": "Death",
    "BURI": "Burial",
    "CREM": "Cremation",
    "ADOP": "Adoption",
    "BARM": "Bar Mitzvah",
    "BASM": "Bas Mitzvah",
    "BLES": "Blessing",
    "CHRA": "Adult Christening",
    "CONF": "Confirmation",
    "FCOM": "First Communion",
    "ORDN": "Ordination",
    "NATU": "Naturalization",
    "EMIG": "Emigration",
    "IMMI": "Immigration",
    "CENS": "Census",
    "PROB": "Probate",
    "WILL": "Will",
    "GRAD": "Graduation",
    "RETI": "Retirement",
    "EVEN": "Event",
}
INDI_ATTR_TAGS = {
    "CAST": "Caste",
    "DSCR": "Description",
    "EDUC": "Education",
    "IDNO": "ID number",
    "NATI": "Nationality",
    "NCHI": "Number of children",
    "NMR": "Number of marriages",
    "OCCU": "Occupation",
    "PROP": "Property",
    "RELI": "Religion",
    "RESI": "Residence",
    "SSN": "Social security number",
    "TITL": "Title",
    "FACT": "Fact",
}
FAM_EVENT_TAGS = {
    "ANUL": "Annulment",
    "CENS": "Census",
    "DIV": "Divorce",
    "DIVF": "Divorce filed",
    "ENGA": "Engagement",
    "MARB": "Marriage banns",
    "MARC": "Marriage contract",
    "MARR": "Marriage",
    "MARL": "Marriage licence",
    "MARS": "Marriage settlement",
    "RESI": "Residence",
    "EVEN": "Event",
}
# Ancestry-specific custom event tags seen in exports
CUSTOM_EVENT_TAGS = {
    "_MILT": "Military service",
    "_MILTID": "Military ID",
    "_DEG": "Degree",
    "_ELEC": "Elected",
    "_EMPLOY": "Employment",
    "_EXCM": "Excommunication",
    "_FUN": "Funeral",
    "_MDCL": "Medical",
    "_NAMS": "Namesake",
    "_ORDI": "Ordinance",
    "_ORIG": "Origin",
    "_SEPR": "Separation",
    "_WEIG": "Weight",
    "_HEIG": "Height",
    "_DNA": "DNA",
    "_ARRIVAL": "Arrival",
    "_DEPARTURE": "Departure",
}
ALL_INDI_FACT_TAGS = {**INDI_EVENT_TAGS, **INDI_ATTR_TAGS, **CUSTOM_EVENT_TAGS}
ALL_FAM_FACT_TAGS = {**FAM_EVENT_TAGS, **CUSTOM_EVENT_TAGS}


def fact_label(tag: str, type_: str | None = None) -> str:
    if tag in ("EVEN", "FACT") and type_:
        return type_
    return ALL_INDI_FACT_TAGS.get(tag) or ALL_FAM_FACT_TAGS.get(tag) or tag


# -- small value objects ---------------------------------------------------------------


@dataclass
class Citation:
    source_id: str | None
    source_title: str | None
    page: str | None
    date: str | None
    text: str | None
    apid: str | None
    note: str | None

    @classmethod
    def from_node(cls, f: GedcomFile, node: GedLine) -> Citation:
        src = f.resolve(node) if node.is_pointer else None
        data = node.sub("DATA")
        return cls(
            source_id=node.value if node.is_pointer else None,
            source_title=(src.path_value("TITL") if src is not None else None)
            or (None if node.is_pointer else node.text),
            page=node.path_value("PAGE"),
            date=data.path_value("DATE") if data is not None else None,
            text=(data.path_value("TEXT") if data is not None else None) or node.path_value("TEXT"),
            apid=node.path_value("_APID"),
            note=_first_note(f, node),
        )


def notes_of(f: GedcomFile, node: GedLine) -> list[str]:
    out: list[str] = []
    for n in node.subs("NOTE"):
        target = f.resolve(n) if n.is_pointer else n
        if target is not None:
            text = target.text.strip()
            if text:
                out.append(text)
    return out


def _first_note(f: GedcomFile, node: GedLine) -> str | None:
    notes = notes_of(f, node)
    return notes[0] if notes else None


def citations_of(f: GedcomFile, node: GedLine) -> list[Citation]:
    return [Citation.from_node(f, s) for s in node.subs("SOUR")]


@dataclass
class Event:
    node: GedLine
    file: GedcomFile

    @property
    def tag(self) -> str:
        return self.node.tag

    @property
    def type(self) -> str | None:
        return self.node.path_value("TYPE")

    @property
    def label(self) -> str:
        return fact_label(self.tag, self.type)

    @property
    def date(self) -> str | None:
        return self.node.path_value("DATE")

    @property
    def year(self) -> int | None:
        return year_of(self.date)

    @property
    def place(self) -> str | None:
        return self.node.path_value("PLAC")

    @property
    def value(self) -> str | None:
        v = self.node.text.strip()
        return v if v and v != "Y" else None

    @property
    def notes(self) -> list[str]:
        return notes_of(self.file, self.node)

    @property
    def citations(self) -> list[Citation]:
        return citations_of(self.file, self.node)


# -- records ---------------------------------------------------------------------------


class _Record:
    def __init__(self, file: GedcomFile, rec: GedLine) -> None:
        self.file = file
        self.rec = rec

    @property
    def id(self) -> str:
        return self.rec.xref or ""

    @property
    def notes(self) -> list[str]:
        return notes_of(self.file, self.rec)

    @property
    def citations(self) -> list[Citation]:
        return citations_of(self.file, self.rec)

    @property
    def changed(self) -> str | None:
        return self.rec.path_value("CHAN/DATE")

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _Record) and other.rec is self.rec

    def __hash__(self) -> int:
        return id(self.rec)


class Person(_Record):
    @cached_property
    def name(self) -> ParsedName:
        n = self.rec.sub("NAME")
        if n is None:
            return ParsedName("", "", "")
        parsed = parse_name(n.text)
        # prefer explicit GIVN/SURN sub-tags when present
        givn, surn = n.path_value("GIVN"), n.path_value("SURN")
        if givn or surn:
            return ParsedName(givn or parsed.given, surn or parsed.surname, parsed.suffix)
        return parsed

    @property
    def names(self) -> list[str]:
        return [parse_name(n.text).display for n in self.rec.subs("NAME")]

    @property
    def display_name(self) -> str:
        return self.name.display

    @property
    def sex(self) -> str | None:
        return self.rec.path_value("SEX")

    @property
    def events(self) -> list[Event]:
        return [Event(c, self.file) for c in self.rec.children if c.tag in ALL_INDI_FACT_TAGS]

    def event(self, tag: str, index: int = 0) -> Event | None:
        matches = [c for c in self.rec.children if c.tag == tag]
        return Event(matches[index], self.file) if index < len(matches) else None

    @property
    def birth(self) -> Event | None:
        return self.event("BIRT") or self.event("CHR") or self.event("BAPM")

    @property
    def death(self) -> Event | None:
        return self.event("DEAT") or self.event("BURI")

    @property
    def birth_year(self) -> int | None:
        e = self.birth
        return e.year if e else None

    @property
    def death_year(self) -> int | None:
        e = self.death
        return e.year if e else None

    @property
    def places(self) -> list[str]:
        return [e.place for e in self.events if e.place]

    # -- relationships --------------------------------------------------------------

    @property
    def family_ids_as_child(self) -> list[str]:
        return [c.value for c in self.rec.subs("FAMC") if c.is_pointer]

    @property
    def family_ids_as_spouse(self) -> list[str]:
        return [c.value for c in self.rec.subs("FAMS") if c.is_pointer]

    def families_as_child(self) -> list[Family]:
        return [fam for fid in self.family_ids_as_child if (fam := self.file.family(fid)) is not None]

    def families_as_spouse(self) -> list[Family]:
        return [fam for fid in self.family_ids_as_spouse if (fam := self.file.family(fid)) is not None]

    @property
    def father(self) -> Person | None:
        fams = self.families_as_child()
        return fams[0].husband if fams else None

    @property
    def mother(self) -> Person | None:
        fams = self.families_as_child()
        return fams[0].wife if fams else None

    def parents(self) -> list[Person]:
        out: list[Person] = []
        for fam in self.families_as_child():
            out.extend(p for p in (fam.husband, fam.wife) if p is not None and p not in out)
        return out

    def spouses(self) -> list[tuple[Person | None, Family]]:
        out: list[tuple[Person | None, Family]] = []
        for fam in self.families_as_spouse():
            other = fam.wife if fam.husband == self else fam.husband
            out.append((other, fam))
        return out

    def children(self) -> list[Person]:
        out: list[Person] = []
        for fam in self.families_as_spouse():
            out.extend(c for c in fam.children if c not in out)
        return out

    def siblings(self) -> list[Person]:
        out: list[Person] = []
        for fam in self.families_as_child():
            out.extend(c for c in fam.children if c != self and c not in out)
        return out


class Family(_Record):
    @property
    def husband(self) -> Person | None:
        return self.file.person(self.rec.path_value("HUSB") or "")

    @property
    def wife(self) -> Person | None:
        return self.file.person(self.rec.path_value("WIFE") or "")

    @property
    def children(self) -> list[Person]:
        return [p for c in self.rec.subs("CHIL") if (p := self.file.person(c.value)) is not None]

    @property
    def events(self) -> list[Event]:
        return [Event(c, self.file) for c in self.rec.children if c.tag in ALL_FAM_FACT_TAGS]

    def event(self, tag: str, index: int = 0) -> Event | None:
        matches = [c for c in self.rec.children if c.tag == tag]
        return Event(matches[index], self.file) if index < len(matches) else None

    @property
    def marriage(self) -> Event | None:
        return self.event("MARR")


class Source(_Record):
    @property
    def title(self) -> str | None:
        return self.rec.path_value("TITL")

    @property
    def author(self) -> str | None:
        return self.rec.path_value("AUTH")

    @property
    def publisher(self) -> str | None:
        return self.rec.path_value("PUBL")

    @property
    def abbreviation(self) -> str | None:
        return self.rec.path_value("ABBR")

    @property
    def text(self) -> str | None:
        return self.rec.path_value("TEXT")

    @property
    def apid(self) -> str | None:
        return self.rec.path_value("_APID")

    @property
    def repository(self) -> str | None:
        repo = self.file.resolve(self.rec.sub("REPO"))
        if repo is None:
            return None
        return repo.path_value("NAME") or repo.text or None
