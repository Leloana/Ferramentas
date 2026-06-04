#!/usr/bin/env python3
"""
painel.py  --  Painel grafico minimo do Ecossistema Hibrido (lado PC).

Espelha a aba "Inicio" do app Android: SEMPRE mostra (1) a caixa de celulares
conectados e (2) o QR de pareamento. Em Portugues, visual limpo, sem deps
pesadas (tkinter + Pillow + qrcode; bandeja via pystray e best-effort/opcional).

LICAO DA SESSAO 0/1 (PLANO.md secao 3): quem abre janelas TEM que rodar na
sessao INTERATIVA do usuario. Por isso o painel roda nessa sessao e HOSPEDA o
daemon no PROPRIO processo -- assim le agente.presenca_snapshot() direto, sem
IPC (a presenca e in-memory no processo do daemon).

Arquitetura (3 threads, 1 processo):
  - principal: a GUI (tkinter). root.after() faz polling de presenca (~1.5s) e
    do QR (~1s). tkinter SO pode ser tocado por esta thread.
  - daemon:    agente.daemon_loop(config, parar) -- bind 127.0.0.1:8765.
  - pareamento: loop "sempre ligado" -> monta_info() (token novo a cada ciclo),
    publica o QR exibido, e chama servir_pareamento(info, 180). Ao retornar
    (sucesso OU timeout), gera novo info/QR e repete. O QR exibido e SEMPRE o
    do mesmo `info` que esta no servir_pareamento ativo (mesmo token).

So um daemon pode ter a porta 8765. Se ja houver um daemon headless rodando, o
painel pede _ctrl=shutdown (takeover) e assume a porta. Ao 'Sair' pela bandeja,
o painel devolve a porta religando o daemon headless (os handoffs seguem).

E iniciado por: agente.py --panel  (ou start-painel.vbs / atalho do Menu Iniciar).
"""
import os
import sys
import time
import json
import socket
import logging
import threading
import subprocess
import queue
from pathlib import Path

import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageTk
import qrcode

import agente
import pareamento

# stdout/err em UTF-8 (caso rode com console).
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

SSH_PORT = int(os.environ.get("HANDOFF_SSH_PORT", "22"))
POLL_PRESENCA_MS = 1500
POLL_QR_MS = 1000
POLL_CMD_MS = 200

# Paleta minima (claro, limpo).
COR_FUNDO = "#f4f5f7"
COR_CARD = "#ffffff"
COR_TEXTO = "#1c1c1e"
COR_SUB = "#6b7280"
COR_VERDE = "#22c55e"
COR_CINZA = "#c4c7cc"
COR_BORDA = "#e3e5e8"


# --------------------------------------------------------------------------- #
# Estado compartilhado do QR (escrito pela thread de pareamento, lido pela GUI) #
# --------------------------------------------------------------------------- #
class EstadoQR:
    """Guarda o QR vigente (mesmo token que esta no servir_pareamento ativo).

    A thread de pareamento publica um PIL.Image (seguro fora da main thread); a
    GUI converte para ImageTk.PhotoImage na main thread. `token` muda a cada
    ciclo -> a GUI so redesenha quando muda (evita recriar a imagem a cada tick).
    """
    def __init__(self):
        self._lock = threading.Lock()
        self.token = None
        self.info = None
        self.image = None  # PIL.Image
        self.ultimo_pareado = None  # (nome, timestamp)

    def publicar(self, info: dict, image):
        with self._lock:
            self.token = info.get("token")
            self.info = info
            self.image = image

    def ler(self):
        with self._lock:
            return self.token, self.info, self.image

    def marcar_pareado(self, nome: str):
        with self._lock:
            self.ultimo_pareado = (nome, time.time())

    def ler_pareado(self):
        with self._lock:
            return self.ultimo_pareado


QR_STATE = EstadoQR()
PARAR = threading.Event()
CMD_Q: "queue.Queue" = queue.Queue()  # comandos da bandeja -> GUI (thread-safe)


# --------------------------------------------------------------------------- #
# Takeover da porta 8765 (so um daemon pode existir)                           #
# --------------------------------------------------------------------------- #
def _porta_ocupada() -> bool:
    try:
        with socket.create_connection(
            (agente.DAEMON_HOST, agente.DAEMON_PORT), timeout=0.5
        ):
            return True
    except OSError:
        return False


def _pedir_shutdown_daemon():
    """Pede ao daemon headless atual que se encerre (libera a porta 8765)."""
    try:
        with socket.create_connection(
            (agente.DAEMON_HOST, agente.DAEMON_PORT), timeout=1.0
        ) as s:
            s.sendall(b'{"_ctrl":"shutdown"}\n')
            s.settimeout(1.0)
            try:
                s.recv(64)  # le o "bye" (best-effort)
            except OSError:
                pass
    except OSError:
        pass


def assumir_porta():
    """Garante a 8765 livre para ESTE processo hospedar o daemon.

    No Windows, SO_REUSEADDR permite VARIOS listeners na mesma porta, e novas
    conexoes vao ao socket vinculado por ultimo. Por isso pedimos shutdown em
    LOOP: cada pedido encerra um daemon; a proxima conexao cai no proximo, ate
    nao sobrar nenhum (porta livre). Daemons de versao antiga (sem o handler de
    shutdown) nao saem -> apos N tentativas seguimos mesmo assim (best-effort)."""
    if not _porta_ocupada():
        return
    logging.info("painel: daemon ja ativo na 8765; pedindo takeover (shutdown).")
    for _ in range(20):  # ate ~4s drenando daemons existentes
        if not _porta_ocupada():
            return
        _pedir_shutdown_daemon()
        time.sleep(0.2)
    logging.warning("painel: porta 8765 segue ocupada apos pedir shutdown "
                    "(daemon de versao antiga?); seguindo assim mesmo.")


# --------------------------------------------------------------------------- #
# Threads de fundo                                                             #
# --------------------------------------------------------------------------- #
def _gera_qr_image(texto: str):
    qr = qrcode.QRCode(border=2, box_size=10)
    qr.add_data(texto)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert("RGB")


def thread_daemon():
    config = agente.load_config()
    agente.daemon_loop(config, parar=PARAR)


def _on_pareado(res):
    """Chamado pelo servir_pareamento ao fim de cada ciclo (dict|None)."""
    if res:
        nome = res.get("name") or "Android"
        QR_STATE.marcar_pareado(nome)
        agente.notify("Ecossistema", f"Celular pareado: {nome}")
        logging.info(f"painel: pareado {nome!r}; gerando novo QR.")


def thread_pareamento():
    """Loop 'sempre ligado': QR exibido = info ativo no servir_pareamento."""
    while not PARAR.is_set():
        try:
            info = pareamento.monta_info(port=SSH_PORT)
            texto = pareamento.info_para_qr_texto(info)
            img = _gera_qr_image(texto)
            QR_STATE.publicar(info, img)
            # Bloqueante ate parear (sucesso) ou expirar (180s); depois gira token.
            pareamento.servir_pareamento(info, timeout=180, on_result=_on_pareado)
        except Exception as e:
            logging.error(f"painel: ciclo de pareamento falhou: {e}")
            if PARAR.wait(2):
                break


# --------------------------------------------------------------------------- #
# Acoes do rodape                                                              #
# --------------------------------------------------------------------------- #
def abrir_log():
    try:
        agente.HANDOFF_DIR.mkdir(parents=True, exist_ok=True)
        if not agente.LOG_FILE.exists():
            agente.LOG_FILE.write_text("", encoding="utf-8")
        if agente.IS_WINDOWS:
            os.startfile(str(agente.LOG_FILE))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(agente.LOG_FILE)])
    except Exception as e:
        logging.error(f"painel: abrir log falhou: {e}")


def configurar_ssh():
    """Roda setup-windows.ps1 ELEVADO (UAC) -- configura o sshd/firewall."""
    script = agente.APP_DIR / "setup-windows.ps1"
    if not script.exists():
        logging.error(f"painel: setup-windows.ps1 nao encontrado em {script}")
        return
    try:
        ps = (
            "Start-Process powershell -Verb RunAs -ArgumentList "
            "'-NoProfile','-ExecutionPolicy','Bypass','-File',"
            f"'{script}'"
        )
        subprocess.Popen(
            ["powershell", "-NoProfile", "-Command", ps],
            creationflags=agente.CREATE_NO_WINDOW,
        )
    except Exception as e:
        logging.error(f"painel: configurar SSH falhou: {e}")


def _relancar_daemon_headless():
    """Ao 'Sair', religa o daemon headless para os handoffs continuarem."""
    try:
        if agente.FROZEN:
            cmd = [sys.executable, "--daemon"]
        else:
            pyw = Path(sys.executable).with_name("pythonw.exe")
            exe = str(pyw) if pyw.exists() else sys.executable
            cmd = [exe, str(agente.APP_DIR / "agente.py"), "--daemon"]
        subprocess.Popen(cmd, creationflags=agente.CREATE_NO_WINDOW, close_fds=True)
        logging.info("painel: daemon headless religado ao sair.")
    except Exception as e:
        logging.error(f"painel: nao consegui religar o daemon headless: {e}")


# --------------------------------------------------------------------------- #
# Bandeja (pystray) -- best-effort/opcional                                    #
# --------------------------------------------------------------------------- #
def _icone_bandeja_img():
    """Icone simples (bolinha verde) gerado em runtime, sem arquivo externo."""
    img = Image.new("RGB", (64, 64), COR_FUNDO)
    from PIL import ImageDraw
    d = ImageDraw.Draw(img)
    d.ellipse((16, 16, 48, 48), fill=COR_VERDE)
    return img


def iniciar_bandeja():
    """Sobe o icone na bandeja (area de icones ocultos). Retorna o icon ou None."""
    try:
        import pystray
    except Exception:
        logging.info("painel: pystray ausente; bandeja desabilitada.")
        return None

    def _cmd(c):
        return lambda *a: CMD_Q.put(c)

    menu = pystray.Menu(
        pystray.MenuItem("Mostrar painel", _cmd("mostrar"), default=True),
        pystray.MenuItem("Esconder", _cmd("esconder")),
        pystray.MenuItem("Sair", _cmd("sair")),
    )
    icon = pystray.Icon(
        "ecossistema", _icone_bandeja_img(), "Ecossistema · Painel", menu
    )
    threading.Thread(target=icon.run, daemon=True).start()
    return icon


# --------------------------------------------------------------------------- #
# GUI (tkinter) -- so na thread principal                                      #
# --------------------------------------------------------------------------- #
class Painel:
    def __init__(self, root: tk.Tk, icon_bandeja):
        self.root = root
        self.icon = icon_bandeja
        self._qr_token_exibido = None
        self._qr_photo = None  # mantem referencia viva (senao o tkinter some)
        self._rows = []

        root.title("Ecossistema · Painel")
        root.configure(bg=COR_FUNDO)
        root.minsize(380, 620)
        root.protocol("WM_DELETE_WINDOW", self._ao_fechar)

        self._estilos()
        self._monta_layout()

        # Ticks periodicos (na main thread).
        self.root.after(POLL_PRESENCA_MS, self._tick_presenca)
        self.root.after(POLL_QR_MS, self._tick_qr)
        self.root.after(POLL_CMD_MS, self._tick_comandos)
        # Primeira pintura imediata.
        self._tick_presenca(reagendar=False)
        self._tick_qr(reagendar=False)

    # ---- estilo ----
    def _estilos(self):
        s = ttk.Style()
        try:
            s.theme_use("clam")
        except tk.TclError:
            pass
        s.configure("TFrame", background=COR_FUNDO)
        s.configure("Card.TFrame", background=COR_CARD)
        s.configure("Titulo.TLabel", background=COR_FUNDO, foreground=COR_SUB,
                    font=("Segoe UI", 10, "bold"))
        s.configure("Card.TLabel", background=COR_CARD, foreground=COR_TEXTO,
                    font=("Segoe UI", 11))
        s.configure("CardSub.TLabel", background=COR_CARD, foreground=COR_SUB,
                    font=("Segoe UI", 9))
        s.configure("Vazio.TLabel", background=COR_CARD, foreground=COR_SUB,
                    font=("Segoe UI", 10, "italic"))
        s.configure("Cap.TLabel", background=COR_FUNDO, foreground=COR_TEXTO,
                    font=("Segoe UI", 10, "bold"))
        s.configure("Mono.TLabel", background=COR_FUNDO, foreground=COR_SUB,
                    font=("Consolas", 8))
        s.configure("Rodape.TLabel", background=COR_FUNDO, foreground=COR_SUB,
                    font=("Segoe UI", 8))
        s.configure("Link.TButton", font=("Segoe UI", 8))

    # ---- layout ----
    def _monta_layout(self):
        wrap = ttk.Frame(self.root, padding=16, style="TFrame")
        wrap.pack(fill="both", expand=True)

        # --- Secao: celulares conectados ---
        ttk.Label(wrap, text="Celulares conectados", style="Titulo.TLabel").pack(
            anchor="w", pady=(0, 6))
        self.card_dev = tk.Frame(wrap, bg=COR_CARD, highlightbackground=COR_BORDA,
                                 highlightthickness=1)
        self.card_dev.pack(fill="x")
        self.lista_dev = tk.Frame(self.card_dev, bg=COR_CARD)
        self.lista_dev.pack(fill="x", padx=12, pady=10)

        # --- Secao: parear ---
        ttk.Label(wrap, text="Parear novo celular", style="Titulo.TLabel").pack(
            anchor="w", pady=(18, 6))
        card_qr = tk.Frame(wrap, bg=COR_CARD, highlightbackground=COR_BORDA,
                           highlightthickness=1)
        card_qr.pack(fill="x")
        inner = tk.Frame(card_qr, bg=COR_CARD)
        inner.pack(padx=14, pady=14)

        self.qr_label = tk.Label(inner, bg=COR_CARD, text="gerando QR…",
                                 fg=COR_SUB, width=18, height=9)
        self.qr_label.pack()
        ttk.Label(inner, text='Escaneie no app: "Parear com QR"',
                  style="Cap.TLabel", background=COR_CARD).pack(pady=(10, 2))
        self.lbl_pareado = tk.Label(inner, bg=COR_CARD, fg=COR_VERDE,
                                    font=("Segoe UI", 9, "bold"), text="")
        self.lbl_pareado.pack()

        meta = tk.Frame(card_qr, bg=COR_CARD)
        meta.pack(fill="x", padx=14, pady=(0, 12))
        self.lbl_host = tk.Label(meta, bg=COR_CARD, fg=COR_SUB, justify="left",
                                 font=("Consolas", 8), anchor="w")
        self.lbl_host.pack(fill="x")

        # --- Rodape: status do daemon + acoes ---
        rod = ttk.Frame(wrap, style="TFrame")
        rod.pack(fill="x", side="bottom", pady=(18, 0))
        self.lbl_daemon = tk.Label(rod, bg=COR_FUNDO, fg=COR_SUB, anchor="w",
                                   font=("Segoe UI", 8), text="● daemon: …")
        self.lbl_daemon.pack(side="left")
        ttk.Button(rod, text="Configurar SSH", style="Link.TButton",
                   command=configurar_ssh).pack(side="right")
        ttk.Button(rod, text="Abrir log", style="Link.TButton",
                   command=abrir_log).pack(side="right", padx=(0, 6))

    # ---- ticks ----
    def _tick_presenca(self, reagendar=True):
        try:
            self._render_dispositivos()
            self._render_daemon()
        except Exception as e:
            logging.debug(f"painel: tick presenca: {e}")
        if reagendar:
            self.root.after(POLL_PRESENCA_MS, self._tick_presenca)

    def _render_dispositivos(self):
        online = [d for d in agente.presenca_snapshot() if d.get("online")]
        for w in self._rows:
            w.destroy()
        self._rows = []
        if not online:
            lbl = ttk.Label(self.lista_dev, text="Nenhum celular conectado",
                            style="Vazio.TLabel")
            lbl.pack(anchor="w")
            self._rows.append(lbl)
            return
        for i, dev in enumerate(online):
            row = tk.Frame(self.lista_dev, bg=COR_CARD)
            row.pack(fill="x", pady=(0 if i == 0 else 8, 0))
            tk.Label(row, text="●", fg=COR_VERDE, bg=COR_CARD,
                     font=("Segoe UI", 12)).pack(side="left", padx=(0, 8))
            txt = tk.Frame(row, bg=COR_CARD)
            txt.pack(side="left", fill="x", expand=True)
            tk.Label(txt, text=dev.get("name") or dev.get("id") or "Android",
                     bg=COR_CARD, fg=COR_TEXTO, anchor="w",
                     font=("Segoe UI", 11)).pack(fill="x")
            tk.Label(txt, text=self._subtitulo(dev), bg=COR_CARD, fg=COR_SUB,
                     anchor="w", font=("Segoe UI", 9)).pack(fill="x")
            self._rows.append(row)

    @staticmethod
    def _subtitulo(dev) -> str:
        delta = time.time() - float(dev.get("last_seen") or 0)
        if delta < 12:
            quando = "ativo agora"
        elif delta < 90:
            quando = f"visto há {int(delta)}s"
        else:
            quando = f"visto há {int(delta // 60)} min"
        atv = (dev.get("atividade") or "").strip()
        return f"{quando} · {atv}" if atv else quando

    def _render_daemon(self):
        ativo = _porta_ocupada()
        cor = COR_VERDE if ativo else COR_CINZA
        txt = ("● daemon escutando 127.0.0.1:8765" if ativo
               else "● daemon offline")
        self.lbl_daemon.config(fg=cor, text=txt)

    def _tick_qr(self, reagendar=True):
        try:
            token, info, img = QR_STATE.ler()
            if img is not None and token != self._qr_token_exibido:
                disp = img.resize((220, 220), Image.NEAREST)
                self._qr_photo = ImageTk.PhotoImage(disp)
                self.qr_label.config(image=self._qr_photo, text="", width=220,
                                     height=220)
                self._qr_token_exibido = token
                if info:
                    host = info.get("host") or "—"
                    ts = info.get("tshost")
                    user = info.get("user") or "—"
                    fp = info.get("fp") or "—"
                    linhas = [f"host: {host}" + (f"   (ts: {ts})" if ts else ""),
                              f"usuário: {user}", f"fingerprint: {fp}"]
                    self.lbl_host.config(text="\n".join(linhas))
            # Banner "pareado" temporario (~6s).
            pareado = QR_STATE.ler_pareado()
            if pareado and (time.time() - pareado[1]) < 6:
                self.lbl_pareado.config(text=f"✓ {pareado[0]} pareado!")
            else:
                self.lbl_pareado.config(text="")
        except Exception as e:
            logging.debug(f"painel: tick qr: {e}")
        if reagendar:
            self.root.after(POLL_QR_MS, self._tick_qr)

    def _tick_comandos(self):
        try:
            while True:
                cmd = CMD_Q.get_nowait()
                if cmd == "mostrar":
                    self.root.deiconify()
                    self.root.lift()
                elif cmd == "esconder":
                    self.root.withdraw()
                elif cmd == "sair":
                    self._sair()
                    return
        except queue.Empty:
            pass
        self.root.after(POLL_CMD_MS, self._tick_comandos)

    # ---- ciclo de vida ----
    def _ao_fechar(self):
        """Botao X: se ha bandeja, esconde (daemon segue vivo); senao, sai."""
        if self.icon is not None:
            self.root.withdraw()
        else:
            self._sair()

    def _sair(self):
        logging.info("painel: encerrando (Sair).")
        PARAR.set()
        if self.icon is not None:
            try:
                self.icon.stop()
            except Exception:
                pass
        # Devolve a porta 8765: para o daemon deste processo e religa um headless
        # para os handoffs continuarem mesmo com o painel fechado.
        for _ in range(30):  # ate ~3s p/ o daemon_loop liberar a porta
            if not _porta_ocupada():
                break
            time.sleep(0.1)
        _relancar_daemon_headless()
        try:
            self.root.destroy()
        except tk.TclError:
            pass
        os._exit(0)


def main() -> int:
    agente.setup_logging()
    logging.info("painel: iniciando (modo --panel).")

    # 1) Garante a porta livre e HOSPEDA o daemon neste processo.
    assumir_porta()
    threading.Thread(target=thread_daemon, daemon=True).start()
    # 2) Pareamento "sempre ligado".
    threading.Thread(target=thread_pareamento, daemon=True).start()
    # 3) Bandeja (opcional) + GUI.
    icon = iniciar_bandeja()
    root = tk.Tk()
    Painel(root, icon)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass
    PARAR.set()
    return 0


if __name__ == "__main__":
    sys.exit(main())
