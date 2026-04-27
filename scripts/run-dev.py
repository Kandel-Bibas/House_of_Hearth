#!/usr/bin/env python3
"""Supervisor that runs uvicorn + Vite together.

Ctrl-C kills both. Output from each process is prefixed.
"""
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VENV = REPO_ROOT / ".venv"
FRONTEND = REPO_ROOT / "frontend"


def stream(proc: subprocess.Popen, prefix: str, color: str):
    for line in iter(proc.stdout.readline, b""):
        sys.stdout.write(f"\033[{color}m[{prefix}]\033[0m {line.decode(errors='replace')}")
        sys.stdout.flush()


def main():
    if not (FRONTEND / "node_modules").exists():
        print("frontend/node_modules missing — run `cd frontend && pnpm install` (or `npm install`) first.")
        sys.exit(1)

    backend = subprocess.Popen(
        [str(VENV / "bin" / "uvicorn"), "api.main:app",
         "--host", "127.0.0.1", "--port", "8000", "--reload"],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    npm_or_pnpm = "pnpm" if (FRONTEND / "pnpm-lock.yaml").exists() else "npm"
    frontend = subprocess.Popen(
        [npm_or_pnpm, "run", "dev"],
        cwd=FRONTEND,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    threading.Thread(target=stream, args=(backend, "api", "36"), daemon=True).start()
    threading.Thread(target=stream, args=(frontend, "ui", "32"), daemon=True).start()

    def shutdown(signum, frame):
        for p in (backend, frontend):
            try:
                p.send_signal(signal.SIGTERM)
            except ProcessLookupError:
                pass
        time.sleep(1)
        for p in (backend, frontend):
            if p.poll() is None:
                p.kill()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Wait for either to exit; if one dies, kill the other.
    while True:
        if backend.poll() is not None:
            print(f"[api] exited with {backend.returncode}; stopping ui")
            shutdown(None, None)
        if frontend.poll() is not None:
            print(f"[ui] exited with {frontend.returncode}; stopping api")
            shutdown(None, None)
        time.sleep(0.5)


if __name__ == "__main__":
    main()
