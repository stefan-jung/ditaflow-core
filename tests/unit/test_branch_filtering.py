"""ditavalref parsing (spec/DITAFLOW-SPEC.md §6): href/keyref preservation,
and inline resolution of a referenced .ditaval file into inlinedDitaval."""

from __future__ import annotations

from pathlib import Path

from ditaflow.converter.dita_parser import DitaParser

MAP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<map id="m1">
  <title>M</title>
  <topicref href="a.dita">
    <ditavalref href="filters/server.ditaval" dvrKeyscopePrefix="server-"/>
  </topicref>
</map>
"""


def test_ditavalref_without_base_dir_keeps_href_only() -> None:
    result = DitaParser().parse_string(MAP_XML)
    ref = result.document["root"]["topicrefs"][0]["ditavalrefs"][0]
    assert ref["href"] == "filters/server.ditaval"
    assert ref["dvrKeyscopePrefix"] == "server-"
    assert "inlinedDitaval" not in ref


def test_ditavalref_with_base_dir_inlines_ditaval_rules(tmp_path: Path) -> None:
    filters_dir = tmp_path / "filters"
    filters_dir.mkdir()
    (filters_dir / "server.ditaval").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
        <val>
          <prop att="product" val="Server" action="include"/>
          <prop att="product" action="exclude"/>
        </val>
        """,
        encoding="utf-8",
    )

    result = DitaParser().parse_string(MAP_XML, base_dir=tmp_path)
    ref = result.document["root"]["topicrefs"][0]["ditavalrefs"][0]
    profile = ref["inlinedDitaval"]
    assert profile["props"] == [
        {"att": "product", "val": "Server", "action": "include"},
        {"att": "product", "action": "exclude"},
    ]
