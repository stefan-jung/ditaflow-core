"""DITA XML -> DitaFlow (.dtf) parser.

See spec/DITAFLOW-SPEC.md for the format this module produces. Key design
rules implemented here (spec references in parentheses):

- classChain is copied verbatim from a literal `class` attribute when the
  source has one; otherwise it is looked up in the SpecialisationRegistry;
  otherwise it is synthesized as an opaque single-level chain (§1, §3).
- attrs not individually typed land in attrs._ext, including standard DITA
  attributes that just aren't modeled yet, not only unknown ones (§7).
- An element collapses into a text mark only if its entire content is text
  with no element children; otherwise it stays a generic element node (§4.1).
- Insignificant inter-element whitespace (pure whitespace containing a
  newline) is dropped; everything else is preserved as real text content
  (§9). This makes generic content arrays naturally round-trip exact
  whitespace without per-element content-model tables.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lxml import etree

from ditaflow.converter.class_chain import base_type_from_class_string
from ditaflow.converter.specialisation_registry import SpecialisationRegistry

DTF_VERSION = "1.0.0"
XML_NS_LANG = "{http://www.w3.org/XML/1998/namespace}lang"

# Attributes that map 1:1 onto a typed `attrs` field under the same JSON key.
# Kept in sync with schema/ditaflow.schema.json and schema/ditaflow.types.ts.
DIRECT_ATTRS: set[str] = {
    "id",
    "conref",
    "conrefend",
    "conaction",
    "conkeyref",
    "keyref",
    "keys",
    "outputclass",
    "translate",
    "dir",
    "importance",
    "status",
    "rev",
    "audience",
    "product",
    "platform",
    "props",
    "otherprops",
    "href",
    "format",
    "scope",
    "navtitle",
    "locktitle",
    "toc",
    "print",
    "search",
    "chunk",
    "collection-type",
    "linking",
    "keyscope",
    "frame",
    "colsep",
    "rowsep",
    "rowheader",
    "height",
    "width",
    "scale",
    "scalefit",
    "placement",
    "align",
    "hazard",
}

# Elements whose XML "type" attribute is the note-type enum (note_type),
# not the generic link-type-hint `type` field. Both share the XML attribute
# name "type" but mean different things (spec §7).
NOTE_TYPE_ELEMENTS: set[str] = {"note"}

# Attributes promoted to dedicated named fields on topicref/keydef nodes
# rather than left in the generic attrs bag.
TOPICREF_PROMOTED_ATTRS: set[str] = {"href", "keyref", "keys", "keyscope"}

# Attributes promoted to dedicated named fields on conref-bearing nodes.
CONREF_PROMOTED_ATTRS: set[str] = {"conref", "conkeyref", "conrefend", "conaction"}

MARK_ELEMENT_NAMES: set[str] = {"b", "i", "u", "sup", "sub", "tt"}

TOPIC_ROOT_NAMES: set[str] = {"topic", "concept", "task", "reference", "glossentry"}
MAP_ROOT_NAMES: set[str] = {"map", "bookmap"}

_INSIGNIFICANT_WS_RE = re.compile(r"^\s*\n\s*$")


def _is_insignificant_whitespace(text: str | None) -> bool:
    if not text:
        return False
    return bool(_INSIGNIFICANT_WS_RE.match(text))


def _is_comment(el: Any) -> bool:
    return not isinstance(el.tag, str) and el.tag is etree.Comment


def _is_pi(el: Any) -> bool:
    return not isinstance(el.tag, str) and el.tag is etree.PI


@dataclass
class DtfConversionWarning:
    severity: str
    code: str
    message: str
    node_path: str | None = None
    dita_x_path: str | None = None


@dataclass
class DtfImportResult:
    document: dict[str, Any]
    warnings: list[DtfConversionWarning] = field(default_factory=list)
    is_lossless: bool = True


class DitaParser:
    """Converts DITA XML (topics or maps) into a DTF document dict."""

    def __init__(
        self,
        registry: SpecialisationRegistry | None = None,
        *,
        default_dita_version: str = "1.3",
    ) -> None:
        self.registry = registry or SpecialisationRegistry()
        self.default_dita_version = default_dita_version
        self._warnings: list[DtfConversionWarning] = []
        self._base_dir: Path | None = None

    # -- Public API ----------------------------------------------------

    def parse_file(self, path: str | Path) -> DtfImportResult:
        path = Path(path)
        return self.parse_string(
            path.read_text(encoding="utf-8"),
            source_uri=str(path),
            base_dir=path.parent,
        )

    def parse_string(
        self,
        xml: str,
        *,
        source_uri: str | None = None,
        base_dir: str | Path | None = None,
    ) -> DtfImportResult:
        self._warnings = []
        self._base_dir = Path(base_dir) if base_dir is not None else None
        xml_bytes = xml.encode("utf-8")
        parser = etree.XMLParser(
            resolve_entities=False,
            no_network=True,
            load_dtd=False,
            dtd_validation=False,
            strip_cdata=False,
            remove_blank_text=False,
        )
        tree = etree.fromstring(xml_bytes, parser=parser).getroottree()
        root_el = tree.getroot()
        # lxml-stubs' DocInfo type is incomplete (missing doctype/system_url).
        docinfo: Any = tree.docinfo

        doctype_decl: dict[str, Any] | None = None
        if docinfo.doctype:
            doctype_decl = {"name": docinfo.root_name}
            if docinfo.public_id:
                doctype_decl["publicId"] = docinfo.public_id
            if docinfo.system_url:
                doctype_decl["systemId"] = docinfo.system_url

        tag = etree.QName(root_el).localname
        class_chain, base_type = self._class_chain_and_base(root_el)

        if tag in MAP_ROOT_NAMES or base_type == "map":
            base_doctype = "map"
            root_node = self._convert_map(root_el, class_chain, base_type)
        else:
            base_doctype = "topic"
            root_node = self._convert_topic(root_el, class_chain, base_type)

        meta: dict[str, Any] = {
            "sourceHash": hashlib.sha256(xml_bytes).hexdigest(),
        }
        if source_uri:
            meta["sourceUri"] = source_uri
        if doctype_decl:
            meta["doctypeDecl"] = doctype_decl

        document: dict[str, Any] = {
            "dtf": "ditaflow",
            "dtfVersion": DTF_VERSION,
            "ditaVersion": self.default_dita_version,
            "doctype": tag,
            "classChain": class_chain,
            "baseDoctype": base_doctype,
            "root": root_node,
            "meta": meta,
        }
        return DtfImportResult(document=document, warnings=list(self._warnings))

    # -- classChain / attrs ---------------------------------------------

    def _class_chain_and_base(self, el: Any) -> tuple[list[str], str]:
        tag = etree.QName(el).localname
        class_attr = el.get("class")
        if class_attr:
            class_string = class_attr
        else:
            entry = self.registry.lookup(tag)
            if entry is not None:
                class_string = entry.dita_class
            else:
                self._warnings.append(
                    DtfConversionWarning(
                        severity="info",
                        code="unregistered-element",
                        message=(
                            f"Element <{tag}> has no class attribute and is not "
                            "registered; synthesizing an opaque classChain."
                        ),
                    )
                )
                class_string = f"- {tag}/{tag} "
        base_type = base_type_from_class_string(class_string)
        return [class_string], base_type

    def _split_attrs(self, el: Any, *, promoted: AbstractSet[str] = frozenset()) -> dict[str, Any]:
        tag = etree.QName(el).localname
        attrs: dict[str, Any] = {}
        ext: dict[str, str] = {}
        for name, value in el.attrib.items():
            if name == "class" or name in promoted:
                continue
            if name == XML_NS_LANG:
                attrs["xml:lang"] = value
            elif name == "type":
                attrs["note_type" if tag in NOTE_TYPE_ELEMENTS else "type"] = value
            elif name in DIRECT_ATTRS:
                attrs[name] = value
            else:
                ext[name] = value
        if ext:
            attrs["_ext"] = ext
        return attrs

    # -- Mixed content / generic elements --------------------------------

    def _convert_mixed_content(self, el: Any) -> list[dict[str, Any]]:
        content: list[dict[str, Any]] = []
        if el.text and not _is_insignificant_whitespace(el.text):
            content.append({"type": "text", "text": el.text})
        for child in el:
            if _is_comment(child):
                content.append({"type": "comment", "text": child.text or ""})
            elif _is_pi(child):
                pi: dict[str, Any] = {"type": "pi", "target": child.target}
                if child.text:
                    pi["data"] = child.text
                content.append(pi)
            else:
                content.append(self._convert_element(child))
            if child.tail and not _is_insignificant_whitespace(child.tail):
                content.append({"type": "text", "text": child.tail})
        return self._collapse_marks(content)

    def _collapse_marks(self, content: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Collapse pure-text mark elements (b/i/u/sup/sub/tt) into marked
        text nodes, per the rule in spec §4.1: only when content is text
        with no element children."""
        result: list[dict[str, Any]] = []
        for node in content:
            mark_type = node.pop("_markCandidate", None)
            if mark_type is not None:
                inner = node.get("content", [])
                if inner and all(c.get("type") == "text" for c in inner):
                    for text_node in inner:
                        marks = list(text_node.get("marks", []))
                        marks.append({"type": mark_type})
                        result.append({**text_node, "marks": marks})
                    continue
            result.append(node)
        return result

    def _convert_element(self, el: Any) -> dict[str, Any]:
        tag = etree.QName(el).localname

        if tag == "image":
            return self._convert_image(el)
        if tag in ("table",):
            return self._convert_table(el)
        if tag == "simpletable":
            return self._convert_simpletable(el)
        if tag == "ditavalref":
            return self._convert_ditavalref(el)
        if tag in ("topicref", "keydef") or self._looks_like_topicref(el):
            return self._convert_topicref(el)

        class_chain, base_type = self._class_chain_and_base(el)
        conref = el.get("conref")
        conkeyref = el.get("conkeyref")
        if conref or conkeyref:
            node: dict[str, Any] = {
                "type": "conref",
                "classChain": class_chain,
                "baseType": base_type,
                "attrs": self._split_attrs(el, promoted=CONREF_PROMOTED_ATTRS),
                "resolved": None,
            }
            if conref:
                node["conref"] = conref
            if conkeyref:
                node["conkeyref"] = conkeyref
            if el.get("conrefend"):
                node["conrefend"] = el.get("conrefend")
            if el.get("conaction"):
                node["conaction"] = el.get("conaction")
            return node

        node = {
            "type": tag,
            "classChain": class_chain,
            "baseType": base_type,
            "attrs": self._split_attrs(el),
            "content": self._convert_mixed_content(el),
        }
        if tag in MARK_ELEMENT_NAMES:
            node["_markCandidate"] = tag
        return node

    def _looks_like_topicref(self, el: Any) -> bool:
        tag = etree.QName(el).localname
        if tag == "ditavalref":
            return False
        class_attr = el.get("class")
        if class_attr:
            return "map/topicref" in class_attr
        entry = self.registry.lookup(tag)
        return entry is not None and entry.base_element == "topicref"

    # -- Image -------------------------------------------------------------

    def _convert_image(self, el: Any) -> dict[str, Any]:
        class_chain, base_type = self._class_chain_and_base(el)
        node: dict[str, Any] = {
            "type": "image",
            "classChain": class_chain,
            "baseType": base_type,
            "attrs": self._split_attrs(el),
        }
        alt_el = el.find("alt")
        if alt_el is not None:
            node["alt"] = self._convert_mixed_content(alt_el)
        longdescref_el = el.find("longdescref")
        if longdescref_el is not None:
            node["longdescref"] = {
                k: v
                for k, v in (
                    ("href", longdescref_el.get("href")),
                    ("keyref", longdescref_el.get("keyref")),
                    ("format", longdescref_el.get("format")),
                )
                if v
            }
        return node

    # -- Topic envelope ------------------------------------------------

    def _convert_topic(self, el: Any, class_chain: list[str], base_type: str) -> dict[str, Any]:
        tag = etree.QName(el).localname
        node: dict[str, Any] = {
            "type": tag,
            "classChain": class_chain,
            "baseType": "topic",
            "attrs": self._split_attrs(el),
            "content": [],
        }
        nested: list[dict[str, Any]] = []
        for child in el:
            if not isinstance(child.tag, str):
                continue
            child_tag = etree.QName(child).localname
            if child_tag == "title":
                node["title"] = self._convert_simple_named(child)
            elif child_tag == "shortdesc":
                node["shortdesc"] = self._convert_simple_named(child)
            elif child_tag == "abstract":
                node["abstract"] = self._convert_simple_named(child)
            elif child_tag == "prolog":
                node["prolog"] = self._convert_simple_named(child)
            elif child_tag == "related-links":
                node["related_links"] = self._convert_simple_named(child)
            elif child_tag in TOPIC_ROOT_NAMES:
                nested.append(self._convert_topic(child, *self._class_chain_and_base(child)))
            elif child_tag == "body" or child_tag.endswith("body"):
                node["body"] = self._convert_simple_named(child)
        if nested:
            node["nested"] = nested
        return node

    def _convert_simple_named(self, el: Any) -> dict[str, Any]:
        class_chain, base_type = self._class_chain_and_base(el)
        return {
            "type": etree.QName(el).localname,
            "classChain": class_chain,
            "baseType": base_type,
            "attrs": self._split_attrs(el),
            "content": self._convert_mixed_content(el),
        }

    # -- Map envelope ----------------------------------------------------

    def _convert_map(self, el: Any, class_chain: list[str], base_type: str) -> dict[str, Any]:
        tag = etree.QName(el).localname
        keyscope_attr = el.get("keyscope")
        node: dict[str, Any] = {
            "type": tag,
            "classChain": class_chain,
            "baseType": "map",
            "attrs": self._split_attrs(el, promoted={"keyscope"}),
            "content": [],
            "topicrefs": [],
        }
        if keyscope_attr:
            node["keyscope"] = keyscope_attr.split()
        keydefs: list[dict[str, Any]] = []
        reltables: list[dict[str, Any]] = []
        topicrefs: list[dict[str, Any]] = []
        own_scope = node.get("keyscope", [])
        for child in el:
            if not isinstance(child.tag, str):
                continue
            child_tag = etree.QName(child).localname
            if child_tag == "title":
                node["title"] = self._convert_mixed_content(child)
            elif child_tag == "topicmeta":
                node["topicmeta"] = self._convert_simple_named(child)
            elif child_tag == "reltable":
                reltables.append(self._convert_reltable(child))
            elif child_tag == "keydef":
                keydefs.append(self._convert_topicref(child, parent_scope_path=own_scope))
            elif self._looks_like_topicref(child) or child_tag == "topicref":
                topicrefs.append(self._convert_topicref(child, parent_scope_path=own_scope))
        node["topicrefs"] = topicrefs
        if keydefs:
            node["keydefs"] = keydefs
        if reltables:
            node["reltables"] = reltables
        return node

    # -- Topicref tree --------------------------------------------------

    def _convert_topicref(
        self, el: Any, parent_scope_path: list[str] | None = None
    ) -> dict[str, Any]:
        parent_scope_path = parent_scope_path or []
        tag = etree.QName(el).localname
        class_chain, base_type = self._class_chain_and_base(el)
        attrs = self._split_attrs(el, promoted=TOPICREF_PROMOTED_ATTRS | {"keys"})
        node: dict[str, Any] = {
            "type": tag,
            "classChain": class_chain,
            "baseType": "topicref",
            "attrs": attrs,
            "content": [],
        }
        if el.get("href"):
            node["href"] = el.get("href")
        if el.get("keyref"):
            node["keyref"] = el.get("keyref")
        if el.get("keys"):
            node["keys"] = el.get("keys").split()
        keyscope_attr = el.get("keyscope")
        own_scope = keyscope_attr.split() if keyscope_attr else []
        node["keyscope"] = own_scope
        scope_path = list(parent_scope_path)
        for name in own_scope:
            qualified = f"{scope_path[-1]}.{name}" if scope_path else name
            scope_path.append(qualified)
        node["_keyscopePath"] = scope_path or list(parent_scope_path)

        if el.get("processing-role") == "resource-only" or tag == "keydef":
            node["type"] = "keydef" if tag == "keydef" else tag
            if el.get("processing-role") == "resource-only":
                node["resourceOnly"] = True

        ditavalrefs: list[dict[str, Any]] = []
        children: list[dict[str, Any]] = []
        for child in el:
            if not isinstance(child.tag, str):
                continue
            child_tag = etree.QName(child).localname
            if child_tag == "topicmeta":
                node["topicmeta"] = self._convert_simple_named(child)
            elif child_tag == "ditavalref":
                ditavalrefs.append(self._convert_ditavalref(child))
            elif self._looks_like_topicref(child) or child_tag in ("topicref", "keydef"):
                children.append(self._convert_topicref(child, parent_scope_path=scope_path))
        if ditavalrefs:
            node["ditavalrefs"] = ditavalrefs
        if children:
            node["children"] = children
        return node

    # -- Branch filtering: ditavalref + DITAVAL files --------------------

    def _convert_ditavalref(self, el: Any) -> dict[str, Any]:
        class_chain, base_type = self._class_chain_and_base(el)
        node: dict[str, Any] = {
            "type": "ditavalref",
            "classChain": class_chain,
            "baseType": "ditavalref",
            "attrs": self._split_attrs(
                el,
                promoted=TOPICREF_PROMOTED_ATTRS
                | {
                    "dvrResourcePrefix",
                    "dvrResourceSuffix",
                    "dvrKeyscopePrefix",
                    "dvrKeyscopeSuffix",
                },
            ),
            "content": [],
        }
        if el.get("href"):
            node["href"] = el.get("href")
        if el.get("keyref"):
            node["keyref"] = el.get("keyref")
        for attr_name in (
            "dvrResourcePrefix",
            "dvrResourceSuffix",
            "dvrKeyscopePrefix",
            "dvrKeyscopeSuffix",
        ):
            if el.get(attr_name):
                node[attr_name] = el.get(attr_name)

        if el.get("href") and self._base_dir is not None:
            ditaval_path = (self._base_dir / el.get("href")).resolve()
            if ditaval_path.is_file():
                node["inlinedDitaval"] = self._parse_ditaval_file(ditaval_path)
        return node

    def _parse_ditaval_file(self, path: Path) -> dict[str, Any]:
        tree = etree.parse(str(path))
        props: list[dict[str, Any]] = []
        for prop_el in tree.getroot().findall("prop"):
            prop: dict[str, Any] = {
                "att": prop_el.get("att"),
                "action": prop_el.get("action"),
            }
            if prop_el.get("val"):
                prop["val"] = prop_el.get("val")
            flag: dict[str, Any] = {}
            for flag_attr in ("color", "backcolor", "style"):
                if prop_el.get(flag_attr):
                    flag[flag_attr] = prop_el.get(flag_attr)
            if flag:
                prop["flag"] = flag
            props.append(prop)
        return {"version": "1.0", "props": props}

    # -- Tables: CALS -----------------------------------------------------

    def _convert_table(self, el: Any) -> dict[str, Any]:
        class_chain, base_type = self._class_chain_and_base(el)
        node: dict[str, Any] = {
            "type": "table",
            "classChain": class_chain,
            "baseType": "table",
            "attrs": self._split_attrs(el),
        }
        title_el = el.find("title")
        if title_el is not None:
            node["title"] = self._convert_mixed_content(title_el)
        desc_el = el.find("desc")
        if desc_el is not None:
            node["desc"] = self._convert_mixed_content(desc_el)
        tgroups = [self._convert_tgroup(tg) for tg in el.findall("tgroup")]
        if tgroups:
            node["tgroups"] = tgroups
        return node

    def _convert_tgroup(self, el: Any) -> dict[str, Any]:
        node: dict[str, Any] = {
            "type": "tgroup",
            "classChain": ["- topic/tgroup "],
            "baseType": "tgroup",
            "attrs": self._split_attrs(el),
        }
        colspecs = [self._simple_leaf(c, "colspec") for c in el.findall("colspec")]
        if colspecs:
            node["colspecs"] = colspecs
        spanspecs = [self._simple_leaf(s, "spanspec") for s in el.findall("spanspec")]
        if spanspecs:
            node["spanspecs"] = spanspecs
        for section_name, key in (("thead", "thead"), ("tbody", "tbody"), ("tfoot", "tfoot")):
            section_el = el.find(section_name)
            if section_el is not None:
                node[key] = self._convert_table_section(section_el)
        return node

    def _simple_leaf(self, el: Any, type_name: str) -> dict[str, Any]:
        return {
            "type": type_name,
            "classChain": [f"- topic/{type_name} "],
            "baseType": type_name,
            "attrs": self._split_attrs(el),
            "content": [],
        }

    def _convert_table_section(self, el: Any) -> dict[str, Any]:
        tag = etree.QName(el).localname
        return {
            "type": tag,
            "classChain": [f"- topic/{tag} "],
            "baseType": tag,
            "attrs": self._split_attrs(el),
            "rows": [self._convert_row(r) for r in el.findall("row")],
        }

    def _convert_row(self, el: Any) -> dict[str, Any]:
        return {
            "type": "row",
            "classChain": ["- topic/row "],
            "baseType": "row",
            "attrs": self._split_attrs(el),
            "entries": [self._convert_entry(e) for e in el.findall("entry")],
        }

    def _convert_entry(self, el: Any) -> dict[str, Any]:
        return {
            "type": "entry",
            "classChain": ["- topic/entry "],
            "baseType": "entry",
            "attrs": self._split_attrs(el),
            "content": self._convert_mixed_content(el),
        }

    # -- Tables: simple ----------------------------------------------------

    def _convert_simpletable(self, el: Any) -> dict[str, Any]:
        class_chain, base_type = self._class_chain_and_base(el)
        node: dict[str, Any] = {
            "type": "simpletable",
            "classChain": class_chain,
            "baseType": base_type,
            "attrs": self._split_attrs(el),
        }
        sthead_el = el.find("sthead")
        if sthead_el is not None:
            node["sthead"] = self._convert_strow(sthead_el, "sthead", "stentry")
        strows = [self._convert_strow(r, "strow", "stentry") for r in el.findall("strow")]
        if strows:
            node["strows"] = strows
        return node

    def _convert_strow(self, el: Any, row_type: str, entry_type: str) -> dict[str, Any]:
        return {
            "type": row_type,
            "classChain": [f"- topic/{row_type} "],
            "baseType": row_type,
            "attrs": self._split_attrs(el),
            "entries": [
                {
                    "type": entry_type,
                    "classChain": [f"- topic/{entry_type} "],
                    "baseType": entry_type,
                    "attrs": self._split_attrs(e),
                    "content": self._convert_mixed_content(e),
                }
                for e in el.findall(entry_type)
            ],
        }

    # -- Relationship tables -----------------------------------------------

    def _convert_reltable(self, el: Any) -> dict[str, Any]:
        node: dict[str, Any] = {
            "type": "reltable",
            "classChain": ["- map/reltable "],
            "baseType": "reltable",
            "attrs": self._split_attrs(el),
            "content": [],
            "relrows": [],
        }
        relheader_el = el.find("relheader")
        if relheader_el is not None:
            node["relheader"] = {
                "type": "relheader",
                "classChain": ["- map/relheader "],
                "baseType": "relheader",
                "attrs": self._split_attrs(relheader_el),
                "content": [],
                "relcolspecs": [
                    self._simple_leaf(c, "relcolspec") for c in relheader_el.findall("relcolspec")
                ],
            }
        for relrow_el in el.findall("relrow"):
            node["relrows"].append(
                {
                    "type": "relrow",
                    "classChain": ["- map/relrow "],
                    "baseType": "relrow",
                    "attrs": self._split_attrs(relrow_el),
                    "content": [],
                    "relcells": [
                        {
                            "type": "relcell",
                            "classChain": ["- map/relcell "],
                            "baseType": "relcell",
                            "attrs": self._split_attrs(c),
                            "content": self._convert_mixed_content(c),
                        }
                        for c in relrow_el.findall("relcell")
                    ],
                }
            )
        return node
