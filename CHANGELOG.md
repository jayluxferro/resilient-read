# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.1] - 2026-04-29

### Added

- README transport docs for running the MCP server over `stdio`, `sse`, and streamable `http`.
- README config snippets for SSE (`/sse`) and HTTP (`/mcp`) MCP client connections.
- Published PyPI package reference and install instructions.
- End-to-end MCP stdio integration tests using `mcp.ClientSession` to validate tool wiring and handshake behavior.
- `rr.read_tail` for tail-window reads on large append-only files.
- `rr.search_then_page` for query-driven navigation with line-context excerpts and pagination.
- Example JSON-RPC request/response payloads for each tool plus a full multi-call session.
- Initial release scaffolding: CI workflow, MIT license, and manual release playbook.

### Fixed

- `rr.search_then_page` now reports `has_more=true` only when additional query matches actually exist.
- Added regression assertions for `has_more` behavior and ignored local `tmp/` fixtures in git.

## [0.1.0] - 2026-04-29

### Added

- Initial `resilient-read` MCP server with chunk-friendly read primitives.
- Core tools: `rr.stat`, `rr.read_bytes`, `rr.read_lines`, `rr.make_cursor`, `rr.read_next`.
- Cursor drift detection using file size and mtime snapshots.
- Python package metadata and `uv`-based development setup.

[Unreleased]: https://github.com/jayluxferro/resilient-read/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/jayluxferro/resilient-read/releases/tag/v0.1.1
[0.1.0]: https://github.com/jayluxferro/resilient-read/releases/tag/v0.1.0
