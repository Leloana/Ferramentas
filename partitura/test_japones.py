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

    def test_sem_japones_fica_igual(self):
        self.assertFalse(tem_japones("hello"))
        self.assertEqual(silabas_japonesas("hello"), ["hello"])


if __name__ == "__main__":
    unittest.main()
