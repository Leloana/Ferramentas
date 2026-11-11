"""Níveis de dificuldade da partitura: fácil, médio, difícil.

| | fácil | médio | difícil |
|---|---|---|---|
| ritmo (grade) | semínima | colcheia | semicolcheia |
| mão esquerda (Acordes) | só o baixo, segurado | baixo + 3ª e 7ª | baixo + acorde em ritmo |
| Pop2Piano / Híbrido | 1 nota por mão | até 2 (esq.) / 3 (dir.) | completo |
| cifra | só tríades | completa | completa |
| tom | transposto pra tom sem acidentes | original | original |
"""
from __future__ import annotations

import numpy as np

NIVEIS = ("facil", "medio", "dificil")
NOME = {"facil": "Facil", "medio": "Medio", "dificil": "Dificil"}
GRADE = {"facil": 1, "medio": 2, "dificil": 4}  # subdivisões por tempo

# tétrade -> tríade (pra cifra fácil)
TRIADE = {"maj": "maj", "6": "maj", "7": "maj", "maj7": "maj",
          "m": "m", "m6": "m", "m7": "m", "m7b5": "m", "dim7": "m"}


def cifras_do_nivel(cifras, nivel):
    if nivel != "facil":
        return cifras
    saida, anterior = [], None
    for off, r, tipo in cifras:
        t = TRIADE.get(tipo, tipo)
        if (r, t) != anterior:
            saida.append((off, r, t))
        anterior = (r, t)
    return saida


def mao_esquerda_acordes(acs, nivel, fim, tipos, janela=2):
    """Mão esquerda gerada a partir dos acordes detectados."""
    ev = []
    blocos = [(j, r, t) for j, r, t, _ in acs if r is not None and j <= fim]
    if nivel == "facil":
        # só a fundamental (C3..B3), segurada enquanto o acorde não muda (até 4 tempos)
        i = 0
        while i < len(blocos):
            j, r, t = blocos[i]
            k = i + 1
            while k < len(blocos) and blocos[k][1] == r and blocos[k][0] == blocos[k - 1][0] + janela:
                k += 1
            dur = blocos[k - 1][0] + janela - j
            pos = j
            while dur > 0:
                d = min(4, dur)
                ev.append((pos, d, [48 + r % 12 if r % 12 < 8 else 36 + r % 12]))
                pos += d
                dur -= d
            i = k
        return ev
    for j, r, t in blocos:
        ints = tipos[t][0]
        raiz = 40 + (r - 4) % 12
        tons = [(r + ints[1]) % 12, (r + ints[-1]) % 12] if len(ints) == 4 else [(r + x) % 12 for x in ints[1:]]
        sup = sorted(52 + (pc - 4) % 12 for pc in tons)
        if nivel == "medio":
            # acorde fechado dentro de 1 oitava (baixo entre G2 e F#3 + 3ª/7ª logo acima): a análise mostrou
            # 64% de aberturas > oitava no voicing antigo (baixo e 3ª/7ª em oitavas separadas)
            baixo = 43 + (r - 7) % 12
            ev.append((j, janela, [baixo] + sorted(baixo + (pc - baixo) % 12 for pc in tons)))
        else:  # difícil: baixo no 1, acorde no 2 (padrão de "comping")
            ev.append((j, 1, [raiz]))
            ev.append((j + 1, janela - 1, sup + ([raiz + 19] if len(ints) == 3 else [])))
    return ev


# nota mais grave da esquerda no médio/difícil (MIDI). 28 = Mi1, quatro linhas abaixo da clave de fá.
GRAVE_MINIMO = 28


def reduzir_mao(ev, nivel, mao):
    """Simplifica eventos polifônicos (Pop2Piano): limita notas por acorde.
    Mão direita guarda as de cima (melodia), esquerda as de baixo (baixo)."""
    maximo = 4 if nivel == "dificil" else (1 if nivel == "facil" else (3 if mao == "direita" else 2))
    saida = []
    for off, dur, ps, *resto in ev:
        ps = sorted(ps)
        if len(ps) > maximo:
            if maximo == 1:
                ps = [ps[-1]] if mao == "direita" else [ps[0]]
            elif mao == "direita":
                ps = ps[-maximo:]
            else:
                ps = [ps[0], ps[-1]]
        # Conservar classes de altura e a voz externa, mudando apenas oitavas.
        # Selecionar os extremos, sozinho, mantinha justamente a maior abertura.
        if ps:
            ancora = ps[-1] if mao == "direita" else ps[0]
            ps = sorted({ancora - (ancora-p) % 12 if mao == "direita"
                         else ancora + (p-ancora) % 12 for p in ps})
        saida.append((off, dur, ps, *resto))
    return suavizar_baixo(saida, nivel) if mao == "esquerda" else saida


def suavizar_baixo(ev, nivel):
    """Escolhe oitavas por programação dinâmica, com custo para saltos rápidos.

    Mantém ritmo e classes de altura. A mão direita nunca é transposta aqui.
    Pausas longas permitem deslocamentos maiores; penaliza mudanças de registro.
    """
    if not ev:
        return []
    lo, hi = (36, 60) if nivel == "facil" else (GRAVE_MINIMO, 60)
    candidatos = []
    for _, _, ps, *_ in ev:
        opts = [[p+k for p in ps] for k in range(-48, 49, 12)
                if ps and lo <= min(ps)+k and max(ps)+k <= hi]
        candidatos.append(opts or [list(ps)])
    custos, caminhos = [], []
    for i, opts in enumerate(candidatos):
        local, back = [], []
        for ps in opts:
            ancora = min(ps) if ps else 48
            origem = min(ev[i][2]) if ev[i][2] else 48
            registro = .025 * (ancora-origem)**2
            if i == 0:
                local.append(registro)
                back.append(0)
                continue
            # Tempo desde o ataque anterior: ligações longas também dão tempo
            # para preparar o movimento. Limite cresce até duas oitavas.
            tempo = max(0, ev[i][0]-ev[i-1][0])
            limite = min(24, (5 if nivel == 'facil' else 7) + 2*tempo)
            escolhas = []
            for j, ant in enumerate(candidatos[i-1]):
                salto = abs(ancora-min(ant)) if ant else 0
                escolhas.append(custos[i-1][j] + max(0, salto-limite)**2 + .04*salto)
            j = int(np.argmin(escolhas))
            local.append(registro+escolhas[j])
            back.append(j)
        custos.append(local)
        caminhos.append(back)
    j = int(np.argmin(custos[-1]))
    resultado = []
    for i in range(len(ev)-1, -1, -1):
        off, dur, _, *resto = ev[i]
        resultado.append((off, dur, candidatos[i][j], *resto))
        j = caminhos[i][j]
    return resultado[::-1]


def fechar_acordes(ev, mao='esquerda'):
    """Fecha a abertura sem reduzir o número de classes de altura."""
    saida = []
    for o,d,ps,*resto in ev:
        ancora = (max(ps) if mao == 'direita' else min(ps)) if ps else 48
        notas = sorted({ancora-(ancora-p)%12 if mao == 'direita'
                        else ancora+(p-ancora)%12 for p in ps})
        saida.append((o,d,notas,*resto))
    return saida


def completar_instrumentais(melodia, instrumental, passo, bloqueios=()):
    """Usa a direita da IA em lacunas de >= quatro tempos sem melodia/palavras.

    Recorta notas nas bordas, sem sobrepor a voz nem associar letra ao instrumental.
    Os bloqueios vêm também das palavras do Whisper, protegendo voz não detectada.
    """
    if not instrumental or not melodia:
        return list(melodia)
    fim = max(o+d for o,d,*_ in melodia+instrumental)
    ocupados = [(o, o+d) for o,d,*_ in melodia]
    ocupados += [(np.floor(a/passo)*passo, np.ceil(b/passo)*passo) for a,b in bloqueios]
    unidos = []
    for a,b in sorted(ocupados):
        if unidos and a <= unidos[-1][1]+1e-7:
            unidos[-1][1] = max(b,unidos[-1][1])
        else:
            unidos.append([a,b])
    lacunas, inicio = [], min(0, min(o for o, *_ in instrumental))
    for a,b in unidos+[[fim,fim]]:
        if a-inicio >= 4:
            lacunas.append((inicio,a))
        inicio = max(inicio,b)
    extras = []
    for o,d,ps,*_ in instrumental:
        for a,b in lacunas:
            ini, fin = max(o,a), min(o+d,b)
            if fin-ini >= passo-1e-7:
                extras.append((ini, fin-ini, ps))
    return sorted(list(melodia)+extras, key=lambda e:e[0])


def simplificar_passagens(notas, palavras=()):
    """No Fácil, suaviza ornamento cromático curto entre duas notas iguais.

    Não altera ataque de palavra, notas longas, nem cromatismos sem esse contexto.
    Usa os segundos originais, antes da quantização, e mantém o ritmo.
    """
    out=list(notas)
    for i in range(1,len(notas)-1):
        a,b,p=notas[i]
        ant,seg=notas[i-1],notas[i+1]
        if (b-a<=.18 and ant[2]==seg[2] and abs(p-ant[2])==1
            and a-ant[1]<=.12 and seg[0]-b<=.12
            and ant[1]-ant[0]>=.2 and seg[1]-seg[0]>=.2
            and not any(a-.03<=ini<b for ini,_,_ in palavras)):
            out[i]=(a,b,ant[2])
    return out


def transpor_facil(md_ev, me_ev, cifras):
    """Semitons pra levar a melhor armadura única da música pra zero acidentes (Dó maior / Lá menor).
    Armadura com s sustenidos tem tônica 7·s; transpor k soma 7·k ⇒ k ≡ -7·s (mod 12)."""
    import gerar
    eventos = [(d, ps) for _, d, ps, *_ in md_ev] + [(0.3 * d, ps) for _, d, ps, *_ in me_ev]
    s = gerar.escolher_armadura(eventos)
    k = (-7 * s) % 12
    if k > 6:
        k -= 12
    return md_ev, me_ev, cifras, k


def escala_da_armadura(sustenidos):
    """Classes de altura da escala maior da armadura (a relativa menor tem as mesmas)."""
    t = (7 * sustenidos) % 12
    return {(t + k) % 12 for k in (0, 2, 4, 5, 7, 9, 11)}


def notas_do_acorde(acs, tipos, pos, janela=2):
    """Classes de altura do acorde detectado na posição (tempos), ou set() sem acorde."""
    for j, r, t, *_ in reversed(acs):
        if j <= pos + 1e-6:
            if r is None or pos >= j + janela:
                return set()
            return {(r + i) % 12 for i in tipos[t][0]}
    return set()


def alinhar_cromaticas(notas, palavras, pos, acs, tipos, escala, max_tempos=1.0):
    """No Fácil, nota curta fora da escala e fora do acorde vai pro grau vizinho da escala.

    Fica como está: nota com 1 tempo ou mais, nota do acorde do momento (inclui a sensível
    do menor, que é nota do acorde de dominante), ataque de palavra e nota sem grau vizinho
    na escala a um semitom. Entre os dois vizinhos, prefere nota do acorde, depois a nota
    igual à anterior/seguinte, depois a mais perto da média das vizinhas.
    notas: (ini_s, fim_s, midi); pos: segundos -> tempos. Devolve (notas, mudanças).
    """
    saida, mudancas = list(notas), []
    for i, (a, b, p) in enumerate(notas):
        if p % 12 in escala:
            continue
        if pos(b) - pos(a) >= max_tempos:
            continue
        acorde = notas_do_acorde(acs, tipos, pos(a))
        if p % 12 in acorde:
            continue
        if any(ini - .03 <= a < fim for ini, fim, _ in palavras):
            continue
        cands = [q for q in (p - 1, p + 1) if q % 12 in escala]
        if not cands:
            continue
        viz = [notas[k][2] for k in (i - 1, i + 1) if 0 <= k < len(notas)]
        media = sum(viz) / len(viz) if viz else p

        def chave(q):
            return (q % 12 not in acorde, q not in viz, abs(q - media))
        novo = min(cands, key=chave)
        saida[i] = (a, b, novo)
        mudancas.append(dict(ini=round(a, 3), antes=p, depois=novo,
                             motivo="acorde" if novo % 12 in acorde else "escala"))
    return saida, mudancas
