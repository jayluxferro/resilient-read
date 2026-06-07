#!/usr/bin/env python3
"""PostToolUse hook for `mcp__resilient-read__*` tools.

Why this exists
---------------
Claude Code's built-in Edit/Write tools enforce a "file must be read first"
precondition that is satisfied only by the built-in `Read` tool. MCP-served
reads (e.g. `rr.read_lines`) don't register, so an Edit immediately after an
`rr.*` read fails with "File has not been read yet" and Claude has to retry.

The precondition is checked *before* PreToolUse hooks fire, so a PreToolUse
hook cannot intercept the rejection. PostToolUse on the read side is the
workable bridge: after every successful `rr.*` call, inject an
`additionalContext` reminding Claude exactly which `Read(file_path=...)`
call to issue if it intends to Edit/Write the same path.

Wire it up by adding to `~/.claude/settings.json`:

    {
      "hooks": {
        "PostToolUse": [
          {
            "matcher": "mcp__resilient-read__.*",
            "hooks": [
              {
                "type": "command",
                "command": "python3 /absolute/path/to/resilient_read_nudge.py"
              }
            ]
          }
        ]
      }
    }
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _extract_path(tool_input: dict) -> str | None:
    path = tool_input.get("path")
    if not path or not isinstance(path, str):
        return None
    return path


def _resolve_abs(path: str, cwd: str | None = None) -> str:
    """Resolve against the harness's CWD (from hook input) when available."""
    base = Path(cwd) if cwd else Path.cwd()
    try:
        return str((base / path).resolve())
    except (OSError, ValueError):
        return path


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0

    tool_name = payload.get("tool_name", "")
    if not tool_name.startswith("mcp__resilient-read__"):
        return 0

    tool_input = payload.get("tool_input") or {}
    tool_response = payload.get("tool_response") or {}
    if isinstance(tool_response, dict) and tool_response.get("ok") is False:
        return 0

    rel_path = _extract_path(tool_input)
    if not rel_path:
        return 0

    cwd = payload.get("cwd") or None
    abs_path = _resolve_abs(rel_path, cwd)
    message = (
        f"resilient-read served `{rel_path}` (abs: `{abs_path}`). "
        f"The harness Edit/Write gate is satisfied only by the built-in `Read` tool. "
        f"If you intend to modify this file, issue `Read(file_path=\"{abs_path}\")` "
        f"before any Edit/Write — otherwise the edit will fail with "
        f"\"File has not been read yet\"."
    )

    output = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": message,
        }
    }
    sys.stdout.write(json.dumps(output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
