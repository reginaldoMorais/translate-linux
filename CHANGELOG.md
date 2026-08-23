# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-08-23

### Added

- A tray icon, implemented by speaking StatusNotifierItem and
  com.canonical.dbusmenu directly over D-Bus, and `--tray` to run resident.
- A GTK4 result window in Brazilian Portuguese showing the translation, the
  recognised text, and a way to correct that text and translate again.
- A local translation cache, composed onto any provider as a decorator.
- `capture_async`, a non-blocking capture for use inside the GTK main loop.
- `recognise_and_translate` and `translate_text`, which separate recognition
  from capture so the tray can capture asynchronously.

### Changed

- libayatana-appindicator3 is not used: it is built against GTK 3 and cannot
  be loaded beside GTK 4.

## [0.1.0] - 2026-08-23

### Added

- Offline translation with CTranslate2 and OPUS-MT models, now the default
  provider: no per-character cost, no network, and nothing leaves the machine.
- `--install-engine`, `--install-model` and `--list-models` commands.
- `--provider` to choose between the local engine and the Google API, and
  `--source` for language pairs that do not start from English.
- `split_sentences`, which always cuts at paragraph and sentence boundaries so
  that layout survives translation whatever the length of the text.
- A guard in the unit suite that fails loudly if a test reaches the real
  screenshot portal.

### Changed

- The Cloud Translation API is no longer the default provider; it remains
  available through `--provider google`.

### Fixed

- `restore_padding` doubled the content of a whitespace-only chunk.

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
