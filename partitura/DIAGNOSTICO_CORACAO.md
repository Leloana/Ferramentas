# Notas estranhas em Para Machucar Meu Coração

**Atualização:** após este diagnóstico, a proteção foi implementada e a música foi
regenerada nos três níveis. No Médio, os três casos foram filtrados; o Difícil mantém
mais ornamentos breves. Ver seção 13 do HANDOFF.md. O texto abaixo registra a investigação anterior.

Verificação de 2026-11-10 dos três exemplos indicados pelo usuário. Os exemplos
correspondem às notas do nível Médio de Acordes/Híbrido AMT; o Difícil também foi conferido.
Versão/nível não foram confirmados pelo usuário durante a análise.

Método: localizar sílabas e notas no MusicXML, reconstruir o mapa de batidas da
gravação original e comparar CREPE e pYIN na voz isolada. Ambos são estimadores;
concordância não substitui revisão auditiva ou uma partitura de referência humana.
Não houve alteração das partituras nesta verificação.

| Trecho | Evidência | Diagnóstico e edição recomendada |
|---|---|---|
| “meu violão”, Sol♭4 entre Fá4 e Sol4 | Original ~31,4 s e repetição ~75 s. A voz sobe de Fá3 a Sol3, atravessando altura intermediária brevemente. CREPE estima ~54,39 MIDI, enquanto pYIN já aponta ~54,69 (Sol3); depois ambos convergem para Sol3. | O Sol♭ escrito é uma discretização de transição vocal, não evidência de uma nota estável. Para piano, remover o degrau intermediário e preservar Fá–Sol é uma edição conservadora; manter como ornamento só se desejada fidelidade ao gesto vocal. |
| “nosso lar des…”, Sol♭3 grave | Segunda passagem, original ~62,3–62,5 s, beat 138,5 da partitura. Ambos captam uma região grave perto de Fá♯2 no ataque; há baixa periodicidade em parte do trecho e Ré3 estável antes/depois. Na primeira passagem também há registros graves instáveis no ataque. | Provável extração de ataque/voz crepitante ou vazamento instrumental, promovida a nota melódica pelo filtro. Não há base para tratá-la como Sol♭ melódico sustentado. Descartar a excursão grave e apoiar a entrada na nota vocal estável seguinte (Ré), com revisão do tempo da sílaba. A origem exata do som grave não foi identificada. |
| “mo-ro-nou”, Lá natural antes de Si♭ | Primeira passagem, original ~22,23 s: CREPE ~45,10 e pYIN ~45,49 (Lá2), logo seguidos por Si♭2 estável. Na repetição, ~65,7–65,9 s, a subida passa por alturas intermediárias antes do Si♭. | O Lá aparece no gesto da gravação, mas muito brevemente. No Médio vira colcheia (~233 ms a 129 BPM), dando peso excessivo à passagem. Não corrigir para Lá♭. Preferir encurtar/omitir o intermediário no arranjo simples; no Difícil pode ficar como ornamento breve. |

O CREPE original aceita segmentos de 60 ms. A grade do Médio impõe duração mínima
de aproximadamente 233 ms nesta música, e o legato pode alongar ainda mais um
segmento. Isso explica por que uma transição aceitável no canto pode soar como nota
errada ou excessivamente marcada no piano. Não é necessário afinar globalmente o
SoundFont nem forçar todas as notas à escala.

Dados por janela em `trabalho/diagnostico_coracao.json`.
Scripts: `diagnosticar_coracao.py` e `diagnosticar_coracao_audio.py`.
