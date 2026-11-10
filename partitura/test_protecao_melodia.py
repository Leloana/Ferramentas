import unittest
import numpy as np
from protecao_melodia import qualidade_segmento,proteger_melodia


class GradeTeste:
    def __init__(self,passo=.5): self.passo=passo
    def pos(self,t): return t*2  # 120 BPM


FIRME=dict(periodicidade=.95,apoio=.95,patamar_s=.4)
FRACA=dict(periodicidade=.80,apoio=.4,patamar_s=.03)


class Protecao(unittest.TestCase):
    def test_deslizamento_fa_sol_sem_degrau_cromatico(self):
        ns=[(0,.5,53),(.5,.59,54),(.59,1,55)]
        saida,c=proteger_melodia(ns,GradeTeste(),'medio',diagnostico={'notas':[FIRME,FRACA,FIRME]})
        self.assertEqual([n[2] for n in saida],[53,55])
        self.assertEqual(len(c),1)

    def test_preserva_cromatismo_curto_firme_e_nota_longa(self):
        q=dict(periodicidade=.96,apoio=.95,patamar_s=.09)
        for dur in (.09,.5):
            ns=[(0,.5,53),(.5,.5+dur,54),(.5+dur,1.5,55)]
            saida,c=proteger_melodia(ns,GradeTeste(),'medio',diagnostico={'notas':[FIRME,q,FIRME]})
            self.assertEqual(saida,ns); self.assertEqual(c,[])

    def test_ataque_grave_fora_do_registro(self):
        ns=[(0,.5,50),(.6,.74,42),(.76,1.4,50)]
        saida,c=proteger_melodia(ns,GradeTeste(),'dificil',diagnostico={'notas':[FIRME,FRACA,FIRME]})
        self.assertEqual([n[2] for n in saida],[50,50])
        self.assertEqual(c[0]['motivo'],'ataque fora do registro')

    def test_preserva_salto_legitimo_sem_retorno(self):
        ns=[(0,.5,50),(.5,.65,42),(.65,1.1,43)]
        saida,c=proteger_melodia(ns,GradeTeste(),'medio',diagnostico={'notas':[FIRME,FRACA,FIRME]})
        self.assertEqual(saida,ns)

    def test_preserva_salto_curto_com_apoio_forte(self):
        ns=[(0,.5,50),(.5,.57,42),(.57,1.1,50)]
        q=dict(periodicidade=.96,apoio=.95,patamar_s=.07)
        saida,c=proteger_melodia(ns,GradeTeste(),'medio',diagnostico={'notas':[FIRME,q,FIRME]})
        self.assertEqual(saida,ns); self.assertEqual(c,[])

    def test_passagem_la_curta_depende_da_grade(self):
        ns=[(0,.3,43),(.3,.39,45),(.39,1,46)]
        q=dict(periodicidade=.82,apoio=.7,patamar_s=.05)
        diag={'notas':[FIRME,q,FIRME]}
        medio,_=proteger_melodia(ns,GradeTeste(.5),'medio',diagnostico=diag)
        dificil,_=proteger_melodia(ns,GradeTeste(.25),'dificil',diagnostico=diag)
        self.assertEqual([n[2] for n in medio],[43,46]); self.assertEqual(dificil,ns)

    def test_preserva_ataque_de_palavra_com_altura_apoiada(self):
        ns=[(0,.3,43),(.3,.39,45),(.39,1,46)]
        q=dict(periodicidade=.90,apoio=.7,patamar_s=.06)
        saida,c=proteger_melodia(ns,GradeTeste(),'medio',[(.3,.6,'não')],{'notas':[FIRME,q,FIRME]})
        self.assertEqual(saida,ns)

    def test_recupera_inicio_da_palavra_na_altura_firme(self):
        ns=[(0,.5,50),(.6,.74,42),(.76,1.4,50)]
        saida,_=proteger_melodia(ns,GradeTeste(),'medio',[(.6,1.2,'lar')],{'notas':[FIRME,FRACA,FIRME]})
        self.assertEqual(saida[1],(.6,1.4,50))

    def test_sem_evidencia_nao_adivinha(self):
        ns=[(0,.5,53),(.5,.59,54),(.59,1,55)]
        self.assertEqual(proteger_melodia(ns,GradeTeste(),'medio'),(ns,[]))

    def test_estabilidade_distingue_nota_de_rampa(self):
        reta=qualidade_segmento(np.full(30,54.),np.full(30,.95),0,30)
        rampa=qualidade_segmento(np.linspace(53,55,30),np.full(30,.95),0,30)
        self.assertGreater(reta['patamar_s'],.25)
        self.assertLess(rampa['patamar_s'],.10)


if __name__=='__main__': unittest.main()
