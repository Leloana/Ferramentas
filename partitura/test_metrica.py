"""Compasso de 3 tempos (madmom) escrito em 3/4 e serviço do AMT-APC com o modelo carregado."""
import os
import unittest
from pathlib import Path
from unittest import mock

import amtapc
import gerar
import metrica
from limpeza import juntar_repetidas_esquerda
from regressao import repetidos


class Compasso(unittest.TestCase):
    def tearDown(self):
        metrica.definir(4)

    def test_definir_so_aceita_3_ou_4(self):
        self.assertEqual(metrica.definir(3), 3)
        self.assertEqual(metrica.definir(2), 4)
        self.assertEqual(metrica.definir(None), 4)

    def test_tempos_do_musicxml(self):
        self.assertEqual(metrica.do_musicxml("<time><beats>3</beats><beat-type>4</beat-type></time>"), 3)
        self.assertEqual(metrica.do_musicxml("<time>\n <beats>6</beats>\n <beat-type>8</beat-type></time>"), 3)
        self.assertEqual(metrica.do_musicxml("<score/>"), 4)

    def test_valsa_sai_em_3_4_com_compassos_de_3_tempos(self):
        from music21 import meter, stream
        metrica.definir(3)
        # oom-pa-pa: baixo no 1, acorde no 2 e 3; a música começa no 2º tempo (anacruse)
        me = [(3 * k + j, 1.0, [48] if j == 0 else [60, 64, 67]) for k in range(4) for j in range(3)]
        md = [(1.0, 2.0, [76])] + [(3.0 * k, 3.0, [72 + k]) for k in range(1, 4)]
        sc, _ = gerar.montar_partitura(md, me, [], 150, "t", "s")
        ts = sc.recurse().getElementsByClass(meter.TimeSignature)[0]
        self.assertEqual(ts.ratioString, "3/4")
        compassos = list(sc.parts[1].getElementsByClass(stream.Measure))
        self.assertEqual({m.duration.quarterLength for m in compassos}, {3.0})
        for m in compassos:   # o baixo cai no tempo 1 de cada compasso
            self.assertEqual(min(m.recurse().notes, key=lambda n: min(p.midi for p in n.pitches)).offset, 0.0)

    def test_deslocamento_e_inicio_no_compasso_de_3(self):
        metrica.definir(3)
        self.assertEqual(gerar.deslocamento([(-1.0, 1.0, [60])], []), 3.0)
        metrica.definir(4)
        self.assertEqual(gerar.deslocamento([(-1.0, 1.0, [60])], []), 4.0)

    def test_repetida_da_esquerda_nao_atravessa_a_barra_do_3_4(self):
        me = [(float(t), 1.0, [48]) for t in range(6)]
        metrica.definir(3)
        self.assertEqual([(o, d) for o, d, _ in juntar_repetidas_esquerda(me)], [(0.0, 3.0), (3.0, 3.0)])
        metrica.definir(4)
        self.assertEqual([(o, d) for o, d, _ in juntar_repetidas_esquerda(me)], [(0.0, 2.0), (2.0, 2.0), (4.0, 2.0)])

    def test_repetidos_conta_pelo_compasso_da_partitura(self):
        md = [(float(t), 1.0, (60 + t % 3,)) for t in range(9)]   # 3 compassos de 3/4 iguais
        self.assertEqual(repetidos(md, [], 3), 2)
        self.assertEqual(repetidos(md, [], 4), 0)


class ServicoAmtapc(unittest.TestCase):
    def test_sem_servico_cai_pro_lancador(self):
        with mock.patch.dict(os.environ, {amtapc.VARIAVEL: "127.0.0.1:1"}):
            self.assertFalse(amtapc._pelo_servico(Path("x.wav"), Path("y.mid"), "level2"))
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(amtapc._pelo_servico(Path("x.wav"), Path("y.mid"), "level2"))

    def test_conversa_com_o_servico(self):
        import json
        import socket
        import threading
        escuta = socket.create_server(("127.0.0.1", 0))
        pedidos = []

        def atender(resposta):
            c, _ = escuta.accept()
            with c, c.makefile("rw", encoding="utf-8", newline="\n") as arq:
                pedidos.append(json.loads(arq.readline()))
                arq.write(resposta)
                arq.flush()

        endereco = f"127.0.0.1:{escuta.getsockname()[1]}"
        with mock.patch.dict(os.environ, {amtapc.VARIAVEL: endereco}):
            t = threading.Thread(target=atender, args=("Processing each segment: 50%|x| 1/2\n#OK\n",))
            t.start()
            self.assertTrue(amtapc._pelo_servico(Path("a.wav"), Path("b.mid"), "level1"))
            t.join()
            self.assertEqual(pedidos[0]["estilo"], "level1")
            t = threading.Thread(target=atender, args=("#ERRO RuntimeError: quebrou\n",))
            t.start()
            with self.assertRaisesRegex(RuntimeError, "quebrou"):
                amtapc._pelo_servico(Path("a.wav"), Path("b.mid"), "level2")
            t.join()
        escuta.close()


if __name__ == "__main__":
    unittest.main()
