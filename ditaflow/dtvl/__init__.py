"""DTF Validation Language (DTVL) — Schematron-equivalent rule engine for DTF.

Quick start::

    from ditaflow.dtvl import DtvlEngine, DtvlRuleset

    ruleset = DtvlRuleset.from_yaml(Path("my-rules.dtvl.yaml").read_text())
    engine  = DtvlEngine(ruleset)
    result  = engine.validate(dtf_document)

    if not result.is_valid:
        for msg in result.errors():
            print(f"[{msg.node_path}] {msg.message}")

Schematron round-trip::

    from ditaflow.dtvl import import_schematron, export_schematron

    ruleset = import_schematron(Path("rules.sch").read_text())
    Path("rules.dtvl.yaml").write_text(ruleset.to_yaml())

    sch_xml = export_schematron(ruleset)
    Path("rules-exported.sch").write_text(sch_xml)
"""

from ditaflow.dtvl.engine import DtvlEngine
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
    ValidationMessage,
    ValidationResult,
)
from ditaflow.dtvl.sandbox import DtvlSandboxError
from ditaflow.dtvl.schematron import export_schematron, import_schematron

__all__ = [
    # Engine
    "DtvlEngine",
    # Model
    "DtvlAssertion",
    "DtvlFix",
    "DtvlFixType",
    "DtvlPattern",
    "DtvlPhase",
    "DtvlReport",
    "DtvlRule",
    "DtvlRuleset",
    "DtvlSeverity",
    "ValidationMessage",
    "ValidationResult",
    # Sandbox
    "DtvlSandboxError",
    # Schematron bridge
    "import_schematron",
    "export_schematron",
]
