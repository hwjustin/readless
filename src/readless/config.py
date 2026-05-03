from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, time
from pathlib import Path
from typing import Optional

import yaml

CONFIG_DIR = Path.home() / ".readless"
CONFIG_PATH = CONFIG_DIR / "config.yaml"

DEFAULT_YAML = """\
tts_provider: openai      # openai | elevenlabs

openai_api_key: ""        # or set OPENAI_API_KEY env var
voice: alloy              # alloy / echo / fable / onyx / nova / shimmer

# Used when tts_provider: elevenlabs (or set ELEVENLABS_API_KEY env var)
elevenlabs_api_key: ""
elevenlabs_voice_id: "JBFqnCBsd6RMkjVDRZzb"   # default: "George"
elevenlabs_model_id: "eleven_flash_v2_5"

speed: 1.1                # 1.0 - 1.3 (openai only; elevenlabs ignores)
language_hint: zh
quiet_hours:
  start: "23:00"
  end: "08:00"
tools:
  speak_status: true
  speak_summary: true
  speak_blocker: true
status_throttle_seconds: 60
log_path: ~/.readless/log.jsonl
"""


@dataclass
class ToolToggles:
    speak_status: bool = True
    speak_summary: bool = True
    speak_blocker: bool = True


@dataclass
class Config:
    tts_provider: str = "openai"
    openai_api_key: str = ""
    voice: str = "alloy"
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = "JBFqnCBsd6RMkjVDRZzb"
    elevenlabs_model_id: str = "eleven_flash_v2_5"
    speed: float = 1.1
    language_hint: str = "zh"
    quiet_start: Optional[time] = time(23, 0)
    quiet_end: Optional[time] = time(8, 0)
    tools: ToolToggles = field(default_factory=ToolToggles)
    status_throttle_seconds: int = 60
    log_path: Path = Path("~/.readless/log.jsonl").expanduser()

    @property
    def has_tts_key(self) -> bool:
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
    raw = yaml.safe_load(CONFIG_PATH.read_text()) or {}

    qh = raw.get("quiet_hours") or {}
    tools_raw = raw.get("tools") or {}

    key = os.environ.get("OPENAI_API_KEY") or raw.get("openai_api_key") or ""
    el_key = os.environ.get("ELEVENLABS_API_KEY") or raw.get("elevenlabs_api_key") or ""

    provider = (raw.get("tts_provider") or "openai").lower().strip()
    if provider not in ("openai", "elevenlabs"):
        provider = "openai"

    return Config(
        tts_provider=provider,
        openai_api_key=key,
        voice=raw.get("voice", "alloy"),
        elevenlabs_api_key=el_key,
        elevenlabs_voice_id=raw.get("elevenlabs_voice_id", "JBFqnCBsd6RMkjVDRZzb"),
        elevenlabs_model_id=raw.get("elevenlabs_model_id", "eleven_flash_v2_5"),
        speed=float(raw.get("speed", 1.1)),
        language_hint=raw.get("language_hint", "zh"),
        quiet_start=_parse_time(qh.get("start")),
        quiet_end=_parse_time(qh.get("end")),
        tools=ToolToggles(
            speak_status=bool(tools_raw.get("speak_status", True)),
            speak_summary=bool(tools_raw.get("speak_summary", True)),
            speak_blocker=bool(tools_raw.get("speak_blocker", True)),
        ),
        status_throttle_seconds=int(raw.get("status_throttle_seconds", 60)),
        log_path=Path(raw.get("log_path", "~/.readless/log.jsonl")).expanduser(),
    )
