import json

import pytest

from research.db import connect, init_db
from research.render_spec import run_render_spec
from research.scene_layout import (
    LAYOUT_VERSION,
    build_layout_constraints,
    build_scene_layout,
    classify_layout_type,
    compile_scene_layout,
    run_scene_layout,
    run_scene_layout_integrity_check,
    validate_layout_entry_gate,
    validate_scene_layout,
)
from research.timeline_compiler import run_timeline_compiler
from tests.test_timeline_compiler import _make_ready_plan_with_render_spec


def _make_ready_plan_with_timeline(tmp_path, db_path):
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_render_spec(tmp_path, db_path)
    timeline_result = run_timeline_compiler(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert timeline_result["pass"] is True
    return plan_id, assets_dir, reports_dir


# CASE A: normal 13.2 Timeline -> Layout generation succeeds
def test_case_a_normal_timeline_generates_layout(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_timeline(tmp_path, db_path)
    result = run_scene_layout(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["pass"] is True
    assert result["layout"]["layout_version"] == LAYOUT_VERSION
    assert len(result["layout"]["scenes"]) == 2


# CASE B: ready_for_scene_layout=NO -> blocked
def test_case_b_not_ready_for_scene_layout_blocks(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_render_spec(tmp_path, db_path)
    # no render-timeline run yet -- no render_timelines row exists
    entry_gate = validate_layout_entry_gate(db_path, assets_dir, plan_id=plan_id)
    assert entry_gate["pass"] is False
    assert entry_gate["reason"]


# CASE C: wrong timeline_version -> blocked
def test_case_c_wrong_timeline_version_blocks(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_timeline(tmp_path, db_path)
    with connect(db_path) as conn:
        row = conn.execute("SELECT id, timeline_json FROM render_timelines WHERE production_plan_id = ? ORDER BY id DESC LIMIT 1", (plan_id,)).fetchone()
        timeline = json.loads(row["timeline_json"])
        timeline["timeline_version"] = "99.9"
        conn.execute("UPDATE render_timelines SET timeline_json = ? WHERE id = ?", (json.dumps(timeline), row["id"]))
    json_path = assets_dir / "generated" / f"plan_{plan_id}" / "render" / "timeline.json"
    json_path.write_text(json.dumps(timeline), encoding="utf-8")
    entry_gate = validate_layout_entry_gate(db_path, assets_dir, plan_id=plan_id)
    assert entry_gate["pass"] is False
    assert "timeline_version" in entry_gate["reason"]


# CASE D: scene count preserved
def test_case_d_scene_count_preserved(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_timeline(tmp_path, db_path)
    result = run_scene_layout(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert len(result["layout"]["scenes"]) == 2
    assert result["validation"]["checks"]["scene_count_preserved"] is True


# CASE E: scene timing fully preserved verbatim from the Timeline
def test_case_e_scene_timing_fully_preserved(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_timeline(tmp_path, db_path)
    entry_gate = validate_layout_entry_gate(db_path, assets_dir, plan_id=plan_id)
    timeline_by_id = {s["scene_id"]: s for s in entry_gate["timeline"]["scenes"]}
    result = run_scene_layout(db_path, assets_dir, reports_dir, plan_id=plan_id)
    for s in result["layout"]["scenes"]:
        t = timeline_by_id[s["scene_id"]]
        assert s["start_ms"] == t["start_ms"]
        assert s["end_ms"] == t["end_ms"]
        assert s["duration_ms"] == t["duration_ms"]


# CASE F: Layout Type classification is deterministic given scene_role
def test_case_f_layout_type_classification_deterministic():
    assert classify_layout_type("MINI_SUCCESS") == "MINI_SUCCESS_LAYOUT"
    assert classify_layout_type("BLENDING") == "BLENDING_LAYOUT"
    assert classify_layout_type("RECAP") == "RECAP_LAYOUT"
    assert classify_layout_type("UNRESOLVED") == "UNRESOLVED_LAYOUT"
    assert classify_layout_type("totally_unknown") == "UNRESOLVED_LAYOUT"


# CASE G: required text elements bind to exactly one Zone
def test_case_g_required_elements_bind_to_zone(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_timeline(tmp_path, db_path)
    result = run_scene_layout(db_path, assets_dir, reports_dir, plan_id=plan_id)
    for s in result["layout"]["scenes"]:
        source_ids = [b["source_element_id"] for b in s["element_bindings"]]
        assert len(source_ids) == len(set(source_ids))
        for b in s["element_bindings"]:
            assert b["zone_id"]


# CASE H: TARGET_WORD -> PRIMARY_FOCUS zone
def test_case_h_target_word_binds_to_primary_focus(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_timeline(tmp_path, db_path)
    result = run_scene_layout(db_path, assets_dir, reports_dir, plan_id=plan_id)
    cb01 = next(s for s in result["layout"]["scenes"] if s["scene_id"] == "CB01")
    target_word_bindings = [b for b in cb01["element_bindings"] if b["element_role"] == "TARGET_WORD"]
    assert target_word_bindings
    assert all(b["zone_id"] == "primary_focus" for b in target_word_bindings)


# CASE L/M/N: Mini Success prompt/answer separation, ANSWER hidden before pause, barrier timing
# taken verbatim from Timeline
def test_case_l_m_n_mini_success_structure(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_timeline(tmp_path, db_path)
    entry_gate = validate_layout_entry_gate(db_path, assets_dir, plan_id=plan_id)
    timeline_cb02 = next(s for s in entry_gate["timeline"]["scenes"] if s["scene_id"] == "CB02")
    barrier = next(e for e in timeline_cb02["events"] if e["event_type"] == "ANSWER_REVEAL_BARRIER")

    result = run_scene_layout(db_path, assets_dir, reports_dir, plan_id=plan_id)
    cb02 = next(s for s in result["layout"]["scenes"] if s["scene_id"] == "CB02")
    assert cb02["layout_type"] == "MINI_SUCCESS_LAYOUT"
    zone_ids = {z["zone_id"] for z in cb02["zones"]}
    assert "answer" in zone_ids
    assert "prompt" in zone_ids or "primary_focus" in zone_ids  # question-derived zone present

    answer_rules = [r for r in cb02["visibility_rules"] if r["visibility"]["policy"] == "AFTER_BARRIER"]
    assert len(answer_rules) == 1
    assert answer_rules[0]["visibility"]["not_before_ms"] == barrier["reveal_not_before_ms"]

    answer_constraints = [c for c in cb02["layout_constraints"] if c["constraint_type"] == "ANSWER_HIDDEN_BEFORE_BARRIER"]
    assert len(answer_constraints) == 1
    assert answer_constraints[0]["not_before_ms"] == barrier["reveal_not_before_ms"]


# CASE O: viewer_action preserved via PROMPT_VISIBLE_DURING_ATTEMPT constraint
def test_case_o_viewer_action_preserved(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_timeline(tmp_path, db_path)
    result = run_scene_layout(db_path, assets_dir, reports_dir, plan_id=plan_id)
    cb02 = next(s for s in result["layout"]["scenes"] if s["scene_id"] == "CB02")
    assert any(c["constraint_type"] == "PROMPT_VISIBLE_DURING_ATTEMPT" for c in cb02["layout_constraints"])
    assert result["validation"]["checks"]["viewer_action_preserved"] is True


# CASE P: 3000ms PAUSE preserved (indirectly, through Timeline lineage the layout was built from)
def test_case_p_pause_duration_preserved(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_timeline(tmp_path, db_path)
    result = run_scene_layout(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["validation"]["checks"]["pause_duration_preserved"] is True


# CASE Q/R: CAP active fallback kept, failed SP003 (bare DIRECT_WORD) unused
def test_case_q_r_cap_fallback_kept_failed_variant_unused(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_timeline(tmp_path, db_path)
    entry_gate = validate_layout_entry_gate(db_path, assets_dir, plan_id=plan_id)
    cb02_spec = next(s for s in entry_gate["spec"]["scenes"] if s["scene_id"] == "CB02")
    cap_audio = [a for a in cb02_spec["audio_elements"] if a["source_speech_asset_id"] == "SP003"]
    assert len(cap_audio) == 1
    assert cap_audio[0]["asset_id"] == "SP003::CONTEXTUAL_WORD"
    result = run_scene_layout(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["validation"]["checks"]["no_failed_or_rejected_asset_reintroduced"] is True


# CASE S: experimental variants never used
def test_case_s_experimental_variants_unused(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_timeline(tmp_path, db_path)
    result = run_scene_layout(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["validation"]["checks"]["no_experimental_variant_reintroduced"] is True


# CASE T: real-data-discovered edge case -- a RECAP-like scene whose render_spec-level
# answer_reveal_policy is set (because is_mini_success_answer_asset is asset-scoped, not
# block-scoped -- see plan section "중요 발견") must NOT get an ANSWER_HIDDEN_BEFORE_BARRIER
# constraint when the Timeline has no real ANSWER_REVEAL_BARRIER event for that scene.
def test_case_t_recap_like_scene_without_real_barrier_gets_no_constraint():
    fake_spec_scene = {
        "scene_id": "CBX", "content_block_id": "CBX", "scene_role": "RECAP", "visual_intent": "RECAP",
        "viewer_action": None,
        # render_spec-level answer_reveal_policy incorrectly set (mirrors the real CB07 quirk) --
        # but no text_element actually has reveal_policy == AFTER_PAUSE, matching real CB07 data.
        "answer_reveal_policy": {"reveal_after_pause": True, "reveal_before_pause_allowed": False},
        "text_elements": [
            {"element_id": "CBX-TXT1", "role": "TARGET_WORD", "text": "BAG", "source": "SP003", "emphasis": False, "reveal_policy": "IMMEDIATE", "event_order": 1},
        ],
        "audio_elements": [], "pause_requirements": [], "emphasis_targets": [],
    }
    fake_timeline_scene = {
        "scene_id": "CBX", "start_ms": 0, "end_ms": 1000, "duration_ms": 1000,
        "events": [{"event_id": "CBX-EV1", "event_type": "AUDIO", "start_ms": 0, "end_ms": 1000}],
    }
    layout = compile_scene_layout(fake_spec_scene, fake_timeline_scene)
    assert not any(c["constraint_type"] == "ANSWER_HIDDEN_BEFORE_BARRIER" for c in layout["layout_constraints"])
    assert all(r["visibility"]["policy"] == "SCENE_DEFAULT" for r in layout["visibility_rules"])


# CASE T (continued, real data): a real RECAP scene with legitimate cross-scene element/audio
# reuse is not misclassified as an error
def test_case_t_real_recap_scene_reuse_not_flagged(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_timeline(tmp_path, db_path)
    result = run_scene_layout(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["pass"] is True
    assert all(v is True for v in result["integrity_checks"].values())


# CASE U: renderer-specific leakage blocked
def test_case_u_renderer_specific_leakage_blocked(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_timeline(tmp_path, db_path)
    entry_gate = validate_layout_entry_gate(db_path, assets_dir, plan_id=plan_id)
    layout = build_scene_layout(entry_gate["spec"], entry_gate["timeline"])
    clean_validation = validate_scene_layout(db_path, plan_id, entry_gate["spec"], entry_gate["timeline"], layout)
    assert clean_validation["checks"]["renderer_neutral"] is True

    dirty_layout = json.loads(json.dumps(layout))
    dirty_layout["scenes"][0]["renderer_hint"] = "Wrap this in a div with flexbox"
    dirty_validation = validate_scene_layout(db_path, plan_id, entry_gate["spec"], entry_gate["timeline"], dirty_layout)
    assert dirty_validation["checks"]["renderer_neutral"] is False


# CASE V: normal semantic vocabulary (BLEND_SEQUENCE) does not false-positive
def test_case_v_blend_sequence_vocabulary_not_false_positive(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_timeline(tmp_path, db_path)
    result = run_scene_layout(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["validation"]["checks"]["renderer_neutral"] is True
    assert result["integrity_checks"]["scene_layout_renderer_neutral"] is True


# CASE W: pixel coordinates never invented
def test_case_w_no_pixel_coordinates_invented(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_timeline(tmp_path, db_path)
    result = run_scene_layout(db_path, assets_dir, reports_dir, plan_id=plan_id)
    for s in result["layout"]["scenes"]:
        for zone in s["zones"]:
            assert "x" not in zone and "y" not in zone and "width" not in zone and "height" not in zone
    assert result["validation"]["checks"]["no_pixel_or_resolution_invented"] is True


# CASE X: fps/resolution never invented
def test_case_x_fps_resolution_never_invented(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_timeline(tmp_path, db_path)
    result = run_scene_layout(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert "width" not in result["layout"]
    assert "video.width/height/fps/orientation" in result["validation"]["unresolved_non_critical"]
    assert "max_simultaneous_elements" in result["validation"]["unresolved_non_critical"]


# CASE Y: same input -> same output (determinism)
def test_case_y_determinism(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_timeline(tmp_path, db_path)
    entry_gate = validate_layout_entry_gate(db_path, assets_dir, plan_id=plan_id)
    l1 = build_scene_layout(entry_gate["spec"], entry_gate["timeline"])
    l2 = build_scene_layout(entry_gate["spec"], entry_gate["timeline"])
    assert json.dumps(l1, sort_keys=True) == json.dumps(l2, sort_keys=True)
    result = run_scene_layout(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["integrity_checks"]["scene_layout_deterministic"] is True


# CASE Z: unresolved critical -> Ready for Visual Design NO
def test_case_z_unresolved_critical_blocks_ready(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_timeline(tmp_path, db_path)
    entry_gate = validate_layout_entry_gate(db_path, assets_dir, plan_id=plan_id)
    layout = build_scene_layout(entry_gate["spec"], entry_gate["timeline"])
    # force a real validation failure: corrupt scene timing so it no longer matches the Timeline
    layout["scenes"][0]["start_ms"] = 999999
    validation = validate_scene_layout(db_path, plan_id, entry_gate["spec"], entry_gate["timeline"], layout)
    integrity_checks = run_scene_layout_integrity_check(entry_gate, entry_gate["spec"], entry_gate["timeline"], layout, validation)
    from research.scene_layout import ready_for_visual_design_gate
    ready = ready_for_visual_design_gate(entry_gate, validation, integrity_checks)
    assert validation["unresolved_critical"]
    assert ready is False


# CASE AA: non-critical resolution unresolved -> Ready for Visual Design still possible
def test_case_aa_non_critical_resolution_unresolved_allows_ready(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_timeline(tmp_path, db_path)
    result = run_scene_layout(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert "video.width/height/fps/orientation" in result["validation"]["unresolved_non_critical"]
    assert result["ready_for_visual_design"] is True


# CASE AB: no regression in 13-1/13-2 -- Production Plan/production_blocks/speech_assets/
# generated_assets/render_specs/render_timelines rows unchanged by building a scene layout
def test_case_ab_no_regression_upstream_unchanged(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_timeline(tmp_path, db_path)
    with connect(db_path) as conn:
        before_plan = dict(conn.execute("SELECT * FROM production_plans WHERE id = ?", (plan_id,)).fetchone())
        before = {
            t: [dict(r) for r in conn.execute(f"SELECT * FROM {t} WHERE production_plan_id = ? ORDER BY id", (plan_id,)).fetchall()]
            for t in ["production_blocks", "speech_assets", "generated_assets", "render_specs", "render_timelines"]
        }
    run_scene_layout(db_path, assets_dir, reports_dir, plan_id=plan_id)
    with connect(db_path) as conn:
        after_plan = dict(conn.execute("SELECT * FROM production_plans WHERE id = ?", (plan_id,)).fetchone())
        after = {
            t: [dict(r) for r in conn.execute(f"SELECT * FROM {t} WHERE production_plan_id = ? ORDER BY id", (plan_id,)).fetchall()]
            for t in ["production_blocks", "speech_assets", "generated_assets", "render_specs", "render_timelines"]
        }
    assert before_plan == after_plan
    assert before == after


# Ready for Visual Design end-to-end + DB/file persistence
def test_ready_for_visual_design_end_to_end(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_timeline(tmp_path, db_path)
    result = run_scene_layout(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["pass"] is True
    assert result["ready_for_visual_design"] is True
    assert all(v is True for v in result["integrity_checks"].values())
    assert result["json_path"].exists()
    assert result["report_path"].exists()
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM scene_layouts WHERE production_plan_id = ?", (plan_id,)).fetchone()
    assert row is not None
    assert row["layout_version"] == LAYOUT_VERSION


# Entry gate: DB/file mismatch on render_timelines is a hard FAIL
def test_entry_gate_timeline_db_file_mismatch_hard_fails(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_timeline(tmp_path, db_path)
    json_path = assets_dir / "generated" / f"plan_{plan_id}" / "render" / "timeline.json"
    on_disk = json.loads(json_path.read_text(encoding="utf-8"))
    on_disk["scenes"][0]["scene_id"] = "TAMPERED"
    json_path.write_text(json.dumps(on_disk), encoding="utf-8")
    entry_gate = validate_layout_entry_gate(db_path, assets_dir, plan_id=plan_id)
    assert entry_gate["pass"] is False
    assert "differ" in entry_gate["reason"]
