# Métricas para validar as partituras geradas

Pesquisa de 2026-11-10 (subagente com busca na web; links e licenças conferidos no GitHub;
o que veio de memória e não foi reconferido na fonte está marcado como *não verificado*).
Tudo aqui é algoritmo ou modelo estatístico clássico — nada de LLM na validação, como pedido.
Uso pretendido: rodar antes/depois de cada regra (`validar_biblioteca.py`) e por nível.

## Prioridade (custo × benefício)

1. **Fidelidade à gravação: Qmax e desvio do caminho de DTW** — chroma da prévia contra o
   original; recorrência cruzada (Serrà et al. 2009) com `librosa.segment.cross_similarity`
   + `librosa.sequence.rqa`; DTW com `librosa.sequence.dtw` e o desvio padrão dos resíduos
   da regressão do caminho (Warp Path Deviation, do Etude). Referência do AMT-APC
   (arXiv 2409.14086): distância humana 0,038; AMT-APC 0,035; PiCoGen2 0,054; Pop2Piano 0,090.
   Introdução/final gerados não existem no original: mascarar.
2. **Melodia: MCA e F1 de notas via `mir_eval`** — `mir_eval.melody.raw_chroma_accuracy`
   (f0 da voz × linha superior da direita; Pop2Piano, arXiv 2211.00895; covers humanos
   ~0,35–0,40, e MCA alta não garante cover melhor) e `mir_eval.transcription` (onset 50 ms)
   no lugar da "concordância" caseira, pra comparar com a literatura.
3. **Tensão tonal (spiral array, Herremans & Chew, TENOR 2016)** — cloud diameter
   (dissonância), cloud momentum (mudança harmônica), tensile strain (distância do tom),
   em `partitura.musicanalysis.estimate_tonaltension` (CPJKU/partitura, Apache-2.0, ativo).
   Mais perfis de tonalidade em janela (`music21.analysis.discrete`, Krumhansl/Temperley)
   comparados com a tonalidade do áudio. Pega acorde errado e modulação espúria; confere
   que introdução/final terminam com tensão baixa.
4. **Dificuldade por mão (descritores do RubricNet, Ramoneda et al. 2024, arXiv 2408.00473,
   MIT)** — entropia de alturas, extensão, altura média, taxa de deslocamento da mão, IOI
   médio, complexidade Lempel-Ziv dos conjuntos de notas. Teste: fácil < médio < difícil.
5. **Dissonância sensorial por evento (Plomp-Levelt / Sethares 1993)** — pacote `dissonant`
   (MIT) com harmônicos sintéticos; e "low interval limit" na esquerda (terças abaixo de
   ~Dó3 embolam). Defeito mais audível de acompanhamento gerado.
6. **Segundo modelo de dedilhado** — HMM de Nakamura et al. (arXiv 1904.10237, dataset PIG;
   licença do código não confirmada) ou ArGNN do Ramoneda (github.com/PRamoneda/
   Automatic-Piano-Fingering, MIT, pré-treinado). NLL por nota como "dificuldade de
   dedilhado"; base pra formulação de Nakamura & Yoshii 2018 (arXiv 1808.05006):
   fidelidade máxima sob teto de dificuldade por nível.
7. **Ritmo** — sincopação de Longuet-Higgins & Lee (reimplementar, ~30 linhas; fórmula de
   memória), RGC e IPE do Etude (arXiv 2509.16522, código MIT com `evaluate.py`),
   `muspy.metrics.groove_consistency` (MIT). Detecta quantização ruim e acompanhamento sem padrão.
8. **Distribuição parecida com covers humanos (MGEval, Yang & Lerch 2020)** — features por
   peça + sobreposição (OA) e KL entre conjuntos; reimplementar (repo sem licença). Depende
   de montar um corpus de referência (ex.: parte do POP909). Depois: IDyOM (surpresa
   melódica; Lisp GPL ou IDyOMpy sem licença).

## Outras referências úteis

- Dificuldade: Ramoneda et al. 2024 (CIPI, código AGPL), versão por imagem (PDF-difficulty),
  Sébastien et al. ISMIR 2012 (7 critérios do MusicXML), Chiu & Chen 2012 (não verificado).
- Harmonia: Tonal Pitch Space de Lerdahl (TPSD em github.com/andreamust/TPSD, MIT; fórmula
  de memória), Tonnetz (`librosa.feature.tonnetz`) da prévia × original, condução de vozes
  (`music21.voiceLeading`; distância de Tymoczko).
- Melodia: Narmour/Schellenberg (proximidade e reversão; sem pacote, trivial),
  `melody-features` (Apache-2.0, 200+ features).
- Avaliação geral: Lerch et al. 2025, "Survey on the Evaluation of Generative Models in Music"
  (arXiv 2506.05104). Fréchet Music Distance usa encoder neural (CLaMP) — fica de fora.
- Legibilidade: não há métrica estabelecida. Heurística própria: linhas suplementares por
  nota, acidentes por compasso, ligaduras atravessando tempo, densidade por sistema e
  colisões contadas no SVG do Verovio.

## Lacunas

Não achados: código Python de Narmour, métrica publicada de legibilidade, download atual
do PIG. Não confirmados: licença do HMM do Nakamura, critérios exatos de Sébastien e de
Chiu & Chen; fórmulas de Toussaint, LHL, Lerdahl e lista do MGEval (de memória).
