"""
Phase 1 crawl: shared, language-agnostic.
Walks documentSymbol responses to build nodes and CONTAINS relationships.
Delegates symbol-to-label mapping to the extractor layer.
"""
import logging
from pathlib import Path
from typing import Any

from ..lsp.client import LspClient
from ..extractor import get_mapper

logger = logging.getLogger(__name__)


def crawl_phase1(
    client: LspClient,
    file_paths: list[str],
    language: str,
    codebase_id: str,
) -> tuple[list[dict], list[dict]]:
    """
    Phase 1 crawl: extract nodes and CONTAINS relationships from LSP documentSymbol.
    
    Args:
        client: Initialized LSP client
        file_paths: List of absolute file paths to analyze
        language: Language name (e.g. "java", "python")
        codebase_id: Codebase UUID
        
    Returns:
        (nodes, contains_edges) tuple
        - nodes: list of node dicts
        - contains_edges: list of CONTAINS edge dicts
    """
    logger.info("Phase 1 crawl started: language=%s files=%d", language, len(file_paths))
    
    mapper = get_mapper(language)
    all_nodes = []
    all_contains_edges = []
    
    for file_path in file_paths:
        try:
            # Read file content
            content = Path(file_path).read_text(encoding="utf-8", errors="ignore")
            
            # Open document in LSP
            language_id = _get_language_id(language)
            client.did_open(file_path, language_id, content)
            
            # Request documentSymbol
            symbols = client.document_symbol(file_path)
            if not symbols:
                logger.debug("Phase 1: no symbols found in %s", file_path)
                continue
            
            # Extract nodes and CONTAINS edges from symbol tree
            file_nodes, file_edges = _extract_nodes_and_contains(
                symbols,
                file_path,
                language,
                codebase_id,
                mapper,
            )
            
            all_nodes.extend(file_nodes)
            all_contains_edges.extend(file_edges)
            
            logger.debug(
                "Phase 1: extracted %d nodes, %d CONTAINS edges from %s",
                len(file_nodes),
                len(file_edges),
                file_path,
            )
            
        except Exception as e:
            logger.exception("Phase 1 error processing file %s: %s", file_path, e)
            raise
    
    logger.info(
        "Phase 1 crawl completed: nodes=%d contains_edges=%d",
        len(all_nodes),
        len(all_contains_edges),
    )
    
    return all_nodes, all_contains_edges


def _get_language_id(language: str) -> str:
    """Map internal language name to LSP languageId."""
    mapping = {
        "java": "java",
        "python": "python",
        "javascript": "javascript",
        "typescript": "typescript",
        "go": "go",
        "cpp": "cpp",
        "c": "c",
        "rust": "rust",
    }
    return mapping.get(language.lower(), language.lower())


def _extract_nodes_and_contains(
    symbols: list[dict],
    file_path: str,
    language: str,
    codebase_id: str,
    mapper: Any,
    parent_id: str | None = None,
    level_offset: int = 1,
) -> tuple[list[dict], list[dict]]:
    """
    Recursively walk DocumentSymbol tree to extract nodes and CONTAINS edges.
    
    Args:
        symbols: List of DocumentSymbol dicts from LSP
        file_path: Absolute file path
        language: Language name
        codebase_id: Codebase UUID
        mapper: Language-specific mapper instance
        parent_id: Parent node ID (for CONTAINS edges)
        level_offset: Current hierarchical level (1 = file level)
        
    Returns:
        (nodes, contains_edges) tuple
    """
    nodes = []
    edges = []
    
    for symbol in symbols:
        # Extract symbol metadata
        name = symbol.get("name", "")
        kind = symbol.get("kind", 0)
        range_info = symbol.get("range", {})
        start_line = range_info.get("start", {}).get("line", 0) + 1  # LSP is 0-indexed
        end_line = range_info.get("end", {}).get("line", 0) + 1
        
        # Use mapper to convert SymbolKind to labels
        labels = mapper.map_symbol_to_labels(symbol, parent_id)
        if not labels:
            logger.debug("Phase 1: skipping symbol %s (no labels)", name)
            continue
        
        # Generate node ID (simplified; production should use UUID or hash)
        node_id = f"{codebase_id}:{file_path}:{start_line}:{name}"
        
        # Determine level from primary label
        level = _get_level_from_labels(labels, level_offset)
        
        # Build node dict
        node = {
            "id": node_id,
            "codebase_id": codebase_id,
            "name": name,
            "labels": labels,
            "language": language,
            "level": level,
            "path": file_path,
            "storage_ref": f"codebases/{codebase_id}/files/{file_path}",
            "start_line": start_line,
            "end_line": end_line,
            "signature": _extract_signature(symbol),
        }
        
        nodes.append(node)
        
        # Create CONTAINS edge if there's a parent
        if parent_id:
            # #region agent log
            try:
                import json
                _logpath = Path(__file__).resolve().parents[4] / "debug-064aa2.log"
                with open(_logpath, "a", encoding="utf-8") as _f:
                    _f.write(json.dumps({"sessionId":"064aa2","location":"phase1.py:169","message":"CONTAINS edge","data":{"parent_id":parent_id,"child_id":node_id,"name":name,"kind":kind,"file_path":file_path},"timestamp":__import__("time").time_ns()//1000000}) + "\n")
            except Exception:
                pass
            # #endregion
            edge = {
                "from_id": parent_id,
                "to_id": node_id,
                "type": "CONTAINS",
                "order": len(nodes),  # Declaration order
            }
            edges.append(edge)
        
        # Recursively process children
        children = symbol.get("children", [])
        if children:
            child_nodes, child_edges = _extract_nodes_and_contains(
                children,
                file_path,
                language,
                codebase_id,
                mapper,
                parent_id=node_id,
                level_offset=level + 1,
            )
            nodes.extend(child_nodes)
            edges.extend(child_edges)
    
    return nodes, edges


def _get_level_from_labels(labels: list[str], default: int) -> int:
    """
    Determine hierarchical level from node labels.
    Based on documentation/Nodes.txt.
    """
    label_to_level = {
        "Module": 1,
        "File": 1,
        "Container": 2,
        "Class": 2,
        "Interface": 2,
        "Enum": 2,
        "Database": 2,
        "CodeUnit": 3,
        "Function": 3,
        "Method": 3,
        "Instantiator": 3,
        "Constructor": 3,
        "Destructor": 3,
        "StaticMember": 3,
        "InnerClass": 3,
        "Object": 3,
        "Instance": 3,
        "Event": 3,
        "Thread": 3,
        "Lambda": 4,
        "try": 4,
        "except": 4,
        "catch": 4,
    }
    
    for label in labels:
        if label in label_to_level:
            return label_to_level[label]
    
    return default


def _extract_signature(symbol: dict) -> str:
    """
    Extract a compact signature from DocumentSymbol.
    For now, just return name + detail if available.
    """
    name = symbol.get("name", "")
    detail = symbol.get("detail", "")
    if detail:
        return f"{name} {detail}"
    return name
