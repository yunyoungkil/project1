"""Combines my-channel YouTube Analytics performance with market outlier data to produce
market_demand_score / my_channel_fit_score / content_opportunity_score per problem_category.

If no OAuth token exists yet (`research auth` hasn't been run), my-channel data is simply
unavailable and my_channel_fit_score falls back to a neutral value with `fit_data_available=False`
-- the rest of the pipeline (market-only ranking) still works.
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from pathlib import Path

from research.analytics_client import AnalyticsClient, load_credentials
from research.db import connect
from research.keyword_pool import load_pool
from research.youtube_client import YouTubeClient

logger = logging.getLogger(__name__)


def sync_my_channel_stats(
    db_path: Path,
    client_id: str | None,
    client_secret: str | None,
    token_path: Path,
    yt: YouTubeClient,
    lookback_days: int = 90,
    traffic_source_top_n: int = 20,
) -> dict:
    if not client_id or not client_secret:
        return {"available": False, "reason": "missing_oauth_client"}

    try:
        creds = load_credentials(client_id, client_secret, token_path)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to load/refresh OAuth credentials")
        return {"available": False, "reason": "credential_error"}

    if creds is None:
        return {"available": False, "reason": "not_authorized"}

    analytics = AnalyticsClient(creds)
    channel_id = analytics.get_my_channel_id()
    if not channel_id:
        return {"available": False, "reason": "no_channel"}

    end_date = date.today()
    start_date = end_date - timedelta(days=lookback_days)
    records = analytics.get_video_performance(channel_id, start_date.isoformat(), end_date.isoformat())
    if not records:
        return {"available": True, "channel_id": channel_id, "video_count": 0}

    video_ids = [r["video_id"] for r in records if r.get("video_id")]
    titles = {}
    for item in yt.get_videos(video_ids):
        titles[item.get("id")] = (item.get("snippet") or {}).get("title")

    # get_video_performance already sorts by -views, so the first N are the top performers.
    # Traffic source needs one Analytics query per video, so we cap it instead of doing it for
    # every video the channel has ever posted.
    traffic_sources: dict[str, str | None] = {}
    for r in records[:traffic_source_top_n]:
        traffic_sources[r["video_id"]] = analytics.get_top_traffic_source(
            channel_id, r["video_id"], start_date.isoformat(), end_date.isoformat()
        )

    with connect(db_path) as conn:
        for r in records:
            conn.execute(
                """
                INSERT INTO my_channel_video_stats (video_id, title, period_start, period_end,
                    views, ctr, average_view_duration, average_percentage_viewed,
                    watch_time_minutes, subscriber_gain, impressions, top_traffic_source, fetched_at)
                VALUES (:video_id, :title, :period_start, :period_end, :views, :ctr,
                    :average_view_duration, :average_percentage_viewed, :watch_time_minutes,
                    :subscriber_gain, :impressions, :top_traffic_source, datetime('now'))
                ON CONFLICT(video_id) DO UPDATE SET
                    title=excluded.title, period_start=excluded.period_start,
                    period_end=excluded.period_end, views=excluded.views, ctr=excluded.ctr,
                    average_view_duration=excluded.average_view_duration,
                    average_percentage_viewed=excluded.average_percentage_viewed,
                    watch_time_minutes=excluded.watch_time_minutes,
                    subscriber_gain=excluded.subscriber_gain, impressions=excluded.impressions,
                    top_traffic_source=excluded.top_traffic_source,
                    fetched_at=excluded.fetched_at
                """,
                {
                    "video_id": r["video_id"],
                    "title": titles.get(r["video_id"]),
                    "period_start": start_date.isoformat(),
                    "period_end": end_date.isoformat(),
                    "views": r.get("views"),
                    "ctr": r.get("ctr"),
                    "average_view_duration": r.get("average_view_duration"),
                    "average_percentage_viewed": r.get("average_percentage_viewed"),
                    "watch_time_minutes": r.get("watch_time_minutes"),
                    "subscriber_gain": r.get("subscriber_gain"),
                    "impressions": r.get("impressions"),
                    "top_traffic_source": traffic_sources.get(r["video_id"]),
                },
            )

    return {"available": True, "channel_id": channel_id, "video_count": len(records)}


def _matches_category(title: str, queries: list[str], problems: list[str]) -> bool:
    title_lower = (title or "").lower()
    for term in queries + problems:
        # crude but dependency-free relevance check: any keyword-pool term whose distinct
        # words mostly appear in the title counts as a match.
        words = [w for w in term.lower().split() if len(w) > 1]
        if words and sum(1 for w in words if w in title_lower) >= max(1, len(words) - 1):
            return True
    return False


def compute_topic_scores(
    db_path: Path,
    keyword_pool_path: Path,
    *,
    market_demand_top_n: int = 5,
    market_demand_weights: dict | None = None,
    outlier_count_cap: int = 10,
    fit_neutral_score: float = 50.0,
) -> list[dict]:
    market_demand_weights = market_demand_weights or {"avg_opportunity": 0.7, "outlier_count": 0.3}
    pool = load_pool(keyword_pool_path)

    with connect(db_path) as conn:
        my_videos = [dict(r) for r in conn.execute("SELECT * FROM my_channel_video_stats").fetchall()]

    overall_pct_viewed = _avg([v["average_percentage_viewed"] for v in my_videos if v.get("average_percentage_viewed") is not None])

    results = []
    for category, body in pool.items():
        queries = body.get("search_queries") or []
        problems = body.get("problems") or []

        with connect(db_path) as conn:
            rows = conn.execute(
                """
                SELECT os.opportunity_score, os.outlier_grade
                FROM outlier_scores os
                JOIN videos v ON v.video_id = os.video_id
                WHERE v.problem_category = ? OR v.matched_keyword IN (
                    SELECT search_query FROM keywords WHERE category = ?
                )
                ORDER BY os.opportunity_score DESC
                """,
                (problems[0] if problems else category, category),
            ).fetchall()

        scores = [r["opportunity_score"] for r in rows if r["opportunity_score"] is not None]
        outlier_count = sum(1 for r in rows if r["outlier_grade"] and r["outlier_grade"] != "normal")
        top_scores = scores[:market_demand_top_n]
        avg_opportunity = _avg(top_scores) or 0.0
        market_demand_score = min(
            100.0,
            market_demand_weights["avg_opportunity"] * avg_opportunity
            + market_demand_weights["outlier_count"] * min(100.0, (outlier_count / outlier_count_cap) * 100),
        )

        matched_my_videos = [v for v in my_videos if _matches_category(v.get("title") or "", queries, problems)]
        # CTR/impressions aren't available from the YouTube Analytics API (see analytics_client.py),
        # so fit is based on retention (average_percentage_viewed) alone -- the only reliable
        # per-video performance signal we can actually fetch.
        fit_data_available = bool(matched_my_videos) and bool(overall_pct_viewed)
        if fit_data_available:
            my_pct = _avg([v["average_percentage_viewed"] for v in matched_my_videos if v.get("average_percentage_viewed") is not None]) or 0
            pct_ratio = (my_pct / overall_pct_viewed) if overall_pct_viewed else 1
            my_channel_fit_score = max(0.0, min(100.0, 50 * pct_ratio))
        else:
            my_channel_fit_score = fit_neutral_score

        content_opportunity_score = market_demand_score * (my_channel_fit_score / 100.0)

        evidence = {
            "outlier_video_count": outlier_count,
            "top_opportunity_scores": top_scores,
            "matched_my_video_count": len(matched_my_videos),
        }

        with connect(db_path) as conn:
            conn.execute(
                """
                INSERT INTO topic_opportunities (problem_category, market_demand_score,
                    my_channel_fit_score, fit_data_available, content_opportunity_score,
                    outlier_video_count, evidence_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    category,
                    market_demand_score,
                    my_channel_fit_score,
                    1 if fit_data_available else 0,
                    content_opportunity_score,
                    outlier_count,
                    json.dumps(evidence, ensure_ascii=False),
                ),
            )

        results.append(
            {
                "category": category,
                "market_demand_score": market_demand_score,
                "my_channel_fit_score": my_channel_fit_score,
                "fit_data_available": fit_data_available,
                "content_opportunity_score": content_opportunity_score,
                "outlier_video_count": outlier_count,
            }
        )

    return sorted(results, key=lambda r: r["content_opportunity_score"], reverse=True)


def _avg(values: list[float]) -> float | None:
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None
