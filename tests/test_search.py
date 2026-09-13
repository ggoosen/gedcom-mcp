from gedcom_mcp.gedcom.file import GedcomFile
from gedcom_mcp.gedcom.search import SearchQuery, ancestors, descendants, search_persons


def names(persons) -> list[str]:
    return [p.display_name for p in persons]


def test_exact_name_ranks_first(ged: GedcomFile) -> None:
    res = search_persons(ged, SearchQuery(query="john smith"))
    assert names(res)[0] == "John Smith"
    assert len(res) == 1


def test_surname_query_returns_all_and_sorts(ged: GedcomFile) -> None:
    res = names(search_persons(ged, SearchQuery(query="smith")))
    assert len(res) == 7
    assert res == sorted(res, key=lambda n: (n.split()[-1], n.split()[0]))


def test_accent_insensitive(ged: GedcomFile) -> None:
    assert names(search_persons(ged, SearchQuery(query="muller"))) == ["Anne Müller"]
    assert names(search_persons(ged, SearchQuery(surname="MÜLLER"))) == ["Anne Müller"]


def test_partial_tokens(ged: GedcomFile) -> None:
    assert names(search_persons(ged, SearchQuery(query="eliz smi"))) == ["Elizabeth Smith"]
    assert search_persons(ged, SearchQuery(query="nobody here")) == []


def test_year_filters(ged: GedcomFile) -> None:
    res = search_persons(ged, SearchQuery(surname="smith", birth_year_from=1865, birth_year_to=1872))
    assert names(res) == ["Elizabeth Smith", "John Smith", "Thomas Smith"]
    res = search_persons(ged, SearchQuery(death_year_from=1950))
    assert names(res) == ["Robert Smith"]


def test_place_and_sex_filters(ged: GedcomFile) -> None:
    res = search_persons(ged, SearchQuery(place="sydney"))
    assert names(res) == ["Alice Brown", "George Smith", "Robert Smith"]
    res = search_persons(ged, SearchQuery(place="cardiff", sex="f"))
    assert names(res) == ["Mary Jones"]


def test_ancestors_tree(ged: GedcomFile) -> None:
    tree = ancestors(ged.person("@I10@"), generations=3)
    assert tree.person.display_name == "George Smith"
    robert = tree.father
    john = robert.father
    assert (robert.person.display_name, john.person.display_name) == ("Robert Smith", "John Smith")
    assert john.father.person.display_name == "William Smith"
    assert john.father.truncated is False  # William has no recorded parents
    assert john.mother.person.display_name == "Mary Jones"
    assert john.mother.truncated is True  # Henry & Sarah are beyond generation 3
    assert john.mother.father is None
    assert robert.mother.person.display_name == "Anne Müller"
    assert tree.mother.person.display_name == "Alice Brown"
    # generations=1 truncates immediately
    short = ancestors(ged.person("@I10@"), generations=1)
    assert short.father.truncated is True
    assert short.father.father is None


def test_descendants_tree(ged: GedcomFile) -> None:
    tree = descendants(ged.person("@I1@"), generations=2)
    assert tree.person.display_name == "William Smith"
    assert len(tree.families) == 1
    fam = tree.families[0]
    assert fam.spouse.display_name == "Mary Jones"
    kids = [c.person.display_name for c in fam.children]
    assert kids == ["John Smith", "Elizabeth Smith", "Thomas Smith"]
    john = fam.children[0]
    grandkids = [c.person.display_name for c in john.families[0].children]
    assert grandkids == ["Robert Smith", "Margaret Smith"]
    robert = john.families[0].children[0]
    assert robert.truncated is True  # George is generation 3
    assert robert.families == []
