from __future__ import annotations

import logging

from ...tier3_common import (
    lsp_range_start_line_1based,
    lsp_uri_to_repo_rel,
    match_stored_path,
)
from ....lsp.field_type_from_lsp import (
    definition_result_to_uri,
    resolve_field_type_at_position,
)
from ..base import Tier3EnrichmentResult, Tier3NodeContext

logger = logging.getLogger(__name__)

# LSP SymbolKind: Method=6, Property=7, Field=8, Constructor=9, Function=12, Variable=13, Constant=14, EnumMember=22
_CALLABLE_KINDS = frozenset({6, 9, 12})
_ATTRIBUTE_KINDS_FOR_HIGHLIGHT = frozenset({7, 8, 13, 14, 22})
_FIELD_KINDS_FOR_OBJECT = frozenset({7, 8, 13, 14, 22})

_JAVA_PRIMITIVES = frozenset(
    {
        "boolean",
        "byte",
        "char",
        "short",
        "int",
        "long",
        "float",
        "double",
        "void",
    }
)


def _java_simple_type_name(qualified: str) -> str:
    text = qualified.strip()
    if not text:
        return ""
    base = text.split()[-1] if " " in text else text
    base = base.split(".")[-1]
    base = base.split("<")[0].strip()
    return base


def is_java_primitive_type(qualified: str) -> bool:
    name = _java_simple_type_name(qualified)
    return name.lower() in _JAVA_PRIMITIVES


class JavaTier3Strategy:
    language = "java"

    def should_process_node(self, node: dict) -> bool:
        return (node.get("language") or "").lower() == "java"

    def did_open_language_id(self, rel_path: str) -> str:
        _ = rel_path
        return "java"

    def enrich_node(self, node: dict, ctx: Tier3NodeContext) -> Tier3EnrichmentResult:
        result = Tier3EnrichmentResult()
        kind = node.get("kind")
        name = node.get("name") or ""
        nid = node["id"]
        start_line = int(node.get("start_line") or 1)
        rel_path = str(node.get("path") or "")

        if kind is not None:
            try:
                raw_def = ctx.client.definition(ctx.abs_file, ctx.line0, ctx.col0)
            except Exception as e:
                logger.debug("Tier3 definition failed id=%s: %s", nid, e)
                raw_def = None
            uri = definition_result_to_uri(raw_def)
            if uri:
                result.properties["definition_uri"] = uri

        if kind in _FIELD_KINDS_FOR_OBJECT and ctx.parent_of.get(nid):
            parent_kind = ctx.id_to_node.get(ctx.parent_of[nid], {}).get("kind")
            if parent_kind == 5 and name:
                try:
                    resolved_type = resolve_field_type_at_position(
                        ctx.client, ctx.abs_file, ctx.line0, ctx.col0, name, "java"
                    )
                except Exception as e:
                    logger.debug("Tier3 field type resolve failed id=%s: %s", nid, e)
                    resolved_type = None
                if resolved_type and not is_java_primitive_type(resolved_type):
                    result.labels_to_add.extend(["Object", "Instance"])
                    result.properties["reference_type_detail"] = resolved_type

        if kind in _CALLABLE_KINDS:
            try:
                items = ctx.client.call_hierarchy_prepare(ctx.abs_file, ctx.line0, ctx.col0)
            except Exception as e:
                logger.debug("Tier3 prepareCallHierarchy failed id=%s: %s", nid, e)
                items = []
            if items:
                try:
                    outgoing = ctx.client.call_hierarchy_outgoing(items[0])
                except Exception as e:
                    logger.debug("Tier3 outgoingCalls failed id=%s: %s", nid, e)
                    outgoing = []
                for edge in outgoing:
                    to_item = edge.get("to") or {}
                    to_uri = to_item.get("uri") or ""
                    selection = to_item.get("selectionRange") or to_item.get("range")
                    line_1 = lsp_range_start_line_1based(selection)

                    resolved_rel = lsp_uri_to_repo_rel(to_uri, ctx.workspace_root)
                    if not resolved_rel:
                        continue
                    stored_path = match_stored_path(resolved_rel, ctx.all_paths)
                    if not stored_path:
                        continue

                    target_ids = ctx.graph_writer.find_code_node_ids_covering_line(
                        ctx.codebase_id, stored_path, line_1
                    )
                    for target_id in target_ids:
                        if target_id == nid:
                            continue
                        from_ranges = edge.get("fromRanges") or []
                        line_prop = start_line
                        col_prop = None
                        if from_ranges:
                            r0 = from_ranges[0].get("start", {})
                            line_prop = int(r0.get("line", ctx.line0)) + 1
                            col_prop = int(r0.get("character", 0))
                        result.calls_edges.append(
                            {
                                "from_id": nid,
                                "to_id": target_id,
                                "line": line_prop,
                                "column": col_prop,
                            }
                        )

        if kind in _ATTRIBUTE_KINDS_FOR_HIGHLIGHT:
            try:
                highlights = ctx.client.document_highlight(ctx.abs_file, ctx.line0, ctx.col0)
            except Exception as e:
                logger.debug("Tier3 documentHighlight failed id=%s: %s", nid, e)
                highlights = []
            for highlight in highlights:
                highlight_range = highlight.get("range") or {}
                highlight_kind = highlight.get("kind")
                occurrence_line = lsp_range_start_line_1based(highlight_range)

                caller_id = ctx.graph_writer.find_enclosing_callable_id(
                    ctx.codebase_id, rel_path, occurrence_line
                )
                if not caller_id or caller_id == nid:
                    continue

                if highlight_kind == 3:
                    result.sets_edges.append(
                        {
                            "from_id": caller_id,
                            "to_id": nid,
                            "line": occurrence_line,
                            "member_name": name or None,
                        }
                    )
                elif highlight_kind == 2:
                    result.gets_edges.append(
                        {
                            "from_id": caller_id,
                            "to_id": nid,
                            "line": occurrence_line,
                            "member_name": name or None,
                        }
                    )

        return result


JAVA_TIER3_STRATEGY = JavaTier3Strategy()

__all__ = [
    "JAVA_TIER3_STRATEGY",
    "is_java_primitive_type",
]
