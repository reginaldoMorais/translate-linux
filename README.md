# translate-linux

Selecione uma região da tela como no `PrintScreen` do Zorin OS e, em vez de
salvar uma imagem, receba **o texto reconhecido e traduzido**.

> **Status: M2 — tradução offline funcionando.** Captura, OCR e tradução local
> funcionam via `translate-linux --capture`, sem rede e sem custo por uso. A
> bandeja do sistema e a janela de resultado chegam no M3. A especificação está em
> [`docs/plans/SPEC.md`](docs/plans/SPEC.md) e o estado corrente do projeto em
> [`docs/plans/HANDOFF.md`](docs/plans/HANDOFF.md).

---

## Como vai funcionar

1. Você aciona a captura pela bandeja do sistema, por um atalho global ou por
   `translate-linux --capture`.
2. O **GNOME Shell** exibe a própria interface de seleção de região — a mesma
   do `PrintScreen`, porque a captura é feita pelo portal XDG
   (`org.freedesktop.portal.Screenshot`), único caminho possível em Wayland.
3. A imagem passa por pré-processamento e por OCR com **Tesseract**.
4. O texto é normalizado e traduzido, com cache local.
5. Uma janela GTK4 mostra a tradução, o original e o idioma detectado.

## Ambiente-alvo

| Item | Versão |
|---|---|
| Distribuição | Zorin OS 18 (Ubuntu 24.04 "noble") |
| Sessão | Wayland (X11 tem fallback de menor prioridade) |
| GNOME Shell | 46 |
| Python | 3.10 ou superior (3.12 no alvo) |
| GTK / libadwaita | 4.14 / 1.5 |

## Requisitos de sistema

```bash
make system-deps
```

Ou, manualmente:

```bash
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 \
                 gir1.2-ayatanaappindicator3-0.1 gir1.2-secret-1 \
                 tesseract-ocr tesseract-ocr-eng tesseract-ocr-por \
                 tesseract-ocr-osd python3-sentencepiece libglib2.0-bin
```

## Ambiente de desenvolvimento

> [!IMPORTANT]
> **Use o interpretador da distribuição.** O PyGObject (`python3-gi`) é
> instalado pelo APT e **não é visível** a um Python de pyenv, asdf ou
> conda — `import gi` falha com `ModuleNotFoundError`. Por isso o
> `make dev-setup` cria o virtualenv com `/usr/bin/python3` e a flag
> `--system-site-packages`. Não substitua isso por `python3 -m venv .venv`.

```bash
git clone https://github.com/rmorais/translate-linux.git
cd translate-linux
make dev-setup
```

Equivalente manual:

```bash
/usr/bin/python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install -e ".[dev]"
```

Verifique se o PyGObject está acessível:

```bash
.venv/bin/python -c "import gi; gi.require_version('Gtk','4.0'); \
  from gi.repository import Gtk; print(Gtk.get_major_version())"
```

## Comandos de desenvolvimento

| Comando | O que faz |
|---|---|
| `make dev-setup` | Cria o virtualenv e instala o projeto em modo editável |
| `make lint` | `ruff check` + verificação de formatação |
| `make format` | Corrige e reformata o código |
| `make typecheck` | `mypy` em modo estrito |
| `make test` | Executa a suíte de testes |
| `make coverage` | Testes com relatório de cobertura |
| `make check` | Lint + tipos + testes (o mesmo que a CI roda) |
| `make run` | Executa a aplicação a partir da árvore de trabalho |
| `make clean` | Remove artefatos de build e caches |

Testes marcados com `network` ficam fora da execução padrão e nunca rodam na
CI. Para executá-los deliberadamente:

```bash
.venv/bin/pytest -m network
```

## Uso

### Preparo (uma vez)

```bash
.venv/bin/translate-linux --install-engine        # motor offline, ~40 MB
.venv/bin/translate-linux --install-model en-pt   # modelo en->pt, ~66 MB
```

Confira o que ficou instalado com `--list-models`.

### Capturar e traduzir

```bash
.venv/bin/translate-linux --capture                 # offline, idioma do seu locale
.venv/bin/translate-linux --capture --target en     # idioma de destino explícito
.venv/bin/translate-linux --capture --source es     # origem diferente de inglês
.venv/bin/translate-linux --capture --ocr-only      # só reconhece, não traduz
.venv/bin/translate-linux --capture --json          # saída para script
```

A tradução roda **localmente por padrão**: nada sai da sua máquina e não há
custo por caractere. Os modelos locais são de direção única e não detectam o
idioma de origem — o padrão é inglês, ajustável com `--source`.

Se quiser mais qualidade e aceitar o custo por caractere, há o provider oficial
do Google:

```bash
.venv/bin/translate-linux --set-api-key
.venv/bin/translate-linux --capture --provider google
```

Outros comandos:

| Comando | O que faz |
|---|---|
| `--list-models` | Lista o motor e os modelos offline instalados |
| `--install-engine` | Instala o motor offline em um virtualenv privado |
| `--install-model PAR` | Baixa e instala um modelo, por exemplo `en-pt` |
| `--portal-info` | Mostra o tipo de sessão e a versão do portal de captura |
| `--set-api-key` | Guarda a chave da API do Google no chaveiro (sem eco) |
| `--clear-api-key` | Remove a chave guardada |

Cancelar a seleção com `Esc` encerra em silêncio, sem erro e sem consumir cota.

### Ajuste de reconhecimento

| Opção | Quando usar |
|---|---|
| `--ocr-lang deu+eng` | O texto na tela está em outro idioma |
| `--psm 3` | O texto está em várias colunas |
| `--scale 4` | O texto é muito pequeno e o reconhecimento falha |

## Build e instalação

O empacotamento `.deb` e o pipeline de release por tag chegam no marco **M5**.
Até lá, execute a partir da árvore de trabalho com `make run`.

## Estrutura do projeto

```
src/translate_linux/
├── cli.py            # ponto de entrada de linha de comando
├── capture/          # backends de captura (portal XDG, fallback X11)
├── ocr/              # pré-processamento de imagem e Tesseract
├── text/             # normalização do texto reconhecido
├── translate/        # providers de tradução, chunking e cache
└── ui/               # interface GTK4 / libadwaita
tests/
├── unit/             # lógica pura, sem rede e sem GTK
├── integration/      # D-Bus simulado, Tesseract real, HTTP simulado
└── fixtures/         # imagens e respostas gravadas
docs/plans/           # SPEC.md e HANDOFF.md
```

## Roteiro

| Marco | Escopo | Tag |
|---|---|---|
| ~~M0~~ | Estrutura, ferramentas e CI | — |
| ~~M1~~ | Fatia vertical em CLI: portal → Tesseract → tradução | `v0.0.1` |
| **M2** | Tradução offline (CTranslate2 + OPUS-MT) | `v0.1.0` |
| M3 | Bandeja, janela de resultado e cache | `v0.2.0` |
| M4 | Preferências, consentimento, autostart, atalho global | `v0.3.0` |
| M5 | Empacotamento `.deb` e pipeline de release | `v1.0.0` |

## Privacidade

**Por padrão nada sai da sua máquina.** A tradução roda localmente, e o
aplicativo nunca registra o conteúdo reconhecido em log. Capturas temporárias
são criadas com permissão `0600` e apagadas logo após o reconhecimento.

Se você escolher explicitamente um provider online, o texto reconhecido passa a
ser enviado a terceiros — e nesse caso o aplicativo pedirá consentimento antes
da primeira tradução.

## Licença

[MIT](LICENSE).
