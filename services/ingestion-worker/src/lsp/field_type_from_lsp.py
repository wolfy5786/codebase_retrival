"""
Resolve declared field/variable type when DocumentSymbol.detail is empty.

Option B: textDocument/hover first, then textDocument/typeDefinition (URI stem).
Used by Phase 1 for Java/C++ class-scoped reference fields.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from .hover_parse import hover_result_to_text, split_hover_signature_and_doc

logger = logging.getLogger(__name__)

_JAVA_LEADING_MODIFIERS = frozenset(
    {
        "private",
        "public",
        "protected",
        "static",
        "final",
        "volatile",
        "transient",
        "default",
        "abstract",
        "synchronized",
        "native",
        "strictfp",
    }
)

_CPP_LEADING_MODIFIERS = frozenset(
    {
        "private",
        "public",
        "protected",
        "static",
        "const",
        "volatile",
        "mutable",
        "inline",
        "constexpr",
        "explicit",
        "virtual",
        "extern",
    }
)


def _strip_leading_modifiers(tokens: list[str], modifiers: frozenset[str]) -> list[str]:
    i = 0
    while i < len(tokens) and tokens[i].lower() in modifiers:
        i += 1
    return tokens[i:]


def extract_type_before_field_name(line: str, field_name: str, modifiers: frozenset[str]) -> str | None:
    """
    From a hover signature line like `private final MyService svc` or `std::string s`,
    return the type substring before the field name (last token).
    """
    if not line or not field_name:
        return None
    line = re.sub(r"\s+", " ", line.strip())
    if not line:
        return None
    tokens = line.split()
    tokens = _strip_leading_modifiers(tokens, modifiers)
    if len(tokens) < 2:
        return None
    if tokens[-1] != field_name:
        return None
    type_tokens = tokens[:-1]
    if not type_tokens:
        return None
    return " ".join(type_tokens)


def parse_type_from_hover(hover_text: str, field_name: str, language: str) -> str | None:
    """Parse declared type from full hover text (try signature line then following lines)."""
    if not hover_text or not field_name:
        return None
    lang = language.lower()
    modifiers = _CPP_LEADING_MODIFIERS if lang in ("cpp", "c", "cxx") else _JAVA_LEADING_MODIFIERS

    sig, doc = split_hover_signature_and_doc(hover_text)
    for block in (sig, doc, hover_text):
        if not block:
            continue
        for raw_line in block.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or line.startswith("```"):
                continue
            t = extract_type_before_field_name(line, field_name, modifiers)
            if t:
                return t
    return None


def _normalize_locations(result: dict | list | None) -> list[dict]:
    if not result:
        return []
    if isinstance(result, list):
        return [x for x in result if isinstance(x, dict)]
    if isinstance(result, dict):
        return [result]
    return []


def definition_result_to_uri(result: dict | list | None) -> str | None:
    """First definition target URI from ``textDocument/definition`` result."""
    locs = _normalize_locations(result)
    if not locs:
        return None
    loc = locs[0]
    uri = loc.get("uri") or loc.get("targetUri")
    return str(uri) if uri else None


def type_name_from_definition_location(loc: dict) -> str | None:
    """Use definition target file stem as simple type name (best-effort)."""
    uri = loc.get("uri") or loc.get("targetUri") or ""
    if not uri or not uri.startswith("file:"):
        return None
    path = uri.split("file://", 1)[-1]
    path = path.replace("%3A", ":").replace("%20", " ")
    if path.startswith("/") and len(path) > 3 and path[2] == ":":
        path = path.lstrip("/")
    stem = Path(path).stem
    return stem or None


def resolve_field_type_at_position(
    client: "LspClient",
    file_path: str,
    line0: int,
    char0: int,
    field_name: str,
    language: str,
) -> str | None:
    """
    Same as ``resolve_field_type_when_detail_empty`` but with explicit LSP positions.
    Used by Phase 2 Tier 3 for Object/Instance on class-scoped fields.
    """
    hover = None
    try:
        hover = client.hover(file_path, line0, char0)
    except Exception as e:
        logger.debug("hover failed for field %s: %s", field_name, e)

    hover_txt = hover_result_to_text(hover)
    parsed = parse_type_from_hover(hover_txt, field_name, language)
    if parsed:
        return parsed.strip()

    try:
        raw = client.type_definition(file_path, line0, char0)
    except Exception as e:
        logger.debug("typeDefinition failed for field %s: %s", field_name, e)
        return None

    for loc in _normalize_locations(raw):
        stem = type_name_from_definition_location(loc)
        if stem:
            return stem

    return None


def resolve_field_type_when_detail_empty(
    client: "LspClient",
    file_path: str,
    language: str,
    symbol: dict,
    field_name: str,
) -> str | None:
    """
    When DocumentSymbol has no detail, ask LSP for type: hover, then typeDefinition URI stem.
    Returns a type string suitable for reference_type_detail / mapper heuristics.
    """
    sel = symbol.get("selectionRange") or symbol.get("range") or {}
    start = sel.get("start", {})
    line = int(start.get("line", 0))
    char = int(start.get("character", 0))

    return resolve_field_type_at_position(client, file_path, line, char, field_name, language)
