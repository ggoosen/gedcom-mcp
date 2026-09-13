from pathlib import Path

import pytest

from gedcom_mcp.gedcom import edit
from gedcom_mcp.gedcom.file import GedcomFile
from gedcom_mcp.gedcom.lines import parse_bytes


def reload(f: GedcomFile) -> GedcomFile:
    return GedcomFile.load(f.path)


def record_bytes(data: bytes, xref: str) -> bytes:
    """The raw lines of one level-0 record, for byte-level comparisons."""
    lines = data.split(b"\r\n")
    out, inside = [], False
    for ln in lines:
        if ln.startswith(b"0 "):
            inside = ln.startswith(f"0 {xref} ".encode())
        if inside:
            out.append(ln)
    return b"\r\n".join(out)


def test_save_writes_backup_and_preserves_untouched_records(ged: GedcomFile, fixture_bytes: bytes) -> None:
    edit.add_individual(ged, "Zed", "Tester", sex="M", birth_date="1 jan 1950", birth_place="Perth")
    bak = ged.save()
    assert bak == ged.path.with_name("smith.ged.bak")
    assert bak.read_bytes() == fixture_bytes
    new = ged.path.read_bytes()
    assert new.startswith(b"\xef\xbb\xbf0 HEAD\r\n")
    assert new.endswith(b"0 TRLR\r\n")
    for xref in ("@I1@", "@I3@", "@F1@", "@S1@", "@N1@"):
        assert record_bytes(new, xref) == record_bytes(fixture_bytes, xref)
    added = record_bytes(new, "@I13@").decode()
    assert "1 NAME Zed /Tester/" in added
    assert "2 DATE 1 JAN 1950" in added
    assert "2 PLAC Perth" in added
    assert "1 CHAN" in added


def test_add_individual_roundtrip(ged: GedcomFile) -> None:
    p = edit.add_individual(ged, "Zed", "Tester", note="line one\nline two")
    assert p.id == "@I13@"
    ged.save()
    p2 = reload(ged).person("@I13@")
    assert p2.display_name == "Zed Tester"
    assert p2.notes == ["line one\nline two"]


def test_update_individual(ged: GedcomFile) -> None:
    edit.update_individual(ged, "@I4@", given="Eliza", sex="f")
    ged.save()
    p = reload(ged).person("@I4@")
    assert p.name.given == "Eliza" and p.name.surname == "Smith"
    assert p.rec.sub("NAME").text == "Eliza /Smith/"
    assert p.sex == "F"
    assert p.changed is not None


def test_set_event_create_and_update(ged: GedcomFile) -> None:
    node, created = edit.set_event(ged, "@I4@", "DEAT", date="abt 1940", place="Bath")
    assert created and node.tag == "DEAT"
    node, created = edit.set_event(ged, "@I4@", "DEAT", place="Bath, Somerset")
    assert not created
    node, created = edit.set_event(ged, "@I4@", "OCCU", value="Milliner", date="1891")
    assert created
    ged.save()
    p = reload(ged).person("@I4@")
    assert p.death.date == "ABT 1940"
    assert p.death.place == "Bath, Somerset"
    assert p.event("OCCU").value == "Milliner"
    # facts go after NAME/SEX and existing facts, before FAMC
    tags = [c.tag for c in p.rec.children]
    assert tags.index("OCCU") < tags.index("FAMC")


def test_set_event_on_family_and_bad_tag(ged: GedcomFile) -> None:
    edit.set_event(ged, "@F4@", "MARR", date="1843", place="Cardiff")
    assert ged.family("@F4@").marriage.date == "1843"
    with pytest.raises(edit.EditError):
        edit.set_event(ged, "@I1@", "BOGUS", date="1900")
    with pytest.raises(edit.EditError):
        edit.set_event(ged, "@I1@", "BIRT", index=5, date="1900")


def test_remove_event(ged: GedcomFile) -> None:
    edit.remove_event(ged, "@I1@", "_MILT")
    assert ged.person("@I1@").event("_MILT") is None
    with pytest.raises(edit.EditError):
        edit.remove_event(ged, "@I1@", "_MILT")


def test_add_note(ged: GedcomFile) -> None:
    edit.add_note(ged, "@F1@", "Married at St Mary Redcliffe.")
    ged.save()
    assert reload(ged).family("@F1@").notes == ["Married at St Mary Redcliffe."]


def test_add_family_writes_backlinks(ged: GedcomFile) -> None:
    kid = edit.add_individual(ged, "Baby", "Smith")
    fam = edit.add_family(ged, husband_id="@I10@", wife_id=None, child_ids=[kid.id], marriage_date="1940")
    assert fam.id == "@F5@"
    ged.save()
    g = reload(ged)
    george = g.person("@I10@")
    assert george.family_ids_as_spouse == ["@F5@"]
    assert [c.display_name for c in george.children()] == ["Baby Smith"]
    assert g.person(kid.id).father.display_name == "George Smith"


def test_set_parents_reuses_existing_family(ged: GedcomFile) -> None:
    kid = edit.add_individual(ged, "Late", "Smith", birth_date="1875")
    fam = edit.set_parents(ged, kid.id, father_id="@I1@", mother_id="@I2@")
    assert fam.id == "@F1@"
    assert [c.display_name for c in ged.family("@F1@").children][-1] == "Late Smith"
    # idempotent
    edit.set_parents(ged, kid.id, father_id="@I1@", mother_id="@I2@")
    assert sum(1 for c in ged.family("@F1@").rec.subs("CHIL") if c.value == kid.id) == 1


def test_set_parents_creates_family_when_needed(ged: GedcomFile) -> None:
    kid = edit.add_individual(ged, "Only", "Brown")
    fam = edit.set_parents(ged, kid.id, mother_id="@I9@")
    assert fam.id == "@F5@"
    assert fam.husband is None and fam.wife.display_name == "Alice Brown"
    # a later father fills the empty slot of that same family
    fam2 = edit.set_parents(ged, kid.id, father_id="@I7@", mother_id="@I9@")
    assert fam2.id in ("@F3@", "@F5@")  # exact-match F3 wins because Robert+Alice already exist


def test_remove_individual_cleans_pointers(ged: GedcomFile) -> None:
    removed = edit.remove_individual(ged, "@I12@")  # Sarah Evans, wife in F4
    assert removed == []
    assert ged.family("@F4@").wife is None
    removed = edit.remove_individual(ged, "@I11@")  # Henry Jones, now the only spouse; F4 still has child I2
    assert removed == []
    removed = edit.remove_individual(ged, "@I2@")
    assert removed == ["@F4@"]
    ged.save()
    g = reload(ged)
    assert g.person("@I2@") is None and g.family("@F4@") is None
    assert g.family("@F1@").wife is None
    data = g.path.read_bytes()
    assert b"@I2@" not in data and b"@F4@" not in data


def test_created_file_is_loadable(tmp_path: Path) -> None:
    f = GedcomFile.create(tmp_path / "new.ged")
    p = edit.add_individual(f, "First", "Person")
    f.save()
    doc = parse_bytes((tmp_path / "new.ged").read_bytes())
    assert doc.record(p.id).tag == "INDI"
    assert doc.records[-1].tag == "TRLR"
