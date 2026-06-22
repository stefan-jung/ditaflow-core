"""Registry of known DITA elements and specializations.

Per spec/DITAFLOW-SPEC.md §1 and §8, this registry is *not* required for
correct round-tripping. An unregistered element still imports and exports
correctly via ``classChain`` and ``attrs._ext`` — registering it only adds
attribute validation and editor affordances (inline-ness). Content-model
("what can this contain") data lives separately in
``ditaflow.validator.content_model``, keyed by ``base_element`` rather
than ``element_name``, since DITA content models are defined once per
base structural type and specializations inherit them.
The parser and serializer must treat ``lookup()`` returning ``None`` as
"generic element", not as an error.

``lookup()``'s real source of data, in precedence order, is: (1) entries
``register()``-ed explicitly on this instance -- an intentional, caller-
driven override, always honored, never shadowed by anything below; (2)
``ditaflow.grammar.overrides``'s manual correction table, for the rare
documented exception; (3) ``ditaflow.grammar.element_registry``'s
grammar-derived registry, covering 557 elements across every vendored
domain (vs. this module's own ``_CORE_PROFILE``, 83 elements, prose +
highlight only) -- and, where they overlap, *more accurate*: e.g.
``keydef``'s real classChain is a ``mapgroup-d`` specialization of
``topicref``, not the bare base ``topicref`` ``_CORE_PROFILE`` claims, and
``image`` genuinely allows an optional ``alt``/``longdescref`` child, not
the empty content ``_CORE_PROFILE`` claims (confirmed against the real
grammar while building the grammar registry); (4) ``_CORE_PROFILE``
itself, kept as a last-ditch fallback for the case the grammar registry
is somehow unavailable, not deleted. Deliberately *not* preloaded into a
fresh instance's entries the way it used to be -- doing so would let
every stale hand-curated record permanently shadow the more-accurate
grammar registry for every element they overlap on, defeating the point
of grammar derivation.

The grammar registry is per-doctype
(``ditaflow.grammar.element_registry.get_registry(doctype)``), but
``lookup()`` here takes no doctype -- it tries every vendored shell, in
``element_registry.SHELLS``'s declared order, returning the first hit.
This is safe because a given element's grammar-derived metadata does not
vary by which shell happens to include it (the same domain `.rng` file
contributes the same `class` attribute default regardless of includer,
confirmed against real data), and cheap because ``get_registry`` is
process-lifetime cached per doctype -- a doctype shell is compiled at
most once per process, not once per lookup or per document, however many
of either there are.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ditaflow.grammar.content_model_ast import Empty
from ditaflow.grammar.element_registry import SHELLS, ElementInfo, get_registry
from ditaflow.grammar.overrides import lookup_override


@dataclass(frozen=True)
class SpecialisationEntry:
    element_name: str
    dita_class: str
    base_element: str
    module: str
    allows_content: bool
    is_inline: bool
    attrs_schema: dict[str, Any] | None = None


class SpecialisationRegistry:
    """Lookup table from DITA element name to its specialization metadata.

    See the module docstring for ``lookup()``'s full precedence chain.
    """

    def __init__(self) -> None:
        self._entries: dict[str, SpecialisationEntry] = {}

    def register(self, entry: SpecialisationEntry) -> None:
        self._entries[entry.element_name] = entry

    def lookup(self, element_name: str) -> SpecialisationEntry | None:
        if element_name in self._entries:
            return self._entries[element_name]
        override = lookup_override(element_name)
        if override is not None:
            return override
        from_grammar = _lookup_in_grammar_registry(element_name)
        if from_grammar is not None:
            return from_grammar
        return _CORE_PROFILE_BY_NAME.get(element_name)

    def is_registered(self, element_name: str) -> bool:
        return self.lookup(element_name) is not None

    def __contains__(self, element_name: str) -> bool:
        return self.is_registered(element_name)


def _lookup_in_grammar_registry(element_name: str) -> SpecialisationEntry | None:
    for doctype in SHELLS:
        info = get_registry(doctype).get_element_info(element_name)
        if info is None:
            continue
        entry = _element_info_to_specialisation_entry(info)
        if entry is not None:
            return entry
    return None


def _element_info_to_specialisation_entry(info: ElementInfo) -> SpecialisationEntry | None:
    if info.dita_class is None or info.module is None:
        return None
    return SpecialisationEntry(
        element_name=info.element_name,
        dita_class=info.dita_class,
        base_element=info.base_element,
        module=info.module,
        allows_content=info.content != Empty(),
        is_inline=info.is_inline,
    )


def _e(
    element_name: str,
    dita_class: str,
    base_element: str,
    module: str,
    *,
    allows_content: bool = True,
    is_inline: bool = False,
    attrs_schema: dict[str, Any] | None = None,
) -> SpecialisationEntry:
    return SpecialisationEntry(
        element_name=element_name,
        dita_class=dita_class,
        base_element=base_element,
        module=module,
        allows_content=allows_content,
        is_inline=is_inline,
        attrs_schema=attrs_schema,
    )


# Core profile: the base topic/map vocabulary plus the highlight domain,
# covering everything illustrated in spec/DITAFLOW-SPEC.md. This is
# intentionally not exhaustive of DITA — see module docstring.
_CORE_PROFILE: tuple[SpecialisationEntry, ...] = (
    # Topic family
    _e("topic", "- topic/topic ", "topic", "base"),
    _e("concept", "- topic/topic concept/concept ", "topic", "base"),
    _e("task", "- topic/topic task/task ", "topic", "base"),
    _e("reference", "- topic/topic reference/reference ", "topic", "base"),
    _e("title", "- topic/title ", "title", "base"),
    _e("shortdesc", "- topic/shortdesc ", "shortdesc", "base"),
    _e("abstract", "- topic/abstract ", "abstract", "base"),
    _e("prolog", "- topic/prolog ", "prolog", "base"),
    _e("body", "- topic/body ", "body", "base"),
    _e("conbody", "- topic/body concept/conbody ", "body", "base"),
    _e("taskbody", "- topic/body task/taskbody ", "body", "base"),
    _e("refbody", "- topic/body reference/refbody ", "body", "base"),
    _e("related-links", "- topic/related-links ", "related-links", "base"),
    _e("link", "- topic/link ", "link", "base"),
    # Block content
    _e("p", "- topic/p ", "p", "base"),
    _e("section", "- topic/section ", "section", "base"),
    _e("example", "- topic/example ", "example", "base"),
    _e("note", "- topic/note ", "note", "base"),
    _e("ol", "- topic/ol ", "ol", "base"),
    _e("ul", "- topic/ul ", "ul", "base"),
    _e("sl", "- topic/sl ", "sl", "base"),
    _e("li", "- topic/li ", "li", "base"),
    _e("sli", "- topic/sli ", "sli", "base"),
    _e("dl", "- topic/dl ", "dl", "base"),
    _e("dlentry", "- topic/dlentry ", "dlentry", "base"),
    _e("dt", "- topic/dt ", "dt", "base"),
    _e("dd", "- topic/dd ", "dd", "base"),
    _e("fig", "- topic/fig ", "fig", "base"),
    _e("image", "- topic/image ", "image", "base", allows_content=False),
    _e("codeblock", "- topic/codeblock ", "codeblock", "base"),
    _e("pre", "- topic/pre ", "pre", "base"),
    _e("lines", "- topic/lines ", "lines", "base"),
    _e("required-cleanup", "- topic/required-cleanup ", "required-cleanup", "base"),
    _e("data", "- topic/data ", "data", "base"),
    # Inline (block-incapable) elements
    _e("xref", "- topic/xref ", "xref", "base", is_inline=True),
    _e("keyword", "- topic/keyword ", "keyword", "base", is_inline=True),
    _e("term", "- topic/term ", "term", "base", is_inline=True),
    _e("cite", "- topic/cite ", "cite", "base", is_inline=True),
    _e("ph", "- topic/ph ", "ph", "base", is_inline=True),
    _e("fn", "- topic/fn ", "fn", "base", is_inline=True),
    _e("indexterm", "- topic/indexterm ", "indexterm", "base", is_inline=True),
    # Highlight domain — these collapse into marks per spec §4.1 when their
    # content is pure text; the registry entry covers the case where they
    # don't (e.g. <b><xref/></b>) and must stay generic element nodes.
    _e("b", "+ topic/ph hi-d/b ", "ph", "hi-d", is_inline=True),
    _e("i", "+ topic/ph hi-d/i ", "ph", "hi-d", is_inline=True),
    _e("u", "+ topic/ph hi-d/u ", "ph", "hi-d", is_inline=True),
    _e("sup", "+ topic/ph hi-d/sup ", "ph", "hi-d", is_inline=True),
    _e("sub", "+ topic/ph hi-d/sub ", "ph", "hi-d", is_inline=True),
    _e("tt", "+ topic/ph hi-d/tt ", "ph", "hi-d", is_inline=True),
    # Tables — CALS
    _e("table", "- topic/table ", "table", "base"),
    _e("tgroup", "- topic/tgroup ", "tgroup", "base"),
    _e("colspec", "- topic/colspec ", "colspec", "base", allows_content=False),
    _e("spanspec", "- topic/spanspec ", "spanspec", "base", allows_content=False),
    _e("thead", "- topic/thead ", "thead", "base"),
    _e("tbody", "- topic/tbody ", "tbody", "base"),
    _e("tfoot", "- topic/tfoot ", "tfoot", "base"),
    _e("row", "- topic/row ", "row", "base"),
    _e("entry", "- topic/entry ", "entry", "base"),
    # Tables — simple
    _e("simpletable", "- topic/simpletable ", "simpletable", "base"),
    _e("sthead", "- topic/sthead ", "sthead", "base"),
    _e("strow", "- topic/strow ", "strow", "base"),
    _e("stentry", "- topic/stentry ", "stentry", "base"),
    # Task specializations
    _e("steps", "- topic/ol task/steps ", "ol", "task"),
    _e("step", "- topic/li task/step ", "li", "task"),
    _e("cmd", "- topic/ph task/cmd ", "ph", "task", is_inline=True),
    _e("info", "- topic/itemgroup task/info ", "itemgroup", "task"),
    _e("stepresult", "- topic/itemgroup task/stepresult ", "itemgroup", "task"),
    _e("context", "- topic/section task/context ", "section", "task"),
    _e("prereq", "- topic/section task/prereq ", "section", "task"),
    _e("postreq", "- topic/section task/postreq ", "section", "task"),
    _e("result", "- topic/section task/result ", "section", "task"),
    # Map family
    _e("map", "- map/map ", "map", "base"),
    _e("bookmap", "- map/map bookmap/bookmap ", "map", "bookmap"),
    _e("topicref", "- map/topicref ", "topicref", "base"),
    _e("chapter", "- map/topicref bookmap/chapter ", "topicref", "bookmap"),
    _e("appendix", "- map/topicref bookmap/appendix ", "topicref", "bookmap"),
    _e("part", "- map/topicref bookmap/part ", "topicref", "bookmap"),
    _e("topicmeta", "- map/topicmeta ", "topicmeta", "base"),
    _e("keydef", "- map/topicref ", "topicref", "base"),
    _e("reltable", "- map/reltable ", "reltable", "base"),
    _e("relheader", "- map/relheader ", "relheader", "base"),
    _e("relcolspec", "- map/relcolspec ", "relcolspec", "base", allows_content=False),
    _e("relrow", "- map/relrow ", "relrow", "base"),
    _e("relcell", "- map/relcell ", "relcell", "base"),
    # Branch filtering
    _e("ditavalref", "- map/topicref ditavalref-d/ditavalref ", "topicref", "ditavalref-d"),
)

_CORE_PROFILE_BY_NAME: dict[str, SpecialisationEntry] = {e.element_name: e for e in _CORE_PROFILE}
