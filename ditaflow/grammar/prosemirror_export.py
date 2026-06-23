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

A fourth, much more common case needing the same treatment: ProseMirror
requires a node's content to be *uniformly* inline or block (a node's
`inlineContent` is one fixed fact about its NodeType, never a per-position
choice) -- but DITA's real grammar has no such rule, and a great many
elements (roughly half of the long tail across the vendored shells, not a
rare corner case) freely mix inline phrase content with "universal"
carrier elements like `<data>`/`<foreign>`/`<unknown>` that are valid in
both inline and block positions throughout DITA. Passing `prefer_inline`
and `classify` makes `to_content_expression` drop whichever members don't
match the target element's own inline-ness, flagging the result
`is_approximate=True` exactly like the other three cases -- never a silent
loss. Both parameters are optional and unused by default, so every
existing pure-structural caller (and the synthetic tier-1 tests) is
unaffected; only json_export.py, which has real is_inline data to supply,
opts into the filtering.
"""

from __future__ import annotations

from collections.abc import Callable
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


@dataclass(frozen=True)
class _RenderFilter:
    prefer_inline: bool
    classify: Callable[[str], bool]
    # None means "assume every extension point has real members" (the
    # common case) -- only json_export.py, which has the real per-doctype
    # member counts, ever passes something else. An extension point can
    # be a real, valid RELAX NG combine point with *zero* members in one
    # particular doctype's grammar (confirmed: "glossentry-info-types" in
    # glossgroup) -- referencing it is then a dangling token with nothing
    # to resolve against, the same shape of problem as the inline/block
    # mismatch above, just a different cause.
    has_members: Callable[[str], bool] | None = None


def to_content_expression(
    node: ContentNode,
    *,
    prefer_inline: bool = False,
    classify: Callable[[str], bool] | None = None,
    has_members: Callable[[str], bool] | None = None,
) -> ProseMirrorContent:
    filter_ = _RenderFilter(prefer_inline, classify, has_members) if classify is not None else None
    rendered = _render(node, filter_)
    return ProseMirrorContent(
        expression=rendered.text, is_approximate=rendered.is_approximate, notes=rendered.notes
    )


def _wrap_if_needed(rendered: _Rendered) -> str:
    return rendered.text if rendered.is_atomic else f"({rendered.text})"


# Returns the dropped-placeholder rendering if `name` doesn't match the
# active filter's target category, else None (render `name` normally).
# `is_inline=True` lets TextRef short-circuit the classify() call -- "text"
# always means ProseMirror's built-in, hard-coded-inline text node, so a
# bare TextRef mixed into an otherwise block-only expression hits the
# exact same "mixing inline and block content" error a literal inline
# element reference would, with no registry lookup needed to know that.
#
# DITA also has a real, separate element literally named `<text>` (a
# generic mixed-content wrapper, e.g. for keyword variants) -- confirmed:
# its own classify() would say "block" (it isn't one of the known inline
# bases), but rendered as the bare token "text" it is indistinguishable
# from ProseMirror's reserved inline text-node token, so it must be
# classified the *same* way regardless of what classify() would otherwise
# say, or it can silently survive into a block-only expression and hit
# the exact mixing error this function exists to prevent.
def _filtered(
    name: str, filter_: _RenderFilter | None, *, is_inline: bool | None = None
) -> _Rendered | None:
    if filter_ is None:
        return None
    if is_inline is None and name == "text":
        is_inline = True
    actual = filter_.classify(name) if is_inline is None else is_inline
    if actual == filter_.prefer_inline:
        return None
    note = (
        f"'{name}' dropped here: the real grammar allows both inline and block-level content "
        "in this position, but a ProseMirror node's content can't mix the two; "
        "RelaxNgValidator remains the authoritative check"
    )
    return _Rendered("", True, True, (note,))


def _render(node: ContentNode, filter_: _RenderFilter | None) -> _Rendered:
    if isinstance(node, ElementRef):
        return _filtered(node.element_name, filter_) or _Rendered(
            node.element_name, True, False, ()
        )
    if isinstance(node, ExtensionPointRef):
        if (
            filter_ is not None
            and filter_.has_members is not None
            and not filter_.has_members(node.name)
        ):
            note = (
                f"'{node.name}' dropped here: this extension point has no members in this "
                "doctype's grammar"
            )
            return _Rendered("", True, True, (note,))
        return _filtered(node.name, filter_) or _Rendered(node.name, True, False, ())
    if isinstance(node, TextRef):
        return _filtered("text", filter_, is_inline=True) or _Rendered("text", True, False, ())
    if isinstance(node, Empty):
        return _Rendered("", True, False, ())
    if isinstance(node, Sequence):
        return _render_joined(node.children, " ", filter_, wrap_multi=False)
    if isinstance(node, Choice):
        return _render_joined(node.children, " | ", filter_, wrap_multi=True)
    if isinstance(node, Interleave):
        return _render_interleave(node, filter_)
    if isinstance(node, Optional):
        return _render_quantified(node.child, "?", filter_)
    if isinstance(node, ZeroOrMore):
        return _render_quantified(node.child, "*", filter_)
    if isinstance(node, OneOrMore):
        return _render_quantified(node.child, "+", filter_)
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


def _render_joined(
    children: tuple[ContentNode, ...],
    sep: str,
    filter_: _RenderFilter | None,
    *,
    wrap_multi: bool,
) -> _Rendered:
    parts = [_render(c, filter_) for c in children]
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


def _render_interleave(node: Interleave, filter_: _RenderFilter | None) -> _Rendered:
    parts = [_render(c, filter_) for c in node.children]
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


def _render_quantified(child: ContentNode, suffix: str, filter_: _RenderFilter | None) -> _Rendered:
    rendered = _render(child, filter_)
    if not rendered.text:
        return _Rendered("", True, rendered.is_approximate, rendered.notes)
    text = f"{_wrap_if_needed(rendered)}{suffix}"
    return _Rendered(text, True, rendered.is_approximate, rendered.notes)
