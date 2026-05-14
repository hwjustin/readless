# readless

[English](./README.md) · [中文](./README.zh.md)

Claude Code 插件，每轮回复结束自动念出最后一段话，agent 卡住等用户输入时也会提醒——让你可以放心离开屏幕。

两个 hook，不需要 MCP，也不需要往 `CLAUDE.md` 贴任何东西：

| Hook | 触发时机 | 行为 |
|---|---|---|
| `Stop` | Assistant 一轮回复结束 | 读取最后一条 assistant 消息，截短后念出来 |
| `Notification` | Claude Code 请求权限 / 用户长时间未响应 | 打断当前语音，念出提示内容 |

默认 TTS 用系统自带语音（macOS `say` / Linux `espeak-ng` / Windows SAPI），**完全不需要 API key**。想要更好音质就在配置里填 OpenAI 或 ElevenLabs 的 key。

## 安装

```
/plugin marketplace add hwjustin/readless
/plugin install readless
```

**默认 `system` backend 不需要任何 pip 包**——hook 脚本会向上找 plugin 目录里的 `src/` import `readless`，默认后端除 Python 3.11+ 外零依赖。

想用云端 TTS 时，给 `/usr/bin/env python3` 解析到的那个 Python 装 extras：

```bash
pip install --user 'readless[openai] @ git+https://github.com/hwjustin/readless.git'
# 或
pip install --user 'readless[elevenlabs] @ git+https://github.com/hwjustin/readless.git'
```

到此为止。打开 Claude Code 跑一轮对话，就能听到声音。

## 配置（可选）

第一次运行自动从默认值生成 `~/.readless/config.yaml`。可以编辑：

- `system_voice: Tingting`——选 macOS 语音（`say -v '?'` 列所有）
- `tts_provider: openai` + `openai_api_key: sk-...`——用 OpenAI TTS
- `tts_provider: elevenlabs` + `elevenlabs_api_key: ...` + `elevenlabs_voice_id: ...`
- `quiet_hours.start / end`——夜间静音（不影响 notification）
- `summary_max_chars: 80`——念多少字符就截断

详见 [`config.example.yaml`](./config.example.yaml)。

## 为什么不会闪报错

hook 脚本（`hooks/readless_hook.py`）照搬了 [open-vibe-island](https://github.com/Octane0411/open-vibe-island) 的 fail-open 模式：

1. **永远 `exit 0`**——hook 进程不可能以非零状态退出
2. **顶层 `try / except: pass`** 吞掉所有异常
3. **stdout 一个字不写**（Stop / Notification 都不需要返回 directive JSON）
4. **fork 出子进程，setsid，stdio 重定向到 /dev/null**——真正的 TTS 工作和 Claude Code 的 stdio 完全脱钩，TTS 慢或失败都不可能冒回终端

所有异常追加写入 `~/.readless/log.jsonl` 供调试。

## 日志

```json
{"ts": "2026-05-14T22:30:00+08:00", "kind": "stop", "headline": "构建通过，3 个测试都过了。"}
{"ts": "2026-05-14T22:31:12+08:00", "kind": "notification", "headline": "Claude needs your permission to run Bash"}
```

## 协议

Apache 2.0——见 [LICENSE](./LICENSE)。

## 结构

```
.claude-plugin/
  plugin.json          声明 Stop + Notification hook
  marketplace.json     /plugin marketplace add 用的清单
hooks/
  readless_hook.py     封口入口；fork + detach
src/readless/
  hook_runner.py       事件分发 -> speak()
  tts.py               system / openai / elevenlabs 后端
  config.py            YAML 加载 + 静音时段计算
  logger.py            JSONL 追加写日志
```
