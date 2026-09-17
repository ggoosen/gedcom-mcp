# gedcom-mcp

[![CI](https://github.com/ggoosen/gedcom-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/ggoosen/gedcom-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-Python%20SDK%202.x-purple.svg)](https://github.com/modelcontextprotocol/python-sdk)
[![M8ven Live Monitored](https://m8ven.ai/badge/mcp/ggoosen-gedcom-mcp-1k4mv1)](https://m8ven.ai/mcp/ggoosen-gedcom-mcp-1k4mv1)
[![M8ven Live Monitored](https://m8ven.ai/badge/mcp/ggoosen-gedcom-mcp-1k4mv1?variant=verified)](https://m8ven.ai/mcp/ggoosen-gedcom-mcp-1k4mv1)

A [Model Context Protocol](https://modelcontextprotocol.io) server that lets Claude (or any MCP
client) **read, search and edit GEDCOM `.ged` family-tree files** — the export format used by
Ancestry.com, FamilySearch, MyHeritage, Gramps, RootsMagic, Family Tree Maker and most other
genealogy software.

Point it at a folder of `.ged` files and ask things like:

> *"Who were the parents of John Smith, born about 1840 in Bristol?"*
> *"Show me four generations of ancestors for @I123@."*
> *"Add a burial for Mary Jones on 3 May 1901 at St Mary's, Islington."*
> *"Which source records cite the 1881 census?"*

Edits are written straight back to the file — safely, with a backup, and without disturbing
anything you didn't touch.

---

## Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Running the server](#running-the-server)
- [Connecting an MCP client](#connecting-an-mcp-client)
  - [Claude Code](#claude-code)
  - [Claude Desktop](#claude-desktop)
  - [Cursor, Windsurf, VS Code and others](#cursor-windsurf-vs-code-and-others)
- [Usage](#usage)
  - [Ids and file names](#ids-and-file-names)
  - [Dates](#dates)
  - [Example conversations](#example-conversations)
- [Tool reference](#tool-reference)
  - [Read tools](#read-tools)
  - [Write tools](#write-tools)
  - [Resources](#resources)
- [How editing works (safety guarantees)](#how-editing-works-safety-guarantees)
- [Working with Ancestry.com exports](#working-with-ancestrycom-exports)
- [Development](#development)
- [Architecture](#architecture)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## Features

- **Current MCP SDK** — built on `mcp>=2.2` (`MCPServer`, structured/typed output, tool
  annotations for read-only / destructive hints).
- **Proper search** — free-text name search that is case- and accent-insensitive
  (`Müller` matches `muller`), ranked by match quality; filter by given name, surname, birth/death
  year ranges, place and sex; paginated.
- **Relationship navigation** — parents, spouses, children, siblings; N-generation pedigree
  (ancestor) and descendant trees, with children grouped per marriage.
- **Sources, citations and notes** — full source records, per-fact citations (including
  Ancestry's `_APID` record ids), and note text everywhere it appears.
- **Editing** — add, update and remove people; create or update any event/fact; add notes; create
  families; link children to parents; delete people cleanly (all back-references removed).
- **Lossless** — the file is held as a line tree and only lines you actually change are
  re-rendered. Unknown and vendor tags (`_APID`, `_OID`, `OBJE`, `_MILT`, …), record order,
  character encoding, byte-order mark and line endings all survive byte-for-byte. Round-tripping a
  file without edits produces an identical file.
- **Safe** — every edit writes a `<name>.ged.bak` first, then saves atomically. File names are
  plain names inside the configured directory: no path traversal, no globs, no writes anywhere else.
- **No log files** — diagnostics go to stderr only; nothing is written next to your data.
- **Any GEDCOM 5.5 / 5.5.1 file** — tested against Ancestry.com exports (BOM + CRLF, ~2,300
  people) and standard fixtures.

## Requirements

- Python **3.10 or newer**
- [`uv`](https://docs.astral.sh/uv/) (recommended) or `pip`
- An MCP client — Claude Code, Claude Desktop, Cursor, VS Code Copilot, etc.

## Installation

Clone the repository and create a virtual environment:

```bash
git clone https://github.com/ggoosen/gedcom-mcp.git
cd gedcom-mcp

# with uv (recommended)
uv venv
uv pip install -e .

# or with plain pip
python -m venv .venv
.venv/Scripts/activate        # Windows
source .venv/bin/activate     # macOS / Linux
pip install -e .
```

This installs a `gedcom-mcp` console script into the virtual environment:

| Platform | Executable |
|---|---|
| Windows | `<repo>\.venv\Scripts\gedcom-mcp.exe` |
| macOS / Linux | `<repo>/.venv/bin/gedcom-mcp` |

You'll need that full path when registering the server with a client (clients don't activate
your venv for you).

> **Tip:** if you'd rather not clone, `uv tool install git+https://github.com/ggoosen/gedcom-mcp`
> installs `gedcom-mcp` onto your `PATH`, or run it ad hoc with
> `uvx --from git+https://github.com/ggoosen/gedcom-mcp gedcom-mcp --gedcom-path DIR`.

## Running the server

The server speaks MCP over **stdio**. It takes one required setting — the directory that holds
your `.ged` files:

```bash
gedcom-mcp --gedcom-path "C:/Users/you/Documents/Genealogy"
# or
GEDCOM_PATH="/home/you/genealogy" gedcom-mcp
```

Options:

| Flag | Description |
|---|---|
| `--gedcom-path DIR` | Directory containing `.ged` files. Falls back to the `GEDCOM_PATH` environment variable. Required. |
| `-v`, `--verbose` | Debug logging on stderr. |
| `-h`, `--help` | Show help. |

Run from a terminal it will simply wait for a client on stdin — that's normal. Press `Ctrl+C` to
exit. Normally you don't run it yourself; the MCP client launches it.

**Put your files in a dedicated folder.** The server can read and *write* every `.ged` in the
directory, so don't point it at a folder that also holds files you'd rather it never touched.
Keep your own backups too — the `.bak` only holds the state before the *most recent* edit.

## Connecting an MCP client

### Claude Code

Register the server for the current project (local scope):

```bash
# Windows
claude mcp add gedcom -- "C:/path/to/gedcom-mcp/.venv/Scripts/gedcom-mcp.exe" --gedcom-path "C:/Users/you/Documents/Genealogy"

# macOS / Linux
claude mcp add gedcom -- /path/to/gedcom-mcp/.venv/bin/gedcom-mcp --gedcom-path /home/you/genealogy
```

Add `--scope user` to make it available in every project, or `--scope project` to write a
shareable `.mcp.json` into the current repo. Check with `claude mcp list`; remove with
`claude mcp remove gedcom`.

Equivalent `.mcp.json` (project scope):

```json
{
  "mcpServers": {
    "gedcom": {
      "type": "stdio",
      "command": "C:/path/to/gedcom-mcp/.venv/Scripts/gedcom-mcp.exe",
      "args": ["--gedcom-path", "C:/Users/you/Documents/Genealogy"]
    }
  }
}
```

Once registered, start Claude Code in that project and the tools appear as `mcp__gedcom__*`.
Try: *"list the gedcom files and give me a summary of the first one."*

### Claude Desktop

Edit `claude_desktop_config.json` (**Settings → Developer → Edit Config**):

- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "gedcom": {
      "command": "C:/path/to/gedcom-mcp/.venv/Scripts/gedcom-mcp.exe",
      "args": ["--gedcom-path", "C:/Users/you/Documents/Genealogy"]
    }
  }
}
```

Restart Claude Desktop. The server shows up under the tools (🔨) icon.

### Cursor, Windsurf, VS Code and others

Any client that supports stdio MCP servers works with the same shape — a `command` and `args`.
For example, VS Code (`.vscode/mcp.json`):

```json
{
  "servers": {
    "gedcom": {
      "type": "stdio",
      "command": "/path/to/gedcom-mcp/.venv/bin/gedcom-mcp",
      "args": ["--gedcom-path", "/home/you/genealogy"]
    }
  }
}
```

You can also pass the directory via the environment instead of `args`:

```json
"env": { "GEDCOM_PATH": "/home/you/genealogy" }
```

## Usage

The intended workflow is:

1. `list_files` (or `file_summary`) — see what's there.
2. `search_individuals` — find people and get their ids.
3. `get_individual` / `get_family` / `get_ancestors` / `get_descendants` / `get_source` — drill in.
4. The write tools — make changes; each returns a short confirmation and saves immediately.

Claude figures this out on its own from the tool descriptions; you just ask questions in plain
English.

### Ids and file names

- **Record ids** are GEDCOM cross-references *including the `@` signs*: `@I12@` (individual),
  `@F3@` (family), `@S7@` (source). Ancestry exports use long numeric ids such as
  `@I200180069284@`; those work too.
- **File names** are plain names relative to the configured directory, with or without the
  `.ged` extension: `Smith Family Tree` or `Smith Family Tree.ged`. Path separators, `..`, globs
  and control characters are rejected.
- **`file` may be omitted** on every tool when the directory contains exactly one `.ged` file.
  With several files, the error message lists the available names.

### Dates

Dates are GEDCOM-style and are normalised on write:

| Input | Meaning |
|---|---|
| `12 MAR 1840` | Exact date |
| `MAR 1840`, `1840` | Partial date |
| `ABT 1845` / `EST 1845` / `CAL 1845` | Approximate / estimated / calculated |
| `BEF 1900` / `AFT 1900` | Before / after |
| `BET 1930 AND 1935` | Range |
| `FROM 1901 TO 1905` | Period |

Year filters in `search_individuals` (`birth_year_from`, etc.) understand all of these forms.

### Example conversations

**Finding someone**

> **You:** Find anyone called Smith born in Bristol between 1830 and 1850.
>
> Claude calls `search_individuals(surname="Smith", place="Bristol", birth_year_from=1830, birth_year_to=1850)`
> and returns a ranked list with ids, life spans and birth places.

**Exploring a family**

> **You:** Show me William Smith's family and four generations of his ancestors.
>
> Claude calls `get_individual(id="@I1@")` — parents, every marriage with its children, siblings,
> all facts with citations — then `get_ancestors(id="@I1@", generations=4)`.

**Correcting a record**

> **You:** William's birth date is wrong — it should be 12 March 1841, and add a note that this
> came from his baptism register entry.
>
> Claude calls `set_event(id="@I1@", tag="BIRT", date="12 MAR 1841")` and
> `add_note(id="@I1@", text="Birth date corrected from baptism register …")`. Both save
> immediately with a `.bak` written first.

**Adding a new person and linking them**

> **You:** Add a daughter for William and Mary, Elizabeth, born 4 June 1866 in Bristol.
>
> Claude calls `add_individual(given="Elizabeth", surname="Smith", sex="F", birth_date="4 JUN 1866", birth_place="Bristol, Gloucestershire, England")`
> which returns `@I9@`, then `set_parents(child_id="@I9@", father_id="@I1@", mother_id="@I2@")` —
> reusing William and Mary's existing family record.

**Tracing sources**

> **You:** What does source @S2@ cover and who is cited against it?
>
> Claude calls `get_source(id="@S2@")` — title, author, publisher, repository, Ancestry `_APID`,
> and every individual/fact that cites it.

## Tool reference

Every tool accepts an optional `file` argument (see [Ids and file names](#ids-and-file-names)).

### Read tools

All read tools are annotated `readOnlyHint` so well-behaved clients won't prompt for approval.

| Tool | Parameters | Returns |
|---|---|---|
| `list_files` | — | Each `.ged` file: name, size, modified time. |
| `file_summary` | `file` | Record counts (individuals, families, sources, notes), originating software, earliest/latest year, top surnames. |
| `search_individuals` | `query` (free-text name), `given`, `surname`, `birth_year_from`, `birth_year_to`, `death_year_from`, `death_year_to`, `place`, `sex` (`M`/`F`), `limit` (1–200, default 25), `offset` | Ranked matches with id, name, sex, birth and death (date + place), plus `total` for pagination. |
| `get_individual` | `id`, `include_sources` (default true), `include_notes` (default true) | Full record: all names, every event/fact with date, place, value, citations and notes; parents; each marriage with spouse and children; siblings; `CHAN` timestamp. |
| `get_family` | `id` | Husband, wife, children (with life spans), marriage/divorce and other family events, notes, citations. |
| `get_ancestors` | `id`, `generations` (1–10, default 4) | Pedigree tree — each node is a person with `father` and `mother` sub-trees. |
| `get_descendants` | `id`, `generations` (1–10, default 3) | Descendant tree — each node lists marriages, and each marriage its children as sub-trees. |
| `get_source` | `id` | Title, author, publication, repository, Ancestry `_APID`, notes, and a list of who cites it (person, fact, page). |

### Write tools

Write tools **save immediately**. Each one first writes `<name>.ged.bak`, then replaces the file
atomically, and stamps the touched record with a `CHAN` (change date) entry. Tools that delete
data are annotated `destructiveHint` so clients can ask for confirmation.

| Tool | Parameters | What it does |
|---|---|---|
| `create_file` | `name` | Create a new, empty GEDCOM 5.5.1 file (UTF-8, with header and submitter). |
| `rename_file` | `file`, `new_name` | Rename a file. Refuses to overwrite an existing one. |
| `add_individual` | `given`, `surname`, `sex` (`M`/`F`/`U`), `birth_date`, `birth_place`, `death_date`, `death_place`, `note` | Add a person. Returns the new `@I..@` id — use `set_parents` / `add_family` to link them. |
| `update_individual` | `id`, `given`, `surname`, `sex` | Change name parts and/or sex. Only supplied fields change; other name sub-tags are kept. |
| `set_event` | `id` (person **or** family), `tag`, `date`, `place`, `value`, `type`, `index` (default 0) | Create or update a fact. `tag` is any GEDCOM event/attribute tag — `BIRT`, `DEAT`, `BURI`, `CHR`, `BAPM`, `OCCU`, `RESI`, `CENS`, `EMIG`, `IMMI`, `EVEN`, `FACT`, … or `MARR`/`DIV`/`ENGA` on a family. `value` is the attribute text (e.g. occupation). `type` sets the `TYPE` sub-tag (describes `EVEN`/`FACT`). `index` picks the Nth existing fact with that tag; set it equal to the current count to add another one. |
| `remove_event` | `id`, `tag`, `index` (default 0) | ⚠️ Delete the Nth fact with that tag, including its citations and notes. |
| `add_note` | `id` (any record), `text` | Attach a free-text note. Multi-line text is folded into `CONT`/`CONC` correctly. |
| `add_family` | `husband_id`, `wife_id`, `child_ids`, `marriage_date`, `marriage_place` | Create an `@F..@` record and write the `FAMS`/`FAMC` back-links on every person named. |
| `add_child` | `family_id`, `child_id` | Add an existing person as a child of an existing family. |
| `set_parents` | `child_id`, `father_id`, `mother_id` | Make the named people the child's parents. Reuses the parents' existing family if they already have one together (or fills the empty spouse slot of a one-parent family), otherwise creates a new one. |
| `remove_individual` | `id` | ⚠️ Delete a person and every reference to them (as spouse or child). Families left with no members are removed as well. |

All write tools return a `WriteResult` with the affected id, a human-readable message, and the
path of the backup that was written.

### Resources

For clients that support MCP resources:

| URI | Content |
|---|---|
| `gedcom://{file}` | Markdown summary of the file (same data as `file_summary`). |
| `gedcom://{file}/person/{id}` | A Markdown card for one person — handy to attach to a conversation as context. |

## How editing works (safety guarantees)

GEDCOM files from commercial software are full of vendor extensions, odd ordering and
encoding quirks, and most parsers silently drop or rewrite things they don't understand. This
server avoids that entirely:

1. The file is parsed into a tree of lines, and **every line keeps its original raw bytes**.
2. Only a line that you actually change is re-rendered; everything else is written back exactly
   as it was read. `parse(data).to_bytes() == data` holds for every file we've tried.
3. `CONT`/`CONC` continuation lines are handled as ordinary children of a line, so note text
   with embedded newlines or stray carriage returns round-trips correctly.
4. Before saving, the previous content is copied to `<name>.ged.bak`; the new content is then
   written to a temporary file and atomically renamed over the original, so a crash mid-write
   can't leave you with a truncated file.
5. Edited records get a `CHAN` / `DATE` / `TIME` stamp (local time, per GEDCOM convention) so
   you can see in any genealogy program what was touched.
6. Deleting a person walks every family and removes their `HUSB` / `WIFE` / `CHIL` references;
   families left with nobody in them are deleted too. No dangling pointers.

Files are cached in memory and re-read automatically when their modification time or size
changes, so you can edit them in other software while the server is running.

## Working with Ancestry.com exports

Ancestry's *Export tree* produces a GEDCOM 5.5.1 file with a UTF-8 BOM, CRLF line endings, long
numeric ids and a number of custom tags. All are preserved:

- `_APID` — Ancestry's record-collection id on each citation. Surfaced on citations and sources
  so you can trace a fact back to the exact Ancestry record.
- `_OID`, `_MTYPE`, `_PRIM`, `OBJE` — media links and metadata. Preserved untouched.
- `_MILT`, `_DEG`, `_EMPLOY` etc. — custom facts. Preserved, and readable/editable via
  `set_event` with the raw tag name.

Editing an Ancestry export and re-importing it is up to Ancestry (their importer creates a new
tree rather than merging), but the file stays valid for any desktop program — Family Tree Maker,
RootsMagic, Gramps, Legacy — and for re-upload.

## Development

```bash
uv venv && uv pip install -e ".[dev]"

pytest                                # 51 tests, ~1.5 s
ruff check src tests                  # lint
ruff format src tests                 # format
pyright                               # type-check
python tests/make_fixture.py          # regenerate tests/fixtures/sample.ged
```

Tests cover the lossless parser (round-trip of BOM + CRLF fixtures and files with embedded
`\r`), the person/family model, search ranking and filters, every write tool (save → reload →
assert, and untouched records byte-identical), and the MCP surface itself through an in-memory
`mcp.Client`.

The `.gitattributes` marks `*.ged` as binary so fixture bytes are never altered by line-ending
normalisation on checkout.

## Architecture

```
src/gedcom_mcp/
  __main__.py      CLI entry point (argparse → configure → mcp.run())
  server.py        MCPServer instance; all @mcp.tool / @mcp.resource; converters to schemas
  config.py        Settings: root directory, safe file-name resolution, per-file cache
  schemas.py       pydantic output models (MCP structured output)
  gedcom/
    lines.py       Lossless line tree: GedLine / GedDocument, parse_bytes() / to_bytes()
    file.py        GedcomFile: load, xref index, CHAN stamping, atomic save + .bak
    model.py       Person / Family / Event / Citation / Source views over the line tree
    search.py      ranked search; ancestors() / descendants() walkers
    edit.py        every mutation (add/update/remove person, set_event, families, notes)
    dates.py       year extraction, normalisation, today's date in GEDCOM form
    names.py       "Given /Surname/ Suffix" parsing; accent-insensitive folding
tests/             pytest; fixtures/sample.ged is a synthetic Ancestry-style file
```

Data flows `lines.py` → `file.py` → `model.py` → `search.py` / `edit.py` → `server.py`. The
line tree is the single source of truth; the model classes are thin views over it, and edits
mutate the tree directly so nothing has to be "serialised back".

Dependencies: [`mcp`](https://github.com/modelcontextprotocol/python-sdk) (server framework),
[`pydantic`](https://docs.pydantic.dev/) (output models), and
[`ged4py`](https://ged4py.readthedocs.io/) — used only for its date parser and encoding
detection, not as the storage layer.

## Troubleshooting

**The client says the server failed to start / no tools appear.**
Run the exact command from your config in a terminal. `--gedcom-path` must be an existing
directory; the message will tell you if it isn't. On Windows use forward slashes or escaped
backslashes in JSON.

**`No .ged files in …`**
The directory is right but empty. Files must end in `.ged` (lower-case is safest).

**`Several GEDCOM files are available; pass 'file'`**
More than one `.ged` in the directory — ask for the one you want by name.

**`Invalid file name`**
File names must be bare names (`My Tree` or `My Tree.ged`), not paths.

**Non-ASCII names don't display correctly.**
The file's declared `CHAR` is honoured (UTF-8, ANSEL, ASCII, …) and the encoding is auto-detected
when the header is wrong. If a file was mis-encoded by the exporting software the text will look
wrong everywhere, not just here.

**I want to undo an edit.**
Copy `<name>.ged.bak` back over `<name>.ged`. Only the most recent pre-edit state is kept, so for
longer histories keep the folder under version control or take periodic copies.

**Enable debug output.**
Add `-v` to the args; output goes to stderr, which the client captures in its MCP log (Claude
Desktop: **Settings → Developer → Open Logs Folder**; Claude Code: `/mcp` shows server status).

## License

[MIT](LICENSE) © George Goosen
