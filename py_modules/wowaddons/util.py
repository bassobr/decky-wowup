"""Subprocess, hashing, download, atomic file and JSON helpers."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from typing import Callable, Dict, Iterable, List, Optional

from . import paths
from .constants import USER_AGENT


class Result:
    __slots__ = ("rc", "out", "err")

    def __init__(self, rc: int, out: str, err: str):
        self.rc, self.out, self.err = rc, out, err

    def __repr__(self) -> str:
        return f"Result(rc={self.rc})"

    @property
    def ok(self) -> bool:
        return self.rc == 0


def user_env(extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Fresh environment for child processes. Decky's PyInstaller runtime sets
    LD_LIBRARY_PATH, which breaks system binaries, so nothing is inherited."""
    uid = os.getuid()
    env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": paths.HOME,
        "USER": paths.USER,
        "LOGNAME": paths.USER,
        "LANG": "C.UTF-8",
        "XDG_RUNTIME_DIR": os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{uid}",
    }
    if extra:
        env.update(extra)
    return env


def run(cmd: List[str], timeout: float = 60, env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None, input_text: Optional[str] = None) -> Result:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           env=env if env is not None else user_env(), cwd=cwd, input=input_text)
        return Result(p.returncode, p.stdout, p.stderr)
    except FileNotFoundError as e:
        return Result(127, "", f"not found: {e}")
    except subprocess.TimeoutExpired:
        return Result(124, "", f"timeout after {timeout}s: {' '.join(cmd[:3])}")


def which(name: str) -> Optional[str]:
    return shutil.which(name, path="/usr/local/bin:/usr/bin:/bin")


# ---------------------------------------------------------------- hashing
def hash_file(path: str, algorithms: Iterable[str] = ("sha256",)) -> Dict[str, bytes]:
    hs = {a: hashlib.new(a) for a in algorithms}
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            for h in hs.values():
                h.update(chunk)
    return {a: h.digest() for a, h in hs.items()}


def sha256_file(path: str) -> str:
    return hash_file(path, ("sha256",))["sha256"].hex()


# ---------------------------------------------------------------- HTTP (curl uses the system CA store)
GITHUB_HEADERS = ["-H", "Accept: application/vnd.github+json", "-H", "X-GitHub-Api-Version: 2022-11-28"]


def curl_text(url: str, timeout: int = 20, headers: Optional[List[str]] = None) -> str:
    cmd = ["curl", "-fsSL", "--max-time", str(timeout), "-A", USER_AGENT] + (headers or []) + [url]
    r = run(cmd, timeout=timeout + 10)
    if not r.ok:
        raise RuntimeError(f"request failed (rc={r.rc}) for {url}: {r.err.strip()[:160]}")
    return r.out


def curl_json(url: str, timeout: int = 20, github: bool = True):
    return json.loads(curl_text(url, timeout, GITHUB_HEADERS if github else None))


def curl_download(url: str, dest: str, timeout: int, expected_size: Optional[int] = None,
                  on_progress: Optional[Callable[[int, Optional[int]], None]] = None) -> None:
    """Download to `dest`, reporting progress by polling the file size."""
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    if os.path.exists(dest):
        os.unlink(dest)
    cmd = ["curl", "-fsSL", "--retry", "2", "--max-time", str(timeout), "-A", USER_AGENT, "-o", dest, url]
    p = subprocess.Popen(cmd, env=user_env(), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    deadline = time.monotonic() + timeout + 15
    last = -1
    while p.poll() is None:
        if time.monotonic() > deadline:
            p.kill()
            p.wait()
            raise RuntimeError(f"download timed out: {url}")
        size = os.path.getsize(dest) if os.path.exists(dest) else 0
        if on_progress and size != last:
            on_progress(size, expected_size)
            last = size
        time.sleep(0.5)
    err = (p.stderr.read() if p.stderr else "") or ""
    if p.returncode != 0:
        raise RuntimeError(f"download failed (rc={p.returncode}): {err.strip()[:160]}")
    if on_progress:
        on_progress(os.path.getsize(dest), expected_size)


# ---------------------------------------------------------------- files
def atomic_write_bytes(path: str, data: bytes, mode: int = 0o644) -> None:
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    tmp = os.path.join(d, f".tmp-{os.getpid()}-{os.urandom(4).hex()}")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def atomic_write_text(path: str, text: str, mode: int = 0o644) -> None:
    atomic_write_bytes(path, text.encode("utf-8"), mode)


def read_json(path: str, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path: str, obj, mode: int = 0o644) -> None:
    atomic_write_text(path, json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n", mode)


# ---------------------------------------------------------------- processes
def pids_by_name(names: Iterable[str]) -> List[int]:
    """PIDs whose /proc/<pid>/comm matches one of `names` (empty on non-Linux)."""
    wanted = set(names)
    found = []
    try:
        entries = os.listdir("/proc")
    except OSError:
        return []
    for e in entries:
        if not e.isdigit():
            continue
        try:
            with open(f"/proc/{e}/comm", "r", encoding="utf-8", errors="replace") as f:
                if f.read().strip() in wanted:
                    found.append(int(e))
        except OSError:
            continue
    return found


# ---------------------------------------------------------------- misc
def new_uuid4() -> str:
    b = bytearray(os.urandom(16))
    b[6] = (b[6] & 0x0F) | 0x40
    b[8] = (b[8] & 0x3F) | 0x80
    h = b.hex()
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def human_bytes(n: Optional[float]) -> str:
    if n is None:
        return "?"
    n = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} GB"
