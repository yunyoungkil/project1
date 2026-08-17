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
    build_block_speech_plan,
    build_caption_spec,
    build_pause_event,
    build_production_plan,
    build_production_plan_report,
    build_timeline,
    build_visual_spec,
    classify_speech_mode,
    compute_planner_score,
    compute_required_content_coverage,
    estimate_block_duration,
    estimate_production_complexity,
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
        _block("CB03", "CORE_EXPLANATION", "BAG에서 글자 소리를 하나씩 살펴보겠습니다. 이 단어에서 B는 /b/ 소리를 냅니다. 그리고 가운데 A는 /æ/ 소리를 냅니다. 마지막 G는 /g/ 소리를 냅니다. 이제 이어 붙이면 BAG가 됩니다.",
               required_content=["BAG 예시 사용", "B /b/ A /æ/ G /g/ 음소 제시"], section_number=2),
        _block("CB04", "DEMONSTRATION", "BAT에서 T는 /t/ 소리를 냅니다.", required_content=["BAT 예시 사용"], section_number=3),
        _block("CB05", "PRACTICE", "MAP에서 M은 /m/, P는 /p/ 소리를 냅니다.", required_content=["MAP 예시 사용"], section_number=4),
        _block("CB06", "MINI_SUCCESS", "이 단어 CAP에서는 C가 /k/ 소리를 냅니다. 가운데 A는 /æ/, 끝 글자 P는 /p/ 소리입니다. 이 세 소리를 순서대로 직접 소리 내어 이어 붙여보세요.",
               required_content=["CAP 예시 사용", "CAP에서 C가 /k/ 소리를 냄을 안내"],
               viewer_action="정답 공개 전에 CAP을 직접 읽어본다.", thinking_time_seconds=3, section_number=5),
        _block("CB07", "RECAP", "오늘 BAG, BAT, MAP, CAP을 배웠습니다.", section_number=6),
        _block("CB08", "RESOLUTION", "영어는 이해할수록 쉬워집니다.", section_number=None),
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
