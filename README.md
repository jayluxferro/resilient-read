# resilient-read

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

PyPI release (`0.1.0`): [https://pypi.org/project/resilient-read/0.1.0/](https://pypi.org/project/resilient-read/0.1.0/)

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

## MCP config (stdio)

```json
{
  "mcpServers": {
    "resilient-read": {
      "command": "uvx",
      "args": ["resilient-read"],
      "env": {
        "RR_WORKSPACE": "/path/to/your/project"
      }
    }
  }
}
```

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
