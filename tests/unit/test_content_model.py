from __future__ import annotations

from typing import Any

from ditaflow.converter.specialisation_registry import _CORE_PROFILE
from ditaflow.validator.content_model import (
    ALLOWED_CHILDREN,
    KNOWN_BASE_TYPES,
    ContentModelChecker,
)


def _node(node_type: str, base_type: str, content: list[Any] | None = None, **extra: Any) -> dict:
    return {
        "type": node_type,
        "baseType": base_type,
        "attrs": {},
        "content": content or [],
        **extra,
    }


def _text(value: str) -> dict:
    return {"type": "text", "text": value}


def test_known_base_types_matches_the_registry() -> None:
    # Catches drift between this module's hand-maintained list and the
    # registry it's meant to describe.
    assert frozenset(e.base_element for e in _CORE_PROFILE) == KNOWN_BASE_TYPES


def test_allowed_children_keys_are_a_subset_of_known_base_types() -> None:
    assert set(ALLOWED_CHILDREN) <= KNOWN_BASE_TYPES


def test_valid_section_with_title_note_and_list_has_no_errors() -> None:
    doc = {
        "root": _node(
            "topic",
            "topic",
            content=[],
            body=_node(
                "body",
                "body",
                content=[
                    _node(
                        "section",
                        "section",
                        content=[
                            _node("title", "title", content=[_text("Overview")]),
                            _node("p", "p", content=[_text("Details.")]),
                            _node(
                                "note",
                                "note",
                                content=[_node("p", "p", content=[_text("Careful.")])],
                            ),
                            _node("ul", "ul", content=[_node("li", "li", content=[_text("x")])]),
                        ],
                    )
                ],
            ),
        )
    }
    assert ContentModelChecker().validate(doc) == []


def test_specialisation_inherits_its_base_elements_rules() -> None:
    # steps/step share baseType ol/li with ol/li themselves -- this is the
    # whole point of keying the table by baseType, not element name.
    doc = {
        "root": _node(
            "topic",
            "topic",
            body=_node(
                "body",
                "body",
                content=[
                    _node(
                        "steps",
                        "ol",
                        content=[_node("step", "li", content=[_text("Do the thing.")])],
                    )
                ],
            ),
        )
    }
    assert ContentModelChecker().validate(doc) == []


def test_flags_a_block_element_in_the_wrong_container() -> None:
    doc = {
        "root": _node(
            "topic",
            "topic",
            body=_node(
                "body",
                "body",
                # A bare 'p' (baseType p) directly inside 'ul' (only 'li' allowed).
                content=[_node("ul", "ul", content=[_node("p", "p", content=[_text("x")])])],
            ),
        )
    }
    errors = ContentModelChecker().validate(doc)
    assert len(errors) == 1
    assert "'p'" in errors[0]
    assert "'ul'" in errors[0]


def test_inline_elements_are_always_allowed_in_block_content() -> None:
    doc = {
        "root": _node(
            "topic",
            "topic",
            body=_node(
                "body",
                "body",
                # Text and an inline 'xref' as direct children of body --
                # unusual DITA, but inline content is never block-flagged.
                content=[_text("loose text"), _node("xref", "xref", content=[])],
            ),
        )
    }
    assert ContentModelChecker().validate(doc) == []


def test_unmodeled_base_types_children_are_not_checked() -> None:
    # 'table' (CALS) has no ALLOWED_CHILDREN entry -- deliberately
    # deferred, so its children pass unchecked, not flagged as a gap.
    # Used as the document root here specifically to isolate that case
    # from "is 'table' itself allowed as someone's child" (it currently
    # isn't, body's allowed set doesn't include the deferred CALS table --
    # a separate, correctly-flagged concern, not what this test is about).
    doc = {"root": _node("table", "table", content=[_node("note", "note", content=[])])}
    assert ContentModelChecker().validate(doc) == []


def test_simpletable_sthead_and_strow_use_their_dedicated_keys() -> None:
    doc = {
        "root": _node(
            "topic",
            "topic",
            body=_node(
                "body",
                "body",
                content=[
                    {
                        "type": "simpletable",
                        "baseType": "simpletable",
                        "attrs": {},
                        "sthead": _node("sthead", "sthead", content=[]),
                        "strows": [
                            {
                                "type": "strow",
                                "baseType": "strow",
                                "attrs": {},
                                "entries": [_node("stentry", "stentry", content=[_text("cell")])],
                            }
                        ],
                    }
                ],
            ),
        )
    }
    assert ContentModelChecker().validate(doc) == []


def test_is_valid_mirrors_validate() -> None:
    valid_doc = {"root": _node("topic", "topic", body=_node("body", "body", content=[]))}
    checker = ContentModelChecker()
    assert checker.is_valid(valid_doc) is True

    invalid_doc = {
        "root": _node(
            "topic",
            "topic",
            body=_node(
                "body",
                "body",
                content=[_node("ul", "ul", content=[_node("p", "p", content=[])])],
            ),
        )
    }
    assert checker.is_valid(invalid_doc) is False
