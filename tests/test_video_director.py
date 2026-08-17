import json

from research.db import connect, init_db
from research.video_director import (
    CLIP_GRADES,
    CLIP_ROLES,
    FORMATS,
    analyze_clips_for_blocks,
    build_all_block_directions,
    build_direction,
    build_podcast_direction,
    build_video_direction_report,
    check_no_renderer_instruction,
    check_podcast_isolation_safe,
    classify_clip_role,
    compute_clip_boundary,
    compute_clip_score,
    decide_final_format,
    decide_format,
    generate_clip_candidates,
    grade_for_score,
    ready_for_production_planning_gate,
    run_direction_integrity_check,
    select_best_clip,
    select_target_script,
)

_MEDIA_AFFINITY_KEYS = (
    "visualization", "real_world_clip", "dialogue", "audio_demonstration", "replay",
    "comparison", "interaction", "storytelling",
)

_CLIP_CONFIG = {
    "weights": {"learning_match": 0.30, "phenomenon_clarity": 0.25, "replay_value": 0.20, "context_independence": 0.15, "audio_usability": 0.10},
    "grade_thresholds": {"strong": 85, "good": 70, "usable": 55},
    "min_learning_match_to_keep": 10,
    "replay_ideal_seconds": [2, 6],
    "neutral_audio_quality": 65,
    "context_padding_seconds": 2.0,
}


def _affinity(**overrides):
    base = {k: "low" for k in _MEDIA_AFFINITY_KEYS}
    base.update(overrides)
    return base


def _block(content_block_id, learning_function, base_narration, required_content=None,
           viewer_action=None, thinking_time_seconds=0, media_affinity=None, section_number=1):
    return {
        "content_block_id": content_block_id,
        "section_number": section_number,
        "learning_function": learning_function,
        "purpose": f"{learning_function} purpose",
        "required_content": required_content or [],
        "importance": "required",
        "prerequisite_blocks": [],
        "viewer_action": viewer_action,
        "thinking_time_seconds": thinking_time_seconds,
        "retention_intent": {"type": "open_loop", "purpose": "..."},
        "media_affinity": media_affinity or _affinity(),
        "base_narration": base_narration,
        "format_neutral": True,
        "direction_eligible": True,
    }


def _bag_content_blocks():
    """The real BAG/BAT/MAP/CAP acceptance-test structure (spec section 34)."""
    education_affinity = _affinity(visualization="high", audio_demonstration="high", comparison="high", interaction="medium")
    return [
        _block("CB01", "PROBLEM_RECOGNITION", "B, A, G. 알파벳 이름을 다 아는데 왜 안 읽힐까요?", media_affinity=education_affinity),
        _block("CB02", "CONTRAST", "글자 이름과 소리는 다릅니다.", media_affinity=education_affinity),
        _block("CB03", "CORE_EXPLANATION", "BAG에서 B는 /b/, A는 /æ/, G는 /g/ 소리를 냅니다.",
               required_content=["BAG 예시 사용", "B /b/ A /æ/ G /g/ 음소 제시"], media_affinity=education_affinity),
        _block("CB04", "DEMONSTRATION", "BAT에서 T는 /t/ 소리를 냅니다.", required_content=["BAT 예시 사용"], media_affinity=education_affinity),
        _block("CB05", "PRACTICE", "MAP에서 M은 /m/, P는 /p/ 소리를 냅니다.", required_content=["MAP 예시 사용"], media_affinity=education_affinity),
        _block("CB06", "MINI_SUCCESS", "이 단어 CAP에서는 C가 /k/ 소리를 냅니다. 직접 읽어보세요.",
               required_content=["CAP 예시 사용", "CAP에서 C가 /k/ 소리를 냄을 안내"],
               viewer_action="정답 공개 전에 CAP을 직접 읽어본다.", thinking_time_seconds=3,
               media_affinity=_affinity(visualization="medium", audio_demonstration="high", interaction="high")),
        _block("CB07", "RECAP", "오늘 BAG, BAT, MAP, CAP을 배웠습니다.", media_affinity=_affinity()),
        _block("CB08", "RESOLUTION", "영어는 이해할수록 쉬워집니다.", media_affinity=_affinity()),
    ]


def _seed_script(conn, content_blocks=None, ready_for_direction=1, title="왜 알파벳 이름을 다 아는데 3글자 단어도 바로 안 읽힐까?"):
    blocks = content_blocks if content_blocks is not None else _bag_content_blocks()
    cur = conn.execute(
        """
        INSERT INTO video_scripts (blueprint_id, package_id, topic_candidate_id, title, thumbnail_text,
            viewer_problem, video_promise, expected_transformation, core_question, core_answer,
            script_json, script_text, estimated_duration_seconds, estimated_word_count, hook_score,
            clarity_score, scope_alignment_score, example_alignment_score, audio_first_score,
            retention_score, script_score, integrity_json, ready_for_production, generation_method,
            content_blocks_json, ready_for_direction)
        VALUES (4, 42, 3, ?, 'B-A-G', '알파벳 이름은 아는데 못 읽는다', '소리를 이어 붙여 읽는다',
            '스스로 읽을 수 있게 된다', ?, '이름이 아니라 소리를 이어 붙여야 한다', '{}', 'text',
            300.0, 500, 100, 100, 100, 100, 100, 100, 100, '{}', 1, 'gemini', ?, ?)
        """,
        (title, title, json.dumps(blocks, ensure_ascii=False), ready_for_direction),
    )
    return cur.lastrowid


class _FakeGemini:
    available = True

    def __init__(self, response):
        self._response = response

    def generate_json(self, prompt, max_output_tokens=6000):
        return self._response


def _education_gates():
    return {
        "podcast_necessity": False, "podcast_reason": "설명/시연 중심 콘텐츠",
        "clip_necessity": False, "clip_reason": "실제 발화 증거가 필요하지 않음",
        "explanation_necessity": True, "explanation_reason": "원리 설명이 핵심",
    }


def _clip_analysis_gates():
    return {
        "podcast_necessity": False, "podcast_reason": "대화 중심 아님",
        "clip_necessity": True, "clip_reason": "실제 발화를 들어야 이해됨",
        "explanation_necessity": False, "explanation_reason": "클립 분석 자체가 중심",
    }


def _hybrid_gates():
    return {
        "podcast_necessity": False, "podcast_reason": "대화 중심 아님",
        "clip_necessity": True, "clip_reason": "실제 발화 경험이 중요",
        "explanation_necessity": True, "explanation_reason": "체계적 설명도 동시에 중요",
    }


def _podcast_gates():
    return {
        "podcast_necessity": True, "podcast_reason": "학습 습관/경험 공유가 핵심 가치",
        "clip_necessity": False, "clip_reason": "실제 발화 증거 불필요",
        "explanation_necessity": False, "explanation_reason": "",
    }


# --------------------------------------------------------------------------
# CASE A/B: BAG real-data acceptance -> EDUCATION, clip_dependency none
# --------------------------------------------------------------------------

def test_case_a_bag_selects_education():
    blocks = _bag_content_blocks()
    script_row = {"title": "t", "viewer_problem": "p", "core_question": "q"}
    result = decide_format(blocks, script_row, _FakeGemini(_education_gates()), {})
    assert result["preferred_format"] == "EDUCATION"


def test_case_b_bag_clip_dependency_none():
    blocks = _bag_content_blocks()
    script_row = {"title": "t", "viewer_problem": "p", "core_question": "q"}
    result = decide_format(blocks, script_row, _FakeGemini(_education_gates()), {})
    assert result["clip_dependency"] == "none"


# --------------------------------------------------------------------------
# CASE C/D: CAP viewer_action / thinking_time preserved
# --------------------------------------------------------------------------

def test_case_c_cap_viewer_action_preserved():
    blocks = _bag_content_blocks()
    directions = build_all_block_directions(blocks, "EDUCATION", {}, {})
    cap = next(d for d in directions if d["content_block_id"] == "CB06")
    assert cap["viewer_interaction"]["viewer_action"] == "정답 공개 전에 CAP을 직접 읽어본다."
    assert cap["viewer_interaction"]["reveal_before_attempt"] is False


def test_case_d_cap_thinking_time_preserved():
    blocks = _bag_content_blocks()
    directions = build_all_block_directions(blocks, "EDUCATION", {}, {})
    cap = next(d for d in directions if d["content_block_id"] == "CB06")
    assert cap["viewer_interaction"]["thinking_time_seconds"] == 3


# --------------------------------------------------------------------------
# CASE E/F: content block loss / required_content loss -> integrity fail
# --------------------------------------------------------------------------

def test_case_e_missing_content_block_fails_integrity():
    blocks = _bag_content_blocks()
    directions = build_all_block_directions(blocks, "EDUCATION", {}, {})
    directions.pop()  # drop CB08
    format_result = {"preferred_format": "EDUCATION", "format_confidence": "high", "format_reason": [], "clip_dependency": "none"}
    final_result = {"final_format": "EDUCATION", "final_format_status": "resolved", "per_block_delivery_mode": {}}
    checks = run_direction_integrity_check(blocks, format_result, final_result, directions, None, {}, True)
    assert checks["content_blocks_preserved"] == "fail"
    assert ready_for_production_planning_gate(checks) is False


def test_case_f_lost_required_content_fails_integrity():
    blocks = _bag_content_blocks()
    directions = build_all_block_directions(blocks, "EDUCATION", {}, {})
    for d in directions:
        if d["content_block_id"] == "CB03":
            d["required_content"] = []  # simulate loss
    format_result = {"preferred_format": "EDUCATION", "format_confidence": "high", "format_reason": [], "clip_dependency": "none"}
    final_result = {"final_format": "EDUCATION", "final_format_status": "resolved", "per_block_delivery_mode": {}}
    checks = run_direction_integrity_check(blocks, format_result, final_result, directions, None, {}, True)
    assert checks["required_content_preserved"] == "fail"


# --------------------------------------------------------------------------
# CASE G/H: clip/education necessity -> CLIP_ANALYSIS / HYBRID candidates
# --------------------------------------------------------------------------

def test_case_g_authentic_speech_selects_clip_analysis():
    blocks = [_block("CB01", "CORE_EXPLANATION", "실제 원어민 발화를 들어봅니다.")]
    script_row = {"title": "왜 Did you가 디쥬처럼 들릴까", "viewer_problem": "p", "core_question": "q"}
    result = decide_format(blocks, script_row, _FakeGemini(_clip_analysis_gates()), {})
    assert result["preferred_format"] == "CLIP_ANALYSIS"
    assert result["clip_dependency"] == "required"


def test_case_h_clip_and_education_necessity_selects_hybrid():
    blocks = [_block("CB01", "CORE_EXPLANATION", "실제 발화와 원리 설명이 모두 필요합니다.")]
    script_row = {"title": "t", "viewer_problem": "p", "core_question": "q"}
    result = decide_format(blocks, script_row, _FakeGemini(_hybrid_gates()), {})
    assert result["preferred_format"] == "HYBRID"


# --------------------------------------------------------------------------
# CASE I/J: podcast candidate vs dialogue-affinity-alone not forcing podcast
# --------------------------------------------------------------------------

def test_case_i_dialogue_storytelling_selects_podcast():
    blocks = [_block("CB01", "PROBLEM_RECOGNITION", "영어 공부를 매일 지속하는 방법 이야기")]
    script_row = {"title": "영어 공부를 매일 지속하는 방법", "viewer_problem": "p", "core_question": "q"}
    result = decide_format(blocks, script_row, _FakeGemini(_podcast_gates()), {})
    assert result["preferred_format"] == "PODCAST"


def test_case_j_dialogue_affinity_alone_does_not_force_podcast():
    # Gemini explicitly says podcast_necessity=False even though dialogue affinity could be high --
    # the gate answer, not the raw affinity signal, must drive the decision.
    blocks = [_block("CB01", "CORE_EXPLANATION", "text", media_affinity=_affinity(dialogue="high"))]
    script_row = {"title": "t", "viewer_problem": "p", "core_question": "q"}
    result = decide_format(blocks, script_row, _FakeGemini(_education_gates()), {})
    assert result["preferred_format"] != "PODCAST"


# --------------------------------------------------------------------------
# CASE K/L: STRONG clip kept, WEAK clip not forced
# --------------------------------------------------------------------------

def test_case_k_strong_clip_keeps_clip_format():
    block = _block("CB01", "CORE_EXPLANATION", "did you get it 발화 확인", required_content=["did you get it"])
    segments = [{"start": 10.0, "end": 13.0, "text": "did you get it 발화 확인 완전히 명확하게 들립니다.", "audio_quality": 90}]
    block_clip_results = analyze_clips_for_blocks([block], segments, _CLIP_CONFIG)
    final = decide_final_format("CLIP_ANALYSIS", "required", block_clip_results, transcript_provided=True)
    assert final["final_format"] == "CLIP_ANALYSIS"


def test_case_l_weak_clip_not_forced():
    block = _block("CB01", "CORE_EXPLANATION", "did you get it 발화 확인", required_content=["did you get it"])
    # Barely clears the learning_match floor but everything else is weak (very long clip, dangling
    # opener, no audio hint) -- should land as WEAK, not STRONG/GOOD.
    segments = [{"start": 10.0, "end": 45.0, "text": "그래서 did you", "audio_quality": 10}]
    block_clip_results = analyze_clips_for_blocks([block], segments, _CLIP_CONFIG)
    selected = block_clip_results["CB01"]["selected"]
    if selected:
        assert selected["clip_grade"] != "STRONG"
    final = decide_final_format("CLIP_ANALYSIS", "required", block_clip_results, transcript_provided=True)
    assert final["final_format"] != "CLIP_ANALYSIS" or all(
        v != "CLIP_ANALYSIS" or (block_clip_results.get(k, {}).get("selected") or {}).get("clip_grade") != "WEAK"
        for k, v in final["per_block_delivery_mode"].items()
    )


# --------------------------------------------------------------------------
# CASE M/N: HYBRID partial clip fallback / full EDUCATION fallback
# --------------------------------------------------------------------------

def test_case_m_hybrid_partial_clip_falls_back_per_block():
    block_clip_results = {
        "CB01": {"candidates": [], "selected": {"clip_grade": "STRONG", "clip_score": 90.0, "clip_role": "EVIDENCE",
                                                  "focus_in": 1.0, "focus_out": 2.0, "context_in": 0.0, "context_out": 3.0}},
        "CB02": {"candidates": [], "selected": None},
    }
    final = decide_final_format("HYBRID", "required", block_clip_results, transcript_provided=True)
    assert final["final_format"] == "HYBRID"
    assert final["per_block_delivery_mode"]["CB01"] == "CLIP_ANALYSIS"
    assert final["per_block_delivery_mode"]["CB02"] == "EDUCATION"


def test_case_n_all_clips_unusable_falls_back_to_education():
    block_clip_results = {"CB01": {"candidates": [], "selected": None}, "CB02": {"candidates": [], "selected": None}}
    final = decide_final_format("HYBRID", "required", block_clip_results, transcript_provided=True)
    assert final["final_format"] == "EDUCATION"
    assert final["fallback_format"] == "HYBRID"


# --------------------------------------------------------------------------
# CASE O/P: clip boundary safety
# --------------------------------------------------------------------------

def test_case_o_focus_outside_context_fails_boundary_check():
    block_clip_results = {"CB01": {"candidates": [
        {"focus_in": 5.0, "focus_out": 10.0, "context_in": 6.0, "context_out": 9.0}
    ], "selected": None}}
    format_result = {"preferred_format": "CLIP_ANALYSIS", "format_confidence": "high", "format_reason": [], "clip_dependency": "required"}
    final_result = {"final_format": "CLIP_ANALYSIS", "final_format_status": "resolved", "per_block_delivery_mode": {}}
    checks = run_direction_integrity_check([], format_result, final_result, [], None, block_clip_results, True)
    assert checks["clip_boundary_safe"] == "fail"


def test_case_p_negative_timestamp_excluded_from_candidates():
    block = _block("CB01", "CORE_EXPLANATION", "text", required_content=["text"])
    segments = [{"start": -5.0, "end": 2.0, "text": "text", "audio_quality": 80}]
    candidates = generate_clip_candidates(block, segments, _CLIP_CONFIG)
    assert candidates == []


# --------------------------------------------------------------------------
# CASE Q/R: Clip Score formula / grade thresholds
# --------------------------------------------------------------------------

def test_case_q_clip_score_formula():
    sub_scores = {"learning_match": 100, "phenomenon_clarity": 100, "replay_value": 100, "context_independence": 100, "audio_usability": 100}
    assert compute_clip_score(sub_scores, _CLIP_CONFIG["weights"]) == 100.0
    sub_scores_zero = {k: 0 for k in sub_scores}
    assert compute_clip_score(sub_scores_zero, _CLIP_CONFIG["weights"]) == 0.0
    mixed = {"learning_match": 100, "phenomenon_clarity": 0, "replay_value": 0, "context_independence": 0, "audio_usability": 0}
    assert compute_clip_score(mixed, _CLIP_CONFIG["weights"]) == 30.0


def test_case_r_clip_grade_thresholds():
    thresholds = _CLIP_CONFIG["grade_thresholds"]
    assert grade_for_score(85.0, thresholds) == "STRONG"
    assert grade_for_score(84.9, thresholds) == "GOOD"
    assert grade_for_score(70.0, thresholds) == "GOOD"
    assert grade_for_score(55.0, thresholds) == "USABLE"
    assert grade_for_score(54.9, thresholds) == "WEAK"


# --------------------------------------------------------------------------
# CASE S: PODCAST isolation
# --------------------------------------------------------------------------

def test_case_s_podcast_isolation_fails_when_block_directions_present():
    assert check_podcast_isolation_safe("PODCAST", {"speakers": [], "dialogue_beats": []}, [{"content_block_id": "CB01"}]) == "fail"


def test_case_s_podcast_isolation_fails_when_podcast_leaks_into_non_podcast():
    assert check_podcast_isolation_safe("EDUCATION", {"speakers": [], "dialogue_beats": [{"x": 1}]}, []) == "fail"


def test_case_s_podcast_isolation_passes_when_clean():
    assert check_podcast_isolation_safe("PODCAST", {"speakers": [], "dialogue_beats": []}, []) == "pass"
    assert check_podcast_isolation_safe("EDUCATION", None, [{"content_block_id": "CB01"}]) == "pass"


# --------------------------------------------------------------------------
# CASE T: renderer-specific instruction detection
# --------------------------------------------------------------------------

def test_case_t_renderer_instruction_detected():
    block_directions = [{"content_block_id": "CB01", "production_intent": "화면 왼쪽에 BAG를 표시하고 카메라를 확대한다"}]
    assert check_no_renderer_instruction(block_directions, None) == "fail"


def test_case_t_clean_direction_passes():
    block_directions = [{"content_block_id": "CB01", "production_intent": "explain_core_principle"}]
    assert check_no_renderer_instruction(block_directions, None) == "pass"


# --------------------------------------------------------------------------
# CASE U/V: 09 source unchanged, 09 Integrity Check 17 preserved
# --------------------------------------------------------------------------

def test_case_u_source_script_unchanged_after_direction_build(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        script_id = _seed_script(conn)
        before = conn.execute("SELECT content_blocks_json, script_json FROM video_scripts WHERE id=?", (script_id,)).fetchone()

    build_direction(db_path, _FakeGemini(_education_gates()), {}, _CLIP_CONFIG)

    with connect(db_path) as conn:
        after = conn.execute("SELECT content_blocks_json, script_json FROM video_scripts WHERE id=?", (script_id,)).fetchone()
    assert dict(before) == dict(after)


def test_case_v_existing_09_integrity_checks_still_importable():
    from research.script_writer import run_script_integrity_check

    assert callable(run_script_integrity_check)


# --------------------------------------------------------------------------
# CASE W: existing CLI backward compatibility
# --------------------------------------------------------------------------

def test_case_w_cli_backward_compatible():
    from research.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(["direction"])
    assert args.script_id is None
    assert args.transcript_json is None
    args2 = parser.parse_args(["direction", "--script-id", "3", "--transcript-json", "x.json"])
    assert args2.script_id == 3
    assert args2.transcript_json == "x.json"
    # Every pre-existing subcommand must still parse.
    for cmd in ["topics", "clicks", "packages", "blueprint", "script"]:
        parser.parse_args([cmd])


# --------------------------------------------------------------------------
# CASE X: Gemini fallback with insufficient quality -> NO
# --------------------------------------------------------------------------

def test_case_x_gemini_unavailable_still_produces_valid_direction(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_script(conn)

    result = build_direction(db_path, gemini=None, channel_cfg={}, clip_config=_CLIP_CONFIG)
    assert result["generation_method"] == "fallback"
    # Pipeline must not crash and must still produce a valid, gated result.
    assert result["format_result"]["preferred_format"] in FORMATS
    assert isinstance(result["ready_for_production_planning"], bool)


# --------------------------------------------------------------------------
# Additional structural/unit coverage
# --------------------------------------------------------------------------

def test_select_target_script_picks_latest_ready(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_script(conn, ready_for_direction=0, title="old")
        target_id = _seed_script(conn, ready_for_direction=1, title="new")

    row = select_target_script(db_path)
    assert row["id"] == target_id


def test_select_target_script_by_explicit_id(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        target_id = _seed_script(conn, ready_for_direction=0)

    row = select_target_script(db_path, script_id=target_id)
    assert row["id"] == target_id


def test_classify_clip_role_within_taxonomy():
    for lf in ("PROBLEM_RECOGNITION", "CORE_EXPLANATION", "MINI_SUCCESS", "UNKNOWN"):
        assert classify_clip_role(lf) in CLIP_ROLES


def test_compute_clip_boundary_never_lets_focus_escape_context():
    boundary = compute_clip_boundary({"start": 1.0, "end": 2.0}, padding_seconds=5.0, source_duration=3.0)
    assert boundary["context_in"] <= boundary["focus_in"] <= boundary["focus_out"] <= boundary["context_out"]
    assert boundary["context_in"] >= 0.0
    assert boundary["context_out"] <= 3.0 or boundary["context_out"] == boundary["focus_out"]


def test_select_best_clip_prefers_higher_grade_then_score():
    candidates = [
        {"clip_grade": "GOOD", "clip_score": 95.0},
        {"clip_grade": "STRONG", "clip_score": 86.0},
    ]
    best = select_best_clip(candidates)
    assert best["clip_grade"] == "STRONG"


def test_select_best_clip_returns_none_for_empty_list():
    assert select_best_clip([]) is None


def test_all_content_blocks_get_a_direction_for_education_format():
    blocks = _bag_content_blocks()
    directions = build_all_block_directions(blocks, "EDUCATION", {}, {})
    assert {d["content_block_id"] for d in directions} == {b["content_block_id"] for b in blocks}
    assert all(d["delivery_mode"] == "EDUCATION" for d in directions)


def test_build_podcast_direction_fallback_covers_every_block():
    blocks = [_block("CB01", "PROBLEM_RECOGNITION", "text one"), _block("CB02", "RECAP", "text two")]
    direction = build_podcast_direction(blocks, {}, gemini=None)
    covered = {b["content_block_id"] for b in direction["dialogue_beats"]}
    assert covered == {"CB01", "CB02"}
    assert direction["generation_method"] == "fallback"


def test_ready_for_production_planning_gate_requires_no_fail():
    assert ready_for_production_planning_gate({"a": "pass", "b": "warning"}) is True
    assert ready_for_production_planning_gate({"a": "pass", "b": "fail"}) is False


# --------------------------------------------------------------------------
# Real BAG report generation end-to-end
# --------------------------------------------------------------------------

def test_report_generation_produces_expected_sections(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_script(conn)

    out_path = build_video_direction_report(db_path, tmp_path / "reports", _FakeGemini(_education_gates()), {}, _CLIP_CONFIG)
    text = out_path.read_text(encoding="utf-8")
    for heading in [
        "# Video Director Report",
        "## 1. Source Content Script",
        "## 2. Format Decision",
        "## 3. Format Reason",
        "## 4. Clip Dependency",
        "## 5. Fallback Format",
        "## 6. Content Block Direction Table",
        "## 7. Viewer Interaction Plan",
        "## 8. Retention Translation",
        "## 9. Clip Analysis Result",
        "## 10. Clip Candidates",
        "## 11. Fallback Decisions",
        "## 12. Podcast Direction",
        "## 13. Integrity Check",
        "## 14. Ready for Production Planning",
        "## 15. Known Limitations",
    ]:
        assert heading in text

    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM video_directions").fetchone()
        block_rows = conn.execute("SELECT * FROM block_directions WHERE video_direction_id=?", (row["id"],)).fetchall()
    assert row is not None
    assert row["preferred_format"] == "EDUCATION"
    assert row["final_format"] == "EDUCATION"
    assert row["ready_for_production_planning"] in (0, 1)
    assert len(block_rows) == 8


def test_report_raises_when_no_script_selected(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    try:
        build_video_direction_report(db_path, tmp_path / "reports", _FakeGemini(_education_gates()), {}, _CLIP_CONFIG)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_upstream_data_unchanged_by_direction_build(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_script(conn)
        before = {
            t: conn.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"]
            for t in ("topic_candidates", "click_analysis_topics", "content_packages", "production_blueprints")
        }

    build_video_direction_report(db_path, tmp_path / "reports", _FakeGemini(_education_gates()), {}, _CLIP_CONFIG)

    with connect(db_path) as conn:
        after = {
            t: conn.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"]
            for t in ("topic_candidates", "click_analysis_topics", "content_packages", "production_blueprints")
        }
    assert before == after
