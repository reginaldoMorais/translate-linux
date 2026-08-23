"""Ask before any text leaves the machine.

The application reads whatever is on screen, which regularly includes things
nobody intends to send anywhere: password managers, private messages, medical
records. While translation stays local this is a non-issue and the dialog never
appears. It appears exactly once per version of the terms, and only when an
online provider is chosen (RF-35).
"""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk  # noqa: E402

# Raise this when the terms change, so consent is asked again (NFR-S7).
CONSENT_VERSION = 1

HEADING = "Enviar texto para um serviço online?"

BODY = (
    "Você escolheu um provider de tradução online. A partir de agora, o texto "
    "reconhecido nas suas capturas será <b>enviado pela internet</b> para esse "
    "serviço.\n\n"
    "Isso inclui qualquer coisa que estiver na região capturada — inclusive o "
    "que você não pretendia enviar.\n\n"
    "Se recusar, o aplicativo continua funcionando normalmente com o "
    "<b>modelo local</b>, que não envia nada para lugar nenhum."
)

ACCEPT_LABEL = "Aceitar e usar o serviço online"
DECLINE_LABEL = "Manter tudo local"


def consent_needed(provider: str, recorded_version: int) -> bool:
    """Whether consent must be asked before using ``provider``.

    Local translation never needs it: nothing leaves the machine.
    """
    if provider == "local_ct2":
        return False
    return recorded_version < CONSENT_VERSION


class ConsentDialog(Adw.MessageDialog):
    """Asks for informed consent before enabling an online provider."""

    def __init__(
        self,
        parent: Gtk.Window | None,
        *,
        on_decision: Callable[[bool], None],
    ) -> None:
        super().__init__(transient_for=parent, modal=True)
        self._on_decision = on_decision

        self.set_heading(HEADING)
        self.set_body_use_markup(True)
        self.set_body(BODY)

        self.add_response("decline", DECLINE_LABEL)
        self.add_response("accept", ACCEPT_LABEL)
        self.set_response_appearance("accept", Adw.ResponseAppearance.SUGGESTED)
        self.set_default_response("decline")
        self.set_close_response("decline")

        self.connect("response", self._on_response)

    def _on_response(self, _dialog: Adw.MessageDialog, response: str) -> None:
        self._on_decision(response == "accept")
