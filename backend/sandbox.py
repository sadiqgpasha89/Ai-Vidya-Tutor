"""Run untrusted Python (student/model code, sympy algebra) with no network, no access to app data, and hard limits.

Uses bubblewrap when installed (read-only view of just the Python installation, no network, fresh /tmp, killed with the
parent). Without it, code is limited by an AST allow-list plus resource limits - weaker, and reported as such.
"""
from __future__ import annotations

import ast
import os
import resource
import shutil
import subprocess
import sys
import tempfile

from .logs import get

log = get("sandbox")
def _probe(path: str | None) -> str | None:
    """bubblewrap is only usable if the kernel/container lets it create namespaces; test it once instead of failing later."""
    if not path:
        return None
    try:
        r = subprocess.run([path, "--unshare-all", "--die-with-parent", "--ro-bind", "/usr", "/usr", "--ro-bind", "/bin", "/bin", "--ro-bind", "/lib", "/lib", "--ro-bind", "/lib64", "/lib64",
                            "--proc", "/proc", "--dev", "/dev", "true"], capture_output=True, timeout=10)
        if r.returncode == 0:
            return path
        log.warning("bubblewrap is installed but cannot create a sandbox here (%s); falling back to restricted mode", r.stderr.decode()[:120].strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return None


BWRAP = _probe(shutil.which("bwrap"))
SAFE_IMPORTS = {"math", "cmath", "statistics", "random", "fractions", "decimal", "itertools", "functools", "collections", "string", "re",
                "datetime", "operator", "numbers", "heapq", "bisect", "textwrap", "json", "sympy", "numpy"}
BANNED_NAMES = {"open", "exec", "eval", "compile", "__import__", "input", "breakpoint", "globals", "locals", "vars", "getattr", "setattr", "delattr", "memoryview"}
MAX_OUT = 4000


def mode() -> str:
    return "bubblewrap" if BWRAP else "restricted"


def check_ast(code: str) -> str | None:
    """Reason the code is not allowed, or None."""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return f"SyntaxError: {exc.msg} (line {exc.lineno})"
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] not in SAFE_IMPORTS:
                    return f"import of '{a.name}' is not allowed here"
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] not in SAFE_IMPORTS:
                return f"import from '{node.module}' is not allowed here"
        elif isinstance(node, ast.Name) and node.id in BANNED_NAMES:
            return f"'{node.id}' is not allowed here"
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            return "dunder attributes are not allowed here"
    return None


def _limits() -> None:
    resource.setrlimit(resource.RLIMIT_CPU, (6, 6))
    resource.setrlimit(resource.RLIMIT_AS, (1024 * 1024 * 1024, 1024 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1_000_000, 1_000_000))
    os.setsid()


def _command(script_path: str) -> list[str]:
    py = sys.executable
    if not BWRAP:
        return [py, "-I", script_path]
    binds: list[str] = []
    for path in ("/usr", "/lib", "/lib64", "/bin", "/etc/ld.so.cache", sys.base_prefix, sys.prefix):
        if os.path.exists(path):
            binds += ["--ro-bind", path, path]
    return [BWRAP, "--unshare-all", "--die-with-parent", "--new-session", *binds, "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
            "--ro-bind", script_path, "/tmp/run.py", "--chdir", "/tmp", py, "-I", "/tmp/run.py"]


def run_python(code: str, timeout: float = 8.0, check: bool = True) -> dict:
    """-> {"ok": bool, "stdout": str, "stderr": str, "mode": str}"""
    if len(code) > 20000:
        return {"ok": False, "stdout": "", "stderr": "Program too long", "mode": mode()}
    if check or not BWRAP:
        problem = check_ast(code)
        if problem:
            return {"ok": False, "stdout": "", "stderr": problem, "mode": mode()}
    with tempfile.TemporaryDirectory() as tmp:
        script = os.path.join(tmp, "run.py")
        with open(script, "w") as f:
            f.write(code)
        env = {"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1", "HOME": "/tmp", "PYTHONIOENCODING": "utf-8"}
        try:
            proc = subprocess.run(_command(script), capture_output=True, text=True, timeout=timeout, preexec_fn=_limits, env=env, cwd=tmp)
        except subprocess.TimeoutExpired:
            return {"ok": False, "stdout": "", "stderr": f"Timed out after {timeout:.0f} seconds (infinite loop?)", "mode": mode()}
        except OSError as exc:
            log.warning(f"sandbox failed to start: {exc}")
            return {"ok": False, "stdout": "", "stderr": "The code runner is unavailable.", "mode": mode()}
    return {"ok": proc.returncode == 0, "stdout": proc.stdout[:MAX_OUT], "stderr": proc.stderr[-MAX_OUT:], "mode": mode()}
