# LLM Proxy 服务 PRD

## 1. 模块概述

| 属性 | 值 |
|---|---|
| 模块 ID | 24 |
| 模块名称 | LLM Proxy 服务（LiteLLM） |
| 核心功能 | LiteLLM 代理服务，统一路由 MiniMax-M3 / KIMI-K2.6 / Claude-Sonnet/Opus/Haiku；主密钥认证 |
| 关键文件 | `llm_proxy/config.yaml`, `pyproject.toml`, `start.sh` |
| 触发方式 | 独立进程 `./start.sh` |

## 2. 模型配置

| 模型 ID | 底层模型 | 用途 |
|---|---|---|
| `analysis` | KIMI-K2.6 | 市场分析、预测、复盘 |
| `news-scorer` | KIMI-K2.6 | 新闻影响力评分 |
| `chat` | MiniMax-M3 | 用户对话 |
| `claude-sonnet` | Claude Sonnet | 备用分析 |
| `claude-opus` | Claude Opus | 复杂分析任务 |
| `claude-haiku` | Claude Haiku | 轻量任务 |

## 3. 配置文件

位置：`llm_proxy/config.yaml`

```yaml
model_list:
  - model_name: analysis
    litellm_params:
      model: kimi/kimi-k2.6
      api_key: os.environ/KIMI_API_KEY
      ...

  - model_name: chat
    litellm_params:
      model: minimax/minimax-精iseable-01
      ...
```

## 4. 服务管理

| 操作 | 命令 |
|---|---|
| 启动 | `./start.sh` 或 `python main.py` |
| 停止 | `pkill -f "litellm"` |
| 重启 | 先停止再启动 |

## 5. API 端点

- `POST /chat/completions` — OpenAI 兼容接口
- `GET /models` — 模型列表

## 6. 前端页面

- `/ai-assistant/llm-config` — LLM 配置
