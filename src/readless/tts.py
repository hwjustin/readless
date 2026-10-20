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
# Short status updates should never occupy a tool call indefinitely.
SYNTHESIS_TIMEOUT = 30.0
PLAYBACK_TIMEOUT = 120.0
PROCESS_EXIT_TIMEOUT = 2.0
MEDIA_OPEN_TIMEOUT = 10.0

_speech_lock = asyncio.Lock()
_cancel_flag = asyncio.Event()
_active_stream = None
_active_cancel: asyncio.Event | None = None
_speech_generation = 0


def _warn(msg: str) -> None:
    print(f"[readless] {msg}", file=sys.stderr, flush=True)


async def speak(text: str, cfg: Config, interrupt: bool = False) -> str:
    if cfg.tts_provider in ("edge", "system"):
        return await _speak_managed(text, cfg, interrupt)

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


class _Interrupted(Exception):
    """An explicit speech interrupt, distinct from caller cancellation."""


async def _speak_managed(text: str, cfg: Config, interrupt: bool) -> str:
    global _active_cancel, _speech_generation
    if interrupt:
        _speech_generation += 1
        if _active_cancel is not None:
            _active_cancel.set()
    generation = _speech_generation
    async with _speech_lock:
        # Discard queued updates superseded by a blocker, too.
        if generation != _speech_generation:
            return "interrupted"
        cancel = asyncio.Event()
        _active_cancel = cancel
        try:
            if cfg.tts_provider == "edge":
                result = await _speak_edge(text, cfg, cancel)
                if result != "edge_failed":
                    return result
                _warn("edge-tts failed, falling back to system TTS")
            if cancel.is_set():
                raise _Interrupted
            return await _speak_system(text, cfg, cancel)
        except _Interrupted:
            return "interrupted"
        finally:
            _active_cancel = None


async def _until_done(awaitable, cancel: asyncio.Event, timeout: float):
    """Bound an operation and stop it when this speech request is interrupted."""
    operation = asyncio.ensure_future(awaitable)
    stopped = asyncio.create_task(cancel.wait())
    try:
        done, _ = await asyncio.wait(
            (operation, stopped), timeout=timeout,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if cancel.is_set():
            raise _Interrupted
        if operation in done:
            return operation.result()
        raise asyncio.TimeoutError
    finally:
        for task in (operation, stopped):
            if not task.done():
                task.cancel()
        await asyncio.gather(operation, stopped, return_exceptions=True)


async def _terminate_process(proc: asyncio.subprocess.Process) -> None:
    """Reap the direct player process; escalate if SIGTERM is ignored."""
    if proc.returncode is not None:
        return
    for stop in (proc.terminate, proc.kill):
        try:
            stop()
        except ProcessLookupError:
            pass  # The exit notification may still need to be reaped.
        except OSError as e:
            _warn(f"could not signal audio process ({e.__class__.__name__})")
        try:
            await asyncio.wait_for(proc.wait(), PROCESS_EXIT_TIMEOUT)
            return
        except asyncio.TimeoutError:
            continue
    _warn("audio process did not exit after kill")


async def _run_process(cmd: list[str], cancel: asyncio.Event, *, stderr=None) -> str:
    if cancel.is_set():
        raise _Interrupted
    # Shield creation so cancellation cannot lose a newly spawned process.
    spawning = asyncio.create_task(asyncio.create_subprocess_exec(
        *cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=stderr if stderr is not None else subprocess.DEVNULL,
    ))
    try:
        proc = await asyncio.shield(spawning)
    except asyncio.CancelledError as cancelled:
        try:
            proc = await spawning
            await _terminate_process(proc)
        except Exception as e:
            _warn(f"cancelled audio process cleanup failed ({e.__class__.__name__})")
        raise cancelled
    try:
        code = await _until_done(proc.wait(), cancel, PLAYBACK_TIMEOUT)
        if code == 0:
            return "spoken"
        _warn(f"audio process exited with status {code}")
        return "tts_failed_but_logged"
    finally:
        # Also runs on timeout, caller cancellation and explicit interruption.
        await _terminate_process(proc)


# --- edge-tts (default) -----------------------------------------------------

async def _speak_edge(text: str, cfg: Config, cancel: asyncio.Event) -> str:
    try:
        import edge_tts  # type: ignore
    except ImportError:
        _warn("edge-tts not installed; `pip install edge-tts` or switch tts_provider")
        return "edge_failed"

    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    tmp.close()
    try:
        try:
            communicate = edge_tts.Communicate(text, voice=cfg.edge_voice, rate=cfg.edge_rate)
            await _until_done(communicate.save(tmp.name), cancel, SYNTHESIS_TIMEOUT)
        except _Interrupted:
            raise
        except Exception as e:
            _warn(f"edge-tts synth failed ({e.__class__.__name__}: {e})")
            return "edge_failed"
        result = await _play_audio_file(tmp.name, cancel)
        return "spoken" if result == "spoken" else "edge_failed"
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


async def _play_audio_file(path: str, cancel: asyncio.Event) -> str:
    cmd = _audio_player_cmd(path)
    if cmd is None:
        _warn("no audio player available; install mpg123 / ffplay / mpv")
        return "audio_player_unavailable"
    try:
        if cmd[0] == "ffplay":
            # ffplay can exit 0 on decoder/device errors. Capture error-level
            # output in a file (not a PIPE that can fill and deadlock wait()).
            with tempfile.TemporaryFile() as errors:
                result = await _run_process(cmd, cancel, stderr=errors)
                if result == "spoken" and os.fstat(errors.fileno()).st_size:
                    _warn("ffplay reported a playback error")
                    return "tts_failed_but_logged"
                return result
        return await _run_process(cmd, cancel)
    except _Interrupted:
        raise
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
            return ["ffplay", "-nodisp", "-autoexit", "-loglevel", "error", path]
        if shutil.which("mpv"):
            return ["mpv", "--really-quiet", "--no-video", "--keep-open=no", path]
        return None
    if sys.platform == "win32":
        return _powershell_cmd(_windows_audio_script(path))
    return None


def _ps_literal(value: str) -> str:
    # PowerShell single-quoted literals do not expand $, backticks or commands.
    return "'" + value.replace("'", "''") + "'"


def _powershell_cmd(script: str) -> list[str]:
    # UTF-16 avoids command-line quoting and non-ASCII text/path corruption.
    import base64

    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    return ["powershell", "-NoProfile", "-NonInteractive", "-STA", "-EncodedCommand", encoded]


def _windows_audio_script(path: str) -> str:
    # Pump WPF's dispatcher so media events can run. Completion is event-based:
    # neither missing nor incorrect NaturalDuration can cause an endless wait.
    return f"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName PresentationCore
Add-Type -AssemblyName WindowsBase
$p = New-Object System.Windows.Media.MediaPlayer
$frame = New-Object System.Windows.Threading.DispatcherFrame
$timer = New-Object System.Windows.Threading.DispatcherTimer
$state = @{{ opened = $false; code = 1 }}
$clock = [System.Diagnostics.Stopwatch]::StartNew()
$p.add_MediaOpened({{ $state.opened = $true; $p.Play() }})
$p.add_MediaEnded({{ $state.code = 0; $frame.Continue = $false }})
$p.add_MediaFailed({{ $state.code = 1; $frame.Continue = $false }})
$timer.Interval = [TimeSpan]::FromMilliseconds(100)
$timer.add_Tick({{
    if ((-not $state.opened -and $clock.Elapsed.TotalSeconds -ge {MEDIA_OPEN_TIMEOUT}) -or
        $clock.Elapsed.TotalSeconds -ge {PLAYBACK_TIMEOUT}) {{
        $state.code = 1
        $frame.Continue = $false
    }}
}})
try {{
    $p.Open([uri]{_ps_literal(os.path.abspath(path))})
    $timer.Start()
    [System.Windows.Threading.Dispatcher]::PushFrame($frame)
}} catch {{
    $state.code = 1
}} finally {{
    $timer.Stop()
    $p.Stop()
    $p.Close()
}}
exit $state.code
"""


# --- system (offline fallback) ---------------------------------------------

async def _speak_system(text: str, cfg: Config, cancel: asyncio.Event) -> str:
    try:
        cmd = _system_cmd(text, cfg)
    except RuntimeError as e:
        _warn(f"system tts unavailable: {e}")
        return "system_unavailable_logged"
    try:
        return await _run_process(cmd, cancel)
    except _Interrupted:
        raise
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
        cmd = [binary, "-v", voice or (cfg.language_hint or "zh"), "--", text]
        return cmd
    if sys.platform == "win32":
        ps = (
            "$ErrorActionPreference = 'Stop';"
            "Add-Type -AssemblyName System.Speech;"
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
            "try {"
            + (f"$s.SelectVoice({_ps_literal(voice)});" if voice else "")
            + f"$s.Speak({_ps_literal(text)})"
            + "} finally { $s.Dispose() }"
        )
        return _powershell_cmd(ps)
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
