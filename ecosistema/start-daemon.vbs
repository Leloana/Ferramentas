' start-daemon.vbs -- Inicia o Handoff daemon (receiver.py --daemon) OCULTO,
' na sessao interativa do usuario. Uma copia deste arquivo fica na pasta
' Startup do Windows para subir o daemon automaticamente no login.
'
' O daemon escuta em 127.0.0.1:8765 e abre no navegador padrao as URLs que
' o celular envia (via 'receiver.py --send' disparado por SSH).

Dim shell, pyw, script
Set shell = CreateObject("WScript.Shell")
pyw = "C:\Users\mf827\AppData\Local\Microsoft\WindowsApps\pythonw.exe"
script = "C:\Users\mf827\Documents\Ferramentas\ecosistema\receiver.py"
' 0 = janela oculta ; False = nao espera terminar
shell.Run """" & pyw & """ """ & script & """ --daemon", 0, False
