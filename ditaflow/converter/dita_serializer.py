"""DitaFlow (.dtf) -> DITA XML serializer. Mirrors dita_parser.py.

Pretty-printing strategy (spec/DITAFLOW-SPEC.md §9): we only ever fill in
indentation where no text was preserved at all (``.text``/``.tail`` is
``None``). Anywhere the parser preserved real text — including a meaningful
single space between inline elements — is left completely untouched. This
guarantees pretty-printing can never corrupt mixed content, at the cost of
not reproducing the original file's exact indentation (which the round-trip
semantics explicitly do not require, see spec §9).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lxml import etree

from ditaflow.converter.specialisation_registry import SpecialisationRegistry

XML_NS_LANG = "{http://www.w3.org/XML/1998/namespace}lang"


# A topicref (or any specialization: topicgroup/topichead/keydef/chapter/...)
# can legitimately appear inside otherwise-generic mixed content -- most
# commonly a <relcell>'s content (a relationship table's whole purpose is
# linking real topicrefs into a cell) or a table entry. dita_parser.py's
# `_convert_mixed_content` already gives such a nested element the same
# promoted-field treatment (href/keys/keyscope/children, not plain attrs) as
# a top-level topicref -- see `_looks_like_topicref` there -- so the reverse
# direction must route it to `_topicref_node_to_element`, not the generic
# `_element_node_to_element`, or those promoted fields are silently dropped
# (confirmed: a relcell's <topicref href="..."/> lost its href entirely
# before this check existed). classChain is always present on a DTF node by
# construction, so -- unlike the parser, which may have only a bare XML
# element to work from -- no registry lookup is needed here.
def _is_topicref_shaped(node: dict[str, Any]) -> bool:
    class_chain = node.get("classChain") or [""]
    return "map/topicref" in class_chain[0]


def _is_bookmap_shaped(node: dict[str, Any]) -> bool:
    class_chain = node.get("classChain") or [""]
    return "bookmap/bookmap" in class_chain[0]


# entityRef content nodes (see dita_parser.py's _is_entity_ref) can appear
# anywhere mixed content can -- title, shortdesc, a topicref's topicmeta,
# deep inside body/section/p, etc. -- so this walks every dict/list value
# generically rather than enumerating each of those fields, mirroring how
# _append_content's own dispatch already treats content recursively without
# caring which named field it came from.
def _collect_entity_refs(value: Any, out: set[str]) -> None:
    if isinstance(value, dict):
        if value.get("type") == "entityRef":
            out.add(value["name"])
        for v in value.values():
            _collect_entity_refs(v, out)
    elif isinstance(value, list):
        for item in value:
            _collect_entity_refs(item, out)


ATTR_ORDER: list[str] = [
    "id",
    "conref",
    "conrefend",
    "conaction",
    "conkeyref",
    "keyref",
    "keys",
    "href",
    "navtitle",
    "locktitle",
    "toc",
    "print",
    "search",
    "chunk",
    "collection-type",
    "linking",
    "keyscope",
    "audience",
    "product",
    "platform",
    "props",
    "otherprops",
    "outputclass",
    "translate",
    "xml:lang",
    "dir",
    "importance",
    "status",
    "rev",
    "scope",
    "format",
    "type",
    "note_type",
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
]


@dataclass
class DtfExportResult:
    xml: str
    warnings: list[Any] = field(default_factory=list)


class DtfSerializer:
    """Converts a DTF document dict back into DITA XML."""

    def __init__(self, registry: SpecialisationRegistry | None = None) -> None:
        self.registry = registry or SpecialisationRegistry()

    # -- Public API ----------------------------------------------------

    def serialize(self, document: dict[str, Any]) -> DtfExportResult:
        root_node = document["root"]
        if document["baseDoctype"] == "map":
            root_el = self._map_node_to_element(root_node)
        else:
            root_el = self._topic_node_to_element(root_node)

        self._fill_indentation(root_el)

        entity_names: set[str] = set()
        _collect_entity_refs(root_node, entity_names)
        doctype = self._build_doctype(
            document.get("meta", {}).get("doctypeDecl"), entity_names, root_node["type"]
        )
        if doctype is not None:
            xml_bytes = etree.tostring(
                root_el, xml_declaration=True, encoding="UTF-8", doctype=doctype
            )
        else:
            xml_bytes = etree.tostring(root_el, xml_declaration=True, encoding="UTF-8")
        return DtfExportResult(xml=xml_bytes.decode("utf-8"))

    @staticmethod
    def _build_doctype(
        decl: dict[str, Any] | None, entity_names: set[str], root_tag: str
    ) -> str | None:
        # Entity references (entityRef content nodes -- see dita_parser.py's
        # _is_entity_ref) are only well-formed XML when something declares
        # them; the resolved value was never captured in DTF in the first
        # place (resolve_entities=False on import -- see parse_string), so
        # re-declaring each with an empty placeholder value here is enough
        # to make the *structure* (the reference itself) round-trip and
        # stay parseable, without needing to know what the entity actually
        # expands to. Needed even when no doctypeDecl was captured at all:
        # confirmed real-world content (the Oxygen XML User Guide corpus)
        # has entity references declared only in an external DTD that this
        # serializer never reads -- not declaring them here would silently
        # reintroduce the "undefined entity" parse failure entityRef was
        # added to avoid in the first place.
        internal_subset = (
            " [" + "".join(f'<!ENTITY {name} "">' for name in sorted(entity_names)) + "]"
            if entity_names
            else ""
        )
        if not decl:
            if not entity_names:
                return None
            return f"<!DOCTYPE {root_tag}{internal_subset}>"
        name = decl["name"]
        public_id = decl.get("publicId")
        system_id = decl.get("systemId")
        if public_id and system_id:
            return f'<!DOCTYPE {name} PUBLIC "{public_id}" "{system_id}"{internal_subset}>'
        if system_id:
            return f'<!DOCTYPE {name} SYSTEM "{system_id}"{internal_subset}>'
        return f"<!DOCTYPE {name}{internal_subset}>"

    @staticmethod
    def _fill_indentation(el: Any, depth: int = 0) -> None:
        children = [c for c in el if isinstance(c.tag, str)]
        if not children:
            return
        if el.text is None:
            el.text = "\n" + "  " * (depth + 1)
        for i, child in enumerate(children):
            DtfSerializer._fill_indentation(child, depth + 1)
            if child.tail is None:
                is_last = i == len(children) - 1
                child.tail = "\n" + "  " * (depth if is_last else depth + 1)

    # -- Attributes ------------------------------------------------------

    def _set_attrs(self, el: Any, attrs: dict[str, Any]) -> None:
        ext = attrs.get("_ext", {})
        for key in ATTR_ORDER:
            if key not in attrs:
                continue
            value = attrs[key]
            if key == "xml:lang":
                el.set(XML_NS_LANG, value)
            elif key == "note_type":
                el.set("type", value)
            else:
                el.set(key, value)
        for key in sorted(ext):
            el.set(key, ext[key])

    @staticmethod
    def _real_tag_from_class_chain(class_chain: list[str]) -> str:
        body = class_chain[0].strip()
        if body and body[0] in "+-":
            body = body[1:].strip()
        last_pair = body.rsplit(" ", 1)[-1] if body else ""
        return last_pair.split("/", 1)[1] if "/" in last_pair else last_pair

    # -- Mixed content -----------------------------------------------------

    def _append_content(self, parent_el: Any, content: list[dict[str, Any]]) -> None:
        last_child: Any = None
        for node in content:
            ntype = node.get("type")
            if ntype == "text":
                marks = node.get("marks")
                if marks:
                    wrapper = self._build_mark_wrapper(node["text"], marks)
                    parent_el.append(wrapper)
                    last_child = wrapper
                else:
                    self._append_plain_text(parent_el, last_child, node["text"])
                    continue
            elif ntype == "comment":
                last_child = etree.Comment(node.get("text", ""))
                parent_el.append(last_child)
            elif ntype == "pi":
                last_child = etree.ProcessingInstruction(node["target"], node.get("data") or "")
                parent_el.append(last_child)
            elif ntype == "entityRef":
                last_child = etree.Entity(node["name"])
                parent_el.append(last_child)
            elif ntype == "conref":
                last_child = self._conref_node_to_element(node)
                parent_el.append(last_child)
            elif ntype == "image":
                last_child = self._image_node_to_element(node)
                parent_el.append(last_child)
            elif ntype == "table":
                last_child = self._table_node_to_element(node)
                parent_el.append(last_child)
            elif ntype == "simpletable":
                last_child = self._simpletable_node_to_element(node)
                parent_el.append(last_child)
            elif _is_topicref_shaped(node):
                last_child = self._topicref_node_to_element(node)
                parent_el.append(last_child)
            else:
                last_child = self._element_node_to_element(node)
                parent_el.append(last_child)

    @staticmethod
    def _append_plain_text(parent_el: Any, last_child: Any, text: str) -> None:
        if last_child is None:
            parent_el.text = (parent_el.text or "") + text
        else:
            last_child.tail = (last_child.tail or "") + text

    def _build_mark_wrapper(self, text: str, marks: list[dict[str, str]]) -> Any:
        el = None
        for mark in marks:
            tag = mark["type"]
            new_el = etree.Element(tag)
            entry = self.registry.lookup(tag)
            if entry:
                new_el.set("class", entry.dita_class)
            if el is None:
                new_el.text = text
            else:
                new_el.append(el)
            el = new_el
        return el

    def _element_node_to_element(self, node: dict[str, Any]) -> Any:
        el = etree.Element(node["type"])
        el.set("class", node["classChain"][0])
        self._set_attrs(el, node.get("attrs", {}))
        self._append_content(el, node.get("content", []))
        return el

    def _conref_node_to_element(self, node: dict[str, Any]) -> Any:
        tag = self._real_tag_from_class_chain(node["classChain"])
        el = etree.Element(tag)
        el.set("class", node["classChain"][0])
        for field_name, attr_name in (
            ("conref", "conref"),
            ("conkeyref", "conkeyref"),
            ("conrefend", "conrefend"),
            ("conaction", "conaction"),
        ):
            if node.get(field_name):
                el.set(attr_name, node[field_name])
        self._set_attrs(el, node.get("attrs", {}))
        self._append_content(el, node.get("content", []))
        return el

    def _image_node_to_element(self, node: dict[str, Any]) -> Any:
        el = etree.Element("image")
        el.set("class", node["classChain"][0])
        self._set_attrs(el, node.get("attrs", {}))
        if node.get("alt"):
            alt_el = etree.SubElement(el, "alt")
            alt_el.set("class", "- topic/alt ")
            self._append_content(alt_el, node["alt"])
        if node.get("longdescref"):
            ld = node["longdescref"]
            ld_el = etree.SubElement(el, "longdescref")
            ld_el.set("class", "- topic/longdescref ")
            for attr_name in ("href", "keyref", "format"):
                if ld.get(attr_name):
                    ld_el.set(attr_name, ld[attr_name])
        return el

    # -- Topic envelope ------------------------------------------------

    def _topic_node_to_element(self, node: dict[str, Any]) -> Any:
        el = etree.Element(node["type"])
        el.set("class", node["classChain"][0])
        self._set_attrs(el, node.get("attrs", {}))
        if node.get("title"):
            el.append(self._named_field_to_element(node["title"]))
        for field_name in ("shortdesc", "abstract", "prolog"):
            if node.get(field_name):
                el.append(self._named_field_to_element(node[field_name]))
        if node.get("body"):
            el.append(self._named_field_to_element(node["body"]))
        if node.get("related_links"):
            el.append(self._named_field_to_element(node["related_links"]))
        for nested in node.get("nested", []):
            el.append(self._topic_node_to_element(nested))
        return el

    def _named_field_to_element(self, node: dict[str, Any]) -> Any:
        el = etree.Element(node["type"])
        el.set("class", node["classChain"][0])
        self._set_attrs(el, node.get("attrs", {}))
        self._append_content(el, node.get("content", []))
        return el

    # -- Map envelope ----------------------------------------------------

    def _map_node_to_element(self, node: dict[str, Any]) -> Any:
        el = etree.Element(node["type"])
        el.set("class", node["classChain"][0])
        attrs = dict(node.get("attrs", {}))
        if node.get("keyscope"):
            attrs = {**attrs, "keyscope": " ".join(node["keyscope"])}
        self._set_attrs(el, attrs)
        if node.get("title"):
            title_el = etree.SubElement(el, "title")
            title_el.set("class", "- map/title ")
            self._append_content(title_el, node["title"])
        if node.get("booktitle"):
            el.append(self._named_field_to_element(node["booktitle"]))
        if node.get("topicmeta"):
            el.append(self._named_field_to_element(node["topicmeta"]))
        for keydef in node.get("keydefs", []):
            el.append(self._topicref_node_to_element(keydef))
        if _is_bookmap_shaped(node):
            # bookmap.content requires reltable* strictly last, after every
            # frontmatter/chapter/part/appendix/backmatter division
            # (confirmed against the vendored grammar) -- the reverse of
            # the order used below, which is harmless for plain map since
            # map.content freely interleaves reltable/topicref with no
            # fixed relative position required.
            for topicref in node.get("topicrefs", []):
                el.append(self._topicref_node_to_element(topicref))
            for reltable in node.get("reltables", []):
                el.append(self._reltable_to_element(reltable))
        else:
            for reltable in node.get("reltables", []):
                el.append(self._reltable_to_element(reltable))
            for topicref in node.get("topicrefs", []):
                el.append(self._topicref_node_to_element(topicref))
        return el

    # -- Topicref tree --------------------------------------------------

    def _topicref_node_to_element(self, node: dict[str, Any]) -> Any:
        tag = "keydef" if node.get("resourceOnly") and node["type"] == "keydef" else node["type"]
        el = etree.Element(tag)
        el.set("class", node["classChain"][0])
        attrs = dict(node.get("attrs", {}))
        if node.get("href"):
            attrs["href"] = node["href"]
        if node.get("keyref"):
            attrs["keyref"] = node["keyref"]
        if node.get("keys"):
            attrs["keys"] = " ".join(node["keys"])
        if node.get("keyscope"):
            attrs["keyscope"] = " ".join(node["keyscope"])
        if node.get("resourceOnly"):
            attrs["processing-role"] = "resource-only"
        self._set_attrs(el, attrs)
        if node.get("topicmeta"):
            el.append(self._named_field_to_element(node["topicmeta"]))
        for ditavalref in node.get("ditavalrefs", []):
            el.append(self._ditavalref_node_to_element(ditavalref))
        for child in node.get("children", []):
            el.append(self._topicref_node_to_element(child))
        return el

    def _ditavalref_node_to_element(self, node: dict[str, Any]) -> Any:
        el = etree.Element("ditavalref")
        el.set("class", node["classChain"][0])
        attrs = dict(node.get("attrs", {}))
        if node.get("href"):
            attrs["href"] = node["href"]
        if node.get("keyref"):
            attrs["keyref"] = node["keyref"]
        self._set_attrs(el, attrs)
        # dvr* are dedicated node fields, not part of DtfAttrs/_set_attrs's
        # ATTR_ORDER, so they're written directly.
        for field_name in (
            "dvrResourcePrefix",
            "dvrResourceSuffix",
            "dvrKeyscopePrefix",
            "dvrKeyscopeSuffix",
        ):
            if node.get(field_name):
                el.set(field_name, node[field_name])
        return el

    # -- Tables: CALS -----------------------------------------------------

    def _table_node_to_element(self, node: dict[str, Any]) -> Any:
        el = etree.Element("table")
        el.set("class", node["classChain"][0])
        self._set_attrs(el, node.get("attrs", {}))
        if node.get("title"):
            title_el = etree.SubElement(el, "title")
            title_el.set("class", "- topic/title ")
            self._append_content(title_el, node["title"])
        if node.get("desc"):
            desc_el = etree.SubElement(el, "desc")
            desc_el.set("class", "- topic/desc ")
            self._append_content(desc_el, node["desc"])
        for tgroup in node.get("tgroups", []):
            el.append(self._tgroup_to_element(tgroup))
        return el

    def _tgroup_to_element(self, node: dict[str, Any]) -> Any:
        el = etree.Element("tgroup")
        el.set("class", node["classChain"][0])
        self._set_attrs(el, node.get("attrs", {}))
        for colspec in node.get("colspecs", []):
            el.append(self._leaf_to_element(colspec))
        for spanspec in node.get("spanspecs", []):
            el.append(self._leaf_to_element(spanspec))
        for section_name in ("thead", "tbody", "tfoot"):
            if node.get(section_name):
                el.append(self._table_section_to_element(node[section_name]))
        # @cols is REQUIRED by the CALS table model (confirmed: the vendored
        # RELAX NG grammar rejects a tgroup with no cols attribute at all --
        # "Expecting element topic, got body" is libxml2's confusing way of
        # reporting that the *table*, several levels down, failed to match,
        # since RelaxNG error messages point at the nearest ancestor still
        # being matched, not the actual mismatch site). Always recomputed
        # here rather than trusting whatever's in `attrs`: xephon-cms's table
        # editor (tableEditing.ts) never writes a cols value at all when
        # inserting/deleting columns (colname/cols/etc. are plain passthrough
        # attrs there, not dedicated fields it keeps in sync), so an
        # `attrs["cols"]` surviving from import would silently go stale the
        # moment a column is added or removed -- computing it fresh from the
        # actual column count is correct in both the "never had one" and
        # "had a now-stale one" cases. colspecs.length is authoritative once
        # any exist (tableEditing.ts backfills one colspec per real column);
        # the first row's own entry count is the fallback for a tgroup with
        # zero colspecs, which "colspec* thead? tbody" permits.
        el.set("cols", str(self._tgroup_cols(node)))
        return el

    def _tgroup_cols(self, node: dict[str, Any]) -> int:
        colspecs = node.get("colspecs", [])
        if colspecs:
            return len(colspecs)
        for section_name in ("thead", "tbody"):
            section = node.get(section_name)
            rows = section.get("rows", []) if section else []
            if rows:
                return len(rows[0].get("entries", []))
        return 1

    def _leaf_to_element(self, node: dict[str, Any]) -> Any:
        el = etree.Element(node["type"])
        el.set("class", node["classChain"][0])
        self._set_attrs(el, node.get("attrs", {}))
        return el

    def _table_section_to_element(self, node: dict[str, Any]) -> Any:
        el = etree.Element(node["type"])
        el.set("class", node["classChain"][0])
        self._set_attrs(el, node.get("attrs", {}))
        for row in node.get("rows", []):
            el.append(self._row_to_element(row))
        return el

    def _row_to_element(self, node: dict[str, Any]) -> Any:
        el = etree.Element("row")
        el.set("class", node["classChain"][0])
        self._set_attrs(el, node.get("attrs", {}))
        for entry in node.get("entries", []):
            entry_el = etree.SubElement(el, "entry")
            entry_el.set("class", entry["classChain"][0])
            self._set_attrs(entry_el, entry.get("attrs", {}))
            self._append_content(entry_el, entry.get("content", []))
        return el

    # -- Tables: simple ----------------------------------------------------

    def _simpletable_node_to_element(self, node: dict[str, Any]) -> Any:
        el = etree.Element("simpletable")
        el.set("class", node["classChain"][0])
        self._set_attrs(el, node.get("attrs", {}))
        if node.get("sthead"):
            el.append(self._strow_to_element(node["sthead"]))
        for strow in node.get("strows", []):
            el.append(self._strow_to_element(strow))
        return el

    def _strow_to_element(self, node: dict[str, Any]) -> Any:
        el = etree.Element(node["type"])
        el.set("class", node["classChain"][0])
        self._set_attrs(el, node.get("attrs", {}))
        for entry in node.get("entries", []):
            entry_el = etree.SubElement(el, entry["type"])
            entry_el.set("class", entry["classChain"][0])
            self._set_attrs(entry_el, entry.get("attrs", {}))
            self._append_content(entry_el, entry.get("content", []))
        return el

    # -- Relationship tables -----------------------------------------------

    def _reltable_to_element(self, node: dict[str, Any]) -> Any:
        el = etree.Element("reltable")
        el.set("class", node["classChain"][0])
        self._set_attrs(el, node.get("attrs", {}))
        if node.get("relheader"):
            header = node["relheader"]
            header_el = etree.SubElement(el, "relheader")
            header_el.set("class", header["classChain"][0])
            self._set_attrs(header_el, header.get("attrs", {}))
            for colspec in header.get("relcolspecs", []):
                header_el.append(self._leaf_to_element(colspec))
        for relrow in node.get("relrows", []):
            relrow_el = etree.SubElement(el, "relrow")
            relrow_el.set("class", relrow["classChain"][0])
            self._set_attrs(relrow_el, relrow.get("attrs", {}))
            for relcell in relrow.get("relcells", []):
                cell_el = etree.SubElement(relrow_el, "relcell")
                cell_el.set("class", relcell["classChain"][0])
                self._set_attrs(cell_el, relcell.get("attrs", {}))
                self._append_content(cell_el, relcell.get("content", []))
        return el
