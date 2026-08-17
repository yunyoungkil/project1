"""Runs keyword searches for a category, respecting the search cache (avoids repeat search.list
calls within cache_ttl_hours -- by far the most expensive endpoint at 100 units/call)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from research.db import connect
from research.keyword_pool import Keyword, best_matching_problem, keywords_for_category, load_pool
from research.video_stats import normalize_video, upsert_videos
from research.youtube_client import YouTubeClient


def _is_cached(db_path: Path, category: str, search_query: str, ttl_hours: int) -> bool:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT executed_at FROM search_cache WHERE category = ? AND search_query = ?",
            (category, search_query),
        ).fetchone()
    if not row:
        return False
    executed_at = datetime.fromisoformat(row["executed_at"])
    return datetime.now(timezone.utc) - executed_at < timedelta(hours=ttl_hours)


def estimate_search_units(
    db_path: Path,
    keyword_pool_path: Path,
    category: str,
    *,
    cache_ttl_hours: int = 168,
    query_limit: int | None = None,
) -> int:
    """Estimates the search.list quota this category run will actually spend, before running
    it -- counts only the queries that aren't still fresh in search_cache."""
    pool = load_pool(keyword_pool_path)
    keywords = keywords_for_category(pool, category)
    if query_limit is not None:
        keywords = keywords[:query_limit]
    uncached = sum(0 if _is_cached(db_path, kw.category, kw.search_query, cache_ttl_hours) else 1 for kw in keywords)
    return uncached * 100


def _mark_cached(db_path: Path, category: str, search_query: str, result_count: int) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO search_cache (category, search_query, executed_at, result_count)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(category, search_query) DO UPDATE SET
                executed_at = excluded.executed_at, result_count = excluded.result_count
            """,
            (category, search_query, datetime.now(timezone.utc).isoformat(), result_count),
        )


def _record_matches(
    db_path: Path, videos: list[dict], category: str, search_query: str, problems: list[str]
) -> None:
    """Records each video's match and picks the specific problem (out of the category's full
    problem list) whose words best overlap the video's own title, rather than always tagging
    every match in a category with the same "primary" problem."""
    with connect(db_path) as conn:
        for v in videos:
            vid = v["video_id"]
            conn.execute(
                """
                INSERT OR IGNORE INTO video_keyword_matches (video_id, category, search_query)
                VALUES (?, ?, ?)
                """,
                (vid, category, search_query),
            )
            problem = best_matching_problem(v.get("title"), problems) or category
            conn.execute(
                """
                UPDATE videos SET
                    matched_keyword = COALESCE(matched_keyword, ?),
                    problem_category = COALESCE(problem_category, ?),
                    is_search_result = 1
                WHERE video_id = ?
                """,
                (search_query, problem, vid),
            )


def run_category_search(
    db_path: Path,
    keyword_pool_path: Path,
    yt: YouTubeClient,
    category: str,
    *,
    max_results_per_query: int = 15,
    cache_ttl_hours: int = 168,
    region_code: str = "KR",
    relevance_language: str = "ko",
    query_limit: int | None = None,
    short_max_seconds: int = 60,
    ambiguous_max_seconds: int = 180,
) -> dict:
    pool = load_pool(keyword_pool_path)
    keywords: list[Keyword] = keywords_for_category(pool, category)
    if query_limit is not None:
        keywords = keywords[:query_limit]

    all_new_video_ids: set[str] = set()
    queries_run = 0
    category_problems = (pool.get(category) or {}).get("problems") or []

    for kw in keywords:
        if _is_cached(db_path, kw.category, kw.search_query, cache_ttl_hours):
            continue
        video_ids = yt.search_videos(
            kw.search_query,
            max_results=max_results_per_query,
            region_code=region_code,
            relevance_language=relevance_language,
        )
        queries_run += 1
        _mark_cached(db_path, kw.category, kw.search_query, len(video_ids))

        if video_ids:
            items = yt.get_videos(video_ids)
            normalized = [normalize_video(i, short_max_seconds, ambiguous_max_seconds) for i in items]
            upsert_videos(db_path, normalized)
            _record_matches(db_path, normalized, kw.category, kw.search_query, category_problems)
            all_new_video_ids.update(v["video_id"] for v in normalized)

    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO search_runs (category, keyword_count, new_video_count, api_units_used) VALUES (?, ?, ?, ?)",
            (category, len(keywords), len(all_new_video_ids), queries_run * 100),
        )

    return {
        "category": category,
        "keywords_total": len(keywords),
        "queries_run": queries_run,
        "queries_cached": len(keywords) - queries_run,
        "new_video_count": len(all_new_video_ids),
    }
