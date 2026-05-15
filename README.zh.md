# readless

[English](./README.md) · [中文](./README.zh.md)

Claude Code 插件（MCP 模式），让 agent 主动把状态、总结、阻塞问题"念"出来——这样你跑长任务时可以放心离开屏幕。

三个 agent 主动调用的工具：

| 工具 | 调用时机 | 朗读长度 |
|---|---|---|
| `speak_summary(headline, details="")` | 每轮回复结束 / 用户关心的任务节点完成 | ≤ 50 字 |
| `speak_status(message)` | 长任务（预计 >2 分钟）中途报进度（服务端限频 1 次/分钟） | ≤ 10 词 |
| `speak_blocker(question)` | Agent 卡住，需要你输入。绕过静音、打断当前语音。 | ≤ 20 词 |

默认 TTS 后端是 **edge-tts**——调用微软免费在线 TTS 端点。**不需要 API key、不需要注册、不需要下载模型**，默认声音 `zh-CN-XiaoxiaoNeural` 处理中英混读非常自然。断网时自动回落到系统自带语音。如果想用自己的 OpenAI / ElevenLabs key，提供两个可选后端——通过单独的 CLI 工具填 key，**key 不会进入 Claude 对话上下文**。

## 安装

```
/plugin marketplace add hwjustin/readless
/plugin install readless
/readless:setup
```

`/readless:setup` 命令做两件事：

1. 跑 `pip install --user -e ${CLAUDE_PLUGIN_ROOT}`，让 `python3 -m readless.server` 能跑起来（plugin manifest 里 MCP 入口启动它）。默认安装会带上 `edge-tts`——开箱就能听到声音，不用任何 key。
2. 问你要中文还是英文版指令块，然后追加到 `~/.claude/CLAUDE.md`，agent 从此知道每轮要调 `speak_summary`。

完事后重启 Claude Code，`/mcp` 应该显示 `readless ✓ Connected`。

> **为什么还有一步 setup？** Claude Code 的 plugin manifest 不支持自动往用户的 CLAUDE.md 注入指令，MCP server 的 Python 依赖也得落到 `python3` 解析到的那个 Python 上。`/readless:setup` 把这两件事一次性确认完。

## 换成 OpenAI / ElevenLabs（可选）

默认 edge-tts 对绝大多数人够用。想用 OpenAI 或 ElevenLabs 自家声音的话，**在你自己的终端里**装 extras 并填 key——**不要把 key 粘进 Claude 对话**：

```bash
# OpenAI
pip install --user -e "${CLAUDE_PLUGIN_ROOT}[openai]"
readless-setkey openai            # 提示粘贴 key，输入不回显

# ElevenLabs
pip install --user -e "${CLAUDE_PLUGIN_ROOT}[elevenlabs]"
readless-setkey elevenlabs
```

`readless-setkey` 用 `getpass` 静默读取 key，写入 `~/.readless/config.yaml`（chmod 600），并自动切换 `tts_provider`。要清掉已保存的 key 用 `readless-setkey clear openai`（或 `elevenlabs`）。

环境变量 `OPENAI_API_KEY` / `ELEVENLABS_API_KEY` 优先级高于配置文件——如果你更习惯把 secret 放在 shell rc 里也可以。

## 配置

`~/.readless/config.yaml` 第一次跑时自动生成。常见改动：

- `edge_voice: en-US-AriaNeural`——换 edge-tts 声音（`edge-tts --list-voices` 列出全部）
- `edge_rate: "+20%"`——调语速
- `tts_provider: system`——强制走系统自带 TTS（完全离线场景）
- `system_voice: Tingting`——选 macOS 语音（`say -v '?'` 列所有）
- `quiet_hours.start / end`——夜间静音（不影响 `speak_blocker`）
- `tools.speak_status: false` 等——单独关闭某个工具
- `status_throttle_seconds: 60`——`speak_status` 限频

详见 [`config.example.yaml`](./config.example.yaml)。

## 调 agent 行为

[`CLAUDE_EXAMPLE.md`](./CLAUDE_EXAMPLE.md) 是"什么时候调哪个工具"的真正杠杆。觉得 agent 太啰嗦或太安静，去改你 `~/.claude/CLAUDE.md` 里那段——别改代码。

## 日志

所有工具调用追加写入 `~/.readless/log.jsonl`：

```json
{"ts": "2026-05-14T22:30:00+08:00", "kind": "summary", "headline": "构建通过，3 个测试都过了", "details": ""}
```

## 协议

Apache 2.0——见 [LICENSE](./LICENSE)。

## 结构

```
.claude-plugin/
  plugin.json          声明 readless MCP server
  marketplace.json     /plugin marketplace add 用的清单
commands/
  setup.md             /readless:setup —— pip install + 写 CLAUDE.md
src/readless/
  server.py            FastMCP 入口 + 三个工具定义
  tts.py               edge / system / openai / elevenlabs 四种后端
  setkey.py            readless-setkey CLI —— 安全填 API key
  config.py            YAML 加载 + 静音时段计算（自带 YAML 解析回落）
  throttle.py          StatusThrottle（默认 1 次/分钟）
  logger.py            JSONL 追加写日志
CLAUDE_EXAMPLE.md      agent 指令块（中文 + 英文）
```
