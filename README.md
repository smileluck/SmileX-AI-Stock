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
uvicorn app.main:app --port 8801 --reload
```

### 3. 前端

```bash
cd frontend
npm install
npm run dev
```

访问 http://localhost:5173，设置页面可查看 LiteLLM Proxy 连接状态。

## 板块数据

### 实时板块

后端启动后，工作日 15:20 自动执行板块数据快照（行业 + 概念），将实时行情和资金流向写入 SQLite。也可手动触发：

```bash
curl -X POST http://localhost:8801/api/v1/market/sector/snapshot
```

### 历史数据回填

`backfill_sector.py` 支持从东方财富或同花顺回填过去一年的板块历史 K 线数据。

```bash
cd backend

# 自动检测数据源（EM 可用则用 EM，否则用 THS）
python backfill_sector.py

# 强制指定数据源
python backfill_sector.py --source em    # 东方财富（板块编码与实时数据一致）
python backfill_sector.py --source ths   # 同花顺（独立编码体系，不依赖 EM）
```

| 数据源 | 说明 | 板块编码 |
|--------|------|----------|
| EM（东方财富） | `push2his.eastmoney.com` K 线接口，与实时数据一致 | BKxxxx |
| THS（同花顺） | akshare 同花顺源，EM 被限流时自动降级 | 881xxx / 30xxxx |

脚本自动跳过已有数据的板块，支持中断后续跑。

### 历史查询 API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/market/sector/history/date` | GET | 按日查询：`trade_date` + `sector_type` |
| `/market/sector/history/range` | GET | 区间统计：`start_date` + `end_date` + `sector_type` |
| `/market/sector/history/trend` | GET | 单板块趋势：`code` + 日期范围 |
| `/market/sector/history/dates` | GET | 可用快照日期列表 |
| `/market/sector/snapshot` | POST | 手动触发快照 |

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `MINIMAX_API_KEY` | MiniMax 模型 API Key（proxy 使用） | - |
| `LITELLM_PROXY_URL` | LiteLLM Proxy 地址 | `http://localhost:4000` |
| `LITELLM_MASTER_KEY` | Proxy Master Key（可选） | - |
