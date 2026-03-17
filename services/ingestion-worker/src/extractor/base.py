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
    
    def map_symbol_to_labels(self, symbol: dict, parent_id: str | None = None) -> list[str]:
        """
        Map LSP DocumentSymbol to CodeGraph node labels.
        
        Args:
            symbol: DocumentSymbol dict from LSP
            parent_id: Parent node ID (if nested)
            
        Returns:
            List of label strings (e.g. ["Container", "Internal"])
        """
        kind = symbol.get("kind", 0)
        name = symbol.get("name", "")
        detail = symbol.get("detail", "")
        
        labels = []
        
        # Map SymbolKind to primary labels
        if kind == 1:  # File
            labels = ["File", "Module"]
        elif kind == 2:  # Module
            labels = ["Module"]
        elif kind == 5:  # Class
            labels = ["Container", "Class", "Internal"]
        elif kind == 11:  # Interface
            labels = ["Interface", "Internal"]
        elif kind == 6:  # Method
            labels = ["CodeUnit", "Method"]
        elif kind == 9:  # Constructor
            labels = ["Instantiator", "Constructor"]
        elif kind == 12:  # Function
            labels = ["CodeUnit", "Function"]
        elif kind == 8:  # Field
            labels = ["StaticMember"]
        elif kind == 7:  # Property
            labels = ["StaticMember"]
        elif kind == 13:  # Variable
            labels = ["StaticMember"]
        elif kind == 14:  # Constant
            labels = ["StaticMember"]
        elif kind == 10:  # Enum
            labels = ["Enum", "Internal"]
        elif kind == 22:  # EnumMember
            labels = ["StaticMember"]
        elif kind == 24:  # Event
            labels = ["Event"]
        elif kind == 23:  # Struct
            labels = ["Container", "Internal"]
        else:
            logger.debug("Unmapped SymbolKind %d for symbol %s", kind, name)
            return []
        
        return labels
    
    def get_symbol_kind_name(self, kind: int) -> str:
        """Get human-readable name for SymbolKind."""
        return self.SYMBOL_KIND.get(kind, f"Unknown({kind})")
