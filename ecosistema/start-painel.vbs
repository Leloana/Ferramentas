' start-painel.vbs -- Inicia o PAINEL do Ecossistema (agente.py --panel), na
' sessao INTERATIVA do usuario. Atalho manual (o autostart do login segue
' subindo o --daemon headless; ver start-agente.vbs).
'
' O painel HOSPEDA o daemon no proprio processo (le a presenca direto, sem IPC).
' Se ja houver um daemon headless ocupando a 8765, o painel assume (takeover) e
' devolve a porta ao 'Sair' pela bandeja. Por que aqui (e nao via servico/SSH):
' so quem roda na sessao do usuario pode abrir janelas/apps VISIVELMENTE
' (PLANO.md secao 3, sessao 0 x 1).
'
' Usa pythonw.exe (sem console) e janela 1 = normal (o painel mostra sua janela;
' depois pode esconder na bandeja / area de icones ocultos do Windows).

Dim shell, pyw, script
Set shell = CreateObject("WScript.Shell")
pyw = "C:\Users\mf827\AppData\Local\Microsoft\WindowsApps\pythonw.exe"
script = "C:\Users\mf827\Documents\Ferramentas\ecosistema\agente.py"
' 1 = janela normal ; False = nao espera terminar
shell.Run """" & pyw & """ """ & script & """ --panel", 1, False
