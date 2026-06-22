"""Unit tests for element_registry.py.

Tier 1 (synthetic, via tests/fixtures/synthetic_rng/shell.rng): exercises
class-default extraction through combine="interleave"/multi-child-group
attlists, extension-point member collection, and the two "missing
companion define" degradation paths.

Tier 2 (real vendored grammars, narrow/subset assertions, not a golden
snapshot): a handful of named elements across inline/block/table/map/task
categories, chosen because they were independently confirmed against the
raw .rng source while building this module (see element_registry.py's
docstring for the cmd.attlist trace this is grounded in).

Seam test: SpecialisationRegistry's hand-curated entries must agree with
the grammar-derived registry on dita_class/base_element/is_inline for
every element the hand-curated table happens to cover -- *not* on
`module`, which the hand-curated table only ever sets to the placeholder
"base" rather than a real per-file moduleShortName (a known, intentional
representational gap that grammar derivation now actually fixes, e.g.
`keydef`'s real class chain turns out to be a `mapgroup-d` specialization
of topicref, not the bare base topicref the hand-curated entry claims --
exactly the kind of drift this whole effort exists to eliminate).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ditaflow.converter.specialisation_registry import SpecialisationRegistry
from ditaflow.grammar.content_model_ast import Empty
from ditaflow.grammar.element_registry import SHELLS, _build_registry, get_registry
from ditaflow.grammar.rng_loader import load_shell

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "synthetic_rng"


@pytest.fixture(scope="module")
def synthetic_registry():
    grammar = load_shell(FIXTURES_DIR / "shell.rng", doctype="synthetic")
    return _build_registry(grammar)


class TestSyntheticTier1:
    def test_element_discovery_is_structural_not_name_based(self, synthetic_registry):
        # gadget/thingy are discovered via isinstance(pattern, RngElement),
        # not by string-matching a ".element" suffix in the define name.
        assert set(synthetic_registry.elements) == {"gadget", "thingy"}

    def test_class_default_found_through_single_contribution_group(self, synthetic_registry):
        gadget = synthetic_registry.get_element_info("gadget")
        assert gadget.dita_class == "- base/gadget "
        assert gadget.base_element == "gadget"
        assert gadget.module == "widget-domain-a"

    def test_class_default_found_through_interleaved_contributions(self, synthetic_registry):
        # thingy.attlist is combine="interleave" of two contributions; the
        # class default sits in the second one, behind <optional>, with
        # the first being a dead-end <ref> to a fragment with no class --
        # exactly the shape real taskMod.rng's cmd.attlist has.
        thingy = synthetic_registry.get_element_info("thingy")
        assert thingy.dita_class == "- base/thingy "
        assert thingy.base_element == "thingy"

    def test_extension_point_members_collected(self, synthetic_registry):
        assert synthetic_registry.extension_points["widget"] == frozenset({"gadget", "thingy"})
        assert synthetic_registry.get_extension_point_members("widget") == frozenset(
            {"gadget", "thingy"}
        )

    def test_element_records_its_own_extension_point_membership(self, synthetic_registry):
        assert synthetic_registry.get_element_info("gadget").extension_points == frozenset(
            {"widget"}
        )

    def test_missing_attlist_define_degrades_to_no_class(self):
        grammar = load_shell(FIXTURES_DIR / "shell.rng", doctype="synthetic")
        # Drop the attlist define entirely and rebuild, simulating an
        # element with no attributes at all.
        del grammar.defines["gadget.attlist"]
        registry = _build_registry(grammar)
        gadget = registry.get_element_info("gadget")
        assert gadget.dita_class is None
        assert gadget.base_element == "gadget"  # falls back to its own tag name

    def test_missing_content_define_degrades_to_empty(self):
        grammar = load_shell(FIXTURES_DIR / "shell.rng", doctype="synthetic")
        del grammar.defines["gadget.content"]
        registry = _build_registry(grammar)
        assert registry.get_element_info("gadget").content == Empty()

    def test_unregistered_element_name_returns_none(self, synthetic_registry):
        assert synthetic_registry.get_element_info("does-not-exist") is None
        assert synthetic_registry.get_extension_point_members("does-not-exist") == frozenset()


class TestRealGrammarTier2:
    def test_all_eighteen_shells_load_without_error(self):
        for doctype in SHELLS:
            registry = get_registry(doctype)
            assert len(registry.elements) > 0

    def test_highlight_domain_inline_specialization(self):
        b = get_registry("topic").get_element_info("b")
        assert b.dita_class == "+ topic/ph hi-d/b "
        assert b.base_element == "ph"
        assert b.module == "hi-d"
        assert b.is_inline is True

    def test_base_block_element_not_inline(self):
        p = get_registry("topic").get_element_info("p")
        assert p.dita_class == "- topic/p "
        assert p.base_element == "p"
        assert p.is_inline is False

    def test_ph_extension_point_covers_known_highlight_members(self):
        members = get_registry("topic").get_extension_point_members("ph")
        assert {"ph", "b", "i", "u", "tt", "sub", "sup", "uicontrol"} <= members

    def test_task_specialization_inline_via_base_element_not_extension_point(self):
        # cmd specializes ph (classChain-wise) but is never wired into
        # ph's combine="choice" extension slot -- it has its own fixed
        # position as the first child of <step>. is_inline must still be
        # True, derived from base_element rather than extension-point
        # membership (see element_registry.py's _KNOWN_INLINE_BASE_ELEMENTS
        # comment for why the naive approach under-detects this).
        registry = get_registry("task")
        cmd = registry.get_element_info("cmd")
        assert cmd.dita_class == "- topic/ph task/cmd "
        assert cmd.is_inline is True
        assert "cmd" not in registry.get_extension_point_members("ph")

    def test_task_list_specialization_not_inline(self):
        registry = get_registry("task")
        step = registry.get_element_info("step")
        assert step.dita_class == "- topic/li task/step "
        assert step.base_element == "li"
        assert step.is_inline is False

    def test_map_family_base_and_specialized_elements(self):
        registry = get_registry("map")
        topicref = registry.get_element_info("topicref")
        assert topicref.dita_class == "- map/topicref "
        keydef = registry.get_element_info("keydef")
        assert keydef.dita_class == "+ map/topicref mapgroup-d/keydef "
        assert keydef.base_element == "topicref"
        assert keydef.module == "mapgroup-d"

    def test_bookmap_structural_specialization(self):
        chapter = get_registry("bookmap").get_element_info("chapter")
        assert chapter.dita_class == "- map/topicref bookmap/chapter "
        assert chapter.base_element == "topicref"

    def test_every_discovered_element_has_a_class_default_in_practice(self):
        # Not a structural guarantee (a hypothetical attribute-less element
        # would legitimately have dita_class=None) -- but confirmed true
        # for every element in every one of the 18 real shells, so a
        # regression here is worth surfacing rather than silently passing.
        for doctype in SHELLS:
            registry = get_registry(doctype)
            missing = [name for name, info in registry.elements.items() if info.dita_class is None]
            assert missing == [], f"{doctype}: elements with no dita_class: {missing}"


# A handful of elements across categories, picked because the hand-curated
# SpecialisationRegistry's dita_class for each was independently confirmed
# against the real grammar while building this module. `keydef` is
# deliberately excluded -- see module docstring; it's a known, expected
# divergence, not something both sources should agree on.
_SEAM_TEST_ELEMENTS = ("b", "p", "xref", "table", "entry", "topicref", "step", "cmd", "chapter")


@pytest.mark.parametrize("element_name", _SEAM_TEST_ELEMENTS)
def test_specialisation_registry_agrees_with_grammar_registry(element_name):
    hand_curated = SpecialisationRegistry().lookup(element_name)
    assert hand_curated is not None, f"{element_name} missing from hand-curated registry"

    # bookmap/task-specific elements aren't in topic.rng's own shell.
    grammar_doctype = (
        "bookmap"
        if element_name == "chapter"
        else "task"
        if element_name in ("step", "cmd")
        else "map"
        if element_name == "topicref"
        else "topic"
    )
    from_grammar = get_registry(grammar_doctype).get_element_info(element_name)
    assert from_grammar is not None, f"{element_name} missing from grammar registry"

    assert hand_curated.dita_class == from_grammar.dita_class, element_name
    assert hand_curated.base_element == from_grammar.base_element, element_name
    assert hand_curated.is_inline == from_grammar.is_inline, element_name
