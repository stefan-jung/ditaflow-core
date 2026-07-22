"""Lightweight, intentionally partial DITA content-model checker.

ditaflow-core's converter is deliberately grammar-agnostic (see
specialisation_registry.py's module docstring) -- it round-trips via
classChain/baseType without enforcing DITA nesting rules. This module adds
an OPTIONAL, approximate content-model check on top, keyed by
**baseType** rather than element name, so specializations (e.g. `steps`/
`step`, both sharing baseType `ol`/`li` with `ol`/`li` themselves)
automatically inherit their base element's rules without a separate
table entry.

This is NOT the official DITA grammar. For real RELAX NG validation
against the official DITA 1.3 grammar, see
``ditaflow.validator.relaxng_validator.RelaxNgValidator`` -- that module
operates on serialized XML (a later-stage check against the serializer's
output), while this one operates on DTF JSON dicts, so they're
complementary, not redundant: this one is cheap and runs directly on the
DTF a caller already has in hand, the other is authoritative but requires
serializing first. An empty error list from *this* checker means "nothing
this checker knows how to flag is wrong", not "guaranteed valid DITA" --
only ``RelaxNgValidator`` (or its absence of errors) gives that guarantee,
and only for the five doctypes it covers.

Lenient by omission: a parent baseType with no entry in
``ALLOWED_CHILDREN`` is not checked at all (no false positives for
structure this module doesn't model). ``KNOWN_BASE_TYPES`` documents every
baseType the specialisation registry produces, so a test can assert
``ALLOWED_CHILDREN``'s keys are a deliberate subset of it -- "not modeled
yet" stays distinguishable from "forgotten" as the table grows.

Known limitation: checking baseType instead of literal element name means
this cannot catch e.g. ``<ul><step>...</step></ul>`` -- ``step``'s
baseType is ``li``, which IS allowed under ``ul``. ``RelaxNgValidator``
models nesting at that level of detail (see its own test suite for this
exact example).
"""

from __future__ import annotations

from typing import Any

# Every baseType ditaflow-core's specialisation registry produces (see
# specialisation_registry.py's _CORE_PROFILE). Kept as a flat, auditable
# list here rather than imported, so this module doesn't reach into that
# module's private _CORE_PROFILE -- a test asserts the two stay in sync.
KNOWN_BASE_TYPES: frozenset[str] = frozenset(
    {
        "topic",
        "title",
        "shortdesc",
        "abstract",
        "prolog",
        "body",
        "related-links",
        "link",
        "p",
        "section",
        "example",
        "note",
        "ol",
        "ul",
        "sl",
        "li",
        "sli",
        "dl",
        "dlentry",
        "dt",
        "dd",
        "fig",
        "image",
        "codeblock",
        "pre",
        "lines",
        "required-cleanup",
        "data",
        "xref",
        "keyword",
        "term",
        "cite",
        "ph",
        "fn",
        "indexterm",
        "table",
        "tgroup",
        "colspec",
        "spanspec",
        "thead",
        "tbody",
        "tfoot",
        "row",
        "entry",
        "simpletable",
        "sthead",
        "strow",
        "stentry",
        "itemgroup",
        "map",
        "topicref",
        "topicmeta",
        "reltable",
        "relheader",
        "relcolspec",
        "relrow",
        "relcell",
    }
)

# Inline-capable baseTypes (is_inline=True in the registry -- this also
# covers cmd and the highlight-domain marks b/i/u/sup/sub/tt, which all
# share baseType "ph"), plus the pseudo-baseType "text" for text nodes. A
# child of any of these baseTypes is always allowed wherever block content
# is allowed, so block containers below don't need to enumerate every
# inline element individually.
INLINE_BASE_TYPES: frozenset[str] = frozenset({"ph", "xref", "term", "keyword", "text"})

# Block-level content models, keyed by baseType. Only covers the
# structured editor's in-scope elements (see xephon-cms/ROADMAP.md) --
# dl, fig, fn, cite, indexterm, and the map family are deliberately
# excluded, not forgotten (see module docstring). CALS tables ("table",
# baseType "table") are NOT in that excluded set -- the roadmap's own
# "CALS + simple tables ... full bidirectional round-trip" entry and
# KNOWN_BASE_TYPES both already treat it as a modeled, in-scope element;
# omitting it here (while "simpletable" -- a peer, equally table-shaped
# element -- was included) was a real gap, not a deliberate one. Confirmed
# via a real document: every table built through xephon-cms's table editor
# was flagged as "not allowed inside body" by this checker even once
# RelaxNgValidator (the authoritative check) validated it clean.
ALLOWED_CHILDREN: dict[str, frozenset[str]] = {
    "body": frozenset(
        {"section", "note", "p", "ul", "ol", "sl", "image", "codeblock", "simpletable", "table"}
    ),
    "section": frozenset(
        {"title", "p", "note", "ul", "ol", "sl", "image", "codeblock", "simpletable", "table"}
    ),
    "li": frozenset(
        {"p", "note", "ul", "ol", "sl", "image", "codeblock", "simpletable", "table"}
    ),
    "note": frozenset({"p", "ul", "ol", "sl"}),
    "ul": frozenset({"li"}),
    "ol": frozenset({"li"}),
    "sl": frozenset({"sli"}),
    "itemgroup": frozenset(
        {"p", "ul", "ol", "sl", "note", "image", "codeblock", "simpletable", "table"}
    ),
    "simpletable": frozenset({"sthead", "strow"}),
    "sthead": frozenset({"stentry"}),
    "strow": frozenset({"stentry"}),
    "stentry": frozenset(),
    "title": frozenset(),
    "codeblock": frozenset(),
}


# Keys that hold dict/list-of-dict values but aren't child nodes: "attrs"
# is a flat metadata bag, and a text node's "marks" entries (e.g.
# {"type": "b"}) look like nodes (they have a "type" key) but annotate the
# text node rather than nesting inside it.
_NON_CHILD_KEYS = frozenset({"attrs", "marks"})


def _children_of(node: dict[str, Any]) -> list[Any]:
    """Returns a node's child nodes, walking every key generically rather
    than assuming children always live in a "content" array -- DTF isn't
    consistent about this: topic/concept/task/reference put title/body/
    etc. in dedicated keys (not "content"), simpletable uses "sthead"/
    "strows", strow uses "entries", but section/note/p/li use "content"
    (see schema/ditaflow.schema.json). Any dict with a "type" key (which
    covers both element nodes and text nodes) found under any other key
    counts as a child.
    """
    children: list[Any] = []
    for key, value in node.items():
        if key in _NON_CHILD_KEYS:
            continue
        if isinstance(value, dict) and "type" in value:
            children.append(value)
        elif isinstance(value, list):
            children.extend(item for item in value if isinstance(item, dict) and "type" in item)
    return children


def _walk(node: Any, path: str, errors: list[str]) -> None:
    if isinstance(node, dict):
        base_type = node.get("baseType")
        node_label = str(node.get("type", base_type))
        children = _children_of(node)
        allowed = ALLOWED_CHILDREN.get(base_type) if base_type else None
        if allowed is not None:
            for child in children:
                if not isinstance(child, dict):
                    continue
                child_base_type = child.get("baseType")
                if child.get("type") == "text" or child_base_type in INLINE_BASE_TYPES:
                    continue
                if child_base_type not in allowed:
                    child_label = child.get("type", child_base_type)
                    errors.append(
                        f"{path}: '{child_label}' (baseType '{child_base_type}') is not "
                        f"allowed inside '{node_label}' (baseType '{base_type}'); expected "
                        f"one of: {', '.join(sorted(allowed)) or '(none)'}"
                    )
        for child in children:
            _walk(child, f"{path}/{node_label}", errors)
    elif isinstance(node, list):
        for item in node:
            _walk(item, path, errors)


class ContentModelChecker:
    """Approximate DITA content-model check -- see module docstring."""

    def validate(self, document: dict[str, Any]) -> list[str]:
        """Returns a list of human-readable error messages (empty if no
        modeled violations were found -- see module docstring for what
        that does and doesn't guarantee).
        """
        errors: list[str] = []
        root = document.get("root")
        if isinstance(root, dict):
            _walk(root, "root", errors)
        return errors

    def is_valid(self, document: dict[str, Any]) -> bool:
        return not self.validate(document)
