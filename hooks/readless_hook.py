#!/usr/bin/env python3
"""readless plugin entry point for Claude Code hooks.

Sealed-stdio contract — copied from open-vibe-island's fail-open pattern:
  * always exit 0 (no exit(non-zero) anywhere)
  * top-level try/except: pass swallows every exception
  * stdout stays empty (Stop / Notification need no directive JSON)
  * real TTS work happens in a detached child process, fully disconnected
    from Claude Code's stdio, so nothing can leak back to the terminal
"""
from __future__ import annotations

import json
import os
import sys


def _try_import_runner():
    """Import the hook runner. Walks up to find a sibling src/ if not on path."""
    try:
        from readless.hook_runner import run  # type: ignore
        return run
    except ImportError:
        pass
    here = os.path.dirname(os.path.abspath(__file__))
    candidate = os.path.normpath(os.path.join(here, "..", "src"))
    if os.path.isdir(candidate):
        sys.path.insert(0, candidate)
        try:
            from readless.hook_runner import run  # type: ignore
            return run
        except ImportError:
            return None
    return None


def _detach_and_run(payload: dict) -> None:
    if sys.platform == "win32":
        # Windows has no fork; relaunch self in a new session as a child,
        # with stdio fully redirected to NUL.
        import subprocess
        DEVNULL = subprocess.DEVNULL
        subprocess.Popen(
            [sys.executable, os.path.abspath(__file__), "--child"],
            stdin=subprocess.PIPE,
            stdout=DEVNULL,
            stderr=DEVNULL,
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            close_fds=True,
        ).stdin.write(json.dumps(payload).encode())
        return

    pid = os.fork()
    if pid != 0:
        return  # parent exits immediately
    # --- child ---
    try:
        os.setsid()
    except Exception:
        pass
    try:
        devnull = os.open(os.devnull, os.O_RDWR)
        for fd in (0, 1, 2):
            try:
                os.dup2(devnull, fd)
            except Exception:
                pass
        os.close(devnull)
    except Exception:
        pass
    try:
        run = _try_import_runner()
        if run is not None:
            run(payload)
    except Exception:
        pass
    os._exit(0)


def _child_main() -> None:
    """Windows child entry: read payload JSON from stdin and run."""
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        run = _try_import_runner()
        if run is not None:
            run(payload)
    except Exception:
        pass


def main() -> None:
    try:
        if len(sys.argv) > 1 and sys.argv[1] == "--child":
            _child_main()
            return
        raw = sys.stdin.buffer.read()
        if not raw:
            return
        payload = json.loads(raw)
        _detach_and_run(payload)
    except Exception:
        # Never let an exception reach stderr — that would surface in the UI.
        pass


if __name__ == "__main__":
    main()
    sys.exit(0)
