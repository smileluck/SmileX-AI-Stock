# 第7周：策略回测（Backtrader）

> 阶段：核心 | 难度：进阶 | 核心文件：`smilex/backtest.py`、`smilex/strategy.py`

## 本周目标

- 理解 Backtrader 框架的核心架构与组件协作方式
- 能读懂双均线交叉策略的两种实现方式（纯 pandas vs Backtrader 内置）
- 能在现有策略基础上添加止损规则，并能独立实现新策略
- 理解绩效指标（收益率、最大回撤、胜率等）的计算方法和含义

---

## Backtrader 核心架构

### 组件对照表（Java 开发者视角）

| Backtrader 组件 | 职责 | Java 类比 |
|----------------|------|----------|
| **Cerebro** | 回测引擎，负责组装所有组件并驱动运行 | Spring ApplicationContext |
| **Strategy** | 交易逻辑，每根K线触发一次 `next()` | @Service 业务逻辑类 |
| **Data Feed** | OHLCV 数据输入 | Repository / DAO 数据层 |
| **Broker** | 资金管理、下单执行、手续费计算 | PaymentGateway 支付网关 |
| **Position** | 持仓状态跟踪（`self.position`） | 实体状态字段 |
| **Indicator** | 技术指标计算（SMA、CrossOver 等） | Helper / Utility 工具类 |
| **Observer** | 运行时数据观察（如资金曲线） | AOP 切面 / @EventListener |

### 核心概念详解

**Cerebro（大脑）**：回测引擎的总调度器。它的职责是把 Strategy、Data Feed、Broker 等组件组装到一起，然后按时间顺序逐根K线推进，每推进一步就调用 Strategy 的 `next()` 方法。类似 Spring 容器管理 Bean 的生命周期。

**Strategy（策略）**：你写交易逻辑的地方。核心是 `next()` 方法——每收到一根新K线就会调用一次，你可以在这里判断指标、决定买卖。参数通过 `params` 元组定义，类似 Java 的构造器参数。

**Data Feed（数据源）**：给 Cerebro 喂入的历史行情数据，通常用 `bt.feeds.PandasData` 把 DataFrame 转为 Backtrader 格式。

**Broker（经纪商）**：模拟券商，管理现金、计算手续费、执行委托。通过 `cerebro.broker.setcash()` 设初始资金，`setcommission()` 设佣金费率。

---

## 两种信号生成方式对比

本项目在 `strategy.py` 和 `backtest.py` 中展示了两种截然不同的信号生成方式：

### 方式一：纯 pandas（strategy.py）

```python
# smilex/strategy.py — 用 shift() 手动比较前后K线
golden_cross = (
    (df[f"ma{short_period}"] > df[f"ma{long_period}"]) &
    (df[f"ma{short_period}"].shift(1) <= df[f"ma{long_period}"].shift(1))
)
```

特点：直接操作整个 DataFrame，向量化计算，适合快速验证信号。

### 方式二：Backtrader 内置（backtest.py）

```python
# smilex/backtest.py — 用 bt.indicators.CrossOver 自动检测交叉
self.crossover = bt.indicators.CrossOver(self.ma_short, self.ma_long)
# 在 next() 中判断 self.crossover > 0 即金叉
```

特点：框架内置指标，自动处理逐K线计算，天然避免未来函数。

### 对比总结

| 对比维度 | 纯 pandas（strategy.py） | Backtrader 内置（backtest.py） |
|---------|------------------------|------------------------------|
| 计算方式 | 向量化，一次算完所有K线 | 逐K线推进，模拟实时环境 |
| 代码复杂度 | 较低，几行搞定 | 需要理解框架约定 |
| 未来函数风险 | 较高（需手动避免 shift 误用） | 较低（框架天然防止） |
| 适用场景 | 信号验证、快速原型 | 完整回测、策略开发 |
| 交易模拟 | 不支持 | 支持资金管理、手续费 |

---

## 代码精读：strategy.py

```python
# smilex/strategy.py 完整代码逐行解读

def generate_signals(df, short_period=5, long_period=20):
    df = df.copy()  # 防止修改原始数据，类似 Java 的防御性拷贝

    # 第1步：计算均线
    df[f"ma{short_period}"] = df["close"].rolling(window=short_period).mean()
    df[f"ma{long_period}"]  = df["close"].rolling(window=long_period).mean()

    # 第2步：检测金叉（当前短>长 且 前一根短<=长）
    golden_cross = (
        (df[f"ma{short_period}"] > df[f"ma{long_period}"]) &       # 当日：短均线在上方
        (df[f"ma{short_period}"].shift(1) <= df[f"ma{long_period}"].shift(1))  # 昨日：短均线在下方或持平
    )

    # 第3步：检测死叉（当前短<长 且 前一根短>=长）
    death_cross = (
        (df[f"ma{short_period}"] < df[f"ma{long_period}"]) &
        (df[f"ma{short_period}"].shift(1) >= df[f"ma{long_period}"].shift(1))
    )

    # 第4步：生成信号列（1=买入, -1=卖出, 0=无操作）
    df["signal"] = 0
    df.loc[golden_cross, "signal"] = 1
    df.loc[death_cross, "signal"] = -1

    # 第5步：生成持仓列（短>长就持仓，否则空仓）
    df["position"] = np.where(df[f"ma{short_period}"] > df[f"ma{long_period}"], 1, 0)
    return df
```

关键理解点：
- `shift(1)` 的作用是"把所有数据向下移一行"，相当于"昨日的值"。这与 SQL 的 `LAG()` 窗口函数原理相同。
- `signal` 只在交叉点有值（1 或 -1），`position` 则是连续的持仓状态。

---

## 代码精读：backtest.py

### MAStrategy 类

```python
class MAStrategy(bt.Strategy):
    params = (                          # 类似 Java 的构造器参数
        ("short_period", 5),            # 默认值来自 config.py 的 MA_SHORT_PERIOD
        ("long_period", 20),
    )

    def __init__(self):
        # 在 __init__ 中初始化指标（只执行一次）
        self.ma_short = bt.indicators.SMA(self.data.close, period=self.p.short_period)
        self.ma_long  = bt.indicators.SMA(self.data.close, period=self.p.long_period)
        self.crossover = bt.indicators.CrossOver(self.ma_short, self.ma_long)
        self.trades = []                # 记录交易日志

    def next(self):                     # 每根K线调用一次
        if self.crossover > 0:          # 金叉
            if not self.position:       # 空仓才买入
                # A股100股为一手，向下取整
                size = int(self.broker.getcash() / self.data.close[0] / 100) * 100
                if size > 0:
                    self.buy(size=size)
                    self.trades.append({...})
        elif self.crossover < 0:        # 死叉
            if self.position:           # 持仓才卖出
                self.close()            # 平仓（卖出全部持仓）
                self.trades.append({...})
```

重点解读：
- **A 股整手限制**：`int(cash / price / 100) * 100` — 因为 A 股必须以 100 股为单位买入，所以先除以 100 取整再乘回 100。例如 10 万元买 15.6 元的股票：`100000 / 15.6 / 100 = 64.1`，取整后 `64 * 100 = 6400` 股。
- **`self.close()` vs `self.sell()`**：`close()` 是平仓（卖出全部），`sell()` 是开空仓或指定数量卖出。

### run() 函数

```python
def run(df, short_period=5, long_period=20, cash=100000.0):
    # 第1步：准备数据
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df.set_index("date", inplace=True)

    # 第2步：转为 Backtrader 数据格式
    data = bt.feeds.PandasData(dataview=df, open="open", high="high",
                                low="low", close="close", volume="volume")

    # 第3步：创建引擎并组装组件
    cerebro = bt.Cerebro()
    cerebro.addstrategy(MAStrategy, short_period=short_period, long_period=long_period)
    cerebro.adddata(data)
    cerebro.broker.setcash(cash)
    cerebro.broker.setcommission(commission=0.00025)  # 万2.5佣金

    # 第4步：执行回测
    start_value = cerebro.broker.getvalue()
    strat = cerebro.run()[0]           # run() 返回策略实例列表
    end_value = cerebro.broker.getvalue()

    # 第5步：计算绩效指标
    total_return = (end_value - start_value) / start_value
    annual_return = (1 + total_return) ** (252 / trading_days) - 1
    ...
```

流程总结：`准备数据 → 创建 Cerebro → 添加策略 → 添加数据 → 设初始资金 → 设佣金 → 运行 → 计算指标`

### 绩效指标计算

#### 总收益率

```python
total_return = (end_value - start_value) / start_value
```

含义：期末资产相对期初资产的增长比例。如投入 10 万，最终 12 万，则总收益率 = 20%。

#### 年化收益率

```python
annual_return = (1 + total_return) ** (252 / trading_days) - 1
```

含义：把总收益率换算为"一年"的等价收益率。252 是 A 股一年的交易日数。公式来源：复利公式 `FV = PV * (1+r)^n` 的逆运算。

#### 资金曲线（_build_equity_curve）

```python
def _build_equity_curve(df, trades, cash):
    running_value = cash       # 当前现金
    position_size = 0          # 当前持仓股数
    curve = []
    for i in range(len(df)):   # 逐日遍历
        for t in trades:       # 检查当日是否有交易
            if t["type"] == "BUY":
                running_value -= t["price"] * t["size"] * 1.00025   # 扣除买入金额+佣金
            elif t["type"] == "SELL":
                running_value += t["price"] * t["size"] * 0.99975   # 收回卖出金额-佣金
        # 当日总资产 = 现金 + 持仓市值
        curve.append(running_value + position_size * row["close"])
    return curve
```

#### 最大回撤（_calc_max_drawdown）

```python
def _calc_max_drawdown(curve):
    peak = curve[0]       # 历史最高点
    max_dd = 0.0          # 最大回撤
    for v in curve:
        peak = max(peak, v)           # 更新最高点
        max_dd = max(max_dd, (peak - v) / peak)  # 计算当前回撤并取最大
    return max_dd
```

含义：从资金曲线的任一历史最高点到之后最低点的最大跌幅。例如最高 15 万，跌到 12 万，最大回撤 = (15-12)/15 = 20%。

#### 胜率（_calc_win_rate）

```python
def _calc_win_rate(trades):
    wins = []
    for i in range(0, len(trades) - 1, 2):  # 买卖配对（0和1，2和3...）
        profit = (trades[i+1]["price"] - trades[i]["price"]) * trades[i]["size"]
        wins.append(profit > 0)
    return sum(wins) / len(wins)
```

含义：盈利交易次数占总交易次数的比例。将买卖记录配对（奇偶配对），计算每笔交易盈亏。

### 绩效指标速查表

| 指标 | 公式 | 含义 | 参考标准 |
|------|------|------|---------|
| 总收益率 | (期末 - 期初) / 期初 | 整个回测期间的收益比例 | > 0 即盈利 |
| 年化收益率 | (1 + 总收益率)^(252/天数) - 1 | 折算为年度收益率 | > 15% 较好 |
| 最大回撤 | max((peak - valley) / peak) | 最糟糕情况下亏损多少 | < 20% 较安全 |
| 胜率 | 盈利次数 / 总交易次数 | 每笔交易盈利的概率 | > 50% 即可 |
| 夏普比率 | (年化收益 - 无风险利率) / 收益率标准差 | 每承担一单位风险获得多少收益 | > 1.0 较好 |

---

## 回测六大陷阱

### 1. 未来函数（Look-ahead Bias）

使用了"未来"的数据来做"当下"的决策。例如在当日收盘价还没确定时就用收盘价做判断。本项目的 `strategy.py` 使用 `shift(1)` 对比"昨日"值，就是为了避免未来函数。

### 2. 幸存者偏差（Survivorship Bias）

只回测了当前仍在上市的股票，忽略了已经退市的股票。这会让回测结果偏乐观。完整的回测应包含已退市的股票。

### 3. 过拟合（Overfitting）

反复调整参数直到回测结果完美，但这种"完美"只在历史数据上有效，实盘往往表现很差。应对方法：样本外测试、参数敏感性分析。

### 4. 滑点（Slippage）

实际成交价与预期价格的差异。回测中假设以收盘价成交，但实际可能以更差的价格成交。可在 Backtrader 中通过 `slippage` 设置模拟。

### 5. 冲击成本（Market Impact）

大额买卖单会推动价格变动。回测假设可以无限量买卖而不影响价格，但实盘中大额交易会改变市场供需。

### 6. 资金限制（Capital Constraints）

本项目 MAStrategy 使用全仓买入策略（`cash / price / 100 * 100`），实盘中需考虑留一部分现金应对意外。此外涨跌停板可能无法成交。

---

## 实践练习

### 练习1：追踪 MAStrategy 生命周期

在 `backtest.py` 的 `MAStrategy.next()` 中添加 `print` 语句，打印每次金叉/死叉时的日期、价格和持仓状态，观察策略的完整运行过程。

### 练习2：对比两种信号方式

用同一只股票的同一时间段数据，分别用 `strategy.py` 的 `generate_signals()` 和 `backtest.py` 的 `run()` 计算信号，对比结果是否一致。思考为什么可能有细微差异。

### 练习3：添加止损规则

在 `MAStrategy.next()` 中添加止损逻辑：如果持仓亏损超过 5%，自动卖出。

```python
def next(self):
    # 在现有逻辑前添加止损判断
    if self.position:
        cost = self.position.price  # 买入均价
        current = self.data.close[0]
        loss_pct = (current - cost) / cost
        if loss_pct < -0.05:        # 亏损超过5%
            self.close()
            self.trades.append({
                "type": "STOP_LOSS", "date": self.data.datetime.date(0),
                "price": current, "size": self.position.size,
            })
            return                   # 止损后跳过后续逻辑
    # ... 原有买卖逻辑
```

### 练习4：实现 RSI 策略

参考 `MAStrategy` 的结构，创建 `RSIStrategy`：RSI < 30 时买入（超卖），RSI > 70 时卖出（超买）。提示：`bt.indicators.RSI(self.data.close, period=14)`。

### 练习5：添加夏普比率计算

在 `backtest.py` 的 `run()` 函数中，利用 `equity_curve` 计算每日收益率的标准差，进而计算夏普比率。公式：`Sharpe = (年化收益 - 0.03) / (日收益率标准差 * sqrt(252))`。

### 练习6：对比不同均线周期

用 `run(df, short_period=5, long_period=20)` 和 `run(df, short_period=10, long_period=30)` 分别回测，对比总收益率和最大回撤，思考哪组参数更稳健。

---

## 自测清单

- [ ] 能解释 Cerebro、Strategy、Data Feed、Broker 四大组件的职责
- [ ] 能说清 `strategy.py` 中 `shift(1)` 的作用以及为什么不能省略
- [ ] 能解释 A 股"100 股整手"限制在代码中的体现
- [ ] 能说出最大回撤和胜率的计算方法
- [ ] 能列举至少三种回测陷阱及其应对方法

---

## 学习资料

### 官方文档
- [Backtrader Quickstart Guide](https://www.backtrader.com/docu/quickstart/quickstart/) — 从零开始学 Backtrader
- [Backtrader Strategy Guide](https://www.backtrader.com/docu/strategy/) — Strategy 类详解
- [Backtrader Indicator Reference](https://www.backtrader.com/docu/indicator-ref/) — 所有内置指标参考

### 中文教程
- 知乎 Backtrader 专栏系列教程 — 搜索"backtrader 教程"
- CSDN Backtrader 全面指南 — 搜索"backtrader 入门到精通"

### 视频教程
- B 站搜索"Backtrader 量化回测" — 多个系列视频教程

### 注意事项文章
- 最大回撤计算的常见错误（搜索"最大回撤 计算 错误"）
- 夏普比率的正确计算方式（搜索"夏普比率 计算 注意"）

### 推荐书籍
- 《量化投资：以 Python 为工具》— 回测相关章节
- 《打开量化投资的黑箱》— 理解量化策略设计思路
