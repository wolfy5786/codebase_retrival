"""
C/C++ mapper: clangd-style symbols; Object/Instance on class-scoped reference fields.
"""
import re

from ...base import BaseMapper

# Includes Interface for MSVC __interface / abstract bases modeled as Interface.
_CPP_PARENT_FOR_OBJECT = frozenset({"Class", "InnerClass", "Enum", "Interface"})

# Single-token primitive and common typedefs we do not tag as Object/Instance.
_CPP_NON_REFERENCE_FIRST = frozenset(
    {
        "void",
        "bool",
        "char",
        "short",
        "int",
        "long",
        "float",
        "double",
        "wchar_t",
        "char16_t",
        "char32_t",
        "size_t",
        "ssize_t",
        "int8_t",
        "int16_t",
        "int32_t",
        "int64_t",
        "uint8_t",
        "uint16_t",
        "uint32_t",
        "uint64_t",
    }
)


def _cpp_field_detail_is_reference_type(detail: str) -> bool:
    if not detail or not detail.strip():
        return False
    t = detail.strip()
    for prefix in ("const ", "volatile ", "static ", "mutable ", "inline ", "constexpr "):
        while t.lower().startswith(prefix):
            t = t[len(prefix) :]
    t = t.lstrip(":").strip()
    if not t:
        return False
    # Unwrap one level: `Foo *`, `Foo &`, `Foo &&`
    t = re.sub(r"\s*([&*]+)\s*$", "", t)
    head = t.split("<", 1)[0]
    first = head.replace("typename", "").strip().split()[-1] if head.strip() else ""
    first = re.sub(r"\[.*?\]", "", first)
    base = first.split("::")[-1] if first else ""
    if not base:
        return False
    if base.lower() in _CPP_NON_REFERENCE_FIRST:
        return False
    return True


class CppMapper(BaseMapper):
    def map_symbol_to_labels(
        self,
        symbol: dict,
        parent_id: str | None = None,
        parent_labels: list[str] | None = None,
    ) -> list[str]:
        kind = symbol.get("kind", 0)
        detail = symbol.get("detail", "")

        labels = super().map_symbol_to_labels(symbol, parent_id, parent_labels)

        if kind == 5 and parent_id and parent_labels:
            if "Class" in parent_labels and "Class" in labels and "InnerClass" not in labels:
                labels.append("InnerClass")

        if kind in (7, 8, 13, 22) and parent_labels:
            if _CPP_PARENT_FOR_OBJECT.intersection(parent_labels) and _cpp_field_detail_is_reference_type(detail):
                if "Object" not in labels:
                    labels.append("Object")
                if "Instance" not in labels:
                    labels.append("Instance")

        return labels
