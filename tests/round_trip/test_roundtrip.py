"""DITA -> DTF -> DITA round-trip tests.

Per spec/DITAFLOW-SPEC.md §9, the round-trip guarantee is semantic identity,
not byte-for-byte identity. We verify this by re-parsing the reconstructed
XML and comparing the resulting DTF document to the original DTF document —
DTF *is* DitaFlow's canonical semantic representation, so dict equality
after the round trip is exactly the definition of "semantically identical"
the spec gives. We also check DTF -> DITA -> DTF stability (parsing the
reconstructed XML again must reproduce the same DTF) and idempotency
(serializing a second time produces no further drift).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ditaflow.converter.dita_parser import DitaParser
from ditaflow.converter.dita_serializer import DtfSerializer
from ditaflow.validator.dtf_validator import DtfValidator

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "dita"
FIXTURE_FILES = sorted(p.name for p in FIXTURES_DIR.glob("*.dita"))


def _normalize(document: dict[str, Any]) -> dict[str, Any]:
    doc = dict(document)
    doc.pop("meta", None)  # sourceUri/sourceHash differ by construction
    return doc


@pytest.mark.parametrize("fixture_name", FIXTURE_FILES)
def test_roundtrip_semantic_identity(fixture_name: str) -> None:
    fixture_path = FIXTURES_DIR / fixture_name
    parser = DitaParser()
    serializer = DtfSerializer()
    validator = DtfValidator()

    original_xml = fixture_path.read_text(encoding="utf-8")
    import_result = parser.parse_string(
        original_xml, source_uri=str(fixture_path), base_dir=FIXTURES_DIR
    )

    errors = validator.validate(import_result.document)
    assert not errors, f"{fixture_name}: DTF document failed schema validation: {errors}"

    export_result = serializer.serialize(import_result.document)
    reimport_result = parser.parse_string(export_result.xml, base_dir=FIXTURES_DIR)

    original_doc = _normalize(import_result.document)
    reconstructed_doc = _normalize(reimport_result.document)
    assert original_doc == reconstructed_doc, (
        f"{fixture_name}: round trip changed the DTF document.\n"
        f"Reconstructed XML:\n{export_result.xml}"
    )

    # Idempotency: serializing again from the reconstructed document should
    # not introduce any further drift.
    second_export = serializer.serialize(reimport_result.document)
    second_reimport = parser.parse_string(second_export.xml, base_dir=FIXTURES_DIR)
    assert _normalize(second_reimport.document) == reconstructed_doc, (
        f"{fixture_name}: a second serialize/parse cycle was not stable."
    )
