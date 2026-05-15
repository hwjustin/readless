---
description: Ensure `uv` is installed and append the readless agent instructions to ~/.claude/CLAUDE.md so speak_summary / speak_status / speak_blocker get called. The MCP server itself is launched by `uvx readless-mcp` — uv provisions Python automatically, no manual pip install or virtualenv.
---

You are setting up the `readless` plugin for the user. Two steps: confirm `uv` is available (the MCP entry in `plugin.json` uses `uvx`), then append the agent instructions to the user's CLAUDE.md. At the end, tell the user how to switch to OpenAI / ElevenLabs safely if they want.

**Why uv instead of pip?** The MCP SDK requires Python ≥3.10, but macOS ships Python 3.9 system-wide. `uv` downloads and caches the right Python for the user automatically, then runs `readless-mcp` from PyPI in an isolated environment. No system-Python contamination, no PEP 668 issues, no venv management for the user.

## Step 1 — Ensure `uv` is on PATH

`uvx` is what `plugin.json` calls. If it's missing, the readless MCP server cannot start.

1. Check whether `uvx` is already installed:
   ```bash
   command -v uvx && uvx --version
   ```

2. If it's missing, install it. The official Astral installer drops `uv` / `uvx` into `~/.local/bin/`:
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
   - macOS users with Homebrew can use `brew install uv` instead.
   - Windows users (rare for Claude Code, but possible): `irm https://astral.sh/uv/install.ps1 | iex` in PowerShell.

3. **Important:** after install, `~/.local/bin/` must be on `PATH` in the shell Claude Code inherits. The installer usually edits `~/.zshrc` / `~/.bashrc` for the user, but the change only takes effect in **new** shells. Tell the user to **fully restart Claude Code** (not just start a new chat) so the new PATH is picked up.

4. Pre-warm the package so the first MCP startup isn't a 30-second download:
   ```bash
   uvx --from readless-mcp readless --help 2>/dev/null || echo "(first run will fetch Python + package; that's normal)"
   ```

5. Sanity-check the audio player for edge-tts playback:
   - macOS: `afplay` is built in — no action.
   - Linux: confirm `mpg123` or `ffplay` is installed (`which mpg123 ffplay`). If neither, suggest `apt install mpg123` / `dnf install mpg123` / `pacman -S mpg123`.
   - Windows: PowerShell + MediaPlayer ships with the OS — no action.

## Step 2 — Append the agent instructions to ~/.claude/CLAUDE.md

Claude Code merges `~/.claude/CLAUDE.md` into every session. Without this block, the agent does not know it should call `speak_summary` etc.

1. Ask the user which language version they want (default to the language of their previous message):
   - **中文** — for Chinese-speaking users
   - **English** — for English-speaking users

2. Check whether the readless block is already present (marker-bounded for idempotency):
   ```bash
   grep -q "<!-- readless:begin -->" ~/.claude/CLAUDE.md 2>/dev/null && echo "already present" || echo "needs append"
   ```

3. If already present, do nothing — tell the user the block is there. They can edit between the markers if they want different behavior.

4. If not present, build the full marker-wrapped block by taking the chosen language section from `${CLAUDE_PLUGIN_ROOT}/CLAUDE_EXAMPLE.md` and wrapping it like this:
   ```
   <!-- readless:begin -->
   <!-- managed by /readless:setup — edit freely; keep these markers for idempotent updates -->

   ...the chosen language block from CLAUDE_EXAMPLE.md...

   <!-- readless:end -->
   ```

5. **Print the full block to the user first**, with this framing (in their language):
   > "I'll try to append the block below to `~/.claude/CLAUDE.md`. If the auto-mode classifier blocks the write or you decline the permission prompt, just paste it in yourself — same effect. After that, restart Claude Code."
   >
   > ```
   > [full marker-wrapped block here, fenced so it's easy to copy]
   > ```

   Doing this **before** attempting the write means the user always has a manual fallback if anything goes wrong with the next step. Don't skip it even when you expect the write to succeed.

6. Then attempt to append the block to `~/.claude/CLAUDE.md` (create the file if missing; add a blank line before the block if the file already had content).

7. Report the outcome honestly:
   - **Write succeeded** → "✓ Appended to `~/.claude/CLAUDE.md`. Restart Claude Code to activate."
   - **Write was denied / failed for any reason** → "✗ Could not write `~/.claude/CLAUDE.md` automatically (auto-mode classifier or permission decline). Paste the block above into `~/.claude/CLAUDE.md` yourself, then restart Claude Code." **Do not claim setup succeeded when the file wasn't actually written.**

## Step 3 — Tell the user how to switch to OpenAI / ElevenLabs (optional, secure)

After Step 1+2 the user already has a working TTS — `edge-tts` with the `zh-CN-XiaoxiaoNeural` voice, free, online, no key. **Most users should stop here.**

If the user wants OpenAI or ElevenLabs voices, tell them exactly this (do NOT ask them to paste the key into this chat — keys pasted here would land in the conversation context and the transcript):

> "If you'd rather use OpenAI or ElevenLabs voices, do this **in your own terminal** (not via me):
>
> ```bash
> # For OpenAI:
> uvx --from 'readless-mcp[openai]' readless-setkey openai
>
> # For ElevenLabs:
> uvx --from 'readless-mcp[elevenlabs]' readless-setkey elevenlabs
> ```
>
> `readless-setkey` will prompt you to paste the key with input hidden, write it to `~/.readless/config.yaml` (chmod 600), and flip `tts_provider` for you. The key never enters the Claude conversation."

**Important — what Claude must NOT do here:**

- Do not run `readless-setkey` via the Bash tool. It needs a real TTY for `getpass`, and even if it ran, the key would surface in the tool result.
- Do not ask the user for their key.
- If the user pastes a key into this chat anyway, refuse to write it to the config file. Tell them the key is now in the transcript and they should rotate it, then re-run `readless-setkey` themselves.

## Step 4 — Tell the user to restart Claude Code

The MCP server connection is established at session start, and any new PATH from the uv installer also requires a fresh shell. After Steps 1 and 2, the user must **fully restart Claude Code** (close and reopen the CLI / IDE host, not just start a new chat) for `readless` to appear under `/mcp` as `✓ Connected`.
