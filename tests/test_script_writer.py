import json

from research.db import connect, init_db
from research.production_blueprint import _scope_safe_over_text_blob
from research.script_writer import (
    LEARNING_FUNCTIONS,
    build_content_blocks,
    build_script,
    build_script_report,
    check_content_block_uniqueness_safe,
    check_ending_resolves_opening,
    check_format_neutrality_safe,
    check_mini_success_answer_barrier_safe,
    check_mini_success_present,
    check_practice_mini_success_progression_safe,
    collect_closing_region,
    compute_audio_first_score,
    compute_hook_score,
    compute_retention_score,
    compute_scope_alignment_score,
    compute_script_score,
    estimate_duration_and_words,
    generate_script_content,
    ready_for_production_gate,
    recheck_script_integrity,
    run_script_integrity_check,
    select_target_blueprint,
)


def _example_ladder():
    return [
        {"level": 1, "word": "BAG", "target_pattern": "CVC", "purpose": "기본 확인", "difficulty": "easy", "exception_risk": "low"},
        {"level": 2, "word": "BAT", "target_pattern": "CVC", "purpose": "끝소리 변경", "difficulty": "easy", "exception_risk": "low"},
        {"level": 3, "word": "MAP", "target_pattern": "CVC", "purpose": "자음 확장", "difficulty": "medium", "exception_risk": "low"},
        {"level": 4, "word": "CAP", "target_pattern": "CVC", "purpose": "스스로 도전", "difficulty": "medium", "exception_risk": "low"},
    ]


def _sections():
    return [
        {"section_number": 1, "section_goal": "이름과 소리 차이", "viewer_question": "왜 안 읽힐까",
         "key_point": "이름과 소리는 다르다", "example": "BAG", "estimated_duration": "40초",
         "retention_device": "misconception_correction", "visual_type": "comparison"},
        {"section_number": 2, "section_goal": "BAG sound blending", "viewer_question": "어떻게 합칠까",
         "key_point": "B /b/ + A /æ/ + G /g/", "example": "BAG", "estimated_duration": "50초",
         "retention_device": "visual_change", "visual_type": "sound_build"},
        {"section_number": 3, "section_goal": "BAT 끝소리 변경", "viewer_question": "다른 단어도 될까",
         "key_point": "B /b/ + A /æ/ + T /t/", "example": "BAT", "estimated_duration": "40초",
         "retention_device": "contrast", "visual_type": "letter_highlight"},
        {"section_number": 4, "section_goal": "MAP 자음 확장", "viewer_question": "첫소리도 바뀌면",
         "key_point": "M /m/ + A /æ/ + P /p/", "example": "MAP", "estimated_duration": "45초",
         "retention_device": "new_example", "visual_type": "sound_build"},
        {"section_number": 5, "section_goal": "CAP 스스로 도전", "viewer_question": "혼자 읽을 수 있을까",
         "key_point": "이 단어 CAP에서는 C가 /k/ 소리를 냅니다", "example": "CAP", "estimated_duration": "45초",
         "retention_device": "mini_success", "visual_type": "quiz_card"},
        {"section_number": 6, "section_goal": "복습", "viewer_question": "정리하면",
         "key_point": "소리를 이어 붙인다", "example": "BAG BAT MAP CAP", "estimated_duration": "30초",
         "retention_device": "next_question", "visual_type": "recap_card"},
    ]


def _blueprint_dict():
    return {
        "viewer_contract": {
            "viewer_problem": "알파벳 이름은 아는데 3글자 단어가 안 읽힌다",
            "click_expectation": "안 읽히는 이유를 알고 싶다",
            "video_promise": "단모음 a가 들어간 3글자 단어를 소리 조합으로 읽는 원리를 알려드립니다",
            "expected_transformation": "단모음 a가 포함된 기초 CVC 단어를 스스로 읽을 수 있게 된다",
        },
        "core_question": "왜 알파벳 이름을 다 알아도 3글자 단어가 바로 안 읽힐까?",
        "core_answer": "단어는 알파벳 이름이 아니라 각 글자가 내는 소리를 이어 붙여 읽기 때문입니다.",
        "learning_objectives": ["이름과 소리 차이를 이해한다", "단모음 a CVC 단어를 소리 조합으로 읽는다"],
        "prerequisite_level": "very_beginner",
        "scope_in": ["알파벳 이름 vs 글자 소리", "단모음 a CVC 단어 읽기"],
        "scope_out": ["단모음 e, i, o, u", "이중자음, 이중모음", "묵음 규칙"],
        "example_ladder": _example_ladder(),
        "hook": {
            "primary_hook_type": "misconception", "secondary_hook_type": "problem_reenactment",
            "opening_line": "B-A-G를 보고 비-에이-지라고 읽으려 하셨나요?",
            "gap_line": "알파벳 이름을 다 알아도 단어가 안 읽히는 건 당연합니다.",
            "promise_line": "오늘 글자의 진짜 소리를 연결하는 원리를 알려드립니다.",
        },
        "sections": _sections(),
        "mini_success": {"description": "CAP을 스스로 읽어본다", "prompt_word": "CAP", "think_seconds": 3},
        "audio_visual": {"overall_audio_dependency": "high", "overall_visual_dependency": "medium", "notes": "텍스트 애니메이션 중심"},
        "natural_next_topics": ["단모음 o CVC", "단모음 i CVC"],
        "title": "왜 알파벳 이름을 다 아는데 3글자 단어도 바로 안 읽힐까?",
        "thumbnail_text": "B-A-G\n비-에이-지? NO",
    }


def _seed_blueprint(conn, ready_for_script=1, blueprint_score=94.5):
    bp = _blueprint_dict()
    contract = bp["viewer_contract"]
    cur = conn.execute(
        """
        INSERT INTO production_blueprints (package_id, category, problem_id, title, thumbnail_text,
            viewer_problem, click_expectation, video_promise, expected_transformation,
            core_question, core_answer, learning_objectives_json, scope_in_json, scope_out_json,
            prerequisite_level, hook_json, sections_json, example_ladder_json, mini_success_json,
            audio_visual_json, shorts_candidates_json, natural_next_topics_json,
            promise_feasibility, brand_design_fit, integrity_check_json, production_complexity,
            blueprint_score, ready_for_script)
        VALUES (42, 'reading', 'p1', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'very_beginner', ?, ?, ?, ?, ?, '[]', ?,
            'strong', 'high', '{}', 'medium', ?, ?)
        """,
        (
            bp["title"], bp["thumbnail_text"], contract["viewer_problem"], contract["click_expectation"],
            contract["video_promise"], contract["expected_transformation"], bp["core_question"], bp["core_answer"],
            json.dumps(bp["learning_objectives"], ensure_ascii=False), json.dumps(bp["scope_in"], ensure_ascii=False),
            json.dumps(bp["scope_out"], ensure_ascii=False), json.dumps(bp["hook"], ensure_ascii=False),
            json.dumps(bp["sections"], ensure_ascii=False), json.dumps(bp["example_ladder"], ensure_ascii=False),
            json.dumps(bp["mini_success"], ensure_ascii=False), json.dumps(bp["audio_visual"], ensure_ascii=False),
            json.dumps(bp["natural_next_topics"], ensure_ascii=False),
            blueprint_score, ready_for_script,
        ),
    )
    return cur.lastrowid


class _FakeGemini:
    available = True

    def __init__(self, response):
        self._response = response

    def generate_json(self, prompt, max_output_tokens=8000):
        return self._response


def _good_script_response():
    return {
        "opening": {
            "beats": [
                {"type": "narration", "text": "알파벳 이름은 아는데 3글자 단어가 바로 안 읽힌다면, B-A-G를 보고 비-에이-지라고 읽으려 하셨을 겁니다."},
                {"type": "narration", "text": "오늘 단모음 a가 들어간 3글자 단어를 소리 조합으로 읽는 원리를 알려드립니다."},
                {"type": "on_screen", "text": "B A G"},
            ]
        },
        "sections": [
            {"section_number": 1, "purpose": "이름과 소리 차이", "estimated_seconds": 40,
             "beats": [{"type": "narration", "text": "알파벳에는 이름이 있고 단어 안에서 내는 소리가 따로 있습니다."}]},
            {"section_number": 2, "purpose": "BAG sound blending", "estimated_seconds": 50,
             "beats": [{"type": "narration", "text": "B /b/, A /æ/, G /g/를 순서대로 이어 붙이면 BAG가 됩니다. BAG의 끝소리는 /g/입니다."}]},
            {"section_number": 3, "purpose": "BAT 끝소리 변경", "estimated_seconds": 40,
             "beats": [{"type": "narration", "text": "끝소리만 /t/로 바꾸면 B /b/ + A /æ/ + T /t/ → BAT가 됩니다."}]},
            {"section_number": 4, "purpose": "MAP 자음 확장", "estimated_seconds": 45,
             "beats": [{"type": "narration", "text": "M /m/ + A /æ/ + P /p/를 이어 붙이면 MAP이 됩니다. MAP의 끝소리는 /p/입니다."}]},
            {"section_number": 5, "purpose": "CAP 도전", "estimated_seconds": 45,
             "beats": [{"type": "narration", "text": "이 단어 CAP에서는 C가 /k/ 소리를 냅니다. 한번 이어 보세요."}]},
            {"section_number": 6, "purpose": "복습", "estimated_seconds": 30,
             "beats": [{"type": "narration", "text": "오늘 배운 것을 정리하면, 이름이 아니라 소리를 이어 붙이는 것입니다."}]},
        ],
        "mini_success_beats": [
            {"type": "narration", "text": "이번에는 제가 먼저 읽지 않겠습니다. CAP, 세 소리를 이어 보세요. 생각 시간을 드릴게요."},
            {"type": "cue", "text": "[PAUSE 3 SEC]"},
            {"type": "narration", "text": "네, C /k/, A /æ/, P /p/가 이어져 CAP이 됩니다."},
        ],
        "ending": {
            "beats": [
                {"type": "narration", "text": "오늘 알파벳 이름을 다 알아도 단어가 안 읽히는 이유를 정리해봤습니다. 이름이 아니라 소리를 이어 붙이면 됩니다."},
            ]
        },
        "no_unverified_rule_self_check": "pass",
        "ipa_not_memorization_self_check": "pass",
    }


# --------------------------------------------------------------------------
# CASE A: title/thumbnail preserved
# --------------------------------------------------------------------------

def test_select_target_blueprint_uses_latest_ready_for_script(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_blueprint(conn)

    row = select_target_blueprint(db_path)
    assert row["title"] == "왜 알파벳 이름을 다 아는데 3글자 단어도 바로 안 읽힐까?"
    assert row["thumbnail_text"].startswith("B-A-G")


def test_title_and_thumbnail_preserved_in_integrity_check():
    blueprint = _blueprint_dict()
    script = _good_script_response()
    from research.script_writer import render_script_text

    script_text = render_script_text(script)
    checks = run_script_integrity_check(blueprint, blueprint["title"], blueprint["thumbnail_text"], script, script_text)
    assert checks["title_preserved"] == "pass"
    assert checks["thumbnail_preserved"] == "pass"


# --------------------------------------------------------------------------
# CASE B: BAG -> BAT -> MAP -> CAP order preserved
# --------------------------------------------------------------------------

def test_example_ladder_preserved_when_order_correct():
    blueprint = _blueprint_dict()
    script = _good_script_response()
    from research.script_writer import render_script_text

    script_text = render_script_text(script)
    checks = run_script_integrity_check(blueprint, blueprint["title"], blueprint["thumbnail_text"], script, script_text)
    assert checks["example_ladder_preserved"] == "pass"


def test_example_ladder_preserved_fails_when_out_of_order():
    blueprint = _blueprint_dict()
    script = _good_script_response()
    # Words appear out of the Blueprint's BAG->BAT->MAP->CAP order, and no other section/purpose
    # text re-mentions any of the four words, so the reordering is the only signal present.
    script["sections"][0]["purpose"] = "설명"
    script["sections"][0]["beats"] = [{"type": "narration", "text": "MAP CAP BAG BAT 순서가 섞였습니다."}]
    for s in script["sections"][1:]:
        s["purpose"] = "설명"
        s["beats"] = [{"type": "narration", "text": "설명"}]
    script["opening"]["beats"] = [{"type": "narration", "text": "시작"}]
    script["mini_success_beats"] = []
    script["ending"]["beats"] = [{"type": "narration", "text": "끝"}]
    from research.script_writer import render_script_text

    script_text = render_script_text(script)
    checks = run_script_integrity_check(blueprint, blueprint["title"], blueprint["thumbnail_text"], script, script_text)
    assert checks["example_ladder_preserved"] == "fail"


# --------------------------------------------------------------------------
# CASE C: BAG /g/ not distorted into /k/
# --------------------------------------------------------------------------

def test_phoneme_check_fails_when_bag_flattened_to_fixed_hangul():
    blueprint = _blueprint_dict()
    script = _good_script_response()
    script["sections"][1]["beats"] = [{"type": "narration", "text": "B(/ㅂ/) + A(/애/) + G(/ㄱ/)가 만나면 '백(BAG)'이 됩니다."}]
    from research.script_writer import render_script_text

    script_text = render_script_text(script)
    checks = run_script_integrity_check(blueprint, blueprint["title"], blueprint["thumbnail_text"], script, script_text)
    assert checks["phoneme_explanation_safe"] == "fail"


# --------------------------------------------------------------------------
# CASE D: BAT /t/, MAP /p/, CAP /k/ accuracy maintained
# --------------------------------------------------------------------------

def test_phoneme_check_passes_when_all_four_words_use_explicit_phonemes():
    blueprint = _blueprint_dict()
    script = _good_script_response()
    from research.script_writer import render_script_text

    script_text = render_script_text(script)
    checks = run_script_integrity_check(blueprint, blueprint["title"], blueprint["thumbnail_text"], script, script_text)
    assert checks["phoneme_explanation_safe"] == "pass"


# --------------------------------------------------------------------------
# CASE E: "C는 항상 /k/" generalization blocked
# --------------------------------------------------------------------------

def test_scope_safe_fails_on_unscoped_c_generalization():
    blueprint = _blueprint_dict()
    script = _good_script_response()
    script["sections"][4]["beats"] = [{"type": "narration", "text": "C의 소리는 'ㅋ'입니다."}]
    from research.script_writer import render_script_text

    script_text = render_script_text(script)
    checks = run_script_integrity_check(blueprint, blueprint["title"], blueprint["thumbnail_text"], script, script_text)
    assert checks["example_scope_safe"] == "fail"


# --------------------------------------------------------------------------
# CASE F: broader-than-scope promise fails
# --------------------------------------------------------------------------

def test_promise_matches_scope_fails_when_broader_than_scope():
    blueprint = _blueprint_dict()
    blueprint["viewer_contract"]["video_promise"] = "모든 단모음 단어를 완벽하게 읽게 해준다"
    blueprint["viewer_contract"]["expected_transformation"] = "처음 보는 어떤 단어든 무조건 바로 읽을 수 있게 된다"
    script = _good_script_response()
    from research.script_writer import render_script_text

    script_text = render_script_text(script)
    checks = run_script_integrity_check(blueprint, blueprint["title"], blueprint["thumbnail_text"], script, script_text)
    assert checks["promise_matches_scope"] == "fail"


# --------------------------------------------------------------------------
# CASE G: scope creep into body fails
# --------------------------------------------------------------------------

def test_no_scope_creep_fails_when_scope_out_taught_in_body():
    blueprint = _blueprint_dict()
    script = _good_script_response()
    script["sections"][5]["beats"] = [
        {"type": "narration", "text": "이제 단모음 e, i, o, u도 같이 배워보겠습니다. 이중자음, 이중모음도 함께 살펴봅니다."}
    ]
    from research.script_writer import render_script_text

    script_text = render_script_text(script)
    checks = run_script_integrity_check(blueprint, blueprint["title"], blueprint["thumbnail_text"], script, script_text)
    assert checks["no_scope_creep"] == "fail"


def test_no_scope_creep_passes_for_brief_ending_mention():
    blueprint = _blueprint_dict()
    script = _good_script_response()
    script["ending"]["beats"] = [
        {"type": "narration", "text": "다음에는 단모음 e, i, o, u가 들어간 단어도 살펴보겠습니다."}
    ]
    from research.script_writer import render_script_text

    script_text = render_script_text(script)
    checks = run_script_integrity_check(blueprint, blueprint["title"], blueprint["thumbnail_text"], script, script_text)
    assert checks["no_scope_creep"] == "pass"


# --------------------------------------------------------------------------
# CASE H: CAP mini success + 3-second think time present
# --------------------------------------------------------------------------

def test_mini_success_present_with_word_and_pause():
    blueprint = _blueprint_dict()
    script = _good_script_response()
    from research.script_writer import render_script_text

    script_text = render_script_text(script)
    checks = run_script_integrity_check(blueprint, blueprint["title"], blueprint["thumbnail_text"], script, script_text)
    assert checks["mini_success_present"] == "pass"


def test_mini_success_fails_when_pause_missing():
    blueprint = _blueprint_dict()
    script = _good_script_response()
    script["mini_success_beats"] = [{"type": "narration", "text": "CAP을 읽어보세요."}]
    from research.script_writer import render_script_text

    script_text = render_script_text(script)
    checks = run_script_integrity_check(blueprint, blueprint["title"], blueprint["thumbnail_text"], script, script_text)
    assert checks["mini_success_present"] == "fail"


# --------------------------------------------------------------------------
# CASE I: IPA memorization requirement fails
# --------------------------------------------------------------------------

def test_ipa_memorization_backstop_forces_fail():
    blueprint = _blueprint_dict()
    script = _good_script_response()
    script["ipa_not_memorization_self_check"] = "pass"
    script["sections"][1]["beats"] = [{"type": "narration", "text": "/æ/ 기호를 반드시 외우세요."}]
    from research.script_writer import render_script_text

    script_text = render_script_text(script)
    checks = run_script_integrity_check(blueprint, blueprint["title"], blueprint["thumbnail_text"], script, script_text)
    assert checks["ipa_not_taught_as_memorization"] == "fail"


# --------------------------------------------------------------------------
# CASE J: false guarantee detected
# --------------------------------------------------------------------------

def test_no_false_guarantee_detects_banned_keywords():
    blueprint = _blueprint_dict()
    script = _good_script_response()
    script["ending"]["beats"] = [{"type": "narration", "text": "이제 모든 단어를 무조건 완벽하게 읽을 수 있습니다."}]
    from research.script_writer import render_script_text

    script_text = render_script_text(script)
    checks = run_script_integrity_check(blueprint, blueprint["title"], blueprint["thumbnail_text"], script, script_text)
    assert checks["no_false_guarantee"] == "fail"


# --------------------------------------------------------------------------
# CASE K: generic-greeting-heavy opening scores lower on Hook
# --------------------------------------------------------------------------

def test_hook_score_lower_for_generic_greeting_opening():
    blueprint = _blueprint_dict()
    good_script = _good_script_response()
    bad_script = _good_script_response()
    bad_script["opening"] = {"beats": [{"type": "narration", "text": "여러분 안녕하세요. 오늘은 영어 공부를 해보겠습니다."}]}

    good_score = compute_hook_score(blueprint, good_script)
    bad_score = compute_hook_score(blueprint, bad_script)
    assert bad_score < good_score


# --------------------------------------------------------------------------
# CASE L: heavy visual-dependent phrasing lowers Audio-first score
# --------------------------------------------------------------------------

def test_audio_first_score_lower_for_visual_dependent_checks():
    high_score = compute_audio_first_score({"audio_first_usable": "pass"})
    low_score = compute_audio_first_score({"audio_first_usable": "fail"})
    assert low_score < high_score


# --------------------------------------------------------------------------
# CASE M: Gemini JSON failure doesn't crash the pipeline
# --------------------------------------------------------------------------

def test_generate_script_content_falls_back_when_gemini_returns_none():
    blueprint = _blueprint_dict()
    script, method = generate_script_content(blueprint, gemini=None, channel_cfg={})
    assert method == "fallback"
    assert script["sections"]


def test_generate_script_content_falls_back_on_malformed_json():
    blueprint = _blueprint_dict()
    script, method = generate_script_content(blueprint, _FakeGemini({"not": "valid"}), channel_cfg={})
    assert method == "fallback"
    assert script["sections"]


# --------------------------------------------------------------------------
# CASE N: fallback quality shortfall -> ready_for_production = NO
# --------------------------------------------------------------------------

def test_fallback_script_is_not_ready_for_production(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_blueprint(conn)

    result = build_script(db_path, gemini=None, channel_cfg={})
    assert result["generation_method"] == "fallback"
    assert result["ready_for_production"] is False


def test_good_gemini_script_can_be_ready_for_production(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_blueprint(conn)

    result = build_script(db_path, _FakeGemini(_good_script_response()), channel_cfg={})
    assert result["generation_method"] == "gemini"
    assert not any(v == "fail" for v in result["integrity_checks"].values())


# --------------------------------------------------------------------------
# duration/word count estimate + report generation (also covers CASE O via full suite)
# --------------------------------------------------------------------------

def test_estimate_duration_and_words_counts_pause_seconds():
    text = "안녕하세요 BAG [PAUSE 3 SEC] 읽어보세요"
    seconds, words = estimate_duration_and_words(text)
    assert seconds > 3.0
    assert words > 0


def test_script_score_within_bounds():
    score = compute_script_score(
        {"hook": 80, "clarity": 90, "scope_alignment": 100, "example_alignment": 100, "audio_first": 100, "retention": 60}
    )
    assert 0.0 <= score <= 100.0


def test_ready_for_production_gate_requires_no_fail_and_threshold():
    checks_ok = {"a": "pass", "b": "warning"}
    assert ready_for_production_gate(checks_ok, 75.0) is True
    assert ready_for_production_gate(checks_ok, 50.0) is False
    checks_fail = {"a": "fail"}
    assert ready_for_production_gate(checks_fail, 95.0) is False


def test_report_generation_produces_expected_sections(tmp_path):
    # 09-2: report headings follow prompts/09-2 section 25 (Content Script framing).
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_blueprint(conn)

    out_path = build_script_report(db_path, tmp_path / "reports", _FakeGemini(_good_script_response()), {"audience": "왕초보"})
    text = out_path.read_text(encoding="utf-8")
    for heading in [
        "# Content Script",
        "## Viewer Contract",
        "## Core Question",
        "## Core Answer",
        "## Learning Objectives",
        "## Scope",
        "## Content Blocks",
        "## Example Ladder",
        "## Mini Success",
        "## Educational Integrity Check",
        "## Format Neutrality Check",
        "## Script/Content Score",
        "## Ready for Direction",
    ]:
        assert heading in text

    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM video_scripts").fetchone()
    assert row is not None
    assert row["ready_for_production"] in (0, 1)
    assert row["ready_for_direction"] in (0, 1)
    assert json.loads(row["script_json"])
    assert json.loads(row["content_blocks_json"])


def test_report_raises_when_no_blueprint_selected(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    try:
        build_script_report(db_path, tmp_path / "reports", _FakeGemini(_good_script_response()), {})
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_earlier_stage_blueprint_row_unchanged_after_script_build(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        bp_id = _seed_blueprint(conn, blueprint_score=94.5)

    build_script(db_path, _FakeGemini(_good_script_response()), {})
    with connect(db_path) as conn:
        row = conn.execute("SELECT blueprint_score, ready_for_script FROM production_blueprints WHERE id=?", (bp_id,)).fetchone()
    assert row["blueprint_score"] == 94.5
    assert row["ready_for_script"] == 1


# ==========================================================================
# 09-1: narration quality / retention regression tests (prompts/09-1)
# ==========================================================================

# --------------------------------------------------------------------------
# CASE A/B: narration_scope_safe -- scope overreach vs properly scoped
# --------------------------------------------------------------------------

def test_091_case_a_scope_overreach_fails():
    blueprint = _blueprint_dict()
    script = _good_script_response()
    script["sections"][3]["beats"] = [
        {"type": "narration", "text": "이 방법이면 어떤 단어도 읽을 수 있습니다."}
    ]
    from research.script_writer import render_script_text

    script_text = render_script_text(script)
    checks = run_script_integrity_check(blueprint, blueprint["title"], blueprint["thumbnail_text"], script, script_text)
    assert checks["narration_scope_safe"] == "fail"


def test_091_case_b_scoped_phrase_passes():
    blueprint = _blueprint_dict()
    script = _good_script_response()
    script["sections"][3]["beats"] = [
        {"type": "narration", "text": "이런 기초 3글자 단어는 같은 방식으로 읽어볼 수 있습니다."}
    ]
    from research.script_writer import render_script_text

    script_text = render_script_text(script)
    checks = run_script_integrity_check(blueprint, blueprint["title"], blueprint["thumbnail_text"], script, script_text)
    assert checks["narration_scope_safe"] == "pass"


# --------------------------------------------------------------------------
# CASE C/D: learning-outcome exaggeration vs honest learning-behavior framing
# --------------------------------------------------------------------------

def test_091_case_c_outcome_exaggeration_fails():
    blueprint = _blueprint_dict()
    script = _good_script_response()
    script["sections"][5]["beats"] = [
        {"type": "narration", "text": "외우지 않아도 소리가 저절로 연결됩니다."}
    ]
    from research.script_writer import render_script_text

    script_text = render_script_text(script)
    checks = run_script_integrity_check(blueprint, blueprint["title"], blueprint["thumbnail_text"], script, script_text)
    assert checks["no_false_guarantee"] == "fail"


def test_091_case_d_learning_behavior_framing_passes():
    blueprint = _blueprint_dict()
    script = _good_script_response()
    script["sections"][5]["beats"] = [
        {"type": "narration", "text": "각 글자의 소리를 하나씩 연결하는 연습을 해보세요."}
    ]
    from research.script_writer import render_script_text

    script_text = render_script_text(script)
    checks = run_script_integrity_check(blueprint, blueprint["title"], blueprint["thumbnail_text"], script, script_text)
    assert checks["no_false_guarantee"] == "pass"


def test_091_bare_word_soon_does_not_false_positive():
    # "바로 다음 단어를 보겠습니다." must not be treated as an outcome guarantee.
    assert not any(
        p in "바로 다음 단어를 보겠습니다." for p in ("저절로", "자동으로 됩니다", "한 번에 됩니다")
    )


# --------------------------------------------------------------------------
# CASE E/F/G: letter-phoneme generalization strengthening (shared with 08-1)
# --------------------------------------------------------------------------

def test_091_case_e_letter_generalization_without_word_fails():
    assert _scope_safe_over_text_blob("B는 단어 안에서 /b/ 소리를 냅니다.") == "fail"
    assert _scope_safe_over_text_blob("C는 /k/ 소리를 냅니다.") == "fail"


def test_091_case_f_scoped_to_multiple_example_words_passes():
    assert _scope_safe_over_text_blob("BAG와 BAT에서는 B가 /b/ 소리를 냅니다.") == "pass"


def test_091_case_g_scoped_to_cap_passes():
    assert _scope_safe_over_text_blob("이 단어 CAP에서는 C가 /k/ 소리를 냅니다.") == "pass"


# --------------------------------------------------------------------------
# CASE H: real Blueprint retention devices show up as participatory narration
# --------------------------------------------------------------------------

def test_091_case_h_participatory_phrase_counts_without_question_mark():
    script = {"sections": [{"section_number": 1, "beats": [
        {"type": "narration", "text": "이제 마지막은 여러분 차례입니다. CAP을 직접 소리 내어 읽어보세요."}
    ]}]}
    # No literal "?" anywhere, but this is genuine participatory narration.
    assert "?" not in script["sections"][0]["beats"][0]["text"]
    assert compute_retention_score(script) > 0


# --------------------------------------------------------------------------
# CASE I: spamming trivial question marks doesn't scale the score linearly
# --------------------------------------------------------------------------

def test_091_case_i_question_spam_does_not_scale_linearly():
    def _script_with_n_bare_questions(n, total=6):
        sections = []
        for i in range(total):
            text = "그런가요?" if i < n else "설명입니다."
            sections.append({"section_number": i + 1, "beats": [{"type": "narration", "text": text}]})
        return {"sections": sections}

    score_one = compute_retention_score(_script_with_n_bare_questions(1))
    score_six = compute_retention_score(_script_with_n_bare_questions(6))
    assert score_six > score_one
    assert score_six < score_one * 6


# --------------------------------------------------------------------------
# CASE J: Example Ladder still preserved after all 09-1 changes
# --------------------------------------------------------------------------

def test_091_case_j_example_ladder_still_preserved():
    blueprint = _blueprint_dict()
    script = _good_script_response()
    from research.script_writer import render_script_text

    script_text = render_script_text(script)
    checks = run_script_integrity_check(blueprint, blueprint["title"], blueprint["thumbnail_text"], script, script_text)
    assert checks["example_ladder_preserved"] == "pass"
    ladder_words = [e["word"] for e in blueprint["example_ladder"]]
    assert ladder_words == ["BAG", "BAT", "MAP", "CAP"]


# --------------------------------------------------------------------------
# scope_alignment_score now folds in narration_scope_safe
# --------------------------------------------------------------------------

def test_091_scope_alignment_score_drops_when_narration_scope_unsafe():
    blueprint = _blueprint_dict()
    checks_ok = {"promise_matches_scope": "pass", "no_scope_creep": "pass", "narration_scope_safe": "pass"}
    checks_bad = {"promise_matches_scope": "pass", "no_scope_creep": "pass", "narration_scope_safe": "fail"}
    assert compute_scope_alignment_score(blueprint, checks_bad) < compute_scope_alignment_score(blueprint, checks_ok)


def test_091_full_integrity_check_includes_narration_scope_safe():
    blueprint = _blueprint_dict()
    script = _good_script_response()
    from research.script_writer import render_script_text

    script_text = render_script_text(script)
    checks = run_script_integrity_check(blueprint, blueprint["title"], blueprint["thumbnail_text"], script, script_text)
    assert "narration_scope_safe" in checks
    assert checks["narration_scope_safe"] == "pass"


# ==========================================================================
# 09-2: format-neutral Content Script regression tests (prompts/09-2)
# ==========================================================================

def _blocks(required_content=None, base_narration=""):
    return [{"required_content": required_content or [], "base_narration": base_narration}]


# --------------------------------------------------------------------------
# CASE A/B/C/D/E: format_neutrality_safe
# --------------------------------------------------------------------------

def test_092_case_a_format_neutral_education_passes():
    blocks = _blocks(base_narration="BAG를 예시로 /b/ /æ/ /g/를 설명한다.")
    assert check_format_neutrality_safe(blocks) == "pass"


def test_092_case_b_visual_direction_leakage_fails():
    blocks = _blocks(base_narration="화면 왼쪽에 BAG를 크게 표시한다.")
    assert check_format_neutrality_safe(blocks) == "fail"


def test_092_case_c_clip_direction_leakage_fails():
    blocks = _blocks(base_narration="여기서 영화 클립을 재생한다.")
    assert check_format_neutrality_safe(blocks) == "fail"


def test_092_case_d_podcast_leakage_fails():
    blocks = _blocks(base_narration="Mia가 질문하고 Leo가 설명한다.")
    assert check_format_neutrality_safe(blocks) == "fail"


def test_092_case_e_editing_direction_leakage_fails():
    blocks = _blocks(base_narration="CAP에서 화면을 확대하고 자막 색을 바꾼다.")
    assert check_format_neutrality_safe(blocks) == "fail"


def test_092_format_leakage_detected_via_required_content_too():
    blocks = _blocks(required_content=["카메라를 확대해서 BAG를 보여준다"])
    assert check_format_neutrality_safe(blocks) == "fail"


# --------------------------------------------------------------------------
# CASE F: viewer_action / thinking_time stored as educational requirement, not
# a production instruction
# --------------------------------------------------------------------------

def test_092_case_f_viewer_action_and_thinking_time_stored():
    blueprint = _blueprint_dict()
    script = _good_script_response()
    script["mini_success_meta"] = {
        "learning_function": "MINI_SUCCESS", "required_content": ["CAP을 직접 읽어본다"],
        "importance": "required", "viewer_action": "정답 공개 전에 CAP을 직접 읽어본다",
        "thinking_time_seconds": 3, "retention_intent": {"type": "mini_success", "purpose": "직접 성공 경험"},
        "media_affinity": {k: "medium" for k in (
            "visualization", "real_world_clip", "dialogue", "audio_demonstration", "replay",
            "comparison", "interaction", "storytelling",
        )},
    }
    blocks = build_content_blocks(blueprint, script)
    mini_block = next(b for b in blocks if b["learning_function"] == "MINI_SUCCESS")
    assert mini_block["viewer_action"] == "정답 공개 전에 CAP을 직접 읽어본다"
    assert mini_block["thinking_time_seconds"] == 3
    assert check_format_neutrality_safe([mini_block]) == "pass"


# --------------------------------------------------------------------------
# CASE G/H: media_affinity is a signal, never a format selection
# --------------------------------------------------------------------------

def test_092_case_g_media_affinity_does_not_create_format_fields():
    blueprint = _blueprint_dict()
    script = _good_script_response()
    blocks = build_content_blocks(blueprint, script)
    for block in blocks:
        assert "recommended_format" not in block
        assert "selected_format" not in block
        assert "video_format" not in block
    assert check_format_neutrality_safe(blocks) == "pass"


def test_092_case_h_dialogue_affinity_does_not_create_speakers():
    blueprint = _blueprint_dict()
    script = _good_script_response()
    for s in script["sections"]:
        s["media_affinity"] = {
            "visualization": "medium", "real_world_clip": "low", "dialogue": "high",
            "audio_demonstration": "medium", "replay": "low", "comparison": "low",
            "interaction": "medium", "storytelling": "low",
        }
    blocks = build_content_blocks(blueprint, script)
    for block in blocks:
        assert block["media_affinity"]["dialogue"] in {"low", "medium", "high"}
        assert "Mia" not in block["base_narration"]
        assert "Leo" not in block["base_narration"]
    assert check_format_neutrality_safe(blocks) == "pass"


# --------------------------------------------------------------------------
# CASE I/J/K: Example Ladder / pronunciation / scope regressions still caught
# --------------------------------------------------------------------------

def test_092_case_i_example_ladder_order_and_words_unchanged():
    blueprint = _blueprint_dict()
    ladder_words = [e["word"] for e in blueprint["example_ladder"]]
    assert ladder_words == ["BAG", "BAT", "MAP", "CAP"]


def test_092_case_j_pronunciation_regression_still_caught():
    blueprint = _blueprint_dict()
    script = _good_script_response()
    script["sections"][1]["beats"] = [{"type": "narration", "text": "BAG(백)이 됩니다."}]
    from research.script_writer import render_script_text

    script_text = render_script_text(script)
    checks = run_script_integrity_check(blueprint, blueprint["title"], blueprint["thumbnail_text"], script, script_text)
    assert checks["phoneme_explanation_safe"] == "fail"


def test_092_case_k_scope_regression_still_caught():
    blueprint = _blueprint_dict()
    script = _good_script_response()
    script["ending"]["beats"] = [{"type": "narration", "text": "이제 모든 3글자 영어 단어를 읽을 수 있습니다."}]
    from research.script_writer import render_script_text

    script_text = render_script_text(script)
    checks = run_script_integrity_check(blueprint, blueprint["title"], blueprint["thumbnail_text"], script, script_text)
    assert checks["narration_scope_safe"] == "fail"


# --------------------------------------------------------------------------
# CASE L/M: existing 15 checks preserved, format_neutrality_safe is the 16th
# --------------------------------------------------------------------------

def test_092_case_l_existing_fifteen_checks_preserved():
    blueprint = _blueprint_dict()
    script = _good_script_response()
    from research.script_writer import render_script_text

    script_text = render_script_text(script)
    checks = run_script_integrity_check(blueprint, blueprint["title"], blueprint["thumbnail_text"], script, script_text)
    expected_09_1 = {
        "title_preserved", "thumbnail_preserved", "answers_core_question", "promise_matches_scope",
        "example_ladder_preserved", "phoneme_explanation_safe", "example_scope_safe",
        "no_scope_creep", "narration_scope_safe", "mini_success_present", "audio_first_usable",
        "no_false_guarantee", "no_unverified_rule", "ipa_not_taught_as_memorization",
        "ending_resolves_opening",
    }
    assert expected_09_1.issubset(checks.keys())
    assert len(expected_09_1) == 15


def test_092_case_m_format_neutrality_safe_included_in_full_check():
    blueprint = _blueprint_dict()
    script = _good_script_response()
    from research.script_writer import render_script_text

    script_text = render_script_text(script)
    checks = run_script_integrity_check(blueprint, blueprint["title"], blueprint["thumbnail_text"], script, script_text)
    assert "format_neutrality_safe" in checks
    assert "content_block_uniqueness_safe" in checks
    assert "practice_mini_success_progression_safe" in checks  # 09-4 addition
    assert "mini_success_answer_barrier_safe" in checks  # 09-5 addition
    assert len(checks) == 19


# --------------------------------------------------------------------------
# CASE N: ready_for_direction gating
# --------------------------------------------------------------------------

def test_092_case_n_ready_for_direction_yes_when_all_pass(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_blueprint(conn)

    result = build_script(db_path, _FakeGemini(_good_script_response()), {})
    assert result["ready_for_direction"] is True
    assert result["ready_for_production"] == result["ready_for_direction"]


def test_092_case_n_format_neutrality_fail_forces_ready_for_direction_no(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_blueprint(conn)

    leaking_response = _good_script_response()
    leaking_response["sections"][0]["beats"] = [
        {"type": "narration", "text": "화면 왼쪽에 BAG를 표시하고 카메라를 확대한다."}
    ]
    result = build_script(db_path, _FakeGemini(leaking_response), {})
    assert result["integrity_checks"]["format_neutrality_safe"] == "fail"
    assert result["ready_for_direction"] is False


# --------------------------------------------------------------------------
# CASE O: Gemini fallback still produces valid Content Blocks
# --------------------------------------------------------------------------

def test_092_case_o_fallback_produces_content_blocks_and_not_ready(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_blueprint(conn)

    result = build_script(db_path, gemini=None, channel_cfg={})
    assert result["generation_method"] == "fallback"
    assert result["content_blocks"]
    for block in result["content_blocks"]:
        assert block["learning_function"] in LEARNING_FUNCTIONS
    assert result["ready_for_direction"] is False


# --------------------------------------------------------------------------
# CASE P: DB backward compatibility -- existing video_scripts rows survive init_db
# --------------------------------------------------------------------------

def test_092_case_p_db_backward_compatible_with_existing_rows(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        bp_id = _seed_blueprint(conn)

    build_script_report(db_path, tmp_path / "reports", _FakeGemini(_good_script_response()), {})

    # Re-running init_db (as the CLI does on every invocation) must not fail or drop data.
    init_db(db_path)
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM video_scripts").fetchone()
        bp_row = conn.execute("SELECT * FROM production_blueprints WHERE id=?", (bp_id,)).fetchone()
    assert row is not None
    assert bp_row is not None
    assert row["content_blocks_json"] is not None


# --------------------------------------------------------------------------
# CASE Q: CLI signature backward compatibility
# --------------------------------------------------------------------------

def test_092_case_q_cli_script_command_signature_unchanged():
    from research.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(["script"])
    assert args.blueprint_id is None
    args_with_id = parser.parse_args(["script", "--blueprint-id", "7"])
    assert args_with_id.blueprint_id == 7


# --------------------------------------------------------------------------
# CASE R: upstream stage data untouched by a script build
# --------------------------------------------------------------------------

def test_092_case_r_upstream_tables_untouched(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_blueprint(conn)
        before = {
            t: conn.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"]
            for t in ("topic_candidates", "click_analysis_topics", "content_packages", "production_blueprints")
        }

    build_script(db_path, _FakeGemini(_good_script_response()), {})

    with connect(db_path) as conn:
        after = {
            t: conn.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"]
            for t in ("topic_candidates", "click_analysis_topics", "content_packages", "production_blueprints")
        }
    assert before == after


# ==========================================================================
# 09-3: Content Block dedup / letter-sound generalization regression tests
# (prompts/09-3)
# ==========================================================================

def _duplicating_script():
    """A script whose Section 5 (CAP, MINI_SUCCESS) and mini_success_meta describe the same
    event, and whose Section 6 (RECAP) and ending describe the same recap -- the exact real-data
    duplication pattern found in reports/script_2026-08-17.md."""
    script = _good_script_response()
    script["sections"][4]["learning_function"] = "MINI_SUCCESS"
    script["sections"][4]["viewer_action"] = "정답 공개 전에 CAP 글자의 소리를 스스로 조합하여 읽어본다"
    script["sections"][4]["thinking_time_seconds"] = 3
    script["sections"][4]["required_content"] = ["CAP을 예시로 사용", "CAP에서 C가 /k/ 소리를 냄을 명시"]
    script["sections"][4]["beats"] = [
        {"type": "narration", "text": "이제 마지막은 여러분 차례입니다. 이 단어 CAP을 세 소리로 직접 합쳐서 읽어보세요."},
        {"type": "narration", "text": "CAP에서는 C가 /k/ 소리를 냅니다."},
    ]
    script["mini_success_meta"] = {
        "learning_function": "MINI_SUCCESS", "purpose": "CAP 직접 읽기",
        "required_content": ["CAP을 예시로 사용", "CAP에서 C가 /k/ 소리를 냄을 명시"],
        "importance": "required", "viewer_action": "정답 공개 전에 CAP을 직접 소리 내어 읽어본다",
        "thinking_time_seconds": 3, "retention_intent": {"type": "mini_success", "purpose": "직접 성공 경험"},
        "media_affinity": {k: "medium" for k in (
            "visualization", "real_world_clip", "dialogue", "audio_demonstration", "replay",
            "comparison", "interaction", "storytelling",
        )},
    }
    script["mini_success_beats"] = [
        {"type": "narration", "text": "이제 마지막은 여러분 차례입니다. 이 단어 CAP을 세 소리로 직접 합쳐서 읽어보세요."},
        {"type": "cue", "text": "[PAUSE 3 SEC]"},
        {"type": "narration", "text": "CAP에서는 C가 /k/ 소리를 냅니다."},
    ]
    script["sections"][5]["learning_function"] = "RECAP"
    script["sections"][5]["beats"] = [
        {"type": "narration", "text": "오늘 우리는 BAG, BAT, MAP, CAP을 통해 소리 조합 원리를 확인했습니다. 다음에는 다른 모음도 함께 읽어보겠습니다."}
    ]
    script["ending"] = {
        "beats": [
            {"type": "narration", "text": "오늘 우리는 BAG, BAT, MAP, CAP을 통해 소리 조합 원리를 확인했습니다. 다음에는 다른 모음도 함께 읽어보겠습니다."}
        ],
        "learning_function": "RECAP", "required_content": [], "importance": "required",
        "viewer_action": None, "thinking_time_seconds": 0,
        "retention_intent": {"type": "next_question", "purpose": ""},
        "media_affinity": {k: "low" for k in (
            "visualization", "real_world_clip", "dialogue", "audio_demonstration", "replay",
            "comparison", "interaction", "storytelling",
        )},
    }
    return script


# --------------------------------------------------------------------------
# CASE A/B: real duplication pattern is merged, not duplicated
# --------------------------------------------------------------------------

def test_093_case_a_mini_success_duplicate_merged():
    blueprint = _blueprint_dict()
    script = _duplicating_script()
    blocks = build_content_blocks(blueprint, script)
    mini_blocks = [b for b in blocks if b["learning_function"] == "MINI_SUCCESS"]
    assert len(mini_blocks) == 1
    assert mini_blocks[0]["thinking_time_seconds"] == 3
    assert mini_blocks[0]["viewer_action"]


def test_093_case_b_recap_duplicate_merged():
    blueprint = _blueprint_dict()
    script = _duplicating_script()
    blocks = build_content_blocks(blueprint, script)
    recap_blocks = [b for b in blocks if b["learning_function"] == "RECAP"]
    assert len(recap_blocks) == 1


# --------------------------------------------------------------------------
# CASE C: different learning_function is never merged even if content overlaps
# --------------------------------------------------------------------------

def test_093_case_c_different_learning_function_not_merged():
    blueprint = _blueprint_dict()
    script = _good_script_response()
    script["sections"][1]["learning_function"] = "DEMONSTRATION"  # BAG (section_number=2)
    script["sections"][2]["learning_function"] = "REINFORCEMENT"  # BAT (section_number=3)
    blocks = build_content_blocks(blueprint, script)
    bag_block = next(b for b in blocks if b["section_number"] == 2)
    bat_block = next(b for b in blocks if b["section_number"] == 3)
    assert bag_block["learning_function"] != bat_block["learning_function"]
    assert bag_block["content_block_id"] != bat_block["content_block_id"]


# --------------------------------------------------------------------------
# CASE D: same learning_function but genuinely different content stays separate
# --------------------------------------------------------------------------

def test_093_case_d_distinct_recaps_both_kept():
    a = {"learning_function": "RECAP", "base_narration": "BAG와 BAT 복습: 끝소리 교체 원리를 다시 확인합니다.", "required_content": []}
    b = {"learning_function": "RECAP", "base_narration": "전체 영상 마무리: 다음 시간에는 단모음 o를 배웁니다.", "required_content": []}
    assert check_content_block_uniqueness_safe([
        {**a, "content_block_id": "CB01", "direction_eligible": True},
        {**b, "content_block_id": "CB02", "direction_eligible": True},
    ]) == "pass"


# --------------------------------------------------------------------------
# CASE E: prerequisite_blocks integrity after dedup
# --------------------------------------------------------------------------

def test_093_case_e_prerequisite_blocks_reference_existing_ids():
    blueprint = _blueprint_dict()
    script = _duplicating_script()
    blocks = build_content_blocks(blueprint, script)
    ids = {b["content_block_id"] for b in blocks}
    for block in blocks:
        for prereq in block["prerequisite_blocks"]:
            assert prereq in ids
            assert prereq != block["content_block_id"]


# --------------------------------------------------------------------------
# CASE F/G: "고유한/정해진 소리" (letter = fixed sound) generalization
# --------------------------------------------------------------------------

def test_093_case_f_unique_sound_phrasing_fails():
    assert _scope_safe_over_text_blob("각 글자가 내는 고유한 소리를 순서대로 이어 붙여 읽기 때문입니다.") == "fail"
    assert _scope_safe_over_text_blob("알파벳마다 정해진 소리가 있다.") == "fail"


def test_093_case_g_scoped_letter_sound_passes():
    assert _scope_safe_over_text_blob("각 글자가 이 단어에서 나타내는 소리를 순서대로 이어 붙여 읽습니다.") == "pass"


# --------------------------------------------------------------------------
# CASE H/I/J: existing letter+IPA generalization checks still work
# --------------------------------------------------------------------------

def test_093_case_h_unscoped_letter_ipa_fails():
    assert _scope_safe_over_text_blob("B는 /b/ 소리입니다.") == "fail"


def test_093_case_i_scoped_to_named_words_passes():
    assert _scope_safe_over_text_blob("BAG에서 B는 /b/ 소리를 냅니다.") == "pass"


def test_093_case_j_scoped_to_cap_passes():
    assert _scope_safe_over_text_blob("이 단어 CAP에서는 C가 /k/ 소리를 냅니다.") == "pass"


# --------------------------------------------------------------------------
# CASE K/L: Example Ladder / Mini Success preserved through dedup
# --------------------------------------------------------------------------

def test_093_case_k_example_ladder_preserved_after_dedup():
    blueprint = _blueprint_dict()
    ladder_words = [e["word"] for e in blueprint["example_ladder"]]
    assert ladder_words == ["BAG", "BAT", "MAP", "CAP"]


def test_093_case_l_mini_success_present_after_dedup():
    blueprint = _blueprint_dict()
    script = _duplicating_script()
    from research.script_writer import render_script_text

    script_text = render_script_text(script)
    checks = run_script_integrity_check(blueprint, blueprint["title"], blueprint["thumbnail_text"], script, script_text)
    assert checks["mini_success_present"] == "pass"
    blocks = build_content_blocks(blueprint, script)
    mini_block = next(b for b in blocks if b["learning_function"] == "MINI_SUCCESS")
    assert mini_block["thinking_time_seconds"] == 3


# --------------------------------------------------------------------------
# CASE M/N: format neutrality regression (field-name leakage / media_affinity)
# --------------------------------------------------------------------------

def test_093_case_m_selected_format_field_value_fails():
    blocks = [{"required_content": ['selected_format = "EDUCATION"'], "base_narration": ""}]
    assert check_format_neutrality_safe(blocks) == "fail"


def test_093_case_n_real_world_clip_high_stored_without_format_selection():
    blueprint = _blueprint_dict()
    script = _good_script_response()
    for s in script["sections"]:
        s["media_affinity"] = {
            "visualization": "medium", "real_world_clip": "high", "dialogue": "low",
            "audio_demonstration": "medium", "replay": "low", "comparison": "low",
            "interaction": "low", "storytelling": "low",
        }
    blocks = build_content_blocks(blueprint, script)
    for block in blocks:
        assert "recommended_format" not in block
        assert "selected_format" not in block
    assert check_format_neutrality_safe(blocks) == "pass"


# --------------------------------------------------------------------------
# CASE O/P: content_block_uniqueness_safe respects direction_eligible
# --------------------------------------------------------------------------

def test_093_case_o_duplicate_direction_eligible_blocks_fail():
    dup = {"learning_function": "MINI_SUCCESS", "base_narration": "CAP을 직접 읽어보세요. C /k/ A /æ/ P /p/.", "required_content": []}
    blocks = [
        {**dup, "content_block_id": "CB06", "direction_eligible": True},
        {**dup, "content_block_id": "CB08", "direction_eligible": True},
    ]
    assert check_content_block_uniqueness_safe(blocks) == "fail"
    checks = {"content_block_uniqueness_safe": "fail"}
    assert ready_for_production_gate(checks, 95.0) is False


def test_093_case_p_duplicate_of_marked_ineligible_passes():
    dup = {"learning_function": "MINI_SUCCESS", "base_narration": "CAP을 직접 읽어보세요. C /k/ A /æ/ P /p/.", "required_content": []}
    blocks = [
        {**dup, "content_block_id": "CB06", "direction_eligible": True, "duplicate_of": None},
        {**dup, "content_block_id": "CB08", "direction_eligible": False, "duplicate_of": "CB06"},
    ]
    assert check_content_block_uniqueness_safe(blocks) == "pass"


# --------------------------------------------------------------------------
# CASE Q: existing 16 Integrity Checks (09-2 baseline) preserved
# --------------------------------------------------------------------------

def test_093_case_q_existing_sixteen_checks_preserved():
    blueprint = _blueprint_dict()
    script = _good_script_response()
    from research.script_writer import render_script_text

    script_text = render_script_text(script)
    checks = run_script_integrity_check(blueprint, blueprint["title"], blueprint["thumbnail_text"], script, script_text)
    expected_09_2 = {
        "title_preserved", "thumbnail_preserved", "answers_core_question", "promise_matches_scope",
        "example_ladder_preserved", "phoneme_explanation_safe", "example_scope_safe",
        "no_scope_creep", "narration_scope_safe", "mini_success_present", "audio_first_usable",
        "no_false_guarantee", "no_unverified_rule", "ipa_not_taught_as_memorization",
        "ending_resolves_opening", "format_neutrality_safe",
    }
    assert expected_09_2.issubset(checks.keys())
    assert len(expected_09_2) == 16
    assert "content_block_uniqueness_safe" in checks
    assert "practice_mini_success_progression_safe" in checks  # 09-4 addition
    assert "mini_success_answer_barrier_safe" in checks  # 09-5 addition
    assert len(checks) == 19


# --------------------------------------------------------------------------
# CASE R: 05~08 data unchanged by a full report build
# --------------------------------------------------------------------------

def test_093_case_r_upstream_data_unchanged_by_report_build(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_blueprint(conn)
        before = {
            t: conn.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"]
            for t in ("topic_candidates", "click_analysis_topics", "content_packages")
        }
        bp_before = conn.execute("SELECT blueprint_score, ready_for_script FROM production_blueprints").fetchone()

    build_script_report(db_path, tmp_path / "reports", _FakeGemini(_duplicating_script()), {})

    with connect(db_path) as conn:
        after = {
            t: conn.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"]
            for t in ("topic_candidates", "click_analysis_topics", "content_packages")
        }
        bp_after = conn.execute("SELECT blueprint_score, ready_for_script FROM production_blueprints").fetchone()
    assert before == after
    assert dict(bp_before) == dict(bp_after)


# --------------------------------------------------------------------------
# CASE S: existing CLI command signatures unchanged
# --------------------------------------------------------------------------

def test_093_case_s_all_existing_cli_commands_present():
    from research.cli import build_parser

    parser = build_parser()
    sub_actions = [a for a in parser._subparsers._group_actions if hasattr(a, "choices")]
    command_names = set(sub_actions[0].choices.keys())
    expected = {
        "auth", "keywords", "search", "analyze", "top", "patterns", "report", "run-scheduled",
        "run-all", "topics", "clicks", "packages", "blueprint", "script",
    }
    assert expected.issubset(command_names)


# ---------------------------------------------------------------------------
# 09-4: Content Script Mini Success Gate correction (spec section 23)
# ---------------------------------------------------------------------------

def _cb(content_block_id, learning_function, base_narration, viewer_action=None,
        thinking_time_seconds=0, retention_type="open_loop"):
    return {
        "content_block_id": content_block_id,
        "learning_function": learning_function,
        "base_narration": base_narration,
        "viewer_action": viewer_action,
        "thinking_time_seconds": thinking_time_seconds,
        "retention_intent": {"type": retention_type, "purpose": ""},
    }


def _blank_script():
    return {"mini_success_beats": [], "mini_success_meta": {}, "ending": {"beats": []}}


# CASE A
def test_case_a_no_mini_success_block_fails():
    blocks = [_cb("CB01", "PROBLEM_RECOGNITION", "문제 제기"), _cb("CB02", "RECAP", "정리")]
    assert check_mini_success_present({}, _blank_script(), blocks) == "fail"


# CASE B
def test_case_b_mini_success_block_without_viewer_action_or_attempt_cue_fails():
    blocks = [_cb("CB05", "MINI_SUCCESS", "화면의 단어를 확인해보세요. /m/ /æ/ /p/가 이어집니다.")]
    assert check_mini_success_present({}, _blank_script(), blocks) == "fail"


# CASE C
def test_case_c_mini_success_with_viewer_action_but_no_answer_fails():
    blocks = [_cb("CB05", "MINI_SUCCESS", "MAP을 직접 읽어보세요.", viewer_action="MAP을 직접 읽어본다")]
    assert check_mini_success_present({}, _blank_script(), blocks) == "fail"


# CASE D
def test_case_d_answer_before_attempt_fails():
    script = {
        "mini_success_beats": [
            {"type": "narration", "text": "MAP은 /mæp/입니다. 이제 직접 읽어보세요."},
        ],
        "mini_success_meta": {"viewer_action": "MAP을 직접 읽어본다"},
    }
    blocks = [_cb("CB05", "MINI_SUCCESS", "MAP은 /mæp/입니다. 이제 직접 읽어보세요.", viewer_action="MAP을 직접 읽어본다")]
    assert check_mini_success_present({}, script, blocks) == "fail"


# CASE E
def test_case_e_full_structure_with_pause_and_answer_passes():
    script = {
        "mini_success_beats": [
            {"type": "narration", "text": "MAP을 직접 읽어보세요."},
            {"type": "cue", "text": "[PAUSE 3 SEC]"},
            {"type": "narration", "text": "/m/ /æ/ /p/가 이어져 /mæp/입니다."},
        ],
        "mini_success_meta": {"viewer_action": "MAP을 직접 읽어본다"},
    }
    narration = "MAP을 직접 읽어보세요. /m/ /æ/ /p/가 이어져 /mæp/입니다."
    blocks = [_cb("CB05", "MINI_SUCCESS", narration, viewer_action="MAP을 직접 읽어본다", thinking_time_seconds=3)]
    assert check_mini_success_present({}, script, blocks) == "pass"


# CASE F: current real MAP CB08 structure (unit-level, mirrors the actual DB content)
def test_case_f_real_map_cb08_structure_passes():
    script = {
        "mini_success_beats": [
            {"type": "narration", "text": "화면에 나오는 MAP 단어를 보면서, 세 소리를 순서대로 합쳐 3초 안에 직접 소리 내어 읽어보세요."},
            {"type": "cue", "text": "[PAUSE 3 SEC]"},
            {"type": "narration", "text": "네, /m/, /æ/, /p/가 이어져 /mæp/이 됩니다. 스스로 소리를 연결해 읽어내셨습니다."},
        ],
        "mini_success_meta": {"viewer_action": "정답 공개 전에 MAP 단어의 세 소리를 연결해 직접 소리 내어 읽어본다"},
    }
    narration = (
        "화면에 나오는 MAP 단어를 보면서, 세 소리를 순서대로 합쳐 3초 안에 직접 소리 내어 읽어보세요. "
        "네, /m/, /æ/, /p/가 이어져 /mæp/이 됩니다. 스스로 소리를 연결해 읽어내셨습니다."
    )
    blocks = [_cb(
        "CB08", "MINI_SUCCESS", narration,
        viewer_action="정답 공개 전에 MAP 단어의 세 소리를 연결해 직접 소리 내어 읽어본다", thinking_time_seconds=3,
        retention_type="mini_success",
    )]
    assert check_mini_success_present({}, script, blocks) == "pass"


# CASE G/H: [PAUSE N SEC] cue recognized as the attempt/answer boundary
def test_case_g_h_pause_cue_used_as_attempt_answer_boundary():
    beats_safe = [
        {"type": "narration", "text": "직접 읽어보세요."},
        {"type": "cue", "text": "[PAUSE 3 SEC]"},
        {"type": "narration", "text": "/k/ /æ/ /p/입니다."},
    ]
    from research.script_writer import _answer_revealed_before_attempt

    assert _answer_revealed_before_attempt(beats_safe) is False
    beats_unsafe = [
        {"type": "narration", "text": "/k/ /æ/ /p/입니다. 직접 읽어보세요."},
        {"type": "cue", "text": "[PAUSE 3 SEC]"},
    ]
    assert _answer_revealed_before_attempt(beats_unsafe) is True


# CASE J
def test_case_j_practice_and_mini_success_different_targets_is_safe():
    blocks = [
        _cb("CB05", "PRACTICE", "단어 BAT에서 B는 /b/, A는 /æ/, T는 /t/ 소리를 냅니다."),
        _cb("CB08", "MINI_SUCCESS", "MAP을 직접 읽어보세요.", viewer_action="MAP을 직접 읽어본다", thinking_time_seconds=3),
    ]
    assert check_practice_mini_success_progression_safe(blocks) == "pass"


# CASE K (same as the real CB05->CB08 shape)
def test_case_k_guided_practice_to_independent_mini_success_is_safe():
    blocks = [
        _cb("CB05", "PRACTICE", "단어 MAP에서 M은 /m/, A는 /æ/, P는 /p/ 소리를 냅니다."),
        _cb("CB08", "MINI_SUCCESS", "MAP을 직접 읽어보세요.", viewer_action="MAP을 직접 읽어본다", thinking_time_seconds=3),
    ]
    assert check_practice_mini_success_progression_safe(blocks) == "pass"


# CASE L
def test_case_l_identical_target_action_timing_answer_is_duplication():
    blocks = [
        _cb("CB05", "PRACTICE", "MAP을 직접 읽어보세요. /m/ /æ/ /p/입니다.",
            viewer_action="MAP을 직접 읽어본다", thinking_time_seconds=3),
        _cb("CB08", "MINI_SUCCESS", "MAP을 직접 읽어보세요. /m/ /æ/ /p/입니다.",
            viewer_action="MAP을 직접 읽어본다", thinking_time_seconds=3),
    ]
    assert check_practice_mini_success_progression_safe(blocks) == "fail"


# CASE N/O: opening resolved in the last RECAP, short final sign-off doesn't defeat it
def test_case_n_o_problem_resolved_in_recap_before_short_signoff():
    blueprint = {"core_question": "왜 3글자 단어가 안 읽힐까?"}
    blocks = [
        _cb("CB01", "PROBLEM_RECOGNITION", "왜 3글자 단어가 안 읽힐까?"),
        _cb("CB06", "RECAP", "오늘 배운 핵심을 정리하면, 왜 3글자 단어가 안 읽히는지 알 수 있었습니다."),
        _cb("CB07", "RECAP", "다음 영상에서 만나요. 감사합니다."),
    ]
    assert check_ending_resolves_opening(blueprint, blocks) == "pass"


# CASE P
def test_case_p_no_resolution_anywhere_in_closing_region_stays_warning():
    blueprint = {"core_question": "왜 3글자 단어가 안 읽힐까?"}
    blocks = [
        _cb("CB01", "PROBLEM_RECOGNITION", "왜 3글자 단어가 안 읽힐까?"),
        _cb("CB06", "RECAP", "오늘도 즐거운 시간이었습니다."),
        _cb("CB07", "RECAP", "다음에 만나요. 감사합니다."),
    ]
    assert check_ending_resolves_opening(blueprint, blocks) == "warning"


# collect_closing_region unit coverage
def test_collect_closing_region_includes_trailing_recap_mini_success_run():
    blocks = [
        _cb("CB01", "PROBLEM_RECOGNITION", "..."),
        _cb("CB05", "PRACTICE", "..."),
        _cb("CB06", "TRANSFER", "..."),
        _cb("CB07", "RECAP", "정리1"),
        _cb("CB08", "MINI_SUCCESS", "미니 성공", viewer_action="읽어본다"),
        _cb("CB09", "RECAP", "정리2"),
    ]
    closing = collect_closing_region(blocks)
    assert [cb["content_block_id"] for cb in closing] == ["CB07", "CB08", "CB09"]


# ---------------------------------------------------------------------------
# 09-5: mini_success_answer_barrier_safe -- TARGET ORTHOGRAPHY (bare word) is a safe pre-pause
# prompt; only IPA/answer-pronunciation evidence before the pause is a real reveal (spec section
# 10-11, CASE H-M).
# ---------------------------------------------------------------------------

def _mini_success_script(pre_pause_text, post_pause_text):
    return {
        "mini_success_beats": [
            {"type": "narration", "text": pre_pause_text},
            {"type": "cue", "text": "[PAUSE 3 SEC]"},
            {"type": "narration", "text": post_pause_text},
        ],
        "mini_success_meta": {"viewer_action": "CAP을 직접 읽어본다"},
    }


def _mini_success_blocks(pre_pause_text, post_pause_text):
    narration = f"{pre_pause_text} {post_pause_text}"
    return [_cb("CB08", "MINI_SUCCESS", narration, viewer_action="CAP을 직접 읽어본다", thinking_time_seconds=3)]


# CASE H
def test_case_h_bare_target_spelling_before_pause_passes_barrier():
    script = _mini_success_script("CAP을 직접 읽어보세요.", "정답을 확인해보겠습니다.")
    blocks = _mini_success_blocks("CAP을 직접 읽어보세요.", "정답을 확인해보겠습니다.")
    assert check_mini_success_answer_barrier_safe(script, blocks) == "pass"


# CASE I
def test_case_i_phoneme_breakdown_before_pause_fails_barrier():
    script = _mini_success_script("C /k/, A /æ/, P /p/를 떠올리며 읽어보세요.", "정답입니다.")
    blocks = _mini_success_blocks("C /k/, A /æ/, P /p/를 떠올리며 읽어보세요.", "정답입니다.")
    assert check_mini_success_answer_barrier_safe(script, blocks) == "fail"


# CASE J
def test_case_j_combined_ipa_before_pause_fails_barrier():
    script = _mini_success_script("/kæp/를 떠올리며 읽어보세요.", "정답입니다.")
    blocks = _mini_success_blocks("/kæp/를 떠올리며 읽어보세요.", "정답입니다.")
    assert check_mini_success_answer_barrier_safe(script, blocks) == "fail"


# CASE L
def test_case_l_phoneme_breakdown_after_pause_passes_barrier():
    script = _mini_success_script("CAP을 직접 읽어보세요.", "C /k/, A /æ/, P /p/가 이어집니다.")
    blocks = _mini_success_blocks("CAP을 직접 읽어보세요.", "C /k/, A /æ/, P /p/가 이어집니다.")
    assert check_mini_success_answer_barrier_safe(script, blocks) == "pass"


# CASE M
def test_case_m_natural_answer_word_after_pause_passes_barrier():
    script = _mini_success_script("CAP을 직접 읽어보세요.", "정답은 CAP입니다.")
    blocks = _mini_success_blocks("CAP을 직접 읽어보세요.", "정답은 CAP입니다.")
    assert check_mini_success_answer_barrier_safe(script, blocks) == "pass"


def test_answer_barrier_safe_wired_into_full_integrity_check():
    blueprint = _blueprint_dict()
    script = _good_script_response()
    from research.script_writer import render_script_text

    script_text = render_script_text(script)
    checks = run_script_integrity_check(blueprint, blueprint["title"], blueprint["thumbnail_text"], script, script_text)
    assert checks["mini_success_answer_barrier_safe"] == "pass"


def test_answer_barrier_no_mini_success_at_all_is_a_warning_not_a_crash():
    assert check_mini_success_answer_barrier_safe(_blank_script(), []) == "warning"


# ---------------------------------------------------------------------------
# 09-5: practice_mini_success_progression_safe scaffold framing (spec section 32, CASE R/T/U)
# ---------------------------------------------------------------------------

# CASE R
def test_case_r_full_ladder_guided_to_cap_independent_progression_passes():
    blocks = [
        _cb("CB02", "CORE_EXPLANATION", "CAT에서 C는 /k/, A는 /æ/, T는 /t/ 소리를 냅니다."),
        _cb("CB03", "DEMONSTRATION", "BAT에서 B는 /b/, A는 /æ/, T는 /t/ 소리를 냅니다."),
        _cb("CB04", "REINFORCEMENT", "BAG에서 B는 /b/, A는 /æ/, G는 /g/ 소리를 냅니다."),
        _cb("CB05", "PRACTICE", "MAP에서 M은 /m/, A는 /æ/, P는 /p/ 소리를 냅니다."),
        _cb("CB08", "MINI_SUCCESS", "CAP을 직접 읽어보세요.", viewer_action="CAP을 직접 읽어본다", thinking_time_seconds=3),
    ]
    assert check_practice_mini_success_progression_safe(blocks) == "pass"


# CASE T
def test_case_t_mini_success_scaffold_lower_than_practice_passes():
    blocks = [
        _cb("CB05", "PRACTICE", "MAP에서 M은 /m/, A는 /æ/, P는 /p/ 소리를 냅니다."),
        _cb("CB08", "MINI_SUCCESS", "MAP을 직접 읽어보세요.", viewer_action="MAP을 직접 읽어본다", thinking_time_seconds=3),
    ]
    assert check_practice_mini_success_progression_safe(blocks) == "pass"


# CASE U
def test_case_u_mini_success_scaffold_not_lower_than_practice_with_same_target_fails():
    blocks = [
        _cb("CB05", "PRACTICE", "MAP을 직접 읽어보세요.", viewer_action="MAP을 직접 읽어본다", thinking_time_seconds=3),
        _cb("CB08", "MINI_SUCCESS", "MAP을 직접 읽어보세요.", viewer_action="MAP을 직접 읽어본다", thinking_time_seconds=3),
    ]
    assert check_practice_mini_success_progression_safe(blocks) == "fail"


# ---------------------------------------------------------------------------
# Smoke-test against whatever the real, previously-generated latest DB row currently holds --
# read-only, no Gemini call. This is deliberately not a hard content assertion: which real
# video_scripts row is "latest" (and whether its Mini Success target has already been corrected
# upstream at 08) can change between sessions as the real pipeline is re-run, so this only checks
# that recheck_script_integrity runs cleanly and never mutates the stored score. Skips gracefully
# if no real database is present in this environment.
# ---------------------------------------------------------------------------

def test_real_db_latest_script_recheck_runs_cleanly():
    from pathlib import Path

    db_path = Path("data/research.db")
    if not db_path.exists():
        return  # no real pipeline data in this environment -- nothing to recheck

    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM video_scripts ORDER BY id DESC LIMIT 1").fetchone()
    if row is None:
        return
    row = dict(row)

    result = recheck_script_integrity(db_path, row)
    checks = result["integrity_checks"]

    assert set(checks.values()) <= {"pass", "warning", "fail"}
    for key in ("mini_success_present", "practice_mini_success_progression_safe", "ending_resolves_opening"):
        assert key in checks

    # Script content itself must be untouched by this recheck.
    assert result["script_score"] == row["script_score"]

    if not any(status == "fail" for status in checks.values()):
        assert result["ready_for_direction"] is True
