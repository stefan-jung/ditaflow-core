"""DITA -> DTF -> DITA round-trip tests for multi-file *project* fixtures
(a map plus the topics/images/.ditaval it references), as opposed to the
single-file feature fixtures in test_roundtrip.py.

Each subdirectory of fixtures/projects/ is one project: every .dita/.ditamap
file inside it is round-tripped individually (same semantic-identity
definition as test_roundtrip.py, via _helpers.assert_semantic_roundtrip),
*and* the map's topicref hrefs are checked to still resolve to real files on
disk both before and after the round trip — the property a single-file test
can't observe, since a single file has no relative paths to other files to
get wrong.

To add a new project fixture, create fixtures/projects/<name>/ with a
realistic layout (e.g. root.ditamap, topics/*.dita, images/, *.ditaval) and
matching href attributes between them — both test functions below
auto-discover every project directory, no code change required.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ditaflow.converter.dita_parser import DitaParser
from ditaflow.converter.dita_serializer import DtfSerializer

from ._helpers import assert_semantic_roundtrip

PROJECTS_DIR = Path(__file__).parent / "fixtures" / "projects"
PROJECT_DIRS = sorted(p for p in PROJECTS_DIR.iterdir() if p.is_dir())


def _discover_files() -> list[Path]:
    files: list[Path] = []
    for project_dir in PROJECT_DIRS:
        files.extend(sorted(project_dir.rglob("*.dita")))
        files.extend(sorted(project_dir.rglob("*.ditamap")))
    return files


PROJECT_FILES = _discover_files()
PROJECT_FILE_IDS = [str(p.relative_to(PROJECTS_DIR)) for p in PROJECT_FILES]


@pytest.mark.parametrize("xml_path", PROJECT_FILES, ids=PROJECT_FILE_IDS)
def test_project_file_roundtrips(xml_path: Path) -> None:
    assert_semantic_roundtrip(xml_path, base_dir=xml_path.parent)


def _collect_topicref_hrefs(topicrefs: list[dict[str, Any]]) -> list[str]:
    hrefs = []
    for ref in topicrefs:
        if ref.get("href"):
            hrefs.append(ref["href"])
        hrefs.extend(_collect_topicref_hrefs(ref.get("children", [])))
    return hrefs


def _collect_image_hrefs(node: Any) -> list[str]:
    """Recursively finds every image node's href anywhere in a DTF document
    (or sub-tree), regardless of which named field/content array it's
    nested under."""
    hrefs: list[str] = []
    if isinstance(node, dict):
        if node.get("type") == "image":
            href = node.get("attrs", {}).get("href")
            if href:
                hrefs.append(href)
        for value in node.values():
            hrefs.extend(_collect_image_hrefs(value))
    elif isinstance(node, list):
        for item in node:
            hrefs.extend(_collect_image_hrefs(item))
    return hrefs


def _assert_hrefs_resolve(hrefs: list[str], base_dir: Path, label: str) -> None:
    for href in hrefs:
        target = (base_dir / href).resolve()
        assert target.is_file(), f"{label}: href {href!r} does not resolve to a real file"


@pytest.mark.parametrize("project_dir", PROJECT_DIRS, ids=[p.name for p in PROJECT_DIRS])
def test_project_topicref_hrefs_resolve_to_real_files(project_dir: Path) -> None:
    """Cross-file consistency the single-file tests can't observe: every
    topicref href in the map, and every image href inside the topics it
    references, still resolves to a real file relative to its own document
    -- both before and after the round trip."""
    parser = DitaParser()
    serializer = DtfSerializer()

    for ditamap_path in sorted(project_dir.rglob("*.ditamap")):
        xml = ditamap_path.read_text(encoding="utf-8")
        import_result = parser.parse_string(xml, base_dir=ditamap_path.parent)
        export_result = serializer.serialize(import_result.document)
        reimport_result = parser.parse_string(export_result.xml, base_dir=ditamap_path.parent)

        for document, label in (
            (import_result.document, f"{ditamap_path.name} (original)"),
            (reimport_result.document, f"{ditamap_path.name} (reconstructed)"),
        ):
            topicref_hrefs = _collect_topicref_hrefs(document["root"]["topicrefs"])
            _assert_hrefs_resolve(topicref_hrefs, ditamap_path.parent, label)

            for topic_href in topicref_hrefs:
                topic_path = (ditamap_path.parent / topic_href).resolve()
                topic_xml = topic_path.read_text(encoding="utf-8")
                topic_doc = parser.parse_string(topic_xml, base_dir=topic_path.parent).document
                image_hrefs = _collect_image_hrefs(topic_doc["root"])
                _assert_hrefs_resolve(
                    image_hrefs, topic_path.parent, f"{label} -> {topic_path.name}"
                )
