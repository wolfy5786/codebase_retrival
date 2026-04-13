"""
Phase 2 Tier 3: LSP-based labels, properties, and relationships on existing nodes.

Language-specific enrichment is delegated to per-language strategies.
"""
from __future__ import annotations

import logging
from typing import Any

from .languages import get_tier3_strategy
from .languages.base import Tier3NodeContext
from .phase2 import _bfs_ids, _parent_maps, file_key_for_node


def _lsp_position_for_tier3(
    node: dict,
    file_map: dict[str, str],
    workspace_root: str,
    rel_path: str,
) -> tuple[int, int]:
    """
    Line/column for textDocument/* requests. Prefer DocumentSymbol selection from Phase 1;
    if absent, move off leading whitespace / onto the symbol name when possible.
    """
    if node.get("selection_line") is not None:
        line0 = max(0, int(node["selection_line"]) - 1)
        col0 = int(node.get("selection_character") or 0)
        return line0, col0
    line0 = max(0, int(node.get("start_line") or 1) - 1)
    key = file_key_for_node(workspace_root, rel_path)
    text = file_map.get(key, "")
    lines = text.splitlines()
    if line0 < len(lines):
        line = lines[line0]
        name = str(node.get("name") or "")
        if name:
            idx = line.find(name)
            if idx >= 0:
                return line0, idx
        for i, ch in enumerate(line):
            if ch not in " \t":
                return line0, i
    return line0, 0
from .tier3_common import (
    abs_path_for_file,
    lsp_range_start_line_1based,
    lsp_uri_to_repo_rel,
    match_stored_path,
)
from .languages.java.phase2_tier3_strategy import is_java_primitive_type
from ..graph_writer import GraphWriter
from ..lsp.client import LspClient

logger = logging.getLogger(__name__)


def crawl_phase2_tier3(
    client: LspClient,
    graph_writer: GraphWriter,
    nodes: list[dict],
    contains_edges: list[dict],
    file_map: dict[str, str],
    workspace_root: str,
    codebase_id: str,
) -> dict[str, Any]:
    """
    Tier 3 LSP pass: ``definition_uri``, object/reference details, and call/member relationships.

    Returns:
        ``updates`` — rows for ``GraphWriter.apply_phase2_tier3``
        ``calls_edges``, ``sets_edges``, ``gets_edges`` — rows for ``apply_phase2_tier3_relationships``
    """
    id_to_node = {n["id"]: n for n in nodes}
    parent_of, children_of = _parent_maps(nodes, contains_edges)
    order = _bfs_ids(parent_of, children_of, [n["id"] for n in nodes])
    all_paths = {str(n.get("path") or "") for n in nodes if n.get("path")}
    file_languages: dict[str, str] = {}
    for node in nodes:
        rel_path = str(node.get("path") or "")
        language = (node.get("language") or "").lower()
        if rel_path and language and rel_path not in file_languages:
            file_languages[rel_path] = language

    rows: dict[str, dict[str, Any]] = {}
    calls_raw: list[dict[str, Any]] = []
    sets_raw: list[dict[str, Any]] = []
    gets_raw: list[dict[str, Any]] = []

    def ensure_row(nid: str) -> dict[str, Any]:
        if nid not in rows:
            rows[nid] = {
                "id": nid,
                "labels_to_add": [],
                "properties": {},
            }
        return rows[nid]

    def add_labels(nid: str, labels: list[str]) -> None:
        row = ensure_row(nid)
        seen = set(row["labels_to_add"])
        for label in labels:
            if label not in seen:
                seen.add(label)
                row["labels_to_add"].append(label)

    def set_props(nid: str, props: dict[str, Any]) -> None:
        row = ensure_row(nid)
        for key, value in props.items():
            if value is not None:
                row["properties"][key] = value

    opened_abs: set[str] = set()

    def ensure_open(rel_path: str) -> str:
        abs_path = abs_path_for_file(workspace_root, rel_path)
        if abs_path in opened_abs:
            return abs_path
        node_language = file_languages.get(rel_path, "")
        strategy = get_tier3_strategy(node_language)
        language = strategy.did_open_language_id(rel_path) or node_language
        key = file_key_for_node(workspace_root, rel_path)
        text = file_map.get(key, "")
        try:
            client.did_open(abs_path, language, text)
        except Exception as e:
            logger.debug("Tier3 did_open failed %s: %s", abs_path, e)
        opened_abs.add(abs_path)
        return abs_path

    seen_calls: set[tuple[str, str]] = set()
    seen_sets: set[tuple[str, str, int | None]] = set()
    seen_gets: set[tuple[str, str, int | None]] = set()

    for nid in order:
        node = id_to_node[nid]
        language = (node.get("language") or "").lower()
        strategy = get_tier3_strategy(language)
        if not strategy.should_process_node(node):
            continue

        rel_path = str(node.get("path") or "")
        if not rel_path:
            continue

        line0, col0 = _lsp_position_for_tier3(node, file_map, workspace_root, rel_path)
        abs_file = ensure_open(rel_path)

        ctx = Tier3NodeContext(
            client=client,
            graph_writer=graph_writer,
            workspace_root=workspace_root,
            codebase_id=codebase_id,
            file_map=file_map,
            abs_file=abs_file,
            line0=line0,
            id_to_node=id_to_node,
            parent_of=parent_of,
            all_paths=all_paths,
            col0=col0,
        )

        try:
            result = strategy.enrich_node(node, ctx)
        except Exception as e:
            logger.debug("Tier3 strategy failed id=%s language=%s: %s", nid, language, e)
            continue

        if result.labels_to_add:
            add_labels(nid, result.labels_to_add)
        if result.properties:
            set_props(nid, result.properties)

        for edge in result.calls_edges:
            key = (edge["from_id"], edge["to_id"])
            if key in seen_calls:
                continue
            seen_calls.add(key)
            calls_raw.append(edge)

        for edge in result.sets_edges:
            key = (edge["from_id"], edge["to_id"], edge.get("line"))
            if key in seen_sets:
                continue
            seen_sets.add(key)
            sets_raw.append(edge)

        for edge in result.gets_edges:
            key = (edge["from_id"], edge["to_id"], edge.get("line"))
            if key in seen_gets:
                continue
            seen_gets.add(key)
            gets_raw.append(edge)

    updates = list(rows.values())
    for update in updates:
        update["labels_to_add"] = sorted(set(update["labels_to_add"]))

    logger.info(
        "crawl_phase2_tier3: updates=%d calls=%d sets=%d gets=%d",
        len(updates),
        len(calls_raw),
        len(sets_raw),
        len(gets_raw),
    )

    return {
        "updates": updates,
        "calls_edges": calls_raw,
        "sets_edges": sets_raw,
        "gets_edges": gets_raw,
    }


__all__ = [
    "crawl_phase2_tier3",
    "is_java_primitive_type",
    "lsp_uri_to_repo_rel",
    "match_stored_path",
    "lsp_range_start_line_1based",
]
