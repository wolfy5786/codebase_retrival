import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.crawl.languages import get_phase1_lsp_backends, get_tier3_lsp_backends
from src.crawl.phase1 import crawl_phase1


class _FakeLspClient:
    def __init__(self):
        self.did_open_calls: list[tuple[str, str, str]] = []

    def did_open(self, abs_path: str, language_id: str, text: str) -> None:
        self.did_open_calls.append((abs_path, language_id, text))

    def document_symbol(self, abs_path: str) -> list[dict]:
        _ = abs_path
        return []


class TestLanguageRegistry(unittest.TestCase):
    def test_phase1_backends_select_java_only(self):
        backends = get_phase1_lsp_backends(["src/App.java", "src/app.py"])
        self.assertEqual([backend.language for backend in backends], ["java"])

    def test_tier3_backends_select_java_only(self):
        nodes = [
            {"id": "1", "language": "java", "path": "src/App.java"},
            {"id": "2", "language": "python", "path": "src/app.py"},
        ]
        backends = get_tier3_lsp_backends(nodes)
        self.assertEqual([backend.language for backend in backends], ["java"])


class TestPhase1LanguageRouting(unittest.TestCase):
    def test_crawl_phase1_uses_registry_language_id_for_java(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            java_file = root / "App.java"
            java_file.write_text("class App {}", encoding="utf-8")

            client = _FakeLspClient()
            nodes, edges = crawl_phase1(
                client,
                {"File": [(str(java_file), "App.java")]},
                "cb1",
                active_lsp_languages={"java"},
            )

            self.assertEqual(len(edges), 0)
            self.assertEqual(len(nodes), 1)
            self.assertEqual(client.did_open_calls[0][1], "java")
            self.assertEqual(nodes[0]["labels"], ["CodeNode", "File"])

    def test_crawl_phase1_uses_placeholder_without_active_backend(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            java_file = root / "App.java"
            java_file.write_text("class App {}", encoding="utf-8")

            client = _FakeLspClient()
            nodes, edges = crawl_phase1(
                client,
                {"File": [(str(java_file), "App.java")]},
                "cb1",
                active_lsp_languages=set(),
            )

            self.assertEqual(len(edges), 0)
            self.assertEqual(len(nodes), 1)
            self.assertEqual(client.did_open_calls, [])
            self.assertEqual(nodes[0]["labels"], ["CodeNode", "File"])


if __name__ == "__main__":
    unittest.main()
