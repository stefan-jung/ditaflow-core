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


class TestInlineBlockFilterTier1:
    """prefer_inline/classify: unused by default (every test above is a
    no-op proof -- identical results to before this parameter pair
    existed), opt-in for a caller -- json_export.py -- that needs
    ProseMirror's inline-XOR-block content rule enforced on an otherwise-
    faithful rendering. See prosemirror_export.py's module docstring."""

    @staticmethod
    def _classify(name: str) -> bool:
        return name in {"ph", "keyword"}  # "image", "data" etc. classify as block

    def test_block_member_dropped_when_target_is_inline(self):
        pm = to_content_expression(
            Choice((ElementRef("ph"), ElementRef("image"))),
            prefer_inline=True,
            classify=self._classify,
        )
        assert pm.expression == "ph"
        assert pm.is_approximate is True
        assert "image" in pm.notes[0]

    def test_inline_member_dropped_when_target_is_block(self):
        pm = to_content_expression(
            Choice((ElementRef("ph"), ElementRef("image"))),
            prefer_inline=False,
            classify=self._classify,
        )
        assert pm.expression == "image"
        assert pm.is_approximate is True
        assert "ph" in pm.notes[0]

    def test_bare_text_dropped_when_target_is_block(self):
        pm = to_content_expression(
            Sequence((TextRef(), ElementRef("image"))),
            prefer_inline=False,
            classify=self._classify,
        )
        assert pm.expression == "image"
        assert pm.is_approximate is True

    def test_element_literally_named_text_is_dropped_like_textref_not_like_classify_says(self):
        # DITA has a real element tag-named "text" (see the Tier2 test
        # against "data" below). `classify_everything_as_block` says
        # *everything*, including "text", classifies as block -- so
        # without the override, "text" would (wrongly) be considered a
        # match against prefer_inline=False and survive. It must still be
        # dropped here, because the rendered *token* "text" is
        # indistinguishable from ProseMirror's own reserved inline text
        # node regardless of which DITA element produced it or what
        # classify() said about it.
        def classify_everything_as_block(name: str) -> bool:
            return False

        pm = to_content_expression(
            Sequence((ElementRef("text"), ElementRef("image"))),
            prefer_inline=False,
            classify=classify_everything_as_block,
        )
        assert pm.expression == "image"
        assert pm.is_approximate is True

    def test_extension_point_token_classified_same_as_a_literal_element(self):
        pm = to_content_expression(
            Choice((ExtensionPointRef(name="ph", expansion=Empty()), ElementRef("image"))),
            prefer_inline=True,
            classify=self._classify,
        )
        assert pm.expression == "ph"
        assert pm.is_approximate is True

    def test_no_mismatch_leaves_expression_exact_and_not_approximate(self):
        pm = to_content_expression(
            Sequence((ElementRef("ph"), ElementRef("keyword"))),
            prefer_inline=True,
            classify=self._classify,
        )
        assert pm.expression == "ph keyword"
        assert pm.is_approximate is False

    def test_all_members_mismatched_renders_empty_but_approximate(self):
        pm = to_content_expression(
            Choice((ElementRef("image"), ElementRef("object"))),
            prefer_inline=True,
            classify=self._classify,
        )
        assert pm.expression == ""
        assert pm.is_approximate is True
        assert len(pm.notes) == 2

    def test_extension_point_with_no_members_is_dropped_regardless_of_inline_block_match(self):
        # has_members is checked *before* classify -- an extension point
        # can be a real, valid RELAX NG combine point with zero members in
        # one particular doctype's grammar (see the real "glossentry-info-
        # types" case in Tier2 below); referencing it is a dangling token
        # no matter which inline/block category it would otherwise match.
        pm = to_content_expression(
            Sequence((ExtensionPointRef(name="empty-point", expansion=Empty()), ElementRef("ph"))),
            prefer_inline=True,
            classify=self._classify,
            has_members=lambda name: name != "empty-point",
        )
        assert pm.expression == "ph"
        assert pm.is_approximate is True

    def test_has_members_not_consulted_for_a_plain_element_ref(self):
        # has_members only makes sense for ExtensionPointRef (a *group*
        # that may or may not have members) -- a literal ElementRef always
        # refers to one concrete, real element, so even a has_members that
        # would say "no" for everything must not affect it.
        pm = to_content_expression(
            ElementRef("ph"),
            prefer_inline=True,
            classify=self._classify,
            has_members=lambda _: False,
        )
        assert pm.expression == "ph"
        assert pm.is_approximate is False


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

    def test_real_universal_carrier_element_mixes_inline_and_block_without_the_filter(self):
        # "data" is real-world proof the new filter parameters exist for a
        # reason, not a hypothetical: rendered with no filter (this
        # module's pre-existing, still-default behavior), its content
        # genuinely mixes inline (ph/keyword/...) and block (image/object/
        # title) members in one expression -- exactly the shape ProseMirror
        # itself cannot accept (confirmed: this is also the real "Unexpected
        # token"/"Mixing inline and block content" crash a live xephon-cms
        # editor hit before json_export.py started passing the filter).
        data = get_registry("topic").get_element_info("data")
        pm = to_content_expression(data.content)
        assert "ph" in pm.expression
        assert "image" in pm.expression

    def test_real_universal_carrier_element_with_the_filter_drops_the_mismatched_side(self):
        registry = get_registry("topic")
        data = registry.get_element_info("data")
        pm = to_content_expression(
            data.content, prefer_inline=data.is_inline, classify=registry.classify_inline
        )
        assert data.is_inline is False
        assert "image" in pm.expression  # block member kept (matches data's own is_inline)
        assert "ph" not in pm.expression  # inline member dropped
        assert pm.is_approximate is True

    def test_real_text_element_inside_data_does_not_survive_as_the_reserved_text_token(self):
        # "data"'s content nests a literal <text> ElementRef inside its
        # inline-phrase choice (see test_grammar_element_registry.py or
        # element_registry.py's docstring for why "text" isn't in
        # _KNOWN_INLINE_BASE_ELEMENTS -- it's a real, separate, block-
        # shaped element, not the AST's TextRef primitive). Before
        # `_filtered`'s "text" special-case, this slipped through
        # `classify_inline` as a block match and rendered as the bare
        # token "text" -- indistinguishable from ProseMirror's own
        # reserved inline text node and just as invalid in this block-
        # targeted expression as a literal inline element reference.
        import re

        registry = get_registry("topic")
        data = registry.get_element_info("data")
        assert registry.classify_inline("text") is False  # confirms the trap is real
        pm = to_content_expression(
            data.content, prefer_inline=data.is_inline, classify=registry.classify_inline
        )
        tokens = re.findall(r"[^\s()|?*+]+", pm.expression)
        assert "text" not in tokens
        assert "image" in tokens

    def test_filter_applied_uniformly_leaves_no_element_in_any_shell_mixing_inline_and_block(self):
        import re

        from ditaflow.grammar.element_registry import SHELLS

        token_re = re.compile(r"[^\s()|?*+]+")
        for doctype in SHELLS:
            registry = get_registry(doctype)
            for name, info in registry.elements.items():
                pm = to_content_expression(
                    info.content,
                    prefer_inline=info.is_inline,
                    classify=registry.classify_inline,
                    has_members=lambda n, r=registry: len(r.get_extension_point_members(n)) > 0,
                )
                tokens = token_re.findall(pm.expression)
                mismatched = [
                    token
                    for token in tokens
                    if token != "text"  # always inline, special-cased in production too
                    and registry.classify_inline(token) != info.is_inline
                ]
                assert mismatched == [], f"{doctype}/{name}: {mismatched} in {pm.expression!r}"
                # Every surviving token must resolve to *something*: either
                # a real element, or a group/extension-point with at least
                # one real member -- exactly json_export.py's real call
                # site, exercised against the full real registry rather
                # than a synthetic fixture.
                dangling = [
                    token
                    for token in tokens
                    if token != "text"
                    and token not in registry.elements
                    and len(registry.get_extension_point_members(token)) == 0
                ]
                assert dangling == [], f"{doctype}/{name}: {dangling} in {pm.expression!r}"

    def test_real_extension_point_with_no_members_in_this_doctype_is_dropped(self):
        # glossgroup's "glossentry-info-types" extension point is a real,
        # valid RELAX NG combine point -- just with zero concrete members
        # in this particular doctype's grammar (confirmed: the live
        # xephon-cms editor crashed constructing this doctype's schema
        # with "No node type or group 'glossentry-info-types' found"
        # before has_members existed).
        registry = get_registry("glossgroup")
        assert registry.get_extension_point_members("glossentry-info-types") == frozenset()
        glossentry = registry.get_element_info("glossentry")
        pm = to_content_expression(
            glossentry.content,
            prefer_inline=glossentry.is_inline,
            classify=registry.classify_inline,
            has_members=lambda n: len(registry.get_extension_point_members(n)) > 0,
        )
        assert "glossentry-info-types" not in pm.expression
        assert pm.is_approximate is True
