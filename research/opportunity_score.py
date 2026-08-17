"""Video-level opportunity_score: a log-normalized weighted sum of outlier strength, view
velocity, subscriber advantage, engagement, and keyword relevance. Log normalization + caps keep
one extreme metric (e.g. a 500x outlier) from swamping the whole score."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

DEFAULT_WEIGHTS = {
    "outlier_strength": 0.4,
    "views_velocity": 0.2,
    "subscriber_ratio": 0.1,
    "engagement": 0.1,
    "relevance": 0.2,
}

DEFAULT_CAPS = {
    "outlier_ratio_cap": 50,
    "views_per_day_cap": 5000,
    "subscriber_ratio_cap": 5,
    "like_rate_cap": 0.08,
    "comment_rate_cap": 0.01,
}

NEUTRAL_SCORE = 50.0


def _log_normalize(value: float, cap: float) -> float:
    """Maps value in [0, inf) to a [0, 100] score with diminishing returns; value>=cap -> 100."""
    if value <= 0:
        return 0.0
    score = 100 * math.log1p(value) / math.log1p(cap)
    return max(0.0, min(100.0, score))


@dataclass
class OpportunityInputs:
    outlier_ratio: Optional[float]
    views_per_day: Optional[float]
    subscriber_ratio: Optional[float]
    like_rate: Optional[float]
    comment_rate: Optional[float]
    matched_keyword_count: int = 1


def compute_opportunity_score(
    inputs: OpportunityInputs,
    weights: dict[str, float] = DEFAULT_WEIGHTS,
    caps: dict[str, float] = DEFAULT_CAPS,
    neutral_score: float = NEUTRAL_SCORE,
) -> float:
    if inputs.outlier_ratio is None:
        outlier_component = 0.0
    else:
        outlier_component = _log_normalize(inputs.outlier_ratio, caps["outlier_ratio_cap"])

    if inputs.views_per_day is None:
        velocity_component = neutral_score
    else:
        velocity_component = _log_normalize(inputs.views_per_day, caps["views_per_day_cap"])

    if inputs.subscriber_ratio is None:
        subscriber_component = neutral_score
    else:
        subscriber_component = _log_normalize(inputs.subscriber_ratio, caps["subscriber_ratio_cap"])

    engagement_parts = []
    if inputs.like_rate is not None:
        engagement_parts.append(_log_normalize(inputs.like_rate, caps["like_rate_cap"]))
    if inputs.comment_rate is not None:
        engagement_parts.append(_log_normalize(inputs.comment_rate, caps["comment_rate_cap"]))
    engagement_component = sum(engagement_parts) / len(engagement_parts) if engagement_parts else neutral_score

    # A video matched by more than one category keyword is more clearly "on topic".
    relevance_component = min(100.0, 85.0 + (max(0, inputs.matched_keyword_count - 1) * 5))

    score = (
        weights["outlier_strength"] * outlier_component
        + weights["views_velocity"] * velocity_component
        + weights["subscriber_ratio"] * subscriber_component
        + weights["engagement"] * engagement_component
        + weights["relevance"] * relevance_component
    )
    return max(0.0, min(100.0, score))
