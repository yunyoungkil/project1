"""Parses raw YouTube API video/channel payloads into normalized rows and classifies content_type."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from research.db import connect

_ISO8601_DURATION_RE = re.compile(
    r"P(?:(?P<days>\d+)D)?T?(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?"
)


def parse_iso8601_duration(value: str | None) -> int | None:
    """Parses an ISO 8601 duration string (e.g. 'PT1M30S') into whole seconds."""
    if not value:
        return None
    match = _ISO8601_DURATION_RE.fullmatch(value)
    if not match:
        return None
    parts = match.groupdict()
    days = int(parts["days"] or 0)
    hours = int(parts["hours"] or 0)
    minutes = int(parts["minutes"] or 0)
    seconds = int(parts["seconds"] or 0)
    total = days * 86400 + hours * 3600 + minutes * 60 + seconds
    return total


def classify_content_type(duration_seconds: int | None, short_max: int, ambiguous_max: int) -> str:
    """Classifies a video as short/longform/unknown. See README for the known limitation:
    Shorts can now run up to `ambiguous_max` seconds, so mid-length videos can't be reliably
    classified from duration alone.
    """
    if duration_seconds is None:
        return "unknown"
    if duration_seconds <= short_max:
        return "short"
    if duration_seconds <= ambiguous_max:
        return "unknown"
    return "longform"


def normalize_video(item: dict[str, Any], short_max: int, ambiguous_max: int) -> dict[str, Any]:
    snippet = item.get("snippet", {}) or {}
    stats = item.get("statistics", {}) or {}
    content_details = item.get("contentDetails", {}) or {}
    duration_seconds = parse_iso8601_duration(content_details.get("duration"))
    is_live = bool(item.get("liveStreamingDetails")) or snippet.get("liveBroadcastContent") in (
        "live",
        "upcoming",
    )

    def _int_or_none(v: Any) -> int | None:
        return int(v) if v is not None else None

    return {
        "video_id": item.get("id"),
        "channel_id": snippet.get("channelId"),
        "title": snippet.get("title"),
        "description": snippet.get("description"),
        "published_at": snippet.get("publishedAt"),
        "thumbnail_url": (snippet.get("thumbnails", {}).get("high") or snippet.get("thumbnails", {}).get("default") or {}).get("url"),
        "duration_seconds": duration_seconds,
        "content_type": classify_content_type(duration_seconds, short_max, ambiguous_max),
        "is_live": 1 if is_live else 0,
        "view_count": _int_or_none(stats.get("viewCount")),
        "like_count": _int_or_none(stats.get("likeCount")),
        "comment_count": _int_or_none(stats.get("commentCount")),
        "likes_hidden": 0 if "likeCount" in stats else 1,
        "comments_disabled": 0 if "commentCount" in stats else 1,
    }


def normalize_channel(item: dict[str, Any]) -> dict[str, Any]:
    snippet = item.get("snippet", {}) or {}
    stats = item.get("statistics", {}) or {}
    content_details = item.get("contentDetails", {}) or {}
    hidden = bool(stats.get("hiddenSubscriberCount"))
    sub_count = stats.get("subscriberCount")
    return {
        "channel_id": item.get("id"),
        "title": snippet.get("title"),
        "subscriber_count": None if hidden or sub_count is None else int(sub_count),
        "subscriber_hidden": 1 if hidden else 0,
        "video_count": int(stats["videoCount"]) if stats.get("videoCount") is not None else None,
        "view_count": int(stats["viewCount"]) if stats.get("viewCount") is not None else None,
        "uploads_playlist_id": content_details.get("relatedPlaylists", {}).get("uploads"),
    }


def upsert_channels(db_path: Path, channels: list[dict[str, Any]]) -> None:
    with connect(db_path) as conn:
        for c in channels:
            conn.execute(
                """
                INSERT INTO channels (channel_id, title, subscriber_count, subscriber_hidden,
                    video_count, view_count, uploads_playlist_id, last_updated_at)
                VALUES (:channel_id, :title, :subscriber_count, :subscriber_hidden,
                    :video_count, :view_count, :uploads_playlist_id, datetime('now'))
                ON CONFLICT(channel_id) DO UPDATE SET
                    title=excluded.title,
                    subscriber_count=excluded.subscriber_count,
                    subscriber_hidden=excluded.subscriber_hidden,
                    video_count=excluded.video_count,
                    view_count=excluded.view_count,
                    uploads_playlist_id=excluded.uploads_playlist_id,
                    last_updated_at=excluded.last_updated_at
                """,
                c,
            )


def upsert_videos(db_path: Path, videos: list[dict[str, Any]]) -> None:
    with connect(db_path) as conn:
        for v in videos:
            conn.execute(
                """
                INSERT INTO videos (video_id, channel_id, title, description, published_at,
                    thumbnail_url, duration_seconds, content_type, is_live, view_count, like_count,
                    comment_count, likes_hidden, comments_disabled, last_updated_at)
                VALUES (:video_id, :channel_id, :title, :description, :published_at,
                    :thumbnail_url, :duration_seconds, :content_type, :is_live, :view_count, :like_count,
                    :comment_count, :likes_hidden, :comments_disabled, datetime('now'))
                ON CONFLICT(video_id) DO UPDATE SET
                    title=excluded.title,
                    description=excluded.description,
                    duration_seconds=excluded.duration_seconds,
                    content_type=excluded.content_type,
                    is_live=excluded.is_live,
                    view_count=excluded.view_count,
                    like_count=excluded.like_count,
                    comment_count=excluded.comment_count,
                    likes_hidden=excluded.likes_hidden,
                    comments_disabled=excluded.comments_disabled,
                    last_updated_at=excluded.last_updated_at
                """,
                v,
            )
            if v.get("view_count") is not None:
                # Keep a point-in-time history so view growth can be reconstructed later, per the
                # spec's optional "시간에 따른 조회수 변화는 snapshot 형태로 보존" requirement.
                conn.execute(
                    """
                    INSERT INTO video_metrics_snapshots (video_id, view_count, like_count, comment_count)
                    VALUES (:video_id, :view_count, :like_count, :comment_count)
                    """,
                    v,
                )
