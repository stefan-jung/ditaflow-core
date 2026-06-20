"""Validates DTF document dicts against schema/ditaflow.schema.json."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import jsonschema

_SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent / "schema" / "ditaflow.schema.json"


@lru_cache(maxsize=1)
def _load_schema() -> dict[str, Any]:
    schema: dict[str, Any] = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    return schema


class DtfValidator:
    """Validates a DTF document dict against the JSON Schema."""

    def __init__(self) -> None:
        self._validator = jsonschema.Draft7Validator(_load_schema())

    def validate(self, document: dict[str, Any]) -> list[str]:
        """Returns a list of human-readable error messages (empty if valid)."""
        errors = sorted(self._validator.iter_errors(document), key=lambda e: list(e.path))
        return [f"{'/'.join(str(p) for p in e.path)}: {e.message}" for e in errors]

    def is_valid(self, document: dict[str, Any]) -> bool:
        return bool(self._validator.is_valid(document))
