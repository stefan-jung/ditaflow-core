"""DTVL data model — rulesets, patterns, rules, assertions, and quick fixes.

DTF Validation Language (DTVL) is the Schematron counterpart for DTF
documents.  It keeps the same conceptual layering as ISO Schematron
(phases → patterns → rules → assertions/reports → quick fixes) while
targeting the DTF JSON tree instead of XML/XPath.

Contexts and test expressions are Python boolean expressions evaluated in a
restricted sandbox with the DTF node exposed as ``node``.  Rules imported
from a Schematron ``.sch`` file carry an optional ``lxml_xpath`` that the
engine resolves against a lightweight lxml representation of the document so
complex multi-axis XPaths keep working without any manual conversion.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal

import yaml

# ── Enumerations ──────────────────────────────────────────────────────────────


class DtvlSeverity(StrEnum):
    error = "error"
    warning = "warning"
    info = "info"


class DtvlFixType(StrEnum):
    add_child = "add-child"
    delete_node = "delete-node"
    replace_field = "replace-field"
    string_replace = "string-replace"
    ai = "ai"
    script = "script"


# ── Quick-fix ─────────────────────────────────────────────────────────────────


@dataclass
class DtvlFix:
    type: DtvlFixType
    # add-child
    node: dict[str, Any] | None = None
    # replace-field
    field: str | None = None
    value: Any = None
    # string-replace
    pattern: str | None = None
    replacement: str | None = None
    # ai / script
    prompt: str | None = None
    script: str | None = None
    description: str | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DtvlFix:
        raw_type = d.get("type", "script")
        try:
            fix_type = DtvlFixType(raw_type)
        except ValueError:
            fix_type = DtvlFixType.script
        return cls(
            type=fix_type,
            node=d.get("node"),
            field=d.get("field"),
            value=d.get("value"),
            pattern=d.get("pattern"),
            replacement=d.get("replacement"),
            prompt=d.get("prompt"),
            script=d.get("script"),
            description=d.get("description"),
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"type": self.type.value}
        for key in (
            "node",
            "field",
            "value",
            "pattern",
            "replacement",
            "prompt",
            "script",
            "description",
        ):
            v = getattr(self, key)
            if v is not None:
                out[key] = v
        return out


# ── Assertions and reports ────────────────────────────────────────────────────


@dataclass
class DtvlAssertion:
    """Assertion: fails (fires a message) when *test* evaluates to False."""

    test: str
    message: str
    id: str | None = None
    severity: DtvlSeverity = DtvlSeverity.error
    diagnostics: list[str] = field(default_factory=list)
    fix: DtvlFix | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DtvlAssertion:
        raw_sev = d.get("severity", "error")
        try:
            sev = DtvlSeverity(raw_sev)
        except ValueError:
            sev = DtvlSeverity.error
        return cls(
            test=d["test"],
            message=d.get("message", "Assertion failed"),
            id=d.get("id"),
            severity=sev,
            diagnostics=d.get("diagnostics", []),
            fix=DtvlFix.from_dict(d["fix"]) if "fix" in d else None,
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"test": self.test, "message": self.message}
        if self.id:
            out["id"] = self.id
        if self.severity != DtvlSeverity.error:
            out["severity"] = self.severity.value
        if self.diagnostics:
            out["diagnostics"] = self.diagnostics
        if self.fix:
            out["fix"] = self.fix.to_dict()
        return out


@dataclass
class DtvlReport:
    """Report: fires a message when *test* evaluates to True."""

    test: str
    message: str
    id: str | None = None
    severity: DtvlSeverity = DtvlSeverity.warning
    fix: DtvlFix | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DtvlReport:
        raw_sev = d.get("severity", "warning")
        try:
            sev = DtvlSeverity(raw_sev)
        except ValueError:
            sev = DtvlSeverity.warning
        return cls(
            test=d["test"],
            message=d.get("message", "Report fired"),
            id=d.get("id"),
            severity=sev,
            fix=DtvlFix.from_dict(d["fix"]) if "fix" in d else None,
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"test": self.test, "message": self.message}
        if self.id:
            out["id"] = self.id
        if self.severity != DtvlSeverity.warning:
            out["severity"] = self.severity.value
        if self.fix:
            out["fix"] = self.fix.to_dict()
        return out


# ── Rule ─────────────────────────────────────────────────────────────────────


@dataclass
class DtvlRule:
    """A rule binds assertions and reports to a set of DTF nodes via *context*.

    *context* is a Python boolean expression (or shorthand like
    ``baseType == 'p'``) evaluated for every node in the tree.
    *lxml_xpath* is set by the Schematron importer for context expressions
    that could not be mechanically converted; the engine evaluates them
    against a lightweight lxml tree.
    """

    context: str
    assertions: list[DtvlAssertion] = field(default_factory=list)
    reports: list[DtvlReport] = field(default_factory=list)
    id: str | None = None
    abstract: bool = False
    extends: str | None = None
    lxml_xpath: str | None = None  # set by Schematron importer for complex XPaths

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DtvlRule:
        return cls(
            context=d.get("context", "True"),
            id=d.get("id"),
            abstract=d.get("abstract", False),
            extends=d.get("extends"),
            lxml_xpath=d.get("lxml_xpath"),
            assertions=[DtvlAssertion.from_dict(a) for a in d.get("assertions", [])],
            reports=[DtvlReport.from_dict(r) for r in d.get("reports", [])],
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"context": self.context}
        if self.id:
            out["id"] = self.id
        if self.abstract:
            out["abstract"] = True
        if self.extends:
            out["extends"] = self.extends
        if self.lxml_xpath:
            out["lxml_xpath"] = self.lxml_xpath
        if self.assertions:
            out["assertions"] = [a.to_dict() for a in self.assertions]
        if self.reports:
            out["reports"] = [r.to_dict() for r in self.reports]
        return out


# ── Pattern ───────────────────────────────────────────────────────────────────


@dataclass
class DtvlPattern:
    id: str
    rules: list[DtvlRule] = field(default_factory=list)
    title: str | None = None
    abstract: bool = False

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DtvlPattern:
        return cls(
            id=d["id"],
            title=d.get("title"),
            abstract=d.get("abstract", False),
            rules=[DtvlRule.from_dict(r) for r in d.get("rules", [])],
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"id": self.id}
        if self.title:
            out["title"] = self.title
        if self.abstract:
            out["abstract"] = True
        out["rules"] = [r.to_dict() for r in self.rules]
        return out


# ── Phase ─────────────────────────────────────────────────────────────────────


@dataclass
class DtvlPhase:
    id: str
    active_patterns: list[str] = field(default_factory=list)
    title: str | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DtvlPhase:
        return cls(
            id=d["id"],
            title=d.get("title"),
            active_patterns=d.get("active_patterns", []),
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"id": self.id}
        if self.title:
            out["title"] = self.title
        if self.active_patterns:
            out["active_patterns"] = self.active_patterns
        return out


# ── Ruleset ───────────────────────────────────────────────────────────────────


@dataclass
class DtvlRuleset:
    """Top-level container for a DTVL ruleset — analagous to a Schematron schema."""

    patterns: list[DtvlPattern] = field(default_factory=list)
    phases: list[DtvlPhase] = field(default_factory=list)
    id: str | None = None
    title: str | None = None
    default_phase: str = "#ALL"

    # ── serialization ──────────────────────────────────────────────────────

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DtvlRuleset:
        return cls(
            id=d.get("id"),
            title=d.get("title"),
            default_phase=d.get("default_phase", "#ALL"),
            phases=[DtvlPhase.from_dict(ph) for ph in d.get("phases", [])],
            patterns=[DtvlPattern.from_dict(p) for p in d.get("patterns", [])],
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.id:
            out["id"] = self.id
        if self.title:
            out["title"] = self.title
        if self.default_phase != "#ALL":
            out["default_phase"] = self.default_phase
        if self.phases:
            out["phases"] = [ph.to_dict() for ph in self.phases]
        out["patterns"] = [p.to_dict() for p in self.patterns]
        return out

    @classmethod
    def from_yaml(cls, text: str) -> DtvlRuleset:
        data: dict[str, Any] = yaml.safe_load(text)
        return cls.from_dict(data)

    def to_yaml(self) -> str:
        return yaml.dump(
            self.to_dict(), allow_unicode=True, sort_keys=False, default_flow_style=False
        )


# ── Validation results ────────────────────────────────────────────────────────


@dataclass
class ValidationMessage:
    severity: DtvlSeverity
    message: str
    node_path: str
    node: dict[str, Any]
    type: Literal["assert", "report"]
    rule_id: str | None = None
    assertion_id: str | None = None
    pattern_id: str | None = None
    fix: DtvlFix | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "severity": self.severity.value,
            "message": self.message,
            "node_path": self.node_path,
            "type": self.type,
        }
        for key in ("rule_id", "assertion_id", "pattern_id"):
            v = getattr(self, key)
            if v is not None:
                out[key] = v
        if self.fix:
            out["fix"] = self.fix.to_dict()
        return out


@dataclass
class ValidationResult:
    messages: list[ValidationMessage]

    @property
    def is_valid(self) -> bool:
        return not any(m.severity == DtvlSeverity.error for m in self.messages)

    @property
    def error_count(self) -> int:
        return sum(1 for m in self.messages if m.severity == DtvlSeverity.error)

    @property
    def warning_count(self) -> int:
        return sum(1 for m in self.messages if m.severity == DtvlSeverity.warning)

    @property
    def info_count(self) -> int:
        return sum(1 for m in self.messages if m.severity == DtvlSeverity.info)

    def errors(self) -> list[ValidationMessage]:
        return [m for m in self.messages if m.severity == DtvlSeverity.error]

    def warnings(self) -> list[ValidationMessage]:
        return [m for m in self.messages if m.severity == DtvlSeverity.warning]

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "info_count": self.info_count,
            "messages": [m.to_dict() for m in self.messages],
        }

    def summary(self) -> str:
        if self.is_valid:
            suffix = f" ({self.warning_count} warning(s))" if self.warning_count else ""
            return f"Valid{suffix}"
        parts = [f"{self.error_count} error(s)"]
        if self.warning_count:
            parts.append(f"{self.warning_count} warning(s)")
        return "Invalid: " + ", ".join(parts)


# Re-exported convenience alias used by the engine's message formatter.
_TEMPLATE_VAR_RE = re.compile(r"\{([^}]+)\}")
