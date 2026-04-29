"""MCP entrypoint for resilient-read."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from .errors import ResilientReadError
from .reader import (
    file_stat,
    make_cursor,
    read_bytes,
    read_lines,
    read_next,
    read_tail,
    search_then_page,
    workspace_root,
)

SERVER_NAME = "resilient-read"

_STAT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["path"],
    "properties": {
        "path": {"type": "string"},
        "include_sha256": {"type": "boolean", "default": False},
    },
    "additionalProperties": False,
}

_READ_BYTES_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["path"],
    "properties": {
        "path": {"type": "string"},
        "offset": {"type": "integer", "minimum": 0, "default": 0},
        "max_bytes": {"type": "integer", "minimum": 1, "default": 65536},
        "encoding": {"type": "string", "default": "utf-8"},
        "errors": {"type": "string", "default": "replace"},
    },
    "additionalProperties": False,
}

_READ_LINES_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["path"],
    "properties": {
        "path": {"type": "string"},
        "start_line": {"type": "integer", "minimum": 1, "default": 1},
        "max_lines": {"type": "integer", "minimum": 1, "default": 400},
    },
    "additionalProperties": False,
}

_READ_TAIL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["path"],
    "properties": {
        "path": {"type": "string"},
        "max_lines": {"type": "integer", "minimum": 1, "default": 200},
    },
    "additionalProperties": False,
}

_SEARCH_THEN_PAGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["path", "query"],
    "properties": {
        "path": {"type": "string"},
        "query": {"type": "string"},
        "from_line": {"type": "integer", "minimum": 1, "default": 1},
        "context_before": {"type": "integer", "minimum": 0, "default": 2},
        "context_after": {"type": "integer", "minimum": 0, "default": 6},
        "max_matches": {"type": "integer", "minimum": 1, "maximum": 100, "default": 5},
        "case_sensitive": {"type": "boolean", "default": False},
    },
    "additionalProperties": False,
}

_MAKE_CURSOR_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["path"],
    "properties": {
        "path": {"type": "string"},
        "offset": {"type": "integer", "minimum": 0, "default": 0},
        "max_bytes": {"type": "integer", "minimum": 1, "default": 65536},
    },
    "additionalProperties": False,
}

_READ_NEXT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["cursor"],
    "properties": {
        "cursor": {"type": "string"},
        "max_bytes": {"type": "integer", "minimum": 1},
    },
    "additionalProperties": False,
}

_TOOL_DEFINITIONS: list[Tool] = [
    Tool(
        name="rr.stat",
        description=(
            "Get size and mtime for a workspace-relative file before chunked reads. "
            "Optionally include SHA-256 for strict integrity checks."
        ),
        inputSchema=_STAT_SCHEMA,
    ),
    Tool(
        name="rr.read_bytes",
        description=(
            "Read a byte window from a file and return text content plus next_offset/eof. "
            "Use for large-file pagination when context windows are small."
        ),
        inputSchema=_READ_BYTES_SCHEMA,
    ),
    Tool(
        name="rr.read_lines",
        description=(
            "Read line-numbered text windows (N lines at a time). Useful for code review "
            "or logs where stable line anchors matter."
        ),
        inputSchema=_READ_LINES_SCHEMA,
    ),
    Tool(
        name="rr.read_tail",
        description=(
            "Read the last N lines of a file with line numbers. Useful for logs or append-only "
            "artifacts when only the newest region matters."
        ),
        inputSchema=_READ_TAIL_SCHEMA,
    ),
    Tool(
        name="rr.search_then_page",
        description=(
            "Find query matches and return compact contextual excerpts with `next_from_line` "
            "for paginated follow-up calls."
        ),
        inputSchema=_SEARCH_THEN_PAGE_SCHEMA,
    ),
    Tool(
        name="rr.make_cursor",
        description=(
            "Create a resumable cursor token for a file path+offset+budget. "
            "Cursor embeds file mtime/size to detect drift."
        ),
        inputSchema=_MAKE_CURSOR_SCHEMA,
    ),
    Tool(
        name="rr.read_next",
        description=(
            "Advance a cursor and return next chunk. Rejects stale cursors if the file changed "
            "since cursor creation."
        ),
        inputSchema=_READ_NEXT_SCHEMA,
    ),
]

_SERVER_INSTRUCTIONS = (
    "This workspace has the resilient-read MCP server active. "
    "Use rr.read_bytes or rr.read_lines for small-window retrieval instead of monolithic reads. "
    "For long files, create a cursor with rr.make_cursor and iterate with rr.read_next. "
    "For append-only files use rr.read_tail; for targeted navigation use rr.search_then_page. "
    "Always respect eof and next_offset; avoid re-reading overlapping ranges unless needed."
)


def _dispatch(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    workspace = workspace_root()
    if name == "rr.stat":
        return file_stat(
            workspace,
            arguments["path"],
            include_sha256=bool(arguments.get("include_sha256", False)),
        )
    if name == "rr.read_bytes":
        return read_bytes(
            workspace,
            arguments["path"],
            offset=int(arguments.get("offset", 0)),
            max_bytes=arguments.get("max_bytes"),
            encoding=arguments.get("encoding", "utf-8"),
            errors=arguments.get("errors", "replace"),
        )
    if name == "rr.read_lines":
        return read_lines(
            workspace,
            arguments["path"],
            start_line=int(arguments.get("start_line", 1)),
            max_lines=arguments.get("max_lines"),
        )
    if name == "rr.read_tail":
        return read_tail(
            workspace,
            arguments["path"],
            max_lines=int(arguments.get("max_lines", 200)),
        )
    if name == "rr.search_then_page":
        return search_then_page(
            workspace,
            arguments["path"],
            query=arguments["query"],
            from_line=int(arguments.get("from_line", 1)),
            context_before=int(arguments.get("context_before", 2)),
            context_after=int(arguments.get("context_after", 6)),
            max_matches=int(arguments.get("max_matches", 5)),
            case_sensitive=bool(arguments.get("case_sensitive", False)),
        )
    if name == "rr.make_cursor":
        return make_cursor(
            workspace,
            arguments["path"],
            offset=int(arguments.get("offset", 0)),
            max_bytes=arguments.get("max_bytes"),
        )
    if name == "rr.read_next":
        return read_next(
            workspace,
            arguments["cursor"],
            max_bytes=arguments.get("max_bytes"),
        )
    raise ResilientReadError("policy_violation", "unknown_tool", "Unknown tool", {"tool": name})


def _envelope_or_error(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    try:
        return _dispatch(name, arguments)
    except ResilientReadError as exc:
        env = exc.to_envelope()
        env.setdefault("context", {}).setdefault("tool", name)
        return env


def build_server() -> Server:
    server: Server = Server(SERVER_NAME, instructions=_SERVER_INSTRUCTIONS)

    @server.list_tools()
    async def _list_tools() -> list[Tool]:
        return list(_TOOL_DEFINITIONS)

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        result = _envelope_or_error(name, arguments or {})
        return [TextContent(type="text", text=json.dumps(result, separators=(",", ":"), sort_keys=True))]

    return server


async def _run_stdio() -> None:
    server = build_server()
    init_options = server.create_initialization_options()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, init_options)


async def _run_sse(host: str, port: int) -> None:
    import uvicorn
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.routing import Mount, Route

    server = build_server()
    init_options = server.create_initialization_options()
    sse = SseServerTransport("/messages/")

    async def handle_sse(request):  # type: ignore[no-untyped-def]
        async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
            await server.run(streams[0], streams[1], init_options)

    app = Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse.handle_post_message),
        ]
    )

    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    srv = uvicorn.Server(config)
    await srv.serve()


async def _run_streamable_http(host: str, port: int) -> None:
    import contextlib

    import uvicorn
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
    from starlette.applications import Starlette
    from starlette.routing import Mount

    server = build_server()
    session_manager = StreamableHTTPSessionManager(app=server, stateless=False)

    @contextlib.asynccontextmanager
    async def lifespan(app):  # type: ignore[no-untyped-def]
        async with session_manager.run():
            yield

    app = Starlette(routes=[Mount("/mcp", app=session_manager.handle_request)], lifespan=lifespan)
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    srv = uvicorn.Server(config)
    await srv.serve()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(prog="resilient-read", description="Resilient-read MCP server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "http"],
        default="stdio",
        help="Transport to use: stdio (default), sse, or http",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind host for sse/http transports")
    parser.add_argument("--port", type=int, default=8000, help="Bind port for sse/http transports")
    args = parser.parse_args()

    if args.transport == "stdio":
        asyncio.run(_run_stdio())
    elif args.transport == "sse":
        asyncio.run(_run_sse(args.host, args.port))
    else:
        asyncio.run(_run_streamable_http(args.host, args.port))


if __name__ == "__main__":
    main()
