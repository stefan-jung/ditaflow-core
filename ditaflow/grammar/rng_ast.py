"""Raw RELAX NG pattern shapes, parsed directly from a `.rng` file's XML
tree before any DITA-specific semantics (extension points, `class`
attribute defaults, etc.) are applied. Deliberately mirrors RELAX NG's own
grammar terms, not "content model" terms -- see content_model_ast.py for
the DITA-facing AST these get resolved into.

Only the subset of RELAX NG actually used by DITA's grammars is modeled:
`<element>`, `<attribute>`, `<ref>`, `<choice>`, `<group>` (and implicit
sequence), `<interleave>`, `<optional>`, `<zeroOrMore>`, `<oneOrMore>`,
`<text>`, `<empty>`, and `<externalRef>`. Anything else encountered raises
GrammarError rather than silently producing a wrong pattern.
"""

from __future__ import annotations

from dataclasses import dataclass


class GrammarError(Exception):
    """Raised on a genuine RELAX NG structural problem -- an unexpected
    element, a combine conflict, a missing file. Vendored, trusted
    DITA-OT grammars should never actually trigger this; if one does,
    failing loudly at shell-compile time is far preferable to silently
    shipping a wrong content model to every document processed.
    """


class RngPattern:
    """Base class for raw, pre-merge RELAX NG pattern shapes."""


@dataclass(frozen=True)
class RngRef(RngPattern):
    name: str


@dataclass(frozen=True)
class RngElement(RngPattern):
    tag_name: str
    child: RngPattern
    long_name: str | None = None


@dataclass(frozen=True)
class RngAttribute(RngPattern):
    attr_name: str
    default_value: str | None


@dataclass(frozen=True)
class RngGroup(RngPattern):
    """Implicit or explicit sequence -- a `<define>` body with multiple
    direct child patterns is the same shape as an explicit `<group>`.
    """

    children: tuple[RngPattern, ...]


@dataclass(frozen=True)
class RngChoice(RngPattern):
    children: tuple[RngPattern, ...]


@dataclass(frozen=True)
class RngInterleave(RngPattern):
    children: tuple[RngPattern, ...]


@dataclass(frozen=True)
class RngOptional(RngPattern):
    child: RngPattern


@dataclass(frozen=True)
class RngZeroOrMore(RngPattern):
    child: RngPattern


@dataclass(frozen=True)
class RngOneOrMore(RngPattern):
    child: RngPattern


@dataclass(frozen=True)
class RngText(RngPattern):
    pass


@dataclass(frozen=True)
class RngEmpty(RngPattern):
    pass


@dataclass(frozen=True)
class RngExternal(RngPattern):
    """An `<externalRef href="...">` leaf -- treated as opaque foreign
    content (e.g. SVG) and never recursed into.
    """

    href: str


@dataclass(frozen=True)
class RawDefine:
    name: str
    pattern: RngPattern
    combine: str | None  # None | "choice" | "interleave"
    source_file: str
