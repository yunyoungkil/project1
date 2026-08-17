from pathlib import Path

from research.click_analysis import (
    CLICK_DRIVERS,
    analyze_video_click_reasons,
    build_click_analysis_report,
    classify_brand_fit,
    classify_click_devices,
    compute_click_evidence_score,
    fallback_click_driver,
    select_next_stage_candidates,
    select_representative_videos,
)
from research.db import connect, init_db


def _seed_channel(conn, channel_id, title=None):
    conn.execute("INSERT OR IGNORE INTO channels (channel_id, title) VALUES (?, ?)", (channel_id, title or f"Ch {channel_id}"))


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


def _seed_shortlisted_topic(conn, category="reading", problem_id="p1", problem_label="영어 강세 위치를 어떻게 아는가", score=80.0):
    conn.execute(
        """
        INSERT INTO topic_candidates (category, problem_id, problem_label, topic_text, cluster_id,
            is_cluster_representative, recommended_format, evidence_quality, topic_candidate_score,
            matched_video_count, outlier_video_count, shortlisted, shortlist_reason)
        VALUES (?, ?, ?, ?, 1, 1, 'Long-form', 'adjacent', ?, 5, 3, 1, '시장 반응 강함')
        """,
        (category, problem_id, problem_label, f"{problem_label}?", score),
    )


# --------------------------------------------------------------------------
# 1 & 2: representative video selection + video-level dedup
# --------------------------------------------------------------------------

def test_select_representative_videos_dedups_multi_query_matches(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_video(conn, "v1", "영어 강세 위치 정리")
        _seed_match(conn, "v1", "reading", "query a", "p1", "영어 강세 위치를 어떻게 아는가")
        _seed_match(conn, "v1", "reading", "query b", "p1", "영어 강세 위치를 어떻게 아는가")
        _seed_outlier(conn, "v1", 8.0, 80.0)

    reps = select_representative_videos(db_path, "reading", "p1", "영어 강세 위치를 어떻게 아는가")
    assert len(reps) == 1  # not 2, despite two query matches


def test_select_representative_videos_returns_up_to_max_n(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        for i in range(8):
            _seed_video(conn, f"v{i}", f"영어 강세 영상 {i}", channel_id=f"c{i}")
            _seed_match(conn, f"v{i}", "reading", "q", "p1", "영어 강세 위치를 어떻게 아는가")
            _seed_outlier(conn, f"v{i}", 8.0, 50.0 + i)

    reps = select_representative_videos(db_path, "reading", "p1", "영어 강세 위치를 어떻게 아는가", max_n=5)
    assert len(reps) == 5


# --------------------------------------------------------------------------
# 3: direct evidence prioritized over adjacent/weak
# --------------------------------------------------------------------------

def test_direct_evidence_sorted_first(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        # weak evidence but a higher opportunity_score
        _seed_video(conn, "weak1", "아이돌 예능 밈 모음", channel_id="c1")
        _seed_match(conn, "weak1", "reading", "영어 강세", "p1", "영어 강세 위치를 어떻게 아는가")
        _seed_outlier(conn, "weak1", 8.0, 99.0)

        # direct evidence, lower opportunity_score
        _seed_video(conn, "direct1", "영어 강세 위치 완벽 정리", channel_id="c2")
        _seed_match(conn, "direct1", "reading", "영어 강세 위치", "p1", "영어 강세 위치를 어떻게 아는가")
        _seed_outlier(conn, "direct1", 5.0, 40.0)

    reps = select_representative_videos(db_path, "reading", "p1", "영어 강세 위치를 어떻게 아는가", max_n=5)
    assert reps[0]["video_id"] == "direct1"
    assert reps[0]["evidence_quality"] == "direct"


# --------------------------------------------------------------------------
# 4 & 6: fixed taxonomy + hallucinated driver rejection
# --------------------------------------------------------------------------

def test_click_drivers_taxonomy_has_the_twelve_spec_ids():
    expected = {
        "problem_recognition", "curiosity_gap", "result_promise", "one_solution", "beginner_identity",
        "loss_avoidance", "speed_convenience", "specificity", "surprise", "social_proof",
        "fear_or_failure", "transformation",
    }
    assert set(CLICK_DRIVERS.keys()) == expected


class _FakeGemini:
    available = True

    def __init__(self, response):
        self._response = response

    def generate_json(self, prompt, max_output_tokens=512):
        return self._response


def test_gemini_hallucinated_driver_falls_back_to_rule_based():
    response = {"primary_click_driver": "made_up_driver_xyz", "secondary_click_driver": None}
    video = {"video_id": "v1", "title": "영어 강세 5가지 규칙", "content_type": "longform", "evidence_quality": "direct"}
    result = analyze_video_click_reasons(video, "영어 강세 위치를 어떻게 아는가", _FakeGemini(response))
    assert result["primary_click_driver"] in CLICK_DRIVERS
    assert result["primary_click_driver"] == fallback_click_driver(classify_click_devices(video["title"]))


def test_gemini_valid_driver_is_used():
    response = {"primary_click_driver": "curiosity_gap", "secondary_click_driver": "specificity"}
    video = {"video_id": "v1", "title": "왜 강세를 틀리면 안 들릴까?", "content_type": "longform", "evidence_quality": "direct"}
    result = analyze_video_click_reasons(video, "영어 강세 위치를 어떻게 아는가", _FakeGemini(response))
    assert result["primary_click_driver"] == "curiosity_gap"
    assert result["secondary_click_driver"] == "specificity"


# --------------------------------------------------------------------------
# 5: at most 2 drivers assigned
# --------------------------------------------------------------------------

def test_at_most_primary_and_secondary_driver_assigned():
    video = {"video_id": "v1", "title": "영어 강세 5가지 규칙", "content_type": "longform", "evidence_quality": "direct"}
    result = analyze_video_click_reasons(video, "영어 강세 위치를 어떻게 아는가", gemini=None)
    driver_fields = [k for k in result if "click_driver" in k]
    assert set(driver_fields) == {"primary_click_driver", "secondary_click_driver"}
    assert result["secondary_click_driver"] is None  # rule-based path never invents a secondary


# --------------------------------------------------------------------------
# 7 & 8: thumbnail / hook unavailable
# --------------------------------------------------------------------------

def test_thumbnail_and_hook_status_always_unavailable(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_shortlisted_topic(conn)
        _seed_video(conn, "v1", "영어 강세 정리")
        _seed_match(conn, "v1", "reading", "q", "p1", "영어 강세 위치를 어떻게 아는가")
        _seed_outlier(conn, "v1", 8.0, 80.0)

    from research.click_analysis import build_click_analysis

    topics = build_click_analysis(db_path, gemini=None, top_n=10)
    assert all(t["thumbnail_data_status"] == "unavailable" for t in topics)
    assert all(t["hook_data_status"] == "unavailable" for t in topics)


# --------------------------------------------------------------------------
# 9 & 10: weight renormalization, score bounds
# --------------------------------------------------------------------------

def _video_analysis(evidence_quality="direct", driver="curiosity_gap"):
    return {
        "video_id": "v1", "primary_click_driver": driver, "evidence_quality": evidence_quality,
        "devices": {}, "content_type": "longform",
    }


def test_score_renormalizes_without_thumbnail_data():
    analyses = [_video_analysis() for _ in range(3)]
    score = compute_click_evidence_score(video_analyses=analyses, thumbnail_data_available=False)
    # all 3 videos: same driver (repeated=100), evidence direct(100), non-weak(100), count log-normalized
    assert 0.0 <= score <= 100.0
    assert score > 50  # strong, consistent evidence should score well despite missing thumbnail dimension


def test_score_is_zero_for_no_videos():
    assert compute_click_evidence_score(video_analyses=[]) == 0.0


def test_score_stays_in_bounds_with_mixed_quality():
    analyses = [_video_analysis("weak", "surprise"), _video_analysis("direct", "curiosity_gap"), _video_analysis("adjacent", "one_solution")]
    score = compute_click_evidence_score(video_analyses=analyses)
    assert 0.0 <= score <= 100.0


# --------------------------------------------------------------------------
# 11: Shorts vs Long-form separated (checked via representative video content_type)
# --------------------------------------------------------------------------

def test_representative_videos_carry_content_type_for_format_split(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_video(conn, "s1", "영어 강세 shorts", content_type="short", channel_id="c1")
        _seed_match(conn, "s1", "reading", "q", "p1", "영어 강세 위치를 어떻게 아는가")
        _seed_outlier(conn, "s1", 8.0, 80.0)
        _seed_video(conn, "l1", "영어 강세 longform", content_type="longform", channel_id="c2")
        _seed_match(conn, "l1", "reading", "q2", "p1", "영어 강세 위치를 어떻게 아는가")
        _seed_outlier(conn, "l1", 8.0, 70.0)

    reps = select_representative_videos(db_path, "reading", "p1", "영어 강세 위치를 어떻게 아는가")
    content_types = {v["content_type"] for v in reps}
    assert content_types == {"short", "longform"}


# --------------------------------------------------------------------------
# 12: brand fit
# --------------------------------------------------------------------------

def test_brand_fit_high_when_aligned_drivers_dominate():
    analyses = [_video_analysis(driver="problem_recognition"), _video_analysis(driver="curiosity_gap"), _video_analysis(driver="transformation")]
    assert classify_brand_fit(analyses) == "high"


def test_brand_fit_low_when_conflicting_drivers_dominate():
    analyses = [_video_analysis(driver="fear_or_failure"), _video_analysis(driver="surprise"), _video_analysis(driver="social_proof")]
    assert classify_brand_fit(analyses) == "low"


def test_brand_fit_medium_for_mixed_signals():
    analyses = [_video_analysis(driver="problem_recognition"), _video_analysis(driver="fear_or_failure")]
    assert classify_brand_fit(analyses) == "medium"


# --------------------------------------------------------------------------
# 13 & 14: topic_candidate_score untouched, click score stored separately
# --------------------------------------------------------------------------

def test_topic_candidate_score_unchanged_after_click_analysis(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_shortlisted_topic(conn, score=83.7)
        _seed_video(conn, "v1", "영어 강세 정리")
        _seed_match(conn, "v1", "reading", "q", "p1", "영어 강세 위치를 어떻게 아는가")
        _seed_outlier(conn, "v1", 8.0, 80.0)

    with connect(db_path) as conn:
        before = conn.execute("SELECT topic_candidate_score FROM topic_candidates").fetchone()["topic_candidate_score"]

    build_click_analysis_report(db_path, tmp_path / "reports", None, top_n=10)

    with connect(db_path) as conn:
        after = conn.execute("SELECT topic_candidate_score FROM topic_candidates").fetchone()["topic_candidate_score"]
    assert before == after == 83.7


def test_click_score_persisted_in_separate_table(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_shortlisted_topic(conn)
        _seed_video(conn, "v1", "영어 강세 정리")
        _seed_match(conn, "v1", "reading", "q", "p1", "영어 강세 위치를 어떻게 아는가")
        _seed_outlier(conn, "v1", 8.0, 80.0)

    build_click_analysis_report(db_path, tmp_path / "reports", None, top_n=10)

    with connect(db_path) as conn:
        topic_rows = conn.execute("SELECT * FROM click_analysis_topics").fetchall()
        video_rows = conn.execute("SELECT * FROM click_analysis_videos").fetchall()
    assert len(topic_rows) == 1
    assert topic_rows[0]["click_evidence_score"] is not None
    assert len(video_rows) == 1


# --------------------------------------------------------------------------
# 15: 3-5 candidates for stage 07
# --------------------------------------------------------------------------

def test_select_next_stage_candidates_excludes_low_brand_fit():
    topics = [
        {"category": "a", "problem_id": "p1", "topic_text": "t1", "click_evidence_score": 90, "brand_fit": "high", "topic_candidate_score": 80, "representative_video_count": 5},
        {"category": "b", "problem_id": "p2", "topic_text": "t2", "click_evidence_score": 95, "brand_fit": "low", "topic_candidate_score": 85, "representative_video_count": 5},
        {"category": "c", "problem_id": "p3", "topic_text": "t3", "click_evidence_score": 70, "brand_fit": "medium", "topic_candidate_score": 60, "representative_video_count": 3},
    ]
    selected = select_next_stage_candidates(topics, min_n=1, max_n=5)
    assert all(t["brand_fit"] != "low" for t in selected)
    assert "t2" not in [t["topic_text"] for t in selected]
    for t in selected:
        assert t["selection_reason"]


def test_select_next_stage_candidates_caps_at_max_n():
    topics = [
        {"category": "x", "problem_id": f"p{i}", "topic_text": f"t{i}", "click_evidence_score": 100 - i,
         "brand_fit": "high", "topic_candidate_score": 80, "representative_video_count": 5}
        for i in range(8)
    ]
    selected = select_next_stage_candidates(topics, min_n=3, max_n=5)
    assert len(selected) == 5


def test_report_generation_produces_expected_sections(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_shortlisted_topic(conn)
        _seed_video(conn, "v1", "영어 강세 정리")
        _seed_match(conn, "v1", "reading", "q", "p1", "영어 강세 위치를 어떻게 아는가")
        _seed_outlier(conn, "v1", 8.0, 80.0)

    out_path = build_click_analysis_report(db_path, tmp_path / "reports", None, top_n=10)
    text = out_path.read_text(encoding="utf-8")
    for heading in [
        "# YouTube Click Analysis",
        "## 1. 분석 데이터 상태",
        "## 2. 분석 대상 Topic",
        "## 3. Topic별 대표 Outlier",
        "## 4. Click Driver 전체 빈도",
        "## 10. Topic Candidate Score vs Click Evidence Score",
        "## 13. 07 단계로 넘길 후보",
    ]:
        assert heading in text
