---
description: Install readless dependencies and add the agent instructions to CLAUDE.md so speak_summary / speak_status / speak_blocker get called. Default TTS is edge-tts (free, online, no API key).
---

You are setting up the `readless` plugin for the user. Two steps: install Python deps, then append the agent instructions to the user's CLAUDE.md. At the end, tell the user how to switch to OpenAI / ElevenLabs safely if they want.

## Step 1 — Install the readless Python package

Claude Code launches MCP servers with `python3` on PATH. The `readless` package and its `mcp` + `edge-tts` dependencies must be importable by that interpreter.

1. Check which Python is on PATH and whether `readless`, `mcp`, and `edge_tts` are already importable:
   ```bash
   python3 -c "import readless, mcp, edge_tts; print('readless ok')" 2>&1 || echo "needs install"
   ```

2. If they're missing, install from the plugin source. The plugin root is `${CLAUDE_PLUGIN_ROOT}`. Run:
   ```bash
   pip install --user -e "${CLAUDE_PLUGIN_ROOT}"
   ```
   - Default install brings in `edge-tts` so the user has a working, no-key, bilingual TTS backend immediately.
   - **Do NOT install the `[openai]` or `[elevenlabs]` extras here.** Those backends are opt-in — the user installs them later only if they want to use their own API key (see Step 3 below).
   - If `pip install --user` fails with "externally-managed-environment" (Homebrew Python on macOS, Debian-style Python on Linux), retry with `--break-system-packages` or set up a dedicated venv and adjust the MCP server `command` in the plugin manifest.

3. Verify:
   ```bash
   python3 -c "import readless.server; print('ok')"
   ```

4. Sanity-check the audio player edge-tts needs for playback:
   - macOS: `afplay` is built in — no action needed.
   - Linux: confirm `mpg123` or `ffplay` is installed (`which mpg123 ffplay`). If neither is present, suggest `apt install mpg123` (or `dnf` / `pacman` equivalent).
   - Windows: PowerShell + MediaPlayer ships with the OS — no action needed.

## Step 2 — Append the agent instructions to ~/.claude/CLAUDE.md

Claude Code merges `~/.claude/CLAUDE.md` into every session. Without this block, the agent will not know it should call `speak_summary` etc.

1. Ask the user which language version they want (default to the language of their previous message):
   - **中文** — for Chinese-speaking users
   - **English** — for English-speaking users

2. Check whether the block is already present:
   ```bash
   grep -q "Readless 语音播报规则\|speak_summary" ~/.claude/CLAUDE.md 2>/dev/null && echo "already present" || echo "needs append"
   ```

3. If it's not present, append the appropriate block from `${CLAUDE_PLUGIN_ROOT}/CLAUDE_EXAMPLE.md`. Read that file to get both language blocks; the file separates them with `## 中文版` and `## English version` headings. Extract the user's chosen block (everything from its `#` heading down to the next `---` or end of file) and append to `~/.claude/CLAUDE.md`. Create the file if it doesn't exist. Add a blank line before the appended content.

4. Confirm to the user what was appended (show them the snippet) so they can edit it later if they want different behavior.

## Step 3 — Tell the user how to switch to OpenAI / ElevenLabs (optional, secure)

After Step 1 the user already has a working TTS — `edge-tts` with the `zh-CN-XiaoxiaoNeural` voice, free, online, no key. **Most users should stop here.**

If the user wants to use OpenAI or ElevenLabs voices instead, tell them exactly this (do not ask them to paste the key into this chat — keys pasted here would land in the conversation context and the transcript):

> "If you'd rather use OpenAI or ElevenLabs voices, do this **in your own terminal** (not via me):
>
> ```bash
> # For OpenAI:
> pip install --user -e '${CLAUDE_PLUGIN_ROOT}[openai]'
> readless-setkey openai
>
> # For ElevenLabs:
> pip install --user -e '${CLAUDE_PLUGIN_ROOT}[elevenlabs]'
> readless-setkey elevenlabs
> ```
>
> `readless-setkey` will prompt you to paste the key with input hidden, write it to `~/.readless/config.yaml` (chmod 600), and flip `tts_provider` for you. The key never enters the Claude conversation."

**Important — what Claude must NOT do here:**

- Do not run `readless-setkey` via the Bash tool. It needs a real TTY for `getpass`, and even if it ran, the key would surface in the tool result.
- Do not ask the user for their key.
- If the user pastes a key into this chat anyway, refuse to write it to the config file. Tell them the key is now in the transcript and they should rotate it, then re-run `readless-setkey` themselves.

## Step 4 — Tell the user to restart Claude Code

The MCP server connection is established at session start. After installing the Python package, the user must restart Claude Code (close and reopen, or in CLI mode just start a fresh session) for `readless` to appear under `/mcp`.

Suggest:
> "Restart Claude Code, then run `/mcp` — you should see `readless ✓ Connected` with three tools. Try saying 'hello' to me to hear the first voice summary."

## Notes

- Default TTS backend is `edge` — uses Microsoft's free online TTS endpoint, no API key, handles Chinese + English code-switching naturally. If it can't reach the network, the server automatically falls back to the OS-native `system` backend (macOS `say` / Linux `espeak-ng` / Windows SAPI).
- `~/.readless/config.yaml` is auto-created on first run. To change voice, rate, or quiet hours, edit it directly.
- Env vars `OPENAI_API_KEY` / `ELEVENLABS_API_KEY` always override the config file — handy if the user prefers shell-rc-managed secrets.
- All tool calls are logged to `~/.readless/log.jsonl`.
