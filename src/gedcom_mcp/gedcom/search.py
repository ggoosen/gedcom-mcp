"""Searching individuals and walking ancestor/descendant trees."""

from __future__ import annotations

from dataclasses import dataclass, field

from .file import GedcomFile
from .model import Family, Person
from .names import fold


@dataclass
class SearchQuery:
    query: str | None = None
    given: str | None = None
    surname: str | None = None
    birth_year_from: int | None = None
    birth_year_to: int | None = None
    death_year_from: int | None = None
    death_year_to: int | None = None
    place: str | None = None
    sex: str | None = None


def _rank(p: Person, q: SearchQuery) -> tuple[int, str, str] | None:
    """Return a sort key (lower is better) or None if the person does not match."""
    name = p.name
    full = fold(name.display)
    given, surname = fold(name.given), fold(name.surname)
    all_names = " | ".join(fold(n) for n in p.names)

    score = 3
    if q.query:
        needle = fold(q.query)
        tokens = needle.split()
        if needle == full or needle == f"{given} {surname}".strip():
            score = 0
        elif needle == surname or needle == given:
            score = 1
        elif all(t in all_names for t in tokens):
            score = 2
        else:
            return None
    if q.given and fold(q.given) not in given:
        return None
    if q.surname:
        s = fold(q.surname)
        if s != surname and s not in surname:
            return None
        if s == surname and score > 1:
            score = 1
    if q.sex and (p.sex or "").upper() != q.sex.upper():
        return None
    if q.birth_year_from is not None or q.birth_year_to is not None:
        y = p.birth_year
        if y is None:
            return None
        if q.birth_year_from is not None and y < q.birth_year_from:
            return None
        if q.birth_year_to is not None and y > q.birth_year_to:
            return None
    if q.death_year_from is not None or q.death_year_to is not None:
        y = p.death_year
        if y is None:
            return None
        if q.death_year_from is not None and y < q.death_year_from:
            return None
        if q.death_year_to is not None and y > q.death_year_to:
            return None
    if q.place:
        needle = fold(q.place)
        if not any(needle in fold(pl) for pl in p.places):
            return None
    return (score, surname, given)


def search_persons(f: GedcomFile, q: SearchQuery) -> list[Person]:
    scored = []
    for p in f.persons():
        key = _rank(p, q)
        if key is not None:
            scored.append((key, p))
    scored.sort(key=lambda kp: kp[0])
    return [p for _, p in scored]


# -- trees -----------------------------------------------------------------------------


@dataclass
class AncestorNode:
    person: Person
    generation: int
    father: AncestorNode | None = None
    mother: AncestorNode | None = None
    truncated: bool = False


def ancestors(p: Person, generations: int) -> AncestorNode:
    def walk(person: Person, gen: int, seen: frozenset[str]) -> AncestorNode:
        node = AncestorNode(person, gen)
        if gen >= generations:
            node.truncated = person.father is not None or person.mother is not None
            return node
        seen = seen | {person.id}
        for attr in ("father", "mother"):
            parent = getattr(person, attr)
            if parent is not None and parent.id not in seen:
                setattr(node, attr, walk(parent, gen + 1, seen))
        return node

    return walk(p, 0, frozenset())


@dataclass
class DescendantFamily:
    family: Family
    spouse: Person | None
    children: list[DescendantNode] = field(default_factory=list)


@dataclass
class DescendantNode:
    person: Person
    generation: int
    families: list[DescendantFamily] = field(default_factory=list)
    truncated: bool = False


def descendants(p: Person, generations: int) -> DescendantNode:
    def walk(person: Person, gen: int, seen: frozenset[str]) -> DescendantNode:
        node = DescendantNode(person, gen)
        if gen >= generations:
            node.truncated = bool(person.children())
            return node
        seen = seen | {person.id}
        for spouse, fam in person.spouses():
            df = DescendantFamily(fam, spouse)
            for child in fam.children:
                if child.id not in seen:
                    df.children.append(walk(child, gen + 1, seen))
            node.families.append(df)
        return node

    return walk(p, 0, frozenset())
