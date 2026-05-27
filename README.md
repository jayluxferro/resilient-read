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

## State root vs workspace roots

Two independent concepts, both defaulting to `$PWD`:

| Env var | Purpose | Default |
|---|---|---|
| `RR_STATE_DIR` | Where future resilient-read state lives | first `$RR_WORKSPACE` → `$PWD` |
| `RR_WORKSPACE` | Base directories for relative read paths | `$PWD` |

`RR_WORKSPACE` accepts two formats:

- **Plain string** (backward compatible): `"/Users/jay/my-project"`
- **JSON array** (multi-workspace): `["/Users/jay/proj-a", "/Volumes/Lux/dev/proj-b"]`

When multiple workspaces are configured, relative paths are tried against each
workspace in order — first match wins. Absolute paths are accepted as-is from
anywhere on the filesystem. The first workspace is used as the fallback for
`RR_STATE_DIR`.

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
        "RR_STATE_DIR": "/path/to/your/project",
        "RR_WORKSPACE": "[\"/Users/jay/proj-a\", \"/Volumes/Lux/dev/proj-b\"]"
      }
    }
  }
}
```

`RR_STATE_DIR` is optional — it falls back to `RR_WORKSPACE`, which falls back
to `$PWD`. resilient-read is currently stateless; `RR_STATE_DIR` exists for
forward compatibility.

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
