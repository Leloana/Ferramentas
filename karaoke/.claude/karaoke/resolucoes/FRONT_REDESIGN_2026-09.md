# Redesign do front — "partitura antiga" (2026-09-30)

Registro do que mudou no front do karaokê e **por quê**. O estado atual das
convenções está em `docs/guides/PROJECT_GUIDE.md` (seção 4.C) e no `CLAUDE.md`
do karaokê; este arquivo é o histórico.

## Objetivo

Refazer o visual (tons pastéis, partitura antiga, cantos retos, nome só
"Karaoke"), melhorar navegação — principalmente no celular e no navegador de
TV — e simplificar os fluxos de adicionar música e montar a partida.

## Estrutura

| Antes | Depois | Motivo |
| :--- | :--- | :--- |
| `index.html` monolítico (1 100 linhas, estilos inline) | Esqueleto com `<!-- @include partials/... -->`; o `GET /` monta a página (`server/utils/html_includes.py`) | Código separado por tela sem build step; a TV continua recebendo uma resposta só. |
| `styles/main.css` (3 400 linhas, neon) | 10 arquivos por área: `tokens`, `base`, `layout`, `songs`, `game`, `mobile-mic`, `modals`, `queue`, `states`, `tv` | Manutenção; `states.css` concentra a máquina de estados por `data-*`. |
| Lucide (`vendor/lucide.min.js`, 400 KB) + emojis | `js/icons.js`: ícones próprios em SVG | Pedido do usuário (nada de emojis/ícones prontos); 400 KB a menos para a TV. A montagem `/vendor` saiu do servidor. |
| `<select>` nativo | `js/select.js` | Visual próprio; funciona com controle remoto. |
| JS com `?.`, `??`, `catch {}`, `replaceChildren` | Até ES2018 + `js/compat.js` | Navegadores de TV anteriores a ~2021 não abriam o app. |

## Visual

- Paleta em `tokens.css`: papel `#f4ecd8`, tinta sépia `#3b3024`, pastéis (azul-pó, rosa-antigo, sálvia, manteiga, lavanda, pêssego) com versões "em tinta" para texto.
- Cantos retos em tudo (`--radius: 0`), sombras de papel, textura (`assets/art/paper-texture.svg`).
- Letra: palavra cantada com **marca-texto** pastel; fundo do palco com linhas de pauta.
- Fontes: **Inter** para tudo que se lê; **Lora** só no estético (marca, títulos, rank). A Playfair Display foi trocada por ser "agressiva".
- Rank do fim de jogo como **marca de ensaio** (letra num quadrado), no lugar de um selo de lacre que parecia "feito por IA".
- Artes SVG geradas pelo Codex em `assets/art/` (símbolo clave+microfone, pauta, textura, estante vazia, notas). O logo desenhado à mão saiu errado ("Karakoke") e virou texto; o ornamento de canto foi removido a pedido.

## Navegação

- **Abas**: só "Músicas" e "Adicionar" (a fila fica dentro de "Adicionar", com o botão de adicionar). No celular viram barra fixa no rodapé.
- **TV** (`js/tv-nav.js`): setas com navegação espacial, OK aciona cards, Voltar fecha/volta (na partida pausa), Play/Pause. `?tv=1` força; `config.isTvBrowser` detecta Tizen/webOS/Android TV/Fire TV.
- **Voltar em toda tela**: botão no lobby (antes escondido), seta no título dos modais (no "Adicionar", recua um passo).
- **Rolagem**: trocar de tela, aba ou abrir modal volta ao topo.
- **Celular no lobby/partida**: a seta de voltar fica na barra do app (à esquerda de "Karaoke"), para a capa do álbum ocupar o topo.
- **Celular-microfone**: textos enxutos ("Seu apelido" → Entrar, "Na fila · Posição N"), mic desligado centralizado, letra maior ocupando o meio. Apelidos passam por `escapeHtml` antes de ir para o HTML.
- **Toasts no celular**: só erros; o aviso "Retornou à lista" saiu. Validações viraram `'error'`.

## Retorno de acerto/erro por verso

- **Carimbo de ensaio** (`js/verse-stamp.js`): a nota do verso vira "Na mosca" (85+; era "Afinado", trocado porque mede a letra, não o tom), "Quase" (70–84) ou "Fora" (<70), carimbado no canto do palco com a cor da faixa e recolhido depois de ~2 s. No multiplayer cada barra ganha um carimbinho e pisca na cor da faixa (a moldura da tela fica só no solo, porque a nota geral mistura os times).
- Moldura da tela mais grossa e na cor "em tinta" (antes quase invisível); "Último" e a nota do celular pulsam na cor da faixa.
- "Ouvi" compara sem acento (`normalizeWord`): o `\w` do JS é só ASCII e marcava "não" cantado certo como erro.

## Adicionar música

- Removidos: botão flutuante com formulário rápido, aba "Enviar arquivos", upload de instrumental local, botão "refazer música" dos cards (o alinhamento mais confiável fica para depois, no backend).
- **Busca no YouTube pelo nome**: `GET /api/youtube-search` (`utils/youtube.search_youtube`, `yt-dlp` com `extract_flat`), devolve título/canal/duração/miniatura e palpite de artista/título (`split_artist_title`, a mesma heurística do `youtube-metadata`, agora também limpando "áudio/oficial/ao vivo"). Escolher um resultado pula direto para o passo 2 já preenchido.

## Lobby e placar

- **Lobby** (`js/lobby.js`): vagas com "+", cada uma com **microfone próprio** e **time A–D**; mesmo time = dupla/trio. O modo de jogo sai das vagas (`solo`…`1v1v1v1` ou `teams`). O botão de time só aparece com 2+ cantores.
- **Capa do álbum + cantor** no lobby: `GET /api/songs/{id}/cover` (`utils/cover.py`) busca no iTunes (arte do álbum) e cai para a miniatura do YouTube; guarda `songs/<slug>/cover.jpg` (fora do git). Sem capa grava `cover.none`, exceto em falha de rede.
- **Placar** (`js/score-bars.js`): uma barra por time nas bordas; time com 2+ membros mostra a média em destaque e uma barrinha discreta por membro. Pódio por time.
- "Mic do PC" virou **"Mic do dispositivo"** e depois só **"Local"** (texto curto; pode ser o celular abrindo a tela da TV).
- Lobby: forma de pontuação saiu do quadro dos cantores (fica logo abaixo) e o botão "Conectar celular" do topo saiu — a vaga "+" já leva ao pareamento.

## Bugs antigos encontrados

- **Barras de placar multiplayer nunca apareciam**: a chamada a `resetAndShowMpScoreBars` e o `data-players="multi"` foram removidos por engano no commit `8fc8799`. Sem isso o placar solo e o "Ouvi" também ficavam visíveis em disputas.
- **Celular-microfone não conseguia pedir música**: o botão ficava atrás da tela do microfone (z-index).
- Selo "Pendente" dos cards invisível dentro dos grupos de artista; editor de letras reabria na última aba; ícones Lucide nunca eram hidratados; nome do artista inserido como HTML no cabeçalho do grupo.
- Abrir/fechar grupo de artista "travava": animação de `max-height` até 6000 px; e a grade de 2 colunas criava buracos. Agora anima a altura real e usa duas colunas independentes.

## Varredura de bugs (depois do redesign)

Três varreduras em paralelo (lógica do front, telas no navegador, servidor); cada achado foi conferido no código antes de corrigir.

- **Segurança**
  - Slug/id de música vindo do cliente saía de `songs/` (`..`, `%2E%2E`): `delete-song`, `reinstall-song`, `save-meta` (que apaga/renomeia pasta), `save-lyrics`, `get-lyrics` e o `song_manager`. Agora tudo passa por `utils/song_paths.safe_song_dir` (teste em `tests/unit/test_song_paths.py` e `test_song_routes_reject_path_traversal`).
  - Apelidos, títulos e o `?room=` iam crus para `innerHTML` na TV (pódio, toasts) e no celular. `showToast` virou texto puro; `js/html.js` (`escapeHtml`) no resto. O servidor limita o apelido a 15 caracteres imprimíveis.
- **GPU**: `upload-song` e `save-lyrics` rodavam o Whisper sem o `whisper_lock`. Cancelar um item na fase 2 soltava o lock com a thread ainda na GPU (agora a fase 2 termina). Fase 2 duplicada no mesmo tick.
- **Partida**
  - O relógio `playback_time` (100 ms) acumulava a cada partida e seguia depois do "voltar" (mandando tempo 0 e apagando o placar final dos celulares).
  - Reconexão da TV no meio da música reenviava `start_game` e zerava o placar: agora reconecta com `resume=1` e o servidor mantém a partida.
  - Duas telas na mesma sala se derrubavam em loop: o servidor fecha a antiga com o código 4001 e ela não reconecta.
  - Resultado atrasado do Whisper caía na partida seguinte (`room.game_id`).
  - Voltar a música mostrava "Fora 0%": o recálculo vem com `recalc` e só atualiza totais.
  - Celular que reconecta volta a pontuar (não sai mais de `active_players`).
  - INICIAR ficava preso em "PREPARANDO..." se a música não carregasse; "voltar" durante o início deixava o jogo abrir por cima.
- **Servidor robusto**: celular que fechava na hora travava a fila de apelidos; JSON inválido, `current_time` não numérico ou pacote de áudio com índice NaN derrubavam a TV; iteração do dict de jogadores durante `await`; exportação de MP3 bloqueava o loop (agora em thread); perfil corrompido era sobrescrito (agora é guardado à parte e a escrita é atômica) e erro no perfil impedia o `game_over`.
- **Modais**: fechar um e abrir outro no mesmo instante (picker → pareamento, passo 3 → opções) quebrava o histórico e o "Fechar" saía do app. Esc/Voltar da TV/botão do navegador recuam um passo no "Adicionar" antes de fechar. Tab fica preso no modal aberto. QR sem internet mostra o link.
- Textos explicativos que sobraram foram encurtados; o modal morto `lyrics-review` saiu.

## Rodadas seguintes (mesmo dia)

- **Recursos de festa**: cartão 4:5 para print no fim de jogo (TV e celular), perfis e ranking ("Cantores" na TV, aba "Perfil" no celular), recorde pessoal e melhor da sala, ouvir a própria apresentação, revezar versos e sortear, fila da noite ("quero cantar") com próxima automática em 10 s, contagem 3-2-1 depois do solo, voz guia, tela sempre acesa, painel de saúde (clique no "Online").
- **Afinação**: "tom X%" por verso (YIN contra a melodia do vocal separado), informativo; o carimbo "Afinado" virou "Na mosca" porque mede a letra.
- **Capas**: candidatos iTunes + Deezer + YouTube com nota por artista/título (tributo, karaokê, ao vivo e coletânea perdem — "A Wolf at the Door" saía com a capa de um tributo); "Trocar capa" no lobby.
- **Lista**: ouvir 12 s do refrão (verso mais repetido); selo "Revisar" quando a sincronia da letra ficou fraca.
- **Lobby**: pontuação abaixo do quadro dos cantores, sem o botão "Conectar celular" do topo (a vaga "+" já pareia); "Mic do dispositivo" virou "Local".
- **Mutex de GPU**: gerando letra, o INICIAR mostra "GPU ocupada" e o servidor recusa `start_game`.

## Ferramentas e testes

- `tools/preview_front.py`: serve o front sem GPU/FastAPI, com dados de exemplo (usa busca real e capas se houver `yt-dlp`).
- Testes novos: `tests/unit/test_html_includes.py`, `tests/unit/test_cover.py`; `tests/flow/test_http_api.py` atualizado (estáticos sem `/vendor`, index montado).

## Pendências

- Checklist completo em `docs/guides/TODO_SERVIDOR_FINAL.md` ("Validar no servidor").
- Testar num navegador de TV de verdade e no iPhone.
- Alinhamento de letras mais confiável: feito (PRO linha por linha + nota de qualidade), falta validar com áudio real. Destacar no editor as linhas fracas (os dados já estão em `alignment_quality.lines`).
- Testes das telas: `tests/ui/test_screens.py` (Playwright).
