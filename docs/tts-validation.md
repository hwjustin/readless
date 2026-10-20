# TTS playback lifecycle validation

Baseline reviewed: `main` at `c1064c0ce569be47a048797ea03b7d8aeec0d787`.
Scope: edge-tts file playback and the offline system fallback on Windows and
Linux. The optional OpenAI/ElevenLabs PCM streaming implementation is unchanged.

## Findings and fixes

| Baseline finding | Evidence and resulting behavior |
| --- | --- |
| Windows polls `NaturalDuration.HasTimeSpan` without a deadline. | Static risk, not a reproduced Windows hang. Replace duration polling with WPF `MediaOpened`, `MediaEnded` and `MediaFailed` events, a dispatcher, a 10-second open deadline, and a total playback deadline. Always close the player on normal script exit. |
| Both external players and system TTS use unbounded `Popen.wait()`. | Static proof of no application timeout. Use asynchronous subprocesses with a 120-second deadline per playback attempt. Edge synthesis has a separate 30-second deadline. |
| Return codes are ignored, and only synthesis failure triggers fallback. | Nonzero player exits previously returned `spoken`. Missing players, launch errors, timeouts and detected playback errors now cause one attempt at system TTS. A failed system attempt returns a failure status; it does not retry recursively. |
| `ffplay` can exit zero after a decoding error. | Reproduced with the installed Linux `ffplay` and an invalid MP3. Run it at error log level and inspect stderr as well as exit status. Stderr goes to a temporary file so a full pipe cannot deadlock playback. This deliberately treats any stderr from that invocation as failure; it may also reject noisy third-party builds. |
| `terminate()` is not followed by a wait or escalation. | Reap the direct child before releasing the speech lock or deleting the MP3. Allow two seconds after terminate, then kill and allow another two seconds. Log if the OS still fails to report exit. Real Linux children ignoring SIGTERM are covered. |
| Global process tracking races with concurrent requests; a synthesis in flight can play after an interrupt. | Serialize edge/system requests and interrupt synthesis, playback and fallback as one request. Mark superseded queued requests `interrupted`. Caller cancellation propagates after child cleanup. Ordinary updates queue rather than killing each other. |
| Windows interpolates paths, voice names and speech into PowerShell source. | Use single-quoted, escaped literals and UTF-16 encoded commands; request STA/noninteractive mode and terminating PowerShell errors. Also separate Linux espeak text from command options with `--`. |
| Linux may select `paplay` for edge's MP3. | Remove this fallback because MP3 decoding depends on the libsndfile build. Prefer mpg123, ffplay or mpv, then system TTS. Force mpv to exit after playback regardless of keep-open user settings. |

The time limits are for short status updates, not long-form narration. A failed
edge playback can consume its deadline before the separate system fallback
deadline starts. These are application deadlines for cooperative asyncio/OS
operations, not a guarantee against an unresponsive kernel or uncooperative
third-party coroutine. Cleanup manages the directly launched player, not arbitrary
descendant processes created by locally customized player wrappers.

## Automated coverage

The baseline has four tests, all for status throttling; it has no TTS tests.
Run the complete suite from the repository root:

```sh
python -m pip install pytest
PYTHONPATH=src python -m pytest -q
```

On PowerShell, set `$env:PYTHONPATH = 'src'` before running pytest.
No online TTS calls or API keys are needed. The Actions workflow runs on Linux,
Windows and macOS with Python 3.10 and 3.12.

`test_tts.py` covers missing players, spawn errors, exit status, timeouts,
terminate-to-kill escalation, fallback, literal quoting, synthesis interruption,
queued updates, consecutive interrupts, cancellation during spawn/playback,
serialization and temporary-file cleanup ordering. Real Python child processes
exercise exit status on every OS and ignored SIGTERM on Linux. A real Linux
ffplay rejection test runs when ffplay is installed.

`test_tts_windows.py` runs only on Windows. It executes the generated PowerShell
script with the actual WPF dispatcher and a fake media object (which has no
duration property), checking ended/failed/missing-open/missing-end events and
timeouts. Separate cases send corrupt and missing files to the native MediaPlayer.
These are native OS integration checks, not audible playback validation.

## Manual audio acceptance still required

Use a Windows desktop and a Linux desktop with working audio outputs:

1. Play a valid edge-generated MP3 with each available player, then with the
   system provider. Confirm complete audible speech and the `spoken` status.
2. Interrupt a long utterance with a blocker during synthesis and during
   playback. Confirm old audio stops, the blocker plays once, and no stale
   fallback resumes afterward. Repeat with two blockers in quick succession.
3. Disconnect the audio device or force the selected player to fail. Confirm
   failure is detected, the system fallback is attempted once, and failures
   are reported without leaving a child process or MP3 behind.
4. Try non-ASCII text/paths, apostrophes, dollar signs and backticks. Confirm
   they remain literal data. Test Windows with the installed voice names.

A zero exit status cannot prove that a speaker produced sound. Linux container
process tests and native Windows CI checks must not be reported as desktop audio
acceptance, nor as proof that the original Windows duration hang was reproduced.
The unchecked historical PR checklist alone says nothing about later manual tests.
