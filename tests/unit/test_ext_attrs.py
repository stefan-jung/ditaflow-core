"""attrs._ext (spec/DITAFLOW-SPEC.md §7): catches both genuinely unknown
attributes and standard-but-unmodeled DITA attributes (e.g. domains), and
round-trips them verbatim."""

from __future__ import annotations

from ditaflow.converter.dita_parser import DitaParser
from ditaflow.converter.dita_serializer import DtfSerializer

XML = """<?xml version="1.0" encoding="UTF-8"?>
<topic id="t1" domains="(topic hi-d) (topic ut-d)">
  <title>T</title>
  <body>
    <p data-cms-id="abc123">Hello</p>
  </body>
</topic>
"""


def test_unmodeled_and_unknown_attrs_land_in_ext() -> None:
    document = DitaParser().parse_string(XML).document
    root_attrs = document["root"]["attrs"]
    assert root_attrs["id"] == "t1"
    assert root_attrs["_ext"] == {"domains": "(topic hi-d) (topic ut-d)"}

    p_node = document["root"]["body"]["content"][0]
    assert p_node["attrs"]["_ext"] == {"data-cms-id": "abc123"}


def test_ext_attrs_round_trip_verbatim() -> None:
    document = DitaParser().parse_string(XML).document
    xml = DtfSerializer().serialize(document).xml
    reparsed = DitaParser().parse_string(xml).document
    assert reparsed["root"]["attrs"]["_ext"] == {"domains": "(topic hi-d) (topic ut-d)"}
    p_node = reparsed["root"]["body"]["content"][0]
    assert p_node["attrs"]["_ext"] == {"data-cms-id": "abc123"}
