# readless

[English](./README.md) · [中文](./README.zh.md)

Claude Code plugin that speaks each turn's last message and pings you when the agent is waiting for input — so you can walk away from a long task without losing the thread.

Two hooks, zero MCP wiring, no `CLAUDE.md` block to paste:

| Hook | When it fires | What it does |
|---|---|---|
| `Stop` | Assistant finishes a turn | Reads the last assistant message and speaks a short summary |
| `Notification` | Claude Code needs permission or has been idle | Interrupts current speech and says what's blocking |

Default TTS backend is your OS's built-in voice (macOS `say`, Linux `espeak-ng`, Windows SAPI) — **no API key required**. Set one in the config to upgrade to OpenAI or ElevenLabs voices.

## Install

```
/plugin marketplace add hwjustin/readless
/plugin install readless
```

**No pip install needed for the default `system` backend** — the hook walks up to `src/` inside the plugin directory and imports `readless` from there, and the default backend has zero dependencies beyond Python 3.11+.

For cloud TTS, install extras into whatever Python `/usr/bin/env python3` resolves to:

```bash
pip install --user 'readless[openai] @ git+https://github.com/hwjustin/readless.git'
# or
pip install --user 'readless[elevenlabs] @ git+https://github.com/hwjustin/readless.git'
```

That's it. Open Claude Code, run a turn, hear the summary.

## Configure (optional)

The first run auto-creates `~/.readless/config.yaml` from defaults. Edit it to:

- `system_voice: Tingting` — pick a macOS voice (run `say -v '?'` to list)
- `tts_provider: openai` + `openai_api_key: sk-...` — use OpenAI TTS
- `tts_provider: elevenlabs` + `elevenlabs_api_key: ...` + `elevenlabs_voice_id: ...`
- `quiet_hours.start / end` — silence per-turn summaries at night (notifications still play)
- `summary_max_chars: 80` — cap on how much of the last message gets spoken

See [`config.example.yaml`](./config.example.yaml).

## How it stays silent on errors

The hook script (`hooks/readless_hook.py`) follows the same fail-open pattern as [open-vibe-island](https://github.com/Octane0411/open-vibe-island):

1. Always exits 0 — never raises a non-zero status
2. Top-level `try / except: pass` swallows every exception
3. Writes nothing to stdout (Stop / Notification don't need a directive)
4. Forks a child, calls `setsid`, redirects stdio to `/dev/null` — the TTS work is fully detached from Claude Code's stdio, so a slow or failing API call can't leak into your terminal

All errors get appended to `~/.readless/log.jsonl` for debugging.

## Logs

```json
{"ts": "2026-05-14T22:30:00+08:00", "kind": "stop", "headline": "Build succeeded. 3 tests passed."}
{"ts": "2026-05-14T22:31:12+08:00", "kind": "notification", "headline": "Claude needs your permission to run Bash"}
```

## License

Apache 2.0 — see [LICENSE](./LICENSE).

## Structure

```
.claude-plugin/
  plugin.json          Stop + Notification hook declarations
  marketplace.json     marketplace metadata for /plugin marketplace add
hooks/
  readless_hook.py     sealed-stdio entry point; forks + detaches
src/readless/
  hook_runner.py       event dispatch -> speak()
  tts.py               system / openai / elevenlabs backends
  config.py            YAML loading + quiet-hours math
  logger.py            JSONL append-only log
```
