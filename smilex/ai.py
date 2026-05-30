import os
from datetime import datetime, timedelta

from smilex.config import AI_MODEL, AI_API_KEY, AI_API_BASE, AI_INDICES
from smilex.store import query_index, query_market_stats


def build_market_context(days: int = 90) -> str:
    from smilex.indicators import ma, macd, rsi, bollinger

    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    lines = [f"数据区间：近{days}天（{start_date} 至今）\n"]

    for name, code in AI_INDICES.items():
        df = query_index(code, start_date=start_date)
        if df.empty:
            continue
        df = ma(df, periods=[5, 10, 20, 60])
        df = macd(df)
        df = rsi(df)
        df = bollinger(df)
        latest = df.iloc[-1]

        lines.append(f"## {name}（{code}）")
        lines.append(f"  最新收盘价：{latest['close']:.2f}")
        lines.append(f"  MA5={latest.get('ma5', 0):.2f}  MA10={latest.get('ma10', 0):.2f}  "
                      f"MA20={latest.get('ma20', 0):.2f}  MA60={latest.get('ma60', 0):.2f}")
        lines.append(f"  RSI14={latest.get('rsi14', 0):.2f}")
        lines.append(f"  MACD DIF={latest.get('macd_dif', 0):.4f}  DEA={latest.get('macd_dea', 0):.4f}  "
                      f"HIST={latest.get('macd_hist', 0):.4f}")
        lines.append(f"  布林带 上轨={latest.get('boll_upper', 0):.2f}  "
                      f"中轨={latest.get('boll_mid', 0):.2f}  "
                      f"下轨={latest.get('boll_lower', 0):.2f}")

        if len(df) >= 5:
            chg5 = (df["close"].iloc[-1] - df["close"].iloc[-5]) / df["close"].iloc[-5] * 100
            lines.append(f"  近5日涨跌幅：{chg5:.2f}%")
        if len(df) >= 20:
            chg20 = (df["close"].iloc[-1] - df["close"].iloc[-20]) / df["close"].iloc[-20] * 100
            lines.append(f"  近20日涨跌幅：{chg20:.2f}%")
        if len(df) >= 60:
            chg60 = (df["close"].iloc[-1] - df["close"].iloc[-60]) / df["close"].iloc[-60] * 100
            lines.append(f"  近60日涨跌幅：{chg60:.2f}%")

        # 区间高低点
        high = df["high"].max()
        low = df["low"].min()
        lines.append(f"  区间最高：{high:.2f}  最低：{low:.2f}")
        lines.append("")

    stats_df = query_market_stats()
    if not stats_df.empty:
        s = stats_df.iloc[0]
        lines.append("## 市场广度")
        lines.append(f"  上涨：{int(s['up_count'])}  下跌：{int(s['down_count'])}  "
                      f"平盘：{int(s['flat_count'])}")
        lines.append(f"  涨停：{int(s['limit_up'])}  跌停：{int(s['limit_down'])}  "
                      f"总数：{int(s['total'])}")

    return "\n".join(lines)


def call_llm(system_prompt: str, user_prompt: str) -> str:
    import litellm

    api_key = AI_API_KEY or os.environ.get("SMILEX_AI_API_KEY", "")
    if not api_key:
        raise ValueError("SMILEX_AI_API_KEY 未配置，请设置环境变量")

    kwargs = {
        "model": AI_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "num_retries": 2,
    }
    api_base = AI_API_BASE or os.environ.get("SMILEX_AI_API_BASE", "")
    if api_base:
        kwargs["api_base"] = api_base

    response = litellm.completion(**kwargs)
    content = response.choices[0].message.content
    if not content:
        raise ValueError("AI返回内容为空")
    return content


_SYSTEM_EVALUATE = (
    "你是一位资深A股市场分析师。请根据提供的指数数据和技术指标，"
    "对近期大盘走势进行全面、客观的评价。要求：\n"
    "1. 判断当前市场所处的阶段（牛市/熊市/震荡市）\n"
    "2. 分别分析上证指数、深证成指、创业板指的走势特征\n"
    "3. 指出关键支撑位和阻力位\n"
    "4. 分析成交量能和市场情绪\n"
    "5. 给出风险等级评估（低/中/高）\n"
    "6. 给出操作建议（仓位建议）\n\n"
    "请用中文回答，使用markdown格式，条理清晰。"
)

_SYSTEM_SUMMARY = (
    "你是一位资深A股市场分析师。请根据今日收盘数据，完成两项任务：\n\n"
    "## 今日总结\n"
    "用3-5句话总结今日市场表现，包括指数涨跌、市场广度、资金情绪等。\n\n"
    "## 明日预测\n"
    "1. 给出明日走势的方向性判断（看多/看空/中性）\n"
    "2. 给出关键点位（支撑位和压力位）\n"
    "3. 给出信心度（高/中/低）\n"
    "4. 提示可能影响明日走势的因素\n\n"
    "请用中文回答，使用markdown格式。在回答开头用【今日总结】和【明日预测】明确分隔两部分。"
)


def evaluate_market(context: str | None = None) -> dict:
    if context is None:
        context = build_market_context(days=90)

    evaluation = call_llm(_SYSTEM_EVALUATE, context)
    return {
        "evaluation": evaluation,
        "model": AI_MODEL,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def summarize_and_predict(context: str | None = None) -> dict:
    if context is None:
        context = build_market_context(days=10)

    result = call_llm(_SYSTEM_SUMMARY, context)

    # 分割今日总结和明日预测
    summary = result
    prediction = result
    marker = "【明日预测】"
    idx = result.find(marker)
    if idx > 0:
        summary = result[:idx].replace("【今日总结】", "").strip()
        prediction = result[idx:].replace(marker, "").strip()

    return {
        "summary": summary,
        "prediction": prediction,
        "model": AI_MODEL,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
