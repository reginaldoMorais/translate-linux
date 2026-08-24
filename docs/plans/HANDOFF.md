# HANDOFF — translate-linux

> **Propósito:** memória persistente do projeto entre janelas de contexto. Toda sessão de trabalho **começa lendo este arquivo** e **termina atualizando-o**.
> **Documento irmão:** [SPEC.md](SPEC.md) — a especificação é a fonte da verdade sobre *o que* construir; este arquivo registra *onde estamos*.

---

## 1. Estado atual

| Campo | Valor |
|---|---|
| **Fase SDD** | **v1.0.0 entregue.** SPEC **v1.5** |
| **Marco atual** | **v1.0.1 publicada** com as três correções de uso real |
| **Bloqueado por** | Nada |
| **Código de produção** | Completo e empacotado. **516 testes**, CI verde |
| **Git** | `main` e `develop` em `reginaldoMorais/translate-linux`, última tag `v1.0.1`, release publicado |
| **Última atualização** | 2026-08-23 |

### Progresso por marco

| Marco | Escopo | Tag | Estado |
|---|---|---|---|
| M0 | `git init`, estrutura, `pyproject.toml`, CI de lint/testes, README inicial | — | ✅ **Concluído em 2026-08-23** |
| M1 | Fatia vertical: CLI `--capture` → portal → tesseract → `google_cloud_v2` → stdout | `v0.0.1` | ✅ **Concluído em 2026-08-23** |
| M2 | **Provider offline `local_ct2`** + comandos de instalação | `v0.1.0` | ✅ **Concluído em 2026-08-23** |
| M3 | Bandeja + janela GTK4 + cache | `v0.2.0` | ✅ **Concluído em 2026-08-23** |
| M4 | Preferências, consentimento (só online), autostart, atalho global, `--doctor` | `v0.3.0` | ✅ **Concluído em 2026-08-23** |
| M5 | `.deb` + workflow de release + README completo + roteiro manual | `v1.0.0` | ✅ **Concluído em 2026-08-23** |

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
| ~~D-05~~ | ~~Bandeja via `AyatanaAppIndicator3`~~ | — | ❌ **Revogada em 2026-08-23:** a biblioteca é GTK 3 e não convive com GTK 4. Ver D-17 |
| D-17 | **Bandeja falando `org.kde.StatusNotifierItem` direto sobre GDBus**, sem `libayatana` | GTK 3 e GTK 4 não coexistem no mesmo processo; SNI é só um protocolo D-Bus. Registro verificado funcionando com GTK 4 carregado | ✅ Firme (verificado em 2026-08-23) |
| D-06 | Autostart por XDG `~/.config/autostart` com `X-GNOME-Autostart-Delay=5` | Mais simples que systemd `--user` e herda o ambiente da sessão; o atraso evita a corrida com a extensão da bandeja | ✅ Firme |
| D-07 | Configuração em GSettings; chave de API em libsecret | Nativo do GNOME; chave nunca em texto plano | ✅ Firme |
| D-08 | Consentimento explícito de primeiro uso; histórico opt-in | A ferramenta lê qualquer pixel da tela, incluindo dados sensíveis | ✅ Firme |
| D-09 | M1 é uma fatia vertical em CLI, sem GUI | Resolve os maiores riscos técnicos (corrida do portal, comportamento do `interactive`) antes de investir em interface | ✅ Firme |
| D-10 | Empacotamento apenas `.deb` via GitHub Releases | Um usuário, uma distribuição | ✅ Firme |
| D-18 | **UI em pt-BR, CLI em inglês.** Exceções mantêm texto em inglês (vão para log e relatório de bug); `ui/messages.py` é dono do que o usuário lê | Decisão do usuário em 2026-08-23; a separação evita mistura de idiomas e mantém logs úteis | ✅ **Aprovado pelo usuário** |
| D-11 | **Clique esquerdo na bandeja abre o menu**, com "Capturar e traduzir" no primeiro item | Convenção do StatusNotifierItem sob GNOME; ação direta no clique não é possível | ✅ **Aprovado pelo usuário (PA-05, 2026-08-23)** |
| D-12 | **Provider offline `local_ct2`** com CTranslate2 + OPUS-MT int8, entregue no M4 | Elimina exposição de conteúdo de tela a terceiros e a dependência de rede e de conta de faturamento, para quem optar | ✅ Firme (pesquisa registrada na seção 2) |
| D-13 | Modelos offline **fora do `.deb`**, baixados sob demanda; `ctranslate2` em venv privado | ~80–100 MB por direção, e `ctranslate2` não está no APT | ✅ **Aprovado pelo usuário (PA-11, 2026-08-23)** |
| D-14 | Par de idiomas offline inicial: **`en → pt`** | Caso de uso predominante; cada direção extra custa ~80–100 MB | ✅ **Aprovado pelo usuário (PA-12, 2026-08-23)** |
| D-15 | Chave da Cloud Translation API providenciada pelo usuário | Pré-requisito humano do M1, confirmado em 2026-08-23 | ✅ Confirmado |

---

## 4. Perguntas em aberto

| ID | Pergunta | Suposição atual | Bloqueia |
|---|---|---|---|
| ~~PA-02~~ | Owner do GitHub / nome do repositório | ✅ **RESOLVIDO em 2026-08-23:** `reginaldoMorais/translate-linux`. O app ID passou a `io.github.reginaldomorais.TranslateLinux` (componente de domínio em minúsculas, por convenção) | — |
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

### Próximos passos

**`v1.0.1` publicada em 2026-08-23** com as três correções de uso real. **O atalho global ainda não foi confirmado funcionando pelo usuário** — a correção foi verificada aqui (delegação responde de ambos os interpretadores), mas não em uso.

1. **Executar `docs/manual-test-plan.md` por inteiro.** Continua sendo o portão que a CI não substitui, e os três defeitos acima reforçam isso: nenhum era detectável por teste automatizado nesta máquina.
2. **Assistente de primeira execução (RF-46):** instalar motor e modelo ainda é manual. Quem instalar o `.deb` sem ler o README encontra um app que não traduz — e agora sabemos que ele encontra isso *duas* vezes, porque o motor também dependia de pacotes não declarados.
3. **Detecção de idioma de origem:** o padrão é `en` e não há detecção, então capturar outro idioma erra em silêncio.
4. **Modelos além de `en→pt`:** instalar continua sendo pela CLI.

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

### 2026-08-23 — M2 concluído (tag `v0.1.0`)

**Entregue:** tradução offline funcionando e **como padrão**. `--capture` agora traduz sem chave, sem rede e sem custo.

**Módulos novos:** `translate/engine.py` (localiza e carrega o venv privado), `translate/models.py` (índice, download, extração, instalação, remoção), `translate/local_ct2.py` (o provider), `tests/unit/conftest.py` (guarda contra portal real).

**Comandos novos:** `--install-engine`, `--install-model PAR`, `--list-models`, `--provider {local,google}`, `--source`.

**Gates:** ruff limpo, mypy `--strict` em 37 arquivos, **315 testes** passando.

**Três bugs reais encontrados e corrigidos durante o M2:**

1. **Estrutura de parágrafo se perdia.** `split_text` só corta quando o texto excede o limite, então uma captura curta de dois parágrafos ia ao modelo como uma string só e voltava como uma linha, sem a linha em branco. Criado `split_sentences`, que sempre corta em fronteira de parágrafo e sentença. **Descoberto testando manualmente, não pelos testes** — os testes usavam textos longos o bastante para serem cortados de qualquer jeito.
2. **`restore_padding` duplicava chunks só de espaço.** Nunca dispararia na prática (esses chunks são filtrados), mas a função estava errada. Pego por um teste de borda.
3. **`PROVIDER_NAME` renomeado deixou `--set-api-key` e `--clear-api-key` quebrados** com `NameError`. Pego pelo ruff, não pelos testes — esses comandos estavam descobertos. Agora têm testes.

**Incidente que virou salvaguarda:** ao trocar o padrão para offline, um teste unitário que antes retornava cedo (por falta de chave) passou a executar o pipeline inteiro e **abriu o seletor de região real na tela**, capturando conteúdo de verdade durante a suíte. Agora `tests/unit/conftest.py` tem uma fixture autouse que faz qualquer teste unitário falhar imediatamente ao tocar o portal real.

**Ponta solta consciente:** `LocalTranslator.unload_if_idle()` está implementado e testado, mas **nada o chama** — não há main loop na CLI. O M3 precisa ligá-lo a um timer do GLib, senão o modelo fica residente indefinidamente.

**Desvio da SPEC a registrar:** a RF-41 pede verificação de checksum, mas o índice do Argos **não publica hash algum** (verificado: os campos são `package_version`, `from_code`, `to_code`, `links`, `code`). A integridade é estabelecida validando a estrutura do zip, recusando caminhos que escapem do destino, e gravando em `install.json` o digest observado na instalação — o que permite detectar corrupção posterior em disco, mas não adulteração na origem.

### 2026-08-23 — A biblioteca de bandeja não serve: GTK 3 contra GTK 4

**O que aconteceu:** ao preparar o M3, a descrição do pacote `gir1.2-ayatanaappindicator3-0.1` chamou atenção — "GTK-3+ version". Verificado: `libayatana-appindicator3.so.1` está linkada contra `libgtk-3.so.0`, e importá-la depois de `Gtk 4.0` falha com `Requiring namespace 'Gtk' version '3.0', but '4.0' is already loaded`.

**Por que passou despercebido na Fase 1:** na descoberta eu confirmei que o typelib existia e que o `StatusNotifierWatcher` estava ativo, mas **não verifiquei contra qual GTK a biblioteca estava linkada**. A conclusão certa ("a bandeja funciona neste sistema") escondia uma premissa errada ("logo, podemos usar esta biblioteca").

**Saída, já verificada:** StatusNotifierItem é apenas um protocolo D-Bus — a `libayatana` é uma conveniência sobre ele. Com GTK 4 carregado no mesmo processo, o spike adquiriu `org.kde.StatusNotifierItem-<pid>-1`, registrou-se via `RegisterStatusNotifierItem` e passou a constar em `RegisteredStatusNotifierItems` do watcher. Virou **RF-49** e **D-17**.

**O que ainda NÃO foi verificado:** o menu. O SNI delega o menu a `com.canonical.dbusmenu`, protocolo verboso que o spike não implementou. Esse é o risco **R15** do M3 — o análogo do R12 no M1, e deve ser atacado primeiro pelo mesmo motivo.

**Alternativas descartadas:** rebaixar tudo para GTK 3 (perde libadwaita 1.5 e contradiz D-02); processo auxiliar em GTK 3 só para a bandeja (dois toolkits e IPC para um ícone).

### 2026-08-23 — M3 concluído (tag `v0.2.0`), validado na máquina real

**Entregue:** bandeja funcionando, janela de resultado em pt-BR, cache de traduções, e `--tray` para rodar residente. O usuário confirmou o fluxo completo: ícone → menu → seleção → OCR → tradução offline.

**Módulos novos:** `tray.py` (SNI + dbusmenu sobre GDBus), `ui/menu.py` (modelo do menu, testável), `ui/result.py` (janela GTK4), `ui/messages.py` (textos em pt-BR), `translate/cache.py` (cache + `CachingProvider`), `app.py` (`Adw.Application` residente), `capture/portal.capture_async`.

**Gates:** ruff limpo, mypy `--strict` em 48 arquivos, **435 testes**.

**Bug que quebrou o primeiro teste do usuário:** `show_outcome` esvaziava um `AdwPreferencesGroup` percorrendo `get_first_child()`. O widget devolvido é a caixa **interna** do Adwaita, que não pode ser removida — a condição nunca mudava, o laço girava para sempre e o processo era morto. O laço ainda por cima era código morto: nada é adicionado àquele grupo. **Nenhum teste podia ter pego**, porque toda a cobertura de UI era de lógica pura e a janela nunca era construída. Agora existe `tests/integration/test_result_window.py`, que constrói a janela de verdade — verificado que trava se o defeito for reintroduzido — e um `timeout = 60` por teste, para que um laço infinito falhe em vez de pendurar a suíte.

**Problema de design resolvido no caminho:** `capture_interactive` cria o próprio `MainLoop`, o que congela o GTK (o toolkit já é dono do contexto padrão). Foi preciso `capture_async`, mantendo a mesma ordenação assinar-antes-de-chamar do R12.

**Duas pontas soltas do M2 fechadas:** `unload_if_idle` finalmente tem quem o chame (timer do GLib), e o cache foi ligado ao pipeline como `CachingProvider` — ambos existiam e estavam testados, mas nada os usava.

**R13 confirmado em uso real:** "My name is Reginaldo" virou "O meu nome é Reginaldo" — fraseado de português europeu. Inerente ao OPUS-MT en→pt; sem ajuste. A mitigação continua sendo sinalizar a origem e permitir editar e retraduzir.

### 2026-08-23 — M4 concluído (tag `v0.3.0`)

**Entregue:** configuração persistente (GSettings), janela de preferências, autostart, atalho global, diálogo de consentimento e `--doctor`.

**Módulos novos:** `config.py`, `autostart.py`, `shortcuts.py`, `diagnostics.py`, `ui/preferences.py`, `ui/consent.py`, mais `data/io.github.rmorais.TranslateLinux.gschema.xml`.

**Gates:** ruff limpo, mypy `--strict` em 58 arquivos, **495 testes**.

**Decisões de implementação:**
- O schema GSettings é procurado **primeiro no checkout** (`data/gschemas.compiled`, via `make schema`) e só depois no sistema, para que desenvolver não exija instalar nada em `/usr`.
- Se o schema não existir, o app **continua funcionando** — apenas esquece as configurações. Uma configuração ausente não é motivo para não traduzir.
- O consentimento (RF-35) só é pedido ao **escolher um provider online**. Com o padrão local o diálogo nunca aparece, e recusar mantém o modelo local em vez de deixar o app inutilizável.
- A exceção do mypy para subclassificar widgets foi generalizada para `translate_linux.ui.*` em vez de crescer módulo a módulo.

**Fragilidade registrada:** o atalho global escreve em `org.gnome.settings-daemon.plugins.media-keys`, porque o portal `GlobalShortcuts` não existe aqui (IC4). É a parte mais sujeita a quebrar numa atualização do GNOME. Por isso tudo em `shortcuts.py` falha suavemente: um atalho que não registra é inconveniente, nunca fatal.

**Ainda manual:** instalar motor e modelo continua sendo `--install-engine` + `--install-model`. O assistente de primeira execução (RF-46) ficou para o M5, junto com o empacotamento, que é quando ele passa a importar de verdade.

### 2026-08-23 — M5 concluído, v1.0.0 publicado

**Entregue:** `.deb` (51 KB) construído por `packaging/build-deb.sh`, workflow de release por tag, ícone e `.desktop` próprios, roteiro de teste manual, e o Release publicado em `github.com/reginaldoMorais/translate-linux/releases/tag/v1.0.0`.

**Decisão de empacotamento:** `dpkg-deb` sobre uma árvore montada, **não** debhelper. O pacote é Python puro, `arch: all`, com um punhado de arquivos de dados — o script inteiro cabe numa leitura, não exige build-deps, e permitiu verificar o layout localmente sem instalar nada. Como a distribuição é por GitHub Releases e não pelo arquivo Debian, a maquinaria do dh-python não pagava o próprio custo.

**App ID definido:** `io.github.reginaldomorais.TranslateLinux` (era `rmorais`). É o schema GSettings, o nome D-Bus e o schema do libsecret, então precisava assentar antes do empacotamento congelá-lo. Configurações guardadas sob o ID antigo não são migradas — os padrões voltam a valer.

**Quatro defeitos que só a CI revelou**, todos reais:

1. **Testes acoplados à minha máquina.** Os testes da CLI passavam aqui e falhavam na CI porque a disponibilidade do motor offline era lida do sistema de arquivos real. Eles asseguravam o estado desta máquina, não o comportamento do código. Corrigido e **verificado escondendo o `.venv-offline` e os modelos localmente**.
2. **`Gio.Settings.new` num schema ausente aborta o processo** via `g_error` — não lança, então o `try/except` não pegava, e a suíte morria com SIGTRAP mudo. Isso era **bug de produção**: crasharia em qualquer desktop não-GNOME. Agora o schema é verificado por `SettingsSchemaSource` antes de construir qualquer `Settings`.
3. **`font.getlength()` devolve lixo no runner** (valores na casa dos milhões, e negativos), gerando um PNG que o Tesseract rejeitava com erro opaco de libpng. A asserção de dimensão que eu tinha acabado de acrescentar foi o que tornou a causa visível. A fixture deixou de perguntar métricas à fonte.
4. **A fonte carrega mas não desenha glifos no runner.** A fixture agora confere a própria premissa contando tinta na tela e **pula** com explicação, em vez de acusar o OCR por algo que não é culpa dele.

**Sequência de diagnóstico que funcionou:** cada correção tornou o erro seguinte mais legível — SIGTRAP mudo → erro de libpng → "fixture width is implausible" → "assert 'Tt' == 'The quick brown fox'". Vale lembrar disso: investir em mensagem de falha rendeu mais que investir em adivinhação.

### 2026-08-23 — Três defeitos encontrados em uso real, depois da v1.0.0

A v1.0.0 passou em 499 testes, na CI e no smoke test em contêiner limpo — e produziu três defeitos no primeiro uso fora desta máquina. **Os três falhavam em silêncio**, que é o padrão que liga os três.

**1. `python3-venv` e `python3-pip` faltavam no `Depends:`.** Sem eles o `--install-engine` não cria o venv privado. O modo de falha é traiçoeiro: `python3 -m venv` monta a árvore de diretórios **antes** de falhar no `ensurepip`, deixando algo que parece instalado. Corrigido: dependências declaradas, venv pela metade é apagado antes de nova tentativa, falha não deixa resíduo, mensagem nomeia o `apt install`, e a instalação **termina importando o motor** em vez de confiar que arquivos apareceram.

**2. Markup Pango não escapado.** Títulos de `Adw.Toast` são interpretados como markup. `Atalho registrado: <Super><Shift>t` faz o Pango falhar com `Unknown tag 'Super'`, e o widget renderiza **nada** — o usuário viu uma caixa vazia com botão de fechar. Texto que o Pango não parseia não degrada: some. Corrigido em todos os widgets com markup, não só no toast que apareceu.

**3. `--capture` não delegava para a instância em execução.** Era a RF-09. Eu implementei o lado do aplicativo (`do_command_line`) e **nunca liguei o lado da CLI** — metade de um requisito, que é pior que nenhuma, porque parece pronto. O atalho global executava `translate-linux --capture`, que subia um segundo processo headless, capturava e escrevia num terminal inexistente. Corrigido expondo a ação `capture` em `org.freedesktop.Application` (interface que o `GApplication` já publicava) e ativando-a a partir da CLI. Efeito colateral bom: **torna irrelevante qual `translate-linux` está primeiro no `PATH`** — quem detém o nome no barramento faz o trabalho.

**Erro de processo meu:** empurrei um commit com o `mypy` quebrado. O `make check` falhou e o `push` rodou na sequência porque o script não parava no erro. Corrigido no commit seguinte, mas o certo era ter parado.

**O que isso mudou na SPEC (v1.5):** RF-09 reescrita nomeando o mecanismo exato (a ambiguidade foi o que permitiu implementar metade); RF-50 sobre escape de markup; IC8 sobre `Gio.Settings` abortar via `g_error`; decisão de empacotamento sem debhelper registrada; desvio de checksum do índice Argos documentado; riscos R16 e R17; e um adendo à Fase 3 sobre o que a primeira instalação real ensinou.
