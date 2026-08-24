"""Command-line entry point.

Milestone M1 exposes the whole pipeline through ``--capture``; the tray icon,
the result window and the D-Bus single-instance activation of RF-09/RF-10
arrive in M2.

Imports that pull in PyGObject or an HTTP stack are deferred into the command
handlers, so ``--version`` stays instant and works without a session bus
(NFR-P2, NFR-P4).
"""

from __future__ import annotations

import argparse
import getpass
import json
import locale
import os
import sys
from collections.abc import Sequence

from translate_linux import __version__

PROG = "translate-linux"

PROVIDER_LOCAL = "local"
PROVIDER_GOOGLE = "google"
DEFAULT_PROVIDER = PROVIDER_LOCAL

GOOGLE_KEYRING_NAME = "google_cloud_v2"

EXIT_OK = 0
EXIT_FAILURE = 1

FALLBACK_TARGET = "pt"


# "C" and "POSIX" are the absence of a locale, not a language.
_NEUTRAL_LOCALES = frozenset({"c", "posix"})

# Regional variants that have a model of their own. Falling back to the generic
# language would work, but "pt" produces European Portuguese for a Brazilian
# user, which reads as a foreign translation rather than a poor one.
_REGIONAL_TARGETS = {"pt_br": "pb"}


def default_target_language() -> str:
    """Derive the target language from the user's locale (RF-29)."""
    candidates: list[str] = []
    try:
        code, _encoding = locale.getlocale()
    except ValueError:
        code = None
    if code:
        candidates.append(code)
    candidates.append(os.environ.get("LANG", ""))

    for candidate in candidates:
        cleaned = candidate.split(".", 1)[0].strip().lower()
        regional = _REGIONAL_TARGETS.get(cleaned)
        if regional:
            return regional
        language = cleaned.split("_", 1)[0]
        if language.isalpha() and language not in _NEUTRAL_LOCALES:
            return language
    return FALLBACK_TARGET


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the ``translate-linux`` command."""
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="Capture a screen region, recognise its text and translate it.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"{PROG} {__version__}",
        help="show the installed version and exit",
    )

    actions = parser.add_argument_group("actions")
    actions.add_argument(
        "--capture",
        action="store_true",
        help="select a screen region, recognise its text and translate it",
    )
    actions.add_argument(
        "--set-api-key",
        action="store_true",
        help="store the Cloud Translation API key in the login keyring",
    )
    actions.add_argument(
        "--clear-api-key",
        action="store_true",
        help="remove the stored Cloud Translation API key",
    )
    actions.add_argument(
        "--doctor",
        action="store_true",
        help="report the state of everything the application depends on",
    )
    actions.add_argument(
        "--autostart",
        choices=["on", "off", "status"],
        help="control whether the tray starts with the session",
    )
    actions.add_argument(
        "--shortcut",
        metavar="BINDING",
        help="register a global capture shortcut, for example '<Super><Shift>t' "
        "(use 'off' to remove it)",
    )
    actions.add_argument(
        "--portal-info",
        action="store_true",
        help="report the screenshot portal version available on this session",
    )
    actions.add_argument(
        "--install-engine",
        action="store_true",
        help="install the offline translation engine into its private virtualenv",
    )
    actions.add_argument(
        "--install-model",
        metavar="PAIR",
        help="download and install an offline model, for example 'en-pt'",
    )
    actions.add_argument(
        "--tray",
        action="store_true",
        help="run resident in the system tray",
    )
    actions.add_argument(
        "--list-models",
        action="store_true",
        help="list the offline models installed on this machine",
    )

    options = parser.add_argument_group("capture options")
    options.add_argument(
        "--provider",
        choices=[PROVIDER_LOCAL, PROVIDER_GOOGLE],
        default=DEFAULT_PROVIDER,
        help="translation back end (default: %(default)s, which runs offline)",
    )
    options.add_argument(
        "--source",
        metavar="LANG",
        default=None,
        help="source language code (default: en; local models cannot detect it)",
    )
    options.add_argument(
        "--target",
        metavar="LANG",
        default=None,
        help="target language code (default: derived from the current locale)",
    )
    options.add_argument(
        "--ocr-lang",
        metavar="LANGS",
        default="eng+por",
        help="Tesseract languages, joined by '+' (default: %(default)s)",
    )
    options.add_argument(
        "--psm",
        type=int,
        default=6,
        help="Tesseract page segmentation mode (default: %(default)s)",
    )
    options.add_argument(
        "--scale",
        type=float,
        default=3.0,
        help="upscale factor applied before recognition (default: %(default)s)",
    )
    options.add_argument(
        "--ocr-only",
        action="store_true",
        help="recognise the text but do not translate it",
    )
    options.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="print the result as JSON",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line interface and return a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.set_api_key:
        return _set_api_key()
    if args.clear_api_key:
        return _clear_api_key()
    if args.doctor:
        return _doctor()
    if args.autostart:
        return _autostart(args.autostart)
    if args.shortcut:
        return _shortcut(args.shortcut)
    if args.portal_info:
        return _portal_info()
    if args.install_engine:
        return _install_engine()
    if args.install_model:
        return _install_model(args.install_model)
    if args.list_models:
        return _list_models()
    if args.tray:
        return _tray(args)
    if args.capture:
        return _capture(args)

    parser.print_help()
    return EXIT_OK


def _fail(message: str) -> int:
    print(f"{PROG}: {message}", file=sys.stderr)
    return EXIT_FAILURE


def _set_api_key() -> int:
    from translate_linux.credentials import CredentialError, store_api_key

    print("The key is read without echo and stored in the login keyring.")
    print("Create one at https://console.cloud.google.com/apis/credentials")
    try:
        key = getpass.getpass("Cloud Translation API key: ")
    except (EOFError, KeyboardInterrupt):
        print()
        return EXIT_FAILURE

    try:
        store_api_key(GOOGLE_KEYRING_NAME, key)
    except CredentialError as error:
        return _fail(str(error))
    print("Stored.")
    return EXIT_OK


def _clear_api_key() -> int:
    from translate_linux.credentials import CredentialError, clear_api_key

    try:
        removed = clear_api_key(GOOGLE_KEYRING_NAME)
    except CredentialError as error:
        return _fail(str(error))
    print("Removed." if removed else "No key was stored.")
    return EXIT_OK


def _portal_info() -> int:
    from translate_linux.capture.portal import CaptureError, screenshot_portal_version

    try:
        version = screenshot_portal_version()
    except CaptureError as error:
        return _fail(str(error))

    print(f"session type        : {os.environ.get('XDG_SESSION_TYPE', 'unknown')}")
    print(f"desktop             : {os.environ.get('XDG_CURRENT_DESKTOP', 'unknown')}")
    print(f"Screenshot portal   : version {version}")
    if version < 2:
        print("warning: interactive region selection needs version 2 or newer.")
    return EXIT_OK


def _doctor() -> int:
    from translate_linux.diagnostics import collect, has_failures, render

    checks = collect()
    print(render(checks))
    return EXIT_FAILURE if has_failures(checks) else EXIT_OK


def _autostart(action: str) -> int:
    from translate_linux import autostart

    if action == "status":
        print("enabled" if autostart.is_enabled() else "disabled")
        return EXIT_OK

    enabled = action == "on"
    autostart.apply(enabled)
    if enabled:
        print(f"Autostart enabled: {autostart.entry_path()}")
    else:
        print("Autostart disabled.")
    return EXIT_OK


def _shortcut(binding: str) -> int:
    from translate_linux.shortcuts import (
        ShortcutError,
        find_conflicts,
        install,
        uninstall,
    )

    try:
        if binding.lower() == "off":
            print("Shortcut removed." if uninstall() else "No shortcut was registered.")
            return EXIT_OK

        conflicts = find_conflicts(binding)
        for name, slot in conflicts:
            print(f"warning: {binding} is already used by {name!r} ({slot})", file=sys.stderr)

        install(binding)
    except ShortcutError as error:
        return _fail(str(error))

    print(f"Shortcut registered: {binding}")
    return EXIT_OK


def _install_engine() -> int:
    from translate_linux.translate import engine

    if engine.is_available():
        print(f"The offline engine is already {engine.describe()}.")
        return EXIT_OK

    print(f"Installing the offline engine into {engine.default_venv()} ...")
    try:
        location = engine.install()
    except engine.EngineInstallFailed as error:
        return _fail(str(error))
    print(f"Installed at {location}")
    return EXIT_OK


def _install_model(pair: str) -> int:
    from translate_linux.translate import models

    codes = pair.split("-")
    if len(codes) != 2 or not all(codes):
        return _fail(f"'{pair}' is not a language pair; use a form such as 'en-pt'.")

    try:
        catalogue = models.fetch_index()
        wanted = models.find_available(catalogue, codes[0], codes[1])
    except models.ModelError as error:
        return _fail(str(error))

    print(f"Downloading {wanted.pair} v{wanted.version} ...")

    def progress(written: int, total: int | None) -> None:
        if total:
            sys.stdout.write(f"\r  {written / 1e6:.0f} / {total / 1e6:.0f} MB")
        else:
            sys.stdout.write(f"\r  {written / 1e6:.0f} MB")
        sys.stdout.flush()

    try:
        result = models.install(wanted, progress=progress)
    except models.ModelError as error:
        sys.stdout.write("\n")
        return _fail(str(error))

    sys.stdout.write("\n")
    print(f"Installed {result.pair} at {result.path}")
    return EXIT_OK


def _list_models() -> int:
    from translate_linux.translate import engine, models

    print(f"offline engine : {engine.describe()}")
    found = models.installed()
    if not found:
        print("installed models: none")
        print(f"  Install one with: {PROG} --install-model en-pt")
        return EXIT_OK

    print("installed models:")
    for model in found:
        size = sum(f.stat().st_size for f in model.path.rglob("*") if f.is_file())
        print(f"  {model.pair}  v{model.version}  {size / 1e6:.0f} MB  {model.path}")
    return EXIT_OK


def _tray(args: argparse.Namespace) -> int:
    from translate_linux.app import TranslateLinuxApplication

    target = args.target or default_target_language()
    return int(TranslateLinuxApplication(target_language=target).run([PROG]))


def _build_provider(args: argparse.Namespace) -> object | int:
    """Return a provider, or an exit code when one cannot be built."""
    if args.provider == PROVIDER_GOOGLE:
        from translate_linux.credentials import CredentialError, lookup_api_key
        from translate_linux.translate.google_cloud import GoogleCloudTranslator

        try:
            api_key = lookup_api_key(GOOGLE_KEYRING_NAME)
        except CredentialError as error:
            return _fail(str(error))
        if not api_key:
            return _fail(
                "no Cloud Translation API key is stored.\n"
                f"  Run '{PROG} --set-api-key', or use --ocr-only to skip translation."
            )
        return GoogleCloudTranslator(api_key)

    from translate_linux.translate import engine
    from translate_linux.translate.local_ct2 import LocalTranslator

    if not engine.is_available():
        return _fail(
            "the offline translation engine is not installed.\n"
            f"  Run '{PROG} --install-engine' first."
        )
    return LocalTranslator()


def delegate_to_running_instance() -> bool:
    """Ask an already-running tray instance to capture; report whether it did.

    A global shortcut can only run a command, so the shortcut runs this one.
    Without delegation that command starts a second, headless process which
    captures into a terminal nobody is looking at -- which is what "the
    shortcut does nothing" actually was.
    """
    import gi

    gi.require_version("Gio", "2.0")
    from gi.repository import Gio, GLib

    from translate_linux.constants import APP_ID, APP_OBJECT_PATH, CAPTURE_ACTION

    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        bus.call_sync(
            APP_ID,
            APP_OBJECT_PATH,
            "org.freedesktop.Application",
            "ActivateAction",
            GLib.Variant("(sava{sv})", (CAPTURE_ACTION, [], {})),
            None,
            # Never spawn an instance: absence of one is the answer we want.
            Gio.DBusCallFlags.NO_AUTO_START,
            3000,
            None,
        )
    except GLib.Error:
        return False
    return True


def _capture(args: argparse.Namespace) -> int:
    from translate_linux.capture.portal import CaptureCancelled, CaptureError
    from translate_linux.ocr.tesseract import TesseractError
    from translate_linux.orchestrator import NoTextRecognised, capture_and_translate
    from translate_linux.translate.base import TranslationError

    # A plain capture belongs to the tray when one is running: that is where
    # the result window lives. Asking for terminal output means the caller
    # wants it here, so those forms always run in this process.
    wants_terminal_output = args.as_json or args.ocr_only
    if not wants_terminal_output and delegate_to_running_instance():
        return EXIT_OK

    target = args.target or default_target_language()

    provider = None
    if not args.ocr_only:
        built = _build_provider(args)
        if isinstance(built, int):
            return built
        provider = built

    try:
        outcome = capture_and_translate(
            provider=provider,  # type: ignore[arg-type]
            target=target,
            source=args.source,
            ocr_languages=args.ocr_lang,
            psm=args.psm,
            scale=args.scale,
        )
    except CaptureCancelled:
        return EXIT_OK  # RF-03: dismissing the selection is not an error
    except (CaptureError, TesseractError, NoTextRecognised, TranslationError) as error:
        return _fail(str(error))

    _render(outcome, as_json=args.as_json)
    return EXIT_OK


def _render(outcome: object, *, as_json: bool) -> None:
    from translate_linux.orchestrator import CaptureOutcome

    assert isinstance(outcome, CaptureOutcome)
    translation = outcome.translation

    if as_json:
        payload = {
            "original": outcome.original,
            "translated": translation.text if translation else None,
            "detected_source": translation.detected_source if translation else None,
            "target": translation.target if translation else None,
            "provider": translation.provider if translation else None,
            "ocr_languages": outcome.ocr_languages,
            "mean_confidence": round(outcome.mean_confidence, 1),
        }
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return

    print(f"--- original [{outcome.ocr_languages}, confidence {outcome.mean_confidence:.0f}%] ---")
    print(outcome.original)
    if translation is not None:
        source = translation.detected_source or "auto"
        print(f"\n--- translation [{source} -> {translation.target}, {translation.provider}] ---")
        print(translation.text)


if __name__ == "__main__":  # pragma: no cover - exercised through __main__.py
    sys.exit(main())
