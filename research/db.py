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
    problem_id TEXT,
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
    problem_id TEXT,
    problem_label TEXT,
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
    primary_archetype TEXT,
    secondary_archetype TEXT,
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
    market_evidence_status TEXT NOT NULL DEFAULT 'sufficient',
    candidate_video_count INTEGER NOT NULL DEFAULT 0,
    evidence_confidence TEXT NOT NULL DEFAULT 'low',
    evidence_json TEXT
);

CREATE TABLE IF NOT EXISTS weekly_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    generated_at TEXT NOT NULL DEFAULT (datetime('now')),
    file_path TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS topic_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    generated_at TEXT NOT NULL DEFAULT (datetime('now')),
    report_path TEXT,
    category TEXT NOT NULL,
    problem_id TEXT NOT NULL,
    problem_label TEXT NOT NULL,
    topic_text TEXT NOT NULL,
    cluster_id INTEGER NOT NULL,
    is_cluster_representative INTEGER NOT NULL DEFAULT 1,
    recommended_format TEXT NOT NULL,
    evidence_quality TEXT NOT NULL,
    topic_candidate_score REAL NOT NULL,
    market_demand_score REAL,
    my_channel_fit_score REAL,
    matched_video_count INTEGER NOT NULL,
    outlier_video_count INTEGER NOT NULL,
    representative_video_id TEXT,
    representative_outlier_ratio REAL,
    shortlisted INTEGER NOT NULL DEFAULT 0,
    shortlist_reason TEXT
);

CREATE TABLE IF NOT EXISTS click_analysis_videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    generated_at TEXT NOT NULL DEFAULT (datetime('now')),
    report_path TEXT,
    category TEXT NOT NULL,
    problem_id TEXT NOT NULL,
    video_id TEXT NOT NULL,
    content_type TEXT,
    evidence_quality TEXT NOT NULL,
    viewer_problem_at_click TEXT,
    title_hook TEXT,
    title_promise TEXT,
    has_curiosity_gap INTEGER,
    specificity TEXT,
    emotion TEXT,
    devices_json TEXT,
    primary_click_driver TEXT NOT NULL,
    secondary_click_driver TEXT,
    source TEXT NOT NULL DEFAULT 'rule'
);

CREATE TABLE IF NOT EXISTS click_analysis_topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    generated_at TEXT NOT NULL DEFAULT (datetime('now')),
    report_path TEXT,
    category TEXT NOT NULL,
    problem_id TEXT NOT NULL,
    topic_text TEXT NOT NULL,
    topic_candidate_score REAL,
    click_evidence_score REAL NOT NULL,
    combined_signal REAL,
    brand_fit TEXT NOT NULL,
    representative_video_count INTEGER NOT NULL,
    repeated_click_drivers_json TEXT,
    thumbnail_data_status TEXT NOT NULL DEFAULT 'unavailable',
    hook_data_status TEXT NOT NULL DEFAULT 'unavailable',
    selected_for_next_stage INTEGER NOT NULL DEFAULT 0,
    selection_reason TEXT
);

CREATE TABLE IF NOT EXISTS content_packages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    generated_at TEXT NOT NULL DEFAULT (datetime('now')),
    report_path TEXT,
    category TEXT NOT NULL,
    problem_id TEXT NOT NULL,
    topic_text TEXT NOT NULL,
    is_comparison_candidate INTEGER NOT NULL DEFAULT 0,
    title TEXT NOT NULL,
    thumbnail_text TEXT NOT NULL,
    visual_focus TEXT,
    layout TEXT,
    example_word TEXT,
    highlight_element TEXT,
    primary_angle TEXT NOT NULL,
    secondary_angle TEXT,
    primary_click_driver TEXT NOT NULL,
    title_thumbnail_relationship TEXT NOT NULL,
    brand_fit TEXT NOT NULL,
    copy_risk TEXT NOT NULL,
    exaggeration_penalty REAL NOT NULL DEFAULT 0,
    package_score REAL NOT NULL,
    topic_candidate_score REAL,
    click_evidence_score REAL,
    excluded_reason TEXT,
    selected_for_production INTEGER NOT NULL DEFAULT 0,
    production_reason TEXT
);

CREATE TABLE IF NOT EXISTS production_blueprints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    generated_at TEXT NOT NULL DEFAULT (datetime('now')),
    report_path TEXT,
    package_id INTEGER,
    category TEXT NOT NULL,
    problem_id TEXT NOT NULL,
    title TEXT NOT NULL,
    thumbnail_text TEXT NOT NULL,
    viewer_problem TEXT,
    click_expectation TEXT,
    video_promise TEXT,
    expected_transformation TEXT,
    core_question TEXT NOT NULL,
    core_answer TEXT NOT NULL,
    learning_objectives_json TEXT,
    scope_in_json TEXT,
    scope_out_json TEXT,
    prerequisite_level TEXT,
    hook_json TEXT,
    sections_json TEXT,
    example_ladder_json TEXT,
    mini_success_json TEXT,
    audio_visual_json TEXT,
    shorts_candidates_json TEXT,
    natural_next_topics_json TEXT,
    external_clip_needed INTEGER NOT NULL DEFAULT 0,
    clip_purpose TEXT,
    promise_feasibility TEXT NOT NULL,
    promise_risk_reason TEXT,
    brand_design_fit TEXT NOT NULL,
    brand_fit_reason TEXT,
    integrity_check_json TEXT,
    production_complexity TEXT NOT NULL,
    blueprint_score REAL NOT NULL,
    ready_for_script INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS video_scripts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    generated_at TEXT NOT NULL DEFAULT (datetime('now')),
    report_path TEXT,
    blueprint_id INTEGER,
    package_id INTEGER,
    topic_candidate_id INTEGER,
    title TEXT NOT NULL,
    thumbnail_text TEXT NOT NULL,
    viewer_problem TEXT,
    video_promise TEXT,
    expected_transformation TEXT,
    core_question TEXT NOT NULL,
    core_answer TEXT NOT NULL,
    script_json TEXT NOT NULL,
    script_text TEXT NOT NULL,
    estimated_duration_seconds REAL NOT NULL,
    estimated_word_count INTEGER NOT NULL,
    hook_score REAL NOT NULL,
    clarity_score REAL NOT NULL,
    scope_alignment_score REAL NOT NULL,
    example_alignment_score REAL NOT NULL,
    audio_first_score REAL NOT NULL,
    retention_score REAL NOT NULL,
    script_score REAL NOT NULL,
    integrity_json TEXT NOT NULL,
    ready_for_production INTEGER NOT NULL DEFAULT 0,
    generation_method TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS video_directions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    generated_at TEXT NOT NULL DEFAULT (datetime('now')),
    report_path TEXT,
    video_script_id INTEGER NOT NULL,
    preferred_format TEXT NOT NULL,
    final_format TEXT NOT NULL,
    format_confidence TEXT NOT NULL,
    format_reason_json TEXT,
    clip_dependency TEXT NOT NULL,
    fallback_format TEXT,
    final_format_status TEXT NOT NULL,
    director_score REAL,
    integrity_json TEXT NOT NULL,
    ready_for_production_planning INTEGER NOT NULL DEFAULT 0,
    generation_method TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS block_directions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_direction_id INTEGER NOT NULL,
    content_block_id TEXT NOT NULL,
    delivery_mode TEXT NOT NULL,
    production_intent TEXT,
    viewer_interaction_json TEXT,
    audio_requirement_json TEXT,
    visual_requirement_json TEXT,
    clip_requirement_json TEXT,
    retention_role_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS source_clip_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_direction_id INTEGER NOT NULL,
    content_block_id TEXT NOT NULL,
    source_ref TEXT,
    transcript TEXT,
    focus_in REAL NOT NULL,
    focus_out REAL NOT NULL,
    context_in REAL NOT NULL,
    context_out REAL NOT NULL,
    learning_match REAL NOT NULL,
    phenomenon_clarity REAL NOT NULL,
    replay_value REAL NOT NULL,
    context_independence REAL NOT NULL,
    audio_usability REAL NOT NULL,
    clip_score REAL NOT NULL,
    clip_grade TEXT NOT NULL,
    clip_role TEXT NOT NULL,
    confidence TEXT,
    selected INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS production_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    generated_at TEXT NOT NULL DEFAULT (datetime('now')),
    report_path TEXT,
    video_direction_id INTEGER NOT NULL,
    video_script_id INTEGER NOT NULL,
    final_format TEXT NOT NULL,
    plan_json TEXT NOT NULL,
    estimated_duration_seconds REAL NOT NULL,
    production_complexity TEXT NOT NULL,
    generation_method TEXT NOT NULL,
    integrity_check_json TEXT NOT NULL,
    planner_score REAL,
    ready_for_asset_generation INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS production_blocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    production_plan_id INTEGER NOT NULL,
    content_block_id TEXT NOT NULL,
    block_order INTEGER NOT NULL,
    delivery_mode TEXT NOT NULL,
    production_intent TEXT,
    timeline_spec_json TEXT NOT NULL,
    speech_segments_json TEXT NOT NULL,
    visual_spec_json TEXT NOT NULL,
    caption_spec_json TEXT NOT NULL,
    clip_spec_json TEXT,
    interaction_spec_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS speech_assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    production_plan_id INTEGER NOT NULL,
    content_block_id TEXT NOT NULL,
    speech_asset_id TEXT NOT NULL,
    speech_mode TEXT NOT NULL,
    voice_name TEXT,
    language_code TEXT,
    source_text TEXT NOT NULL,
    tts_input_text TEXT,
    display_text TEXT,
    expected_pronunciation TEXT,
    approximation_only INTEGER NOT NULL DEFAULT 0,
    source_clip_candidate_id INTEGER,
    pause_before_ms INTEGER NOT NULL DEFAULT 0,
    pause_after_ms INTEGER NOT NULL DEFAULT 0,
    replay_group TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
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
    ("content_patterns", "primary_archetype", "TEXT"),
    ("content_patterns", "secondary_archetype", "TEXT"),
    ("keywords", "problem_id", "TEXT"),
    ("video_keyword_matches", "problem_id", "TEXT"),
    ("video_keyword_matches", "problem_label", "TEXT"),
    ("topic_opportunities", "market_evidence_status", "TEXT NOT NULL DEFAULT 'sufficient'"),
    ("topic_opportunities", "candidate_video_count", "INTEGER NOT NULL DEFAULT 0"),
    ("topic_opportunities", "evidence_confidence", "TEXT NOT NULL DEFAULT 'low'"),
    ("video_scripts", "content_blocks_json", "TEXT"),
    ("video_scripts", "ready_for_direction", "INTEGER"),
    # 10 computed PODCAST dialogue beats in-memory but never persisted them, so 11 (which reads
    # video_directions/block_directions/source_clip_candidates as its base input per its own spec)
    # had no queryable way to consume a PODCAST direction from the DB. Purely additive.
    ("video_directions", "podcast_direction_json", "TEXT"),
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
