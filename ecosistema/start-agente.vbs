' start-agente.vbs -- Inicia o Agente do Ecossistema (agente.py --daemon) OCULTO,
' na sessao INTERATIVA do usuario. Uma copia deste arquivo fica na pasta
' Startup do Windows para subir o agente automaticamente no login.
'
' Por que aqui (e nao via servico/SSH): so quem roda na sessao do usuario pode
' abrir navegador/Explorer/apps VISIVELMENTE (PLANO.md secao 3, sessao 0 x 1).
' O agente escuta em 127.0.0.1:8765 e resolve os descritores de handoff que o
' celular envia (via 'agente.py --send' disparado por SSH).

Dim shell, pyw, script
Set shell = CreateObject("WScript.Shell")
pyw = "C:\Users\mf827\AppData\Local\Microsoft\WindowsApps\pythonw.exe"
script = "C:\Users\mf827\Documents\Ferramentas\ecosistema\agente.py"
' 0 = janela oculta ; False = nao espera terminar
shell.Run """" & pyw & """ """ & script & """ --daemon", 0, False
