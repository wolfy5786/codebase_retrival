from __future__ import annotations


class JavaPhase1Strategy:
    language = "java"

    def supports_file(self, rel_path: str) -> bool:
        return rel_path.lower().endswith(".java")

    def needs_lsp(self, rel_path: str) -> bool:
        return self.supports_file(rel_path)

    def lsp_language_id(self, rel_path: str) -> str:
        _ = rel_path
        return "java"


JAVA_PHASE1_STRATEGY = JavaPhase1Strategy()
