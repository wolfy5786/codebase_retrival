"""
Extractor layer: maps LSP SymbolKind to CodeGraph node labels.
Provides shared base mapping and per-language refinements.
"""
import logging

logger = logging.getLogger(__name__)


def get_mapper(language: str):
    """
    Get the appropriate mapper for the given language.
    
    Args:
        language: Language name (e.g. "java", "python")
        
    Returns:
        Mapper instance with map_symbol_to_labels method
    """
    language_lower = language.lower()
    
    if language_lower == "java":
        from .languages.java.mapper import JavaMapper
        return JavaMapper()
    
    # Default to base mapper for unsupported languages
    from .base import BaseMapper
    logger.warning("No specific mapper for language %s, using base mapper", language)
    return BaseMapper()
