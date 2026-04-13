"""
Phase 2 Tier 1: semantic labels and Tier-1 properties on existing Phase 1 nodes.

Does not create new symbol nodes. Emits Tier 1 relationship *candidates*
(``INHERITS``, ``IMPLEMENTS`` for Java) resolved and written by ``GraphWriter``.

Uses the same language mappers as the extractor layer (``get_mapper``) plus
language-specific regex rules for additive labels (e.g. Testing, Database).
"""
from __future__ import annotations

import logging
import os
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from .languages import get_tier1_strategy
from ..extractor import get_mapper

logger = logging.getLogger(__name__)

# ── path helpers (match Neo4j / worker file map keys) ──────────────────────────


def norm_path(path: str) -> str:
    """Normalise a file path to forward-slash, lowercase on Windows."""
    p = Path(path).resolve()
    s = str(p).replace("\\", "/")
    if os.name == "nt":
        s = s.lower()
    return s


def file_key_for_node(workspace_root: str, rel_path: str) -> str:
    """Key into ``file_contents`` for a node ``path`` (repo-relative)."""
    return norm_path(str(Path(workspace_root) / rel_path))


def build_file_contents_from_batch(
    workspace_root: str,
    batch: list[tuple[str, str, bytes]],
) -> dict[str, str]:
    """
    Map normalised absolute path -> UTF-8 source text from ingest batch bytes.
    """
    out: dict[str, str] = {}
    for rel_path, _, content_bytes in batch:
        key = file_key_for_node(workspace_root, rel_path)
        out[key] = content_bytes.decode("utf-8", errors="replace")
    return out


# ── containment (parent labels for mapper) ───────────────────────────────────


def _parent_maps(
    nodes: list[dict],
    contains_edges: list[dict],
) -> tuple[dict[str, str], dict[str, list[str]]]:
    parent_of: dict[str, str] = {}
    children_of: dict[str, list[str]] = defaultdict(list)
    id_set = {n["id"] for n in nodes}
    for edge in contains_edges:
        if edge.get("type") != "CONTAINS":
            continue
        p, c = edge["from_id"], edge["to_id"]
        if p in id_set and c in id_set:
            parent_of[c] = p
            children_of[p].append(c)
    return parent_of, children_of


def _bfs_ids(parent_of: dict[str, str], children_of: dict[str, list[str]], all_ids: list[str]) -> list[str]:
    roots = [i for i in all_ids if i not in parent_of]
    ordered: list[str] = []
    seen: set[str] = set()
    q: deque[str] = deque(roots)
    while q:
        nid = q.popleft()
        if nid in seen:
            continue
        seen.add(nid)
        ordered.append(nid)
        for c in children_of.get(nid, []):
            q.append(c)
    for i in all_ids:
        if i not in seen:
            ordered.append(i)
    return ordered


# ── level (from semantic labels) ──────────────────────────────────────────────

_LEVEL: dict[str, int] = {
    "Attribute": 4,
    "Method": 3,
    "Function": 3,
    "Constructor": 3,
    "Instantiator": 3,
    "Destructor": 3,
    "Lambda": 3,
    "CodeUnit": 3,
    "Event": 3,
    "Class": 2,
    "Interface": 2,
    "Enum": 2,
    "InnerClass": 2,
    "Module": 2,
    "File": 1,
    "Property": 4,
    "Variable": 4,
    "Constant": 4,
    "EnumMember": 4,
}


def _compute_level(semantic: set[str]) -> int:
    best = 0
    for lb in semantic:
        best = max(best, _LEVEL.get(lb, 0))
    return best


# ── public API ───────────────────────────────────────────────────────────────


def crawl_phase2_tier1(
    nodes: list[dict],
    contains_edges: list[dict],
    file_contents: dict[str, str],
    workspace_root: str,
    codebase_id: str,
) -> dict[str, Any]:
    """
    Compute Tier 1 label additions, properties, and Java Tier 1 relationship candidates.

    Returns a dict:

    - ``updates``: list of ``{"id", "labels_to_add", "properties"}``
    - ``tier1_rel_candidates``: list of ``{"from_id", "target_name", "rel_type"}``
      for ``GraphWriter.apply_phase2_tier1_relationships`` (Java ``INHERITS`` / ``IMPLEMENTS``).

    Nodes without ``kind`` get only ``level`` where applicable.
    """
    _ = codebase_id
    id_to_node = {n["id"]: n for n in nodes}
    parent_of, children_of = _parent_maps(nodes, contains_edges)
    order = _bfs_ids(parent_of, children_of, [n["id"] for n in nodes])

    resolved_semantic: dict[str, list[str]] = {}
    updates: list[dict[str, Any]] = []
    tier1_rel_candidates: list[dict[str, str]] = []

    for nid in order:
        node = id_to_node[nid]
        existing = set(node.get("labels") or [])
        kind = node.get("kind")

        if kind is None:
            props: dict[str, Any] = {"level": 0}
            updates.append({"id": nid, "labels_to_add": [], "properties": props})
            continue

        lang = (node.get("language") or "").lower()
        mapper = get_mapper(lang)
        parent_id = parent_of.get(nid)
        parent_semantic = resolved_semantic.get(parent_id) if parent_id else None

        symbol = {
            "kind": kind,
            "name": node.get("name") or "",
            "detail": node.get("detail") or "",
        }
        try:
            mapped = mapper.map_symbol_to_labels(symbol, parent_id, parent_semantic)
        except Exception as e:
            logger.warning("Tier1 mapper failed id=%s: %s", nid, e)
            mapped = []

        resolved_semantic[nid] = list(mapped)

        rel_path = node.get("path") or ""
        fkey = file_key_for_node(workspace_root, rel_path)
        text = file_contents.get(fkey, "")
        strategy = get_tier1_strategy(lang)
        regex_extra = strategy.extra_labels(node, text)

        combined = set(mapped) | set(regex_extra)
        labels_to_add = sorted(combined - existing)

        props = strategy.extract_properties(node, text)
        props["level"] = _compute_level(combined)

        updates.append({
            "id": nid,
            "labels_to_add": labels_to_add,
            "properties": props,
        })

        for c in strategy.relationship_candidates(node, text):
            tier1_rel_candidates.append({
                "from_id": nid,
                "target_name": c["target_name"],
                "rel_type": c["rel_type"],
            })

    logger.info(
        "crawl_phase2_tier1: nodes=%d updates=%d tier1_rel_candidates=%d",
        len(nodes),
        len(updates),
        len(tier1_rel_candidates),
    )
    return {
        "updates": updates,
        "tier1_rel_candidates": tier1_rel_candidates,
    }


__all__ = [
    "norm_path",
    "file_key_for_node",
    "build_file_contents_from_batch",
    "crawl_phase2_tier1",
]
