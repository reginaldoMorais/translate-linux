# SPEC — translate-linux

> **Status:** Rascunho aguardando aprovação explícita
> **Autor:** Claude (Staff Engineer) — processo SDD
> **Data:** 2026-08-23
> **Versão do documento:** 1.2 — todas as perguntas bloqueantes resolvidas em 2026-08-23 (PA-01, PA-03, PA-05, PA-11, PA-12); provider de tradução offline acrescentado
> **Fase SDD:** 2 (Especificação) + 3 (Revisão Crítica) concluídas. **Nenhum código de produção foi escrito.**

---

## Problema

Usuários de Zorin OS que consomem conteúdo em idioma estrangeiro dentro de aplicações gráficas (PDFs, vídeos legendados, jogos, aplicativos proprietários, imagens, terminais, diagramas) não conseguem selecionar e copiar esse texto para traduzi-lo. O texto está renderizado como pixels, não como texto selecionável.

O fluxo atual obriga o usuário a:

1. Ler o texto na tela;
2. Redigitá-lo manualmente em translate.google.com no navegador;
3. Alternar de janela repetidamente para comparar.

Isso é lento (dezenas de segundos por trecho), sujeito a erros de transcrição, e inviável para volumes grandes ou alfabetos desconhecidos (cirílico, CJK, grego), onde o usuário sequer consegue digitar o texto.

O Zorin OS já possui o gesto mental correto: `PrintScreen` abre uma interface de seleção de região. O que falta é que o resultado dessa seleção seja **traduzido** em vez de **salvo como imagem**.

---

## Objetivos

1. **O1** — Traduzir texto visível em qualquer região da tela em até ~3 segundos após a confirmação da seleção, sem sair do contexto da aplicação atual.
2. **O2** — Reaproveitar o gesto já conhecido do usuário: seleção retangular idêntica à do PrintScreen do Zorin OS.
3. **O3** — Disponibilidade permanente: aplicativo residente na bandeja do sistema, iniciado automaticamente no login.
4. **O4** — Funcionar nativamente na sessão **Wayland** do Zorin OS 18 (padrão), com degradação graciosa para X11.
5. **O5** — Entregar artefato instalável (`.deb`) publicado automaticamente em Release do GitHub a partir de uma tag `vX.Y.Z`.
6. **O6** — `README.md` completo cobrindo build a partir do fonte, instalação, dependências, configuração e desinstalação.
7. **O7** — Não vazar conteúdo sensível de tela sem consentimento informado e explícito do usuário.
8. **O8** — Oferecer um modo de tradução **offline** opcional, que funcione sem rede e sem enviar conteúdo de tela a terceiros.

### Métricas de sucesso

| Métrica                                                       | Alvo                            |
| ------------------------------------------------------------- | ------------------------------- |
| Latência p95 (confirmação da seleção → tradução visível)      | ≤ 3,0 s                         |
| Acurácia de OCR em texto de UI ≥ 12 px, alto contraste        | ≥ 95% de caracteres corretos    |
| Consumo de RAM em repouso (residente na bandeja)              | ≤ 80 MB RSS                     |
| Taxa de falha do pipeline de captura em Zorin OS 18.1 Wayland | 0% em 20 execuções consecutivas |
| Tempo de instalação a partir do `.deb`                        | ≤ 2 min incluindo dependências  |

---

## Fora de Escopo

Explicitamente **não** serão resolvidos nesta entrega:

- **FE1** — Tradução de áudio, vídeo em tempo real ou legendas dinâmicas.
- **FE2** — Sobreposição da tradução _in-place_ sobre a tela original (estilo Google Lens AR). O resultado aparece em janela própria.
- **FE3** — Tradução contínua/streaming de uma região monitorada.
- **FE4** — OCR offline de alta qualidade com modelos neurais (PaddleOCR, EasyOCR, TrOCR). A v1 usa Tesseract.
- **FE5** — Suporte a desktops não-GNOME (KDE Plasma, XFCE, Sway, Hyprland). A arquitetura via portal XDG deve funcionar, mas **não será testada nem suportada** na v1.
- **FE6** — Empacotamento Flatpak, Snap, AppImage ou publicação em repositório APT/PPA próprio. Apenas `.deb` avulso via GitHub Releases.
- **FE7** — Tradução de arquivos, seleção de texto já selecionável, ou integração com clipboard como fonte de entrada.
- **FE8** — Sincronização de histórico, contas de usuário, telemetria ou backend próprio.
- **FE9** — Internacionalização da própria interface do aplicativo (a UI será em português brasileiro na v1; a estrutura de i18n fica preparada mas sem catálogos traduzidos).
- **FE10** — Suporte a arquiteturas diferentes de `amd64`.

---

## Análise do Estado Atual

### Do repositório

O repositório está **vazio em termos de produto**. Estado verificado:

| Item                           | Estado                                                                                                        |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------- |
| `git`                          | **Não inicializado** (`fatal: not a git repository`)                                                          |
| `README.md`                    | Existe, 0 bytes                                                                                               |
| `CLAUDE.md`                    | Regras de processo (planejar antes de executar, testes unitários obrigatórios, Conventional Commits, GitFlow) |
| `.gitignore`                   | Apenas `.code-review-graph/`                                                                                  |
| `.mcp.json`                    | Servidor MCP `code-review-graph` configurado                                                                  |
| Código-fonte, testes, ADRs, CI | **Inexistentes**                                                                                              |

Consequência: não há comportamento atual a preservar, nem compatibilidade retroativa a manter. É um projeto _greenfield_. O grafo de conhecimento `code-review-graph` está configurado mas vazio — ele se popula conforme o código for escrito.

### Do ambiente-alvo (verificado nesta máquina)

Este é o dado mais determinante do design. Tudo abaixo foi **medido**, não presumido:

| Componente                                            | Valor verificado                                                                                                        |
| ----------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| Distribuição                                          | **Zorin OS 18.1** (`ID=zorin`, `ID_LIKE=ubuntu debian`)                                                                 |
| Base                                                  | Ubuntu 24.04 LTS (`UBUNTU_CODENAME=noble`)                                                                              |
| Servidor gráfico                                      | **`XDG_SESSION_TYPE=wayland`** (`WAYLAND_DISPLAY=wayland-0`)                                                            |
| Desktop                                               | `XDG_CURRENT_DESKTOP=zorin:GNOME`, **GNOME Shell 46.0**                                                                 |
| XWayland                                              | Ativo (`DISPLAY=:0`)                                                                                                    |
| Portal XDG                                            | `xdg-desktop-portal 1.18.4` + **`xdg-desktop-portal-gnome 46.2`**                                                       |
| Backends de portal                                    | `gnome.portal`, `gtk.portal`, `gnome-keyring.portal`                                                                    |
| `org.freedesktop.portal.Screenshot`                   | **Disponível, `version = 2`**                                                                                           |
| `org.freedesktop.portal.Notification`                 | Disponível                                                                                                              |
| `org.freedesktop.portal.GlobalShortcuts`              | **INDISPONÍVEL**                                                                                                        |
| Bandeja do sistema                                    | `org.kde.StatusNotifierWatcher` **ativo em `gnome-shell`** (PID 2260) via `gnome-shell-extension-zorin-appindicator 64` |
| `libayatana-appindicator3-1`                          | `0.5.93` instalado                                                                                                      |
| `gir1.2-ayatanaappindicator3-0.1`                     | **Não instalado** (necessário para bindings Python)                                                                     |
| GTK4                                                  | `gir1.2-gtk-4.0` **4.14.5**                                                                                             |
| libadwaita                                            | `gir1.2-adw-1` **1.5.0**                                                                                                |
| GIR auxiliares                                        | `Secret-1`, `Notify-0.7`, `GdkPixbuf-2.0` presentes                                                                     |
| Python do sistema                                     | **3.12.3** em `/usr/bin/python3`, com `gi` + GTK4 + Adw funcionais                                                      |
| Python do `PATH` do usuário                           | **3.11.6 via pyenv**, **SEM módulo `gi`**                                                                               |
| Go                                                    | 1.25.2                                                                                                                  |
| Rust                                                  | 1.75.0 (defasado; noble entrega 1.75)                                                                                   |
| **Tesseract OCR**                                     | **NÃO instalado.** Candidato APT: `5.3.4-1build5`                                                                       |
| `gnome-screenshot`, `grim`, `slurp`, `maim`, `import` | **Nenhum instalado**                                                                                                    |
| `wl-copy`, `notify-send`                              | Instalados                                                                                                              |

### Implicações críticas derivadas do ambiente

Estas cinco constatações moldam toda a solução e invalidam abordagens ingênuas:

**IC1 — Wayland proíbe captura direta de tela.** Não existe equivalente a `XGetImage`. Um processo não-privilegiado **não pode** ler o framebuffer nem desenhar uma janela de sobreposição em tela cheia para desenhar o retângulo de seleção (o GNOME/Mutter não implementa `wlr-layer-shell`). Toda a família de soluções "desenhe seu próprio overlay e capture a região" — comum em tutoriais X11 — é **tecnicamente impossível** aqui.

**IC2 — O portal XDG é o único caminho sancionado, e ele já resolve a seleção.** `org.freedesktop.portal.Screenshot` versão 2 aceita a opção `interactive: true`. Com ela, **o próprio GNOME Shell exibe sua interface nativa de captura** — exatamente a mesma tela que o `PrintScreen` do Zorin OS abre — e devolve ao aplicativo a URI do PNG da região escolhida. Isso significa que **o objetivo O2 é atendido sem escrever uma única linha de UI de seleção**, e que a experiência é literalmente idêntica à do PrintScreen do sistema. Esta é a peça central do design.

**IC3 — Nenhuma ferramenta de captura CLI existe na máquina.** Não há `gnome-screenshot`, `grim`, `maim` nem `import`. Fallbacks baseados em shell-out são inviáveis sem adicionar dependências. Reforça que o portal é o caminho primário, não um plano B.

**IC4 — Atalho global não pode usar o portal.** `org.freedesktop.portal.GlobalShortcuts` não está exposto neste sistema (portal 1.18 / xdg-desktop-portal-gnome 46 não o implementam). O registro de atalho terá de ser feito escrevendo em `org.gnome.settings-daemon.plugins.media-keys custom-keybindings` via GSettings, apontando para a CLI do aplicativo.

**IC5 — A bandeja funciona, mas com semântica limitada.** O `StatusNotifierWatcher` está ativo graças à extensão `zorin-appindicator` pré-instalada. Porém, no protocolo StatusNotifierItem sob GNOME, **o clique esquerdo abre o menu do indicador; não há callback confiável de "ativação" direta**. O desejo literal do usuário ("ao clicar nele será aberta a janela de seleção") não é implementável ao pé da letra sem quebrar a convenção da plataforma. Mitigação especificada em RF-07.

**IC6 — Conflito de Python no ambiente de desenvolvimento.** O `python3` do `PATH` é o pyenv 3.11.6, que não enxerga o `gi` do sistema (PyGObject não é instalável de forma confiável via `pip` sem toolchain e headers). O desenvolvimento **deve** usar `/usr/bin/python3` com `venv --system-site-packages`. Isso precisa estar documentado com destaque no README, sob pena de o primeiro `import gi` falhar e travar o onboarding.

---

## Solução Proposta

### Visão geral

Um daemon de sessão em Python 3 + GTK4/libadwaita, residente na bandeja do sistema, que orquestra quatro etapas:

```
                    ┌──────────────────────────────────────────────┐
   Bandeja ──┐      │  1. CAPTURA                                  │
   Atalho  ──┼─────▶│     org.freedesktop.portal.Screenshot        │
   CLI     ──┘      │     { interactive: true }                    │
                    │     ── GNOME Shell desenha a seleção ──      │
                    │     ◀── file:///…/screenshot.png             │
                    └───────────────────┬──────────────────────────┘
                                        ▼
                    ┌──────────────────────────────────────────────┐
                    │  2. PRÉ-PROCESSAMENTO + OCR                  │
                    │     Pillow: escala 3x, cinza, autocontraste  │
                    │     tesseract <png> stdout -l <langs> --psm  │
                    │     ◀── texto bruto + confiança              │
                    └───────────────────┬──────────────────────────┘
                                        ▼
                    ┌──────────────────────────────────────────────┐
                    │  3. NORMALIZAÇÃO                             │
                    │     de-hifenização, junção de linhas,        │
                    │     preservação de parágrafos, limpeza       │
                    └───────────────────┬──────────────────────────┘
                                        ▼
                    ┌──────────────────────────────────────────────┐
                    │  4. TRADUÇÃO                                 │
                    │     cache SQLite → provider HTTP → cache     │
                    └───────────────────┬──────────────────────────┘
                                        ▼
                    ┌──────────────────────────────────────────────┐
                    │  5. APRESENTAÇÃO                             │
                    │     Adw.Window: tradução + original + copiar │
                    └──────────────────────────────────────────────┘
```

### Decisão de stack: Python 3.12 + PyGObject (GTK4 + libadwaita)

**Recomendação: Python.** Justificativa e trade-offs, conforme exigido por `CLAUDE.md`:

| Critério                 | Python + PyGObject                                                                          | Go 1.25                                                                                               | Rust                                                                       |
| ------------------------ | ------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| Toolkit nativo GNOME     | GTK4 4.14 + Adw 1.5 **já instalados**, bindings oficiais via GIR                            | `gotk4` exige **cgo** + `libgtk-4-dev`; ecossistema pequeno. Fyne evita GTK mas tem visual não-nativo | `gtk4-rs` é excelente, mas Rust do sistema é 1.75 (defasado); exige rustup |
| Chamada ao portal D-Bus  | `Gio.DBusProxy` embutido, incluindo `Gio.DBusConnection.signal_subscribe` para o `Response` | `godbus/dbus/v5`, puro Go, muito bom                                                                  | `zbus`/`ashpd` — `ashpd` é excelente para portais                          |
| Bandeja (SNI)            | `AyatanaAppIndicator3` via GIR (1 pacote APT a instalar)                                    | `fyne.io/systray`, puro Go, fala SNI direto                                                           | `ksni`                                                                     |
| Ciclo de build           | **Nenhum** — `.deb` `arch: all`, sem compilação                                             | Binário, mas cgo reintroduz toolchain e deps de build                                                 | Compilação longa                                                           |
| Familiaridade do usuário | Alta (declarada)                                                                            | Alta (declarada)                                                                                      | Nenhuma declarada                                                          |
| Distribuição             | Depende de `python3-gi` etc. (**todos já presentes no Zorin 18**)                           | Binário único — vantagem **anulada** pelo cgo/GTK                                                     | Binário único, mesma ressalva                                              |
| Risco principal          | Atrito do pyenv (IC6)                                                                       | Bindings GTK menos maduros                                                                            | Curva de aprendizado + toolchain                                           |

**Trade-off honesto:** Go produziria um artefato de distribuição mais limpo _se_ a UI fosse trivial. Mas este aplicativo é essencialmente **cola entre D-Bus, um binário externo (`tesseract`), HTTP e uma janela GTK** — e no momento em que a janela GTK entra, Go precisa de cgo e das mesmas bibliotecas de sistema, perdendo a vantagem do binário estático e ganhando bindings menos maduros. Python/PyGObject é o padrão da plataforma GNOME (a maioria dos aplicativos GNOME é escrita assim), elimina a etapa de compilação e usa bibliotecas que **já estão instaladas e verificadas** nesta máquina.

**Custo aceito:** o atrito do pyenv (IC6), mitigado por documentação no README e por um alvo `make dev-setup` que cria o venv com o interpretador correto.

> Esta decisão está registrada como **PA-01** em _Perguntas em Aberto_ e pode ser revertida antes da implementação sem retrabalho de especificação — os requisitos funcionais são agnósticos de linguagem.

### Componentes

| Módulo                      | Responsabilidade                                                                                              |
| --------------------------- | ------------------------------------------------------------------------------------------------------------- |
| `app.py`                    | `Adw.Application` com `HANDLES_COMMAND_LINE`; instância única via D-Bus; ciclo de vida                        |
| `tray.py`                   | Indicador `AyatanaAppIndicator3`, menu, detecção de `StatusNotifierWatcher`                                   |
| `capture/portal.py`         | Cliente do `org.freedesktop.portal.Screenshot` (assinatura do `Response` **antes** da chamada)                |
| `capture/x11.py`            | Fallback X11 (overlay GTK4 próprio + `GdkPixbuf`), usado só se `XDG_SESSION_TYPE=x11`                         |
| `ocr/preprocess.py`         | Pillow: upscale, escala de cinza, autocontraste, binarização                                                  |
| `ocr/tesseract.py`          | Invocação de `tesseract`, parsing de TSV (texto + confiança), descoberta de idiomas instalados                |
| `text/normalize.py`         | De-hifenização, junção de linhas, preservação de parágrafos, filtro de ruído — **núcleo puro, 100% testável** |
| `translate/base.py`         | Interface `TranslationProvider` + `Translation` (dataclass)                                                   |
| `translate/google_free.py`  | Endpoint `translate_a/single` (não-oficial)                                                                   |
| `translate/google_cloud.py` | Cloud Translation API v2 (oficial, com chave)                                                                 |
| `translate/local_ct2.py` | Provider offline: CTranslate2 + SentencePiece sobre modelos OPUS-MT int8, com carregamento preguiçoso |
| `translate/models.py` | Descoberta, download com checksum, instalação e remoção de modelos offline |
| `translate/chunking.py`     | Divisão em blocos respeitando fronteiras de sentença                                                          |
| `translate/cache.py`        | Cache SQLite com TTL e limite de tamanho                                                                      |
| `ui/result.py`              | `Adw.Window` de resultado                                                                                     |
| `ui/preferences.py`         | `Adw.PreferencesWindow`                                                                                       |
| `ui/consent.py`             | Diálogo de consentimento de primeiro uso                                                                      |
| `config.py`                 | GSettings (schema GLib) + `libsecret` para a chave de API                                                     |
| `logging_setup.py`          | Logging estruturado com redação de conteúdo sensível                                                          |

---

## Requisitos Funcionais

### Captura

- **RF-01** — O sistema DEVE capturar uma região retangular da tela usando `org.freedesktop.portal.Screenshot.Screenshot()` com `interactive: true` e `modal: true`, delegando a interface de seleção ao GNOME Shell.
- **RF-02** — O sistema DEVE assinar o sinal `org.freedesktop.portal.Request.Response` no caminho de objeto previsto **antes** de emitir a chamada ao portal, usando um `handle_token` gerado aleatoriamente, para eliminar a condição de corrida em que a resposta chega antes da assinatura.
- **RF-03** — O sistema DEVE tratar `response == 1` (cancelado pelo usuário) e `response == 2` (encerrado por outro motivo) como término silencioso, sem exibir erro e sem consumir cota de tradução.
- **RF-04** — Em sessões X11 (`XDG_SESSION_TYPE=x11`), o sistema DEVE tentar o portal primeiro e, se indisponível, recorrer a um overlay GTK4 próprio para seleção e captura via `GdkPixbuf`.
- **RF-05** — O sistema DEVE apagar o arquivo PNG temporário retornado pelo portal imediatamente após o OCR, mesmo em caminhos de erro (bloco `finally`).
- **RF-06** — O sistema DEVE rejeitar seleções com área menor que 8×8 px, exibindo mensagem orientando nova seleção.

### Bandeja e acionamento

- **RF-07** — O sistema DEVE exibir um ícone permanente na bandeja via StatusNotifierItem. Como o clique esquerdo sob GNOME abre o menu e não permite ação direta (IC5), o **primeiro item do menu DEVE ser "Capturar e traduzir"**, tornando a ação alcançável em dois cliques. O sistema DEVE adicionalmente registrar essa ação como _secondary activate target_ (clique do meio) quando o ambiente suportar.
- **RF-08** — O menu da bandeja DEVE conter, nesta ordem: `Capturar e traduzir`, separador, submenu `Idioma de destino` (rádio, idiomas favoritos + "Mais…"), `Histórico` (oculto se desabilitado), separador, `Preferências`, `Sobre`, `Sair`.
- **RF-09** — O sistema DEVE expor a CLI `translate-linux --capture`, que aciona a captura na instância já em execução via ativação D-Bus, sem iniciar um segundo processo.
- **RF-10** — O sistema DEVE garantir instância única: uma segunda invocação sem argumentos DEVE apenas focar/notificar a instância existente.
- **RF-11** — O sistema DEVE oferecer, nas Preferências, um botão que registra um atalho global de teclado (padrão sugerido `<Super><Shift>T`) escrevendo em `org.gnome.settings-daemon.plugins.media-keys custom-keybindings` e apontando para `translate-linux --capture`, detectando e avisando sobre conflitos com atalhos existentes.
- **RF-12** — O sistema DEVE detectar a ausência de `org.kde.StatusNotifierWatcher` no barramento e, nesse caso, notificar o usuário de que a bandeja está indisponível, permanecendo funcional via atalho global e CLI.

### OCR

- **RF-13** — O sistema DEVE aplicar pré-processamento antes do OCR: upscale (fator configurável, padrão 3×, algoritmo Lanczos), conversão para escala de cinza e autocontraste.
- **RF-14** — O sistema DEVE executar `tesseract` como subprocesso com timeout de 20 s, capturando saída em formato TSV para obter texto **e confiança por palavra**.
- **RF-15** — O sistema DEVE permitir configurar os idiomas de OCR (`-l`, ex.: `eng+por`) e o modo de segmentação de página (`--psm`, padrão 6).
- **RF-16** — O sistema DEVE detectar em tempo de execução os pacotes de idioma instalados (`tesseract --list-langs`) e apresentar apenas esses nas Preferências, com instrução de instalação (`apt install tesseract-ocr-<lang>`) para os ausentes.
- **RF-17** — Se o OCR não produzir texto com confiança média ≥ 40, o sistema DEVE informar "Nenhum texto reconhecido" com dicas acionáveis (aumentar a região, aumentar o zoom da aplicação de origem, verificar o idioma de OCR).
- **RF-18** — Se o binário `tesseract` estiver ausente, o sistema DEVE exibir erro explícito com o comando exato de instalação, sem travar o daemon.

### Normalização de texto

- **RF-19** — O sistema DEVE remover a hifenização de fim de linha (`palavra-\npalavra` → `palavrapalavra`).
- **RF-20** — O sistema DEVE unir linhas de um mesmo parágrafo com espaço, preservando quebras duplas como separadores de parágrafo.
- **RF-21** — O sistema DEVE descartar tokens com confiança abaixo de um limiar configurável (padrão 30) quando isolados entre tokens de alta confiança.
- **RF-22** — O sistema DEVE colapsar espaços redundantes e normalizar para Unicode NFC.

### Tradução

- **RF-23** — O sistema DEVE definir a interface `TranslationProvider` com o contrato `translate(text: str, source: str|None, target: str) -> Translation`, onde `Translation` carrega `text`, `detected_source`, `provider` e `from_cache`.
- **RF-24** — O sistema PODE oferecer o provider `google_free` (`https://translate.googleapis.com/translate_a/single?client=gtx&dt=t`) como opção **desabilitada por padrão**, exigindo ativação consciente nas Preferências, acompanhada de aviso de que é uma interface **não oficial, não suportada, sujeita a bloqueio por IP e provavelmente contrária aos Termos de Serviço do Google**.
- **RF-25** — O sistema DEVE implementar o provider `google_cloud_v2` (Cloud Translation API v2) **como provider padrão**, com a chave de API armazenada exclusivamente no **libsecret** (chaveiro do GNOME), nunca em arquivo de configuração, `argv` ou log. Na ausência de chave configurada, o sistema DEVE conduzir o usuário às Preferências com instruções de obtenção, em vez de falhar genericamente.
- **RF-26** — O sistema DEVE dividir textos longos em blocos de no máximo 1.500 caracteres, quebrando em fronteiras de sentença e depois de palavra, e recompor a tradução na ordem original.
- **RF-27** — O sistema DEVE aplicar retry com backoff exponencial (3 tentativas, base 500 ms, jitter) para HTTP 429, 500, 502, 503, 504 e erros de conexão; timeout total de 15 s.
- **RF-28** — O sistema DEVE consultar um cache local antes de cada requisição, chaveado por `sha256(texto ‖ origem ‖ destino ‖ provider)`.
- **RF-29** — O idioma de destino padrão DEVE ser derivado do locale do usuário na primeira execução, com fallback para `pt`.
- **RF-30** — Se o idioma detectado for igual ao de destino, o sistema DEVE exibir o texto original com aviso de que nenhuma tradução foi necessária, sem consumir cota.

### Interface de resultado

- **RF-31** — O sistema DEVE exibir uma janela com a tradução em destaque, o texto original em um `Adw.ExpanderRow` recolhido por padrão, o idioma detectado e o provider utilizado.
- **RF-32** — A janela DEVE oferecer: copiar tradução, copiar original, trocar o idioma de destino com retradução imediata, **editar o texto original e retraduzir** (correção manual de erros de OCR) e fechar com `Esc`.
- **RF-33** — O sistema DEVE exibir estado de carregamento com indicação da etapa (`Reconhecendo texto…` / `Traduzindo…`) e um botão de cancelar.
- **RF-34** — Todo trabalho de OCR e rede DEVE ocorrer fora da thread principal do GTK, com atualização de UI via `GLib.idle_add`.

### Configuração, consentimento e ciclo de vida

- **RF-35** — Na primeira execução, o sistema DEVE exibir um diálogo de consentimento explicando que o texto reconhecido é **enviado a um serviço de terceiros (Google)**, exigindo aceite explícito antes da primeira tradução. A recusa mantém o aplicativo instalado e funcional apenas para OCR local (exibe o texto reconhecido sem traduzir).
- **RF-36** — O sistema DEVE persistir configuração via GSettings sob o schema `io.github.<owner>.TranslateLinux`.
- **RF-37** — O sistema DEVE oferecer, nas Preferências, alternância de "Iniciar automaticamente no login", gerenciando `~/.config/autostart/translate-linux.desktop` com `X-GNOME-Autostart-Delay=5`.
- **RF-38** — O `.deb` DEVE instalar o autostart habilitado por padrão, respeitando desativação posterior pelo usuário em reinstalações/upgrades.
- **RF-39** — O histórico DEVE ser **desabilitado por padrão** (opt-in), limitado a 200 entradas quando ativo, com botão "Limpar histórico" e armazenamento em SQLite com permissão `0600`.

### Tradução offline (provider local)

- **RF-40** — O sistema DEVE implementar o provider `local_ct2`, de tradução **totalmente offline**, baseado em **CTranslate2** + **SentencePiece**, executando modelos neurais OPUS-MT quantizados em int8 sobre CPU.
- **RF-41** — Os modelos NÃO DEVEM ser embutidos no `.deb`. O sistema DEVE oferecer instalação sob demanda nas Preferências, com barra de progresso, verificação de checksum e opção de remoção, armazenando em `~/.local/share/translate-linux/models/<origem>-<destino>/`.
- **RF-42** — Como `ctranslate2` **não está disponível no APT do Ubuntu 24.04** (verificado), o sistema DEVE instalá-lo sob demanda em um ambiente virtual privado (`~/.local/share/translate-linux/venv-offline`), mantendo o `.deb` livre de dependências fora de repositório. Falha nessa instalação NÃO DEVE afetar os providers online.
- **RF-43** — O modelo DEVE ser carregado preguiçosamente na primeira tradução offline e descarregado após 10 minutos de ociosidade, para respeitar o orçamento de memória em repouso (NFR-P3).
- **RF-44** — Quando o provider online falhar por indisponibilidade de rede e houver modelo offline instalado para o par de idiomas, o sistema DEVE traduzir automaticamente offline, sinalizando na janela que o resultado veio do modelo local.
- **RF-45** — Se o par de idiomas solicitado não possuir modelo offline instalado, o sistema DEVE informá-lo explicitamente e oferecer o download, sem degradar a qualidade em silêncio nem pivotar por um terceiro idioma.

---

## Requisitos Não Funcionais

### Performance

- **NFR-P1** — Latência p95 de confirmação da seleção até tradução visível ≤ 3,0 s para regiões ≤ 800×600 px com ≤ 500 caracteres.
- **NFR-P2** — Tempo de inicialização até o ícone da bandeja aparecer ≤ 1,5 s a partir do `exec`.
- **NFR-P3** — Consumo em repouso ≤ 80 MB RSS e ~0% de CPU (o daemon é orientado a eventos; proibido qualquer polling). Com um modelo offline carregado, o teto sobe para 400 MB, e o modelo DEVE ser descarregado após 10 min de ociosidade (RF-43), retornando ao patamar de 80 MB.
- **NFR-P4** — Importações pesadas (Pillow, cliente HTTP) DEVEM ser carregadas preguiçosamente na primeira captura, não na inicialização.
- **NFR-P5** — Acerto de cache DEVE retornar em ≤ 50 ms.
- **NFR-P6** — A tradução offline DEVE concluir em ≤ 2,0 s para 500 caracteres em CPU, excluído o carregamento inicial do modelo, que DEVE ter indicação de progresso própria.

### Segurança e privacidade

- **NFR-S1** — A chave da API DEVE residir apenas no libsecret; jamais em GSettings, arquivo, argv ou log.
- **NFR-S2** — Todo tráfego DEVE usar HTTPS com verificação de certificado habilitada. Desabilitar verificação TLS não DEVE ser configurável.
- **NFR-S3** — Arquivos temporários de imagem DEVEM ser criados com permissão `0600` sob `$XDG_RUNTIME_DIR` e removidos em bloco `finally`.
- **NFR-S4** — Conteúdo de OCR e traduções NÃO DEVEM ser registrados em log em nível `INFO` ou superior. Em `DEBUG`, o conteúdo DEVE ser truncado em 80 caracteres e marcado, e o nível `DEBUG` exige opt-in explícito.
- **NFR-S5** — O aplicativo NÃO DEVE requerer privilégios de root em tempo de execução.
- **NFR-S6** — Nenhuma telemetria, analytics ou chamada de rede além do provider de tradução configurado.
- **NFR-S7** — O consentimento (RF-35) DEVE ser registrado com data e versão dos termos, e reexibido se os termos mudarem.

### Confiabilidade

- **NFR-R1** — Uma falha em qualquer etapa do pipeline NÃO DEVE encerrar o daemon; o ícone da bandeja DEVE permanecer funcional.
- **NFR-R2** — Toda exceção não tratada em worker threads DEVE ser capturada, registrada e convertida em mensagem de erro na UI.
- **NFR-R3** — O aplicativo DEVE degradar graciosamente: sem bandeja → CLI/atalho; sem rede → exibe o texto OCR; sem tesseract → erro acionável.
- **NFR-R4** — Corrupção do banco de cache DEVE ser detectada e o arquivo recriado automaticamente, sem perda funcional.

### Observabilidade

- **NFR-O1** — Logging estruturado em `stderr` (capturado pelo journald) e em `~/.local/state/translate-linux/app.log`, com rotação em 1 MB × 3 arquivos.
- **NFR-O2** — Cada captura DEVE receber um `trace_id` curto, presente em todas as linhas de log daquela operação.
- **NFR-O3** — Durações de cada etapa (captura, pré-processamento, OCR, tradução) DEVEM ser registradas em `DEBUG`.
- **NFR-O4** — O diálogo "Sobre" DEVE mostrar versão, tipo de sessão, versão do portal, disponibilidade do tesseract e provider ativo — para diagnóstico em issues.
- **NFR-O5** — `translate-linux --doctor` DEVE imprimir um relatório de diagnóstico do ambiente (o mesmo conjunto de checagens feito nesta análise).

### Manutenibilidade

- **NFR-M1** — Nenhum módulo com mais de 300 linhas; funções com no máximo 50.
- **NFR-M2** — Type hints obrigatórios em todas as funções públicas, verificados por `mypy --strict`.
- **NFR-M3** — Lint e formatação por `ruff`, aplicados em CI.
- **NFR-M4** — Cobertura de testes ≥ 80% de linhas nos módulos puros (`text/`, `translate/`, `config`), sem meta rígida na camada de UI.
- **NFR-M5** — Providers de tradução e backends de captura DEVEM ser substituíveis sem alteração no orquestrador (inversão de dependência).
- **NFR-M6** — Commits em inglês seguindo Conventional Commits; branches em inglês seguindo GitFlow (conforme `CLAUDE.md`).

### Escalabilidade

- **NFR-E1** — Escalabilidade é dimensionada por _tamanho de texto_, não por usuários: o sistema DEVE processar até 10.000 caracteres em uma captura sem degradação perceptível, via chunking e requisições sequenciais com limitação de taxa.
- **NFR-E2** — O cache DEVE ser limitado a 2.000 entradas ou 10 MB, com expurgo LRU.
- **NFR-E3** — Capturas simultâneas DEVEM ser serializadas: uma captura em andamento bloqueia nova solicitação (com aviso), evitando corrida no portal.

---

## Fluxos

### Fluxo principal (caminho feliz)

1. Usuário clica no ícone da bandeja e escolhe **Capturar e traduzir** (ou pressiona `<Super><Shift>T`, ou executa `translate-linux --capture`).
2. O aplicativo gera `handle_token`, assina o sinal `Response` no caminho do `Request` e chama `Screenshot(parent_window="", options={interactive: true, modal: true, handle_token: …})`.
3. O GNOME Shell escurece a tela e exibe a interface nativa de captura — **idêntica à do PrintScreen do Zorin OS**.
4. Usuário arrasta o retângulo sobre o texto desejado e confirma.
5. O portal emite `Response(0, {uri: "file:///…/png"})`.
6. O aplicativo exibe a janela de resultado em estado de carregamento (`Reconhecendo texto…`).
7. Worker thread: carrega o PNG, aplica upscale 3× + escala de cinza + autocontraste, e executa `tesseract … tsv`.
8. O texto é normalizado (de-hifenização, junção de linhas, NFC).
9. Estado da UI muda para `Traduzindo…`. O cache é consultado; em falta, o provider é chamado.
10. A janela exibe a tradução, o idioma detectado, o provider e o original recolhido.
11. O PNG temporário é removido; o resultado é gravado no cache (e no histórico, se habilitado).

### Fluxos alternativos

- **FA-1 — Cancelamento da seleção:** usuário pressiona `Esc` na UI do GNOME → `Response(1, {})` → operação encerrada silenciosamente, sem janela e sem erro.
- **FA-2 — Acerto de cache:** etapa 9 resolve localmente; latência cai para < 1 s (dominada pelo OCR).
- **FA-3 — Idioma igual ao destino:** detecção retorna o idioma de destino → exibe o original com aviso (RF-30), sem chamada de rede.
- **FA-4 — Correção manual:** usuário identifica erro de OCR, edita o texto original na janela e aciona "Retraduzir" → novo ciclo a partir da etapa 9.
- **FA-5 — Troca de idioma de destino:** usuário escolhe outro idioma na janela de resultado → retradução do texto original já reconhecido, sem novo OCR nem nova captura.
- **FA-6 — Sem consentimento:** usuário recusou o diálogo de RF-35 → o pipeline para após a etapa 8 e exibe apenas o texto reconhecido, com botão para revisar a decisão.
- **FA-7 — Sessão X11:** `XDG_SESSION_TYPE=x11` e portal indisponível → overlay GTK4 próprio assume a seleção (RF-04); demais etapas inalteradas.
- **FA-8 — Bandeja indisponível:** `StatusNotifierWatcher` ausente → notificação orientando ativar a extensão; o aplicativo segue operante via atalho/CLI.

### Fluxos de erro

| #     | Condição                                                    | Comportamento                                                                                                             |
| ----- | ----------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| FE-1  | Portal indisponível / D-Bus falha                           | Notificação "Não foi possível acessar o serviço de captura"; sugere `--doctor`; daemon segue vivo                         |
| FE-2  | `tesseract` ausente                                         | Diálogo com o comando exato: `sudo apt install tesseract-ocr tesseract-ocr-por tesseract-ocr-eng`                         |
| FE-3  | Pacote de idioma de OCR ausente                             | Erro identificando o idioma e o pacote `tesseract-ocr-<lang>` correspondente                                              |
| FE-4  | `tesseract` excede 20 s                                     | Processo morto; erro "Reconhecimento demorou demais — tente uma região menor"                                             |
| FE-5  | OCR sem texto / confiança < 40                              | "Nenhum texto reconhecido" + dicas acionáveis (RF-17)                                                                     |
| FE-6 | Sem rede (DNS/conexão) | Havendo modelo offline instalado para o par, traduz localmente e sinaliza a origem (RF-44); caso contrário, exibe o texto reconhecido + aviso "Sem conexão" + botão "Tentar novamente" |
| FE-7  | HTTP 429                                                    | 3 tentativas com backoff; persistindo, "Limite de requisições atingido — aguarde ou configure uma chave de API"           |
| FE-8  | HTTP 403 / chave inválida                                   | "Chave de API rejeitada" + atalho direto para Preferências                                                                |
| FE-9  | Formato de resposta inesperado (endpoint não-oficial mudou) | "O serviço de tradução mudou de formato" + sugestão de atualizar ou trocar de provider; log em `DEBUG` com corpo truncado |
| FE-10 | Texto > 10.000 caracteres                                   | Trunca com aviso explícito de quantos caracteres foram descartados                                                        |
| FE-11 | Captura já em andamento                                     | Notificação "Uma captura já está em andamento" (NFR-E3)                                                                   |
| FE-12 | Disco cheio ao gravar temporário                            | Erro claro; cache e histórico desativados na sessão                                                                       |
| FE-13 | Cache SQLite corrompido                                     | Recriação automática silenciosa + log `WARNING`                                                                           |

---

## Design Técnico

### Alterações arquiteturais

Projeto novo. Arquitetura em camadas com dependências apontando para dentro:

```
        ui/ ──┐              tray.py ──┐
              ├──▶ orchestrator.py ◀───┘
capture/ ◀────┤
   ocr/ ◀─────┤     (o orquestrador conhece apenas interfaces)
  text/ ◀─────┤
translate/ ◀──┘
```

Estrutura de diretórios prevista:

```
translate-linux/
├── src/translate_linux/
│   ├── __init__.py, __main__.py, app.py, orchestrator.py
│   ├── tray.py, config.py, logging_setup.py, diagnostics.py
│   ├── capture/{__init__,portal,x11}.py
│   ├── ocr/{__init__,preprocess,tesseract}.py
│   ├── text/{__init__,normalize}.py
│   ├── translate/{__init__,base,google_free,google_cloud,chunking,cache}.py
│   └── ui/{__init__,result,preferences,consent,about}.py
├── data/
│   ├── io.github.<owner>.TranslateLinux.gschema.xml
│   ├── translate-linux.desktop
│   ├── translate-linux-autostart.desktop
│   └── icons/hicolor/scalable/apps/translate-linux.svg
├── tests/{unit,integration,fixtures}/
├── packaging/debian/{control,rules,postinst,postrm,changelog,compat}
├── .github/workflows/{ci.yml,release.yml}
├── docs/plans/{SPEC.md,HANDOFF.md}
├── pyproject.toml, Makefile, README.md, LICENSE, CHANGELOG.md
```

### Banco de dados, schema e migrações

Não há banco relacional de produção. Dois SQLite locais, ambos descartáveis:

**`~/.cache/translate-linux/cache.db`**

```sql
CREATE TABLE IF NOT EXISTS translations (
    key         TEXT PRIMARY KEY,   -- sha256(text‖source‖target‖provider)
    source_lang TEXT NOT NULL,
    target_lang TEXT NOT NULL,
    provider    TEXT NOT NULL,
    result      TEXT NOT NULL,
    created_at  INTEGER NOT NULL,
    hit_count   INTEGER NOT NULL DEFAULT 0,
    last_used   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_last_used ON translations(last_used);
PRAGMA user_version = 1;
```

**`~/.local/share/translate-linux/history.db`** (opt-in, modo `0600`)

```sql
CREATE TABLE IF NOT EXISTS history (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    original     TEXT NOT NULL,
    translated   TEXT NOT NULL,
    source_lang  TEXT,
    target_lang  TEXT NOT NULL,
    created_at   INTEGER NOT NULL
);
PRAGMA user_version = 1;
```

**Estratégia de migração:** `PRAGMA user_version` controla o schema. Para o **cache**, qualquer divergência de versão dispara **recriação destrutiva** (dado derivado, sem valor). Para o **histórico**, migrações aditivas versionadas; nunca destrutivas. Não há migração de dados legados — projeto novo.

**Configuração (GSettings)** — chaves do schema `io.github.<owner>.TranslateLinux`:

| Chave                | Tipo | Padrão                            |
| -------------------- | ---- | --------------------------------- |
| `target-language`    | `s`  | derivado do locale, fallback `pt` |
| `ocr-languages`      | `s`  | `eng+por`                         |
| `ocr-psm`            | `i`  | `6`                               |
| `preprocess-scale`   | `d`  | `3.0`                             |
| `min-confidence`     | `i`  | `40`                              |
| `provider`                  | `s`  | `google_cloud_v2`                 |
| `offline-fallback`          | `b`  | `true`                            |
| `allow-unofficial-provider` | `b`  | `false`                           |
| `offline-idle-unload-min`   | `i`  | `10`                              |
| `autostart`          | `b`  | `true`                            |
| `history-enabled`    | `b`  | `false`                           |
| `favorite-languages` | `as` | `['pt','en','es']`                |
| `consent-version`    | `i`  | `0`                               |
| `global-shortcut`    | `s`  | `''`                              |

### Mudanças de API

Não há API pública exposta. Duas superfícies de contrato:

**D-Bus (consumida internamente pela CLI)** — nome `io.github.<owner>.TranslateLinux`, via `Gio.Application` com `HANDLES_COMMAND_LINE`. Argumentos aceitos: `--capture`, `--doctor`, `--version`, `--quit`, `--verbose`.

**Interface interna de provider (contrato de extensão):**

```python
@dataclass(frozen=True)
class Translation:
    text: str
    detected_source: str | None
    provider: str
    from_cache: bool = False

class TranslationProvider(Protocol):
    name: str
    def translate(self, text: str, source: str | None, target: str) -> Translation: ...
    def supported_languages(self) -> list[tuple[str, str]]: ...
```

### Integrações externas

| Integração                                     | Protocolo      | Detalhes                                                                                                                                                                                                                 |
| ---------------------------------------------- | -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `org.freedesktop.portal.Screenshot` v2         | D-Bus (sessão) | `Screenshot(s parent_window, a{sv} options) → o handle`; opções `interactive: true`, `modal: true`, `handle_token`. Resposta assíncrona via `Request.Response(u response, a{sv} results)`; `results['uri']` aponta o PNG |
| `org.freedesktop.portal.Notification`          | D-Bus (sessão) | Notificações de erro e status                                                                                                                                                                                            |
| `org.kde.StatusNotifierWatcher`                | D-Bus (sessão) | Ícone de bandeja, via `libayatana-appindicator3`                                                                                                                                                                         |
| `org.freedesktop.secrets` (libsecret)          | D-Bus (sessão) | Armazenamento da chave da API                                                                                                                                                                                            |
| `org.gnome.settings-daemon.plugins.media-keys` | GSettings      | Registro do atalho global (IC4)                                                                                                                                                                                          |
| `tesseract` 5.3.4                              | subprocesso    | `tesseract <png> stdout -l <langs> --psm <n> tsv`                                                                                                                                                                        |
| Google Translate (não-oficial)                 | HTTPS GET      | `translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=<t>&dt=t&q=<texto>` — **sem contrato, sem SLA, sujeito a bloqueio por IP e potencialmente contrário aos Termos de Serviço do Google**                 |
| Google Cloud Translation v2                    | HTTPS POST     | `translation.googleapis.com/language/translate/v2?key=<chave>` — oficial, cota gratuita mensal sujeita a mudança; **o usuário deve verificar preços vigentes**                                                           |
| CTranslate2 + SentencePiece (offline) | biblioteca local | Modelos OPUS-MT quantizados int8 executados na CPU. `ctranslate2` **não está no APT** (verificado); instalado sob demanda em venv privado (RF-42). Sem rede e sem terceiros |

### Auditoria

Não há requisito regulatório. A trilha auditável relevante é a de **privacidade**: o aceite de consentimento (RF-35) é persistido com versão dos termos e timestamp em GSettings, e o histórico opcional (RF-39) funciona como registro local, sob controle total do usuário, apagável a qualquer momento.

### Logs, métricas e monitoramento

**Logs:** `stderr` (→ journald quando iniciado pela sessão) + arquivo rotativo. Formato: `timestamp level trace_id module message`. Regra de redação obrigatória (NFR-S4) implementada como filtro do `logging`, testada unitariamente.

**Métricas:** não há coleta remota (NFR-S6). Durações de etapa ficam em `DEBUG`; `--doctor` fornece o instantâneo do ambiente.

**Monitoramento:** para um aplicativo de desktop sem backend, "monitoramento" significa **diagnosticabilidade**: `--doctor`, o diálogo "Sobre" com o ambiente, e logs redigidos e anexáveis a issues do GitHub. Qualquer promessa além disso seria fictícia.

---

## Casos de Borda

**Captura e ambiente**

1. Usuário cancela a seleção com `Esc` → sem erro, sem janela (FA-1).
2. Seleção de área vazia / menor que 8×8 px → RF-06.
3. Seleção abrangendo múltiplos monitores com escalas diferentes → o portal entrega pixels físicos já compostos; testar com escala fracionária.
4. Monitor HiDPI: texto lógico pequeno mas denso em pixels → o upscale 3× pode ser excessivo; considerar ajuste por fator de escala do monitor.
5. Sessão X11 em vez de Wayland → FA-7.
6. Logout ou bloqueio de tela durante a seleção → `Response` nunca chega; timeout de 120 s libera o _lock_ de captura.
7. Portal responde com URI em esquema não-`file://` → erro tratado, não crash.
8. `$XDG_RUNTIME_DIR` ausente ou cheio → fallback para `tempfile.gettempdir()`, e FE-12.

**Conteúdo e OCR**

9. Região sem nenhum texto (foto, gradiente) → FE-5.
10. Texto branco sobre fundo escuro → o autocontraste deve lidar; incluir fixture de regressão.
11. Texto rotacionado ou vertical (CJK) → fora do alvo de acurácia; documentar limitação e sugerir `--psm 5`.
12. Layout multi-coluna → `--psm 6` mescla colunas incorretamente; documentar `--psm 3` como alternativa.
13. Código-fonte ou terminal → OCR frequentemente corrompe pontuação; RF-32 (edição manual) é a mitigação.
14. Emojis e símbolos → Tesseract não os reconhece; degradam para ruído, filtrados por confiança.
15. Texto RTL (árabe, hebraico) → requer pacote de idioma e direção correta na UI (`Pango` cuida se o texto estiver correto).
16. Idioma da tela diferente dos idiomas de OCR configurados → resultado ruim e silencioso; **mitigar exibindo os idiomas de OCR ativos na janela de resultado**, tornando o desalinhamento visível.
17. Texto com mais de 10.000 caracteres → FE-10.
18. Texto contendo senhas, chaves ou dados pessoais → o consentimento (RF-35) e o histórico desligado por padrão (RF-39) são as defesas; o aviso deve ser explícito.

**Tradução e rede**

19. Idioma detectado == destino → RF-30.
20. Detecção de idioma incorreta → RF-32 permite reprocessar; provider oficial permite forçar `source`.
21. Proxy corporativo / `HTTPS_PROXY` no ambiente → o cliente HTTP deve honrar variáveis de proxy do ambiente.
22. Rede volta durante o erro → botão "Tentar novamente" sem refazer captura nem OCR.
23. Endpoint não-oficial muda o formato de resposta → FE-9.
24. Bloqueio por IP do endpoint gratuito → mensagem específica orientando a migrar para a API oficial.

**Ciclo de vida e estado**

25. Duas capturas acionadas em rápida sucessão → NFR-E3 / FE-11.
26. Aplicativo já em execução e usuário clica no `.desktop` novamente → RF-10.
27. Autostart dispara antes do `gnome-shell` carregar a extensão de bandeja → `X-GNOME-Autostart-Delay=5` (RF-37) + retry na conexão ao `StatusNotifierWatcher`.
28. Usuário desabilita a extensão `zorin-appindicator` com o aplicativo em execução → o ícone some; a captura via atalho continua funcionando.
29. Atualização do `.deb` com o daemon em execução → `postinst` não deve matar o processo; a nova versão vale no próximo login (documentar).
30. Remoção do pacote com autostart ativo → `postrm` deve remover o `.desktop` de autostart e o schema compilado.
31. Chaveiro (libsecret) bloqueado ou indisponível → provider oficial falha com mensagem clara; `google_free` segue funcionando.
32. Cache SQLite corrompido → FE-13.
33. Tema claro/escuro e alto contraste → a janela deve usar tokens do libadwaita, sem cores fixas.
34. Locale sem tradução da UI (v1 é pt-BR) → FE9 documenta a limitação.

**Tradução offline**

35. Par de idiomas sem modelo offline instalado → RF-45; jamais pivotar por um terceiro idioma em silêncio.
36. Download de modelo interrompido → artefato parcial descartado, checksum verificado, retomada ou reinício limpo.
37. Espaço em disco insuficiente para o modelo (~100 MB) → verificação prévia e erro claro **antes** de iniciar o download.
38. Modelo corrompido no disco → falha detectada no carregamento, modelo marcado como inválido e novo download oferecido.
39. Tradução offline pedida com o venv privado ausente ou quebrado → erro acionável; providers online seguem intactos (RF-42).
40. Primeira tradução offline após o boot → custo de carregamento do modelo (1–3 s) exibido como etapa própria, para não parecer travamento.

---

## Riscos

| #   | Risco                                                                                                                        | Prob.                    | Impacto     | Mitigação                                                                                                                                                                      |
| --- | ---------------------------------------------------------------------------------------------------------------------------- | ------------------------ | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| R1 | O endpoint `translate_a/single` é não-oficial: pode mudar, bloquear por IP ou **infringir os Termos de Serviço do Google** | Alta | **Baixo** (rebaixado) | **Resolvido por decisão (PA-03):** o padrão passou a ser a API oficial; `google_free` fica desabilitado por padrão e exige ativação consciente (RF-24) |
| R2  | Acurácia insuficiente de OCR em texto pequeno de UI                                                                          | Média                    | Alto        | Pré-processamento com upscale 3× (RF-13); confiança por palavra (RF-14); **edição manual antes de retraduzir (RF-32)** como válvula de escape; fixtures de regressão           |
| R3  | `interactive: true` pode, dependendo da versão do GNOME, também salvar a captura em `~/Pictures/Screenshots` ou no clipboard | Média                    | Médio       | **Validar empiricamente no primeiro spike de implementação**; se ocorrer, documentar e avaliar limpeza pós-captura. Registrado como PA-04                                      |
| R4  | Clique esquerdo na bandeja não dispara ação direta sob GNOME (IC5) — desvio do pedido literal do usuário                     | **Certa**                | Médio       | Primeiro item do menu é a captura (RF-07); atalho global (RF-11); _secondary activate_ no clique do meio. **Precisa de aceite explícito do usuário**                           |
| R5  | Ausência do portal `GlobalShortcuts` (IC4) obriga a manipular GSettings do GNOME — solução frágil a mudanças do GNOME        | Média                    | Médio       | Isolar em um único módulo; falha no registro não é fatal; documentar o passo manual alternativo em Configurações do sistema                                                    |
| R6 | Envio de conteúdo de tela a terceiros pode expor dados sensíveis | Média | **Crítico** | Consentimento explícito e versionado (RF-35); histórico off por padrão (RF-39); redação em logs (NFR-S4); **o provider offline (RF-40) elimina o envio por completo para quem optar por ele** |
| R7  | Atrito do pyenv sem `gi` (IC6) trava o onboarding de desenvolvimento                                                         | **Alta**                 | Médio       | Alvo `make dev-setup` usando `/usr/bin/python3 -m venv --system-site-packages`; seção destacada no README; verificação no `--doctor`                                           |
| R8  | Deriva de dependências: GNOME 47/48 em versões futuras do Zorin podem alterar o comportamento do portal                      | Média                    | Médio       | Depender apenas de interfaces de portal estáveis e versionadas; verificar a propriedade `version` em runtime; testar em CI sobre `ubuntu-24.04`                                |
| R9  | O `.deb` avulso não recebe atualizações automáticas                                                                          | Alta                     | Baixo       | Verificação opcional de nova versão via API de releases do GitHub (opt-in), ou documentar upgrade manual                                                                       |
| R10 | Complexidade excessiva para um utilitário pessoal                                                                            | Média                    | Médio       | Fatiamento em marcos: **M1 = pipeline vertical mínimo funcional**; recursos avançados só depois de o caminho principal provar valor                                            |
| R11 | Tesseract não instalado por padrão no Zorin (verificado) — usuário instala o `.deb` e nada funciona                          | **Certa** se não tratado | Alto        | `Depends:` no `.deb` inclui `tesseract-ocr` e pacotes de idioma; verificação em runtime com mensagem acionável (RF-18)                                                         |
| R12 | Corrida na assinatura do sinal `Response` do portal causa travamento intermitente                                            | Média                    | Alto        | RF-02 torna a ordem obrigatória; teste de integração com barramento simulado                                                                                                   |
| R13 | Qualidade do modelo offline (OPUS-MT int8) inferior à da API do Google, sobretudo em texto técnico e idiomático | **Alta** | Médio | Offline é opt-in e não é o padrão; a janela indica a origem do resultado (RF-44); RF-32 permite editar e retraduzir; comparação de qualidade entra no roteiro de teste manual |
| R14 | Modelos offline pesam ~80–100 MB por direção e `ctranslate2` não está no APT (verificado) | **Certa** | Médio | Modelos fora do `.deb`, baixados sob demanda (RF-41); `ctranslate2` em venv privado (RF-42); falha na instalação não afeta os providers online |

---

## Estratégia de Testes

### Testes unitários (`pytest`, sem GTK, sem rede)

| Alvo                        | Casos                                                                                                                                                                                                               |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `text/normalize.py`         | De-hifenização; junção de linhas; preservação de parágrafo; NFC; colapso de espaços; entrada vazia; só espaços; texto de uma linha; hífen legítimo composto ("bem-vindo" **não** deve ser fundido no meio da linha) |
| `translate/chunking.py`     | Texto abaixo do limite (1 bloco); quebra em fronteira de sentença; sentença única maior que o limite (quebra por palavra); palavra única gigante (quebra dura); recomposição preserva ordem e separadores           |
| `translate/google_free.py`  | Parsing de resposta bem-formada; resposta multi-segmento; array vazio; JSON malformado; campo de idioma detectado ausente; construção correta da URL e escape                                                       |
| `translate/google_cloud.py` | Parsing v2; 403; 429; chave ausente; a chave **nunca** aparece em log ou repr                                                                                                                                       |
| `translate/local_ct2.py` | Tradução com modelo minúsculo de fixture; modelo ausente → RF-45; descarregamento por ociosidade; segmentação de sentenças; venv ausente |
| `translate/models.py` | Verificação de checksum; download parcial descartado; disco insuficiente; listagem de modelos instalados |
| `translate/cache.py`        | Miss → set → hit; estabilidade da chave; expurgo LRU no limite; TTL; recriação em banco corrompido                                                                                                                  |
| `ocr/tesseract.py`          | Parsing de TSV; cálculo de confiança média; filtro de tokens; parsing de `--list-langs`; binário ausente; timeout                                                                                                   |
| `ocr/preprocess.py`         | Fator de escala aplicado; conversão para cinza; imagem 1×1; PNG inválido                                                                                                                                            |
| `config.py`                 | Padrões; derivação de idioma a partir do locale; locale desconhecido → `pt`; validação de valores                                                                                                                   |
| `logging_setup.py`          | **Filtro de redação:** conteúdo não vaza em `INFO`; truncado em 80 chars em `DEBUG`; chave de API sempre mascarada                                                                                                  |
| `capture/portal.py`         | Geração de `handle_token`; construção do caminho do `Request`; mapeamento dos códigos de resposta 0/1/2                                                                                                             |

### Testes de integração

- **Portal simulado:** serviço D-Bus falso implementando `org.freedesktop.portal.Screenshot` sobre um barramento de sessão isolado (`dbus-run-session`), validando: ordem assinatura-antes-da-chamada (R12/RF-02), resposta de sucesso, cancelamento, timeout e URI inválida.
- **OCR real:** invocação do `tesseract` de verdade sobre fixtures PNG geradas com texto conhecido; asserção de acurácia mínima por caractere.
- **HTTP simulado:** servidor local respondendo como cada provider; cobre retry/backoff, 429, timeout e resposta malformada. **Nenhum teste toca a rede real** em CI.
- **Cache + SQLite:** ciclo completo em diretório temporário, incluindo concorrência entre threads.
- **GSettings:** schema compilado em diretório temporário via `GSETTINGS_SCHEMA_DIR`; leitura/escrita/padrões.

### Testes end-to-end

- **Automatizados (CI, `xvfb-run`):** inicialização do aplicativo, aparecimento do ícone da bandeja, abertura da janela de resultado com pipeline injetado (captura e provider falsos), interações de copiar/trocar idioma/editar-retraduzir.
- **Manuais (roteiro versionado em `docs/manual-test-plan.md`), obrigatórios antes de cada release em Zorin OS 18.1 Wayland real:** captura em Wayland; captura em sessão X11; cancelamento; texto pequeno HiDPI; texto claro em fundo escuro; multi-monitor; autostart após reboot; atalho global; comportamento sem rede; sem tesseract; primeiro uso com consentimento.

### Testes de regressão

- **Corpus de fixtures de imagem** (`tests/fixtures/images/`) com esperado por arquivo, executado a cada PR; o limiar de acurácia agregado impede regressões no pré-processamento.
- **Testes de contrato dos providers** com respostas gravadas; se o formato real mudar, o teste continua verde mas a mensagem de FE-9 aparece em produção — por isso há um **teste opcional marcado `@pytest.mark.network`**, executado apenas manualmente, que valida o formato real do endpoint.
- **Suíte completa executada em CI a cada push e obrigatoriamente antes de cada tag**, conforme `CLAUDE.md` ("sempre execute os testes unitários após uma implementação").

---

## Critérios de Aceitação

**CA-01 — Captura e tradução em Wayland**

- **Given** o aplicativo em execução na bandeja em Zorin OS 18.1 com sessão Wayland
- **When** o usuário aciona "Capturar e traduzir" e seleciona uma região contendo texto em inglês
- **Then** a interface nativa de seleção do GNOME é exibida, e em até 3 segundos após a confirmação uma janela apresenta a tradução em português, o idioma detectado e o texto original recolhido

**CA-02 — Paridade com o PrintScreen do Zorin**

- **Given** que o usuário conhece o comportamento do `PrintScreen` do sistema
- **When** ele aciona a captura pelo aplicativo
- **Then** a interface de seleção é a mesma do sistema, sem overlay próprio nem diferença visual

**CA-03 — Cancelamento silencioso**

- **Given** a interface de seleção aberta
- **When** o usuário pressiona `Esc`
- **Then** nenhuma janela, notificação ou erro é exibido, e o aplicativo permanece na bandeja

**CA-04 — Autostart no login**

- **Given** o `.deb` instalado com autostart habilitado
- **When** o usuário reinicia e faz login no Zorin OS
- **Then** o ícone aparece na bandeja em até 15 segundos sem intervenção manual

**CA-05 — Ausência de texto**

- **Given** uma região sem texto legível
- **When** a captura é confirmada
- **Then** o aplicativo informa "Nenhum texto reconhecido" com dicas acionáveis, sem realizar chamada de rede

**CA-06 — Falha de rede**

- **Given** a máquina sem conectividade
- **When** o usuário captura uma região com texto
- **Then** o texto reconhecido é exibido com aviso de indisponibilidade e um botão "Tentar novamente" que retraduz sem repetir a captura

**CA-07 — Consentimento de primeiro uso**

- **Given** a primeira execução após a instalação
- **When** o usuário aciona a primeira captura
- **Then** um diálogo informa que o texto será enviado ao Google e exige aceite explícito; a recusa mantém o aplicativo funcional em modo somente-OCR

**CA-08 — Correção manual de OCR**

- **Given** uma janela de resultado com erro de reconhecimento
- **When** o usuário edita o texto original e aciona "Retraduzir"
- **Then** a tradução é atualizada sem nova captura e sem novo OCR

**CA-09 — Dependência ausente**

- **Given** um sistema sem `tesseract` instalado
- **When** o usuário aciona a captura
- **Then** um erro exibe o comando exato de instalação e o daemon permanece em execução

**CA-10 — Release automatizado**

- **Given** o repositório com CI configurado
- **When** a tag `v0.0.1` é enviada ao GitHub
- **Then** o workflow executa lint, type-check e testes, constrói o `.deb`, gera os checksums SHA256 e publica um GitHub Release com changelog e artefatos anexados

**CA-11 — Instalação a partir do artefato**

- **Given** o `.deb` publicado no Release
- **When** o usuário executa `sudo apt install ./translate-linux_0.0.1_all.deb`
- **Then** as dependências (incluindo `tesseract-ocr`) são resolvidas, o schema GSettings é compilado e o aplicativo é iniciável pelo menu

**CA-12 — Privacidade em logs**

- **Given** o aplicativo em nível de log padrão
- **When** uma tradução é realizada
- **Then** nenhum trecho do texto reconhecido ou traduzido, e nenhuma chave de API, aparece no arquivo de log ou no journald

**CA-13 — Cache**

- **Given** uma tradução já realizada
- **When** a mesma região é capturada de novo com o mesmo idioma de destino
- **Then** o resultado vem do cache local, sem requisição de rede, e a janela indica a origem em cache

**CA-14 — Instância única**

- **Given** o aplicativo em execução
- **When** `translate-linux --capture` é executado no terminal
- **Then** a instância existente inicia a captura e nenhum segundo processo é criado

**CA-15 — Diagnóstico**

- **Given** um usuário relatando problema
- **When** ele executa `translate-linux --doctor`
- **Then** o relatório exibe tipo de sessão, versão do portal, disponibilidade do `StatusNotifierWatcher`, versão do tesseract, idiomas de OCR instalados e provider ativo

**CA-16 — Tradução offline sem rede**

- **Given** o modelo offline `en → pt` instalado e a máquina sem conectividade
- **When** o usuário captura uma região com texto em inglês
- **Then** a tradução é produzida localmente em até 5 segundos e a janela indica que o resultado veio do modelo offline

**CA-17 — Fallback automático para offline**

- **Given** o provider `google_cloud_v2` configurado, o fallback offline habilitado e um modelo instalado
- **When** a chamada de rede falha por indisponibilidade de conexão
- **Then** o sistema traduz offline automaticamente, sem exibir erro, sinalizando a origem do resultado

**CA-18 — Ausência de modelo offline**

- **Given** o provider offline selecionado e nenhum modelo instalado para o par de idiomas
- **When** o usuário captura uma região com texto
- **Then** o sistema informa qual modelo falta e oferece o download, sem traduzir por um idioma-ponte nem falhar em silêncio

---

## Plano de Rollout

### Estratégia de deploy

**Marcos (cada um entregável e testável isoladamente):**

| Marco  | Escopo                                                                                                                                                                                      | Tag      |
| ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| **M0** | `git init`, estrutura do projeto, `pyproject.toml`, CI de lint/testes, README inicial                                                                                                       | —        |
| **M1** | **Fatia vertical mínima:** CLI `--capture` → portal → tesseract → `google_cloud_v2` → saída em `stdout`. Sem bandeja, sem GUI. **Prova o risco técnico central (R12, R3) o mais cedo possível** | `v0.0.1` |
| **M2** | Bandeja + janela de resultado GTK4 + normalização de texto + cache                                                                                                                          | `v0.1.0` |
| **M3** | Preferências, consentimento, autostart, atalho global, provider oficial `google_cloud_v2`, `--doctor` | `v0.2.0` |
| **M4** | **Provider offline `local_ct2`:** instalação sob demanda do runtime e dos modelos, carregamento preguiçoso, fallback automático sem rede | `v0.3.0` |
| **M5** | Empacotamento `.deb` + workflow de release + README completo + roteiro de teste manual | `v1.0.0` |

**Pipeline (GitHub Actions):**

- `ci.yml` — em push e PR, sobre `ubuntu-24.04` (mesma base do Zorin 18): instala dependências de sistema, roda `ruff`, `mypy --strict`, `pytest` (com `xvfb-run` para os testes de UI) e publica cobertura.
- `release.yml` — disparado por tag `v*`:
  1. Reexecuta a suíte completa (uma tag nunca publica sem testes verdes);
  2. Deriva a versão da tag e valida coerência com `__version__` e `debian/changelog`;
  3. Constrói o `.deb` (`arch: all`) com `Depends:` sobre `python3 (>= 3.10)`, `python3-gi`, `gir1.2-gtk-4.0`, `gir1.2-adw-1`, `gir1.2-ayatanaappindicator3-0.1`, `python3-pil`, `python3-requests`, `tesseract-ocr`, `tesseract-ocr-eng`, `tesseract-ocr-por`, `tesseract-ocr-osd`, `gir1.2-secret-1`, `python3-sentencepiece`. **`ctranslate2` fica fora do `Depends:`** por não existir no APT — é instalado sob demanda pelo próprio aplicativo (RF-42), e sua ausência não impede o funcionamento online;
  4. Instala o `.deb` num contêiner limpo como _smoke test_ (`--version` e `--doctor` devem responder);
  5. Gera `SHA256SUMS`;
  6. Publica o GitHub Release com changelog derivado dos Conventional Commits, marcando `v0.x` como pré-lançamento.

**Público:** distribuição pessoal via GitHub Releases. Não haverá PPA nem loja na v1 (FE6).

### Estratégia de rollback

- **Do aplicativo:** `sudo apt install ./translate-linux_<versão-anterior>_all.deb` a partir do Release anterior (todos permanecem disponíveis). Como não há migração destrutiva de dados (o cache é descartável e o histórico só sofre migrações aditivas), o downgrade é seguro por construção.
- **Do release:** tag defeituosa → marcar o Release como _draft_, corrigir e publicar `vX.Y.Z+1`. **Nunca reescrever uma tag já publicada.**
- **Desativação imediata sem desinstalar:** menu da bandeja → `Sair`, e desmarcar o autostart nas Preferências.
- **Desinstalação limpa:** `sudo apt remove translate-linux` remove o autostart e o schema; `--purge` remove também os dados de usuário (cache e histórico), o que deve estar documentado no README.

### Monitoramento pós-deploy

Sem backend, o monitoramento é local e sob controle do usuário — e a especificação evita prometer o que não existe:

1. **Verificação manual pós-instalação:** `translate-linux --doctor` cobre todas as pré-condições ambientais.
2. **Logs locais** rotativos e redigidos, anexáveis a issues.
3. **Template de issue no GitHub** solicitando a saída do `--doctor` e a versão.
4. **Roteiro de teste manual** executado pelo mantenedor em Zorin 18.1 real antes de cada tag — este é o verdadeiro portão de qualidade, já que CI não consegue exercitar Wayland+GNOME de verdade.
5. **Sem telemetria** (NFR-S6). A ausência de dados de campo é uma consequência aceita da postura de privacidade.

---

## Perguntas em Aberto

| #         | Questão                                                                                  | Suposição adotada até resposta                                                  | Impacto se mudar                                                             |
| --------- | ---------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| ~~PA-01~~ | Linguagem: Python 3.12 + PyGObject? | ✅ **RESOLVIDO em 2026-08-23 — Sim.** | — |
| **PA-02** | Owner/organização do GitHub e nome final do repositório                                  | `github.com/rmorais/translate-linux`, app ID `io.github.rmorais.TranslateLinux` | Baixo — afeta IDs, schema e URLs                                             |
| ~~PA-03~~ | Provider padrão | ✅ **RESOLVIDO em 2026-08-23 — API oficial (`google_cloud_v2`).** O `google_free` passou a opt-in desabilitado (RF-24) e um provider **offline** foi acrescentado (RF-40 a RF-45) | — |
| **PA-04** | O `interactive: true` do portal salva cópia em `~/Pictures/Screenshots` ou no clipboard? | Não salva; **exige validação empírica no M1**                                   | Médio — pode exigir limpeza pós-captura                                      |
| ~~PA-05~~ | RF-07: o clique esquerdo abrir o menu em vez de capturar direto é aceitável? | ✅ **RESOLVIDO em 2026-08-23 — Aceito.** | — |
| **PA-06** | Idiomas de OCR a instalar por padrão                                                     | `eng` + `por` (+ `osd`)                                                         | Baixo — tamanho do pacote                                                    |
| **PA-07** | Licença do projeto                                                                       | MIT                                                                             | Baixo                                                                        |
| **PA-08** | Autostart habilitado por padrão na instalação?                                           | Sim (RF-38), desativável                                                        | Baixo                                                                        |
| **PA-09** | Suporte a sessão X11 é realmente necessário, dado que o Zorin 18 usa Wayland?            | Implementar o fallback, mas com prioridade baixa (após M3)                      | Médio — remover reduziria escopo                                             |
| **PA-10** | Estilo de versionamento a partir de qual marco?                                          | `v0.0.1` no M1, conforme o pedido; SemVer daí em diante                         | Baixo                                                                        |
| ~~PA-11~~ | Instalar `ctranslate2` via pip em venv privado no primeiro uso offline? | ✅ **RESOLVIDO em 2026-08-23 — Aceito** (RF-42) | — |
| ~~PA-12~~ | Par de idiomas offline inicial | ✅ **RESOLVIDO em 2026-08-23 — `en → pt`** | — |

---

# Fase 3 — Revisão Crítica

Revisão adversarial da especificação acima. Os achados **já foram incorporados** aos requisitos correspondentes; esta seção registra o raciocínio e o rastro.

### Requisitos faltantes identificados e incorporados

- **RC-01 — Ausência de consentimento de privacidade.** A versão inicial da especificação enviava conteúdo de tela ao Google sem qualquer aceite. Para uma ferramenta que lê _qualquer pixel da tela_ — incluindo gerenciadores de senha, e-mails e documentos — isso é inaceitável. → **RF-35, NFR-S7, R6, CA-07**.
- **RC-02 — Sem escape para erro de OCR.** Sem edição manual, um erro de reconhecimento deixava o usuário sem saída além de repetir a captura. → **RF-32, FA-4, CA-08**.
- **RC-03 — Ausência do tesseract como falha de instalação.** Verifiquei que o tesseract **não está instalado** nesta máquina. Sem `Depends:` no pacote e sem verificação em runtime, todo primeiro uso falharia. → **RF-18, R11, FE-2, CA-09**, e `Depends:` explícito no rollout.
- **RC-04 — Retradução exigia recaptura.** Trocar o idioma de destino recapturava a tela desnecessariamente. → **FA-5, RF-32**.
- **RC-05 — Sem diagnóstico.** Suporte a um aplicativo desktop sem telemetria é impossível sem um comando de diagnóstico. → **NFR-O5, `--doctor`, CA-15**.
- **RC-06 — Idiomas de OCR invisíveis.** O modo de falha mais provável e mais silencioso é o usuário capturar texto em alemão com o OCR configurado para `eng+por`, obtendo lixo sem entender a causa. → **Caso de borda 16**: exibir os idiomas de OCR ativos na janela de resultado.
- **RC-26 — A alternativa offline não havia sido avaliada.** A pergunta do usuário motivou a investigação, com três candidatos verificados: **Apertium** está no APT e é leve, mas **não possui par inglês↔português** (verificado: existem apenas `es-pt`, `pt-gl` e `por-cat`) e é tradução baseada em regras; **Argos Translate** tem boa qualidade, mas depende de `stanza==1.10.1` → **`torch`** e de `spacy` (verificado no PyPI), inviável para um utilitário de desktop; a rota viável é **CTranslate2 (wheel de 39,5 MB) + SentencePiece (este disponível como `python3-sentencepiece` no APT) sobre modelos OPUS-MT int8** — exatamente o motor que o Argos usa por dentro, sem a cauda de dependências. → **RF-40 a RF-45, R13, R14, M4, CA-16 a CA-18**.

### Premissas ocultas expostas

- **RC-07 — "Wayland é como X11".** Falso e fatal. Toda a família de soluções com overlay próprio é impossível (IC1). O design foi ancorado no portal desde a fundação, não como adaptação.
- **RC-08 — "Clique na bandeja dispara uma ação".** Falso sob GNOME/SNI (IC5). O pedido literal do usuário não é implementável de forma convencional; a mitigação está explicitada e o desvio foi elevado a **PA-05** para aceite consciente, em vez de ser silenciosamente ignorado.
- **RC-09 — "Existe um portal de atalho global".** Falso neste sistema — verificado: `GlobalShortcuts` não está exposto (IC4). A alternativa via GSettings é mais frágil e isso está registrado em R5.
- **RC-10 — "`python3` tem `gi`".** Falso no ambiente do usuário: o `python3` do `PATH` é pyenv 3.11.6 sem PyGObject (IC6). Deixado sem tratamento, isso quebra o primeiro `import gi` do desenvolvimento. → **R7** e alvo `make dev-setup`.
- **RC-11 — "A tradução gratuita é estável."** Não é: é uma interface não documentada, sem contrato e provavelmente contrária aos Termos de Serviço. Elevado a **R1** e a **PA-03**, com o provider oficial já na v1 em vez de "trabalho futuro".

### Compatibilidade retroativa

Projeto novo, sem compatibilidade a preservar. Os pontos de compatibilidade **futura** foram endereçados preventivamente: `PRAGMA user_version` nos dois bancos, política de migração aditiva no histórico e destrutiva no cache (caso de borda 32/FE-13), `consent-version` para reexibir termos alterados (NFR-S7), e verificação da propriedade `version` do portal em runtime (R8).

### Cenários de falha adicionais

- **RC-12 — Corrida no sinal do portal.** Chamar `Screenshot()` antes de assinar `Response` produz travamento intermitente e praticamente indepurável — um clássico do desenvolvimento com portais. → **RF-02, R12**, com teste de integração dedicado.
- **RC-13 — Captura sem fim.** Se o `Response` nunca chegar (logout, crash do shell durante a seleção), o _lock_ de captura ficaria preso para sempre, inutilizando o aplicativo até o reinício. → **caso de borda 6**: timeout de 120 s.
- **RC-14 — Bloqueio da UI.** OCR (segundos) e rede na thread principal do GTK congelariam a janela. → **RF-34** torna o threading obrigatório, não uma otimização.
- **RC-15 — Corrida do autostart.** O aplicativo pode iniciar antes de a extensão da bandeja registrar o `StatusNotifierWatcher`, resultando em ausência silenciosa do ícone. → **caso de borda 27**: atraso de 5 s + retry.

### Gargalos de performance

- **RC-16** — Upscale de 3× em uma região de tela grande gera imagens muito grandes e OCR lento. Mitigado pelo timeout de 20 s (FE-4) e pelo fator configurável; o caso de borda 4 registra o ajuste por escala de monitor como refinamento.
- **RC-17** — Importar Pillow e o cliente HTTP no _startup_ atrasaria o ícone da bandeja. → **NFR-P4** (carregamento preguiçoso).
- **RC-18** — Chunking sequencial de textos longos multiplica a latência. Aceito conscientemente: paralelizar aumentaria o risco de _rate limit_ (R1) para um ganho marginal num utilitário interativo. Registrado em **NFR-E1**.

### Problemas de segurança

- **RC-19** — Chave de API em arquivo de configuração seria legível por qualquer processo do usuário. → **NFR-S1** (libsecret obrigatório) e teste unitário que garante que a chave não aparece em log nem em `repr`.
- **RC-20** — PNGs temporários com o conteúdo da tela poderiam permanecer em disco após um crash. → **NFR-S3** (`0600`, `$XDG_RUNTIME_DIR`, remoção em `finally`) e **RF-05**.
- **RC-21** — Logs em `DEBUG` vazariam conteúdo de tela. → **NFR-S4**, implementado como filtro de logging **testado unitariamente**, não como convenção de código.
- **RC-22** — Histórico habilitado por padrão acumularia conteúdo sensível indefinidamente. → **RF-39** inverte o padrão para opt-in.

### Problemas operacionais

- **RC-23** — Atualizar o `.deb` com o daemon em execução deixa a versão antiga na memória, produzindo relatos de bug enganosos. → **caso de borda 29**; o diálogo "Sobre" mostra a versão em execução (NFR-O4).
- **RC-24** — `apt remove` deixaria autostart órfão apontando para um binário inexistente. → `postrm` no plano de rollout.
- **RC-25** — CI não consegue exercitar Wayland+GNOME de verdade; um pipeline verde não prova que o produto funciona. Em vez de fingir cobertura, a especificação torna o **roteiro de teste manual um portão obrigatório de release**.

### Complexidade desnecessária — cortes deliberados

Itens considerados e **removidos** para manter o escopo proporcional a um utilitário pessoal:

- Overlay de seleção próprio → desnecessário e impossível em Wayland; o portal já entrega a UI do sistema (esta é a maior economia do design).
- Serviço systemd `--user` → o XDG autostart é mais simples e herda o ambiente da sessão corretamente.
- OCR neural (PaddleOCR/EasyOCR) → centenas de MB de dependências para um ganho não comprovado; RF-32 (edição manual) cobre a lacuna a custo próximo de zero (FE4).
- Flatpak/Snap/AppImage → três formatos de empacotamento para um usuário; `.deb` basta (FE6).
- Detecção automática de idioma de OCR via `--psm 0` (OSD) → adiciona uma passada de OCR ao caminho crítico para benefício incerto; adiado.
- Tradução _in-place_ estilo AR → problema visual de ordem de magnitude superior (FE2).
- i18n da UI na v1 → um usuário, um idioma (FE9).

### Conclusão da revisão

A especificação é **executável e proporcional**. Com PA-03 resolvido em favor da API oficial, o risco contratual (**R1**) deixou de ser relevante: o endpoint não-oficial virou opção desabilitada por padrão. O maior risco remanescente passa a ser a **acurácia do OCR (R2)**, mitigada pela edição manual em vez de por engenharia especulativa, seguida da **qualidade do modelo offline (R13)**, mitigada por ele ser opt-in e ter a origem sinalizada na interface. A ordem dos marcos é deliberada: o **M1 é uma fatia vertical fina que exercita o portal, o tesseract e a tradução de ponta a ponta**, resolvendo as maiores incógnitas técnicas (R3, R12) antes de qualquer investimento em interface.

---

## Aguardando aprovação

**Decisões aprovadas em 2026-08-23:** PA-01 (Python 3.12 + PyGObject), PA-03 (API oficial do Google como padrão, com o endpoint não-oficial rebaixado a opt-in e um provider offline acrescentado), PA-05 (clique na bandeja abre o menu, com a captura no primeiro item), PA-11 (`ctranslate2` em venv privado) e PA-12 (par offline inicial `en → pt`). O usuário confirmou também que providenciará a chave da Cloud Translation API, pré-requisito humano do M1.

**Nenhuma pergunta em aberto bloqueia qualquer marco.** Restam apenas itens de baixo impacto, decidíveis durante a execução sob as suposições já registradas: PA-02 (owner do repositório → `io.github.rmorais.TranslateLinux`), PA-04 (validação empírica dentro do próprio M1), PA-06, PA-07 (licença MIT), PA-08, PA-09 e PA-10.

Conforme o processo SDD, a implementação começa somente após aprovação explícita desta versão 1.2 do documento.
