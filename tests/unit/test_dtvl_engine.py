"""Tests for the DTVL engine — context matching, assertions, reports, phases."""

from __future__ import annotations

import pytest

from ditaflow.dtvl import (
    DtvlAssertion,
    DtvlEngine,
    DtvlFix,
    DtvlFixType,
    DtvlPattern,
    DtvlPhase,
    DtvlReport,
    DtvlRule,
    DtvlRuleset,
    DtvlSeverity,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _topic(title: str = "Test Topic", body_text: str = "Some body text.") -> dict:
    return {
        "dtf": "ditaflow",
        "dtfVersion": "1.0.0",
        "baseDoctype": "topic",
        "doctype": "topic",
        "baseType": "topic",
        "attrs": {"id": "test-topic"},
        "children": [
            {"baseType": "title", "children": [title]},
            {
                "baseType": "body",
                "children": [{"baseType": "p", "children": [body_text]}],
            },
        ],
    }


def _topic_empty_title() -> dict:
    return {
        "baseDoctype": "topic",
        "doctype": "topic",
        "baseType": "topic",
        "attrs": {},
        "children": [
            {"baseType": "title", "children": []},
            {"baseType": "body", "children": []},
        ],
    }


# ── Context matching ──────────────────────────────────────────────────────────


def test_context_base_type_match() -> None:
    ruleset = DtvlRuleset(
        patterns=[
            DtvlPattern(
                id="titles",
                rules=[
                    DtvlRule(
                        context="baseType == 'title'",
                        assertions=[
                            DtvlAssertion(test="len(children) > 0", message="Title is empty")
                        ],
                    )
                ],
            )
        ]
    )
    engine = DtvlEngine(ruleset)
    result = engine.validate(_topic("Hello"))
    assert result.is_valid
    assert result.error_count == 0


def test_context_no_match_skips_assertions() -> None:
    ruleset = DtvlRuleset(
        patterns=[
            DtvlPattern(
                id="maps",
                rules=[
                    DtvlRule(
                        context="baseType == 'map'",
                        assertions=[DtvlAssertion(test="False", message="Should not fire")],
                    )
                ],
            )
        ]
    )
    engine = DtvlEngine(ruleset)
    result = engine.validate(_topic())
    assert result.is_valid


# ── Assertion failures ────────────────────────────────────────────────────────


def test_assertion_fires_on_empty_title() -> None:
    ruleset = DtvlRuleset(
        patterns=[
            DtvlPattern(
                id="titles",
                rules=[
                    DtvlRule(
                        context="baseType == 'title'",
                        assertions=[
                            DtvlAssertion(
                                id="non-empty-title",
                                test="len(children) > 0",
                                message="Title must not be empty",
                            )
                        ],
                    )
                ],
            )
        ]
    )
    engine = DtvlEngine(ruleset)
    result = engine.validate(_topic_empty_title())
    assert not result.is_valid
    assert result.error_count == 1
    msg = result.messages[0]
    assert msg.type == "assert"
    assert msg.assertion_id == "non-empty-title"
    assert "Title must not be empty" in msg.message
    assert msg.severity == DtvlSeverity.error


def test_report_fires_when_test_is_true() -> None:
    ruleset = DtvlRuleset(
        patterns=[
            DtvlPattern(
                id="lengths",
                rules=[
                    DtvlRule(
                        context="baseType == 'title'",
                        reports=[
                            DtvlReport(
                                test="word_count(node) > 3",
                                message="Title is long",
                                severity=DtvlSeverity.warning,
                            )
                        ],
                    )
                ],
            )
        ]
    )
    engine = DtvlEngine(ruleset)
    result = engine.validate(_topic("This Is A Very Long Title Here"))
    assert result.is_valid  # only warning
    assert result.warning_count == 1
    assert result.messages[0].type == "report"


# ── Message template formatting ───────────────────────────────────────────────


def test_message_template_word_count() -> None:
    ruleset = DtvlRuleset(
        patterns=[
            DtvlPattern(
                id="lengths",
                rules=[
                    DtvlRule(
                        context="baseType == 'title'",
                        reports=[
                            DtvlReport(
                                test="word_count(node) > 3",
                                message="Title has {word_count(node)} words",
                            )
                        ],
                    )
                ],
            )
        ]
    )
    engine = DtvlEngine(ruleset)
    result = engine.validate(_topic("One Two Three Four Five"))
    assert result.warning_count == 1
    assert "5" in result.messages[0].message


# ── Quick-fix attachment ──────────────────────────────────────────────────────


def test_fix_attached_to_failing_message() -> None:
    fix = DtvlFix(type=DtvlFixType.ai, prompt="Write a title for this topic")
    ruleset = DtvlRuleset(
        patterns=[
            DtvlPattern(
                id="titles",
                rules=[
                    DtvlRule(
                        context="baseType == 'title'",
                        assertions=[
                            DtvlAssertion(
                                test="len(children) > 0",
                                message="Title is empty",
                                fix=fix,
                            )
                        ],
                    )
                ],
            )
        ]
    )
    engine = DtvlEngine(ruleset)
    result = engine.validate(_topic_empty_title())
    assert result.messages[0].fix is not None
    assert result.messages[0].fix.type == DtvlFixType.ai


# ── Phase filtering ───────────────────────────────────────────────────────────


def test_phase_filters_patterns() -> None:
    ruleset = DtvlRuleset(
        patterns=[
            DtvlPattern(
                id="authoring",
                rules=[
                    DtvlRule(
                        context="baseType == 'title'",
                        assertions=[DtvlAssertion(test="False", message="authoring")],
                    )
                ],
            ),
            DtvlPattern(
                id="publish",
                rules=[
                    DtvlRule(
                        context="baseType == 'p'",
                        assertions=[DtvlAssertion(test="False", message="publish")],
                    )
                ],
            ),
        ],
        phases=[
            DtvlPhase(id="authoring-only", active_patterns=["authoring"]),
        ],
    )
    engine = DtvlEngine(ruleset)

    # Only "authoring" pattern fires
    result = engine.validate(_topic(), phase="authoring-only")
    messages = result.messages
    assert all(m.message == "authoring" for m in messages)

    # #ALL fires both
    result_all = engine.validate(_topic(), phase="#ALL")
    msgs_all = {m.message for m in result_all.messages}
    assert "authoring" in msgs_all
    assert "publish" in msgs_all


# ── Abstract rule extension ───────────────────────────────────────────────────


def test_abstract_rule_extension() -> None:
    ruleset = DtvlRuleset(
        patterns=[
            DtvlPattern(
                id="base",
                abstract=True,
                rules=[
                    DtvlRule(
                        id="base-rule",
                        context="True",
                        abstract=True,
                        assertions=[
                            DtvlAssertion(test="isinstance(node, dict)", message="base check")
                        ],
                    )
                ],
            ),
            DtvlPattern(
                id="concrete",
                rules=[
                    DtvlRule(
                        context="baseType == 'title'",
                        extends="base-rule",
                        assertions=[DtvlAssertion(test="len(children) > 0", message="title check")],
                    )
                ],
            ),
        ]
    )
    engine = DtvlEngine(ruleset)
    result = engine.validate(_topic_empty_title())
    # base assertion passes (isinstance(dict)), concrete assertion fails
    # (empty title)
    assert result.error_count == 1
    assert result.messages[0].message == "title check"


# ── YAML round-trip ───────────────────────────────────────────────────────────


def test_ruleset_yaml_roundtrip() -> None:
    yaml_src = """
id: test-rules
title: Test Rules
default_phase: "#ALL"
patterns:
  - id: titles
    title: Title rules
    rules:
      - id: non-empty-title
        context: "baseType == 'title'"
        assertions:
          - test: "len(children) > 0"
            message: Title must not be empty
            severity: error
            fix:
              type: ai
              prompt: Suggest a title
        reports:
          - test: "word_count(node) > 10"
            message: "Title too long ({word_count(node)} words)"
            severity: warning
"""
    ruleset = DtvlRuleset.from_yaml(yaml_src)
    assert ruleset.id == "test-rules"
    assert len(ruleset.patterns) == 1
    pattern = ruleset.patterns[0]
    assert len(pattern.rules) == 1
    rule = pattern.rules[0]
    assert len(rule.assertions) == 1
    assert len(rule.reports) == 1
    assert rule.assertions[0].fix is not None
    assert rule.assertions[0].fix.type == DtvlFixType.ai

    # Round-trip through YAML
    yaml_out = ruleset.to_yaml()
    ruleset2 = DtvlRuleset.from_yaml(yaml_out)
    assert ruleset2.id == ruleset.id
    assert ruleset2.patterns[0].rules[0].assertions[0].test == rule.assertions[0].test


# ── lxml XPath fallback (complex context) ────────────────────────────────────


def test_lxml_xpath_context_fallback() -> None:
    """Rules with lxml_xpath should match nodes via the lxml tree."""
    ruleset = DtvlRuleset(
        patterns=[
            DtvlPattern(
                id="p-check",
                rules=[
                    DtvlRule(
                        context="True",
                        lxml_xpath="//p",
                        assertions=[
                            DtvlAssertion(
                                test="has_text(node)",
                                message="Paragraph is empty",
                            )
                        ],
                    )
                ],
            )
        ]
    )
    engine = DtvlEngine(ruleset)

    # Document with a non-empty paragraph — should be valid.
    result = engine.validate(_topic(body_text="Non-empty content."))
    assert result.is_valid

    # Document with an empty paragraph — should fail.
    doc_empty_p: dict = {
        "baseDoctype": "topic",
        "baseType": "topic",
        "attrs": {},
        "children": [
            {"baseType": "title", "children": ["T"]},
            {
                "baseType": "body",
                "children": [{"baseType": "p", "children": []}],
            },
        ],
    }
    result2 = engine.validate(doc_empty_p)
    assert not result2.is_valid


# ── Sandbox security ──────────────────────────────────────────────────────────


def test_sandbox_blocks_import() -> None:
    from ditaflow.dtvl.sandbox import DtvlSandboxError, safe_eval

    # "import os" is a statement, not an expression — ast.parse(mode="eval")
    # raises SyntaxError before the AST walk runs, which sandbox converts to
    # DtvlSandboxError.  ImportFrom inside an expression context is caught by
    # the AST walker instead.
    with pytest.raises(DtvlSandboxError):
        safe_eval("import os", {})


def test_sandbox_blocks_dunder() -> None:
    from ditaflow.dtvl.sandbox import DtvlSandboxError, safe_eval

    with pytest.raises(DtvlSandboxError, match="Dunder"):
        safe_eval("node.__class__", {"node": {}})


def test_sandbox_blocks_exec() -> None:
    from ditaflow.dtvl.sandbox import DtvlSandboxError, safe_eval

    with pytest.raises(DtvlSandboxError, match="exec"):
        safe_eval("exec('pass')", {})
