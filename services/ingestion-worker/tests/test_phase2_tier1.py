"""Unit tests for Phase 2 Tier 1 (labels + properties)."""
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.crawl.phase2 import (
    _compute_level,
    _parse_java_parameter_types,
    build_file_contents_from_batch,
    crawl_phase2_tier1,
    file_key_for_node,
)


class TestJavaParameterTypes(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(
            _parse_java_parameter_types("getName(String a, int b)"),
            ["String", "int"],
        )

    def test_void_method(self):
        self.assertEqual(_parse_java_parameter_types("run()"), [])


class TestLevel(unittest.TestCase):
    def test_method(self):
        self.assertEqual(_compute_level({"Method", "CodeUnit", "Internal"}), 3)

    def test_class(self):
        self.assertEqual(_compute_level({"Class", "Internal"}), 2)


class TestCrawlPhase2Tier1(unittest.TestCase):
    def test_mapper_and_file_map(self):
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            java = tmp_path / "Bar.java"
            java.write_text(
                "package x;\n"
                "public class Bar {\n"
                "  public String hello(int a) { return null; }\n"
                "}\n",
                encoding="utf-8",
            )
            ws = str(tmp_path)
            cid = "cb-test"
            rel = "Bar.java"
            class_id = f"{cid}:{rel}:2:Bar"
            method_id = f"{cid}:{rel}:3:hello"
            nodes = [
                {
                    "id": class_id,
                    "codebase_id": cid,
                    "name": "Bar",
                    "labels": ["CodeNode"],
                    "language": "java",
                    "path": rel,
                    "kind": 5,
                    "detail": "",
                    "signature": "",
                    "start_line": 2,
                    "end_line": 4,
                },
                {
                    "id": method_id,
                    "codebase_id": cid,
                    "name": "hello",
                    "labels": ["CodeNode"],
                    "language": "java",
                    "path": rel,
                    "kind": 6,
                    "detail": "String",
                    "signature": "hello(int a)",
                    "start_line": 3,
                    "end_line": 3,
                },
            ]
            edges = [{"type": "CONTAINS", "from_id": class_id, "to_id": method_id, "order": 1}]
            batch = [(rel, "hash", java.read_bytes())]
            fmap = build_file_contents_from_batch(ws, batch)
            self.assertIn(file_key_for_node(ws, rel), fmap)

            updates = crawl_phase2_tier1(nodes, edges, fmap, ws, cid)
            by_id = {u["id"]: u for u in updates}
            self.assertIn("Class", by_id[class_id]["labels_to_add"])
            self.assertIn("Method", by_id[method_id]["labels_to_add"])
            self.assertEqual(by_id[method_id]["properties"].get("parameter_types"), ["int"])


if __name__ == "__main__":
    unittest.main()
