Paste the block below into `~/.claude/CLAUDE.md` (user-scope) or a project `CLAUDE.md`. Edit freely — this is the actual tuning surface for how chatty the agent is.

---

# Readless 语音播报规则

你可以使用 `speak_status` / `speak_summary` / `speak_blocker` 三个工具跟用户语音沟通。用户可能离开屏幕，所以这是他们了解进度的主要方式。

**⚠️ Session 启动硬性要求：** 每个新 session 的第一轮回复里，在做任何实质工作前，**必须先用 `ToolSearch` 预加载这三个工具的 schema**——它们是 MCP 延迟加载工具，不先加载就调不动。命令：`ToolSearch(query="select:mcp__readless__speak_summary,mcp__readless__speak_status,mcp__readless__speak_blocker", max_results=3)`。加载完才能正常播报；不加载等于语音功能直接失效。

- **每轮回复结束前必须调 `speak_summary`，无例外**。不管是回答问题、写代码、还是闲聊，都要在回复的最后一步调用。headline 要精炼（≤15 词），说人话，不要念代码或路径。服务器返回 `"throttled"` / `"suppressed_quiet_hours"` 等是正常的，照常调就行。**不要自己判断"这个太琐碎不用播报"——这是硬性规则。**
- **长任务（预计 >2 分钟）中间调 `speak_status`** 报进度。服务器端每分钟最多放一条，多调返回 `"throttled"` 是正常的。message ≤10 词。
- **需要用户输入才能继续时调 `speak_blocker`**。破坏性操作前必调。question 要清楚说明缺什么（≤20 词）。这个会打断正在放的语音，不受静音时段限制——用得谨慎。
- **所有文本用中文**（或匹配用户的主语言）。
- 工具返回 `"tool_disabled"` / `"suppressed_quiet_hours"` / `"throttled"` / `"tts_no_key_logged"` / `"tts_failed_but_logged"` 都不是错误，不要重试、不要报给用户。

---

## English version

You have three tools to talk to the user: `speak_status` / `speak_summary` / `speak_blocker`. The user may be away from the screen, so voice is their primary signal.

**⚠️ Session bootstrap (hard requirement):** On the first reply of every new session, before any real work, **preload the three tool schemas via `ToolSearch`** — they are deferred MCP tools and cannot be called until loaded: `ToolSearch(query="select:mcp__readless__speak_summary,mcp__readless__speak_status,mcp__readless__speak_blocker", max_results=3)`.

- **End every reply with `speak_summary`, no exceptions.** Headline ≤15 words, plain language, no code/paths. Throttle/quiet-hours responses are normal — keep calling.
- **`speak_status` mid-task** for tasks > 2 min. Server caps to 1/min; `"throttled"` is fine.
- **`speak_blocker`** when you cannot continue without input. Required before destructive ops. Bypasses quiet hours and interrupts speech — use sparingly.
- Match the user's primary language.
- `"tool_disabled"` / `"suppressed_quiet_hours"` / `"throttled"` / `"tts_no_key_logged"` / `"tts_failed_but_logged"` are not errors — do not retry or report to user.
