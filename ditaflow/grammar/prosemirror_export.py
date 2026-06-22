"""Renders a resolved content_model_ast.ContentNode into a ProseMirror
NodeSpec `content` expression string -- the literal syntax ProseMirror's
schema parser accepts (`"a b"` sequence, `"(a | b)"` choice, `a?`/`a*`/`a+`
quantifiers on a single token or a parenthesized group).

Token choice matches the precedent already established by xephon-cms's
hand-written node specs (frontend/src/editor/nodes/): an `ElementRef`
renders as the element's own tag name (e.g. "cmd"), and -- this is the
piece that scales that precedent from 1 hand-picked shared group ("li",
shared by `Li`/`Step` today) to every one of DITA's real domain-extension
points -- an `ExtensionPointRef` renders as the extension point's *name*
(e.g. "ph"), relying on every member element's own NodeSpec declaring
`group: "ph"` so ProseMirror resolves the reference the same way it
already resolves "li". This module only emits the token; it's Phase 3's
frontend job to put `group: name` on each member node consistently.

Not every ContentNode shape has a faithful ProseMirror equivalent:
`Interleave` (RNG's unordered-all-of-these-once) has no ProseMirror
analogue, and `ForeignAny`/`RecursionMarker` are deliberately opaque even
in the DITA-facing AST. All three degrade to a permissive approximation
(never silently wrong) and set `is_approximate=True` with a human-readable
note on the returned `ProseMirrorContent`, so callers can choose to fall
back to RelaxNgValidator as the authoritative gate for elements where the
live editor schema is only an approximation -- the same "approximate live
schema, authoritative async check" split already established by the
Export & Validate feature.
"""

from __future__ import annotations

from dataclasses import dataclass

from ditaflow.grammar.content_model_ast import (
    Choice,
    ContentNode,
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


@dataclass(frozen=True)
class ProseMirrorContent:
    expression: str
    is_approximate: bool
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class _Rendered:
    text: str
    # Whether `text` can take a `?`/`*`/`+` suffix directly, vs. needing
    # to be parenthesized first (a single token or an already-wrapped
    # group is atomic; a bare multi-token sequence/choice is not).
    is_atomic: bool
    is_approximate: bool
    notes: tuple[str, ...]


def to_content_expression(node: ContentNode) -> ProseMirrorContent:
    rendered = _render(node)
    return ProseMirrorContent(
        expression=rendered.text, is_approximate=rendered.is_approximate, notes=rendered.notes
    )


def _wrap_if_needed(rendered: _Rendered) -> str:
    return rendered.text if rendered.is_atomic else f"({rendered.text})"


def _render(node: ContentNode) -> _Rendered:
    if isinstance(node, ElementRef):
        return _Rendered(node.element_name, True, False, ())
    if isinstance(node, ExtensionPointRef):
        return _Rendered(node.name, True, False, ())
    if isinstance(node, TextRef):
        return _Rendered("text", True, False, ())
    if isinstance(node, Empty):
        return _Rendered("", True, False, ())
    if isinstance(node, Sequence):
        return _render_joined(node.children, " ", wrap_multi=False)
    if isinstance(node, Choice):
        return _render_joined(node.children, " | ", wrap_multi=True)
    if isinstance(node, Interleave):
        return _render_interleave(node)
    if isinstance(node, Optional):
        return _render_quantified(node.child, "?")
    if isinstance(node, ZeroOrMore):
        return _render_quantified(node.child, "*")
    if isinstance(node, OneOrMore):
        return _render_quantified(node.child, "+")
    if isinstance(node, ForeignAny):
        note = (
            f"foreign/external content ({node.namespace_hint or 'unknown namespace'}) has no "
            "ProseMirror equivalent; approximated as no content"
        )
        return _Rendered("", True, True, (note,))
    if isinstance(node, RecursionMarker):
        note = f"pattern-only recursive reference ({node.pattern_name}) approximated as no content"
        return _Rendered("", True, True, (note,))
    raise TypeError(f"unrenderable ContentNode variant: {type(node).__name__}")


def _render_joined(children: tuple[ContentNode, ...], sep: str, *, wrap_multi: bool) -> _Rendered:
    parts = [_render(c) for c in children]
    non_empty = [p for p in parts if p.text]
    approximate = any(p.is_approximate for p in parts)
    notes = tuple(n for p in parts for n in p.notes)
    if not non_empty:
        return _Rendered("", True, approximate, notes)
    text = sep.join(p.text for p in non_empty)
    is_atomic = len(non_empty) <= 1
    if wrap_multi and not is_atomic:
        text = f"({text})"
        is_atomic = True
    return _Rendered(text, is_atomic, approximate, notes)


def _render_interleave(node: Interleave) -> _Rendered:
    parts = [_render(c) for c in node.children]
    non_empty = [p for p in parts if p.text]
    notes = tuple(n for p in parts for n in p.notes)
    if not non_empty:
        note = "interleave with no renderable members approximated as no content"
        return _Rendered("", True, True, (*notes, note))
    inner = " | ".join(p.text for p in non_empty)
    note = (
        f"interleave ({inner}) has no ProseMirror equivalent (unordered, each-exactly-as-specified "
        "membership); approximated as unrestricted repetition of any member, in any order/count -- "
        "more permissive than the real grammar, so RelaxNgValidator remains the authoritative check"
    )
    return _Rendered(f"({inner})*", True, True, (*notes, note))


def _render_quantified(child: ContentNode, suffix: str) -> _Rendered:
    rendered = _render(child)
    if not rendered.text:
        return _Rendered("", True, rendered.is_approximate, rendered.notes)
    text = f"{_wrap_if_needed(rendered)}{suffix}"
    return _Rendered(text, True, rendered.is_approximate, rendered.notes)
