from pathlib import Path

import yaml

from research.db import connect, init_db
from research.my_channel import _matches_category, compute_topic_scores


def test_matches_category_word_overlap():
    assert _matches_category("영어 단어 읽는 법 총정리", ["영어 단어 읽기"], []) is True


def test_matches_category_no_overlap():
    assert _matches_category("오늘의 브이로그", ["영어 단어 읽기"], []) is False


def test_matches_category_empty_title():
    assert _matches_category("", ["영어 단어 읽기"], []) is False


def _write_pool(tmp_path: Path) -> Path:
    pool = {
        "reading": {
            "problems": [
                {"id": "cannot_read_words", "label": "읽기 문제", "search_queries": ["영어 읽기 원리"]},
            ]
        },
        "listening": {
            "problems": [
                {"id": "liaison", "label": "듣기 문제", "search_queries": ["영어 듣기 연음"]},
            ]
        },
    }
    path = tmp_path / "keyword_pool.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(pool, f, allow_unicode=True)
    return path


def _seed_video(conn, video_id, channel_id, title, category, problem_id, problem_label, search_query):
    conn.execute(
        """
        INSERT INTO videos (video_id, channel_id, title, content_type, matched_keyword, problem_category, is_search_result)
        VALUES (?, ?, ?, 'longform', ?, ?, 1)
        """,
        (video_id, channel_id, title, search_query, problem_label),
    )
    conn.execute(
        """
        INSERT INTO video_keyword_matches (video_id, category, search_query, problem_id, problem_label)
        VALUES (?, ?, ?, ?, ?)
        """,
        (video_id, category, search_query, problem_id, problem_label),
    )


def _seed_outlier(conn, video_id, outlier_ratio, grade, score):
    conn.execute(
        "INSERT INTO outlier_scores (video_id, outlier_ratio, outlier_grade, opportunity_score) VALUES (?, ?, ?, ?)",
        (video_id, outlier_ratio, grade, score),
    )


def _seed_market_data(db_path: Path, *, reading_video_count: int = 1):
    with connect(db_path) as conn:
        conn.execute("INSERT INTO channels (channel_id, title, subscriber_count) VALUES ('c1', 'Ch1', 1000)")
        for i in range(reading_video_count):
            vid = f"r{i}"
            _seed_video(conn, vid, "c1", f"읽기 영상 {i}", "reading", "cannot_read_words", "읽기 문제", "영어 읽기 원리")
            _seed_outlier(conn, vid, 8.0, "strong", 80.0)

        _seed_video(conn, "l1", "c1", "듣기 영상", "listening", "liaison", "듣기 문제", "영어 듣기 연음")
        _seed_outlier(conn, "l1", 3.0, "notable", 60.0)


def test_insufficient_data_category_does_not_get_zero_market_demand(tmp_path):
    """A category with too few candidate videos must be flagged insufficient_data, not scored 0 --
    scoring it 0 would look identical to a confirmed dead market."""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    _seed_market_data(db_path, reading_video_count=1)  # well below the min_candidate_videos default
    pool_path = _write_pool(tmp_path)

    results = compute_topic_scores(db_path, pool_path, min_candidate_videos=10)
    by_category = {r["category"]: r for r in results}

    assert by_category["reading"]["market_evidence_status"] == "insufficient_data"
    assert by_category["reading"]["market_demand_score"] is None
    assert by_category["reading"]["content_opportunity_score"] is None
    assert by_category["reading"]["candidate_video_count"] == 1


def test_sufficient_data_category_gets_scored(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    _seed_market_data(db_path, reading_video_count=12)
    pool_path = _write_pool(tmp_path)

    results = compute_topic_scores(db_path, pool_path, min_candidate_videos=10)
    by_category = {r["category"]: r for r in results}

    assert by_category["reading"]["market_evidence_status"] == "sufficient"
    assert by_category["reading"]["market_demand_score"] is not None
    assert by_category["reading"]["market_demand_score"] > by_category["listening"]["market_demand_score"] if by_category["listening"]["market_demand_score"] is not None else True


def test_compute_topic_scores_without_my_channel_data(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    _seed_market_data(db_path, reading_video_count=12)
    pool_path = _write_pool(tmp_path)

    results = compute_topic_scores(db_path, pool_path, min_candidate_videos=10)
    by_category = {r["category"]: r for r in results}

    assert by_category["reading"]["outlier_video_count"] == 12
    # no my_channel_video_stats rows at all => neutral fit, not "available"
    assert by_category["reading"]["fit_data_available"] is False
    assert by_category["reading"]["my_channel_fit_score"] == 50.0


def test_compute_topic_scores_with_my_channel_data(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    _seed_market_data(db_path, reading_video_count=12)
    pool_path = _write_pool(tmp_path)

    with connect(db_path) as conn:
        # A video that clearly matches the "reading" keyword pool terms, with strong retention.
        conn.execute(
            """
            INSERT INTO my_channel_video_stats (video_id, title, average_percentage_viewed)
            VALUES ('m1', '영어 읽기 원리 정리', 80.0)
            """
        )
        # An unrelated video with weak retention, dragging the channel average down.
        conn.execute(
            """
            INSERT INTO my_channel_video_stats (video_id, title, average_percentage_viewed)
            VALUES ('m2', '오늘의 브이로그', 20.0)
            """
        )

    results = compute_topic_scores(db_path, pool_path, min_candidate_videos=10)
    by_category = {r["category"]: r for r in results}

    assert by_category["reading"]["fit_data_available"] is True
    # reading matched video (80%) performs above the channel average (50%) => fit score > 50
    assert by_category["reading"]["my_channel_fit_score"] > 50.0
    # listening has no matching my-channel video => falls back to neutral
    assert by_category["listening"]["fit_data_available"] is False
    assert by_category["listening"]["my_channel_fit_score"] == 50.0


def test_content_opportunity_score_is_product_of_components(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    _seed_market_data(db_path, reading_video_count=12)
    pool_path = _write_pool(tmp_path)

    results = compute_topic_scores(db_path, pool_path, min_candidate_videos=10)
    by_category = {r["category"]: r for r in results}
    reading = by_category["reading"]

    expected = reading["market_demand_score"] * (reading["my_channel_fit_score"] / 100.0)
    assert round(reading["content_opportunity_score"], 6) == round(expected, 6)
