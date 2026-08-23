# Roteiro de teste manual

A CI não consegue exercitar o que mais importa neste projeto. Ela roda sob
`xvfb`, sem Wayland, sem GNOME Shell, sem portal de captura e sem bandeja do
sistema — exatamente as quatro coisas de que o aplicativo depende. Um pipeline
verde prova que a lógica está correta, não que o produto funciona.

Por isso este roteiro é o portão de qualidade real. **Execute-o em Zorin OS
antes de cada tag.**

Ambiente de referência: Zorin OS 18.1, GNOME Shell 46, sessão Wayland.

---

## Antes de começar

```bash
translate-linux --doctor
```

Anote a saída. Tudo deve estar sem marcação `x`. Avisos `!` são aceitáveis se
você souber por quê.

---

## 1. Captura (o caminho crítico)

| # | Passo | Esperado |
|---|---|---|
| 1.1 | `translate-linux --capture` com texto em inglês na tela | A interface de seleção do GNOME aparece — a mesma do PrintScreen |
| 1.2 | Selecionar uma região com texto e confirmar | Texto reconhecido e tradução aparecem em até 3 s |
| 1.3 | Repetir e pressionar `Esc` | Encerra em silêncio: sem erro, sem janela, código de saída 0 |
| 1.4 | Selecionar uma região vazia (fundo liso) | "Nenhum texto reconhecido", com dicas; nenhuma tradução tentada |
| 1.5 | Selecionar uma área minúscula (poucos pixels) | Erro claro, sem travar |
| 1.6 | Verificar `~/Pictures/Screenshots` depois de várias capturas | Nenhum arquivo novo deixado para trás |
| 1.7 | `ls $XDG_RUNTIME_DIR/translate-linux/` após uma captura | Vazio: os temporários são apagados |

## 2. Reconhecimento

| # | Passo | Esperado |
|---|---|---|
| 2.1 | Capturar texto claro sobre fundo escuro | Reconhecido corretamente |
| 2.2 | Capturar texto pequeno (~12 px) | Reconhecido; se falhar, `--scale 4` resolve |
| 2.3 | Capturar texto em duas colunas | `--psm 3` produz resultado melhor que o padrão |
| 2.4 | Capturar texto em idioma **não** configurado no OCR | Resultado ruim, **mas os idiomas ativos aparecem na interface**, tornando a causa visível |

## 3. Tradução offline

| # | Passo | Esperado |
|---|---|---|
| 3.1 | Desconectar a rede e capturar | Traduz normalmente; nada falha |
| 3.2 | Capturar a mesma região duas vezes | A segunda vem do cache, visivelmente mais rápida |
| 3.3 | `translate-linux --list-models` | Motor e modelos instalados são listados |
| 3.4 | Escolher um par sem modelo instalado | Diz qual modelo falta e como instalá-lo; não traduz por idioma-ponte |
| 3.5 | Deixar o app ocioso por mais de 10 min e checar a memória | O modelo foi descarregado; RSS volta ao patamar baixo |

## 4. Bandeja e janela

| # | Passo | Esperado |
|---|---|---|
| 4.1 | `translate-linux --tray` | Ícone aparece na bandeja |
| 4.2 | Clicar no ícone | Menu abre com "Capturar e traduzir" no topo |
| 4.3 | Acionar a captura pelo menu | Fluxo completo funciona |
| 4.4 | Na janela: editar o texto reconhecido e "Retraduzir" | Retraduz sem nova captura e sem novo OCR |
| 4.5 | Copiar tradução e colar em outro aplicativo | Conteúdo correto na área de transferência |
| 4.6 | Pressionar `Esc` na janela | Fecha |
| 4.7 | Trocar o idioma de destino pelo menu, reiniciar o app | A escolha foi lembrada |
| 4.8 | Com o app rodando, executar `translate-linux --capture` em um terminal | Aciona a instância existente; nenhum segundo processo |

## 5. Sistema

| # | Passo | Esperado |
|---|---|---|
| 5.1 | `translate-linux --autostart on`, reiniciar a sessão | Ícone aparece sozinho em até 15 s do login |
| 5.2 | `translate-linux --shortcut '<Super><Shift>t'`, pressionar o atalho | Captura inicia |
| 5.3 | Registrar um atalho já usado por outro aplicativo | Avisa sobre o conflito, não o sobrescreve em silêncio |
| 5.4 | `translate-linux --autostart off`, reiniciar a sessão | Não sobe sozinho |

## 6. Privacidade

| # | Passo | Esperado |
|---|---|---|
| 6.1 | Usar o padrão offline e observar a rede (`ss -tp`) | Nenhuma conexão de saída durante uma tradução |
| 6.2 | Trocar para o provider Google nas Preferências | Diálogo de consentimento aparece antes de qualquer envio |
| 6.3 | Recusar o consentimento | Volta ao modelo local; o app segue utilizável |
| 6.4 | Capturar texto sensível e ler os logs | O conteúdo reconhecido **não** aparece em log algum |

## 7. Pacote

| # | Passo | Esperado |
|---|---|---|
| 7.1 | `sudo apt install ./translate-linux_X.Y.Z_all.deb` em máquina limpa | Dependências resolvidas, sem erro |
| 7.2 | Abrir pelo menu de aplicativos | Inicia na bandeja |
| 7.3 | `translate-linux --doctor` logo após instalar | Aponta que faltam o motor offline e os modelos, com o comando para instalá-los |
| 7.4 | `sudo apt remove translate-linux` | Remove sem erro; o autostart deixa de funcionar |

---

## Registro

| Data | Versão | Executado por | Resultado |
|---|---|---|---|
| | | | |
