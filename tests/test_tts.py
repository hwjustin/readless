"""Lifecycle tests: no network, credentials, speakers or optional TTS SDKs."""

import asyncio
import base64
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace

import pytest

from readless import tts
from readless.config import Config


@pytest.fixture(autouse=True)
def speech_state(monkeypatch):
    # Each test owns its event loop and speech state.
    monkeypatch.setattr(tts, "_speech_lock", asyncio.Lock())
    monkeypatch.setattr(tts, "_active_cancel", None)
    monkeypatch.setattr(tts, "_speech_generation", 0)


@pytest.fixture
def edge(monkeypatch):
    paths = []

    class Communicate:
        def __init__(self, text, **kwargs):
            self.text = text

        async def save(self, path):
            paths.append(Path(path))
            Path(path).write_bytes(b"fake mp3")

    monkeypatch.setitem(sys.modules, "edge_tts", SimpleNamespace(Communicate=Communicate))
    return Communicate, paths


class Process:
    """A player that may ignore terminate(), but exits after kill()."""

    def __init__(self, code=None, ignore_terminate=False):
        self.returncode = code
        self.ignore_terminate = ignore_terminate
        self.exited = asyncio.Event()
        self.actions = []
        if code is not None:
            self.exited.set()

    async def wait(self):
        await self.exited.wait()
        return self.returncode

    def terminate(self):
        self.actions.append("terminate")
        if not self.ignore_terminate:
            self.returncode = -15
            self.exited.set()

    def kill(self):
        self.actions.append("kill")
        self.returncode = -9
        self.exited.set()


def test_player_selection_and_mp3_support(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    available = {"mpg123", "ffplay", "mpv", "paplay"}
    monkeypatch.setattr(tts.shutil, "which", lambda name: name if name in available else None)
    assert tts._audio_player_cmd("test.mp3") == ["mpg123", "-q", "test.mp3"]
    available.remove("mpg123")
    assert tts._audio_player_cmd("test.mp3")[0] == "ffplay"
    available.remove("ffplay")
    cmd = tts._audio_player_cmd("test.mp3")
    assert cmd[0] == "mpv" and "--keep-open=no" in cmd
    available.remove("mpv")
    # paplay alone is not a reliable MP3 decoder.
    assert tts._audio_player_cmd("test.mp3") is None
    monkeypatch.setattr(sys, "platform", "darwin")
    available.add("afplay")
    assert tts._audio_player_cmd("test.mp3") == ["afplay", "test.mp3"]


def test_windows_command_has_bounds_events_and_literal_paths(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    cmd = tts._audio_player_cmd("O'Brien $test 中文.mp3")
    assert "-NonInteractive" in cmd and "-STA" in cmd
    script = base64.b64decode(cmd[-1]).decode("utf-16-le")
    assert "O''Brien $test 中文.mp3" in script
    assert "NaturalDuration" not in script
    for event in ("MediaOpened", "MediaEnded", "MediaFailed"):
        assert f"add_{event}" in script
    assert "PushFrame" in script
    assert str(tts.MEDIA_OPEN_TIMEOUT) in script
    assert str(tts.PLAYBACK_TIMEOUT) in script
    assert "$p.Close()" in script and "exit $state.code" in script


def test_windows_system_text_is_literal_and_errors_are_fatal(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    cmd = tts._system_cmd("Don't run $(exit 0) `n 中文", Config(system_voice="O'Brien"))
    script = base64.b64decode(cmd[-1]).decode("utf-16-le")
    assert "$s.SelectVoice('O''Brien')" in script
    assert "$s.Speak('Don''t run $(exit 0) `n 中文')" in script
    assert "$ErrorActionPreference = 'Stop'" in script
    assert "$s.Dispose()" in script


def test_linux_system_text_cannot_be_an_option(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(tts.shutil, "which", lambda name: "/usr/bin/espeak")
    assert tts._system_cmd("--help", Config())[-2:] == ["--", "--help"]


@pytest.mark.parametrize("code, expected", [(0, "spoken"), (1, "tts_failed_but_logged"), (-15, "tts_failed_but_logged")])
def test_exit_status_is_checked(monkeypatch, code, expected):
    async def scenario():
        proc = Process(code)

        async def spawn(*args, **kwargs):
            return proc

        monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
        assert await tts._run_process(["player"], asyncio.Event()) == expected
        assert proc.actions == []

    asyncio.run(scenario())


def test_timeout_escalates_terminate_to_kill(monkeypatch):
    async def scenario():
        proc = Process(ignore_terminate=True)

        async def spawn(*args, **kwargs):
            return proc

        monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
        monkeypatch.setattr(tts, "PLAYBACK_TIMEOUT", 0.01)
        monkeypatch.setattr(tts, "PROCESS_EXIT_TIMEOUT", 0.01)
        with pytest.raises(asyncio.TimeoutError):
            await tts._run_process(["player"], asyncio.Event())
        assert proc.actions == ["terminate", "kill"]
        assert proc.returncode is not None

    asyncio.run(scenario())


def test_cancellation_during_spawn_reaps_process(monkeypatch):
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        proc = Process()

        async def spawn(*args, **kwargs):
            entered.set()
            await release.wait()
            return proc

        monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
        task = asyncio.create_task(tts._run_process(["player"], asyncio.Event()))
        await entered.wait()
        task.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert proc.actions == ["terminate"]
        assert proc.returncode is not None

    asyncio.run(scenario())


def test_cancellation_wins_over_spawn_error(monkeypatch):
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()

        async def spawn(*args, **kwargs):
            entered.set()
            await release.wait()
            raise FileNotFoundError("player disappeared during cancellation")

        monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
        monkeypatch.setattr(tts, "_system_cmd", lambda *args: ["system"])
        task = asyncio.create_task(tts.speak("hello", Config(tts_provider="system")))
        await entered.wait()
        task.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["missing_player", "spawn", "nonzero", "timeout", "synthesis", "constructor", "synthesis_timeout"])
def test_edge_failure_falls_back_and_removes_tempfile(monkeypatch, edge, failure):
    communicate, paths = edge
    fallback_calls = []

    async def spawn(*args, **kwargs):
        if failure == "spawn":
            raise FileNotFoundError("player disappeared")
        return Process(4 if failure == "nonzero" else None)

    async def fallback(text, cfg, cancel):
        assert not cancel.is_set()
        fallback_calls.append(text)
        return "spoken"

    async def save(self, path):
        paths.append(Path(path))
        if failure == "synthesis":
            raise RuntimeError("network failed")
        await asyncio.Event().wait()

    def constructor(*args, **kwargs):
        raise ValueError("invalid voice")

    if failure in ("synthesis", "synthesis_timeout"):
        monkeypatch.setattr(communicate, "save", save)
    if failure == "constructor":
        monkeypatch.setattr(sys.modules["edge_tts"], "Communicate", constructor)
    monkeypatch.setattr(tts, "_audio_player_cmd", lambda path: None if failure == "missing_player" else ["player"])
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    monkeypatch.setattr(tts, "_speak_system", fallback)
    monkeypatch.setattr(tts, "PLAYBACK_TIMEOUT", 0.01)
    monkeypatch.setattr(tts, "SYNTHESIS_TIMEOUT", 0.01)
    assert asyncio.run(tts.speak("hello", Config())) == "spoken"
    assert fallback_calls == ["hello"]
    assert all(not path.exists() for path in paths)


def test_system_failure_is_reported_without_retry_loop(monkeypatch):
    async def spawn(*args, **kwargs):
        return Process(5)

    monkeypatch.setattr(tts, "_system_cmd", lambda *args: ["system"])
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    assert asyncio.run(tts.speak("hello", Config(tts_provider="system"))) == "tts_failed_but_logged"


def test_unavailable_system_is_reported(monkeypatch):
    def unavailable(*args):
        raise RuntimeError("no system TTS")

    monkeypatch.setattr(tts, "_system_cmd", unavailable)
    assert asyncio.run(tts.speak("hello", Config(tts_provider="system"))) == "system_unavailable_logged"


def test_interrupt_during_synthesis_does_not_play_or_fallback(monkeypatch, edge):
    communicate, paths = edge

    async def scenario():
        entered = asyncio.Event()
        calls = []

        async def save(self, path):
            paths.append(Path(path))
            entered.set()
            await asyncio.Event().wait()

        async def system(text, cfg, cancel):
            calls.append(text)
            return "spoken"

        monkeypatch.setattr(communicate, "save", save)
        monkeypatch.setattr(tts, "_speak_system", system)
        old = asyncio.create_task(tts.speak("old", Config()))
        await entered.wait()
        assert await tts.speak("blocker", Config(tts_provider="system"), interrupt=True) == "spoken"
        assert await old == "interrupted"
        assert calls == ["blocker"]
        assert all(not path.exists() for path in paths)

    asyncio.run(scenario())


def test_interrupt_reaps_before_tempfile_deletion_and_skips_old_queue(monkeypatch, edge):
    _, paths = edge

    async def scenario():
        entered = asyncio.Event()
        proc = Process(ignore_terminate=True)
        calls = []
        unlink = tts.os.unlink

        async def spawn(*args, **kwargs):
            entered.set()
            return proc

        async def system(text, cfg, cancel):
            calls.append(text)
            return "spoken"

        def checked_unlink(path):
            if Path(path) in paths:
                assert proc.returncode is not None
            unlink(path)

        monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
        monkeypatch.setattr(tts, "_audio_player_cmd", lambda path: ["player", path])
        monkeypatch.setattr(tts, "_speak_system", system)
        monkeypatch.setattr(tts.os, "unlink", checked_unlink)
        monkeypatch.setattr(tts, "PROCESS_EXIT_TIMEOUT", 0.01)
        old = asyncio.create_task(tts.speak("old", Config()))
        await entered.wait()
        queued = asyncio.create_task(tts.speak("stale", Config(tts_provider="system")))
        await asyncio.sleep(0)  # queue the request before the blocker arrives
        assert await tts.speak("blocker", Config(tts_provider="system"), interrupt=True) == "spoken"
        assert await old == await queued == "interrupted"
        assert calls == ["blocker"]
        assert proc.actions == ["terminate", "kill"]
        assert all(not path.exists() for path in paths)

    asyncio.run(scenario())


def test_normal_requests_are_serialized(monkeypatch):
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        calls = []

        async def system(text, cfg, cancel):
            calls.append(text)
            if text == "first":
                entered.set()
                await release.wait()
            return "spoken"

        monkeypatch.setattr(tts, "_speak_system", system)
        first = asyncio.create_task(tts.speak("first", Config(tts_provider="system")))
        await entered.wait()
        second = asyncio.create_task(tts.speak("second", Config(tts_provider="system")))
        await asyncio.sleep(0)
        assert calls == ["first"]
        release.set()
        assert await first == await second == "spoken"
        assert calls == ["first", "second"]

    asyncio.run(scenario())


def test_latest_interrupt_wins_during_process_cleanup(monkeypatch):
    async def scenario():
        entered, terminating = asyncio.Event(), asyncio.Event()
        proc = Process(ignore_terminate=True)
        terminate = proc.terminate
        calls = []

        def stop():
            terminate()
            terminating.set()

        proc.terminate = stop

        async def spawn(*args, **kwargs):
            entered.set()
            return proc

        async def edge_speak(text, cfg, cancel):
            calls.append(text)
            if text == "old":
                return await tts._run_process(["player"], cancel)
            return "spoken"

        monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
        monkeypatch.setattr(tts, "_speak_edge", edge_speak)
        monkeypatch.setattr(tts, "PROCESS_EXIT_TIMEOUT", 0.01)
        old = asyncio.create_task(tts.speak("old", Config()))
        await entered.wait()
        first = asyncio.create_task(tts.speak("blocker 1", Config(), interrupt=True))
        await terminating.wait()
        last = asyncio.create_task(tts.speak("blocker 2", Config(), interrupt=True))
        assert await old == await first == "interrupted"
        assert await last == "spoken"
        assert calls == ["old", "blocker 2"]
        assert proc.actions == ["terminate", "kill"]

    asyncio.run(scenario())


def test_external_cancellation_propagates_and_cleans_up(monkeypatch, edge):
    _, paths = edge

    async def scenario():
        entered = asyncio.Event()
        proc = Process()

        async def spawn(*args, **kwargs):
            entered.set()
            return proc

        monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
        monkeypatch.setattr(tts, "_audio_player_cmd", lambda path: ["player"])
        task = asyncio.create_task(tts.speak("hello", Config()))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert proc.returncode is not None
        assert all(not path.exists() for path in paths)
        assert tts._active_cancel is None
        assert not tts._speech_lock.locked()

    asyncio.run(scenario())


@pytest.mark.parametrize("reports_error", [False, True])
def test_ffplay_zero_exit_requires_no_error_output(monkeypatch, reports_error):
    async def spawn(*args, **kwargs):
        if reports_error:
            kwargs["stderr"].write(b"Failed to open audio device")
            kwargs["stderr"].flush()
        return Process(0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    monkeypatch.setattr(tts, "_audio_player_cmd", lambda path: ["ffplay", path])
    result = asyncio.run(tts._play_audio_file("test.mp3", asyncio.Event()))
    assert result == ("tts_failed_but_logged" if reports_error else "spoken")


@pytest.mark.skipif(not sys.platform.startswith("linux") or not shutil.which("ffplay"), reason="Linux ffplay required")
def test_real_linux_ffplay_rejects_invalid_mp3(monkeypatch, tmp_path):
    path = tmp_path / "invalid.mp3"
    path.write_bytes(b"not audio")
    monkeypatch.setattr(tts, "_audio_player_cmd", lambda path: [
        "ffplay", "-nodisp", "-autoexit", "-loglevel", "error", path,
    ])
    monkeypatch.setattr(tts, "PLAYBACK_TIMEOUT", 3)
    assert asyncio.run(tts._play_audio_file(str(path), asyncio.Event())) == "tts_failed_but_logged"


@pytest.mark.parametrize("exit_code", [0, 7])
def test_real_child_exit_status(exit_code):
    async def scenario():
        return await tts._run_process(
            [sys.executable, "-c", f"raise SystemExit({exit_code})"], asyncio.Event(),
        )

    expected = "spoken" if exit_code == 0 else "tts_failed_but_logged"
    assert asyncio.run(scenario()) == expected


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux SIGTERM semantics")
@pytest.mark.parametrize("action", ["timeout", "interrupt", "cancel"])
def test_real_linux_child_ignoring_sigterm_is_killed(monkeypatch, tmp_path, action):
    async def scenario():
        real_spawn = asyncio.create_subprocess_exec
        children = []
        ready = tmp_path / "ready"

        async def spawn(*args, **kwargs):
            proc = await real_spawn(*args, **kwargs)
            children.append(proc)
            return proc

        monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
        monkeypatch.setattr(tts, "PLAYBACK_TIMEOUT", 0.3 if action == "timeout" else 5)
        monkeypatch.setattr(tts, "PROCESS_EXIT_TIMEOUT", 0.05)
        script = (
            "import pathlib, signal, sys, time; "
            "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
            "pathlib.Path(sys.argv[1]).touch(); time.sleep(60)"
        )
        cancel = asyncio.Event()
        task = asyncio.create_task(tts._run_process([sys.executable, "-c", script, str(ready)], cancel))
        try:
            async def wait_ready():
                while not ready.exists():
                    await asyncio.sleep(0.005)

            await asyncio.wait_for(wait_ready(), 3)
            if action == "interrupt":
                cancel.set()
                expected = tts._Interrupted
            elif action == "cancel":
                task.cancel()
                expected = asyncio.CancelledError
            else:
                expected = asyncio.TimeoutError
            with pytest.raises(expected):
                await asyncio.wait_for(task, 3)
            assert children[0].returncode == -9
        finally:
            # A failing regression must not leave the test child alive.
            for proc in children:
                if proc.returncode is None:
                    proc.kill()
                    await proc.wait()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())
