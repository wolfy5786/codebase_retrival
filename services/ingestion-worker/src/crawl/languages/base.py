from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    import subprocess

    from ...graph_writer import GraphWriter
    from ...lsp.client import LspClient


class Phase1LanguageStrategy(Protocol):
    language: str

    def supports_file(self, rel_path: str) -> bool:
        ...

    def needs_lsp(self, rel_path: str) -> bool:
        ...

    def lsp_language_id(self, rel_path: str) -> str:
        ...


class Tier1LanguageStrategy(Protocol):
    language: str

    def extra_labels(self, node: dict[str, Any], file_text: str) -> list[str]:
        ...

    def extract_properties(self, node: dict[str, Any], file_text: str) -> dict[str, Any]:
        ...

    def relationship_candidates(self, node: dict[str, Any], file_text: str) -> list[dict[str, str]]:
        ...


@dataclass(frozen=True)
class Tier3NodeContext:
    client: LspClient
    graph_writer: GraphWriter
    workspace_root: str
    codebase_id: str
    file_map: dict[str, str]
    abs_file: str
    line0: int
    id_to_node: dict[str, dict[str, Any]]
    parent_of: dict[str, str]
    all_paths: set[str]
    col0: int = 0
    """0-based UTF-16 column on ``line0`` for LSP; use symbol selection, not line start."""


@dataclass
class Tier3EnrichmentResult:
    labels_to_add: list[str] = field(default_factory=list)
    properties: dict[str, Any] = field(default_factory=dict)
    calls_edges: list[dict[str, Any]] = field(default_factory=list)
    sets_edges: list[dict[str, Any]] = field(default_factory=list)
    gets_edges: list[dict[str, Any]] = field(default_factory=list)


class Tier3LanguageStrategy(Protocol):
    language: str

    def should_process_node(self, node: dict[str, Any]) -> bool:
        ...

    def did_open_language_id(self, rel_path: str) -> str:
        ...

    def enrich_node(self, node: dict[str, Any], ctx: Tier3NodeContext) -> Tier3EnrichmentResult:
        ...


@dataclass(frozen=True)
class LanguageLspBackend:
    language: str
    start_server: Any
    initialization_options: Any

    def start(self, workspace_root: str) -> subprocess.Popen:
        return self.start_server(workspace_root)

    def get_initialization_options(self, workspace_root: str) -> dict[str, Any]:
        return self.initialization_options(workspace_root)


class NoopPhase1Strategy:
    language = "unknown"

    def supports_file(self, rel_path: str) -> bool:
        return False

    def needs_lsp(self, rel_path: str) -> bool:
        return False

    def lsp_language_id(self, rel_path: str) -> str:
        return ""


class NoopTier1Strategy:
    language = "unknown"

    def extra_labels(self, node: dict[str, Any], file_text: str) -> list[str]:
        _ = node, file_text
        return []

    def extract_properties(self, node: dict[str, Any], file_text: str) -> dict[str, Any]:
        _ = node, file_text
        return {}

    def relationship_candidates(self, node: dict[str, Any], file_text: str) -> list[dict[str, str]]:
        _ = node, file_text
        return []


class NoopTier3Strategy:
    language = "unknown"

    def should_process_node(self, node: dict[str, Any]) -> bool:
        _ = node
        return False

    def did_open_language_id(self, rel_path: str) -> str:
        _ = rel_path
        return ""

    def enrich_node(self, node: dict[str, Any], ctx: Tier3NodeContext) -> Tier3EnrichmentResult:
        _ = node, ctx
        return Tier3EnrichmentResult()
