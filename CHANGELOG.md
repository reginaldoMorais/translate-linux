# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Project scaffolding: `src` layout, packaging metadata and console entry point.
- Development tooling: ruff (lint and format), mypy in strict mode, pytest.
- `make dev-setup`, which builds the virtualenv with the distribution
  interpreter so that PyGObject stays visible.
- Continuous integration on `ubuntu-24.04`, matching the Zorin OS 18 base.
- Specification and handoff documents under `docs/plans/`.
