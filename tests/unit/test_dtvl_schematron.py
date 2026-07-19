"""Tests for the DTVL ↔ Schematron bridge."""

from __future__ import annotations

from ditaflow.dtvl import DtvlEngine, DtvlRuleset, export_schematron, import_schematron
from ditaflow.dtvl.model import DtvlFixType, DtvlSeverity

_MINIMAL_SCH = """<?xml version="1.0" encoding="UTF-8"?>
<schema xmlns="http://purl.oclc.org/dsdl/schematron"
        xmlns:sqf="http://www.schematron-quickfix.com/validator/process"
        id="dita-authoring" defaultPhase="authoring">
  <title>DITA Authoring Rules</title>

  <phase id="authoring">
    <active pattern="titles"/>
  </phase>

  <phase id="full">
    <active pattern="titles"/>
    <active pattern="structure"/>
  </phase>

  <pattern id="titles">
    <title>Title constraints</title>
    <rule context="title">
      <assert test="string-length(.) &gt; 0" id="non-empty-title">
        Title must not be empty.
      </assert>
      <report test="@translate = 'no'" role="warning">
        Title has translate=no — verify this is intentional.
      </report>
    </rule>
  </pattern>

  <pattern id="structure">
    <rule context="topic">
      <assert test="shortdesc" role="warning">
        Topic should have a shortdesc.
      </assert>
      <assert test="@id">
        Topic must have an id attribute.
      </assert>
    </rule>
  </pattern>
</schema>"""


_SQF_SCH = """<?xml version="1.0" encoding="UTF-8"?>
<schema xmlns="http://purl.oclc.org/dsdl/schematron"
        xmlns:sqf="http://www.schematron-quickfix.com/validator/process">
  <pattern id="terms">
    <rule context="p">
      <assert test="string-length(.) &gt; 0"
              sqf:fix="fix-empty-p" id="non-empty-p">
        Paragraph must not be empty.
      </assert>
    </rule>
  </pattern>
  <sqf:fix id="fix-empty-p">
    <title>Delete empty paragraph</title>
    <sqf:delete/>
  </sqf:fix>
</schema>"""


_COMPLEX_CONTEXT_SCH = """<?xml version="1.0" encoding="UTF-8"?>
<schema xmlns="http://purl.oclc.org/dsdl/schematron">
  <pattern id="complex">
    <rule context="section[ancestor::body]">
      <assert test="title">Section must have a title.</assert>
    </rule>
  </pattern>
</schema>"""


# ── Import tests ──────────────────────────────────────────────────────────────


def test_import_title_phases() -> None:
    ruleset = import_schematron(_MINIMAL_SCH)
    assert ruleset.id == "dita-authoring"
    assert ruleset.title == "DITA Authoring Rules"
    assert len(ruleset.phases) == 2
    phase_ids = {ph.id for ph in ruleset.phases}
    assert "authoring" in phase_ids
    assert "full" in phase_ids


def test_import_patterns_and_rules() -> None:
    ruleset = import_schematron(_MINIMAL_SCH)
    assert len(ruleset.patterns) == 2
    titles = next(p for p in ruleset.patterns if p.id == "titles")
    assert len(titles.rules) == 1
    rule = titles.rules[0]
    assert "has_text" in rule.assertions[0].test or "len" in rule.assertions[0].test
    assert rule.assertions[0].id == "non-empty-title"
    assert rule.reports[0].severity == DtvlSeverity.warning


def test_import_attribute_presence_test() -> None:
    ruleset = import_schematron(_MINIMAL_SCH)
    structure = next(p for p in ruleset.patterns if p.id == "structure")
    rule = structure.rules[0]
    # @id → has_attr assertion
    id_assertion = next(a for a in rule.assertions if "id" in a.test)
    assert "has_attr" in id_assertion.test


def test_import_child_existence_test() -> None:
    ruleset = import_schematron(_MINIMAL_SCH)
    structure = next(p for p in ruleset.patterns if p.id == "structure")
    rule = structure.rules[0]
    # shortdesc → has_child_of_type assertion
    shortdesc_assertion = next(a for a in rule.assertions if "shortdesc" in a.test)
    assert "shortdesc" in shortdesc_assertion.test


def test_import_sqf_fix_delete() -> None:
    ruleset = import_schematron(_SQF_SCH)
    pattern = ruleset.patterns[0]
    assertion = pattern.rules[0].assertions[0]
    assert assertion.fix is not None
    assert assertion.fix.type == DtvlFixType.delete_node


def test_import_complex_context_uses_lxml_xpath() -> None:
    ruleset = import_schematron(_COMPLEX_CONTEXT_SCH)
    rule = ruleset.patterns[0].rules[0]
    # Complex XPath cannot be converted — lxml_xpath must be set
    assert rule.lxml_xpath is not None
    assert "section" in rule.lxml_xpath


# ── Export tests ──────────────────────────────────────────────────────────────


def test_export_produces_valid_xml() -> None:
    from lxml import etree

    ruleset = import_schematron(_MINIMAL_SCH)
    sch_out = export_schematron(ruleset)
    # Must be parseable XML
    root = etree.fromstring(sch_out.encode())
    assert root is not None


def test_export_preserves_pattern_ids() -> None:
    ruleset = import_schematron(_MINIMAL_SCH)
    sch_out = export_schematron(ruleset)
    assert 'id="titles"' in sch_out
    assert 'id="structure"' in sch_out


def test_export_preserves_assertion_messages() -> None:
    ruleset = import_schematron(_MINIMAL_SCH)
    sch_out = export_schematron(ruleset)
    assert "Title must not be empty" in sch_out


# ── Round-trip: sch → ruleset → sch ──────────────────────────────────────────


def test_schematron_roundtrip_runs_against_dtf() -> None:
    """Imported rules should fire correctly when validated against a DTF document."""
    ruleset = import_schematron(_MINIMAL_SCH)
    engine = DtvlEngine(ruleset)

    valid_topic = {
        "baseType": "topic",
        "attrs": {"id": "t1"},
        "children": [
            {"baseType": "title", "children": ["My Title"]},
            {"baseType": "shortdesc", "children": ["Brief description."]},
            {"baseType": "body", "children": []},
        ],
    }
    result = engine.validate(valid_topic)
    assert result.is_valid

    invalid_topic = {
        "baseType": "topic",
        "attrs": {},  # no id
        "children": [
            {"baseType": "title", "children": []},  # empty title
            {"baseType": "body", "children": []},
        ],
    }
    result2 = engine.validate(invalid_topic)
    assert not result2.is_valid
    messages = {m.assertion_id for m in result2.errors()}
    assert "non-empty-title" in messages


# ── DTVL → Schematron export of native DTVL rules ─────────────────────────────


def test_export_native_dtvl_ruleset() -> None:
    yaml_src = """
id: export-test
title: Export Test
patterns:
  - id: titles
    rules:
      - id: title-not-empty
        context: "baseType == 'title'"
        assertions:
          - test: "has_text(node)"
            message: Title must not be empty
            severity: error
        reports:
          - test: "word_count(node) > 10"
            message: Title is long
            severity: warning
"""
    ruleset = DtvlRuleset.from_yaml(yaml_src)
    sch_out = export_schematron(ruleset)

    from lxml import etree

    root = etree.fromstring(sch_out.encode())
    assert root.get("id") == "export-test"

    # The context "baseType == 'title'" should map back to XPath "title"
    rules = root.findall(".//{http://purl.oclc.org/dsdl/schematron}rule")
    assert any(r.get("context") == "title" for r in rules)
