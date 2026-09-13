from gedcom_mcp.gedcom.dates import normalize, year_of
from gedcom_mcp.gedcom.file import GedcomFile
from gedcom_mcp.gedcom.names import fold, parse_name


def test_year_extraction() -> None:
    assert year_of("12 Mar 1840") == 1840
    assert year_of("ABT 1845") == 1845
    assert year_of("BET 1930 AND 1935") == 1930
    assert year_of("FROM 1900 TO 1910") == 1900
    assert year_of("(date unknown)") is None
    assert year_of("born around 1850 in Kent") == 1850
    assert year_of(None) is None


def test_normalize_dates() -> None:
    assert normalize("12 Mar 1840") == "12 MAR 1840"
    assert normalize("abt 1845") == "ABT 1845"
    assert normalize("bet 1930 and 1935") == "BET 1930 AND 1935"
    assert normalize("(date unknown)") == "(date unknown)"


def test_parse_name() -> None:
    n = parse_name("John /Smith/ Jr.")
    assert (n.given, n.surname, n.suffix) == ("John", "Smith", "Jr.")
    assert n.display == "John Smith Jr."
    assert n.gedcom == "John /Smith/ Jr."
    assert parse_name("/Smith/").display == "Smith"
    assert parse_name("Mononym").surname == ""


def test_fold_strips_accents_and_case() -> None:
    assert fold("Müller") == "muller"
    assert fold("  José   María ") == "jose maria"
    assert fold(None) == ""


def test_person_basics(ged: GedcomFile) -> None:
    p = ged.person("@I3@")
    assert p is not None
    assert p.display_name == "John Smith"
    assert p.sex == "M"
    assert p.birth_year == 1866
    assert p.death_year == 1930
    assert p.birth.place == "Bristol, Gloucestershire, England"
    assert [e.label for e in p.events] == ["Birth", "Death", "Emigration"]
    assert p.event("EVEN").type == "Emigration"


def test_person_relationships(ged: GedcomFile) -> None:
    p = ged.person("@I3@")
    assert p.father.display_name == "William Smith"
    assert p.mother.display_name == "Mary Jones"
    assert [x.display_name for x in p.siblings()] == ["Elizabeth Smith", "Thomas Smith"]
    spouses = p.spouses()
    assert len(spouses) == 1
    spouse, fam = spouses[0]
    assert spouse.display_name == "Anne Müller"
    assert fam.id == "@F2@"
    assert fam.marriage.date == "1890"
    assert [c.display_name for c in p.children()] == ["Robert Smith", "Margaret Smith"]


def test_notes_inline_and_shared(ged: GedcomFile) -> None:
    notes = ged.person("@I1@").notes
    assert len(notes) == 2
    assert notes[0].endswith('He was known locally as "Iron Bill".')
    assert notes[1].startswith("Shared research note")


def test_citations(ged: GedcomFile) -> None:
    cits = ged.person("@I3@").birth.citations
    assert len(cits) == 1
    c = cits[0]
    assert c.source_id == "@S2@"
    assert c.source_title.startswith("England & Wales")
    assert c.page == "Bristol 1866 vol 5c p 99"
    assert c.apid == "1,8912::5522"


def test_attributes_and_custom_tags(ged: GedcomFile) -> None:
    p = ged.person("@I1@")
    occ = p.event("OCCU")
    assert occ.value == "Blacksmith"
    assert occ.date == "1881"
    milt = p.event("_MILT")
    assert milt.label == "Military service"


def test_source_and_repository(ged: GedcomFile) -> None:
    s = ged.source("@S1@")
    assert s.title == "1881 England Census"
    assert s.repository == "Ancestry.com"
    assert s.apid == "1,7572::0"


def test_source_software(ged: GedcomFile) -> None:
    assert ged.source_software == "Ancestry.com Family Trees (2010.3)"


def test_unknown_ids(ged: GedcomFile) -> None:
    assert ged.person("@I999@") is None
    assert ged.person("@F1@") is None  # wrong record type
    assert ged.family("@I1@") is None
