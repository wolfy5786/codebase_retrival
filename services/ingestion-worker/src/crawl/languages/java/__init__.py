from .phase1_strategy import JAVA_PHASE1_STRATEGY
from .phase2_tier1_strategy import JAVA_TIER1_STRATEGY
from .phase2_tier3_strategy import JAVA_TIER3_STRATEGY
from ..base import LanguageLspBackend
from ....lsp.servers.java import get_initialization_options, start_jdtls

JAVA_LSP_BACKEND = LanguageLspBackend(
    language="java",
    start_server=start_jdtls,
    initialization_options=get_initialization_options,
)

__all__ = [
    "JAVA_LSP_BACKEND",
    "JAVA_PHASE1_STRATEGY",
    "JAVA_TIER1_STRATEGY",
    "JAVA_TIER3_STRATEGY",
]
