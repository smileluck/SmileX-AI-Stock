# 第3周：技术指标（indicators.py）

> 阶段：基础 | 难度：中级 | 核心文件：`smilex/indicators.py`

## 本周目标

- 理解 6 大技术指标（MA、MACD、RSI、布林带、KDJ、量比）的数学原理
- 精读 `indicators.py` 中每个指标的代码实现，理解公式与代码的对应关系
- 掌握 pandas 的三大核心操作：`rolling()`、`ewm()`、`shift()`

---

## 技术指标分类总览

| 指标 | 英文 | 类别 | 核心用途 |
|------|------|------|----------|
| MA | Moving Average | 趋势指标 | 判断股价运行方向，识别支撑/压力位 |
| MACD | Moving Average Convergence Divergence | 趋势指标 | 判断趋势强弱与拐点（金叉/死叉） |
| RSI | Relative Strength Index | 动量指标 | 判断超买超卖状态，发现背离信号 |
| 布林带 | Bollinger Bands | 波动率指标 | 衡量价格波动区间，识别突破信号 |
| KDJ | Stochastic Oscillator | 动量指标 | 判断短期超买超卖，捕捉短线拐点 |
| 量比 | Volume Ratio | 成交量指标 | 衡量当日成交量相对历史水平的异常程度 |

> **理解关键**：技术指标不是"预测未来"的魔法，而是对历史价格的数学变换，帮助量化描述市场状态。每个指标本质上都是一个数学公式。

---

## 六大指标详解

### MA（移动平均线）

**类型**：趋势指标

**数学公式**：

```
MA(n) = (P1 + P2 + ... + Pn) / n

其中 P 为收盘价，n 为周期
```

即：最近 n 个交易日收盘价的算术平均值。

**代码精读**（`indicators.py` 第 6-11 行）：

```python
def ma(df: pd.DataFrame, periods: list[int] | None = None) -> pd.DataFrame:
    if periods is None:
        periods = [5, 10, 20, 60]  # 默认计算4条均线
    for p in periods:
        df[f"ma{p}"] = df["close"].rolling(window=p).mean()
        #                    ^^^^^^^^^^^^^^
        # rolling(window=p) 选取最近 p 行形成一个滑动窗口
        # .mean() 对窗口内的值求平均
    return df
```

**交易信号**：
- **金叉**：短期均线（如 MA5）上穿长期均线（如 MA20），视为买入信号
- **死叉**：短期均线下穿长期均线，视为卖出信号
- **多头排列**：MA5 > MA10 > MA20 > MA60，强势上涨趋势
- **空头排列**：MA5 < MA10 < MA20 < MA60，强势下跌趋势

**参数影响**：
- `period` 越小，均线越灵敏，但假信号越多（如 MA5 比 MA60 灵敏得多）
- 常用周期：MA5（一周）、MA10（两周）、MA20（一月）、MA60（一季）

---

### MACD（指数平滑异同移动平均线）

**类型**：趋势指标

**数学公式**：

```
DIF（快线） = EMA(close, 12) - EMA(close, 26)
DEA（慢线） = EMA(DIF, 9)
MACD柱    = 2 × (DIF - DEA)

其中 EMA 为指数移动平均（见下方 ewm() 详解）
```

**代码精读**（`indicators.py` 第 14-20 行）：

```python
def macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9):
    # 使用 pandas-ta 库计算 MACD（内部实现了 EMA 差值逻辑）
    result = ta.macd(df["close"], fast=fast, slow=slow, length=signal)
    if result is not None:
        df["macd_dif"]  = result.iloc[:, 0]   # DIF 快线
        df["macd_dea"]  = result.iloc[:, 1]   # DEA 慢线
        df["macd_hist"] = result.iloc[:, 2]   # MACD 柱状图
    return df
```

> **注意**：本项目使用 `pandas-ta` 库计算 MACD，而非手动实现。这是因为 MACD 涉及双层 EMA 嵌套，手动实现容易出错。

**交易信号**：
- **金叉**：DIF 上穿 DEA → 买入信号（趋势由弱转强）
- **死叉**：DIF 下穿 DEA → 卖出信号（趋势由强转弱）
- **柱状图由负转正**：确认金叉信号；**由正转负**：确认死叉信号
- **零轴上方金叉**：强买入信号；**零轴下方死叉**：强卖出信号

---

### RSI（相对强弱指标）

**类型**：动量指标

**数学公式**：

```
RS = 平均涨幅 / 平均跌幅（取 n 日内）
RSI = 100 - 100 / (1 + RS)

取值范围：0 ~ 100
```

**代码精读**（`indicators.py` 第 23-25 行）：

```python
def rsi(df: pd.DataFrame, period: int = RSI_PERIOD) -> pd.DataFrame:
    # RSI_PERIOD = 14，即默认计算14日RSI（业界标准）
    df[f"rsi{period}"] = ta.rsi(df["close"], length=period)
    return df
```

**交易信号**：
- **RSI > 70**：超买区，价格可能回调（卖出信号）
- **RSI < 30**：超卖区，价格可能反弹（买入信号）
- **顶背离**：股价创新高，RSI 未创新高 → 上涨动能减弱
- **底背离**：股价创新低，RSI 未创新低 → 下跌动能减弱

> **参数说明**：周期越短（如 RSI6），信号越灵敏但噪音越多；周期越长（如 RSI24），信号越稳定但滞后。

---

### 布林带（Bollinger Bands）

**类型**：波动率指标

**数学公式**：

```
中轨（MID） = MA(close, n)                        — n 日均线
上轨（UPPER）= MID + k × σ                        — 中轨 + k 倍标准差
下轨（LOWER）= MID - k × σ                        — 中轨 - k 倍标准差

其中 n 通常取 20，k 通常取 2，σ 为 n 日收盘价的标准差
```

**代码精读**（`indicators.py` 第 28-35 行）：

```python
def bollinger(df: pd.DataFrame, period: int = BOLLINGER_PERIOD,
              std: float = BOLLINGER_STD) -> pd.DataFrame:
    # BOLLINGER_PERIOD = 20, BOLLINGER_STD = 2
    bb = ta.bbands(df["close"], length=period, std=std)
    if bb is not None:
        df["boll_upper"] = bb.iloc[:, 0]   # 上轨
        df["boll_mid"]   = bb.iloc[:, 1]   # 中轨（= MA20）
        df["boll_lower"] = bb.iloc[:, 2]   # 下轨
    return df
```

**交易信号**：
- **突破上轨**：价格偏强，可能继续上涨，也可能回调
- **突破下轨**：价格偏弱，可能继续下跌，也可能反弹
- **收口（Squeeze）**：上下轨间距收窄 → 即将发生大幅波动（方向待确认）
- **开口（Expansion）**：上下轨间距扩大 → 波动加剧，趋势正在展开

**参数影响**：
- `period` 越大，布林带越平滑（如 period=50 适合中线分析）
- `std` 越大，通道越宽（std=2 时约 95% 的价格在带内，std=3 时约 99.7%）

---

### KDJ（随机指标）

**类型**：动量指标

**数学公式**：

```
RSV（未成熟随机值）= (Close - Low_n) / (High_n - Low_n) × 100

K = 2/3 × K_prev + 1/3 × RSV       （即 RSV 的 EMA，com=2）
D = 2/3 × D_prev + 1/3 × K         （即 K 的 EMA，com=2）
J = 3K - 2D

其中 Low_n 和 High_n 分别为 n 日内最低价和最高价（默认 n=9）
```

**代码精读**（`indicators.py` 第 38-45 行）：

```python
def kdj(df: pd.DataFrame, period: int = 9) -> pd.DataFrame:
    # 第1步：计算 n 日内的最低价和最高价
    low_min = df["low"].rolling(window=period).min()
    high_max = df["high"].rolling(window=period).max()

    # 第2步：计算 RSV（收盘价在 n 日区间的相对位置，0~100）
    rsv = (df["close"] - low_min) / (high_max - low_min) * 100

    # 第3步：K = RSV 的指数移动平均（com=2 等价于平滑系数 1/3）
    df["kdj_k"] = rsv.ewm(com=2, adjust=False).mean()

    # 第4步：D = K 的指数移动平均
    df["kdj_d"] = df["kdj_k"].ewm(com=2, adjust=False).mean()

    # 第5步：J = 3K - 2D（放大的动量指标）
    df["kdj_j"] = 3 * df["kdj_k"] - 2 * df["kdj_d"]
    return df
```

> **注意**：KDJ 是本项目中唯一手动实现的指标（没有用 pandas-ta）。原因可能是 KDJ 的 J 值计算在 pandas-ta 中没有直接对应。

**J 线的特殊性**：
- J 值可以**超过 100** 或**低于 0**（不像 K 和 D 被 0-100 限制）
- J > 100：极端超买，短期可能回调
- J < 0：极端超卖，短期可能反弹

**交易信号**：
- **K 上穿 D**：买入信号（金叉）
- **K 下穿 D**：卖出信号（死叉）
- **J > 100 后回落**：强卖出信号
- **J < 0 后回升**：强买入信号

---

### 量比（Volume Ratio）

**类型**：成交量指标

**数学公式**：

```
量比 = 当日成交量 / 过去5日平均成交量
```

**代码精读**（`indicators.py` 第 48-51 行）：

```python
def volume_ratio(df: pd.DataFrame) -> pd.DataFrame:
    # 关键：shift(1) 将均值向下偏移一行，确保不使用"未来数据"
    avg_vol = df["volume"].rolling(window=5).mean().shift(1)
    df["volume_ratio"] = df["volume"] / avg_vol
    return df
```

> **为什么必须用 `shift(1)`？** 这是量化分析中最容易犯的错误——**前视偏差（Look-ahead Bias）**。如果不加 `shift(1)`，当日平均成交量包含了当天的数据，相当于"用当天的数据预测当天"，在实盘中是不可能的。`shift(1)` 确保只用"昨天及之前"的数据计算均值。

**量比解读标准**：

| 量比范围 | 含义 | 解读 |
|----------|------|------|
| < 0.75 | 缩量 | 交易清淡，市场关注度低 |
| 0.75 - 1.5 | 正常 | 成交量处于正常水平 |
| 1.5 - 2.5 | 温和放量 | 市场关注度提升，可能有资金进场 |
| 2.5 - 5.0 | 明显放量 | 明显异动，需结合价格方向判断 |
| > 5.0 | 剧烈放量 | 极端异常，可能是重大利好/利空 |

---

## pandas 三大核心操作

### rolling() — 滑动窗口

```python
# 计算5日均线
df["ma5"] = df["close"].rolling(window=5).mean()

# 等价于：对每一行，取它和前面4行（共5行）的平均值
# 第1-4行的结果为 NaN（因为不够5行）

# 其他常用聚合：
df["max5"] = df["high"].rolling(window=5).max()   # 5日最高价
df["std20"] = df["close"].rolling(window=20).std() # 20日标准差
```

> **Java 对照**：类似 Java 中对 List 做 sliding window 操作，但 pandas 自动处理边界（前 n-1 行为 NaN）。

### ewm() — 指数加权移动平均

```python
# EMA（指数移动平均）— 越近期的数据权重越大
df["ema12"] = df["close"].ewm(span=12, adjust=False).mean()

# com（center of mass）参数：
# com=2 等价于平滑系数 alpha = 1/(com+1) = 1/3
# 即：新值 = (1/3) × 当前值 + (2/3) × 前一个 EMA 值

# span 参数更直观：
# span=12 等价于 12 日 EMA
```

> **rolling vs ewm 的区别**：rolling 是简单平均（等权重），ewm 是指数衰减权重（近期数据更重要）。MACD 中的 EMA 用的就是 ewm。

### shift() — 行偏移

```python
# shift(1)：所有值向下移一行（取"上一行"的值）
df["prev_close"] = df["close"].shift(1)

# 实际应用：计算涨跌幅
df["change_pct"] = (df["close"] - df["close"].shift(1)) / df["close"].shift(1) * 100

# shift(-1)：向上移一行（取"下一行"的值，一般用于回测中获取未来数据）
```

> **量化核心**：`shift(1)` 是避免前视偏差的关键。任何时候计算指标时，如果需要引用"过去的数据"，用 `shift(1)` 或 `rolling()` 自动处理。

---

## pandas-ta vs 手动计算

| 对比维度 | pandas-ta（第三方库） | 手动计算（pandas 原生） |
|----------|----------------------|------------------------|
| 代码量 | 少（一行调用） | 多（需要理解公式） |
| 可读性 | 需查文档才知道参数含义 | 公式即代码，一目了然 |
| 灵活性 | 受库的接口限制 | 完全自定义 |
| 正确性 | 经过社区验证 | 需自行验证 |
| 依赖 | 需额外安装 `pandas-ta` | 只需 `pandas` |
| 学习价值 | 低（黑盒调用） | 高（理解原理） |

**本项目的策略**：
- MA、量比：用 pandas 原生计算（`rolling`、`shift`）—— 公式简单，直接写更清晰
- MACD、RSI、布林带：用 `pandas-ta` —— 公式复杂，避免重复造轮子
- KDJ：手动实现 —— `pandas-ta` 没有直接提供 KDJ 的 J 值计算

> **建议**：学习阶段优先手动实现，理解公式后再用库提高效率。

---

## 实践练习

1. **手算验证 MA**：取任意一只股票的 20 日数据，手动计算 MA5（纸笔或 Excel），然后与 `indicators.ma()` 的输出对比，确认结果一致。

2. **理解 rolling 的边界**：调用 `indicators.ma(df, periods=[5])`，检查前 4 行的 MA5 值是否为 NaN（`pd.isna()`），理解为什么不够窗口大小时结果为空。

3. **添加 ATR 指标**：在 `indicators.py` 中新增 `atr()` 函数。ATR（Average True Range）的计算公式：
   ```
   TR = max(High-Low, abs(High-PrevClose), abs(Low-PrevClose))
   ATR = MA(TR, 14)
   ```
   提示：需要用 `shift(1)` 获取前一日收盘价。

4. **修改布林带参数**：将 `BOLLINGER_STD` 从 2 改为 2.5，观察布林带的上下轨变宽后，有多少比例的收盘价落在带外。

5. **编写单元测试**：为 `kdj()` 函数编写测试用例。构造一个只有 10 行的简单 DataFrame（含 close、high、low 列），手动计算 RSV、K、D、J，验证代码输出是否匹配。

---

## 自测清单

- [ ] 能在纸上写出 MA、RSI、布林带、KDJ 的数学公式，并解释每个变量的含义
- [ ] 能解释 `rolling()`、`ewm()`、`shift()` 三者的区别和使用场景
- [ ] 能解释量比计算中 `shift(1)` 的作用，以及不加它会导致什么问题（前视偏差）
- [ ] 能说明 pandas-ta 和手动计算的各自适用场景
- [ ] 能独立实现一个新的技术指标函数（如 ATR 或威廉指标 %R）

---

## 学习资料

- [技术分析指标详解（B站）](https://www.bilibili.com/) — 搜索"MACD指标详解"、"KDJ指标教学"等视频
- [BigQuant 指标库](https://bigquant.com/wiki) — 量化平台的技术指标百科，公式+代码
- [pandas-ta 官方文档](https://github.com/twopirllc/pandas-ta) — 了解库中可用的所有指标
- [日本蜡烛图技术（史蒂夫·尼森）](https://book.douban.com/) — K 线形态分析经典著作
- [布林格论布林带（约翰·布林格）](https://book.douban.com/) — 布林带发明者亲笔，深入理解波动率指标
