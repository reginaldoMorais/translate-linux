# HANDOFF — translate-linux

> **Propósito:** memória persistente do projeto entre janelas de contexto. Toda sessão de trabalho **começa lendo este arquivo** e **termina atualizando-o**.
> **Documento irmão:** [SPEC.md](SPEC.md) — a especificação é a fonte da verdade sobre *o que* construir; este arquivo registra *onde estamos*.

---

## 1. Estado atual

| Campo | Valor |
|---|---|
| **Fase SDD** | Fase 2 + Fase 3 concluídas. SPEC em **v1.2**, com **todas as perguntas bloqueantes resolvidas** |
| **Marco atual** | Nenhum. Pré-M0 |
| **Bloqueado por** | **Aprovação explícita da SPEC v1.2** — único item pendente |
| **Código de produção** | **Nenhum escrito** (correto para esta fase) |
| **Última atualização** | 2026-08-23 |

### Progresso por marco

| Marco | Escopo | Tag | Estado |
|---|---|---|---|
| M0 | `git init`, estrutura, `pyproject.toml`, CI de lint/testes, README inicial | — | ⬜ Não iniciado |
| M1 | Fatia vertical: CLI `--capture` → portal → tesseract → `google_cloud_v2` → stdout | `v0.0.1` | ⬜ Não iniciado |
| M2 | Bandeja + janela GTK4 + normalização + cache | `v0.1.0` | ⬜ Não iniciado |
| M3 | Preferências, consentimento, autostart, atalho global, provider oficial, `--doctor` | `v0.2.0` | ⬜ Não iniciado |
| M4 | Provider offline `local_ct2` + download de modelos sob demanda | `v0.3.0` | ⬜ Não iniciado |
| M5 | `.deb` + workflow de release + README completo + roteiro manual | `v1.0.0` | ⬜ Não iniciado |

---

## 2. Contexto essencial (leia antes de qualquer coisa)

O produto: um utilitário de bandeja para Zorin OS que reproduz o gesto do `PrintScreen` — seleção retangular de uma região da tela — mas, em vez de salvar uma imagem, faz **OCR do texto e o traduz**, exibindo o resultado em uma janela.

**Os cinco fatos que mais determinam o design** (todos verificados na máquina em 2026-08-23, não presumidos):

1. **A sessão é Wayland** (Zorin OS 18.1, GNOME Shell 46). Captura direta de tela e overlays próprios em tela cheia são **tecnicamente impossíveis**.
2. **`org.freedesktop.portal.Screenshot` versão 2 está disponível** e aceita `interactive: true`, fazendo o **GNOME Shell desenhar a própria UI de seleção**. Isso entrega a paridade com o PrintScreen do Zorin *de graça* — nenhuma UI de seleção precisa ser escrita. É a peça central do design.
3. **`GlobalShortcuts` do portal NÃO existe** neste sistema. O atalho global precisa ser registrado via GSettings do GNOME (`media-keys custom-keybindings`).
4. **`tesseract` NÃO está instalado.** Precisa ser dependência do `.deb` e ser verificado em runtime.
5. **O `python3` do `PATH` é pyenv 3.11.6 SEM o módulo `gi`.** O desenvolvimento **deve** usar `/usr/bin/python3` (3.12.3, que tem `gi` + GTK4 + Adw 1.5). Este é o tropeço número um do onboarding.

> Detalhes completos do ambiente: SPEC.md → *Análise do Estado Atual* e *Implicações críticas (IC1–IC6)*.

### Sobre tradução offline (pesquisa de 2026-08-23)

Três candidatos foram investigados de fato, não presumidos:

| Candidato | Veredito |
|---|---|
| **Apertium** (no APT, leve, baseado em regras) | ❌ **Não tem par inglês↔português.** Verificado: só existem `es-pt`, `pt-gl`, `por-cat`. Chegar a en→pt exigiria pivô duplo `eng→spa→por`, com erro composto sobre uma base já mediana |
| **Argos Translate** (PyPI, neural, boa qualidade) | ❌ Depende de `stanza==1.10.1` → **`torch`** e de `spacy` (verificado no PyPI). Centenas de MB a alguns GB de dependências para um utilitário de bandeja |
| **CTranslate2 + SentencePiece + modelos OPUS-MT int8** | ✅ **Escolhido.** É o motor que o Argos usa por dentro, sem a cauda de dependências. Wheel de 39,5 MB; deps só `numpy`/`pyyaml`; `python3-sentencepiece` está no APT; modelo ~80–100 MB por direção |

Ressalva de empacotamento: **`ctranslate2` não existe no APT** do Ubuntu 24.04. Por isso ele fica fora do `Depends:` do `.deb` e é instalado sob demanda em venv privado (RF-42), com o suporte offline sendo totalmente opt-in.

---

## 3. Decisões tomadas

| ID | Decisão | Razão | Status |
|---|---|---|---|
| D-01 | Captura via `org.freedesktop.portal.Screenshot` com `interactive: true` | Único caminho viável em Wayland; entrega a UI nativa de seleção sem código próprio | ✅ Firme |
| D-02 | **Python 3.12 + PyGObject (GTK4 + libadwaita)** | GTK 4.14 e Adw 1.5 já instalados; sem etapa de compilação; padrão da plataforma GNOME | ✅ **Aprovado pelo usuário (PA-01, 2026-08-23)** |
| D-03 | Tesseract 5 via subprocesso, com pré-processamento em Pillow | Evita cgo/bindings; TSV fornece confiança por palavra | ✅ Firme |
| D-04 | **`google_cloud_v2` (API oficial) é o provider padrão**; `google_free` vira opt-in desabilitado | Elimina o risco de ToS e de bloqueio por IP que o endpoint não-oficial trazia | ✅ **Aprovado pelo usuário (PA-03, 2026-08-23)** |
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
| PA-04 | O `interactive: true` salva cópia em `~/Pictures/Screenshots`? | Não salva — **validar empiricamente no M1** | Nada; é uma verificação do M1 |
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
| R6 | Exposição de conteúdo de tela a terceiros | 🟡 Mitigado por consentimento; **eliminado por completo para quem usar o provider offline (M4)** |
| R12 | Corrida ao assinar o sinal `Response` do portal | 🟡 Mitigado por design (RF-02) — **exercitar no M1** |
| R13 | Qualidade do modelo offline abaixo da API do Google | 🟡 Aberto — offline é opt-in e a origem é sinalizada na UI |
| R14 | Modelos de ~100 MB e `ctranslate2` fora do APT | 🟡 Mitigado por design (D-13) |
| R7 | Atrito do pyenv sem `gi` | 🟢 Resolvido por design (`make dev-setup` + README) |
| R11 | Tesseract ausente por padrão | 🟢 Resolvido por design (`Depends:` + verificação em runtime) |

---

## 6. Próximos passos

**Imediato (bloqueado):** aprovação explícita da SPEC v1.1.

**Ao aprovar — M0:**
1. `git init`, branch `develop` (GitFlow), `.gitignore` de Python, LICENSE (PA-07).
2. Esqueleto do projeto e `pyproject.toml` conforme a estrutura do SPEC.
3. `make dev-setup` usando `/usr/bin/python3 -m venv --system-site-packages` (contorna IC6).
4. `ci.yml` com ruff + mypy + pytest sobre `ubuntu-24.04`.

**M1 — a fatia vertical que compra informação:**
5. `capture/portal.py` **com a assinatura do sinal antes da chamada** (RF-02) — a primeira coisa a validar.
6. **Verificar PA-04/R3:** o `interactive` deixa arquivo em `~/Pictures/Screenshots`?
7. `ocr/tesseract.py` + `ocr/preprocess.py` (após instalar os pacotes do tesseract, ver seção 8).
8. `translate/google_cloud.py` + chave no libsecret + CLI `--capture` imprimindo em stdout.
9. Testes unitários de tudo que for lógica pura (obrigatório por `CLAUDE.md`).
10. Tag `v0.0.1`.

> **Pré-requisito humano do M1:** ✅ resolvido — o usuário confirmou em 2026-08-23 que providenciará a chave da Cloud Translation API. Ela só é necessária no passo 8.

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
