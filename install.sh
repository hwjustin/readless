#!/usr/bin/env bash
# One-shot installer for readless. Idempotent — safe to re-run.
# Steps: create venv, pip install, seed ~/.readless/config.yaml, register with Claude Code.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$REPO_DIR/.venv"
PYTHON="${PYTHON:-python3}"
CONFIG_DIR="$HOME/.readless"
CONFIG_FILE="$CONFIG_DIR/config.yaml"

echo "==> readless install"
echo "    repo:   $REPO_DIR"
echo "    venv:   $VENV"
echo "    config: $CONFIG_FILE"

# 1. venv
if [[ ! -x "$VENV/bin/python" ]]; then
  echo "==> creating venv ($PYTHON)"
  "$PYTHON" -m venv "$VENV"
fi

# 2. install package
echo "==> installing readless (editable)"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -e "$REPO_DIR"

# 3. seed config
mkdir -p "$CONFIG_DIR"
if [[ ! -f "$CONFIG_FILE" ]]; then
  cp "$REPO_DIR/config.example.yaml" "$CONFIG_FILE"
  echo "==> seeded $CONFIG_FILE — edit it to add your OPENAI_API_KEY (or export the env var)"
else
  echo "==> $CONFIG_FILE already exists, leaving it alone"
fi

# 4. register with Claude Code (if `claude` CLI is on PATH)
if command -v claude >/dev/null 2>&1; then
  if claude mcp list 2>/dev/null | grep -q '^readless'; then
    echo "==> claude mcp: 'readless' already registered, skipping"
  else
    echo "==> registering with claude mcp (user scope)"
    claude mcp add --scope user readless -- "$VENV/bin/python" -m readless.server
  fi
else
  echo "==> 'claude' CLI not found — skipping mcp registration."
  echo "    Run manually:"
  echo "    claude mcp add --scope user readless -- \"$VENV/bin/python\" -m readless.server"
fi

cat <<EOF

==> done. Next steps:
  1. Put your OpenAI key in $CONFIG_FILE (or export OPENAI_API_KEY).
  2. Paste the block from $REPO_DIR/CLAUDE_EXAMPLE.md into ~/.claude/CLAUDE.md.
  3. Restart Claude Code, then ask it to call speak_summary to verify.
EOF
