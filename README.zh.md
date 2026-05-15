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

只需要 PATH 上有 `uv`（[Astral 的 Python 启动器](https://github.com/astral-sh/uv)）—— 就这一个前置条件。`uv` 会自动准备 Python，你不用自己装 Python 3.10+，也不用管 virtualenv。

```bash
# 1. 装 uv（如果已经有就跳过）
curl -LsSf https://astral.sh/uv/install.sh | sh        # macOS / Linux
# brew install uv                                       # macOS 用 Homebrew
# irm https://astral.sh/uv/install.ps1 | iex            # Windows PowerShell
```

然后在 Claude Code 里：

```
/plugin marketplace add hwjustin/readless
/plugin install readless
/readless:setup
```

`/readless:setup` 做两件事：

1. 确认 `uv` 在 PATH 上（不在就提示装），并预热 `uvx --from readless-mcp readless`，这样首次 MCP 启动不用等下载。
2. 问你要中文还是英文版指令块，然后追加到 `~/.claude/CLAUDE.md`（用 marker 包裹，可幂等更新），agent 从此知道每轮要调 `speak_summary`。

完事后**彻底重启 Claude Code**（不是开新对话——要把 CLI / IDE 整个关掉重开，新的 PATH 才能被识别）。`/mcp` 应该显示 `readless ✓ Connected`。

> **为什么用 uv？** MCP SDK 要求 Python ≥3.10，但 macOS 系统自带的是 3.9。让用户自己装 Homebrew Python 或者管 venv 是上一版"装不上"的头号原因。`uv` 按需下载合适的 Python 到自己的缓存目录（`~/.cache/uv/`），在隔离环境里跑 PyPI 上的 `readless-mcp`，完全不动系统 Python。这也是 [MCP 官方仓库推荐的方式](https://github.com/modelcontextprotocol/servers)。

## 换成 OpenAI / ElevenLabs（可选）

默认 edge-tts 对绝大多数人够用。想用 OpenAI 或 ElevenLabs 自家声音的话，**在你自己的终端里**填 key——**不要把 key 粘进 Claude 对话**：

```bash
# OpenAI
uvx --from 'readless-mcp[openai]' readless-setkey openai     # 提示粘贴 key，输入不回显

# ElevenLabs
uvx --from 'readless-mcp[elevenlabs]' readless-setkey elevenlabs
```

`readless-setkey` 用 `getpass` 静默读取 key，写入 `~/.readless/config.yaml`（chmod 600），并自动切换 `tts_provider`。要清掉已保存的 key 用 `readless-setkey clear openai`（或 `elevenlabs`）。

环境变量 `OPENAI_API_KEY` / `ELEVENLABS_API_KEY` 优先级高于配置文件——如果你更习惯把 secret 放在 shell rc 里也可以。

## 配置

`~/.readless/config.yaml` 第一次跑时自动生成。常见改动：

- `edge_voice: en-US-AriaNeural`——换 edge-tts 声音（`edge-tts --list-voices` 列出全部）
- `edge_rate: "+20%"`——调语速
- `tts_provider: system`——强制走系统自带 TTS（完全离线场景）
- `system_voice: Tingting`——选 macOS 语音（`say -v '?'` 列所有）
- `quiet_hours.start / end`——按需开启的夜间静音（默认关；开了也不影响 `speak_blocker`）
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
  plugin.json          插件元信息（name / version / description）
  marketplace.json     /plugin marketplace add 用的清单
.mcp.json              MCP server 声明（uvx --from readless-mcp readless）
commands/
  setup.md             /readless:setup —— 确认 uv 已安装 + 写 CLAUDE.md
src/readless/
  server.py            FastMCP 入口 + 三个工具定义
  tts.py               edge / system / openai / elevenlabs 四种后端
  setkey.py            readless-setkey CLI —— 安全填 API key
  config.py            YAML 加载 + 静音时段计算（自带 YAML 解析回落）
  throttle.py          StatusThrottle（默认 1 次/分钟）
  logger.py            JSONL 追加写日志
CLAUDE_EXAMPLE.md      agent 指令块（中文 + 英文）
```
