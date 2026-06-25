import sqlite3
from contextlib import contextmanager
from app.config import DATABASE_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS news (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source       TEXT NOT NULL,
    title        TEXT NOT NULL,
    content      TEXT DEFAULT '',
    url          TEXT UNIQUE NOT NULL,
    publish_time TEXT,
    fetch_time   TEXT NOT NULL,
    extra        TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_news_source ON news(source);
CREATE INDEX IF NOT EXISTS idx_news_publish_time ON news(publish_time);

CREATE TABLE IF NOT EXISTS sync_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id     TEXT NOT NULL,
    trigger    TEXT NOT NULL DEFAULT 'manual',
    results    TEXT NOT NULL DEFAULT '[]',
    total      INTEGER NOT NULL DEFAULT 0,
    status     TEXT NOT NULL DEFAULT 'ok',
    duration   REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sync_log_job ON sync_log(job_id);
CREATE INDEX IF NOT EXISTS idx_sync_log_created ON sync_log(created_at);

CREATE TABLE IF NOT EXISTS market_snapshot (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date   TEXT NOT NULL,
    market_type  TEXT NOT NULL,
    code         TEXT NOT NULL,
    name         TEXT NOT NULL,
    price        REAL,
    change       REAL,
    change_pct   REAL,
    volume       REAL,
    amount       REAL,
    high         REAL,
    low          REAL,
    open         REAL,
    prev_close   REAL,
    amplitude    REAL,
    update_time  TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ms_date_type_code ON market_snapshot(trade_date, market_type, code);
CREATE INDEX IF NOT EXISTS idx_ms_date ON market_snapshot(trade_date);

CREATE TABLE IF NOT EXISTS market_analysis (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date          TEXT UNIQUE NOT NULL,
    analysis_text       TEXT NOT NULL DEFAULT '',
    prediction_text     TEXT NOT NULL DEFAULT '',
    prediction_summary  TEXT NOT NULL DEFAULT '{}',
    actual_data         TEXT NOT NULL DEFAULT '{}',
    review_text         TEXT NOT NULL DEFAULT '',
    scored_news         TEXT NOT NULL DEFAULT '[]',
    model_used          TEXT NOT NULL DEFAULT '',
    status              TEXT NOT NULL DEFAULT 'pending',
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ma_date ON market_analysis(trade_date);
CREATE INDEX IF NOT EXISTS idx_ma_status ON market_analysis(status);

CREATE TABLE IF NOT EXISTS sector_snapshot (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date   TEXT NOT NULL,
    sector_type  TEXT NOT NULL,
    item_count   INTEGER NOT NULL DEFAULT 0,
    status       TEXT NOT NULL DEFAULT 'ok',
    created_at   TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ss_date_type ON sector_snapshot(trade_date, sector_type);

CREATE TABLE IF NOT EXISTS sector_snapshot_item (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id           INTEGER NOT NULL REFERENCES sector_snapshot(id),
    trade_date            TEXT NOT NULL,
    sector_type           TEXT NOT NULL,
    code                  TEXT NOT NULL,
    name                  TEXT NOT NULL,
    price                 REAL,
    change_pct            REAL,
    change                REAL,
    volume                REAL,
    amount                REAL,
    up_count              INTEGER,
    down_count            INTEGER,
    flat_count            INTEGER,
    leading_stock         TEXT,
    leading_stock_code    TEXT,
    leading_stock_change_pct REAL,
    main_net_inflow       REAL,
    main_net_inflow_pct   REAL,
    super_large_net       REAL,
    large_net             REAL,
    medium_net            REAL,
    small_net             REAL
);
CREATE INDEX IF NOT EXISTS idx_ssi_date_type ON sector_snapshot_item(trade_date, sector_type);
CREATE INDEX IF NOT EXISTS idx_ssi_code_date ON sector_snapshot_item(code, trade_date);

CREATE TABLE IF NOT EXISTS ai_daily_report (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date        TEXT UNIQUE NOT NULL,
    report_text       TEXT NOT NULL DEFAULT '',
    market_summary    TEXT NOT NULL DEFAULT '',
    sector_hot        TEXT NOT NULL DEFAULT '',
    capital_flow      TEXT NOT NULL DEFAULT '',
    news_sentiment    TEXT NOT NULL DEFAULT '',
    outlook           TEXT NOT NULL DEFAULT '',
    risk_warning      TEXT NOT NULL DEFAULT '',
    model_used        TEXT NOT NULL DEFAULT '',
    status            TEXT NOT NULL DEFAULT 'pending',
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_adr_date ON ai_daily_report(trade_date);
CREATE INDEX IF NOT EXISTS idx_adr_status ON ai_daily_report(status);

CREATE TABLE IF NOT EXISTS limit_up_snapshot (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date          TEXT NOT NULL,
    code                TEXT NOT NULL,
    name                TEXT NOT NULL,
    price               REAL,
    change_pct          REAL,
    limit_up_amount     REAL,
    turnover_rate       REAL,
    volume              REAL,
    amount              REAL,
    amplitude           REAL,
    first_limit_up_time TEXT,
    last_limit_up_time  TEXT,
    limit_up_times      INTEGER DEFAULT 1,
    reason              TEXT DEFAULT '',
    sector              TEXT DEFAULT '',
    created_at          TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_lus_date_code ON limit_up_snapshot(trade_date, code);
CREATE INDEX IF NOT EXISTS idx_lus_date ON limit_up_snapshot(trade_date);

CREATE TABLE IF NOT EXISTS stock_recommendation (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date        TEXT NOT NULL,
    code              TEXT NOT NULL,
    name              TEXT NOT NULL,
    reason            TEXT DEFAULT '',
    strategy          TEXT DEFAULT '',
    target_price      REAL,
    stop_loss_price   REAL,
    risk_level        TEXT DEFAULT 'medium',
    confidence        REAL DEFAULT 0.5,
    sector            TEXT DEFAULT '',
    score             REAL DEFAULT 0,
    model_used        TEXT DEFAULT '',
    status            TEXT DEFAULT 'pending',
    actual_return_pct REAL,
    actual_exit_date  TEXT,
    current_price     REAL,
    buy_low           REAL,
    buy_high          REAL,
    take_profit_price REAL,
    phase             TEXT NOT NULL DEFAULT 'afternoon',
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sr_date ON stock_recommendation(trade_date);
CREATE INDEX IF NOT EXISTS idx_sr_status ON stock_recommendation(status);

CREATE TABLE IF NOT EXISTS sector_analysis (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date            TEXT NOT NULL,
    sector_type           TEXT NOT NULL,
    analysis_text         TEXT NOT NULL DEFAULT '',
    prediction_text       TEXT NOT NULL DEFAULT '',
    prediction_summary    TEXT NOT NULL DEFAULT '{}',
    actual_data           TEXT NOT NULL DEFAULT '{}',
    review_text           TEXT NOT NULL DEFAULT '',
    scored_news           TEXT NOT NULL DEFAULT '[]',
    trend_data            TEXT NOT NULL DEFAULT '{}',
    model_used            TEXT NOT NULL DEFAULT '',
    status                TEXT NOT NULL DEFAULT 'pending',
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_saan_date_type ON sector_analysis(trade_date, sector_type);

CREATE TABLE IF NOT EXISTS model_config (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    function_key TEXT UNIQUE NOT NULL,
    model_name   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS strategy (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    type            TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    prompt_template TEXT NOT NULL DEFAULT '',
    weight_config   TEXT NOT NULL DEFAULT '{}',
    news_enabled    INTEGER NOT NULL DEFAULT 1,
    news_count      INTEGER NOT NULL DEFAULT 15,
    output_format   TEXT NOT NULL DEFAULT '{}',
    is_enabled      INTEGER NOT NULL DEFAULT 1,
    is_default      INTEGER NOT NULL DEFAULT 0,
    sort_order      INTEGER NOT NULL DEFAULT 0,
    model_override  TEXT DEFAULT NULL,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_strategy_type ON strategy(type);
CREATE INDEX IF NOT EXISTS idx_strategy_enabled ON strategy(is_enabled);

CREATE TABLE IF NOT EXISTS limit_up_analysis (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date            TEXT NOT NULL,
    code                  TEXT NOT NULL,
    name                  TEXT NOT NULL,
    price                 REAL,
    change_pct            REAL,
    turnover_rate         REAL,
    amount                REAL,
    limit_up_times        INTEGER DEFAULT 1,
    sector                TEXT DEFAULT '',
    board                 TEXT DEFAULT '',
    stock_type            TEXT NOT NULL DEFAULT 'limit_up',
    phase                 TEXT NOT NULL DEFAULT 'close',
    first_limit_up_time   TEXT,
    last_limit_up_time    TEXT,
    limit_up_amount       REAL,
    ai_reason             TEXT DEFAULT '',
    ai_tomorrow_judge     TEXT DEFAULT '',
    ai_tomorrow_prob      TEXT DEFAULT '',
    ai_confidence         REAL DEFAULT 0,
    ai_key_factors        TEXT DEFAULT '[]',
    model_used            TEXT DEFAULT '',
    status                TEXT NOT NULL DEFAULT 'pending',
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_lua_date_code ON limit_up_analysis(trade_date, code, stock_type, phase);
CREATE INDEX IF NOT EXISTS idx_lua_date ON limit_up_analysis(trade_date);
CREATE INDEX IF NOT EXISTS idx_lua_board ON limit_up_analysis(board);

CREATE TABLE IF NOT EXISTS stock_daily (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date              TEXT NOT NULL,
    code                    TEXT NOT NULL,
    name                    TEXT NOT NULL,
    board                   TEXT NOT NULL DEFAULT '',
    open                    REAL,
    close                   REAL,
    high                    REAL,
    low                     REAL,
    prev_close              REAL,
    change_pct              REAL,
    change                  REAL,
    volume                  REAL,
    amount                  REAL,
    turnover_rate           REAL,
    volume_ratio            REAL,
    amplitude               REAL,
    pe_ttm                  REAL,
    pe_static               REAL,
    pb                      REAL,
    total_market_cap        REAL,
    circulating_market_cap  REAL,
    main_net_inflow         REAL,
    main_net_inflow_pct     REAL,
    super_large_net         REAL,
    large_net               REAL,
    medium_net              REAL,
    small_net               REAL,
    created_at              TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_sd_date_code ON stock_daily(trade_date, code);
CREATE INDEX IF NOT EXISTS idx_sd_date ON stock_daily(trade_date);
CREATE INDEX IF NOT EXISTS idx_sd_board ON stock_daily(board);
CREATE INDEX IF NOT EXISTS idx_sd_code ON stock_daily(code);

CREATE TABLE IF NOT EXISTS watchlist_stock (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    code         TEXT UNIQUE NOT NULL,
    name         TEXT NOT NULL DEFAULT '',
    note         TEXT NOT NULL DEFAULT '',
    sort_order   INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_watchlist_code ON watchlist_stock(code);
CREATE INDEX IF NOT EXISTS idx_watchlist_sort ON watchlist_stock(sort_order);

-- 自定义虚拟板块（用户自己命名、手动管理成分股）
CREATE TABLE IF NOT EXISTS watchlist_custom_sector (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    note        TEXT NOT NULL DEFAULT '',
    sort_order  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- 市场板块关注（行业/概念，从已有 sector 体系挑选）
CREATE TABLE IF NOT EXISTS watchlist_sector (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sector_name TEXT NOT NULL,
    sector_type TEXT NOT NULL,
    note        TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ws_name_type ON watchlist_sector(sector_name, sector_type);

-- 关注股每日行情快照（与 stock_daily 解耦，专注关注股的中长期追踪）
CREATE TABLE IF NOT EXISTS watchlist_stock_daily (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    code                TEXT NOT NULL,
    trade_date          TEXT NOT NULL,
    open                REAL,
    high                REAL,
    low                 REAL,
    close               REAL,
    prev_close          REAL,
    change_pct          REAL,
    change              REAL,
    volume              REAL,
    amount              REAL,
    turnover_rate       REAL,
    main_net_inflow     REAL,
    main_net_inflow_pct REAL,
    created_at          TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_wsd_date_code ON watchlist_stock_daily(trade_date, code);
CREATE INDEX IF NOT EXISTS idx_wsd_code ON watchlist_stock_daily(code);

-- 买入时机分析结果（早盘/收盘各一次）
CREATE TABLE IF NOT EXISTS watchlist_analysis (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date      TEXT NOT NULL,
    phase           TEXT NOT NULL,
    code            TEXT NOT NULL,
    name            TEXT NOT NULL DEFAULT '',
    analysis_text   TEXT NOT NULL DEFAULT '',
    suggested_action TEXT NOT NULL DEFAULT '',
    buy_low         REAL,
    buy_high        REAL,
    support_price   REAL,
    resistance_price REAL,
    confidence      REAL DEFAULT 0,
    reason          TEXT NOT NULL DEFAULT '',
    model_used      TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'done',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_wa_date_phase_code ON watchlist_analysis(trade_date, phase, code);
CREATE INDEX IF NOT EXISTS idx_wa_date ON watchlist_analysis(trade_date);
CREATE INDEX IF NOT EXISTS idx_wa_code ON watchlist_analysis(code);

CREATE TABLE IF NOT EXISTS stock_fundamental (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT NOT NULL,
    name            TEXT NOT NULL DEFAULT '',
    report_date     TEXT NOT NULL,
    roe             REAL,
    eps             REAL,
    revenue_growth  REAL,
    profit_growth   REAL,
    gross_margin    REAL,
    net_margin      REAL,
    update_time     TEXT,
    created_at      TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_sf_code_report ON stock_fundamental(code, report_date);
CREATE INDEX IF NOT EXISTS idx_sf_code ON stock_fundamental(code);

CREATE TABLE IF NOT EXISTS stock_capital_detail (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date            TEXT NOT NULL,
    code                  TEXT NOT NULL,
    name                  TEXT NOT NULL DEFAULT '',
    north_hold_qty        REAL,
    north_hold_market_cap REAL,
    north_hold_pct        REAL,
    margin_balance        REAL,
    margin_buy            REAL,
    short_sell_volume     REAL,
    short_balance         REAL,
    created_at            TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_scd_date_code ON stock_capital_detail(trade_date, code);
CREATE INDEX IF NOT EXISTS idx_scd_code ON stock_capital_detail(code);

CREATE TABLE IF NOT EXISTS stock_analysis (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date          TEXT NOT NULL,
    code                TEXT NOT NULL,
    name                TEXT NOT NULL DEFAULT '',
    board               TEXT NOT NULL DEFAULT '',
    analysis_text       TEXT NOT NULL DEFAULT '',
    prediction_text     TEXT NOT NULL DEFAULT '',
    prediction_summary  TEXT NOT NULL DEFAULT '{}',
    stock_data          TEXT NOT NULL DEFAULT '{}',
    context_data        TEXT NOT NULL DEFAULT '{}',
    recent_news         TEXT NOT NULL DEFAULT '[]',
    model_used          TEXT NOT NULL DEFAULT '',
    status              TEXT NOT NULL DEFAULT 'pending',
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sa_code ON stock_analysis(code);
CREATE INDEX IF NOT EXISTS idx_sa_trade_date ON stock_analysis(trade_date);
CREATE INDEX IF NOT EXISTS idx_sa_created_at ON stock_analysis(created_at);
CREATE INDEX IF NOT EXISTS idx_sa_code_date ON stock_analysis(code, trade_date);

CREATE TABLE IF NOT EXISTS news_sector_association (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    news_id         INTEGER NOT NULL,
    sector_code     TEXT NOT NULL,
    sector_name     TEXT NOT NULL,
    sector_type     TEXT NOT NULL,
    impact_score    REAL NOT NULL DEFAULT 5,
    impact_category TEXT DEFAULT '其他',
    relevance       TEXT DEFAULT 'medium',
    trade_date      TEXT NOT NULL,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_nsa_news ON news_sector_association(news_id);
CREATE INDEX IF NOT EXISTS idx_nsa_sector_date ON news_sector_association(sector_code, trade_date);
CREATE INDEX IF NOT EXISTS idx_nsa_date ON news_sector_association(trade_date);

CREATE TABLE IF NOT EXISTS tomorrow_strategy (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date      TEXT UNIQUE NOT NULL,
    content_json    TEXT NOT NULL DEFAULT '{}',
    raw_text        TEXT NOT NULL DEFAULT '',
    sectors_json    TEXT NOT NULL DEFAULT '[]',
    stocks_json     TEXT NOT NULL DEFAULT '[]',
    strategy_json   TEXT NOT NULL DEFAULT '{}',
    model_used      TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'pending',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ts_date ON tomorrow_strategy(trade_date);
CREATE INDEX IF NOT EXISTS idx_ts_status ON tomorrow_strategy(status);

CREATE TABLE IF NOT EXISTS research_report (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source        TEXT NOT NULL DEFAULT 'research_eastmoney',
    title         TEXT NOT NULL,
    url           TEXT UNIQUE NOT NULL,
    report_type   TEXT NOT NULL DEFAULT 'stock',
    org           TEXT DEFAULT '',
    analyst       TEXT DEFAULT '',
    rating        TEXT DEFAULT '',
    target_price  REAL,
    current_price REAL,
    industry      TEXT DEFAULT '',
    stock_codes   TEXT DEFAULT '[]',
    publish_date  TEXT,
    fetch_time    TEXT NOT NULL,
    summary       TEXT DEFAULT '',
    content       TEXT DEFAULT '',
    extra         TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_rr_publish ON research_report(publish_date);
CREATE INDEX IF NOT EXISTS idx_rr_type ON research_report(report_type);
CREATE INDEX IF NOT EXISTS idx_rr_rating ON research_report(rating);
CREATE INDEX IF NOT EXISTS idx_rr_stock_codes ON research_report(stock_codes);

CREATE TABLE IF NOT EXISTS research_pick (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date         TEXT NOT NULL,
    code               TEXT NOT NULL,
    name               TEXT DEFAULT '',
    report_count       INTEGER DEFAULT 0,
    buy_rating_count   INTEGER DEFAULT 0,
    avg_target_price   REAL,
    upside_pct         REAL,
    current_price      REAL,
    org_count          INTEGER DEFAULT 0,
    consensus_score    REAL DEFAULT 0,
    ai_advice          TEXT DEFAULT '',
    ai_buy_low         REAL,
    ai_buy_high        REAL,
    ai_stop_loss       REAL,
    ai_catalyst        TEXT DEFAULT '',
    ai_risk            TEXT DEFAULT '',
    ai_analysis        TEXT DEFAULT '',
    confidence         REAL DEFAULT 0,
    score              REAL DEFAULT 0,
    model_used         TEXT DEFAULT '',
    status             TEXT DEFAULT 'pending',
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_rp_date_code ON research_pick(trade_date, code);
CREATE INDEX IF NOT EXISTS idx_rp_date ON research_pick(trade_date);
CREATE INDEX IF NOT EXISTS idx_rp_advice ON research_pick(ai_advice);

CREATE TABLE IF NOT EXISTS backtest_run (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    strategy_type   TEXT NOT NULL,
    params_json     TEXT NOT NULL,
    universe        TEXT NOT NULL,
    start_date      TEXT NOT NULL,
    end_date        TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'done',
    metrics_json    TEXT DEFAULT '{}',
    error_msg       TEXT DEFAULT '',
    created_at      TEXT NOT NULL,
    finished_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_bt_run_created ON backtest_run(created_at);

CREATE TABLE IF NOT EXISTS backtest_trade (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER NOT NULL,
    trade_date      TEXT NOT NULL,
    code            TEXT NOT NULL,
    name            TEXT,
    side            TEXT NOT NULL,
    price           REAL,
    shares          INTEGER,
    amount          REAL,
    cost            REAL,
    reason          TEXT,
    FOREIGN KEY(run_id) REFERENCES backtest_run(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_bt_trade_run ON backtest_trade(run_id);
CREATE INDEX IF NOT EXISTS idx_bt_trade_date ON backtest_trade(trade_date);

CREATE TABLE IF NOT EXISTS backtest_equity (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER NOT NULL,
    trade_date      TEXT NOT NULL,
    equity          REAL NOT NULL,
    cash            REAL NOT NULL,
    position_value  REAL NOT NULL,
    benchmark       REAL,
    drawdown        REAL,
    FOREIGN KEY(run_id) REFERENCES backtest_run(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_bt_eq_run ON backtest_equity(run_id);
CREATE INDEX IF NOT EXISTS idx_bt_eq_date ON backtest_equity(trade_date);

CREATE TABLE IF NOT EXISTS benchmark_daily (
    code            TEXT NOT NULL,
    trade_date      TEXT NOT NULL,
    close           REAL NOT NULL,
    PRIMARY KEY (code, trade_date)
);
"""


def get_connection() -> sqlite3.Connection:
    # timeout=30s: 默认 5s 太短，scheduler worker 与 FastAPI 写入并发时会触发
    #   OperationalError: database is locked；30s 给锁排队留足窗口。
    conn = sqlite3.connect(str(DATABASE_PATH), timeout=30.0)
    conn.row_factory = sqlite3.Row
    # busy_timeout: 收到 SQLITE_BUSY 时由 SQLite 内部轮询重试 30s，
    #   避免短锁冲突直接抛错；与 connect timeout 双保险。
    conn.execute("PRAGMA busy_timeout=30000")
    # synchronous=NORMAL: WAL 模式下只在 checkpoint 时 fsync，写性能更好；
    # 会话级，每个连接必须单独设（默认 FULL=2 会拖慢所有写入）。
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


@contextmanager
def db_session():
    """连接管理上下文。退出时一定 close()，避免泄漏。

    注意：sqlite3.Connection 内置 ``with`` 语法只做事务 commit/rollback、不关闭连接，
    所以本项目统一通过 ``with db_session() as conn:`` 拿连接，而不是 ``with get_connection()``.
    """
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


_MIGRATIONS = [
    "ALTER TABLE market_analysis ADD COLUMN scored_news TEXT NOT NULL DEFAULT '[]'",
    "ALTER TABLE stock_recommendation ADD COLUMN phase TEXT NOT NULL DEFAULT 'afternoon'",
    "ALTER TABLE stock_recommendation ADD COLUMN current_price REAL",
    "ALTER TABLE stock_recommendation ADD COLUMN buy_low REAL",
    "ALTER TABLE stock_recommendation ADD COLUMN buy_high REAL",
    "ALTER TABLE stock_recommendation ADD COLUMN take_profit_price REAL",
    "DROP INDEX IF EXISTS idx_sr_date_code",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_sr_date_code_phase ON stock_recommendation(trade_date, code, phase)",
    "CREATE INDEX IF NOT EXISTS idx_sr_phase ON stock_recommendation(phase)",
    "ALTER TABLE limit_up_analysis ADD COLUMN phase TEXT NOT NULL DEFAULT 'close'",
    "DROP INDEX IF EXISTS idx_lua_date_code",
    "ALTER TABLE sector_analysis RENAME TO sector_analysis_old",
    ("CREATE TABLE IF NOT EXISTS sector_analysis ("
     "id INTEGER PRIMARY KEY AUTOINCREMENT, "
     "trade_date TEXT NOT NULL, sector_type TEXT NOT NULL, "
     "analysis_text TEXT NOT NULL DEFAULT '', "
     "prediction_text TEXT NOT NULL DEFAULT '', "
     "prediction_summary TEXT NOT NULL DEFAULT '{}', "
     "actual_data TEXT NOT NULL DEFAULT '{}', "
     "review_text TEXT NOT NULL DEFAULT '', "
     "scored_news TEXT NOT NULL DEFAULT '[]', "
     "trend_data TEXT NOT NULL DEFAULT '{}', "
     "model_used TEXT NOT NULL DEFAULT '', "
     "status TEXT NOT NULL DEFAULT 'pending', "
     "created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"),
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_saan_date_type ON sector_analysis(trade_date, sector_type)",
    ("INSERT OR IGNORE INTO sector_analysis "
     "(id, trade_date, sector_type, analysis_text, prediction_text, prediction_summary, "
     "actual_data, review_text, scored_news, trend_data, model_used, status, created_at, updated_at) "
     "SELECT id, trade_date, 'industry', analysis_text, '', '{}', '{}', '', '[]', '{}', "
     "model_used, status, created_at, updated_at FROM sector_analysis_old"),
    "DROP TABLE IF EXISTS sector_analysis_old",
    "UPDATE sector_analysis SET sector_type='industry' WHERE sector_type='all'",
    # ---- stock_recommendation: 估值/累计涨幅/催化剂/风险审计列（PR1 风控） ----
    "ALTER TABLE stock_recommendation ADD COLUMN pe_ttm REAL",
    "ALTER TABLE stock_recommendation ADD COLUMN pe_static REAL",
    "ALTER TABLE stock_recommendation ADD COLUMN pb REAL",
    "ALTER TABLE stock_recommendation ADD COLUMN total_market_cap REAL",
    "ALTER TABLE stock_recommendation ADD COLUMN cum_gain_5d REAL",
    "ALTER TABLE stock_recommendation ADD COLUMN cum_gain_20d REAL",
    "ALTER TABLE stock_recommendation ADD COLUMN cum_gain_60d REAL",
    "ALTER TABLE stock_recommendation ADD COLUMN roe REAL",
    "ALTER TABLE stock_recommendation ADD COLUMN revenue_growth REAL",
    "ALTER TABLE stock_recommendation ADD COLUMN profit_growth REAL",
    "ALTER TABLE stock_recommendation ADD COLUMN catalyst TEXT DEFAULT ''",
    "ALTER TABLE stock_recommendation ADD COLUMN high_position_risk TEXT DEFAULT ''",
    "ALTER TABLE stock_recommendation ADD COLUMN risk_note TEXT DEFAULT ''",
    "ALTER TABLE stock_recommendation ADD COLUMN risk_tags TEXT DEFAULT ''",
    "ALTER TABLE stock_recommendation ADD COLUMN price_stale INTEGER DEFAULT 0",
    # ---- watchlist_stock: 扩展为完整的自选股追踪表 ----
    "ALTER TABLE watchlist_stock ADD COLUMN add_price REAL",
    "ALTER TABLE watchlist_stock ADD COLUMN add_date TEXT",
    "ALTER TABLE watchlist_stock ADD COLUMN target_buy_price REAL",
    "ALTER TABLE watchlist_stock ADD COLUMN stop_loss_price REAL",
    "ALTER TABLE watchlist_stock ADD COLUMN status TEXT DEFAULT 'watching'",
    "ALTER TABLE watchlist_stock ADD COLUMN custom_sector_id INTEGER",
    "ALTER TABLE watchlist_stock ADD COLUMN source TEXT DEFAULT 'manual'",
]


def init_db():
    conn = get_connection()
    # 启用 WAL：读写不再互斥（写只锁 -wal 文件，读走主库 + wal），
    # 持久化到数据库文件头，重启后仍生效；synchronous=NORMAL 配 WAL 足够安全且更快。
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
    except sqlite3.OperationalError:
        pass
    # 清理可能因历史迁移残留的重复数据，防止唯一索引创建失败
    try:
        conn.execute(
            "DELETE FROM sector_analysis WHERE id NOT IN ("
            "SELECT MAX(id) FROM sector_analysis GROUP BY trade_date, sector_type"
            ")"
        )
    except sqlite3.OperationalError:
        pass
    conn.executescript(_SCHEMA)
    for sql in _MIGRATIONS:
        try:
            conn.execute(sql)
        except (sqlite3.OperationalError, sqlite3.IntegrityError):
            pass
    conn.commit()
    conn.close()
    # 启动时清理一次过期 sync_log（覆盖重启场景）；运行期由定时任务清理。
    cleanup_old_logs()


_SYNC_LOG_RETAIN_DAYS = 90


def cleanup_old_logs(retain_days: int = _SYNC_LOG_RETAIN_DAYS) -> int:
    """删除超过 retain_days 天的 sync_log，返回删除条数。

    sync_log 每天写入 ~500 行（5 分钟 news_sync + 30+ cron 任务），
    90 天约 4.5 万行；放任增长会让 sync_log 查询和写入变慢。
    """
    conn = get_connection()
    try:
        cur = conn.execute(
            "DELETE FROM sync_log WHERE created_at < datetime('now', ?)",
            (f"-{retain_days} days",),
        )
        conn.commit()
        return cur.rowcount or 0
    finally:
        conn.close()
