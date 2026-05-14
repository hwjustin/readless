---
description: Install readless dependencies and add the agent instructions to CLAUDE.md so speak_summary / speak_status / speak_blocker get called.
---

You are setting up the `readless` plugin for the user. Two steps: install Python deps, then append the agent instructions to the user's CLAUDE.md.

## Step 1 — Install the readless Python package

Claude Code launches MCP servers with `python3` on PATH. The `readless` package and its `mcp` dependency must be importable by that interpreter.

1. Check which Python is on PATH and whether `readless` and `mcp` are already importable:
   ```bash
   python3 -c "import readless, mcp; print('readless ok')" 2>&1 || echo "needs install"
   ```

2. If they're missing, install from the plugin source. The plugin root is `${CLAUDE_PLUGIN_ROOT}`. Run:
   ```bash
   pip install --user -e "${CLAUDE_PLUGIN_ROOT}"
   ```
   - Default install includes the `mcp` dependency (needed for the MCP server) and the built-in `system` TTS backend that uses macOS `say` / Linux `espeak-ng` / Windows SAPI — no API key required.
   - To use OpenAI or ElevenLabs voices instead, install with extras:
     ```bash
     pip install --user -e "${CLAUDE_PLUGIN_ROOT}[openai]"
     # or
     pip install --user -e "${CLAUDE_PLUGIN_ROOT}[elevenlabs]"
     ```
   - If `pip install --user` fails with "externally-managed-environment" (Homebrew Python on macOS, Debian-style Python on Linux), retry with `--break-system-packages` or set up a dedicated venv and adjust the MCP server `command` in the plugin manifest.

3. Verify:
   ```bash
   python3 -c "import readless.server; print('ok')"
   ```

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

## Step 3 — Tell the user to restart Claude Code

The MCP server connection is established at session start. After installing the Python package, the user must restart Claude Code (close and reopen, or in CLI mode just start a fresh session) for `readless` to appear under `/mcp`.

Suggest:
> "Restart Claude Code, then run `/mcp` — you should see `readless ✓ Connected` with three tools. Try saying 'hello' to me to hear the first voice summary."

## Optional follow-up

- Default TTS backend is `system` (zero config). To switch to OpenAI or ElevenLabs, edit `~/.readless/config.yaml` and set `tts_provider` plus the matching API key. Env vars `OPENAI_API_KEY` / `ELEVENLABS_API_KEY` override the config file.
- Quiet hours default to 23:00–08:00. `speak_summary` and `speak_status` are suppressed during that window; `speak_blocker` still plays.
- All tool calls are logged to `~/.readless/log.jsonl`.
