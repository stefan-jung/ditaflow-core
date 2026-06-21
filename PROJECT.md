# Project: DitaFlow Core

## What this is

The open-source foundation of the Xephon project: a lossless JSON encoding
of the DITA Information Model (`.dtf`), plus a bidirectional converter,
branch-filter/keyscope processor, validator, and CLI. Any valid DITA XML
document (1.3 or 2.0, including specializations) can round-trip through
`.dtf` and back to semantically identical DITA XML — see
[spec/DITAFLOW-SPEC.md](spec/DITAFLOW-SPEC.md) §9 for the exact round-trip
guarantee (semantic identity, not byte-for-byte).

This repo is deliberately toolchain-agnostic — it has no dependency on
Xephon CMS and is usable with DITA-OT pipelines, other CI/CD systems, or
custom editors. Apache 2.0, public.

## Why it's separate from Xephon CMS

Xephon CMS needs a format that lets it store and query DITA content without
parsing XML at request time. Keeping the format/converter as its own
package means: it can be versioned and tested independently of the CMS,
other tools can adopt `.dtf` without buying into the CMS, and the CMS's
own test suite doesn't have to also prove DITA-conformance — this repo's
round-trip suite already does.

## Architecture

```
ditaflow-core/
├── schema/            ditaflow.types.ts (TS types), ditaflow.schema.json (JSON Schema)
├── spec/               DITAFLOW-SPEC.md — the format specification
├── ditaflow/
│   ├── converter/      dita_parser.py (XML→DTF), dita_serializer.py (DTF→XML),
│   │                   specialisation_registry.py, plugins/
│   ├── validator/      dtf_validator.py (JSON Schema + DITA semantic checks)
│   └── cli/            dtf.py — `dtf convert|validate|roundtrip`
└── tests/
    ├── unit/           one converter rule at a time
    └── round_trip/     fixtures/dita/ (single-file) and fixtures/projects/ (multi-file)
```

## Tech stack

Python 3.12+, mypy (strict), ruff, pytest + pytest-cov, hatchling build
backend (note: `[tool.hatch.build.targets.wheel] packages = ["ditaflow"]`
is required explicitly — the PyPI distribution name `ditaflow-core`
doesn't match the importable package name `ditaflow`).

## Relationship to other repos

Consumed by `xephon-cms` and `xephon-ai` as a dependency. Not yet published
to PyPI — no `v*` tag has been cut, so downstream repos install it from
source (`pip install -e ditaflow-core` after a sibling checkout; this is
exactly what `xephon-cms`'s CI workflow does).

## Status

Converter, validator, branch filtering, keyscopes, and CLI are implemented
with a passing round-trip test suite (see README's feature-coverage table —
all rows currently checked). Pre-1.0: no release has been tagged yet.

See [ROADMAP.md](ROADMAP.md) for what's next.
