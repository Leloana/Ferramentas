import unittest

from armaduras import armaduras_por_trecho, inicios_de_frase

DO = [60, 62, 64, 65, 67, 69, 71]
RE = [62, 64, 66, 67, 69, 71, 73]
LA_BEMOL = [56, 58, 60, 61, 63, 65, 67]


def trecho(escala, compassos, inicio=0.0, pausa_no_fim=False):
    """Melodia em colcheias + baixo semibreve, na escala dada."""
    md, me = [], []
    for c in range(compassos):
        base = inicio + 4 * c
        notas = 8 - (2 if pausa_no_fim and c == compassos - 1 else 0)
        md += [(base + .5 * i, .5, [escala[(c + i) % 7]]) for i in range(notas)]
        me.append((base, 4, [escala[c % 7] - 24]))
    return md, me


def armar(*partes):
    md, me = [], []
    for a, b in partes:
        md += a
        me += b
    fim = max(o + d for o, d, _ in md + me)
    eventos = md + [(o, .3 * d, ps) for o, d, ps in me]
    return armaduras_por_trecho(eventos, fim, inicios_de_frase(md))


class Armaduras(unittest.TestCase):
    def test_uma_armadura_sem_modulacao(self):
        self.assertEqual(armar(trecho(DO, 32)), [(0.0, 0)])

    def test_passagem_de_4_compassos_nao_troca(self):
        m = armar(trecho(DO, 14), trecho(RE, 4, 56), trecho(DO, 14, 72))
        self.assertEqual(m, [(0.0, 0)])

    def test_modulacao_de_verdade_troca_no_comeco_da_frase(self):
        m = armar(trecho(DO, 16, pausa_no_fim=True), trecho(RE, 16, 64))
        self.assertEqual(m, [(0.0, 0), (64.0, 2)])

    def test_frase_fora_da_fronteira_puxa_a_troca(self):
        # frase nova começa no compasso 18 (tempo 68), não na fronteira de bloco (64)
        a = trecho(DO, 17, pausa_no_fim=True)
        b = trecho(LA_BEMOL, 15, 68)
        m = armar(a, b)
        self.assertEqual(m, [(0.0, 0), (68.0, -4)])

    def test_ponte_de_8_compassos_fica_com_acidentes(self):
        m = armar(trecho(DO, 16), trecho(LA_BEMOL, 8, 64), trecho(DO, 16, 96))
        self.assertEqual(m, [(0.0, 0)])

    def test_cada_armadura_dura_16_compassos(self):
        m = armar(trecho(DO, 16, pausa_no_fim=True), trecho(RE, 16, 64, True), trecho(DO, 16, 128, True),
                  trecho(RE, 16, 192))
        self.assertEqual([k for _, k in m], [0, 2, 0, 2])
        for (a, _), (b, _) in zip(m, m[1:]):
            self.assertGreaterEqual(b - a, 64)

    def test_inicios_de_frase(self):
        md = [(0, 1, [60]), (1, 1, [62]), (3, 1, [64]), (4.5, 1, [65])]
        self.assertEqual(inicios_de_frase(md), [0, 3])


if __name__ == "__main__":
    unittest.main()
