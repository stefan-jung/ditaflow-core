# Roadmap

Living document for ditaflow-core. Update this as priorities change — it's
the source of truth for "what's next," not a historical record (use
CHANGELOG.md and git history for that).

## In progress / next up

- [ ] Cut the first `v0.1.0` tag and publish to PyPI. The `release` CI job
      already exists and is conditioned on `v*` tags — it has just never
      fired. Until then, every downstream repo installs from source.

## Planned

- [ ] Decide on and publish the TypeScript types package
      (`schema/ditaflow.types.ts`) so frontend tooling (xephon-cms's React
      editor) can depend on it via npm instead of copying the file.
- [ ] Grow `tests/round_trip/fixtures/projects/` beyond the single
      `product-manual` example as new cross-file edge cases come up
      (nested keyscopes across maps, ditavalref chains, conref across
      projects).

## Feature requests from the CMS roadmap (2026-06-21, not yet scoped)

Stefan's feature wishlist for Xephon CMS (see xephon-cms/ROADMAP.md) implies
one thing that touches the format itself, not just the CMS:

- [ ] **"Variables" (Paligo-style)** — likely already covered by the
      existing keyref/keydef mechanism (a variable is just a key that
      resolves to a `<keyword>`/`<ph>` value) rather than a new DTF
      construct. Needs validating against a real CMS-side "insert
      variable" UI once that's built, in case there's a gap (e.g.
      variable sets scoped per-output-channel rather than per-keyscope).

Everything else in that wishlist (project/task management, review
workflows, multi-tenancy, billing, etc.) is CMS/platform-level and doesn't
imply a DTF format change — see xephon-cms/ROADMAP.md instead.

## Deferred / explicitly out of scope for now

- Reusable, named DITAVAL filter profiles as a first-class DTF construct.
  Branch filtering currently stays inline inside a map's `inlinedDitaval`
  (spec §6) — promoting this to a shared/named profile is a CMS-level
  feature (see xephon-cms's ROADMAP.md), not a core-format change, unless
  it turns out the format itself needs to change to support it.

## Done

- DITA 1.3 + 2.0 topic/map conversion, specializations (classChain-based),
  conref/conkeyref, keyref/keydef, nested keyscopes, branch filtering,
  CALS + simple tables, PIs, comments — full bidirectional round-trip with
  semantic-identity guarantee.
- CLI (`dtf convert|validate|roundtrip`).
- CI: lint/format/mypy/pytest matrix (3.12/3.13), round-trip job, job
  summaries, codecov upload.
- `ditaflow.validator.content_model.ContentModelChecker` — approximate,
  baseType-keyed content-model check on DTF JSON (not the official
  grammar).
- `ditaflow.validator.relaxng_validator.RelaxNgValidator` — real RELAX NG
  validation of serialized DITA XML against the official DITA 1.3 grammar
  (vendored from dita-ot, Apache-2.0), covering topic/concept/task/
  reference/map/bookmap/glossentry/glossgroup/troubleshooting/learning*
  (8 learning shells: Content/Overview/Assessment/Plan/Summary/Map/
  GroupMap/ObjectMap, plus learningBookmap). 105 vendored `.rng` files
  total (up from 71 -- see ditaflow/schemas/dita1.3/LICENSE-DITA-OT.txt
  for the two narrow, documented deviations from the upstream files, both
  the same libxml2/RNG interoperability gap already hit once before with
  MathML). No XML catalog support (not needed — every vendored grammar
  module resolves via plain relative-path includes). No DITA 2.0 support
  (no public RELAX NG grammar exists for it yet).

## Known issue (fast-follow, not yet filed as its own task)

- `schema/ditaflow.schema.json` lives outside the `ditaflow` package
  directory and is located via a `Path(__file__)` parent-walk in
  `dtf_validator.py` — this only works for an editable (`pip install -e`)
  install, not a real wheel (confirmed: a built wheel does not contain
  `schema/ditaflow.schema.json` at all). Move it under `ditaflow/schema/`
  before the first PyPI release, same fix already applied to the new
  RELAX NG schemas in `ditaflow/schemas/`.
