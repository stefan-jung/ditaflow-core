"""_keyscopePath computation (spec/DITAFLOW-SPEC.md §6): each keyscope name
is joined to its parent's qualified path with '.', narrowest scope last."""

from __future__ import annotations

from ditaflow.converter.dita_parser import DitaParser

BOOKMAP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<bookmap id="m1" keyscope="manual">
  <title>M</title>
  <chapter href="installation.dita" keyscope="server-edition">
    <topicref href="install-configure.dita"/>
  </chapter>
  <chapter href="other.dita">
    <topicref href="other-child.dita" keyscope="addon"/>
  </chapter>
</bookmap>
"""


def _topicrefs() -> list[dict]:
    return DitaParser().parse_string(BOOKMAP_XML).document["root"]["topicrefs"]


def test_root_keyscope_seeds_the_path() -> None:
    chapter = _topicrefs()[0]
    assert chapter["keyscope"] == ["server-edition"]
    assert chapter["_keyscopePath"] == ["manual", "manual.server-edition"]


def test_child_without_own_keyscope_inherits_parent_path() -> None:
    child = _topicrefs()[0]["children"][0]
    assert child["keyscope"] == []
    assert child["_keyscopePath"] == ["manual", "manual.server-edition"]


def test_sibling_chapter_without_keyscope_keeps_only_root_path() -> None:
    chapter = _topicrefs()[1]
    assert chapter["keyscope"] == []
    assert chapter["_keyscopePath"] == ["manual"]


def test_nested_keyscope_qualifies_against_nearest_ancestor() -> None:
    child = _topicrefs()[1]["children"][0]
    assert child["keyscope"] == ["addon"]
    assert child["_keyscopePath"] == ["manual", "manual.addon"]
