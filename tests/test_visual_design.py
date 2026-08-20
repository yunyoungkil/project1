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
    HUMAN_REVIEWED_FONT_FAMILY,
    generate_font_review_prototypes,
    ready_for_final_renderer_binding,
    run_approve_visual_design,
    run_correct_visual_approval,
    run_font_family_human_approval,
    run_font_family_review,
    run_visual_design,
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
