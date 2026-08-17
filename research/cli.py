"""CLI entry point: `python -m research.cli <command>` (also exposed via run_research.py)."""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime

from research.analyze_pipeline import analyze_pending_videos, estimate_analyze_units
from research.analytics_client import run_oauth_flow
from research.config import load_config
from research.content_pattern_analyzer import analyze_video
from research.db import connect, init_db
from research.gemini_client import GeminiClient
from research.keyword_pool import add_keyword, iter_keywords, load_pool, sync_to_db
from research.my_channel import compute_topic_scores, sync_my_channel_stats
from research.outlier_detector import DEFAULT_GRADE_THRESHOLDS
from research.weekly_report import build_weekly_report
from research.youtube_client import YouTubeClient
from research.youtube_search import estimate_search_units, run_category_search

# Windows consoles often default to a non-UTF-8 codepage, which mangles the Korean text
# throughout this project (titles, keyword pool, reports). Force UTF-8 output regardless of
# the host codepage.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("research.cli")


def _ensure_db(cfg):
    init_db(cfg.db_path)
    pool = load_pool(cfg.keyword_pool_path)
    sync_to_db(cfg.db_path, pool)


def _total_quota_used(db_path) -> int:
    with connect(db_path) as conn:
        row = conn.execute("SELECT COALESCE(SUM(cost_units), 0) AS total FROM api_call_log").fetchone()
    return row["total"]


def _require_youtube_client(cfg) -> YouTubeClient:
    if not cfg.youtube_api_key:
        print("YOUTUBE_API_KEY is not set in .env", file=sys.stderr)
        sys.exit(1)
    return YouTubeClient(cfg.youtube_api_key, cfg.db_path)


def _gemini_client(cfg) -> GeminiClient:
    return GeminiClient(
        cfg.gemini_api_key,
        model=cfg.get("gemini", "model", default="gemini-flash-latest"),
        timeout_seconds=cfg.get("gemini", "timeout_seconds", default=30),
    )


def cmd_auth(args, cfg):
    if not cfg.youtube_client_id or not cfg.youtube_client_secret:
        print("YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET must be set in .env", file=sys.stderr)
        sys.exit(1)
    print("Opening a browser to authorize YouTube Analytics access...")
    run_oauth_flow(cfg.youtube_client_id, cfg.youtube_client_secret, cfg.oauth_token_path)
    print(f"Token saved to {cfg.oauth_token_path}")


def cmd_keywords_list(args, cfg):
    pool = load_pool(cfg.keyword_pool_path)
    for kw in iter_keywords(pool):
        print(f"[{kw.category}/{kw.problem_id}] {kw.search_query}  (problem: {kw.problem_label})")


def cmd_keywords_add(args, cfg):
    add_keyword(cfg.keyword_pool_path, args.category, args.problem_id, args.problem_label, args.query)
    print(f"Added '{args.query}' to category '{args.category}' / problem '{args.problem_id}'")


def cmd_search(args, cfg):
    yt = _require_youtube_client(cfg)
    cache_ttl_hours = cfg.get("search", "cache_ttl_hours", default=168)
    estimated = estimate_search_units(
        cfg.db_path, cfg.keyword_pool_path, args.category,
        cache_ttl_hours=cache_ttl_hours, query_limit=args.query_limit,
    )
    print(f"[quota] estimated {estimated} unit(s) for this search")
    result = run_category_search(
        cfg.db_path,
        cfg.keyword_pool_path,
        yt,
        args.category,
        max_results_per_query=cfg.get("search", "max_results_per_query", default=15),
        cache_ttl_hours=cache_ttl_hours,
        region_code=cfg.get("search", "region_code", default="KR"),
        relevance_language=cfg.get("search", "relevance_language", default="ko"),
        query_limit=args.query_limit,
        short_max_seconds=cfg.get("content_type", "short_max_seconds", default=60),
        ambiguous_max_seconds=cfg.get("content_type", "ambiguous_max_seconds", default=180),
    )
    print(result)


def cmd_analyze(args, cfg):
    yt = _require_youtube_client(cfg)
    estimated = estimate_analyze_units(cfg.db_path, cache_ttl_hours=cfg.get("baseline", "cache_ttl_hours", default=168))
    print(f"[quota] estimated {estimated} unit(s) for this analyze run")
    result = analyze_pending_videos(
        cfg.db_path,
        yt,
        baseline_cfg=cfg.get("baseline", default={}),
        content_type_cfg=cfg.get("content_type", default={}),
        grade_thresholds=cfg.get("outlier", "thresholds", default=DEFAULT_GRADE_THRESHOLDS),
        score_weights=cfg.get("opportunity_score", "weights", default={}),
        score_caps=cfg.get("opportunity_score", "caps", default={}),
        neutral_score=cfg.get("opportunity_score", "neutral_score_when_missing", default=50),
        min_grade_to_store=cfg.get("outlier", "min_grade_to_store", default="notable"),
    )
    print(result)


TOP_VIDEO_QUERY = """
    SELECT v.title, v.video_id, v.thumbnail_url, c.title AS channel_title, v.published_at,
           v.view_count, c.subscriber_count, os.channel_median_views, os.subscriber_ratio,
           os.outlier_ratio, os.views_per_day, os.opportunity_score, os.outlier_grade,
           v.matched_keyword, v.problem_category
    FROM outlier_scores os
    JOIN videos v ON v.video_id = os.video_id
    LEFT JOIN channels c ON c.channel_id = v.channel_id
    WHERE os.outlier_grade IS NOT NULL AND os.outlier_grade != 'normal'
    ORDER BY os.opportunity_score DESC
    LIMIT ?
"""


def cmd_top(args, cfg):
    with connect(cfg.db_path) as conn:
        rows = conn.execute(TOP_VIDEO_QUERY, (args.limit,)).fetchall()
    for i, r in enumerate(rows, start=1):
        print(f"{i}. {r['title']}")
        print(f"   channel: {r['channel_title']}")
        print(f"   video_url: https://www.youtube.com/watch?v={r['video_id']}")
        print(f"   thumbnail: {r['thumbnail_url']}")
        print(f"   published_at: {r['published_at']}")
        print(f"   views: {r['view_count']}  subscriber_count: {r['subscriber_count']}")
        print(f"   channel_median_views: {_fmt1(r['channel_median_views'])}")
        print(f"   subscriber_ratio: {_fmt1(r['subscriber_ratio'])}  outlier_ratio: {_fmt1(r['outlier_ratio'])}X"
              f" ({r['outlier_grade']})  views_per_day: {_fmt1(r['views_per_day'])}")
        print(f"   opportunity_score: {_fmt1(r['opportunity_score'])}/100")
        print(f"   matched_keyword: {r['matched_keyword']}  problem_category: {r['problem_category']}")
        print()


def _fmt1(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)


def cmd_patterns(args, cfg):
    gemini = _gemini_client(cfg)
    with connect(cfg.db_path) as conn:
        rows = conn.execute(
            """
            SELECT v.video_id, v.title FROM outlier_scores os
            JOIN videos v ON v.video_id = os.video_id
            WHERE os.outlier_grade IS NOT NULL AND os.outlier_grade != 'normal'
            ORDER BY os.opportunity_score DESC
            LIMIT 50
            """
        ).fetchall()

    for r in rows:
        pattern = analyze_video(
            r["video_id"], r["title"], gemini, max_output_tokens=cfg.get("gemini", "max_output_tokens", default=1024)
        )
        with connect(cfg.db_path) as conn:
            conn.execute(
                """
                INSERT INTO content_patterns (video_id, viewer_problem, title_pattern, hook, promise,
                    emotion, beginner_appeal, primary_archetype, secondary_archetype, is_question,
                    is_negative, is_reason, is_result, is_number, is_fear_avoidance, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(video_id) DO UPDATE SET
                    viewer_problem=excluded.viewer_problem, title_pattern=excluded.title_pattern,
                    hook=excluded.hook, promise=excluded.promise, emotion=excluded.emotion,
                    beginner_appeal=excluded.beginner_appeal, primary_archetype=excluded.primary_archetype,
                    secondary_archetype=excluded.secondary_archetype, is_question=excluded.is_question,
                    is_negative=excluded.is_negative, is_reason=excluded.is_reason,
                    is_result=excluded.is_result, is_number=excluded.is_number,
                    is_fear_avoidance=excluded.is_fear_avoidance, source=excluded.source,
                    computed_at=datetime('now')
                """,
                (
                    r["video_id"], pattern.viewer_problem, pattern.title_pattern, pattern.hook,
                    pattern.promise, pattern.emotion, pattern.beginner_appeal,
                    pattern.primary_archetype, pattern.secondary_archetype,
                    pattern.flags.is_question, pattern.flags.is_negative,
                    pattern.flags.is_reason, pattern.flags.is_result, pattern.flags.is_number,
                    pattern.flags.is_fear_avoidance, pattern.source,
                ),
            )

    yt = _require_youtube_client(cfg)
    my_stats = sync_my_channel_stats(
        cfg.db_path, cfg.youtube_client_id, cfg.youtube_client_secret, cfg.oauth_token_path, yt,
        lookback_days=cfg.get("my_channel", "lookback_days", default=90),
        traffic_source_top_n=cfg.get("my_channel", "traffic_source_top_n", default=20),
    )
    print("my_channel_stats:", my_stats)

    topics = compute_topic_scores(
        cfg.db_path,
        cfg.keyword_pool_path,
        market_demand_top_n=cfg.get("topic_score", "market_demand_top_n", default=5),
        market_demand_weights=cfg.get("topic_score", "market_demand_weights", default=None),
        outlier_count_cap=cfg.get("topic_score", "outlier_count_cap", default=10),
        fit_neutral_score=cfg.get("topic_score", "fit_neutral_score", default=50),
        min_candidate_videos=cfg.get("topic_score", "min_candidate_videos", default=10),
    )
    for t in topics:
        print(t)


def cmd_report_weekly(args, cfg):
    gemini = _gemini_client(cfg)
    path = build_weekly_report(
        cfg.db_path,
        cfg.reports_dir,
        gemini,
        cfg.get("channel", default={}),
        cfg.keyword_pool_path,
        max_output_tokens=cfg.get("gemini", "max_output_tokens", default=1024),
    )
    print(f"Report written to {path}")


def cmd_run_scheduled(args, cfg):
    weekday = datetime.now().strftime("%A").lower()
    task = cfg.get("schedule", weekday)
    if not task:
        print(f"No scheduled task for {weekday}")
        return
    print(f"Running scheduled task for {weekday}: {task}")
    if task == "report":
        cmd_analyze(args, cfg)
        cmd_patterns(args, cfg)
        cmd_report_weekly(args, cfg)
    else:
        args.category = task
        args.query_limit = None
        cmd_search(args, cfg)


def cmd_run_all(args, cfg):
    pool = load_pool(cfg.keyword_pool_path)
    for category in pool:
        args.category = category
        args.query_limit = args.query_limit
        cmd_search(args, cfg)
    cmd_analyze(args, cfg)
    cmd_patterns(args, cfg)
    cmd_report_weekly(args, cfg)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="research")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("auth", help="One-time OAuth consent for YouTube Analytics").set_defaults(func=cmd_auth)

    kw = sub.add_parser("keywords", help="Manage the keyword pool")
    kw_sub = kw.add_subparsers(dest="keywords_command", required=True)
    kw_sub.add_parser("list").set_defaults(func=cmd_keywords_list)
    kw_add = kw_sub.add_parser("add")
    kw_add.add_argument("--category", required=True)
    kw_add.add_argument("--problem-id", required=True, help="Short stable id, e.g. 'word_stress'")
    kw_add.add_argument("--problem-label", required=True, help="Natural-language viewer problem")
    kw_add.add_argument("--query", required=True)
    kw_add.set_defaults(func=cmd_keywords_add)

    search = sub.add_parser("search", help="Search a category and collect videos")
    search.add_argument("--category", required=True)
    search.add_argument("--query-limit", type=int, default=None, help="Limit number of queries run (for small test runs)")
    search.set_defaults(func=cmd_search)

    sub.add_parser("analyze", help="Compute baselines, outlier and opportunity scores").set_defaults(func=cmd_analyze)

    top = sub.add_parser("top", help="Show top outlier videos")
    top.add_argument("--limit", type=int, default=20)
    top.set_defaults(func=cmd_top)

    sub.add_parser("patterns", help="Analyze title patterns and compute topic scores").set_defaults(func=cmd_patterns)

    report = sub.add_parser("report", help="Generate a report")
    report_sub = report.add_subparsers(dest="report_command", required=True)
    report_sub.add_parser("weekly").set_defaults(func=cmd_report_weekly)

    sub.add_parser("run-scheduled", help="Run today's scheduled task from config").set_defaults(func=cmd_run_scheduled)

    run_all = sub.add_parser("run-all", help="Run the full pipeline for all categories")
    run_all.add_argument("--query-limit", type=int, default=None)
    run_all.set_defaults(func=cmd_run_all)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    cfg = load_config()
    _ensure_db(cfg)
    quota_before = _total_quota_used(cfg.db_path)
    args.func(args, cfg)
    quota_used = _total_quota_used(cfg.db_path) - quota_before
    print(f"[quota] this run used {quota_used} unit(s)")


if __name__ == "__main__":
    main()
