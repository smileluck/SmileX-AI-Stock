# 新闻聚合 PRD

## 1. 模块概述

| 属性 | 值 |
|---|---|
| 模块 ID | 14 |
| 模块名称 | 新闻聚合 |
| 核心功能 | 14 个新闻源统一抓取入库，含时间归一化、去重 |
| 关键文件 | `backend/app/services/news_sync.py`, `news_fetcher.py`, `backend/sources/` |
| 触发方式 | 定时任务 + REST API |

## 2. 新闻源配置

| source key | 中文名 | 采集方式 | API 端点 | page_size |
|---|---|---|---|---|
| `eastmoney` | 东方财富 | HTTP GET | np-listapi.eastmoney.com | 30 |
| `eastmoney_global` | 7x24全球 | HTTP GET | np-weblist.eastmoney.com | 50 |
| `cls` | 财联社综合 | HTTP GET + 签名 | www.cls.cn/v1/roll/get_roll_list | 20 |
| `cls_red` | 财联社加红 | HTTP GET + 签名 | www.cls.cn/v1/roll/get_roll_list | 20 |
| `cls_announcement` | 财联社公告 | HTTP GET + 签名 | www.cls.cn/v1/roll/get_roll_list | 20 |
| `cls_watch` | 财联社看盘 | HTTP GET + 签名 | www.cls.cn/v1/roll/get_roll_list | 20 |
| `cls_hk_us` | 财联社港美股 | HTTP GET + 签名 | www.cls.cn/v1/roll/get_roll_list | 20 |
| `cls_fund` | 财联社基金 | HTTP GET + 签名 | www.cls.cn/v1/roll/get_roll_list | 20 |
| `cls_remind` | 财联社提醒 | HTTP GET + 签名 | www.cls.cn/v1/roll/get_roll_list | 20 |
| `tonghuashun` | 同花顺 | akshare SDK | akshare.stock_info_global_ths() | - |
| `sina` | 新浪财经 | akshare SDK | akshare.stock_info_global_sina() | - |
| `wallstreetcn` | 华尔街见闻 | HTTP GET | api-one-wscn.awtmt.com | 50 |
| `yicai` | 第一财经 | HTTP GET | www.yicai.com/api/ajax/getlatest | - |
| `futu` | 富途快讯 | akshare SDK | akshare.stock_info_global_futu() | - |
| `xueqiu` | 雪球 | HTTP GET + Session | xueqiu.com | 15 |
| `jrj` | 金融界 | HTTP POST | gateway.jrj.com | 20 |

## 3. 数据处理

### 3.1 时间归一化

支持格式：
- 相对时间：`刚刚`、`X分钟前`、`X小时前`、`昨天 HH:MM`
- 月日格式：`MM月DD日 HH:MM`
- 标准格式：`YYYY-MM-DD HH:MM:SS`
- 无年份格式：`MM-DD HH:MM`（自动补全年份）

### 3.2 去重

- 按 `url` 字段 UNIQUE 约束去重
- `INSERT OR IGNORE` 策略

### 3.3 数据清理

- 保留最近 **7 天** 数据

## 4. 定时任务

| 任务 ID | 时间 | 说明 |
|---|---|---|
| `news_sync` | 每 5 分钟 | 新闻聚合抓取 |

## 5. API 端点

- `GET /api/v1/news` — 新闻列表
- `GET /api/v1/news/{id}` — 新闻详情

## 6. 数据表

- `news` — 新闻表
- `sync_log` — 采集日志表

## 7. 前端页面

- `/news` — 新闻聚合
