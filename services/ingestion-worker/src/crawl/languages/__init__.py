from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .base import (
    LanguageLspBackend,
    NoopPhase1Strategy,
    NoopTier1Strategy,
    NoopTier3Strategy,
    Phase1LanguageStrategy,
    Tier1LanguageStrategy,
    Tier3LanguageStrategy,
)
from .java import (
    JAVA_LSP_BACKEND,
    JAVA_PHASE1_STRATEGY,
    JAVA_TIER1_STRATEGY,
    JAVA_TIER3_STRATEGY,
)


@dataclass(frozen=True)
class LanguageSupport:
    language: str
    phase1: Phase1LanguageStrategy
    tier1: Tier1LanguageStrategy
    tier3: Tier3LanguageStrategy
    lsp_backend: LanguageLspBackend | None = None


_NOOP_PHASE1 = NoopPhase1Strategy()
_NOOP_TIER1 = NoopTier1Strategy()
_NOOP_TIER3 = NoopTier3Strategy()

_REGISTRY: dict[str, LanguageSupport] = {
    "java": LanguageSupport(
        language="java",
        phase1=JAVA_PHASE1_STRATEGY,
        tier1=JAVA_TIER1_STRATEGY,
        tier3=JAVA_TIER3_STRATEGY,
        lsp_backend=JAVA_LSP_BACKEND,
    ),
}


def get_registered_languages() -> list[str]:
    return sorted(_REGISTRY.keys())


def get_phase1_strategy_for_file(rel_path: str) -> Phase1LanguageStrategy:
    for support in _REGISTRY.values():
        if support.phase1.supports_file(rel_path):
            return support.phase1
    return _NOOP_PHASE1


def get_tier1_strategy(language: str) -> Tier1LanguageStrategy:
    support = _REGISTRY.get((language or "").lower())
    return support.tier1 if support else _NOOP_TIER1


def get_tier3_strategy(language: str) -> Tier3LanguageStrategy:
    support = _REGISTRY.get((language or "").lower())
    return support.tier3 if support else _NOOP_TIER3


def get_lsp_backend(language: str) -> LanguageLspBackend | None:
    support = _REGISTRY.get((language or "").lower())
    return support.lsp_backend if support else None


def get_phase1_lsp_backends(rel_paths: list[str]) -> list[LanguageLspBackend]:
    languages: list[str] = []
    for rel_path in rel_paths:
        strategy = get_phase1_strategy_for_file(rel_path)
        if not strategy.supports_file(rel_path):
            continue
        if not strategy.needs_lsp(rel_path):
            continue
        if strategy.language not in languages:
            languages.append(strategy.language)
    return [backend for lang in languages if (backend := get_lsp_backend(lang)) is not None]


def get_tier3_lsp_backends(nodes: list[dict[str, Any]]) -> list[LanguageLspBackend]:
    languages: list[str] = []
    for node in nodes:
        language = (node.get("language") or "").lower()
        if not language or language in languages:
            continue
        strategy = get_tier3_strategy(language)
        if not strategy.should_process_node(node):
            continue
        if get_lsp_backend(language) is not None:
            languages.append(language)
    return [backend for lang in languages if (backend := get_lsp_backend(lang)) is not None]


__all__ = [
    "LanguageSupport",
    "get_registered_languages",
    "get_phase1_strategy_for_file",
    "get_tier1_strategy",
    "get_tier3_strategy",
    "get_lsp_backend",
    "get_phase1_lsp_backends",
    "get_tier3_lsp_backends",
]
