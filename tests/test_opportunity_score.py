from research.opportunity_score import OpportunityInputs, compute_opportunity_score


def test_full_outlier_scores_high():
    inputs = OpportunityInputs(
        outlier_ratio=50,
        views_per_day=5000,
        subscriber_ratio=5,
        like_rate=0.08,
        comment_rate=0.01,
        matched_keyword_count=1,
    )
    score = compute_opportunity_score(inputs)
    assert 95 <= score <= 100


def test_no_outlier_data_scores_low_on_outlier_component():
    inputs = OpportunityInputs(
        outlier_ratio=None,
        views_per_day=None,
        subscriber_ratio=None,
        like_rate=None,
        comment_rate=None,
    )
    score = compute_opportunity_score(inputs)
    # outlier_strength (40% weight) is 0, everything else neutral (50) or relevance (85 base)
    expected = 0.4 * 0 + 0.2 * 50 + 0.1 * 50 + 0.1 * 50 + 0.2 * 85
    assert round(score, 2) == round(expected, 2)


def test_score_is_clamped_between_0_and_100():
    inputs = OpportunityInputs(
        outlier_ratio=100000,
        views_per_day=1_000_000,
        subscriber_ratio=1000,
        like_rate=1.0,
        comment_rate=1.0,
        matched_keyword_count=50,
    )
    score = compute_opportunity_score(inputs)
    assert 0 <= score <= 100


def test_multiple_keyword_matches_increase_relevance():
    base = OpportunityInputs(
        outlier_ratio=10, views_per_day=100, subscriber_ratio=1, like_rate=0.02,
        comment_rate=0.002, matched_keyword_count=1,
    )
    more_matches = OpportunityInputs(
        outlier_ratio=10, views_per_day=100, subscriber_ratio=1, like_rate=0.02,
        comment_rate=0.002, matched_keyword_count=5,
    )
    assert compute_opportunity_score(more_matches) > compute_opportunity_score(base)


def test_zero_outlier_ratio_does_not_crash():
    inputs = OpportunityInputs(
        outlier_ratio=0, views_per_day=0, subscriber_ratio=0, like_rate=0, comment_rate=0
    )
    score = compute_opportunity_score(inputs)
    assert score >= 0
