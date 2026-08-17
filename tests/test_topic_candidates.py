from pathlib import Path

import yaml

from research.db import connect, init_db
from research.topic_candidates import (
    aggregate_viewer_problems,
    build_candidates,
    build_topic_candidates_report,
    classify_evidence_quality,
    classify_format,
    cluster_candidates,
    compare_with_weekly_top5,
    compute_topic_candidate_score,
)


def _seed_channel(conn, channel_id="c1"):
    conn.execute("INSERT OR IGNORE INTO channels (channel_id, title) VALUES (?, ?)", (channel_id, f"Ch {channel_id}"))


def _seed_video(conn, video_id, title, channel_id="c1", content_type="longform"):
    _seed_channel(conn, channel_id)
    conn.execute(
        "INSERT INTO videos (video_id, channel_id, title, content_type, is_search_result) VALUES (?, ?, ?, ?, 1)",
        (video_id, channel_id, title, content_type),
    )


def _seed_outlier(conn, video_id, ratio, score, grade="strong"):
    conn.execute(
        "INSERT INTO outlier_scores (video_id, outlier_ratio, outlier_grade, opportunity_score) VALUES (?, ?, ?, ?)",
        (video_id, ratio, grade, score),
    )


def _seed_match(conn, video_id, category, search_query, problem_id, problem_label):
    conn.execute(
        """
        INSERT INTO video_keyword_matches (video_id, category, search_query, problem_id, problem_label)
        VALUES (?, ?, ?, ?, ?)
        """,
        (video_id, category, search_query, problem_id, problem_label),
    )


def _seed_topic_opportunity(conn, category, status="sufficient", demand=80.0, fit=60.0, content_opp=48.0):
    conn.execute(
        """
        INSERT INTO topic_opportunities (problem_category, market_demand_score, my_channel_fit_score,
            fit_data_available, content_opportunity_score, outlier_video_count, market_evidence_status,
            candidate_video_count, evidence_confidence, evidence_json)
        VALUES (?, ?, ?, 1, ?, 5, ?, 20, 'high', '{}')
        """,
        (category, demand, fit, content_opp, status),
    )


def _write_pool(tmp_path, categories=("reading",)):
    pool = {}
    for cat in categories:
        pool[cat] = {"problems": [{"id": "p1", "label": f"{cat} 고민", "search_queries": ["q1"]}]}
    path = tmp_path / "keyword_pool.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(pool, f, allow_unicode=True, sort_keys=False)
    return path


# --------------------------------------------------------------------------
# 1 & 2: unique video x problem aggregation, no inflation from repeat queries
# --------------------------------------------------------------------------

def test_matched_video_count_is_unique_video_not_query_matches(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_topic_opportunity(conn, "reading")
        _seed_video(conn, "v1", "영어 강세 정리")
        # same video matched to the same problem via two different queries
        _seed_match(conn, "v1", "reading", "query a", "word_stress", "영어 강세 위치를 어떻게 아는가")
        _seed_match(conn, "v1", "reading", "query b", "word_stress", "영어 강세 위치를 어떻게 아는가")
        _seed_outlier(conn, "v1", 8.0, 80.0)

    problems = aggregate_viewer_problems(db_path)
    assert len(problems) == 1
    assert problems[0]["matched_video_count"] == 1  # not 2


def test_multiple_distinct_videos_counted_correctly(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_topic_opportunity(conn, "reading")
        for i in range(3):
            _seed_video(conn, f"v{i}", f"영상 {i}")
            _seed_match(conn, f"v{i}", "reading", "q", "word_stress", "영어 강세 위치를 어떻게 아는가")
            _seed_outlier(conn, f"v{i}", 8.0, 80.0)

    problems = aggregate_viewer_problems(db_path)
    assert problems[0]["matched_video_count"] == 3
    assert problems[0]["outlier_video_count"] == 3


# --------------------------------------------------------------------------
# 3 & 12: cluster/duplicate merge + diversity
# --------------------------------------------------------------------------

def test_cluster_candidates_merges_similar_topics():
    # Lexical (word-overlap) clustering, not semantic -- these two share most of their
    # significant words ("영어","강세","위치","어떻게"), which is what the heuristic can detect.
    # True synonyms phrased with completely different words (e.g. "원어민이 빠르게 말한다" vs
    # "듣기 속도를 못 따라간다") won't merge -- a known limitation without embeddings.
    candidates = [
        {"topic_text": "영어 강세 위치를 어떻게 찾을까", "topic_candidate_score": 70},
        {"topic_text": "영어 강세 위치는 어떻게 아는가", "topic_candidate_score": 65},
        {"topic_text": "영어 묵음은 왜 생길까", "topic_candidate_score": 60},
    ]
    result = cluster_candidates(candidates, threshold=0.5)
    cluster_ids = {c["cluster_id"] for c in result}
    assert len(cluster_ids) == 2  # first two merge, third stays separate

    representatives = [c for c in result if c["is_cluster_representative"]]
    assert len(representatives) == 2
    # the higher-scoring of the merged pair becomes representative
    merged_cluster_id = next(c["cluster_id"] for c in result if c["topic_text"] == "영어 강세 위치를 어떻게 찾을까")
    rep = next(c for c in result if c["cluster_id"] == merged_cluster_id and c["is_cluster_representative"])
    assert rep["topic_text"] == "영어 강세 위치를 어떻게 찾을까"


def test_cluster_candidates_keeps_unrelated_topics_separate():
    candidates = [
        {"topic_text": "did you가 왜 디쥬처럼 들리는가", "topic_candidate_score": 70},
        {"topic_text": "schwa 약화는 무엇인가", "topic_candidate_score": 60},
    ]
    result = cluster_candidates(candidates, threshold=0.5)
    assert len({c["cluster_id"] for c in result}) == 2
    assert all(c["is_cluster_representative"] for c in result)


# --------------------------------------------------------------------------
# 4: evidence quality classification
# --------------------------------------------------------------------------

def test_evidence_quality_direct_when_query_in_title():
    assert classify_evidence_quality("영어 강세 위치 완벽 정리", "영어 강세 위치를 어떻게 아는가", "영어 강세 위치") == "direct"


def test_evidence_quality_adjacent_for_partial_overlap():
    assert classify_evidence_quality("영어 발음 꿀팁 모음", "영어 강세 위치를 어떻게 아는가", "영어 강세") == "adjacent"


def test_evidence_quality_weak_for_unrelated_title():
    assert classify_evidence_quality("아이돌 예능 짤 모음", "영어 강세 위치를 어떻게 아는가", "영어 강세") == "weak"


# --------------------------------------------------------------------------
# 5 & 10: insufficient_data handling / minimum evidence bar
# --------------------------------------------------------------------------

def test_insufficient_data_category_produces_no_candidates(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_topic_opportunity(conn, "listening", status="insufficient_data", demand=None, content_opp=None)
        _seed_video(conn, "v1", "듣기 영상")
        _seed_match(conn, "v1", "listening", "q", "p1", "원어민은 왜 이렇게 빨리 말하는가")
        _seed_outlier(conn, "v1", 8.0, 80.0)

    problems = aggregate_viewer_problems(db_path)
    assert problems == []  # category has no market evidence yet -> no candidates, not zero-scored ones


def test_zero_outlier_videos_excluded_from_candidates(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    gemini = None
    with connect(db_path) as conn:
        _seed_topic_opportunity(conn, "reading")
        _seed_video(conn, "v1", "제목")
        _seed_match(conn, "v1", "reading", "q", "p1", "영어 강세 위치를 어떻게 아는가")
        # no outlier_scores row inserted -> 0 outlier videos for this problem

    candidates = build_candidates(db_path, gemini)
    assert candidates == []


def test_too_broad_problem_excluded(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_topic_opportunity(conn, "reading")
        _seed_video(conn, "v1", "영어 공부법 총정리")
        _seed_match(conn, "v1", "reading", "q", "p1", "영어")  # label too short/broad
        _seed_outlier(conn, "v1", 8.0, 80.0)

    candidates = build_candidates(db_path, None)
    assert candidates == []


# --------------------------------------------------------------------------
# 6 & 7: deterministic score, extreme outlier does not dominate
# --------------------------------------------------------------------------

def _score_kwargs(**overrides):
    base = dict(
        matched_video_count=5,
        median_outlier_ratio=10.0,
        outlier_video_count=3,
        market_demand_score=80.0,
        my_channel_fit_score=60.0,
        evidence_quality_scores=[100.0, 60.0],
        granularity="appropriate",
        recommended_format="Both",
    )
    base.update(overrides)
    return base


def test_score_is_deterministic():
    a = compute_topic_candidate_score(**_score_kwargs())
    b = compute_topic_candidate_score(**_score_kwargs())
    assert a == b


def test_extreme_outlier_ratio_does_not_dominate_score():
    normal = compute_topic_candidate_score(**_score_kwargs(median_outlier_ratio=10.0))
    extreme = compute_topic_candidate_score(**_score_kwargs(median_outlier_ratio=100_000.0))
    # log-normalized: massive difference in input should not translate to a massive score jump
    assert extreme - normal < 25
    assert extreme <= 100.0


def test_score_stays_in_bounds():
    score = compute_topic_candidate_score(**_score_kwargs(median_outlier_ratio=1_000_000.0, matched_video_count=1000, outlier_video_count=1000))
    assert 0.0 <= score <= 100.0


# --------------------------------------------------------------------------
# 8: channel fit reflected in score
# --------------------------------------------------------------------------

def test_higher_channel_fit_increases_score():
    low_fit = compute_topic_candidate_score(**_score_kwargs(my_channel_fit_score=10.0))
    high_fit = compute_topic_candidate_score(**_score_kwargs(my_channel_fit_score=90.0))
    assert high_fit > low_fit


# --------------------------------------------------------------------------
# 9: Long-form / Shorts / Both classification
# --------------------------------------------------------------------------

def test_classify_format_mostly_longform():
    assert classify_format(["longform"] * 9 + ["short"]) == "Long-form"


def test_classify_format_mostly_shorts():
    assert classify_format(["short"] * 9 + ["longform"]) == "Shorts"


def test_classify_format_mixed_is_both():
    assert classify_format(["longform", "short"]) == "Both"


def test_classify_format_no_data_defaults_to_both():
    assert classify_format([]) == "Both"


# --------------------------------------------------------------------------
# 11: TOP-N sorting
# --------------------------------------------------------------------------

def test_candidates_sorted_representative_first_then_score(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_topic_opportunity(conn, "reading")
        _seed_video(conn, "v1", "영어 강세 정리 영상")
        _seed_match(conn, "v1", "reading", "q1", "word_stress", "영어 강세 위치를 어떻게 아는가")
        _seed_outlier(conn, "v1", 40.0, 90.0)

        _seed_video(conn, "v2", "영어 묵음 원리 설명")
        _seed_match(conn, "v2", "reading", "q2", "silent_letters", "영어 묵음은 왜 생기는가")
        _seed_outlier(conn, "v2", 5.0, 40.0)

    candidates = build_candidates(db_path, None)
    scores = [c["topic_candidate_score"] for c in candidates]
    assert scores == sorted(scores, reverse=True)


# --------------------------------------------------------------------------
# 13: comparison with Weekly Report TOP5
# --------------------------------------------------------------------------

def test_compare_with_weekly_top5_reports_overlap(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_topic_opportunity(conn, "reading", demand=90.0, fit=60.0, content_opp=54.0)

    candidates = [
        {
            "category": "reading", "problem_id": "p1", "topic_text": "영어 강세 위치를 어떻게 찾을까?",
            "is_cluster_representative": True, "market_demand_score": 90.0, "my_channel_fit_score": 60.0,
            "median_outlier_ratio": 30.0, "evidence_quality_avg": 90.0,
        }
    ]
    lines = compare_with_weekly_top5(db_path, candidates)
    assert any("reading" in line for line in lines)
    assert len(lines) == 5  # five questions from section 14


# --------------------------------------------------------------------------
# 14: report generation + no new API calls
# --------------------------------------------------------------------------

def test_build_topic_candidates_report_generates_expected_sections(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_topic_opportunity(conn, "reading")
        _seed_video(conn, "v1", "영어 강세 정리 영상")
        _seed_match(conn, "v1", "reading", "q1", "word_stress", "영어 강세 위치를 어떻게 아는가")
        _seed_outlier(conn, "v1", 40.0, 90.0)

    pool_path = _write_pool(tmp_path, categories=["reading", "listening"])
    reports_dir = tmp_path / "reports"

    out_path = build_topic_candidates_report(db_path, reports_dir, None, pool_path, top_n=20)

    assert out_path.exists()
    text = out_path.read_text(encoding="utf-8")
    for heading in [
        "# YouTube Topic Candidates",
        "## 1. 데이터 상태",
        "## 2. Viewer Problem 전체 순위",
        "## 3. Topic Cluster",
        "## 4. Topic Candidate TOP20",
        "## 5. Long-form 후보",
        "## 6. Shorts 후보",
        "다음 단계로 넘길 후보",
    ]:
        assert heading in text

    # persisted for the next stage (06_클릭_이유_분석) to query later
    with connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM topic_candidates").fetchall()
    assert len(rows) >= 1


def test_build_topic_candidates_report_uses_no_youtube_api(tmp_path):
    """This stage must work entirely off already-collected DB data -- confirm api_call_log
    doesn't grow at all."""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_topic_opportunity(conn, "reading")
        _seed_video(conn, "v1", "영어 강세 정리 영상")
        _seed_match(conn, "v1", "reading", "q1", "word_stress", "영어 강세 위치를 어떻게 아는가")
        _seed_outlier(conn, "v1", 40.0, 90.0)

    pool_path = _write_pool(tmp_path)
    reports_dir = tmp_path / "reports"

    with connect(db_path) as conn:
        before = conn.execute("SELECT COUNT(*) AS n FROM api_call_log").fetchone()["n"]

    build_topic_candidates_report(db_path, reports_dir, None, pool_path, top_n=20)

    with connect(db_path) as conn:
        after = conn.execute("SELECT COUNT(*) AS n FROM api_call_log").fetchone()["n"]
    assert before == after == 0
