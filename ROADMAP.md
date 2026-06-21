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
