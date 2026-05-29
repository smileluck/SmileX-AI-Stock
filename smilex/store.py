import os
import sqlite3
import pandas as pd
from smilex.config import DB_PATH, DATA_DIR


def _conn() -> sqlite3.Connection:
    os.makedirs(DATA_DIR, exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_db():
    """创建数据库表结构"""
    conn = _conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS stock_info (
            code TEXT PRIMARY KEY, name TEXT, list_date TEXT, industry TEXT
        );
        CREATE TABLE IF NOT EXISTS stock_daily (
            code TEXT, date TEXT, open REAL, close REAL, high REAL, low REAL,
            volume REAL, amount REAL, turnover REAL,
            change_pct REAL, change_amt REAL, amplitude REAL,
            PRIMARY KEY (code, date)
        );
        CREATE TABLE IF NOT EXISTS index_daily (
            code TEXT, date TEXT, open REAL, close REAL, high REAL, low REAL,
            volume REAL, PRIMARY KEY (code, date)
        );
    """)
    conn.commit()
    conn.close()


def save_stock_list(df: pd.DataFrame):
    conn = _conn()
    df[["code", "name"]].to_sql("stock_info", conn, if_exists="replace", index=False)
    conn.close()


def save_daily(df: pd.DataFrame):
    """批量写入日K数据（自动去重）"""
    if df.empty:
        return
    conn = _conn()
    cols = ["code", "date", "open", "close", "high", "low",
            "volume", "amount", "turnover", "change_pct", "change_amt", "amplitude"]
    save_df = df[[c for c in cols if c in df.columns]].copy()
    save_df["date"] = save_df["date"].astype(str)
    save_df.to_sql("_tmp_daily", conn, if_exists="replace", index=False)
    conn.execute("INSERT OR REPLACE INTO stock_daily SELECT * FROM _tmp_daily")
    conn.execute("DROP TABLE _tmp_daily")
    conn.commit()
    conn.close()


def update_daily(codes: list[str] | None = None):
    """增量更新日K数据"""
    from smilex.fetcher import daily_history

    conn = _conn()
    if codes is None:
        codes = pd.read_sql("SELECT code FROM stock_info", conn)["code"].tolist()
    conn.close()

    for i, code in enumerate(codes):
        try:
            existing = query_daily(code)
            if existing.empty:
                daily_history(code).pipe(save_daily)
            else:
                last_date = existing["date"].max().strftime("%Y%m%d")
                new = daily_history(code, start_date=last_date)
                if not new.empty:
                    save_daily(new)
            print(f"[{i+1}/{len(codes)}] {code} updated")
        except Exception as e:
            print(f"[{i+1}/{len(codes)}] {code} failed: {e}")


def query_daily(code: str, start_date: str = "", end_date: str = "") -> pd.DataFrame:
    conn = _conn()
    sql = "SELECT * FROM stock_daily WHERE code = ?"
    params: list = [code]
    if start_date:
        sql += " AND date >= ?"
        params.append(start_date)
    if end_date:
        sql += " AND date <= ?"
        params.append(end_date)
    sql += " ORDER BY date"
    df = pd.read_sql(sql, conn, params=params)
    conn.close()
    if not df.empty and "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
    return df


def save_index(df: pd.DataFrame):
    if df.empty:
        return
    conn = _conn()
    cols = ["code", "date", "open", "close", "high", "low", "volume"]
    save_df = df[[c for c in cols if c in df.columns]].copy()
    save_df["date"] = save_df["date"].astype(str)
    save_df.to_sql("_tmp_index", conn, if_exists="replace", index=False)
    conn.execute("INSERT OR REPLACE INTO index_daily SELECT * FROM _tmp_index")
    conn.execute("DROP TABLE _tmp_index")
    conn.commit()
    conn.close()


def query_index(code: str, start_date: str = "") -> pd.DataFrame:
    conn = _conn()
    sql = "SELECT * FROM index_daily WHERE code = ?"
    params: list = [code]
    if start_date:
        sql += " AND date >= ?"
        params.append(start_date)
    sql += " ORDER BY date"
    df = pd.read_sql(sql, conn, params=params)
    conn.close()
    if not df.empty and "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
    return df
