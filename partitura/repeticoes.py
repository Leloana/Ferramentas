"""Repetições do arranjo: achar os compassos que são "o mesmo" e escrever todos com o mesmo padrão.

O AMT-APC transcreve cada passagem de um jeito: o refrão que volta três vezes sai com três
escritas um pouco diferentes (Ode fácil: 14 de 99 compassos iguais a algum anterior). Pra quem
estuda, a mesma música deveria ter as mesmas notas. Sem LLM, só contas:

1. Impressão de cada compasso: quanto soa cada classe de altura em cada metade do compasso, mão
   direita e esquerda separadas (peso = duração), normalizada. Similaridade = cosseno.
2. Repetição = diagonal da matriz de autossimilaridade: o compasso i parece o i+L por pelo menos
   `min_compassos` seguidos (média móvel acima de `limiar`).
3. Os pares (i, i+L) dessas diagonais formam grupos de compassos equivalentes (união-busca).
4. Em cada grupo, o padrão é a versão real que mais concorda com a votação entre as versões
   (consenso, como na letra por repetição de McVicar, Ellis e Goto, 2014), desempate pela mais
   simples de ler; as demais recebem as notas dela. Compasso cuja emenda obrigaria a mão direita a
   um salto sem tempo fica como estava.

Eventos do gerar.py: (offset_em_tempos, duração, [midis], *resto); compasso de 4 tempos.
"""
from __future__ import annotations

import numpy as np

EPS = 1e-6


def impressoes(md, me, n, compasso=4.0):
    """[n, 48]: classes de altura por metade do compasso, direita (24) e esquerda (24)."""
    f = np.zeros((n, 48))
    for lado, ev in ((0, md), (1, me)):
        for off, dur, ps, *_ in ev:
            b = int(off // compasso + EPS)
            if not 0 <= b < n or not ps:
                continue
            metade = 1 if off - b * compasso >= compasso / 2 - EPS else 0
            for p in ps:
                f[b, 24 * lado + 12 * metade + p % 12] += dur
    for a in (slice(0, 24), slice(24, 48)):   # cada mão pesa igual (o baixo segurado não domina)
        norma = np.linalg.norm(f[:, a], axis=1, keepdims=True)
        f[:, a] /= np.where(norma > 0, norma, 1)
    norma = np.linalg.norm(f, axis=1, keepdims=True)
    return f / np.where(norma > 0, norma, 1)


def diagonais(sim, min_compassos=4, limiar=.85, min_lag=2):
    """[(i, j, k)]: compassos i..i+k-1 repetem em j..j+k-1 (j = i + L)."""
    n = len(sim)
    achados = []
    for lag in range(min_lag, n - min_compassos + 1):
        d = np.array([sim[i, i + lag] for i in range(n - lag)])
        bom = d >= limiar
        i = 0
        while i < len(bom):
            if not bom[i]:
                i += 1
                continue
            k = i
            while k < len(bom) and bom[k]:
                k += 1
            if k - i >= min_compassos:
                achados.append((i, i + lag, k - i))
            i = k
    return achados


def grupos(n, achados):
    """Lista de grupos (listas ordenadas de compassos) com mais de um compasso."""
    pai = list(range(n))

    def raiz(a):
        while pai[a] != a:
            pai[a] = pai[pai[a]]
            a = pai[a]
        return a
    for i, j, k in achados:
        for t in range(k):
            a, b = raiz(i + t), raiz(j + t)
            if a != b:
                pai[max(a, b)] = min(a, b)
    por = {}
    for b in range(n):
        por.setdefault(raiz(b), []).append(b)
    return [g for g in por.values() if len(g) > 1]


def analisar(md, me, compasso=4.0, **kw):
    """(grupos, impressões, matriz de similaridade)."""
    todos = [e for e in md + me if e[2]]
    if not todos:
        return [], None, None
    n = int(max(o for o, *_ in todos) // compasso) + 1
    f = impressoes(md, me, n, compasso)
    sim = f @ f.T
    return grupos(n, diagonais(sim, **kw)), f, sim


# ------------------------------------------------------------------ pelo áudio + confirmação pelas notas

def lags_do_audio(audio, bt, sr=22050, hop=512, contexto=8, k=8, min_batidas=32, vizinhanca=2):
    """Distâncias (em batidas) em que a música se repete, pelo áudio: cromagrama por batida sem a
    média da música, `contexto` batidas empilhadas, recorrência por vizinhos mais próximos e realce
    de diagonal (receita padrão de análise de estrutura). Devolve [(lag, batidas cobertas)] dos picos
    (máximo local em ±`vizinhanca`) que cobrem pelo menos `min_batidas`, mais forte primeiro."""
    import librosa
    y, sr = librosa.load(str(audio), sr=sr, mono=True)
    bt = np.asarray(bt, dtype=float)
    validas = (bt >= 0) & (bt < len(y) / sr)
    c = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop)
    cb = librosa.util.sync(c, librosa.time_to_frames(bt[validas], sr=sr, hop_length=hop), aggregate=np.median)
    cb = cb - cb.mean(axis=1, keepdims=True)
    f = librosa.feature.stack_memory(cb, n_steps=contexto, mode="edge")
    R = librosa.segment.recurrence_matrix(f, k=k, width=contexto, mode="affinity", sym=True)
    R = librosa.segment.path_enhance(R, contexto + 1)
    n = R.shape[0]
    corte = np.percentile(R[R > 0], 50) if (R > 0).any() else 0
    forca = {}
    for lag in range(contexto, n - 16):
        bom = np.diagonal(R, lag) > corte
        tot, i = 0, 0
        while i < len(bom):
            if not bom[i]:
                i += 1
                continue
            j = i
            while j < len(bom) and bom[j]:
                j += 1
            if j - i >= 16:
                tot += j - i
            i = j
        forca[lag] = tot
    picos = [(lag, v) for lag, v in forca.items() if v >= min_batidas
             and all(v >= forca.get(lag + d, 0) for d in range(-vizinhanca, vizinhanca + 1))]
    return sorted(picos, key=lambda x: -x[1])


def achados_confirmados(sim, lags_compasso, limiar=.6, min_compassos=4):
    """[(i, j, k)] nos lags (em compassos) que o áudio indicou, com as notas confirmando: compassos i..i+k-1
    parecidos (cosseno >= limiar) com j..j+k-1, por pelo menos `min_compassos` seguidos."""
    n = len(sim)
    achados = []
    for L in lags_compasso:
        if L <= 0 or L >= n:
            continue
        bom = np.array([sim[i, i + L] >= limiar for i in range(n - L)])
        i = 0
        while i < len(bom):
            if not bom[i]:
                i += 1
                continue
            j = i
            while j < len(bom) and bom[j]:
                j += 1
            if j - i >= min_compassos:
                achados.append((i, i + L, j - i))
            i = j
    return achados


def unificar(md, me, gs, sim, compasso=4.0, bpm=None, nivel="medio", max_salto=7):
    """Cada grupo de compassos equivalentes passa a ter as mesmas notas: a versão real que mais
    concorda com a votação entre as versões (acorde por ataque), mão por mão;
    desempate pela mais simples de ler. Montar o compasso acorde a acorde de versões diferentes criava
    saltos que nenhuma versão tinha (Fuyu médio). Nota que vem de antes e invade um
    compasso trocado é cortada na barra; nota que passa do compasso é cortada no próximo ataque da
    mesma mão. Devolve (md, me, compassos reescritos)."""
    if not gs:
        return md, me, 0

    def por_compasso(ev):
        pc = {}
        for e in ev:
            pc.setdefault(int(e[0] // compasso + EPS), []).append(e)
        return pc

    from tocavel import suplementares_sol

    def assinatura(inst):   # acordes por ataque (a 1/4 de tempo)
        por = {}
        for off, dur, ps, *_ in inst:
            if ps:
                por.setdefault(round(off * 4) / 4, set()).update(ps)
        return {(a, tuple(sorted(ps))) for a, ps in por.items()}

    def ataques(ev, b):
        return [e for e in ev if int(e[0] // compasso + EPS) == b]

    def custo_ler(b):   # a versão mais simples de ler: linhas suplementares + um pouco por nota
        notas = [p for e in ataques(md, b) + ataques(me, b) for p in e[2]]
        return sum(suplementares_sol(p) for e in ataques(md, b) for p in e[2]) + .05 * len(notas)
    # desempate pela versão mais simples (o medoide às vezes é a que tem o enfeite agudo, e copiar
    # ele dobrava as notas acima de Lá5 na Ode)

    def padrao(pc, g):
        """Uma versão real inteira (as passagens dentro do compasso existiram de verdade): a que mais
        concorda com a votação (soma dos votos dos seus acordes), desempate pela mais simples."""
        rel = [[(e[0] - b * compasso, *e[1:]) for e in pc.get(b, [])] for b in g]
        votos = {}
        for inst in rel:
            for chave in assinatura(inst):
                votos[chave] = votos.get(chave, 0) + 1
        def nota(k):
            return (sum(votos[c] for c in assinatura(rel[k])) - PESO_LEITURA * custo_ler(g[k]), -g[k])
        return rel[max(range(len(g)), key=nota)]

    # compasso reescrito que obrigaria a mão direita a um salto sem tempo (emenda com o vizinho que
    # ficou original) não é reescrito: modelo do maos.PERFIL (base + distância/velocidade do nível)
    pular = set()
    if bpm:
        from maos import PERFIL
        perf = PERFIL[nivel]
        pc_md = por_compasso(md)
        trocados = {b for g in gs for b in g}
        padroes = {b: [(off + b * compasso, *r) for off, *r in padrao(pc_md, g)] for g in gs for b in g}

        def chega(e1, e2):
            if not e1 or not e2 or not e1[2] or not e2[2]:
                return True
            salto = abs(max(e2[2]) - max(e1[2]))
            tempo = (e2[0] - e1[0]) * 60 / bpm
            return salto <= max_salto or tempo >= perf["base"] + salto / perf["vel"] - EPS
        for b in sorted(trocados):
            novo_b = padroes[b]
            if not novo_b:
                continue
            ant = None if b - 1 in trocados else (pc_md.get(b - 1) or [None])[-1]
            seg = None if b + 1 in trocados else (pc_md.get(b + 1) or [None])[0]
            if not chega(ant, novo_b[0]) or not chega(novo_b[-1], seg):
                pular.add(b)

    def refazer(ev):
        pc = por_compasso(ev)
        novo = {}
        for g in gs:
            c = padrao(pc, g)
            for b in g:
                if b not in pular:
                    novo[b] = [(off + b * compasso, *r) for off, *r in c]
        saida = []
        for b, lista in pc.items():
            if b in novo:
                continue
            for e in lista:
                fim = e[0] + e[1]
                prox = (int(e[0] // compasso + EPS) + 1) * compasso
                if fim > prox + EPS and int(prox // compasso + EPS) in novo:   # invade compasso reescrito
                    e = (e[0], prox - e[0], *e[2:])
                saida.append(e)
        for lista in novo.values():
            saida += lista
        saida.sort(key=lambda e: e[0])
        for i in range(len(saida) - 1):           # sem sobreposição dentro da mão
            if saida[i][0] + saida[i][1] > saida[i + 1][0] + EPS and saida[i + 1][0] > saida[i][0] + EPS:
                saida[i] = (saida[i][0], saida[i + 1][0] - saida[i][0], *saida[i][2:])
        return saida
    return refazer(md), refazer(me), sum(len(g) for g in gs) - len(pular)


_CACHE_LAGS = {}
PESO_LEITURA = 2.0   # (varredura 0,5–4 nas 5 músicas: 2 é o único sem piora de leitura) quanto cada linha suplementar da versão pesa contra um voto na escolha do padrão


def apertar(gs, sim, limiar=.75):
    """Tira do grupo o compasso que não se parece com o medoide: a união-busca encadeia (1~3~5...) e
    juntaria compassos que só se parecem com o vizinho do vizinho."""
    saida = []
    for g in gs:
        medoide = max(g, key=lambda b: sum(sim[b, o] for o in g if o != b))
        fica = [b for b in g if b == medoide or sim[b, medoide] >= limiar]
        if len(fica) > 1:
            saida.append(fica)
    return saida


def padronizar(md, me, audio, bt, limiar=.6, min_compassos=4, compasso=4.0, min_lag=4, limiar_grupo=.75, bpm=None):
    """Modo leve: repetições pelo áudio (lag múltiplo do compasso), confirmadas pelas notas, escritas
    com o mesmo padrão (consenso). Devolve (md, me, registro)."""
    chave = str(audio)
    if chave not in _CACHE_LAGS:
        try:
            _CACHE_LAGS[chave] = lags_do_audio(audio, bt)
        except Exception as e:   # áudio ruim/curto demais: segue sem padronizar, não derruba a geração
            print(f"[repeticoes] análise do áudio falhou ({type(e).__name__}: {e}); segue sem padronizar")
            _CACHE_LAGS[chave] = []
    picos = _CACHE_LAGS[chave]
    # lag em batidas -> em compassos (a fase do compasso não muda a distância)
    lags = sorted({int(round(lag / compasso)) for lag, _ in picos
                   if abs(lag / compasso - round(lag / compasso)) < .3 and round(lag / compasso) >= min_lag})
    todos = [e for e in md + me if e[2]]
    if not todos or not lags:
        return md, me, dict(lags_compasso=lags, grupos=0, compassos=0)
    n = int(max(o for o, *_ in todos) // compasso) + 1
    f = impressoes(md, me, n, compasso)
    sim = f @ f.T
    gs = apertar(grupos(n, achados_confirmados(sim, lags, limiar, min_compassos)), sim, limiar_grupo)
    md2, me2, k = unificar(md, me, gs, sim, compasso, bpm=bpm)
    return md2, me2, dict(lags_compasso=lags, grupos=len(gs), compassos=k)
