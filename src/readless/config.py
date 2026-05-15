from __future__ import annotations

import os
from dataclasses import dataclass, field
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
    `edge` TTS backend has zero extra YAML dependencies.
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

VALID_PROVIDERS = ("edge", "openai", "elevenlabs", "system")

DEFAULT_YAML = """\
# readless config — auto-created on first run.
# Default backend `edge` uses Microsoft's free online TTS (no API key needed).

tts_provider: edge        # edge | openai | elevenlabs | system

# --- edge: free, online, natural bilingual (recommended default) ---
edge_voice: zh-CN-XiaoxiaoNeural   # handles zh+en code-switching well
                                    # other good picks:
                                    #   zh-CN-YunxiNeural    (male, zh)
                                    #   zh-CN-YunyangNeural  (male, news anchor)
                                    #   en-US-AriaNeural     (female, en)
edge_rate: "+0%"          # "-50%" to "+100%"

# --- openai: needs OPENAI_API_KEY (use `readless-setkey openai`) ---
openai_api_key: ""
voice: alloy              # alloy / echo / fable / onyx / nova / shimmer
speed: 1.1                # 1.0 - 1.3

# --- elevenlabs: needs ELEVENLABS_API_KEY (use `readless-setkey elevenlabs`) ---
elevenlabs_api_key: ""
elevenlabs_voice_id: "JBFqnCBsd6RMkjVDRZzb"
elevenlabs_model_id: "eleven_flash_v2_5"

# --- system: OS-native TTS, offline fallback when edge can't reach network ---
# macOS `say`, Linux `espeak-ng`, Windows SAPI. Empty = platform default voice.
system_voice: ""

language_hint: zh

# quiet_hours disabled by default. Uncomment to silence speak_summary/speak_status
# in a window (speak_blocker always plays through quiet hours):
# quiet_hours:
#   start: "23:00"
#   end: "08:00"

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
    tts_provider: str = "edge"
    edge_voice: str = "zh-CN-XiaoxiaoNeural"
    edge_rate: str = "+0%"
    openai_api_key: str = ""
    voice: str = "alloy"
    speed: float = 1.1
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = "JBFqnCBsd6RMkjVDRZzb"
    elevenlabs_model_id: str = "eleven_flash_v2_5"
    system_voice: str = ""
    language_hint: str = "zh"
    quiet_start: Optional[time] = None
    quiet_end: Optional[time] = None
    tools: ToolToggles = field(default_factory=ToolToggles)
    status_throttle_seconds: int = 60
    log_path: Path = Path("~/.readless/log.jsonl").expanduser()

    @property
    def has_tts_key(self) -> bool:
        if self.tts_provider in ("edge", "system"):
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


def ensure_config_file() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(DEFAULT_YAML)
        try:
            CONFIG_PATH.chmod(0o600)
        except OSError:
            pass


def load_config() -> Config:
    ensure_config_file()
    raw = _parse_yaml(CONFIG_PATH.read_text())

    qh = raw.get("quiet_hours") or {}
    tools_raw = raw.get("tools") or {}
    key = os.environ.get("OPENAI_API_KEY") or raw.get("openai_api_key") or ""
    el_key = os.environ.get("ELEVENLABS_API_KEY") or raw.get("elevenlabs_api_key") or ""

    provider = (raw.get("tts_provider") or "edge").lower().strip()
    if provider not in VALID_PROVIDERS:
        provider = "edge"

    return Config(
        tts_provider=provider,
        edge_voice=str(raw.get("edge_voice", "") or "zh-CN-XiaoxiaoNeural"),
        edge_rate=str(raw.get("edge_rate", "") or "+0%"),
        openai_api_key=key,
        voice=raw.get("voice", "alloy"),
        speed=float(raw.get("speed", 1.1)),
        elevenlabs_api_key=el_key,
        elevenlabs_voice_id=raw.get("elevenlabs_voice_id", "JBFqnCBsd6RMkjVDRZzb"),
        elevenlabs_model_id=raw.get("elevenlabs_model_id", "eleven_flash_v2_5"),
        system_voice=str(raw.get("system_voice", "") or ""),
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
