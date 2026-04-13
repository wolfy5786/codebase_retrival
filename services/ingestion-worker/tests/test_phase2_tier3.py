"""Unit tests for Phase 2 Tier 3 helpers and crawl (mocked LSP / Neo4j)."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.crawl.phase2_tier3 import (
    crawl_phase2_tier3,
    is_java_primitive_type,
    lsp_range_start_line_1based,
    lsp_uri_to_repo_rel,
    match_stored_path,
)
from src.graph_writer import GraphWriter
from src.lsp.field_type_from_lsp import definition_result_to_uri


class TestJavaPrimitive(unittest.TestCase):
    def test_int_primitive(self):
        self.assertTrue(is_java_primitive_type("int"))
        self.assertFalse(is_java_primitive_type("java.lang.Integer"))

    def test_reference_string(self):
        self.assertFalse(is_java_primitive_type("java.lang.String"))
        self.assertFalse(is_java_primitive_type("String"))


class TestPathHelpers(unittest.TestCase):
    def test_match_stored_exact(self):
        self.assertEqual(match_stored_path("a/B.java", {"a/B.java"}), "a/B.java")

    def test_lsp_uri_to_repo_rel(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            f = root / "pkg" / "X.java"
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("//", encoding="utf-8")
            uri = f.as_uri()
            got = lsp_uri_to_repo_rel(uri, str(root))
            self.assertEqual(got, "pkg/X.java")

    def test_definition_uri_location(self):
        u = definition_result_to_uri(
            {"uri": "file:///C:/proj/src/Foo.java", "range": {}}
        )
        self.assertIn("Foo.java", u or "")


class TestLspRange(unittest.TestCase):
    def test_line_1based(self):
        self.assertEqual(
            lsp_range_start_line_1based({"start": {"line": 4, "character": 0}}),
            5,
        )


class TestCrawlPhase2Tier3Mocked(unittest.TestCase):
    def test_calls_and_definition_merged(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        workspace_root = str(Path(tmp.name).resolve())
        cid = "cb1"
        rel = "src/A.java"
        mid = f"{cid}:{rel}:5:foo"
        tid = f"{cid}:{rel}:8:bar"
        abs_rel = Path(workspace_root) / rel
        abs_rel.parent.mkdir(parents=True, exist_ok=True)

        nodes = [
            {
                "id": mid,
                "codebase_id": cid,
                "name": "foo",
                "labels": ["CodeNode", "Method"],
                "language": "java",
                "path": rel,
                "kind": 6,
                "start_line": 5,
                "end_line": 10,
            },
            {
                "id": tid,
                "codebase_id": cid,
                "name": "bar",
                "labels": ["CodeNode", "Method"],
                "language": "java",
                "path": rel,
                "kind": 6,
                "start_line": 8,
                "end_line": 15,
            },
        ]
        edges: list = []

        client = MagicMock()
        file_uri = abs_rel.as_uri()
        client.definition.return_value = {
            "uri": file_uri,
            "range": {"start": {"line": 4, "character": 0}},
        }
        client.call_hierarchy_prepare.return_value = [
            {"name": "foo", "uri": file_uri, "range": {}}
        ]
        to_uri = file_uri
        client.call_hierarchy_outgoing.return_value = [
            {
                "to": {
                    "name": "bar",
                    "uri": to_uri,
                    "selectionRange": {
                        "start": {"line": 7, "character": 4},
                        "end": {"line": 7, "character": 7},
                    },
                },
                "fromRanges": [{"start": {"line": 4, "character": 0}}],
            }
        ]
        client.document_highlight.return_value = []

        gw = MagicMock()
        gw.find_code_node_ids_covering_line.return_value = [tid]
        gw.find_enclosing_callable_id.return_value = None

        from src.crawl.phase2 import file_key_for_node

        fmap = {file_key_for_node(workspace_root, rel): "class A { void foo(){} void bar(){} }"}

        out = crawl_phase2_tier3(
            client,
            gw,
            nodes,
            edges,
            fmap,
            workspace_root,
            cid,
        )

        self.assertTrue(any("definition_uri" in (u.get("properties") or {}) for u in out["updates"]))
        self.assertEqual(len(out["calls_edges"]), 1)
        self.assertEqual(out["calls_edges"][0]["from_id"], mid)
        self.assertEqual(out["calls_edges"][0]["to_id"], tid)


class TestSetsGetsFromHighlights(unittest.TestCase):
    def test_sets_and_gets_edges(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        workspace_root = str(Path(tmp.name).resolve())
        cid = "cb1"
        rel = "src/A.java"
        field_id = f"{cid}:{rel}:4:count"
        getter_id = f"{cid}:{rel}:6:getCount"

        nodes = [
            {
                "id": field_id,
                "codebase_id": cid,
                "name": "count",
                "labels": ["CodeNode", "Attribute"],
                "language": "java",
                "path": rel,
                "kind": 8,
                "start_line": 4,
                "end_line": 4,
            },
            {
                "id": getter_id,
                "codebase_id": cid,
                "name": "getCount",
                "labels": ["CodeNode", "Method"],
                "language": "java",
                "path": rel,
                "kind": 6,
                "start_line": 6,
                "end_line": 8,
            },
        ]
        edges = []

        client = MagicMock()
        client.definition.return_value = None
        client.call_hierarchy_prepare.return_value = []
        client.call_hierarchy_outgoing.return_value = []
        client.document_highlight.return_value = [
            {"range": {"start": {"line": 6, "character": 10}}, "kind": 2},
            {"range": {"start": {"line": 7, "character": 4}}, "kind": 3},
        ]

        gw = MagicMock()
        gw.find_enclosing_callable_id.side_effect = lambda c, p, line: (
            getter_id if line in (7, 8) else None
        )

        from src.crawl.phase2 import file_key_for_node

        fmap = {file_key_for_node(workspace_root, rel): "..."}

        out = crawl_phase2_tier3(
            client, gw, nodes, edges, fmap, workspace_root, cid
        )
        self.assertTrue(len(out["gets_edges"]) >= 1 or len(out["sets_edges"]) >= 1)


class TestGraphWriterTier3Relationships(unittest.TestCase):
    def test_apply_tier3_relationships_runs_cypher(self):
        calls_merged = []

        def fake_run(query: str, **kwargs):
            q = query.strip()
            if ":CALLS" in q:
                calls_merged.append(list(kwargs.get("pairs") or []))
            return MagicMock(single=lambda: None)

        session = MagicMock()
        session.run.side_effect = fake_run
        cm = MagicMock()
        cm.__enter__.return_value = session
        cm.__exit__.return_value = None

        gw = object.__new__(GraphWriter)
        gw.driver = MagicMock()
        gw.driver.session.return_value = cm

        gw.apply_phase2_tier3_relationships(
            [{"from_id": "a", "to_id": "b", "line": 1, "column": 0}],
            [],
            [],
            "c1",
        )

        self.assertEqual(len(calls_merged), 1)
        self.assertEqual(calls_merged[0][0]["from_id"], "a")


if __name__ == "__main__":
    unittest.main()
