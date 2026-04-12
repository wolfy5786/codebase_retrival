"""Tests for LSP-based field type resolution (Option B)."""
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.lsp.field_type_from_lsp import (
    _JAVA_LEADING_MODIFIERS,
    extract_type_before_field_name,
    parse_type_from_hover,
    type_name_from_definition_location,
)


class TestExtractTypeBeforeFieldName(unittest.TestCase):
    def test_java_simple(self):
        t = extract_type_before_field_name(
            "private final MyService svc", "svc", _JAVA_LEADING_MODIFIERS
        )
        self.assertEqual(t, "MyService")

    def test_java_generics(self):
        t = extract_type_before_field_name(
            "private java.util.List<String> items", "items", _JAVA_LEADING_MODIFIERS
        )
        self.assertEqual(t, "java.util.List<String>")


class TestParseTypeFromHover(unittest.TestCase):
    def test_multiline_hover(self):
        text = "private com.example.Foo bar\n\nSome javadoc here."
        t = parse_type_from_hover(text, "bar", "java")
        self.assertEqual(t, "com.example.Foo")


class TestTypeNameFromUri(unittest.TestCase):
    def test_stem(self):
        self.assertEqual(
            type_name_from_definition_location(
                {"uri": "file:///C:/proj/src/main/java/foo/Bar.java"}
            ),
            "Bar",
        )


if __name__ == "__main__":
    unittest.main()
