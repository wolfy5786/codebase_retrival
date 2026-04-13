from __future__ import annotations

import re
from typing import Any

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
_ANNOTATION_RE = re.compile(r"@(\w+)(?:\([^)]*\))?")


def _lines_near_start(file_text: str, start_line: int) -> tuple[list[str], str, str]:
    lines = file_text.splitlines()
    if not lines:
        return [], "", ""
    start = int(start_line or 1)
    lo = max(0, start - 4)
    hi = min(len(lines), start + 2)
    declaration_block = "\n".join(lines[lo:hi])
    body_hi = min(len(lines), start + 40)
    body_snippet = "\n".join(lines[start - 1 : body_hi])
    return lines, declaration_block, body_snippet


def _java_regex_labels(
    node: dict[str, Any],
    declaration_block: str,
    body_snippet: str,
) -> list[str]:
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
    for part in parts:
        if not part:
            continue
        part = re.sub(r"\s*\.\.\.\s*$", "", part).strip()
        tokens = part.split()
        if len(tokens) >= 2:
            types.append(" ".join(tokens[:-1]))
        elif len(tokens) == 1:
            types.append(tokens[0])
    return types


def _java_return_type_from_line(line: str, name: str) -> str | None:
    s = line.strip()
    if not s or not name:
        return None
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
    node: dict[str, Any],
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
    declaration_block = "\n".join(lines[lo:hi])

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


def _strip_java_generics(text: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(text):
        if text[i] == "<":
            depth = 1
            i += 1
            while i < len(text) and depth:
                if text[i] == "<":
                    depth += 1
                elif text[i] == ">":
                    depth -= 1
                i += 1
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


def _java_simple_type_name(raw: str) -> str:
    if not raw:
        return ""
    text = raw.strip()
    while text.startswith("@"):
        depth = 0
        j = 0
        while j < len(text):
            if text[j] == "(":
                depth += 1
            elif text[j] == ")" and depth > 0:
                depth -= 1
            elif text[j] in " \t" and depth == 0 and j > 0:
                break
            j += 1
        text = text[j:].strip()
    text = _strip_java_generics(text).strip()
    if not text:
        return ""
    return text.split(".")[-1].strip()


def _split_java_type_list(text: str) -> list[str]:
    text = text.strip().rstrip(",")
    if not text:
        return []
    parts: list[str] = []
    cur: list[str] = []
    depth = 0
    for ch in text:
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
    return [part for part in parts if part]


def _extract_java_type_header(lines: list[str], start_line: int, max_lines: int = 40) -> str:
    if not lines or start_line < 1:
        return ""
    idx = start_line - 1
    end = min(len(lines), start_line - 1 + max_lines)
    parts: list[str] = []
    while idx < end:
        parts.append(lines[idx])
        if "{" in lines[idx]:
            break
        idx += 1
    return "\n".join(parts)


def _java_tier1_rel_candidates(kind: int, header: str) -> list[dict[str, str]]:
    header_one = " ".join(header.split())
    if not header_one:
        return []

    is_enum = bool(re.search(r"\benum\s+\w+", header_one))
    is_interface = kind == 11
    out: list[dict[str, str]] = []

    if kind in (5, 10) and not is_interface:
        m_imp = re.search(r"\bimplements\s+(.+?)(?=\s*\{)", header_one)
        if m_imp:
            for type_name in _split_java_type_list(m_imp.group(1)):
                simple_name = _java_simple_type_name(type_name)
                if simple_name:
                    out.append({"rel_type": "IMPLEMENTS", "target_name": simple_name})

    if is_enum:
        return out

    if is_interface:
        m_ext = re.search(r"\bextends\s+(.+?)(?=\s*\{)", header_one)
        if m_ext:
            for type_name in _split_java_type_list(m_ext.group(1)):
                simple_name = _java_simple_type_name(type_name)
                if simple_name:
                    out.append({"rel_type": "INHERITS", "target_name": simple_name})
        return out

    if kind == 5:
        m_ext = re.search(r"\bextends\s+(.+?)(?=\s+implements\s+|\s*\{)", header_one)
        if m_ext:
            simple_name = _java_simple_type_name(m_ext.group(1).strip())
            if simple_name:
                out.append({"rel_type": "INHERITS", "target_name": simple_name})

    return out


class JavaTier1Strategy:
    language = "java"

    def extra_labels(self, node: dict[str, Any], file_text: str) -> list[str]:
        _, declaration_block, body_snippet = _lines_near_start(
            file_text, int(node.get("start_line") or 1)
        )
        return _java_regex_labels(node, declaration_block, body_snippet)

    def extract_properties(self, node: dict[str, Any], file_text: str) -> dict[str, Any]:
        lines = file_text.splitlines()
        return _extract_java_tier1_properties(node, lines)

    def relationship_candidates(self, node: dict[str, Any], file_text: str) -> list[dict[str, str]]:
        kind = node.get("kind")
        if kind not in (5, 10, 11):
            return []
        lines = file_text.splitlines()
        if not lines:
            return []
        start_line = int(node.get("start_line") or 1)
        header = _extract_java_type_header(lines, start_line)
        return _java_tier1_rel_candidates(kind, header)


JAVA_TIER1_STRATEGY = JavaTier1Strategy()

__all__ = [
    "JAVA_TIER1_STRATEGY",
    "_extract_java_type_header",
    "_java_simple_type_name",
    "_java_tier1_rel_candidates",
    "_parse_java_parameter_types",
    "_split_java_type_list",
]
