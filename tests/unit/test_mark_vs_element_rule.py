"""spec/DITAFLOW-SPEC.md §4.1: b/i/u/sup/sub/tt collapse into a Mark only
when their entire content is text with no element children."""

from __future__ import annotations

from ditaflow.converter.dita_parser import DitaParser

TOPIC_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<topic id="t1"><title>T</title><body><p>{body}</p></body></topic>
"""


def _parse_body_content(xml_fragment: str) -> list[dict]:
    xml = TOPIC_TEMPLATE.format(body=xml_fragment)
    result = DitaParser().parse_string(xml)
    return result.document["root"]["body"]["content"][0]["content"]


def test_pure_text_bold_collapses_to_mark() -> None:
    content = _parse_body_content("<b>important</b>")
    assert content == [{"type": "text", "text": "important", "marks": [{"type": "b"}]}]


def test_nested_marks_collapse_innermost_first() -> None:
    content = _parse_body_content("<b><i>both</i></b>")
    assert content == [{"type": "text", "text": "both", "marks": [{"type": "i"}, {"type": "b"}]}]


def test_mark_with_element_child_stays_generic_element() -> None:
    content = _parse_body_content('<b><xref href="other.dita"/></b>')
    assert len(content) == 1
    b_node = content[0]
    assert b_node["type"] == "b"
    assert b_node["baseType"] == "ph"
    assert "marks" not in b_node
    assert "_markCandidate" not in b_node
    assert b_node["content"][0]["type"] == "xref"
    assert b_node["content"][0]["attrs"]["href"] == "other.dita"
