# Changelog

All notable changes to DitaFlow Core are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Initial DitaFlow (.dtf) format specification v1.0.0
- TypeScript type definitions (`schema/ditaflow.types.ts`)
- JSON Schema Draft 7 (`schema/ditaflow.schema.json`)
- Format specification document (`spec/DITAFLOW-SPEC.md`)
- Project structure and build configuration
- DITA XML <-> DitaFlow converter (`ditaflow/converter/`): parser, serializer,
  and specialization registry, covering topics, maps/bookmaps, conref/conkeyref,
  keyref/keyscopes, branch filtering (ditavalref/DITAVAL), CALS and simple tables
- JSON Schema validator (`ditaflow/validator/`) and `dtf` CLI
  (`convert`, `validate`, `roundtrip`)
- Round-trip and unit test suite (`tests/`) proving semantic-identity
  round-tripping, including for specializations unknown to the registry

### Changed
- Spec rewritten from German to English; clarified round-trip semantics,
  the `attrs._ext` extension-attribute mechanism, and the mark-vs-element
  collapsing rule for inline formatting
- Added the previously-missing mandatory `title` field to the topic node
  shape in the schema and types
- Reconciled the JSON Schema's attribute list and table node definitions
  with the TypeScript types (both had independent gaps)
