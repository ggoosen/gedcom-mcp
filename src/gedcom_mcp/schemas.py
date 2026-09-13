"""Pydantic models returned by tools (they become MCP structured output)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class FileInfo(BaseModel):
    name: str = Field(description="File name without the .ged extension; use this as the `file` argument.")
    size_bytes: int
    modified: str = Field(description="ISO-8601 modification time")


class SurnameCount(BaseModel):
    surname: str
    count: int


class FileSummary(BaseModel):
    file: str
    individuals: int
    families: int
    sources: int
    notes: int
    source_software: str | None = None
    earliest_year: int | None = None
    latest_year: int | None = None
    top_surnames: list[SurnameCount]


class CitationOut(BaseModel):
    source_id: str | None = None
    source_title: str | None = None
    page: str | None = None
    date: str | None = None
    text: str | None = None
    apid: str | None = Field(default=None, description="Ancestry.com record id (_APID)")
    note: str | None = None


class EventOut(BaseModel):
    tag: str
    label: str
    type: str | None = None
    date: str | None = None
    year: int | None = None
    place: str | None = None
    value: str | None = Field(default=None, description="Attribute value, e.g. the occupation for OCCU")
    notes: list[str] = []
    citations: list[CitationOut] = []


class PersonSummary(BaseModel):
    id: str
    name: str
    sex: str | None = None
    birth_date: str | None = None
    birth_place: str | None = None
    death_date: str | None = None
    death_place: str | None = None


class SpouseOut(BaseModel):
    family_id: str
    spouse: PersonSummary | None = None
    marriage_date: str | None = None
    marriage_place: str | None = None
    children: list[PersonSummary] = []


class PersonDetail(BaseModel):
    id: str
    name: str
    given: str
    surname: str
    suffix: str | None = None
    other_names: list[str] = []
    sex: str | None = None
    events: list[EventOut] = []
    notes: list[str] = []
    citations: list[CitationOut] = []
    parents: list[PersonSummary] = []
    families: list[SpouseOut] = Field(default=[], description="One entry per marriage/partnership")
    siblings: list[PersonSummary] = []
    family_ids_as_child: list[str] = []
    last_changed: str | None = None


class FamilyOut(BaseModel):
    id: str
    husband: PersonSummary | None = None
    wife: PersonSummary | None = None
    children: list[PersonSummary] = []
    events: list[EventOut] = []
    notes: list[str] = []
    citations: list[CitationOut] = []


class SourceOut(BaseModel):
    id: str
    title: str | None = None
    author: str | None = None
    publisher: str | None = None
    abbreviation: str | None = None
    repository: str | None = None
    apid: str | None = None
    text: str | None = None
    notes: list[str] = []
    cited_by: list[PersonSummary] = Field(
        default=[], description="Individuals with at least one citation of this source"
    )


class SearchResult(BaseModel):
    total: int
    offset: int
    results: list[PersonSummary]


class AncestorNodeOut(BaseModel):
    person: PersonSummary
    generation: int
    father: AncestorNodeOut | None = None
    mother: AncestorNodeOut | None = None
    truncated: bool = Field(
        default=False, description="True if more ancestors exist beyond the generation limit"
    )


class DescendantFamilyOut(BaseModel):
    family_id: str
    spouse: PersonSummary | None = None
    children: list[DescendantNodeOut] = []


class DescendantNodeOut(BaseModel):
    person: PersonSummary
    generation: int
    families: list[DescendantFamilyOut] = []
    truncated: bool = False


class WriteResult(BaseModel):
    file: str
    id: str | None = Field(default=None, description="Id of the record created or modified")
    message: str
    backup: str | None = Field(default=None, description="Path of the .bak written before saving")
