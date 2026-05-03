from __future__ import annotations

import asyncio
import sys
import traceback
from typing import Iterator

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


def _iter_pcm(text: str, cfg: Config) -> Iterator[bytes]:
    """Provider-agnostic generator yielding raw PCM int16 24kHz mono bytes."""
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
