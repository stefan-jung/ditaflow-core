"""Unit tests for relaxng_validator.py -- real RELAX NG validation against
the vendored DITA 1.3 grammars, as opposed to content_model.py's
deliberately approximate, hand-written check.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ditaflow.converter.dita_parser import DitaParser
from ditaflow.converter.dita_serializer import DtfSerializer
from ditaflow.validator.relaxng_validator import RelaxNgValidator

FIXTURES_DIR = Path(__file__).parent.parent / "round_trip" / "fixtures" / "dita"

_MINIMAL_TOPIC_XML = """\
<topic class="- topic/topic " id="t1">
  <title class="- topic/title ">Hello</title>
  <body class="- topic/body ">
    <p class="- topic/p ">Some text.</p>
  </body>
</topic>"""

_MINIMAL_MAP_XML = """\
<map class="- map/map " id="m1">
  <title class="- map/title ">A map</title>
  <topicref class="- map/topicref " href="topics/install.dita"/>
</map>"""


def _serialize_fixture(name: str) -> str:
    xml_path = FIXTURES_DIR / name
    parser = DitaParser()
    document = parser.parse_string(
        xml_path.read_text(encoding="utf-8"), source_uri=str(xml_path), base_dir=FIXTURES_DIR
    ).document
    return DtfSerializer().serialize(document).xml


def test_supports_the_in_scope_doctypes() -> None:
    validator = RelaxNgValidator()
    for doctype in (
        "topic",
        "concept",
        "task",
        "reference",
        "map",
        "bookmap",
        "glossentry",
        "glossgroup",
        "troubleshooting",
        "learningContent",
        "learningOverview",
        "learningAssessment",
        "learningPlan",
        "learningSummary",
        "learningMap",
        "learningGroupMap",
        "learningObjectMap",
        "learningBookmap",
    ):
        assert validator.supports(doctype)
    for doctype in ("ditavalref", "subjectScheme", ""):
        assert not validator.supports(doctype)


def test_unsupported_doctype_returns_a_descriptive_error_not_a_crash() -> None:
    result = RelaxNgValidator().validate(_MINIMAL_TOPIC_XML, "subjectScheme")
    assert result.is_valid is False
    assert "subjectScheme" in result.errors[0]


def test_minimal_topic_validates_clean() -> None:
    result = RelaxNgValidator().validate(_MINIMAL_TOPIC_XML, "topic")
    assert result.errors == []
    assert result.is_valid is True


def test_minimal_map_validates_clean() -> None:
    result = RelaxNgValidator().validate(_MINIMAL_MAP_XML, "map")
    assert result.errors == []


@pytest.mark.parametrize(
    ("fixture_name", "doctype"),
    [
        ("concept_with_conref.dita", "concept"),
        ("reference_with_tables.dita", "reference"),
        ("simple_task.dita", "task"),
    ],
)
def test_real_fixtures_round_tripped_through_the_serializer_validate_clean(
    fixture_name: str, doctype: str
) -> None:
    xml = _serialize_fixture(fixture_name)
    result = RelaxNgValidator().validate(xml, doctype)
    assert result.errors == [], f"{fixture_name}: {result.errors}"


def test_catches_a_violation_content_model_checker_is_documented_to_miss() -> None:
    """ContentModelChecker is keyed by baseType, not literal element name, so
    it can't tell <ul><step> apart from <ul><li> (step's baseType is "li",
    which IS allowed inside ul in its lenient table -- see that module's
    docstring). The real DITA grammar rejects a literal <step> outside a
    task's <steps>. This is the concrete "real value added" case.
    """
    xml = """\
<topic class="- topic/topic " id="t1">
  <title class="- topic/title ">T</title>
  <body class="- topic/body ">
    <ul class="- topic/ul ">
      <step class="- topic/li task/step "><cmd class="- topic/ph task/cmd ">x</cmd></step>
    </ul>
  </body>
</topic>"""
    result = RelaxNgValidator().validate(xml, "topic")
    assert result.is_valid is False
    assert result.errors  # non-empty; exact libxml2 message text isn't load-bearing


_MINIMAL_BOOKMAP_XML = """\
<bookmap class="- map/map bookmap/bookmap " id="b1">
  <title class="- topic/title bookmap/title ">A book</title>
</bookmap>"""

_MINIMAL_GLOSSENTRY_XML = """\
<glossentry class="- topic/topic concept/concept glossentry/glossentry " id="g1">
  <glossterm class="- topic/keyword glossentry/glossterm ">Widget</glossterm>
</glossentry>"""

_MINIMAL_TROUBLESHOOTING_XML = """\
<troubleshooting class="- topic/topic troubleshooting/troubleshooting " id="ts1">
  <title class="- topic/title ">Won't turn on</title>
</troubleshooting>"""

_MINIMAL_LEARNING_CONTENT_XML = """\
<learningContent
    class="- topic/topic learningBase/learningBase learningContent/learningContent "
    id="lc1">
  <title class="- topic/title ">Lesson 1</title>
  <learningContentbody
      class="- topic/body learningBase/learningBase-body learningContentbody/learningContentbody "/>
</learningContent>"""


@pytest.mark.parametrize(
    ("xml", "doctype"),
    [
        (_MINIMAL_BOOKMAP_XML, "bookmap"),
        (_MINIMAL_GLOSSENTRY_XML, "glossentry"),
        (_MINIMAL_TROUBLESHOOTING_XML, "troubleshooting"),
        (_MINIMAL_LEARNING_CONTENT_XML, "learningContent"),
    ],
)
def test_minimal_expanded_domain_fixtures_validate_clean(xml: str, doctype: str) -> None:
    result = RelaxNgValidator().validate(xml, doctype)
    assert result.errors == [], f"{doctype}: {result.errors}"


def test_invalid_nesting_inside_a_simpletable_is_caught() -> None:
    xml = """\
<topic class="- topic/topic " id="t1">
  <title class="- topic/title ">T</title>
  <body class="- topic/body ">
    <simpletable class="- topic/simpletable ">
      <strow class="- topic/strow ">
        <p class="- topic/p ">A bare p directly in strow, not stentry.</p>
      </strow>
    </simpletable>
  </body>
</topic>"""
    result = RelaxNgValidator().validate(xml, "topic")
    assert result.is_valid is False
