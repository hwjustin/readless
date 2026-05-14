from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, time
from pathlib import Path
from typing import Any, Optional

try:
    import yaml  # type: ignore
    _HAVE_YAML = True
except ImportError:
    yaml = None  # type: ignore
    _HAVE_YAML = False


def _parse_yaml(text: str) -> dict:
    """Minimal YAML reader for readless's config shape.

    Supports: top-level `key: value`, one level of nested mapping (`quiet_hours:`),
    inline comments, single/double quoted strings, and bare scalars (true/false/
    numbers/strings). Falls back here when pyyaml isn't installed, so the default
    `system` TTS backend has zero pip dependencies.
    """
    if _HAVE_YAML:
        return yaml.safe_load(text) or {}
    out: dict[str, Any] = {}
    current_map: Optional[dict] = None
    current_indent = -1
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()
        if ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        key = key.strip()
        value = value.strip()
        if indent == 0:
            current_indent = -1
            current_map = None
            if not value:
                out[key] = {}
                current_map = out[key]
                current_indent = indent
            else:
                out[key] = _coerce_scalar(value)
        else:
            if current_map is None or indent <= current_indent:
                continue
            current_map[key] = _coerce_scalar(value)
    return out


def _coerce_scalar(s: str) -> Any:
    if not s:
        return ""
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'"):
        return s[1:-1]
    low = s.lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    if low in ("null", "~", ""):
        return None
    try:
        if "." in s or "e" in low:
            return float(s)
        return int(s)
    except ValueError:
        return s

CONFIG_DIR = Path.home() / ".readless"
CONFIG_PATH = CONFIG_DIR / "config.yaml"

VALID_PROVIDERS = ("system", "openai", "elevenlabs")

DEFAULT_YAML = """\
tts_provider: system      # system | openai | elevenlabs

# --- system (OS-native TTS, no API key needed) ---
# macOS uses `say`, Linux uses `espeak-ng`, Windows uses PowerShell SAPI.
# Leave system_voice empty for platform default, or e.g. "Tingting" (macOS zh).
system_voice: ""

# --- OpenAI TTS ---
openai_api_key: ""        # or set OPENAI_API_KEY env var
voice: alloy              # alloy / echo / fable / onyx / nova / shimmer

# --- ElevenLabs TTS ---
elevenlabs_api_key: ""    # or set ELEVENLABS_API_KEY env var
elevenlabs_voice_id: "JBFqnCBsd6RMkjVDRZzb"
elevenlabs_model_id: "eleven_flash_v2_5"

speed: 1.1                # 1.0 - 1.3 (openai only)
language_hint: zh
summary_max_chars: 80     # cap length of spoken per-turn summary

quiet_hours:
  start: "23:00"          # per-turn summaries silenced inside this window
  end: "08:00"            # notifications always play

log_path: ~/.readless/log.jsonl
"""


@dataclass
class Config:
    tts_provider: str = "system"
    system_voice: str = ""
    openai_api_key: str = ""
    voice: str = "alloy"
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = "JBFqnCBsd6RMkjVDRZzb"
    elevenlabs_model_id: str = "eleven_flash_v2_5"
    speed: float = 1.1
    language_hint: str = "zh"
    summary_max_chars: int = 80
    quiet_start: Optional[time] = time(23, 0)
    quiet_end: Optional[time] = time(8, 0)
    log_path: Path = Path("~/.readless/log.jsonl").expanduser()

    @property
    def has_tts_key(self) -> bool:
        if self.tts_provider == "system":
            return True
        if self.tts_provider == "elevenlabs":
            return bool(self.elevenlabs_api_key)
        return bool(self.openai_api_key)

    def in_quiet_hours(self, now: Optional[datetime] = None) -> bool:
        if self.quiet_start is None or self.quiet_end is None:
            return False
        now = now or datetime.now()
        t = now.time()
        if self.quiet_start <= self.quiet_end:
            return self.quiet_start <= t < self.quiet_end
        return t >= self.quiet_start or t < self.quiet_end


def _parse_time(s: Optional[str]) -> Optional[time]:
    if not s:
        return None
    hh, mm = s.split(":")
    return time(int(hh), int(mm))


def _ensure_config_file() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(DEFAULT_YAML)


def load_config() -> Config:
    _ensure_config_file()
    raw = _parse_yaml(CONFIG_PATH.read_text())

    qh = raw.get("quiet_hours") or {}
    key = os.environ.get("OPENAI_API_KEY") or raw.get("openai_api_key") or ""
    el_key = os.environ.get("ELEVENLABS_API_KEY") or raw.get("elevenlabs_api_key") or ""

    provider = (raw.get("tts_provider") or "system").lower().strip()
    if provider not in VALID_PROVIDERS:
        provider = "system"

    return Config(
        tts_provider=provider,
        system_voice=str(raw.get("system_voice", "") or ""),
        openai_api_key=key,
        voice=raw.get("voice", "alloy"),
        elevenlabs_api_key=el_key,
        elevenlabs_voice_id=raw.get("elevenlabs_voice_id", "JBFqnCBsd6RMkjVDRZzb"),
        elevenlabs_model_id=raw.get("elevenlabs_model_id", "eleven_flash_v2_5"),
        speed=float(raw.get("speed", 1.1)),
        language_hint=raw.get("language_hint", "zh"),
        summary_max_chars=int(raw.get("summary_max_chars", 80)),
        quiet_start=_parse_time(qh.get("start")),
        quiet_end=_parse_time(qh.get("end")),
        log_path=Path(raw.get("log_path", "~/.readless/log.jsonl")).expanduser(),
    )
