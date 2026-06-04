"""Helper de teste (Fase B): mostra o QR de pareamento em PNG (escaneavel) e
escuta o celular com o MESMO token. Equivale ao `agente.py --pair`, mas abre uma
imagem em vez do QR ASCII (muito mais facil de escanear da tela do PC).

Uso: python pair_hw.py   (Ctrl+C para abortar; expira sozinho em 300s)
"""
import io
import os
import sys
import json
import tempfile

import pareamento

# stdout/err em UTF-8 (console cp1252 quebraria com acentos/JSON).
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

info = pareamento.monta_info(port=int(os.environ.get("HANDOFF_SSH_PORT", "22")))
texto = pareamento.info_para_qr_texto(info)

print("==> Pareamento por QR (PNG)")
print(f"    host={info.get('host')} port={info.get('port')} user={info.get('user')}")
print(f"    fingerprint={info.get('fp')}")
print(f"    token={info.get('token')} pair_port={info.get('pair_port')}")
print(f"    conteudo_qr={texto}")

# Gera o PNG e abre no visualizador padrao do Windows (na sessao do usuario).
png_path = os.path.join(tempfile.gettempdir(), "ecossistema_pair_qr.png")
try:
    import qrcode
    qr = qrcode.QRCode(border=2, box_size=10)
    qr.add_data(texto)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(png_path)
    print(f"    QR salvo em: {png_path}")
    try:
        os.startfile(png_path)  # abre na tela do usuario
        print("    QR aberto no visualizador. ESCANEIE no app (Parear com QR).")
    except Exception as e:
        print(f"    (nao consegui abrir a imagem automaticamente: {e})")
except Exception as e:
    print(f"    Falha ao gerar PNG ({e}); caindo para ASCII:")
    print(pareamento.render_qr_ascii(texto))

print("    Aguardando o celular (expira em 300s)...", flush=True)
res = pareamento.servir_pareamento(info, timeout=300)
if res:
    print(f"PAREADO_OK name={res.get('name')!r} device={res.get('device')!r}")
    print(f"PUBKEY={res.get('pubkey')}")
    sys.exit(0)
print("PAREAMENTO_EXPIROU sem dispositivo.", file=sys.stderr)
sys.exit(1)
