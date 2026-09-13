# gedcom-mcp

MCP server (Python, stdio) that lets Claude read, search and **edit** GEDCOM `.ged` family-tree
files — primarily Ancestry.com exports. Replaces the deprecated `reeeeemo/ancestry-mcp`
(which does not run on MCP SDK 2.x).

## Stack

- Python 3.10, `uv` for venv/lock. Venv at `.venv` (Windows: `.venv/Scripts/python`).
- `mcp>=2.2` — high-level `MCPServer` (v2 name for FastMCP). `ToolError` for user-facing errors.
- `ged4py` — used **only** for `date.DateValue` (date parsing) and `parser.guess_codec`
  (encoding). It is read-only, so it is *not* the storage layer.
- `pydantic` models in `schemas.py` are the tool return types (MCP structured output).

## Layout

```
src/gedcom_mcp/
  __main__.py      CLI: gedcom-mcp --gedcom-path DIR [-v]   (or GEDCOM_PATH env)
  server.py        MCPServer instance, all @mcp.tool / @mcp.resource, converters to schemas
  config.py        Settings: root dir, safe file-name resolution, per-file cache (mtime+size)
  schemas.py       pydantic output models
  gedcom/
    lines.py       LOSSLESS line tree (GedLine/GedDocument). parse_bytes / to_bytes.
    file.py        GedcomFile: load, xref index, CHAN stamping, atomic save + .bak
    model.py       Person / Family / Event / Citation / Source views over GedLine
    search.py      ranked search, ancestors()/descendants() walkers
    edit.py        all mutations (add/update/remove person, set_event, families, notes)
    dates.py       year_of(), normalize(), today_gedcom()
    names.py       parse "Given /Surname/ Suffix", fold() for accent-insensitive matching
tests/             pytest; fixtures/sample.ged is an Ancestry-style file (BOM + CRLF)
```

## Non-negotiable design rules

1. **Lossless round-trip.** Every `GedLine` keeps its raw source line and only re-renders when
   mutated (setters clear `_raw`). Unknown/vendor tags (`_APID`, `_OID`, `OBJE`, …), order,
   encoding, BOM, line endings and even stray `\r` inside note values must survive untouched.
   `parse_bytes(data).to_bytes() == data` must hold for any real export. Test this against a
   real Ancestry export (LF endings, embedded CRs) as well as the CRLF fixture.
2. **CONT/CONC are ordinary children.** Read folded text via `GedLine.text`; write via
   `GedLine.set_text()`. Never edit `.value` of a line that has continuation children.
3. **Edits go through `gedcom/edit.py`**, stamp `CHAN` via `GedcomFile.stamp()`, and the tool
   in `server.py` calls `_save()` (writes `<name>.ged.bak` first, then atomic replace).
4. **File names are plain stems inside the configured directory.** `Settings.resolve()` /
   `resolve_new()` reject separators, globs, `..`, control chars. Keep it that way.
5. **No log files.** Logging goes to stderr only (the old server littered `mcp_ancestry.log`).
6. Ids are GEDCOM xrefs with the `@` signs (`@I12@`, `@F3@`, `@S7@`). Ancestry uses long
   numeric ids (`@I200180069284@`); `GedDocument.next_xref()` handles both.

## Commands

```bash
uv pip install --python .venv -e ".[dev]"
.venv/Scripts/python -m pytest -q          # 51 tests, ~1.5 s
.venv/Scripts/ruff check src tests && .venv/Scripts/ruff format src tests
.venv/Scripts/python tests/make_fixture.py # regenerate tests/fixtures/sample.ged
```

Register in Claude Code with
`claude mcp add gedcom -- <path-to>/.venv/Scripts/gedcom-mcp.exe --gedcom-path <dir>`
(see README for other clients).

## Adding a tool

1. Logic in `gedcom/edit.py` (mutations) or `gedcom/search.py` / `model.py` (reads); raise
   `EditError` for user mistakes.
2. Output model in `schemas.py`.
3. `@mcp.tool(annotations=READ_ONLY | WRITE | DESTRUCTIVE)` in `server.py`; open the file with
   `_open(file)`, wrap edit calls in `_edit(...)`, finish writes with `_save(...)`.
4. Add a case to `tests/test_server.py` (in-memory `mcp.Client`) and, for edits,
   `tests/test_write.py` (save → reload → assert; untouched records byte-identical).

## Gotchas

- `ruff` is configured in `pyproject.toml` (E/F/I/UP/B/RUF, E501 off). Local-time `CHAN`
  stamps are intentional (GEDCOM convention).
- `.gitattributes` marks `*.ged` as `-text` so fixtures keep exact bytes on checkout.
- Tool errors surface to clients as `is_error` results, not exceptions — tests use
  `call_error()` helper, not `pytest.raises`.
- Writing Python source via bash heredocs mangles `\n`/`\r` escapes in this environment;
  use the Write/Edit tools for source files.
