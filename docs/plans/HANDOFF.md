# HANDOFF — translate-linux

> **Propósito:** memória persistente do projeto entre janelas de contexto. Toda sessão de trabalho **começa lendo este arquivo** e **termina atualizando-o**.
> **Documento irmão:** [SPEC.md](SPEC.md) — a especificação é a fonte da verdade sobre *o que* construir; este arquivo registra *onde estamos*.

---

## 1. Estado atual

| Campo | Valor |
|---|---|
| **Fase SDD** | Em implementação. SPEC **v1.3** — provider padrão mudou para offline |
| **Marco atual** | **M1 concluído**, tag `v0.0.1`. Próximo: **M2 = provider offline** (reordenado) |
| **Bloqueado por** | Nada |
| **Código de produção** | Pipeline completo em CLI. **211 testes**, cobertura 88%, mypy strict e ruff limpos |
| **Git** | 9 commits em `develop`, tag `v0.0.1`. **Sem remoto configurado** |
| **Última atualização** | 2026-08-23 |

### Progresso por marco

| Marco | Escopo | Tag | Estado |
|---|---|---|---|
| M0 | `git init`, estrutura, `pyproject.toml`, CI de lint/testes, README inicial | — | ✅ **Concluído em 2026-08-23** |
| M1 | Fatia vertical: CLI `--capture` → portal → tesseract → `google_cloud_v2` → stdout | `v0.0.1` | ✅ **Concluído em 2026-08-23** |
| **M2** | **Provider offline `local_ct2`** + assistente de primeira execução | `v0.1.0` | ⬜ Próximo |
| M3 | Bandeja + janela GTK4 + cache | `v0.2.0` | ⬜ Não iniciado |
| M4 | Preferências, consentimento (só online), autostart, atalho global, `--doctor` | `v0.3.0` | ⬜ Não iniciado |
| M5 | `.deb` + workflow de release + README completo + roteiro manual | `v1.0.0` | ⬜ Não iniciado |

---

## 2. Contexto essencial (leia antes de qualquer coisa)

O produto: um utilitário de bandeja para Zorin OS que reproduz o gesto do `PrintScreen` — seleção retangular de uma região da tela — mas, em vez de salvar uma imagem, faz **OCR do texto e o traduz**, exibindo o resultado em uma janela.

**Os cinco fatos que mais determinam o design** (todos verificados na máquina em 2026-08-23, não presumidos):

1. **A sessão é Wayland** (Zorin OS 18.1, GNOME Shell 46). Captura direta de tela e overlays próprios em tela cheia são **tecnicamente impossíveis**.
2. **`org.freedesktop.portal.Screenshot` versão 2 está disponível** e aceita `interactive: true`, fazendo o **GNOME Shell desenhar a própria UI de seleção**. Isso entrega a paridade com o PrintScreen do Zorin *de graça* — nenhuma UI de seleção precisa ser escrita. É a peça central do design.
3. **`GlobalShortcuts` do portal NÃO existe** neste sistema. O atalho global precisa ser registrado via GSettings do GNOME (`media-keys custom-keybindings`).
4. **`tesseract` 5.3.4 está instalado** nesta máquina desde 2026-08-23 (`eng`, `osd`, `por`), mas **não vem por padrão no Zorin**: continua sendo dependência obrigatória do `.deb` e verificação de runtime (RF-18).
5. **O `python3` do `PATH` é pyenv 3.11.6 SEM o módulo `gi`.** O desenvolvimento **deve** usar `/usr/bin/python3` (3.12.3, que tem `gi` + GTK4 + Adw 1.5). Este é o tropeço número um do onboarding.

> Detalhes completos do ambiente: SPEC.md → *Análise do Estado Atual* e *Implicações críticas (IC1–IC6)*.

### Sobre tradução offline (pesquisa de 2026-08-23)

Três candidatos foram investigados de fato, não presumidos:

| Candidato | Veredito |
|---|---|
| **Apertium** (no APT, leve, baseado em regras) | ❌ **Não tem par inglês↔português.** Verificado: só existem `es-pt`, `pt-gl`, `por-cat`. Chegar a en→pt exigiria pivô duplo `eng→spa→por`, com erro composto sobre uma base já mediana |
| **Argos Translate** (PyPI, neural, boa qualidade) | ❌ Depende de `stanza==1.10.1` → **`torch`** e de `spacy` (verificado no PyPI). Centenas de MB a alguns GB de dependências para um utilitário de bandeja |
| **CTranslate2 + SentencePiece + modelos OPUS-MT int8** | ✅ **Escolhido e comprovado na prática em 2026-08-23** (ver seção 9). Wheel de 39,5 MB; deps só `numpy`/`pyyaml`; par `en→pt` v1.9 com 66 MB comprimido e 82 MB em disco |

Ressalva de empacotamento: **`ctranslate2` não existe no APT** do Ubuntu 24.04. Por isso ele fica fora do `Depends:` do `.deb` e é instalado sob demanda em venv privado (RF-42), com o suporte offline sendo totalmente opt-in.

---

## 3. Decisões tomadas

| ID | Decisão | Razão | Status |
|---|---|---|---|
| D-01 | Captura via `org.freedesktop.portal.Screenshot` com `interactive: true` | Único caminho viável em Wayland; entrega a UI nativa de seleção sem código próprio | ✅ Firme |
| D-02 | **Python 3.12 + PyGObject (GTK4 + libadwaita)** | GTK 4.14 e Adw 1.5 já instalados; sem etapa de compilação; padrão da plataforma GNOME | ✅ **Aprovado pelo usuário (PA-01, 2026-08-23)** |
| D-03 | Tesseract 5 via subprocesso, com pré-processamento em Pillow | Evita cgo/bindings; TSV fornece confiança por palavra | ✅ Firme |
| ~~D-04~~ | ~~`google_cloud_v2` é o provider padrão~~ | — | ❌ **Revogada em 2026-08-23 por custo da API.** Ver D-16 |
| D-16 | **`local_ct2` (offline) é o provider padrão.** `google_cloud_v2` continua implementado e testado, como escolha explícita; `google_free` segue desabilitado | Custo por caractere da API do Google; e o motor local provou-se rápido o bastante (0,11 s para 284 caracteres) e leve o bastante (141 MB residentes) | ✅ **Decidido pelo usuário (revisão de PA-03, 2026-08-23)** |
| D-05 | Bandeja via `AyatanaAppIndicator3` (SNI) | `StatusNotifierWatcher` confirmado ativo via `gnome-shell-extension-zorin-appindicator` | ✅ Firme |
| D-06 | Autostart por XDG `~/.config/autostart` com `X-GNOME-Autostart-Delay=5` | Mais simples que systemd `--user` e herda o ambiente da sessão; o atraso evita a corrida com a extensão da bandeja | ✅ Firme |
| D-07 | Configuração em GSettings; chave de API em libsecret | Nativo do GNOME; chave nunca em texto plano | ✅ Firme |
| D-08 | Consentimento explícito de primeiro uso; histórico opt-in | A ferramenta lê qualquer pixel da tela, incluindo dados sensíveis | ✅ Firme |
| D-09 | M1 é uma fatia vertical em CLI, sem GUI | Resolve os maiores riscos técnicos (corrida do portal, comportamento do `interactive`) antes de investir em interface | ✅ Firme |
| D-10 | Empacotamento apenas `.deb` via GitHub Releases | Um usuário, uma distribuição | ✅ Firme |
| D-11 | **Clique esquerdo na bandeja abre o menu**, com "Capturar e traduzir" no primeiro item | Convenção do StatusNotifierItem sob GNOME; ação direta no clique não é possível | ✅ **Aprovado pelo usuário (PA-05, 2026-08-23)** |
| D-12 | **Provider offline `local_ct2`** com CTranslate2 + OPUS-MT int8, entregue no M4 | Elimina exposição de conteúdo de tela a terceiros e a dependência de rede e de conta de faturamento, para quem optar | ✅ Firme (pesquisa registrada na seção 2) |
| D-13 | Modelos offline **fora do `.deb`**, baixados sob demanda; `ctranslate2` em venv privado | ~80–100 MB por direção, e `ctranslate2` não está no APT | ✅ **Aprovado pelo usuário (PA-11, 2026-08-23)** |
| D-14 | Par de idiomas offline inicial: **`en → pt`** | Caso de uso predominante; cada direção extra custa ~80–100 MB | ✅ **Aprovado pelo usuário (PA-12, 2026-08-23)** |
| D-15 | Chave da Cloud Translation API providenciada pelo usuário | Pré-requisito humano do M1, confirmado em 2026-08-23 | ✅ Confirmado |

---

## 4. Perguntas em aberto

| ID | Pergunta | Suposição atual | Bloqueia |
|---|---|---|---|
| PA-02 | Owner do GitHub / nome do repositório | `rmorais/translate-linux` | M0 (nomes de schema e app ID) |
| PA-04 | O `interactive: true` salva cópia em `~/Pictures/Screenshots`? | Não salva — **verificação humana pendente**, ver seção 6 | Nada; script pronto em `scripts/verify_portal_behaviour.py` |
| PA-06 | Idiomas de OCR padrão | `eng` + `por` + `osd` | Nada |
| PA-07 | Licença | MIT | M0 |
| PA-08 | Autostart ligado por padrão? | Sim | M3 |
| PA-09 | Fallback X11 é necessário? | Sim, prioridade baixa (após M3) | Nada |
| PA-10 | Versionamento a partir do M1 | `v0.0.1`, SemVer adiante | Nada |

**Resolvidas em 2026-08-23:** PA-01 (Python), PA-03 (API oficial + offline), PA-05 (menu da bandeja), PA-11 (venv privado), PA-12 (`en → pt`) → migradas para *Decisões tomadas*.

**Nenhuma pergunta pendente bloqueia marco algum.** PA-02 e PA-07 são necessárias no M0 e seguem sob as suposições registradas (`io.github.rmorais.TranslateLinux`, licença MIT) — basta avisar se divergir.

---

## 5. Riscos em acompanhamento

| ID | Risco | Estado |
|---|---|---|
| R1 | Endpoint gratuito do Google é não-oficial | 🟢 **Rebaixado** — não é mais o padrão (D-04); virou opt-in desabilitado |
| R2 | Acurácia de OCR em texto pequeno de UI | 🟡 **Maior risco aberto.** Mitigado por design (edição manual, upscale 3×) — validar no M1 |
| R3 | `interactive: true` pode salvar cópia da captura | 🟡 **Validar empiricamente no M1** (PA-04) |
| R6 | Exposição de conteúdo de tela a terceiros | 🟢 **Rebaixado** — com o padrão offline nada sai da máquina |
| R12 | Corrida ao assinar o sinal `Response` do portal | 🟢 **Retirado em 2026-08-23** — teste de regressão contra portal falso reproduz a ordenação patológica |
| R13 | Qualidade do modelo offline; mistura pt-PT e pt-BR | 🔴 **Promovido a risco principal** — deixou de ser opt-in e passou a afetar todo uso. Mitigado por sinalizar a origem (RF-48), permitir editar e retraduzir (RF-32) e manter `google_cloud_v2` disponível |
| R14 | Modelos de ~100 MB e `ctranslate2` fora do APT | 🟡 Mitigado por design (D-13) |
| R7 | Atrito do pyenv sem `gi` | 🟢 Resolvido por design (`make dev-setup` + README) |
| R11 | Tesseract ausente por padrão | 🟢 Resolvido por design; OCR validado de verdade contra o binário 5.3.4 |

---

## 6. Próximos passos

### Verificação humana pendente do M1 (fazer antes do M2)

Duas coisas exigem uma sessão gráfica real e uma pessoa na frente da tela:

1. **Fechar PA-04/R3:** rodar `.venv/bin/python scripts/verify_portal_behaviour.py`, selecionar uma região e ler o veredito. Ele responde se o `interactive: true` deixa cópia em `~/Pictures/Screenshots` ou no clipboard. **Registrar o resultado aqui e na SPEC.**
2. **Primeira captura real ponta a ponta:** `.venv/bin/translate-linux --set-api-key` e depois `--capture`. Até aqui o caminho portal→arquivo só foi exercitado contra um portal falso, e a tradução só contra uma sessão HTTP falsa.

### M2 — provider offline `local_ct2` (reordenado, era M4)

Trabalhar em `feature/local-translation` a partir de `develop`. **A viabilidade já está provada** (seção 9); o que falta é transformar o experimento em código de produção.

1. `translate/models.py` — índice, download com progresso e checksum, extração do `.argosmodel` **descartando `stanza/`**, instalação em `~/.local/share/translate-linux/models/<origem>-<destino>/`, listagem e remoção.
2. `translate/local_ct2.py` — provider implementando o mesmo `TranslationProvider`. Pontos não-óbvios já descobertos:
   - **Não usar `SentencePieceProcessor.decode()`**: deixa `U+2581` na saída. Usar `"".join(tokens).replace("\u2581", " ").strip()` (RF-47).
   - Traduzir sentença a sentença via `translate_batch`, reaproveitando `chunking.py` para as fronteiras.
   - Carregamento preguiçoso e descarte após 10 min de ociosidade (RF-43).
3. `setup/bootstrap.py` — assistente que instala `ctranslate2` em venv privado e baixa o modelo padrão numa etapa só (RF-46).
4. Trocar o padrão do provider para `local_ct2`; `--capture` passa a funcionar sem nenhuma chave.
5. Testes: destokenização, seleção de modelo, modelo ausente, checksum, descarregamento por ociosidade. Integração marcada para pular quando o modelo não estiver instalado.
6. Tag `v0.1.0`.

### Pendências de baixo risco

- **Sem remoto git:** `git push` e a CI do GitHub só funcionam depois de criar o repositório remoto. A tag `v0.0.1` existe só localmente.
- **PA-02:** o app ID `io.github.rmorais.TranslateLinux` já está em `constants.py` e é usado como schema do libsecret. Trocar antes do M3, se divergir.
- **Idioma da interface:** a CLI do M1 está em **inglês**. A SPEC (FE9) pede UI em pt-BR na v1. Decisão a tomar no M2, quando a UI GTK entrar: adotar gettext e traduzir tudo o que é voltado ao usuário, ou assumir inglês. Não resolver isso pela metade.

---

## 7. Protocolo de handoff entre janelas de contexto

**Ao iniciar uma sessão:**
1. Ler este arquivo por inteiro.
2. Ler a seção do SPEC.md correspondente ao marco atual (não o documento inteiro).
3. Conferir o estado real do repositório contra a seção 1 — **o repositório é a verdade; se divergir, corrigir este arquivo primeiro**.

**Ao encerrar uma sessão:**
1. Atualizar a tabela de estado (seção 1) e o progresso dos marcos.
2. Registrar decisões novas em *Decisões tomadas*, com a razão.
3. Mover perguntas respondidas de *Perguntas em aberto* para *Decisões tomadas*.
4. Atualizar o estado dos riscos; adicionar riscos descobertos durante a implementação.
5. Reescrever *Próximos passos* de forma que a próxima sessão possa agir sem reler o histórico.
6. Anexar uma entrada no *Diário*.

**Regras de higiene:**
- Datas sempre absolutas (`2026-08-23`), nunca relativas ("ontem", "semana passada").
- Este arquivo registra **estado e decisões**, não narrativa. Nada de log de conversa.
- Se o SPEC mudar, incrementar a versão dele no cabeçalho e anotar aqui o motivo.
- Achados que contradigam o SPEC vão para o SPEC **e** para o diário — a especificação nunca deve ficar obsoleta em silêncio.

---

## 8. Referência rápida

**Ambiente-alvo:** Zorin OS 18.1 · Ubuntu 24.04 noble · GNOME Shell 46.0 · Wayland · GTK 4.14.5 · libadwaita 1.5.0 · `/usr/bin/python3` 3.12.3 · portal Screenshot v2 · Go 1.25.2 disponível

**Dependências de sistema para desenvolver:**
```bash
sudo apt install tesseract-ocr tesseract-ocr-eng tesseract-ocr-por tesseract-ocr-osd \
                 gir1.2-ayatanaappindicator3-0.1 python3-pil python3-requests \
                 gir1.2-secret-1 python3-sentencepiece libglib2.0-bin
```
> Já presentes e verificados: `python3-gi`, `gir1.2-gtk-4.0`, `gir1.2-adw-1`, `libayatana-appindicator3-1`, `xdg-desktop-portal-gnome`, `Secret-1`, `Notify-0.7`, `GdkPixbuf-2.0`.
> **`ctranslate2` não está no APT** — só é instalado no M4, em venv privado.

**Ambiente de desenvolvimento (contorna o pyenv sem `gi`):**
```bash
/usr/bin/python3 -m venv --system-site-packages .venv && source .venv/bin/activate
python -c "import gi; gi.require_version('Gtk','4.0'); from gi.repository import Gtk; print('ok')"
```

**Comandos de diagnóstico do ambiente:**
```bash
echo "$XDG_SESSION_TYPE $XDG_CURRENT_DESKTOP"
busctl --user get-property org.freedesktop.portal.Desktop /org/freedesktop/portal/desktop \
       org.freedesktop.portal.Screenshot version
busctl --user list | grep -i statusnotifier
tesseract --list-langs
```

**Convenções do projeto** (de `CLAUDE.md`): planejar antes de executar · código funcional, nunca pseudocódigo · testes unitários após toda implementação · testes novos para toda feature ou alteração · branches em inglês (GitFlow) · commits em inglês (Conventional Commits).

---

## 9. Diário

### 2026-08-23 — Fase 1 (Descoberta) e Fases 2/3 (Especificação e Revisão)

**Feito:** levantamento completo do ambiente-alvo em máquina real; `SPEC.md` v1.0 e este `HANDOFF.md`.

**Descobertas que mudaram o design:**
- Sessão é **Wayland**, o que elimina toda a classe de soluções com overlay próprio de seleção.
- O portal `Screenshot` v2 com `interactive: true` **entrega a UI de seleção do próprio GNOME**, atendendo o requisito de paridade com o PrintScreen sem escrever UI alguma. Maior simplificação do projeto.
- `GlobalShortcuts` do portal **não existe** aqui → atalho global via GSettings do GNOME.
- **Tesseract não está instalado**; sem tratamento, todo primeiro uso falharia.
- O `python3` do usuário (pyenv 3.11.6) **não enxerga o `gi`** do sistema.
- Nenhuma ferramenta CLI de captura (`grim`, `maim`, `gnome-screenshot`) existe → o portal não é plano B, é o único caminho.

**Achados da revisão crítica incorporados:** consentimento de privacidade (faltava por completo); edição manual do texto de OCR como escape para erros de reconhecimento; tesseract como dependência de pacote e verificação em runtime; comando `--doctor`; ordem obrigatória de assinatura do sinal do portal; redação de conteúdo sensível em logs como filtro testado.

### 2026-08-23 — SPEC v1.1: decisões aprovadas e provider offline

**Respostas do usuário:** PA-01 → Python; PA-03 → **API oficial**, com a pergunta "existe pacote offline de tradução que poderíamos usar?"; PA-05 → aceito.

**Pesquisa feita** (resultados na seção 2): Apertium **não tem par inglês↔português**; Argos Translate puxa `torch` via `stanza`; a rota viável é **CTranslate2 + SentencePiece + OPUS-MT int8**.

**Mudanças na SPEC (v1.0 → v1.1):**
- Objetivo **O8** (modo offline) acrescentado.
- **RF-24** rebaixado: `google_free` vira opt-in desabilitado. **RF-25**: `google_cloud_v2` passa a padrão.
- Nova seção **RF-40 a RF-45** (provider offline, modelos sob demanda, venv privado, carregamento preguiçoso, fallback automático sem rede).
- **NFR-P3** ajustado (teto de 400 MB com modelo carregado); **NFR-P6** acrescentado.
- **FE-6** (sem rede) deixou de ser erro e virou degradação graciosa para offline.
- **R1 rebaixado**; **R13** (qualidade offline) e **R14** (peso dos modelos, `ctranslate2` fora do APT) acrescentados.
- Casos de borda 35–40 (modelos offline); **CA-16 a CA-18**; **RC-26** na revisão crítica.
- Marcos renumerados: **M4 = provider offline (`v0.3.0`)**, **M5 = empacotamento (`v1.0.0`)**.
- Corrigido um colapso de lista introduzido pelo formatador automático na seção de Casos de Borda.

**Estado:** aguardando aprovação da v1.1. Nenhum código escrito, nenhum commit feito.

### 2026-08-23 — SPEC v1.2: últimas perguntas bloqueantes fechadas

**Respostas do usuário:** PA-11 (instalar `ctranslate2` em venv privado no primeiro uso offline) → aceito; PA-12 (par offline inicial `en → pt`) → aceito; chave da Cloud Translation API → o usuário providencia.

**Mudanças na SPEC (v1.1 → v1.2):** PA-11 e PA-12 marcadas como resolvidas; seção final reescrita registrando que **nenhuma pergunta em aberto bloqueia qualquer marco**. Nenhuma alteração em requisitos, riscos ou design — apenas fechamento de decisões já especificadas.

**Suposições que valem até aviso em contrário:** app ID `io.github.rmorais.TranslateLinux` (PA-02) e licença MIT (PA-07), ambas necessárias no M0.

**Estado:** aguardando a aprovação explícita da v1.2 para iniciar o M0. Nenhum código escrito, nenhum commit feito.

### 2026-08-23 — M0 concluído

**Aprovação:** o usuário aprovou a SPEC v1.2. Implementação liberada.

**Entregue:**
- `git init` com `main` e `develop` (GitFlow), commit `2bdbb51` em Conventional Commits. **Sem remoto configurado** — o `git push` ainda não é possível.
- Layout `src/`, com `translate_linux` e os subpacotes `capture`, `ocr`, `text`, `translate` e `ui` contendo apenas o contrato de responsabilidade (sem stubs falsos).
- `cli.py` funcional com `--version`; entry point `translate-linux` e `python -m translate_linux` ambos verificados.
- `pyproject.toml`: setuptools, `requires-python >=3.10`, versão derivada de `translate_linux.__version__` (contrato que o release do M5 valida contra a tag).
- Ferramentas: ruff (lint + format), mypy `strict`, pytest com marcadores `network`, `integration` e `ui`; `network` fica fora da execução padrão.
- `Makefile` com `.RECIPEPREFIX := >`, e `dev-setup` fixando `/usr/bin/python3 -m venv --system-site-packages` — a mitigação de IC6/R7.
- `.github/workflows/ci.yml` em `ubuntu-24.04`, replicando o `make check` e reportando o ambiente resolvido.
- `README.md`, `LICENSE` (MIT), `CHANGELOG.md`, `.gitignore`.

**Resultado dos quality gates:** `ruff check` e `ruff format --check` limpos; `mypy --strict` sem erros em 9 arquivos; **4 testes passando**; cobertura 86% (o descoberto é `__main__.py`, que só roda como subprocesso).

**Achado durante o M0:** o `ruff format` tenta formatar blocos Python embutidos em Markdown e reprovava a `SPEC.md`. Resolvido com `extend-exclude = ["docs"]` — documentação é prosa, não código-fonte.

**Confirmado na prática:** o venv com `--system-site-packages` criado por `/usr/bin/python3` enxerga o PyGObject (GTK 4.14). A mitigação de IC6 funciona.

**Estado:** M0 fechado, working tree limpa na branch `develop`. Pronto para o M1.

### 2026-08-23 — M1 concluído (tag `v0.0.1`)

**Entregue:** o pipeline vertical completo em linha de comando — portal → pré-processamento → Tesseract → normalização → Cloud Translation v2 → stdout.

**Módulos:** `capture/portal.py`, `ocr/preprocess.py`, `ocr/tesseract.py`, `text/normalize.py`, `translate/{base,chunking,google_cloud}.py`, `orchestrator.py`, `credentials.py`, `constants.py`, `cli.py`.

**Resultado dos gates:** ruff limpo, mypy `--strict` sem erros em 29 arquivos, **211 testes passando**, cobertura 88% (`normalize`, `preprocess` e `orchestrator` em 100%; `google_cloud` 97%; `tesseract` 96%).

**R12 retirado.** O teste `test_a_response_emitted_before_the_method_reply_is_still_caught` sobe um portal falso num barramento D-Bus privado e emite o `Response` **antes** da resposta do método. Se a assinatura do sinal fosse feita depois da chamada, ele travaria até o timeout. Além disso, o código guarda contra `loop.quit()` antes de `loop.run()`, que travaria para sempre.

**Bug real encontrado e corrigido durante o M1:** a remontagem dos chunks traduzidos indexava por `id()` da string. O CPython reutiliza o mesmo objeto para strings de 1 caractere, então textos com chunks idênticos seriam remontados fora de ordem. Passou a usar posição. Coberto por `test_repeated_identical_chunks_are_reassembled_in_order`.

**Tesseract 5.3.4 foi instalado durante a sessão** (eng, osd, por), então os testes de integração de OCR rodaram **de verdade**: frase simples, texto claro sobre fundo escuro, texto de 12 px e rejunção de linhas quebradas — todos passando com o pré-processamento de upscale 3×.

**Decisões tomadas na implementação:**
- Providers e backends recebem a conexão D-Bus e a sessão HTTP por injeção, o que tornou possível testar tudo sem rede e sem sessão gráfica.
- `batch()` agrupa chunks em poucas requisições em vez de uma por chunk, reduzindo latência.
- `N818` desativado no ruff: `CaptureCancelled` e `NoTextRecognised` são desfechos normais, e o sufixo `Error` os descreveria mal.
- `ruff format` reformatava blocos Python dentro do Markdown da SPEC; `docs/` foi excluído do ruff.

**Ainda não exercitado de verdade:** o caminho portal→arquivo com seleção humana, e uma chamada real à API do Google. Ambos estão na seção 6 como verificação humana pendente.

### 2026-08-23 — Mudança de rumo: tradução offline passa a ser o padrão

**Motivo:** o usuário apurou o custo por caractere da Cloud Translation API e o considerou alto. Como o provider offline já estava aprovado (D-12) e especificado, a mudança **não descarta trabalho**: o `google_cloud_v2` do M1 continua implementado e testado, apenas deixa de ser o padrão.

**Viabilidade comprovada nesta máquina, não presumida:**

| Medição | Resultado |
|---|---|
| Pacote `en→pt` v1.9 | 66 MB comprimido, 82 MB em disco |
| Carregamento do modelo | 0,13 s |
| Tradução de 284 caracteres | 0,11 s |
| RSS com modelo residente | 141 MB (baseline 12 MB) |
| Liberado ao descarregar | ~77 MB |
| Dependências | `ctranslate2` 4.8.1 + `sentencepiece` 0.2.0 — **sem `torch`** |

**Dois achados que viraram requisito:**
1. **`SentencePieceProcessor.decode()` não funciona** com esses modelos — o vocabulário é compartilhado com o CTranslate2 e o `decode()` devolve o marcador `U+2581` embutido no texto (`'▁Clique no▁botão'`). A destokenização precisa ser manual: concatenar as peças e trocar `U+2581` por espaço. Virou **RF-47**. Sem esse achado, a saída sairia sutilmente quebrada.
2. **O modelo mistura português europeu e brasileiro** na mesma sessão ("gravar o ficheiro" e "arquivos de log"). Isso promoveu **R13** a risco de impacto alto, já que agora afeta todo uso por padrão.

**Qualidade observada:** boa para texto de interface e mensagens de erro ("Deseja descartar as alterações não salvas?", "Uso da memória: 45%, carga média de CPU 1.2 em 5 minutos" — ambas corretas). Fraca em texto idiomático (traduziu "The quick brown fox" como "A rapidinha raposa marrom").

**O diretório `stanza/` dos pacotes Argos é descartado** na extração: ele existe só para segmentar sentenças, e `translate/chunking.py` já faz isso desde o M1.

**Efeito colateral bom:** com o padrão offline, nada sai da máquina, então **R6 caiu para verde** e o diálogo de consentimento (RF-35) deixa de aparecer para quem nunca escolher um provider online.

**Estado:** SPEC v1.3 e marcos reordenados (M2 = offline, M3 = bandeja/UI). Nenhum código de produção escrito para o M2 ainda.
