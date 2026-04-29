"""End-to-end MCP stdio integration tests for resilient-read."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp")

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


@pytest.mark.anyio
async def test_stdio_initialize_and_list_tools(tmp_path: Path) -> None:
    async with stdio_client(_params(tmp_path)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            names = {t.name for t in listed.tools}
            assert "rr.stat" in names
            assert "rr.read_bytes" in names
            assert "rr.read_lines" in names
            assert "rr.read_tail" in names
            assert "rr.search_then_page" in names
            assert "rr.make_cursor" in names
            assert "rr.read_next" in names


@pytest.mark.anyio
async def test_stdio_cursor_round_trip(tmp_path: Path) -> None:
    target = tmp_path / "big.txt"
    target.write_text("0123456789" * 1000, encoding="utf-8")

    async with stdio_client(_params(tmp_path)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            cur_resp = await session.call_tool(
                "rr.make_cursor",
                {"path": "big.txt", "offset": 0, "max_bytes": 100},
            )
            cur_payload = json.loads(_text(cur_resp))
            assert cur_payload["ok"] is True

            next_resp = await session.call_tool(
                "rr.read_next",
                {"cursor": cur_payload["cursor"]},
            )
            next_payload = json.loads(_text(next_resp))
            assert next_payload["ok"] is True
            assert next_payload["bytes_read"] == 100
            assert next_payload["offset"] == 0
            assert next_payload["next_offset"] == 100
            assert next_payload["eof"] is False


@pytest.mark.anyio
async def test_stdio_search_then_page(tmp_path: Path) -> None:
    target = tmp_path / "server.log"
    target.write_text(
        "\n".join(["ok", "timeout one", "ok", "timeout two", "ok"]) + "\n",
        encoding="utf-8",
    )

    async with stdio_client(_params(tmp_path)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            resp = await session.call_tool(
                "rr.search_then_page",
                {
                    "path": "server.log",
                    "query": "timeout",
                    "max_matches": 1,
                    "context_before": 0,
                    "context_after": 0,
                },
            )
            payload = json.loads(_text(resp))
            assert payload["ok"] is True
            assert payload["matches_returned"] == 1
            assert payload["matches"][0]["match_line"] == 2
            assert payload["next_from_line"] == 3


def _params(workspace: Path) -> StdioServerParameters:
    env = dict(os.environ)
    env["RR_WORKSPACE"] = str(workspace)
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "resilient_read.server"],
        env=env,
    )


def _text(result) -> str:
    assert result.content, f"no content in result: {result}"
    return result.content[0].text
