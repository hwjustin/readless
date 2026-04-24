from __future__ import annotations

import asyncio
import sys
import traceback
from typing import Optional

from .config import Config

SAMPLE_RATE = 24000
CHANNELS = 1
CHUNK_BYTES = 4096

_speech_lock = asyncio.Lock()
_cancel_flag = asyncio.Event()
_active_stream = None


def _warn(msg: str) -> None:
    print(f"[readless] {msg}", file=sys.stderr, flush=True)


async def speak(text: str, cfg: Config, interrupt: bool = False) -> str:
    if not cfg.openai_api_key:
        _warn(f"(no-key) {text}")
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
            return await _stream_and_play(text, cfg)
        except Exception as e:
            traceback.print_exc(file=sys.stderr)
            _warn(f"TTS failed ({e.__class__.__name__}): {text}")
            return "tts_failed_but_logged"


async def _stream_and_play(text: str, cfg: Config) -> str:
    import sounddevice as sd
    from openai import OpenAI

    client = OpenAI(api_key=cfg.openai_api_key)

    def _blocking_play() -> str:
        global _active_stream
        stream = sd.RawOutputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
        )
        stream.start()
        _active_stream = stream
        try:
            with client.audio.speech.with_streaming_response.create(
                model="gpt-4o-mini-tts",
                voice=cfg.voice,
                input=text,
                response_format="pcm",
                speed=cfg.speed,
            ) as response:
                for chunk in response.iter_bytes(chunk_size=CHUNK_BYTES):
                    if _cancel_flag.is_set():
                        return "interrupted"
                    if chunk:
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

    return await asyncio.to_thread(_blocking_play)
