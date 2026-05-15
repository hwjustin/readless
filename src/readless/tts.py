from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
import traceback
from typing import Iterator

from .config import Config

SAMPLE_RATE = 24000
CHANNELS = 1
CHUNK_BYTES = 4096

_speech_lock = asyncio.Lock()
_cancel_flag = asyncio.Event()
_active_stream = None
_active_proc: subprocess.Popen | None = None


def _warn(msg: str) -> None:
    print(f"[readless] {msg}", file=sys.stderr, flush=True)


async def speak(text: str, cfg: Config, interrupt: bool = False) -> str:
    if cfg.tts_provider == "edge":
        if interrupt:
            _stop_active_proc()
        result = await _speak_edge(text, cfg)
        if result == "edge_failed":
            _warn("edge-tts failed, falling back to system TTS")
            return await asyncio.to_thread(_speak_system, text, cfg)
        return result

    if cfg.tts_provider == "system":
        if interrupt:
            _stop_active_proc()
        return await asyncio.to_thread(_speak_system, text, cfg)

    if not cfg.has_tts_key:
        _warn(f"(no-key, provider={cfg.tts_provider}) {text}")
        return "tts_no_key_logged"

    if interrupt:
        _cancel_flag.set()
        global _active_stream
        if _active_stream is not None:
            try:
                _active_stream.abort()
            except Exception:
                pass

    async with _speech_lock:
        _cancel_flag.clear()
        try:
            return await asyncio.to_thread(_play_pcm, _iter_pcm(text, cfg))
        except Exception as e:
            traceback.print_exc(file=sys.stderr)
            _warn(f"TTS failed ({e.__class__.__name__}): {text}")
            return "tts_failed_but_logged"


def _stop_active_proc() -> None:
    global _active_proc
    if _active_proc is not None and _active_proc.poll() is None:
        try:
            _active_proc.terminate()
        except Exception:
            pass


# --- edge-tts (default) -----------------------------------------------------

async def _speak_edge(text: str, cfg: Config) -> str:
    try:
        import edge_tts  # type: ignore
    except ImportError:
        _warn("edge-tts not installed; `pip install edge-tts` or switch tts_provider")
        return "edge_failed"

    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    tmp.close()
    try:
        communicate = edge_tts.Communicate(text, voice=cfg.edge_voice, rate=cfg.edge_rate)
        try:
            await communicate.save(tmp.name)
        except Exception as e:
            _warn(f"edge-tts synth failed ({e.__class__.__name__}: {e})")
            return "edge_failed"
        return await asyncio.to_thread(_play_audio_file, tmp.name)
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def _play_audio_file(path: str) -> str:
    global _active_proc
    _stop_active_proc()
    cmd = _audio_player_cmd(path)
    if cmd is None:
        _warn("no audio player available; install mpg123 / ffplay / mpv")
        return "audio_player_unavailable"
    try:
        _active_proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _active_proc.wait()
        return "spoken"
    except Exception as e:
        _warn(f"audio playback failed ({e.__class__.__name__}: {e})")
        return "tts_failed_but_logged"


def _audio_player_cmd(path: str) -> list[str] | None:
    if sys.platform == "darwin":
        if shutil.which("afplay"):
            return ["afplay", path]
        return None
    if sys.platform.startswith("linux"):
        if shutil.which("mpg123"):
            return ["mpg123", "-q", path]
        if shutil.which("ffplay"):
            return ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path]
        if shutil.which("mpv"):
            return ["mpv", "--really-quiet", path]
        if shutil.which("paplay"):
            return ["paplay", path]
        return None
    if sys.platform == "win32":
        # Best-effort: PowerShell + System.Media.SoundPlayer (WAV only), so fall back
        # to invoking the default associated app via `start`.
        ps = (
            "Add-Type -AssemblyName presentationCore;"
            "$p = New-Object System.Windows.Media.MediaPlayer;"
            f"$p.Open([uri]'{path}');"
            "$p.Play();"
            "Start-Sleep -Seconds 1;"
            "while ($p.NaturalDuration.HasTimeSpan -eq $false) { Start-Sleep -Milliseconds 100 }"
            "Start-Sleep -Seconds ([int]$p.NaturalDuration.TimeSpan.TotalSeconds + 1);"
        )
        return ["powershell", "-NoProfile", "-Command", ps]
    return None


# --- system (offline fallback) ---------------------------------------------

def _speak_system(text: str, cfg: Config) -> str:
    global _active_proc
    _stop_active_proc()
    try:
        cmd = _system_cmd(text, cfg)
    except RuntimeError as e:
        _warn(f"system tts unavailable: {e}")
        return "system_unavailable_logged"
    try:
        _active_proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _active_proc.wait()
        return "spoken"
    except Exception as e:
        _warn(f"system tts failed ({e.__class__.__name__}): {text}")
        return "tts_failed_but_logged"


def _system_cmd(text: str, cfg: Config) -> list[str]:
    voice = (cfg.system_voice or "").strip()
    if sys.platform == "darwin":
        if not shutil.which("say"):
            raise RuntimeError("`say` not found")
        cmd = ["say"]
        if voice:
            cmd += ["-v", voice]
        cmd.append(text)
        return cmd
    if sys.platform.startswith("linux"):
        binary = shutil.which("espeak-ng") or shutil.which("espeak")
        if not binary:
            raise RuntimeError("`espeak-ng` not found; install with: apt install espeak-ng")
        cmd = [binary, "-v", voice or (cfg.language_hint or "zh"), text]
        return cmd
    if sys.platform == "win32":
        safe = text.replace('"', '`"')
        ps = (
            "Add-Type -AssemblyName System.Speech;"
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
            + (f"$s.SelectVoice('{voice}');" if voice else "")
            + f'$s.Speak("{safe}")'
        )
        return ["powershell", "-NoProfile", "-Command", ps]
    raise RuntimeError(f"unsupported platform: {sys.platform}")


# --- openai / elevenlabs (opt-in, PCM streaming via sounddevice) -----------

def _iter_pcm(text: str, cfg: Config) -> Iterator[bytes]:
    if cfg.tts_provider == "elevenlabs":
        return _elevenlabs_pcm(text, cfg)
    return _openai_pcm(text, cfg)


def _openai_pcm(text: str, cfg: Config) -> Iterator[bytes]:
    from openai import OpenAI

    client = OpenAI(api_key=cfg.openai_api_key)
    with client.audio.speech.with_streaming_response.create(
        model="gpt-4o-mini-tts",
        voice=cfg.voice,
        input=text,
        response_format="pcm",
        speed=cfg.speed,
    ) as response:
        for chunk in response.iter_bytes(chunk_size=CHUNK_BYTES):
            if chunk:
                yield chunk


def _elevenlabs_pcm(text: str, cfg: Config) -> Iterator[bytes]:
    from elevenlabs.client import ElevenLabs

    client = ElevenLabs(api_key=cfg.elevenlabs_api_key)
    stream = client.text_to_speech.convert(
        voice_id=cfg.elevenlabs_voice_id,
        text=text,
        model_id=cfg.elevenlabs_model_id,
        output_format="pcm_24000",
    )
    for chunk in stream:
        if chunk:
            yield chunk


def _play_pcm(chunks: Iterator[bytes]) -> str:
    import sounddevice as sd

    global _active_stream
    stream = sd.RawOutputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="int16",
    )
    stream.start()
    _active_stream = stream
    try:
        for chunk in chunks:
            if _cancel_flag.is_set():
                return "interrupted"
            stream.write(chunk)
        return "spoken"
    finally:
        try:
            stream.stop()
            stream.close()
        except Exception:
            pass
        if _active_stream is stream:
            _active_stream = None
