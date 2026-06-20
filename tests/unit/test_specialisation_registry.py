from __future__ import annotations

from ditaflow.converter.specialisation_registry import (
    SpecialisationEntry,
    SpecialisationRegistry,
)


def test_known_element_is_registered() -> None:
    registry = SpecialisationRegistry()
    entry = registry.lookup("step")
    assert entry is not None
    assert entry.base_element == "li"
    assert entry.module == "task"
    assert entry.dita_class == "- topic/li task/step "


def test_unknown_element_returns_none() -> None:
    registry = SpecialisationRegistry()
    assert registry.lookup("apiOperation") is None
    assert "apiOperation" not in registry


def test_register_adds_new_entry() -> None:
    registry = SpecialisationRegistry()
    registry.register(
        SpecialisationEntry(
            element_name="apiOperation",
            dita_class="+ topic/section reference/section apiRef-d/apiOperation ",
            base_element="section",
            module="apiRef-d",
            allows_content=True,
            is_inline=False,
        )
    )
    entry = registry.lookup("apiOperation")
    assert entry is not None
    assert entry.base_element == "section"
    assert "apiOperation" in registry
