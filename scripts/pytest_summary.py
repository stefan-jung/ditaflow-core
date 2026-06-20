#!/usr/bin/env python3
"""Renders a pytest JUnit XML report (and optionally a coverage.xml) as
Markdown suitable for a GitHub Actions job summary.

Usage:
    python scripts/pytest_summary.py <junit-xml-path> --title "Title" \
        [--coverage-xml coverage.xml]

Writes Markdown to stdout; the CI workflow redirects it into
$GITHUB_STEP_SUMMARY. This intentionally always exits 0 -- it only renders
a report, it never decides pass/fail (the pytest step already did that).
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def render_junit(xml_path: Path, title: str) -> str:
    tree = ET.parse(xml_path)
    root = tree.getroot()
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    if suite is None:
        return f"## {title}\n\nNo test results found in `{xml_path}`.\n"

    tests = int(suite.get("tests", 0))
    failures = int(suite.get("failures", 0))
    errors = int(suite.get("errors", 0))
    skipped = int(suite.get("skipped", 0))
    duration = float(suite.get("time", 0.0))
    passed = tests - failures - errors - skipped

    ok = failures == 0 and errors == 0
    icon = "✅" if ok else "❌"
    status = "PASS" if ok else "FAIL"

    lines = [
        f"## {icon} {title}: {status}",
        "",
        "| Total | Passed | Failed | Errors | Skipped | Duration |",
        "|---|---|---|---|---|---|",
        f"| {tests} | {passed} | {failures} | {errors} | {skipped} | {duration:.2f}s |",
    ]

    failing_cases = [
        case
        for case in suite.findall("testcase")
        if case.find("failure") is not None or case.find("error") is not None
    ]
    if failing_cases:
        lines += ["", "### Failures", ""]
        for case in failing_cases:
            name = f"{case.get('classname', '')}::{case.get('name', '')}"
            problem = case.find("failure")
            if problem is None:
                problem = case.find("error")
            message = ""
            if problem is not None and problem.get("message"):
                message = problem.get("message", "").strip().splitlines()[0]
            lines.append(f"- `{name}` — {message}")

    lines.append("")
    return "\n".join(lines)


def render_coverage(coverage_xml_path: Path) -> str:
    tree = ET.parse(coverage_xml_path)
    line_rate = float(tree.getroot().get("line-rate", 0.0))
    return f"**Line coverage:** {line_rate * 100:.1f}%\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("junit_xml", type=Path)
    parser.add_argument("--title", default="Test results")
    parser.add_argument("--coverage-xml", type=Path, default=None)
    args = parser.parse_args()

    if not args.junit_xml.is_file():
        print(f"## {args.title}\n\n_No JUnit report found at `{args.junit_xml}`._")
        return 0

    print(render_junit(args.junit_xml, args.title))
    if args.coverage_xml is not None and args.coverage_xml.is_file():
        print(render_coverage(args.coverage_xml))
    return 0


if __name__ == "__main__":
    sys.exit(main())
