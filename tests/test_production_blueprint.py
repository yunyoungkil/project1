import json

from research.db import connect, init_db
from research.production_blueprint import (
    HOOK_TYPES,
    PREREQUISITE_LEVELS,
    RETENTION_DEVICES,
    VISUAL_TYPES,
    build_blueprint,
    build_production_blueprint_report,
    check_example_scope_safe,
    check_mini_success_target_novel_safe,
    check_mini_success_uses_learned_material_safe,
    check_phoneme_explanation_safe,
    check_promise_matches_scope,
    compute_blueprint_score,
    estimate_production_complexity,
    generate_blueprint_content,
    ready_for_script,
    run_integrity_check,
    select_target_package,
    verify_promise_feasibility,
)


def _seed_package(conn, package_id=None, category="reading", problem_id="p1",
                   title="왜 알파벳 이름을 다 아는데 3글자 단어도 바로 안 읽힐까?",
                   thumbnail_text="KNIFE K는 어디 갔지?", example_word="KNIFE",
                   package_score=88.0, selected=1):
    cur = conn.execute(
        """
        INSERT INTO content_packages (category, problem_id, topic_text, title, thumbnail_text,
            example_word, primary_angle, primary_click_driver, title_thumbnail_relationship,
            brand_fit, copy_risk, package_score, topic_candidate_score, click_evidence_score,
            selected_for_production, production_reason)
        VALUES (?, ?, ?, ?, ?, ?, 'curiosity', 'curiosity_gap', 'complementary', 'high', 'low',
            ?, 80.0, 75.0, ?, 'top pick')
        """,
        (category, problem_id, title, title, thumbnail_text, example_word, package_score, selected),
    )
    return cur.lastrowid


class _FakeGemini:
    available = True

    def __init__(self, response):
        self._response = response

    def generate_json(self, prompt, max_output_tokens=6000):
        return self._response


def _valid_response(**overrides):
    base = {
        "viewer_contract": {
            "viewer_problem": "알파벳은 아는데 새 단어를 못 읽는다",
            "click_expectation": "KNIFE의 K가 왜 안 읽히는지 알고 싶다",
            "video_promise": "묵음 규칙을 이해하고 새 단어를 스스로 읽게 된다",
            "expected_transformation": "영상 전: 막연함 / 영상 후: 규칙을 알고 스스로 적용",
        },
        "core_question": "왜 KNIFE의 K는 안 읽힐까?",
        "core_answer": "KNIFE는 kn 묵음 규칙 때문에 K를 읽지 않는다",
        "learning_objectives": ["kn 묵음 규칙을 설명할 수 있다", "새 kn 단어를 읽을 수 있다"],
        "prerequisite_level": "very_beginner",
        "scope_in": ["kn 묵음 규칙", "대표 단어 4개"],
        "scope_out": ["다른 묵음 규칙 전체"],
        "example_ladder": [
            {"level": 1, "word": "KNIFE", "target_pattern": "kn 묵음", "purpose": "기본 확인", "difficulty": "easy", "exception_risk": "low"},
            {"level": 2, "word": "KNEE", "target_pattern": "kn 묵음", "purpose": "반복 확인", "difficulty": "easy", "exception_risk": "low"},
            {"level": 3, "word": "KNOW", "target_pattern": "kn 묵음", "purpose": "응용", "difficulty": "medium", "exception_risk": "low"},
            {"level": 4, "word": "KNIGHT", "target_pattern": "kn 묵음", "purpose": "도전", "difficulty": "medium", "exception_risk": "medium"},
        ],
        "hook": {
            "primary_hook_type": "misconception", "secondary_hook_type": "quiz",
            "opening_line": "KNIFE, 어떻게 읽으세요?", "gap_line": "많은 분들이 나이프라고 읽지만...",
            "promise_line": "오늘 그 이유를 알려드립니다.",
        },
        "sections": [
            {"section_number": i, "section_goal": f"단계 {i}", "viewer_question": "왜 K가 안 읽힐까",
             "key_point": "kn 묵음 규칙", "example": "KNIFE", "estimated_duration": "약 1분",
             "retention_device": "new_example" if i > 1 else "open_loop", "visual_type": "letter_highlight"}
            for i in range(1, 6)
        ],
        "mini_success": {"description": "KNOT을 스스로 읽어보게 한다", "prompt_word": "KNOT", "think_seconds": 3},
        "audio_visual": {"overall_audio_dependency": "medium", "overall_visual_dependency": "high", "notes": "자막 강조"},
        "shorts_candidates": [
            {"hook": "KNIFE 어떻게 읽어요?", "question": "K는 왜 안 읽힐까", "example": "KNIFE",
             "payoff": "kn 묵음 규칙 30초 요약", "source_section": 1, "estimated_duration": "약 30초"}
        ],
        "natural_next_topics": ["wr 묵음 규칙"],
        "external_clip_needed": False,
        "clip_purpose": None,
        "promise_feasibility_self_assessment": "strong",
        "promise_risk_reason": None,
        "brand_design_fit_self_assessment": "high",
        "brand_fit_reason": "채널 핵심 주제와 정확히 일치",
        "integrity_jargon_before_explained": "pass",
        "integrity_examples_match_rule": "pass",
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------
# 1: target package loading
# --------------------------------------------------------------------------

def test_select_target_package_picks_top_selected_for_production(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_package(conn, category="a", problem_id="p1", package_score=70.0, selected=1)
        best_id = _seed_package(conn, category="b", problem_id="p2", package_score=95.0, selected=1)

    package = select_target_package(db_path)
    assert package["id"] == best_id


def test_select_target_package_by_explicit_id(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        target_id = _seed_package(conn, category="a", problem_id="p1", package_score=50.0, selected=0)

    package = select_target_package(db_path, package_id=target_id)
    assert package["id"] == target_id


def test_select_target_package_none_when_nothing_selected(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_package(conn, selected=0)

    assert select_target_package(db_path) is None


# --------------------------------------------------------------------------
# 2: viewer contract
# --------------------------------------------------------------------------

def test_viewer_contract_has_four_fields():
    package = {"title": "t", "thumbnail_text": "th", "topic_text": "topic", "example_word": "KNIFE"}
    blueprint = generate_blueprint_content(package, _FakeGemini(_valid_response()), {})
    contract = blueprint["viewer_contract"]
    for field in ["viewer_problem", "click_expectation", "video_promise", "expected_transformation"]:
        assert contract.get(field)


# --------------------------------------------------------------------------
# 3: promise feasibility verification (backstop)
# --------------------------------------------------------------------------

def test_promise_feasibility_kept_when_example_covered_and_answer_overlaps():
    package = {"title": "왜 KNIFE의 K는 안 읽힐까?", "example_word": "KNIFE"}
    blueprint = _valid_response()
    feasibility, reason = verify_promise_feasibility(package, blueprint)
    assert feasibility == "strong"


def test_promise_feasibility_downgraded_when_example_not_covered_and_no_overlap():
    package = {"title": "왜 KNIFE의 K는 안 읽힐까?", "example_word": "KNIFE"}
    blueprint = _valid_response(
        example_ladder=[{"level": 1, "word": "PSALM", "target_pattern": "x", "purpose": "y", "difficulty": "easy", "exception_risk": "low"}],
        core_answer="영어는 재미있는 언어입니다",
        promise_feasibility_self_assessment="strong",
    )
    feasibility, reason = verify_promise_feasibility(package, blueprint)
    assert feasibility == "risky"
    assert reason


# --------------------------------------------------------------------------
# 4 & 5: single core question / core answer
# --------------------------------------------------------------------------

def test_core_question_and_answer_are_single_strings():
    package = {"title": "t", "thumbnail_text": "th", "topic_text": "topic", "example_word": "KNIFE"}
    blueprint = generate_blueprint_content(package, _FakeGemini(_valid_response()), {})
    assert isinstance(blueprint["core_question"], str) and blueprint["core_question"]
    assert isinstance(blueprint["core_answer"], str) and blueprint["core_answer"]


# --------------------------------------------------------------------------
# 6: learning objectives 1~3
# --------------------------------------------------------------------------

def test_learning_objectives_clamped_to_three():
    package = {"title": "t", "thumbnail_text": "th", "topic_text": "topic", "example_word": "KNIFE"}
    response = _valid_response(learning_objectives=["a", "b", "c", "d", "e"])
    blueprint = generate_blueprint_content(package, _FakeGemini(response), {})
    assert 1 <= len(blueprint["learning_objectives"]) <= 3


# --------------------------------------------------------------------------
# 7: scope IN/OUT separated
# --------------------------------------------------------------------------

def test_scope_in_and_out_present_and_separate():
    package = {"title": "t", "thumbnail_text": "th", "topic_text": "topic", "example_word": "KNIFE"}
    blueprint = generate_blueprint_content(package, _FakeGemini(_valid_response()), {})
    assert blueprint["scope_in"] and blueprint["scope_out"]
    assert set(blueprint["scope_in"]).isdisjoint(set(blueprint["scope_out"]))


# --------------------------------------------------------------------------
# 8: example ladder ordering
# --------------------------------------------------------------------------

def test_example_ladder_levels_are_ordered_one_to_four():
    package = {"title": "t", "thumbnail_text": "th", "topic_text": "topic", "example_word": "KNIFE"}
    blueprint = generate_blueprint_content(package, _FakeGemini(_valid_response()), {})
    levels = [e["level"] for e in blueprint["example_ladder"]]
    assert levels == sorted(levels)
    assert levels == [1, 2, 3, 4]


# --------------------------------------------------------------------------
# 9: example exception risk field present
# --------------------------------------------------------------------------

def test_example_ladder_entries_have_exception_risk():
    package = {"title": "t", "thumbnail_text": "th", "topic_text": "topic", "example_word": "KNIFE"}
    blueprint = generate_blueprint_content(package, _FakeGemini(_valid_response()), {})
    assert all("exception_risk" in e for e in blueprint["example_ladder"])


# --------------------------------------------------------------------------
# 10: hook taxonomy validated
# --------------------------------------------------------------------------

def test_invalid_hook_type_falls_back():
    package = {"title": "t", "thumbnail_text": "th", "topic_text": "topic", "example_word": "KNIFE"}
    response = _valid_response(hook={"primary_hook_type": "made_up", "secondary_hook_type": "also_fake",
                                      "opening_line": "a", "gap_line": "b", "promise_line": "c"})
    blueprint = generate_blueprint_content(package, _FakeGemini(response), {})
    assert blueprint["hook"]["primary_hook_type"] in HOOK_TYPES
    assert blueprint["hook"]["secondary_hook_type"] is None


# --------------------------------------------------------------------------
# 11: 5~8 sections
# --------------------------------------------------------------------------

def test_sections_between_five_and_eight():
    package = {"title": "t", "thumbnail_text": "th", "topic_text": "topic", "example_word": "KNIFE"}
    blueprint = generate_blueprint_content(package, _FakeGemini(_valid_response()), {})
    assert 5 <= len(blueprint["sections"]) <= 8


def test_too_many_sections_clamped_to_eight():
    package = {"title": "t", "thumbnail_text": "th", "topic_text": "topic", "example_word": "KNIFE"}
    sections = [
        {"section_number": i, "section_goal": "g", "viewer_question": "q", "key_point": "k",
         "example": "e", "estimated_duration": "1분", "retention_device": "new_example", "visual_type": "word_focus"}
        for i in range(1, 12)
    ]
    response = _valid_response(sections=sections)
    blueprint = generate_blueprint_content(package, _FakeGemini(response), {})
    assert len(blueprint["sections"]) == 8


# --------------------------------------------------------------------------
# 12: retention device taxonomy validated
# --------------------------------------------------------------------------

def test_invalid_retention_device_falls_back_to_none():
    package = {"title": "t", "thumbnail_text": "th", "topic_text": "topic", "example_word": "KNIFE"}
    sections = [
        {"section_number": 1, "section_goal": "g", "viewer_question": "q", "key_point": "k",
         "example": "e", "estimated_duration": "1분", "retention_device": "made_up_device", "visual_type": "word_focus"}
    ] + [
        {"section_number": i, "section_goal": "g", "viewer_question": "q", "key_point": "k",
         "example": "e", "estimated_duration": "1분", "retention_device": "new_example", "visual_type": "word_focus"}
        for i in range(2, 6)
    ]
    response = _valid_response(sections=sections)
    blueprint = generate_blueprint_content(package, _FakeGemini(response), {})
    assert blueprint["sections"][0]["retention_device"] is None
    assert all(s["retention_device"] in RETENTION_DEVICES or s["retention_device"] is None for s in blueprint["sections"])


# --------------------------------------------------------------------------
# 13: mini success minimum one
# --------------------------------------------------------------------------

def test_mini_success_present():
    package = {"title": "t", "thumbnail_text": "th", "topic_text": "topic", "example_word": "KNIFE"}
    blueprint = generate_blueprint_content(package, _FakeGemini(_valid_response()), {})
    assert blueprint["mini_success"]["description"]


# --------------------------------------------------------------------------
# 14: audio-first info present
# --------------------------------------------------------------------------

def test_audio_visual_info_present():
    package = {"title": "t", "thumbnail_text": "th", "topic_text": "topic", "example_word": "KNIFE"}
    blueprint = generate_blueprint_content(package, _FakeGemini(_valid_response()), {})
    assert blueprint["audio_visual"]["overall_audio_dependency"]
    assert blueprint["audio_visual"]["overall_visual_dependency"]


# --------------------------------------------------------------------------
# 15: visual type taxonomy validated
# --------------------------------------------------------------------------

def test_invalid_visual_type_falls_back():
    package = {"title": "t", "thumbnail_text": "th", "topic_text": "topic", "example_word": "KNIFE"}
    sections = [
        {"section_number": i, "section_goal": "g", "viewer_question": "q", "key_point": "k",
         "example": "e", "estimated_duration": "1분", "retention_device": "new_example", "visual_type": "made_up_visual"}
        for i in range(1, 6)
    ]
    response = _valid_response(sections=sections)
    blueprint = generate_blueprint_content(package, _FakeGemini(response), {})
    assert all(s["visual_type"] in VISUAL_TYPES for s in blueprint["sections"])


# --------------------------------------------------------------------------
# 16: shorts candidate minimum one
# --------------------------------------------------------------------------

def test_shorts_candidates_at_least_one():
    package = {"title": "t", "thumbnail_text": "th", "topic_text": "topic", "example_word": "KNIFE"}
    response = _valid_response(shorts_candidates=[])
    blueprint = generate_blueprint_content(package, _FakeGemini(response), {})
    assert len(blueprint["shorts_candidates"]) >= 1


# --------------------------------------------------------------------------
# 17: natural next topic
# --------------------------------------------------------------------------

def test_natural_next_topics_is_list():
    package = {"title": "t", "thumbnail_text": "th", "topic_text": "topic", "example_word": "KNIFE"}
    blueprint = generate_blueprint_content(package, _FakeGemini(_valid_response()), {})
    assert isinstance(blueprint["natural_next_topics"], list)


# --------------------------------------------------------------------------
# 18 & 19: content integrity check + ready_for_script gate
# --------------------------------------------------------------------------

def test_integrity_check_passes_for_well_formed_blueprint():
    package = {"title": "왜 KNIFE의 K는 안 읽힐까?", "example_word": "KNIFE"}
    blueprint = _valid_response()
    checks = run_integrity_check(package, blueprint)
    assert ready_for_script(checks) is True


def test_integrity_check_fails_when_example_not_covered():
    package = {"title": "왜 KNIFE의 K는 안 읽힐까?", "example_word": "KNIFE"}
    blueprint = _valid_response(
        example_ladder=[{"level": 1, "word": "PSALM", "target_pattern": "x", "purpose": "y", "difficulty": "easy", "exception_risk": "low"}],
        sections=[
            {"section_number": i, "section_goal": "g", "viewer_question": "q", "key_point": "k",
             "example": "PSALM", "estimated_duration": "1분", "retention_device": "new_example", "visual_type": "word_focus"}
            for i in range(1, 6)
        ],
    )
    checks = run_integrity_check(package, blueprint)
    assert checks["thumbnail_example_covered"] == "fail"
    assert ready_for_script(checks) is False


def test_integrity_check_fails_when_no_mini_success():
    package = {"title": "t", "example_word": None}
    blueprint = _valid_response(mini_success=None)
    checks = run_integrity_check(package, blueprint)
    assert checks["has_hands_on_moment"] == "fail"
    assert ready_for_script(checks) is False


def test_integrity_check_flags_high_exception_risk_early_example():
    package = {"title": "t", "example_word": None}
    blueprint = _valid_response()
    blueprint["example_ladder"][0]["exception_risk"] = "high"
    checks = run_integrity_check(package, blueprint)
    assert checks["no_exception_taught_as_rule"] == "fail"


# --------------------------------------------------------------------------
# 20: production complexity
# --------------------------------------------------------------------------

def test_production_complexity_low_for_minimal_blueprint():
    blueprint = _valid_response(shorts_candidates=[{"hook": "h", "question": "q", "example": "e", "payoff": "p",
                                                      "source_section": 1, "estimated_duration": "30s"}])
    assert estimate_production_complexity(blueprint) in {"low", "medium"}


def test_production_complexity_high_when_external_clip_needed_and_many_sections():
    sections = [
        {"section_number": i, "section_goal": "g", "viewer_question": "q", "key_point": "k",
         "example": "e", "estimated_duration": "1분", "retention_device": "new_example", "visual_type": "word_focus"}
        for i in range(1, 9)
    ]
    blueprint = _valid_response(
        sections=sections,
        example_ladder=[{"level": i, "word": "w", "target_pattern": "p", "purpose": "p", "difficulty": "easy", "exception_risk": "low"} for i in range(1, 5)],
        shorts_candidates=[{"hook": "h", "question": "q", "example": "e", "payoff": "p", "source_section": 1, "estimated_duration": "30s"} for _ in range(3)],
        external_clip_needed=True,
    )
    assert estimate_production_complexity(blueprint) == "high"


# --------------------------------------------------------------------------
# 21: blueprint score bounds
# --------------------------------------------------------------------------

def test_blueprint_score_within_bounds():
    blueprint = _valid_response()
    score = compute_blueprint_score(blueprint, brand_design_fit="high", production_complexity="low")
    assert 0.0 <= score <= 100.0


def test_blueprint_score_lower_for_weak_blueprint():
    strong = _valid_response()
    weak = _valid_response(mini_success=None, example_ladder=[])
    strong_score = compute_blueprint_score(strong, brand_design_fit="high", production_complexity="low")
    weak_score = compute_blueprint_score(weak, brand_design_fit="low", production_complexity="high")
    assert weak_score < strong_score


# --------------------------------------------------------------------------
# 22: earlier-stage scores untouched
# --------------------------------------------------------------------------

def test_earlier_stage_scores_unchanged_after_build(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_package(conn, package_score=88.0, selected=1)

    result = build_blueprint(db_path, _FakeGemini(_valid_response()), {})
    with connect(db_path) as conn:
        row = conn.execute("SELECT package_score, topic_candidate_score, click_evidence_score FROM content_packages").fetchone()
    assert row["package_score"] == 88.0
    assert row["topic_candidate_score"] == 80.0
    assert row["click_evidence_score"] == 75.0
    assert result["blueprint_score"] != row["package_score"]


# --------------------------------------------------------------------------
# report generation (used for real-data verification, and exercises persistence)
# --------------------------------------------------------------------------

def test_report_generation_produces_expected_sections(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_package(conn, selected=1)

    out_path = build_production_blueprint_report(db_path, tmp_path / "reports", _FakeGemini(_valid_response()), {})
    text = out_path.read_text(encoding="utf-8")
    for heading in [
        "# YouTube Production Blueprint",
        "## 1. 선택 Package",
        "## 2. Viewer Contract",
        "## 3. Core Question / Core Answer",
        "## 4. Learning Objectives",
        "## 5. Scope",
        "## 6. Example Ladder",
        "## 7. Opening Hook",
        "## 8. Long-form Structure",
        "## 9. Mini Success Point",
        "## 10. Audio-first / Visual Design",
        "## 11. Shorts Candidates",
        "## 12. Natural Next Topics",
        "## 13. Content Integrity Check",
        "## 14. Production Complexity",
        "## 15. Production Blueprint Score",
        "## 16. Ready for Script",
    ]:
        assert heading in text

    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM production_blueprints").fetchone()
    assert row is not None
    assert row["ready_for_script"] in (0, 1)
    assert json.loads(row["sections_json"])


def test_report_raises_when_no_package_selected(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    try:
        build_production_blueprint_report(db_path, tmp_path / "reports", _FakeGemini(_valid_response()), {})
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_fallback_used_when_gemini_unavailable(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_package(conn, selected=1)

    out_path = build_production_blueprint_report(db_path, tmp_path / "reports", None, {})
    assert out_path.exists()
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM production_blueprints").fetchone()
    assert row is not None


# --------------------------------------------------------------------------
# 08-1 regression tests: real-output bugs found by human review of
# reports/production_blueprint_2026-08-17.md
# --------------------------------------------------------------------------

# CASE A: BAG must not be flattened into a single Hangul reading ("백") that erases the /g/-/k/
# contrast, and a word must not be given two conflicting Hangul readings at once ("배트/뱃").

def test_phoneme_check_fails_on_fixed_equivalence_hiding_g_k_contrast():
    blueprint = _valid_response(
        sections=[
            {"section_number": 1, "section_goal": "g", "viewer_question": "q", "key_point": "k",
             "example": "B(/ㅂ/) + A(/애/) + G(/ㄱ/)가 빠르게 만나면 '백(BAG)'이 된다.",
             "estimated_duration": "1분", "retention_device": "open_loop", "visual_type": "word_focus"}
        ] + [
            {"section_number": i, "section_goal": "g", "viewer_question": "q", "key_point": "k",
             "example": "e", "estimated_duration": "1분", "retention_device": "new_example", "visual_type": "word_focus"}
            for i in range(2, 6)
        ],
    )
    assert check_phoneme_explanation_safe(blueprint) == "fail"


def test_phoneme_check_passes_when_ipa_phoneme_is_explicit():
    blueprint = _valid_response(
        sections=[
            {"section_number": 1, "section_goal": "g", "viewer_question": "q", "key_point": "k",
             "example": "B /b/ + A /æ/ + G /g/ 가 만나면 BAG(백)이 된다. BAG의 끝소리는 /g/입니다.",
             "estimated_duration": "1분", "retention_device": "open_loop", "visual_type": "word_focus"}
        ] + [
            {"section_number": i, "section_goal": "g", "viewer_question": "q", "key_point": "k",
             "example": "e", "estimated_duration": "1분", "retention_device": "new_example", "visual_type": "word_focus"}
            for i in range(2, 6)
        ],
    )
    assert check_phoneme_explanation_safe(blueprint) == "pass"


def test_phoneme_check_fails_on_dual_hangul_reading():
    blueprint = _valid_response(
        sections=[
            {"section_number": i, "section_goal": "g", "viewer_question": "q",
             "key_point": "BA(배) + T(ㅌ) = BAT(배트/뱃)" if i == 1 else "k",
             "example": "e", "estimated_duration": "1분", "retention_device": "new_example", "visual_type": "word_focus"}
            for i in range(1, 6)
        ],
    )
    assert check_phoneme_explanation_safe(blueprint) == "fail"


# CASE B: a single letter's sound must be scoped to the current example word, not stated as a
# universal rule.

def test_scope_check_fails_on_unscoped_letter_generalization():
    blueprint = _valid_response(
        sections=[
            {"section_number": i, "section_goal": "g", "viewer_question": "q",
             "key_point": "C의 소리는 'ㅋ', A는 '애', P는 'ㅍ'이므로 합치면 CAP이다." if i == 1 else "k",
             "example": "e", "estimated_duration": "1분", "retention_device": "new_example", "visual_type": "word_focus"}
            for i in range(1, 6)
        ],
    )
    assert check_example_scope_safe(blueprint) == "fail"


def test_scope_check_passes_when_scoped_to_current_word():
    blueprint = _valid_response(
        sections=[
            {"section_number": i, "section_goal": "g", "viewer_question": "q",
             "key_point": "CAP에서는 C가 /k/ 소리를 냅니다." if i == 1 else "k",
             "example": "e", "estimated_duration": "1분", "retention_device": "new_example", "visual_type": "word_focus"}
            for i in range(1, 6)
        ],
    )
    assert check_example_scope_safe(blueprint) == "pass"


# CASE C: Video Promise / Expected Transformation must not promise more than Learning
# Objectives / Scope IN actually cover.

def test_promise_scope_check_fails_when_transformation_broader_than_scope():
    blueprint = _valid_response(
        learning_objectives=["kn 묵음 규칙을 설명할 수 있다"],
        scope_in=["kn 묵음 규칙"],
        viewer_contract={
            "viewer_problem": "새 단어를 못 읽는다",
            "click_expectation": "읽는 법을 알고 싶다",
            "video_promise": "모든 단모음 단어를 완벽하게 읽게 해준다",
            "expected_transformation": "처음 보는 어떤 단어든 무조건 바로 읽을 수 있게 된다",
        },
    )
    assert check_promise_matches_scope(blueprint) == "fail"


def test_promise_scope_check_passes_when_transformation_matches_scope():
    blueprint = _valid_response(
        learning_objectives=["kn 묵음 규칙을 설명할 수 있다"],
        scope_in=["kn 묵음 규칙"],
        viewer_contract={
            "viewer_problem": "새 단어를 못 읽는다",
            "click_expectation": "읽는 법을 알고 싶다",
            "video_promise": "kn 묵음 규칙을 이해하고 관련 단어를 읽는 방법을 익힌다",
            "expected_transformation": "kn 묵음 규칙이 들어간 단어를 스스로 읽어볼 수 있게 된다",
        },
    )
    assert check_promise_matches_scope(blueprint) == "pass"


def test_integrity_check_includes_new_08_1_items_and_fails_ready_for_script():
    package = {"title": "왜 KNIFE의 K는 안 읽힐까?", "example_word": "KNIFE"}
    blueprint = _valid_response(
        sections=[
            {"section_number": 1, "section_goal": "g", "viewer_question": "q",
             "key_point": "C의 소리는 'ㅋ'이다.",
             "example": "e", "estimated_duration": "1분", "retention_device": "open_loop", "visual_type": "word_focus"}
        ] + [
            {"section_number": i, "section_goal": "g", "viewer_question": "q", "key_point": "k",
             "example": "e", "estimated_duration": "1분", "retention_device": "new_example", "visual_type": "word_focus"}
            for i in range(2, 6)
        ],
    )
    checks = run_integrity_check(package, blueprint)
    assert "phoneme_explanation_safe" in checks
    assert "example_scope_safe" in checks
    assert "promise_matches_scope" in checks
    assert checks["example_scope_safe"] == "fail"
    assert ready_for_script(checks) is False


# CASE D: the existing BAG -> BAT -> MAP -> CAP example ladder must survive sanitation
# unchanged (08-1 keeps the ladder itself, only the phrasing around it changes).

def test_example_ladder_words_pass_through_sanitize_unchanged():
    package = {"title": "t", "thumbnail_text": "th", "topic_text": "topic", "example_word": "BAG"}
    response = _valid_response(
        example_ladder=[
            {"level": 1, "word": "BAG", "target_pattern": "CVC", "purpose": "p", "difficulty": "easy", "exception_risk": "low"},
            {"level": 2, "word": "BAT", "target_pattern": "CVC", "purpose": "p", "difficulty": "easy", "exception_risk": "low"},
            {"level": 3, "word": "MAP", "target_pattern": "CVC", "purpose": "p", "difficulty": "medium", "exception_risk": "low"},
            {"level": 4, "word": "CAP", "target_pattern": "CVC", "purpose": "p", "difficulty": "medium", "exception_risk": "medium"},
        ],
    )
    blueprint = generate_blueprint_content(package, _FakeGemini(response), {})
    words = [e["word"] for e in blueprint["example_ladder"]]
    assert words == ["BAG", "BAT", "MAP", "CAP"]


# ---------------------------------------------------------------------------
# 09-5: Mini Success target lineage backstops (spec sections 28-29)
# ---------------------------------------------------------------------------

def _bag_ladder():
    return [
        {"level": 1, "word": "CAT", "target_pattern": "C /k/ + A /æ/ + T /t/", "purpose": "p", "difficulty": "easy", "exception_risk": "low"},
        {"level": 2, "word": "BAT", "target_pattern": "B /b/ + A /æ/ + T /t/", "purpose": "p", "difficulty": "easy", "exception_risk": "low"},
        {"level": 3, "word": "BAG", "target_pattern": "B /b/ + A /æ/ + G /g/", "purpose": "p", "difficulty": "medium", "exception_risk": "low"},
        {"level": 4, "word": "MAP", "target_pattern": "M /m/ + A /æ/ + P /p/", "purpose": "p", "difficulty": "medium", "exception_risk": "low"},
    ]


# CASE A: 08 Practice=MAP, 08 MiniSuccess=CAP -- independent target preserved.
def test_case_a_independent_new_target_passes_novelty_and_material_checks():
    blueprint = {"example_ladder": _bag_ladder(), "mini_success": {"description": "CAP을 스스로 읽어본다", "prompt_word": "CAP", "think_seconds": 3}}
    assert check_mini_success_target_novel_safe(blueprint) == "pass"
    assert check_mini_success_uses_learned_material_safe(blueprint) == "pass"


# CASE C: 08 itself already has Practice=MAP, MiniSuccess=MAP -- upstream design issue detected.
def test_case_c_reusing_the_fully_scaffolded_practice_word_fails_novelty():
    blueprint = {"example_ladder": _bag_ladder(), "mini_success": {"description": "MAP을 스스로 읽어본다", "prompt_word": "MAP", "think_seconds": 3}}
    assert check_mini_success_target_novel_safe(blueprint) == "fail"


def test_legacy_equation_style_prompt_word_still_caught_by_novelty_check():
    # The exact real-data shape found in production_blueprints -- prompt_word bakes the answer
    # phonemes in and still names the practiced word, even with no clean [A-Z]{2,} token to extract.
    blueprint = {
        "example_ladder": _bag_ladder(),
        "mini_success": {"description": "MAP 단어를 3초 안에 스스로 소리 내어 읽어보는 퀴즈", "prompt_word": "M /m/ + A /æ/ + P /p/ = ?", "think_seconds": 3},
    }
    assert check_mini_success_target_novel_safe(blueprint) == "fail"


# CASE D: CAP's required phonemes (C/A/P) are all a subset of the learned inventory -- pass.
def test_case_d_novel_target_using_only_learned_phonemes_passes():
    blueprint = {"example_ladder": _bag_ladder(), "mini_success": {"prompt_word": "CAP"}}
    assert check_mini_success_uses_learned_material_safe(blueprint) == "pass"


# CASE E: a target requiring an unlearned letter/sound fails.
def test_case_e_target_requiring_unlearned_letter_fails():
    blueprint = {"example_ladder": _bag_ladder(), "mini_success": {"prompt_word": "DOG"}}
    assert check_mini_success_uses_learned_material_safe(blueprint) == "fail"


def test_mini_success_lineage_checks_wired_into_full_integrity_check():
    package = {"title": "t", "example_word": "MAP"}
    blueprint = _valid_response(
        example_ladder=_bag_ladder(),
        mini_success={"description": "CAP을 스스로 읽어본다", "prompt_word": "CAP", "think_seconds": 3},
    )
    checks = run_integrity_check(package, blueprint)
    assert checks["mini_success_target_novel_safe"] == "pass"
    assert checks["mini_success_uses_learned_material_safe"] == "pass"


def test_mini_success_reused_target_fails_full_integrity_gate():
    package = {"title": "t", "example_word": "MAP"}
    blueprint = _valid_response(
        example_ladder=_bag_ladder(),
        mini_success={"description": "MAP을 스스로 읽어본다", "prompt_word": "MAP", "think_seconds": 3},
    )
    checks = run_integrity_check(package, blueprint)
    assert checks["mini_success_target_novel_safe"] == "fail"
    assert ready_for_script(checks) is False


# 09-5 section 19: "고유한 소리" scoped-exception regression, found in live Gemini output --
# "이 단어 안에서 내는 고유한 소리" must fail regardless of the "이 단어" scoping phrase nearby.
def test_generic_letter_sound_claim_fails_even_when_softly_scoped():
    text = "각 글자가 이 단어 안에서 내는 고유한 소리를 순서대로 이어 붙이는 것입니다."
    assert check_example_scope_safe({"core_answer": text}) == "fail"
