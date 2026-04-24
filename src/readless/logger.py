from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

_log_path: Path = Path("~/.readless/log.jsonl").expanduser()


def configure(path: Path) -> None:
    global _log_path
    _log_path = path


def log_event(kind: str, headline: str, details: str = "") -> None:
    try:
        _log_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
            "kind": kind,
            "headline": headline,
            "details": details,
        }
        with _log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[readless] log write failed: {e}", file=sys.stderr)
