"""
Extract plain text from textDocument/hover results for docstring/signature hints.
"""
from __future__ import annotations

import re


def hover_result_to_text(hover: dict | None) -> str:
    """
    Flatten LSP Hover to a single string (markdown/code blocks stripped loosely).
    """
    if not hover:
        return ""
    contents = hover.get("contents")
    if contents is None:
        return ""
    if isinstance(contents, str):
        return _strip_markdown_noise(contents)
    if isinstance(contents, dict):
        return _strip_markdown_noise(contents.get("value", "") or "")
    if isinstance(contents, list):
        parts: list[str] = []
        for item in contents:
            if isinstance(item, str):
                parts.append(_strip_markdown_noise(item))
            elif isinstance(item, dict):
                parts.append(_strip_markdown_noise(item.get("value", "") or ""))
        return "\n".join(p for p in parts if p)
    return ""


def split_hover_signature_and_doc(hover_text: str) -> tuple[str, str]:
    """
    Heuristic split: first line(s) as signature, rest as documentation.
    """
    text = hover_text.strip()
    if not text:
        return "", ""
    lines = text.splitlines()
    if len(lines) == 1:
        return lines[0], ""
    # JavaDoc / block often starts after first line (signature)
    sig = lines[0]
    doc = "\n".join(lines[1:]).strip()
    return sig, doc


def _strip_markdown_noise(s: str) -> str:
    s = re.sub(r"```[\w]*\n?", "", s)
    s = s.replace("```", "")
    return s.strip()
