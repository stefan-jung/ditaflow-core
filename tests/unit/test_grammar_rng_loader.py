"""Unit tests for rng_loader.py -- combine merging, include-graph dedup,
and include-nested-define override. Tier 1 (synthetic fixtures) per
PROJECT plan; the real vendored grammars are exercised separately by
test_grammar_element_registry.py's Tier 2 assertions, since they're the
actual consumer-facing surface.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ditaflow.grammar.rng_ast import (
    GrammarError,
    RawDefine,
    RngAttribute,
    RngChoice,
    RngInterleave,
    RngOptional,
    RngRef,
)
from ditaflow.grammar.rng_loader import _merge_combine_group, load_shell

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "synthetic_rng"


def _load_synthetic():
    return load_shell(FIXTURES_DIR / "shell.rng", doctype="synthetic")


def test_dedup_by_resolved_path_across_two_includers():
    grammar = _load_synthetic()
    # shared.rng is included by both domain_a.rng and domain_b.rng; if it
    # were re-walked the second time, common.attlist's single contribution
    # would still look the same, but widget-info-types would be visited
    # twice -- harmless here since revisiting is a no-op, but the real
    # signal is that loading raised nothing and every shared.rng define
    # is present exactly once with a single, unmerged contribution.
    assert grammar.defines["common.attlist"].combine is None
    assert grammar.defines["common.attlist"].source_file.endswith("shared.rng")


def test_combine_choice_merges_two_file_contributions():
    grammar = _load_synthetic()
    widget = grammar.defines["widget"]
    assert widget.combine == "choice"
    assert widget.pattern == RngChoice(
        (RngRef(name="gadget.element"), RngRef(name="thingy.element"))
    )


def test_combine_interleave_merges_two_same_file_contributions():
    grammar = _load_synthetic()
    thingy_attlist = grammar.defines["thingy.attlist"]
    assert thingy_attlist.combine == "interleave"
    assert thingy_attlist.pattern == RngInterleave(
        (
            RngRef(name="common.attlist"),
            RngOptional(RngAttribute(attr_name="class", default_value="- base/thingy ")),
        )
    )


def test_include_nested_define_overrides_transitively_sourced_define():
    grammar = _load_synthetic()
    # widget-info-types originates in shared.rng as <ref name="widget"/>;
    # shell.rng's <include href="domain_b.rng"> carries a nested <define>
    # that must win regardless of shared.rng being reached transitively
    # via domain_a.rng/domain_b.rng rather than directly by shell.rng.
    assert grammar.defines["widget-info-types"].pattern == RngRef(name="gadget.element")
    assert grammar.defines["widget-info-types"].combine is None


def test_module_of_define_from_module_short_name():
    grammar = _load_synthetic()
    assert grammar.module_of_define["gadget.element"] == "widget-domain-a"
    # domain_b.rng declares no moduleDesc -- absence is fine, not an error.
    assert "thingy.element" not in grammar.module_of_define


def test_start_pattern_resolved():
    grammar = _load_synthetic()
    assert grammar.start == RngRef(name="widget")


def test_unknown_file_raises_on_missing_include(tmp_path):
    shell = tmp_path / "broken.rng"
    shell.write_text(
        '<grammar xmlns="http://relaxng.org/ns/structure/1.0">'
        '<include href="does-not-exist.rng"/>'
        "</grammar>"
    )
    with pytest.raises(OSError):
        load_shell(shell, doctype="broken")


class TestMergeCombineGroupConflicts:
    """_merge_combine_group is a pure function over RawDefine lists -- the
    genuine-conflict error paths are exercised directly rather than via
    fixture files, since fabricating a real grammar dependent only on
    fabricating a Python list is needless indirection.
    """

    def test_single_contribution_passes_through_unchanged(self):
        only = RawDefine(name="x", pattern=RngRef(name="y"), combine=None, source_file="a.rng")
        assert _merge_combine_group("x", [only]) is only

    def test_two_bare_contributions_is_a_conflict(self):
        bare1 = RawDefine(name="x", pattern=RngRef(name="a"), combine=None, source_file="a.rng")
        bare2 = RawDefine(name="x", pattern=RngRef(name="b"), combine=None, source_file="b.rng")
        with pytest.raises(GrammarError, match="no combine attribute"):
            _merge_combine_group("x", [bare1, bare2])

    def test_one_bare_plus_choice_contributions_is_allowed(self):
        # The RELAX NG DTD-compatibility convention, confirmed against the
        # real vendored grammars (e.g. commonElementsMod.rng's bare `data`
        # vs. utilitiesDomain.rng's combine="choice" extension of it).
        bare = RawDefine(name="x", pattern=RngRef(name="a"), combine=None, source_file="a.rng")
        choice = RawDefine(
            name="x", pattern=RngRef(name="b"), combine="choice", source_file="b.rng"
        )
        merged = _merge_combine_group("x", [bare, choice])
        assert merged.combine == "choice"
        assert merged.pattern == RngChoice((RngRef(name="a"), RngRef(name="b")))

    def test_conflicting_combine_values_is_an_error(self):
        choice = RawDefine(
            name="x", pattern=RngRef(name="a"), combine="choice", source_file="a.rng"
        )
        interleave = RawDefine(
            name="x", pattern=RngRef(name="b"), combine="interleave", source_file="b.rng"
        )
        with pytest.raises(GrammarError, match="conflicting combine"):
            _merge_combine_group("x", [choice, interleave])
