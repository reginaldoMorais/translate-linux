"""Translate offline with CTranslate2, using OPUS-MT models.

This is the default provider: it costs nothing per character, works without a
network and never lets the contents of the screen leave the machine.

Two behaviours here are not obvious and were established by measurement rather
than by reading documentation:

* ``SentencePieceProcessor.decode()`` cannot be used. These models carry a
  vocabulary shared with the CTranslate2 model, and ``decode()`` leaves the
  ``U+2581`` word-boundary marker embedded in the output. Detokenisation is
  done by hand instead, which is the canonical SentencePiece rule.
* The model is loaded lazily and dropped after a period of inactivity. Loading
  costs about 0.13 s and 77 MB, which is cheap enough to pay again but far too
  expensive to hold while the application sits idle in the tray.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from translate_linux.translate import engine, models
from translate_linux.translate.base import (
    Translation,
    TranslationError,
)
from translate_linux.translate.chunking import restore_padding, split_sentences

PROVIDER_NAME = "local_ct2"

# The engine translates one sentence at a time, so chunks are kept small enough
# that the splitter reaches sentence granularity.
DEFAULT_MAX_CHARS = 240
DEFAULT_COMPUTE_TYPE = "int8"
DEFAULT_IDLE_TIMEOUT = 600.0
DEFAULT_SOURCE = "en"

# SentencePiece marks a word boundary with this character.
SPACE_MARKER = "▁"


class ModelNotInstalled(TranslationError):
    """No offline model is installed for the requested language pair."""

    def __init__(self, from_code: str, to_code: str) -> None:
        super().__init__(
            f"No offline model is installed for {from_code} -> {to_code}.\n"
            f"  Install it with: translate-linux --install-model {from_code}-{to_code}"
        )
        self.from_code = from_code
        self.to_code = to_code


def detokenize(pieces: list[str]) -> str:
    """Rebuild text from SentencePiece pieces.

    ``SentencePieceProcessor.decode()`` is deliberately not used: with these
    models it returns the marker verbatim, producing output such as
    ``'▁Clique no▁botao'``.

    >>> detokenize(["▁Ola", "▁mundo", "."])
    'Ola mundo.'
    """
    return "".join(pieces).replace(SPACE_MARKER, " ").strip()


@dataclass(slots=True)
class _Loaded:
    """A model held in memory, with the pair it serves."""

    pair: str
    translator: Any
    vocabulary: Any
    last_used: float


class LocalTranslator:
    """Translate text with a locally installed CTranslate2 model."""

    name = PROVIDER_NAME

    def __init__(
        self,
        *,
        models_root: Path | None = None,
        compute_type: str = DEFAULT_COMPUTE_TYPE,
        idle_timeout: float = DEFAULT_IDLE_TIMEOUT,
        max_chars: int = DEFAULT_MAX_CHARS,
        default_source: str = DEFAULT_SOURCE,
    ) -> None:
        self._models_root = models_root
        self._compute_type = compute_type
        self._idle_timeout = idle_timeout
        self._max_chars = max_chars
        self._default_source = default_source
        self._loaded: _Loaded | None = None
        self._lock = threading.Lock()

    def __repr__(self) -> str:
        state = self._loaded.pair if self._loaded else "unloaded"
        return f"<LocalTranslator {state}>"

    @property
    def is_loaded(self) -> bool:
        return self._loaded is not None

    def available_pairs(self) -> tuple[str, ...]:
        """Return the language pairs this machine can translate offline."""
        return tuple(model.pair for model in models.installed(self._models_root))

    def translate(self, text: str, source: str | None, target: str) -> Translation:
        """Translate ``text`` into ``target`` using an installed model.

        The local models are single-direction, so the source cannot be
        detected; when it is not given, ``default_source`` is assumed.

        Raises:
            ModelNotInstalled: no model covers the requested pair.
            engine.EngineNotInstalled: CTranslate2 is not present.
        """
        origin = source or self._default_source

        if not text.strip():
            return Translation(text=text, detected_source=origin, target=target, provider=self.name)

        if origin == target:
            # RF-30: nothing to do, and no reason to spend a model load on it.
            return Translation(text=text, detected_source=origin, target=target, provider=self.name)

        model = models.find_installed(origin, target, self._models_root)
        if model is None:
            raise ModelNotInstalled(origin, target)

        chunks = split_sentences(text, self._max_chars)
        pending = [(index, chunk) for index, chunk in enumerate(chunks) if chunk.strip()]

        rendered = self._run(model, [chunk.strip() for _, chunk in pending])

        translated = {
            index: restore_padding(chunk, output)
            for (index, chunk), output in zip(pending, rendered, strict=True)
        }
        rebuilt = "".join(translated.get(index, chunk) for index, chunk in enumerate(chunks))

        return Translation(text=rebuilt, detected_source=origin, target=target, provider=self.name)

    def _run(self, model: models.InstalledModel, sentences: list[str]) -> list[str]:
        with self._lock:
            loaded = self._ensure_loaded(model)
            tokens = [loaded.vocabulary.encode(text, out_type=str) for text in sentences]
            results = loaded.translator.translate_batch(tokens)
            loaded.last_used = time.monotonic()
        return [detokenize(result.hypotheses[0]) for result in results]

    def _ensure_loaded(self, model: models.InstalledModel) -> _Loaded:
        if self._loaded is not None and self._loaded.pair == model.pair:
            return self._loaded

        ctranslate2, sentencepiece = engine.load()
        translator = ctranslate2.Translator(
            str(model.ct2_path), device="cpu", compute_type=self._compute_type
        )
        vocabulary = sentencepiece.SentencePieceProcessor(str(model.vocabulary_path))
        self._loaded = _Loaded(
            pair=model.pair,
            translator=translator,
            vocabulary=vocabulary,
            last_used=time.monotonic(),
        )
        return self._loaded

    def unload(self) -> bool:
        """Drop the resident model; report whether one was held."""
        with self._lock:
            if self._loaded is None:
                return False
            self._loaded = None
        return True

    def unload_if_idle(self, now: float | None = None) -> bool:
        """Drop the model when it has gone unused for ``idle_timeout`` seconds.

        The tray application calls this on a timer so that sitting idle costs
        the memory of an empty process rather than of a loaded model.
        """
        with self._lock:
            if self._loaded is None:
                return False
            elapsed = (now if now is not None else time.monotonic()) - self._loaded.last_used
            if elapsed < self._idle_timeout:
                return False
            self._loaded = None
        return True
