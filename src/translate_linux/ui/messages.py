"""Portuguese wording for everything the user reads.

Exceptions carry English text because they are a developer surface: they end up
in logs, tracebacks and bug reports. The interface is Brazilian Portuguese, so
the presentation layer owns the wording and maps each failure to a sentence that
says what happened and what to do about it.
"""

from __future__ import annotations

import gi

gi.require_version("Gio", "2.0")

from gi.repository import GLib  # noqa: E402

from translate_linux.capture.portal import (  # noqa: E402
    CaptureCancelled,
    CaptureError,
    PortalUnavailable,
)
from translate_linux.ocr.tesseract import (  # noqa: E402
    TesseractLanguageMissing,
    TesseractNotFound,
    TesseractTimeout,
)
from translate_linux.orchestrator import NoTextRecognised  # noqa: E402
from translate_linux.translate.base import (  # noqa: E402
    TranslationAuthError,
    TranslationRateLimited,
    TranslationUnavailable,
)
from translate_linux.translate.engine import EngineNotInstalled  # noqa: E402
from translate_linux.translate.local_ct2 import ModelNotInstalled  # noqa: E402

APP_TITLE = "Tradutor de Tela"

MENU_CAPTURE = "Capturar e traduzir"
MENU_TARGET_LANGUAGE = "Idioma de destino"
MENU_PREFERENCES = "Preferências"
MENU_ABOUT = "Sobre"
MENU_QUIT = "Sair"

WINDOW_TITLE = "Tradução"
STATE_RECOGNISING = "Reconhecendo texto…"
STATE_TRANSLATING = "Traduzindo…"
LABEL_ORIGINAL = "Texto reconhecido"
LABEL_RETRANSLATE = "Retraduzir"
LABEL_COPY = "Copiar tradução"
LABEL_COPY_ORIGINAL = "Copiar original"
LABEL_CLOSE = "Fechar"
TOAST_COPIED = "Copiado"

SOURCE_LOCAL = "modelo local"
SOURCE_CACHE = "cache"

# Translation providers use ISO 639-1 ("en"); Tesseract uses ISO 639-2 ("eng").
# Both reach this module, so both are mapped.
LANGUAGE_NAMES = {
    "pt": "Português",
    "por": "Português",
    "en": "Inglês",
    "eng": "Inglês",
    "es": "Espanhol",
    "spa": "Espanhol",
    "fr": "Francês",
    "fra": "Francês",
    "de": "Alemão",
    "deu": "Alemão",
    "it": "Italiano",
    "ita": "Italiano",
    "osd": "detecção de orientação",
}


def language_name(code: str) -> str:
    """Return the Portuguese name of a language code, or the code itself."""
    return LANGUAGE_NAMES.get(code, code)


def provider_label(provider: str, *, from_cache: bool = False) -> str:
    """Describe where a translation came from, so quality is attributable."""
    if from_cache:
        return SOURCE_CACHE
    if provider == "local_ct2":
        return SOURCE_LOCAL
    if provider.startswith("google"):
        return "Google"
    return provider


def describe_error(error: Exception) -> str:
    """Turn a failure into a sentence that says what to do next."""
    if isinstance(error, CaptureCancelled):
        return "Seleção cancelada."

    if isinstance(error, EngineNotInstalled):
        return (
            "O motor de tradução offline não está instalado.\n"
            "Instale com: translate-linux --install-engine"
        )
    if isinstance(error, ModelNotInstalled):
        pair = f"{error.from_code}-{error.to_code}"
        return (
            f"Não há modelo offline para {language_name(error.from_code)} → "
            f"{language_name(error.to_code)}.\n"
            f"Instale com: translate-linux --install-model {pair}"
        )

    if isinstance(error, TesseractNotFound):
        return (
            "O Tesseract não está instalado.\n"
            "Instale com: sudo apt install tesseract-ocr tesseract-ocr-por tesseract-ocr-eng"
        )
    if isinstance(error, TesseractLanguageMissing):
        return (
            "Falta o pacote de idioma do Tesseract para o reconhecimento.\n"
            "Veja os idiomas instalados com: tesseract --list-langs"
        )
    if isinstance(error, TesseractTimeout):
        return "O reconhecimento demorou demais. Tente selecionar uma região menor."

    if isinstance(error, NoTextRecognised):
        return (
            "Nenhum texto reconhecido nessa região.\n"
            "Tente uma área um pouco maior, aumente o zoom da aplicação de origem, "
            "ou verifique se o idioma de reconhecimento está correto."
        )

    if isinstance(error, TranslationRateLimited):
        return "O serviço de tradução recusou por excesso de requisições. Aguarde um instante."
    if isinstance(error, TranslationAuthError):
        return "A chave da API foi recusada. Verifique-a nas Preferências."
    if isinstance(error, TranslationUnavailable):
        return "Não foi possível alcançar o serviço de tradução. Verifique a conexão."

    if isinstance(error, PortalUnavailable):
        return "Não foi possível acessar o serviço de captura de tela do sistema."
    if isinstance(error, CaptureError):
        return "A captura falhou."

    return "Ocorreu um erro inesperado."


def confidence_note(mean_confidence: float, ocr_languages: str) -> str:
    """Describe recognition quality, naming the languages actually in use.

    Surfacing the configured languages turns the most likely silent failure --
    capturing German with recognition set to English -- into something visible.
    """
    languages = ", ".join(language_name(code) for code in ocr_languages.split("+"))
    return f"Reconhecimento {mean_confidence:.0f}% · {languages}"


def escape_markup(text: str) -> str:
    """Make ``text`` safe for a widget that parses Pango markup.

    Several Adwaita widgets -- toast titles, group descriptions, row subtitles
    -- interpret their text as markup. A keyboard shortcut such as
    ``<Super><Shift>t`` therefore looks like an unknown tag, Pango refuses to
    parse it, and the widget renders **nothing at all**: an empty toast with a
    close button and no message. Escaping is what keeps such text visible.
    """
    return str(GLib.markup_escape_text(text))
