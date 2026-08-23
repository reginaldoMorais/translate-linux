"""Discover, install and remove offline translation models.

Models are distributed by the Argos project as ``.argosmodel`` packages, which
are ordinary zip archives holding a CTranslate2 model directory and a
SentencePiece vocabulary. The ``stanza/`` directory each package also carries is
discarded on extraction: it exists only to split sentences, and
:mod:`translate_linux.translate.chunking` has done that since M1.

The upstream index publishes no checksum, so integrity is established by
validating the archive structure and recording the digest observed at install
time, which lets later on-disk corruption be detected.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import shutil
import tempfile
import zipfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from translate_linux.constants import data_dir

INDEX_URL = "https://raw.githubusercontent.com/argosopentech/argospm-index/main/index.json"
DOWNLOAD_TIMEOUT = 60.0
CHUNK_BYTES = 256 * 1024

MODEL_SUBDIR = "model"
VOCABULARY_FILE = "sentencepiece.model"
RECEIPT_FILE = "install.json"
DISCARDED_DIRS = ("stanza/",)

# A package expands to roughly 82 MB; require headroom for the archive too.
REQUIRED_FREE_BYTES = 300 * 1024 * 1024

ProgressCallback = Callable[[int, int | None], None]


class ModelError(Exception):
    """A model could not be listed, downloaded or installed."""


class ModelNotAvailable(ModelError):
    """The requested language pair is not published upstream."""


@dataclass(frozen=True, slots=True)
class ModelInfo:
    """A model published in the upstream index."""

    from_code: str
    to_code: str
    version: str
    url: str

    @property
    def pair(self) -> str:
        return f"{self.from_code}-{self.to_code}"


@dataclass(frozen=True, slots=True)
class InstalledModel:
    """A model present on this machine."""

    from_code: str
    to_code: str
    version: str
    path: Path

    @property
    def pair(self) -> str:
        return f"{self.from_code}-{self.to_code}"

    @property
    def ct2_path(self) -> Path:
        return self.path / MODEL_SUBDIR

    @property
    def vocabulary_path(self) -> Path:
        return self.path / VOCABULARY_FILE


def models_root() -> Path:
    """Return the directory holding installed models."""
    root = data_dir() / "models"
    root.mkdir(parents=True, exist_ok=True)
    return root


def parse_index(payload: Any) -> tuple[ModelInfo, ...]:
    """Turn the upstream index document into model descriptions."""
    if not isinstance(payload, list):
        raise ModelError("The model index is not a list.")

    models: list[ModelInfo] = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        links = entry.get("links") or []
        if not links or not entry.get("from_code") or not entry.get("to_code"):
            continue
        models.append(
            ModelInfo(
                from_code=str(entry["from_code"]),
                to_code=str(entry["to_code"]),
                version=str(entry.get("package_version", "unknown")),
                url=str(links[0]),
            )
        )
    return tuple(models)


def fetch_index(session: requests.Session | None = None) -> tuple[ModelInfo, ...]:
    """Download and parse the upstream model index."""
    client = session or requests.Session()
    try:
        response = client.get(INDEX_URL, timeout=DOWNLOAD_TIMEOUT)
    except requests.RequestException as error:
        raise ModelError(
            "Could not reach the model index. Check the network connection."
        ) from error
    if response.status_code != 200:
        raise ModelError(f"The model index answered with HTTP {response.status_code}.")
    try:
        return parse_index(response.json())
    except ValueError as error:
        raise ModelError("The model index is not valid JSON.") from error


def find_available(models: Iterable[ModelInfo], from_code: str, to_code: str) -> ModelInfo:
    """Return the published model for a pair, or explain that there is none."""
    for model in models:
        if model.from_code == from_code and model.to_code == to_code:
            return model
    raise ModelNotAvailable(f"No offline model is published for {from_code} -> {to_code}.")


def installed(root: Path | None = None) -> tuple[InstalledModel, ...]:
    """Return every model installed on this machine."""
    base = root or models_root()
    found: list[InstalledModel] = []
    for directory in sorted(base.iterdir()) if base.is_dir() else []:
        model = _read_installed(directory)
        if model is not None:
            found.append(model)
    return tuple(found)


def find_installed(from_code: str, to_code: str, root: Path | None = None) -> InstalledModel | None:
    """Return the installed model for a pair, or ``None``."""
    base = root or models_root()
    return _read_installed(base / f"{from_code}-{to_code}")


def _read_installed(directory: Path) -> InstalledModel | None:
    if not (directory / MODEL_SUBDIR / "model.bin").is_file():
        return None
    if not (directory / VOCABULARY_FILE).is_file():
        return None

    pair = directory.name.split("-")
    if len(pair) != 2:
        return None

    version = "unknown"
    receipt = directory / RECEIPT_FILE
    if receipt.is_file():
        with contextlib.suppress(OSError, ValueError):
            version = str(json.loads(receipt.read_text(encoding="utf-8")).get("version", version))

    return InstalledModel(from_code=pair[0], to_code=pair[1], version=version, path=directory)


def install(
    model: ModelInfo,
    *,
    root: Path | None = None,
    session: requests.Session | None = None,
    progress: ProgressCallback | None = None,
) -> InstalledModel:
    """Download and install ``model``, replacing any previous version."""
    base = root or models_root()
    _require_free_space(base)

    with tempfile.TemporaryDirectory(prefix="translate-linux-model-", dir=base) as scratch:
        workspace = Path(scratch)
        archive = workspace / "package.argosmodel"
        digest = _download(model.url, archive, session=session, progress=progress)

        staging = workspace / "staged"
        _extract(archive, staging)

        destination = base / model.pair
        (staging / RECEIPT_FILE).write_text(
            json.dumps(
                {"version": model.version, "url": model.url, "sha256": digest},
                indent=2,
            ),
            encoding="utf-8",
        )
        if destination.exists():
            shutil.rmtree(destination)
        shutil.move(str(staging), str(destination))

    result = _read_installed(base / model.pair)
    if result is None:  # pragma: no cover - _extract validates the layout
        raise ModelError("The model was installed but cannot be read back.")
    return result


def remove(from_code: str, to_code: str, root: Path | None = None) -> bool:
    """Delete an installed model; report whether one was there."""
    directory = (root or models_root()) / f"{from_code}-{to_code}"
    if not directory.is_dir():
        return False
    shutil.rmtree(directory)
    return True


def _require_free_space(base: Path) -> None:
    free = shutil.disk_usage(base).free
    if free < REQUIRED_FREE_BYTES:
        raise ModelError(
            f"Not enough free space to install a model: "
            f"{free / 1e6:.0f} MB available, about "
            f"{REQUIRED_FREE_BYTES / 1e6:.0f} MB needed."
        )


def _download(
    url: str,
    destination: Path,
    *,
    session: requests.Session | None,
    progress: ProgressCallback | None,
) -> str:
    client = session or requests.Session()
    digest = hashlib.sha256()
    try:
        with client.get(url, stream=True, timeout=DOWNLOAD_TIMEOUT) as response:
            if response.status_code != 200:
                raise ModelError(f"The model download answered with HTTP {response.status_code}.")
            declared = response.headers.get("content-length")
            total = int(declared) if declared and declared.isdigit() else None
            written = 0
            with destination.open("wb") as handle:
                for block in response.iter_content(chunk_size=CHUNK_BYTES):
                    if not block:
                        continue
                    handle.write(block)
                    digest.update(block)
                    written += len(block)
                    if progress is not None:
                        progress(written, total)
    except requests.RequestException as error:
        raise ModelError("The model download failed. Check the network connection.") from error
    return digest.hexdigest()


def _extract(archive: Path, destination: Path) -> None:
    """Unpack the package, dropping the parts the application does not use."""
    destination.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(archive) as bundle:
            names = bundle.namelist()
            prefix = _common_prefix(names)
            for name in names:
                relative = name[len(prefix) :] if prefix else name
                if not relative or name.endswith("/"):
                    continue
                if relative.startswith(DISCARDED_DIRS):
                    continue
                target = destination / relative
                # Refuse anything that would escape the destination directory.
                if not _is_within(destination, target):
                    raise ModelError(f"The package contains an unsafe path: {name!r}")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(bundle.read(name))
    except zipfile.BadZipFile as error:
        raise ModelError("The downloaded model package is not a valid archive.") from error

    if not (destination / MODEL_SUBDIR / "model.bin").is_file():
        raise ModelError("The model package has no CTranslate2 model inside.")
    if not (destination / VOCABULARY_FILE).is_file():
        raise ModelError("The model package has no SentencePiece vocabulary inside.")


def _common_prefix(names: Iterable[str]) -> str:
    tops = {name.split("/", 1)[0] for name in names if "/" in name}
    return f"{tops.pop()}/" if len(tops) == 1 else ""


def _is_within(parent: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True
