import asyncio
import errno
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from config import load_config

REPO_ROOT = Path(__file__).resolve().parent.parent
IS_WINDOWS = sys.platform == "win32"

# Detecção de recursos PTY por plataforma
HAS_POSIX_PTY = False
HAS_WINPTY = False

if IS_WINDOWS:
    try:
        from winpty import PtyProcess
        HAS_WINPTY = True
    except ImportError:
        HAS_WINPTY = False
else:
    try:
        import pty
        import termios
        import fcntl
        import struct
        HAS_POSIX_PTY = True
    except ImportError:
        HAS_POSIX_PTY = False


def get_default_windows_shell() -> List[str]:
    """Retorna os argumentos para lançar a melhor shell do Windows disponível."""
    cfg = load_config()
    configured = cfg.get("terminal", {}).get("windows_shell", "").lower()

    if configured == "cmd":
        return ["cmd.exe"]

    if configured in ("bash", "git-bash"):
        git_bash = r"C:\Program Files\Git\bin\bash.exe"
        if os.path.exists(git_bash):
            return [git_bash, "--login", "-i"]
        sh = shutil.which("bash.exe") or shutil.which("bash")
        if sh:
            return [sh, "--login", "-i"]

    # 1. PowerShell 7 (pwsh)
    pwsh = shutil.which("pwsh.exe") or shutil.which("pwsh")
    if pwsh:
        return [pwsh, "-ExecutionPolicy", "Bypass", "-NoLogo"]

    # 2. Windows PowerShell 5.1
    ps = shutil.which("powershell.exe")
    if ps:
        return [ps, "-ExecutionPolicy", "Bypass", "-NoLogo"]
    sys_ps = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
    if os.path.exists(sys_ps):
        return [sys_ps, "-ExecutionPolicy", "Bypass", "-NoLogo"]

    # 3. cmd.exe
    return ["cmd.exe"]


class PtySession:
    """
    Representa uma sessão interativa de terminal.
    - No Linux/macOS: Utiliza o módulo nativo pty (openpty).
    - No Windows: Utiliza ConPTY (via pywinpty) ou fallback com pipes assíncronos.
    """

    def __init__(self, session_id: str, cols: int = 80, rows: int = 24, cwd: Optional[str] = None):
        self.session_id = session_id
        self.cols = cols
        self.rows = rows
        self.cwd = cwd or str(REPO_ROOT)
        self.master_fd: Optional[int] = None
        self.proc: Optional[subprocess.Popen] = None
        self.winpty_proc: Optional[Any] = None  # Se rodando no Windows com pywinpty
        self.subscribers: Set[asyncio.Queue] = set()
        self.history = bytearray()
        self.max_history = 100_000  # ~100KB de buffer circular para reconexão
        self._closed = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    @property
    def is_alive(self) -> bool:
        if self._closed:
            return False
        if IS_WINDOWS and HAS_WINPTY and self.winpty_proc:
            return self.winpty_proc.isalive()
        if self.proc is not None:
            return self.proc.poll() is None
        return False

    def start(self, loop: Optional[asyncio.AbstractEventLoop] = None) -> bool:
        self._loop = loop or asyncio.get_event_loop()
        work_dir = self.cwd if os.path.isdir(self.cwd) else str(Path.home())

        env = os.environ.copy()
        env["TERM"] = "xterm-256color"
        env["COLORTERM"] = "truecolor"
        env["LANG"] = env.get("LANG", "en_US.UTF-8")

        # Caminhos padrão do usuário no Linux e Windows
        if IS_WINDOWS:
            extra_paths = [
                str(Path.home() / "AppData" / "Roaming" / "npm"),
                str(Path.home() / ".local" / "bin"),
                str(Path.home() / "bin")
            ]
        else:
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
                curr_path = f"{p}{os.pathsep}{curr_path}"
        env["PATH"] = curr_path

        # 1. Modo Windows
        if IS_WINDOWS:
            shell_argv = get_default_windows_shell()

            if HAS_WINPTY:
                # Windows com suporte completo a ConPTY (pywinpty)
                try:
                    from winpty import PtyProcess
                    self.winpty_proc = PtyProcess.spawn(
                        argv=shell_argv,
                        dimensions=(self.rows, self.cols),
                        cwd=work_dir,
                        env=env
                    )
                    threading.Thread(target=self._winpty_read_loop, daemon=True).start()
                    return True
                except Exception as e:
                    print(f"[agent-remote] Erro ao iniciar winpty: {e}, usando fallback.")

            # Fallback Windows: Subprocess com Pipes
            try:
                self.proc = subprocess.Popen(
                    shell_argv,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    cwd=work_dir,
                    env=env,
                    bufsize=0
                )
                # Envia dica amigável
                banner = (
                    b"\r\n\x1b[36m[Agent-Remote Windows]\x1b[0m Sessao iniciada em "
                    + work_dir.encode("utf-8")
                    + b"\r\n\x1b[33m[Dica]\x1b[0m Execute \x1b[1mpip install pywinpty\x1b[0m no PC para suporte completo a emulador de terminal no Windows.\r\n\r\n"
                )
                self.history.extend(banner)
                threading.Thread(target=self._pipe_read_loop, daemon=True).start()
                return True
            except Exception as e:
                print(f"[agent-remote] Erro ao iniciar subprocess no Windows: {e}")
                return False

        # 2. Modo Linux / macOS (Nativo)
        if not HAS_POSIX_PTY:
            return False

        import fcntl
        import pty
        import struct
        import termios

        master, slave = pty.openpty()
        self.master_fd = master

        try:
            fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", self.rows, self.cols, 0, 0))
        except Exception:
            pass

        try:
            fcntl.fcntl(master, fcntl.F_SETFL, os.O_NONBLOCK)
        except Exception:
            pass

        shell = os.environ.get("SHELL", "/bin/bash")
        if not os.path.exists(shell):
            shell = "/bin/sh"

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
            os.close(slave)

        self._loop.add_reader(self.master_fd, self._posix_handle_read)
        return True

    def _winpty_read_loop(self) -> None:
        """Loop de leitura em thread para o ConPTY do Windows."""
        while self.is_alive and not self._closed:
            try:
                data = self.winpty_proc.read(4096)
                if not data:
                    break
                chunk = data.encode("utf-8", errors="replace") if isinstance(data, str) else data
                self._dispatch_chunk(chunk)
            except Exception:
                break
        self.close()

    def _pipe_read_loop(self) -> None:
        """Loop de leitura para fallback no Windows."""
        while self.is_alive and not self._closed:
            try:
                chunk = self.proc.stdout.read(1024)
                if not chunk:
                    break
                self._dispatch_chunk(chunk)
            except Exception:
                break
        self.close()

    def _posix_handle_read(self) -> None:
        """Manipulador não-bloqueante para Linux/macOS."""
        if self.master_fd is None or self._closed:
            return

        try:
            chunk = os.read(self.master_fd, 4096)
            if not chunk:
                self.close()
                return
            self._dispatch_chunk(chunk)
        except OSError as e:
            if e.errno in (errno.EIO, errno.EBADF):
                self.close()
            elif e.errno not in (errno.EAGAIN, errno.EWOULDBLOCK):
                self.close()

    def _dispatch_chunk(self, chunk: bytes) -> None:
        self.history.extend(chunk)
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]

        for q in list(self.subscribers):
            try:
                if self._loop and self._loop.is_running():
                    self._loop.call_soon_threadsafe(q.put_nowait, chunk)
                else:
                    q.put_nowait(chunk)
            except Exception:
                pass

    def write(self, data: bytes) -> None:
        if self._closed:
            return

        if IS_WINDOWS:
            if HAS_WINPTY and self.winpty_proc:
                try:
                    self.winpty_proc.write(data.decode("utf-8", errors="replace"))
                except Exception:
                    pass
            elif self.proc and self.proc.stdin:
                try:
                    self.proc.stdin.write(data)
                    self.proc.stdin.flush()
                except Exception:
                    pass
        else:
            if self.master_fd is not None:
                try:
                    os.write(self.master_fd, data)
                except Exception:
                    pass

    def resize(self, cols: int, rows: int) -> None:
        if self._closed:
            return
        self.cols = max(10, cols)
        self.rows = max(4, rows)

        if IS_WINDOWS:
            if HAS_WINPTY and self.winpty_proc:
                try:
                    self.winpty_proc.set_winsize(self.rows, self.cols)
                except Exception:
                    pass
        else:
            if self.master_fd is not None and HAS_POSIX_PTY:
                import fcntl
                import struct
                import termios
                try:
                    fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, struct.pack("HHHH", self.rows, self.cols, 0, 0))
                except Exception:
                    pass

    def subscribe(self, queue: asyncio.Queue) -> None:
        self.subscribers.add(queue)
        if self.history:
            queue.put_nowait(bytes(self.history))

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self.subscribers.discard(queue)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True

        if IS_WINDOWS:
            if self.winpty_proc is not None:
                try:
                    self.winpty_proc.terminate(force=True)
                except Exception:
                    pass
                self.winpty_proc = None
        else:
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

        for q in list(self.subscribers):
            try:
                msg = b"\r\n\x1b[33m[Sessao de terminal encerrada]\x1b[0m\r\n"
                if self._loop and self._loop.is_running():
                    self._loop.call_soon_threadsafe(q.put_nowait, msg)
                else:
                    q.put_nowait(msg)
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
