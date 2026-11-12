"""Fórmula de compasso da música que está sendo escrita.

O madmom (gerar.batidas_madmom) escolhe entre 3 e 4 tempos por compasso; o gerar.py guarda aqui e os
passos do modo leve leem daqui (repetições, derivados, tocabilidade, armadura, barra final, sincronia).
Fica num módulo à parte porque o gerar.py roda como __main__ e `import gerar` pega outra cópia.

6/8 não é escrito: a música em 6/8 sai em 3/4 (o madmom marca as colcheias pontuadas como 2 tempos
de 3 colcheias e o DBN só tem 3 ou 4 tempos) ou em 4/4 (2 tempos de semínima pontuada viram 4).
"""
TEMPOS = 4


def definir(tempos) -> int:
    """3 ou 4 (outro valor vira 4). Devolve o valor guardado."""
    global TEMPOS
    TEMPOS = 3 if int(tempos or 4) == 3 else 4
    return TEMPOS


def do_musicxml(texto: str) -> int:
    """Tempos por compasso de um MusicXML pronto (o 1º <time>); 4 se não tiver."""
    import re
    m = re.search(r"<time\b[^>]*>\s*<beats>(\d+)</beats>\s*<beat-type>(\d+)</beat-type>", texto)
    return int(m.group(1)) * 4 // int(m.group(2)) if m else 4
