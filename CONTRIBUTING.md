# Contributing to DitaFlow Core

Thank you for your interest in contributing.

## Before You Start

- Check the [open issues](https://github.com/ditaflow/ditaflow-core/issues) for existing discussions.
- For significant changes, open an issue first to discuss the approach.
- All contributions are licensed under Apache 2.0.

## Development Setup

```bash
git clone https://github.com/ditaflow/ditaflow-core.git
cd ditaflow-core
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Running Tests

```bash
pytest                          # all tests
pytest tests/unit/              # unit tests only
pytest tests/round_trip/        # round-trip tests only
pytest --cov=ditaflow           # with coverage
```

## Code Style

This project uses `ruff` for linting and formatting, and `mypy` for type checking.

```bash
ruff check .
ruff format .
mypy ditaflow/
```

All checks must pass before a pull request can be merged.

## Commit Convention

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add support for DITA 2.0 specialisations
fix: correct classChain reconstruction for domain elements
docs: update round-trip guarantee table in spec
test: add round-trip fixtures for bookmap
chore: bump lxml to 5.3.0
```

A `feat!:` or `fix!:` prefix (with `!`) signals a breaking change
and will trigger a major version bump in the release pipeline.

## Pull Request Checklist

- [ ] Tests added or updated for all changed behaviour
- [ ] `ruff` and `mypy` pass with no errors
- [ ] CHANGELOG.md updated under `[Unreleased]`
- [ ] Round-trip fixtures added if new DITA features are supported
- [ ] Commit messages follow the Conventional Commits convention

## Round-Trip Test Fixtures

When adding support for new DITA elements or features, add matching fixtures:

```
tests/round_trip/fixtures/dita/my-feature.dita   ← input DITA XML
tests/round_trip/fixtures/dtf/my-feature.dtf     ← expected DTF output
```

The round-trip test suite verifies DITA → DTF → DITA produces identical XML.
