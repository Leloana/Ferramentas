import unittest

from japones import moras, silabas_japonesas, tem_japones


class Japones(unittest.TestCase):
    def test_moras(self):
        self.assertEqual(moras("キョウ"), ["キョ", "ウ"])
        self.assertEqual(moras("トーキョー"), ["トー", "キョー"])
        self.assertEqual(moras("ナッテ"), ["ナッ", "テ"])
        self.assertEqual(moras("カンジ"), ["カ", "ン", "ジ"])

    def test_romaji_como_se_canta(self):
        try:
            self.assertEqual(silabas_japonesas("空は"), ["so", "ra", "wa"])    # は partícula = wa
        except ImportError:
            self.skipTest("pykakasi/fugashi ausentes")
        self.assertEqual(silabas_japonesas("ちょっと"), ["chot", "to"])
        self.assertEqual(silabas_japonesas("行こう、"), ["i", "koo、"])
        self.assertEqual(silabas_japonesas("空", "kana"), ["そ", "ら"])
        # kana mostra a grafia, cortada nas moras da pronúncia
        self.assertEqual(silabas_japonesas("東京", "kana"), ["とう", "きょう"])
        self.assertEqual(silabas_japonesas("空は", "kana"), ["そ", "ら", "は"])

    def test_kana_espacado_so_no_desenho(self):
        import gerar
        xml = '<note><lyric number="1"><syllabic>single</syllabic><text>きょう</text></lyric></note>'
        saida = gerar.espacar_kana(xml)
        self.assertIn("<text>   きょう   </text>", saida)
        latino = '<note><lyric number="1"><text>so</text></lyric></note>'
        self.assertEqual(gerar.espacar_kana(latino), latino)

    def test_sem_japones_fica_igual(self):
        self.assertFalse(tem_japones("hello"))
        self.assertEqual(silabas_japonesas("hello"), ["hello"])


if __name__ == "__main__":
    unittest.main()
