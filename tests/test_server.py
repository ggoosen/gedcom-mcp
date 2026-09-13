from pathlib import Path

import pytest
from mcp import Client
from mcp.shared.exceptions import MCPError

from gedcom_mcp.config import make_settings
from gedcom_mcp.server import configure, mcp


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client(ged_dir: Path):
    configure(make_settings(str(ged_dir)))
    async with Client(mcp, raise_exceptions=True) as c:
        yield c


async def call(client: Client, tool: str, **args):
    res = await client.call_tool(tool, args)
    assert not res.is_error, res.content
    return res.structured_content


async def call_error(client: Client, tool: str, **args) -> str:
    res = await client.call_tool(tool, args)
    assert res.is_error, res.structured_content
    return res.content[0].text


@pytest.mark.anyio
async def test_lists_tools_and_resources(client: Client) -> None:
    tools = {t.name for t in (await client.list_tools()).tools}
    assert {"list_files", "search_individuals", "get_individual", "add_individual", "set_parents"} <= tools
    templates = {t.uri_template for t in (await client.list_resource_templates()).resource_templates}
    assert templates == {"gedcom://{file}", "gedcom://{file}/person/{id}"}


@pytest.mark.anyio
async def test_list_files_and_summary(client: Client) -> None:
    files = await call(client, "list_files")
    assert [f["name"] for f in files["result"]] == ["smith"]
    summary = await call(client, "file_summary")  # file omitted: only one present
    assert summary["individuals"] == 12
    assert summary["families"] == 4
    assert summary["source_software"].startswith("Ancestry.com")
    assert summary["top_surnames"][0] == {"surname": "Smith", "count": 7}
    assert (summary["earliest_year"], summary["latest_year"]) == (1815, 1960)


@pytest.mark.anyio
async def test_search_and_detail(client: Client) -> None:
    res = await call(client, "search_individuals", file="smith.ged", query="smith", birth_year_from=1890)
    assert [r["name"] for r in res["results"]] == ["George Smith", "Margaret Smith", "Robert Smith"]
    assert res["total"] == 3
    detail = await call(client, "get_individual", id="@I3@")
    assert detail["name"] == "John Smith"
    assert [p["name"] for p in detail["parents"]] == ["William Smith", "Mary Jones"]
    assert detail["families"][0]["spouse"]["name"] == "Anne Müller"
    assert [c["name"] for c in detail["families"][0]["children"]] == ["Robert Smith", "Margaret Smith"]
    assert detail["events"][0]["citations"][0]["apid"] == "1,8912::5522"
    slim = await call(client, "get_individual", id="@I3@", include_sources=False)
    assert slim["events"][0]["citations"] == []


@pytest.mark.anyio
async def test_family_source_and_trees(client: Client) -> None:
    fam = await call(client, "get_family", id="@F1@")
    assert fam["husband"]["name"] == "William Smith"
    assert fam["events"][0]["label"] == "Marriage"
    src = await call(client, "get_source", id="@S2@")
    assert {p["id"] for p in src["cited_by"]} == {"@I1@", "@I3@"}
    anc = await call(client, "get_ancestors", id="@I10@", generations=2)
    assert anc["father"]["father"]["person"]["name"] == "John Smith"
    assert anc["father"]["father"]["truncated"] is True
    desc = await call(client, "get_descendants", id="@I1@", generations=1)
    assert len(desc["families"][0]["children"]) == 3


@pytest.mark.anyio
async def test_write_tools_end_to_end(client: Client, ged_dir: Path) -> None:
    r = await call(
        client,
        "add_individual",
        given="Zed",
        surname="Smith",
        sex="M",
        birth_date="2 feb 1920",
        birth_place="Sydney",
    )
    assert r["id"] == "@I13@"
    assert r["backup"].endswith("smith.ged.bak")
    r = await call(client, "set_parents", child_id="@I13@", father_id="@I7@", mother_id="@I9@")
    assert r["id"] == "@F3@"
    await call(client, "set_event", id="@I13@", tag="OCCU", value="Engineer", date="1945")
    await call(client, "add_note", id="@I13@", text="Added by test")
    detail = await call(client, "get_individual", id="@I13@")
    assert [p["name"] for p in detail["parents"]] == ["Robert Smith", "Alice Brown"]
    assert [s["name"] for s in detail["siblings"]] == ["George Smith"]
    assert detail["events"][1]["value"] == "Engineer"
    assert detail["notes"] == ["Added by test"]
    # the change is on disk, not just in memory
    assert b"1 NAME Zed /Smith/" in (ged_dir / "smith.ged").read_bytes()
    r = await call(client, "remove_individual", id="@I13@")
    assert "Zed Smith" in r["message"]
    res = await call(client, "search_individuals", query="zed")
    assert res["total"] == 0


@pytest.mark.anyio
async def test_create_and_rename_file(client: Client, ged_dir: Path) -> None:
    await call(client, "create_file", name="new")
    assert (ged_dir / "new.ged").exists()
    await call(client, "rename_file", file="new", new_name="renamed")
    assert not (ged_dir / "new.ged").exists() and (ged_dir / "renamed.ged").exists()
    files = await call(client, "list_files")
    assert [f["name"] for f in files["result"]] == ["renamed", "smith"]
    assert "already exists" in await call_error(client, "rename_file", file="renamed", new_name="smith")
    # two files now -> `file` becomes mandatory
    assert "Several GEDCOM files" in await call_error(client, "file_summary")


@pytest.mark.anyio
async def test_path_escape_is_rejected(client: Client) -> None:
    for bad in ("../smith", r"..\smith", "C:/Windows/win.ini", "sub/smith", "*", "smith" + chr(0)):
        assert "Invalid file name" in await call_error(client, "file_summary", file=bad), bad
    assert "No GEDCOM file named" in await call_error(client, "file_summary", file="missing")
    assert "No individual" in await call_error(client, "get_individual", id="@I999@")


@pytest.mark.anyio
async def test_resources(client: Client) -> None:
    res = await client.read_resource("gedcom://smith")
    assert res.contents[0].text.startswith("# smith.ged")
    res = await client.read_resource("gedcom://smith/person/@I1@")
    text = res.contents[0].text
    assert text.startswith("# William Smith (@I1@)")
    assert "- Occupation: 1881, Bristol, Gloucestershire, England, Blacksmith" in text
    with pytest.raises(MCPError):
        await client.read_resource("gedcom://smith/person/@I999@")
