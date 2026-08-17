"""Glues together channel_baseline + outlier_detector + opportunity_score for every video
collected by youtube_search, and writes the results to outlier_scores."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from research.channel_baseline import compute_channel_baseline, has_fresh_baseline
from research.db import connect
from research.opportunity_score import OpportunityInputs, compute_opportunity_score
from research.outlier_detector import (
    comment_rate,
    like_rate,
    meets_min_grade,
    outlier_grade,
    outlier_ratio,
    subscriber_ratio,
    views_per_day,
)
from research.youtube_client import YouTubeClient

logger = logging.getLogger(__name__)


def _fetch_pending_videos(db_path: Path) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT v.*, c.subscriber_count, c.subscriber_hidden
            FROM videos v
            LEFT JOIN channels c ON c.channel_id = v.channel_id
            WHERE v.is_search_result = 1 AND v.is_live = 0
            """
        ).fetchall()
    return [dict(r) for r in rows]


def _matched_keyword_count(db_path: Path, video_id: str) -> int:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM video_keyword_matches WHERE video_id = ?", (video_id,)
        ).fetchone()
    return row["n"] if row else 1


def estimate_analyze_units(db_path: Path, cache_ttl_hours: int = 168) -> int:
    """Estimates the quota `research analyze` will spend, before running it. Counts only
    (channel, content_type) pairs that don't already have a fresh cached baseline; each such
    channel costs ~3 units (channels.list + playlistItems.list + one videos.list batch)."""
    videos = _fetch_pending_videos(db_path)
    pairs = {(v["channel_id"], v["content_type"]) for v in videos if v["content_type"] != "unknown"}
    uncached = sum(0 if has_fresh_baseline(db_path, cid, ct, cache_ttl_hours) else 1 for cid, ct in pairs)
    return uncached * 3


def analyze_pending_videos(
    db_path: Path,
    yt: YouTubeClient,
    *,
    baseline_cfg: dict,
    content_type_cfg: dict,
    grade_thresholds: dict,
    score_weights: dict,
    score_caps: dict,
    neutral_score: float = 50.0,
    min_grade_to_store: str = "notable",
    on_progress: Callable[[int, int], None] | None = None,
) -> dict:
    videos = _fetch_pending_videos(db_path)
    total = len(videos)
    processed = 0
    skipped_unknown_type = 0
    skipped_no_baseline = 0
    skipped_below_threshold = 0

    for i, v in enumerate(videos, start=1):
        if on_progress:
            on_progress(i, total)

        if v["content_type"] == "unknown":
            skipped_unknown_type += 1
            continue

        try:
            baseline = compute_channel_baseline(
                db_path,
                yt,
                v["channel_id"],
                v["content_type"],
                exclude_video_id=v["video_id"],
                sample_size=baseline_cfg.get("sample_size", 30),
                min_sample_size=baseline_cfg.get("min_sample_size", 5),
                max_age_days=baseline_cfg.get("max_age_days"),
                exclude_live=baseline_cfg.get("exclude_live", True),
                short_max_seconds=content_type_cfg.get("short_max_seconds", 60),
                ambiguous_max_seconds=content_type_cfg.get("ambiguous_max_seconds", 180),
                cache_ttl_hours=baseline_cfg.get("cache_ttl_hours", 168),
            )
        except Exception:  # noqa: BLE001 - one bad channel must not kill the whole batch
            logger.exception("Baseline computation failed for channel=%s", v["channel_id"])
            baseline = None

        median_views = baseline.get("median_views") if baseline else None
        mean_views = baseline.get("mean_views") if baseline else None
        confidence = baseline.get("confidence") if baseline else "none"
        if median_views is None:
            skipped_no_baseline += 1

        sub_count = None if v.get("subscriber_hidden") else v.get("subscriber_count")
        subs_ratio = subscriber_ratio(v["view_count"], sub_count)
        ratio = outlier_ratio(v["view_count"], median_views)
        vpd = views_per_day(v["view_count"], v["published_at"])
        lr = like_rate(v["like_count"], v["view_count"], bool(v["likes_hidden"]))
        cr = comment_rate(v["comment_count"], v["view_count"], bool(v["comments_disabled"]))
        grade = outlier_grade(ratio, grade_thresholds)

        score = compute_opportunity_score(
            OpportunityInputs(
                outlier_ratio=ratio,
                views_per_day=vpd,
                subscriber_ratio=subs_ratio,
                like_rate=lr,
                comment_rate=cr,
                matched_keyword_count=_matched_keyword_count(db_path, v["video_id"]),
            ),
            weights=score_weights,
            caps=score_caps,
            neutral_score=neutral_score,
        )

        if not meets_min_grade(grade, min_grade_to_store):
            # Below the interesting-enough threshold (e.g. "normal", <2x) -- don't keep it around.
            # Delete any previously-stored row too, in case a re-analyze demoted this video.
            with connect(db_path) as conn:
                conn.execute("DELETE FROM outlier_scores WHERE video_id = ?", (v["video_id"],))
            skipped_below_threshold += 1
            continue

        with connect(db_path) as conn:
            conn.execute(
                """
                INSERT INTO outlier_scores (video_id, channel_median_views, channel_mean_views,
                    baseline_confidence, subscriber_ratio, outlier_ratio, views_per_day,
                    like_rate, comment_rate, outlier_grade, opportunity_score)
                VALUES (:video_id, :median_views, :mean_views, :confidence, :subs_ratio, :ratio,
                    :vpd, :lr, :cr, :grade, :score)
                ON CONFLICT(video_id) DO UPDATE SET
                    computed_at = datetime('now'),
                    channel_median_views = excluded.channel_median_views,
                    channel_mean_views = excluded.channel_mean_views,
                    baseline_confidence = excluded.baseline_confidence,
                    subscriber_ratio = excluded.subscriber_ratio,
                    outlier_ratio = excluded.outlier_ratio,
                    views_per_day = excluded.views_per_day,
                    like_rate = excluded.like_rate,
                    comment_rate = excluded.comment_rate,
                    outlier_grade = excluded.outlier_grade,
                    opportunity_score = excluded.opportunity_score
                """,
                {
                    "video_id": v["video_id"],
                    "median_views": median_views,
                    "mean_views": mean_views,
                    "confidence": confidence,
                    "subs_ratio": subs_ratio,
                    "ratio": ratio,
                    "vpd": vpd,
                    "lr": lr,
                    "cr": cr,
                    "grade": grade,
                    "score": score,
                },
            )
        processed += 1

    return {
        "total_candidates": len(videos),
        "processed": processed,
        "skipped_unknown_type": skipped_unknown_type,
        "skipped_no_baseline": skipped_no_baseline,
        "skipped_below_threshold": skipped_below_threshold,
    }
