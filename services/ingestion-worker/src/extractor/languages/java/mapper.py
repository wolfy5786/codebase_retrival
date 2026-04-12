"""
Java-specific mapper: refines base SymbolKind mapping for Java edge cases.
"""
import logging
import re

from ...base import BaseMapper

logger = logging.getLogger(__name__)

# Fields under these parents may be tagged Object/Instance when type is reference.
# Includes Interface for `public static final` reference constants on interfaces.
_JAVA_OBJECT_PARENT_LABELS = frozenset({"Class", "InnerClass", "Enum", "Interface"})

_JAVA_PRIMITIVE_TYPES = frozenset(
    {
        "int",
        "long",
        "float",
        "double",
        "boolean",
        "char",
        "byte",
        "short",
        "void",
    }
)


def _java_field_detail_is_reference_type(detail: str) -> bool:
    """True if jdtls-style field detail looks like a non-primitive (reference) type."""
    if not detail or not detail.strip():
        return False
    t = detail.strip().lstrip(":").strip()
    # Strip generics for primitive check: List<int> still reference outer type
    base_for_prim = t.split("<", 1)[0].strip()
    base_for_prim = re.sub(r"\[\s*\]$", "", base_for_prim)
    first = base_for_prim.split()[0] if base_for_prim else ""
    first = first.replace("[]", "")
    simple = first.split(".")[-1]
    if simple.lower() in _JAVA_PRIMITIVE_TYPES:
        return False
    return True


class JavaMapper(BaseMapper):
    """
    Java-specific refinements on top of base LSP SymbolKind mapping.
    """

    def map_symbol_to_labels(
        self,
        symbol: dict,
        parent_id: str | None = None,
        parent_labels: list[str] | None = None,
    ) -> list[str]:
        kind = symbol.get("kind", 0)
        name = symbol.get("name", "")
        detail = symbol.get("detail", "")

        labels = super().map_symbol_to_labels(symbol, parent_id, parent_labels)

        # 1. Inner class detection
        if kind == 5 and parent_id:
            if parent_labels and "Class" in parent_labels:
                if "Class" in labels and "InnerClass" not in labels:
                    labels.append("InnerClass")

        # 2. Static field detection (redundant safety)
        if kind == 8:
            if "static" in detail.lower() and "Attribute" not in labels:
                labels.append("Attribute")

        # 3. Object / Instance on class-scoped reference fields (not Python — handled by never using this mapper for python)
        # Kind 22 = EnumMember (reference-typed enum constants).
        if kind in (7, 8, 13, 22) and parent_labels:
            if _JAVA_OBJECT_PARENT_LABELS.intersection(parent_labels) and _java_field_detail_is_reference_type(
                detail
            ):
                if "Object" not in labels:
                    labels.append("Object")
                if "Instance" not in labels:
                    labels.append("Instance")

        # 4. Language-specific label
        if kind == 5:
            labels.append("JavaClass")
        elif kind == 11:
            labels.append("JavaInterface")
        elif kind == 10:
            labels.append("JavaEnum")

        return labels
