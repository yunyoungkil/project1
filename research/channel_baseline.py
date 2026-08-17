"""Computes a channel's 'normal' view count (median/mean) per content_type from its recent uploads.

Uses the channel's uploads playlist (playlistItems.list, 1 quota unit) instead of search.list
(100 units) to fetch recent video ids -- this is the main quota-saving trick for baselines.
"""
from __future__ import annotations

import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from research.db import connect
from research.video_stats import normalize_channel, normalize_video, upsert_channels, upsert_videos
from research.youtube_client import YouTubeClient


def _confidence(sample_size: int, min_sample_size: int) -> str:
    if sample_size >= 15:
        return "high"
    if sample_size >= min_sample_size:
        return "medium"
    return "low"


def _get_cached_baseline(db_path: Path, channel_id: str, content_type: str, ttl_hours: int) -> dict[str, Any] | None:
    """Returns a still-fresh baseline for (channel_id, content_type) if one was computed within
    ttl_hours, so `research analyze` doesn't re-fetch a channel's uploads on every run -- this is
    the 'reuse already-collected channel baselines' quota saving from the spec."""
    with connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT * FROM channel_baselines
            WHERE channel_id = ? AND content_type = ?
              AND computed_at > datetime('now', ?)
            """,
            (channel_id, content_type, f"-{ttl_hours} hours"),
        ).fetchone()
    return dict(row) if row else None


def has_fresh_baseline(db_path: Path, channel_id: str, content_type: str, ttl_hours: int) -> bool:
    """Public helper for quota estimation: would compute_channel_baseline reuse a cached result?"""
    return _get_cached_baseline(db_path, channel_id, content_type, ttl_hours) is not None


def _get_or_fetch_channel(db_path: Path, yt: YouTubeClient, channel_id: str) -> dict[str, Any] | None:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM channels WHERE channel_id = ? AND uploads_playlist_id IS NOT NULL", (channel_id,)
        ).fetchone()
        if row:
            return dict(row)
    items = yt.get_channels([channel_id])
    if not items:
        return None
    normalized = [normalize_channel(i) for i in items]
    upsert_channels(db_path, normalized)
    return normalized[0]


def compute_channel_baseline(
    db_path: Path,
    yt: YouTubeClient,
    channel_id: str,
    content_type: str,
    exclude_video_id: str,
    *,
    sample_size: int = 30,
    min_sample_size: int = 5,
    max_age_days: int | None = 730,
    exclude_live: bool = True,
    short_max_seconds: int = 60,
    ambiguous_max_seconds: int = 180,
    cache_ttl_hours: int = 168,
) -> dict[str, Any] | None:
    """Fetches the channel's recent uploads, filters to the same content_type, and stores
    median/mean baseline views. Returns the stored baseline row (or None if the channel couldn't
    be resolved). Reuses a still-fresh baseline (within cache_ttl_hours) instead of re-fetching."""
    if content_type == "unknown":
        # Unknown-duration videos are never mixed into a baseline -- there's nothing reliable
        # to compare them against.
        return None

    cached = _get_cached_baseline(db_path, channel_id, content_type, cache_ttl_hours)
    if cached is not None:
        return cached

    channel = _get_or_fetch_channel(db_path, yt, channel_id)
    if not channel or not channel.get("uploads_playlist_id"):
        return None

    # Pull extra candidates since some will be filtered out (live, wrong content_type, too old).
    candidate_ids = yt.get_playlist_video_ids(channel["uploads_playlist_id"], max_items=sample_size * 3)
    candidate_ids = [v for v in candidate_ids if v != exclude_video_id]
    if not candidate_ids:
        return _store_baseline(db_path, channel_id, content_type, [], min_sample_size)

    items = yt.get_videos(candidate_ids)
    normalized = [normalize_video(i, short_max_seconds, ambiguous_max_seconds) for i in items]
    upsert_videos(db_path, normalized)

    cutoff = None
    if max_age_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)

    views: list[int] = []
    for v in normalized:
        if v["content_type"] != content_type:
            continue
        if exclude_live and v["is_live"]:
            continue
        if v["view_count"] is None:
            continue
        if cutoff is not None and v.get("published_at"):
            try:
                published = datetime.fromisoformat(v["published_at"].replace("Z", "+00:00"))
                if published < cutoff:
                    continue
            except ValueError:
                pass
        views.append(v["view_count"])
        if len(views) >= sample_size:
            break

    return _store_baseline(db_path, channel_id, content_type, views, min_sample_size)


def _store_baseline(
    db_path: Path, channel_id: str, content_type: str, views: list[int], min_sample_size: int
) -> dict[str, Any]:
    sample_size = len(views)
    median_views = statistics.median(views) if views else None
    mean_views = statistics.mean(views) if views else None
    confidence = _confidence(sample_size, min_sample_size) if sample_size > 0 else "none"

    row = {
        "channel_id": channel_id,
        "content_type": content_type,
        "sample_size": sample_size,
        "median_views": median_views,
        "mean_views": mean_views,
        "confidence": confidence,
    }
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO channel_baselines (channel_id, content_type, sample_size, median_views, mean_views, confidence)
            VALUES (:channel_id, :content_type, :sample_size, :median_views, :mean_views, :confidence)
            ON CONFLICT(channel_id, content_type) DO UPDATE SET
                computed_at = datetime('now'),
                sample_size = excluded.sample_size,
                median_views = excluded.median_views,
                mean_views = excluded.mean_views,
                confidence = excluded.confidence
            """,
            row,
        )
    return row
