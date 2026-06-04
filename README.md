# SmileX AI Stock

AI 驱动的股票资讯聚合与分析平台。

## 项目结构

```
SmileX-AI-Stock/
├── llm_proxy/          # LiteLLM Proxy 服务
│   └── config.yaml     # 模型路由配置
├── backend/            # FastAPI 后端
├── frontend/           # React + TypeScript 前端
└── docs/
```

## 快速启动

### 1. LiteLLM Proxy

```bash
# 设置模型 API Key
export MINIMAX_API_KEY=your-api-key

# 启动 proxy
litellm --config llm_proxy/config.yaml --port 4000
```

### 2. 后端

```bash
cd backend
cp .env.example .env   # 按需修改配置
pip install -e .
uvicorn app.main:app --port 8001 --reload
```

### 3. 前端

```bash
cd frontend
npm install
npm run dev
```

访问 http://localhost:5173，设置页面可查看 LiteLLM Proxy 连接状态。

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `MINIMAX_API_KEY` | MiniMax 模型 API Key（proxy 使用） | - |
| `LITELLM_PROXY_URL` | LiteLLM Proxy 地址 | `http://localhost:4000` |
| `LITELLM_MASTER_KEY` | Proxy Master Key（可选） | - |
