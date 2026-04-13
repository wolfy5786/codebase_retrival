from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote


def lsp_uri_to_repo_rel(uri: str, workspace_root: str) -> str | None:
    """Map ``file:`` URI to repo-relative path using forward slashes."""
    if not uri or not uri.startswith("file:"):
        return None
    raw = uri[7:]
    if raw.startswith("//"):
        raw = raw[2:]
    raw = unquote(raw)
    if raw.startswith("/") and len(raw) > 2 and raw[2] == ":":
        raw = raw.lstrip("/")
    path = Path(raw)
    try:
        rel = path.resolve().relative_to(Path(workspace_root).resolve())
        return str(rel).replace("\\", "/")
    except ValueError:
        return None


def match_stored_path(resolved_rel: str, all_paths: set[str]) -> str | None:
    """Match ``resolved_rel`` to a ``CodeNode.path`` value (case-insensitive on Windows)."""
    if resolved_rel in all_paths:
        return resolved_rel
    if os.name == "nt":
        want = resolved_rel.replace("\\", "/").lower()
        for path in all_paths:
            if path.replace("\\", "/").lower() == want:
                return path
    return None


def lsp_range_start_line_1based(rng: dict | None) -> int:
    if not rng:
        return 1
    start = rng.get("start") or {}
    return int(start.get("line", 0)) + 1


def abs_path_for_file(workspace_root: str, rel_path: str) -> str:
    """Absolute path for LSP (native casing; no lowercasing)."""
    return str((Path(workspace_root) / rel_path).resolve())
