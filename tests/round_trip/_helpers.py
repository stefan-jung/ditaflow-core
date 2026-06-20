"""Shared round-trip assertion helper for tests/round_trip/.

Used by both test_roundtrip.py (single-file feature fixtures) and
test_project_roundtrip.py (multi-file project fixtures) so the two suites
share exactly one definition of "semantically identical" (spec
spec/DITAFLOW-SPEC.md §9).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ditaflow.converter.dita_parser import DitaParser
from ditaflow.converter.dita_serializer import DtfSerializer
from ditaflow.validator.dtf_validator import DtfValidator


def normalize(document: dict[str, Any]) -> dict[str, Any]:
    doc = dict(document)
    doc.pop("meta", None)  # sourceUri/sourceHash differ by construction
    return doc


def assert_semantic_roundtrip(
    xml_path: Path, *, base_dir: Path
) -> tuple[dict[str, Any], dict[str, Any], str]:
    """Parses xml_path -> DTF, validates it, serializes back to DITA, then
    re-parses and asserts the result is a semantically identical DTF
    document (spec §9). Also checks DTF -> DITA -> DTF stability and
    serialize idempotency.

    Returns (original_doc, reconstructed_doc, reconstructed_xml) in case the
    caller wants to make further assertions (e.g. cross-file href checks).
    """
    parser = DitaParser()
    serializer = DtfSerializer()
    validator = DtfValidator()

    original_xml = xml_path.read_text(encoding="utf-8")
    import_result = parser.parse_string(original_xml, source_uri=str(xml_path), base_dir=base_dir)

    errors = validator.validate(import_result.document)
    assert not errors, f"{xml_path}: DTF document failed schema validation: {errors}"

    export_result = serializer.serialize(import_result.document)
    reimport_result = parser.parse_string(export_result.xml, base_dir=base_dir)

    original_doc = normalize(import_result.document)
    reconstructed_doc = normalize(reimport_result.document)
    assert original_doc == reconstructed_doc, (
        f"{xml_path}: round trip changed the DTF document.\nReconstructed XML:\n{export_result.xml}"
    )

    # Idempotency: serializing again from the reconstructed document should
    # not introduce any further drift.
    second_export = serializer.serialize(reimport_result.document)
    second_reimport = parser.parse_string(second_export.xml, base_dir=base_dir)
    assert normalize(second_reimport.document) == reconstructed_doc, (
        f"{xml_path}: a second serialize/parse cycle was not stable."
    )

    return original_doc, reconstructed_doc, export_result.xml
