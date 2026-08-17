import json

from research.content_packages import (
    CLICK_DRIVERS,
    PACKAGING_ANGLES,
    RELATIONSHIP_TYPES,
    build_content_packages_report,
    classify_package_brand_fit,
    compute_copy_risk,
    compute_package_score,
    detect_exaggeration,
    generate_packages_for_topic,
    is_duplicate_relationship,
    select_overall_top10,
    select_production_candidates,
    select_target_topics,
    select_topic_top3,
)
from research.db import connect, init_db


def _seed_channel(conn, channel_id="c1"):
    conn.execute("INSERT OR IGNORE INTO channels (channel_id, title) VALUES (?, ?)", (channel_id, f"Ch {channel_id}"))


def _seed_video(conn, video_id, title, channel_id="c1"):
    _seed_channel(conn, channel_id)
    conn.execute(
        "INSERT INTO videos (video_id, channel_id, title, content_type, is_search_result) VALUES (?, ?, ?, 'longform', 1)",
        (video_id, channel_id, title),
    )


def _seed_match(conn, video_id, category, search_query, problem_id, problem_label):
    conn.execute(
        "INSERT INTO video_keyword_matches (video_id, category, search_query, problem_id, problem_label) VALUES (?, ?, ?, ?, ?)",
        (video_id, category, search_query, problem_id, problem_label),
    )


def _seed_click_analysis_topic(conn, category="reading", problem_id="p1", topic_text="topic?", selected=1, click_score=80.0, topic_score=80.0, drivers=None):
    drivers = drivers or {"curiosity_gap": 3, "beginner_identity": 2}
    conn.execute(
        """
        INSERT INTO click_analysis_topics (category, problem_id, topic_text, topic_candidate_score,
            click_evidence_score, brand_fit, representative_video_count, repeated_click_drivers_json,
            selected_for_next_stage, selection_reason)
        VALUES (?, ?, ?, ?, ?, 'high', 5, ?, ?, 'test')
        """,
        (category, problem_id, topic_text, topic_score, click_score, json.dumps({"driver_counts": drivers}), selected),
    )


class _FakeGemini:
    available = True

    def __init__(self, response):
        self._response = response

    def generate_json(self, prompt, max_output_tokens=1536):
        return self._response


def _five_packages(angles=None):
    angles = angles or ["problem", "curiosity", "result", "example", "simplicity"]
    return [
        {
            "title": f"제목 {i} - {angle}", "thumbnail_text": f"썸네일 {i}", "visual_focus": "KNIFE",
            "layout": "중앙 배치", "example_word": "KNIFE", "highlight_element": "K",
            "primary_angle": angle, "secondary_angle": None, "primary_click_driver": "curiosity_gap",
            "title_thumbnail_relationship": "complementary",
        }
        for i, angle in enumerate(angles)
    ]


# --------------------------------------------------------------------------
# 1, 2, 3: >=5 titles, distinct angles, thumbnail text present
# --------------------------------------------------------------------------

def test_generate_packages_returns_at_least_five():
    topic = {"topic_text": "왜 원어민 말이 빠른가", "problem_label": "원어민은 왜 이렇게 빨리 말하는가", "repeated_drivers": []}
    packages = generate_packages_for_topic(topic, _FakeGemini(_five_packages()), {})
    assert len(packages) >= 5


def test_generated_packages_use_distinct_angles():
    topic = {"topic_text": "왜 원어민 말이 빠른가", "problem_label": "원어민은 왜 이렇게 빨리 말하는가", "repeated_drivers": []}
    packages = generate_packages_for_topic(topic, _FakeGemini(_five_packages()), {})
    angles = {p["primary_angle"] for p in packages}
    assert len(angles) >= 4


def test_every_package_has_thumbnail_text():
    topic = {"topic_text": "t", "problem_label": "p", "repeated_drivers": []}
    packages = generate_packages_for_topic(topic, _FakeGemini(_five_packages()), {})
    assert all(p["thumbnail_text"] for p in packages)


def test_fallback_used_when_gemini_unavailable_and_titles_are_not_the_raw_topic():
    topic = {"topic_text": "원어민은 왜 이렇게 빨리 말하는가", "problem_label": "원어민은 왜 이렇게 빨리 말하는가", "repeated_drivers": []}
    packages = generate_packages_for_topic(topic, gemini=None, channel_cfg={})
    assert len(packages) >= 5
    # none of the fallback titles are a literal copy of the raw topic sentence
    assert all(p["title"] != topic["topic_text"] for p in packages)


# --------------------------------------------------------------------------
# 4 & 5: duplicate detection + relationship taxonomy
# --------------------------------------------------------------------------

def test_is_duplicate_relationship_detects_high_overlap():
    # Near-verbatim repeat (same nouns/particles, just missing 를) -- the common real case the
    # word-overlap heuristic reliably catches. See is_duplicate_relationship's docstring for the
    # verb-conjugation limitation (e.g. "읽히지 않을까" vs "안 읽힐까" won't overlap this way).
    assert is_duplicate_relationship("영어 강세 위치를 어떻게 찾을까", "영어 강세 위치 어떻게 찾을까") is True


def test_is_duplicate_relationship_false_for_distinct_text():
    assert is_duplicate_relationship("영어는 왜 철자대로 읽히지 않을까", "KNIFE K는 어디 갔지?") is False


def test_relationship_taxonomy_is_fixed_set():
    expected = {
        "complementary", "curiosity_plus_answer", "problem_plus_solution", "setup_plus_payoff",
        "contrast", "duplicate", "unclear",
    }
    assert RELATIONSHIP_TYPES == expected


def test_invalid_relationship_from_gemini_falls_back_to_unclear():
    response = _five_packages()
    response[0]["title_thumbnail_relationship"] = "made_up_relationship"
    topic = {"topic_text": "t", "problem_label": "p", "repeated_drivers": []}
    packages = generate_packages_for_topic(topic, _FakeGemini(response), {})
    assert packages[0]["title_thumbnail_relationship"] == "unclear"


# --------------------------------------------------------------------------
# 6: click driver taxonomy validated
# --------------------------------------------------------------------------

def test_invalid_click_driver_from_gemini_falls_back():
    response = _five_packages()
    response[0]["primary_click_driver"] = "made_up_driver"
    topic = {"topic_text": "t", "problem_label": "p", "repeated_drivers": []}
    packages = generate_packages_for_topic(topic, _FakeGemini(response), {})
    assert packages[0]["primary_click_driver"] in CLICK_DRIVERS


def test_packaging_angles_taxonomy_has_eight_ids():
    expected = {"problem", "curiosity", "result", "example", "beginner_identity", "mistake", "contrast", "simplicity"}
    assert set(PACKAGING_ANGLES.keys()) == expected


# --------------------------------------------------------------------------
# 7: brand fit
# --------------------------------------------------------------------------

def test_brand_fit_high_for_aligned_driver():
    assert classify_package_brand_fit("curiosity_gap") == "high"


def test_brand_fit_low_for_conflicting_driver():
    assert classify_package_brand_fit("fear_or_failure") == "low"


# --------------------------------------------------------------------------
# 8: exaggeration penalty
# --------------------------------------------------------------------------

def test_detect_exaggeration_flags_known_phrases():
    assert detect_exaggeration("무조건 100% 완벽하게 끝냅니다") > 0


def test_detect_exaggeration_zero_for_clean_title():
    assert detect_exaggeration("영어 강세 위치를 이해하는 법") == 0.0


def test_detect_exaggeration_caps_at_twenty():
    text = "무조건 100% 완벽 평생 이것만 알면 끝 99%가 모르는 충격 기적 1초 만에 무조건 됩니다"
    assert detect_exaggeration(text) == 20.0


# --------------------------------------------------------------------------
# 9 & 10: copy risk detection + exclusion from shortlists
# --------------------------------------------------------------------------

def test_copy_risk_high_for_near_identical_title():
    existing = ["영어 강세 위치를 완벽하게 이해하는 방법 총정리"]
    risk, overlap = compute_copy_risk("영어 강세 위치를 완벽하게 이해하는 방법", existing)
    assert risk == "high"


def test_copy_risk_low_for_unrelated_title():
    existing = ["아이돌 예능 짤 모음"]
    risk, overlap = compute_copy_risk("영어 강세 위치를 이해하는 법", existing)
    assert risk == "low"


def test_high_copy_risk_excluded_from_topic_top3():
    packages = [
        {"category": "a", "problem_id": "p1", "package_score": 95, "copy_risk": "high", "excluded_reason": "copy_risk=high"},
        {"category": "a", "problem_id": "p1", "package_score": 60, "copy_risk": "low", "excluded_reason": None},
    ]
    top3 = select_topic_top3(packages)
    titles_scores = top3[("a", "p1")]
    assert len(titles_scores) == 1
    assert titles_scores[0]["package_score"] == 60


# --------------------------------------------------------------------------
# 11: package score bounds
# --------------------------------------------------------------------------

def test_package_score_within_bounds():
    result = compute_package_score(
        title="영어 강세 위치를 이해하는 법", problem_label="영어 강세 위치를 어떻게 아는가",
        primary_click_driver="curiosity_gap", repeated_drivers=["curiosity_gap"],
        title_thumbnail_relationship="complementary", example_word="STRESS", copy_overlap=0.0,
    )
    assert 0.0 <= result["base_score"] <= 100.0


def test_package_score_lower_for_duplicate_relationship():
    common = dict(
        title="영어 강세 위치를 이해하는 법", problem_label="영어 강세 위치를 어떻게 아는가",
        primary_click_driver="curiosity_gap", repeated_drivers=["curiosity_gap"], example_word=None, copy_overlap=0.0,
    )
    complementary = compute_package_score(title_thumbnail_relationship="complementary", **common)
    duplicate = compute_package_score(title_thumbnail_relationship="duplicate", **common)
    assert duplicate["base_score"] < complementary["base_score"]


# --------------------------------------------------------------------------
# 12: three scores kept separate (build_all_packages carries all three fields)
# --------------------------------------------------------------------------

def test_scores_kept_as_three_separate_fields(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_click_analysis_topic(conn, topic_score=79.4, click_score=69.4)
        _seed_video(conn, "v1", "영어 강세 관련 영상")
        _seed_match(conn, "v1", "reading", "q", "p1", "topic?")

    from research.content_packages import build_all_packages

    packages = build_all_packages(db_path, _FakeGemini(_five_packages()), {})
    assert packages
    p = packages[0]
    assert p["topic_candidate_score"] == 79.4
    assert p["click_evidence_score"] == 69.4
    assert "package_score" in p
    assert p["package_score"] != p["topic_candidate_score"]  # never blended


# --------------------------------------------------------------------------
# 13 & 14: Topic TOP3, overall TOP10 diversity
# --------------------------------------------------------------------------

def test_select_topic_top3_caps_at_three():
    packages = [
        {"category": "a", "problem_id": "p1", "package_score": 90 - i, "copy_risk": "low", "excluded_reason": None}
        for i in range(5)
    ]
    top3 = select_topic_top3(packages)
    assert len(top3[("a", "p1")]) == 3


def test_select_overall_top10_limits_per_topic():
    packages = []
    for topic_i in range(3):
        for pkg_i in range(4):
            packages.append(
                {"category": "a", "problem_id": f"p{topic_i}", "package_score": 100 - topic_i * 10 - pkg_i,
                 "copy_risk": "low", "excluded_reason": None}
            )
    top10 = select_overall_top10(packages, max_n=10, max_per_topic=2)
    from collections import Counter
    counts = Counter((p["category"], p["problem_id"]) for p in top10)
    assert all(c <= 2 for c in counts.values())


# --------------------------------------------------------------------------
# 15: Listening comparison candidate retained even if not auto-selected
# --------------------------------------------------------------------------

def test_listening_comparison_candidate_included_when_strong(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_click_analysis_topic(conn, category="reading", problem_id="p1", topic_text="reading topic", selected=1)
        # listening topic NOT selected_for_next_stage, but should still show up as comparison candidate
        _seed_click_analysis_topic(conn, category="listening", problem_id="p2", topic_text="listening topic", selected=0, click_score=85.0)
        _seed_video(conn, "v1", "reading vid")
        _seed_match(conn, "v1", "reading", "q", "p1", "reading topic")
        _seed_video(conn, "v2", "listening vid")
        _seed_match(conn, "v2", "listening", "q2", "p2", "listening topic")

    topics = select_target_topics(db_path)
    categories = {t["category"] for t in topics}
    assert "listening" in categories
    listening_topic = next(t for t in topics if t["category"] == "listening")
    assert listening_topic["is_comparison_candidate"] is True


# --------------------------------------------------------------------------
# 16: production candidate selection
# --------------------------------------------------------------------------

def test_select_production_candidates_excludes_low_brand_fit_and_ensures_topic_diversity():
    packages = [
        {"category": "a", "problem_id": "p1", "title": "t1", "package_score": 95, "brand_fit": "low",
         "click_evidence_score": 90, "topic_candidate_score": 90, "excluded_reason": None},
        {"category": "b", "problem_id": "p2", "title": "t2", "package_score": 80, "brand_fit": "high",
         "click_evidence_score": 75, "topic_candidate_score": 75, "excluded_reason": None},
        {"category": "b", "problem_id": "p2", "title": "t3", "package_score": 78, "brand_fit": "high",
         "click_evidence_score": 70, "topic_candidate_score": 70, "excluded_reason": None},
        {"category": "c", "problem_id": "p3", "title": "t4", "package_score": 70, "brand_fit": "medium",
         "click_evidence_score": 65, "topic_candidate_score": 65, "excluded_reason": None},
    ]
    selected = select_production_candidates(packages, min_n=1, max_n=3)
    assert all(p["brand_fit"] != "low" for p in selected)
    # topic diversity: p2 shouldn't contribute both t2 and t3
    topics = [(p["category"], p["problem_id"]) for p in selected]
    assert len(topics) == len(set(topics))
    assert all(p.get("production_reason") for p in selected)


def test_report_generation_produces_expected_sections(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_click_analysis_topic(conn)
        _seed_video(conn, "v1", "영상")
        _seed_match(conn, "v1", "reading", "q", "p1", "topic?")

    out_path = build_content_packages_report(db_path, tmp_path / "reports", None, {})
    text = out_path.read_text(encoding="utf-8")
    for heading in [
        "# YouTube Title & Thumbnail Strategy",
        "## 1. 분석 대상",
        "## 4. 전체 제목 후보",
        "## 5. Topic별 TOP3 Package",
        "## 6. 전체 Package TOP10",
        "## 7. Listening 비교군",
        "## 9. 실제 제작 검토 후보",
    ]:
        assert heading in text
