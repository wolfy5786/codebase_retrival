"""Unit tests for Phase 1 symbol → label mappers."""
import unittest
import sys
from pathlib import Path

# Package root: services/ingestion-worker/src
_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from extractor.base import BaseMapper
from extractor.languages.java.mapper import JavaMapper, _java_field_detail_is_reference_type
from extractor.languages.cpp.mapper import CppMapper, _cpp_field_detail_is_reference_type


class TestBaseMapper(unittest.TestCase):
    def test_namespace_and_package_map_to_module(self):
        m = BaseMapper()
        self.assertEqual(
            m.map_symbol_to_labels({"kind": 3, "name": "ns"}, None, None),
            ["Module", "Internal"],
        )
        self.assertEqual(
            m.map_symbol_to_labels({"kind": 4, "name": "pkg"}, None, None),
            ["Module", "Internal"],
        )

    def test_operator_maps_to_method(self):
        m = BaseMapper()
        self.assertEqual(
            m.map_symbol_to_labels({"kind": 25, "name": "operator+", "detail": ""}, None, None),
            ["CodeUnit", "Method"],
        )

    def test_destructor_heuristic(self):
        m = BaseMapper()
        labels = m.map_symbol_to_labels(
            {"kind": 6, "name": "~Foo", "detail": ""},
            None,
            None,
        )
        self.assertIn("Destructor", labels)
        self.assertIn("Method", labels)

    def test_python_field_no_object_from_base(self):
        """Base mapper never adds Object; Python uses BaseMapper."""
        m = BaseMapper()
        labels = m.map_symbol_to_labels(
            {"kind": 8, "name": "x", "detail": "SomeType"},
            "parent",
            ["Class", "Internal"],
        )
        self.assertIn("Attribute", labels)
        self.assertNotIn("Object", labels)


class TestJavaMapper(unittest.TestCase):
    def test_class_field_reference_gets_object_instance(self):
        j = JavaMapper()
        labels = j.map_symbol_to_labels(
            {"kind": 8, "name": "svc", "detail": "MyService"},
            "pid",
            ["Class", "Internal", "JavaClass"],
        )
        self.assertIn("Attribute", labels)
        self.assertIn("Object", labels)
        self.assertIn("Instance", labels)

    def test_class_field_primitive_no_object(self):
        j = JavaMapper()
        labels = j.map_symbol_to_labels(
            {"kind": 8, "name": "n", "detail": "int"},
            "pid",
            ["Class", "Internal"],
        )
        self.assertIn("Attribute", labels)
        self.assertNotIn("Object", labels)

    def test_field_at_file_scope_no_object(self):
        j = JavaMapper()
        labels = j.map_symbol_to_labels(
            {"kind": 8, "name": "x", "detail": "String"},
            "pid",
            ["Module", "File"],
        )
        self.assertNotIn("Object", labels)

    def test_interface_field_reference_gets_object(self):
        """Interface static fields: parent Interface is allowed for Object/Instance."""
        j = JavaMapper()
        labels = j.map_symbol_to_labels(
            {"kind": 8, "name": "NAME", "detail": "String"},
            "pid",
            ["Interface", "Internal", "JavaInterface"],
        )
        self.assertIn("Object", labels)
        self.assertIn("Instance", labels)

    def test_enum_member_reference_gets_object(self):
        """SymbolKind 22 EnumMember with reference type under Enum."""
        j = JavaMapper()
        labels = j.map_symbol_to_labels(
            {"kind": 22, "name": "ITEM", "detail": "MyType"},
            "pid",
            ["Enum", "Internal", "JavaEnum"],
        )
        self.assertIn("Attribute", labels)
        self.assertIn("Object", labels)


class TestCppMapper(unittest.TestCase):
    def test_class_field_std_string_gets_object(self):
        c = CppMapper()
        labels = c.map_symbol_to_labels(
            {"kind": 8, "name": "s", "detail": "std::string"},
            "pid",
            ["Class", "Internal"],
        )
        self.assertIn("Object", labels)

    def test_class_field_int_no_object(self):
        c = CppMapper()
        labels = c.map_symbol_to_labels(
            {"kind": 8, "name": "n", "detail": "int"},
            "pid",
            ["Class", "Internal"],
        )
        self.assertNotIn("Object", labels)

    def test_interface_field_reference_gets_object(self):
        c = CppMapper()
        labels = c.map_symbol_to_labels(
            {"kind": 8, "name": "p", "detail": "std::shared_ptr<Foo>"},
            "pid",
            ["Interface", "Internal"],
        )
        self.assertIn("Object", labels)

    def test_enum_member_reference_gets_object(self):
        c = CppMapper()
        labels = c.map_symbol_to_labels(
            {"kind": 22, "name": "A", "detail": "Bar"},
            "pid",
            ["Enum", "Internal"],
        )
        self.assertIn("Object", labels)


class TestDetailHeuristics(unittest.TestCase):
    def test_java_reference_detection(self):
        self.assertTrue(_java_field_detail_is_reference_type("String"))
        self.assertTrue(_java_field_detail_is_reference_type("java.util.List<String>"))
        self.assertFalse(_java_field_detail_is_reference_type("int"))
        self.assertFalse(_java_field_detail_is_reference_type("int[]"))

    def test_cpp_reference_detection(self):
        self.assertTrue(_cpp_field_detail_is_reference_type("std::string"))
        self.assertTrue(_cpp_field_detail_is_reference_type("Foo *"))
        self.assertFalse(_cpp_field_detail_is_reference_type("int"))
        self.assertFalse(_cpp_field_detail_is_reference_type("unsigned int"))


if __name__ == "__main__":
    unittest.main()
