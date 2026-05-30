# 第10周：测试 + 代码质量

> 阶段：进阶 | 难度：中级 | 核心目录：`tests/`
>
> 前置知识：完成第 1-9 周学习，理解所有核心模块

## 本周目标

- 为 `indicators.py` 编写单元测试，验证技术指标计算正确性
- 为 `store.py` 编写集成测试，验证数据库 CRUD 操作
- 为 `scanner.py` 编写测试，验证评分逻辑
- 掌握 pytest 的核心用法（Java 开发者可类比 JUnit）

## pytest 快速入门（JUnit 对照）

### JUnit 5 vs pytest 对照表

| 特性 | JUnit 5 | pytest |
|------|---------|--------|
| 测试方法标记 | `@Test` | 函数名以 `test_` 开头 |
| 断言 | `assertEquals(a, b)` | `assert a == b` |
| 异常测试 | `assertThrows` | `with pytest.raises(ValueError)` |
| 前置/后置 | `@BeforeEach / @AfterEach` | `fixture`（装饰器 `@pytest.fixture`）|
| 参数化测试 | `@ParameterizedTest` | `@pytest.mark.parametrize` |
| 测试发现 | 自动扫描 `src/test/` | 自动扫描 `test_*.py` |
| 测试跳过 | `@Disabled` | `@pytest.mark.skip` |
| 测试套件 | `@Suite` | `conftest.py` 共享 fixture |

### 基本 pytest 示例

```python
# tests/test_indicators.py
import pandas as pd
import numpy as np
from smilex.indicators import ma, macd, rsi, kdj, volume_ratio

def test_ma_basic():
    """测试 MA5 计算"""
    df = pd.DataFrame({"close": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]})
    result = ma(df, periods=[5])
    # 第5个值的 MA5 = (1+2+3+4+5)/5 = 3.0
    assert result["ma5"].iloc[4] == 3.0
    # 前4个值为 NaN（数据不足）
    assert pd.isna(result["ma5"].iloc[3])
```

### pytest 核心特性

**fixture（测试数据准备）：**
```python
import pytest

@pytest.fixture
def sample_ohlcv():
    """创建测试用的 OHLCV 数据"""
    np.random.seed(42)
    n = 100
    dates = pd.date_range("2025-01-01", periods=n)
    close = 100 + np.cumsum(np.random.randn(n))
    return pd.DataFrame({
        "date": dates,
        "open": close - 0.5,
        "high": close + 1,
        "low": close - 1,
        "close": close,
        "volume": np.random.randint(1000, 10000, n).astype(float),
    })

def test_ma_with_fixture(sample_ohlcv):
    result = ma(sample_ohlcv, periods=[20])
    assert len(result) == len(sample_ohlcv)
    assert pd.notna(result["ma20"].iloc[19])
```

**参数化测试：**
```python
@pytest.mark.parametrize("period", [5, 10, 20, 60])
def test_ma_various_periods(sample_ohlcv, period):
    result = ma(sample_ohlcv, periods=[period])
    col = f"ma{period}"
    assert col in result.columns
    # 前period-1个值为NaN
    assert pd.isna(result[col].iloc[period - 2])
    # 第period个值不为NaN
    assert pd.notna(result[col].iloc[period - 1])
```

**异常测试：**
```python
def test_ma_empty_dataframe():
    """空 DataFrame 不应崩溃"""
    df = pd.DataFrame({"close": pd.Series(dtype=float)})
    result = ma(df)
    assert len(result) == 0
```

## 测试策略

### 测试金字塔

```
       /  E2E  \          ← 少量：启动完整看板验证功能
      / 集成测试  \         ← 适量：store.py 数据库操作
     /   单元测试    \       ← 大量：indicators.py 纯函数
```

### 本项目测试优先级

| 优先级 | 模块 | 测试类型 | 原因 |
|--------|------|---------|------|
| P0 | `indicators.py` | 单元测试 | 纯函数，最易测试，指标计算必须正确 |
| P0 | `strategy.py` | 单元测试 | 信号生成逻辑是策略核心 |
| P1 | `store.py` | 集成测试 | 数据库操作需要验证 |
| P1 | `scanner.py` | 单元测试 | _evaluate() 评分逻辑需要覆盖 |
| P2 | `backtest.py` | 集成测试 | 需要真实数据，较复杂 |
| P3 | `fetcher.py` | 集成测试 | 依赖外部 API，可用 mock |
| P3 | dashboard | E2E | 需要 Streamlit 运行环境 |

## 测试用例设计

### indicators.py 测试清单

```python
# tests/test_indicators.py

class TestMA:
    def test_ma5_calculation(self):
        """MA5 计算结果正确"""

    def test_ma_default_periods(self):
        """默认计算 MA5/10/20/60"""

    def test_ma_custom_periods(self):
        """自定义周期"""

    def test_ma_insufficient_data(self):
        """数据不足时返回 NaN"""

class TestMACD:
    def test_macd_columns_exist(self):
        """返回 macd_dif/macd_dea/macd_hist 三列"""

    def test_macd_dif_is_difference(self):
        """DIF ≈ EMA(12) - EMA(26)"""

    def test_macd_hist_is_2x_diff(self):
        """MACD柱 = 2 × (DIF - DEA)"""

class TestRSI:
    def test_rsi_range(self):
        """RSI 值在 0-100 之间"""

    def test_rsi_period(self):
        """默认 14 周期"""

class TestKDJ:
    def test_kdj_columns_exist(self):
        """返回 kdj_k/kdj_d/kdj_j 三列"""

    def test_kdj_k_d_range(self):
        """K、D 值在 0-100 附近"""

    def test_kdj_j_formula(self):
        """J = 3K - 2D"""

class TestVolumeRatio:
    def test_volume_ratio_calculation(self):
        """量比 = 当前量 / 前5日均量"""

    def test_volume_ratio_uses_shift(self):
        """使用 shift(1) 避免未来函数"""
```

### scanner.py 测试清单

```python
# tests/test_scanner.py

class TestShouldSkip:
    def test_skip_st_stock(self):
        """ST 股票被过滤"""

    def test_skip_delisted_stock(self):
        """退市股票被过滤"""

    def test_skip_limit_up(self):
        """涨停股票（涨幅≥9.9%）被过滤"""

    def test_not_skip_normal_stock(self):
        """正常股票不被过滤"""

class TestEvaluate:
    def test_ma_alignment_30pts(self):
        """均线多头排列得 30 分"""

    def test_macd_golden_cross_20pts(self):
        """MACD 金叉得 20 分"""

    def test_macd_near_cross_10pts(self):
        """MACD 即将金叉得 10 分"""

    def test_volume_ratio_20pts(self):
        """量比 > 1.5 得 20 分"""

    def test_bollinger_mid_15pts(self):
        """站上布林中轨得 15 分"""

    def test_rsi_moderate_15pts(self):
        """RSI 在 40-70 得 15 分"""

    def test_rsi_low_5pts(self):
        """RSI < 40 得 5 分"""

    def test_total_score_100(self):
        """所有条件满足得 100 分"""
```

### store.py 测试清单

```python
# tests/test_store.py

import tempfile
import os

@pytest.fixture
def db():
    """创建临时数据库"""
    import smilex.store as store
    # 使用临时文件替代真实数据库
    original_db_path = store.DB_PATH
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        store.DB_PATH = f.name
    store.init_db()
    yield store
    # 清理
    os.unlink(store.DB_PATH)
    store.DB_PATH = original_db_path

class TestSaveDaily:
    def test_save_and_query(self, db):
        """保存后能查询到"""

    def test_deduplication(self, db):
        """同一数据重复保存不产生重复记录"""

    def test_update_existing(self, db):
        """INSERT OR REPLACE 覆盖更新"""

class TestSaveNews:
    def test_dedup_by_url(self, db):
        """相同 URL 的新闻只入库一次"""
```

## 运行测试

```bash
# 运行所有测试
uv run pytest tests/ -v

# 运行指定模块
uv run pytest tests/test_indicators.py -v

# 运行指定测试
uv run pytest tests/test_indicators.py::TestMA::test_ma5_calculation -v

# 显示打印输出
uv run pytest tests/ -v -s

# 测试覆盖率
uv run pytest tests/ --cov=smilex --cov-report=term-missing
```

## 代码质量工具

### Ruff（替代 Java 的 Checkstyle/PMD）

```bash
# 安装
uv add --dev ruff

# 检查代码风格
uv run ruff check smilex/

# 自动修复
uv run ruff check --fix smilex/

# 格式化代码
uv run ruff format smilex/
```

### 类型检查（mypy）

```bash
uv add --dev mypy
uv run mypy smilex/
```

## 实践练习

1. **编写 indicators.py 单元测试**：为 `ma()`、`macd()`、`rsi()` 各写 3 个测试用例
2. **编写 scanner.py 评分测试**：为 `_evaluate()` 的每个评分规则写测试，验证分数正确
3. **编写 store.py 集成测试**：使用临时数据库测试 `save_daily()` 的去重逻辑
4. **添加测试覆盖率报告**：安装 pytest-cov，运行覆盖率分析，找出未覆盖的代码路径
5. **修复发现的问题**：如果测试发现 bug，修复代码并确保测试通过

## 自测清单

- [ ] 能解释 pytest 与 JUnit 的核心区别
- [ ] 能独立编写 pytest fixture 准备测试数据
- [ ] 能用 `@pytest.mark.parametrize` 编写参数化测试
- [ ] 为 indicators.py 至少编写 15 个测试用例
- [ ] 能使用临时数据库测试 store.py 的 CRUD 操作

## 学习资料

- [pytest 官方文档](https://docs.pytest.org/) — 最权威的参考
- [pytest 中文教程（菜鸟教程）](https://www.runoob.com/w3cnote/pytest-tutorial.html)
- [Ruff 官方文档](https://docs.astral.sh/ruff/) — Python 代码检查和格式化
- [pytest-cov 文档](https://pytest-cov.readthedocs.io/) — 测试覆盖率
- [mypy 官方文档](https://mypy.readthedocs.io/) — Python 类型检查
