# translate-linux — development tasks
#
# Recipes use ">" instead of a leading tab (GNU make >= 3.82).
.RECIPEPREFIX := >
.DEFAULT_GOAL := help

# The distribution interpreter is mandatory: PyGObject (python3-gi) is only
# visible to it. A pyenv/asdf python3 on PATH will NOT find the "gi" module.
SYSTEM_PYTHON := /usr/bin/python3
VENV          := .venv
# The offline engine lives in its own virtualenv, mirroring RF-42: the .deb
# cannot depend on ctranslate2 through apt, so the application installs it
# privately and reaches it by extending sys.path at runtime.
OFFLINE_VENV  := .venv-offline
PY            := $(VENV)/bin/python
PYTEST        := $(VENV)/bin/pytest
RUFF          := $(VENV)/bin/ruff
MYPY          := $(VENV)/bin/mypy

APT_PACKAGES := python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 \
                gir1.2-ayatanaappindicator3-0.1 gir1.2-secret-1 \
                tesseract-ocr tesseract-ocr-eng tesseract-ocr-por tesseract-ocr-osd \
                python3-sentencepiece libglib2.0-bin

.PHONY: help system-deps dev-setup offline-engine lint format typecheck test coverage check run clean distclean

help: ## Show this help
> @grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
>   | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

system-deps: ## Install the distribution packages the app needs
> sudo apt-get update
> sudo apt-get install -y --no-install-recommends $(APT_PACKAGES)

$(VENV)/bin/activate: pyproject.toml
> $(SYSTEM_PYTHON) -m venv --system-site-packages $(VENV)
> $(PY) -m pip install --quiet --upgrade pip
> $(PY) -m pip install --quiet -e ".[dev]"
> @touch $(VENV)/bin/activate

dev-setup: $(VENV)/bin/activate ## Create the virtualenv and install the project
> @$(PY) -c "import gi; gi.require_version('Gtk', '4.0'); from gi.repository import Gtk; \
>   print(f'PyGObject OK - GTK {Gtk.get_major_version()}.{Gtk.get_minor_version()}')" \
>   || echo "WARNING: PyGObject unavailable - install python3-gi (make system-deps)"

offline-engine: ## Install the offline translation engine into its private venv
> $(SYSTEM_PYTHON) -m venv $(OFFLINE_VENV)
> $(OFFLINE_VENV)/bin/python -m pip install --quiet --upgrade pip
> $(OFFLINE_VENV)/bin/python -m pip install --quiet "ctranslate2>=4.0,<5" "sentencepiece>=0.2,<0.3"
> @$(OFFLINE_VENV)/bin/python -c "import ctranslate2, sentencepiece; \
>   print(f'offline engine OK - ctranslate2 {ctranslate2.__version__}')"

lint: dev-setup ## Run ruff (lint + format check)
> $(RUFF) check .
> $(RUFF) format --check .

format: dev-setup ## Reformat the code with ruff
> $(RUFF) check --fix .
> $(RUFF) format .

typecheck: dev-setup ## Run mypy in strict mode
> $(MYPY)

test: dev-setup ## Run the test suite
> $(PYTEST)

coverage: dev-setup ## Run the test suite with a coverage report
> $(PYTEST) --cov=translate_linux --cov-report=term-missing

check: lint typecheck test ## Run every quality gate

run: dev-setup ## Run the application from the working tree
> $(PY) -m translate_linux

clean: ## Remove build and test artefacts
> rm -rf build dist .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
> find . -name __pycache__ -type d -prune -exec rm -rf {} +
> find . -name '*.egg-info' -type d -prune -exec rm -rf {} +

distclean: clean ## Also remove both virtualenvs
> rm -rf $(VENV) $(OFFLINE_VENV)
