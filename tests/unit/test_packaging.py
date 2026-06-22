"""Builds a real wheel and checks the vendored RELAX NG schemas actually
ship in it -- catches the exact class of bug already silently true of
schema/ditaflow.schema.json (works via an editable install, missing from
a real wheel; see ROADMAP.md's "Known issue" note). Skipped if the
`build` package isn't installed, since it's a dev-only check, not a
runtime dependency.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

pytest.importorskip("build")


def test_built_wheel_contains_the_vendored_relaxng_schemas() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            [sys.executable, "-m", "build", "--wheel", "--outdir", tmp],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
        )
        wheels = list(Path(tmp).glob("*.whl"))
        assert len(wheels) == 1, wheels
        with zipfile.ZipFile(wheels[0]) as wheel:
            names = wheel.namelist()
        rng_files = [n for n in names if n.endswith(".rng")]
        assert len(rng_files) >= 70, f"expected ~73 vendored .rng files, found {len(rng_files)}"
        assert any(n.endswith("topic.rng") for n in rng_files)
        assert any(n.endswith("map.rng") for n in rng_files)
        assert any("LICENSE-DITA-OT.txt" in n for n in names)
