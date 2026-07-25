# SmileX-AI-Stock 功能模块总览

## 模块清单

| ID | 模块名称 | 触发方式 |
|---|---|---|
| 01 | [大盘/指数行情](./01-market-quote.md) | 定时任务 + API |
| 02 | [大盘 AI 分析](./02-market-analysis.md) | 定时任务 + API |
| 03 | [板块行情快照](./03-sector-quote.md) | 定时任务 + API |
| 04 | [板块 AI 分析](./04-sector-analysis.md) | 定时任务 + API |
| 05 | [板块强度追踪](./05-sector-strength.md) | 被调用 |
| 06 | [个股日线数据](./06-stock-daily.md) | 定时任务 + API |
| 07 | [涨停/炸板分析](./07-limit-up-analysis.md) | 定时任务 + API |
| 08 | [AI 个股推荐](./08-stock-recommendation.md) | 定时任务 + API |
| 09 | [明日策略](./09-tomorrow-strategy.md) | 定时任务 + API |
| 10 | [自选股管理](./10-watchlist.md) | 定时任务 + API |
| 11 | [券商研报同步](./11-research-sync.md) | 定时任务 + API |
| 12 | [研报 AI 选股](./12-research-pick.md) | 定时任务 + API |
| 13 | [AI 每日收盘报告](./13-ai-daily-report.md) | 定时任务 + API |
| 14 | [新闻聚合](./14-news-sync.md) | 定时任务 + API |
| 15 | [新闻-板块关联](./15-news-sector-assoc.md) | 被调用 |
| 16 | [基本面数据](./16-fundamental.md) | 定时任务 |
| 17 | [资金流明细](./17-capital-detail.md) | 定时任务 |
| 18 | [技术指标计算](./18-technical-indicators.md) | 被调用 |
| 19 | [个股 AI 分析](./19-stock-analysis.md) | REST API |
| 20 | [策略管理](./20-strategy.md) | REST API |
| 21 | [回测引擎](./21-backtest.md) | REST API |
| 22 | [历史数据回填](./22-backfill-daily.md) | 命令行 |
| 23 | [LLM 调用代理](./23-llm-proxy-client.md) | 被调用 |
| 24 | [LLM Proxy 服务](./24-llm-proxy-server.md) | 独立进程 |
| 25 | [定时调度器](./25-scheduler.md) | FastAPI 启动 |

## 架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                          前端 (React)                            │
│  /market /analysis/market /sector/today /stock/recommendation   │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                      FastAPI (backend/)                         │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ 定时调度器    │  │ REST API     │  │ LLM 调用代理 │          │
│  │ (scheduler)  │  │ (routes/)    │  │ (llm.py)    │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                     服务层 (services/)                    │   │
│  │  market/ sector/ stock/ news/ research/ watchlist/ ...   │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                   数据源 (sources/)                       │   │
│  │  eastmoney/ cls/ sina/ wallstreetcn/ xueqiu/ jrj/ ...   │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                   LLM Proxy (llm_proxy/)                        │
│                     LiteLLM + config.yaml                        │
│                  MiniMax / KIMI / Claude                         │
└─────────────────────────────────────────────────────────────────┘
```

## 数据流

```
新闻源 (14个) ──▶ news_sync ──▶ news ──▶ news_sector_assoc ──▶ news_sector_association
                                                              │
大盘快照 ──▶ index_snapshot ◀─────────────────────────────┘
                                                              │
板块快照 ──▶ sector_snapshot ◀──────────────────────────────┘
                                                              │
个股快照 ──▶ stock_daily ◀─────────────────────────────────┘
                                                              │
                                        ┌──────────────────────┘
                                        ▼
                              ┌──────────────────┐
                              │ LLM 分析服务      │
                              │ (analysis_chat)  │
                              └──────────────────┘
```

## 定时任务时间线

```
09:26  ┌─ stock_recommendation_morning
09:30  └─ watchlist_morning_analysis
11:25  └─ stock_recommendation_midday
12:00  ├─ market_snapshot_midday
12:01  ├─ stock_daily_snapshot_midday
12:02  ├─ sector_snapshot_midday
12:03  └─ limit_up_analysis_snapshot_midday
12:05  └─ limit_up_ai_analysis_midday
14:45  └─ stock_recommendation_afternoon
15:00  ├─ limit_up_analysis_snapshot_close
15:05  ├─ limit_up_ai_analysis_close
15:10  ├─ market_snapshot_close
15:12  ├─ stock_daily_snapshot_close
15:15  ├─ daily_market_analysis
15:20  ├─ sector_snapshot_close
15:25  ├─ ai_daily_report
15:30  ├─ watchlist_daily_snapshot
15:30  ├─ limit_up_snapshot
15:35  ├─ stock_recommendation_review
15:42  └─ watchlist_close_analysis
15:50  ├─ tomorrow_strategy_generation
15:58  └─ sector_ai_analysis
16:00  ├─ research_sync
16:10  └─ research_pick_generation
16:30  └─ stock_fundamental_snapshot
16:40  └─ stock_capital_detail_snapshot
17:00  └─ sync_log_cleanup
周日21:00 └─ sector_ai_analysis_sunday
```
