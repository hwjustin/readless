# readless

[English](./README.md) · [中文](./README.zh.md)

Claude Code plugin (MCP-based) that speaks status, summaries, and blocker questions out loud — so you can walk away from a long task and still know what's happening.

Three agent-callable tools:

| Tool | When the agent calls it | Spoken length |
|---|---|---|
| `speak_summary(headline, details="")` | End of every turn, or when a user-visible task finishes | ≤ 50 words |
| `speak_status(message)` | Mid-task heartbeat during work expected to run > 2 min (server throttles to 1/min) | ≤ 10 words |
| `speak_blocker(question)` | Agent is stuck and needs your input. Bypasses quiet hours, interrupts current speech. | ≤ 20 words |

Default TTS backend is your OS's built-in voice (macOS `say`, Linux `espeak-ng`, Windows SAPI) — **no API key required**. Switch to OpenAI or ElevenLabs by editing `~/.readless/config.yaml`.

## Install

```
/plugin marketplace add hwjustin/readless
/plugin install readless
/readless:setup
```

The `/readless:setup` slash command:

1. `pip install --user -e ${CLAUDE_PLUGIN_ROOT}` so `python3 -m readless.server` works (this is what the MCP entry in the plugin manifest spawns)
2. Asks whether you want the Chinese or English instruction block, then appends it to `~/.claude/CLAUDE.md` so the agent knows to call `speak_summary` at the end of every turn

After setup, restart Claude Code. `/mcp` should show `readless ✓ Connected`.

> **Why the manual setup step?** Claude Code plugin manifests cannot inject instructions into the user's CLAUDE.md, and the MCP server's Python dependencies have to land in whatever Python `python3` resolves to. `/readless:setup` handles both with one consent.

## Configure (optional)

`~/.readless/config.yaml` is auto-created from defaults on first run. Edit it for:

- `tts_provider: openai` + `openai_api_key: sk-...` — use OpenAI voices
- `tts_provider: elevenlabs` + `elevenlabs_api_key: ...` + `elevenlabs_voice_id: ...`
- `system_voice: Tingting` — pick a macOS voice (`say -v '?'` to list)
- `quiet_hours.start / end` — silence `speak_summary` / `speak_status` at night (`speak_blocker` still plays)
- `tools.speak_status: false` (etc.) — disable individual tools
- `status_throttle_seconds: 60` — limit `speak_status` rate

Env vars `OPENAI_API_KEY` / `ELEVENLABS_API_KEY` override the YAML.

See [`config.example.yaml`](./config.example.yaml).

## Tune the agent

[`CLAUDE_EXAMPLE.md`](./CLAUDE_EXAMPLE.md) is the source of truth for "when should the agent call which tool." Edit your `~/.claude/CLAUDE.md` block to make the agent more or less chatty — that's the lever, not the code.

## Logs

All tool calls append to `~/.readless/log.jsonl`:

```json
{"ts": "2026-05-14T22:30:00+08:00", "kind": "summary", "headline": "构建通过，3 个测试都过了", "details": ""}
```

## License

Apache 2.0 — see [LICENSE](./LICENSE).

## Structure

```
.claude-plugin/
  plugin.json          declares the readless MCP server
  marketplace.json     /plugin marketplace add metadata
commands/
  setup.md             /readless:setup — pip install + CLAUDE.md append
src/readless/
  server.py            FastMCP entry + tool definitions
  tts.py               system / openai / elevenlabs backends
  config.py            YAML loading + quiet-hours math (built-in YAML fallback)
  throttle.py          StatusThrottle (1 call/min default)
  logger.py            JSONL append-only log
CLAUDE_EXAMPLE.md      agent instruction blocks (Chinese + English)
```
