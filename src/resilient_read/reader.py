"""Chunked and resumable reads for large files.

Two independent concerns:

- **state root** — where state lives (future-proofing; ``$RR_STATE_DIR`` if
  set, otherwise the current working directory).
- **workspace roots** — the *access boundary* for user-supplied paths.
  Parsed from ``$RR_WORKSPACE`` (a single path, an ``os.pathsep``-separated
  list, or a JSON array). The current working directory is auto-added if
  not already inside one of the configured roots — so the agent's CWD is
  always inside its own access boundary.

Relative paths anchor at the CWD by default. Absolute paths are accepted
if they fall inside any workspace root. Reads outside all workspace roots
are denied.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .errors import ResilientReadError

_DEFAULT_MAX_BYTES = 64 * 1024
_MAX_BYTES_HARD_LIMIT = 2 * 1024 * 1024
_DEFAULT_MAX_LINES = 400
_MAX_LINES_HARD_LIMIT = 5000
_UNSAFE_ROOTS = frozenset({"/", "/bin", "/sbin", "/usr", "/etc", "/var", "/tmp"})


def _parse_root_list(raw: str) -> list[Path]:
    """Parse env-var content. Accepts JSON array, ``os.pathsep`` list, or plain path."""
    stripped = raw.strip()
    if not stripped:
        return []
    if stripped.startswith("["):
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, list):
                return [Path(p).resolve() for p in parsed if p]
        except json.JSONDecodeError:
            pass
    if os.pathsep in stripped:
        return [Path(p).resolve() for p in stripped.split(os.pathsep) if p]
    return [Path(stripped).resolve()]


def _guard_unsafe(roots: list[Path], env_var: str) -> None:
    for root in roots:
        if str(root) in _UNSAFE_ROOTS:
            raise SystemExit(
                f"resilient-read: refusing to use '{root}' as {env_var}. "
                "Set the variable to your project directory."
            )


def _resolve_roots(env_var: str) -> list[Path]:
    """Return roots from env var, falling back to CWD."""
    override = os.environ.get(env_var)
    roots = _parse_root_list(override) if override else []
    if not roots:
        roots = [Path.cwd().resolve()]
    _guard_unsafe(roots, env_var)
    return roots


def _resolve_root_single(env_var: str) -> Path:
    return _resolve_roots(env_var)[0]


def state_root() -> Path:
    """Return the directory where future resilient-read state will live.

    Uses ``$RR_STATE_DIR`` if set, otherwise the current working directory.
    State is intentionally decoupled from ``$RR_WORKSPACE``.
    """
    if os.environ.get("RR_STATE_DIR"):
        return _resolve_root_single("RR_STATE_DIR")
    root = Path.cwd().resolve()
    if str(root) in _UNSAFE_ROOTS:
        raise SystemExit(
            f"resilient-read: refusing to use '{root}' as state root. "
            "Set $RR_STATE_DIR to your project directory."
        )
    return root


def workspace_roots() -> list[Path]:
    """Return workspace roots (the access boundary).

    Parsed from ``$RR_WORKSPACE``; if unset, falls back to CWD. The current
    working directory is always included — auto-added at the front if it
    isn't already inside one of the configured roots.
    """
    override = os.environ.get("RR_WORKSPACE")
    configured = _parse_root_list(override) if override else []
    cwd = Path.cwd().resolve()

    if not configured:
        roots = [cwd]
    else:
        cwd_inside = any(_path_inside(cwd, ws) for ws in configured)
        roots = configured if cwd_inside else [cwd, *configured]

    _guard_unsafe(roots, "RR_WORKSPACE")
    return roots


def _path_inside(target: Path, root: Path) -> bool:
    """Return True if ``target`` is equal to or nested under ``root``."""
    try:
        target.relative_to(root)
        return True
    except ValueError:
        return False


def _containing_workspace(workspaces: list[Path], target: Path) -> Path | None:
    for ws in workspaces:
        if _path_inside(target, ws):
            return ws
    return None


def _resolve_path(workspaces: list[Path], rel_path: str) -> Path:
    """Resolve a user-supplied path with CWD anchoring + workspace boundary.

    - Relative paths anchor at CWD first; if not found there, fall back to
      each workspace root in order (first match wins).
    - Absolute paths are accepted only if they fall inside some workspace root.
    - The final target must exist and be a regular file.
    """
    p = Path(rel_path)
    if p.is_absolute():
        full = p.resolve()
        if _containing_workspace(workspaces, full) is None:
            raise ResilientReadError(
                "permission_denied", "outside_workspace",
                "Absolute path is not inside any workspace root",
                {"path": rel_path, "resolved": str(full),
                 "workspaces": [str(ws) for ws in workspaces]},
            )
    else:
        cwd = Path.cwd().resolve()
        cwd_candidate = (cwd / rel_path).resolve()
        full = None
        if _path_inside(cwd_candidate, cwd) and cwd_candidate.exists():
            full = cwd_candidate
        else:
            for ws in workspaces:
                candidate = (ws / rel_path).resolve()
                if _path_inside(candidate, ws) and candidate.exists():
                    full = candidate
                    break
        if full is None:
            full = cwd_candidate
    if not full.exists():
        raise ResilientReadError("not_found", "missing", "File not found", {"path": rel_path})
    if not full.is_file():
        raise ResilientReadError("invalid_input", "not_file", "Path is not a file", {"path": rel_path})
    return full


def file_stat(workspaces: list[Path], path: str, include_sha256: bool = False) -> dict[str, Any]:
    full = _resolve_path(workspaces, path)
    st = full.stat()
    data: dict[str, Any] = {
        "ok": True,
        "path": path,
        "size": st.st_size,
        "mtime_ns": st.st_mtime_ns,
    }
    if include_sha256:
        h = hashlib.sha256()
        with full.open("rb") as f:
            for block in iter(lambda: f.read(1024 * 1024), b""):
                h.update(block)
        data["sha256"] = h.hexdigest()
    return data


def _normalize_max_bytes(max_bytes: int | None) -> int:
    val = max_bytes or _DEFAULT_MAX_BYTES
    if val < 1:
        raise ResilientReadError("invalid_input", "range", "max_bytes must be positive")
    if val > _MAX_BYTES_HARD_LIMIT:
        raise ResilientReadError(
            "invalid_input",
            "range",
            f"max_bytes cannot exceed {_MAX_BYTES_HARD_LIMIT}",
        )
    return val


def _normalize_max_lines(max_lines: int | None) -> int:
    cap = max_lines or _DEFAULT_MAX_LINES
    if cap < 1 or cap > _MAX_LINES_HARD_LIMIT:
        raise ResilientReadError(
            "invalid_input",
            "range",
            f"max_lines must be between 1 and {_MAX_LINES_HARD_LIMIT}",
        )
    return cap


def read_bytes(
    workspaces: list[Path],
    path: str,
    *,
    offset: int = 0,
    max_bytes: int | None = None,
    encoding: str = "utf-8",
    errors: str = "replace",
) -> dict[str, Any]:
    full = _resolve_path(workspaces, path)
    if offset < 0:
        raise ResilientReadError("invalid_input", "range", "offset must be >= 0")
    budget = _normalize_max_bytes(max_bytes)

    st = full.stat()
    size = st.st_size
    if offset > size:
        raise ResilientReadError(
            "invalid_input", "range", "offset exceeds file size", {"size": size, "offset": offset}
        )

    with full.open("rb") as f:
        f.seek(offset)
        payload = f.read(budget)

    next_offset = offset + len(payload)
    eof = next_offset >= size
    text = payload.decode(encoding, errors=errors)

    return {
        "ok": True,
        "path": path,
        "offset": offset,
        "bytes_read": len(payload),
        "next_offset": next_offset,
        "eof": eof,
        "size": size,
        "mtime_ns": st.st_mtime_ns,
        "encoding": encoding,
        "content": text,
    }


def read_lines(
    workspaces: list[Path],
    path: str,
    *,
    start_line: int = 1,
    max_lines: int | None = None,
) -> dict[str, Any]:
    full = _resolve_path(workspaces, path)
    if start_line < 1:
        raise ResilientReadError("invalid_input", "range", "start_line must be >= 1")

    cap = _normalize_max_lines(max_lines)

    lines: list[str] = []
    line_no = 0
    with full.open("r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            line_no += 1
            if line_no < start_line:
                continue
            lines.append(f"{line_no}|{raw.rstrip()}")
            if len(lines) >= cap:
                break

    st = full.stat()
    end_line = (start_line + len(lines) - 1) if lines else (start_line - 1)
    return {
        "ok": True,
        "path": path,
        "start_line": start_line,
        "end_line": end_line,
        "lines_returned": len(lines),
        "eof": len(lines) < cap,
        "mtime_ns": st.st_mtime_ns,
        "content": "\n".join(lines),
    }


def read_tail(
    workspaces: list[Path],
    path: str,
    *,
    max_lines: int = 200,
) -> dict[str, Any]:
    full = _resolve_path(workspaces, path)
    cap = _normalize_max_lines(max_lines)

    with full.open("r", encoding="utf-8", errors="replace") as f:
        all_lines = f.readlines()

    total = len(all_lines)
    start_line = max(1, total - cap + 1)
    selected = all_lines[-cap:]
    numbered = [f"{start_line + idx}|{line.rstrip()}" for idx, line in enumerate(selected)]

    st = full.stat()
    return {
        "ok": True,
        "path": path,
        "total_lines": total,
        "start_line": start_line,
        "end_line": start_line + len(numbered) - 1 if numbered else 0,
        "lines_returned": len(numbered),
        "eof": True,
        "mtime_ns": st.st_mtime_ns,
        "content": "\n".join(numbered),
    }


def search_then_page(
    workspaces: list[Path],
    path: str,
    *,
    query: str,
    from_line: int = 1,
    context_before: int = 2,
    context_after: int = 6,
    max_matches: int = 5,
    case_sensitive: bool = False,
) -> dict[str, Any]:
    if not query:
        raise ResilientReadError("invalid_input", "range", "query must not be empty")
    if from_line < 1:
        raise ResilientReadError("invalid_input", "range", "from_line must be >= 1")
    if context_before < 0 or context_after < 0:
        raise ResilientReadError("invalid_input", "range", "context_* must be >= 0")
    if max_matches < 1 or max_matches > 100:
        raise ResilientReadError("invalid_input", "range", "max_matches must be between 1 and 100")

    full = _resolve_path(workspaces, path)
    with full.open("r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    hay_query = query if case_sensitive else query.lower()
    hits: list[dict[str, Any]] = []
    total = len(lines)

    for idx in range(from_line - 1, total):
        line = lines[idx].rstrip("\n")
        hay_line = line if case_sensitive else line.lower()
        if hay_query not in hay_line:
            continue

        start = max(1, idx + 1 - context_before)
        end = min(total, idx + 1 + context_after)
        excerpt_lines = [f"{n}|{lines[n - 1].rstrip()}" for n in range(start, end + 1)]
        hits.append(
            {
                "match_line": idx + 1,
                "start_line": start,
                "end_line": end,
                "excerpt": "\n".join(excerpt_lines),
            }
        )
        if len(hits) >= max_matches:
            break

    st = full.stat()
    next_from_line = hits[-1]["match_line"] + 1 if hits else from_line
    search_start_idx = max(0, next_from_line - 1)
    has_more = False
    for idx in range(search_start_idx, total):
        line = lines[idx].rstrip("\n")
        hay_line = line if case_sensitive else line.lower()
        if hay_query in hay_line:
            has_more = True
            break
    return {
        "ok": True,
        "path": path,
        "query": query,
        "from_line": from_line,
        "next_from_line": next_from_line,
        "matches_returned": len(hits),
        "has_more": has_more,
        "mtime_ns": st.st_mtime_ns,
        "matches": hits,
    }


def make_cursor(workspaces: list[Path], path: str, *, offset: int = 0, max_bytes: int | None = None) -> dict[str, Any]:
    full = _resolve_path(workspaces, path)
    st = full.stat()
    if offset < 0 or offset > st.st_size:
        raise ResilientReadError("invalid_input", "range", "offset out of file bounds")
    budget = _normalize_max_bytes(max_bytes)
    cursor_payload = {
        "path": path,
        "offset": offset,
        "max_bytes": budget,
        "size": st.st_size,
        "mtime_ns": st.st_mtime_ns,
    }
    token = base64.urlsafe_b64encode(json.dumps(cursor_payload, separators=(",", ":")).encode("utf-8")).decode("ascii")
    return {"ok": True, "cursor": token, **cursor_payload}


def read_next(workspaces: list[Path], cursor: str, *, max_bytes: int | None = None) -> dict[str, Any]:
    try:
        decoded = base64.urlsafe_b64decode(cursor.encode("ascii"))
        state = json.loads(decoded.decode("utf-8"))
    except Exception as exc:
        raise ResilientReadError("invalid_input", "cursor_decode", "Cursor token is invalid") from exc

    path = str(state["path"])
    expected_size = int(state["size"])
    expected_mtime = int(state["mtime_ns"])
    offset = int(state["offset"])
    budget = _normalize_max_bytes(max_bytes if max_bytes is not None else int(state["max_bytes"]))

    full = _resolve_path(workspaces, path)
    st = full.stat()
    if st.st_size != expected_size or st.st_mtime_ns != expected_mtime:
        raise ResilientReadError(
            "stale_precondition",
            "file_changed",
            "File changed since cursor was issued",
            {
                "path": path,
                "expected_size": expected_size,
                "actual_size": st.st_size,
                "expected_mtime_ns": expected_mtime,
                "actual_mtime_ns": st.st_mtime_ns,
            },
        )

    result = read_bytes(workspaces, path, offset=offset, max_bytes=budget)
    next_cursor = make_cursor(
        workspaces,
        path,
        offset=int(result["next_offset"]),
        max_bytes=budget,
    )
    result["cursor"] = next_cursor["cursor"]
    return result
