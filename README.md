# DitaFlow Core

**The canonical JSON representation of the DITA Information Model.**

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](https://python.org)
[![PyPI](https://img.shields.io/pypi/v/ditaflow-core)](https://pypi.org/project/ditaflow-core/)

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

```bash
pip install ditaflow-core
```

## Quick Start

```python
from ditaflow.converter import DitaParser, DitaSerializer

# DITA XML → DitaFlow
parser = DitaParser()
result = parser.parse_file("my-topic.dita")
dtf_doc = result.document

# DitaFlow → DITA XML
serializer = DitaSerializer()
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
├── converter/
│   ├── dita_parser.py         # DITA XML → DTF
│   ├── dita_serializer.py     # DTF → DITA XML
│   ├── branch_processor.py    # Branch Filter & Keyscope engine
│   ├── specialisation_registry.py
│   └── plugins/               # Specialisation plugins
├── validator/
│   └── dtf_validator.py
├── cli/
│   └── dtf.py
└── tests/
    ├── unit/
    └── round_trip/
        └── fixtures/
            ├── dita/          # DITA XML test files
            └── dtf/           # Expected DTF output
```

## Relationship to Xephon CMS

DitaFlow Core is the open-source foundation of the [Xephon CMS](https://xephon.io).
The core format and converter are maintained independently and can be used
with any toolchain — DITA-OT pipelines, CI/CD systems, or custom editors.

## Contributing

Contributions are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) before
submitting a pull request. All contributions are licensed under Apache 2.0.

## License

Apache License 2.0 — see [LICENSE](LICENSE).
