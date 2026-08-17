"""SQLite schema and connection helpers."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS keywords (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    problem TEXT,
    search_query TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(category, search_query)
);

CREATE TABLE IF NOT EXISTS search_cache (
    category TEXT NOT NULL,
    search_query TEXT NOT NULL,
    executed_at TEXT NOT NULL,
    result_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (category, search_query)
);

CREATE TABLE IF NOT EXISTS search_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    executed_at TEXT NOT NULL DEFAULT (datetime('now')),
    keyword_count INTEGER NOT NULL DEFAULT 0,
    new_video_count INTEGER NOT NULL DEFAULT 0,
    api_units_used INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS channels (
    channel_id TEXT PRIMARY KEY,
    title TEXT,
    subscriber_count INTEGER,
    subscriber_hidden INTEGER NOT NULL DEFAULT 0,
    video_count INTEGER,
    view_count INTEGER,
    uploads_playlist_id TEXT,
    last_updated_at TEXT
);

CREATE TABLE IF NOT EXISTS videos (
    video_id TEXT PRIMARY KEY,
    channel_id TEXT NOT NULL,
    title TEXT,
    description TEXT,
    published_at TEXT,
    thumbnail_url TEXT,
    duration_seconds INTEGER,
    content_type TEXT NOT NULL DEFAULT 'unknown',
    is_live INTEGER NOT NULL DEFAULT 0,
    view_count INTEGER,
    like_count INTEGER,
    comment_count INTEGER,
    likes_hidden INTEGER NOT NULL DEFAULT 0,
    comments_disabled INTEGER NOT NULL DEFAULT 0,
    matched_keyword TEXT,
    problem_category TEXT,
    is_search_result INTEGER NOT NULL DEFAULT 0,
    first_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_updated_at TEXT
);

CREATE TABLE IF NOT EXISTS video_metrics_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT NOT NULL,
    snapshot_at TEXT NOT NULL DEFAULT (datetime('now')),
    view_count INTEGER,
    like_count INTEGER,
    comment_count INTEGER
);

CREATE INDEX IF NOT EXISTS idx_video_metrics_snapshots_video_id
    ON video_metrics_snapshots (video_id, snapshot_at);

CREATE TABLE IF NOT EXISTS video_keyword_matches (
    video_id TEXT NOT NULL,
    category TEXT NOT NULL,
    search_query TEXT NOT NULL,
    matched_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (video_id, category, search_query)
);

CREATE TABLE IF NOT EXISTS channel_baselines (
    channel_id TEXT NOT NULL,
    content_type TEXT NOT NULL,
    computed_at TEXT NOT NULL DEFAULT (datetime('now')),
    sample_size INTEGER NOT NULL,
    median_views REAL,
    mean_views REAL,
    confidence TEXT NOT NULL,
    PRIMARY KEY (channel_id, content_type)
);

CREATE TABLE IF NOT EXISTS outlier_scores (
    video_id TEXT PRIMARY KEY,
    computed_at TEXT NOT NULL DEFAULT (datetime('now')),
    channel_median_views REAL,
    channel_mean_views REAL,
    baseline_confidence TEXT,
    subscriber_ratio REAL,
    outlier_ratio REAL,
    views_per_day REAL,
    like_rate REAL,
    comment_rate REAL,
    outlier_grade TEXT,
    opportunity_score REAL
);

CREATE TABLE IF NOT EXISTS content_patterns (
    video_id TEXT PRIMARY KEY,
    viewer_problem TEXT,
    title_pattern TEXT,
    hook TEXT,
    promise TEXT,
    emotion TEXT,
    beginner_appeal TEXT,
    is_question INTEGER,
    is_negative INTEGER,
    is_reason INTEGER,
    is_result INTEGER,
    is_number INTEGER,
    is_fear_avoidance INTEGER,
    source TEXT NOT NULL DEFAULT 'rule',
    computed_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS my_channel_video_stats (
    video_id TEXT PRIMARY KEY,
    title TEXT,
    period_start TEXT,
    period_end TEXT,
    views INTEGER,
    ctr REAL,
    average_view_duration REAL,
    average_percentage_viewed REAL,
    watch_time_minutes REAL,
    subscriber_gain INTEGER,
    impressions INTEGER,
    top_traffic_source TEXT,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS topic_opportunities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    problem_category TEXT NOT NULL,
    computed_at TEXT NOT NULL DEFAULT (datetime('now')),
    market_demand_score REAL,
    my_channel_fit_score REAL,
    fit_data_available INTEGER NOT NULL DEFAULT 0,
    content_opportunity_score REAL,
    outlier_video_count INTEGER,
    evidence_json TEXT
);

CREATE TABLE IF NOT EXISTS weekly_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    generated_at TEXT NOT NULL DEFAULT (datetime('now')),
    file_path TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS api_call_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    endpoint TEXT NOT NULL,
    cost_units INTEGER NOT NULL,
    called_at TEXT NOT NULL DEFAULT (datetime('now')),
    context TEXT
);
"""


def get_connection(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# Columns added after a table already existed in someone's local database. `CREATE TABLE IF NOT
# EXISTS` silently no-ops on existing tables, so new columns need an explicit ALTER TABLE here.
_COLUMN_MIGRATIONS = [
    ("content_patterns", "emotion", "TEXT"),
    ("content_patterns", "beginner_appeal", "TEXT"),
]


def _run_migrations(conn: sqlite3.Connection) -> None:
    for table, column, col_type in _COLUMN_MIGRATIONS:
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")


def init_db(db_path: Path) -> None:
    conn = get_connection(db_path)
    try:
        conn.executescript(SCHEMA)
        _run_migrations(conn)
        conn.commit()
    finally:
        conn.close()


@contextmanager
def connect(db_path: Path):
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
