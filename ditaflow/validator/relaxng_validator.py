"""Validates serialized DITA XML against the official DITA 1.3 RELAX NG
grammars vendored from dita-ot (Apache-2.0; see
ditaflow/schemas/dita1.3/LICENSE-DITA-OT.txt for provenance and the
deliberate deviations from the upstream files -- the MathML domain
include (removed from topic/glossentry/glossgroup/troubleshooting) and
troubleshooting.rng's task-info-types override (removed), both because of
the same libxml2/RNG interoperability gap: libxml2 rejects an `<include>`
override whose target define is only present in the included grammar
*transitively* (via that file's own nested `<include>`), even though
that's valid per RELAX NG's spec semantics. Neither deviation is
DITA-content-relevant -- see the package's LICENSE-DITA-OT.txt for the
full per-file note.

Unlike DtfValidator (JSON Schema, structural) and ContentModelChecker
(hand-written, baseType-keyed approximation), this validator operates on
**serialized XML strings**, not DTF JSON dicts -- RELAX NG validation is
necessarily a later-stage check against the serializer's *output*, since
that's what the grammar describes. See app/services/export.py in
xephon-cms for how the three checks compose.

No XML catalog support: every grammar module's `<include>`/`<externalRef>`
reference in the vendored files is a relative file path, not a catalog
public-identifier indirection, so plain base-URI resolution is sufficient
(see the module-level note on `_compiled_schema` for the one detail that
makes this work reliably). Catalogs in dita-ot exist for resolving
arbitrary third-party DITA files' DOCTYPE/PUBLIC-ID declarations and for
Schematron association -- neither applies to validating our own
serializer's output against a doctype we already know.

No DITA 2.0 support: no public RELAX NG grammar for DITA 2.0 exists yet
(checked dita-ot's repository directly -- no `v2_0`-named schema path).
`supports()` returns False for any doctype outside the dispatch table
below, so callers can degrade gracefully rather than guess.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import as_file, files

from lxml import etree

_SCHEMA_ROOT = files("ditaflow") / "schemas" / "dita1.3"

# doctype -> path (relative to _SCHEMA_ROOT) of the shell .rng to compile.
# generalTask.rng, not task.rng: it's DITA-OT's own modern default shell
# for task (relaxed step ordering) since DITA 1.3, and ditaflow-core's task
# support (steps/step/cmd/info) is a strict subset of what it accepts --
# task.rng's fixed-sequence ordering risks flagging legitimate output as
# ditaflow-core's task support grows. Matching DITA-OT's own default also
# keeps this check consistent with what a downstream DITA-OT publish run
# will itself enforce.
_SHELLS: dict[str, str] = {
    "topic": "technicalContent/rng/topic.rng",
    "concept": "technicalContent/rng/concept.rng",
    "task": "technicalContent/rng/generalTask.rng",
    "reference": "technicalContent/rng/reference.rng",
    "map": "technicalContent/rng/map.rng",
    "bookmap": "bookmap/rng/bookmap.rng",
    "glossentry": "technicalContent/rng/glossentry.rng",
    "glossgroup": "technicalContent/rng/glossgroup.rng",
    "troubleshooting": "technicalContent/rng/troubleshooting.rng",
    "learningContent": "learning/rng/learningContent.rng",
    "learningOverview": "learning/rng/learningOverview.rng",
    "learningAssessment": "learning/rng/learningAssessment.rng",
    "learningPlan": "learning/rng/learningPlan.rng",
    "learningSummary": "learning/rng/learningSummary.rng",
    "learningMap": "learning/rng/learningMap.rng",
    "learningGroupMap": "learning/rng/learningGroupMap.rng",
    "learningObjectMap": "learning/rng/learningObjectMap.rng",
    "learningBookmap": "learning/rng/learningBookmap.rng",
}


@dataclass(frozen=True)
class RelaxNgResult:
    errors: list[str]

    @property
    def is_valid(self) -> bool:
        return not self.errors


@lru_cache(maxsize=len(_SHELLS))
def _compiled_schema(doctype: str) -> etree.RelaxNG:
    """Compiles (and, via lru_cache, permanently caches) the RELAX NG shell
    for one doctype. Lazy on purpose -- compiling the full transitive
    grammar is real but bounded work (low hundreds of ms), and a process
    that only ever exports one doctype should never pay for the others.

    Must go through `as_file()` to get a real, materialized filesystem
    path before parsing: the grammar's own `<include href="...">`
    references are relative file paths that libxml2 resolves against the
    *parsed document's base URI* -- parsing from bytes/a string (e.g. via
    `etree.fromstring(resource.read_bytes())`) has no base URI, and the
    relative includes silently fail to resolve. `as_file()` guarantees a
    real path even when the package is installed from a zipped wheel.
    """
    rel_path = _SHELLS[doctype]  # KeyError on an unknown doctype is intentional
    resource = _SCHEMA_ROOT / rel_path
    with as_file(resource) as real_path:
        return etree.RelaxNG(etree.parse(str(real_path)))


class RelaxNgValidator:
    """Validates a serialized DITA XML string against the DITA 1.3 RELAX
    NG shell grammar matching the given doctype.
    """

    def supports(self, doctype: str) -> bool:
        return doctype in _SHELLS

    def validate(self, xml: str, doctype: str) -> RelaxNgResult:
        if doctype not in _SHELLS:
            return RelaxNgResult(errors=[f"no RELAX NG grammar for doctype '{doctype}'"])
        schema = _compiled_schema(doctype)
        # No base URI needed here -- only the grammar's own internal
        # includes depend on one, not the instance document being checked.
        doc = etree.fromstring(xml.encode("utf-8"))
        if schema.validate(doc):
            return RelaxNgResult(errors=[])
        return RelaxNgResult(errors=[str(e) for e in schema.error_log])
