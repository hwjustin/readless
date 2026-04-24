# readless

Local MCP server that lets Claude Code (and other MCP-aware agents) speak status, summaries, and blocking questions out loud via OpenAI TTS. Designed so you can step away from the screen during long agent tasks without losing situational awareness.

Three tools exposed to the agent:

| Tool | When to call | Max words spoken |
|---|---|---|
| `speak_summary(headline, details="")` | Task the user will care about is done | ~15 |
| `speak_status(message)` | Progress heartbeat during long tasks (server throttles to 1/min) | ~10 |
| `speak_blocker(question)` | Agent is stuck; needs user input. Bypasses quiet hours, interrupts speech. | ~20 |

## Quick start

```bash
git clone https://github.com/hwjustin/readless.git
cd readless
./install.sh
# then edit ~/.readless/config.yaml to paste your OPENAI_API_KEY,
# paste the block from CLAUDE_EXAMPLE.md into ~/.claude/CLAUDE.md,
# restart Claude Code, and ask it to call speak_summary.
```

`install.sh` is idempotent: creates the venv, `pip install -e .`, seeds `~/.readless/config.yaml` from the example, and runs `claude mcp add --scope user`. Re-run anytime — it skips steps already done.

## Install (detail)

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

On macOS, `sounddevice` needs PortAudio. If the install errors on it:

```bash
brew install portaudio
```

## Configure

Copy [`config.example.yaml`](./config.example.yaml) to `~/.readless/config.yaml` and paste your OpenAI key (or set `OPENAI_API_KEY` in your shell — env var wins). First launch also auto-creates a default config if one doesn't exist.

Without a key the server still runs — tools print `[readless:<kind>] <text>` to stderr and log to JSONL. Useful for wiring up the MCP connection before the key lands.

## Register with Claude Code

```bash
claude mcp add --scope user readless -- "$(pwd)/.venv/bin/python" -m readless.server
claude mcp list
```

Absolute python path matters — Claude Code spawns the server with its own `$PATH`. `--scope user` makes the server available across every project.

To remove: `claude mcp remove readless --scope user`.

## Tell your agent to use it

Paste the block in [CLAUDE_EXAMPLE.md](./CLAUDE_EXAMPLE.md) into `~/.claude/CLAUDE.md` or a project `CLAUDE.md`. This is the actual lever for tuning behavior — if the agent is too chatty or too silent, edit that block, not the code.

## Verify

1. `claude mcp list` shows `readless ✓`.
2. In Claude Code, `/mcp` lists readless with three tools.
3. Ask: "Call readless.speak_summary with headline='test'." 
   - No key yet → tool returns `tts_no_key_logged`; check `~/.readless/log.jsonl`.
   - Key set → laptop speaker plays "test".

## Logs

All tool calls append to `~/.readless/log.jsonl`:

```json
{"ts": "2026-04-24T10:15:03+08:00", "kind": "summary", "headline": "测试通过", "details": "3 files modified"}
```

## Troubleshooting

- **No sound but no error**: `OPENAI_API_KEY` not set. Check stderr for `[readless] (no-key)` lines, or edit the yaml.
- **`sd.PortAudioError: Error querying device`**: audio output device missing/changed. Plug in headphones or pick a default output in System Settings → Sound.
- **Claude Code doesn't see the server**: run `claude mcp list` — if missing, re-run the `claude mcp add` command with the absolute venv python path. Restart Claude Code after adding.
- **Tool returns `throttled` a lot**: by design — `speak_status` caps at one speech per minute. Lower `status_throttle_seconds` in the yaml if you want tighter pings.

## License

Apache 2.0 — see [LICENSE](./LICENSE).

## Design notes

- `speak_status` throttling is server-side and stateless across restarts. The agent calling "too often" is not an error condition.
- `speak_blocker` interrupts in-progress speech and ignores quiet hours — if you started a long task you're presumably awake enough to unblock it.
- No terminal reverse-summarization, no STT, no multi-TTS-backend abstraction. v1 is deliberately thin.

## Structure

```
src/readless/
  server.py    FastMCP entrypoint + tool definitions
  tts.py       OpenAI streaming -> sounddevice + no-key/failure fallback
  config.py    YAML + env var loader + quiet-hours math
  throttle.py  StatusThrottle (tested)
  logger.py    JSONL append
tests/
  test_throttle.py
```
