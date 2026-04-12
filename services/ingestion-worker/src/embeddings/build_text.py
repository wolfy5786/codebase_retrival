"""
Build transient embedding input text per retrieval docs:
body + docstring + definition; nested symbol bodies replaced by child signatures only.
"""
from __future__ import annotations

import logging

from ..lsp.hover_parse import split_hover_signature_and_doc

logger = logging.getLogger(__name__)


def symbol_signature_for_replace(symbol: dict) -> str:
    """Compact signature for replacing a child span inside a parent body."""
    name = symbol.get("name", "")
    detail = symbol.get("detail", "")
    if detail:
        return f"{name} {detail}".strip()
    return name or "<symbol>"


def _phase1_line_span_to_slice_indices(start_line: int, end_line: int) -> tuple[int, int]:
    """
    phase1 stores start_line/end_line as 1-based inclusive last line convention:
    body = lines[start_line - 1 : end_line - 1] in Python (exclusive end index = end_line - 1).
    See phase1.py: end_line = range.end.line + 1.
    """
    lo = max(0, start_line - 1)
    hi = max(lo, end_line - 1)
    return lo, hi


def _replace_child_spans_with_signatures(
    lines: list[str],
    parent_start: int,
    parent_end: int,
    children: list[dict],
) -> list[str]:
    """
    Take 1-based parent span (phase1 convention), return line list for that span
    with each child's line range replaced by a single signature line.
    Children processed innermost-first by sorting by start line descending.
    """
    p_lo, p_hi = _phase1_line_span_to_slice_indices(parent_start, parent_end)
    segment = lines[p_lo:p_hi]
    if not children:
        return segment

    # (slice_start, slice_end, sig) in indices relative to `segment` (0-based within segment)
    rel_ranges: list[tuple[int, int, str]] = []
    for ch in children:
        cr = ch.get("range", {})
        cs = cr.get("start", {}).get("line", 0) + 1
        ce = cr.get("end", {}).get("line", 0) + 1
        c_lo, c_hi = _phase1_line_span_to_slice_indices(cs, ce)
        if c_lo < p_lo or c_hi > p_hi:
            continue
        rel_lo = c_lo - p_lo
        rel_hi = c_hi - p_lo
        rel_ranges.append((rel_lo, rel_hi, symbol_signature_for_replace(ch)))

    rel_ranges.sort(key=lambda x: x[0], reverse=True)
    out = list(segment)
    for rel_lo, rel_hi, sig in rel_ranges:
        if rel_lo < 0 or rel_hi > len(out) or rel_lo >= rel_hi:
            continue
        out[rel_lo:rel_hi] = [sig]

    return out


def build_embedding_input_text(
    file_lines: list[str],
    symbol: dict,
    hover_plain_text: str,
    symbol_signature: str,
) -> str:
    """
    Assemble deterministic embedding input for one node.

    - Sections: Documentation (from hover), Signature, Code (body with nested bodies
      collapsed to child signatures for non-leaf symbols).
    """
    name = symbol.get("name", "")
    range_info = symbol.get("range", {})
    start_line = range_info.get("start", {}).get("line", 0) + 1
    end_line = range_info.get("end", {}).get("line", 0) + 1

    children = symbol.get("children") or []
    hover_sig, hover_doc = split_hover_signature_and_doc(hover_plain_text)

    sig_line = symbol_signature.strip()
    if hover_sig and hover_sig not in sig_line:
        sig_line = f"{sig_line}\n{hover_sig}".strip()

    doc_block = (hover_doc or "").strip()

    if children:
        body_lines = _replace_child_spans_with_signatures(
            file_lines, start_line, end_line, children
        )
        body_text = "\n".join(body_lines).strip()
    else:
        lo, hi = _phase1_line_span_to_slice_indices(start_line, end_line)
        body_text = "\n".join(file_lines[lo:hi]).strip()

    parts: list[str] = []
    if doc_block:
        parts.append("Documentation:\n" + doc_block)
    if sig_line:
        parts.append("Signature:\n" + sig_line)
    if body_text:
        parts.append("Code:\n" + body_text)
    elif not parts:
        parts.append(name or "empty")

    return "\n\n".join(parts).strip()
