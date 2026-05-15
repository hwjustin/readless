# readless

[English](./README.md) · [中文](./README.zh.md)

Claude Code plugin (MCP-based) that speaks status, summaries, and blocker questions out loud — so you can walk away from a long task and still know what's happening.

Three agent-callable tools:

| Tool | When the agent calls it | Spoken length |
|---|---|---|
| `speak_summary(headline, details="")` | End of every turn, or when a user-visible task finishes | ≤ 50 words |
| `speak_status(message)` | Mid-task heartbeat during work expected to run > 2 min (server throttles to 1/min) | ≤ 10 words |
| `speak_blocker(question)` | Agent is stuck and needs your input. Bypasses quiet hours, interrupts current speech. | ≤ 20 words |

Default TTS backend is **edge-tts** — Microsoft's free online TTS endpoint. **No API key, no signup, no model download**, and the default voice `zh-CN-XiaoxiaoNeural` handles Chinese + English code-switching naturally. Falls back to your OS's built-in voice if the network is unreachable. Optional OpenAI / ElevenLabs backends are available if you want your own voice — keys are entered through a separate CLI so they never touch the Claude conversation.

## Install

You need `uv` ([Astral's Python launcher](https://github.com/astral-sh/uv)) on PATH — that's it. `uv` provisions Python automatically, so you do not need to install Python 3.10+ yourself or manage virtualenvs.

```bash
# 1. Install uv (skip if you already have it)
curl -LsSf https://astral.sh/uv/install.sh | sh        # macOS / Linux
# brew install uv                                       # macOS via Homebrew
# irm https://astral.sh/uv/install.ps1 | iex            # Windows PowerShell
```

Then in Claude Code:

```
/plugin marketplace add hwjustin/readless
/plugin install readless
/readless:setup
```

`/readless:setup`:

1. Verifies `uv` is on PATH (re-prompts if not) and pre-warms `uvx --from readless-mcp readless` so the first MCP startup is instant.
2. Asks whether you want the Chinese or English instruction block, then appends it to `~/.claude/CLAUDE.md` (marker-bounded, idempotent) so the agent knows to call `speak_summary` at the end of every turn.

After setup, **fully restart Claude Code** (not just a new chat — close the CLI / IDE host so the new PATH is picked up). `/mcp` should show `readless ✓ Connected`.

> **Why uv?** The MCP SDK requires Python ≥3.10. macOS ships 3.9 system-wide, and asking users to install Homebrew Python or manage a venv was the #1 source of "it doesn't work." `uv` downloads a suitable Python on demand into its own cache (`~/.cache/uv/`), runs `readless-mcp` from PyPI in isolation, and leaves the system Python untouched. This is the [pattern recommended by the official MCP servers repo](https://github.com/modelcontextprotocol/servers).

## Switching to OpenAI / ElevenLabs (optional)

The default edge-tts backend is good enough for most people. If you want OpenAI or ElevenLabs voices, set the key **in your own terminal** — don't paste the key into Claude:

```bash
# OpenAI
uvx --from 'readless-mcp[openai]' readless-setkey openai     # prompts for key, input hidden

# ElevenLabs
uvx --from 'readless-mcp[elevenlabs]' readless-setkey elevenlabs
```

`readless-setkey` uses `getpass` to read the key without echoing it, writes it to `~/.readless/config.yaml` (chmod 600), and flips `tts_provider` for you. Use `readless-setkey clear openai` (or `elevenlabs`) to wipe a saved key.

Env vars `OPENAI_API_KEY` / `ELEVENLABS_API_KEY` always override the config file if you prefer shell-rc-managed secrets.

## Configure

`~/.readless/config.yaml` is auto-created from defaults on first run. Common edits:

- `edge_voice: en-US-AriaNeural` — pick a different edge-tts voice (`edge-tts --list-voices` to list)
- `edge_rate: "+20%"` — speed up the default voice
- `tts_provider: system` — force OS-native TTS (useful for fully offline machines)
- `system_voice: Tingting` — pick a macOS voice (`say -v '?'` to list)
- `quiet_hours.start / end` — silence `speak_summary` / `speak_status` at night (`speak_blocker` still plays)
- `tools.speak_status: false` (etc.) — disable individual tools
- `status_throttle_seconds: 60` — limit `speak_status` rate

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
  plugin.json          plugin metadata (name, version, description)
  marketplace.json     /plugin marketplace add metadata
.mcp.json              MCP server declaration (uvx --from readless-mcp readless)
commands/
  setup.md             /readless:setup — ensure `uv` is installed + CLAUDE.md append
src/readless/
  server.py            FastMCP entry + tool definitions
  tts.py               edge / system / openai / elevenlabs backends
  setkey.py            readless-setkey CLI — secure API-key entry
  config.py            YAML loading + quiet-hours math (built-in YAML fallback)
  throttle.py          StatusThrottle (1 call/min default)
  logger.py            JSONL append-only log
CLAUDE_EXAMPLE.md      agent instruction blocks (Chinese + English)
```
