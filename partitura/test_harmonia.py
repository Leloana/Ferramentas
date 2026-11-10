import unittest

from gerar import TIPOS
from harmonia import corrigir_qualidade, tirar_choques

DO = 0


def acorde(tipo, pos=0, raiz=DO):
    return [(pos, raiz, tipo, raiz)]


class Qualidade(unittest.TestCase):
    def test_si_sustentado_troca_c7_por_c7m(self):
        acs, mud = corrigir_qualidade(acorde("7"), [(0, 2, 71)], TIPOS)
        self.assertEqual(acs[0][2], "maj7")
        self.assertEqual(mud[0]["antes"], "7")

    def test_sib_sustentado_troca_c7m_por_c7(self):
        acs, _ = corrigir_qualidade(acorde("maj7"), [(0, 2, 70)], TIPOS)
        self.assertEqual(acs[0][2], "7")

    def test_treze_sobre_c7m_fica(self):
        # Lá sobre C7M fica a um tom do Si e do Sol: é a 13ª, tensão; não mexe
        acs, mud = corrigir_qualidade(acorde("maj7"), [(0, 2, 69)], TIPOS)
        self.assertEqual((acs[0][2], mud), ("maj7", []))

    def test_si_sobre_c6_vira_c7m(self):
        acs, _ = corrigir_qualidade(acorde("6"), [(0, 2, 71)], TIPOS)
        self.assertEqual(acs[0][2], "maj7")

    def test_nota_curta_nao_decide(self):
        acs, mud = corrigir_qualidade(acorde("7"), [(0, .5, 71)], TIPOS)
        self.assertEqual(acs[0][2], "7")
        self.assertEqual(mud, [])

    def test_blue_note_nao_vira_menor(self):
        # Mib sustentado sobre Dó maior: família maior não tem Mib; fica
        acs, _ = corrigir_qualidade(acorde("maj"), [(0, 2, 63)], TIPOS)
        self.assertEqual(acs[0][2], "maj")

    def test_tensao_sem_semitom_fica(self):
        # Ré (9ª) sobre C7M: tom inteiro das notas do acorde, não é choque
        acs, mud = corrigir_qualidade(acorde("maj7"), [(0, 2, 62)], TIPOS)
        self.assertEqual((acs[0][2], mud), ("maj7", []))

    def test_menor(self):
        # Si sustentado sobre Ré m7 (Dó): m6 tem o Si
        acs, _ = corrigir_qualidade(acorde("m7", raiz=2), [(0, 2, 71)], TIPOS)
        self.assertEqual(acs[0][2], "m6")


class Choques(unittest.TestCase):
    def test_tira_a_terca_debaixo_do_sus4(self):
        md = [(0, 2, [65])]                  # Fá cantado
        me = [(0, 2, [48, 52, 55])]          # Dó Mi Sol
        me2, mud = tirar_choques(md, me)
        self.assertEqual(me2[0][2], [48, 55])
        self.assertEqual(len(mud), 1)

    def test_baixo_nunca_sai(self):
        me2, _ = tirar_choques([(0, 2, [61])], [(0, 2, [48, 55])])  # Dó# cantado sobre baixo Dó
        self.assertEqual(me2[0][2], [48, 55])

    def test_nota_curta_e_tensao_ficam(self):
        me = [(0, 2, [48, 52, 55])]
        self.assertEqual(tirar_choques([(0, .5, [65])], me)[0], me)     # Fá de passagem
        self.assertEqual(tirar_choques([(0, 2, [62])], me)[0], me)      # Ré: 9ª
        self.assertEqual(tirar_choques([(0, 2, [71])], me)[0], me)      # Si: 7M sobre o baixo Dó

    def test_so_quando_soa_junto(self):
        me = [(2, 2, [48, 52, 55])]
        self.assertEqual(tirar_choques([(0, 2, [65])], me)[0], me)


if __name__ == "__main__":
    unittest.main()
