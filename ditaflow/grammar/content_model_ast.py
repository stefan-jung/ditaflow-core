"""The DITA-facing content-model AST: what a merged RELAX NG define table
(rng_loader.MergedGrammar) resolves into. One level of element-content deep
per node -- resolving e.g. `section.content` gives a tree of `ElementRef`s
for `fig`, `p`, `note`, etc., not their own recursive expansion inline.
This matches how ProseMirror node specs themselves work (a `content:`
expression references other node names/groups, never inlines them), which
is exactly what this AST feeds (see prosemirror_export.py).
"""

from __future__ import annotations

from dataclasses import dataclass


class ContentNode:
    """Base class for resolved content-model AST nodes."""


@dataclass(frozen=True)
class Sequence(ContentNode):
    children: tuple[ContentNode, ...]


@dataclass(frozen=True)
class Choice(ContentNode):
    children: tuple[ContentNode, ...]


@dataclass(frozen=True)
class Interleave(ContentNode):
    children: tuple[ContentNode, ...]


@dataclass(frozen=True)
class Optional(ContentNode):
    child: ContentNode


@dataclass(frozen=True)
class ZeroOrMore(ContentNode):
    child: ContentNode


@dataclass(frozen=True)
class OneOrMore(ContentNode):
    child: ContentNode


@dataclass(frozen=True)
class ElementRef(ContentNode):
    """A leaf that, however many `<ref>` hops it took to resolve, denotes
    exactly one concrete `<element name="...">`.
    """

    element_name: str


@dataclass(frozen=True)
class ExtensionPointRef(ContentNode):
    """A leaf marking 'this position accepts any member of extension point
    `name`' -- DITA's domain-extension mechanism (e.g. `ph`, `keyword`)
    collapsed to a single named slot rather than an enumerated Choice.
    `expansion` keeps the full resolved pattern (a Choice/Interleave of
    ElementRefs) for callers that need it; most won't.
    """

    name: str
    expansion: ContentNode


@dataclass(frozen=True)
class TextRef(ContentNode):
    pass


@dataclass(frozen=True)
class Empty(ContentNode):
    pass


@dataclass(frozen=True)
class ForeignAny(ContentNode):
    """An `<externalRef>` leaf -- e.g. SVG. Opaque; never expanded further."""

    namespace_hint: str | None = None


@dataclass(frozen=True)
class RecursionMarker(ContentNode):
    """Cycle-truncation point for a pattern-only self-reference that never
    crosses an `<element>` boundary. See pattern_resolver.py's docstring
    for why this is rare and why it's always safe.
    """

    pattern_name: str
