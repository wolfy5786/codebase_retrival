"""
Phase 1 crawl: structural nodes and CONTAINS only.

- Labels: `CodeNode` on every node; one mutually exclusive file-type label for
  whole-file nodes (Dockerfile, MarkupFile, etc.). No semantic labels.
- LSP: `textDocument/documentSymbol` for File-typed source files only.
- Properties: id, codebase_id, name, language, path, storage_ref, start_line,
  end_line, kind, signature, detail (Phase 2 consumes kind/detail).
"""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from .languages import get_phase1_strategy_for_file
from ..lsp.client import LspClient

logger = logging.getLogger(__name__)

# Source extensions treated as `File` (LSP-backed when a server is available).
_FILE_SOURCE_EXTENSIONS = frozenset({
    ".py", ".java", ".kt", ".go", ".js", ".ts", ".tsx", ".jsx",
    ".c", ".cpp", ".h", ".hpp", ".cc", ".cxx",
    ".rs", ".rb", ".php", ".swift", ".m", ".mm", ".cs", ".scala",
})

_MARKUP_EXTENSIONS = frozenset({
    ".json", ".yaml", ".yml", ".xml", ".toml", ".ini", ".cfg", ".properties", ".html",
})

_DOCUMENTATION_EXTENSIONS = frozenset({".md", ".txt", ".rst", ".adoc"})

_SQL_EXTENSIONS = frozenset({".sql", ".cql", ".cypher", ".mongo", ".hql"})


def classify_file(rel_path: str) -> str | None:
    """
    Classify a repo-relative path into a Phase-1 file-type bucket.

    Returns one of: File, Dockerfile, MarkupFile, Documentation, SQLNoSQLScript,
    CICD, or None if the path should not be ingested as a graph node.
    """
    p = rel_path.replace("\\", "/").strip()
    if not p:
        return None

    name = Path(p).name
    lower = name.lower()
    suffix = Path(p).suffix.lower()

    # Dockerfile (before generic extension checks)
    if lower == "dockerfile" or lower.startswith("dockerfile.") or lower.endswith(".dockerfile"):
        return "Dockerfile"

    # CICD path patterns (before MarkupFile catches .yml)
    parts = p.split("/")
    if ".github" in parts:
        gi = parts.index(".github")
        if gi + 1 < len(parts) and parts[gi + 1] == "workflows":
            if suffix in (".yml", ".yaml"):
                return "CICD"
    if lower == "jenkinsfile":
        return "CICD"
    if lower == ".gitlab-ci.yml":
        return "CICD"
    if ".circleci" in parts:
        return "CICD"

    if suffix in _DOCUMENTATION_EXTENSIONS:
        return "Documentation"
    if suffix in _SQL_EXTENSIONS:
        return "SQLNoSQLScript"
    if suffix in _MARKUP_EXTENSIONS:
        return "MarkupFile"

    if suffix in _FILE_SOURCE_EXTENSIONS:
        return "File"

    return None


def _language_for_source_file(rel_path: str) -> str:
    """Infer `language` property from file extension (for File-typed nodes)."""
    ext = Path(rel_path).suffix.lower()
    mapping = {
        ".java": "java",
        ".py": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".go": "go",
        ".rs": "rust",
        ".c": "c",
        ".cpp": "cpp",
        ".cc": "cpp",
        ".cxx": "cpp",
        ".h": "c",
        ".hpp": "cpp",
        ".cs": "csharp",
        ".kt": "kotlin",
        ".scala": "scala",
        ".rb": "ruby",
        ".php": "php",
        ".swift": "swift",
    }
    return mapping.get(ext, ext.lstrip(".") or "unknown")


def _language_for_non_file_label(file_type: str, rel_path: str) -> str:
    """`language` property for whole-file Dockerfile / Markup / etc."""
    if file_type == "Dockerfile":
        return "dockerfile"
    if file_type == "Documentation":
        ext = Path(rel_path).suffix.lower()
        if ext == ".md":
            return "markdown"
        return "text"
    if file_type == "MarkupFile":
        ext = Path(rel_path).suffix.lower()
        return {".json": "json", ".yaml": "yaml", ".yml": "yaml", ".xml": "xml",
                ".toml": "toml", ".html": "html"}.get(ext, "markup")
    if file_type == "SQLNoSQLScript":
        return "sql"
    if file_type == "CICD":
        return "cicd"
    return file_type.lower()


def _storage_ref(codebase_id: str, rel_path: str) -> str:
    return f"codebases/{codebase_id}/files/{rel_path}"


def _extract_signature(symbol: dict) -> str:
    name = symbol.get("name", "") or ""
    detail = (symbol.get("detail") or "").strip()
    if detail:
        return f"{name} {detail}".strip()
    return name


def _get_language_id_for_lsp(rel_path: str) -> str:
    """languageId for textDocument/didOpen from the registered file strategy."""
    strategy = get_phase1_strategy_for_file(rel_path)
    if strategy.supports_file(rel_path):
        return strategy.lsp_language_id(rel_path)
    return _language_for_source_file(rel_path)


def _should_use_lsp_for_file(rel_path: str, active_lsp_languages: set[str]) -> bool:
    """True if the current pipeline has an active backend for this file."""
    strategy = get_phase1_strategy_for_file(rel_path)
    if not strategy.supports_file(rel_path):
        return False
    return strategy.needs_lsp(rel_path) and strategy.language in active_lsp_languages


def _extract_nodes_and_contains(
    symbols: list[dict],
    rel_path: str,
    language: str,
    codebase_id: str,
    parent_id: str | None = None,
    sibling_order_start: int = 1,
) -> tuple[list[dict], list[dict]]:
    """Walk DocumentSymbol tree: CodeNode-only labels, CONTAINS with order."""
    nodes: list[dict] = []
    edges: list[dict] = []

    for order, symbol in enumerate(symbols, start=sibling_order_start):
        name = symbol.get("name", "")
        range_info = symbol.get("range", {}) or {}
        selection_info = symbol.get("selectionRange") or range_info
        sel_start = selection_info.get("start") or range_info.get("start", {}) or {}
        selection_line = int(sel_start.get("line", 0)) + 1
        selection_character = int(sel_start.get("character", 0))
        start_line = range_info.get("start", {}).get("line", 0) + 1
        end_line = range_info.get("end", {}).get("line", 0) + 1
        kind = symbol.get("kind")
        detail = symbol.get("detail")
        if detail is not None and isinstance(detail, str) and detail.strip() == "":
            detail = None

        node_id = f"{codebase_id}:{rel_path}:{start_line}:{name}"

        node: dict[str, Any] = {
            "id": node_id,
            "codebase_id": codebase_id,
            "name": name,
            "labels": ["CodeNode"],
            "language": language,
            "path": rel_path,
            "storage_ref": _storage_ref(codebase_id, rel_path),
            "start_line": start_line,
            "end_line": end_line,
            "selection_line": selection_line,
            "selection_character": selection_character,
            "kind": kind,
            "signature": _extract_signature(symbol),
            "detail": detail,
        }

        nodes.append(node)

        if parent_id:
            edges.append({
                "from_id": parent_id,
                "to_id": node_id,
                "type": "CONTAINS",
                "order": order,
            })

        children = symbol.get("children") or []
        if children:
            child_nodes, child_edges = _extract_nodes_and_contains(
                children,
                rel_path,
                language,
                codebase_id,
                parent_id=node_id,
                sibling_order_start=1,
            )
            nodes.extend(child_nodes)
            edges.extend(child_edges)

    return nodes, edges


def _whole_file_node(
    file_type: str,
    rel_path: str,
    codebase_id: str,
    line_count: int,
) -> dict:
    """Single node for Dockerfile / MarkupFile / Documentation / SQL / CICD."""
    name = Path(rel_path).name
    lang = _language_for_non_file_label(file_type, rel_path)
    labels = ["CodeNode", file_type]
    node_id = f"{codebase_id}:{rel_path}:1:{name}"

    return {
        "id": node_id,
        "codebase_id": codebase_id,
        "name": name,
        "labels": labels,
        "language": lang,
        "path": rel_path,
        "storage_ref": _storage_ref(codebase_id, rel_path),
        "start_line": 1,
        "end_line": max(1, line_count),
        "kind": None,
        "signature": None,
        "detail": None,
    }


def _file_placeholder_node(rel_path: str, codebase_id: str, line_count: int) -> dict:
    """
    Single CodeNode + File for a source file when no LSP is available for it yet.
    """
    name = Path(rel_path).name
    language = _language_for_source_file(rel_path)
    node_id = f"{codebase_id}:{rel_path}:1:{name}"
    return {
        "id": node_id,
        "codebase_id": codebase_id,
        "name": name,
        "labels": ["CodeNode", "File"],
        "language": language,
        "path": rel_path,
        "storage_ref": _storage_ref(codebase_id, rel_path),
        "start_line": 1,
        "end_line": max(1, line_count),
        "kind": None,
        "signature": None,
        "detail": None,
    }


def _process_one_lsp_file(
    client: LspClient,
    abs_path: str,
    rel_path: str,
    codebase_id: str,
    lock: threading.Lock,
) -> tuple[list[dict], list[dict]]:
    """didOpen + documentSymbol for one file; returns nodes and CONTAINS edges."""
    language = _language_for_source_file(rel_path)
    lang_id = _get_language_id_for_lsp(rel_path)

    content = Path(abs_path).read_text(encoding="utf-8", errors="ignore")

    with lock:
        client.did_open(abs_path, lang_id, content)
        symbols = client.document_symbol(abs_path)

    if not symbols:
        logger.debug("Phase 1: no symbols in %s", rel_path)
        line_count = max(1, len(content.splitlines()))
        return [_file_placeholder_node(rel_path, codebase_id, line_count)], []

    file_nodes, file_edges = _extract_nodes_and_contains(
        symbols,
        rel_path,
        language,
        codebase_id,
    )
    return file_nodes, file_edges


def crawl_phase1(
    client: LspClient | None,
    classified_files: dict[str, list[tuple[str, str]]],
    codebase_id: str,
    *,
    active_lsp_languages: set[str] | None = None,
    max_workers: int = 4,
) -> tuple[list[dict], list[dict]]:
    """
    Phase 1: nodes (CodeNode + optional file-type label) and CONTAINS edges.

    Args:
        client: LSP client when File-typed paths are processed with LSP; may be
            None if there are no LSP-backed files.
        classified_files: Maps file-type string -> list of (abs_path, rel_path).
        codebase_id: Codebase UUID.
        active_lsp_languages: Languages whose LSP backends are active for this pass.
        max_workers: Thread pool size for file-level tasks (LSP calls are locked).

    Returns:
        (nodes, contains_edges)
    """
    all_nodes: list[dict] = []
    all_edges: list[dict] = []
    active_lsp_languages = active_lsp_languages or set()

    # ── Whole-file nodes (no LSP) ───────────────────────────────────────────
    for ft in ("Dockerfile", "MarkupFile", "Documentation", "SQLNoSQLScript", "CICD"):
        for abs_path, rel_path in classified_files.get(ft, []):
            try:
                text = Path(abs_path).read_text(encoding="utf-8", errors="ignore")
            except OSError as e:
                logger.warning("Phase 1: skip %s: %s", rel_path, e)
                continue
            lines = text.splitlines()
            all_nodes.append(_whole_file_node(ft, rel_path, codebase_id, len(lines)))

    # ── File-typed: LSP vs placeholder ─────────────────────────────────────
    file_entries = classified_files.get("File", [])
    lsp_files: list[tuple[str, str]] = []
    placeholder_files: list[tuple[str, str]] = []

    for abs_path, rel_path in file_entries:
        if client is not None and _should_use_lsp_for_file(rel_path, active_lsp_languages):
            lsp_files.append((abs_path, rel_path))
        else:
            placeholder_files.append((abs_path, rel_path))

    for abs_path, rel_path in placeholder_files:
        try:
            text = Path(abs_path).read_text(encoding="utf-8", errors="ignore")
        except OSError as e:
            logger.warning("Phase 1: skip %s: %s", rel_path, e)
            continue
        line_count = max(1, len(text.splitlines()))
        all_nodes.append(_file_placeholder_node(rel_path, codebase_id, line_count))

    if not lsp_files:
        logger.info(
            "Phase 1 crawl completed: nodes=%d contains_edges=%d (no LSP files)",
            len(all_nodes),
            len(all_edges),
        )
        return all_nodes, all_edges

    if client is None:
        logger.warning("Phase 1: LSP files present but client is None; skipping LSP")
        return all_nodes, all_edges

    lock = threading.Lock()
    workers = max(1, min(max_workers, len(lsp_files)))

    logger.info(
        "Phase 1: LSP processing %d file(s) workers=%d language=%s",
        len(lsp_files),
        workers,
        ",".join(sorted(active_lsp_languages)) or "none",
    )

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {
            ex.submit(
                _process_one_lsp_file,
                client,
                abs_path,
                rel_path,
                codebase_id,
                lock,
            ): rel_path
            for abs_path, rel_path in lsp_files
        }
        for fut in as_completed(futures):
            rel_path = futures[fut]
            try:
                nodes, edges = fut.result()
                all_nodes.extend(nodes)
                all_edges.extend(edges)
            except Exception as e:
                logger.exception("Phase 1: LSP failed for %s: %s", rel_path, e)
                raise

    logger.info(
        "Phase 1 crawl completed: nodes=%d contains_edges=%d",
        len(all_nodes),
        len(all_edges),
    )
    return all_nodes, all_edges
