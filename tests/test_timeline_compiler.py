import json
from pathlib import Path

import pytest

from research.asset_generator import (
    _persist_generated_assets,
    record_pronunciation_review,
    record_tone_consistency_review,
    run_asset_generation,
    synthesize_asset,
)
from research.db import connect, init_db
from research.render_spec import run_render_spec
from research.timeline_compiler import (
    TIMELINE_VERSION,
    build_timeline,
    compile_global_timeline,
    compile_scene_events,
    compile_scene_timeline,
    run_timeline_compiler,
    run_timeline_integrity_check,
    validate_timeline,
    validate_timeline_entry_gate,
)
from tests.test_render_spec import FakeTTSClient, _asset_by_id, _gen, _seed_render_plan, _speech_assets_for


def _make_ready_plan_with_render_spec(tmp_path, db_path):
    """Reuses 13-1's exact CAP DIRECT_WORD-fails/CONTEXTUAL_WORD-fallback fixture, then runs the
    real render-spec orchestration (persist + file write) so the DB row and JSON file genuinely
    agree -- exercising the same entry gate real CLI usage would hit, not a hand-built spec."""
    with connect(db_path) as conn:
        plan_id = _seed_render_plan(conn)
    assets = _speech_assets_for(db_path, plan_id)
    ko, bag, cap = _asset_by_id(assets, "SP001"), _asset_by_id(assets, "SP002"), _asset_by_id(assets, "SP003")
    client = FakeTTSClient()

    _gen(db_path, plan_id, ko, client, tmp_path)
    _gen(db_path, plan_id, bag, client, tmp_path)
    record_pronunciation_review(db_path, plan_id, "SP002", "APPROVED")
    record_tone_consistency_review(db_path, plan_id, "SP002", "APPROVED")
    _gen(db_path, plan_id, cap, client, tmp_path)
    record_pronunciation_review(db_path, plan_id, "SP003", "REGENERATE_REQUIRED")
    _gen(db_path, plan_id, cap, client, tmp_path, asset_id="SP003::CONTEXTUAL_WORD", pronunciation_strategy="CONTEXTUAL_WORD")
    record_pronunciation_review(db_path, plan_id, "SP003::CONTEXTUAL_WORD", "APPROVED")
    record_tone_consistency_review(db_path, plan_id, "SP003::CONTEXTUAL_WORD", "APPROVED")

    assets_dir = tmp_path / "assets"
    run_asset_generation(db_path, client, mode="SAMPLE", tts_model="m", assets_dir=assets_dir, plan_id=plan_id)
    run_asset_generation(db_path, client, mode="FULL", tts_model="m", assets_dir=assets_dir, plan_id=plan_id)

    reports_dir = tmp_path / "reports"
    spec_result = run_render_spec(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert spec_result["blocked"] is False
    return plan_id, assets_dir, reports_dir


# CASE A: Ready for Timeline Compilation false -> reject
def test_case_a_not_ready_rejects_entry(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_render_plan(conn)
    entry_gate = validate_timeline_entry_gate(db_path, tmp_path / "assets", plan_id=plan_id)
    assert entry_gate["pass"] is False
    assert entry_gate["reason"]


# CASE B: scene order preserved
def test_case_b_scene_order_preserved(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_render_spec(tmp_path, db_path)
    result = run_timeline_compiler(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["pass"] is True
    scene_ids = [s["scene_id"] for s in result["timeline"]["scenes"]]
    assert scene_ids == ["CB01", "CB02"]


# CASE C: audio duration preserved verbatim from the Render Spec's audio_elements
def test_case_c_audio_duration_preserved(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_render_spec(tmp_path, db_path)
    result = run_timeline_compiler(db_path, assets_dir, reports_dir, plan_id=plan_id)
    entry_gate = validate_timeline_entry_gate(db_path, assets_dir, plan_id=plan_id)
    spec_audio = {a["asset_id"]: a["duration_ms"] for s in entry_gate["spec"]["scenes"] for a in s["audio_elements"]}
    for scene in result["timeline"]["scenes"]:
        for e in scene["events"]:
            if e["event_type"] == "AUDIO":
                assert e["duration_ms"] == spec_audio[e["asset_id"]]


# CASE D: consecutive audio events chain start/end exactly (no gap, no invented timing)
def test_case_d_consecutive_audio_events_chain(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_render_spec(tmp_path, db_path)
    result = run_timeline_compiler(db_path, assets_dir, reports_dir, plan_id=plan_id)
    cb01 = next(s for s in result["timeline"]["scenes"] if s["scene_id"] == "CB01")
    audio_events = sorted([e for e in cb01["events"] if e["event_type"] == "AUDIO"], key=lambda e: e["start_ms"])
    assert len(audio_events) == 2
    assert audio_events[0]["end_ms"] == audio_events[1]["start_ms"]


# CASE F/G: PAUSE exactly 3000ms, advances the cursor by exactly 3000ms
def test_case_f_g_pause_exactly_3000ms_advances_cursor(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_render_spec(tmp_path, db_path)
    result = run_timeline_compiler(db_path, assets_dir, reports_dir, plan_id=plan_id)
    cb02 = next(s for s in result["timeline"]["scenes"] if s["scene_id"] == "CB02")
    pause = next(e for e in cb02["events"] if e["event_type"] == "PAUSE")
    assert pause["duration_ms"] == 3000
    assert pause["end_ms"] - pause["start_ms"] == 3000


# CASE H: ANSWER_REVEAL_BARRIER reveal_not_before_ms >= pause.end_ms, and the answer audio
# actually starts at/after it (not merely unconstrained)
def test_case_h_answer_reveal_barrier_gates_real_answer(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_render_spec(tmp_path, db_path)
    result = run_timeline_compiler(db_path, assets_dir, reports_dir, plan_id=plan_id)
    cb02 = next(s for s in result["timeline"]["scenes"] if s["scene_id"] == "CB02")
    pause = next(e for e in cb02["events"] if e["event_type"] == "PAUSE")
    barrier = next(e for e in cb02["events"] if e["event_type"] == "ANSWER_REVEAL_BARRIER")
    answer_audio = next(e for e in cb02["events"] if e["event_type"] == "AUDIO" and e["source_speech_asset_id"] == "SP003")
    assert barrier["reveal_not_before_ms"] == pause["end_ms"]
    assert answer_audio["start_ms"] >= barrier["reveal_not_before_ms"]
    assert result["validation"]["checks"]["answer_not_revealed_before_pause"] is True


# CASE I: answer revealed before the pause -> validation FAILs (constructed regression, not real data)
def test_case_i_answer_revealed_before_pause_fails_validation():
    scene = {
        "scene_id": "CBX", "content_block_id": "CBX", "scene_role": "MINI_SUCCESS", "visual_intent": "QUESTION_THEN_REVEAL",
        "answer_reveal_policy": {"reveal_after_pause": True}, "viewer_action": None,
        "audio_elements": [
            {"asset_id": "A1", "source_speech_asset_id": "SPX", "generation_unit_id": "SPX", "speech_mode": "EN_NATIVE", "duration_ms": 500, "event_order": 1, "segment_index": None},
        ],
        "pause_requirements": [{"duration_ms": 3000, "answer_reveal_allowed": False, "event_order": 2}],
        "emphasis_targets": [],
    }
    timeline = build_timeline({"production_plan_id": 1, "spec_version": "13.1", "scenes": [scene]})
    validation = validate_timeline({"scenes": [scene]}, timeline)
    # The only audio event starts at 0ms, before the pause -- the barrier requires >= pause.end_ms
    # but no EN_NATIVE audio exists at/after it, so the invariant must fail.
    assert validation["checks"]["answer_not_revealed_before_pause"] is False


# CASE J: viewer_action text preserved verbatim
def test_case_j_viewer_action_text_preserved(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_render_spec(tmp_path, db_path)
    result = run_timeline_compiler(db_path, assets_dir, reports_dir, plan_id=plan_id)
    with connect(db_path) as conn:
        interaction_spec = json.loads(conn.execute(
            "SELECT interaction_spec_json FROM production_blocks WHERE production_plan_id = ? AND content_block_id = 'CB02'",
            (plan_id,),
        ).fetchone()["interaction_spec_json"])
    cb02 = next(s for s in result["timeline"]["scenes"] if s["scene_id"] == "CB02")
    va = next(e for e in cb02["events"] if e["event_type"] == "VIEWER_ACTION")
    assert va["viewer_action"] == interaction_spec["viewer_action"]
    assert result["validation"]["checks"]["viewer_action_text_preserved"] is True


# CASE K: scene duration = max end_ms of its timed events
def test_case_k_scene_duration_calculation(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_render_spec(tmp_path, db_path)
    result = run_timeline_compiler(db_path, assets_dir, reports_dir, plan_id=plan_id)
    cb02 = next(s for s in result["timeline"]["scenes"] if s["scene_id"] == "CB02")
    timed = [e for e in cb02["events"] if e["event_type"] in {"AUDIO", "PAUSE"}]
    assert cb02["duration_ms"] == cb02["end_ms"] - cb02["start_ms"]
    assert cb02["end_ms"] == max(e["end_ms"] for e in timed)


# CASE L/M: no arbitrary inter-scene gap, no scene overlap -- scenes chain exactly end-to-end
def test_case_l_m_scenes_chain_with_zero_gap_no_overlap(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_render_spec(tmp_path, db_path)
    result = run_timeline_compiler(db_path, assets_dir, reports_dir, plan_id=plan_id)
    scenes = result["timeline"]["scenes"]
    for i in range(len(scenes) - 1):
        assert scenes[i]["end_ms"] == scenes[i + 1]["start_ms"]
    assert result["validation"]["checks"]["no_scene_overlap"] is True


# CASE N: negative timestamp is structurally impossible (pure-accumulation construction)
def test_case_n_no_negative_timestamps(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_render_spec(tmp_path, db_path)
    result = run_timeline_compiler(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["validation"]["checks"]["no_negative_timestamps"] is True


# CASE O: global video duration accuracy -- video.duration_ms == last scene's end_ms
def test_case_o_global_duration_matches_last_scene(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_render_spec(tmp_path, db_path)
    result = run_timeline_compiler(db_path, assets_dir, reports_dir, plan_id=plan_id)
    timeline = result["timeline"]
    assert timeline["video"]["duration_ms"] == timeline["scenes"][-1]["end_ms"]
    assert timeline["video"]["end_ms"] == timeline["video"]["duration_ms"]
    assert timeline["video"]["start_ms"] == 0


# CASE P: same Render Spec -> same Timeline (determinism, recompiled fresh not hash-shortcut)
def test_case_p_determinism_recompile_matches(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_render_spec(tmp_path, db_path)
    entry_gate = validate_timeline_entry_gate(db_path, assets_dir, plan_id=plan_id)
    t1 = build_timeline(entry_gate["spec"])
    t2 = build_timeline(entry_gate["spec"])
    assert json.dumps(t1, sort_keys=True) == json.dumps(t2, sort_keys=True)
    result = run_timeline_compiler(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["integrity_checks"]["timeline_deterministic"] is True


# CASE Q/R: CAP active asset stays CONTEXTUAL_WORD; the failed DIRECT_WORD (SP003 bare) is unused
def test_case_q_r_cap_active_asset_is_contextual_word_fallback(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_render_spec(tmp_path, db_path)
    result = run_timeline_compiler(db_path, assets_dir, reports_dir, plan_id=plan_id)
    cb02 = next(s for s in result["timeline"]["scenes"] if s["scene_id"] == "CB02")
    cap_audio = [e for e in cb02["events"] if e["event_type"] == "AUDIO" and e["source_speech_asset_id"] == "SP003"]
    assert len(cap_audio) == 1
    assert cap_audio[0]["asset_id"] == "SP003::CONTEXTUAL_WORD"


# CASE S: experimental EN_NATIVE variants (LOWERCASE_WORD/MINIMAL_CONTEXT_WORD) are never used
def test_case_s_experimental_variants_unused(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_render_spec(tmp_path, db_path)
    result = run_timeline_compiler(db_path, assets_dir, reports_dir, plan_id=plan_id)
    all_asset_ids = [
        e["asset_id"] for s in result["timeline"]["scenes"] for e in s["events"] if e["event_type"] == "AUDIO"
    ]
    assert not any("LOWERCASE_WORD" in a or "MINIMAL_CONTEXT_WORD" in a for a in all_asset_ids)


# CASE U/V: fps null still allows compilation, and never causes a frame number to be invented
def test_case_u_v_fps_null_allows_compilation_no_frame_invention(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_render_spec(tmp_path, db_path)
    result = run_timeline_compiler(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["pass"] is True
    assert result["timeline"]["video"]["fps"] is None
    assert result["timeline"]["video"]["frame_count"] is None
    assert "video.fps/frame_count" in result["validation"]["unresolved_non_critical"]


# CASE W: no renderer-specific vocabulary leaks into the timeline
def test_case_w_renderer_neutral(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_render_spec(tmp_path, db_path)
    result = run_timeline_compiler(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["integrity_checks"]["timeline_renderer_neutral"] is True

    dirty_timeline = json.loads(json.dumps(result["timeline"]))
    dirty_timeline["scenes"][0]["renderer_hint"] = "Wrap this in a Remotion Sequence"
    dirty_validation = validate_timeline({"scenes": [{"scene_id": "CB01"}, {"scene_id": "CB02"}]}, result["timeline"])
    from research.render_spec import _RENDERER_SPECIFIC_MARKER_RE
    assert _RENDERER_SPECIFIC_MARKER_RE.search(json.dumps(dirty_timeline).lower()) is not None


# CASE X: 05~13-1 upstream data unchanged by compiling a timeline
def test_case_x_upstream_data_unchanged(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_render_spec(tmp_path, db_path)
    with connect(db_path) as conn:
        before_plan = dict(conn.execute("SELECT * FROM production_plans WHERE id = ?", (plan_id,)).fetchone())
        before_blocks = [dict(r) for r in conn.execute(
            "SELECT * FROM production_blocks WHERE production_plan_id = ? ORDER BY block_order", (plan_id,)
        ).fetchall()]
        before_assets = [dict(r) for r in conn.execute(
            "SELECT * FROM speech_assets WHERE production_plan_id = ? ORDER BY speech_asset_id", (plan_id,)
        ).fetchall()]
        before_specs = [dict(r) for r in conn.execute("SELECT * FROM render_specs WHERE production_plan_id = ?", (plan_id,)).fetchall()]
    run_timeline_compiler(db_path, assets_dir, reports_dir, plan_id=plan_id)
    with connect(db_path) as conn:
        after_plan = dict(conn.execute("SELECT * FROM production_plans WHERE id = ?", (plan_id,)).fetchone())
        after_blocks = [dict(r) for r in conn.execute(
            "SELECT * FROM production_blocks WHERE production_plan_id = ? ORDER BY block_order", (plan_id,)
        ).fetchall()]
        after_assets = [dict(r) for r in conn.execute(
            "SELECT * FROM speech_assets WHERE production_plan_id = ? ORDER BY speech_asset_id", (plan_id,)
        ).fetchall()]
        after_specs = [dict(r) for r in conn.execute("SELECT * FROM render_specs WHERE production_plan_id = ?", (plan_id,)).fetchall()]
    assert before_plan == after_plan
    assert before_blocks == after_blocks
    assert before_assets == after_assets
    assert before_specs == after_specs


# entry gate mismatch between DB row and JSON file is a hard FAIL, never a guess
def test_entry_gate_db_file_mismatch_hard_fails(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_render_spec(tmp_path, db_path)
    json_path = assets_dir / "generated" / f"plan_{plan_id}" / "render" / "render_spec.json"
    on_disk = json.loads(json_path.read_text(encoding="utf-8"))
    on_disk["scenes"][0]["scene_id"] = "TAMPERED"
    json_path.write_text(json.dumps(on_disk), encoding="utf-8")
    entry_gate = validate_timeline_entry_gate(db_path, assets_dir, plan_id=plan_id)
    assert entry_gate["pass"] is False
    assert "differ" in entry_gate["reason"]


# Ready for Scene/Layout is granted end-to-end on the real fixture, and DB/file persistence happens
def test_ready_for_scene_layout_end_to_end(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_render_spec(tmp_path, db_path)
    result = run_timeline_compiler(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["pass"] is True
    assert result["ready_for_scene_layout"] is True
    assert all(v is True for v in result["integrity_checks"].values())
    assert result["json_path"].exists()
    assert result["report_path"].exists()
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM render_timelines WHERE production_plan_id = ?", (plan_id,)).fetchone()
    assert row is not None
    assert row["timeline_version"] == TIMELINE_VERSION
