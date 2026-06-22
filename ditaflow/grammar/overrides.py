"""Manual correction table for documented exceptions to grammar-derived
element metadata. Consulted first in SpecialisationRegistry's lookup
chain (manual overrides -> grammar registry -> hand-curated _CORE_PROFILE
-> None), ahead of the grammar registry itself -- the successor role
specialisation_registry.py's own hand data used to play alone, now
narrowed to just the rare cases where grammar derivation genuinely needs
correcting.

Starts empty: every element checked so far while building the grammar
registry (element_registry.py's Tier 2 real-grammar tests, plus the
SpecialisationRegistry seam test in test_grammar_element_registry.py)
derives correctly from the grammar alone, with no override needed.

Add an entry here only with a comment explaining *why* grammar derivation
is insufficient for that specific element -- this table exists for rare,
documented corrections, not to become a second hand-curated registry by
accretion. An override is a full SpecialisationEntry, not a partial patch:
when grammar derivation is wrong for an element, replacing the whole
record is simpler than merging field-by-field, and matches how rare these
entries are expected to stay.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Deferred to break a real cycle: specialisation_registry.py (which
    # defines SpecialisationEntry) imports this module to consult
    # OVERRIDES, so this module can't import it back at runtime. Safe
    # because `from __future__ import annotations` makes every annotation
    # in this file a lazy string -- never evaluated at runtime, only read
    # by mypy, which does see real imports like this one.
    from ditaflow.converter.specialisation_registry import SpecialisationEntry

OVERRIDES: dict[str, SpecialisationEntry] = {}


def lookup_override(element_name: str) -> SpecialisationEntry | None:
    return OVERRIDES.get(element_name)
