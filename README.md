# resilient-read

[![PyPI version](https://img.shields.io/pypi/v/resilient-read)](https://pypi.org/project/resilient-read/)

MCP server that lets coding agents read very large files safely in **small, resumable chunks**.

## Why this exists

When context windows are small, naive full-file reads are brittle and expensive. `resilient-read` provides deterministic pagination with cursor-based continuation and drift detection.

## Tools

- `rr.stat` - get file metadata (`size`, `mtime_ns`, optional `sha256`)
- `rr.read_bytes` - read byte windows with `offset`, `max_bytes`, `next_offset`, `eof`
- `rr.read_lines` - read line-numbered slices for code/log analysis
- `rr.read_tail` - read only the latest lines from append-only files
- `rr.search_then_page` - search with contextual excerpts and `next_from_line`
- `rr.make_cursor` - mint resumable cursor token
- `rr.read_next` - read next chunk from cursor (fails if file changed)

## Install

```bash
uv sync
```

PyPI (latest): [https://pypi.org/project/resilient-read/](https://pypi.org/project/resilient-read/)

Install from PyPI:

```bash
pip install resilient-read
```

Run with stdio (default):

```bash
uv run resilient-read
```

Run with SSE:

```bash
uv run resilient-read --transport sse --host 127.0.0.1 --port 8000
```

Run with Streamable HTTP:

```bash
uv run resilient-read --transport http --host 127.0.0.1 --port 8000
```

## Path resolution: CWD, workspaces, state

Three independent concepts:

| Env var / source | Purpose | Default |
|---|---|---|
| **CWD** (process working directory) | The default anchor for relative paths supplied by the agent | inherited from the launcher |
| `RR_WORKSPACE` | The *access boundary* — paths must resolve inside one of these roots | CWD |
| `RR_STATE_DIR` | Where future resilient-read state will live | CWD |

### Resolution rules

- **Relative paths** anchor at **CWD** first. If the file isn't there, each
  workspace root is tried in order (first match wins). The fallback for "not
  found" is the CWD-relative candidate so error messages are consistent.
- **Absolute paths** are accepted only if they fall inside *some* workspace
  root. Reads outside all configured workspaces are denied with
  `permission_denied`.
- **CWD is auto-added** to the workspace list if it isn't already inside one of
  the configured roots, so a plain relative path is always within the access
  boundary.
- **State is decoupled** from workspaces. Set `RR_STATE_DIR` to put state
  somewhere specific; otherwise it lives in CWD.

`RR_WORKSPACE` accepts:

- **Plain string**: `"/Users/jay/my-project"`
- **`os.pathsep` list**: `"/Users/jay/a:/Volumes/Lux/dev/b"`
- **JSON array**: `["/Users/jay/a", "/Volumes/Lux/dev/b"]`

### CLI

```bash
# Single workspace
resilient-read -w /Users/jay/proj-a

# Multiple workspaces (repeatable)
resilient-read -w /Users/jay/proj-a -w /Volumes/Lux/dev/proj-b
```

CLI args prepend to `$RR_WORKSPACE`.

## MCP config (stdio)

```json
{
  "mcpServers": {
    "resilient-read": {
      "command": "uvx",
      "args": ["resilient-read"],
      "env": {
        "RR_WORKSPACE": "[\"/Users/jay/proj-a\", \"/Volumes/Lux/dev/proj-b\"]"
      }
    }
  }
}
```

### Running from a checkout: use `--project`, not `--directory`

When launching from a local source checkout via `uv run`, use **`--project`**, not `--directory`:

```json
{
  "command": "uv",
  "args": ["run", "--project", "/path/to/resilient-read-src", "resilient-read"],
  "env": { "RR_WORKSPACE": "[\"/Users/jay\"]" }
}
```

`uv run --directory X` **chdir's** to X before running, which pins the server's
CWD to its own source tree — relative paths from the agent then resolve there
rather than in the agent's project. `--project X` locates the package without
changing CWD, so the server inherits the launcher's CWD (your active project).
For any MCP server that resolves user-supplied relative paths, prefer
`--project`.

`RR_STATE_DIR` is optional — when unset, state lives in CWD. resilient-read is
currently stateless; `RR_STATE_DIR` exists for forward compatibility.

## MCP config (SSE)

```json
{
  "mcpServers": {
    "resilient-read": {
      "type": "sse",
      "url": "http://127.0.0.1:8000/sse"
    }
  }
}
```

## MCP config (HTTP)

```json
{
  "mcpServers": {
    "resilient-read": {
      "type": "http",
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

## Example workflows

### Cursor-based file pagination

1. Call `rr.stat(path="large.log")`
2. Call `rr.make_cursor(path="large.log", offset=0, max_bytes=65536)`
3. Loop on `rr.read_next(cursor=...)` until `eof=true`

### Targeted search pagination

1. Call `rr.search_then_page(path="server.log", query="timeout", max_matches=3)`
2. Follow with `rr.search_then_page(..., from_line=<next_from_line>)`

Each response is small and composable, so you can process huge files while staying inside small model contexts.

## Project housekeeping

- Release notes and version history: `CHANGELOG.md`
- Manual semver tagging flow: `docs/RELEASE.md`
- JSON-RPC examples: `examples/`
