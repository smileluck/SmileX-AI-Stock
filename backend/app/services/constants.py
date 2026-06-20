"""项目常量集中地。

将散落在服务层的策略/调参类魔法数字集中到这里，便于产品调参与回归比对。
**只放可调阈值**，不放 schema、URL、列名等结构性常量。
"""

# ---- 个股推荐候选预评分（stock） ----
RECOMMENDATION_AMOUNT_MIN = 1_0000_0000
RECOMMENDATION_IDEAL_TURNOVER_MIN = 3.0
RECOMMENDATION_IDEAL_TURNOVER_MAX = 15.0
RECOMMENDATION_HIGH_AMPLITUDE = 8.0

# ---- 尾盘候选股预筛（stock._preselect_afternoon_candidates） ----
# 主力净流入排行抓取数量
AFTERNOON_RANK_TOP_N = 30
# 候选股最大数量
AFTERNOON_CANDIDATE_MAX = 20
# 涨幅过滤区间（%）：低于下限或高于上限的剔除
AFTERNOON_CHANGE_PCT_MIN = -2.0
AFTERNOON_CHANGE_PCT_MAX = 7.0
AFTERNOON_AMOUNT_MIN = 1_0000_0000
AFTERNOON_MAIN_INFLOW_PCT_MIN = 3.0
AFTERNOON_TURNOVER_MIN = 2.0
AFTERNOON_TURNOVER_MAX = 18.0
AFTERNOON_AMPLITUDE_MAX = 10.0

# ---- 大盘新闻评分（market_analysis） ----
# 新闻时间衰减系数：每小时衰减幅度（>0 即每小时减多少权重）
NEWS_TIME_DECAY_PER_HOUR = 0.006
# 时间权重下限
NEWS_TIME_WEIGHT_FLOOR = 0.3
# 评分目标条数（普通 / 周末）
NEWS_FILTER_TARGET_COUNT = 30
# 当日新闻拉取上限
NEWS_DAILY_FETCH_LIMIT = 30

# ---- 推荐复盘价格调整 ----
# 这里仅作为占位说明：当前 stock.py 的价格按 ratio 等比例调整属于业务逻辑非阈值，故不集中。

# ---- 个股推荐候选股硬过滤（stock._apply_hard_filters） ----
# PE_TTM 绝对上限（兜底红线）。超过即 reject。
# 选 120 的依据：报告基准下东阳光 PE229、鹏鼎 PE149 都被过滤；
# 兆易 PE76、巨石 PE43 放行依赖 prompt 二次约束。
RECOMMENDATION_PE_TTM_MAX = 120.0

# 累计涨幅阈值（%），任一区间超限即 reject
RECOMMENDATION_CUM_GAIN_5D_MAX = 25.0    # 对应"连涨3天+21.72%"红线
RECOMMENDATION_CUM_GAIN_20D_MAX = 80.0   # 对应"4月以来+264%"红线（折算到20日大约80%）
RECOMMENDATION_CUM_GAIN_60D_MAX = 150.0  # 极端情况兜底

# 连板数上限：>= 此值直接 reject
RECOMMENDATION_LIMIT_UP_TIMES_MAX = 3

# 数据滞后判定：实时价与昨收偏离 < 此容差（默认 0.05%）且在交易时段内 → stale
RECOMMENDATION_STALE_PRICE_TOLERANCE_PCT = 0.0005

# 接近阈值的"边缘标签"门槛（用于 risk_proximity_tags，不触发 reject）
# PE 80~120 标 "PE偏高"；5日涨幅 15~25% 标 "涨幅偏大"；连板 2 标 "连板情绪"
RECOMMENDATION_PE_TTM_WARN = 80.0
RECOMMENDATION_CUM_GAIN_5D_WARN = 15.0
RECOMMENDATION_CUM_GAIN_20D_WARN = 50.0
RECOMMENDATION_LIMIT_UP_TIMES_WARN = 2
