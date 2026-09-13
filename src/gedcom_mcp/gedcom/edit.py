"""Mutating operations on a :class:`GedcomFile`.

Every function edits the in-memory tree and stamps ``CHAN`` on the records it touched;
callers are responsible for calling ``file.save()`` afterwards.
"""

from __future__ import annotations

from .dates import normalize
from .file import GedcomFile
from .lines import GedLine
from .model import ALL_FAM_FACT_TAGS, ALL_INDI_FACT_TAGS, Family, Person
from .names import ParsedName


class EditError(ValueError):
    pass


# Sub-tags that must precede a new fact so the record stays tidy (NAME, SEX first).
_HEAD_TAGS = ("NAME", "SEX")


def _require_person(f: GedcomFile, xref: str) -> Person:
    p = f.person(xref)
    if p is None:
        raise EditError(f"No individual with id {xref}")
    return p


def _require_family(f: GedcomFile, xref: str) -> Family:
    fam = f.family(xref)
    if fam is None:
        raise EditError(f"No family with id {xref}")
    return fam


def _fact_insert_index(rec: GedLine) -> int:
    """Insert new facts after NAME/SEX but before family links / notes / CHAN."""
    idx = 0
    for i, c in enumerate(rec.children):
        if c.tag in _HEAD_TAGS or c.tag in ALL_INDI_FACT_TAGS or c.tag in ALL_FAM_FACT_TAGS:
            idx = i + 1
    return idx


def _link_insert_index(rec: GedLine) -> int:
    """FAMS/FAMC/HUSB/WIFE/CHIL go after facts but before NOTE/SOUR/CHAN."""
    idx = 0
    for i, c in enumerate(rec.children):
        if c.tag not in ("NOTE", "SOUR", "OBJE", "CHAN", "REFN", "RIN"):
            idx = i + 1
    return idx


def _set_child_value(node: GedLine, tag: str, value: str | None) -> None:
    """Set/replace/remove a single-valued sub-tag."""
    existing = node.sub(tag)
    if value is None or value == "":
        if existing is not None:
            existing.remove()
        return
    if existing is None:
        node.add(tag, value)
    else:
        existing.set_text(value)


# -- individuals -----------------------------------------------------------------------


def add_individual(
    f: GedcomFile,
    given: str,
    surname: str,
    sex: str | None = None,
    birth_date: str | None = None,
    birth_place: str | None = None,
    death_date: str | None = None,
    death_place: str | None = None,
    note: str | None = None,
) -> Person:
    if not given and not surname:
        raise EditError("At least one of given name or surname is required")
    rec = f.new_record("INDI", "I")
    name = ParsedName(given.strip(), surname.strip(), "")
    n = rec.add("NAME", name.gedcom)
    if name.given:
        n.add("GIVN", name.given)
    if name.surname:
        n.add("SURN", name.surname)
    if sex:
        rec.add("SEX", _norm_sex(sex))
    if birth_date or birth_place:
        _fill_event(rec.add("BIRT"), birth_date, birth_place, None, None)
    if death_date or death_place:
        _fill_event(rec.add("DEAT"), death_date, death_place, None, None)
    if note:
        rec.add("NOTE").set_text(note)
    f.stamp(rec)
    return Person(f, rec)


def update_individual(
    f: GedcomFile,
    xref: str,
    given: str | None = None,
    surname: str | None = None,
    sex: str | None = None,
) -> Person:
    p = _require_person(f, xref)
    rec = p.rec
    if given is not None or surname is not None:
        current = p.name
        new = ParsedName(
            current.given if given is None else given.strip(),
            current.surname if surname is None else surname.strip(),
            current.suffix,
        )
        n = rec.sub("NAME")
        if n is None:
            n = rec.add("NAME", index=0)
        n.set_text(new.gedcom)
        if n.sub("GIVN") is not None or new.given:
            _set_child_value(n, "GIVN", new.given or None)
        if n.sub("SURN") is not None or new.surname:
            _set_child_value(n, "SURN", new.surname or None)
    if sex is not None:
        existing = rec.sub("SEX")
        if existing is None:
            rec.add("SEX", _norm_sex(sex), index=1 if rec.sub("NAME") is not None else 0)
        else:
            existing.value = _norm_sex(sex)
    f.stamp(rec)
    return f.person(xref)  # type: ignore[return-value]


def _norm_sex(sex: str) -> str:
    s = sex.strip().upper()[:1]
    if s not in ("M", "F", "U"):
        raise EditError("sex must be M, F or U")
    return s


def remove_individual(f: GedcomFile, xref: str) -> list[str]:
    """Delete a person and every pointer to them. Returns ids of families also removed."""
    p = _require_person(f, xref)
    removed_families: list[str] = []
    for fam_rec in f.records_of("FAM"):
        touched = False
        for c in list(fam_rec.children):
            if c.tag in ("HUSB", "WIFE", "CHIL") and c.value == xref:
                c.remove()
                touched = True
        if not touched:
            continue
        still_linked = any(c.tag in ("HUSB", "WIFE", "CHIL") for c in fam_rec.children)
        if still_linked:
            f.stamp(fam_rec)
        else:
            removed_families.append(fam_rec.xref or "")
            f.delete_record(fam_rec)
    # any other record pointing at this person (ASSO etc.) — drop those lines too
    for rec in f.doc.records:
        for node in list(rec.walk()):
            if node.is_pointer and node.value == xref and node.parent is not None:
                node.remove()
    f.delete_record(p.rec)
    return removed_families


# -- facts / events --------------------------------------------------------------------


def _fill_event(
    node: GedLine,
    date: str | None,
    place: str | None,
    value: str | None,
    type_: str | None,
) -> None:
    if value is not None:
        node.set_text(value)
    _set_child_value(node, "TYPE", type_)
    _set_child_value(node, "DATE", normalize(date) if date else None)
    _set_child_value(node, "PLAC", place)


def set_event(
    f: GedcomFile,
    xref: str,
    tag: str,
    date: str | None = None,
    place: str | None = None,
    value: str | None = None,
    type_: str | None = None,
    index: int = 0,
) -> tuple[GedLine, bool]:
    """Create or update the ``index``-th fact with ``tag``. Returns (node, created)."""
    tag = tag.strip().upper()
    rec = f.record(xref)
    if rec is None or rec.tag not in ("INDI", "FAM"):
        raise EditError(f"No individual or family with id {xref}")
    known = ALL_INDI_FACT_TAGS if rec.tag == "INDI" else ALL_FAM_FACT_TAGS
    if tag not in known and not tag.startswith("_"):
        raise EditError(f"{tag} is not a known {'individual' if rec.tag == 'INDI' else 'family'} fact tag")
    matches = [c for c in rec.children if c.tag == tag]
    created = False
    if index < len(matches):
        node = matches[index]
        # only the supplied fields change on update
        if value is not None:
            node.set_text(value)
        if type_ is not None:
            _set_child_value(node, "TYPE", type_)
        if date is not None:
            _set_child_value(node, "DATE", normalize(date) if date else None)
        if place is not None:
            _set_child_value(node, "PLAC", place)
    elif index == len(matches):
        node = rec.add(tag, index=_fact_insert_index(rec))
        created = True
        _fill_event(node, date, place, value, type_)
        if tag in ("BIRT", "DEAT", "MARR", "DIV") and not node.children and not node.value:
            node.value = "Y"
    else:
        raise EditError(f"{xref} has only {len(matches)} {tag} facts; index {index} is out of range")
    f.stamp(rec)
    return node, created


def remove_event(f: GedcomFile, xref: str, tag: str, index: int = 0) -> None:
    tag = tag.strip().upper()
    rec = f.record(xref)
    if rec is None or rec.tag not in ("INDI", "FAM"):
        raise EditError(f"No individual or family with id {xref}")
    matches = [c for c in rec.children if c.tag == tag]
    if index >= len(matches):
        raise EditError(f"{xref} has no {tag} fact at index {index}")
    matches[index].remove()
    f.stamp(rec)


def add_note(f: GedcomFile, xref: str, text: str) -> None:
    rec = f.record(xref)
    if rec is None:
        raise EditError(f"No record with id {xref}")
    text = text.strip()
    if not text:
        raise EditError("Note text is empty")
    rec.add("NOTE", index=_link_insert_index(rec)).set_text(text)
    f.stamp(rec)


# -- families --------------------------------------------------------------------------


_LINK_GROUPS = {
    "HUSB": ("HUSB",),
    "WIFE": ("HUSB", "WIFE"),
    "CHIL": ("HUSB", "WIFE", "CHIL"),
    "FAMS": ("FAMC", "FAMS"),
    "FAMC": ("FAMC", "FAMS"),
}


def _add_link(rec: GedLine, tag: str, xref: str) -> bool:
    """Add a pointer line, keeping it next to its siblings (CHIL after CHIL, FAMS after FAMC...)."""
    if any(c.tag == tag and c.value == xref for c in rec.children):
        return False
    group = _LINK_GROUPS.get(tag, (tag,))
    idx = None
    for i, c in enumerate(rec.children):
        if c.tag in group:
            idx = i + 1
    rec.add(tag, xref, index=_link_insert_index(rec) if idx is None else idx)
    return True


def add_family(
    f: GedcomFile,
    husband_id: str | None = None,
    wife_id: str | None = None,
    child_ids: list[str] | None = None,
    marriage_date: str | None = None,
    marriage_place: str | None = None,
) -> Family:
    if not husband_id and not wife_id and not child_ids:
        raise EditError("A family needs at least one spouse or child")
    for xref in [x for x in (husband_id, wife_id) if x] + list(child_ids or []):
        _require_person(f, xref)
    rec = f.new_record("FAM", "F")
    if husband_id:
        rec.add("HUSB", husband_id)
        _add_link(f.record(husband_id), "FAMS", rec.xref or "")  # type: ignore[arg-type]
        f.stamp(f.record(husband_id))  # type: ignore[arg-type]
    if wife_id:
        rec.add("WIFE", wife_id)
        _add_link(f.record(wife_id), "FAMS", rec.xref or "")  # type: ignore[arg-type]
        f.stamp(f.record(wife_id))  # type: ignore[arg-type]
    for cid in child_ids or []:
        rec.add("CHIL", cid)
        _add_link(f.record(cid), "FAMC", rec.xref or "")  # type: ignore[arg-type]
        f.stamp(f.record(cid))  # type: ignore[arg-type]
    if marriage_date or marriage_place:
        _fill_event(rec.add("MARR"), marriage_date, marriage_place, None, None)
    f.stamp(rec)
    return Family(f, rec)


def add_child(f: GedcomFile, family_id: str, child_id: str) -> bool:
    fam = _require_family(f, family_id)
    child = _require_person(f, child_id)
    if not _add_link(fam.rec, "CHIL", child_id):
        return False
    _add_link(child.rec, "FAMC", family_id)
    f.stamp(fam.rec)
    f.stamp(child.rec)
    return True


def set_parents(
    f: GedcomFile,
    child_id: str,
    father_id: str | None = None,
    mother_id: str | None = None,
) -> Family:
    """Attach ``child`` to the family of ``father`` + ``mother``, creating it if needed."""
    if not father_id and not mother_id:
        raise EditError("At least one parent id is required")
    child = _require_person(f, child_id)
    for xref in (father_id, mother_id):
        if xref:
            _require_person(f, xref)
    # find an existing family with exactly these spouses
    for fam in f.families():
        h = fam.rec.path_value("HUSB")
        w = fam.rec.path_value("WIFE")
        if (h or None) == (father_id or None) and (w or None) == (mother_id or None):
            add_child(f, fam.id, child_id)
            return fam
    # an existing family with one matching spouse and the other slot empty
    for fam in f.families():
        h = fam.rec.path_value("HUSB")
        w = fam.rec.path_value("WIFE")
        if father_id and h == father_id and not w and mother_id:
            fam.rec.add("WIFE", mother_id, index=1)
            _add_link(f.record(mother_id), "FAMS", fam.id)  # type: ignore[arg-type]
            add_child(f, fam.id, child_id)
            return fam
        if mother_id and w == mother_id and not h and father_id:
            fam.rec.add("HUSB", father_id, index=0)
            _add_link(f.record(father_id), "FAMS", fam.id)  # type: ignore[arg-type]
            add_child(f, fam.id, child_id)
            return fam
    fam = add_family(f, husband_id=father_id, wife_id=mother_id, child_ids=[child.id])
    return fam
