"""Derives per-element metadata for every element a DITA doctype's grammar
declares -- the registry that becomes the *primary* source behind
``SpecialisationRegistry``, which keeps its hand-curated 83-element table
only as a last-ditch fallback (see that module's docstring).

Element discovery does not treat the "{tag}.element" naming convention as
load-bearing -- it's a DITA-OT authoring convention, not a RELAX NG
requirement. Instead, any merged define whose RAW pattern is *directly* an
``RngElement`` is a real element declaration: confirmed exhaustively true
for every sampled module/domain in the vendored grammars (base, hi-d,
task), and the only mechanism that doesn't silently miss an element should
some future module skip the convention.

Locating each element's ``.attlist``/``.content`` companions *does* use the
naming convention, because it's how DITA-OT's grammar generator has
written these refs for 20+ years and every sampled element confirms it
(``cmd.element`` -> ``<ref name="cmd.attlist"/><ref name="cmd.content"/>``,
same shape for ``b``/``keyword``/``p``/``image``/``data``). A missing
companion define degrades to "no attributes" / "no content" rather than
raising, since this module's job is best-effort metadata enrichment, not a
second grammar validator.

``class`` attribute default extraction (the source of ``dita_class``) needs
its own raw-pattern walk over the merged ``.attlist`` define -- *not* the
resolved content_model_ast, which deliberately collapses ``RngAttribute``
to ``Empty()`` (attributes aren't content). Confirmed against real data:
``taskMod.rng``'s ``cmd.attlist`` is ``combine="interleave"`` with two
contributions -- one bare ref to ``cmd.attributes`` (no class attribute at
all), the other a ``<ref name="global-atts"/>`` plus an
``<optional><attribute name="class" a:defaultValue="- topic/ph task/cmd "/>
</optional>``. So the default can sit behind ``RngInterleave``,
``RngOptional``, and an unrelated sibling ``RngRef`` that turns out to be a
dead end -- ``_find_class_default`` below walks the full container
vocabulary, plus ``RngRef`` indirection with a cycle guard, for exactly
this reason.

``long_name`` (a human-readable label, e.g. "uicontrol" -> "User
Interface Control") comes straight off the matched ``RngElement`` node
itself -- no extra walk needed, since rng_loader.py already reads it
(namespace-URI-aware: the same
http://dita.oasis-open.org/architecture/2005/ namespace shows up bound
to "dita"/"ditaarch"/"a" depending on the file). Confirmed present for
every element in every one of the 18 vendored shells; this is the
register's one piece of UI-facing data, included because hand-curating
labels for 557 elements would be exactly the kind of drift-prone
duplication this whole module exists to eliminate, and DITA-OT's own
grammar already carries the data for free.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import as_file, files

from ditaflow.converter.class_chain import base_type_from_class_string
from ditaflow.grammar.content_model_ast import (
    Choice,
    ContentNode,
    ElementRef,
    Empty,
    ExtensionPointRef,
    Interleave,
    OneOrMore,
    Optional,
    Sequence,
    ZeroOrMore,
)
from ditaflow.grammar.pattern_resolver import PatternResolver
from ditaflow.grammar.rng_ast import (
    RngAttribute,
    RngChoice,
    RngElement,
    RngGroup,
    RngInterleave,
    RngOneOrMore,
    RngOptional,
    RngPattern,
    RngRef,
    RngZeroOrMore,
)
from ditaflow.grammar.rng_loader import MergedGrammar, load_shell

_SCHEMA_ROOT = files("ditaflow") / "schemas" / "dita1.3"

# Mirrors relaxng_validator._SHELLS exactly (that one stays private and
# module-local; this one is public because specialisation_registry.py
# and json_export.py both have a genuine need to iterate real doctype
# keys, not just compile a schema). Duplicated rather than shared because
# the two modules are deliberately independent layers (this one derives a
# content/metadata registry; that one compiles a libxml2 validator) that
# happen to need the same input files -- not because the data should
# drift, so keep any doctype addition/removal in sync with that table.
SHELLS: dict[str, str] = {
    "topic": "technicalContent/rng/topic.rng",
    "concept": "technicalContent/rng/concept.rng",
    "task": "technicalContent/rng/generalTask.rng",
    "reference": "technicalContent/rng/reference.rng",
    "map": "technicalContent/rng/map.rng",
    "bookmap": "bookmap/rng/bookmap.rng",
    "glossentry": "technicalContent/rng/glossentry.rng",
    "glossgroup": "technicalContent/rng/glossgroup.rng",
    "troubleshooting": "technicalContent/rng/troubleshooting.rng",
    "learningContent": "learning/rng/learningContent.rng",
    "learningOverview": "learning/rng/learningOverview.rng",
    "learningAssessment": "learning/rng/learningAssessment.rng",
    "learningPlan": "learning/rng/learningPlan.rng",
    "learningSummary": "learning/rng/learningSummary.rng",
    "learningMap": "learning/rng/learningMap.rng",
    "learningGroupMap": "learning/rng/learningGroupMap.rng",
    "learningObjectMap": "learning/rng/learningObjectMap.rng",
    "learningBookmap": "learning/rng/learningBookmap.rng",
}

# RELAX NG has no "this is a phrase-level element" concept -- it only
# describes legal nesting -- so "is_inline" can't be a pure grammar fact.
# These are DITA's known inline *root* base types. Checked against each
# element's own `base_element` (the root of its classChain, already
# derived from the grammar's `class` attribute default), not against
# literal tag-name membership in some extension-point choice -- that
# would *under*-detect: `cmd` (classChain `- topic/ph task/cmd `) is
# clearly inline-shaped (phrase content, single required position) but is
# never wired into `ph`'s combine="choice" interchangeable-slot mechanism,
# because it has its own fixed position as `step`'s first child rather
# than being a drop-in `ph` substitute (confirmed real: `cmd` is absent
# from `get_extension_point_members("ph")`). Rooting the check in
# `base_element` instead catches `cmd`, `b`, `uicontrol`, and everything
# else specializing one of these base types uniformly, with no need to
# separately enumerate or transitively expand extension-point choices.
_KNOWN_INLINE_BASE_ELEMENTS = frozenset(
    {"ph", "keyword", "term", "xref", "cite", "fn", "indexterm", "q", "tm", "boolean", "state"}
)


@dataclass(frozen=True)
class ElementInfo:
    element_name: str
    dita_class: str | None
    base_element: str
    module: str | None
    is_inline: bool
    extension_points: frozenset[str]
    content: ContentNode
    long_name: str | None


@dataclass(frozen=True)
class GrammarRegistry:
    doctype: str
    elements: dict[str, ElementInfo]
    extension_points: dict[str, frozenset[str]]

    def get_element_info(self, element_name: str) -> ElementInfo | None:
        return self.elements.get(element_name)

    def get_extension_point_members(self, name: str) -> frozenset[str]:
        return self.extension_points.get(name, frozenset())

    def classify_inline(self, name: str) -> bool:
        """Classifies a content-model token -- an element name or an
        extension-point name -- as inline or block, for
        prosemirror_export.py's inline/block-mixing guard (see
        json_export.py, the only caller). An element name resolves via its
        own `is_inline`; anything else (an extension-point name, e.g.
        "ph") resolves via `_KNOWN_INLINE_BASE_ELEMENTS` directly, since an
        extension point's members all share its own base element's
        inline-ness by construction -- the same allowlist `is_inline`
        itself derives from.
        """
        element = self.elements.get(name)
        if element is not None:
            return element.is_inline
        return name in _KNOWN_INLINE_BASE_ELEMENTS


@lru_cache(maxsize=len(SHELLS))
def get_registry(doctype: str) -> GrammarRegistry:
    """Compiles (and, via lru_cache, permanently caches) the element
    registry for one doctype. Mirrors relaxng_validator._compiled_schema's
    caching rationale exactly: bounded, real work that must happen at most
    once per doctype per process, not once per document.
    """
    rel_path = SHELLS[doctype]  # KeyError on an unknown doctype is intentional
    resource = _SCHEMA_ROOT / rel_path
    with as_file(resource) as real_path:
        grammar = load_shell(real_path, doctype=doctype)
    return _build_registry(grammar)


def _build_registry(grammar: MergedGrammar) -> GrammarRegistry:
    resolver = PatternResolver(grammar)
    extension_points = _collect_extension_points(grammar, resolver)

    elements: dict[str, ElementInfo] = {}
    for define_name, raw in grammar.defines.items():
        if not isinstance(raw.pattern, RngElement):
            continue
        tag_name = raw.pattern.tag_name
        attlist_name = f"{tag_name}.attlist"
        content_name = f"{tag_name}.content"

        dita_class = (
            _find_class_default(grammar, attlist_name) if attlist_name in grammar.defines else None
        )
        base_element = base_type_from_class_string(dita_class) if dita_class else tag_name
        content = resolver.resolve(content_name) if content_name in grammar.defines else Empty()
        member_of = frozenset(
            ext_name for ext_name, members in extension_points.items() if tag_name in members
        )

        elements[tag_name] = ElementInfo(
            element_name=tag_name,
            dita_class=dita_class,
            base_element=base_element,
            module=grammar.module_of_define.get(define_name),
            is_inline=base_element in _KNOWN_INLINE_BASE_ELEMENTS,
            extension_points=member_of,
            content=content,
            long_name=raw.pattern.long_name,
        )

    return GrammarRegistry(
        doctype=grammar.doctype, elements=elements, extension_points=extension_points
    )


def _collect_extension_points(
    grammar: MergedGrammar, resolver: PatternResolver
) -> dict[str, frozenset[str]]:
    points: dict[str, frozenset[str]] = {}
    for name, raw in grammar.defines.items():
        if raw.combine is None:
            continue
        resolved = resolver.resolve(name)
        if not isinstance(resolved, ExtensionPointRef):
            continue  # unreachable: resolve() always wraps a combine!=None define this way
        points[name] = frozenset(_collect_member_names(resolved.expansion))
    return points


def _collect_member_names(node: ContentNode) -> set[str]:
    if isinstance(node, ElementRef):
        return {node.element_name}
    if isinstance(node, ExtensionPointRef):
        return _collect_member_names(node.expansion)
    if isinstance(node, (Sequence, Choice, Interleave)):
        names: set[str] = set()
        for child in node.children:
            names |= _collect_member_names(child)
        return names
    if isinstance(node, (Optional, ZeroOrMore, OneOrMore)):
        return _collect_member_names(node.child)
    return set()  # TextRef/Empty/ForeignAny/RecursionMarker: no element members


def _find_class_default(grammar: MergedGrammar, attlist_name: str) -> str | None:
    return _walk_for_class_default(grammar, grammar.defines[attlist_name].pattern, set())


def _walk_for_class_default(
    grammar: MergedGrammar, pattern: RngPattern, seen: set[str]
) -> str | None:
    if isinstance(pattern, RngAttribute):
        return pattern.default_value if pattern.attr_name == "class" else None
    if isinstance(pattern, RngRef):
        if pattern.name in seen:
            return None  # pattern-only cycle in a shared attribute fragment; not seen in practice
        seen.add(pattern.name)
        target = grammar.defines.get(pattern.name)
        return _walk_for_class_default(grammar, target.pattern, seen) if target else None
    if isinstance(pattern, (RngGroup, RngChoice, RngInterleave)):
        for child in pattern.children:
            found = _walk_for_class_default(grammar, child, seen)
            if found is not None:
                return found
        return None
    if isinstance(pattern, (RngOptional, RngZeroOrMore, RngOneOrMore)):
        return _walk_for_class_default(grammar, pattern.child, seen)
    return None  # RngElement/RngText/RngEmpty/RngExternal: no class attribute inside
