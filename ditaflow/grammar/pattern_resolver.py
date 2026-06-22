"""Resolves a MergedGrammar's raw RELAX NG define table into the DITA-facing
content-model AST (content_model_ast.py).

Cycle-handling strategy, decisively: memoized resolution by name with an
in-progress-set sentinel, not lazy thunks. DITA content-model cycles are
real (e.g. `section.content` can reach `fig.content` which can eventually
reach back toward phrase/block content) but every such cycle passes through
at least one `<element>` boundary -- you can't have `section.content`
directly contain `section.content` without an intervening concrete
`<element name="...">` first, and DITA-OT's grammars are well-formed RELAX
NG (no unguarded left-recursion through pure `<ref>` chains with no
intervening element). `_resolve_raw`'s `RngElement` case is itself the
natural cycle-breaker: it returns `ElementRef(tag_name)` and deliberately
does not recurse into resolving that element's own `.content` pattern --
that's a separate top-level `resolve()` call, not embedded inline. So the
in-progress guard only ever needs to protect against pattern-only cycles
that never cross an element boundary; a `RecursionMarker` returned for
those is correct and final, because the outer call already on the stack
resolves the real value, and that's what ends up cached.
"""

from __future__ import annotations

from ditaflow.grammar.content_model_ast import (
    Choice,
    ContentNode,
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
from ditaflow.grammar.content_model_ast import ElementRef as ResolvedElementRef
from ditaflow.grammar.rng_ast import (
    RngAttribute,
    RngChoice,
    RngElement,
    RngEmpty,
    RngExternal,
    RngGroup,
    RngInterleave,
    RngOneOrMore,
    RngOptional,
    RngPattern,
    RngRef,
    RngText,
    RngZeroOrMore,
)
from ditaflow.grammar.rng_loader import MergedGrammar


class PatternResolver:
    def __init__(self, grammar: MergedGrammar) -> None:
        self._grammar = grammar
        self._cache: dict[str, ContentNode] = {}
        self._in_progress: set[str] = set()

    def resolve(self, define_name: str) -> ContentNode:
        if define_name in self._cache:
            return self._cache[define_name]
        if define_name in self._in_progress:
            return RecursionMarker(pattern_name=define_name)
        self._in_progress.add(define_name)
        try:
            raw = self._grammar.defines.get(define_name)
            if raw is None:
                node: ContentNode = ForeignAny(namespace_hint=define_name)
            else:
                resolved = self._resolve_raw(raw.pattern)
                # A name whose merged define came from combine="choice"/
                # "interleave" across 2+ contributions is, by construction,
                # an extension point (DITA's domain-extension mechanism) --
                # tag it so downstream consumers (ProseMirror export, JSON
                # export) can treat it as one named group instead of an
                # enumerated literal choice. See module docstring of
                # element_registry.py for why this signal alone is enough
                # (no separate file-provenance bookkeeping needed).
                node = (
                    ExtensionPointRef(name=define_name, expansion=resolved)
                    if raw.combine is not None
                    else resolved
                )
        finally:
            self._in_progress.discard(define_name)
        self._cache[define_name] = node
        return node

    def _resolve_raw(self, pattern: RngPattern) -> ContentNode:
        if isinstance(pattern, RngRef):
            return self.resolve(pattern.name)
        if isinstance(pattern, RngElement):
            return ResolvedElementRef(element_name=pattern.tag_name)
        if isinstance(pattern, RngAttribute):
            # Attributes aren't content -- callers walking a `.content`
            # pattern never see these (attlist patterns are resolved
            # separately, see element_registry.py), but a defensive Empty
            # keeps this function total over every RngPattern variant.
            return Empty()
        if isinstance(pattern, RngGroup):
            return Sequence(tuple(self._resolve_raw(c) for c in pattern.children))
        if isinstance(pattern, RngChoice):
            return Choice(tuple(self._resolve_raw(c) for c in pattern.children))
        if isinstance(pattern, RngInterleave):
            return Interleave(tuple(self._resolve_raw(c) for c in pattern.children))
        if isinstance(pattern, RngOptional):
            return Optional(self._resolve_raw(pattern.child))
        if isinstance(pattern, RngZeroOrMore):
            return ZeroOrMore(self._resolve_raw(pattern.child))
        if isinstance(pattern, RngOneOrMore):
            return OneOrMore(self._resolve_raw(pattern.child))
        if isinstance(pattern, RngText):
            return TextRef()
        if isinstance(pattern, RngEmpty):
            return Empty()
        if isinstance(pattern, RngExternal):
            return ForeignAny(namespace_hint=pattern.href)
        raise TypeError(f"unresolvable RngPattern variant: {type(pattern).__name__}")
