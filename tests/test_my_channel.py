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
            "problems": ["읽기 문제"],
            "search_queries": ["영어 읽기 원리"],
        },
        "listening": {
            "problems": ["듣기 문제"],
            "search_queries": ["영어 듣기 연음"],
        },
    }
    path = tmp_path / "keyword_pool.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(pool, f, allow_unicode=True)
    return path


def _seed_market_data(db_path: Path):
    with connect(db_path) as conn:
        conn.execute("INSERT INTO keywords (category, problem, search_query) VALUES ('reading', '읽기 문제', '영어 읽기 원리')")
        conn.execute("INSERT INTO keywords (category, problem, search_query) VALUES ('listening', '듣기 문제', '영어 듣기 연음')")

        conn.execute(
            "INSERT INTO channels (channel_id, title, subscriber_count) VALUES ('c1', 'Ch1', 1000)"
        )
        conn.execute(
            """
            INSERT INTO videos (video_id, channel_id, title, content_type, matched_keyword, problem_category, is_search_result)
            VALUES ('v1', 'c1', '읽기 영상', 'longform', '영어 읽기 원리', '읽기 문제', 1)
            """
        )
        conn.execute(
            """
            INSERT INTO videos (video_id, channel_id, title, content_type, matched_keyword, problem_category, is_search_result)
            VALUES ('v2', 'c1', '듣기 영상', 'longform', '영어 듣기 연음', '듣기 문제', 1)
            """
        )
        conn.execute(
            """
            INSERT INTO outlier_scores (video_id, outlier_ratio, outlier_grade, opportunity_score)
            VALUES ('v1', 8.0, 'strong', 80.0)
            """
        )
        conn.execute(
            """
            INSERT INTO outlier_scores (video_id, outlier_ratio, outlier_grade, opportunity_score)
            VALUES ('v2', 3.0, 'notable', 60.0)
            """
        )


def test_compute_topic_scores_without_my_channel_data(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    _seed_market_data(db_path)
    pool_path = _write_pool(tmp_path)

    results = compute_topic_scores(db_path, pool_path)
    by_category = {r["category"]: r for r in results}

    assert by_category["reading"]["outlier_video_count"] == 1
    assert by_category["reading"]["market_demand_score"] > by_category["listening"]["market_demand_score"]
    # no my_channel_video_stats rows at all => neutral fit, not "available"
    assert by_category["reading"]["fit_data_available"] is False
    assert by_category["reading"]["my_channel_fit_score"] == 50.0


def test_compute_topic_scores_with_my_channel_data(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    _seed_market_data(db_path)
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

    results = compute_topic_scores(db_path, pool_path)
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
    _seed_market_data(db_path)
    pool_path = _write_pool(tmp_path)

    results = compute_topic_scores(db_path, pool_path)
    by_category = {r["category"]: r for r in results}
    reading = by_category["reading"]

    expected = reading["market_demand_score"] * (reading["my_channel_fit_score"] / 100.0)
    assert round(reading["content_opportunity_score"], 6) == round(expected, 6)
