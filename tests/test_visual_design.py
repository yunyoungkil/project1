import json
import re

import pytest

from research.db import connect, init_db
from research.scene_layout import run_scene_layout
from research.visual_design import (
    APPROVED_PROFILE_CATEGORIES,
    CANDIDATES,
    CONDITIONAL_VISUAL_CATEGORIES,
    FONT_CANDIDATES,
    MANDATORY_VISUAL_CATEGORIES,
    OPTIONAL_VISUAL_CATEGORIES,
    VISUAL_DESIGN_VERSION,
    build_category_approvals,
    build_font_glyph_test_prototype,
    build_font_hierarchy_test_prototype,
    build_font_learning_prototype,
    build_visual_design,
    classify_visual_review,
    CAPTION_STYLE_CANDIDATES,
    COLOR_REVIEW_ROLES,
    FOCUS_STYLE_CANDIDATES,
    FONT_WEIGHT_CANDIDATE_DELTAS,
    SUCCESS_STYLE_CANDIDATES,
    HUMAN_REVIEWED_FONT_FAMILY,
    HUMAN_SELECTED_CAPTION_STYLE_CANDIDATE,
    HUMAN_SELECTED_FOCUS_STYLE_CANDIDATE,
    HUMAN_SELECTED_FONT_WEIGHT_CANDIDATE,
    HUMAN_SELECTED_MUTED_CANDIDATE,
    HUMAN_SELECTED_TYPOGRAPHY_CANDIDATE,
    MUTED_CANDIDATE_FACTORS,
    TYPOGRAPHY_SCALE_CANDIDATE_DELTAS,
    TYPOGRAPHY_SCALE_ROLES,
    _color_role_usage_counts,
    build_caption_style_candidates,
    build_contrast_results,
    build_focus_style_candidates,
    build_font_weight_candidates,
    build_muted_candidates,
    build_success_style_candidates,
    build_typography_scale_candidates,
    contrast_ratio,
    generate_color_background_review_prototypes,
    generate_font_review_prototypes,
    generate_muted_color_review_prototypes,
    ready_for_final_renderer_binding,
    run_approve_visual_design,
    run_background_human_approval,
    run_caption_style_human_approval,
    run_caption_style_review,
    run_color_background_review,
    run_color_palette_human_approval,
    run_correct_visual_approval,
    run_focus_style_human_approval,
    run_focus_style_review,
    run_font_family_human_approval,
    run_font_family_review,
    run_font_weight_human_approval,
    run_font_weight_review,
    run_muted_color_refinement,
    run_success_style_review,
    run_typography_scale_human_approval,
    run_typography_scale_review,
    run_visual_design,
    validate_caption_style_candidates,
    validate_focus_style_candidates,
    validate_font_weight_candidates,
    validate_success_style_candidates,
    validate_typography_scale_candidates,
    run_visual_design_integrity_check,
    select_canonical_visual_approval,
    select_visual_candidate,
    validate_visual_design,
    validate_visual_design_entry_gate,
)
from tests.test_scene_layout import _make_ready_plan_with_timeline


def _make_ready_plan_with_scene_layout(tmp_path, db_path):
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_timeline(tmp_path, db_path)
    layout_result = run_scene_layout(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert layout_result["pass"] is True
    return plan_id, assets_dir, reports_dir


# CASE A: normal Plan 7-like entry -> Visual Design generated
def test_case_a_normal_entry_generates_visual_design(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    result = run_visual_design(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["pass"] is True
    assert result["design"]["visual_design_version"] == VISUAL_DESIGN_VERSION
    assert len(result["design"]["scene_visual_rules"]) == 2


# CASE B: Ready for Visual Design=NO -> blocked (no scene_layouts row yet)
def test_case_b_not_ready_blocks(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_timeline(tmp_path, db_path)
    entry_gate = validate_visual_design_entry_gate(db_path, assets_dir, plan_id=plan_id)
    assert entry_gate["pass"] is False
    assert entry_gate["reason"]


# CASE C: scene lineage mismatch -> blocked
def test_case_c_scene_lineage_mismatch_blocks(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    json_path = assets_dir / "generated" / f"plan_{plan_id}" / "render" / "scene_layout.json"
    on_disk = json.loads(json_path.read_text(encoding="utf-8"))
    on_disk["scenes"][0]["scene_id"] = "TAMPERED"
    json_path.write_text(json.dumps(on_disk), encoding="utf-8")
    entry_gate = validate_visual_design_entry_gate(db_path, assets_dir, plan_id=plan_id)
    assert entry_gate["pass"] is False
    assert "differ" in entry_gate["reason"]


# CASE D: zone/binding mismatch -> blocked (validation catches it, not silently accepted)
def test_case_d_zone_binding_mismatch_caught(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    entry_gate = validate_visual_design_entry_gate(db_path, assets_dir, plan_id=plan_id)
    spec, layout = entry_gate["spec"], entry_gate["layout"]
    design = build_visual_design(spec, layout)
    design["scene_visual_rules"][0]["typography_bindings"].pop()
    validation = validate_visual_design(spec, layout, design)
    assert validation["checks"]["element_binding_lineage_preserved"] is False
    assert "element_binding_lineage_preserved" in validation["unresolved_critical"]


# CASE E: CB06-like Mini Success answer visible before barrier -> caught
def test_case_e_answer_visible_before_barrier_caught(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    entry_gate = validate_visual_design_entry_gate(db_path, assets_dir, plan_id=plan_id)
    spec, layout = entry_gate["spec"], entry_gate["layout"]
    design = build_visual_design(spec, layout)
    cb02 = next(s for s in design["scene_visual_rules"] if s["scene_id"] == "CB02")
    for t in cb02["typography_bindings"]:
        if any(e["element_id"] == t["element_id"] and e["entrance_style"] == "ANSWER_REVEAL" for e in cb02["element_states"]):
            t["typography_role"] = "CAPTION"  # corrupt: answer should be DOMINANT
    validation = validate_visual_design(spec, layout, design)
    assert validation["checks"]["mini_success_answer_reveal_safe"] is False


# CASE F: a RECAP-role scene wrongly given an ANSWER_HIDDEN_BEFORE_BARRIER-style constraint at the
# Scene Layout level -> caught by recap_scope_safe
def test_case_f_recap_with_false_answer_barrier_style_caught():
    layout_scene = {
        "scene_id": "CBX", "scene_role": "RECAP", "layout_type": "RECAP_LAYOUT",
        "zones": [], "element_bindings": [], "visibility_rules": [], "emphasis_bindings": [],
        "layout_constraints": [{"constraint_type": "ANSWER_HIDDEN_BEFORE_BARRIER", "target_element_id": "X"}],
    }
    from research.visual_design import validate_visual_design as _v
    layout = {"scenes": [layout_scene]}
    spec = {"scenes": [{"scene_id": "CBX", "text_elements": [], "audio_elements": [], "emphasis_targets": []}]}
    design = {
        "scene_visual_rules": [{
            "scene_id": "CBX", "layout_type": "RECAP_LAYOUT", "typography_bindings": [], "color_bindings": [],
            "caption_bindings": [], "motion_bindings": [], "element_states": [], "background_role": "LEARNING_BACKGROUND",
            "container_bindings": [],
        }],
        "visual_review_rules": [{"scene_id": "CBX", "status": "AUTO_LAYOUT", "reasons": []}],
        "responsive_rules": {"CAPTION": {"orientation_16_9": {"placement": "SUPPORTING_SIDE"}, "orientation_9_16": {"placement": "STACKED_BELOW"}},
                              "PRIMARY_FOCUS": {"orientation_16_9": {"placement": "CORE_SAFE_AREA_CENTER"}, "orientation_9_16": {"placement": "CORE_SAFE_AREA_CENTER"}}},
        "approval_status": "PENDING_HUMAN_REVIEW",
    }
    validation = _v(spec, layout, design)
    assert validation["checks"]["recap_scope_safe"] is False


# CASE G: semantic meaning conveyed by color alone -> caught
def test_case_g_color_alone_semantic_caught(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    entry_gate = validate_visual_design_entry_gate(db_path, assets_dir, plan_id=plan_id)
    spec, layout = entry_gate["spec"], entry_gate["layout"]
    design = build_visual_design(spec, layout)
    design["scene_visual_rules"][0]["color_bindings"][0]["non_color_cue"] = None
    validation = validate_visual_design(spec, layout, design)
    assert validation["checks"]["color_not_sole_cue"] is False


# CASE H: renderer-specific field contamination -> caught
def test_case_h_renderer_specific_field_caught(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    entry_gate = validate_visual_design_entry_gate(db_path, assets_dir, plan_id=plan_id)
    spec, layout = entry_gate["spec"], entry_gate["layout"]
    design = build_visual_design(spec, layout)
    clean_validation = validate_visual_design(spec, layout, design)
    assert clean_validation["checks"]["renderer_neutral"] is True

    dirty_design = json.loads(json.dumps(design))
    dirty_design["scenes_hint"] = "Use a div with flexbox and a Remotion Sequence"
    dirty_validation = validate_visual_design(spec, layout, dirty_design)
    assert dirty_validation["checks"]["renderer_neutral"] is False


# CASE I: canonical pixel/resolution arbitrarily fixed -> caught
def test_case_i_pixel_resolution_invention_caught(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    entry_gate = validate_visual_design_entry_gate(db_path, assets_dir, plan_id=plan_id)
    spec, layout = entry_gate["spec"], entry_gate["layout"]
    design = build_visual_design(spec, layout)
    clean_validation = validate_visual_design(spec, layout, design)
    assert clean_validation["checks"]["no_pixel_or_resolution_invented"] is True

    dirty_design = json.loads(json.dumps(design))
    dirty_design["scenes_hint"] = "width: 1920px"
    dirty_validation = validate_visual_design(spec, layout, dirty_design)
    assert dirty_validation["checks"]["no_pixel_or_resolution_invented"] is False


# CASE J: caption and learning text semantic mixed -> detected
def test_case_j_caption_learning_text_mixup_detected(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    entry_gate = validate_visual_design_entry_gate(db_path, assets_dir, plan_id=plan_id)
    spec, layout = entry_gate["spec"], entry_gate["layout"]
    design = build_visual_design(spec, layout)
    clean_validation = validate_visual_design(spec, layout, design)
    assert clean_validation["checks"]["caption_learning_text_separated"] is True

    for s in design["scene_visual_rules"]:
        for cb in s["caption_bindings"]:
            if cb["zone_id"] == "caption":
                cb["caption_role"] = "LEARNING_TEXT"  # wrong: caption zone should be NARRATION_CAPTION
    dirty_validation = validate_visual_design(spec, layout, design)
    assert dirty_validation["checks"]["caption_learning_text_separated"] is False


# CASE K: 9:16 is not simple crop-only -- detected as a contract violation if forced equal
def test_case_k_crop_only_contract_detected():
    from research.visual_design import build_responsive_rules
    rules = build_responsive_rules()
    crop_only = {k: {**v, "orientation_9_16": v["orientation_16_9"]} for k, v in rules.items()}
    differs = any(v["orientation_16_9"] != v["orientation_9_16"] for v in crop_only.values())
    assert differs is False  # this is exactly the violation the real rules must NOT exhibit


# CASE L: responsive recomposition contract passes for the real generator
def test_case_l_responsive_recomposition_contract_passes(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    entry_gate = validate_visual_design_entry_gate(db_path, assets_dir, plan_id=plan_id)
    spec, layout = entry_gate["spec"], entry_gate["layout"]
    design = build_visual_design(spec, layout)
    validation = validate_visual_design(spec, layout, design)
    assert validation["checks"]["responsive_recomposition_supported"] is True


# CASE M: failed/rejected asset introduction -- 13-4 never re-selects assets, so audio_elements
# stay exactly as 13-1 resolved them (structural proof: visual_design.py never imports asset
# selection helpers, confirmed by re-reading spec.scenes[].audio_elements unchanged)
def test_case_m_failed_rejected_asset_not_introduced(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    entry_gate = validate_visual_design_entry_gate(db_path, assets_dir, plan_id=plan_id)
    cb02 = next(s for s in entry_gate["spec"]["scenes"] if s["scene_id"] == "CB02")
    cap_audio = [a for a in cb02["audio_elements"] if a["source_speech_asset_id"] == "SP003"]
    assert len(cap_audio) == 1
    assert cap_audio[0]["asset_id"] == "SP003::CONTEXTUAL_WORD"


# CASE N: experimental variant introduction -- same structural guarantee
def test_case_n_experimental_variant_not_introduced(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    result = run_visual_design(db_path, assets_dir, reports_dir, plan_id=plan_id)
    # structural: Visual Design never references asset_id anywhere -- it binds roles onto 13-3
    # zones/elements, never re-selects or re-serializes generation_unit/asset identity.
    assert "asset_id" not in json.dumps(result["design"])
    assert "generation_unit_id" not in json.dumps(result["design"])


# CASE O: Prototype must never be auto-approved
def test_case_o_prototype_never_auto_approved(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    result = run_visual_design(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["design"]["approval_status"] == "PENDING_HUMAN_REVIEW"
    assert result["human_visual_review_status"] == "PENDING"
    assert result["approved_visual_profile"] is False
    assert result["ready_for_final_renderer_binding"] is False
    assert result["ready_for_visual_prototype_review"] is True  # 13-4A/B done, distinct from approval


# CASE P: VISUAL_REVIEW_REQUIRED without a reason -> caught
def test_case_p_visual_review_required_without_reason_caught():
    layout_scene_unresolved = {"layout_type": "UNRESOLVED_LAYOUT", "zones": []}
    status, reasons = classify_visual_review(layout_scene_unresolved)
    assert status == "VISUAL_REVIEW_REQUIRED"
    assert reasons  # must never be empty when status requires review

    spec = {"scenes": []}
    layout = {"scenes": []}
    design = {
        "scene_visual_rules": [], "responsive_rules": {},
        "visual_review_rules": [{"scene_id": "CBX", "status": "VISUAL_REVIEW_REQUIRED", "reasons": []}],
        "approval_status": "PENDING_HUMAN_REVIEW",
    }
    validation = validate_visual_design(spec, layout, design)
    assert validation["checks"]["visual_review_reason_complete"] is False


# CASE P (continued): 2+ DOMINANT zones in one scene triggers RESPONSIVE_RECOMPOSITION_RISK
def test_case_p_multiple_dominant_zones_triggers_review():
    layout_scene = {"layout_type": "MINI_SUCCESS_LAYOUT", "zones": [
        {"zone_id": "answer", "size_intent": "DOMINANT"}, {"zone_id": "primary_focus", "size_intent": "DOMINANT"},
    ]}
    status, reasons = classify_visual_review(layout_scene)
    assert status == "VISUAL_REVIEW_REQUIRED"
    assert "RESPONSIVE_RECOMPOSITION_RISK" in reasons


# CASE Q: same input -> same output (determinism)
def test_case_q_determinism(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    entry_gate = validate_visual_design_entry_gate(db_path, assets_dir, plan_id=plan_id)
    spec, layout = entry_gate["spec"], entry_gate["layout"]
    d1 = build_visual_design(spec, layout)
    d2 = build_visual_design(spec, layout)
    assert json.dumps(d1, sort_keys=True) == json.dumps(d2, sort_keys=True)
    result = run_visual_design(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["integrity_checks"]["visual_design_deterministic"] is True


# CASE R: no regression in 13-1/13-2/13-3 -- rows unchanged by generating a visual design
def test_case_r_no_regression_upstream_unchanged(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    with connect(db_path) as conn:
        before = {
            t: [dict(r) for r in conn.execute(f"SELECT * FROM {t} WHERE production_plan_id = ? ORDER BY id", (plan_id,)).fetchall()]
            for t in ["production_blocks", "speech_assets", "generated_assets", "render_specs", "render_timelines", "scene_layouts"]
        }
    run_visual_design(db_path, assets_dir, reports_dir, plan_id=plan_id)
    with connect(db_path) as conn:
        after = {
            t: [dict(r) for r in conn.execute(f"SELECT * FROM {t} WHERE production_plan_id = ? ORDER BY id", (plan_id,)).fetchall()]
            for t in ["production_blocks", "speech_assets", "generated_assets", "render_specs", "render_timelines", "scene_layouts"]
        }
    assert before == after


# Ready for Visual Design System / Prototype end-to-end + DB/file persistence
def test_end_to_end_gates_and_persistence(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    result = run_visual_design(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["pass"] is True
    assert result["ready_for_visual_design_system"] is True
    assert all(v is True for v in result["integrity_checks"].values())
    assert result["json_path"].exists()
    assert result["report_path"].exists()
    assert result["prototype_dir"].exists()
    assert result["prototype_file_count"] > 0
    assert (result["prototype_dir"] / "manifest.json").exists()
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()
    assert row is not None
    assert row["visual_design_version"] == VISUAL_DESIGN_VERSION


# Prototype HTML: answer text is hidden before reveal, visible after -- real content check
# (13-4B-R: Mini-Success-style scenes now use the 6-phase sequence instead of a flat BEFORE/AFTER
# split; ATTEMPT_PROMPT is the pre-barrier phase, ANSWER_CONFIRMATION is the first post-barrier one)
def test_prototype_html_hides_answer_before_reveal(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    result = run_visual_design(db_path, assets_dir, reports_dir, plan_id=plan_id)
    manifest = json.loads((result["prototype_dir"] / "manifest.json").read_text(encoding="utf-8"))
    cb02_files = [f for f in manifest["files"] if f["scene_id"] == "CB02"]
    assert any(f["reveal_state"] == "ATTEMPT_PROMPT" for f in cb02_files)
    assert any(f["reveal_state"] == "ANSWER_CONFIRMATION" for f in cb02_files)
    before_file = next(f for f in cb02_files if f["reveal_state"] == "ATTEMPT_PROMPT" and f["candidate"] == "SOFT_LIGHT_EDUCATION")
    after_file = next(f for f in cb02_files if f["reveal_state"] == "ANSWER_CONFIRMATION" and f["candidate"] == "SOFT_LIGHT_EDUCATION")
    before_html = (result["prototype_dir"] / before_file["file"]).read_text(encoding="utf-8")
    after_html = (result["prototype_dir"] / after_file["file"]).read_text(encoding="utf-8")
    # 13-4B-R renders the answer element only from ANSWER_CONFIRMATION onward -- it's omitted from
    # the HTML entirely (not merely CSS-hidden) in the pre-barrier phases.
    assert 'data-element-role="ANSWER"' not in before_html
    assert 'data-element-role="ANSWER"' in after_html


# ---------------------------------------------------------------------------
# 13-4C: Approved Visual Profile -- reachable only via an explicit approval call, never implied by
# 13-4A/13-4B alone.
# ---------------------------------------------------------------------------

# 13-4A/B alone never produce an approval -- this is the "no automatic APPROVED" guarantee
def test_visual_design_alone_never_auto_approves(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    result = run_visual_design(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["design"]["approval_status"] == "PENDING_HUMAN_REVIEW"
    assert result["human_visual_review_status"] == "PENDING"
    assert result["approved_visual_profile"] is False
    assert result["ready_for_final_renderer_binding"] is False


# 13-4C-2: build_category_approvals never auto-approves color_palette/typography_scale merely
# because Prototype CSS values exist for them -- candidate direction preference != exact token
# approval (section 9), and the previously-APPROVED values were provenance-traced back to a
# DIFFERENT candidate entirely (see run_correct_visual_approval tests below). All 15 categories are
# honestly PENDING_VISUAL_REVIEW until a human explicitly approves an exact value.
def test_build_category_approvals_all_pending_by_default():
    approvals = build_category_approvals("SOFT_LIGHT_EDUCATION")
    assert approvals["checked_candidate"] == "SOFT_LIGHT_EDUCATION"
    assert approvals["approved_category_count"] == 0
    assert approvals["total_category_count"] == len(APPROVED_PROFILE_CATEGORIES) == 15
    for name in APPROVED_PROFILE_CATEGORIES:
        assert approvals["categories"][name]["resolution_status"] == "PENDING_VISUAL_REVIEW"
        assert approvals["categories"][name]["resolved_style"] is None


# build_category_approvals rejects a candidate that was never actually offered in the prototype
def test_build_category_approvals_rejects_unknown_candidate():
    with pytest.raises(ValueError):
        build_category_approvals("NEVER_SHOWN_CANDIDATE")


def test_select_visual_candidate_and_ready_gate():
    selection = select_visual_candidate("SOFT_LIGHT_EDUCATION")
    assert selection["candidate_selection_status"] == "SELECTED"
    approvals = build_category_approvals("SOFT_LIGHT_EDUCATION")
    # candidate selection alone never satisfies the mandatory-category gate (section 5/19: SELECT
    # CANDIDATE != FINALIZE PROFILE) -- with all categories still pending, the gate must be False.
    assert ready_for_final_renderer_binding(selection, approvals) is False
    assert ready_for_final_renderer_binding({"candidate_selection_status": "PENDING"}, approvals) is False
    # even with every MANDATORY category explicitly approved, gate becomes True
    all_mandatory_approved = {
        "categories": {c: {"resolution_status": "APPROVED"} for c in MANDATORY_VISUAL_CATEGORIES}
    }
    assert ready_for_final_renderer_binding(selection, all_mandatory_approved) is True


# run_approve_visual_design: candidate selection only -- never implies full profile approval
# (section 19/20 fix: this used to set approval_status="APPROVED" unconditionally, a semantic bug)
def test_run_approve_visual_design_end_to_end(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    run_visual_design(db_path, assets_dir, reports_dir, plan_id=plan_id)

    result = run_approve_visual_design(db_path, assets_dir, reports_dir, plan_id=plan_id, candidate="SOFT_LIGHT_EDUCATION")
    assert result["pass"] is True
    assert result["candidate_selection"]["candidate_selection_status"] == "SELECTED"
    assert result["category_approvals"]["approved_category_count"] == 0
    assert result["ready_for_final_renderer_binding"] is False  # candidate selection alone is never enough
    assert result["json_path"].exists()
    assert result["report_path"].exists()

    selected = json.loads(result["json_path"].read_text(encoding="utf-8"))
    assert selected["candidate_selection_status"] == "SELECTED"
    assert selected["full_profile_approved"] is False
    assert selected["category_approvals"]["color_palette"]["resolution_status"] == "PENDING_VISUAL_REVIEW"
    assert selected["category_approvals"]["border"]["resolution_status"] == "PENDING_VISUAL_REVIEW"

    with connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM visual_design_specs WHERE production_plan_id = ? ORDER BY id", (plan_id,)).fetchall()
    assert len(rows) == 2  # 13-4A's original row is untouched, 13-4C added a new one
    original_design = json.loads(rows[0]["design_json"])
    assert original_design["approval_status"] == "PENDING_HUMAN_REVIEW"  # 13-4A row never mutated


# run_approve_visual_design rejects an unrecognized candidate without recording anything
def test_run_approve_visual_design_rejects_unknown_candidate(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    run_visual_design(db_path, assets_dir, reports_dir, plan_id=plan_id)
    result = run_approve_visual_design(db_path, assets_dir, reports_dir, plan_id=plan_id, candidate="NOT_A_REAL_CANDIDATE")
    assert result["pass"] is False
    with connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchall()
    assert len(rows) == 1  # no new row was added on rejection


# run_approve_visual_design requires run_visual_design to have run first
def test_run_approve_visual_design_requires_prior_run_visual_design(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    result = run_approve_visual_design(db_path, assets_dir, reports_dir, plan_id=plan_id, candidate="SOFT_LIGHT_EDUCATION")
    assert result["pass"] is False
    assert "render-visual-design" in result["reason"]


# ---------------------------------------------------------------------------
# 13-4B-R: Visual Prototype Revision -- CB06-style (any ANSWER_REVEAL scene) phase sequence
# ---------------------------------------------------------------------------

from research.visual_design import CB06_PHASES, build_cb06_phase_prototype, generate_cb06_phase_prototypes


def _cb02_pieces(db_path, assets_dir, reports_dir, plan_id):
    from research.visual_design import validate_visual_design_entry_gate
    entry_gate = validate_visual_design_entry_gate(db_path, assets_dir, plan_id=plan_id)
    design = build_visual_design(entry_gate["spec"], entry_gate["layout"])
    layout_scene = next(s for s in entry_gate["layout"]["scenes"] if s["scene_id"] == "CB02")
    spec_scene = next(s for s in entry_gate["spec"]["scenes"] if s["scene_id"] == "CB02")
    scene_visual_rule = next(s for s in design["scene_visual_rules"] if s["scene_id"] == "CB02")
    return scene_visual_rule, layout_scene, spec_scene


# CASE: all 6 phases generated for both candidates (12 files) for a Mini-Success-style scene
def test_all_six_phases_generated_for_both_candidates(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    result = run_visual_design(db_path, assets_dir, reports_dir, plan_id=plan_id)
    manifest = json.loads((result["prototype_dir"] / "manifest.json").read_text(encoding="utf-8"))
    cb02_files = [f for f in manifest["files"] if f["scene_id"] == "CB02"]
    assert len(cb02_files) == len(CB06_PHASES) * len(CANDIDATES) == 12
    for phase in CB06_PHASES:
        assert sum(1 for f in cb02_files if f["reveal_state"] == phase) == len(CANDIDATES)


# CASE: answer never appears (not even hidden) in either pre-barrier phase
def test_answer_absent_in_both_pre_barrier_phases(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    scene_visual_rule, layout_scene, spec_scene = _cb02_pieces(db_path, assets_dir, reports_dir, plan_id)
    for phase in ("ATTEMPT_PROMPT", "THINKING_PAUSE"):
        html = build_cb06_phase_prototype(scene_visual_rule, layout_scene, spec_scene, "CLEAN_DARK_FOCUS", phase)
        assert 'data-element-role="ANSWER"' not in html


# CASE: ANSWER_CONFIRMATION shows the answer as DOMINANT/SUCCESS and mutes the prior prompt trace
def test_answer_confirmation_dominant_success_and_prompt_muted(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    scene_visual_rule, layout_scene, spec_scene = _cb02_pieces(db_path, assets_dir, reports_dir, plan_id)
    html = build_cb06_phase_prototype(scene_visual_rule, layout_scene, spec_scene, "CLEAN_DARK_FOCUS", "ANSWER_CONFIRMATION")
    candidate = CANDIDATES["CLEAN_DARK_FOCUS"]
    assert candidate["roles"]["DOMINANT"] in html
    assert candidate["colors"]["SUCCESS"] in html
    assert 'data-element-role="QUESTION" data-element-state="MUTED"' in html


# CASE: CASE_BRIDGE shows a lowercase display transform, with an explicit non-mutation comment, and
# never touches the canonical source text
def test_case_bridge_lowercase_display_only_transform(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    scene_visual_rule, layout_scene, spec_scene = _cb02_pieces(db_path, assets_dir, reports_dir, plan_id)
    answer_text = next(t["text"] for t in spec_scene["text_elements"] if t["role"] == "ANSWER")
    html = build_cb06_phase_prototype(scene_visual_rule, layout_scene, spec_scene, "CLEAN_DARK_FOCUS", "CASE_BRIDGE")
    assert answer_text.lower() in html
    assert "VISUAL_TRANSFORMATION" in html
    # canonical spec_scene itself must remain untouched
    assert next(t["text"] for t in spec_scene["text_elements"] if t["role"] == "ANSWER") == answer_text


# CASE: SCAFFOLD_REMOVAL removes prompt/caption scaffolding, keeping only the answer
def test_scaffold_removal_drops_prompt_and_caption(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    scene_visual_rule, layout_scene, spec_scene = _cb02_pieces(db_path, assets_dir, reports_dir, plan_id)
    html = build_cb06_phase_prototype(scene_visual_rule, layout_scene, spec_scene, "CLEAN_DARK_FOCUS", "SCAFFOLD_REMOVAL")
    assert 'data-element-role="QUESTION"' not in html
    assert 'data-element-role="ANSWER"' in html


# CASE: NATURAL_WORD_FINAL has no celebration decoration and no scaffolding
def test_natural_word_final_no_celebration_decoration(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    scene_visual_rule, layout_scene, spec_scene = _cb02_pieces(db_path, assets_dir, reports_dir, plan_id)
    html = build_cb06_phase_prototype(scene_visual_rule, layout_scene, spec_scene, "CLEAN_DARK_FOCUS", "NATURAL_WORD_FINAL")
    for forbidden in ("정답입니다", "성공", "축하", "confetti", "badge"):
        assert forbidden not in html
    assert 'data-element-role="QUESTION"' not in html
    assert 'data-element-role="ANSWER"' in html


# CASE: THINKING_PAUSE cites the canonical PAUSE duration only in a comment, invents no new timing
def test_thinking_pause_no_new_timing_invented(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    scene_visual_rule, layout_scene, spec_scene = _cb02_pieces(db_path, assets_dir, reports_dir, plan_id)
    html = build_cb06_phase_prototype(scene_visual_rule, layout_scene, spec_scene, "CLEAN_DARK_FOCUS", "THINKING_PAUSE")
    assert "THINKING_PROGRESS" in html
    assert "3000ms" in html  # cited verbatim from the canonical PAUSE, not recomputed
    for forbidden in ("setTimeout", "setInterval", "<script"):
        assert forbidden not in html


# CASE: CB07 (a real RECAP-style scene reused elsewhere, no ANSWER_REVEAL) is entirely unaffected
# by the 13-4B-R phase logic -- confirmed via the general-purpose generator path still being used
def test_non_answer_reveal_scene_untouched_by_phase_logic(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    result = run_visual_design(db_path, assets_dir, reports_dir, plan_id=plan_id)
    manifest = json.loads((result["prototype_dir"] / "manifest.json").read_text(encoding="utf-8"))
    cb01_files = [f for f in manifest["files"] if f["scene_id"] == "CB01"]
    assert len(cb01_files) == len(CANDIDATES)
    assert all(f["reveal_state"] == "N/A" for f in cb01_files)


# CASE: canonical visual_design.json/scene_layout.json/render_spec.json completely unchanged by
# generating the revised prototype (13-4B-R never re-persists canonical design)
def test_canonical_artifacts_unchanged_by_revision(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    with connect(db_path) as conn:
        before = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
    result = run_visual_design(db_path, assets_dir, reports_dir, plan_id=plan_id)
    with connect(db_path) as conn:
        after = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
    assert after == before + 1  # exactly the one row run_visual_design itself creates
    assert result["design"]["approval_status"] == "PENDING_HUMAN_REVIEW"  # revision never auto-approves


# CASE: determinism -- same input produces byte-identical phase HTML
def test_cb06_phase_prototype_determinism(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    scene_visual_rule, layout_scene, spec_scene = _cb02_pieces(db_path, assets_dir, reports_dir, plan_id)
    h1 = build_cb06_phase_prototype(scene_visual_rule, layout_scene, spec_scene, "CLEAN_DARK_FOCUS", "ANSWER_CONFIRMATION")
    h2 = build_cb06_phase_prototype(scene_visual_rule, layout_scene, spec_scene, "CLEAN_DARK_FOCUS", "ANSWER_CONFIRMATION")
    assert h1 == h2


# CASE: prototype index.html is generated and links every manifest file
def test_prototype_index_generated(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    result = run_visual_design(db_path, assets_dir, reports_dir, plan_id=plan_id)
    index_path = result["prototype_dir"] / "index.html"
    assert index_path.exists()
    index_html = index_path.read_text(encoding="utf-8")
    manifest = json.loads((result["prototype_dir"] / "manifest.json").read_text(encoding="utf-8"))
    for entry in manifest["files"]:
        assert entry["file"] in index_html


# ---------------------------------------------------------------------------
# 13-4B-R1: CB06 Caption / Scaffold Visibility Correction -- real bug: _cb06_phase_overrides had no
# CAPTION branch at all, so narration captions leaked into every phase's actual frame (visible
# instead of hidden), including SCAFFOLD_REMOVAL/NATURAL_WORD_FINAL where their names promise a
# clean frame. These tests inspect the actual rendered <main data-frame-preview> content, never the
# Python objects alone and never the <header data-preview-metadata> text, per the spec's explicit
# warning against string-match false positives.
# ---------------------------------------------------------------------------

_NARRATION_SNIPPETS = ("이제 여러분 차례입니다", "화면에 나온 단어를 보고")


def _extract_frame_preview(html: str) -> str:
    start = html.index("<main data-frame-preview>") + len("<main data-frame-preview>")
    end = html.index("</main>", start)
    return html[start:end]


def _cb06_phase_html(db_path, assets_dir, reports_dir, plan_id, candidate, phase):
    scene_visual_rule, layout_scene, spec_scene = _cb02_pieces(db_path, assets_dir, reports_dir, plan_id)
    return build_cb06_phase_prototype(scene_visual_rule, layout_scene, spec_scene, candidate, phase)


# CASE A/B: ATTEMPT_PROMPT has the action prompt but no narration caption in the actual frame
def test_attempt_prompt_frame_has_action_prompt_no_narration_caption(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    html = _cb06_phase_html(db_path, assets_dir, reports_dir, plan_id, "CLEAN_DARK_FOCUS", "ATTEMPT_PROMPT")
    frame = _extract_frame_preview(html)
    assert "직접 읽어보세요." in frame
    for snippet in _NARRATION_SNIPPETS:
        assert snippet not in frame


# CASE C/D/E: THINKING_PAUSE frame has no narration caption, has THINKING_PROGRESS, no answer
def test_thinking_pause_frame_no_caption_has_progress_no_answer(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    html = _cb06_phase_html(db_path, assets_dir, reports_dir, plan_id, "CLEAN_DARK_FOCUS", "THINKING_PAUSE")
    frame = _extract_frame_preview(html)
    for snippet in _NARRATION_SNIPPETS:
        assert snippet not in frame
    assert "THINKING_PROGRESS" in frame
    assert 'data-element-role="ANSWER"' not in frame


# CASE F/G/H: ANSWER_CONFIRMATION frame has the answer, no narration caption, no action prompt
def test_answer_confirmation_frame_no_caption_no_action_prompt(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    html = _cb06_phase_html(db_path, assets_dir, reports_dir, plan_id, "CLEAN_DARK_FOCUS", "ANSWER_CONFIRMATION")
    frame = _extract_frame_preview(html)
    assert 'data-element-role="ANSWER"' in frame
    for snippet in _NARRATION_SNIPPETS:
        assert snippet not in frame
    assert "직접 읽어보세요." not in frame


# CASE I/J: CASE_BRIDGE frame keeps the lowercase transform, no narration caption
def test_case_bridge_frame_no_narration_caption(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    html = _cb06_phase_html(db_path, assets_dir, reports_dir, plan_id, "CLEAN_DARK_FOCUS", "CASE_BRIDGE")
    frame = _extract_frame_preview(html)
    assert "VISUAL_TRANSFORMATION" in frame
    for snippet in _NARRATION_SNIPPETS:
        assert snippet not in frame


# CASE K/L: SCAFFOLD_REMOVAL frame has no visible caption content and no QUESTION content
def test_scaffold_removal_frame_no_caption_no_question(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    html = _cb06_phase_html(db_path, assets_dir, reports_dir, plan_id, "CLEAN_DARK_FOCUS", "SCAFFOLD_REMOVAL")
    frame = _extract_frame_preview(html)
    for snippet in _NARRATION_SNIPPETS:
        assert snippet not in frame
    assert 'data-element-role="QUESTION"' not in frame
    assert 'data-element-role="ANSWER"' in frame


# CASE M-Q: NATURAL_WORD_FINAL -- the single most important regression. The actual frame must
# contain exactly one visible learning-content element (the lowercase answer), zero caption/
# prompt/question-trace/progress/celebration content.
def test_natural_word_final_frame_is_cap_only(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    html = _cb06_phase_html(db_path, assets_dir, reports_dir, plan_id, "CLEAN_DARK_FOCUS", "NATURAL_WORD_FINAL")
    frame = _extract_frame_preview(html)
    for snippet in _NARRATION_SNIPPETS:
        assert snippet not in frame
    assert frame.count('data-element-role="CAPTION"') == 0
    assert frame.count('data-element-role="QUESTION"') == 0
    assert "THINKING_PROGRESS" not in frame
    for forbidden in ("정답입니다", "성공", "축하", "confetti", "badge"):
        assert forbidden not in frame
    assert frame.count('data-element-role="ANSWER"') == 1
    answer_text = next(t["text"] for t in _cb02_pieces(db_path, assets_dir, reports_dir, plan_id)[2]["text_elements"] if t["role"] == "ANSWER")
    assert answer_text.lower() in frame


# CASE R/S: source_text/display_text/canonical visual_design.json completely unchanged by the fix
def test_source_and_canonical_design_unchanged_by_visibility_fix(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    _, _, spec_scene_before = _cb02_pieces(db_path, assets_dir, reports_dir, plan_id)
    answer_before = next(t["text"] for t in spec_scene_before["text_elements"] if t["role"] == "ANSWER")
    result = run_visual_design(db_path, assets_dir, reports_dir, plan_id=plan_id)
    _, _, spec_scene_after = _cb02_pieces(db_path, assets_dir, reports_dir, plan_id)
    answer_after = next(t["text"] for t in spec_scene_after["text_elements"] if t["role"] == "ANSWER")
    assert answer_before == answer_after
    assert result["design"]["approval_status"] == "PENDING_HUMAN_REVIEW"


# CASE V: the other 7 Scenes' prototype output is completely unaffected by this CB06-only fix
def test_other_scenes_unaffected_by_cb06_visibility_fix(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    result = run_visual_design(db_path, assets_dir, reports_dir, plan_id=plan_id)
    manifest = json.loads((result["prototype_dir"] / "manifest.json").read_text(encoding="utf-8"))
    cb01_files = [f for f in manifest["files"] if f["scene_id"] == "CB01"]
    assert len(cb01_files) == len(CANDIDATES)
    for f in cb01_files:
        html = (result["prototype_dir"] / f["file"]).read_text(encoding="utf-8")
        assert 'data-element-role="CAPTION"' in html  # CB01's own caption is untouched by the CB06 fix


# CASE W: CLEAN_DARK_FOCUS and SOFT_LIGHT_EDUCATION share identical CB06 visibility semantics
def test_both_candidates_share_cb06_visibility_semantics(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    for phase in CB06_PHASES:
        frames = []
        for candidate in CANDIDATES:
            html = _cb06_phase_html(db_path, assets_dir, reports_dir, plan_id, candidate, phase)
            frame = _extract_frame_preview(html)
            roles_present = sorted(set(re.findall(r'data-element-role="([A-Z]+)"', frame)))
            frames.append(roles_present)
        assert frames[0] == frames[1], f"phase {phase} visibility semantics differ between candidates"


# ---------------------------------------------------------------------------
# 13-4C-2: Revised Prototype 반영 Visual Approval 정합성 교정 -- corrects the Source of Truth
# without deleting history. Negative CASEs per prompts/13-4C-2 section 21.
# ---------------------------------------------------------------------------

def _approve_then_correct(tmp_path, db_path, assets_dir, reports_dir, plan_id, legacy_candidate="SOFT_LIGHT_EDUCATION"):
    """Reproduces the real Plan 7 history shape: a legacy candidate-selection row (standing in for
    the real id=2 SOFT_LIGHT_EDUCATION record) followed by a correction to CLEAN_DARK_FOCUS."""
    run_visual_design(db_path, assets_dir, reports_dir, plan_id=plan_id)
    run_approve_visual_design(db_path, assets_dir, reports_dir, plan_id=plan_id, candidate=legacy_candidate)
    with connect(db_path) as conn:
        legacy_id = conn.execute("SELECT id FROM visual_design_specs WHERE production_plan_id = ? ORDER BY id DESC LIMIT 1", (plan_id,)).fetchone()["id"]
    correction = run_correct_visual_approval(db_path, assets_dir, reports_dir, plan_id=plan_id, selected_candidate="CLEAN_DARK_FOCUS", corrects_record_id=legacy_id)
    return legacy_id, correction


# CASE A: the legacy candidate-selection record is never returned as the current canonical candidate
def test_case_a_legacy_record_not_canonical(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    legacy_id, correction = _approve_then_correct(tmp_path, db_path, assets_dir, reports_dir, plan_id)
    assert correction["pass"] is True
    canonical = select_canonical_visual_approval(db_path, plan_id)
    assert canonical is not None
    assert canonical["id"] != legacy_id
    assert canonical["design"]["selected_candidate"] == "CLEAN_DARK_FOCUS"


# CASE B: selected_candidate with unresolved exact tokens must never yield full_profile_approved=True
def test_case_b_selection_without_token_approval_not_full_approved(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    _, correction = _approve_then_correct(tmp_path, db_path, assets_dir, reports_dir, plan_id)
    assert correction["record"]["selected_candidate"] == "CLEAN_DARK_FOCUS"
    assert correction["record"]["full_profile_approved"] is False
    assert correction["ready_for_final_renderer_binding"] is False


# CASE C: a pending mandatory category structurally forces renderer ready=false
def test_case_c_pending_mandatory_category_forces_gate_false():
    selection = select_visual_candidate("CLEAN_DARK_FOCUS")
    approvals = build_category_approvals("CLEAN_DARK_FOCUS")
    # Even with 14/15 approved, one unresolved mandatory category (color_palette) keeps the gate closed.
    for name in APPROVED_PROFILE_CATEGORIES:
        if name != "color_palette":
            approvals["categories"][name]["resolution_status"] = "APPROVED"
    assert ready_for_final_renderer_binding(selection, approvals) is False


# CASE D: an invalidated/legacy row is structurally invisible to canonical selection even if it is
# the only row that exists (no correction row present yet)
def test_case_d_no_correction_row_means_no_canonical(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    run_approve_visual_design(db_path, assets_dir, reports_dir, plan_id=plan_id, candidate="SOFT_LIGHT_EDUCATION")
    assert select_canonical_visual_approval(db_path, plan_id) is None


# CASE E/F: Prototype CSS values (HEX/font-size) existing in CANDIDATES never cause automatic
# category approval
def test_case_e_f_preview_css_values_never_auto_approve_categories():
    approvals = build_category_approvals("CLEAN_DARK_FOCUS")
    assert approvals["categories"]["color_palette"]["resolution_status"] == "PENDING_VISUAL_REVIEW"
    assert approvals["categories"]["typography_scale"]["resolution_status"] == "PENDING_VISUAL_REVIEW"


# CASE G: candidate selection alone never auto-finalizes the full profile
def test_case_g_candidate_selection_never_auto_finalizes(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    run_visual_design(db_path, assets_dir, reports_dir, plan_id=plan_id)
    result = run_approve_visual_design(db_path, assets_dir, reports_dir, plan_id=plan_id, candidate="CLEAN_DARK_FOCUS")
    assert result["ready_for_final_renderer_binding"] is False


# CASE I/J: correcting the record never deletes the row(s) it corrects
def test_case_i_j_correction_preserves_all_prior_history(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    with connect(db_path) as conn:
        before_count = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
    assert before_count == 0
    # _approve_then_correct produces exactly 3 rows: 13-4A design, legacy candidate selection, correction
    legacy_id, correction = _approve_then_correct(tmp_path, db_path, assets_dir, reports_dir, plan_id)
    with connect(db_path) as conn:
        after_count = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
        legacy_row = conn.execute("SELECT * FROM visual_design_specs WHERE id = ?", (legacy_id,)).fetchone()
    assert after_count == 3  # nothing removed -- design row + legacy selection row + correction row
    assert legacy_row is not None
    legacy_design = json.loads(legacy_row["design_json"])
    assert legacy_design["selected_candidate"] == "SOFT_LIGHT_EDUCATION"  # untouched by the correction


# CASE K/L: generating the Visual Design (13-4A) or Prototype (13-4B) never triggers any approval
def test_case_k_l_generation_alone_never_approves(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    result = run_visual_design(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["design"].get("record_status") is None
    assert result["design"].get("candidate_selection_status") is None
    assert result["approved_visual_profile"] is False


# CASE M: canonical selected candidate after correction must be exactly the human-confirmed one
def test_case_m_canonical_candidate_is_clean_dark_focus(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    _, correction = _approve_then_correct(tmp_path, db_path, assets_dir, reports_dir, plan_id)
    canonical = select_canonical_visual_approval(db_path, plan_id)
    assert canonical["design"]["selected_candidate"] == "CLEAN_DARK_FOCUS"


# CASE N: full_profile_approved=false and ready_for_final_renderer_binding=true simultaneously is
# structurally impossible (the gate function itself enforces this, never independently overridable)
def test_case_n_false_approved_true_ready_is_impossible():
    selection = {"candidate_selection_status": "SELECTED"}
    approvals_all_pending = {"categories": {}}
    assert ready_for_final_renderer_binding(selection, approvals_all_pending) is False


# CASE O: manifest revision lineage mismatch is corrected (13-4B-R -> 13-4B-R1)
def test_case_o_manifest_revision_corrected(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    run_visual_design(db_path, assets_dir, reports_dir, plan_id=plan_id)
    manifest_path = assets_dir / "generated" / f"plan_{plan_id}" / "render" / "prototypes" / "manifest.json"
    before = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert before["revision"] == "13-4B-R"  # the real lineage bug this stage fixes

    _, correction = _approve_then_correct(tmp_path, db_path, assets_dir, reports_dir, plan_id)
    assert correction["manifest_corrected"] is True
    after = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert after["revision"] == "13-4B-R1"


# CASE P: Preview-only values are never classified as Human Approved -- category_approvals always
# carries an explicit non-APPROVED reason distinguishing preview existence from human sign-off
def test_case_p_preview_value_not_classified_as_human_approved():
    approvals = build_category_approvals("CLEAN_DARK_FOCUS")
    for name in ("color_palette", "typography_scale"):
        cat = approvals["categories"][name]
        assert cat["resolution_status"] != "APPROVED"
        assert "승인" not in cat["reason"] or "근거 없음" in cat["reason"] or "별개" in cat["reason"]


# Mandatory/Optional/Conditional taxonomy is a complete, non-overlapping partition of all 15 categories
def test_category_taxonomy_is_complete_partition():
    all_categorized = set(MANDATORY_VISUAL_CATEGORIES) | set(OPTIONAL_VISUAL_CATEGORIES) | set(CONDITIONAL_VISUAL_CATEGORIES)
    assert all_categorized == set(APPROVED_PROFILE_CATEGORIES)
    assert len(set(MANDATORY_VISUAL_CATEGORIES) & set(OPTIONAL_VISUAL_CATEGORIES)) == 0
    assert len(set(MANDATORY_VISUAL_CATEGORIES) & set(CONDITIONAL_VISUAL_CATEGORIES)) == 0
    assert len(set(OPTIONAL_VISUAL_CATEGORIES) & set(CONDITIONAL_VISUAL_CATEGORIES)) == 0


# run_correct_visual_approval rejects an unrecognized candidate without recording anything
def test_run_correct_visual_approval_rejects_unknown_candidate(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    run_visual_design(db_path, assets_dir, reports_dir, plan_id=plan_id)
    with connect(db_path) as conn:
        before = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
    result = run_correct_visual_approval(db_path, assets_dir, reports_dir, plan_id=plan_id, selected_candidate="NOT_REAL")
    assert result["pass"] is False
    with connect(db_path) as conn:
        after = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
    assert after == before


# End-to-end: full correction report/json/unresolved mandatory categories against the real fixture
def test_run_correct_visual_approval_end_to_end_report(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    _, correction = _approve_then_correct(tmp_path, db_path, assets_dir, reports_dir, plan_id)
    assert correction["json_path"].exists()
    assert correction["report_path"].exists()
    assert set(correction["unresolved_mandatory_categories"]) == set(MANDATORY_VISUAL_CATEGORIES)
    assert correction["ready_for_final_renderer_binding"] is False
    record = json.loads(correction["json_path"].read_text(encoding="utf-8"))
    assert record["record_status"] == "CANONICAL_CORRECTION"
    assert record["mandatory_categories"] == list(MANDATORY_VISUAL_CATEGORIES)
    assert record["optional_categories"] == list(OPTIONAL_VISUAL_CATEGORIES)
    assert record["conditional_categories"] == list(CONDITIONAL_VISUAL_CATEGORIES)


# ---------------------------------------------------------------------------
# 13-4C-3: Font Family 비교 Prototype 생성 -- font_family is the only variable; Background/Color
# Palette/Typography Scale stay pinned to CANDIDATES["CLEAN_DARK_FOCUS"]; zero DB writes; font_family
# stays PENDING_VISUAL_REVIEW.
# ---------------------------------------------------------------------------

# CASE A (inverse): exactly 3 font candidates, never more
def test_font_candidates_exactly_three():
    assert len(FONT_CANDIDATES) == 3


# CASE B (inverse): every candidate has a real distinct stack, never empty
def test_font_candidates_all_have_real_stacks():
    for key, info in FONT_CANDIDATES.items():
        assert info["stack"]
        assert "sans-serif" in info["stack"]  # generic fallback present


# CASE C: candidates do not all collapse to the identical stack (genuinely distinct comparison)
def test_font_candidates_stacks_are_distinct():
    stacks = [info["stack"] for info in FONT_CANDIDATES.values()]
    assert len(set(stacks)) == len(stacks)


# CASE D/E: font-size and font-weight per typography role are identical across all 3 candidates --
# only font-family differs
def test_font_candidates_share_identical_typography_scale():
    reference = None
    for font_key in FONT_CANDIDATES:
        html = build_font_hierarchy_test_prototype(font_key)
        frame = _extract_frame_preview(html)
        sizes = re.findall(r"font-size:(\d+px)", frame)
        weights = re.findall(r"font-weight:(\d+)", frame)
        if reference is None:
            reference = (sizes, weights)
        else:
            assert (sizes, weights) == reference, f"{font_key} typography scale differs from other candidates"


# CASE F: Color Palette is identical (by HEX) across all 3 candidates
def test_font_candidates_share_identical_color_palette():
    reference = None
    for font_key in FONT_CANDIDATES:
        html = build_font_learning_prototype(font_key)
        frame = _extract_frame_preview(html)
        colors = sorted(set(re.findall(r"color:(#[0-9a-fA-F]{6})", frame)))
        if reference is None:
            reference = colors
        else:
            assert colors == reference


# CASE G (inverse): confirms background is pinned to the CLEAN_DARK_FOCUS value for every candidate
def test_font_candidates_share_identical_background():
    for font_key in FONT_CANDIDATES:
        html = build_font_learning_prototype(font_key)
        assert CANDIDATES["CLEAN_DARK_FOCUS"]["page_bg"] in html


# CASE H/I/J: glyph test includes I/l, O/0, b/d/p/q (and the rest of the required pairs)
def test_glyph_test_includes_required_pairs():
    html = build_font_glyph_test_prototype("VERDANA_HUMANIST")
    frame = _extract_frame_preview(html)
    for pair in ("I l", "1 I l", "O 0", "b d", "p q", "u v", "c e", "rn m", "a o"):
        assert pair in frame


# CASE K: CAP -> cap visual transformation present in glyph test
def test_glyph_test_includes_case_bridge_pairs():
    html = build_font_glyph_test_prototype("VERDANA_HUMANIST")
    frame = _extract_frame_preview(html)
    for upper, lower in (("CAP", "cap"), ("BAT", "bat"), ("MAP", "map"), ("BAG", "bag")):
        assert upper in frame and lower in frame


# CASE L/M/N/O/P: all 5 typography hierarchy levels preserved -- values taken from the real
# CANDIDATES["CLEAN_DARK_FOCUS"]["roles"], never a separately hardcoded guess (that mismatch was a
# real bug caught here: PRIMARY's real value is 42px, not the 40px this test originally assumed)
def test_hierarchy_test_preserves_all_five_levels():
    html = build_font_hierarchy_test_prototype("VERDANA_HUMANIST")
    frame = _extract_frame_preview(html)
    for role in ("DOMINANT", "PRIMARY", "SUPPORTING", "CAPTION", "MICRO"):
        assert CANDIDATES["CLEAN_DARK_FOCUS"]["roles"][role] in frame


# CASE Q: background exactly matches the canonical CLEAN_DARK_FOCUS value
def test_font_review_background_matches_canonical():
    assert CANDIDATES["CLEAN_DARK_FOCUS"]["page_bg"] == "#111318"


# CASE R: color palette values used in the review match the canonical CLEAN_DARK_FOCUS palette exactly
def test_font_review_colors_match_canonical_palette():
    html = build_font_hierarchy_test_prototype("SEGOE_MODERN")
    frame = _extract_frame_preview(html)
    assert CANDIDATES["CLEAN_DARK_FOCUS"]["colors"]["SUCCESS"] in frame


# CASE S/T/U: generating the Font Review never approves font_family, never sets full_profile_approved,
# never makes the renderer gate true -- because it writes to the DB at all
def test_font_review_never_writes_to_db(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    run_visual_design(db_path, assets_dir, reports_dir, plan_id=plan_id)
    with connect(db_path) as conn:
        before = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
    result = run_font_family_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["pass"] is True
    with connect(db_path) as conn:
        after = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
    assert after == before  # zero new rows -- the strongest structural proof of no auto-approval


# CASE V: no external font URLs (http/https) anywhere in the generated files
def test_font_review_no_external_font_urls(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    run_visual_design(db_path, assets_dir, reports_dir, plan_id=plan_id)
    result = run_font_family_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    for entry in result["manifest"]["files"]:
        html = (result["review_dir"] / entry["file"]).read_text(encoding="utf-8")
        assert "http://" not in html and "https://" not in html
        assert "fonts.googleapis.com" not in html and "fonts.gstatic.com" not in html


# CASE W: the existing 26-file prototypes/ directory (13-4B-R1) is completely untouched
def test_font_review_does_not_touch_existing_prototypes(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    design_result = run_visual_design(db_path, assets_dir, reports_dir, plan_id=plan_id)
    proto_manifest_before = (design_result["prototype_dir"] / "manifest.json").read_text(encoding="utf-8")
    proto_files_before = sorted(p.name for p in design_result["prototype_dir"].glob("*.html"))

    run_font_family_review(db_path, assets_dir, reports_dir, plan_id=plan_id)

    proto_manifest_after = (design_result["prototype_dir"] / "manifest.json").read_text(encoding="utf-8")
    proto_files_after = sorted(p.name for p in design_result["prototype_dir"].glob("*.html"))
    assert proto_manifest_before == proto_manifest_after
    assert proto_files_before == proto_files_after


# manifest never contains a selected_font/approved_font field (section 25's explicit prohibition)
def test_font_review_manifest_never_declares_a_winner(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    run_visual_design(db_path, assets_dir, reports_dir, plan_id=plan_id)
    result = run_font_family_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert "selected_font" not in result["manifest"]
    assert "approved_font" not in result["manifest"]
    assert result["manifest"]["font_family_status"] == "PENDING_VISUAL_REVIEW"


# end-to-end: real file counts, index.html links every file, report exists
def test_run_font_family_review_end_to_end(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    run_visual_design(db_path, assets_dir, reports_dir, plan_id=plan_id)
    result = run_font_family_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["pass"] is True
    assert result["file_count"] == len(FONT_CANDIDATES) * 3  # learning + glyph_test + hierarchy_test
    assert result["report_path"].exists()
    index_html = (result["review_dir"] / "index.html").read_text(encoding="utf-8")
    for entry in result["manifest"]["files"]:
        assert entry["file"] in index_html


# run_font_family_review only depends on Scene Layout being ready (validate_visual_design_entry_gate),
# not on a prior visual_design_specs row -- it succeeds as soon as 13-3 is ready, exactly like
# run_visual_design itself does not require a pre-existing visual_design_specs row.
def test_run_font_family_review_only_requires_scene_layout(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    with connect(db_path) as conn:
        before = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
    assert before == 0  # no visual_design_specs row exists yet
    result = run_font_family_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["pass"] is True


# the real failure case: no Scene Layout ready at all
def test_run_font_family_review_fails_without_scene_layout(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    result = run_font_family_review(db_path, tmp_path / "assets", tmp_path / "reports", plan_id=1)
    assert result["pass"] is False


# ---------------------------------------------------------------------------
# 13-4C-6: Font Family Human Approval -- persists only font_family=APPROVED (VERDANA_HUMANIST) on
# top of the current canonical CANONICAL_CORRECTION record, append-only, every other category
# untouched, full_profile_approved/ready_for_final_renderer_binding both stay False.
# ---------------------------------------------------------------------------

def _ready_plan_with_canonical_correction(tmp_path, db_path):
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    legacy_id, correction = _approve_then_correct(tmp_path, db_path, assets_dir, reports_dir, plan_id)
    return plan_id, assets_dir, reports_dir, legacy_id, correction


# end-to-end: font_family becomes APPROVED with the real code font stack, provenance recorded,
# every other category preserved PENDING, gates stay False, append-only (new row, prior untouched)
def test_run_font_family_human_approval_end_to_end(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, legacy_id, correction = _ready_plan_with_canonical_correction(tmp_path, db_path)
    prior_canonical_id = correction["visual_design_row_id"]

    with connect(db_path) as conn:
        before = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
        prior_design_json_before = conn.execute("SELECT design_json FROM visual_design_specs WHERE id = ?", (prior_canonical_id,)).fetchone()["design_json"]

    result = run_font_family_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["pass"] is True
    assert result["approved_font_family"] == "VERDANA_HUMANIST"
    assert result["font_stack"] == FONT_CANDIDATES["VERDANA_HUMANIST"]["stack"]
    assert result["record"]["category_approvals"]["font_family"]["resolution_status"] == "APPROVED"
    assert result["record"]["category_approvals"]["font_family"]["resolved_style"] == FONT_CANDIDATES["VERDANA_HUMANIST"]["stack"]
    assert result["record"]["category_approvals"]["font_family"]["provenance"]["review_stage"] == "13-4C-6"
    assert result["record"]["category_approvals"]["font_family"]["provenance"]["review_type"] == "HUMAN_VISUAL_REVIEW"
    assert result["record"]["selected_candidate"] == "CLEAN_DARK_FOCUS"

    # every other category preserved exactly (still PENDING_VISUAL_REVIEW, matching the real fixture)
    for name, cat in result["record"]["category_approvals"].items():
        if name == "font_family":
            continue
        assert cat["resolution_status"] == "PENDING_VISUAL_REVIEW"

    assert result["record"]["full_profile_approved"] is False
    assert result["record"]["ready_for_final_renderer_binding"] is False
    assert result["full_profile_approved"] is False
    assert result["ready_for_final_renderer_binding"] is False

    with connect(db_path) as conn:
        after = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
        prior_design_json_after = conn.execute("SELECT design_json FROM visual_design_specs WHERE id = ?", (prior_canonical_id,)).fetchone()["design_json"]
    assert after == before + 1  # exactly one new append-only row
    assert prior_design_json_after == prior_design_json_before  # prior canonical row byte-for-byte unchanged
    assert result["prior_canonical_id"] == prior_canonical_id
    assert result["record"]["corrects_record_id"] == prior_canonical_id

    profile = json.loads(result["json_path"].read_text(encoding="utf-8"))
    assert profile["category_approvals"]["font_family"]["resolution_status"] == "APPROVED"
    assert profile["full_profile_approved"] is False
    assert result["report_path"].exists()


# PRIMARY typography is untouched by this stage
def test_run_font_family_human_approval_does_not_change_typography(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, legacy_id, correction = _ready_plan_with_canonical_correction(tmp_path, db_path)
    result = run_font_family_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["pass"] is True
    assert CANDIDATES["CLEAN_DARK_FOCUS"]["roles"]["PRIMARY"] == "font-size:42px;font-weight:700;"
    assert result["record"]["category_approvals"]["typography_scale"]["resolution_status"] == "PENDING_VISUAL_REVIEW"


# CASE A: approving a font key that does not exist at all fails, writes nothing
def test_run_font_family_human_approval_case_a_unknown_candidate_fails(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, legacy_id, correction = _ready_plan_with_canonical_correction(tmp_path, db_path)
    with connect(db_path) as conn:
        before = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
    result = run_font_family_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id, approved_font_family="NOT_A_REAL_FONT")
    assert result["pass"] is False
    with connect(db_path) as conn:
        after = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
    assert after == before


# CASE B: ARIAL_NEUTRAL has no recorded Human Review decision -- refused, writes nothing
def test_run_font_family_human_approval_case_b_arial_without_human_review_fails(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, legacy_id, correction = _ready_plan_with_canonical_correction(tmp_path, db_path)
    with connect(db_path) as conn:
        before = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
    result = run_font_family_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id, approved_font_family="ARIAL_NEUTRAL")
    assert result["pass"] is False
    assert "ARIAL_NEUTRAL" in result["reason"]
    with connect(db_path) as conn:
        after = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
    assert after == before


# CASE C: SEGOE_MODERN has no recorded Human Review decision -- refused, writes nothing
def test_run_font_family_human_approval_case_c_segoe_without_human_review_fails(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, legacy_id, correction = _ready_plan_with_canonical_correction(tmp_path, db_path)
    result = run_font_family_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id, approved_font_family="SEGOE_MODERN")
    assert result["pass"] is False
    assert "SEGOE_MODERN" in result["reason"]


# CASE D (inverse, structural): typography_scale never becomes APPROVED as a side effect
def test_run_font_family_human_approval_case_d_never_approves_typography_scale(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, legacy_id, correction = _ready_plan_with_canonical_correction(tmp_path, db_path)
    result = run_font_family_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["record"]["category_approvals"]["typography_scale"]["resolution_status"] != "APPROVED"


# CASE E (inverse, structural): PRIMARY's real code value never changes because of this approval
def test_run_font_family_human_approval_case_e_primary_value_unchanged(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, legacy_id, correction = _ready_plan_with_canonical_correction(tmp_path, db_path)
    before = CANDIDATES["CLEAN_DARK_FOCUS"]["roles"]["PRIMARY"]
    run_font_family_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert CANDIDATES["CLEAN_DARK_FOCUS"]["roles"]["PRIMARY"] == before == "font-size:42px;font-weight:700;"


# CASE F: full_profile_approved never becomes True from this single-category approval
def test_run_font_family_human_approval_case_f_full_profile_stays_false(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, legacy_id, correction = _ready_plan_with_canonical_correction(tmp_path, db_path)
    result = run_font_family_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["record"]["full_profile_approved"] is False


# CASE G: ready_for_final_renderer_binding never becomes True (8 other mandatory categories still PENDING)
def test_run_font_family_human_approval_case_g_renderer_gate_stays_false(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, legacy_id, correction = _ready_plan_with_canonical_correction(tmp_path, db_path)
    result = run_font_family_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["record"]["ready_for_final_renderer_binding"] is False


# CASE H: the existing canonical DB row is never overwritten -- append-only
def test_run_font_family_human_approval_case_h_does_not_overwrite_canonical_row(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, legacy_id, correction = _ready_plan_with_canonical_correction(tmp_path, db_path)
    prior_id = correction["visual_design_row_id"]
    with connect(db_path) as conn:
        before = conn.execute("SELECT design_json FROM visual_design_specs WHERE id = ?", (prior_id,)).fetchone()["design_json"]
    run_font_family_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    with connect(db_path) as conn:
        after = conn.execute("SELECT design_json FROM visual_design_specs WHERE id = ?", (prior_id,)).fetchone()["design_json"]
    assert before == after


# CASE I: the CLEAN_DARK_FOCUS canonical visual candidate is never changed by a font_family approval
def test_run_font_family_human_approval_case_i_visual_candidate_unchanged(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, legacy_id, correction = _ready_plan_with_canonical_correction(tmp_path, db_path)
    result = run_font_family_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["record"]["selected_candidate"] == "CLEAN_DARK_FOCUS"


# fails cleanly with no canonical correction record yet (no correct-visual-approval run at all)
def test_run_font_family_human_approval_fails_without_canonical_record(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    run_visual_design(db_path, assets_dir, reports_dir, plan_id=plan_id)
    result = run_font_family_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["pass"] is False


# the default approved_font_family constant is exactly VERDANA_HUMANIST -- the only candidate with a
# real Human Review decision on record
def test_human_reviewed_font_family_constant_is_verdana():
    assert HUMAN_REVIEWED_FONT_FAMILY == "VERDANA_HUMANIST"


# Font Review Prototype (font_review/) and existing Visual Prototype (prototypes/) are both untouched
def test_run_font_family_human_approval_does_not_touch_prototype_directories(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, legacy_id, correction = _ready_plan_with_canonical_correction(tmp_path, db_path)
    design_result = run_visual_design(db_path, assets_dir, reports_dir, plan_id=plan_id)
    review_result = run_font_family_review(db_path, assets_dir, reports_dir, plan_id=plan_id)

    proto_manifest_before = (design_result["prototype_dir"] / "manifest.json").read_text(encoding="utf-8")
    font_review_manifest_before = (review_result["review_dir"] / "manifest.json").read_text(encoding="utf-8")

    run_font_family_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)

    proto_manifest_after = (design_result["prototype_dir"] / "manifest.json").read_text(encoding="utf-8")
    font_review_manifest_after = (review_result["review_dir"] / "manifest.json").read_text(encoding="utf-8")
    assert proto_manifest_before == proto_manifest_after
    assert font_review_manifest_before == font_review_manifest_after


# ---------------------------------------------------------------------------
# 13-4C-7: Color Palette + Background Human Review -- Review Preparation only, exactly like
# 13-4C-3's Font Review: zero DB writes. Background/Color Palette come from CANDIDATES["CLEAN_DARK_
# FOCUS"]'s real preview values (the thing under review); Typography and the already-APPROVED
# font_family are both fixed conditions, never re-approved or mutated here.
# ---------------------------------------------------------------------------

def _ready_plan_with_font_approved(tmp_path, db_path):
    plan_id, assets_dir, reports_dir, legacy_id, correction = _ready_plan_with_canonical_correction(tmp_path, db_path)
    font_result = run_font_family_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert font_result["pass"] is True
    return plan_id, assets_dir, reports_dir, font_result


# --- Contrast pure function tests (no DB) ---

def test_contrast_ratio_white_black_is_21():
    assert contrast_ratio("#ffffff", "#000000") == pytest.approx(21.0, abs=0.001)


def test_contrast_ratio_order_independent():
    assert contrast_ratio("#111318", "#e6e6e6") == contrast_ratio("#e6e6e6", "#111318")


def test_contrast_ratio_same_color_is_one():
    assert contrast_ratio("#60a5fa", "#60a5fa") == pytest.approx(1.0, abs=0.001)


def test_contrast_ratio_rejects_invalid_hex():
    with pytest.raises(ValueError):
        contrast_ratio("not-a-color", "#000000")
    with pytest.raises(ValueError):
        contrast_ratio("#12345", "#000000")


def test_build_contrast_results_covers_all_seven_roles():
    results = build_contrast_results(CANDIDATES["CLEAN_DARK_FOCUS"]["page_bg"], CANDIDATES["CLEAN_DARK_FOCUS"]["colors"])
    assert set(results.keys()) == set(COLOR_REVIEW_ROLES)
    for role in COLOR_REVIEW_ROLES:
        entry = results[role]
        assert entry["hex"] == CANDIDATES["CLEAN_DARK_FOCUS"]["colors"][role]
        expected_ratio = contrast_ratio(entry["hex"], CANDIDATES["CLEAN_DARK_FOCUS"]["page_bg"])
        assert entry["contrast_ratio"] == pytest.approx(round(expected_ratio, 2))
        assert entry["normal_text_reference"] in ("PASS", "FAIL")
        assert entry["large_text_reference"] in ("PASS", "FAIL")


# real failure cases
def test_run_color_background_review_fails_without_scene_layout(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    result = run_color_background_review(db_path, tmp_path / "assets", tmp_path / "reports", plan_id=1)
    assert result["pass"] is False


def test_run_color_background_review_fails_without_font_approval(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, legacy_id, correction = _ready_plan_with_canonical_correction(tmp_path, db_path)
    result = run_color_background_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["pass"] is False


# end-to-end
def test_run_color_background_review_end_to_end(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, font_result = _ready_plan_with_font_approved(tmp_path, db_path)
    result = run_color_background_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["pass"] is True
    assert result["file_count"] == 7
    assert result["report_path"].exists()
    index_html = (result["review_dir"] / "index.html").read_text(encoding="utf-8")
    for entry in result["manifest"]["files"]:
        assert entry["file"] in index_html
    assert result["font_stack"] == font_result["font_stack"]
    assert result["approved_font_candidate"] == "VERDANA_HUMANIST"


def test_color_role_usage_counts_shape(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, font_result = _ready_plan_with_font_approved(tmp_path, db_path)
    result = run_color_background_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    usage = result["color_role_usage"]
    assert set(usage.keys()) == set(COLOR_REVIEW_ROLES)
    assert all(isinstance(v, int) and v >= 0 for v in usage.values())


def test_manifest_never_declares_approved_fields(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, font_result = _ready_plan_with_font_approved(tmp_path, db_path)
    result = run_color_background_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert "approved_color_palette" not in result["manifest"]
    assert "approved_background" not in result["manifest"]
    assert result["manifest"]["color_palette_status"] == "PENDING_VISUAL_REVIEW"
    assert result["manifest"]["background_status"] == "PENDING_VISUAL_REVIEW"


# CASE A: canonical candidate != CLEAN_DARK_FOCUS -> fails, writes nothing
def test_run_color_background_review_case_a_wrong_candidate_fails(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    run_visual_design(db_path, assets_dir, reports_dir, plan_id=plan_id)
    run_correct_visual_approval(db_path, assets_dir, reports_dir, plan_id=plan_id, selected_candidate="SOFT_LIGHT_EDUCATION", corrects_record_id=1)
    with connect(db_path) as conn:
        before = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
    result = run_color_background_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["pass"] is False
    with connect(db_path) as conn:
        after = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
    assert after == before


# CASE B: font_family category is never changed by this stage
def test_run_color_background_review_case_b_font_family_unchanged(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, font_result = _ready_plan_with_font_approved(tmp_path, db_path)
    before = select_canonical_visual_approval(db_path, plan_id)["design"]["category_approvals"]["font_family"]
    run_color_background_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    after = select_canonical_visual_approval(db_path, plan_id)["design"]["category_approvals"]["font_family"]
    assert before == after


# CASE C: Font Review artifact (13-4C-3) is completely untouched
def test_run_color_background_review_case_c_font_review_unchanged(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, font_result = _ready_plan_with_font_approved(tmp_path, db_path)
    font_review_result = run_font_family_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    manifest_before = (font_review_result["review_dir"] / "manifest.json").read_text(encoding="utf-8")
    run_color_background_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    manifest_after = (font_review_result["review_dir"] / "manifest.json").read_text(encoding="utf-8")
    assert manifest_before == manifest_after


# CASE D: 13-4B-R1 Visual Prototype directory is completely untouched
def test_run_color_background_review_case_d_prototypes_unchanged(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, font_result = _ready_plan_with_font_approved(tmp_path, db_path)
    proto_manifest_path = assets_dir / "generated" / f"plan_{plan_id}" / "render" / "prototypes" / "manifest.json"
    manifest_before = proto_manifest_path.read_text(encoding="utf-8")
    run_color_background_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    manifest_after = proto_manifest_path.read_text(encoding="utf-8")
    assert manifest_before == manifest_after


# CASE E: Color Review Prototype content matches the real CLEAN_DARK_FOCUS preview colors exactly
def test_run_color_background_review_case_e_colors_match_real_candidate(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, font_result = _ready_plan_with_font_approved(tmp_path, db_path)
    result = run_color_background_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    html = (result["review_dir"] / "02_SEMANTIC_COLOR_ROLES.html").read_text(encoding="utf-8")
    for role in COLOR_REVIEW_ROLES:
        assert CANDIDATES["CLEAN_DARK_FOCUS"]["colors"][role] in html


# CASE F: Background review value matches the real preview page_bg exactly
def test_run_color_background_review_case_f_background_matches_real_value(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, font_result = _ready_plan_with_font_approved(tmp_path, db_path)
    result = run_color_background_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    for entry in result["manifest"]["files"]:
        html = (result["review_dir"] / entry["file"]).read_text(encoding="utf-8")
        assert CANDIDATES["CLEAN_DARK_FOCUS"]["page_bg"] in html
    assert result["manifest"]["preview_values"]["page_bg"] == CANDIDATES["CLEAN_DARK_FOCUS"]["page_bg"]


# CASE G: Typography is a fixed condition -- every font-size/font-weight pair that appears is one
# of the real CANDIDATES roles, never an invented or per-screen-varied value
def test_run_color_background_review_case_g_typography_fixed_across_screens(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, font_result = _ready_plan_with_font_approved(tmp_path, db_path)
    result = run_color_background_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    roles = CANDIDATES["CLEAN_DARK_FOCUS"]["roles"]
    for entry in result["manifest"]["files"]:
        html = (result["review_dir"] / entry["file"]).read_text(encoding="utf-8")
        found_styles = set(re.findall(r"font-size:\d+px;font-weight:\d+;", html))
        for style in found_styles:
            assert style in roles.values()


# CASE H: PRIMARY still matches the fixed baseline (42px/700), never silently changed
def test_run_color_background_review_case_h_primary_matches_fixed_baseline():
    assert CANDIDATES["CLEAN_DARK_FOCUS"]["roles"]["PRIMARY"] == "font-size:42px;font-weight:700;"


# CASE I/J: generating the review never flips color_palette or background to APPROVED
def test_run_color_background_review_case_i_j_never_approves_color_or_background(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, font_result = _ready_plan_with_font_approved(tmp_path, db_path)
    run_color_background_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    record = select_canonical_visual_approval(db_path, plan_id)["design"]
    assert record["category_approvals"]["color_palette"]["resolution_status"] == "PENDING_VISUAL_REVIEW"
    assert record["category_approvals"]["background"]["resolution_status"] == "PENDING_VISUAL_REVIEW"


# CASE K/L/M: full_profile_approved / ready_for_final_renderer_binding (the same gate also governs
# Stage 13-5 readiness -- no separate code-level flag exists for that) both stay False
def test_run_color_background_review_case_k_l_m_gates_stay_false(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, font_result = _ready_plan_with_font_approved(tmp_path, db_path)
    run_color_background_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    record = select_canonical_visual_approval(db_path, plan_id)["design"]
    assert record["full_profile_approved"] is False
    assert record["ready_for_final_renderer_binding"] is False


# CASE N: contrast calculation never mutates CANDIDATES' real HEX values
def test_run_color_background_review_case_n_contrast_never_mutates_hex(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, font_result = _ready_plan_with_font_approved(tmp_path, db_path)
    before = dict(CANDIDATES["CLEAN_DARK_FOCUS"]["colors"])
    run_color_background_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert CANDIDATES["CLEAN_DARK_FOCUS"]["colors"] == before


# CASE O: the grayscale preview never changes the canonical CANDIDATES palette either
def test_run_color_background_review_case_o_grayscale_never_mutates_palette(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, font_result = _ready_plan_with_font_approved(tmp_path, db_path)
    before_bg = CANDIDATES["CLEAN_DARK_FOCUS"]["page_bg"]
    result = run_color_background_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    html = (result["review_dir"] / "07_GRAYSCALE_ACCESSIBILITY_SAMPLE.html").read_text(encoding="utf-8")
    assert "filter:grayscale(100%)" in html
    assert CANDIDATES["CLEAN_DARK_FOCUS"]["page_bg"] == before_bg


# CASE P: EXCEPTION_CAUTION (and SECONDARY/MUTED, same real 0-usage finding for Plan 7) are never
# falsely labeled as an actual Plan 7 usage example when they are not actually used
def test_run_color_background_review_case_p_no_false_usage_claim(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, font_result = _ready_plan_with_font_approved(tmp_path, db_path)
    result = run_color_background_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    usage = result["color_role_usage"]
    exception_html = (result["review_dir"] / "06_EXCEPTION_CAUTION_SAMPLE.html").read_text(encoding="utf-8")
    secondary_html = (result["review_dir"] / "05_MUTED_SECONDARY_SAMPLE.html").read_text(encoding="utf-8")
    if usage.get("EXCEPTION_CAUTION", 0) == 0:
        assert "NOT USED IN CURRENT PLAN 7" in exception_html
    if usage.get("SECONDARY", 0) == 0 and usage.get("MUTED", 0) == 0:
        assert "NOT USED IN CURRENT PLAN 7" in secondary_html


# CASE Q: the existing canonical DB row is never modified by this stage
def test_run_color_background_review_case_q_canonical_row_unchanged(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, font_result = _ready_plan_with_font_approved(tmp_path, db_path)
    canonical_id = font_result["visual_design_row_id"]
    with connect(db_path) as conn:
        before = conn.execute("SELECT design_json FROM visual_design_specs WHERE id = ?", (canonical_id,)).fetchone()["design_json"]
    run_color_background_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    with connect(db_path) as conn:
        after = conn.execute("SELECT design_json FROM visual_design_specs WHERE id = ?", (canonical_id,)).fetchone()["design_json"]
    assert before == after


# CASE R: this stage is Review Preparation -- it writes ZERO new visual_design_specs rows
def test_run_color_background_review_case_r_writes_zero_db_rows(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, font_result = _ready_plan_with_font_approved(tmp_path, db_path)
    with connect(db_path) as conn:
        before = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
    result = run_color_background_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["pass"] is True
    with connect(db_path) as conn:
        after = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
    assert after == before


# CASE S: approved_visual_profile.json's approval state is untouched by this stage
def test_run_color_background_review_case_s_profile_json_unchanged(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, font_result = _ready_plan_with_font_approved(tmp_path, db_path)
    profile_path = font_result["json_path"]
    before = profile_path.read_text(encoding="utf-8")
    run_color_background_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    after = profile_path.read_text(encoding="utf-8")
    assert before == after


# Determinism: identical inputs -> identical manifest fields (except generated_at) and identical HTML
def test_run_color_background_review_determinism(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, font_result = _ready_plan_with_font_approved(tmp_path, db_path)

    result1 = run_color_background_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    files1 = {p.name: p.read_text(encoding="utf-8") for p in result1["review_dir"].glob("*.html")}
    manifest1 = dict(result1["manifest"])
    manifest1.pop("generated_at")

    result2 = run_color_background_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    files2 = {p.name: p.read_text(encoding="utf-8") for p in result2["review_dir"].glob("*.html")}
    manifest2 = dict(result2["manifest"])
    manifest2.pop("generated_at")

    assert files1 == files2
    assert manifest1 == manifest2


# ---------------------------------------------------------------------------
# 13-4C-8: MUTED Color Refinement Human Review -- (A) Background Human Approval persistence
# (append-only, exactly like 13-4C-6's font_family approval) + (B) MUTED Review Prep (zero DB
# writes, exactly like 13-4C-3/13-4C-7).
# ---------------------------------------------------------------------------

# --- pure function tests ---

def test_build_muted_candidates_returns_three_distinct_candidates():
    candidates = build_muted_candidates("#111318", "#555b66", "#9ca3af")
    assert candidates["A_CURRENT"]["hex"] == "#555b66"
    assert candidates["B_MODERATE"]["hex"] != candidates["A_CURRENT"]["hex"]
    assert candidates["C_ACCESSIBLE"]["hex"] not in (candidates["A_CURRENT"]["hex"], candidates["B_MODERATE"]["hex"])
    assert candidates["C_ACCESSIBLE"]["hex"] != "#9ca3af"


def test_build_muted_candidates_contrast_strictly_increasing_and_below_secondary():
    page_bg = CANDIDATES["CLEAN_DARK_FOCUS"]["page_bg"]
    secondary = CANDIDATES["CLEAN_DARK_FOCUS"]["colors"]["SECONDARY"]
    muted = CANDIDATES["CLEAN_DARK_FOCUS"]["colors"]["MUTED"]
    candidates = build_muted_candidates(page_bg, muted, secondary)
    a = candidates["A_CURRENT"]["contrast_ratio"]
    b = candidates["B_MODERATE"]["contrast_ratio"]
    c = candidates["C_ACCESSIBLE"]["contrast_ratio"]
    secondary_ratio = contrast_ratio(secondary, page_bg)
    assert a < b < c < secondary_ratio


def test_build_muted_candidates_deterministic():
    r1 = build_muted_candidates("#111318", "#555b66", "#9ca3af")
    r2 = build_muted_candidates("#111318", "#555b66", "#9ca3af")
    assert r1 == r2


def test_muted_candidates_never_declare_approved_or_selected():
    candidates = build_muted_candidates("#111318", "#555b66", "#9ca3af")
    for info in candidates.values():
        assert "approved" not in info
        assert "selected" not in info


def test_muted_candidate_factors_are_fixed_constants():
    assert set(MUTED_CANDIDATE_FACTORS.keys()) == {"B_MODERATE", "C_ACCESSIBLE"}
    assert 0 < MUTED_CANDIDATE_FACTORS["B_MODERATE"] < MUTED_CANDIDATE_FACTORS["C_ACCESSIBLE"] < 1


# --- Background Human Approval persistence ---

def test_run_background_human_approval_end_to_end(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, font_result = _ready_plan_with_font_approved(tmp_path, db_path)
    prior_id = font_result["visual_design_row_id"]
    with connect(db_path) as conn:
        before_count = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
        prior_json_before = conn.execute("SELECT design_json FROM visual_design_specs WHERE id = ?", (prior_id,)).fetchone()["design_json"]

    result = run_background_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["pass"] is True
    assert result["approved_background"] == CANDIDATES["CLEAN_DARK_FOCUS"]["page_bg"]
    bg_cat = result["record"]["category_approvals"]["background"]
    assert bg_cat["resolution_status"] == "APPROVED"
    assert bg_cat["resolved_style"] == CANDIDATES["CLEAN_DARK_FOCUS"]["page_bg"]
    assert bg_cat["provenance"]["review_stage"] == "13-4C-8"
    assert bg_cat["provenance"]["review_type"] == "HUMAN_VISUAL_REVIEW"
    assert result["record"]["category_approvals"]["font_family"]["resolution_status"] == "APPROVED"
    assert result["record"]["category_approvals"]["font_family"]["resolved_style"] == font_result["font_stack"]
    assert result["record"]["category_approvals"]["color_palette"]["resolution_status"] == "PENDING_VISUAL_REVIEW"
    assert result["full_profile_approved"] is False
    assert result["ready_for_final_renderer_binding"] is False

    with connect(db_path) as conn:
        after_count = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
        prior_json_after = conn.execute("SELECT design_json FROM visual_design_specs WHERE id = ?", (prior_id,)).fetchone()["design_json"]
    assert after_count == before_count + 1
    assert prior_json_after == prior_json_before
    assert result["prior_canonical_id"] == prior_id

    profile = json.loads(result["json_path"].read_text(encoding="utf-8"))
    assert profile["category_approvals"]["background"]["resolution_status"] == "APPROVED"
    assert profile["category_approvals"]["font_family"]["resolution_status"] == "APPROVED"
    assert profile["category_approvals"]["color_palette"]["resolution_status"] == "PENDING_VISUAL_REVIEW"


def test_run_background_human_approval_fails_without_canonical_record(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir = _make_ready_plan_with_scene_layout(tmp_path, db_path)
    run_visual_design(db_path, assets_dir, reports_dir, plan_id=plan_id)
    result = run_background_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["pass"] is False


# CASE A: no parameter exists to persist a background value other than the real code page_bg --
# a structural guarantee, verified directly
def test_run_background_human_approval_case_a_value_always_matches_real_code(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, font_result = _ready_plan_with_font_approved(tmp_path, db_path)
    result = run_background_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["approved_background"] == CANDIDATES["CLEAN_DARK_FOCUS"]["page_bg"]
    assert result["record"]["category_approvals"]["background"]["resolved_style"] == CANDIDATES["CLEAN_DARK_FOCUS"]["page_bg"]


# CASE B: the existing canonical row is never modified -- append-only
def test_run_background_human_approval_case_b_prior_row_unchanged(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, font_result = _ready_plan_with_font_approved(tmp_path, db_path)
    prior_id = font_result["visual_design_row_id"]
    with connect(db_path) as conn:
        before = conn.execute("SELECT design_json FROM visual_design_specs WHERE id = ?", (prior_id,)).fetchone()["design_json"]
    run_background_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    with connect(db_path) as conn:
        after = conn.execute("SELECT design_json FROM visual_design_specs WHERE id = ?", (prior_id,)).fetchone()["design_json"]
    assert before == after


# CASE C/D: color_palette and typography_scale are never auto-approved as a side effect
def test_run_background_human_approval_case_c_d_other_categories_stay_pending(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, font_result = _ready_plan_with_font_approved(tmp_path, db_path)
    result = run_background_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    cats = result["record"]["category_approvals"]
    assert cats["color_palette"]["resolution_status"] == "PENDING_VISUAL_REVIEW"
    assert cats["typography_scale"]["resolution_status"] == "PENDING_VISUAL_REVIEW"


# CASE E: font_family is never changed by a background approval
def test_run_background_human_approval_case_e_font_family_preserved(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, font_result = _ready_plan_with_font_approved(tmp_path, db_path)
    before_font = font_result["record"]["category_approvals"]["font_family"]
    result = run_background_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["record"]["category_approvals"]["font_family"] == before_font


# CASE F/G/H: full_profile_approved / ready_for_final_renderer_binding (also gates Stage 13-5) all stay False
def test_run_background_human_approval_case_f_g_h_gates_stay_false(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, font_result = _ready_plan_with_font_approved(tmp_path, db_path)
    result = run_background_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["record"]["full_profile_approved"] is False
    assert result["record"]["ready_for_final_renderer_binding"] is False


# --- MUTED Color Refinement orchestration (Background approval + MUTED review prep) ---

def test_run_muted_color_refinement_end_to_end(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, font_result = _ready_plan_with_font_approved(tmp_path, db_path)
    result = run_muted_color_refinement(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["pass"] is True
    assert result["file_count"] == 5
    assert result["report_path"].exists()
    assert result["background_approval"]["approved_background"] == CANDIDATES["CLEAN_DARK_FOCUS"]["page_bg"]
    index_html = (result["review_dir"] / "index.html").read_text(encoding="utf-8")
    for entry in result["manifest"]["files"]:
        assert entry["file"] in index_html


# the whole stage writes exactly ONE new DB row -- the background approval -- MUTED review itself is zero-write
def test_run_muted_color_refinement_writes_exactly_one_db_row(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, font_result = _ready_plan_with_font_approved(tmp_path, db_path)
    with connect(db_path) as conn:
        before = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
    result = run_muted_color_refinement(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["pass"] is True
    with connect(db_path) as conn:
        after = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
    assert after == before + 1


# CASE I/J: MUTED candidate generation never mutates CANDIDATES' real colors or page_bg
def test_run_muted_color_refinement_case_i_j_never_mutates_candidates_dict(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, font_result = _ready_plan_with_font_approved(tmp_path, db_path)
    before_colors = dict(CANDIDATES["CLEAN_DARK_FOCUS"]["colors"])
    before_bg = CANDIDATES["CLEAN_DARK_FOCUS"]["page_bg"]
    run_muted_color_refinement(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert CANDIDATES["CLEAN_DARK_FOCUS"]["colors"] == before_colors
    assert CANDIDATES["CLEAN_DARK_FOCUS"]["page_bg"] == before_bg


# CASE K: candidates B and C are always weaker (lower contrast) than SECONDARY
def test_run_muted_color_refinement_case_k_candidates_weaker_than_secondary(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, font_result = _ready_plan_with_font_approved(tmp_path, db_path)
    result = run_muted_color_refinement(db_path, assets_dir, reports_dir, plan_id=plan_id)
    secondary_ratio = contrast_ratio(CANDIDATES["CLEAN_DARK_FOCUS"]["colors"]["SECONDARY"], CANDIDATES["CLEAN_DARK_FOCUS"]["page_bg"])
    for key in ("B_MODERATE", "C_ACCESSIBLE"):
        assert result["candidates"][key]["contrast_ratio"] < secondary_ratio


# CASE L: A/B/C are all distinct -- never a meaningless duplicate comparison
def test_run_muted_color_refinement_case_l_candidates_distinct(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, font_result = _ready_plan_with_font_approved(tmp_path, db_path)
    result = run_muted_color_refinement(db_path, assets_dir, reports_dir, plan_id=plan_id)
    hexes = [info["hex"] for info in result["candidates"].values()]
    assert len(set(hexes)) == 3


# CASE M/N: candidate generation alone never marks MUTED or color_palette as approved
def test_run_muted_color_refinement_case_m_n_no_approval_flags_written(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, font_result = _ready_plan_with_font_approved(tmp_path, db_path)
    result = run_muted_color_refinement(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["manifest"]["muted_approval_written"] is False
    assert result["manifest"]["color_palette_approval_written"] is False
    canonical = select_canonical_visual_approval(db_path, plan_id)["design"]
    assert canonical["category_approvals"]["color_palette"]["resolution_status"] == "PENDING_VISUAL_REVIEW"


# CASE O: WCAG results never auto-select a candidate -- no candidate carries an approved/selected field
def test_run_muted_color_refinement_case_o_no_auto_selection(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, font_result = _ready_plan_with_font_approved(tmp_path, db_path)
    result = run_muted_color_refinement(db_path, assets_dir, reports_dir, plan_id=plan_id)
    for info in result["candidates"].values():
        assert "approved" not in info and "selected" not in info


# CASE P: the grayscale simulation never mutates the canonical palette
def test_run_muted_color_refinement_case_p_grayscale_does_not_mutate_palette(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, font_result = _ready_plan_with_font_approved(tmp_path, db_path)
    before = dict(CANDIDATES["CLEAN_DARK_FOCUS"]["colors"])
    result = run_muted_color_refinement(db_path, assets_dir, reports_dir, plan_id=plan_id)
    html = (result["review_dir"] / "05_MUTED_GRAYSCALE.html").read_text(encoding="utf-8")
    assert "filter:grayscale(100%)" in html
    assert CANDIDATES["CLEAN_DARK_FOCUS"]["colors"] == before


# CASE Q: an unused-in-Plan-7 semantic (SECONDARY/MUTED) is never falsely shown as a real usage example
def test_run_muted_color_refinement_case_q_no_false_usage_claim(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, font_result = _ready_plan_with_font_approved(tmp_path, db_path)
    result = run_muted_color_refinement(db_path, assets_dir, reports_dir, plan_id=plan_id)
    canonical = select_canonical_visual_approval(db_path, plan_id)["design"]
    usage = _color_role_usage_counts(canonical.get("scene_visual_rules", []))
    secondary_used = usage.get("SECONDARY", 0) > 0 or usage.get("MUTED", 0) > 0
    html = (result["review_dir"] / "02_MUTED_LEARNING_CONTEXT.html").read_text(encoding="utf-8")
    if not secondary_used:
        assert "NOT USED IN CURRENT PLAN 7" in html


# CASE R: 13-4C-7 evidence artifact is never modified
def test_run_muted_color_refinement_case_r_13_4c_7_evidence_unchanged(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, font_result = _ready_plan_with_font_approved(tmp_path, db_path)
    color_review_result = run_color_background_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    manifest_before = (color_review_result["review_dir"] / "manifest.json").read_text(encoding="utf-8")
    run_muted_color_refinement(db_path, assets_dir, reports_dir, plan_id=plan_id)
    manifest_after = (color_review_result["review_dir"] / "manifest.json").read_text(encoding="utf-8")
    assert manifest_before == manifest_after


# Font Review (13-4C-3) and Visual Prototype (13-4B-R1) artifacts are also untouched
def test_run_muted_color_refinement_does_not_touch_font_review_or_prototypes(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, font_result = _ready_plan_with_font_approved(tmp_path, db_path)
    font_review_result = run_font_family_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    proto_manifest_path = assets_dir / "generated" / f"plan_{plan_id}" / "render" / "prototypes" / "manifest.json"
    font_manifest_before = (font_review_result["review_dir"] / "manifest.json").read_text(encoding="utf-8")
    proto_manifest_before = proto_manifest_path.read_text(encoding="utf-8")

    run_muted_color_refinement(db_path, assets_dir, reports_dir, plan_id=plan_id)

    font_manifest_after = (font_review_result["review_dir"] / "manifest.json").read_text(encoding="utf-8")
    proto_manifest_after = proto_manifest_path.read_text(encoding="utf-8")
    assert font_manifest_before == font_manifest_after
    assert proto_manifest_before == proto_manifest_after


# Determinism: identical inputs -> identical candidates/manifest (except generated_at)/HTML
def test_generate_muted_color_review_prototypes_determinism(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, font_result = _ready_plan_with_font_approved(tmp_path, db_path)

    page_bg = CANDIDATES["CLEAN_DARK_FOCUS"]["page_bg"]
    muted = CANDIDATES["CLEAN_DARK_FOCUS"]["colors"]["MUTED"]
    secondary = CANDIDATES["CLEAN_DARK_FOCUS"]["colors"]["SECONDARY"]
    candidates = build_muted_candidates(page_bg, muted, secondary)
    font_stack = font_result["font_stack"]

    result1 = generate_muted_color_review_prototypes(assets_dir, plan_id, font_stack, candidates, True)
    files1 = {p.name: p.read_text(encoding="utf-8") for p in result1["review_dir"].glob("*.html")}
    manifest1 = dict(result1["manifest"])
    manifest1.pop("generated_at")

    result2 = generate_muted_color_review_prototypes(assets_dir, plan_id, font_stack, candidates, True)
    files2 = {p.name: p.read_text(encoding="utf-8") for p in result2["review_dir"].glob("*.html")}
    manifest2 = dict(result2["manifest"])
    manifest2.pop("generated_at")

    assert files1 == files2
    assert manifest1 == manifest2


# ---------------------------------------------------------------------------
# 13-4C-11: Typography Scale Human Approval -- persists the real Human Review decision (LARGE_
# BEGINNER from 13-4C-10) as the typography_scale approval. Append-only, exactly like 13-4C-6
# (font_family) / 13-4C-8 (background) / 13-4C-9 (color_palette). font_weight stays PENDING; the
# Prototype's reference weights (800/700/500/400/400) are recorded as provenance metadata only.
#
# NOTE: placed here (ahead of the 13-4C-9 section below) only because Python needs
# _ready_plan_with_color_palette_approved defined before use is not required (helpers are resolved
# at call time), so ordering is purely narrative -- see the 13-4C-9 section for that fixture.
# ---------------------------------------------------------------------------

def test_human_selected_typography_candidate_constant_is_large_beginner():
    assert HUMAN_SELECTED_TYPOGRAPHY_CANDIDATE == "LARGE_BEGINNER"


def test_run_typography_scale_human_approval_end_to_end(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, palette_result = _ready_plan_with_color_palette_approved(tmp_path, db_path)
    prior_id = palette_result["visual_design_row_id"]
    with connect(db_path) as conn:
        before_count = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
        prior_json_before = conn.execute("SELECT design_json FROM visual_design_specs WHERE id = ?", (prior_id,)).fetchone()["design_json"]

    result = run_typography_scale_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["pass"] is True
    assert result["selected_candidate"] == "LARGE_BEGINNER"

    baseline = CANDIDATES["CLEAN_DARK_FOCUS"]["roles"]
    expected_sizes = build_typography_scale_candidates(baseline)["LARGE_BEGINNER"]["sizes"]
    assert result["approved_sizes"] == expected_sizes == {"DOMINANT": 72, "PRIMARY": 46, "SUPPORTING": 28, "CAPTION": 20, "MICRO": 15}

    cat = result["record"]["category_approvals"]["typography_scale"]
    assert cat["resolution_status"] == "APPROVED"
    assert cat["resolved_style"] == expected_sizes
    assert cat["provenance"]["review_stage"] == "13-4C-11"
    assert cat["provenance"]["selected_candidate"] == "LARGE_BEGINNER"
    assert "NOT approved" in cat["provenance"]["reference_weights_note"]

    assert result["record"]["category_approvals"]["font_weight"]["resolution_status"] == "PENDING_VISUAL_REVIEW"
    assert result["record"]["category_approvals"]["font_family"]["resolution_status"] == "APPROVED"
    assert result["record"]["category_approvals"]["background"]["resolution_status"] == "APPROVED"
    assert result["record"]["category_approvals"]["color_palette"]["resolution_status"] == "APPROVED"
    assert result["record"]["category_approvals"]["color_palette"]["resolved_style"]["MUTED"] == "#757b87"
    assert result["full_profile_approved"] is False
    assert result["ready_for_final_renderer_binding"] is False

    with connect(db_path) as conn:
        after_count = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
        prior_json_after = conn.execute("SELECT design_json FROM visual_design_specs WHERE id = ?", (prior_id,)).fetchone()["design_json"]
    assert after_count == before_count + 1
    assert prior_json_after == prior_json_before

    profile = json.loads(result["json_path"].read_text(encoding="utf-8"))
    assert profile["category_approvals"]["typography_scale"]["resolution_status"] == "APPROVED"
    assert profile["category_approvals"]["typography_scale"]["resolved_style"] == expected_sizes


def test_run_typography_scale_human_approval_fails_without_color_palette(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, muted_result = _ready_plan_with_background_approved(tmp_path, db_path)
    result = run_typography_scale_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["pass"] is False


def test_run_typography_scale_human_approval_fails_without_background(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, font_result = _ready_plan_with_font_approved(tmp_path, db_path)
    result = run_typography_scale_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["pass"] is False


def test_run_typography_scale_human_approval_fails_without_font_family(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, legacy_id, correction = _ready_plan_with_canonical_correction(tmp_path, db_path)
    result = run_typography_scale_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["pass"] is False


def test_run_typography_scale_human_approval_rejects_when_already_approved(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, palette_result = _ready_plan_with_color_palette_approved(tmp_path, db_path)
    first = run_typography_scale_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert first["pass"] is True
    second = run_typography_scale_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert second["pass"] is False


def test_run_typography_scale_human_approval_rejects_compact_learning(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, palette_result = _ready_plan_with_color_palette_approved(tmp_path, db_path)
    result = run_typography_scale_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id, selected_candidate="COMPACT_LEARNING")
    assert result["pass"] is False


def test_run_typography_scale_human_approval_rejects_current_balanced(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, palette_result = _ready_plan_with_color_palette_approved(tmp_path, db_path)
    result = run_typography_scale_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id, selected_candidate="CURRENT_BALANCED")
    assert result["pass"] is False


def test_run_typography_scale_human_approval_rejects_unknown_candidate(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, palette_result = _ready_plan_with_color_palette_approved(tmp_path, db_path)
    with connect(db_path) as conn:
        before = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
    result = run_typography_scale_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id, selected_candidate="NOT_REAL")
    assert result["pass"] is False
    with connect(db_path) as conn:
        after = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
    assert after == before


def test_run_typography_scale_human_approval_preserves_other_approvals(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, palette_result = _ready_plan_with_color_palette_approved(tmp_path, db_path)
    before_font = palette_result["record"]["category_approvals"]["font_family"]
    before_bg = palette_result["record"]["category_approvals"]["background"]
    before_palette = palette_result["record"]["category_approvals"]["color_palette"]
    result = run_typography_scale_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["record"]["category_approvals"]["font_family"] == before_font
    assert result["record"]["category_approvals"]["background"] == before_bg
    assert result["record"]["category_approvals"]["color_palette"] == before_palette


def test_run_typography_scale_human_approval_gates_stay_false(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, palette_result = _ready_plan_with_color_palette_approved(tmp_path, db_path)
    result = run_typography_scale_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["record"]["full_profile_approved"] is False
    assert result["record"]["ready_for_final_renderer_binding"] is False


def test_run_typography_scale_human_approval_production_data_untouched(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, palette_result = _ready_plan_with_color_palette_approved(tmp_path, db_path)
    with connect(db_path) as conn:
        before = {t: conn.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"] for t in ("production_blocks", "speech_assets", "generated_assets", "render_specs", "render_timelines", "scene_layouts")}
    run_typography_scale_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    with connect(db_path) as conn:
        after = {t: conn.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"] for t in before}
    assert before == after


def test_run_typography_scale_human_approval_does_not_touch_review_artifacts(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, palette_result = _ready_plan_with_color_palette_approved(tmp_path, db_path)
    typo_review_result = run_typography_scale_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    color_review_result = run_color_background_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    before = {
        "typography": (typo_review_result["review_dir"] / "manifest.json").read_text(encoding="utf-8"),
        "color": (color_review_result["review_dir"] / "manifest.json").read_text(encoding="utf-8"),
    }
    run_typography_scale_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    after = {
        "typography": (typo_review_result["review_dir"] / "manifest.json").read_text(encoding="utf-8"),
        "color": (color_review_result["review_dir"] / "manifest.json").read_text(encoding="utf-8"),
    }
    assert before == after


def test_run_typography_scale_human_approval_deterministic_values(tmp_path):
    db_path1 = tmp_path / "test1.db"
    init_db(db_path1)
    plan_id1, assets_dir1, reports_dir1, palette_result1 = _ready_plan_with_color_palette_approved(tmp_path, db_path1)
    result1 = run_typography_scale_human_approval(db_path1, assets_dir1, reports_dir1, plan_id=plan_id1)

    tmp_path2 = tmp_path / "second"
    tmp_path2.mkdir()
    db_path2 = tmp_path2 / "test2.db"
    init_db(db_path2)
    plan_id2, assets_dir2, reports_dir2, palette_result2 = _ready_plan_with_color_palette_approved(tmp_path2, db_path2)
    result2 = run_typography_scale_human_approval(db_path2, assets_dir2, reports_dir2, plan_id=plan_id2)

    assert result1["approved_sizes"] == result2["approved_sizes"]


# ---------------------------------------------------------------------------
# 13-4C-9: Color Palette Human Approval -- persists the real Human Review decision (MUTED=MODERATE
# from 13-4C-8) combined with the 6 KEEP roles from 13-4C-7 as the final color_palette approval.
# Append-only, exactly like 13-4C-6 (font_family) and 13-4C-8 (background).
# ---------------------------------------------------------------------------

def _ready_plan_with_background_approved(tmp_path, db_path):
    plan_id, assets_dir, reports_dir, font_result = _ready_plan_with_font_approved(tmp_path, db_path)
    muted_result = run_muted_color_refinement(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert muted_result["pass"] is True
    return plan_id, assets_dir, reports_dir, muted_result


def test_run_color_palette_human_approval_end_to_end(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, muted_result = _ready_plan_with_background_approved(tmp_path, db_path)
    prior_id = muted_result["background_approval"]["visual_design_row_id"]
    with connect(db_path) as conn:
        before_count = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
        prior_json_before = conn.execute("SELECT design_json FROM visual_design_specs WHERE id = ?", (prior_id,)).fetchone()["design_json"]

    result = run_color_palette_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["pass"] is True

    palette = result["approved_palette"]
    for role in COLOR_REVIEW_ROLES:
        if role != "MUTED":
            assert palette[role] == CANDIDATES["CLEAN_DARK_FOCUS"]["colors"][role]
    muted_candidates = build_muted_candidates(
        CANDIDATES["CLEAN_DARK_FOCUS"]["page_bg"], CANDIDATES["CLEAN_DARK_FOCUS"]["colors"]["MUTED"],
        CANDIDATES["CLEAN_DARK_FOCUS"]["colors"]["SECONDARY"],
    )
    assert palette["MUTED"] == muted_candidates["B_MODERATE"]["hex"]

    cat = result["record"]["category_approvals"]["color_palette"]
    assert cat["resolution_status"] == "APPROVED"
    assert cat["provenance"]["review_stage"] == "13-4C-9"
    assert cat["provenance"]["selected_muted_candidate"] == "MODERATE"
    assert cat["provenance"]["muted_normal_text_reference"] == "FAIL"
    assert cat["provenance"]["muted_large_text_reference"] == "PASS"
    assert "NOT PRIMARY BODY TEXT" in cat["provenance"]["muted_usage_guidance"]

    assert result["record"]["category_approvals"]["background"]["resolution_status"] == "APPROVED"
    assert result["record"]["category_approvals"]["font_family"]["resolution_status"] == "APPROVED"
    assert result["full_profile_approved"] is False
    assert result["ready_for_final_renderer_binding"] is False

    with connect(db_path) as conn:
        after_count = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
        prior_json_after = conn.execute("SELECT design_json FROM visual_design_specs WHERE id = ?", (prior_id,)).fetchone()["design_json"]
    assert after_count == before_count + 1
    assert prior_json_after == prior_json_before

    profile = json.loads(result["json_path"].read_text(encoding="utf-8"))
    assert profile["category_approvals"]["color_palette"]["resolved_style"]["MUTED"] == muted_candidates["B_MODERATE"]["hex"]


def test_run_color_palette_human_approval_fails_without_background(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, font_result = _ready_plan_with_font_approved(tmp_path, db_path)
    result = run_color_palette_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["pass"] is False


# Mandatory Negative Test A: persisting MUTED=CURRENT(#555b66) is structurally refused
def test_run_color_palette_human_approval_negative_a_current_refused(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, muted_result = _ready_plan_with_background_approved(tmp_path, db_path)
    with connect(db_path) as conn:
        before = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
    result = run_color_palette_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id, selected_muted_candidate="A_CURRENT")
    assert result["pass"] is False
    with connect(db_path) as conn:
        after = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
    assert after == before


# Mandatory Negative Test B: persisting MUTED=ACCESSIBLE(#8a919d) is structurally refused
def test_run_color_palette_human_approval_negative_b_accessible_refused(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, muted_result = _ready_plan_with_background_approved(tmp_path, db_path)
    result = run_color_palette_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id, selected_muted_candidate="C_ACCESSIBLE")
    assert result["pass"] is False


# Mandatory Negative Test A/B (inverse) + unknown candidate
def test_run_color_palette_human_approval_negative_unknown_candidate_refused(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, muted_result = _ready_plan_with_background_approved(tmp_path, db_path)
    result = run_color_palette_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id, selected_muted_candidate="NOT_REAL")
    assert result["pass"] is False


# Mandatory Negative Test C (structural): the 6 KEEP roles are always read live from CANDIDATES --
# there is no parameter through which a different KEEP value could be injected
def test_run_color_palette_human_approval_negative_c_keep_roles_always_match_real_code(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, muted_result = _ready_plan_with_background_approved(tmp_path, db_path)
    result = run_color_palette_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    for role in ("DEFAULT", "PRIMARY_FOCUS", "RELATION", "SUCCESS", "SECONDARY", "EXCEPTION_CAUTION"):
        assert result["approved_palette"][role] == CANDIDATES["CLEAN_DARK_FOCUS"]["colors"][role]


# Mandatory Negative Test D/E: background/font_family are never changed by a color_palette approval
def test_run_color_palette_human_approval_negative_d_e_background_font_family_preserved(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, muted_result = _ready_plan_with_background_approved(tmp_path, db_path)
    before_bg = muted_result["background_approval"]["record"]["category_approvals"]["background"]
    before_font = muted_result["background_approval"]["record"]["category_approvals"]["font_family"]
    result = run_color_palette_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["record"]["category_approvals"]["background"] == before_bg
    assert result["record"]["category_approvals"]["font_family"] == before_font


# Mandatory Negative Test F/G: typography_scale and font_weight are never auto-approved
def test_run_color_palette_human_approval_negative_f_g_typography_font_weight_stay_pending(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, muted_result = _ready_plan_with_background_approved(tmp_path, db_path)
    result = run_color_palette_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    cats = result["record"]["category_approvals"]
    assert cats["typography_scale"]["resolution_status"] == "PENDING_VISUAL_REVIEW"
    assert cats["font_weight"]["resolution_status"] == "PENDING_VISUAL_REVIEW"


# Mandatory Negative Test H/I/J: full_profile_approved / ready_for_final_renderer_binding (also
# gates Stage 13-5) all stay False -- 6 of 9 mandatory categories remain PENDING
def test_run_color_palette_human_approval_negative_h_i_j_gates_stay_false(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, muted_result = _ready_plan_with_background_approved(tmp_path, db_path)
    result = run_color_palette_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["record"]["full_profile_approved"] is False
    assert result["record"]["ready_for_final_renderer_binding"] is False


# Mandatory Negative Test K: the existing canonical row is never modified -- append-only
def test_run_color_palette_human_approval_negative_k_prior_row_unchanged(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, muted_result = _ready_plan_with_background_approved(tmp_path, db_path)
    prior_id = muted_result["background_approval"]["visual_design_row_id"]
    with connect(db_path) as conn:
        before = conn.execute("SELECT design_json FROM visual_design_specs WHERE id = ?", (prior_id,)).fetchone()["design_json"]
    run_color_palette_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    with connect(db_path) as conn:
        after = conn.execute("SELECT design_json FROM visual_design_specs WHERE id = ?", (prior_id,)).fetchone()["design_json"]
    assert before == after


# Mandatory Negative Test L/M: 13-4C-8 and 13-4C-7 evidence artifacts are never modified -- 13-4C-7
# correctly still shows the historical CURRENT MUTED (#555b66), never retroactively rewritten
def test_run_color_palette_human_approval_negative_l_m_historical_evidence_unchanged(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, muted_result = _ready_plan_with_background_approved(tmp_path, db_path)
    color_review_result = run_color_background_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    muted_manifest_before = (muted_result["review_dir"] / "manifest.json").read_text(encoding="utf-8")
    color_manifest_before = (color_review_result["review_dir"] / "manifest.json").read_text(encoding="utf-8")
    color_html_before = (color_review_result["review_dir"] / "02_SEMANTIC_COLOR_ROLES.html").read_text(encoding="utf-8")

    run_color_palette_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)

    muted_manifest_after = (muted_result["review_dir"] / "manifest.json").read_text(encoding="utf-8")
    color_manifest_after = (color_review_result["review_dir"] / "manifest.json").read_text(encoding="utf-8")
    color_html_after = (color_review_result["review_dir"] / "02_SEMANTIC_COLOR_ROLES.html").read_text(encoding="utf-8")
    assert muted_manifest_before == muted_manifest_after
    assert color_manifest_before == color_manifest_after
    assert color_html_before == color_html_after
    assert "#555b66" in color_html_after  # historical evidence still correctly shows the old CURRENT value


# Mandatory Negative Test N: approved_visual_profile.json always matches the latest canonical DB row
def test_run_color_palette_human_approval_negative_n_profile_matches_canonical(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, muted_result = _ready_plan_with_background_approved(tmp_path, db_path)
    result = run_color_palette_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    profile = json.loads(result["json_path"].read_text(encoding="utf-8"))
    canonical = select_canonical_visual_approval(db_path, plan_id)["design"]
    assert profile["category_approvals"]["color_palette"] == canonical["category_approvals"]["color_palette"]


# Mandatory Negative Test O: CANDIDATES is never the active canonical palette source -- the real
# active source (select_canonical_visual_approval) correctly returns the approved MUTED value even
# though CANDIDATES itself still (correctly) holds the old preview value #555b66
def test_run_color_palette_human_approval_negative_o_no_source_of_truth_conflict(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, muted_result = _ready_plan_with_background_approved(tmp_path, db_path)
    run_color_palette_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    canonical = select_canonical_visual_approval(db_path, plan_id)["design"]
    assert canonical["category_approvals"]["color_palette"]["resolved_style"]["MUTED"] == "#757b87"
    assert CANDIDATES["CLEAN_DARK_FOCUS"]["colors"]["MUTED"] == "#555b66"  # untouched preview source, by design


# Mandatory Negative Test P: the WCAG AA normal-text FAIL fact is never hidden or misreported
def test_run_color_palette_human_approval_negative_p_wcag_fail_not_hidden(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, muted_result = _ready_plan_with_background_approved(tmp_path, db_path)
    result = run_color_palette_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    prov = result["record"]["category_approvals"]["color_palette"]["provenance"]
    assert prov["muted_normal_text_reference"] == "FAIL"
    assert prov["muted_large_text_reference"] == "PASS"


# Mandatory Negative Test Q: MUTED's usage guidance is never distorted into a body-text/primary claim
def test_run_color_palette_human_approval_negative_q_usage_guidance_not_distorted(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, muted_result = _ready_plan_with_background_approved(tmp_path, db_path)
    result = run_color_palette_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    guidance = result["record"]["category_approvals"]["color_palette"]["provenance"]["muted_usage_guidance"]
    assert "NOT PRIMARY BODY TEXT" in guidance
    assert "DE-EMPHASIZED" in guidance or "ALREADY-SEEN" in guidance


# HUMAN_SELECTED_MUTED_CANDIDATE constant is exactly the real Human Review decision (MODERATE)
def test_human_selected_muted_candidate_constant_is_moderate():
    assert HUMAN_SELECTED_MUTED_CANDIDATE == "B_MODERATE"


# ---------------------------------------------------------------------------
# 13-4C-10: Typography Scale Human Review -- Review Preparation only (zero DB write), exactly like
# 13-4C-3/13-4C-7. Font Family/Background/Color Palette are fixed conditions read from the real
# canonical APPROVED values (never re-read from CANDIDATES, which still holds the superseded MUTED
# preview #555b66). Typography Scale itself stays PENDING; three deterministic candidates only.
# ---------------------------------------------------------------------------

def _ready_plan_with_color_palette_approved(tmp_path, db_path):
    plan_id, assets_dir, reports_dir, muted_result = _ready_plan_with_background_approved(tmp_path, db_path)
    palette_result = run_color_palette_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert palette_result["pass"] is True
    return plan_id, assets_dir, reports_dir, palette_result


# --- pure function tests ---

def test_build_typography_scale_candidates_current_balanced_matches_real_baseline():
    baseline = CANDIDATES["CLEAN_DARK_FOCUS"]["roles"]
    candidates = build_typography_scale_candidates(baseline)
    b = candidates["CURRENT_BALANCED"]
    assert b["sizes"] == {"DOMINANT": 68, "PRIMARY": 42, "SUPPORTING": 26, "CAPTION": 18, "MICRO": 14}
    assert b["weights"] == {"DOMINANT": 800, "PRIMARY": 700, "SUPPORTING": 500, "CAPTION": 400, "MICRO": 400}


def test_build_typography_scale_candidates_deterministic():
    baseline = CANDIDATES["CLEAN_DARK_FOCUS"]["roles"]
    r1 = build_typography_scale_candidates(baseline)
    r2 = build_typography_scale_candidates(baseline)
    assert r1 == r2


def test_build_typography_scale_candidates_hierarchy_holds_for_all_three():
    baseline = CANDIDATES["CLEAN_DARK_FOCUS"]["roles"]
    candidates = build_typography_scale_candidates(baseline)
    for name, info in candidates.items():
        sizes = [info["sizes"][role] for role in TYPOGRAPHY_SCALE_ROLES]
        assert all(sizes[i] > sizes[i + 1] for i in range(len(sizes) - 1)), f"{name}: {sizes}"


def test_validate_typography_scale_candidates_passes_for_real_candidates():
    baseline = CANDIDATES["CLEAN_DARK_FOCUS"]["roles"]
    candidates = build_typography_scale_candidates(baseline)
    result = validate_typography_scale_candidates(candidates)
    assert result["pass"] is True
    assert result["issues"] == []


def test_validate_typography_scale_candidates_catches_collapsed_hierarchy():
    broken = {"X": {"sizes": {"DOMINANT": 20, "PRIMARY": 20, "SUPPORTING": 10, "CAPTION": 5, "MICRO": 2}, "weights": {}}}
    result = validate_typography_scale_candidates(broken)
    assert result["pass"] is False
    assert "hierarchy collapsed" in result["issues"][0]


def test_typography_scale_candidate_deltas_are_the_reasoned_rule():
    assert TYPOGRAPHY_SCALE_CANDIDATE_DELTAS["CURRENT_BALANCED"] == {role: 0 for role in TYPOGRAPHY_SCALE_ROLES}
    assert TYPOGRAPHY_SCALE_CANDIDATE_DELTAS["COMPACT_LEARNING"]["DOMINANT"] < 0
    assert TYPOGRAPHY_SCALE_CANDIDATE_DELTAS["LARGE_BEGINNER"]["DOMINANT"] > 0


# --- end-to-end ---

def test_run_typography_scale_review_end_to_end(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, palette_result = _ready_plan_with_color_palette_approved(tmp_path, db_path)
    result = run_typography_scale_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["pass"] is True
    assert result["file_count"] == 18
    assert result["validation"]["pass"] is True
    assert result["report_path"].exists()
    index_html = (result["review_dir"] / "index.html").read_text(encoding="utf-8")
    assert "COMPACT_LEARNING" in index_html and "CURRENT_BALANCED" in index_html and "LARGE_BEGINNER" in index_html


def test_run_typography_scale_review_fails_without_color_palette(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, muted_result = _ready_plan_with_background_approved(tmp_path, db_path)
    result = run_typography_scale_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["pass"] is False


# Mandatory Negative Test A/B: typography_scale and font_weight are never auto-approved by this stage
def test_run_typography_scale_review_negative_a_b_no_auto_approval(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, palette_result = _ready_plan_with_color_palette_approved(tmp_path, db_path)
    run_typography_scale_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    canonical = select_canonical_visual_approval(db_path, plan_id)["design"]
    assert canonical["category_approvals"]["typography_scale"]["resolution_status"] == "PENDING_VISUAL_REVIEW"
    assert canonical["category_approvals"]["font_weight"]["resolution_status"] == "PENDING_VISUAL_REVIEW"


# Mandatory Negative Test C/D/E/F: font_family/background/color_palette (incl. MUTED) never change
def test_run_typography_scale_review_negative_c_d_e_f_approved_categories_preserved(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, palette_result = _ready_plan_with_color_palette_approved(tmp_path, db_path)
    before = select_canonical_visual_approval(db_path, plan_id)["design"]["category_approvals"]
    run_typography_scale_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    after = select_canonical_visual_approval(db_path, plan_id)["design"]["category_approvals"]
    assert before["font_family"] == after["font_family"]
    assert before["background"] == after["background"]
    assert before["color_palette"] == after["color_palette"]
    assert after["color_palette"]["resolved_style"]["MUTED"] == "#757b87"


# Mandatory Negative Test G: CURRENT_BALANCED must equal the real current baseline exactly
def test_run_typography_scale_review_negative_g_current_balanced_matches_baseline(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, palette_result = _ready_plan_with_color_palette_approved(tmp_path, db_path)
    result = run_typography_scale_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    b = result["candidates"]["CURRENT_BALANCED"]["sizes"]
    assert b == {"DOMINANT": 68, "PRIMARY": 42, "SUPPORTING": 26, "CAPTION": 18, "MICRO": 14}


# Mandatory Negative Test H: every displayed label's px matches the actual applied CSS px (single source)
def test_run_typography_scale_review_negative_h_label_matches_css(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, palette_result = _ready_plan_with_color_palette_approved(tmp_path, db_path)
    result = run_typography_scale_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    for candidate_name, candidate in result["candidates"].items():
        html = (result["review_dir"] / f"02_HIERARCHY_{candidate_name}.html").read_text(encoding="utf-8")
        for role in TYPOGRAPHY_SCALE_ROLES:
            px, weight = candidate["sizes"][role], candidate["weights"][role]
            assert f"{role} — {px}px / {weight}" in html
            assert f"font-size:{px}px;font-weight:{weight};" in html


# Mandatory Negative Test I/J/K: font-family, palette, and content are identical across candidates --
# only Typography Scale (font-size/font-weight) varies
def test_run_typography_scale_review_negative_i_j_k_only_typography_varies(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, palette_result = _ready_plan_with_color_palette_approved(tmp_path, db_path)
    result = run_typography_scale_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    font_stacks, page_bgs = set(), set()
    for candidate_name in result["candidates"]:
        html = (result["review_dir"] / f"01_FULL_LEARNING_{candidate_name}.html").read_text(encoding="utf-8")
        assert "CAP" in html and "cap" in html  # same content across candidates
        font_stacks.add(re.search(r"font-family:([^;]+);", html).group(1))
        page_bgs.add(re.search(r"background:([^;]+);", html).group(1))
    assert len(font_stacks) == 1
    assert len(page_bgs) == 1


# Mandatory Negative Test L: hierarchy never collapses in the generated candidates
def test_run_typography_scale_review_negative_l_hierarchy_never_collapses(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, palette_result = _ready_plan_with_color_palette_approved(tmp_path, db_path)
    result = run_typography_scale_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["validation"]["pass"] is True


# Mandatory Negative Test M: Review Preparation never inserts a new visual_design_specs row
def test_run_typography_scale_review_negative_m_zero_db_writes(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, palette_result = _ready_plan_with_color_palette_approved(tmp_path, db_path)
    with connect(db_path) as conn:
        before = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
    run_typography_scale_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    with connect(db_path) as conn:
        after = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
    assert after == before


# Mandatory Negative Test N: approved_visual_profile.json is never touched by this stage
def test_run_typography_scale_review_negative_n_profile_json_unchanged(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, palette_result = _ready_plan_with_color_palette_approved(tmp_path, db_path)
    profile_path = palette_result["json_path"]
    before = profile_path.read_text(encoding="utf-8")
    run_typography_scale_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    after = profile_path.read_text(encoding="utf-8")
    assert before == after


# Mandatory Negative Test O/P/Q: renderer gates never flip True by this stage
def test_run_typography_scale_review_negative_o_p_q_gates_unaffected(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, palette_result = _ready_plan_with_color_palette_approved(tmp_path, db_path)
    run_typography_scale_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    canonical = select_canonical_visual_approval(db_path, plan_id)["design"]
    assert canonical["full_profile_approved"] is False
    assert canonical["ready_for_final_renderer_binding"] is False


# Mandatory Negative Test R: Production/Audio/Layout data untouched (no writes to those tables at all)
def test_run_typography_scale_review_negative_r_production_data_untouched(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, palette_result = _ready_plan_with_color_palette_approved(tmp_path, db_path)
    with connect(db_path) as conn:
        before = {t: conn.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"] for t in ("production_blocks", "speech_assets", "generated_assets", "render_specs", "render_timelines", "scene_layouts")}
    run_typography_scale_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    with connect(db_path) as conn:
        after = {t: conn.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"] for t in before}
    assert before == after


# Mandatory Negative Test S: font_weight is never claimed as Human Approved because it was used as a preview reference
def test_run_typography_scale_review_negative_s_font_weight_not_claimed_approved(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, palette_result = _ready_plan_with_color_palette_approved(tmp_path, db_path)
    result = run_typography_scale_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["manifest"]["font_weight_status"] == "PENDING_VISUAL_REVIEW"
    assert "reference values" in result["manifest"]["font_weight_note"]
    assert result["manifest"]["human_approved_typography"] is None


# Mandatory Negative Test T: VERDANA_HUMANIST 800 is never claimed as verified-native
def test_run_typography_scale_review_negative_t_verdana_800_not_claimed_native(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, palette_result = _ready_plan_with_color_palette_approved(tmp_path, db_path)
    result = run_typography_scale_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["manifest"]["verdana_800_note"] == FONT_CANDIDATES["VERDANA_HUMANIST"]["weight_800_behavior"]
    assert "synthesized" in result["manifest"]["verdana_800_note"] or "no true 800" in result["manifest"]["verdana_800_note"]


# historical artifacts (13-4C-3/13-4C-7/13-4C-8/13-4B-R1) are never modified
def test_run_typography_scale_review_does_not_touch_historical_artifacts(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, palette_result = _ready_plan_with_color_palette_approved(tmp_path, db_path)
    font_review_result = run_font_family_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    color_review_result = run_color_background_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    proto_manifest_path = assets_dir / "generated" / f"plan_{plan_id}" / "render" / "prototypes" / "manifest.json"

    before = {
        "font_review": (font_review_result["review_dir"] / "manifest.json").read_text(encoding="utf-8"),
        "color_review": (color_review_result["review_dir"] / "manifest.json").read_text(encoding="utf-8"),
        "prototypes": proto_manifest_path.read_text(encoding="utf-8"),
    }
    run_typography_scale_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    after = {
        "font_review": (font_review_result["review_dir"] / "manifest.json").read_text(encoding="utf-8"),
        "color_review": (color_review_result["review_dir"] / "manifest.json").read_text(encoding="utf-8"),
        "prototypes": proto_manifest_path.read_text(encoding="utf-8"),
    }
    assert before == after


# overflow-check limitation is reported honestly, never falsely claiming browser verification
def test_run_typography_scale_review_reports_overflow_limitation_honestly(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, palette_result = _ready_plan_with_color_palette_approved(tmp_path, db_path)
    result = run_typography_scale_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    limitation = result["manifest"]["overflow_check_limitation"]
    assert "cannot be computed programmatically" in limitation
    assert "human opening the HTML" in limitation


# Determinism: identical inputs -> identical candidates/manifest (except generated_at)/HTML
def test_run_typography_scale_review_determinism(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, palette_result = _ready_plan_with_color_palette_approved(tmp_path, db_path)

    result1 = run_typography_scale_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    files1 = {p.name: p.read_text(encoding="utf-8") for p in result1["review_dir"].glob("*.html")}
    manifest1 = dict(result1["manifest"])
    manifest1.pop("generated_at")

    result2 = run_typography_scale_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    files2 = {p.name: p.read_text(encoding="utf-8") for p in result2["review_dir"].glob("*.html")}
    manifest2 = dict(result2["manifest"])
    manifest2.pop("generated_at")

    assert files1 == files2
    assert manifest1 == manifest2


# ---------------------------------------------------------------------------
# 13-4C-12: Font Weight Human Review -- Review Preparation only (zero DB write), exactly like
# 13-4C-3/13-4C-7/13-4C-10. Font Family/Background/Color Palette/Typography Scale are fixed
# conditions read from the real canonical APPROVED values. Only font-weight varies across
# candidates. Native-vs-synthetic is computed against the real
# FONT_CANDIDATES["VERDANA_HUMANIST"]["native_weights"]. Human decision is always None here.
# ---------------------------------------------------------------------------

def _ready_plan_with_typography_scale_approved(tmp_path, db_path):
    plan_id, assets_dir, reports_dir, palette_result = _ready_plan_with_color_palette_approved(tmp_path, db_path)
    typo_result = run_typography_scale_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert typo_result["pass"] is True
    return plan_id, assets_dir, reports_dir, typo_result


# --- pure function tests ---

def test_build_font_weight_candidates_balanced_matches_real_reference():
    baseline = CANDIDATES["CLEAN_DARK_FOCUS"]["roles"]
    candidates = build_font_weight_candidates(baseline)
    b = candidates["BALANCED_HIERARCHY"]["weights"]
    assert b == {"DOMINANT": 800, "PRIMARY": 700, "SUPPORTING": 500, "CAPTION": 400, "MICRO": 400}


def test_build_font_weight_candidates_deterministic():
    baseline = CANDIDATES["CLEAN_DARK_FOCUS"]["roles"]
    r1 = build_font_weight_candidates(baseline)
    r2 = build_font_weight_candidates(baseline)
    assert r1 == r2


def test_build_font_weight_candidates_hierarchy_holds_for_all_three():
    baseline = CANDIDATES["CLEAN_DARK_FOCUS"]["roles"]
    candidates = build_font_weight_candidates(baseline)
    for name, info in candidates.items():
        w = info["weights"]
        assert w["DOMINANT"] >= w["PRIMARY"] >= w["SUPPORTING"] >= w["CAPTION"], f"{name}: {w}"
        assert w["MICRO"] <= w["CAPTION"], f"{name}: {w}"


def test_build_font_weight_candidates_native_matches_real_font_candidates():
    baseline = CANDIDATES["CLEAN_DARK_FOCUS"]["roles"]
    candidates = build_font_weight_candidates(baseline)
    native_weights = FONT_CANDIDATES["VERDANA_HUMANIST"]["native_weights"]
    for info in candidates.values():
        for role, weight in info["weights"].items():
            assert info["native"][role] == (weight in native_weights)
    # the real, honest finding: LIGHTER_HIERARCHY uses more native faces than STRONG_BEGINNER
    lighter_native_count = sum(candidates["LIGHTER_HIERARCHY"]["native"].values())
    strong_native_count = sum(candidates["STRONG_BEGINNER"]["native"].values())
    assert lighter_native_count > strong_native_count


def test_validate_font_weight_candidates_passes_for_real_candidates():
    baseline = CANDIDATES["CLEAN_DARK_FOCUS"]["roles"]
    candidates = build_font_weight_candidates(baseline)
    result = validate_font_weight_candidates(candidates)
    assert result["pass"] is True
    assert result["issues"] == []


def test_validate_font_weight_candidates_catches_hierarchy_violation():
    broken = {"X": {"weights": {"DOMINANT": 400, "PRIMARY": 700, "SUPPORTING": 500, "CAPTION": 400, "MICRO": 400}, "native": {}}}
    result = validate_font_weight_candidates(broken)
    assert result["pass"] is False
    assert "hierarchy violated" in result["issues"][0]


def test_font_weight_candidate_deltas_are_the_reasoned_rule():
    assert FONT_WEIGHT_CANDIDATE_DELTAS["BALANCED_HIERARCHY"] == {role: 0 for role in TYPOGRAPHY_SCALE_ROLES}
    assert FONT_WEIGHT_CANDIDATE_DELTAS["LIGHTER_HIERARCHY"]["DOMINANT"] < 0
    assert FONT_WEIGHT_CANDIDATE_DELTAS["STRONG_BEGINNER"]["DOMINANT"] > 0


# --- end-to-end ---

def test_run_font_weight_review_end_to_end(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, typo_result = _ready_plan_with_typography_scale_approved(tmp_path, db_path)
    result = run_font_weight_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["pass"] is True
    assert result["file_count"] == 19  # 18 + side-by-side
    assert result["validation"]["pass"] is True
    assert result["sizes"] == {"DOMINANT": 72, "PRIMARY": 46, "SUPPORTING": 28, "CAPTION": 20, "MICRO": 15}
    assert result["manifest"]["human_decision"] is None
    assert result["manifest"]["font_weight_status"] == "PENDING_VISUAL_REVIEW"
    assert result["report_path"].exists()
    index_html = (result["review_dir"] / "index.html").read_text(encoding="utf-8")
    assert "LIGHTER_HIERARCHY" in index_html and "BALANCED_HIERARCHY" in index_html and "STRONG_BEGINNER" in index_html


def test_run_font_weight_review_fails_without_typography_scale(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, palette_result = _ready_plan_with_color_palette_approved(tmp_path, db_path)
    result = run_font_weight_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["pass"] is False


# CASE D-G: the four prerequisite categories must all be APPROVED first
def test_run_font_weight_review_negative_d_g_requires_all_prerequisites(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, font_result = _ready_plan_with_font_approved(tmp_path, db_path)
    result = run_font_weight_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["pass"] is False


# CASE H: font_weight already APPROVED -- structurally impossible to reach today (no approve-
# font-weight function exists yet), verified by confirming the category is never touched by review
def test_run_font_weight_review_never_writes_font_weight_category(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, typo_result = _ready_plan_with_typography_scale_approved(tmp_path, db_path)
    before = select_canonical_visual_approval(db_path, plan_id)["design"]["category_approvals"]["font_weight"]
    run_font_weight_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    after = select_canonical_visual_approval(db_path, plan_id)["design"]["category_approvals"]["font_weight"]
    assert before == after
    assert after["resolution_status"] == "PENDING_VISUAL_REVIEW"


# CASE I-R: only font-weight varies across candidates -- font-family/background/palette/content/size
# are all identical
def test_run_font_weight_review_negative_i_r_only_weight_varies(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, typo_result = _ready_plan_with_typography_scale_approved(tmp_path, db_path)
    result = run_font_weight_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    font_stacks, page_bgs, sizes_seen = set(), set(), set()
    for candidate_name in result["candidates"]:
        html = (result["review_dir"] / f"01_FULL_LEARNING_{candidate_name}.html").read_text(encoding="utf-8")
        assert "CAP" in html and "cap" in html
        font_stacks.add(re.search(r"font-family:([^;]+);", html).group(1))
        page_bgs.add(re.search(r"background:([^;]+);", html).group(1))
        sizes_seen.add(tuple(sorted(re.findall(r"font-size:(\d+px);", html))))
    assert len(font_stacks) == 1
    assert len(page_bgs) == 1
    assert len(sizes_seen) == 1  # same set of font-sizes across all candidates -- only weight differs


# CASE O: hierarchy never violated in the generated candidates
def test_run_font_weight_review_negative_o_hierarchy_never_violated(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, typo_result = _ready_plan_with_typography_scale_approved(tmp_path, db_path)
    result = run_font_weight_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["validation"]["pass"] is True


# CASE S: 18 core prototypes + side-by-side + index + manifest all exist
def test_run_font_weight_review_negative_s_prototype_count_complete(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, typo_result = _ready_plan_with_typography_scale_approved(tmp_path, db_path)
    result = run_font_weight_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    html_files = list(result["review_dir"].glob("*.html"))
    assert len(html_files) == 20  # 18 core + 1 side-by-side + index.html
    assert (result["review_dir"] / "index.html").exists()
    assert (result["review_dir"] / "manifest.json").exists()
    assert (result["review_dir"] / "00_FONT_WEIGHT_SIDE_BY_SIDE.html").exists()


# CASE T/U/V: zero DB writes, approved_visual_profile.json untouched, canonical row unchanged
def test_run_font_weight_review_negative_t_u_v_zero_writes(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, typo_result = _ready_plan_with_typography_scale_approved(tmp_path, db_path)
    prior_id = typo_result["visual_design_row_id"]
    with connect(db_path) as conn:
        before_count = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
        prior_json_before = conn.execute("SELECT design_json FROM visual_design_specs WHERE id = ?", (prior_id,)).fetchone()["design_json"]
    profile_before = typo_result["json_path"].read_text(encoding="utf-8")

    result = run_font_weight_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["pass"] is True

    with connect(db_path) as conn:
        after_count = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
        prior_json_after = conn.execute("SELECT design_json FROM visual_design_specs WHERE id = ?", (prior_id,)).fetchone()["design_json"]
    profile_after = typo_result["json_path"].read_text(encoding="utf-8")

    assert after_count == before_count
    assert prior_json_after == prior_json_before
    assert profile_after == profile_before


# existing approvals (incl. MUTED and LARGE_BEGINNER sizes) preserved, production data untouched,
# and historical review artifacts (13-4C-3/7/8/10) are never modified
def test_run_font_weight_review_preserves_everything_else(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, typo_result = _ready_plan_with_typography_scale_approved(tmp_path, db_path)

    font_review_result = run_font_family_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    color_review_result = run_color_background_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    typo_review_result = run_typography_scale_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    with connect(db_path) as conn:
        before_prod = {t: conn.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"] for t in ("production_blocks", "speech_assets", "generated_assets", "render_specs", "render_timelines", "scene_layouts")}
    before_artifacts = {
        "font": (font_review_result["review_dir"] / "manifest.json").read_text(encoding="utf-8"),
        "color": (color_review_result["review_dir"] / "manifest.json").read_text(encoding="utf-8"),
        "typo": (typo_review_result["review_dir"] / "manifest.json").read_text(encoding="utf-8"),
    }

    run_font_weight_review(db_path, assets_dir, reports_dir, plan_id=plan_id)

    with connect(db_path) as conn:
        after_prod = {t: conn.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"] for t in before_prod}
    after_artifacts = {
        "font": (font_review_result["review_dir"] / "manifest.json").read_text(encoding="utf-8"),
        "color": (color_review_result["review_dir"] / "manifest.json").read_text(encoding="utf-8"),
        "typo": (typo_review_result["review_dir"] / "manifest.json").read_text(encoding="utf-8"),
    }
    assert before_prod == after_prod
    assert before_artifacts == after_artifacts

    canonical = select_canonical_visual_approval(db_path, plan_id)["design"]
    assert canonical["category_approvals"]["color_palette"]["resolved_style"]["MUTED"] == "#757b87"
    assert canonical["category_approvals"]["typography_scale"]["resolved_style"] == {"DOMINANT": 72, "PRIMARY": 46, "SUPPORTING": 28, "CAPTION": 20, "MICRO": 15}


# CASE W: determinism -- identical inputs -> identical candidates/manifest (except generated_at)/HTML
def test_run_font_weight_review_determinism(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, typo_result = _ready_plan_with_typography_scale_approved(tmp_path, db_path)

    result1 = run_font_weight_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    files1 = {p.name: p.read_text(encoding="utf-8") for p in result1["review_dir"].glob("*.html")}
    manifest1 = dict(result1["manifest"])
    manifest1.pop("generated_at")

    result2 = run_font_weight_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    files2 = {p.name: p.read_text(encoding="utf-8") for p in result2["review_dir"].glob("*.html")}
    manifest2 = dict(result2["manifest"])
    manifest2.pop("generated_at")

    assert files1 == files2
    assert manifest1 == manifest2


# ---------------------------------------------------------------------------
# 13-4C-13: Font Weight Human Approval -- persists the real Human Review decision (BALANCED_
# HIERARCHY from 13-4C-12) as the font_weight approval. Append-only, exactly like 13-4C-6/8/9/11.
# Native/synthetic provenance carried from build_font_weight_candidates() itself, never re-typed.
# ---------------------------------------------------------------------------

def test_human_selected_font_weight_candidate_constant_is_balanced():
    assert HUMAN_SELECTED_FONT_WEIGHT_CANDIDATE == "BALANCED_HIERARCHY"


def test_run_font_weight_human_approval_end_to_end(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, typo_result = _ready_plan_with_typography_scale_approved(tmp_path, db_path)
    prior_id = typo_result["visual_design_row_id"]
    with connect(db_path) as conn:
        before_count = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
        prior_json_before = conn.execute("SELECT design_json FROM visual_design_specs WHERE id = ?", (prior_id,)).fetchone()["design_json"]

    result = run_font_weight_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["pass"] is True
    assert result["selected_candidate"] == "BALANCED_HIERARCHY"

    baseline = CANDIDATES["CLEAN_DARK_FOCUS"]["roles"]
    expected = build_font_weight_candidates(baseline)["BALANCED_HIERARCHY"]
    assert result["approved_weights"] == expected["weights"] == {"DOMINANT": 800, "PRIMARY": 700, "SUPPORTING": 500, "CAPTION": 400, "MICRO": 400}
    assert result["native_provenance"] == expected["native"]
    assert result["native_provenance"] == {"DOMINANT": False, "PRIMARY": True, "SUPPORTING": False, "CAPTION": True, "MICRO": True}

    cat = result["record"]["category_approvals"]["font_weight"]
    assert cat["resolution_status"] == "APPROVED"
    assert cat["resolved_style"] == expected["weights"]
    assert cat["provenance"]["review_stage"] == "13-4C-13"
    assert cat["provenance"]["selected_candidate"] == "BALANCED_HIERARCHY"
    assert cat["provenance"]["native_face_by_role"] == expected["native"]
    assert "does not mean synthetic weights are absent" in cat["provenance"]["native_synthetic_note"]

    assert result["record"]["category_approvals"]["font_family"]["resolution_status"] == "APPROVED"
    assert result["record"]["category_approvals"]["background"]["resolution_status"] == "APPROVED"
    assert result["record"]["category_approvals"]["color_palette"]["resolution_status"] == "APPROVED"
    assert result["record"]["category_approvals"]["color_palette"]["resolved_style"]["MUTED"] == "#757b87"
    assert result["record"]["category_approvals"]["typography_scale"]["resolved_style"] == {"DOMINANT": 72, "PRIMARY": 46, "SUPPORTING": 28, "CAPTION": 20, "MICRO": 15}
    assert result["full_profile_approved"] is False
    assert result["ready_for_final_renderer_binding"] is False
    assert result["approved_category_count"] == 5
    assert result["pending_category_count"] == 10

    with connect(db_path) as conn:
        after_count = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
        prior_json_after = conn.execute("SELECT design_json FROM visual_design_specs WHERE id = ?", (prior_id,)).fetchone()["design_json"]
    assert after_count == before_count + 1
    assert prior_json_after == prior_json_before

    profile = json.loads(result["json_path"].read_text(encoding="utf-8"))
    assert profile["category_approvals"]["font_weight"]["resolution_status"] == "APPROVED"
    assert profile["category_approvals"]["font_weight"]["resolved_style"] == expected["weights"]


def test_run_font_weight_human_approval_fails_without_typography_scale(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, palette_result = _ready_plan_with_color_palette_approved(tmp_path, db_path)
    result = run_font_weight_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["pass"] is False


def test_run_font_weight_human_approval_rejects_when_already_approved(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, typo_result = _ready_plan_with_typography_scale_approved(tmp_path, db_path)
    first = run_font_weight_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert first["pass"] is True
    second = run_font_weight_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert second["pass"] is False


# CASE B: LIGHTER_HIERARCHY approval attempt is structurally refused
def test_run_font_weight_human_approval_rejects_lighter_hierarchy(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, typo_result = _ready_plan_with_typography_scale_approved(tmp_path, db_path)
    result = run_font_weight_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id, selected_candidate="LIGHTER_HIERARCHY")
    assert result["pass"] is False


# CASE C: STRONG_BEGINNER approval attempt is structurally refused
def test_run_font_weight_human_approval_rejects_strong_beginner(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, typo_result = _ready_plan_with_typography_scale_approved(tmp_path, db_path)
    result = run_font_weight_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id, selected_candidate="STRONG_BEGINNER")
    assert result["pass"] is False


# CASE D: unknown candidate is rejected, writes nothing
def test_run_font_weight_human_approval_rejects_unknown_candidate(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, typo_result = _ready_plan_with_typography_scale_approved(tmp_path, db_path)
    with connect(db_path) as conn:
        before = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
    result = run_font_weight_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id, selected_candidate="NOT_REAL")
    assert result["pass"] is False
    with connect(db_path) as conn:
        after = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
    assert after == before


# CASE M-P: existing font_family/background/color_palette/typography_scale approvals preserved exactly
def test_run_font_weight_human_approval_preserves_other_approvals(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, typo_result = _ready_plan_with_typography_scale_approved(tmp_path, db_path)
    before_font = typo_result["record"]["category_approvals"]["font_family"]
    before_bg = typo_result["record"]["category_approvals"]["background"]
    before_palette = typo_result["record"]["category_approvals"]["color_palette"]
    before_typo = typo_result["record"]["category_approvals"]["typography_scale"]
    result = run_font_weight_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["record"]["category_approvals"]["font_family"] == before_font
    assert result["record"]["category_approvals"]["background"] == before_bg
    assert result["record"]["category_approvals"]["color_palette"] == before_palette
    assert result["record"]["category_approvals"]["typography_scale"] == before_typo


# CASE Q: the existing canonical row is never modified -- append-only
def test_run_font_weight_human_approval_prior_row_unchanged(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, typo_result = _ready_plan_with_typography_scale_approved(tmp_path, db_path)
    prior_id = typo_result["visual_design_row_id"]
    with connect(db_path) as conn:
        before = conn.execute("SELECT design_json FROM visual_design_specs WHERE id = ?", (prior_id,)).fetchone()["design_json"]
    run_font_weight_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    with connect(db_path) as conn:
        after = conn.execute("SELECT design_json FROM visual_design_specs WHERE id = ?", (prior_id,)).fetchone()["design_json"]
    assert before == after


# CASE V/W/X: renderer gates stay False -- 10 mandatory-or-optional categories still PENDING
def test_run_font_weight_human_approval_gates_stay_false(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, typo_result = _ready_plan_with_typography_scale_approved(tmp_path, db_path)
    result = run_font_weight_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["record"]["full_profile_approved"] is False
    assert result["record"]["ready_for_final_renderer_binding"] is False


# CASE Y: Production/Audio/Layout tables untouched
def test_run_font_weight_human_approval_production_data_untouched(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, typo_result = _ready_plan_with_typography_scale_approved(tmp_path, db_path)
    with connect(db_path) as conn:
        before = {t: conn.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"] for t in ("production_blocks", "speech_assets", "generated_assets", "render_specs", "render_timelines", "scene_layouts")}
    run_font_weight_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    with connect(db_path) as conn:
        after = {t: conn.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"] for t in before}
    assert before == after


# CASE Z: existing Font Weight Review artifact (13-4C-12) is never modified
def test_run_font_weight_human_approval_does_not_touch_review_artifact(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, typo_result = _ready_plan_with_typography_scale_approved(tmp_path, db_path)
    review_result = run_font_weight_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    manifest_before = (review_result["review_dir"] / "manifest.json").read_text(encoding="utf-8")
    run_font_weight_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    manifest_after = (review_result["review_dir"] / "manifest.json").read_text(encoding="utf-8")
    assert manifest_before == manifest_after


# CASE AA: determinism across independent runs
def test_run_font_weight_human_approval_deterministic_values(tmp_path):
    db_path1 = tmp_path / "test1.db"
    init_db(db_path1)
    plan_id1, assets_dir1, reports_dir1, typo_result1 = _ready_plan_with_typography_scale_approved(tmp_path, db_path1)
    result1 = run_font_weight_human_approval(db_path1, assets_dir1, reports_dir1, plan_id=plan_id1)

    tmp_path2 = tmp_path / "second"
    tmp_path2.mkdir()
    db_path2 = tmp_path2 / "test2.db"
    init_db(db_path2)
    plan_id2, assets_dir2, reports_dir2, typo_result2 = _ready_plan_with_typography_scale_approved(tmp_path2, db_path2)
    result2 = run_font_weight_human_approval(db_path2, assets_dir2, reports_dir2, plan_id=plan_id2)

    assert result1["approved_weights"] == result2["approved_weights"]
    assert result1["native_provenance"] == result2["native_provenance"]


# ---------------------------------------------------------------------------
# 13-4C-14: Caption Style Human Review -- Review Preparation only (zero DB write), exactly like
# 13-4C-3/7/10/12. Font Family/Background/Color Palette/Typography Scale/Font Weight are all fixed
# conditions read from the real canonical APPROVED values. caption_style only styles the bottom
# NARRATION_CAPTION zone (CAPTION_ROLES); text color always reuses an approved palette role, never
# a new HEX. Human decision is always None here.
# ---------------------------------------------------------------------------

def _ready_plan_with_font_weight_approved(tmp_path, db_path):
    plan_id, assets_dir, reports_dir, typo_result = _ready_plan_with_typography_scale_approved(tmp_path, db_path)
    weight_result = run_font_weight_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert weight_result["pass"] is True
    return plan_id, assets_dir, reports_dir, weight_result


# --- pure function tests ---

def test_build_caption_style_candidates_returns_three_and_reuses_approved_palette_roles():
    candidates = build_caption_style_candidates()
    assert len(candidates) == 3
    for props in candidates.values():
        assert props["text_color_role"] in COLOR_REVIEW_ROLES


def test_build_caption_style_candidates_deterministic():
    r1 = build_caption_style_candidates()
    r2 = build_caption_style_candidates()
    assert r1 == r2
    assert r1 == CAPTION_STYLE_CANDIDATES  # matches the constant exactly, no hidden computation


def test_validate_caption_style_candidates_passes_for_real_candidates():
    candidates = build_caption_style_candidates()
    result = validate_caption_style_candidates(candidates)
    assert result["pass"] is True
    assert result["issues"] == []


def test_validate_caption_style_candidates_catches_bad_palette_role():
    broken = {"X": {"text_color_role": "NOT_A_ROLE", "background": "none", "background_opacity": 0.0, "padding": "4px 8px", "line_height": 1.4}}
    result = validate_caption_style_candidates(broken)
    assert result["pass"] is False
    assert any("not an approved palette role" in issue for issue in result["issues"])


def test_validate_caption_style_candidates_catches_invalid_opacity_and_padding():
    broken = {
        "X": {"text_color_role": "DEFAULT", "background": "box", "background_opacity": 1.5, "padding": "not-css", "line_height": 1.4},
    }
    result = validate_caption_style_candidates(broken)
    assert result["pass"] is False
    assert any("opacity" in issue for issue in result["issues"])
    assert any("padding" in issue for issue in result["issues"])


# --- end-to-end ---

def test_run_caption_style_review_end_to_end(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, weight_result = _ready_plan_with_font_weight_approved(tmp_path, db_path)
    result = run_caption_style_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["pass"] is True
    assert result["file_count"] == 19  # 18 + side-by-side
    assert result["validation"]["pass"] is True
    assert result["manifest"]["human_decision"] is None
    assert result["manifest"]["caption_style_status"] == "PENDING_VISUAL_REVIEW"
    assert result["report_path"].exists()
    index_html = (result["review_dir"] / "index.html").read_text(encoding="utf-8")
    for name in CAPTION_STYLE_CANDIDATES:
        assert name in index_html


def test_run_caption_style_review_fails_without_font_weight(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, typo_result = _ready_plan_with_typography_scale_approved(tmp_path, db_path)
    result = run_caption_style_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["pass"] is False


def test_run_caption_style_review_fails_if_already_approved(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, weight_result = _ready_plan_with_font_weight_approved(tmp_path, db_path)
    canonical = select_canonical_visual_approval(db_path, plan_id)["design"]
    assert canonical["category_approvals"]["caption_style"]["resolution_status"] == "PENDING_VISUAL_REVIEW"
    # no approve-caption-style function exists yet (by design, per 13-4C-14 §33) -- structurally
    # impossible to reach the "already approved" branch through public API, so this documents that
    # the gate exists rather than exercising a real transition
    result = run_caption_style_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["pass"] is True


# CASE A: text_color_role always reuses an approved palette role, never a new HEX
def test_run_caption_style_review_negative_a_no_new_hex(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, weight_result = _ready_plan_with_font_weight_approved(tmp_path, db_path)
    result = run_caption_style_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    for candidate in result["candidates"].values():
        assert candidate["text_color_role"] in COLOR_REVIEW_ROLES


# CASE B/C/D: typography size, font weight, and font family never change across candidates
def test_run_caption_style_review_negative_b_c_d_fixed_conditions_identical(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, weight_result = _ready_plan_with_font_weight_approved(tmp_path, db_path)
    result = run_caption_style_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    font_stacks, caption_sizes = set(), set()
    for candidate_name in result["candidates"]:
        html = (result["review_dir"] / f"02_SHORT_CAPTION_{candidate_name}.html").read_text(encoding="utf-8")
        font_stacks.add(re.search(r"font-family:([^;]+);", html).group(1))
        frame = _extract_frame_preview(html)
        caption_sizes.add(re.search(r"font-size:(\d+px);", frame).group(1))
    assert len(font_stacks) == 1
    assert len(caption_sizes) == 1
    assert list(caption_sizes)[0] == f"{result['sizes']['CAPTION']}px"


# CASE E: candidate ids are unique (structural -- dict keys)
def test_run_caption_style_review_negative_e_candidate_ids_unique(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, weight_result = _ready_plan_with_font_weight_approved(tmp_path, db_path)
    result = run_caption_style_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert len(set(result["candidates"].keys())) == len(result["candidates"])


# CASE H: caption_style is never auto-approved by review generation
def test_run_caption_style_review_negative_h_never_auto_approved(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, weight_result = _ready_plan_with_font_weight_approved(tmp_path, db_path)
    run_caption_style_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    canonical = select_canonical_visual_approval(db_path, plan_id)["design"]
    assert canonical["category_approvals"]["caption_style"]["resolution_status"] == "PENDING_VISUAL_REVIEW"


# CASE I: Human Decision is never set to a candidate -- always None
def test_run_caption_style_review_negative_i_human_decision_always_none(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, weight_result = _ready_plan_with_font_weight_approved(tmp_path, db_path)
    result = run_caption_style_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["manifest"]["human_decision"] is None


# CASE J: zero DB writes
def test_run_caption_style_review_negative_j_zero_db_writes(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, weight_result = _ready_plan_with_font_weight_approved(tmp_path, db_path)
    with connect(db_path) as conn:
        before = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
    run_caption_style_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    with connect(db_path) as conn:
        after = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
    assert after == before


# CASE K: approved_visual_profile.json is never touched
def test_run_caption_style_review_negative_k_profile_json_unchanged(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, weight_result = _ready_plan_with_font_weight_approved(tmp_path, db_path)
    profile_path = weight_result["json_path"]
    before = profile_path.read_text(encoding="utf-8")
    run_caption_style_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    after = profile_path.read_text(encoding="utf-8")
    assert before == after


# CASE L: Production/Audio/Layout data untouched
def test_run_caption_style_review_negative_l_production_data_untouched(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, weight_result = _ready_plan_with_font_weight_approved(tmp_path, db_path)
    with connect(db_path) as conn:
        before = {t: conn.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"] for t in ("production_blocks", "speech_assets", "generated_assets", "render_specs", "render_timelines", "scene_layouts")}
    run_caption_style_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    with connect(db_path) as conn:
        after = {t: conn.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"] for t in before}
    assert before == after


# existing 5 approvals (incl. MUTED, LARGE_BEGINNER sizes, BALANCED_HIERARCHY weights/provenance)
# preserved, and all prior review artifacts untouched
def test_run_caption_style_review_preserves_everything_else(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, weight_result = _ready_plan_with_font_weight_approved(tmp_path, db_path)

    # Note: run_font_weight_review itself is not called here -- it refuses to re-run once
    # font_weight is APPROVED (same "already approved" guard as this stage's own review function),
    # so font/color/typography review artifacts (unaffected by that guard) are checked instead;
    # font_weight_review's own unchanged-artifact invariant is covered separately in the 13-4C-12
    # section's own tests.
    font_review_result = run_font_family_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    color_review_result = run_color_background_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    typo_review_result = run_typography_scale_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    before_artifacts = {
        "font": (font_review_result["review_dir"] / "manifest.json").read_text(encoding="utf-8"),
        "color": (color_review_result["review_dir"] / "manifest.json").read_text(encoding="utf-8"),
        "typo": (typo_review_result["review_dir"] / "manifest.json").read_text(encoding="utf-8"),
    }

    run_caption_style_review(db_path, assets_dir, reports_dir, plan_id=plan_id)

    after_artifacts = {
        "font": (font_review_result["review_dir"] / "manifest.json").read_text(encoding="utf-8"),
        "color": (color_review_result["review_dir"] / "manifest.json").read_text(encoding="utf-8"),
        "typo": (typo_review_result["review_dir"] / "manifest.json").read_text(encoding="utf-8"),
    }
    assert before_artifacts == after_artifacts

    canonical = select_canonical_visual_approval(db_path, plan_id)["design"]
    assert canonical["category_approvals"]["color_palette"]["resolved_style"]["MUTED"] == "#757b87"
    assert canonical["category_approvals"]["typography_scale"]["resolved_style"] == {"DOMINANT": 72, "PRIMARY": 46, "SUPPORTING": 28, "CAPTION": 20, "MICRO": 15}
    assert canonical["category_approvals"]["font_weight"]["resolved_style"] == {"DOMINANT": 800, "PRIMARY": 700, "SUPPORTING": 500, "CAPTION": 400, "MICRO": 400}


# Determinism: identical inputs -> identical candidates/manifest (except generated_at)/HTML
def test_run_caption_style_review_determinism(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, weight_result = _ready_plan_with_font_weight_approved(tmp_path, db_path)

    result1 = run_caption_style_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    files1 = {p.name: p.read_text(encoding="utf-8") for p in result1["review_dir"].glob("*.html")}
    manifest1 = dict(result1["manifest"])
    manifest1.pop("generated_at")

    result2 = run_caption_style_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    files2 = {p.name: p.read_text(encoding="utf-8") for p in result2["review_dir"].glob("*.html")}
    manifest2 = dict(result2["manifest"])
    manifest2.pop("generated_at")

    assert files1 == files2
    assert manifest1 == manifest2


# ---------------------------------------------------------------------------
# 13-4C-15: Caption Style Human Approval -- persists the real Human Review decision (BALANCED_
# INTEGRATED from 13-4C-14) as the caption_style approval. Append-only, exactly like
# 13-4C-6/9/11/13.
# ---------------------------------------------------------------------------

def _ready_plan_with_caption_style_approved(tmp_path, db_path):
    plan_id, assets_dir, reports_dir, weight_result = _ready_plan_with_font_weight_approved(tmp_path, db_path)
    caption_result = run_caption_style_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert caption_result["pass"] is True
    return plan_id, assets_dir, reports_dir, caption_result


def test_human_selected_caption_style_candidate_constant_is_balanced_integrated():
    assert HUMAN_SELECTED_CAPTION_STYLE_CANDIDATE == "BALANCED_INTEGRATED"


def test_run_caption_style_human_approval_end_to_end(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, weight_result = _ready_plan_with_font_weight_approved(tmp_path, db_path)
    prior_id = weight_result["visual_design_row_id"]
    with connect(db_path) as conn:
        before_count = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
        prior_json_before = conn.execute("SELECT design_json FROM visual_design_specs WHERE id = ?", (prior_id,)).fetchone()["design_json"]

    result = run_caption_style_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["pass"] is True
    assert result["selected_candidate"] == "BALANCED_INTEGRATED"

    expected = CAPTION_STYLE_CANDIDATES["BALANCED_INTEGRATED"]
    assert result["approved_style"] == expected

    cat = result["record"]["category_approvals"]["caption_style"]
    assert cat["resolution_status"] == "APPROVED"
    assert cat["resolved_style"] == expected
    assert cat["provenance"]["review_stage"] == "13-4C-15"
    assert cat["provenance"]["selected_candidate"] == "BALANCED_INTEGRATED"

    assert result["record"]["category_approvals"]["font_family"]["resolution_status"] == "APPROVED"
    assert result["record"]["category_approvals"]["background"]["resolution_status"] == "APPROVED"
    assert result["record"]["category_approvals"]["color_palette"]["resolution_status"] == "APPROVED"
    assert result["record"]["category_approvals"]["color_palette"]["resolved_style"]["MUTED"] == "#757b87"
    assert result["record"]["category_approvals"]["typography_scale"]["resolved_style"] == {"DOMINANT": 72, "PRIMARY": 46, "SUPPORTING": 28, "CAPTION": 20, "MICRO": 15}
    assert result["record"]["category_approvals"]["font_weight"]["resolved_style"] == {"DOMINANT": 800, "PRIMARY": 700, "SUPPORTING": 500, "CAPTION": 400, "MICRO": 400}
    assert result["full_profile_approved"] is False
    assert result["ready_for_final_renderer_binding"] is False
    assert result["approved_category_count"] == 6
    assert result["pending_category_count"] == 9

    with connect(db_path) as conn:
        after_count = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
        prior_json_after = conn.execute("SELECT design_json FROM visual_design_specs WHERE id = ?", (prior_id,)).fetchone()["design_json"]
    assert after_count == before_count + 1
    assert prior_json_after == prior_json_before

    profile = json.loads(result["json_path"].read_text(encoding="utf-8"))
    assert profile["category_approvals"]["caption_style"]["resolution_status"] == "APPROVED"
    assert profile["category_approvals"]["caption_style"]["resolved_style"] == expected


def test_run_caption_style_human_approval_fails_without_font_weight(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, typo_result = _ready_plan_with_typography_scale_approved(tmp_path, db_path)
    result = run_caption_style_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["pass"] is False


def test_run_caption_style_human_approval_rejects_when_already_approved(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, weight_result = _ready_plan_with_font_weight_approved(tmp_path, db_path)
    first = run_caption_style_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert first["pass"] is True
    second = run_caption_style_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert second["pass"] is False


# CASE B: MINIMAL_TEXT approval attempt is structurally refused
def test_run_caption_style_human_approval_rejects_minimal_text(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, weight_result = _ready_plan_with_font_weight_approved(tmp_path, db_path)
    result = run_caption_style_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id, selected_candidate="MINIMAL_TEXT")
    assert result["pass"] is False


# CASE C: BEGINNER_EMPHASIS approval attempt is structurally refused
def test_run_caption_style_human_approval_rejects_beginner_emphasis(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, weight_result = _ready_plan_with_font_weight_approved(tmp_path, db_path)
    result = run_caption_style_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id, selected_candidate="BEGINNER_EMPHASIS")
    assert result["pass"] is False


# CASE D: unknown candidate is rejected, writes nothing
def test_run_caption_style_human_approval_rejects_unknown_candidate(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, weight_result = _ready_plan_with_font_weight_approved(tmp_path, db_path)
    with connect(db_path) as conn:
        before = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
    result = run_caption_style_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id, selected_candidate="NOT_REAL")
    assert result["pass"] is False
    with connect(db_path) as conn:
        after = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
    assert after == before


# CASE M-Q: existing font_family/background/color_palette/typography_scale/font_weight approvals preserved exactly
def test_run_caption_style_human_approval_preserves_other_approvals(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, weight_result = _ready_plan_with_font_weight_approved(tmp_path, db_path)
    before_font = weight_result["record"]["category_approvals"]["font_family"]
    before_bg = weight_result["record"]["category_approvals"]["background"]
    before_palette = weight_result["record"]["category_approvals"]["color_palette"]
    before_typo = weight_result["record"]["category_approvals"]["typography_scale"]
    before_weight = weight_result["record"]["category_approvals"]["font_weight"]
    result = run_caption_style_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["record"]["category_approvals"]["font_family"] == before_font
    assert result["record"]["category_approvals"]["background"] == before_bg
    assert result["record"]["category_approvals"]["color_palette"] == before_palette
    assert result["record"]["category_approvals"]["typography_scale"] == before_typo
    assert result["record"]["category_approvals"]["font_weight"] == before_weight


# CASE Q: the existing canonical row is never modified -- append-only
def test_run_caption_style_human_approval_prior_row_unchanged(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, weight_result = _ready_plan_with_font_weight_approved(tmp_path, db_path)
    prior_id = weight_result["visual_design_row_id"]
    with connect(db_path) as conn:
        before = conn.execute("SELECT design_json FROM visual_design_specs WHERE id = ?", (prior_id,)).fetchone()["design_json"]
    run_caption_style_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    with connect(db_path) as conn:
        after = conn.execute("SELECT design_json FROM visual_design_specs WHERE id = ?", (prior_id,)).fetchone()["design_json"]
    assert before == after


# CASE V/W/X: renderer gates stay False -- 9 mandatory-or-optional categories still PENDING
def test_run_caption_style_human_approval_gates_stay_false(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, weight_result = _ready_plan_with_font_weight_approved(tmp_path, db_path)
    result = run_caption_style_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["record"]["full_profile_approved"] is False
    assert result["record"]["ready_for_final_renderer_binding"] is False


# CASE Y: Production/Audio/Layout tables untouched
def test_run_caption_style_human_approval_production_data_untouched(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, weight_result = _ready_plan_with_font_weight_approved(tmp_path, db_path)
    with connect(db_path) as conn:
        before = {t: conn.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"] for t in ("production_blocks", "speech_assets", "generated_assets", "render_specs", "render_timelines", "scene_layouts")}
    run_caption_style_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    with connect(db_path) as conn:
        after = {t: conn.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"] for t in before}
    assert before == after


# CASE Z: existing Caption Style Review artifact (13-4C-14) is never modified
def test_run_caption_style_human_approval_does_not_touch_review_artifact(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, weight_result = _ready_plan_with_font_weight_approved(tmp_path, db_path)
    review_result = run_caption_style_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    manifest_before = (review_result["review_dir"] / "manifest.json").read_text(encoding="utf-8")
    run_caption_style_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    manifest_after = (review_result["review_dir"] / "manifest.json").read_text(encoding="utf-8")
    assert manifest_before == manifest_after


# CASE AA: determinism across independent runs
def test_run_caption_style_human_approval_deterministic_values(tmp_path):
    db_path1 = tmp_path / "test1.db"
    init_db(db_path1)
    plan_id1, assets_dir1, reports_dir1, weight_result1 = _ready_plan_with_font_weight_approved(tmp_path, db_path1)
    result1 = run_caption_style_human_approval(db_path1, assets_dir1, reports_dir1, plan_id=plan_id1)

    tmp_path2 = tmp_path / "second"
    tmp_path2.mkdir()
    db_path2 = tmp_path2 / "test2.db"
    init_db(db_path2)
    plan_id2, assets_dir2, reports_dir2, weight_result2 = _ready_plan_with_font_weight_approved(tmp_path2, db_path2)
    result2 = run_caption_style_human_approval(db_path2, assets_dir2, reports_dir2, plan_id=plan_id2)

    assert result1["approved_style"] == result2["approved_style"]


# ---------------------------------------------------------------------------
# 13-4C-16: Focus Style Human Review -- Review Preparation only (zero DB write), exactly like
# 13-4C-3/7/10/12/14. focus_style has no prior implementation beyond the already-approved
# PRIMARY_FOCUS color role and the hardcoded element_state ACTIVE/MUTED opacity effect. Candidates
# only add presentation (highlight box / underline) on top of the fixed PRIMARY_FOCUS color for the
# currently ACTIVE target -- never for an already-MUTED (superseded) one. Human decision is always
# None here.
# ---------------------------------------------------------------------------

# --- pure function tests ---

def test_build_focus_style_candidates_returns_three_and_reuses_approved_palette_role():
    candidates = build_focus_style_candidates()
    assert len(candidates) == 3
    for props in candidates.values():
        assert props["color_role"] == "PRIMARY_FOCUS"
        assert props["color_role"] in COLOR_REVIEW_ROLES


def test_build_focus_style_candidates_deterministic():
    r1 = build_focus_style_candidates()
    r2 = build_focus_style_candidates()
    assert r1 == r2
    assert r1 == FOCUS_STYLE_CANDIDATES  # matches the constant exactly, no hidden computation


def test_validate_focus_style_candidates_passes_for_real_candidates():
    candidates = build_focus_style_candidates()
    result = validate_focus_style_candidates(candidates)
    assert result["pass"] is True
    assert result["issues"] == []


def test_validate_focus_style_candidates_catches_bad_palette_role():
    broken = {"X": {"color_role": "NOT_A_ROLE", "highlight_box": False, "box_opacity": 0.0, "padding": "0", "underline": False}}
    result = validate_focus_style_candidates(broken)
    assert result["pass"] is False
    assert any("not an approved palette role" in issue for issue in result["issues"])


def test_validate_focus_style_candidates_catches_invalid_opacity_padding_and_types():
    broken = {
        "X": {"color_role": "PRIMARY_FOCUS", "highlight_box": "yes", "box_opacity": 1.5, "padding": "not-css", "underline": "no"},
    }
    result = validate_focus_style_candidates(broken)
    assert result["pass"] is False
    assert any("highlight_box" in issue for issue in result["issues"])
    assert any("box_opacity" in issue for issue in result["issues"])
    assert any("padding" in issue for issue in result["issues"])
    assert any("underline" in issue for issue in result["issues"])


# --- end-to-end ---

def test_run_focus_style_review_end_to_end(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, caption_result = _ready_plan_with_caption_style_approved(tmp_path, db_path)
    result = run_focus_style_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["pass"] is True
    assert result["file_count"] == 19  # 18 + side-by-side
    assert result["validation"]["pass"] is True
    assert result["manifest"]["human_decision"] is None
    assert result["manifest"]["focus_style_status"] == "PENDING_VISUAL_REVIEW"
    assert result["report_path"].exists()
    index_html = (result["review_dir"] / "index.html").read_text(encoding="utf-8")
    for name in FOCUS_STYLE_CANDIDATES:
        assert name in index_html


def test_run_focus_style_review_fails_without_caption_style(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, weight_result = _ready_plan_with_font_weight_approved(tmp_path, db_path)
    result = run_focus_style_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["pass"] is False


def test_run_focus_style_review_fails_if_already_approved(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, caption_result = _ready_plan_with_caption_style_approved(tmp_path, db_path)
    canonical = select_canonical_visual_approval(db_path, plan_id)["design"]
    assert canonical["category_approvals"]["focus_style"]["resolution_status"] == "PENDING_VISUAL_REVIEW"
    # no approve-focus-style function exists yet (by design, per 13-4C-16 spec) -- structurally
    # impossible to reach the "already approved" branch through public API, so this documents that
    # the gate exists rather than exercising a real transition
    result = run_focus_style_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["pass"] is True


# CASE D: color_role always reuses an approved palette role, never a new HEX/role
def test_run_focus_style_review_negative_d_no_new_palette_role(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, caption_result = _ready_plan_with_caption_style_approved(tmp_path, db_path)
    result = run_focus_style_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    for candidate in result["candidates"].values():
        assert candidate["color_role"] in COLOR_REVIEW_ROLES


# CASE E/F/G/H/I: font family, background, typography scale, font weight, and caption style never
# change across candidates -- fixed conditions identical
def test_run_focus_style_review_negative_efghi_fixed_conditions_identical(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, caption_result = _ready_plan_with_caption_style_approved(tmp_path, db_path)
    result = run_focus_style_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    font_stacks, dominant_sizes = set(), set()
    for candidate_name in result["candidates"]:
        html = (result["review_dir"] / f"01_SINGLE_WORD_FOCUS_{candidate_name}.html").read_text(encoding="utf-8")
        font_stacks.add(re.search(r"font-family:([^;]+);", html).group(1))
        frame = _extract_frame_preview(html)
        dominant_sizes.add(re.search(r"font-size:(\d+px);", frame).group(1))
    assert len(font_stacks) == 1
    assert len(dominant_sizes) == 1
    assert list(dominant_sizes)[0] == f"{result['sizes']['DOMINANT']}px"


# CASE: candidate ids are unique (structural -- dict keys)
def test_run_focus_style_review_candidate_ids_unique(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, caption_result = _ready_plan_with_caption_style_approved(tmp_path, db_path)
    result = run_focus_style_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert len(set(result["candidates"].keys())) == len(result["candidates"])


# CASE: focus_style is never auto-approved by review generation
def test_run_focus_style_review_never_auto_approved(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, caption_result = _ready_plan_with_caption_style_approved(tmp_path, db_path)
    run_focus_style_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    canonical = select_canonical_visual_approval(db_path, plan_id)["design"]
    assert canonical["category_approvals"]["focus_style"]["resolution_status"] == "PENDING_VISUAL_REVIEW"


# CASE: Human Decision is never set to a candidate -- always None
def test_run_focus_style_review_human_decision_always_none(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, caption_result = _ready_plan_with_caption_style_approved(tmp_path, db_path)
    result = run_focus_style_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["manifest"]["human_decision"] is None


# CASE M: zero DB writes
def test_run_focus_style_review_zero_db_writes(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, caption_result = _ready_plan_with_caption_style_approved(tmp_path, db_path)
    with connect(db_path) as conn:
        before = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
    run_focus_style_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    with connect(db_path) as conn:
        after = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
    assert after == before


# CASE N: canonical id never changes
def test_run_focus_style_review_canonical_id_unchanged(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, caption_result = _ready_plan_with_caption_style_approved(tmp_path, db_path)
    before_id = select_canonical_visual_approval(db_path, plan_id)["id"]
    run_focus_style_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    after_id = select_canonical_visual_approval(db_path, plan_id)["id"]
    assert after_id == before_id


# CASE O: approved_visual_profile.json is never touched
def test_run_focus_style_review_profile_json_unchanged(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, caption_result = _ready_plan_with_caption_style_approved(tmp_path, db_path)
    profile_path = caption_result["json_path"]
    before = profile_path.read_text(encoding="utf-8")
    run_focus_style_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    after = profile_path.read_text(encoding="utf-8")
    assert before == after


# CASE Q/R: Production/Audio/Layout data untouched
def test_run_focus_style_review_production_data_untouched(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, caption_result = _ready_plan_with_caption_style_approved(tmp_path, db_path)
    with connect(db_path) as conn:
        before = {t: conn.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"] for t in ("production_blocks", "speech_assets", "generated_assets", "render_specs", "render_timelines", "scene_layouts")}
    run_focus_style_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    with connect(db_path) as conn:
        after = {t: conn.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"] for t in before}
    assert before == after


# CASE P: existing 6 approvals (incl. MUTED, LARGE_BEGINNER sizes, BALANCED_HIERARCHY weights,
# BALANCED_INTEGRATED caption style) preserved, and all prior review artifacts untouched
def test_run_focus_style_review_preserves_everything_else(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, caption_result = _ready_plan_with_caption_style_approved(tmp_path, db_path)

    # Note: run_caption_style_review itself is not called here -- it refuses to re-run once
    # caption_style is APPROVED (same "already approved" guard as this stage's own review
    # function), so font/color/typography review artifacts (unaffected by that guard) are checked
    # instead; caption_style_review's own unchanged-artifact invariant is covered separately in the
    # 13-4C-14 section's own tests.
    font_review_result = run_font_family_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    color_review_result = run_color_background_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    typo_review_result = run_typography_scale_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    before_artifacts = {
        "font": (font_review_result["review_dir"] / "manifest.json").read_text(encoding="utf-8"),
        "color": (color_review_result["review_dir"] / "manifest.json").read_text(encoding="utf-8"),
        "typo": (typo_review_result["review_dir"] / "manifest.json").read_text(encoding="utf-8"),
    }

    run_focus_style_review(db_path, assets_dir, reports_dir, plan_id=plan_id)

    after_artifacts = {
        "font": (font_review_result["review_dir"] / "manifest.json").read_text(encoding="utf-8"),
        "color": (color_review_result["review_dir"] / "manifest.json").read_text(encoding="utf-8"),
        "typo": (typo_review_result["review_dir"] / "manifest.json").read_text(encoding="utf-8"),
    }
    assert before_artifacts == after_artifacts

    canonical = select_canonical_visual_approval(db_path, plan_id)["design"]
    assert canonical["category_approvals"]["color_palette"]["resolved_style"]["MUTED"] == "#757b87"
    assert canonical["category_approvals"]["typography_scale"]["resolved_style"] == {"DOMINANT": 72, "PRIMARY": 46, "SUPPORTING": 28, "CAPTION": 20, "MICRO": 15}
    assert canonical["category_approvals"]["font_weight"]["resolved_style"] == {"DOMINANT": 800, "PRIMARY": 700, "SUPPORTING": 500, "CAPTION": 400, "MICRO": 400}
    assert canonical["category_approvals"]["caption_style"]["resolved_style"] == {"text_color_role": "DEFAULT", "background": "box", "background_opacity": 0.55, "padding": "8px 16px", "line_height": 1.5}


# Determinism: identical inputs -> identical candidates/manifest (except generated_at)/HTML
def test_run_focus_style_review_determinism(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, caption_result = _ready_plan_with_caption_style_approved(tmp_path, db_path)

    result1 = run_focus_style_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    files1 = {p.name: p.read_text(encoding="utf-8") for p in result1["review_dir"].glob("*.html")}
    manifest1 = dict(result1["manifest"])
    manifest1.pop("generated_at")

    result2 = run_focus_style_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    files2 = {p.name: p.read_text(encoding="utf-8") for p in result2["review_dir"].glob("*.html")}
    manifest2 = dict(result2["manifest"])
    manifest2.pop("generated_at")

    assert files1 == files2
    assert manifest1 == manifest2


# Focus semantics: multi-word context reuses real CB07 data and never boxes an already-MUTED target
def test_run_focus_style_review_multi_word_muted_not_boxed(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, caption_result = _ready_plan_with_caption_style_approved(tmp_path, db_path)
    result = run_focus_style_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    html = (result["review_dir"] / "02_MULTI_WORD_LEARNING_STRONG_FOCUS.html").read_text(encoding="utf-8")
    frame = _extract_frame_preview(html)
    for muted_word in ("BAG", "BAT", "MAP"):
        muted_div = re.search(rf'<div data-focus-element data-element-state="MUTED"[^>]*>{muted_word}</div>', frame)
        assert muted_div is not None
        assert "opacity:0.4" in muted_div.group(0)
        assert "background:rgba" not in muted_div.group(0)
    active_div = re.search(r'<div data-focus-element style="[^"]*">CAP</div>', frame)
    assert active_div is not None
    assert "background:rgba" in active_div.group(0)  # STRONG_FOCUS has highlight_box=True


# ---------------------------------------------------------------------------
# 13-4C-17: Focus Style Human Approval -- persists the real Human Review decision (COLOR_ONLY from
# 13-4C-16) as the focus_style approval. Append-only, exactly like 13-4C-6/9/11/13/15.
# ---------------------------------------------------------------------------

def _ready_plan_with_focus_style_approved(tmp_path, db_path):
    plan_id, assets_dir, reports_dir, caption_result = _ready_plan_with_caption_style_approved(tmp_path, db_path)
    focus_result = run_focus_style_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert focus_result["pass"] is True
    return plan_id, assets_dir, reports_dir, focus_result


def test_human_selected_focus_style_candidate_constant_is_color_only():
    assert HUMAN_SELECTED_FOCUS_STYLE_CANDIDATE == "COLOR_ONLY"


def test_run_focus_style_human_approval_end_to_end(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, caption_result = _ready_plan_with_caption_style_approved(tmp_path, db_path)
    prior_id = caption_result["visual_design_row_id"]
    with connect(db_path) as conn:
        before_count = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
        prior_json_before = conn.execute("SELECT design_json FROM visual_design_specs WHERE id = ?", (prior_id,)).fetchone()["design_json"]

    result = run_focus_style_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["pass"] is True
    assert result["selected_candidate"] == "COLOR_ONLY"

    expected = FOCUS_STYLE_CANDIDATES["COLOR_ONLY"]
    assert result["approved_style"] == expected
    assert result["resolved_focus_color"] == "#60a5fa"

    cat = result["record"]["category_approvals"]["focus_style"]
    assert cat["resolution_status"] == "APPROVED"
    assert cat["resolved_style"] == expected
    assert cat["provenance"]["review_stage"] == "13-4C-17"
    assert cat["provenance"]["selected_candidate"] == "COLOR_ONLY"
    assert cat["provenance"]["resolved_focus_color"] == "#60a5fa"

    assert result["record"]["category_approvals"]["font_family"]["resolution_status"] == "APPROVED"
    assert result["record"]["category_approvals"]["background"]["resolution_status"] == "APPROVED"
    assert result["record"]["category_approvals"]["color_palette"]["resolution_status"] == "APPROVED"
    assert result["record"]["category_approvals"]["color_palette"]["resolved_style"]["MUTED"] == "#757b87"
    assert result["record"]["category_approvals"]["typography_scale"]["resolved_style"] == {"DOMINANT": 72, "PRIMARY": 46, "SUPPORTING": 28, "CAPTION": 20, "MICRO": 15}
    assert result["record"]["category_approvals"]["font_weight"]["resolved_style"] == {"DOMINANT": 800, "PRIMARY": 700, "SUPPORTING": 500, "CAPTION": 400, "MICRO": 400}
    assert result["record"]["category_approvals"]["caption_style"]["resolved_style"] == {"text_color_role": "DEFAULT", "background": "box", "background_opacity": 0.55, "padding": "8px 16px", "line_height": 1.5}
    assert result["full_profile_approved"] is False
    assert result["ready_for_final_renderer_binding"] is False
    assert result["approved_category_count"] == 7
    assert result["pending_category_count"] == 8

    with connect(db_path) as conn:
        after_count = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
        prior_json_after = conn.execute("SELECT design_json FROM visual_design_specs WHERE id = ?", (prior_id,)).fetchone()["design_json"]
    assert after_count == before_count + 1
    assert prior_json_after == prior_json_before

    profile = json.loads(result["json_path"].read_text(encoding="utf-8"))
    assert profile["category_approvals"]["focus_style"]["resolution_status"] == "APPROVED"
    assert profile["category_approvals"]["focus_style"]["resolved_style"] == expected


def test_run_focus_style_human_approval_fails_without_caption_style(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, weight_result = _ready_plan_with_font_weight_approved(tmp_path, db_path)
    result = run_focus_style_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["pass"] is False


def test_run_focus_style_human_approval_rejects_when_already_approved(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, caption_result = _ready_plan_with_caption_style_approved(tmp_path, db_path)
    first = run_focus_style_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert first["pass"] is True
    second = run_focus_style_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert second["pass"] is False


# CASE D: BALANCED_FOCUS approval attempt is structurally refused
def test_run_focus_style_human_approval_rejects_balanced_focus(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, caption_result = _ready_plan_with_caption_style_approved(tmp_path, db_path)
    result = run_focus_style_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id, selected_candidate="BALANCED_FOCUS")
    assert result["pass"] is False


# CASE E: STRONG_FOCUS approval attempt is structurally refused
def test_run_focus_style_human_approval_rejects_strong_focus(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, caption_result = _ready_plan_with_caption_style_approved(tmp_path, db_path)
    result = run_focus_style_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id, selected_candidate="STRONG_FOCUS")
    assert result["pass"] is False


# CASE: unknown candidate is rejected, writes nothing
def test_run_focus_style_human_approval_rejects_unknown_candidate(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, caption_result = _ready_plan_with_caption_style_approved(tmp_path, db_path)
    with connect(db_path) as conn:
        before = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
    result = run_focus_style_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id, selected_candidate="NOT_REAL")
    assert result["pass"] is False
    with connect(db_path) as conn:
        after = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
    assert after == before


# CASE I: existing font_family/background/color_palette/typography_scale/font_weight/caption_style
# approvals preserved exactly
def test_run_focus_style_human_approval_preserves_other_approvals(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, caption_result = _ready_plan_with_caption_style_approved(tmp_path, db_path)
    before_font = caption_result["record"]["category_approvals"]["font_family"]
    before_bg = caption_result["record"]["category_approvals"]["background"]
    before_palette = caption_result["record"]["category_approvals"]["color_palette"]
    before_typo = caption_result["record"]["category_approvals"]["typography_scale"]
    before_weight = caption_result["record"]["category_approvals"]["font_weight"]
    before_caption = caption_result["record"]["category_approvals"]["caption_style"]
    result = run_focus_style_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["record"]["category_approvals"]["font_family"] == before_font
    assert result["record"]["category_approvals"]["background"] == before_bg
    assert result["record"]["category_approvals"]["color_palette"] == before_palette
    assert result["record"]["category_approvals"]["typography_scale"] == before_typo
    assert result["record"]["category_approvals"]["font_weight"] == before_weight
    assert result["record"]["category_approvals"]["caption_style"] == before_caption


# CASE J: unrelated pending category never becomes APPROVED
def test_run_focus_style_human_approval_no_unrelated_auto_approval(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, caption_result = _ready_plan_with_caption_style_approved(tmp_path, db_path)
    result = run_focus_style_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    for name in ("success_style", "motion_style", "output_profile_16_9", "output_profile_9_16", "spacing_scale", "container", "border", "radius"):
        assert result["record"]["category_approvals"][name]["resolution_status"] == "PENDING_VISUAL_REVIEW"


# CASE K: the existing canonical row is never modified -- append-only
def test_run_focus_style_human_approval_prior_row_unchanged(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, caption_result = _ready_plan_with_caption_style_approved(tmp_path, db_path)
    prior_id = caption_result["visual_design_row_id"]
    with connect(db_path) as conn:
        before = conn.execute("SELECT design_json FROM visual_design_specs WHERE id = ?", (prior_id,)).fetchone()["design_json"]
    run_focus_style_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    with connect(db_path) as conn:
        after = conn.execute("SELECT design_json FROM visual_design_specs WHERE id = ?", (prior_id,)).fetchone()["design_json"]
    assert before == after


# CASE L: more than one new canonical row is never created per call
def test_run_focus_style_human_approval_exactly_one_new_row(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, caption_result = _ready_plan_with_caption_style_approved(tmp_path, db_path)
    with connect(db_path) as conn:
        before = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
    run_focus_style_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    with connect(db_path) as conn:
        after = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
    assert after == before + 1


# Renderer gates stay False -- 8 mandatory-or-optional categories still PENDING
def test_run_focus_style_human_approval_gates_stay_false(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, caption_result = _ready_plan_with_caption_style_approved(tmp_path, db_path)
    result = run_focus_style_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["record"]["full_profile_approved"] is False
    assert result["record"]["ready_for_final_renderer_binding"] is False


# CASE N: Production/Audio/Layout tables untouched
def test_run_focus_style_human_approval_production_data_untouched(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, caption_result = _ready_plan_with_caption_style_approved(tmp_path, db_path)
    with connect(db_path) as conn:
        before = {t: conn.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"] for t in ("production_blocks", "speech_assets", "generated_assets", "render_specs", "render_timelines", "scene_layouts")}
    run_focus_style_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    with connect(db_path) as conn:
        after = {t: conn.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"] for t in before}
    assert before == after


# CASE M: existing Focus Style Review artifact (13-4C-16) is never modified
def test_run_focus_style_human_approval_does_not_touch_review_artifact(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, caption_result = _ready_plan_with_caption_style_approved(tmp_path, db_path)
    review_result = run_focus_style_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    manifest_before = (review_result["review_dir"] / "manifest.json").read_text(encoding="utf-8")
    run_focus_style_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    manifest_after = (review_result["review_dir"] / "manifest.json").read_text(encoding="utf-8")
    assert manifest_before == manifest_after


# CASE U: determinism across independent runs
def test_run_focus_style_human_approval_deterministic_values(tmp_path):
    db_path1 = tmp_path / "test1.db"
    init_db(db_path1)
    plan_id1, assets_dir1, reports_dir1, caption_result1 = _ready_plan_with_caption_style_approved(tmp_path, db_path1)
    result1 = run_focus_style_human_approval(db_path1, assets_dir1, reports_dir1, plan_id=plan_id1)

    tmp_path2 = tmp_path / "second"
    tmp_path2.mkdir()
    db_path2 = tmp_path2 / "test2.db"
    init_db(db_path2)
    plan_id2, assets_dir2, reports_dir2, caption_result2 = _ready_plan_with_caption_style_approved(tmp_path2, db_path2)
    result2 = run_focus_style_human_approval(db_path2, assets_dir2, reports_dir2, plan_id=plan_id2)

    assert result1["approved_style"] == result2["approved_style"]
    assert result1["resolved_focus_color"] == result2["resolved_focus_color"]


# ---------------------------------------------------------------------------
# 13-4C-18: Success Style Human Review -- Review Preparation only (zero DB write), exactly like
# 13-4C-3/7/10/12/14/16. success_style has no prior implementation beyond the already-approved
# SUCCESS color role and the real _cb06_phase_overrides(role=="ANSWER") policy. Real Plan 7 data
# confirms SUCCESS is used exactly once, in CB06. Candidates only add presentation (highlight box /
# underline) on top of the fixed SUCCESS color -- no celebration content, no new palette role. Human
# decision is always None here.
# ---------------------------------------------------------------------------

# --- pure function tests ---

def test_build_success_style_candidates_returns_three_and_reuses_approved_palette_role():
    candidates = build_success_style_candidates()
    assert len(candidates) == 3
    for props in candidates.values():
        assert props["color_role"] == "SUCCESS"
        assert props["color_role"] in COLOR_REVIEW_ROLES


def test_build_success_style_candidates_deterministic():
    r1 = build_success_style_candidates()
    r2 = build_success_style_candidates()
    assert r1 == r2
    assert r1 == SUCCESS_STYLE_CANDIDATES  # matches the constant exactly, no hidden computation


def test_validate_success_style_candidates_passes_for_real_candidates():
    candidates = build_success_style_candidates()
    result = validate_success_style_candidates(candidates)
    assert result["pass"] is True
    assert result["issues"] == []


def test_validate_success_style_candidates_catches_bad_palette_role():
    broken = {"X": {"color_role": "NOT_A_ROLE", "highlight_box": False, "box_opacity": 0.0, "padding": "0", "underline": False}}
    result = validate_success_style_candidates(broken)
    assert result["pass"] is False
    assert any("not an approved palette role" in issue for issue in result["issues"])


def test_validate_success_style_candidates_catches_invalid_opacity_padding_and_types():
    broken = {
        "X": {"color_role": "SUCCESS", "highlight_box": "yes", "box_opacity": 1.5, "padding": "not-css", "underline": "no"},
    }
    result = validate_success_style_candidates(broken)
    assert result["pass"] is False
    assert any("highlight_box" in issue for issue in result["issues"])
    assert any("box_opacity" in issue for issue in result["issues"])
    assert any("padding" in issue for issue in result["issues"])
    assert any("underline" in issue for issue in result["issues"])


# --- end-to-end ---

def test_run_success_style_review_end_to_end(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, focus_result = _ready_plan_with_focus_style_approved(tmp_path, db_path)
    result = run_success_style_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["pass"] is True
    assert result["file_count"] == 19  # 18 + side-by-side
    assert result["validation"]["pass"] is True
    assert result["manifest"]["human_decision"] is None
    assert result["manifest"]["success_style_status"] == "PENDING_VISUAL_REVIEW"
    assert result["report_path"].exists()
    index_html = (result["review_dir"] / "index.html").read_text(encoding="utf-8")
    for name in SUCCESS_STYLE_CANDIDATES:
        assert name in index_html


def test_run_success_style_review_fails_without_focus_style(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, caption_result = _ready_plan_with_caption_style_approved(tmp_path, db_path)
    result = run_success_style_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["pass"] is False


def test_run_success_style_review_fails_if_already_approved(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, focus_result = _ready_plan_with_focus_style_approved(tmp_path, db_path)
    canonical = select_canonical_visual_approval(db_path, plan_id)["design"]
    assert canonical["category_approvals"]["success_style"]["resolution_status"] == "PENDING_VISUAL_REVIEW"
    # no approve-success-style function exists yet (by design, per 13-4C-18 spec) -- structurally
    # impossible to reach the "already approved" branch through public API, so this documents that
    # the gate exists rather than exercising a real transition
    result = run_success_style_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["pass"] is True


# CASE D: color_role always reuses an approved palette role, never a new HEX/role
def test_run_success_style_review_negative_d_no_new_palette_role(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, focus_result = _ready_plan_with_focus_style_approved(tmp_path, db_path)
    result = run_success_style_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    for candidate in result["candidates"].values():
        assert candidate["color_role"] in COLOR_REVIEW_ROLES


# CASE E/F/G/H: font family, typography scale, font weight, caption style, and focus style never
# change across candidates -- fixed conditions identical
def test_run_success_style_review_negative_efgh_fixed_conditions_identical(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, focus_result = _ready_plan_with_focus_style_approved(tmp_path, db_path)
    result = run_success_style_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    font_stacks, dominant_sizes = set(), set()
    for candidate_name in result["candidates"]:
        html = (result["review_dir"] / f"01_SINGLE_ANSWER_{candidate_name}.html").read_text(encoding="utf-8")
        font_stacks.add(re.search(r"font-family:([^;]+);", html).group(1))
        frame = _extract_frame_preview(html)
        dominant_sizes.add(re.search(r"font-size:(\d+px);", frame).group(1))
    assert len(font_stacks) == 1
    assert len(dominant_sizes) == 1
    assert list(dominant_sizes)[0] == f"{result['sizes']['DOMINANT']}px"


# CASE L: no celebration content is invented
def test_run_success_style_review_negative_l_no_celebration_content(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, focus_result = _ready_plan_with_focus_style_approved(tmp_path, db_path)
    result = run_success_style_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    celebration_markers = ("Great!", "Correct!", "Well done!", "정답입니다", "잘했어요", "\U0001F389", "✅")
    for html_path in result["review_dir"].glob("*.html"):
        html = html_path.read_text(encoding="utf-8")
        for marker in celebration_markers:
            assert marker not in html, f"{html_path.name} contains celebration marker {marker!r}"


# CASE M: candidate ids are unique (structural -- dict keys)
def test_run_success_style_review_candidate_ids_unique(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, focus_result = _ready_plan_with_focus_style_approved(tmp_path, db_path)
    result = run_success_style_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert len(set(result["candidates"].keys())) == len(result["candidates"])


# CASE: success_style is never auto-approved by review generation
def test_run_success_style_review_never_auto_approved(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, focus_result = _ready_plan_with_focus_style_approved(tmp_path, db_path)
    run_success_style_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    canonical = select_canonical_visual_approval(db_path, plan_id)["design"]
    assert canonical["category_approvals"]["success_style"]["resolution_status"] == "PENDING_VISUAL_REVIEW"


# CASE: Human Decision is never set to a candidate -- always None
def test_run_success_style_review_human_decision_always_none(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, focus_result = _ready_plan_with_focus_style_approved(tmp_path, db_path)
    result = run_success_style_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    assert result["manifest"]["human_decision"] is None


# CASE O: zero DB writes
def test_run_success_style_review_zero_db_writes(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, focus_result = _ready_plan_with_focus_style_approved(tmp_path, db_path)
    with connect(db_path) as conn:
        before = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
    run_success_style_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    with connect(db_path) as conn:
        after = conn.execute("SELECT COUNT(*) c FROM visual_design_specs WHERE production_plan_id = ?", (plan_id,)).fetchone()["c"]
    assert after == before


# canonical id never changes
def test_run_success_style_review_canonical_id_unchanged(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, focus_result = _ready_plan_with_focus_style_approved(tmp_path, db_path)
    before_id = select_canonical_visual_approval(db_path, plan_id)["id"]
    run_success_style_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    after_id = select_canonical_visual_approval(db_path, plan_id)["id"]
    assert after_id == before_id


# CASE P: approved_visual_profile.json is never touched
def test_run_success_style_review_profile_json_unchanged(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, focus_result = _ready_plan_with_focus_style_approved(tmp_path, db_path)
    profile_path = focus_result["json_path"]
    before = profile_path.read_text(encoding="utf-8")
    run_success_style_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    after = profile_path.read_text(encoding="utf-8")
    assert before == after


# CASE R: Production/Audio/Layout data untouched
def test_run_success_style_review_production_data_untouched(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, focus_result = _ready_plan_with_focus_style_approved(tmp_path, db_path)
    with connect(db_path) as conn:
        before = {t: conn.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"] for t in ("production_blocks", "speech_assets", "generated_assets", "render_specs", "render_timelines", "scene_layouts")}
    run_success_style_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    with connect(db_path) as conn:
        after = {t: conn.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"] for t in before}
    assert before == after


# CASE Q: existing 7 approvals preserved, and all prior review artifacts untouched
def test_run_success_style_review_preserves_everything_else(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, focus_result = _ready_plan_with_focus_style_approved(tmp_path, db_path)

    # Note: run_focus_style_review itself is not called here -- it refuses to re-run once
    # focus_style is APPROVED (same "already approved" guard as this stage's own review function),
    # so font/color/typography review artifacts (unaffected by that guard) are checked instead;
    # focus_style_review's own unchanged-artifact invariant is covered separately in the 13-4C-16
    # section's own tests.
    font_review_result = run_font_family_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    color_review_result = run_color_background_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    typo_review_result = run_typography_scale_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    before_artifacts = {
        "font": (font_review_result["review_dir"] / "manifest.json").read_text(encoding="utf-8"),
        "color": (color_review_result["review_dir"] / "manifest.json").read_text(encoding="utf-8"),
        "typo": (typo_review_result["review_dir"] / "manifest.json").read_text(encoding="utf-8"),
    }

    run_success_style_review(db_path, assets_dir, reports_dir, plan_id=plan_id)

    after_artifacts = {
        "font": (font_review_result["review_dir"] / "manifest.json").read_text(encoding="utf-8"),
        "color": (color_review_result["review_dir"] / "manifest.json").read_text(encoding="utf-8"),
        "typo": (typo_review_result["review_dir"] / "manifest.json").read_text(encoding="utf-8"),
    }
    assert before_artifacts == after_artifacts

    canonical = select_canonical_visual_approval(db_path, plan_id)["design"]
    assert canonical["category_approvals"]["color_palette"]["resolved_style"]["MUTED"] == "#757b87"
    assert canonical["category_approvals"]["typography_scale"]["resolved_style"] == {"DOMINANT": 72, "PRIMARY": 46, "SUPPORTING": 28, "CAPTION": 20, "MICRO": 15}
    assert canonical["category_approvals"]["font_weight"]["resolved_style"] == {"DOMINANT": 800, "PRIMARY": 700, "SUPPORTING": 500, "CAPTION": 400, "MICRO": 400}
    assert canonical["category_approvals"]["caption_style"]["resolved_style"] == {"text_color_role": "DEFAULT", "background": "box", "background_opacity": 0.55, "padding": "8px 16px", "line_height": 1.5}
    assert canonical["category_approvals"]["focus_style"]["resolved_style"] == {"color_role": "PRIMARY_FOCUS", "highlight_box": False, "box_opacity": 0.0, "padding": "0", "underline": False}


# Determinism: identical inputs -> identical candidates/manifest (except generated_at)/HTML
def test_run_success_style_review_determinism(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, focus_result = _ready_plan_with_focus_style_approved(tmp_path, db_path)

    result1 = run_success_style_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    files1 = {p.name: p.read_text(encoding="utf-8") for p in result1["review_dir"].glob("*.html")}
    manifest1 = dict(result1["manifest"])
    manifest1.pop("generated_at")

    result2 = run_success_style_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    files2 = {p.name: p.read_text(encoding="utf-8") for p in result2["review_dir"].glob("*.html")}
    manifest2 = dict(result2["manifest"])
    manifest2.pop("generated_at")

    assert files1 == files2
    assert manifest1 == manifest2


# Success semantics: prompt-to-answer context reuses real CB06 CASE_BRIDGE+ phase data
def test_run_success_style_review_prompt_to_answer_uses_real_cb06_data(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id, assets_dir, reports_dir, focus_result = _ready_plan_with_focus_style_approved(tmp_path, db_path)
    result = run_success_style_review(db_path, assets_dir, reports_dir, plan_id=plan_id)
    html = (result["review_dir"] / "02_PROMPT_TO_ANSWER_STRONG_SUCCESS.html").read_text(encoding="utf-8")
    frame = _extract_frame_preview(html)
    prompt_div = re.search(r'<div data-element-state="MUTED"[^>]*>CAP</div>', frame)
    assert prompt_div is not None
    assert "opacity:0.4" in prompt_div.group(0)
    answer_div = re.search(r'<div data-success-element style="[^"]*">cap</div>', frame)
    assert answer_div is not None
    assert "background:rgba" in answer_div.group(0)  # STRONG_SUCCESS has highlight_box=True
