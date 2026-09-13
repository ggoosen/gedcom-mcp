"""The MCP server: tools and resources over a directory of GEDCOM files."""

from __future__ import annotations

import datetime as _dt
import logging
from collections import Counter
from typing import Annotated

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ResourceNotFoundError, ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from . import schemas as S
from .config import ConfigError, Settings
from .gedcom import edit
from .gedcom.file import GedcomFile
from .gedcom.lines import GedcomParseError
from .gedcom.model import Citation, Event, Family, Person
from .gedcom.search import AncestorNode, DescendantNode, SearchQuery, ancestors, descendants, search_persons

log = logging.getLogger("gedcom_mcp")

INSTRUCTIONS = """\
Tools for reading, searching and editing GEDCOM (.ged) family-tree files such as Ancestry.com exports.

Workflow: call `list_files` (or `file_summary`) first, then `search_individuals` to find people, then
`get_individual` / `get_family` / `get_ancestors` / `get_descendants` by id. Ids look like `@I123@`
(individuals), `@F45@` (families) and `@S7@` (sources). When only one .ged file is present the `file`
argument may be omitted.

Editing tools (`add_individual`, `update_individual`, `set_event`, `remove_event`, `add_note`,
`add_family`, `add_child`, `set_parents`, `remove_individual`) save the file immediately and write a
`<name>.ged.bak` backup first. Everything not touched by an edit is preserved byte-for-byte.
Dates are GEDCOM style, e.g. `12 MAR 1840`, `ABT 1845`, `BET 1930 AND 1935`.
"""

mcp = MCPServer("gedcom", instructions=INSTRUCTIONS, version="0.1.0")

_settings: Settings | None = None

READ_ONLY = ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)
DESTRUCTIVE = ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=False)

FileArg = Annotated[
    str | None,
    Field(description="GEDCOM file name (with or without .ged). Optional when only one file exists."),
]
IdArg = Annotated[str, Field(description="Record id such as @I12@", pattern=r"^@[^@]+@$")]


def configure(settings: Settings) -> None:
    global _settings
    _settings = settings


def settings() -> Settings:
    if _settings is None:
        raise ToolError("Server is not configured with a GEDCOM directory")
    return _settings


def _open(file: str | None) -> GedcomFile:
    try:
        return settings().open(file)
    except ConfigError as e:
        raise ToolError(str(e)) from e
    except GedcomParseError as e:
        raise ToolError(f"Could not parse GEDCOM file: {e}") from e


def _person(f: GedcomFile, xref: str) -> Person:
    p = f.person(xref)
    if p is None:
        raise ToolError(f"No individual with id {xref} in {f.path.stem}")
    return p


def _family(f: GedcomFile, xref: str) -> Family:
    fam = f.family(xref)
    if fam is None:
        raise ToolError(f"No family with id {xref} in {f.path.stem}")
    return fam


def _save(f: GedcomFile, xref: str | None, message: str) -> S.WriteResult:
    bak = f.save()
    settings().remember(f)
    return S.WriteResult(file=f.path.stem, id=xref, message=message, backup=str(bak) if bak else None)


def _edit(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except edit.EditError as e:
        raise ToolError(str(e)) from e


# -- converters ------------------------------------------------------------------------


def _summary(p: Person | None) -> S.PersonSummary | None:
    if p is None:
        return None
    b, d = p.birth, p.death
    return S.PersonSummary(
        id=p.id,
        name=p.display_name,
        sex=p.sex,
        birth_date=b.date if b else None,
        birth_place=b.place if b else None,
        death_date=d.date if d else None,
        death_place=d.place if d else None,
    )


def _summary_req(p: Person) -> S.PersonSummary:
    return _summary(p)  # type: ignore[return-value]


def _citation(c: Citation) -> S.CitationOut:
    return S.CitationOut(**c.__dict__)


def _event(e: Event, include_sources: bool, include_notes: bool) -> S.EventOut:
    return S.EventOut(
        tag=e.tag,
        label=e.label,
        type=e.type,
        date=e.date,
        year=e.year,
        place=e.place,
        value=e.value,
        notes=e.notes if include_notes else [],
        citations=[_citation(c) for c in e.citations] if include_sources else [],
    )


def _detail(p: Person, include_sources: bool, include_notes: bool) -> S.PersonDetail:
    fams: list[S.SpouseOut] = []
    for spouse, fam in p.spouses():
        m = fam.marriage
        fams.append(
            S.SpouseOut(
                family_id=fam.id,
                spouse=_summary(spouse),
                marriage_date=m.date if m else None,
                marriage_place=m.place if m else None,
                children=[_summary_req(c) for c in fam.children],
            )
        )
    n = p.name
    return S.PersonDetail(
        id=p.id,
        name=p.display_name,
        given=n.given,
        surname=n.surname,
        suffix=n.suffix or None,
        other_names=p.names[1:],
        sex=p.sex,
        events=[_event(e, include_sources, include_notes) for e in p.events],
        notes=p.notes if include_notes else [],
        citations=[_citation(c) for c in p.citations] if include_sources else [],
        parents=[_summary_req(x) for x in p.parents()],
        families=fams,
        siblings=[_summary_req(x) for x in p.siblings()],
        family_ids_as_child=p.family_ids_as_child,
        last_changed=p.changed,
    )


def _family_out(fam: Family) -> S.FamilyOut:
    return S.FamilyOut(
        id=fam.id,
        husband=_summary(fam.husband),
        wife=_summary(fam.wife),
        children=[_summary_req(c) for c in fam.children],
        events=[_event(e, True, True) for e in fam.events],
        notes=fam.notes,
        citations=[_citation(c) for c in fam.citations],
    )


def _ancestor_out(n: AncestorNode) -> S.AncestorNodeOut:
    return S.AncestorNodeOut(
        person=_summary_req(n.person),
        generation=n.generation,
        father=_ancestor_out(n.father) if n.father else None,
        mother=_ancestor_out(n.mother) if n.mother else None,
        truncated=n.truncated,
    )


def _descendant_out(n: DescendantNode) -> S.DescendantNodeOut:
    return S.DescendantNodeOut(
        person=_summary_req(n.person),
        generation=n.generation,
        families=[
            S.DescendantFamilyOut(
                family_id=df.family.id,
                spouse=_summary(df.spouse),
                children=[_descendant_out(c) for c in df.children],
            )
            for df in n.families
        ],
        truncated=n.truncated,
    )


def _file_summary(f: GedcomFile) -> S.FileSummary:
    persons = f.persons()
    years = [y for p in persons for y in (p.birth_year, p.death_year) if y]
    surnames = Counter(p.name.surname for p in persons if p.name.surname)
    return S.FileSummary(
        file=f.path.stem,
        individuals=len(persons),
        families=len(f.records_of("FAM")),
        sources=len(f.records_of("SOUR")),
        notes=len(f.records_of("NOTE")),
        source_software=f.source_software,
        earliest_year=min(years) if years else None,
        latest_year=max(years) if years else None,
        top_surnames=[S.SurnameCount(surname=s, count=c) for s, c in surnames.most_common(20)],
    )


# -- read tools ------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
def list_files() -> list[S.FileInfo]:
    """List the GEDCOM (.ged) files available to this server."""
    out = []
    for p in settings().list_paths():
        st = p.stat()
        out.append(
            S.FileInfo(
                name=p.stem,
                size_bytes=st.st_size,
                modified=_dt.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
            )
        )
    return out


@mcp.tool(annotations=READ_ONLY)
def file_summary(file: FileArg = None) -> S.FileSummary:
    """Overview of a GEDCOM file: record counts, originating software, year range, most common surnames."""
    return _file_summary(_open(file))


@mcp.tool(annotations=READ_ONLY)
def search_individuals(
    file: FileArg = None,
    query: Annotated[
        str | None, Field(description="Free-text name match, e.g. 'john smith' or 'smith'")
    ] = None,
    given: Annotated[str | None, Field(description="Given-name filter (substring)")] = None,
    surname: Annotated[str | None, Field(description="Surname filter (substring)")] = None,
    birth_year_from: int | None = None,
    birth_year_to: int | None = None,
    death_year_from: int | None = None,
    death_year_to: int | None = None,
    place: Annotated[str | None, Field(description="Matches any event place, e.g. 'Bristol'")] = None,
    sex: Annotated[str | None, Field(description="M or F")] = None,
    limit: Annotated[int, Field(ge=1, le=200)] = 25,
    offset: Annotated[int, Field(ge=0)] = 0,
) -> S.SearchResult:
    """Search individuals by name, birth/death year range, place or sex.

    Matching is case- and accent-insensitive. Results are ranked: exact full-name matches first,
    then surname/given matches, then partial matches; ties sort by surname then given name.
    """
    f = _open(file)
    q = SearchQuery(
        query=query,
        given=given,
        surname=surname,
        birth_year_from=birth_year_from,
        birth_year_to=birth_year_to,
        death_year_from=death_year_from,
        death_year_to=death_year_to,
        place=place,
        sex=sex,
    )
    matches = search_persons(f, q)
    page = matches[offset : offset + limit]
    return S.SearchResult(total=len(matches), offset=offset, results=[_summary_req(p) for p in page])


@mcp.tool(annotations=READ_ONLY)
def get_individual(
    id: IdArg,
    file: FileArg = None,
    include_sources: Annotated[bool, Field(description="Include source citations")] = True,
    include_notes: Annotated[bool, Field(description="Include note text")] = True,
) -> S.PersonDetail:
    """Full record for one individual: names, all events/facts, notes, citations, parents, spouses, children, siblings."""
    f = _open(file)
    return _detail(_person(f, id), include_sources, include_notes)


@mcp.tool(annotations=READ_ONLY)
def get_family(id: IdArg, file: FileArg = None) -> S.FamilyOut:
    """One family record (@F..@): spouses, children, marriage and other family events."""
    f = _open(file)
    return _family_out(_family(f, id))


@mcp.tool(annotations=READ_ONLY)
def get_ancestors(
    id: IdArg,
    file: FileArg = None,
    generations: Annotated[int, Field(ge=1, le=10)] = 4,
) -> S.AncestorNodeOut:
    """Pedigree tree (father/mother recursively) for an individual, up to N generations."""
    f = _open(file)
    return _ancestor_out(ancestors(_person(f, id), generations))


@mcp.tool(annotations=READ_ONLY)
def get_descendants(
    id: IdArg,
    file: FileArg = None,
    generations: Annotated[int, Field(ge=1, le=10)] = 3,
) -> S.DescendantNodeOut:
    """Descendant tree (children per marriage, recursively) for an individual, up to N generations."""
    f = _open(file)
    return _descendant_out(descendants(_person(f, id), generations))


@mcp.tool(annotations=READ_ONLY)
def get_source(id: IdArg, file: FileArg = None) -> S.SourceOut:
    """A source record (@S..@): title, author, publisher, repository, Ancestry _APID, and who cites it."""
    f = _open(file)
    src = f.source(id)
    if src is None:
        raise ToolError(f"No source with id {id} in {f.path.stem}")
    cited_by = [
        p
        for p in f.persons()
        if any(c.source_id == id for e in [*p.events] for c in e.citations)
        or any(c.source_id == id for c in p.citations)
    ]
    return S.SourceOut(
        id=src.id,
        title=src.title,
        author=src.author,
        publisher=src.publisher,
        abbreviation=src.abbreviation,
        repository=src.repository,
        apid=src.apid,
        text=src.text,
        notes=src.notes,
        cited_by=[_summary_req(p) for p in cited_by],
    )


# -- write tools -----------------------------------------------------------------------


@mcp.tool(annotations=WRITE)
def create_file(name: Annotated[str, Field(description="New file name, without path")]) -> S.WriteResult:
    """Create a new, empty GEDCOM 5.5.1 file in the server's directory."""
    try:
        path = settings().resolve_new(name)
    except ConfigError as e:
        raise ToolError(str(e)) from e
    if path.exists():
        raise ToolError(f"{path.name} already exists")
    f = GedcomFile.create(path)
    settings().remember(f)
    return S.WriteResult(file=path.stem, id=None, message=f"Created {path.name}")


@mcp.tool(annotations=WRITE)
def rename_file(
    file: Annotated[str, Field(description="Existing file name")], new_name: str
) -> S.WriteResult:
    """Rename a GEDCOM file. Refuses to overwrite an existing file."""
    try:
        src = settings().resolve(file)
        dst = settings().resolve_new(new_name)
    except ConfigError as e:
        raise ToolError(str(e)) from e
    if dst.exists():
        raise ToolError(f"{dst.name} already exists")
    src.rename(dst)
    settings().forget(src)
    return S.WriteResult(file=dst.stem, id=None, message=f"Renamed {src.name} to {dst.name}")


@mcp.tool(annotations=WRITE)
def add_individual(
    given: Annotated[str, Field(description="Given name(s)")],
    surname: str,
    file: FileArg = None,
    sex: Annotated[str | None, Field(description="M, F or U")] = None,
    birth_date: str | None = None,
    birth_place: str | None = None,
    death_date: str | None = None,
    death_place: str | None = None,
    note: str | None = None,
) -> S.WriteResult:
    """Add a new individual and save. Returns the new @I..@ id; link them with add_family / set_parents."""
    f = _open(file)
    p = _edit(
        edit.add_individual, f, given, surname, sex, birth_date, birth_place, death_date, death_place, note
    )
    return _save(f, p.id, f"Added {p.display_name} as {p.id}")


@mcp.tool(annotations=WRITE)
def update_individual(
    id: IdArg,
    file: FileArg = None,
    given: str | None = None,
    surname: str | None = None,
    sex: str | None = None,
) -> S.WriteResult:
    """Change an individual's given name, surname and/or sex. Only supplied fields change."""
    f = _open(file)
    if given is None and surname is None and sex is None:
        raise ToolError("Nothing to update: pass given, surname and/or sex")
    p = _edit(edit.update_individual, f, id, given, surname, sex)
    return _save(f, p.id, f"Updated {p.id}: now {p.display_name}{(' (' + p.sex + ')') if p.sex else ''}")


@mcp.tool(annotations=WRITE)
def set_event(
    id: Annotated[str, Field(description="Individual (@I..@) or family (@F..@) id", pattern=r"^@[^@]+@$")],
    tag: Annotated[
        str,
        Field(
            description="Fact tag: BIRT, DEAT, BURI, CHR, OCCU, RESI, EVEN, CENS, EMIG, IMMI ... or MARR/DIV for families"
        ),
    ],
    file: FileArg = None,
    date: Annotated[str | None, Field(description="GEDCOM date, e.g. '12 MAR 1840', 'ABT 1845'")] = None,
    place: str | None = None,
    value: Annotated[str | None, Field(description="Attribute value (e.g. occupation text for OCCU)")] = None,
    type: Annotated[str | None, Field(description="TYPE sub-tag, used to describe EVEN/FACT facts")] = None,
    index: Annotated[
        int,
        Field(
            ge=0,
            description="Which fact with this tag to update (0 = first). Equal to the current count to add another.",
        ),
    ] = 0,
) -> S.WriteResult:
    """Create or update an event/fact on an individual or family (e.g. set a birth date, add an occupation)."""
    f = _open(file)
    node, created = _edit(edit.set_event, f, id, tag, date, place, value, type, index)
    verb = "Added" if created else "Updated"
    return _save(
        f,
        id,
        f"{verb} {node.tag} on {id}: date={node.path_value('DATE')!r} place={node.path_value('PLAC')!r}",
    )


@mcp.tool(annotations=DESTRUCTIVE)
def remove_event(
    id: Annotated[str, Field(pattern=r"^@[^@]+@$")],
    tag: str,
    file: FileArg = None,
    index: Annotated[int, Field(ge=0)] = 0,
) -> S.WriteResult:
    """Delete the index-th fact with the given tag from an individual or family."""
    f = _open(file)
    _edit(edit.remove_event, f, id, tag, index)
    return _save(f, id, f"Removed {tag.upper()}[{index}] from {id}")


@mcp.tool(annotations=WRITE)
def add_note(
    id: Annotated[str, Field(description="Any record id (@I..@, @F..@, @S..@)", pattern=r"^@[^@]+@$")],
    text: str,
    file: FileArg = None,
) -> S.WriteResult:
    """Attach a free-text note to a record."""
    f = _open(file)
    _edit(edit.add_note, f, id, text)
    return _save(f, id, f"Added note to {id}")


@mcp.tool(annotations=WRITE)
def add_family(
    file: FileArg = None,
    husband_id: str | None = None,
    wife_id: str | None = None,
    child_ids: list[str] | None = None,
    marriage_date: str | None = None,
    marriage_place: str | None = None,
) -> S.WriteResult:
    """Create a family (@F..@) linking spouses and/or children; FAMS/FAMC back-links are written too."""
    f = _open(file)
    fam = _edit(edit.add_family, f, husband_id, wife_id, child_ids, marriage_date, marriage_place)
    return _save(f, fam.id, f"Created family {fam.id}")


@mcp.tool(annotations=WRITE)
def add_child(family_id: IdArg, child_id: IdArg, file: FileArg = None) -> S.WriteResult:
    """Add an existing individual as a child of an existing family."""
    f = _open(file)
    added = _edit(edit.add_child, f, family_id, child_id)
    if not added:
        return S.WriteResult(
            file=f.path.stem, id=family_id, message=f"{child_id} is already a child of {family_id}"
        )
    return _save(f, family_id, f"Added {child_id} as child of {family_id}")


@mcp.tool(annotations=WRITE)
def set_parents(
    child_id: IdArg,
    file: FileArg = None,
    father_id: str | None = None,
    mother_id: str | None = None,
) -> S.WriteResult:
    """Make father/mother the parents of a child, reusing their existing family or creating one."""
    f = _open(file)
    fam = _edit(edit.set_parents, f, child_id, father_id, mother_id)
    return _save(f, fam.id, f"{child_id} is now a child of family {fam.id}")


@mcp.tool(annotations=DESTRUCTIVE)
def remove_individual(id: IdArg, file: FileArg = None) -> S.WriteResult:
    """Delete an individual and all references to them. Families left with no members are removed too."""
    f = _open(file)
    p = _person(f, id)
    name = p.display_name
    removed = _edit(edit.remove_individual, f, id)
    extra = f"; also removed empty families {', '.join(removed)}" if removed else ""
    return _save(f, id, f"Removed {name} ({id}){extra}")


# -- resources -------------------------------------------------------------------------


def _md_summary(s: S.FileSummary) -> str:
    lines = [
        f"# {s.file}.ged",
        "",
        f"- Individuals: {s.individuals}",
        f"- Families: {s.families}",
        f"- Sources: {s.sources}",
        f"- Notes: {s.notes}",
        f"- Software: {s.source_software or 'unknown'}",
        f"- Years: {s.earliest_year or '?'} – {s.latest_year or '?'}",
        "",
        "## Most common surnames",
    ]
    lines += [f"- {x.surname} ({x.count})" for x in s.top_surnames]
    return "\n".join(lines)


def _md_person(d: S.PersonDetail) -> str:
    lines = [f"# {d.name} ({d.id})", ""]
    if d.sex:
        lines.append(f"- Sex: {d.sex}")
    for e in d.events:
        bits = [b for b in (e.date, e.place, e.value) if b]
        lines.append(f"- {e.label}: {', '.join(bits) if bits else '(no details)'}")
    if d.parents:
        lines += ["", "## Parents"] + [f"- {p.name} ({p.id})" for p in d.parents]
    if d.families:
        lines += ["", "## Families"]
        for fam in d.families:
            sp = f"{fam.spouse.name} ({fam.spouse.id})" if fam.spouse else "(unknown spouse)"
            m = f", married {fam.marriage_date}" if fam.marriage_date else ""
            lines.append(f"- {fam.family_id}: with {sp}{m}")
            lines += [f"  - child: {c.name} ({c.id})" for c in fam.children]
    if d.notes:
        lines += ["", "## Notes"] + [f"- {n}" for n in d.notes]
    return "\n".join(lines)


@mcp.resource("gedcom://{file}", mime_type="text/markdown")
def file_resource(file: str) -> str:
    """Summary of one GEDCOM file."""
    try:
        return _md_summary(_file_summary(settings().open(file)))
    except (ConfigError, ToolError) as e:
        raise ResourceNotFoundError(str(e)) from e


@mcp.resource("gedcom://{file}/person/{id}", mime_type="text/markdown")
def person_resource(file: str, id: str) -> str:
    """One individual, as a markdown card."""
    try:
        f = settings().open(file)
    except (ConfigError, ToolError) as e:
        raise ResourceNotFoundError(str(e)) from e
    p = f.person(id)
    if p is None:
        raise ResourceNotFoundError(f"No individual {id} in {file}")
    return _md_person(_detail(p, True, True))
