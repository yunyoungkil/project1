"""Pure calculation functions for the core per-video metrics. No API/DB access here so they're
trivially unit-testable."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


def subscriber_ratio(view_count: Optional[int], subscriber_count: Optional[int]) -> Optional[float]:
    """view_count / subscriber_count. None if subscriber_count is hidden/0/missing."""
    if view_count is None or not subscriber_count:
        return None
    return view_count / subscriber_count


def outlier_ratio(view_count: Optional[int], channel_median_views: Optional[float]) -> Optional[float]:
    """view_count / channel_median_views. None if no reliable baseline exists."""
    if view_count is None or not channel_median_views:
        return None
    return view_count / channel_median_views


def views_per_day(view_count: Optional[int], published_at: Optional[str], now: Optional[datetime] = None) -> Optional[float]:
    if view_count is None or not published_at:
        return None
    now = now or datetime.now(timezone.utc)
    try:
        published = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    age_days = max(1.0, (now - published).total_seconds() / 86400)
    return view_count / age_days


def like_rate(like_count: Optional[int], view_count: Optional[int], likes_hidden: bool = False) -> Optional[float]:
    if likes_hidden or like_count is None or not view_count:
        return None
    return like_count / view_count


def comment_rate(comment_count: Optional[int], view_count: Optional[int], comments_disabled: bool = False) -> Optional[float]:
    if comments_disabled or comment_count is None or not view_count:
        return None
    return comment_count / view_count


def baseline_confidence(sample_size: int, min_sample_size: int) -> str:
    if sample_size >= 15:
        return "high"
    if sample_size >= min_sample_size:
        return "medium"
    if sample_size > 0:
        return "low"
    return "none"


DEFAULT_GRADE_THRESHOLDS = {
    "notable": 2,
    "strong": 5,
    "very_strong": 10,
    "exceptional": 20,
}


def outlier_grade(ratio: Optional[float], thresholds: dict[str, float] = DEFAULT_GRADE_THRESHOLDS) -> Optional[str]:
    if ratio is None:
        return None
    if ratio >= thresholds["exceptional"]:
        return "exceptional"
    if ratio >= thresholds["very_strong"]:
        return "very_strong"
    if ratio >= thresholds["strong"]:
        return "strong"
    if ratio >= thresholds["notable"]:
        return "notable"
    return "normal"
