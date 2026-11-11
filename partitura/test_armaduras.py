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


class TomDaMusica(unittest.TestCase):
    def test_mixolidio_fica_na_armadura_da_tonica(self):
        # Si♭ com o Lá♭ do Si♭7 mais frequente que o Lá (Águas de Março): 2 bemóis, não 3
        from armaduras import custo_por_armadura
        peso = {58: 29, 65: 17, 62: 14, 56: 8, 55: 7, 63: 6, 60: 6, 64: 5, 66: 4, 61: 2, 57: 1}
        eventos = [(d, [m]) for m, d in peso.items()]
        self.assertEqual(int(custo_por_armadura(eventos).argmin()) - 6, -2)

    def test_tom_sem_acidentes_continua_igual(self):
        from armaduras import custo_por_armadura
        self.assertEqual(int(custo_por_armadura([(1, [m]) for m in DO]).argmin()) - 6, 0)
        self.assertEqual(int(custo_por_armadura([(1, [m]) for m in LA_BEMOL]).argmin()) - 6, -4)


class GrafiaDoAcorde(unittest.TestCase):
    def nomes(self, r, kind, sust):
        from gerar import acorde_com_grafia
        return [q.name for q in acorde_com_grafia(r, kind, sust).pitches]

    def test_diminuto_sem_dobrado_bemol(self):
        nomes = self.nomes(8, "diminished-seventh", -2)
        self.assertEqual(nomes[0], "G#")
        self.assertFalse(any("--" in n or "##" in n for n in nomes))

    def test_acorde_do_tom_nao_muda(self):
        self.assertEqual(self.nomes(10, "dominant-seventh", -2), ["B-", "D", "F", "A-"])
        self.assertEqual(self.nomes(9, "dominant-seventh", 0), ["A", "C#", "E", "G"])


if __name__ == "__main__":
    unittest.main()
