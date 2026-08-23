# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.0.1] - 2026-08-23

### Added

- Interactive region capture through `org.freedesktop.portal.Screenshot`,
  which lets the GNOME Shell draw its native selection interface. The
  `Response` signal is subscribed before the call is issued, so a fast reply
  cannot be lost.
- Image pre-processing (greyscale, upscaling, contrast stretch) bounded by a
  pixel budget.
- Tesseract recognition through TSV output, carrying per-word confidence.
- OCR text normalisation: de-hyphenation, paragraph-preserving line joining,
  Unicode NFC and whitespace collapsing.
- Translation through the official Cloud Translation API v2, with chunking,
  batching, retry with exponential backoff and structure-preserving reassembly.
- API key storage in the login keyring through libsecret.
- `--capture`, `--ocr-only`, `--json`, `--set-api-key`, `--clear-api-key` and
  `--portal-info` commands.
- `scripts/verify_portal_behaviour.py`, which answers whether an interactive
  portal capture leaves a copy behind.

## [0.0.0]

### Added

- Project scaffolding: `src` layout, packaging metadata and console entry point.
- Development tooling: ruff (lint and format), mypy in strict mode, pytest.
- `make dev-setup`, which builds the virtualenv with the distribution
  interpreter so that PyGObject stays visible.
- Continuous integration on `ubuntu-24.04`, matching the Zorin OS 18 base.
- Specification and handoff documents under `docs/plans/`.
