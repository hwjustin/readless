"""Dispatch a Claude Code hook payload to TTS.

Called from the detached child process spawned by hooks/readless_hook.py.
This module must never let an exception escape — log everything to the
JSONL file, swallow the rest.
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any

from . import logger
from .config import load_config
from .tts import speak


def run(payload: dict) -> None:
    try:
        cfg = load_config()
        logger.configure(cfg.log_path)
    except Exception as e:
        _safe_log("config_error", repr(e))
        return

    event = (payload.get("hook_event_name") or "").strip()
    try:
        if event == "Stop":
            _handle_stop(payload, cfg)
        elif event == "Notification":
            _handle_notification(payload, cfg)
        else:
            _safe_log("ignored_event", event)
    except Exception as e:
        _safe_log("dispatch_error", f"{event}: {e!r}")


def _handle_stop(payload: dict, cfg) -> None:
    if cfg.in_quiet_hours():
        _safe_log("stop_quiet", "")
        return
    text = _extract_last_assistant_text(payload)
    if not text:
        _safe_log("stop_no_text", "")
        return
    text = _shorten(text, cfg.summary_max_chars)
    logger.log_event("stop", text)
    asyncio.run(speak(text, cfg))


def _handle_notification(payload: dict, cfg) -> None:
    # Notifications bypass quiet hours — they signal the user is needed NOW.
    message = (payload.get("message") or payload.get("title") or "需要你的输入").strip()
    message = _shorten(message, cfg.summary_max_chars)
    logger.log_event("notification", message)
    asyncio.run(speak(message, cfg, interrupt=True))


def _extract_last_assistant_text(payload: dict) -> str:
    # Newer Claude Code payloads include `last_assistant_message` directly.
    direct = payload.get("last_assistant_message")
    if isinstance(direct, str) and direct.strip():
        return direct
    # Otherwise read the transcript JSONL and find the most recent assistant text.
    path = payload.get("transcript_path")
    if not path:
        return ""
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except Exception:
        return ""
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except Exception:
            continue
        text = _text_from_entry(entry)
        if text:
            return text
    return ""


def _text_from_entry(entry: dict) -> str:
    # Claude Code transcript entries vary by version; we handle a few shapes.
    if entry.get("type") != "assistant" and entry.get("role") != "assistant":
        msg = entry.get("message")
        if not isinstance(msg, dict):
            return ""
        if msg.get("role") != "assistant":
            return ""
        entry = msg
    content: Any = entry.get("content") or entry.get("message", {}).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                t = block.get("text") or ""
                if t:
                    parts.append(t)
        return "\n".join(parts)
    return ""


_CODE_BLOCK = re.compile(r"```.*?```", re.DOTALL)
_TOOL_BLOCK = re.compile(r"<[a-z_]+>.*?</[a-z_]+>", re.DOTALL | re.IGNORECASE)


def _shorten(text: str, limit: int) -> str:
    # Strip code blocks and XML-ish tool tags before speaking — they sound terrible.
    text = _CODE_BLOCK.sub(" ", text)
    text = _TOOL_BLOCK.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 1)].rstrip() + "…"


def _safe_log(kind: str, msg: str) -> None:
    try:
        logger.log_event(kind, msg)
    except Exception:
        pass
