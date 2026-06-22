"""Unit tests for prosemirror_export.py.

Tier 1 (synthetic): every ContentNode variant, including Interleave, which
-- confirmed by grepping the full vendored grammar set -- never actually
occurs in a real DITA `.content` resolution (combine="interleave" is only
ever used for attlist/attribute merging in practice), so it has no real-
grammar test home and must be covered synthetically here.

Tier 2 (real grammar): representative element content expressions, plus
`svg-container`, the one element across all 18 vendored shells whose
content resolution actually reaches a ForeignAny leaf (svgDomain.rng's
`<externalRef>`) and therefore the only real is_approximate=True case in
the entire vendored set (confirmed by scanning every shell while building
this module).
"""

from __future__ import annotations

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
from ditaflow.grammar.element_registry import get_registry
from ditaflow.grammar.prosemirror_export import to_content_expression


class TestSyntheticTier1:
    def test_element_ref(self):
        assert to_content_expression(ElementRef("cmd")).expression == "cmd"

    def test_extension_point_collapses_to_its_own_name(self):
        pm = to_content_expression(
            ExtensionPointRef(name="ph", expansion=Choice((ElementRef("b"), ElementRef("i"))))
        )
        assert pm.expression == "ph"
        assert pm.is_approximate is False

    def test_text_and_empty(self):
        assert to_content_expression(TextRef()).expression == "text"
        assert to_content_expression(Empty()).expression == ""

    def test_sequence_of_single_child_is_unwrapped(self):
        assert to_content_expression(Sequence((ElementRef("a"),))).expression == "a"

    def test_sequence_of_multiple_children_is_space_joined_unparenthesized(self):
        pm = to_content_expression(Sequence((ElementRef("a"), ElementRef("b"))))
        assert pm.expression == "a b"

    def test_choice_of_single_child_is_unwrapped(self):
        assert to_content_expression(Choice((ElementRef("a"),))).expression == "a"

    def test_choice_of_multiple_children_is_parenthesized(self):
        pm = to_content_expression(Choice((ElementRef("a"), ElementRef("b"))))
        assert pm.expression == "(a | b)"

    def test_optional_of_atomic_child_has_no_parens(self):
        assert to_content_expression(Optional(ElementRef("a"))).expression == "a?"

    def test_zero_or_more_of_sequence_is_parenthesized_before_suffix(self):
        pm = to_content_expression(ZeroOrMore(Sequence((ElementRef("a"), ElementRef("b")))))
        assert pm.expression == "(a b)*"

    def test_one_or_more_of_choice_is_parenthesized_before_suffix(self):
        pm = to_content_expression(OneOrMore(Choice((ElementRef("a"), ElementRef("b")))))
        assert pm.expression == "(a | b)+"

    def test_quantifier_over_extension_point_has_no_redundant_parens(self):
        # A single extension-point token is already atomic -- "ph*", not
        # "(ph)*" -- exactly like a plain element-name token.
        pm = to_content_expression(ZeroOrMore(ExtensionPointRef(name="ph", expansion=Empty())))
        assert pm.expression == "ph*"

    def test_interleave_degrades_to_flagged_permissive_choice_star(self):
        pm = to_content_expression(Interleave((ElementRef("a"), ElementRef("b"))))
        assert pm.expression == "(a | b)*"
        assert pm.is_approximate is True
        assert len(pm.notes) == 1
        assert "interleave" in pm.notes[0].lower()

    def test_foreign_any_renders_empty_but_flags_approximate(self):
        pm = to_content_expression(ForeignAny(namespace_hint="svg.rng"))
        assert pm.expression == ""
        assert pm.is_approximate is True
        assert "svg.rng" in pm.notes[0]

    def test_recursion_marker_renders_empty_but_flags_approximate(self):
        pm = to_content_expression(RecursionMarker(pattern_name="a"))
        assert pm.expression == ""
        assert pm.is_approximate is True

    def test_approximate_flag_and_notes_propagate_up_through_containers(self):
        pm = to_content_expression(
            Sequence((ElementRef("a"), Optional(ForeignAny(namespace_hint="x"))))
        )
        assert pm.expression == "a"  # the foreign leaf contributes no token
        assert pm.is_approximate is True
        assert len(pm.notes) == 1


class TestRealGrammarTier2:
    def test_step_content_uses_extension_point_token_and_literal_choice(self):
        step = get_registry("task").get_element_info("step")
        pm = to_content_expression(step.content)
        assert pm.expression == (
            "note* cmd (choices | choicetable | info | itemgroup | stepxmp | substeps | "
            "tutorialinfo)* stepresult? steptroubleshooting?"
        )
        assert pm.is_approximate is False

    def test_steps_content_wraps_sequence_before_plus(self):
        steps = get_registry("task").get_element_info("steps")
        pm = to_content_expression(steps.content)
        assert pm.expression == "(data | data-about)* (stepsection? step)+"

    def test_svg_container_is_the_one_real_approximate_element(self):
        info = get_registry("topic").get_element_info("svg-container")
        pm = to_content_expression(info.content)
        assert pm.is_approximate is True
        assert "svg" in pm.notes[0].lower()
        # The real, nameable alternatives are still present in the
        # expression -- only the literal foreign SVG content is dropped.
        assert "svgref" in pm.expression

    def test_no_other_element_in_any_shell_is_approximate(self):
        from ditaflow.grammar.element_registry import SHELLS

        for doctype in SHELLS:
            registry = get_registry(doctype)
            approximate = [
                name
                for name, info in registry.elements.items()
                if name != "svg-container" and to_content_expression(info.content).is_approximate
            ]
            assert approximate == [], f"{doctype}: unexpected approximate elements: {approximate}"
