# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.1.0] - 2026-08-24

### Added

- An About window, reachable from the tray menu and from the preferences.
  Its troubleshooting section carries the same report `--doctor` prints,
  copyable in one click: with no telemetry, supporting an installation
  depends on the user being able to hand that over without opening a
  terminal.
- Brazilian Portuguese as a target of its own. The catalogue spells it `pb`,
  and the generic `pt` model produces largely European Portuguese -- "ficheiro",
  "ecrã", "estou a trabalhar" -- which reads as a foreign translation rather
  than a weak one. A `pt_BR` locale now selects `pb` by default, and the code
  is translated to `pt-BR` on the way to an online provider, which does not
  know the catalogue's spelling.

## [1.0.1] - 2026-08-23

Three defects found on a real installation outside the development
machine. All three failed silently, which is what made them worth
recording rather than merely fixing.

### Fixed

- The package did not depend on `python3-venv` or `python3-pip`, so
  `--install-engine` could not build the private virtualenv at all.
  `python3 -m venv` creates the directory tree before it fails on
  ensurepip, which left something that looked installed and was not.
  Installation now clears a half-built virtualenv before retrying, leaves
  nothing behind on failure, names the apt command that fixes a missing
  dependency, and finishes by importing the engine rather than trusting
  that files appeared.
- Adwaita parses toast titles as Pango markup, so a shortcut such as
  `<Super><Shift>t` looked like an unknown tag and the widget rendered
  nothing at all: confirming a shortcut produced an empty box with a
  close button. Dynamic text going into a markup-aware widget is escaped.
- `--capture` never contacted the running tray. A global shortcut can
  only run a command, so the shortcut started a second, headless process
  that captured into a terminal nobody was looking at, and appeared to do
  nothing. The application now exposes a `capture` action over
  `org.freedesktop.Application` and the command activates it, which also
  makes it irrelevant which `translate-linux` comes first on `PATH`.
- A missing GSettings schema aborted the process through `g_error`
  instead of raising, which would have taken the application down on any
  desktop that is not GNOME.

## [1.0.0] - 2026-08-23

### Added

- A `.deb` package, built by assembling the tree and calling dpkg-deb, with a
  desktop entry, an icon and the GSettings schema compiled on install.
- A release workflow triggered by a `v*` tag: it refuses to publish when the
  tag and `__version__` disagree, runs the whole suite, builds the package and
  installs it into a clean Ubuntu container before publishing.
- `docs/manual-test-plan.md`, the roadmap the maintainer runs on real hardware
  before tagging, since CI has no Wayland, no GNOME Shell, no capture portal
  and no tray.

### Changed

- The application id is now `io.github.reginaldomorais.TranslateLinux`, matching
  the repository owner. It is the GSettings schema id, the D-Bus name and the
  libsecret schema, so settings stored under the previous id are not carried
  over; the defaults simply apply again.

### Fixed

- A missing GSettings schema aborted the process through `g_error` instead of
  raising, which would have taken the application down on any desktop that is
  not GNOME.

## [0.3.0] - 2026-08-23

### Added

- Settings that persist, backed by GSettings, with a schema declaring types,
  ranges and defaults.
- A preferences window covering languages, provider, recognition, offline
  models, autostart and the global shortcut.
- An XDG autostart entry, delayed so the shell has a tray host ready before
  the icon tries to appear.
- A global capture shortcut registered through GNOME's custom keybindings,
  with conflict detection.
- A consent dialog shown only when an online provider is chosen; local
  translation never asks, because nothing leaves the machine.
- `--doctor`, which reports every environment dependency, plus `--autostart`
  and `--shortcut`.

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
