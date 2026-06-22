"""Unit tests for pattern_resolver.py -- raw RELAX NG pattern resolution
into the DITA-facing content-model AST, the extension-point tagging rule,
and the pattern-only-cycle guard. All synthetic (Tier 1): constructs
MergedGrammar/RawDefine values directly rather than parsing fixture files,
since the resolver's input is the already-merged define table, one layer
removed from rng_loader.py's own concerns (covered separately).
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
from ditaflow.grammar.pattern_resolver import PatternResolver
from ditaflow.grammar.rng_ast import (
    RawDefine,
    RngChoice,
    RngElement,
    RngEmpty,
    RngExternal,
    RngGroup,
    RngInterleave,
    RngOneOrMore,
    RngOptional,
    RngRef,
    RngText,
    RngZeroOrMore,
)
from ditaflow.grammar.rng_loader import MergedGrammar


def _grammar(defines: dict[str, RawDefine]) -> MergedGrammar:
    return MergedGrammar(doctype="synthetic", defines=defines, start=None, module_of_define={})


def test_resolves_element_to_element_ref_without_recursing_into_content():
    grammar = _grammar(
        {
            "x.element": RawDefine(
                name="x.element",
                pattern=RngElement(tag_name="x", child=RngEmpty()),
                combine=None,
                source_file="<test>",
            )
        }
    )
    resolved = PatternResolver(grammar).resolve("x.element")
    assert resolved == ElementRef(element_name="x")


def test_resolves_each_container_shape():
    grammar = _grammar(
        {
            "seq": RawDefine(
                name="seq",
                pattern=RngGroup((RngText(), RngEmpty())),
                combine=None,
                source_file="<test>",
            ),
            "choice": RawDefine(
                name="choice",
                pattern=RngChoice((RngText(), RngEmpty())),
                combine=None,
                source_file="<test>",
            ),
            "interleave": RawDefine(
                name="interleave",
                pattern=RngInterleave((RngText(), RngEmpty())),
                combine=None,
                source_file="<test>",
            ),
            "opt": RawDefine(
                name="opt", pattern=RngOptional(RngText()), combine=None, source_file="<test>"
            ),
            "star": RawDefine(
                name="star", pattern=RngZeroOrMore(RngText()), combine=None, source_file="<test>"
            ),
            "plus": RawDefine(
                name="plus", pattern=RngOneOrMore(RngText()), combine=None, source_file="<test>"
            ),
            "ext": RawDefine(
                name="ext", pattern=RngExternal(href="svg.rng"), combine=None, source_file="<test>"
            ),
        }
    )
    resolver = PatternResolver(grammar)
    assert resolver.resolve("seq") == Sequence((TextRef(), Empty()))
    assert resolver.resolve("choice") == Choice((TextRef(), Empty()))
    assert resolver.resolve("interleave") == Interleave((TextRef(), Empty()))
    assert resolver.resolve("opt") == Optional(TextRef())
    assert resolver.resolve("star") == ZeroOrMore(TextRef())
    assert resolver.resolve("plus") == OneOrMore(TextRef())
    assert resolver.resolve("ext") == ForeignAny(namespace_hint="svg.rng")


def test_ref_indirection_is_followed():
    grammar = _grammar(
        {
            "a": RawDefine(name="a", pattern=RngRef(name="b"), combine=None, source_file="<test>"),
            "b": RawDefine(name="b", pattern=RngText(), combine=None, source_file="<test>"),
        }
    )
    assert PatternResolver(grammar).resolve("a") == TextRef()


def test_unknown_define_name_becomes_foreign_any():
    resolver = PatternResolver(_grammar({}))
    assert resolver.resolve("nowhere") == ForeignAny(namespace_hint="nowhere")


def test_combine_not_none_wraps_in_extension_point_ref():
    grammar = _grammar(
        {
            "slot": RawDefine(
                name="slot",
                pattern=RngChoice((RngRef(name="x.element"), RngRef(name="y.element"))),
                combine="choice",
                source_file="<merged>",
            ),
            "x.element": RawDefine(
                name="x.element",
                pattern=RngElement(tag_name="x", child=RngEmpty()),
                combine=None,
                source_file="<test>",
            ),
            "y.element": RawDefine(
                name="y.element",
                pattern=RngElement(tag_name="y", child=RngEmpty()),
                combine=None,
                source_file="<test>",
            ),
        }
    )
    resolved = PatternResolver(grammar).resolve("slot")
    assert resolved == ExtensionPointRef(
        name="slot",
        expansion=Choice((ElementRef(element_name="x"), ElementRef(element_name="y"))),
    )


def test_memoization_returns_identical_object_on_second_call():
    grammar = _grammar(
        {"a": RawDefine(name="a", pattern=RngText(), combine=None, source_file="<test>")}
    )
    resolver = PatternResolver(grammar)
    first = resolver.resolve("a")
    second = resolver.resolve("a")
    assert first is second


def test_pattern_only_cycle_terminates_with_recursion_marker():
    # `a` and `b` refer to each other with no intervening <element> -- the
    # one case real DITA grammars never hit but the resolver must still
    # terminate on (see pattern_resolver.py's module docstring). The
    # real assertion here is "this returns at all" -- a previous bug here
    # would manifest as RecursionError/hang, not a wrong-value assertion.
    grammar = _grammar(
        {
            "a": RawDefine(name="a", pattern=RngRef(name="b"), combine=None, source_file="<test>"),
            "b": RawDefine(name="b", pattern=RngRef(name="a"), combine=None, source_file="<test>"),
        }
    )
    resolved = PatternResolver(grammar).resolve("a")
    assert isinstance(resolved, RecursionMarker)
