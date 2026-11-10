"""Proteções locais da voz antes da quantização, sem forçar notas à escala."""
import numpy as np


def qualidade_segmento(midi, periodicidade, inicio, fim, passo_s=.01):
    """Distingue uma altura sustentada da passagem rápida por um semitom."""
    valores=np.asarray(midi[inicio:fim])
    per=np.asarray(periodicidade[inicio:fim])
    if not len(valores):
        return dict(periodicidade=0.,apoio=0.,patamar_s=0.)
    alvo=round(float(np.median(valores)))
    variacao=np.abs(np.gradient(np.asarray(midi)))[inicio:fim] if len(midi)>1 else np.zeros(len(valores))
    perto=np.abs(valores-alvo)<=.30
    estavel=perto & (per>=.70) & (variacao<=.08)
    maior=atual=0
    for ok in estavel:
        atual=atual+1 if ok else 0
        maior=max(maior,atual)
    return dict(periodicidade=float(np.median(per)),apoio=float(np.mean(perto)),
                patamar_s=maior*passo_s)


def proteger_melodia(notas, grade, nivel, palavras=(), diagnostico=None):
    """Retira excursões instáveis e ornamentos que a grade exageraria.

    Exige evidência do detector: sem diagnóstico, não adivinha notas erradas.
    Conserva notas longas/cromáticas sustentadas e a separação de sílabas.
    Nunca troca uma nota por outra apenas por estar fora da escala/acorde.
    """
    if len(notas)<3 or not diagnostico:
        return list(notas),[]
    qualidades=diagnostico.get('notas',[])
    if len(qualidades)!=len(notas):
        raise ValueError('Diagnóstico de melodia não corresponde às notas extraídas.')
    removidas={}; correcoes=[]
    def firme(i):
        q=qualidades[i]
        return notas[i][1]-notas[i][0]>=.20 and q['periodicidade']>=.85 and q['patamar_s']>=.10
    # Um ataque crepitante pode ser periódico e ainda cair uma oitava/quinta.
    # Exigir retorno à mesma região, dois apoios firmes e pouca duração total.
    for i in range(len(notas)-2):
        if not firme(i): continue
        for j in range(i+2,min(len(notas),i+7)):
            if notas[j][0]-notas[i][1]>.65: break
            if not firme(j) or abs(notas[j][2]-notas[i][2])>1: continue
            for k in range(i+1,j):
                a,b,p=notas[k]; q=qualidades[k]
                distante=min(abs(p-notas[i][2]),abs(p-notas[j][2]))>=5
                curto=b-a<=.22
                if q['periodicidade']>=.90 and q['apoio']>=.75 and q['patamar_s']>=.05:
                    continue  # salto breve, mas apoiado: não confundir com ataque crepitante
                fragil=q['periodicidade']<.90 or q['patamar_s']<.08 or q['apoio']<.5
                if distante and curto and fragil:
                    removidas[k]='ataque fora do registro'
            break
    # Passagem monotônica entre duas alturas próximas: só retirar se não houver
    # patamar confiável ou se a grade tornaria uma transição fraca muito longa.
    for i in range(1,len(notas)-1):
        if i in removidas: continue
        a,b,p=notas[i]; ant,seg=notas[i-1],notas[i+1]; q=qualidades[i]
        if b-a>.20 or a-ant[1]>.12 or seg[0]-b>.12: continue
        ponte=(ant[2]<p<seg[2] or ant[2]>p>seg[2]) and abs(seg[2]-ant[2])<=3
        vibrato=ant[2]==seg[2] and abs(p-ant[2])==1
        if not (ponte or vibrato): continue
        # Preservar alturas realmente sustentadas, mesmo cromáticas e curtas.
        if q['patamar_s']>=.08 and q['periodicidade']>=.85 and q['apoio']>=.60: continue
        ataque_palavra=any(a-.03<=ini<b for ini,_,_ in palavras)
        if ataque_palavra and q['patamar_s']>=.05 and q['periodicidade']>=.85: continue
        dt=b-a
        batidas=max(0.,grade.pos(b)-grade.pos(a))
        minimo=grade.passo*dt/batidas if batidas>1e-8 else dt
        inflacao=minimo/max(dt,.001)
        sem_patamar=q['patamar_s']<.04 and q['apoio']<.60
        exagerada=nivel!='dificil' and inflacao>=1.7 and q['patamar_s']<.08
        if sem_patamar or exagerada:
            removidas[i]='deslizamento sem patamar' if sem_patamar else 'passagem alongada pela grade'
    saida=[]
    for i,n in enumerate(notas):
        if i in removidas:
            correcoes.append(dict(inicio=n[0],fim=n[1],midi=n[2],motivo=removidas[i],**qualidades[i]))
        else:
            saida.append(tuple(n))
    # Guardar o ataque de palavra quando a altura firme começa ainda na mesma
    # palavra. Não estender através de silêncio nem inventar uma altura diferente.
    for indice,(a,b,p) in enumerate(saida):
        anteriores=[n for i,n in enumerate(notas) if i in removidas and 0<=a-n[1]<=.18]
        for ini,fim,_ in palavras:
            if ini<=a<=fim and any(ini-.03<=n[0]<fim for n in anteriores):
                novo=max(ini,saida[indice-1][1] if indice else ini)
                if a-novo<=.25:
                    saida[indice]=(novo,b,p)
    return saida,correcoes
