"""Unit tests for Phase 2 Tier 1 (labels + properties + Java Tier 1 edges)."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.crawl.phase2 import (
    _compute_level,
    build_file_contents_from_batch,
    crawl_phase2_tier1,
    file_key_for_node,
)
from src.crawl.languages.java.phase2_tier1_strategy import (
    _extract_java_type_header,
    _java_simple_type_name,
    _java_tier1_rel_candidates,
    _parse_java_parameter_types,
    _split_java_type_list,
)
from src.graph_writer import GraphWriter


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


class TestJavaTier1RelParsing(unittest.TestCase):
    def test_split_java_type_list_generics(self):
        self.assertEqual(
            _split_java_type_list("Map<String, List<Integer>>, Runnable"),
            ["Map<String, List<Integer>>", "Runnable"],
        )

    def test_java_simple_type_name(self):
        self.assertEqual(_java_simple_type_name("java.util.List<String>"), "List")
        self.assertEqual(_java_simple_type_name("Outer.Inner"), "Inner")

    def test_class_extends_and_implements(self):
        h = "public class Child extends Parent implements If1, If2 {"
        got = _java_tier1_rel_candidates(5, h)
        types = {(x["rel_type"], x["target_name"]) for x in got}
        self.assertIn(("INHERITS", "Parent"), types)
        self.assertIn(("IMPLEMENTS", "If1"), types)
        self.assertIn(("IMPLEMENTS", "If2"), types)

    def test_interface_extends_multiple(self):
        h = "public interface IX extends A, B {"
        got = _java_tier1_rel_candidates(11, h)
        types = {(x["rel_type"], x["target_name"]) for x in got}
        self.assertIn(("INHERITS", "A"), types)
        self.assertIn(("INHERITS", "B"), types)
        self.assertNotIn("IMPLEMENTS", {x[0] for x in types})

    def test_enum_implements_only(self):
        h = "public enum Color implements Runnable {"
        got = _java_tier1_rel_candidates(10, h)
        self.assertEqual(
            got,
            [{"rel_type": "IMPLEMENTS", "target_name": "Runnable"}],
        )

    def test_extract_java_type_header_multiline(self):
        lines = [
            "package x;",
            "public class Foo",
            "    extends Bar implements Baz {",
        ]
        self.assertIn("extends Bar", _extract_java_type_header(lines, 2))


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

            result = crawl_phase2_tier1(nodes, edges, fmap, ws, cid)
            self.assertIn("updates", result)
            self.assertIn("tier1_rel_candidates", result)
            by_id = {u["id"]: u for u in result["updates"]}
            self.assertIn("Class", by_id[class_id]["labels_to_add"])
            self.assertIn("Method", by_id[method_id]["labels_to_add"])
            self.assertEqual(by_id[method_id]["properties"].get("parameter_types"), ["int"])
            self.assertEqual(result["tier1_rel_candidates"], [])

    def test_crawl_emits_inherits_implements_candidates(self):
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            java = tmp_path / "Demo.java"
            java.write_text(
                "package x;\n"
                "public class Child extends Parent implements If1 { }\n",
                encoding="utf-8",
            )
            ws = str(tmp_path)
            cid = "cb-test"
            rel = "Demo.java"
            child_id = f"{cid}:{rel}:2:Child"
            parent_id = f"{cid}:{rel}:9:Parent"
            iface_id = f"{cid}:{rel}:9:If1"
            nodes = [
                {
                    "id": child_id,
                    "codebase_id": cid,
                    "name": "Child",
                    "labels": ["CodeNode"],
                    "language": "java",
                    "path": rel,
                    "kind": 5,
                    "detail": "",
                    "signature": "",
                    "start_line": 2,
                    "end_line": 2,
                },
                {
                    "id": parent_id,
                    "codebase_id": cid,
                    "name": "Parent",
                    "labels": ["CodeNode"],
                    "language": "java",
                    "path": rel,
                    "kind": 5,
                    "detail": "",
                    "signature": "",
                    "start_line": 9,
                    "end_line": 9,
                },
                {
                    "id": iface_id,
                    "codebase_id": cid,
                    "name": "If1",
                    "labels": ["CodeNode"],
                    "language": "java",
                    "path": rel,
                    "kind": 11,
                    "detail": "",
                    "signature": "",
                    "start_line": 9,
                    "end_line": 9,
                },
            ]
            edges = []
            batch = [(rel, "hash", java.read_bytes())]
            fmap = build_file_contents_from_batch(ws, batch)
            result = crawl_phase2_tier1(nodes, edges, fmap, ws, cid)
            cands = result["tier1_rel_candidates"]
            by_from = [c for c in cands if c["from_id"] == child_id]
            rels = {(c["rel_type"], c["target_name"]) for c in by_from}
            self.assertIn(("INHERITS", "Parent"), rels)
            self.assertIn(("IMPLEMENTS", "If1"), rels)


class TestGraphWriterTier1Relationships(unittest.TestCase):
    def test_apply_phase2_tier1_relationships_merges_edges(self):
        class FakeResult:
            def __init__(self, rows):
                self._rows = rows

            def __iter__(self):
                return iter(self._rows)

        merged = {"inherits": None, "implements": None}

        def fake_run(query: str, **kwargs):
            q = query.strip()
            if "UNWIND $names AS name" in q:
                return FakeResult(
                    [
                        {"name": "Parent", "ids": ["p1"]},
                        {"name": "If1", "ids": ["i1"]},
                    ]
                )
            if "[:INHERITS]" in q:
                merged["inherits"] = list(kwargs.get("pairs") or [])
                return FakeResult([])
            if "[:IMPLEMENTS]" in q:
                merged["implements"] = list(kwargs.get("pairs") or [])
                return FakeResult([])
            return FakeResult([])

        session = MagicMock()
        session.run.side_effect = fake_run
        cm = MagicMock()
        cm.__enter__.return_value = session
        cm.__exit__.return_value = None

        gw = object.__new__(GraphWriter)
        gw.driver = MagicMock()
        gw.driver.session.return_value = cm

        candidates = [
            {"from_id": "c1", "target_name": "Parent", "rel_type": "INHERITS"},
            {"from_id": "c1", "target_name": "If1", "rel_type": "IMPLEMENTS"},
            {"from_id": "c1", "target_name": "Missing", "rel_type": "INHERITS"},
        ]
        gw.apply_phase2_tier1_relationships(candidates, "cb1")

        self.assertEqual(merged["inherits"], [{"from_id": "c1", "to_id": "p1"}])
        self.assertEqual(merged["implements"], [{"from_id": "c1", "to_id": "i1"}])


if __name__ == "__main__":
    unittest.main()
