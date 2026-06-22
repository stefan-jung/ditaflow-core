"""Pure parsing of DITA's ``class`` attribute classChain string -- e.g.
``"+ topic/ph hi-d/b "`` -- shared by dita_parser.py (parsing real
documents) and ditaflow.grammar.element_registry (deriving the same fact
from the grammar's own attribute defaults). Split out from DitaParser
specifically to avoid a circular import: element_registry.py needs this,
and specialisation_registry.py (which dita_parser.py itself imports) in
turn needs element_registry.py.
"""

from __future__ import annotations


def base_type_from_class_string(class_string: str) -> str:
    body = class_string.strip()
    if body and body[0] in "+-":
        body = body[1:].strip()
    first_pair = body.split(" ", 1)[0] if body else ""
    return first_pair.split("/", 1)[1] if "/" in first_pair else first_pair
