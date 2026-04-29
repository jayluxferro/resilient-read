# resilient-read JSON-RPC examples

These examples show minimal JSON-RPC payloads for MCP `tools/call` requests and representative responses.

## Notes

- Replace `id` values as needed.
- `result.content[0].text` is a JSON string produced by the `resilient-read` server.
- Paths are workspace-relative.

## Files

- `rr.stat.json`
- `rr.read_bytes.json`
- `rr.read_lines.json`
- `rr.read_tail.json`
- `rr.search_then_page.json`
- `rr.make_cursor.json`
- `rr.read_next.json`
