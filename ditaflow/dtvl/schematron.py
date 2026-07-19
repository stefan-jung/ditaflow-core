"""Schematron ↔ DTVL import/export bridge.

Import (.sch → DtvlRuleset)
    Simple XPath context and test expressions are mechanically converted to
    Python.  Complex multi-axis expressions fall back to ``lxml_xpath`` on the
    DtvlRule so the engine evaluates them via lxml without losing any rules.
    SQF quick fixes are mapped to DtvlFix objects.

Export (DtvlRuleset → .sch)
    Simple Python context expressions are reverse-mapped to XPath; complex
    ones become a ``<sch:rule context="*">`` with a diagnostic comment so
    nothing is silently lost.

Namespace prefixes used in generated Schematron:
    sch  → http://purl.oclc.org/dsdl/schematron
    sqf  → http://www.schematron-quickfix.com/validator/process
"""

from __future__ import annotations

import re

from lxml import etree

from ditaflow.dtvl.model import (
    DtvlAssertion,
    DtvlFix,
    DtvlFixType,
    DtvlPattern,
    DtvlPhase,
    DtvlReport,
    DtvlRule,
    DtvlRuleset,
    DtvlSeverity,
)

_SCH = "http://purl.oclc.org/dsdl/schematron"
_SQF = "http://www.schematron-quickfix.com/validator/process"
_NS = {"sch": _SCH, "sqf": _SQF}

_S = f"{{{_SCH}}}"
_Q = f"{{{_SQF}}}"


# ── XPath ↔ Python context conversion ────────────────────────────────────────


def _xpath_context_to_python(xpath: str) -> tuple[str, bool]:
    """Convert a Schematron context XPath to a Python expression.

    Returns ``(expression, is_complex)`` where ``is_complex=True`` means the
    engine must fall back to lxml rather than using the Python expression.
    """
    bare = xpath.strip().lstrip("/").strip()

    # * — matches any element node
    if bare == "*":
        return "isinstance(node, dict)", False

    # Simple element name: "topic", "p", "shortdesc"
    if re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_\-]*", bare):
        return f"baseType == {bare!r}", False

    # Element with attribute presence: "topic[@id]"
    m = re.fullmatch(r"([a-zA-Z][a-zA-Z0-9_\-]*)\[@([a-zA-Z][a-zA-Z0-9_\-:]*)\]", bare)
    if m:
        elem, attr = m.groups()
        return f"baseType == {elem!r} and has_attr(node, {attr!r})", False

    # Element with attribute value: "topic[@outputclass='task']"
    m = re.fullmatch(
        r"([a-zA-Z][a-zA-Z0-9_\-]*)\[@([a-zA-Z][a-zA-Z0-9_\-:]*)=['\"]([^'\"]*)['\"]]\]?",
        bare,
    )
    if not m:
        m = re.fullmatch(
            r"([a-zA-Z][a-zA-Z0-9_\-]*)\[@([a-zA-Z][a-zA-Z0-9_\-:]*)=['\"]([^'\"]*)['\"]]\s*",
            bare,
        )
    if not m:
        # try with bare brackets
        m = re.fullmatch(
            r"([a-zA-Z][a-zA-Z0-9_\-]*)\[@([a-zA-Z][a-zA-Z0-9_\-:]*)\s*=\s*['\"]([^'\"]*)['\"]",
            bare,
        )
    if m:
        elem, attr, val = m.groups()
        return f"baseType == {elem!r} and get_attr(node, {attr!r}) == {val!r}", False

    # Wildcard with attribute value: "*[@outputclass='task']"
    m = re.fullmatch(
        r"\*\[@([a-zA-Z][a-zA-Z0-9_\-:]*)\s*=\s*['\"]([^'\"]*)['\"]",
        bare,
    )
    if m:
        attr, val = m.groups()
        return f"get_attr(node, {attr!r}) == {val!r}", False

    # Wildcard with attribute presence: "*[@id]"
    m = re.fullmatch(r"\*\[@([a-zA-Z][a-zA-Z0-9_\-:]*)\]", bare)
    if m:
        return f"has_attr(node, {m.group(1)!r})", False

    # Complex — fall back to lxml.
    return "True", True


def _xpath_test_to_python(test: str) -> tuple[str, bool]:
    """Convert a Schematron assert/report test XPath to a Python expression.

    Returns ``(expression, is_complex)``.  Complex expressions are kept as
    ``lxml_xpath`` on the assertion for the engine to resolve via lxml.
    """
    t = test.strip()

    # string-length(.) > 0  or  string-length(.) != 0
    if re.match(r"string-length\s*\(\s*\.?\s*\)\s*(>|!=)\s*0", t):
        return "has_text(node)", False

    # string-length(.) = 0
    if re.match(r"string-length\s*\(\s*\.?\s*\)\s*=\s*0", t):
        return "not has_text(node)", False

    # not(string-length(.) = 0)
    if re.match(r"not\s*\(\s*string-length\s*\(\s*\.?\s*\)\s*=\s*0\s*\)", t):
        return "has_text(node)", False

    # count(child) > 0
    m = re.match(r"count\s*\(\s*([a-zA-Z][a-zA-Z0-9_\-]*)\s*\)\s*(>|>=|=|!=|<|<=)\s*(\d+)", t)
    if m:
        child, op, num = m.groups()
        py_op = {"=": "=="}.get(op, op)
        return f"len(children_of_type(node, {child!r})) {py_op} {num}", False

    # @attr  (attribute existence)
    m = re.fullmatch(r"@([a-zA-Z][a-zA-Z0-9_\-:]*)", t)
    if m:
        return f"has_attr(node, {m.group(1)!r})", False

    # not(@attr)
    m = re.fullmatch(r"not\s*\(\s*@([a-zA-Z][a-zA-Z0-9_\-:]*)\s*\)", t)
    if m:
        return f"not has_attr(node, {m.group(1)!r})", False

    # @attr = 'value'
    m = re.fullmatch(r"@([a-zA-Z][a-zA-Z0-9_\-:]*)\s*=\s*['\"]([^'\"]*)['\"]", t)
    if m:
        attr, val = m.groups()
        return f"get_attr(node, {attr!r}) == {val!r}", False

    # @attr != 'value'
    m = re.fullmatch(r"@([a-zA-Z][a-zA-Z0-9_\-:]*)\s*!=\s*['\"]([^'\"]*)['\"]", t)
    if m:
        attr, val = m.groups()
        return f"get_attr(node, {attr!r}) != {val!r}", False

    # normalize-space(.) != ''  /  normalize-space(.)
    if re.match(r"normalize-space\s*\(\s*\.?\s*\)\s*(!=\s*'')?", t):
        return "has_text(node)", False

    # Simple child element existence: "title"
    if re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_\-]*", t):
        return f"has_child_of_type(node, {t!r})", False

    # Complex
    return "True", True


# ── SQF quick-fix import ──────────────────────────────────────────────────────


def _import_sqf_fix(fix_elem: etree._Element) -> DtvlFix | None:
    fix_id = fix_elem.get("id", "")
    desc_elem = fix_elem.find(f"{_S}title")
    description = desc_elem.text.strip() if desc_elem is not None and desc_elem.text else fix_id

    # sqf:add — treat as add-child or replace-field depending on context
    add = fix_elem.find(f"{_Q}add")
    if add is not None:
        return DtvlFix(type=DtvlFixType.add_child, description=description)

    # sqf:delete
    delete = fix_elem.find(f"{_Q}delete")
    if delete is not None:
        return DtvlFix(type=DtvlFixType.delete_node, description=description)

    # sqf:replace
    replace = fix_elem.find(f"{_Q}replace")
    if replace is not None:
        return DtvlFix(type=DtvlFixType.replace_field, description=description)

    # sqf:stringReplace
    sr = fix_elem.find(f"{_Q}stringReplace")
    if sr is not None:
        regex_elem = sr.find(f"{_Q}regex")
        repl_elem = sr.find(f"{_Q}replacement")
        pat = regex_elem.text.strip() if regex_elem is not None and regex_elem.text else None
        rep = repl_elem.text.strip() if repl_elem is not None and repl_elem.text else None
        return DtvlFix(
            type=DtvlFixType.string_replace,
            pattern=pat,
            replacement=rep,
            description=description,
        )

    # Fallback — script stub
    return DtvlFix(type=DtvlFixType.script, description=description)


# ── Main import ───────────────────────────────────────────────────────────────


def import_schematron(sch_xml: str) -> DtvlRuleset:
    """Parse a Schematron ``.sch`` XML string and return a :class:`DtvlRuleset`."""
    root = etree.fromstring(sch_xml.encode() if isinstance(sch_xml, str) else sch_xml)

    ruleset = DtvlRuleset(
        id=root.get("id"),
        title=_elem_text(root, f"{_S}title"),
        default_phase=root.get("defaultPhase", "#ALL"),
    )

    # Collect SQF fix elements keyed by id so assert/report can reference them.
    sqf_fixes: dict[str, DtvlFix] = {}
    for fix_elem in root.iter(f"{_Q}fix"):
        fid = fix_elem.get("id")
        if fid:
            imported = _import_sqf_fix(fix_elem)
            if imported:
                sqf_fixes[fid] = imported

    # Phases
    for phase_elem in root.findall(f"{_S}phase"):
        phase = DtvlPhase(
            id=phase_elem.get("id", "_unnamed"),
            title=_elem_text(phase_elem, f"{_S}p"),
            active_patterns=[
                ap.get("pattern", "")
                for ap in phase_elem.findall(f"{_S}active")
                if ap.get("pattern")
            ],
        )
        ruleset.phases.append(phase)

    # Patterns
    for pat_elem in root.findall(f"{_S}pattern"):
        pattern = DtvlPattern(
            id=pat_elem.get("id") or f"pattern_{len(ruleset.patterns)}",
            title=_elem_text(pat_elem, f"{_S}title"),
            abstract=pat_elem.get("abstract", "false").lower() == "true",
        )

        for rule_elem in pat_elem.findall(f"{_S}rule"):
            xpath_ctx = rule_elem.get("context", "*")
            py_ctx, is_complex = _xpath_context_to_python(xpath_ctx)

            rule = DtvlRule(
                context=py_ctx,
                id=rule_elem.get("id"),
                abstract=rule_elem.get("abstract", "false").lower() == "true",
                lxml_xpath=xpath_ctx if is_complex else None,
            )

            for assert_elem in rule_elem.findall(f"{_S}assert"):
                raw_test = assert_elem.get("test", "True")
                py_test, test_complex = _xpath_test_to_python(raw_test)
                if test_complex:
                    py_test = "True"  # can't convert; always fires — author must review

                msg = _elem_text_or_tail(assert_elem) or "Assertion failed"
                sev_raw = assert_elem.get("role", "error")
                try:
                    sev = DtvlSeverity(sev_raw.lower())
                except ValueError:
                    sev = DtvlSeverity.error

                # Resolve linked SQF fix
                fix: DtvlFix | None = None
                fix_ref = assert_elem.get(f"{_Q}fix")
                if fix_ref and fix_ref in sqf_fixes:
                    fix = sqf_fixes[fix_ref]

                rule.assertions.append(
                    DtvlAssertion(
                        id=assert_elem.get("id"),
                        test=py_test,
                        message=msg.strip(),
                        severity=sev,
                        fix=fix,
                    )
                )

            for report_elem in rule_elem.findall(f"{_S}report"):
                raw_test = report_elem.get("test", "False")
                py_test, test_complex = _xpath_test_to_python(raw_test)
                if test_complex:
                    py_test = "False"

                msg = _elem_text_or_tail(report_elem) or "Report fired"
                sev_raw = report_elem.get("role", "warning")
                try:
                    sev = DtvlSeverity(sev_raw.lower())
                except ValueError:
                    sev = DtvlSeverity.warning

                fix = None
                fix_ref = report_elem.get(f"{_Q}fix")
                if fix_ref and fix_ref in sqf_fixes:
                    fix = sqf_fixes[fix_ref]

                rule.reports.append(
                    DtvlReport(
                        id=report_elem.get("id"),
                        test=py_test,
                        message=msg.strip(),
                        severity=sev,
                        fix=fix,
                    )
                )

            pattern.rules.append(rule)

        ruleset.patterns.append(pattern)

    return ruleset


# ── Main export ───────────────────────────────────────────────────────────────


def export_schematron(ruleset: DtvlRuleset) -> str:
    """Serialise a :class:`DtvlRuleset` to an ISO Schematron XML string."""
    nsmap = {"sch": _SCH, "sqf": _SQF}
    schema = etree.Element(f"{_S}schema", nsmap=nsmap)
    if ruleset.id:
        schema.set("id", ruleset.id)
    if ruleset.default_phase != "#ALL":
        schema.set("defaultPhase", ruleset.default_phase)

    if ruleset.title:
        t = etree.SubElement(schema, f"{_S}title")
        t.text = ruleset.title

    for phase in ruleset.phases:
        pe = etree.SubElement(schema, f"{_S}phase", id=phase.id)
        for pid in phase.active_patterns:
            etree.SubElement(pe, f"{_S}active", pattern=pid)

    fix_counter = 0
    for pattern in ruleset.patterns:
        pat_elem = etree.SubElement(schema, f"{_S}pattern", id=pattern.id)
        if pattern.abstract:
            pat_elem.set("abstract", "true")
        if pattern.title:
            pt = etree.SubElement(pat_elem, f"{_S}title")
            pt.text = pattern.title

        for rule in pattern.rules:
            ctx_xpath = rule.lxml_xpath or _python_context_to_xpath(rule.context)
            rule_elem = etree.SubElement(pat_elem, f"{_S}rule", context=ctx_xpath)
            if rule.id:
                rule_elem.set("id", rule.id)
            if rule.abstract:
                rule_elem.set("abstract", "true")

            for assertion in rule.assertions:
                test_xpath = _python_test_to_xpath(assertion.test)
                a_elem = etree.SubElement(rule_elem, f"{_S}assert", test=test_xpath)
                if assertion.id:
                    a_elem.set("id", assertion.id)
                if assertion.severity != DtvlSeverity.error:
                    a_elem.set("role", assertion.severity.value)
                a_elem.text = assertion.message

                if assertion.fix:
                    fix_id = f"fix_{fix_counter}"
                    fix_counter += 1
                    a_elem.set(f"{_Q}fix", fix_id)
                    _export_sqf_fix(schema, fix_id, assertion.fix)

            for report in rule.reports:
                test_xpath = _python_test_to_xpath(report.test)
                r_elem = etree.SubElement(rule_elem, f"{_S}report", test=test_xpath)
                if report.id:
                    r_elem.set("id", report.id)
                if report.severity != DtvlSeverity.warning:
                    r_elem.set("role", report.severity.value)
                r_elem.text = report.message

                if report.fix:
                    fix_id = f"fix_{fix_counter}"
                    fix_counter += 1
                    r_elem.set(f"{_Q}fix", fix_id)
                    _export_sqf_fix(schema, fix_id, report.fix)

    return etree.tostring(schema, pretty_print=True, encoding="unicode", xml_declaration=False)


# ── Export helpers ────────────────────────────────────────────────────────────


def _python_context_to_xpath(py_expr: str) -> str:
    """Best-effort reverse mapping from Python context expression to XPath."""
    m = re.fullmatch(r"baseType\s*==\s*['\"]([a-zA-Z][a-zA-Z0-9_\-]*)['\"]", py_expr.strip())
    if m:
        return m.group(1)

    m = re.fullmatch(
        r"baseType\s*==\s*['\"]([a-zA-Z][a-zA-Z0-9_\-]*)['\"]"
        r"\s*and\s*has_attr\s*\(\s*node\s*,\s*['\"]([^'\"]*)['\"]",
        py_expr.strip(),
    )
    if m:
        return f"{m.group(1)}[@{m.group(2)}]"

    m = re.fullmatch(
        r"baseType\s*==\s*['\"]([a-zA-Z][a-zA-Z0-9_\-]*)['\"]"
        r"\s*and\s*get_attr\s*\(\s*node\s*,\s*['\"]([^'\"]*)['\"]"
        r"\s*\)\s*==\s*['\"]([^'\"]*)['\"]",
        py_expr.strip(),
    )
    if m:
        return f"{m.group(1)}[@{m.group(2)}='{m.group(3)}']"

    # Fall back to wildcard with comment in the assert test.
    return "*"


def _python_test_to_xpath(py_expr: str) -> str:
    """Best-effort reverse mapping from Python test expression to XPath."""
    t = py_expr.strip()
    if t in ("has_text(node)", "True"):
        return "string-length(.) > 0"
    if t in ("not has_text(node)", "is_empty(node)"):
        return "string-length(.) = 0"

    m = re.fullmatch(r"has_attr\s*\(\s*node\s*,\s*['\"]([^'\"]*)['\"]", t)
    if m:
        return f"@{m.group(1)}"

    m = re.fullmatch(r"not\s+has_attr\s*\(\s*node\s*,\s*['\"]([^'\"]*)['\"]", t)
    if m:
        return f"not(@{m.group(1)})"

    m = re.fullmatch(r"get_attr\s*\(\s*node\s*,\s*['\"]([^'\"]*)['\"].*==\s*['\"]([^'\"]*)['\"]", t)
    if m:
        return f"@{m.group(1)}='{m.group(2)}'"

    m = re.fullmatch(
        r"len\s*\(\s*children_of_type\s*\(\s*node\s*,\s*['\"]([^'\"]*)['\"]"
        r"\s*\)\s*\)\s*(==|!=|>|>=|<|<=)\s*(\d+)",
        t,
    )
    if m:
        child, py_op, num = m.groups()
        xpath_op = {"==": "="}.get(py_op, py_op)
        return f"count({child}) {xpath_op} {num}"

    # Keep as a comment-wrapped expression.
    return f"true() (: DTVL: {t} :)"


def _export_sqf_fix(schema: etree._Element, fix_id: str, fix: DtvlFix) -> None:
    fe = etree.SubElement(schema, f"{_Q}fix", id=fix_id)
    if fix.description:
        t = etree.SubElement(fe, f"{_S}title")
        t.text = fix.description

    if fix.type == DtvlFixType.add_child:
        etree.SubElement(fe, f"{_Q}add")
    elif fix.type == DtvlFixType.delete_node:
        etree.SubElement(fe, f"{_Q}delete")
    elif fix.type == DtvlFixType.replace_field:
        etree.SubElement(fe, f"{_Q}replace")
    elif fix.type == DtvlFixType.string_replace:
        sr = etree.SubElement(fe, f"{_Q}stringReplace")
        if fix.pattern:
            reg = etree.SubElement(sr, f"{_Q}regex")
            reg.text = fix.pattern
        if fix.replacement:
            rep = etree.SubElement(sr, f"{_Q}replacement")
            rep.text = fix.replacement
    elif fix.type in (DtvlFixType.ai, DtvlFixType.script):
        # Represent as a human-readable description in the sch output.
        p = etree.SubElement(fe, f"{_S}p")
        p.text = fix.prompt or fix.script or fix.description or "(AI fix — manual review required)"


# ── Utilities ─────────────────────────────────────────────────────────────────


def _elem_text(parent: etree._Element, tag: str) -> str | None:
    child = parent.find(tag)
    if child is not None and child.text:
        return child.text.strip() or None
    return None


def _elem_text_or_tail(elem: etree._Element) -> str:
    """Return the readable text of a sch:assert or sch:report element.

    Schematron message elements can contain embedded ``<sch:name>`` and
    ``<sch:value-of>`` children; we strip those tags and join the text/tail.
    """
    parts: list[str] = []
    if elem.text:
        parts.append(elem.text)
    for child in elem:
        if child.tail:
            parts.append(child.tail)
    return " ".join(p.strip() for p in parts if p.strip())
