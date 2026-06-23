"""Unit tests for json_export.py -- the tagged-union ContentNode encoding
and the overall per-element/registry dict shape that becomes xephon-cms's
planned dita-schema endpoint payload.
"""

from __future__ import annotations

import json

from ditaflow.grammar.content_model_ast import (
    Choice,
    ElementRef,
    Empty,
    ExtensionPointRef,
    ForeignAny,
    Interleave,
    OneOrMore,
    Optional,
    RecursionMarker,
    Sequence,
    TextRef,
    ZeroOrMore,
)
from ditaflow.grammar.element_registry import SHELLS, get_registry
from ditaflow.grammar.json_export import (
    content_node_to_json_dict,
    registry_to_json_dict,
    to_json_dict,
)


class TestContentNodeTaggedUnionTier1:
    def test_leaves(self):
        assert content_node_to_json_dict(ElementRef("cmd")) == {
            "type": "elementRef",
            "elementName": "cmd",
        }
        assert content_node_to_json_dict(TextRef()) == {"type": "text"}
        assert content_node_to_json_dict(Empty()) == {"type": "empty"}
        assert content_node_to_json_dict(ForeignAny(namespace_hint="svg.rng")) == {
            "type": "foreignAny",
            "namespaceHint": "svg.rng",
        }
        assert content_node_to_json_dict(RecursionMarker(pattern_name="a")) == {
            "type": "recursionMarker",
            "patternName": "a",
        }

    def test_containers(self):
        a, b = ElementRef("a"), ElementRef("b")
        assert content_node_to_json_dict(Sequence((a, b))) == {
            "type": "sequence",
            "children": [
                {"type": "elementRef", "elementName": "a"},
                {"type": "elementRef", "elementName": "b"},
            ],
        }
        assert content_node_to_json_dict(Choice((a, b)))["type"] == "choice"
        assert content_node_to_json_dict(Interleave((a, b)))["type"] == "interleave"
        assert content_node_to_json_dict(Optional(a)) == {
            "type": "optional",
            "child": {"type": "elementRef", "elementName": "a"},
        }
        assert content_node_to_json_dict(ZeroOrMore(a))["type"] == "zeroOrMore"
        assert content_node_to_json_dict(OneOrMore(a))["type"] == "oneOrMore"

    def test_extension_point_ref_nests_its_expansion(self):
        node = ExtensionPointRef(name="ph", expansion=Choice((ElementRef("b"), ElementRef("i"))))
        encoded = content_node_to_json_dict(node)
        assert encoded["type"] == "extensionPointRef"
        assert encoded["name"] == "ph"
        assert encoded["expansion"]["type"] == "choice"

    def test_every_variant_is_json_serializable(self):
        node = Sequence(
            (
                Choice((ElementRef("a"), ExtensionPointRef(name="ph", expansion=TextRef()))),
                Optional(Interleave((ElementRef("b"), ForeignAny(namespace_hint="x")))),
                ZeroOrMore(RecursionMarker(pattern_name="y")),
            )
        )
        json.dumps(content_node_to_json_dict(node))  # must not raise


class TestElementAndRegistryShapeTier1:
    def test_element_dict_has_expected_keys(self):
        registry = get_registry("topic")
        encoded = registry_to_json_dict(registry)
        b = encoded["elements"]["b"]
        assert b["elementName"] == "b"
        assert b["longName"] == "Bold"
        assert b["ditaClass"] == "+ topic/ph hi-d/b "
        assert b["baseElement"] == "ph"
        assert b["module"] == "hi-d"
        assert b["isInline"] is True
        assert "ph" in b["extensionPoints"]
        assert set(b["prosemirror"]) == {"expression", "isApproximate", "notes"}
        assert isinstance(b["content"], dict) and "type" in b["content"]

    def test_extension_points_are_sorted_lists_not_sets(self):
        encoded = registry_to_json_dict(get_registry("topic"))
        ph_members = encoded["extensionPoints"]["ph"]
        assert isinstance(ph_members, list)
        assert ph_members == sorted(ph_members)
        assert "b" in ph_members

    def test_top_level_shape(self):
        encoded = registry_to_json_dict(get_registry("topic"))
        assert set(encoded) == {"doctype", "elements", "extensionPoints"}
        assert encoded["doctype"] == "topic"


class TestRealGrammarTier2:
    def test_to_json_dict_matches_registry_to_json_dict(self):
        assert to_json_dict("map") == registry_to_json_dict(get_registry("map"))

    def test_every_shell_fully_round_trips_through_json(self):
        for doctype in SHELLS:
            blob = json.dumps(to_json_dict(doctype))
            assert json.loads(blob) == to_json_dict(doctype)

    def test_svg_container_foreign_any_survives_encoding(self):
        encoded = to_json_dict("topic")["elements"]["svg-container"]
        assert encoded["prosemirror"]["isApproximate"] is True
        # the ForeignAny leaf is reachable somewhere in the encoded tree
        assert "foreignAny" in json.dumps(encoded["content"])
