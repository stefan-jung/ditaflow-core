"""DTVL engine — evaluates a DtvlRuleset against a DTF document.

The engine walks the DTF tree, checks each node against the active rules'
context expressions, and fires assertion/report messages for any that match.

Rules with an ``lxml_xpath`` context (imported from Schematron) are handled by
building a lightweight lxml tree from the DTF document once per validation run
and running XPath against it.  Every element in the lxml tree carries a
``data-dtvl-path`` attribute so matching nodes can be mapped back to DTF paths
without any identity tricks.
"""

from __future__ import annotations

import contextlib
import re
from typing import Any

from lxml import etree

from ditaflow.dtvl.helpers import HELPER_NAMESPACE
from ditaflow.dtvl.model import (
    _TEMPLATE_VAR_RE,
    DtvlAssertion,
    DtvlPattern,
    DtvlReport,
    DtvlRule,
    DtvlRuleset,
    ValidationMessage,
    ValidationResult,
)
from ditaflow.dtvl.sandbox import DtvlSandboxError, safe_eval

_DTVL_PATH_ATTR = "data-dtvl-path"


# ── lxml tree builder ─────────────────────────────────────────────────────────


def _sanitize_tag(raw: str) -> str:
    tag = re.sub(r"[^a-zA-Z0-9_\-.]", "_", raw)
    if not tag or tag[0].isdigit():
        tag = "_" + tag
    return tag or "_unknown"


def _dtf_to_lxml(node: dict[str, Any], path: str) -> etree._Element:
    tag = _sanitize_tag(node.get("baseType", "node"))
    elem = etree.Element(tag)
    elem.set(_DTVL_PATH_ATTR, path)

    for key, val in node.get("attrs", {}).items():
        if isinstance(val, str):
            with contextlib.suppress(ValueError):
                elem.set(key, val)

    text_parts: list[str] = []
    for i, child in enumerate(node.get("children", [])):
        if isinstance(child, str):
            text_parts.append(child)
        elif isinstance(child, dict):
            elem.append(_dtf_to_lxml(child, f"{path}.children[{i}]"))

    if text_parts:
        elem.text = "".join(text_parts)
    return elem


def _build_lxml_tree(document: dict[str, Any]) -> etree._Element:
    return _dtf_to_lxml(document, "root")


def _xpath_matching_paths(lxml_root: etree._Element, xpath: str) -> frozenset[str]:
    """Return the set of ``data-dtvl-path`` values for elements matching *xpath*."""
    try:
        matches = lxml_root.xpath(xpath)
    except etree.XPathEvalError:
        return frozenset()
    paths: set[str] = set()
    for elem in matches:
        if isinstance(elem, etree._Element):
            p = elem.get(_DTVL_PATH_ATTR)
            if p:
                paths.add(p)
    return frozenset(paths)


# ── Node context builder ───────────────────────────────────────────────────────


def _node_context(node: dict[str, Any], path: str, document: dict[str, Any]) -> dict[str, Any]:
    return {
        "node": node,
        "document": document,
        "path": path,
        "baseType": node.get("baseType", ""),
        "doctype": node.get("doctype", ""),
        "baseDoctype": node.get("baseDoctype", ""),
        "attrs": node.get("attrs", {}),
        "children": node.get("children", []),
        **HELPER_NAMESPACE,
    }


# ── DTF tree walk ─────────────────────────────────────────────────────────────


def _walk(node: dict[str, Any], path: str = "root") -> list[tuple[dict[str, Any], str]]:
    result = [(node, path)]
    for i, child in enumerate(node.get("children", [])):
        if isinstance(child, dict):
            result.extend(_walk(child, f"{path}.children[{i}]"))
    return result


# ── Message template ──────────────────────────────────────────────────────────


def _format_message(template: str, ctx: dict[str, Any]) -> str:
    def replace(m: re.Match[str]) -> str:
        key = m.group(1)
        try:
            return str(safe_eval(key, ctx))
        except Exception:
            return m.group(0)

    return _TEMPLATE_VAR_RE.sub(replace, template)


# ── Engine ─────────────────────────────────────────────────────────────────────


class DtvlEngine:
    """Evaluates a :class:`~ditaflow.dtvl.model.DtvlRuleset` against DTF documents."""

    def __init__(self, ruleset: DtvlRuleset) -> None:
        self.ruleset = ruleset
        self._pattern_index: dict[str, DtvlPattern] = {p.id: p for p in ruleset.patterns}
        self._rule_index: dict[str, DtvlRule] = {}
        for pattern in ruleset.patterns:
            for rule in pattern.rules:
                if rule.id:
                    self._rule_index[rule.id] = rule

    # ── public API ────────────────────────────────────────────────────────

    def validate(
        self,
        document: dict[str, Any],
        phase: str = "#ALL",
        extra_context: dict[str, Any] | None = None,
    ) -> ValidationResult:
        """Validate *document* against the ruleset and return a :class:`ValidationResult`."""
        active = self._active_patterns(phase)
        messages: list[ValidationMessage] = []

        # Build lxml tree once only if any rule needs it.
        lxml_root: etree._Element | None = None
        lxml_path_cache: dict[str, frozenset[str]] = {}

        if any(r.lxml_xpath for p in active for r in p.rules):
            lxml_root = _build_lxml_tree(document)

        all_nodes = _walk(document)

        for pattern in active:
            for rule in self._resolved_rules(pattern):
                # Determine matching paths for this rule.
                if rule.lxml_xpath and lxml_root is not None:
                    if rule.lxml_xpath not in lxml_path_cache:
                        lxml_path_cache[rule.lxml_xpath] = _xpath_matching_paths(
                            lxml_root, rule.lxml_xpath
                        )
                    matching_paths = lxml_path_cache[rule.lxml_xpath]
                    candidates = [(n, p) for n, p in all_nodes if p in matching_paths]
                else:
                    candidates = [
                        (n, p)
                        for n, p in all_nodes
                        if self._matches_context(rule.context, n, document, p)
                    ]

                for node, path in candidates:
                    ctx = _node_context(node, path, document)
                    if extra_context:
                        ctx.update(extra_context)
                    messages.extend(
                        self._eval_assertions(rule.assertions, ctx, node, path, rule.id, pattern.id)
                    )
                    messages.extend(
                        self._eval_reports(rule.reports, ctx, node, path, rule.id, pattern.id)
                    )

        return ValidationResult(messages=messages)

    # ── internals ─────────────────────────────────────────────────────────

    def _active_patterns(self, phase: str) -> list[DtvlPattern]:
        if phase == "#ALL":
            return [p for p in self.ruleset.patterns if not p.abstract]
        resolved_phase = self.ruleset.default_phase if phase == "#DEFAULT" else phase
        for ph in self.ruleset.phases:
            if ph.id == resolved_phase:
                return [
                    self._pattern_index[pid]
                    for pid in ph.active_patterns
                    if pid in self._pattern_index and not self._pattern_index[pid].abstract
                ]
        return []

    def _resolved_rules(self, pattern: DtvlPattern) -> list[DtvlRule]:
        rules: list[DtvlRule] = []
        for rule in pattern.rules:
            if rule.abstract:
                continue
            if rule.extends and rule.extends in self._rule_index:
                base = self._rule_index[rule.extends]
                rules.append(
                    DtvlRule(
                        context=rule.context,
                        id=rule.id,
                        lxml_xpath=rule.lxml_xpath or base.lxml_xpath,
                        assertions=base.assertions + rule.assertions,
                        reports=base.reports + rule.reports,
                    )
                )
            else:
                rules.append(rule)
        return rules

    @staticmethod
    def _matches_context(
        expr: str, node: dict[str, Any], document: dict[str, Any], path: str
    ) -> bool:
        ctx = _node_context(node, path, document)
        try:
            return bool(safe_eval(expr, ctx))
        except DtvlSandboxError:
            return False

    @staticmethod
    def _eval_assertions(
        assertions: list[DtvlAssertion],
        ctx: dict[str, Any],
        node: dict[str, Any],
        path: str,
        rule_id: str | None,
        pattern_id: str,
    ) -> list[ValidationMessage]:
        out: list[ValidationMessage] = []
        for a in assertions:
            try:
                passed = bool(safe_eval(a.test, ctx))
            except DtvlSandboxError:
                passed = True  # don't penalise eval errors as assertion failures
            if not passed:
                out.append(
                    ValidationMessage(
                        severity=a.severity,
                        message=_format_message(a.message, ctx),
                        node_path=path,
                        node=node,
                        type="assert",
                        rule_id=rule_id,
                        assertion_id=a.id,
                        pattern_id=pattern_id,
                        fix=a.fix,
                    )
                )
        return out

    @staticmethod
    def _eval_reports(
        reports: list[DtvlReport],
        ctx: dict[str, Any],
        node: dict[str, Any],
        path: str,
        rule_id: str | None,
        pattern_id: str,
    ) -> list[ValidationMessage]:
        out: list[ValidationMessage] = []
        for r in reports:
            try:
                fired = bool(safe_eval(r.test, ctx))
            except DtvlSandboxError:
                fired = False
            if fired:
                out.append(
                    ValidationMessage(
                        severity=r.severity,
                        message=_format_message(r.message, ctx),
                        node_path=path,
                        node=node,
                        type="report",
                        rule_id=rule_id,
                        assertion_id=r.id,
                        pattern_id=pattern_id,
                        fix=r.fix,
                    )
                )
        return out
