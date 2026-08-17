from research.outlier_detector import (
    baseline_confidence,
    comment_rate,
    like_rate,
    meets_min_grade,
    outlier_grade,
    outlier_ratio,
    subscriber_ratio,
    views_per_day,
)


def test_subscriber_ratio_normal():
    assert subscriber_ratio(1000, 100) == 10.0


def test_subscriber_ratio_hidden_or_zero_is_none():
    assert subscriber_ratio(1000, None) is None
    assert subscriber_ratio(1000, 0) is None


def test_subscriber_ratio_missing_views_is_none():
    assert subscriber_ratio(None, 100) is None


def test_outlier_ratio_normal():
    assert outlier_ratio(100000, 2500) == 40.0


def test_outlier_ratio_zero_baseline_is_none():
    assert outlier_ratio(1000, 0) is None
    assert outlier_ratio(1000, None) is None


def test_views_per_day_min_one_day():
    from datetime import datetime, timezone

    now = datetime(2026, 1, 10, tzinfo=timezone.utc)
    published_today = now.isoformat().replace("+00:00", "Z")
    assert views_per_day(500, published_today, now=now) == 500.0


def test_views_per_day_older_video():
    from datetime import datetime, timezone

    now = datetime(2026, 1, 11, tzinfo=timezone.utc)
    published = "2026-01-01T00:00:00Z"
    result = views_per_day(1000, published, now=now)
    assert round(result, 2) == round(1000 / 10, 2)


def test_views_per_day_missing_inputs():
    assert views_per_day(None, "2026-01-01T00:00:00Z") is None
    assert views_per_day(1000, None) is None


def test_like_rate_hidden():
    assert like_rate(100, 1000, likes_hidden=True) is None


def test_like_rate_zero_views():
    assert like_rate(10, 0) is None


def test_like_rate_normal():
    assert like_rate(50, 1000) == 0.05


def test_comment_rate_disabled():
    assert comment_rate(10, 1000, comments_disabled=True) is None


def test_comment_rate_normal():
    assert comment_rate(5, 1000) == 0.005


def test_baseline_confidence_levels():
    assert baseline_confidence(20, 5) == "high"
    assert baseline_confidence(10, 5) == "medium"
    assert baseline_confidence(2, 5) == "low"
    assert baseline_confidence(0, 5) == "none"


def test_outlier_grade_thresholds():
    assert outlier_grade(1.5) == "normal"
    assert outlier_grade(2.0) == "notable"
    assert outlier_grade(4.9) == "notable"
    assert outlier_grade(5.0) == "strong"
    assert outlier_grade(10.0) == "very_strong"
    assert outlier_grade(20.0) == "exceptional"
    assert outlier_grade(None) is None


def test_meets_min_grade_none_never_meets_threshold():
    assert meets_min_grade(None, "notable") is False


def test_meets_min_grade_exact_match():
    assert meets_min_grade("notable", "notable") is True


def test_meets_min_grade_above_threshold():
    assert meets_min_grade("exceptional", "notable") is True


def test_meets_min_grade_below_threshold():
    assert meets_min_grade("normal", "notable") is False


def test_meets_min_grade_unknown_grade_fails_open():
    assert meets_min_grade("something_new", "notable") is True
