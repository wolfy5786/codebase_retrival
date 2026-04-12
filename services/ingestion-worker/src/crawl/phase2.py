"""
Phase 2 Tier 1: semantic labels and Tier-1 properties on existing Phase 1 nodes.

Does not create nodes. Does not write relationships (Tier 2 / Tier 3 handle edges).

Uses the same language mappers as the extractor layer (``get_mapper``) plus
language-specific regex rules for additive labels (e.g. Testing, Database).
"""
from __future__ import annotations

import logging
import os
import re
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

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


# ── Java: regex additive labels ─────────────────────────────────────────────

_JAVA_TESTING = re.compile(
    r"@Test\b|@Before\b|@After\b|@BeforeEach\b|@AfterEach\b|@ParameterizedTest\b",
)
_JAVA_ACCEPT_NET = re.compile(
    r"@RequestMapping\b|@GetMapping\b|@PostMapping\b|@PutMapping\b|@DeleteMapping\b|@PatchMapping\b|@RestController\b",
)
_JAVA_SENDS_NET = re.compile(
    r"\bHttpURLConnection\b|\bRestTemplate\b|\bWebClient\b|\bOkHttpClient\b",
)
_JAVA_DB = re.compile(
    r"@Repository\b|@Query\b|@Entity\b|@Table\b|javax\.sql\.|java\.sql\.|jdbc\.|JpaRepository\b",
)


def _java_regex_labels(
    node: dict,
    declaration_block: str,
    body_snippet: str,
) -> list[str]:
    lang = (node.get("language") or "").lower()
    if lang != "java":
        return []
    kind = node.get("kind")
    if kind is None:
        return []
    out: list[str] = []
    block = f"{declaration_block}\n{body_snippet}"

    if _JAVA_TESTING.search(block):
        out.append("Testing")
    if kind in (5, 6) and _JAVA_ACCEPT_NET.search(block):
        out.append("Accept_call_over_network")
    if kind in (5, 6, 12) and _JAVA_SENDS_NET.search(body_snippet):
        out.append("Sends_data_over_network")
    if kind in (5, 6) and _JAVA_DB.search(block):
        out.append("Database")

    return out


# ── Java: declaration properties ─────────────────────────────────────────────

_ANNOTATION_RE = re.compile(r"@(\w+)(?:\([^)]*\))?")


def _parse_java_parameter_types(signature: str | None) -> list[str]:
    if not signature:
        return []
    depth = 0
    start = None
    for i, ch in enumerate(signature):
        if ch == "(":
            depth += 1
            if depth == 1:
                start = i + 1
        elif ch == ")":
            if depth == 1 and start is not None:
                inner = signature[start:i]
                return _split_java_params(inner)
            depth -= 1
    return []


def _split_java_params(inner: str) -> list[str]:
    if not inner.strip():
        return []
    parts: list[str] = []
    cur: list[str] = []
    depth = 0
    for ch in inner:
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth = max(0, depth - 1)
        elif ch == "," and depth == 0:
            parts.append("".join(cur).strip())
            cur = []
            continue
        cur.append(ch)
    parts.append("".join(cur).strip())
    types: list[str] = []
    for p in parts:
        if not p:
            continue
        p = re.sub(r"\s*\.\.\.\s*$", "", p).strip()
        tokens = p.split()
        if len(tokens) >= 2:
            types.append(" ".join(tokens[:-1]))
        elif len(tokens) == 1:
            types.append(tokens[0])
    return types


def _java_return_type_from_line(line: str, name: str) -> str | None:
    """Best-effort return type for methods (``public Foo bar()``)."""
    s = line.strip()
    if not s or not name:
        return None
    # strip annotations at start
    while s.startswith("@"):
        depth = 0
        i = 0
        while i < len(s):
            if s[i] == "(":
                depth += 1
            elif s[i] == ")" and depth > 0:
                depth -= 1
            elif s[i] in " \t" and depth == 0 and i > 0 and s[i - 1] != "@":
                break
            i += 1
        s = s[i:].lstrip()
    for mod in (
        "public ",
        "private ",
        "protected ",
        "static ",
        "final ",
        "abstract ",
        "synchronized ",
        "native ",
        "default ",
        "strictfp ",
    ):
        while s.startswith(mod):
            s = s[len(mod) :].lstrip()
    # generic return type
    if s.startswith("<"):
        depth = 1
        j = 1
        while j < len(s) and depth:
            if s[j] == "<":
                depth += 1
            elif s[j] == ">":
                depth -= 1
            j += 1
        s = s[j:].lstrip()
    # type + name + (
    idx = s.find("(")
    if idx == -1:
        return None
    before = s[:idx].strip()
    if not before:
        return None
    parts = before.split()
    if len(parts) >= 2 and parts[-1] == name:
        return " ".join(parts[:-1])
    return None


def _extract_java_tier1_properties(
    node: dict,
    lines: list[str],
) -> dict[str, Any]:
    kind = node.get("kind")
    if kind is None:
        return {}
    start = int(node.get("start_line") or 1)
    name = node.get("name") or ""
    sig = node.get("signature") or ""
    lo = max(0, start - 4)
    hi = min(len(lines), start + 2)
    block_lines = lines[lo:hi]
    declaration_block = "\n".join(block_lines)
    body_hi = min(len(lines), start + 40)
    body_snippet = "\n".join(lines[start - 1 : body_hi])

    annotations = list(dict.fromkeys(_ANNOTATION_RE.findall(declaration_block)))
    access_modifier = None
    m_acc = re.search(r"\b(public|private|protected)\b", declaration_block)
    if m_acc:
        access_modifier = m_acc.group(1)

    modifiers: list[str] = []
    for mod in (
        "static",
        "abstract",
        "final",
        "synchronized",
        "native",
        "volatile",
        "default",
        "strictfp",
    ):
        if re.search(rf"\b{mod}\b", declaration_block):
            modifiers.append(mod)

    props: dict[str, Any] = {
        "annotations": annotations,
        "access_modifier": access_modifier,
        "modifiers": modifiers,
        "is_static": "static" in modifiers,
    }

    if kind in (6, 9, 12):
        props["parameter_types"] = _parse_java_parameter_types(sig)
        if kind != 9:
            line0 = lines[start - 1] if 0 < start <= len(lines) else ""
            props["return_type"] = _java_return_type_from_line(line0, name)

    if kind == 5:
        m_abs = re.search(r"\babstract\b", declaration_block)
        if m_abs and "abstract" not in modifiers:
            modifiers.append("abstract")
            props["modifiers"] = modifiers

    return props


def _extract_tier1_properties(
    node: dict,
    file_text: str,
) -> dict[str, Any]:
    lang = (node.get("language") or "").lower()
    lines = file_text.splitlines()
    if lang == "java":
        return _extract_java_tier1_properties(node, lines)
    return {}


# ── public API ───────────────────────────────────────────────────────────────


def crawl_phase2_tier1(
    nodes: list[dict],
    contains_edges: list[dict],
    file_contents: dict[str, str],
    workspace_root: str,
    codebase_id: str,
) -> list[dict[str, Any]]:
    """
    Compute Tier 1 label additions and properties for each symbol node.

    Returns a list of dicts: ``{"id", "labels_to_add": [...], "properties": {...}}``.
    Nodes without ``kind`` get only ``level`` if applicable.
    """
    _ = codebase_id
    id_to_node = {n["id"]: n for n in nodes}
    parent_of, children_of = _parent_maps(nodes, contains_edges)
    order = _bfs_ids(parent_of, children_of, [n["id"] for n in nodes])

    resolved_semantic: dict[str, list[str]] = {}
    updates: list[dict[str, Any]] = []

    for nid in order:
        node = id_to_node[nid]
        existing = set(node.get("labels") or [])
        kind = node.get("kind")

        if kind is None:
            props: dict[str, Any] = {"level": 0}
            updates.append({"id": nid, "labels_to_add": [], "properties": props})
            continue

        lang = (node.get("language") or "java").lower()
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
        lines = text.splitlines() if text else []
        start = int(node.get("start_line") or 1)
        lo = max(0, start - 4)
        hi = min(len(lines), start + 2)
        declaration_block = "\n".join(lines[lo:hi]) if lines else ""
        body_hi = min(len(lines), start + 40)
        body_snippet = "\n".join(lines[start - 1 : body_hi]) if lines else ""

        regex_extra = _java_regex_labels(node, declaration_block, body_snippet)

        combined = set(mapped) | set(regex_extra)
        labels_to_add = sorted(combined - existing)

        props = _extract_tier1_properties(node, text)
        props["level"] = _compute_level(combined)

        updates.append({
            "id": nid,
            "labels_to_add": labels_to_add,
            "properties": props,
        })

    logger.info(
        "crawl_phase2_tier1: nodes=%d updates=%d",
        len(nodes),
        len(updates),
    )
    return updates


__all__ = [
    "norm_path",
    "file_key_for_node",
    "build_file_contents_from_batch",
    "crawl_phase2_tier1",
]
