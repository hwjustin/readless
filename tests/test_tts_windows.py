"""Native Windows script checks; these do not verify audible playback."""

import subprocess
import sys

import pytest

from readless import tts


pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell/WPF required")


@pytest.mark.parametrize("mode, expected", [
    ("ended", 0), ("failed", 1), ("never_opened", 1), ("never_ended", 1),
])
def test_windows_dispatcher_handles_media_events_and_timeouts(monkeypatch, tmp_path, mode, expected):
    # Exercise the actual generated script and WPF dispatcher with a fake media
    # object. In particular, it has NO NaturalDuration property. No audio device
    # or codec is required for these deterministic lifecycle checks.
    monkeypatch.setattr(tts, "MEDIA_OPEN_TIMEOUT", 0.2)
    monkeypatch.setattr(tts, "PLAYBACK_TIMEOUT", 0.5)
    closed = tmp_path / "closed"
    prefix = """
class ReadlessFakePlayer {
    [string] $Mode
    [string] $ClosedPath
    [scriptblock] $Opened
    [scriptblock] $Ended
    [scriptblock] $Failed
    [void] add_MediaOpened([scriptblock] $handler) { $this.Opened = $handler }
    [void] add_MediaEnded([scriptblock] $handler) { $this.Ended = $handler }
    [void] add_MediaFailed([scriptblock] $handler) { $this.Failed = $handler }
    [void] Open([uri] $path) {
        if ($this.Mode -eq 'failed') { $this.Failed.Invoke() }
        elseif ($this.Mode -ne 'never_opened') { $this.Opened.Invoke() }
    }
    [void] Play() {
        if ($this.Mode -eq 'ended') { $this.Ended.Invoke() }
    }
    [void] Stop() {}
    [void] Close() { [System.IO.File]::WriteAllText($this.ClosedPath, 'closed') }
}
$fake = [ReadlessFakePlayer]::new()
"""
    prefix += f"$fake.Mode = {tts._ps_literal(mode)}\n"
    prefix += f"$fake.ClosedPath = {tts._ps_literal(str(closed))}\n"
    script = tts._windows_audio_script(str(tmp_path / "unused.mp3")).replace(
        "New-Object System.Windows.Media.MediaPlayer", "$fake",
    )
    result = subprocess.run(
        tts._powershell_cmd(prefix + script), capture_output=True, timeout=10,
    )
    assert result.returncode == expected, result.stderr.decode(errors="replace")
    assert closed.read_text() == "closed"


@pytest.mark.parametrize("exists", [True, False])
def test_windows_native_player_rejects_bad_or_missing_media(monkeypatch, tmp_path, exists):
    monkeypatch.setattr(tts, "MEDIA_OPEN_TIMEOUT", 1.0)
    monkeypatch.setattr(tts, "PLAYBACK_TIMEOUT", 2.0)
    path = tmp_path / "O'Brien $test 中文.mp3"
    if exists:
        path.write_bytes(b"not an MP3")
    result = subprocess.run(tts._audio_player_cmd(str(path)), capture_output=True, timeout=10)
    assert result.returncode != 0
