#!/usr/bin/env python3
"""Stop hook: force Claude to call speak_summary before ending the turn.

Reads the transcript, scans the current assistant turn (everything after the
last user message) for a `mcp__readless__speak_summary` tool_use. If it's
missing, emits a block decision so Claude loops once more and plays the
summary — the headline is still written by the model.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SUMMARY_TOOL = "mcp__readless__speak_summary"


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    if payload.get("stop_hook_active"):
        sys.exit(0)

    transcript_path = payload.get("transcript_path")
    if not transcript_path or not Path(transcript_path).exists():
        sys.exit(0)

    entries: list[dict] = []
    with open(transcript_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    last_user_idx = -1
    for i, e in enumerate(entries):
        if e.get("type") == "user":
            last_user_idx = i

    tail = entries[last_user_idx + 1 :] if last_user_idx >= 0 else entries

    for e in tail:
        if e.get("type") != "assistant":
            continue
        msg = e.get("message", {})
        content = msg.get("content", [])
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == SUMMARY_TOOL:
                sys.exit(0)

    reason = (
        "本轮还没播报进度。请立刻调用 mcp__readless__speak_summary，"
        "headline 用 ≤15 个中文字简洁概括你刚才做的事（说人话，不要念代码或路径），"
        "然后再次结束回复。如果工具 schema 未加载，先用 ToolSearch(query=\"select:mcp__readless__speak_summary\") 加载。"
        "不要输出其他文本。"
    )
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


if __name__ == "__main__":
    main()
