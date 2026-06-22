"""Unit tests for overrides.py. The real OVERRIDES table is empty (see its
module docstring) -- these tests exercise the lookup mechanism itself
using a synthetic entry, since there's no real one to assert against yet.
"""

from __future__ import annotations

from ditaflow.converter.specialisation_registry import SpecialisationEntry
from ditaflow.grammar.overrides import OVERRIDES, lookup_override


def test_unregistered_name_returns_none():
    assert lookup_override("does-not-exist") is None


def test_registered_override_is_returned(monkeypatch):
    fake = SpecialisationEntry(
        element_name="widget",
        dita_class="- topic/ph base/widget ",
        base_element="ph",
        module="base",
        allows_content=True,
        is_inline=True,
    )
    monkeypatch.setitem(OVERRIDES, "widget", fake)
    assert lookup_override("widget") is fake


def test_overrides_table_is_currently_empty():
    # Documents the current state explicitly (see module docstring for
    # why) -- this should fail loudly, not silently, the day an entry is
    # added, as a prompt to write a real targeted test for it.
    assert OVERRIDES == {}
