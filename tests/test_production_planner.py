import json

from research.db import connect, init_db
from research.production_planner import (
    CAPTION_MODES,
    FORMATS,
    HIGHLIGHT_MODES,
    NARRATOR_VOICE,
    PAUSE_VISUAL_BEHAVIORS,
    PODCAST_VOICES,
    SPEECH_MODES,
    SpeechAssetRegistry,
    _SAFE_READ_INVITATION,
    build_block_speech_plan,
    build_caption_spec,
    build_pause_event,
    build_production_plan,
    build_production_plan_report,
    build_timeline,
    build_visual_spec,
    check_educational_wording_preserved,
    check_interaction_requirement_coverage,
    check_narration_fragment_safe,
    check_structural_requirement_coverage,
    check_style_intent_coverage,
    classify_required_content_type,
    classify_speech_mode,
    compute_planner_score,
    compute_required_content_coverage,
    estimate_block_duration,
    estimate_production_complexity,
    evaluate_required_content_item,
    is_orphan_narration_fragment,
    is_punctuation_only_fragment,
    is_required_content_covered,
    normalize_fragments,
    ready_for_asset_generation_gate,
    run_planner_integrity_check,
    segment_narration,
    select_target_direction,
)

_CLIP_CONFIG = {
    "weights": {"learning_match": 0.30, "phenomenon_clarity": 0.25, "replay_value": 0.20, "context_independence": 0.15, "audio_usability": 0.10},
    "grade_thresholds": {"strong": 85, "good": 70, "usable": 55},
}
_COMPLEXITY_CONFIG = {"medium_at_total_signals": 12, "high_at_total_signals": 22}


def _block(content_block_id, learning_function, base_narration, required_content=None,
           viewer_action=None, thinking_time_seconds=0, section_number=1, direction_eligible=True):
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
        "media_affinity": {k: "low" for k in ("visualization", "real_world_clip", "dialogue", "audio_demonstration", "replay", "comparison", "interaction", "storytelling")},
        "base_narration": base_narration,
        "format_neutral": True,
        "direction_eligible": direction_eligible,
    }


def _bag_content_blocks():
    return [
        _block("CB01", "PROBLEM_RECOGNITION", "B, A, G. 알파벳 이름을 다 아는데 왜 안 읽힐까요?", section_number=None),
        _block("CB02", "CONTRAST", "글자 이름과 소리는 다릅니다.", section_number=1),
        _block("CB03", "CORE_EXPLANATION", "BAG에서 글자 소리를 하나씩 살펴보겠습니다. 이 단어에서 B는 /b/ 소리를 냅니다. 그리고 가운데 A는 /æ/ 소리를 냅니다. 마지막 G는 /g/ 소리를 냅니다. 이제 이어 붙이면 BAG가 됩니다. 정리하면 /b/ - /æ/ - /g/ 입니다.",
               required_content=["BAG 예시 사용", "B /b/ A /æ/ G /g/ 음소 제시"], section_number=2),
        _block("CB04", "DEMONSTRATION", "BAT에서 T는 /t/ 소리를 냅니다.", required_content=["BAT 예시 사용"], section_number=3),
        _block("CB05", "PRACTICE", "MAP에서 M은 /m/, P는 /p/ 소리를 냅니다. 정리하면 /m/ - /æ/ - /p/ 입니다.", required_content=["MAP 예시 사용"], section_number=4),
        _block("CB06", "MINI_SUCCESS", "이 단어 CAP에서는 C가 /k/ 소리를 냅니다. 가운데 A는 /æ/, 끝 글자 P는 /p/ 소리입니다. 이 세 소리를 순서대로 직접 소리 내어 이어 붙여보세요.",
               required_content=["CAP 예시 사용", "CAP에서 C가 /k/ 소리를 냄을 안내", "정답 공개 전 3초 생각 시간 부여"],
               viewer_action="정답 공개 전에 CAP을 직접 읽어본다.", thinking_time_seconds=3, section_number=5),
        _block("CB07", "RECAP", "오늘 BAG, BAT, MAP, CAP을 배웠습니다.", section_number=6),
        _block("CB08", "RESOLUTION",
               "영어 단어는 외우려고 할수록 복잡해지지만, 소리가 이어지는 원리를 이해하면 훨씬 쉬워집니다. "
               "오늘 영상이 도움이 되셨다면 함께 연습을 이어가 보세요. 시청해 주셔서 감사합니다.",
               required_content=["자연스럽고 부담 없는 마무리 인사", "차분하고 권위적이지 않은 마무리 멘트"], section_number=None),
    ]


def _seed_bundle(conn, content_blocks=None, final_format="EDUCATION", ready=1,
                  podcast_direction=None, clip_candidates_by_block=None, title="왜 알파벳 이름을 다 아는데 3글자 단어도 바로 안 읽힐까?"):
    blocks = content_blocks if content_blocks is not None else _bag_content_blocks()
    script_cur = conn.execute(
        """
        INSERT INTO video_scripts (blueprint_id, package_id, topic_candidate_id, title, thumbnail_text,
            viewer_problem, video_promise, expected_transformation, core_question, core_answer,
            script_json, script_text, estimated_duration_seconds, estimated_word_count, hook_score,
            clarity_score, scope_alignment_score, example_alignment_score, audio_first_score,
            retention_score, script_score, integrity_json, ready_for_production, generation_method,
            content_blocks_json, ready_for_direction)
        VALUES (4, 42, 3, ?, 'B-A-G', 'p', 'promise', 'transform', ?, 'answer', '{}', 'text',
            300.0, 500, 100, 100, 100, 100, 100, 100, 100, '{}', 1, 'gemini', ?, 1)
        """,
        (title, title, json.dumps(blocks, ensure_ascii=False)),
    )
    script_id = script_cur.lastrowid

    direction_cur = conn.execute(
        """
        INSERT INTO video_directions (video_script_id, preferred_format, final_format, format_confidence,
            format_reason_json, clip_dependency, fallback_format, final_format_status, director_score,
            integrity_json, ready_for_production_planning, generation_method, podcast_direction_json)
        VALUES (?, ?, ?, 'high', '[]', 'none', NULL, 'resolved', 100.0, '{}', ?, 'gemini', ?)
        """,
        (script_id, final_format, final_format,
         ready, json.dumps(podcast_direction, ensure_ascii=False) if podcast_direction else None),
    )
    direction_id = direction_cur.lastrowid

    if final_format != "PODCAST":
        for block in blocks:
            if not block.get("direction_eligible", True):
                continue
            block_id = block["content_block_id"]
            candidates = (clip_candidates_by_block or {}).get(block_id)
            delivery_mode = "CLIP_ANALYSIS" if candidates else "EDUCATION"
            conn.execute(
                """
                INSERT INTO block_directions (video_direction_id, content_block_id, delivery_mode,
                    production_intent, viewer_interaction_json, audio_requirement_json,
                    visual_requirement_json, clip_requirement_json, retention_role_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    direction_id, block_id, delivery_mode, f"intent_for_{block_id}",
                    json.dumps({"type": "NONE", "viewer_action": block.get("viewer_action"), "thinking_time_seconds": block.get("thinking_time_seconds", 0)}, ensure_ascii=False),
                    "{}", "{}", "{}", json.dumps(block.get("retention_intent"), ensure_ascii=False),
                ),
            )
            for candidate in candidates or []:
                cur = conn.execute(
                    """
                    INSERT INTO source_clip_candidates (video_direction_id, content_block_id, source_ref,
                        transcript, focus_in, focus_out, context_in, context_out, learning_match,
                        phenomenon_clarity, replay_value, context_independence, audio_usability,
                        clip_score, clip_grade, clip_role, confidence, selected)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        direction_id, block_id, candidate.get("source_ref"), candidate.get("transcript", ""),
                        candidate["focus_in"], candidate["focus_out"], candidate["context_in"], candidate["context_out"],
                        candidate.get("learning_match", 80), candidate.get("phenomenon_clarity", 80),
                        candidate.get("replay_value", 80), candidate.get("context_independence", 80),
                        candidate.get("audio_usability", 80), candidate.get("clip_score", 90),
                        candidate.get("clip_grade", "STRONG"), candidate.get("clip_role", "EVIDENCE"),
                        "high", 1 if candidate.get("selected", True) else 0,
                    ),
                )

    return direction_id


# --------------------------------------------------------------------------
# CASE A: EDUCATION -> Charon
# --------------------------------------------------------------------------

def test_case_a_education_uses_charon(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_bundle(conn)

    result = build_production_plan(db_path, clip_config=_CLIP_CONFIG, complexity_config=_COMPLEXITY_CONFIG)
    non_native_assets = [a for a in result["speech_assets"] if a["speech_mode"] != "ORIGINAL_NATIVE_AUDIO"]
    assert non_native_assets
    assert all(a["voice_name"] == NARRATOR_VOICE for a in non_native_assets)


# --------------------------------------------------------------------------
# CASE B/C: Podcast voice casting
# --------------------------------------------------------------------------

def test_case_b_podcast_female_uses_zephyr():
    registry = SpeechAssetRegistry()
    from research.production_planner import build_podcast_production_blocks

    bundle = {"podcast_direction": {"dialogue_beats": [{"content_block_id": "CB01", "speaker": "host_a", "text": "안녕하세요"}]}}
    build_podcast_production_blocks(bundle, registry)
    assert registry.assets[0]["voice_name"] == PODCAST_VOICES["female"]
    assert PODCAST_VOICES["female"] == "Zephyr"


def test_case_c_podcast_male_uses_charon():
    registry = SpeechAssetRegistry()
    from research.production_planner import build_podcast_production_blocks

    bundle = {"podcast_direction": {"dialogue_beats": [{"content_block_id": "CB01", "speaker": "host_b", "text": "그렇습니다"}]}}
    build_podcast_production_blocks(bundle, registry)
    assert registry.assets[0]["voice_name"] == PODCAST_VOICES["male"]
    assert PODCAST_VOICES["male"] == "Charon"


# --------------------------------------------------------------------------
# CASE D/E/F/G: Speech mode classification
# --------------------------------------------------------------------------

def test_case_d_natural_english_word_is_en_native():
    assert classify_speech_mode("ENGLISH_WORD") == "EN_NATIVE"


def test_case_e_korean_explanation_is_ko_narration():
    assert classify_speech_mode("KOREAN", korean_text="이번에는 BAG를 보겠습니다.") == "KO_NARRATION"


def test_case_f_korean_approximation_guide():
    mode = classify_speech_mode("KOREAN", korean_text="사운즈 라이커 플랜처럼 들릴 수 있습니다.")
    assert mode == "KO_PRONUNCIATION_GUIDE"
    registry = SpeechAssetRegistry()
    asset_id = registry.get_or_create(mode, NARRATOR_VOICE, "사운즈 라이커 플랜처럼 들릴 수 있습니다.")
    asset = registry.by_id()[asset_id]
    assert asset["approximation_only"] is True


def test_case_g_individual_phoneme_is_en_phoneme_demo():
    assert classify_speech_mode("PHONEME") == "EN_PHONEME_DEMO"


# --------------------------------------------------------------------------
# CASE H/I: ORIGINAL_NATIVE_AUDIO priority
# --------------------------------------------------------------------------

def test_case_h_native_audio_source_takes_priority():
    assert classify_speech_mode("ENGLISH_WORD", has_native_audio_source=True) == "ORIGINAL_NATIVE_AUDIO"


def test_case_i_no_native_audio_without_source_clip():
    block = _block("CB01", "CORE_EXPLANATION", "BAG 예시를 봅니다.")
    registry = SpeechAssetRegistry()
    plan = build_block_speech_plan(block, registry, has_native_audio_source=False)
    modes = {seg["speech_mode"] for seg in plan["pre_pause"] + plan["post_pause"]}
    assert "ORIGINAL_NATIVE_AUDIO" not in modes


# --------------------------------------------------------------------------
# CASE J/K: segmentation separates Korean narration from English/phoneme content
# --------------------------------------------------------------------------

def test_case_j_bag_korean_and_en_native_separated():
    tokens = segment_narration("이번에는 BAG를 들어보겠습니다. BAG.")
    kinds = [t["kind"] for t in tokens]
    assert "ENGLISH_WORD" in kinds
    assert "KOREAN" in kinds
    english_tokens = [t for t in tokens if t["kind"] == "ENGLISH_WORD"]
    assert all(t["text"] == "BAG" for t in english_tokens)


def test_case_k_phonemes_split_into_independent_tokens():
    tokens = segment_narration("B는 /b/, A는 /æ/, G는 /g/입니다.")
    phonemes = [t["text"] for t in tokens if t["kind"] == "PHONEME"]
    assert phonemes == ["/b/", "/æ/", "/g/"]


# --------------------------------------------------------------------------
# CASE L: IPA never overwritten by Korean approximation
# --------------------------------------------------------------------------

def test_case_l_ipa_source_of_truth_not_overwritten():
    registry = SpeechAssetRegistry()
    asset_id = registry.get_or_create("EN_PHONEME_DEMO", NARRATOR_VOICE, "/æ/")
    asset = registry.by_id()[asset_id]
    assert asset["source_text"] == "/æ/"
    assert asset["expected_pronunciation"] == "/æ/"
    assert "애" not in asset["source_text"]


# --------------------------------------------------------------------------
# CASE M/N: CAP 3-second pause + no early answer reveal
# --------------------------------------------------------------------------

def test_case_m_cap_thinking_time_preserved():
    block = next(b for b in _bag_content_blocks() if b["content_block_id"] == "CB06")
    pause = build_pause_event(block)
    assert pause["duration_ms"] == 3000


def test_case_n_answer_revealed_before_pause_fails_integrity():
    block = next(b for b in _bag_content_blocks() if b["content_block_id"] == "CB06")
    registry = SpeechAssetRegistry()
    plan = build_block_speech_plan(block, registry)
    timeline = build_timeline(block, plan)
    # Sabotage: move a post-pause EN_NATIVE-like speech event before the PAUSE.
    pause_idx = next(i for i, ev in enumerate(timeline) if ev["type"] == "PAUSE")
    bad_asset_id = registry.get_or_create("EN_NATIVE", NARRATOR_VOICE, "CAP")
    timeline.insert(0, {"event_order": 0, "type": "SPEECH", "speech_asset_id": bad_asset_id})
    for i, ev in enumerate(timeline, start=1):
        ev["event_order"] = i
    production_blocks = [{"content_block_id": "CB06", "block_order": 1, "timeline": timeline, "required_content_coverage": {}, "clip_spec": None, "interaction_spec": {"has_pause": True}}]
    checks = run_planner_integrity_check(_bag_content_blocks(), "EDUCATION", production_blocks, registry.by_id(), {}, True)
    assert checks["answer_not_revealed_before_attempt"] == "fail"


# --------------------------------------------------------------------------
# CASE O: viewer_action loss -> fail
# --------------------------------------------------------------------------

def test_case_o_lost_viewer_action_fails_integrity():
    blocks = _bag_content_blocks()
    production_blocks = [
        {"content_block_id": "CB06", "block_order": 1, "timeline": [], "required_content_coverage": {},
         "clip_spec": None, "interaction_spec": {"has_pause": False, "viewer_action": None, "thinking_time_seconds": 0}},
    ]
    checks = run_planner_integrity_check(blocks, "EDUCATION", production_blocks, {}, {}, True)
    assert checks["viewer_action_preserved"] == "fail"


# --------------------------------------------------------------------------
# CASE P: required_content coverage gap -> fail
# --------------------------------------------------------------------------

def test_case_p_missing_required_content_coverage_fails_integrity():
    blocks = _bag_content_blocks()
    production_blocks = [
        {"content_block_id": "CB03", "block_order": 1, "timeline": [], "required_content_coverage": {"BAG 예시 사용": []},
         "clip_spec": None, "interaction_spec": {"has_pause": False, "viewer_action": None, "thinking_time_seconds": 0}},
    ]
    checks = run_planner_integrity_check(blocks, "EDUCATION", production_blocks, {}, {}, True)
    assert checks["required_content_covered"] == "fail"


def test_required_content_coverage_computed_correctly():
    block = _block("CB03", "CORE_EXPLANATION", "BAG 예시를 봅니다.", required_content=["BAG 예시"])
    registry = SpeechAssetRegistry()
    plan = build_block_speech_plan(block, registry)
    timeline = build_timeline(block, plan)
    coverage = compute_required_content_coverage(block, timeline, registry.by_id())
    assert coverage["BAG 예시"]


# --------------------------------------------------------------------------
# CASE Q: clip boundary change -> fail
# --------------------------------------------------------------------------

def test_case_q_clip_boundary_mismatch_fails_integrity():
    clip_candidates_by_block = {"CB01": [{"id": 1, "focus_in": 5.0, "focus_out": 7.0, "context_in": 4.0, "context_out": 8.0}]}
    production_blocks = [
        {"content_block_id": "CB01", "block_order": 1,
         "timeline": [{"event_order": 1, "type": "SOURCE_CLIP", "source_clip_candidate_id": 1,
                        "focus_in": 5.5, "focus_out": 7.0, "context_in": 4.0, "context_out": 8.0}],
         "required_content_coverage": {}, "clip_spec": {"x": 1},
         "interaction_spec": {"has_pause": False, "viewer_action": None, "thinking_time_seconds": 0}},
    ]
    checks = run_planner_integrity_check([], "CLIP_ANALYSIS", production_blocks, {}, clip_candidates_by_block, True)
    assert checks["clip_boundary_preserved"] == "fail"


# --------------------------------------------------------------------------
# CASE R: EDUCATION narrator inserted into PODCAST -> fail
# --------------------------------------------------------------------------

def test_case_r_education_narrator_in_podcast_fails_isolation():
    registry = SpeechAssetRegistry()
    registry.get_or_create("KO_NARRATION", NARRATOR_VOICE, "이것은 교육 내레이션입니다")  # Charon leaking into PODCAST
    checks = run_planner_integrity_check([], "PODCAST", [], registry.by_id(), {}, True)
    assert checks["podcast_voice_isolation_safe"] == "fail"


def test_zephyr_leaking_into_non_podcast_fails_isolation():
    registry = SpeechAssetRegistry()
    registry.get_or_create("KO_NARRATION", "Zephyr", "잘못 배정된 보이스")
    checks = run_planner_integrity_check([], "EDUCATION", [], registry.by_id(), {}, True)
    assert checks["podcast_voice_isolation_safe"] == "fail"


# --------------------------------------------------------------------------
# CASE S/T: Asset deduplication
# --------------------------------------------------------------------------

def test_case_s_same_en_native_asset_reused():
    registry = SpeechAssetRegistry()
    id1 = registry.get_or_create("EN_NATIVE", NARRATOR_VOICE, "BAG")
    id2 = registry.get_or_create("EN_NATIVE", NARRATOR_VOICE, "BAG")
    assert id1 == id2
    assert len(registry.assets) == 1


def test_case_t_natural_vs_deliberate_allowed_as_separate_assets():
    registry = SpeechAssetRegistry()
    id1 = registry.get_or_create("EN_NATIVE", NARRATOR_VOICE, "BAG", delivery_intent="natural")
    id2 = registry.get_or_create("EN_NATIVE", NARRATOR_VOICE, "BAG", delivery_intent="deliberate_demonstration")
    assert id1 != id2
    assert len(registry.assets) == 2


# --------------------------------------------------------------------------
# CASE U: Pause visualization taxonomy
# --------------------------------------------------------------------------

def test_case_u_pause_visualization_taxonomy_valid():
    block = next(b for b in _bag_content_blocks() if b["content_block_id"] == "CB06")
    pause = build_pause_event(block)
    assert pause["pause_visual_behavior"] in PAUSE_VISUAL_BEHAVIORS


def test_case_u_invalid_pause_behavior_fails_integrity():
    production_blocks = [
        {"content_block_id": "CB01", "block_order": 1,
         "timeline": [{"event_order": 1, "type": "PAUSE", "duration_ms": 1000, "pause_visual_behavior": "SPIN_360"}],
         "required_content_coverage": {}, "clip_spec": None,
         "interaction_spec": {"has_pause": True, "viewer_action": None, "thinking_time_seconds": 0}},
    ]
    checks = run_planner_integrity_check([], "EDUCATION", production_blocks, {}, {}, True)
    assert checks["pause_visualization_valid"] == "fail"


# --------------------------------------------------------------------------
# CASE V: timeline reference integrity
# --------------------------------------------------------------------------

def test_case_v_dangling_speech_asset_reference_fails_integrity():
    production_blocks = [
        {"content_block_id": "CB01", "block_order": 1,
         "timeline": [{"event_order": 1, "type": "SPEECH", "speech_asset_id": "SP999"}],
         "required_content_coverage": {}, "clip_spec": None,
         "interaction_spec": {"has_pause": False, "viewer_action": None, "thinking_time_seconds": 0}},
    ]
    checks = run_planner_integrity_check([], "EDUCATION", production_blocks, {}, {}, True)
    assert checks["asset_references_valid"] == "fail"


def test_out_of_order_timeline_fails_integrity():
    production_blocks = [
        {"content_block_id": "CB01", "block_order": 1,
         "timeline": [{"event_order": 2, "type": "VISUAL", "content": "x"}, {"event_order": 1, "type": "VISUAL", "content": "y"}],
         "required_content_coverage": {}, "clip_spec": None,
         "interaction_spec": {"has_pause": False, "viewer_action": None, "thinking_time_seconds": 0}},
    ]
    checks = run_planner_integrity_check([], "EDUCATION", production_blocks, {}, {}, True)
    assert checks["timeline_order_valid"] == "fail"


# --------------------------------------------------------------------------
# CASE W: 09/10 source rows unchanged
# --------------------------------------------------------------------------

def test_case_w_source_direction_unchanged_after_plan_build(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        direction_id = _seed_bundle(conn)
        before = conn.execute("SELECT preferred_format, final_format, integrity_json FROM video_directions WHERE id=?", (direction_id,)).fetchone()

    build_production_plan(db_path, clip_config=_CLIP_CONFIG, complexity_config=_COMPLEXITY_CONFIG)

    with connect(db_path) as conn:
        after = conn.execute("SELECT preferred_format, final_format, integrity_json FROM video_directions WHERE id=?", (direction_id,)).fetchone()
    assert dict(before) == dict(after)


# --------------------------------------------------------------------------
# CASE X: existing CLI backward compatibility
# --------------------------------------------------------------------------

def test_case_x_cli_backward_compatible():
    from research.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(["production-plan"])
    assert args.direction_id is None
    args2 = parser.parse_args(["production-plan", "--direction-id", "5"])
    assert args2.direction_id == 5
    for cmd in ["topics", "clicks", "packages", "blueprint", "script", "direction"]:
        parser.parse_args([cmd])


# --------------------------------------------------------------------------
# CASE Y: full regression handled by running the whole suite (see report) --
# additional structural coverage below.
# --------------------------------------------------------------------------

def test_select_target_direction_picks_latest_ready(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_bundle(conn, ready=0, title="old")
        target_id = _seed_bundle(conn, ready=1, title="new")

    row = select_target_direction(db_path)
    assert row["id"] == target_id


def test_select_target_direction_by_explicit_id(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        target_id = _seed_bundle(conn, ready=0)

    row = select_target_direction(db_path, direction_id=target_id)
    assert row["id"] == target_id


def test_ready_for_asset_generation_gate_requires_no_fail():
    assert ready_for_asset_generation_gate({"a": "pass", "b": "warning"}) is True
    assert ready_for_asset_generation_gate({"a": "pass", "b": "fail"}) is False


def test_visual_spec_hides_answer_for_mini_success():
    block = next(b for b in _bag_content_blocks() if b["content_block_id"] == "CB06")
    spec = build_visual_spec(block)
    assert spec["primary_visual_type"] in {"QUESTION"}
    assert spec["answer_hidden_until_attempt"] is True


def test_caption_spec_flags_approximation_label():
    block = _block("CB01", "CORE_EXPLANATION", "사운즈 라이커 플랜처럼 들릴 수 있습니다.")
    registry = SpeechAssetRegistry()
    plan = build_block_speech_plan(block, registry)
    caption = build_caption_spec(block, plan)
    assert caption["caption_mode"] in CAPTION_MODES
    assert caption["highlight_mode"] in HIGHLIGHT_MODES
    assert caption["approximation_label_required"] is True


def test_estimate_block_duration_includes_pause_seconds():
    block = next(b for b in _bag_content_blocks() if b["content_block_id"] == "CB06")
    registry = SpeechAssetRegistry()
    plan = build_block_speech_plan(block, registry)
    duration = estimate_block_duration(plan)
    assert duration >= 3.0  # at least the 3-second pause


def test_estimate_production_complexity_low_for_small_plan():
    assert estimate_production_complexity([], _COMPLEXITY_CONFIG) == "low"


def test_compute_planner_score_within_bounds(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_bundle(conn)
    result = build_production_plan(db_path, clip_config=_CLIP_CONFIG, complexity_config=_COMPLEXITY_CONFIG)
    assert 0.0 <= result["planner_score"] <= 100.0


# --------------------------------------------------------------------------
# Real BAG report generation end-to-end
# --------------------------------------------------------------------------

def test_report_generation_produces_expected_sections(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_bundle(conn)

    out_path = build_production_plan_report(db_path, tmp_path / "reports", clip_config=_CLIP_CONFIG, complexity_config=_COMPLEXITY_CONFIG)
    text = out_path.read_text(encoding="utf-8")
    for heading in [
        "# Production Plan Report",
        "## 1. Source Video Direction",
        "## 2. Production Blocks",
        "## 3. Speech Assets",
        "## 4. Block별 Speech 구조",
        "## 5. Required Content Coverage",
        "## 6. Production Complexity",
        "## 7. Integrity Check",
        "## 8. Ready for Asset Generation",
        "## 9. Known Limitations",
    ]:
        assert heading in text

    with connect(db_path) as conn:
        plan_row = conn.execute("SELECT * FROM production_plans").fetchone()
        block_rows = conn.execute("SELECT * FROM production_blocks WHERE production_plan_id=?", (plan_row["id"],)).fetchall()
        asset_rows = conn.execute("SELECT * FROM speech_assets WHERE production_plan_id=?", (plan_row["id"],)).fetchall()
    assert plan_row["final_format"] == "EDUCATION"
    assert plan_row["ready_for_asset_generation"] in (0, 1)
    assert len(block_rows) == 8
    assert len(asset_rows) > 0


def test_report_raises_when_no_direction_selected(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    try:
        build_production_plan_report(db_path, tmp_path / "reports", clip_config=_CLIP_CONFIG, complexity_config=_COMPLEXITY_CONFIG)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_upstream_data_unchanged_by_plan_build(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_bundle(conn)
        before = {
            t: conn.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"]
            for t in ("topic_candidates", "click_analysis_topics", "content_packages", "production_blueprints", "video_scripts", "video_directions", "block_directions")
        }

    build_production_plan_report(db_path, tmp_path / "reports", clip_config=_CLIP_CONFIG, complexity_config=_COMPLEXITY_CONFIG)

    with connect(db_path) as conn:
        after = {
            t: conn.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"]
            for t in ("topic_candidates", "click_analysis_topics", "content_packages", "production_blueprints", "video_scripts", "video_directions", "block_directions")
        }
    assert before == after


# ---------------------------------------------------------------------------
# 11-1: speech_fragment_integrity_safe -- punctuation-only Speech Assets (spec section 31, CASE A-D)
# ---------------------------------------------------------------------------

def test_case_a_dash_only_source_text_fails_speech_fragment_integrity():
    registry = SpeechAssetRegistry()
    registry.get_or_create("KO_NARRATION", NARRATOR_VOICE, "-")
    checks = run_planner_integrity_check([], "EDUCATION", [], registry.by_id(), {}, True)
    assert checks["speech_fragment_integrity_safe"] == "fail"


def test_case_b_whitespace_comma_only_fails_speech_fragment_integrity():
    registry = SpeechAssetRegistry()
    registry.get_or_create("KO_NARRATION", NARRATOR_VOICE, " , ")
    checks = run_planner_integrity_check([], "EDUCATION", [], registry.by_id(), {}, True)
    assert checks["speech_fragment_integrity_safe"] == "fail"


def test_case_c_ipa_not_mistaken_for_punctuation():
    assert is_punctuation_only_fragment("/æ/") is False
    registry = SpeechAssetRegistry()
    registry.get_or_create("EN_PHONEME_DEMO", NARRATOR_VOICE, "/æ/")
    checks = run_planner_integrity_check([], "EDUCATION", [], registry.by_id(), {}, True)
    assert checks["speech_fragment_integrity_safe"] == "pass"


def test_case_d_normalize_fragments_drops_empty_and_punctuation_only():
    tokens = [
        {"kind": "KOREAN", "text": "  "},
        {"kind": "KOREAN", "text": "-"},
        {"kind": "KOREAN", "text": ""},
        {"kind": "PHONEME", "text": "/b/"},
        {"kind": "KOREAN", "text": "실제 내용입니다"},
    ]
    normalized = normalize_fragments(tokens)
    assert normalized == [{"kind": "PHONEME", "text": "/b/"}, {"kind": "KOREAN", "text": "실제 내용입니다"}]


def test_case_e_cb03_dash_between_phonemes_produces_no_dash_asset():
    block = next(b for b in _bag_content_blocks() if b["content_block_id"] == "CB03")
    registry = SpeechAssetRegistry()
    plan = build_block_speech_plan(block, registry)
    all_segments = plan["pre_pause"] + plan["post_pause"]
    assert not any(seg["text"].strip() == "-" for seg in all_segments)
    assert not any(is_punctuation_only_fragment(seg["text"]) for seg in all_segments)


def test_case_f_cb05_dash_between_phonemes_produces_no_dash_asset():
    block = next(b for b in _bag_content_blocks() if b["content_block_id"] == "CB05")
    registry = SpeechAssetRegistry()
    plan = build_block_speech_plan(block, registry)
    all_segments = plan["pre_pause"] + plan["post_pause"]
    assert not any(seg["text"].strip() == "-" for seg in all_segments)
    assert not any(is_punctuation_only_fragment(seg["text"]) for seg in all_segments)


# ---------------------------------------------------------------------------
# 11-1: narration_fragment_safe -- orphaned Korean fragments from answer hiding (CASE G-N)
# ---------------------------------------------------------------------------

def test_case_g_orphan_fragment_missing_subject_detected():
    assert is_orphan_narration_fragment("가 있습니다.") is True


def test_case_h_orphan_fragment_missing_referent_detected():
    assert is_orphan_narration_fragment("에서 첫 글자 C는") is True


def test_case_i_normal_narration_not_flagged_as_orphan():
    assert is_orphan_narration_fragment("이번에는 소리를 하나씩 확인해보겠습니다.") is False


def test_case_j_cap_safe_reconstruction_has_no_orphan_speech():
    block = next(b for b in _bag_content_blocks() if b["content_block_id"] == "CB06")
    registry = SpeechAssetRegistry()
    plan = build_block_speech_plan(block, registry)
    timeline = build_timeline(block, plan)
    production_blocks = [{"content_block_id": "CB06", "block_order": 1, "timeline": timeline}]
    assert check_narration_fragment_safe(production_blocks, registry.by_id()) == "pass"


def test_case_k_cap_visual_before_pause():
    block = next(b for b in _bag_content_blocks() if b["content_block_id"] == "CB06")
    registry = SpeechAssetRegistry()
    plan = build_block_speech_plan(block, registry)
    timeline = build_timeline(block, plan)
    pause_idx = next(i for i, ev in enumerate(timeline) if ev["type"] == "PAUSE")
    visual_idx = next(i for i, ev in enumerate(timeline) if ev["type"] == "VISUAL")
    assert visual_idx < pause_idx
    assert timeline[visual_idx]["content"] == "CAP"


def test_case_l_cap_en_native_answer_only_after_pause():
    block = next(b for b in _bag_content_blocks() if b["content_block_id"] == "CB06")
    registry = SpeechAssetRegistry()
    plan = build_block_speech_plan(block, registry)
    timeline = build_timeline(block, plan)
    pause_idx = next(i for i, ev in enumerate(timeline) if ev["type"] == "PAUSE")
    en_native_indices = [
        i for i, ev in enumerate(timeline)
        if ev["type"] == "SPEECH" and registry.by_id()[ev["speech_asset_id"]]["speech_mode"] == "EN_NATIVE"
    ]
    assert en_native_indices
    assert all(i > pause_idx for i in en_native_indices)
    assert any(registry.by_id()[timeline[i]["speech_asset_id"]]["source_text"] == "CAP" for i in en_native_indices)


def test_case_m_cap_answer_phonemes_only_after_pause():
    block = next(b for b in _bag_content_blocks() if b["content_block_id"] == "CB06")
    registry = SpeechAssetRegistry()
    plan = build_block_speech_plan(block, registry)
    timeline = build_timeline(block, plan)
    pause_idx = next(i for i, ev in enumerate(timeline) if ev["type"] == "PAUSE")
    phoneme_indices = [
        i for i, ev in enumerate(timeline)
        if ev["type"] == "SPEECH" and registry.by_id()[ev["speech_asset_id"]]["speech_mode"] == "EN_PHONEME_DEMO"
    ]
    assert {registry.by_id()[timeline[i]["speech_asset_id"]]["source_text"] for i in phoneme_indices} == {"/k/", "/æ/", "/p/"}
    assert all(i > pause_idx for i in phoneme_indices)


def test_case_n_cap_thinking_time_3000ms_preserved_in_new_structure():
    block = next(b for b in _bag_content_blocks() if b["content_block_id"] == "CB06")
    registry = SpeechAssetRegistry()
    plan = build_block_speech_plan(block, registry)
    timeline = build_timeline(block, plan)
    pause_ev = next(ev for ev in timeline if ev["type"] == "PAUSE")
    assert pause_ev["duration_ms"] == 3000


def test_orphan_fragment_with_no_safe_preceding_context_fails_check():
    # Sabotage: an orphan-looking fragment with a plain KOREAN predecessor (no adjacent
    # English/phoneme/visual context) -- the actual CB06-style regression shape.
    registry = SpeechAssetRegistry()
    first_id = registry.get_or_create("KO_NARRATION", NARRATOR_VOICE, "모자를 뜻하는 단어가 있습니다.")
    orphan_id = registry.get_or_create("KO_NARRATION", NARRATOR_VOICE, "에서 첫 글자 C는")
    timeline = [
        {"event_order": 1, "type": "SPEECH", "speech_asset_id": first_id},
        {"event_order": 2, "type": "SPEECH", "speech_asset_id": orphan_id},
    ]
    production_blocks = [{"content_block_id": "CB06", "block_order": 1, "timeline": timeline}]
    assert check_narration_fragment_safe(production_blocks, registry.by_id()) == "fail"


def test_orphan_fragment_adjacent_to_english_word_is_not_a_false_positive():
    # "MAP에서 M은" immediately follows a spoken EN_NATIVE "MAP" -- the pre-existing, documented
    # segmentation limitation (particle glued to an extracted token), not the CB06 deletion bug.
    registry = SpeechAssetRegistry()
    en_id = registry.get_or_create("EN_NATIVE", NARRATOR_VOICE, "MAP")
    ko_id = registry.get_or_create("KO_NARRATION", NARRATOR_VOICE, "에서 M은 /m/ 소리를 냅니다.")
    timeline = [
        {"event_order": 1, "type": "SPEECH", "speech_asset_id": en_id},
        {"event_order": 2, "type": "SPEECH", "speech_asset_id": ko_id},
    ]
    production_blocks = [{"content_block_id": "CB05", "block_order": 1, "timeline": timeline}]
    assert check_narration_fragment_safe(production_blocks, registry.by_id()) == "pass"


# ---------------------------------------------------------------------------
# 11-1: educational_wording_preserved -- "고유한 소리" family must not reappear (CASE T/U)
# ---------------------------------------------------------------------------

def test_case_t_dangerous_generalization_fails_educational_wording_check():
    registry = SpeechAssetRegistry()
    asset_id = registry.get_or_create(
        "KO_NARRATION", NARRATOR_VOICE, "각 글자가 이 단어에서 내는 고유한 소리를 하나씩 찾아내야 합니다.",
    )
    timeline = [{"event_order": 1, "type": "SPEECH", "speech_asset_id": asset_id}]
    production_blocks = [{"content_block_id": "CB02", "block_order": 1, "timeline": timeline}]
    assert check_educational_wording_preserved(production_blocks, registry.by_id()) == "fail"


def test_case_u_safe_scoped_wording_passes_educational_wording_check():
    registry = SpeechAssetRegistry()
    asset_id = registry.get_or_create(
        "KO_NARRATION", NARRATOR_VOICE, "각 글자가 이 단어에서 나타내는 소리를 순서대로 이어 붙여 읽습니다.",
    )
    timeline = [{"event_order": 1, "type": "SPEECH", "speech_asset_id": asset_id}]
    production_blocks = [{"content_block_id": "CB02", "block_order": 1, "timeline": timeline}]
    assert check_educational_wording_preserved(production_blocks, registry.by_id()) == "pass"


def test_educational_wording_preserved_wired_into_full_integrity_check(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_bundle(conn)
    result = build_production_plan(db_path, clip_config=_CLIP_CONFIG, complexity_config=_COMPLEXITY_CONFIG)
    assert result["integrity_checks"]["educational_wording_preserved"] == "pass"


# ---------------------------------------------------------------------------
# 11-1: STYLE_INTENT vs FACTUAL_CONTENT required_content classification (CASE O-S)
# ---------------------------------------------------------------------------

def test_case_o_ending_greeting_classified_as_style_intent():
    assert classify_required_content_type("자연스럽고 부담 없는 마무리 인사") == "STYLE_INTENT"


def test_case_r_factual_content_classification_preserved():
    assert classify_required_content_type("BAG 예시 사용") == "FACTUAL_CONTENT"
    assert classify_required_content_type("BAG에서 B는 /b/") == "FACTUAL_CONTENT"
    # 11-2: time-structure wording takes priority over a bare digit -- "3초" must not be claimed by
    # the FACTUAL digit signal just because a number happens to be present (spec section 4).
    assert classify_required_content_type("3초 생각 시간 후 CAP 정답 확인") == "STRUCTURAL_REQUIREMENT"


def test_case_p_style_intent_covered_with_real_ending_narration():
    cb08 = {"content_block_id": "CB08", "learning_function": "RESOLUTION"}
    registry = SpeechAssetRegistry()
    asset_id = registry.get_or_create(
        "KO_NARRATION", NARRATOR_VOICE,
        "오늘 영상이 도움이 되셨다면 함께 연습을 이어가 보세요. 시청해 주셔서 감사합니다.",
    )
    pb = {"content_block_id": "CB08", "block_order": 8, "timeline": [{"event_order": 1, "type": "SPEECH", "speech_asset_id": asset_id}]}
    covered = is_required_content_covered("자연스럽고 부담 없는 마무리 인사", [], True, pb, registry.by_id())
    assert covered is True


def test_case_q_style_intent_not_auto_passed_without_narration():
    pb = {"content_block_id": "CB08", "block_order": 8, "timeline": []}
    covered = is_required_content_covered("자연스럽고 부담 없는 마무리 인사", [], True, pb, {})
    assert covered is False


def test_case_s_factual_content_without_match_still_fails():
    pb = {"content_block_id": "CB03", "block_order": 1, "timeline": []}
    covered = is_required_content_covered("BAG 예시 사용", [], False, pb, {})
    assert covered is False


def test_cb08_style_intent_covered_in_full_pipeline(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_bundle(conn)
    result = build_production_plan(db_path, clip_config=_CLIP_CONFIG, complexity_config=_COMPLEXITY_CONFIG)
    cb08 = next(pb for pb in result["production_blocks"] if pb["content_block_id"] == "CB08")
    assert cb08["required_content_coverage"]["자연스럽고 부담 없는 마무리 인사"] == []  # no lexical overlap
    assert result["integrity_checks"]["required_content_covered"] == "pass"  # covered via style evidence


# ---------------------------------------------------------------------------
# 11-1: full-pipeline success condition (spec section 40) -- the corrected BAG plan must be
# ready for asset generation with all 22 Integrity Checks passing.
# ---------------------------------------------------------------------------

def test_full_bag_plan_reaches_ready_for_asset_generation(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_bundle(conn)
    result = build_production_plan(db_path, clip_config=_CLIP_CONFIG, complexity_config=_COMPLEXITY_CONFIG)
    checks = result["integrity_checks"]
    assert len(checks) >= 22
    for name, status in checks.items():
        assert status == "pass", f"{name} unexpectedly failed"
    assert result["ready_for_asset_generation"] is True
    assert not any(
        is_punctuation_only_fragment(a["source_text"]) for a in result["speech_assets"] if a["speech_mode"] != "EN_PHONEME_DEMO"
    )
    en_native = {a["source_text"] for a in result["speech_assets"] if a["speech_mode"] == "EN_NATIVE"}
    assert {"BAG", "BAT", "MAP", "CAP"}.issubset(en_native)

    # 11-2 CASE Y/Z/AA/AB/AC: the two previously-false-negative real items must now be covered via
    # type-appropriate evidence, and the rest of the plan must be untouched by the fix.
    by_item = {ev["required_content"]: ev for ev in result["required_content_evaluations"]}
    cb06_ev = by_item["정답 공개 전 3초 생각 시간 부여"]
    assert cb06_ev["type"] == "STRUCTURAL_REQUIREMENT"
    assert cb06_ev["status"] == "covered"  # CASE Y
    cb08_ev = by_item["차분하고 권위적이지 않은 마무리 멘트"]
    assert cb08_ev["type"] == "STYLE_INTENT"
    assert cb08_ev["status"] == "covered"  # CASE Z
    assert checks["required_content_covered"] == "pass"  # CASE AA
    assert len([s for s in checks.values() if s == "fail"]) == 0  # CASE AB
    assert result["ready_for_asset_generation"] is True  # CASE AC
    assert len(result["production_blocks"]) == 8
    cap_pb = next(pb for pb in result["production_blocks"] if pb["content_block_id"] == "CB06")
    cap_timeline_types = [ev["type"] for ev in cap_pb["timeline"] if ev["type"] in {"VISUAL", "PAUSE", "SPEECH"}]
    pause_i = cap_timeline_types.index("PAUSE")
    assert cap_timeline_types[:pause_i].count("VISUAL") >= 1
    pause_ev = next(ev for ev in cap_pb["timeline"] if ev["type"] == "PAUSE")
    assert pause_ev["duration_ms"] == 3000


# ---------------------------------------------------------------------------
# 11-2: required_content Type Classification (spec section 28, CASE A-F)
# ---------------------------------------------------------------------------

def test_case_a_11_2_factual_word_example_classified_factual():
    assert classify_required_content_type("BAG 예시 단어 사용") == "FACTUAL_CONTENT"


def test_case_b_11_2_time_structure_classified_structural():
    assert classify_required_content_type("정답 공개 전 3초 생각 시간 부여") == "STRUCTURAL_REQUIREMENT"


def test_case_c_11_2_viewer_attempt_classified_interaction():
    assert classify_required_content_type("시청자가 직접 읽어본다") == "INTERACTION_REQUIREMENT"


def test_case_d_11_2_tone_constraint_classified_style():
    assert classify_required_content_type("차분하고 권위적이지 않은 마무리 멘트") == "STYLE_INTENT"


def test_case_e_11_2_concise_wording_classified_style():
    assert classify_required_content_type("간결한 마무리 인사") == "STYLE_INTENT"


def test_case_f_11_2_mixed_structural_interaction_handled_without_crash():
    result_type = classify_required_content_type("3초 생각 시간 + 직접 읽기")
    assert result_type == "STRUCTURAL_REQUIREMENT"  # Priority 1 wins over Priority 2


# ---------------------------------------------------------------------------
# 11-2: STRUCTURAL_REQUIREMENT Coverage (spec section 29, CASE G-K)
# ---------------------------------------------------------------------------

def _structural_pb(pause_duration_ms, answer_before_pause=False, include_visual=True, include_pause=True):
    registry = SpeechAssetRegistry()
    visual_asset = registry.get_or_create("EN_NATIVE", NARRATOR_VOICE, "CAP")
    events = []
    order = 1
    if answer_before_pause:
        events.append({"event_order": order, "type": "SPEECH", "speech_asset_id": visual_asset})
        order += 1
    if include_visual:
        events.append({"event_order": order, "type": "VISUAL", "visual_role": "TARGET_WORD", "content": "CAP"})
        order += 1
    if include_pause:
        events.append({"event_order": order, "type": "PAUSE", "duration_ms": pause_duration_ms, "pause_visual_behavior": "THINKING_DOTS"})
        order += 1
    if not answer_before_pause:
        events.append({"event_order": order, "type": "SPEECH", "speech_asset_id": visual_asset})
        order += 1
    pb = {"content_block_id": "CB06", "block_order": 1, "timeline": events}
    return pb, registry.by_id()


def test_case_g_pause_3000ms_with_answer_after_covered():
    pb, assets = _structural_pb(3000)
    status, evidence, method = check_structural_requirement_coverage("정답 공개 전 3초 생각 시간 부여", pb, assets)
    assert status == "covered"
    assert evidence
    assert method == "timeline_order_and_duration"


def test_case_h_pause_1000ms_for_3_second_requirement_fails():
    pb, assets = _structural_pb(1000)
    status, _, _ = check_structural_requirement_coverage("정답 공개 전 3초 생각 시간 부여", pb, assets)
    assert status == "uncovered"


def test_case_i_answer_before_pause_fails():
    pb, assets = _structural_pb(3000, answer_before_pause=True)
    status, _, _ = check_structural_requirement_coverage("정답 공개 전 3초 생각 시간 부여", pb, assets)
    assert status == "uncovered"


def test_case_j_visual_then_pause_then_answer_passes():
    pb, assets = _structural_pb(3000, include_visual=True)
    status, evidence, _ = check_structural_requirement_coverage("정답 공개 전 3초 생각 시간 부여", pb, assets)
    assert status == "covered"


def test_case_k_thinking_time_metadata_without_timeline_pause_fails():
    pb, assets = _structural_pb(3000, include_pause=False)
    status, _, _ = check_structural_requirement_coverage("정답 공개 전 3초 생각 시간 부여", pb, assets)
    assert status == "uncovered"


# ---------------------------------------------------------------------------
# 11-2: INTERACTION_REQUIREMENT Coverage (spec section 30, CASE L-O)
# ---------------------------------------------------------------------------

def test_case_l_viewer_action_and_attempt_narration_covered():
    registry = SpeechAssetRegistry()
    asset_id = registry.get_or_create("KO_NARRATION", NARRATOR_VOICE, _SAFE_READ_INVITATION)
    pb = {
        "content_block_id": "CB06", "timeline": [{"event_order": 1, "type": "SPEECH", "speech_asset_id": asset_id}],
        "interaction_spec": {"viewer_action": "직접 읽어본다"}, "production_intent": None,
    }
    content_block = {"viewer_action": "직접 읽어본다", "learning_function": "PRACTICE"}
    status, evidence, _ = check_interaction_requirement_coverage("시청자 스스로 소리 조합 시도 안내", content_block, pb, registry.by_id())
    assert status == "covered"
    assert evidence


def test_case_m_no_viewer_action_no_attempt_narration_fails():
    pb = {"content_block_id": "CB06", "timeline": [], "interaction_spec": {}, "production_intent": None}
    content_block = {"viewer_action": None, "learning_function": "CORE_EXPLANATION"}
    status, _, _ = check_interaction_requirement_coverage("시청자 스스로 소리 조합 시도 안내", content_block, pb, {})
    assert status == "uncovered"


def test_case_n_mini_success_full_structure_covered():
    registry = SpeechAssetRegistry()
    en_asset = registry.get_or_create("EN_NATIVE", NARRATOR_VOICE, "CAP")
    confirm_asset = registry.get_or_create("KO_NARRATION", NARRATOR_VOICE, "정말 잘 읽어냈습니다, 성공입니다.")
    timeline = [
        {"event_order": 1, "type": "PAUSE", "duration_ms": 3000, "pause_visual_behavior": "THINKING_DOTS"},
        {"event_order": 2, "type": "SPEECH", "speech_asset_id": en_asset},
        {"event_order": 3, "type": "SPEECH", "speech_asset_id": confirm_asset},
    ]
    pb = {"content_block_id": "CB06", "timeline": timeline, "interaction_spec": {"viewer_action": "직접 읽어본다"}, "production_intent": None}
    content_block = {"viewer_action": "직접 읽어본다", "learning_function": "MINI_SUCCESS", "thinking_time_seconds": 3}
    status, evidence, method = check_interaction_requirement_coverage("시청자의 첫 읽기 성공 경험 격려", content_block, pb, registry.by_id())
    assert status == "covered"
    assert method == "mini_success_attempt_and_confirmation_evidence"


def test_case_o_mini_success_label_without_real_attempt_fails():
    pb = {"content_block_id": "CB06", "timeline": [], "interaction_spec": {}, "production_intent": None}
    content_block = {"viewer_action": None, "learning_function": "MINI_SUCCESS", "thinking_time_seconds": 0}
    status, _, _ = check_interaction_requirement_coverage("시청자의 첫 읽기 성공 경험 격려", content_block, pb, {})
    assert status == "uncovered"


# ---------------------------------------------------------------------------
# 11-2: STYLE_INTENT Coverage (spec section 31, CASE P-T)
# ---------------------------------------------------------------------------

def test_case_p_final_block_natural_closing_no_blacklist_covered():
    registry = SpeechAssetRegistry()
    asset_id = registry.get_or_create("KO_NARRATION", NARRATOR_VOICE, "다음 시간에도 함께 확인해 보겠습니다.")
    pb = {"content_block_id": "CB08", "timeline": [{"event_order": 1, "type": "SPEECH", "speech_asset_id": asset_id}]}
    status, evidence, _ = check_style_intent_coverage(pb, True, registry.by_id())
    assert status == "covered"
    assert evidence


def test_case_q_no_final_block_narration_fails():
    pb = {"content_block_id": "CB08", "timeline": []}
    status, _, _ = check_style_intent_coverage(pb, True, {})
    assert status == "uncovered"


def test_case_r_authoritative_tone_fails_style_requirement():
    registry = SpeechAssetRegistry()
    asset_id = registry.get_or_create("KO_NARRATION", NARRATOR_VOICE, "무조건 하세요. 반드시 해야 합니다. 다음 시간에 만나요.")
    pb = {"content_block_id": "CB08", "timeline": [{"event_order": 1, "type": "SPEECH", "speech_asset_id": asset_id}]}
    status, _, _ = check_style_intent_coverage(pb, True, registry.by_id())
    assert status == "uncovered"


def test_case_s_concise_closing_covered():
    registry = SpeechAssetRegistry()
    asset_id = registry.get_or_create("KO_NARRATION", NARRATOR_VOICE, "시청해 주셔서 감사합니다.")
    pb = {"content_block_id": "CB08", "timeline": [{"event_order": 1, "type": "SPEECH", "speech_asset_id": asset_id}]}
    status, _, _ = check_style_intent_coverage(pb, True, registry.by_id())
    assert status == "covered"


def test_case_t_style_intent_type_alone_never_auto_covers():
    registry = SpeechAssetRegistry()
    asset_id = registry.get_or_create("KO_NARRATION", NARRATOR_VOICE, "그럼 다음 문제로 넘어가겠습니다.")
    pb = {"content_block_id": "CB08", "timeline": [{"event_order": 1, "type": "SPEECH", "speech_asset_id": asset_id}]}
    status, _, _ = check_style_intent_coverage(pb, True, registry.by_id())
    assert status == "uncovered"


# ---------------------------------------------------------------------------
# 11-2: Existing Factual Coverage regression (spec section 32, CASE U-X)
# ---------------------------------------------------------------------------

def test_case_u_bag_example_coverage_still_passes():
    block = _block("CB03", "CORE_EXPLANATION", "BAG 예시를 봅니다.", required_content=["BAG 예시"])
    registry = SpeechAssetRegistry()
    plan = build_block_speech_plan(block, registry)
    timeline = build_timeline(block, plan)
    coverage = compute_required_content_coverage(block, timeline, registry.by_id())
    evaluation = evaluate_required_content_item("BAG 예시", block, {"content_block_id": "CB03", "timeline": timeline}, registry.by_id(), coverage["BAG 예시"], False)
    assert evaluation["type"] == "FACTUAL_CONTENT"
    assert evaluation["status"] == "covered"


def test_case_v_phoneme_breakdown_coverage_still_passes():
    block = next(b for b in _bag_content_blocks() if b["content_block_id"] == "CB03")
    registry = SpeechAssetRegistry()
    plan = build_block_speech_plan(block, registry)
    timeline = build_timeline(block, plan)
    coverage = compute_required_content_coverage(block, timeline, registry.by_id())
    assert coverage["B /b/ A /æ/ G /g/ 음소 제시"]


def test_case_w_cap_target_coverage_still_passes():
    block = next(b for b in _bag_content_blocks() if b["content_block_id"] == "CB06")
    registry = SpeechAssetRegistry()
    plan = build_block_speech_plan(block, registry)
    timeline = build_timeline(block, plan)
    coverage = compute_required_content_coverage(block, timeline, registry.by_id())
    assert coverage["CAP 예시 사용"]


def test_case_x_missing_factual_target_still_fails():
    block = _block("CB03", "CORE_EXPLANATION", "BAG 예시를 봅니다.", required_content=["완전히 다른 단어 목록 확인"])
    registry = SpeechAssetRegistry()
    plan = build_block_speech_plan(block, registry)
    timeline = build_timeline(block, plan)
    coverage = compute_required_content_coverage(block, timeline, registry.by_id())
    evaluation = evaluate_required_content_item(
        "완전히 다른 단어 목록 확인", block, {"content_block_id": "CB03", "timeline": timeline}, registry.by_id(),
        coverage["완전히 다른 단어 목록 확인"], False,
    )
    assert evaluation["status"] == "uncovered"
