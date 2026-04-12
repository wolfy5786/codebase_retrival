"""
Base extractor: standard LSP SymbolKind to CodeGraph label mapping.
Applies to all languages unless overridden by language-specific mapper.
"""
import logging

logger = logging.getLogger(__name__)


class BaseMapper:
    """
    Base mapper: LSP SymbolKind to CodeGraph node labels.
    Uses standard LSP SymbolKind values (see LSP spec).
    """

    # LSP SymbolKind enumeration (from LSP spec)
    SYMBOL_KIND = {
        1: "File",
        2: "Module",
        3: "Namespace",
        4: "Package",
        5: "Class",
        6: "Method",
        7: "Property",
        8: "Field",
        9: "Constructor",
        10: "Enum",
        11: "Interface",
        12: "Function",
        13: "Variable",
        14: "Constant",
        15: "String",
        16: "Number",
        17: "Boolean",
        18: "Array",
        19: "Object",
        20: "Key",
        21: "Null",
        22: "EnumMember",
        23: "Struct",
        24: "Event",
        25: "Operator",
        26: "TypeParameter",
    }

    def map_symbol_to_labels(
        self,
        symbol: dict,
        parent_id: str | None = None,
        parent_labels: list[str] | None = None,
    ) -> list[str]:
        """
        Map LSP DocumentSymbol to CodeGraph node labels.

        Args:
            symbol: DocumentSymbol dict from LSP
            parent_id: Parent node ID (if nested)
            parent_labels: Semantic labels of the parent symbol (no CodeNode), for scoped rules

        Returns:
            List of label strings (e.g. ["Class", "Internal"])
        """
        kind = symbol.get("kind", 0)
        name = symbol.get("name", "")
        detail = symbol.get("detail", "")

        labels: list[str] = []

        # Map SymbolKind to primary labels
        if kind == 1:  # File
            labels = ["File", "Module"]
        elif kind == 2:  # Module
            labels = ["Module"]
        elif kind == 3:  # Namespace
            labels = ["Module", "Internal"]
        elif kind == 4:  # Package
            labels = ["Module", "Internal"]
        elif kind == 5:  # Class
            labels = ["Class", "Internal"]
        elif kind == 11:  # Interface
            labels = ["Interface", "Internal"]
        elif kind == 6:  # Method
            labels = ["CodeUnit", "Method"]
        elif kind == 9:  # Constructor
            labels = ["Instantiator", "Constructor"]
        elif kind == 12:  # Function
            labels = ["CodeUnit", "Function"]
        elif kind == 8:  # Field
            labels = ["Attribute"]
        elif kind == 7:  # Property
            labels = ["Attribute"]
        elif kind == 13:  # Variable
            labels = ["Attribute"]
        elif kind == 14:  # Constant
            labels = ["Attribute"]
        elif kind == 10:  # Enum
            labels = ["Enum", "Internal"]
        elif kind == 22:  # EnumMember
            labels = ["Attribute"]
        elif kind == 24:  # Event
            labels = ["Event"]
        elif kind == 23:  # Struct
            labels = ["Class", "Internal"]
        elif kind == 25:  # Operator
            labels = ["CodeUnit", "Method"]
        else:
            logger.debug("Unmapped SymbolKind %d for symbol %s", kind, name)
            return []

        self._apply_common_heuristics(labels, kind, name, detail)
        return labels

    def _apply_common_heuristics(self, labels: list[str], kind: int, name: str, detail: str) -> None:
        """Mutates labels: destructor, lambda, abstract class hints (LSP has no dedicated kinds)."""
        d = detail or ""
        n = name or ""
        combined = f"{d} {n}"

        if kind in (6, 12) and n.startswith("~"):
            if "Destructor" not in labels:
                labels.append("Destructor")

        if kind in (6, 12):
            cl = combined.lower()
            if "lambda" in cl or "=>" in combined or "<lambda>" in combined:
                if "Lambda" not in labels:
                    labels.append("Lambda")

        if kind == 5 and "abstract" in d.lower():
            if "Abstract" not in labels:
                labels.append("Abstract")

    def get_symbol_kind_name(self, kind: int) -> str:
        """Get human-readable name for SymbolKind."""
        return self.SYMBOL_KIND.get(kind, f"Unknown({kind})")
