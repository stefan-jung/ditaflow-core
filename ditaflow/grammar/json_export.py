"""Converts a GrammarRegistry into a JSON-serializable dict -- the payload
behind xephon-cms's planned `GET /api/v1/dita-schema/{doctype}` endpoint
(Phase 2 of the wider effort; see ditaflow-core's plan history). `content`
is encoded as a tagged union (a `type` discriminator field plus shape-
specific fields) mirroring content_model_ast.py's dataclasses one-to-one,
so a TypeScript consumer can model it as a matching discriminated union
rather than re-deriving content-model structure from scratch. `prosemirror`
is included alongside it purely as a precomputed convenience (it's a pure
function of `content`, cheap to recompute, but every consumer needing a
ProseMirror NodeSpec `content` string would otherwise have to reimplement
prosemirror_export.py's rendering rules in TypeScript) -- the tagged-union
`content` tree remains the structurally complete source of truth.

All dict keys are camelCase to match the existing TypeScript-facing JSON
conventions already established by ditaflow's main DTF schema and
ditaElementInfo.ts's `classChain`/`baseType` fields, not the Python side's
own snake_case.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

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
from ditaflow.grammar.element_registry import SHELLS, ElementInfo, GrammarRegistry, get_registry
from ditaflow.grammar.prosemirror_export import to_content_expression


# get_registry's own cache does the expensive grammar-compilation work;
# this just avoids re-walking the AST into a JSON dict on every request
# for the same doctype.
@lru_cache(maxsize=len(SHELLS))
def to_json_dict(doctype: str) -> dict[str, Any]:
    return registry_to_json_dict(get_registry(doctype))


def registry_to_json_dict(registry: GrammarRegistry) -> dict[str, Any]:
    return {
        "doctype": registry.doctype,
        "elements": {
            name: _element_info_to_json_dict(info, registry)
            for name, info in registry.elements.items()
        },
        "extensionPoints": {
            name: sorted(members) for name, members in registry.extension_points.items()
        },
    }


def _element_info_to_json_dict(info: ElementInfo, registry: GrammarRegistry) -> dict[str, Any]:
    # prefer_inline/classify: see prosemirror_export.py's module docstring
    # ("A fourth ... case") -- ProseMirror can't mix inline and block
    # references in one content expression the way DITA's real grammar
    # can, so this drops whichever side doesn't match the element's own
    # is_inline, flagging the result approximate rather than letting a
    # mixed expression reach the frontend and fail schema construction.
    # has_members similarly drops a reference to an extension point with
    # no real members in *this* doctype's grammar (e.g. glossgroup's
    # "glossentry-info-types") -- same dangling-reference failure mode,
    # different cause.
    prosemirror = to_content_expression(
        info.content,
        prefer_inline=info.is_inline,
        classify=registry.classify_inline,
        has_members=lambda name: len(registry.get_extension_point_members(name)) > 0,
    )
    return {
        "elementName": info.element_name,
        "longName": info.long_name,
        "ditaClass": info.dita_class,
        "baseElement": info.base_element,
        "module": info.module,
        "isInline": info.is_inline,
        "extensionPoints": sorted(info.extension_points),
        "content": content_node_to_json_dict(info.content),
        "prosemirror": {
            "expression": prosemirror.expression,
            "isApproximate": prosemirror.is_approximate,
            "notes": list(prosemirror.notes),
        },
    }


def content_node_to_json_dict(node: ContentNode) -> dict[str, Any]:
    if isinstance(node, Sequence):
        return {
            "type": "sequence",
            "children": [content_node_to_json_dict(c) for c in node.children],
        }
    if isinstance(node, Choice):
        return {"type": "choice", "children": [content_node_to_json_dict(c) for c in node.children]}
    if isinstance(node, Interleave):
        return {
            "type": "interleave",
            "children": [content_node_to_json_dict(c) for c in node.children],
        }
    if isinstance(node, Optional):
        return {"type": "optional", "child": content_node_to_json_dict(node.child)}
    if isinstance(node, ZeroOrMore):
        return {"type": "zeroOrMore", "child": content_node_to_json_dict(node.child)}
    if isinstance(node, OneOrMore):
        return {"type": "oneOrMore", "child": content_node_to_json_dict(node.child)}
    if isinstance(node, ElementRef):
        return {"type": "elementRef", "elementName": node.element_name}
    if isinstance(node, ExtensionPointRef):
        return {
            "type": "extensionPointRef",
            "name": node.name,
            "expansion": content_node_to_json_dict(node.expansion),
        }
    if isinstance(node, TextRef):
        return {"type": "text"}
    if isinstance(node, Empty):
        return {"type": "empty"}
    if isinstance(node, ForeignAny):
        return {"type": "foreignAny", "namespaceHint": node.namespace_hint}
    if isinstance(node, RecursionMarker):
        return {"type": "recursionMarker", "patternName": node.pattern_name}
    raise TypeError(f"unencodable ContentNode variant: {type(node).__name__}")
