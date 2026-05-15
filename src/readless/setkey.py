"""readless-setkey — securely store an OpenAI or ElevenLabs API key.

Run this **in your own terminal**, not via an LLM/agent — `getpass.getpass()`
reads the key without echoing it, and the key never enters any model's
context. The key is written to ~/.readless/config.yaml (chmod 600).

Usage:
    readless-setkey openai
    readless-setkey elevenlabs
    readless-setkey clear openai          # blank the saved key
    readless-setkey clear elevenlabs
"""
from __future__ import annotations

import getpass
import re
import sys
from pathlib import Path

from .config import CONFIG_PATH, ensure_config_file

PROVIDERS: dict[str, tuple[str, str]] = {
    "openai": ("openai_api_key", "OpenAI API key (sk-...)"),
    "elevenlabs": ("elevenlabs_api_key", "ElevenLabs API key"),
}


def _print_usage() -> None:
    print(__doc__, file=sys.stderr)


def _mask(key: str) -> str:
    if len(key) <= 10:
        return "***"
    return f"{key[:4]}...{key[-4:]}"


def _set_field(text: str, field: str, value: str) -> str:
    """Set `field: "value"` in YAML text, preserving everything else."""
    pattern = rf"^{re.escape(field)}\s*:.*$"
    replacement = f'{field}: "{value}"'
    if re.search(pattern, text, flags=re.M):
        return re.sub(pattern, replacement, text, count=1, flags=re.M)
    return text.rstrip() + f"\n{replacement}\n"


def _write_config(text: str) -> None:
    CONFIG_PATH.write_text(text)
    try:
        CONFIG_PATH.chmod(0o600)
    except OSError:
        pass


def _set(provider: str) -> int:
    field, label = PROVIDERS[provider]
    ensure_config_file()

    try:
        key = getpass.getpass(f"Paste {label} (input hidden, Enter to cancel): ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\naborted", file=sys.stderr)
        return 1
    if not key:
        print("aborted: empty input", file=sys.stderr)
        return 1

    text = CONFIG_PATH.read_text()
    text = _set_field(text, "tts_provider", provider)
    text = _set_field(text, field, key)
    # tts_provider is an unquoted scalar — strip quotes the setter added.
    text = re.sub(
        r'^tts_provider:\s*"([^"]+)"',
        r"tts_provider: \1",
        text,
        count=1,
        flags=re.M,
    )
    _write_config(text)

    print(f"✓ saved to {CONFIG_PATH}")
    print(f"  tts_provider = {provider}")
    print(f"  {field} = {_mask(key)}")
    print("Restart Claude Code to pick up the change.")
    return 0


def _clear(provider: str) -> int:
    field, _ = PROVIDERS[provider]
    ensure_config_file()
    text = CONFIG_PATH.read_text()
    text = _set_field(text, field, "")
    _write_config(text)
    print(f"✓ cleared {field} in {CONFIG_PATH}")
    return 0


def main() -> int:
    args = sys.argv[1:]
    if not args:
        _print_usage()
        return 1

    if args[0] == "clear":
        if len(args) < 2 or args[1] not in PROVIDERS:
            _print_usage()
            return 1
        return _clear(args[1])

    if args[0] not in PROVIDERS:
        _print_usage()
        return 1
    return _set(args[0])


if __name__ == "__main__":
    sys.exit(main())
