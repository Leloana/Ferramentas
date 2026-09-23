import asyncio
import errno
import fcntl
import os
import struct
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional, Set

REPO_ROOT = Path(__file__).resolve().parent.parent

# Tenta importar módulos PTY disponíveis no Linux/macOS
try:
    import pty
    import termios
    HAS_PTY = True
except ImportError:
    HAS_PTY = False


class PtySession:
    """
    Representa uma sessão interativa de terminal (PTY) no host.
    Mantém o processo shell (bash) vivo mesmo se a conexão cair temporariamente.
    """

    def __init__(self, session_id: str, cols: int = 80, rows: int = 24, cwd: Optional[str] = None):
        self.session_id = session_id
        self.cols = cols
        self.rows = rows
        self.cwd = cwd or str(REPO_ROOT)
        self.master_fd: Optional[int] = None
        self.proc: Optional[subprocess.Popen] = None
        self.subscribers: Set[asyncio.Queue] = set()
        self.history = bytearray()
        self.max_history = 100_000  # ~100KB de buffer circular para reconexão
        self._closed = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    @property
    def is_alive(self) -> bool:
        if self._closed or self.proc is None:
            return False
        return self.proc.poll() is None

    def start(self, loop: Optional[asyncio.AbstractEventLoop] = None) -> bool:
        if not HAS_PTY:
            return False

        self._loop = loop or asyncio.get_event_loop()
        master, slave = pty.openpty()
        self.master_fd = master

        # Configura tamanho da janela no PTY
        try:
            fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", self.rows, self.cols, 0, 0))
        except Exception:
            pass

        # Modo não-bloqueante no master fd
        try:
            fcntl.fcntl(master, fcntl.F_SETFL, os.O_NONBLOCK)
        except Exception:
            pass

        # Prepara variáveis de ambiente garantindo que ferramentas (agy, node, claude) estejam no PATH
        env = os.environ.copy()
        env["TERM"] = "xterm-256color"
        env["COLORTERM"] = "truecolor"
        env["LANG"] = env.get("LANG", "en_US.UTF-8")

        extra_paths = [
            "/home/marcelo/.local/lib/antigravity",
            "/home/marcelo/.local/opt/node-v22.23.2-linux-x64/bin",
            "/home/marcelo/.local/bin",
            "/home/marcelo/.npm-global/bin",
            str(Path.home() / ".local" / "bin")
        ]
        curr_path = env.get("PATH", "")
        for p in extra_paths:
            if os.path.isdir(p) and p not in curr_path:
                curr_path = f"{p}:{curr_path}"
        env["PATH"] = curr_path

        # Escolhe o shell padrão
        shell = os.environ.get("SHELL", "/bin/bash")
        if not os.path.exists(shell):
            shell = "/bin/sh"

        work_dir = self.cwd if os.path.isdir(self.cwd) else str(Path.home())

        try:
            self.proc = subprocess.Popen(
                [shell, "-i"],
                stdin=slave,
                stdout=slave,
                stderr=slave,
                cwd=work_dir,
                env=env,
                close_fds=True,
                preexec_fn=os.setsid
            )
        finally:
            # O slave deve sempre ser fechado no processo pai
            os.close(slave)

        # Adiciona leitor assíncrono no loop
        self._loop.add_reader(self.master_fd, self._handle_read)
        return True

    def _handle_read(self) -> None:
        if self.master_fd is None or self._closed:
            return

        try:
            chunk = os.read(self.master_fd, 4096)
            if not chunk:
                self.close()
                return

            # Adiciona ao buffer de histórico para reconexões
            self.history.extend(chunk)
            if len(self.history) > self.max_history:
                self.history = self.history[-self.max_history:]

            # Despacha para todos os WebSockets inscritos
            for q in list(self.subscribers):
                try:
                    q.put_nowait(chunk)
                except Exception:
                    pass

        except OSError as e:
            # EIO indica EOF no PTY Linux quando o shell fecha
            if e.errno in (errno.EIO, errno.EBADF):
                self.close()
            # EAGAIN / EWOULDBLOCK apenas significa que não há mais dados agora
            elif e.errno not in (errno.EAGAIN, errno.EWOULDBLOCK):
                self.close()

    def write(self, data: bytes) -> None:
        if self.master_fd is not None and not self._closed:
            try:
                os.write(self.master_fd, data)
            except Exception:
                pass

    def resize(self, cols: int, rows: int) -> None:
        if self.master_fd is None or self._closed or not HAS_PTY:
            return
        self.cols = max(10, cols)
        self.rows = max(4, rows)
        try:
            fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, struct.pack("HHHH", self.rows, self.cols, 0, 0))
        except Exception:
            pass

    def subscribe(self, queue: asyncio.Queue) -> None:
        self.subscribers.add(queue)
        # Se já tiver histórico, envia para catch-up imediato
        if self.history:
            queue.put_nowait(bytes(self.history))

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self.subscribers.discard(queue)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True

        if self.master_fd is not None and self._loop is not None:
            try:
                self._loop.remove_reader(self.master_fd)
            except Exception:
                pass
            try:
                os.close(self.master_fd)
            except Exception:
                pass
            self.master_fd = None

        if self.proc is not None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=1.0)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
            self.proc = None

        # Notifica inscritos sobre encerramento
        for q in list(self.subscribers):
            try:
                q.put_nowait(b"\r\n\x1b[33m[Sess\xc3\xa3o de terminal encerrada]\x1b[0m\r\n")
            except Exception:
                pass
        self.subscribers.clear()


class PtyManager:
    """Gerencia múltiplas sessões PTY identificadas por ID."""

    def __init__(self):
        self._sessions: Dict[str, PtySession] = {}

    def get_or_create(
        self,
        session_id: str = "default",
        cols: int = 80,
        rows: int = 24,
        cwd: Optional[str] = None,
        loop: Optional[asyncio.AbstractEventLoop] = None
    ) -> PtySession:
        self.cleanup_dead()
        session = self._sessions.get(session_id)
        if session is None or not session.is_alive:
            session = PtySession(session_id=session_id, cols=cols, rows=rows, cwd=cwd)
            session.start(loop=loop)
            self._sessions[session_id] = session
        else:
            # Se já existe e os tamanhos mudaram, atualiza
            session.resize(cols, rows)
        return session

    def kill(self, session_id: str) -> None:
        session = self._sessions.pop(session_id, None)
        if session:
            session.close()

    def cleanup_dead(self) -> None:
        dead_keys = [k for k, s in self._sessions.items() if not s.is_alive]
        for k in dead_keys:
            s = self._sessions.pop(k, None)
            if s:
                s.close()


# Instância global do gerenciador PTY
pty_manager = PtyManager()
