"""The About window.

More than a courtesy. There is no telemetry, so supporting an installation
depends on the user being able to hand over what their machine looks like.
``Adw.AboutWindow`` has a troubleshooting section built for exactly that, and it
is filled with the same report ``--doctor`` prints -- copyable in one click,
without asking anyone to open a terminal.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk  # noqa: E402

from translate_linux import __version__  # noqa: E402
from translate_linux.ui import messages  # noqa: E402

REPOSITORY = "https://github.com/reginaldoMorais/translate-linux"
DEVELOPER = "Reginaldo Morais"
DEBUG_FILENAME = "translate-linux-diagnostico.txt"

COMMENTS = (
    "Selecione uma região da tela como no PrintScreen e receba o texto "
    "reconhecido e traduzido.\n\n"
    "A tradução roda localmente por padrão: nada sai da sua máquina e não há "
    "custo por uso."
)


def collect_debug_info() -> str:
    """Return the same report ``--doctor`` prints, for the troubleshooting tab."""
    from translate_linux.diagnostics import collect, render

    try:
        return render(collect())
    except Exception as error:
        return f"O relatório de diagnóstico falhou: {error}"


def build_about_window(parent: Gtk.Window | None = None) -> Adw.AboutWindow:
    """Build the About window, filled with version and diagnostics."""
    window = Adw.AboutWindow(
        application_name=messages.APP_TITLE,
        application_icon="translate-linux",
        version=__version__,
        developer_name=DEVELOPER,
        comments=COMMENTS,
        website=REPOSITORY,
        issue_url=f"{REPOSITORY}/issues",
        license_type=Gtk.License.MIT_X11,
        copyright="© 2026 Reginaldo Morais",
        developers=[DEVELOPER],
    )
    if parent is not None:
        window.set_transient_for(parent)

    window.add_link("Notas de versão", f"{REPOSITORY}/releases")
    window.set_debug_info(collect_debug_info())
    window.set_debug_info_filename(DEBUG_FILENAME)
    return window
