# DitaFlow Core

**The canonical JSON representation of the DITA Information Model.**

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](https://python.org)

DitaFlow Core provides:

- **The `.dtf` format** — a lossless JSON representation of DITA XML 1.3 and 2.0
- **Bidirectional converter** — DITA XML ↔ DitaFlow, with full round-trip fidelity
- **Branch Filter processor** — `ditavalref` and Keyscope resolution
- **Validator** — JSON Schema + DITA semantic validation
- **CLI** — `dtf convert`, `dtf validate`, `dtf roundtrip`
- **TypeScript types** — for use in editors and frontend tooling

## What is DitaFlow (.dtf)?

DitaFlow is a lossless JSON encoding of the DITA Information Model. Every valid DITA XML document (including specialisations, branch filtering, and keyscopes) can be imported to `.dtf` and exported back to byte-compatible DITA XML.

```json
{
  "dtf": "ditaflow",
  "dtfVersion": "1.0.0",
  "ditaVersion": "1.3",
  "doctype": "task",
  "classChain": ["- topic/topic task/task "],
  "baseDoctype": "topic",
  "root": {
    "type": "task",
    "classChain": ["- topic/topic task/task "],
    "baseType": "topic",
    "attrs": { "id": "my-task", "xml:lang": "en-US" },
    "content": [],
    "body": { "..." : "..." }
  }
}
```

## Installation

Not yet published to PyPI (still pre-release — the `release` CI job publishes
on `v*` tags, which haven't been cut yet). Install from source for now:

```bash
git clone https://github.com/ditaflow/ditaflow-core.git
cd ditaflow-core
pip install -e .
```

Once a `v*` tag is released, this will become:

```bash
pip install ditaflow-core
```

## Quick Start

```python
from ditaflow.converter.dita_parser import DitaParser
from ditaflow.converter.dita_serializer import DtfSerializer

# DITA XML → DitaFlow
parser = DitaParser()
result = parser.parse_file("my-topic.dita")
dtf_doc = result.document

# DitaFlow → DITA XML
serializer = DtfSerializer()
xml_result = serializer.serialize(dtf_doc)
print(xml_result.xml)
```

### CLI

```bash
# Convert DITA to DTF
dtf convert input.dita --output output.dtf

# Convert DTF back to DITA XML
dtf convert input.dtf --output output.dita

# Validate a DTF document
dtf validate my-doc.dtf

# Round-trip test (DITA → DTF → DITA, check for diff)
dtf roundtrip my-topic.dita
```

## DITA Feature Coverage

| Feature | Status |
|---|---|
| Topics (concept, task, reference) | ✅ |
| Maps and Bookmaps | ✅ |
| Conref / Conkeyref / Conrefend | ✅ |
| Keyref / Keydef | ✅ |
| Keyscopes (nested) | ✅ |
| Branch Filtering (ditavalref) | ✅ |
| DITAVAL profiles | ✅ |
| Specialisations (via classChain) | ✅ |
| CALS tables | ✅ |
| Simple tables | ✅ |
| Processing Instructions | ✅ |
| XML comments | ✅ |
| DITA 1.3 | ✅ |
| DITA 2.0 | ✅ |

## Project Structure

```
ditaflow-core/
├── schema/
│   ├── ditaflow.types.ts      # TypeScript type definitions
│   └── ditaflow.schema.json   # JSON Schema (Draft 7)
├── spec/
│   └── DITAFLOW-SPEC.md       # Format specification
├── ditaflow/
│   ├── converter/
│   │   ├── dita_parser.py             # DITA XML → DTF
│   │   ├── dita_serializer.py         # DTF → DITA XML
│   │   ├── specialisation_registry.py
│   │   └── plugins/                   # Specialisation plugins
│   ├── validator/
│   │   └── dtf_validator.py
│   └── cli/
│       └── dtf.py
└── tests/
    ├── unit/                  # Focused tests for one converter rule at a time
    └── round_trip/
        ├── test_roundtrip.py          # single-file feature fixtures
        ├── test_project_roundtrip.py  # multi-file project fixtures
        └── fixtures/
            ├── dita/          # single .dita/.ditamap files, one feature each
            └── projects/      # multi-file projects (map + topics + assets)
```

## Testing

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

pytest                          # everything: unit + round-trip
pytest tests/unit/              # unit tests only
pytest tests/round_trip/        # round-trip tests only
pytest --cov=ditaflow           # with coverage
ruff check . && ruff format --check . && mypy ditaflow/   # lint, format, types
```

The round-trip guarantee this suite checks is **semantic identity**, not
byte-for-byte identity (see spec/DITAFLOW-SPEC.md §9): DITA → DTF → DITA must
produce a document that re-parses back to the same DTF — not necessarily the
same bytes (e.g. pretty-printing isn't preserved).

### Adding a test for one DITA construct

Use this when you want to prove a single feature round-trips (a table
variant, a new domain element, a DITA 2.0 construct, an edge case) — most new
tests should be this kind.

1. Drop a `.dita` file into `tests/round_trip/fixtures/dita/`, named after
   what it tests (e.g. `task_with_nested_keyscopes.dita`).
2. That's it. `test_roundtrip.py` globs every `*.dita` file in that directory
   and parametrizes over it automatically — no code change required.
3. If you also want to assert something specific about the parsed structure
   (not just "it round-trips"), add a matching test in `tests/unit/`, e.g.
   `tests/unit/test_branch_filtering.py` for ditavalref parsing.

### Adding a test for a full project

Use this when the thing you're testing only shows up *across* files — a
topicref `href` that must keep resolving to the right relative path, an
image reference inside a referenced topic, a `ditavalref` pointing at a
`.ditaval` file. A single isolated `.dita` file can't exercise this; see
`tests/round_trip/fixtures/projects/product-manual/` for a worked example.

1. Create `tests/round_trip/fixtures/projects/<scenario-name>/` and lay it
   out like a real authoring project, e.g.:
   ```
   <scenario-name>/
   ├── root.ditamap
   ├── topics/*.dita
   ├── images/
   └── filters/*.ditaval
   ```
2. Make sure `href` attributes between files actually resolve (e.g.
   `<chapter href="topics/foo.dita">`, and inside `foo.dita`,
   `<image href="../images/bar.png">`).
3. That's it. `test_project_roundtrip.py` discovers every subdirectory of
   `fixtures/projects/`, round-trips every `.dita`/`.ditamap` file inside it
   individually, and separately checks that every topicref/image `href`
   still resolves to a real file both before and after the round trip.

### Don't commit real customer content

This is the public, open-source repo. Fixtures here should be synthetic —
invented content that exercises a DITA construct, like the existing
fixtures. Don't commit real customer/production DITA here; if you need to
test against real-world content, do it in a private location instead.

## Relationship to Xephon CMS

DitaFlow Core is the open-source foundation of the [Xephon CMS](https://xephon.io).
The core format and converter are maintained independently and can be used
with any toolchain — DITA-OT pipelines, CI/CD systems, or custom editors.

## Contributing

Contributions are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) before
submitting a pull request. All contributions are licensed under Apache 2.0.

## License

Apache License 2.0 — see [LICENSE](LICENSE).
