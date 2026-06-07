import sqlite3
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
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date    TEXT UNIQUE NOT NULL,
    sector_type   TEXT NOT NULL DEFAULT 'all',
    analysis_text TEXT NOT NULL DEFAULT '',
    model_used    TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'pending',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_saan_date ON sector_analysis(trade_date);

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
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DATABASE_PATH))
    conn.row_factory = sqlite3.Row
    return conn


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
]


def init_db():
    conn = get_connection()
    conn.executescript(_SCHEMA)
    for sql in _MIGRATIONS:
        try:
            conn.execute(sql)
        except sqlite3.OperationalError:
            pass
    conn.commit()
    conn.close()
