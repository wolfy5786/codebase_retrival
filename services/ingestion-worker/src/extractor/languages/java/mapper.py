"""
Java-specific mapper: refines base SymbolKind mapping for Java edge cases.
"""
import logging
from ...base import BaseMapper

logger = logging.getLogger(__name__)


class JavaMapper(BaseMapper):
    """
    Java-specific refinements on top of base LSP SymbolKind mapping.
    """
    
    def map_symbol_to_labels(self, symbol: dict, parent_id: str | None = None) -> list[str]:
        """
        Map LSP DocumentSymbol to CodeGraph labels with Java-specific refinements.
        
        Args:
            symbol: DocumentSymbol dict from LSP
            parent_id: Parent node ID (if nested)
            
        Returns:
            List of label strings
        """
        kind = symbol.get("kind", 0)
        name = symbol.get("name", "")
        detail = symbol.get("detail", "")
        
        # Start with base mapping
        labels = super().map_symbol_to_labels(symbol, parent_id)
        
        # Java-specific refinements
        
        # 1. Inner class detection
        if kind == 5 and parent_id:  # Class inside another class
            if "Class" in labels and "InnerClass" not in labels:
                labels.append("InnerClass")
                # Inner classes are level 3, not level 2
                if "Container" in labels:
                    labels.remove("Container")
        
        # 2. Method named same as enclosing class → Constructor
        #    (Redundant safety; jdtls should use Constructor=9 correctly)
        if kind == 6 and parent_id:  # Method
            # Check if method name matches parent class name
            # (This is a simplified check; in production we'd parse parent_id)
            # For now, jdtls correctly reports Constructor as kind=9, so this is just safety
            pass
        
        # 3. Static field detection
        if kind == 8:  # Field
            if "static" in detail.lower():
                # Already mapped to StaticMember by base, ensure it's there
                if "StaticMember" not in labels:
                    labels.append("StaticMember")
        
        # 4. Add language-specific label
        if kind == 5:  # Class
            labels.append("JavaClass")
        elif kind == 11:  # Interface
            labels.append("JavaInterface")
        elif kind == 10:  # Enum
            labels.append("JavaEnum")
        
        return labels
