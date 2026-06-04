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
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DATABASE_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.executescript(_SCHEMA)
    conn.close()
