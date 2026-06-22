"""Walks a DITA RELAX NG doctype shell's `<include>` graph and produces one
merged, doctype-scoped define table -- the input pattern_resolver.py
resolves into the DITA-facing content-model AST.

Two pieces of real RELAX NG semantics this module must get right, both
confirmed against the actual vendored files (see module-level comments at
each site below for the specific evidence):

1. **Combine merging**: when the same `<define name="X">` is contributed by
   more than one file with the same `combine="choice"`/`"interleave"`
   attribute, the final pattern for X is the union (or interleave) of every
   contribution -- this is DITA's domain-extension mechanism itself (e.g.
   every highlight/programming/ui domain module contributes
   `<define name="ph" combine="choice">`).

2. **Include-nested define override**: `<include href="X.rng"><define
   name="Y">PATTERN</define></include>` replaces X's own definition of Y
   (however it was defined within X's subtree, even transitively) with
   PATTERN, for the rest of this shell's compilation. DITA's shells use this
   exactly once per shell for the `{doctype}-info-types` topic-nesting
   pattern (e.g. topic.rng overrides `topic-info-types`). Applied
   unconditionally at the end of the whole walk (not inline at the include
   site) -- order-independent, and correct because no DITA shell in this
   vendored set overrides the same define name more than once.
"""

from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

from ditaflow.grammar.rng_ast import (
    GrammarError,
    RawDefine,
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

_RNG_NS = "http://relaxng.org/ns/structure/1.0"
_ANNOTATIONS_NS = "http://relaxng.org/ns/compatibility/annotations/1.0"
_DITA_ARCH_NS = "http://dita.oasis-open.org/architecture/2005/"


def _qname(local: str) -> str:
    return f"{{{_RNG_NS}}}{local}"


@dataclass(frozen=True)
class MergedGrammar:
    doctype: str
    defines: dict[str, RawDefine]
    start: RngPattern | None
    module_of_define: dict[str, str]


def _local_name(el: etree._Element) -> str:
    tag = el.tag
    if not isinstance(tag, str):
        return ""  # comments/PIs have non-string tags; never structural RNG content
    return etree.QName(tag).localname


def _is_rng(el: etree._Element) -> bool:
    return isinstance(el.tag, str) and etree.QName(el.tag).namespace == _RNG_NS


def _rng_children(el: etree._Element) -> list[etree._Element]:
    """Direct children that are real RELAX NG structural elements --
    skips a:documentation, dita:*, comments, and PIs, which can appear
    interleaved with structural content anywhere in these files.
    """
    return [c for c in el if _is_rng(c)]


def _parse_single_child_pattern(el: etree._Element) -> RngPattern:
    children = _rng_children(el)
    return _parse_pattern_sequence(children)


def _parse_pattern_sequence(elements: list[etree._Element]) -> RngPattern:
    if not elements:
        return RngEmpty()
    if len(elements) == 1:
        return _parse_pattern(elements[0])
    return RngGroup(tuple(_parse_pattern(e) for e in elements))


def _parse_pattern(el: etree._Element) -> RngPattern:
    name = _local_name(el)
    if name == "ref":
        return RngRef(name=el.get("name", ""))
    if name == "element":
        return RngElement(tag_name=el.get("name", ""), child=_parse_single_child_pattern(el))
    if name == "attribute":
        default_value = el.get(f"{{{_ANNOTATIONS_NS}}}defaultValue")
        return RngAttribute(attr_name=el.get("name", ""), default_value=default_value)
    if name in ("group", "define", "start"):
        return _parse_single_child_pattern(el)
    if name == "choice":
        return RngChoice(tuple(_parse_pattern(c) for c in _rng_children(el)))
    if name == "interleave":
        return RngInterleave(tuple(_parse_pattern(c) for c in _rng_children(el)))
    if name == "optional":
        return RngOptional(_parse_single_child_pattern(el))
    if name == "zeroOrMore":
        return RngZeroOrMore(_parse_single_child_pattern(el))
    if name == "oneOrMore":
        return RngOneOrMore(_parse_single_child_pattern(el))
    if name == "text":
        return RngText()
    if name == "empty":
        return RngEmpty()
    if name == "externalRef":
        return RngExternal(href=el.get("href", ""))
    if name in ("notAllowed", "value", "data", "list", "mixed", "anyName", "nsName", "except"):
        # Real RELAX NG constructs DITA's grammars don't use in content-model
        # position for anything this package needs (datatype/value-space
        # constraints on attributes, not element structure) -- treated as an
        # opaque leaf rather than raising, since they're legitimate RNG, just
        # outside this module's scope (attribute value validation).
        return RngEmpty()
    raise GrammarError(f"unrecognized RELAX NG pattern element <{name}>")


def _module_short_name(grammar_el: etree._Element) -> str | None:
    path = (
        f"{{{_DITA_ARCH_NS}}}moduleDesc/{{{_DITA_ARCH_NS}}}moduleMetadata"
        f"/{{{_DITA_ARCH_NS}}}moduleShortName"
    )
    found = grammar_el.find(path)
    return found.text.strip() if found is not None and found.text else None


def load_shell(shell_path: Path, *, doctype: str) -> MergedGrammar:
    """Parses `shell_path` and its full `<include>` transitive closure into
    one MergedGrammar. `shell_path` must be a real filesystem path (relative
    `<include href>` resolution depends on it), matching the same
    constraint RelaxNgValidator's `_compiled_schema` already documents.
    """
    visited_files: set[str] = set()
    raw_defines: dict[str, list[RawDefine]] = defaultdict(list)
    module_of_define: dict[str, str] = {}
    override_instructions: list[tuple[str, RngPattern]] = []
    start_pattern: RngPattern | None = None

    def visit(file_path: Path) -> None:
        nonlocal start_pattern
        real_path = str(file_path.resolve())
        if real_path in visited_files:
            return
        visited_files.add(real_path)
        tree = etree.parse(real_path)
        root = tree.getroot()
        module_name = _module_short_name(root)
        walk_body(root, real_path, module_name)

    def walk_body(container: etree._Element, source_file: str, module_name: str | None) -> None:
        nonlocal start_pattern
        for child in _rng_children(container):
            child_name = _local_name(child)
            if child_name == "div":
                walk_body(child, source_file, module_name)
            elif child_name == "include":
                handle_include(child, source_file)
            elif child_name == "define":
                define_name = child.get("name", "")
                combine = child.get("combine")
                raw_defines[define_name].append(
                    RawDefine(
                        name=define_name,
                        pattern=_parse_single_child_pattern(child),
                        combine=combine,
                        source_file=source_file,
                    )
                )
                if module_name is not None and define_name not in module_of_define:
                    module_of_define[define_name] = module_name
            elif child_name == "start":
                start_pattern = _parse_single_child_pattern(child)
            elif child_name in ("moduleDesc",):
                pass  # metadata only, already extracted via _module_short_name
            else:
                raise GrammarError(
                    f"unexpected top-level grammar element <{child_name}> in {source_file}"
                )

    def handle_include(include_el: etree._Element, including_file: str) -> None:
        href = include_el.get("href", "")
        included_path = Path(os.path.normpath(os.path.join(os.path.dirname(including_file), href)))
        visit(included_path)
        for override_define in _rng_children(include_el):
            override_tag = _local_name(override_define)
            if override_tag != "define":
                raise GrammarError(
                    f"unexpected <include> child <{override_tag}> in {including_file}"
                )
            override_instructions.append(
                (override_define.get("name", ""), _parse_single_child_pattern(override_define))
            )

    visit(shell_path)

    for name, pattern in override_instructions:
        raw_defines[name] = [
            RawDefine(name=name, pattern=pattern, combine=None, source_file="<override>")
        ]

    merged = {
        name: _merge_combine_group(name, contributions)
        for name, contributions in raw_defines.items()
    }
    return MergedGrammar(
        doctype=doctype, defines=merged, start=start_pattern, module_of_define=module_of_define
    )


def _merge_combine_group(name: str, contributions: list[RawDefine]) -> RawDefine:
    if len(contributions) == 1:
        return contributions[0]

    # RELAX NG's DTD-compatibility convention (confirmed against the real
    # vendored files, e.g. base/rng/commonElementsMod.rng's bare `data`
    # define vs. utilitiesDomain.rng's `combine="choice"` extension of it --
    # libxml2 itself accepts this, already proven by every shell compiling
    # successfully): at most one contribution may lack a `combine` attribute
    # at all -- it's an implicit member of whatever combine the others
    # specify, not a conflict. Two or more bare contributions is genuinely
    # ambiguous (no instruction for how to combine them) and stays an error.
    bare = [c for c in contributions if c.combine is None]
    if len(bare) > 1:
        raise GrammarError(
            f"'{name}' has {len(bare)} definitions with no combine attribute "
            f"(at most one allowed; sources: {[c.source_file for c in bare]})"
        )
    combine_values = {c.combine for c in contributions if c.combine is not None}
    if not combine_values:
        raise GrammarError(
            f"'{name}' has {len(contributions)} contributions but none specify a "
            f"combine attribute (sources: {[c.source_file for c in contributions]})"
        )
    if len(combine_values) > 1:
        raise GrammarError(
            f"'{name}' combined with conflicting combine attributes: {combine_values}"
        )

    combine = combine_values.pop()
    wrapper: type[RngChoice] | type[RngInterleave] = (
        RngChoice if combine == "choice" else RngInterleave
    )
    return RawDefine(
        name=name,
        combine=combine,
        pattern=wrapper(tuple(c.pattern for c in contributions)),
        source_file="<merged>",
    )
