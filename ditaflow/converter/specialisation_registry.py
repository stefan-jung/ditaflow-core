"""Registry of known DITA elements and specializations.

Per spec/DITAFLOW-SPEC.md §1 and §8, this registry is *not* required for
correct round-tripping. An unregistered element still imports and exports
correctly via ``classChain`` and ``attrs._ext`` — registering it only adds
attribute validation and editor affordances (allowed children, inline-ness).
The parser and serializer must treat ``lookup()`` returning ``None`` as
"generic element", not as an error.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SpecialisationEntry:
    element_name: str
    dita_class: str
    base_element: str
    module: str
    allows_content: bool
    is_inline: bool
    allowed_children: tuple[str, ...] | None = None
    attrs_schema: dict[str, Any] | None = None


class SpecialisationRegistry:
    """Lookup table from DITA element name to its specialization metadata."""

    def __init__(self) -> None:
        self._entries: dict[str, SpecialisationEntry] = {}
        self._register_core_profile()

    def register(self, entry: SpecialisationEntry) -> None:
        self._entries[entry.element_name] = entry

    def lookup(self, element_name: str) -> SpecialisationEntry | None:
        return self._entries.get(element_name)

    def is_registered(self, element_name: str) -> bool:
        return element_name in self._entries

    def __contains__(self, element_name: str) -> bool:
        return self.is_registered(element_name)

    def _register_core_profile(self) -> None:
        for entry in _CORE_PROFILE:
            self.register(entry)


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
