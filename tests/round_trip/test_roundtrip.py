"""DITA -> DTF -> DITA round-trip tests for single-file feature fixtures.

Per spec/DITAFLOW-SPEC.md §9, the round-trip guarantee is semantic identity,
not byte-for-byte identity — see _helpers.assert_semantic_roundtrip for the
exact definition used here.

To add a new scenario, drop a .dita file into fixtures/dita/ — it is
auto-discovered by the glob below, no code change required. See README.md
"Testing" section for the full instructions, including when to use a
multi-file project fixture (fixtures/projects/, tested by
test_project_roundtrip.py) instead.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ._helpers import assert_semantic_roundtrip

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "dita"
FIXTURE_FILES = sorted(p.name for p in FIXTURES_DIR.glob("*.dita"))


@pytest.mark.parametrize("fixture_name", FIXTURE_FILES)
def test_roundtrip_semantic_identity(fixture_name: str) -> None:
    assert_semantic_roundtrip(FIXTURES_DIR / fixture_name, base_dir=FIXTURES_DIR)
