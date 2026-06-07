import json
import logging
from datetime import datetime

from app.database import get_connection
from app.services import llm

logger = logging.getLogger(__name__)

_DEFAULT_STRATEGIES = [
    {
        "name": "综合个股分析",
        "type": "stock_analysis",
        "description": "从基本面、技术面、消息面、资金流和市场情绪五个维度对个股进行综合评分分析",
        "weight_config": {"fundamentals": 30, "technicals": 25, "news": 20, "capital_flow": 15, "sentiment": 10},
        "prompt_template": """\
你是一位资深A股个股分析师，擅长从多维度对个股进行深度分析评估。

## 分析维度与权重

请严格按照以下五个维度及其权重占比进行分析，每个维度需给出评分（1-10分）和详细评分理由：

1. **基本面分析（权重30%）**
   - 财务指标：PE/PB/ROE/营收增长率/净利润增长率
   - 行业地位：市场份额、竞争优势、护城河
   - 估值水平：与同行业对比是否合理
   - 盈利质量：经营性现金流、毛利率趋势

2. **技术面分析（权重25%）**
   - K线形态：近期走势形态、关键支撑位和阻力位
   - 均线系统：MA5/MA10/MA20/MA60排列及趋势
   - 技术指标：MACD金叉/死叉、RSI超买超卖、KDJ信号
   - 成交量分析：量价配合、放量突破或缩量整理

3. **消息面分析（权重20%）**
   - 公司公告：业绩预告、重大合同、股权变动
   - 政策影响：行业政策利好利空
   - 市场热点：概念题材是否契合当前市场主线
   - 分析师评级：机构研报观点和目标价

4. **资金流向分析（权重15%）**
   - 主力资金：大单/特大单净流入流出
   - 北向资金：外资持股变化
   - 龙虎榜数据：知名游资/机构席位
   - 融资融券：融资余额变化趋势

5. **市场情绪分析（权重10%）**
   - 涨停/跌停表现：封板强度、开板次数
   - 换手率：活跃程度和筹码分布
   - 板块联动：所属板块整体表现
   - 市场情绪指数：赚钱效应和恐慌程度

## 输出格式

先用自由文本输出详细分析，然后输出 ```json``` 代码块：

```json
{
  "stock_name": "股票名称",
  "stock_code": "股票代码",
  "overall_score": 7.5,
  "dimensions": {
    "fundamentals": {"score": 8, "weight": 30, "weighted_score": 2.4, "reason": "评分理由"},
    "technicals": {"score": 7, "weight": 25, "weighted_score": 1.75, "reason": "评分理由"},
    "news": {"score": 8, "weight": 20, "weighted_score": 1.6, "reason": "评分理由"},
    "capital_flow": {"score": 6, "weight": 15, "weighted_score": 0.9, "reason": "评分理由"},
    "sentiment": {"score": 7, "weight": 10, "weighted_score": 0.7, "reason": "评分理由"}
  },
  "risk_level": "medium",
  "confidence": 0.75,
  "suggestion": "操作建议",
  "target_price": 0,
  "stop_loss_price": 0
}
```

注意：weighted_score = score × weight / 10，overall_score 为各维度 weighted_score 之和。\
""",
    },
    {
        "name": "行业轮动分析",
        "type": "sector_analysis",
        "description": "分析行业板块趋势，识别板块轮动机会和资金流向",
        "weight_config": {"fundamentals": 20, "technicals": 20, "news": 25, "capital_flow": 25, "sentiment": 10},
        "prompt_template": """\
你是一位资深A股板块分析师，专注于行业和概念板块的轮动研究。请根据以下板块数据，生成全面的板块分析报告。

## 分析维度与权重

请严格按照以下五个维度及其权重占比进行分析：

1. **基本面分析（权重20%）**
   - 行业景气度：PMI、行业增速、周期位置
   - 政策环境：产业政策支持力度、监管变化
   - 估值水平：板块PE/PB历史分位数

2. **技术面分析（权重20%）**
   - 板块指数走势：趋势方向、支撑阻力
   - 量价关系：放量上涨或缩量下跌信号
   - 相对强度：与大盘对比的相对表现

3. **消息面分析（权重25%）**
   - 政策催化：国家级产业政策、地方扶持政策
   - 事件驱动：行业重大事件、技术突破
   - 市场预期：市场对行业的预期变化

4. **资金流向分析（权重25%）**
   - 主力资金偏好：大单资金流入流出
   - 北向资金动向：外资板块配置变化
   - 机构调仓：基金重仓板块变化

5. **市场情绪分析（权重10%）**
   - 板块热度：涨停股数量、领涨股表现
   - 龙头股走势：板块龙头强弱判断
   - 市场情绪共振：板块联动效应

## 报告结构

### 一、行业板块概览
总结当日行业板块整体表现、涨跌比例、市场广度。

### 二、热门行业板块（Top 5）
分析领涨行业板块及驱动因素，指出持续性判断。每个板块给出评分和理由。

### 三、冷门行业板块（Bottom 3）
分析领跌行业板块及原因，是否存在超跌反弹机会。

### 四、概念板块亮点
分析热门概念板块，指出市场炒作主线和题材轮动方向。

### 五、资金流向分析
分析主力资金偏好，哪些板块受资金追捧，哪些遭到抛售。

### 六、板块轮动趋势
根据近期数据判断板块轮动方向，哪些板块可能接棒。

### 七、明日板块展望
预测下一个交易日可能活跃的板块及逻辑。

最后输出 ```json``` 代码块：
```json
{
  "hot_sectors": [{"name": "板块名", "score": 8.5, "reason": "评分理由", "persistence": "high"}],
  "cold_sectors": [{"name": "板块名", "score": 3.0, "reason": "评分理由", "rebound": false}],
  "rotation_direction": "轮动方向描述",
  "confidence": 0.7,
  "risk_level": "medium"
}
```\
""",
    },
    {
        "name": "大盘趋势预测",
        "type": "market_analysis",
        "description": "分析大盘走势，预测市场方向、关键点位和风险等级",
        "weight_config": {"fundamentals": 20, "technicals": 30, "news": 25, "capital_flow": 15, "sentiment": 10},
        "prompt_template": """\
你是一位资深A股市场分析师。请根据当日市场数据和新闻，提供专业的大盘分析，并对下一个交易日做出预测。

## 分析维度与权重

请严格按照以下五个维度及其权重占比进行分析，每个维度需给出评分和详细理由：

1. **基本面分析（权重20%）**
   - 宏观经济数据：GDP、PMI、CPI、PPI等核心指标
   - 货币政策：MLF/LPR利率、央行公开市场操作
   - 国际环境：美联储政策、中美关系、地缘政治
   - 估值水平：主要指数PE/PB历史分位数

2. **技术面分析（权重30%）**
   - 指数走势：趋势方向、均线系统排列
   - 成交量：量价配合程度、地量/天量信号
   - 支撑阻力：关键支撑位和阻力位
   - 技术形态：头肩顶底、双顶双底、三角形整理等

3. **消息面分析（权重25%）**
   - 政策动向：国家重大政策、证监会公告
   - 外围市场：美股、港股、欧洲市场表现
   - 突发事件：对市场有重大影响的突发事件
   - 市场预期：主流机构对后市的看法

4. **资金流向分析（权重15%）**
   - 两市成交额：资金活跃度
   - 北向资金：外资流入流出及趋势
   - 融资融券：杠杆资金变化
   - ETF申赎：宽基ETF资金流向

5. **市场情绪分析（权重10%）**
   - 涨跌家数：上涨/下跌/平盘家数比
   - 涨停/跌停数：极端情绪指标
   - 换手率：市场活跃程度
   - 赚钱效应：实际赚钱难度

## 输出要求

1. 先输出自由文本的当日大盘分析（包括各指数表现、成交量变化、市场情绪等）
2. 然后输出对下一个交易日的预测，也是自由文本
3. 最后输出 ```json``` 代码块，包含结构化预测数据：

```json
{
  "overall_direction": "up 或 down 或 flat",
  "confidence": 0.0到1.0之间的数字,
  "indices": {
    "sh000001": {"predicted_change_pct": 0.5, "support": 3300, "resistance": 3380},
    "sz399001": {"predicted_change_pct": -0.3, "support": 10500, "resistance": 10800},
    "sz399006": {"predicted_change_pct": 0.2, "support": 2100, "resistance": 2150}
  },
  "key_factors": ["因素1", "因素2", "因素3"],
  "risk_level": "low 或 medium 或 high",
  "dimensions": {
    "fundamentals": {"score": 7, "weight": 20, "reason": "评分理由"},
    "technicals": {"score": 6, "weight": 30, "reason": "评分理由"},
    "news": {"score": 8, "weight": 25, "reason": "评分理由"},
    "capital_flow": {"score": 5, "weight": 15, "reason": "评分理由"},
    "sentiment": {"score": 7, "weight": 10, "reason": "评分理由"}
  }
}
```

注意：indices 中包含所有主要指数代码（sh000001, sz399001, sz399006, sh000688, sh000300, sh000016, sh000905, sh000852）。\
""",
    },
    {
        "name": "个股复盘评价",
        "type": "stock_review",
        "description": "复盘个股历史分析表现，评估预测准确性和改进方向",
        "weight_config": {"fundamentals": 25, "technicals": 30, "news": 15, "capital_flow": 20, "sentiment": 10},
        "prompt_template": """\
你是一位严谨的A股市场分析师，负责复盘个股分析的预测准确性。请对比之前的分析预测与实际市场表现，给出客观评价。

## 复盘维度与权重

请严格按照以下五个维度进行复盘分析：

1. **基本面复盘（权重25%）**
   - 预测时对基本面的判断是否准确
   - 是否遗漏了重要的财务指标变化
   - 行业景气度判断是否与实际一致

2. **技术面复盘（权重30%）**
   - 支撑位/阻力位判断是否有效
   - 趋势方向预判是否正确
   - 技术指标信号是否得到验证
   - 成交量预判与实际偏差

3. **消息面复盘（权重15%）**
   - 哪些消息被正确预判影响
   - 哪些重要消息被遗漏
   - 消息影响的持续时间和力度判断

4. **资金流向复盘（权重20%）**
   - 主力资金流向预判是否准确
   - 北向资金/机构资金动向是否被正确预判
   - 资金对股价的实际推动效果

5. **市场情绪复盘（权重10%）**
   - 市场情绪判断是否准确
   - 板块联动效应是否如预期
   - 涨停/跌停等极端情绪是否被合理评估

## 输出要求

1. 总体评价：分析方向是否正确？置信度是否合理？综合评分
2. 逐维度对比：每个维度的预测vs实际，偏差有多大，给出具体理由
3. 关键因素分析：哪些因素被正确预判，哪些被忽略
4. 改进建议：下次分析应该注意什么，哪些维度需要加强

最后输出 ```json``` 代码块：
```json
{
  "prediction_accuracy": 0.7,
  "direction_correct": true,
  "dimensions": {
    "fundamentals": {"predicted": 8, "actual": 7, "deviation": -1, "reason": "偏差理由"},
    "technicals": {"predicted": 7, "actual": 5, "deviation": -2, "reason": "偏差理由"},
    "news": {"predicted": 6, "actual": 8, "deviation": 2, "reason": "偏差理由"},
    "capital_flow": {"predicted": 7, "actual": 6, "deviation": -1, "reason": "偏差理由"},
    "sentiment": {"predicted": 7, "actual": 7, "deviation": 0, "reason": "偏差理由"}
  },
  "missed_factors": ["遗漏因素1", "遗漏因素2"],
  "improvement_suggestions": ["建议1", "建议2"]
}
```\
""",
    },
    {
        "name": "智能选股推荐",
        "type": "stock_recommendation",
        "description": "基于多因子模型从涨停股、热门股中筛选推荐潜力个股",
        "weight_config": {"fundamentals": 25, "technicals": 20, "news": 20, "capital_flow": 25, "sentiment": 10},
        "prompt_template": """\
你是一位资深A股投资顾问，负责根据当日市场数据为用户挑选具有投资价值的个股。

## 选股维度与权重

请严格按照以下五个维度及其权重占比进行选股评分：

1. **基本面筛选（权重25%）**
   - 财务健康：营收、净利润增长率为正
   - 估值合理：PE/PB不高于行业均值
   - 行业地位：细分领域龙头或有独特优势
   - 排除风险：排除ST、*ST、退市风险股

2. **技术面筛选（权重20%）**
   - 趋势向上：站上5日/10日均线
   - 量价配合：放量突破或缩量回踩
   - 形态良好：突破关键阻力位或回踩支撑位
   - 技术指标：MACD金叉、RSI适中(40-70)

3. **消息面筛选（权重20%）**
   - 利好催化：近期有政策利好或公司利好
   - 热门题材：属于当前市场主线题材
   - 机构关注：有机构研报覆盖或上调评级
   - 概念驱动：所属概念板块整体走强

4. **资金流向筛选（权重25%）**
   - 主力资金：大单/特大单净流入
   - 北向资金：外资增持
   - 龙虎榜：知名游资或机构买入
   - 连续性：资金连续多日流入

5. **市场情绪筛选（权重10%）**
   - 涨停表现：封板强度、涨停次数
   - 换手率适中：3%-15%为佳
   - 板块共振：所属板块整体上涨
   - 市场情绪：大盘情绪向好时加分

## 输出格式

请推荐 5-10 只有潜力的个股，严格用 ```json``` 包裹的 JSON 数组输出：

```json
[
  {
    "code": "600519",
    "name": "贵州茅台",
    "score": 8.5,
    "dimensions": {
      "fundamentals": {"score": 9, "weight": 25, "reason": "评分理由"},
      "technicals": {"score": 8, "weight": 20, "reason": "评分理由"},
      "news": {"score": 8, "weight": 20, "reason": "评分理由"},
      "capital_flow": {"score": 9, "weight": 25, "reason": "评分理由"},
      "sentiment": {"score": 7, "weight": 10, "reason": "评分理由"}
    },
    "reason": "推荐理由（50-100字，结合当日市场表现）",
    "strategy": "操作策略",
    "target_price": 1850.0,
    "stop_loss_price": 1700.0,
    "risk_level": "low",
    "confidence": 0.8,
    "sector": "白酒"
  }
]
```

注意：
- score = Σ(dimension_score × weight / 10)，满分10分
- 优先从涨停股中筛选强势品种
- 关注主力资金大幅流入的个股
- 兼顾不同风险偏好的品种
- 不推荐ST、*ST股票\
""",
    },
]


def _row_to_dict(row) -> dict:
    d = dict(row)
    if d.get("weight_config"):
        d["weight_config"] = json.loads(d["weight_config"])
    else:
        d["weight_config"] = {"fundamentals": 30, "technicals": 25, "news": 20, "capital_flow": 15, "sentiment": 10}
    if d.get("output_format"):
        d["output_format"] = json.loads(d["output_format"])
    else:
        d["output_format"] = {}
    for bool_field in ("news_enabled", "is_enabled", "is_default"):
        d[bool_field] = bool(d.get(bool_field, 0))
    return d


def list_strategies(strategy_type: str | None = None, is_enabled: bool | None = None) -> tuple[list[dict], int]:
    conn = get_connection()
    try:
        conditions = []
        params = []
        if strategy_type:
            conditions.append("type = ?")
            params.append(strategy_type)
        if is_enabled is not None:
            conditions.append("is_enabled = ?")
            params.append(1 if is_enabled else 0)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        total = conn.execute(f"SELECT COUNT(*) FROM strategy {where}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM strategy {where} ORDER BY sort_order, id",
            params,
        ).fetchall()
        return [_row_to_dict(r) for r in rows], total
    finally:
        conn.close()


def get_strategy(strategy_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM strategy WHERE id = ?", (strategy_id,)).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def create_strategy(data: dict) -> dict:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    weight_json = json.dumps(data.get("weight_config", {}), ensure_ascii=False)
    output_json = json.dumps(data.get("output_format", {}), ensure_ascii=False)
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO strategy
               (name, type, description, prompt_template, weight_config, news_enabled, news_count,
                output_format, is_enabled, is_default, sort_order, model_override, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                data["name"],
                data["type"],
                data.get("description", ""),
                data.get("prompt_template", ""),
                weight_json,
                1 if data.get("news_enabled", True) else 0,
                data.get("news_count", 15),
                output_json,
                1 if data.get("is_enabled", True) else 0,
                0,
                data.get("sort_order", 0),
                data.get("model_override"),
                now,
                now,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM strategy WHERE id = last_insert_rowid()").fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def update_strategy(strategy_id: int, data: dict) -> dict | None:
    existing = get_strategy(strategy_id)
    if not existing:
        return None

    fields = []
    params = []
    mapping = {
        "name": "name",
        "type": "type",
        "description": "description",
        "prompt_template": "prompt_template",
        "news_count": "news_count",
        "sort_order": "sort_order",
        "model_override": "model_override",
    }
    for py_key, db_key in mapping.items():
        if py_key in data and data[py_key] is not None:
            fields.append(f"{db_key} = ?")
            params.append(data[py_key])

    if "weight_config" in data and data["weight_config"] is not None:
        fields.append("weight_config = ?")
        params.append(json.dumps(data["weight_config"], ensure_ascii=False))
    if "output_format" in data and data["output_format"] is not None:
        fields.append("output_format = ?")
        params.append(json.dumps(data["output_format"], ensure_ascii=False))
    if "news_enabled" in data and data["news_enabled"] is not None:
        fields.append("news_enabled = ?")
        params.append(1 if data["news_enabled"] else 0)
    if "is_enabled" in data and data["is_enabled"] is not None:
        fields.append("is_enabled = ?")
        params.append(1 if data["is_enabled"] else 0)

    if not fields:
        return existing

    fields.append("updated_at = ?")
    params.append(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    params.append(strategy_id)

    conn = get_connection()
    try:
        conn.execute(f"UPDATE strategy SET {', '.join(fields)} WHERE id = ?", params)
        conn.commit()
        return get_strategy(strategy_id)
    finally:
        conn.close()


def delete_strategy(strategy_id: int) -> bool:
    existing = get_strategy(strategy_id)
    if not existing:
        return False
    if existing["is_default"]:
        return False
    conn = get_connection()
    try:
        conn.execute("DELETE FROM strategy WHERE id = ?", (strategy_id,))
        conn.commit()
        return True
    finally:
        conn.close()


def toggle_strategy(strategy_id: int) -> dict | None:
    existing = get_strategy(strategy_id)
    if not existing:
        return None
    new_val = 0 if existing["is_enabled"] else 1
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE strategy SET is_enabled = ?, updated_at = ? WHERE id = ?",
            (new_val, now, strategy_id),
        )
        conn.commit()
        return get_strategy(strategy_id)
    finally:
        conn.close()


def duplicate_strategy(strategy_id: int) -> dict | None:
    existing = get_strategy(strategy_id)
    if not existing:
        return None
    return create_strategy({
        "name": f"{existing['name']} (副本)",
        "type": existing["type"],
        "description": existing["description"],
        "prompt_template": existing["prompt_template"],
        "weight_config": existing["weight_config"],
        "news_enabled": existing["news_enabled"],
        "news_count": existing["news_count"],
        "output_format": existing["output_format"],
        "is_enabled": existing["is_enabled"],
        "model_override": existing.get("model_override"),
    })


def get_active_strategy_by_type(strategy_type: str) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM strategy WHERE type = ? AND is_enabled = 1 ORDER BY sort_order, id LIMIT 1",
            (strategy_type,),
        ).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def get_strategy_prompt(strategy_type: str, default_prompt: str) -> str:
    """Look up active strategy prompt by type, fallback to default_prompt."""
    strategy = get_active_strategy_by_type(strategy_type)
    if strategy and strategy.get("prompt_template"):
        return strategy["prompt_template"]
    return default_prompt


def run_strategy_test(strategy_id: int, test_input: str) -> str:
    strategy = get_strategy(strategy_id)
    if not strategy:
        raise ValueError("策略不存在")

    messages = [
        {"role": "system", "content": strategy["prompt_template"]},
        {"role": "user", "content": test_input or "请根据当前市场数据进行分析"},
    ]

    model = strategy.get("model_override") or None
    if model:
        return llm.chat(messages, model=model)
    return llm.analysis_chat(messages)


def seed_default_strategies() -> None:
    conn = get_connection()
    try:
        count = conn.execute("SELECT COUNT(*) FROM strategy WHERE is_default = 1").fetchone()[0]
        if count > 0:
            return
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for i, s in enumerate(_DEFAULT_STRATEGIES):
            conn.execute(
                """INSERT INTO strategy
                   (name, type, description, prompt_template, weight_config, news_enabled, news_count,
                    output_format, is_enabled, is_default, sort_order, model_override, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    s["name"],
                    s["type"],
                    s.get("description", ""),
                    s.get("prompt_template", ""),
                    json.dumps(s.get("weight_config", {}), ensure_ascii=False),
                    1,
                    15,
                    json.dumps(s.get("output_format", {}), ensure_ascii=False),
                    1,
                    1,
                    i,
                    None,
                    now,
                    now,
                ),
            )
        conn.commit()
        logger.info("Seeded %d default strategies", len(_DEFAULT_STRATEGIES))
    finally:
        conn.close()
