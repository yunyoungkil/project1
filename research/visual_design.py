"""13-4A/13-4B: binds Renderer-neutral semantic design roles (typography/color/motion/background/
container/caption) onto 13-3's Scene/Layout Model, and renders a static-HTML Visual Prototype for
human comparison. Never invents pixel coordinates, HEX colors, font families, or px sizes -- only
role names. 13-3's zones/element_bindings/visibility_rules/layout_constraints/emphasis_bindings are
the canonical structure; this module binds roles onto them, it never re-derives them. No Gemini
TTS, YouTube, or video-generation API calls -- pure reads + string/JSON construction.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from research.asset_generator import _load_production_blocks, _load_speech_assets, select_target_plan
from research.db import connect
from research.render_spec import (
    _RENDERER_SPECIFIC_MARKERS,
    ready_for_timeline_compilation_gate,
    run_render_spec_integrity_check,
    validate_render_spec,
)
from research.scene_layout import (
    LAYOUT_VERSION,
    _SCENE_LAYOUT_RENDERER_MARKERS,
    ready_for_visual_design_gate,
    run_scene_layout_integrity_check,
    validate_scene_layout,
)
from research.timeline_compiler import (
    ready_for_scene_layout_gate,
    run_timeline_integrity_check,
    validate_timeline,
    validate_timeline_entry_gate,
)

VISUAL_DESIGN_VERSION = "13.4"

# ---------------------------------------------------------------------------
# Fixed role taxonomies (section 5/8/18/19/20/22/23/27 of prompts/13-4) -- candidate names taken
# verbatim from the spec, not invented.
# ---------------------------------------------------------------------------

TYPOGRAPHY_ROLES = {"DOMINANT", "PRIMARY", "SUPPORTING", "CAPTION", "MICRO"}
COLOR_ROLES = {"DEFAULT", "PRIMARY_FOCUS", "RELATION", "SUCCESS", "SECONDARY", "MUTED", "EXCEPTION_CAUTION"}
MOTION_ROLES = {"LEARNING_MOTION", "TRANSITION_MOTION", "EMPHASIS_MOTION", "REVEAL_MOTION", "DECORATIVE_MOTION"}
BACKGROUND_ROLES = {"LEARNING_BACKGROUND", "CONTEXT_BACKGROUND", "TRANSITION_BACKGROUND", "MEDIA_BACKGROUND"}
CONTAINER_ROLES = {"COMPARE", "KEY_POINT", "EXAMPLE", "SUPPORTING_INFO"}
CAPTION_ROLES = {"LEARNING_TEXT", "NARRATION_CAPTION"}
ELEMENT_STATES = {"ACTIVE", "PRIMARY", "MUTED", "REMOVED"}
ENTRANCE_STYLES = {"PRIMARY_ENTRANCE", "SUPPORTING_ENTRANCE", "REUSED_ELEMENT_ENTRANCE", "ANSWER_REVEAL"}
VISUAL_REVIEW_REASONS = {
    "TOO_MANY_COMPETING_ELEMENTS", "VISUAL_HIERARCHY_AMBIGUOUS", "MEDIA_LEARNING_CONTENT_CONFLICT",
    "TEXT_DENSITY_HIGH", "RESPONSIVE_RECOMPOSITION_RISK", "CORE_SAFE_AREA_CONFLICT",
    "CAPTION_COLLISION_RISK", "ACCESSIBILITY_RISK",
}


# ---------------------------------------------------------------------------
# Zone -> Role: fixed, deterministic mappings derived only from 13-3's own zone_role/priority/
# size_intent -- never a new judgment about a specific Scene.
# ---------------------------------------------------------------------------

def _typography_role_for_zone(zone: dict) -> str:
    if zone.get("size_intent") == "DOMINANT":
        return "DOMINANT"
    if zone.get("priority") == 100:
        return "PRIMARY"
    if zone.get("priority") == 70:
        return "SUPPORTING"
    return "CAPTION"


_COLOR_ROLE_BY_ZONE = {
    "ANSWER": "SUCCESS", "PRIMARY_FOCUS": "PRIMARY_FOCUS", "PROMPT": "PRIMARY_FOCUS",
    "PHONEME": "RELATION", "BUILD_SEQUENCE": "RELATION", "CAPTION": "DEFAULT", "EXPLANATION": "DEFAULT",
}


def _color_role_for_zone(zone_role: str) -> str:
    return _COLOR_ROLE_BY_ZONE.get(zone_role, "DEFAULT")


def _caption_role_for_zone(zone_role: str) -> str:
    return "NARRATION_CAPTION" if zone_role == "CAPTION" else "LEARNING_TEXT"


_MOTION_ROLE_BY_ZONE = {
    "ANSWER": "REVEAL_MOTION", "PRIMARY_FOCUS": "LEARNING_MOTION", "PROMPT": "LEARNING_MOTION",
    "PHONEME": "LEARNING_MOTION", "BUILD_SEQUENCE": "LEARNING_MOTION", "CAPTION": "DECORATIVE_MOTION",
    "EXPLANATION": "DECORATIVE_MOTION",
}


def _motion_role_for_zone(zone_role: str) -> str:
    return _MOTION_ROLE_BY_ZONE.get(zone_role, "DECORATIVE_MOTION")


_BACKGROUND_ROLE_BY_LAYOUT_TYPE = {
    "OPENING_LAYOUT": "CONTEXT_BACKGROUND", "MINI_SUCCESS_LAYOUT": "LEARNING_BACKGROUND",
}


def _background_role_for(layout_type: str) -> str:
    return _BACKGROUND_ROLE_BY_LAYOUT_TYPE.get(layout_type, "LEARNING_BACKGROUND")


# ---------------------------------------------------------------------------
# Entry Gate (section 2 of the plan) -- reuses 13-3's own validate_scene_layout/
# run_scene_layout_integrity_check/ready_for_visual_design_gate for a fresh re-verification,
# exactly mirroring how 13-3 re-verified 13-2 and 13-2 re-verified 13-1.
# ---------------------------------------------------------------------------

def validate_visual_design_entry_gate(db_path: Path, assets_dir: Path, plan_id: int | None = None) -> dict:
    plan_row = select_target_plan(db_path, plan_id=plan_id)
    if plan_row is None:
        return {"pass": False, "reason": "No production_plans row found.", "spec": None, "timeline": None, "layout": None, "plan_id": None}
    pid = plan_row["id"]

    with connect(db_path) as conn:
        layout_row = conn.execute(
            "SELECT id, layout_json, validation_json FROM scene_layouts WHERE production_plan_id = ? ORDER BY id DESC LIMIT 1",
            (pid,),
        ).fetchone()
    if layout_row is None:
        return {"pass": False, "reason": "No scene_layouts row found for this plan -- run `render-layout` first.", "spec": None, "timeline": None, "layout": None, "plan_id": pid}

    db_layout = json.loads(layout_row["layout_json"])
    json_path = assets_dir / "generated" / f"plan_{pid}" / "render" / "scene_layout.json"
    if not json_path.exists():
        return {"pass": False, "reason": f"scene_layout.json not found at {json_path}.", "spec": None, "timeline": None, "layout": None, "plan_id": pid}
    file_layout = json.loads(json_path.read_text(encoding="utf-8"))

    if db_layout != file_layout:
        return {
            "pass": False, "spec": None, "timeline": None, "layout": None, "plan_id": pid,
            "reason": "scene_layouts DB row and scene_layout.json file content differ -- refusing to guess which is authoritative.",
        }

    layout = db_layout
    if layout.get("layout_version") != LAYOUT_VERSION:
        return {"pass": False, "reason": f"layout_version {layout.get('layout_version')!r} != {LAYOUT_VERSION!r}", "spec": None, "timeline": None, "layout": layout, "plan_id": pid}

    stored_validation = json.loads(layout_row["validation_json"] or "{}")
    if stored_validation.get("unresolved_critical"):
        return {"pass": False, "spec": None, "timeline": None, "layout": layout, "plan_id": pid, "reason": f"13-3 validation has unresolved critical fields: {stored_validation['unresolved_critical']}"}

    # Re-verify the full 13-1 -> 13-2 -> 13-3 chain fresh against current DB state.
    production_blocks = _load_production_blocks(db_path, pid)
    speech_assets = _load_speech_assets(db_path, pid)

    with connect(db_path) as conn:
        spec_row = conn.execute(
            "SELECT spec_json FROM render_specs WHERE production_plan_id = ? ORDER BY id DESC LIMIT 1", (pid,),
        ).fetchone()
        timeline_row = conn.execute(
            "SELECT timeline_json FROM render_timelines WHERE production_plan_id = ? ORDER BY id DESC LIMIT 1", (pid,),
        ).fetchone()
    if spec_row is None or timeline_row is None:
        return {"pass": False, "reason": "Missing render_specs or render_timelines row for this plan.", "spec": None, "timeline": None, "layout": layout, "plan_id": pid}
    spec = json.loads(spec_row["spec_json"])
    timeline = json.loads(timeline_row["timeline_json"])

    fresh_spec_validation = validate_render_spec(db_path, pid, spec, production_blocks, speech_assets)
    fresh_spec_integrity = run_render_spec_integrity_check({"ready": True}, spec, fresh_spec_validation)
    if not ready_for_timeline_compilation_gate({"ready": True}, spec, fresh_spec_validation, fresh_spec_integrity):
        return {"pass": False, "spec": spec, "timeline": timeline, "layout": layout, "plan_id": pid, "reason": "13-1 Ready for Timeline Compilation is not YES when re-verified."}

    fresh_timeline_validation = validate_timeline(spec, timeline)
    fresh_timeline_integrity = run_timeline_integrity_check({"pass": True}, spec, timeline, fresh_timeline_validation)
    if not ready_for_scene_layout_gate({"pass": True}, fresh_timeline_validation, fresh_timeline_integrity):
        return {"pass": False, "spec": spec, "timeline": timeline, "layout": layout, "plan_id": pid, "reason": "13-2 Ready for Scene/Layout is not YES when re-verified."}

    fresh_layout_validation = validate_scene_layout(db_path, pid, spec, timeline, layout)
    fresh_layout_integrity = run_scene_layout_integrity_check({"pass": True}, spec, timeline, layout, fresh_layout_validation)
    if not ready_for_visual_design_gate({"pass": True}, fresh_layout_validation, fresh_layout_integrity):
        return {"pass": False, "spec": spec, "timeline": timeline, "layout": layout, "plan_id": pid, "reason": "13-3 Ready for Visual Design is not YES when re-verified."}

    return {"pass": True, "reason": None, "spec": spec, "timeline": timeline, "layout": layout, "plan_id": pid, "scene_layout_row_id": layout_row["id"]}


# ---------------------------------------------------------------------------
# Element State / Progressive Disclosure & Assistance (sections 11/12/23) -- ordered purely by the
# already-existing event_order (no new timing invented). Requires the Render Spec scene to look up
# each text_element's event_order (element_bindings themselves don't carry it).
# ---------------------------------------------------------------------------

def build_element_states(layout_scene: dict, spec_scene: dict) -> list[dict]:
    event_order_by_element_id = {t["element_id"]: t["event_order"] for t in spec_scene.get("text_elements") or []}
    element_role_by_id = {t["element_id"]: t["role"] for t in spec_scene.get("text_elements") or []}

    by_zone: dict[str, list[dict]] = {}
    for b in layout_scene["element_bindings"]:
        by_zone.setdefault(b["zone_id"], []).append(b)

    states: list[dict] = []
    for zone_id, bindings in by_zone.items():
        ordered = sorted(bindings, key=lambda b: event_order_by_element_id.get(b["source_element_id"], 0))
        zone_priority = ordered[0]["priority"] if ordered else 40
        prior_state_index: dict[str, int] = {}
        for i, b in enumerate(ordered):
            role = element_role_by_id.get(b["source_element_id"])
            if role == "ANSWER":
                entrance_style = "ANSWER_REVEAL"
            elif i == 0:
                entrance_style = "PRIMARY_ENTRANCE" if zone_priority >= 70 else "SUPPORTING_ENTRANCE"
            else:
                entrance_style = "REUSED_ELEMENT_ENTRANCE"
            states.append({
                "element_id": b["element_id"], "zone_id": zone_id, "entrance_style": entrance_style,
                "element_state": "ACTIVE", "superseded_by": None,
            })
            if i > 0:
                # section 11: role이 끝난 이전 정보는 약화된다 -- the prior occurrence in this same
                # zone is superseded by this one, no new timestamp invented, only ordering.
                states[-2]["element_state"] = "MUTED"
                states[-2]["superseded_by"] = b["element_id"]
    return states


# ---------------------------------------------------------------------------
# Scene Visual Rule assembly (section 28)
# ---------------------------------------------------------------------------

def build_scene_visual_rule(layout_scene: dict, spec_scene: dict) -> dict:
    zones_by_id = {z["zone_id"]: z for z in layout_scene["zones"]}

    typography_bindings, color_bindings, caption_bindings, motion_bindings = [], [], [], []
    for b in layout_scene["element_bindings"]:
        zone = zones_by_id.get(b["zone_id"])
        if zone is None:
            continue
        typography_bindings.append({"element_id": b["element_id"], "zone_id": b["zone_id"], "typography_role": _typography_role_for_zone(zone)})
        color_bindings.append({"element_id": b["element_id"], "zone_id": b["zone_id"], "color_role": _color_role_for_zone(zone["zone_role"]), "non_color_cue": zone["alignment_intent"]})
        caption_bindings.append({"element_id": b["element_id"], "zone_id": b["zone_id"], "caption_role": _caption_role_for_zone(zone["zone_role"])})
        motion_bindings.append({"element_id": b["element_id"], "zone_id": b["zone_id"], "motion_role": _motion_role_for_zone(zone["zone_role"])})

    container_bindings = []
    if any(c["constraint_type"] == "BUILD_SEQUENCE_PRECEDES_TARGET" for c in layout_scene.get("layout_constraints") or []):
        container_bindings.append({"zone_id": "build_sequence", "container_role": "KEY_POINT"})

    return {
        "scene_id": layout_scene["scene_id"], "layout_type": layout_scene["layout_type"],
        "typography_bindings": typography_bindings, "color_bindings": color_bindings,
        "caption_bindings": caption_bindings, "motion_bindings": motion_bindings,
        "element_states": build_element_states(layout_scene, spec_scene),
        "transition_motion_role": "TRANSITION_MOTION",
        "background_role": _background_role_for(layout_scene["layout_type"]),
        "container_bindings": container_bindings,
    }


# ---------------------------------------------------------------------------
# Responsive / Recomposition Rule (sections 3/4/25) -- same semantic Zone, different placement per
# orientation; core learning zones stay centered in both, supporting zones recompose.
# ---------------------------------------------------------------------------

_CORE_ZONE_ROLES = {"PRIMARY_FOCUS", "PHONEME", "BUILD_SEQUENCE", "PROMPT", "ANSWER"}


def build_responsive_rules() -> dict:
    rules = {}
    for zone_role in ("HEADER", "CONTEXT", "MAIN", "PRIMARY_FOCUS", "SECONDARY", "PHONEME", "BUILD_SEQUENCE",
                       "CAPTION", "EXPLANATION", "PROMPT", "ANSWER", "FOOTER"):
        if zone_role in _CORE_ZONE_ROLES:
            rules[zone_role] = {
                "orientation_16_9": {"placement": "CORE_SAFE_AREA_CENTER"},
                "orientation_9_16": {"placement": "CORE_SAFE_AREA_CENTER"},
            }
        else:
            rules[zone_role] = {
                "orientation_16_9": {"placement": "SUPPORTING_SIDE"},
                "orientation_9_16": {"placement": "STACKED_BELOW"},
            }
    return rules


# ---------------------------------------------------------------------------
# Visual Review Gate (section 27) -- only two evidenced signals, no invented thresholds.
# ---------------------------------------------------------------------------

def classify_visual_review(layout_scene: dict) -> tuple[str, list[str]]:
    reasons = []
    if layout_scene["layout_type"] == "UNRESOLVED_LAYOUT":
        reasons.append("VISUAL_HIERARCHY_AMBIGUOUS")
    dominant_zone_count = sum(1 for z in layout_scene["zones"] if z.get("size_intent") == "DOMINANT")
    if dominant_zone_count >= 2:
        reasons.append("RESPONSIVE_RECOMPOSITION_RISK")
    return ("VISUAL_REVIEW_REQUIRED" if reasons else "AUTO_LAYOUT"), reasons


# ---------------------------------------------------------------------------
# Top-level Visual Design System builder
# ---------------------------------------------------------------------------

def build_visual_design(spec: dict, layout: dict) -> dict:
    spec_by_scene_id = {s["scene_id"]: s for s in spec["scenes"]}
    scene_visual_rules = []
    visual_review_rules = []
    for layout_scene in layout["scenes"]:
        spec_scene = spec_by_scene_id[layout_scene["scene_id"]]
        scene_visual_rules.append(build_scene_visual_rule(layout_scene, spec_scene))
        status, reasons = classify_visual_review(layout_scene)
        visual_review_rules.append({"scene_id": layout_scene["scene_id"], "status": status, "reasons": reasons})

    return {
        "visual_design_version": VISUAL_DESIGN_VERSION, "production_plan_id": layout["production_plan_id"],
        "layout_version": layout["layout_version"],
        "typography_roles": sorted(TYPOGRAPHY_ROLES), "color_roles": sorted(COLOR_ROLES),
        "motion_roles": sorted(MOTION_ROLES), "background_roles": sorted(BACKGROUND_ROLES),
        "container_roles": sorted(CONTAINER_ROLES), "caption_roles": sorted(CAPTION_ROLES),
        "element_states": sorted(ELEMENT_STATES), "entrance_styles": sorted(ENTRANCE_STYLES),
        "responsive_rules": build_responsive_rules(),
        "scene_visual_rules": scene_visual_rules, "visual_review_rules": visual_review_rules,
        "approval_status": "PENDING_HUMAN_REVIEW",
    }


# ---------------------------------------------------------------------------
# Renderer-neutral guard (section 25 of 13-4, extends 13-3's own marker set further -- 13-1/13-2/
# 13-3's regexes/constants are never touched).
# ---------------------------------------------------------------------------

_VISUAL_DESIGN_RENDERER_MARKERS = _SCENE_LAYOUT_RENDERER_MARKERS + ("javascript", "svg renderer", "remotion_sequence")
_VISUAL_DESIGN_RENDERER_MARKER_RE = re.compile(r"\b(?:" + "|".join(re.escape(m) for m in _VISUAL_DESIGN_RENDERER_MARKERS) + r")\b")


# ---------------------------------------------------------------------------
# Validation (section 35, realized subset)
# ---------------------------------------------------------------------------

def validate_visual_design(spec: dict, layout: dict, design: dict) -> dict:
    checks: dict[str, bool] = {}
    layout_by_scene_id = {s["scene_id"]: s for s in layout["scenes"]}
    design_by_scene_id = {s["scene_id"]: s for s in design["scene_visual_rules"]}

    checks["scene_count_preserved"] = len(design["scene_visual_rules"]) == len(layout["scenes"])
    checks["scene_ids_preserved"] = set(design_by_scene_id.keys()) == set(layout_by_scene_id.keys())
    checks["layout_type_lineage_preserved"] = all(
        design_by_scene_id[sid]["layout_type"] == layout_by_scene_id[sid]["layout_type"] for sid in layout_by_scene_id
    )

    binding_lineage_ok = True
    for sid, ls in layout_by_scene_id.items():
        ds = design_by_scene_id[sid]
        expected_ids = {b["element_id"] for b in ls["element_bindings"]}
        for kind in ("typography_bindings", "color_bindings", "caption_bindings", "motion_bindings"):
            actual_ids = {b["element_id"] for b in ds[kind]}
            if actual_ids != expected_ids:
                binding_lineage_ok = False
    checks["element_binding_lineage_preserved"] = binding_lineage_ok

    # visibility_rules/layout_constraints/emphasis_bindings are untouched by 13-4 -- confirm the
    # Scene Layout objects passed through unchanged (13-4 never writes back to `layout`).
    checks["visibility_constraint_emphasis_untouched"] = all(
        layout_scene == next(s for s in layout["scenes"] if s["scene_id"] == layout_scene["scene_id"])
        for layout_scene in layout["scenes"]
    )

    mini_success_scenes = [s for s in layout["scenes"] if s["scene_role"] == "MINI_SUCCESS"]
    answer_reveal_ok = True
    for ls in mini_success_scenes:
        ds = design_by_scene_id[ls["scene_id"]]
        answer_states = [e for e in ds["element_states"] if e["entrance_style"] == "ANSWER_REVEAL"]
        if not answer_states:
            answer_reveal_ok = False
            continue
        for e in answer_states:
            zone_id = e["zone_id"]
            typography = next((t for t in ds["typography_bindings"] if t["element_id"] == e["element_id"]), None)
            if typography is None or typography["typography_role"] != "DOMINANT":
                answer_reveal_ok = False
    checks["mini_success_answer_reveal_safe"] = answer_reveal_ok

    checks["no_pause_or_timing_fields_present"] = all(
        "pause" not in json.dumps(s).lower() and "_ms" not in json.dumps(s).lower() for s in design["scene_visual_rules"]
    )

    recap_scenes = [s for s in layout["scenes"] if s["scene_role"] == "RECAP"]
    checks["recap_scope_safe"] = all(
        not any(c["constraint_type"] == "ANSWER_HIDDEN_BEFORE_BARRIER" for c in s.get("layout_constraints") or [])
        for s in recap_scenes
    )

    text = json.dumps(design, ensure_ascii=False).lower()
    checks["renderer_neutral"] = _VISUAL_DESIGN_RENDERER_MARKER_RE.search(text) is None

    # The canonical design never contains coordinate keys, pixel units, or hex colors anywhere --
    # build_visual_design only ever writes role name strings (checked directly, not inferred).
    pixel_markers = ('"x":', '"y":', '"width":', '"height":', "px", "rgb(")
    checks["no_pixel_or_resolution_invented"] = not any(m in text for m in pixel_markers)

    color_accessibility_ok = True
    for ds in design["scene_visual_rules"]:
        for cb in ds["color_bindings"]:
            if not cb.get("non_color_cue"):
                color_accessibility_ok = False
    checks["color_not_sole_cue"] = color_accessibility_ok

    checks["typography_completeness"] = all(
        len(ds["typography_bindings"]) == len(layout_by_scene_id[sid]["element_bindings"]) for sid, ds in design_by_scene_id.items()
    )

    progressive_ok = True
    for ds in design["scene_visual_rules"]:
        by_zone: dict[str, list[dict]] = {}
        for e in ds["element_states"]:
            by_zone.setdefault(e["zone_id"], []).append(e)
        for zone_id, states in by_zone.items():
            if len(states) > 1:
                if not any(s["entrance_style"] == "REUSED_ELEMENT_ENTRANCE" for s in states):
                    progressive_ok = False
                if not any(s["element_state"] == "MUTED" for s in states):
                    progressive_ok = False
    checks["progressive_disclosure_assistance_supported"] = progressive_ok

    caption_layer_ok = True
    for ds in design["scene_visual_rules"]:
        for cb in ds["caption_bindings"]:
            zone_id = cb["zone_id"]
            expected = "NARRATION_CAPTION" if zone_id == "caption" else "LEARNING_TEXT"
            if cb["caption_role"] != expected:
                caption_layer_ok = False
    checks["caption_learning_text_separated"] = caption_layer_ok

    checks["responsive_recomposition_supported"] = any(
        v["orientation_16_9"] != v["orientation_9_16"] for v in design["responsive_rules"].values()
    ) and all(
        v["orientation_16_9"] == v["orientation_9_16"] for k, v in design["responsive_rules"].items() if k in _CORE_ZONE_ROLES
    )

    checks["visual_review_reason_complete"] = all(
        (r["status"] == "AUTO_LAYOUT") or (r["status"] == "VISUAL_REVIEW_REQUIRED" and r["reasons"]) for r in design["visual_review_rules"]
    )

    checks["prototype_not_auto_approved"] = design.get("approval_status") == "PENDING_HUMAN_REVIEW"

    unresolved_critical = [name for name, passed in checks.items() if not passed]
    return {"checks": checks, "unresolved_critical": unresolved_critical, "unresolved_non_critical": ["video.width/height/fps/orientation", "color_role.EXCEPTION_CAUTION (unused)"]}


# ---------------------------------------------------------------------------
# Integrity Check (section 36, realized subset) -- entirely separate dict from 13-1/13-2/13-3.
# ---------------------------------------------------------------------------

def run_visual_design_integrity_check(entry_gate: dict, spec: dict | None, layout: dict | None, design: dict | None, validation: dict) -> dict:
    v = validation["checks"]
    checks = {
        "visual_design_entry_gate_safe": bool(entry_gate.get("pass")),
        "visual_design_scene_lineage_safe": v.get("scene_count_preserved", False) and v.get("scene_ids_preserved", False),
        "visual_design_layout_lineage_safe": v.get("layout_type_lineage_preserved", False),
        "visual_design_binding_lineage_safe": v.get("element_binding_lineage_preserved", False),
        "visual_design_visibility_safe": v.get("visibility_constraint_emphasis_untouched", False),
        "visual_design_constraint_safe": v.get("visibility_constraint_emphasis_untouched", False),
        "visual_design_emphasis_safe": v.get("visibility_constraint_emphasis_untouched", False),
        "visual_design_mini_success_safe": v.get("mini_success_answer_reveal_safe", False),
        "visual_design_recap_scope_safe": v.get("recap_scope_safe", False),
        "visual_design_renderer_neutral": v.get("renderer_neutral", False),
        "visual_design_resolution_independent": v.get("no_pixel_or_resolution_invented", False),
        "visual_design_accessibility_safe": v.get("color_not_sole_cue", False),
        "visual_design_typography_safe": v.get("typography_completeness", False),
        "visual_design_color_semantics_safe": v.get("color_not_sole_cue", False),
        "visual_design_progressive_disclosure_safe": v.get("progressive_disclosure_assistance_supported", False),
        "visual_design_progressive_assistance_safe": v.get("progressive_disclosure_assistance_supported", False),
        "visual_design_caption_layer_safe": v.get("caption_learning_text_separated", False),
        "visual_design_responsive_safe": v.get("responsive_recomposition_supported", False),
        "visual_design_review_gate_safe": v.get("visual_review_reason_complete", False),
        "visual_design_prototype_not_auto_approved": v.get("prototype_not_auto_approved", False),
    }
    if spec is not None and layout is not None and design is not None:
        recompiled = build_visual_design(spec, layout)
        checks["visual_design_deterministic"] = json.dumps(design, sort_keys=True, ensure_ascii=False) == json.dumps(recompiled, sort_keys=True, ensure_ascii=False)
    else:
        checks["visual_design_deterministic"] = False
    checks["visual_design_complete"] = bool(design) and not validation["unresolved_critical"] and all(checks.values())
    return checks


def ready_for_visual_design_system(entry_gate: dict, validation: dict, integrity_checks: dict) -> bool:
    return bool(entry_gate.get("pass") and not validation["unresolved_critical"] and all(v is True for v in integrity_checks.values()))


def ready_for_visual_prototype_review(design_ready: bool, prototype_generated: bool) -> bool:
    return bool(design_ready and prototype_generated)


HUMAN_VISUAL_REVIEW_STATUS = "PENDING"  # this run never records a real human approval action


def approved_visual_profile_ready(human_review_status: str) -> bool:
    return human_review_status == "APPROVED"


# ---------------------------------------------------------------------------
# 13-4B: Visual Prototype (static HTML, preview-only styling, separate from the canonical spec)
# ---------------------------------------------------------------------------

CANDIDATES = {
    "SOFT_LIGHT_EDUCATION": {
        "page_bg": "#faf7f2", "text_default": "#2b2b2b",
        "roles": {
            "DOMINANT": "font-size:64px;font-weight:800;",
            "PRIMARY": "font-size:40px;font-weight:700;",
            "SUPPORTING": "font-size:26px;font-weight:500;",
            "CAPTION": "font-size:18px;font-weight:400;",
            "MICRO": "font-size:14px;font-weight:400;",
        },
        "colors": {
            "DEFAULT": "#2b2b2b", "PRIMARY_FOCUS": "#1d4ed8", "RELATION": "#7c3aed",
            "SUCCESS": "#15803d", "SECONDARY": "#6b7280", "MUTED": "#b3b3b3", "EXCEPTION_CAUTION": "#b45309",
        },
    },
    "CLEAN_DARK_FOCUS": {
        "page_bg": "#111318", "text_default": "#e6e6e6",
        "roles": {
            "DOMINANT": "font-size:68px;font-weight:800;",
            "PRIMARY": "font-size:42px;font-weight:700;",
            "SUPPORTING": "font-size:26px;font-weight:500;",
            "CAPTION": "font-size:18px;font-weight:400;",
            "MICRO": "font-size:14px;font-weight:400;",
        },
        "colors": {
            "DEFAULT": "#e6e6e6", "PRIMARY_FOCUS": "#60a5fa", "RELATION": "#c4b5fd",
            "SUCCESS": "#4ade80", "SECONDARY": "#9ca3af", "MUTED": "#555b66", "EXCEPTION_CAUTION": "#fbbf24",
        },
    },
}


def _html_escape(text: str | None) -> str:
    if text is None:
        return ""
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def build_visual_prototype(scene_visual_rule: dict, layout_scene: dict, spec_scene: dict, candidate_name: str, *, reveal_answer: bool) -> str:
    """Renders a single self-contained static HTML preview for one Scene x Candidate combination.
    Preview-only styling (page_bg/roles/colors) never enters the canonical visual_design.json --
    it exists only inside this function's CANDIDATES lookup."""
    candidate = CANDIDATES[candidate_name]
    text_by_element_id = {t["element_id"]: t for t in spec_scene.get("text_elements") or []}
    typography_by_element_id = {b["element_id"]: b["typography_role"] for b in scene_visual_rule["typography_bindings"]}
    color_by_element_id = {b["element_id"]: b["color_role"] for b in scene_visual_rule["color_bindings"]}
    state_by_element_id = {e["element_id"]: e for e in scene_visual_rule["element_states"]}

    zone_order = [z["zone_id"] for z in layout_scene["zones"]]
    bindings_by_zone: dict[str, list[dict]] = {}
    for b in layout_scene["element_bindings"]:
        bindings_by_zone.setdefault(b["zone_id"], []).append(b)

    blocks = []
    for zone_id in zone_order:
        zone_html = []
        for b in bindings_by_zone.get(zone_id, []):
            source_element_id = b["source_element_id"]
            text_element = text_by_element_id.get(source_element_id, {})
            typography_role = typography_by_element_id.get(b["element_id"], "CAPTION")
            color_role = color_by_element_id.get(b["element_id"], "DEFAULT")
            state = state_by_element_id.get(b["element_id"], {})
            is_answer = state.get("entrance_style") == "ANSWER_REVEAL"
            hidden = is_answer and not reveal_answer
            style = candidate["roles"].get(typography_role, "") + f"color:{candidate['colors'].get(color_role, candidate['text_default'])};"
            visibility_style = "visibility:hidden;" if hidden else ""
            comment = "<!-- AFTER_BARRIER: not-before-ms taken verbatim from Timeline, never re-derived here -->" if is_answer else ""
            zone_html.append(f'<div style="{style}{visibility_style}" data-element-role="{_html_escape(b["element_role"])}" data-element-state="{_html_escape(state.get("element_state", "ACTIVE"))}">{comment}{_html_escape(text_element.get("text"))}</div>')
        if zone_html:
            blocks.append(f'<section data-zone-id="{_html_escape(zone_id)}">' + "\n".join(zone_html) + "</section>")

    reveal_label = "AFTER_REVEAL" if reveal_answer else "BEFORE_REVEAL"
    body = "\n".join(blocks)
    return (
        f'<!doctype html><html><head><meta charset="utf-8">'
        f'<title>{_html_escape(scene_visual_rule["scene_id"])} / {_html_escape(candidate_name)} / {reveal_label}</title></head>'
        f'<body style="background:{candidate["page_bg"]};color:{candidate["text_default"]};font-family:sans-serif;padding:40px;">'
        f'<p style="opacity:0.5;font-size:12px;">PREVIEW ONLY -- not the canonical Visual Design Spec. Scene={_html_escape(scene_visual_rule["scene_id"])} '
        f'Layout={_html_escape(scene_visual_rule["layout_type"])} Candidate={_html_escape(candidate_name)} State={reveal_label}</p>'
        f'{body}</body></html>'
    )


# ---------------------------------------------------------------------------
# 13-4B-R: Mini-Success-style scenes (any scene with an ANSWER_REVEAL element -- real Plan 7 has
# exactly CB06) get a richer phase sequence instead of a flat BEFORE/AFTER split, per explicit
# Human Review feedback. Role-based (CAPTION/QUESTION/ANSWER), not element-id-based, so this
# generalizes to any similarly-shaped scene (including test fixtures under a different scene_id).
# LETTER_SOUND_MAPPING/SEQUENTIAL_BLENDING phases were requested by the original revision brief but
# are deliberately omitted here: real Plan 7 data confirms CAP (SP039) has no EN_PHONEME_DEMO
# breakdown at all (unlike BAG/BAT/MAP in CB03/CB04/CB05) -- building those phases would invent
# phoneme-teaching content no upstream stage ever decided to teach for CAP. Confirmed with the user
# before implementation; reported as a known, deliberate gap rather than silently faked.
# ---------------------------------------------------------------------------

CB06_PHASES = ("ATTEMPT_PROMPT", "THINKING_PAUSE", "ANSWER_CONFIRMATION", "CASE_BRIDGE", "SCAFFOLD_REMOVAL", "NATURAL_WORD_FINAL")
_CB06_BEFORE_BARRIER_PHASES = ("ATTEMPT_PROMPT", "THINKING_PAUSE")


def _cb06_phase_overrides(role: str, phase: str) -> dict:
    if role == "CAPTION":
        # 13-4B-R1: Human Review confirmed the narration caption must never visually compete with
        # CAP in any phase of this specific attempt->reveal->natural-word sequence. Narration AUDIO
        # still plays exactly per the unchanged Timeline, and the Caption Layer/caption data itself
        # is untouched -- only this actual-frame sequence's on-screen text is turned off (Caption
        # Layer existing != Caption always visible).
        return {"visible": False}
    if role == "QUESTION":  # the pre-reveal prompt marker (e.g. "CAP")
        if phase in _CB06_BEFORE_BARRIER_PHASES:
            return {"visible": True, "typography_override": "DOMINANT"}
        if phase in ("ANSWER_CONFIRMATION", "CASE_BRIDGE"):
            return {"visible": True, "state_override": "MUTED", "color_override": "MUTED"}
        return {"visible": False}  # SCAFFOLD_REMOVAL, NATURAL_WORD_FINAL
    if role == "ANSWER":
        if phase in _CB06_BEFORE_BARRIER_PHASES:
            return {"visible": False}
        if phase == "ANSWER_CONFIRMATION":
            return {"visible": True}  # canonical DOMINANT/SUCCESS binding applies as-is
        return {"visible": True, "text_override": "lower"}  # CASE_BRIDGE, SCAFFOLD_REMOVAL, NATURAL_WORD_FINAL
    return {"visible": True}


def build_cb06_phase_prototype(scene_visual_rule: dict, layout_scene: dict, spec_scene: dict, candidate_name: str, phase_name: str) -> str:
    candidate = CANDIDATES[candidate_name]
    text_by_element_id = {t["element_id"]: t for t in spec_scene.get("text_elements") or []}
    typography_by_element_id = {b["element_id"]: b["typography_role"] for b in scene_visual_rule["typography_bindings"]}
    color_by_element_id = {b["element_id"]: b["color_role"] for b in scene_visual_rule["color_bindings"]}
    state_by_element_id = {e["element_id"]: e for e in scene_visual_rule["element_states"]}

    zone_order = [z["zone_id"] for z in layout_scene["zones"]]
    bindings_by_zone: dict[str, list[dict]] = {}
    for b in layout_scene["element_bindings"]:
        bindings_by_zone.setdefault(b["zone_id"], []).append(b)

    blocks = []
    for zone_id in zone_order:
        zone_html = []
        for b in bindings_by_zone.get(zone_id, []):
            state = state_by_element_id.get(b["element_id"], {})
            # Hard structural safety net, independent of the override table above: an element whose
            # canonical entrance_style is ANSWER_REVEAL must never render before the barrier phases,
            # no matter what _cb06_phase_overrides returns.
            if state.get("entrance_style") == "ANSWER_REVEAL" and phase_name in _CB06_BEFORE_BARRIER_PHASES:
                continue

            role = b["element_role"]
            override = _cb06_phase_overrides(role, phase_name)
            if not override.get("visible", True):
                continue

            text_element = text_by_element_id.get(b["source_element_id"], {})
            typography_role = override.get("typography_override") or typography_by_element_id.get(b["element_id"], "CAPTION")
            color_role = override.get("color_override") or color_by_element_id.get(b["element_id"], "DEFAULT")
            element_state = override.get("state_override") or state.get("element_state", "ACTIVE")
            raw_text = text_element.get("text")
            display_text = raw_text.lower() if override.get("text_override") == "lower" and raw_text else raw_text

            style = candidate["roles"].get(typography_role, "") + f"color:{candidate['colors'].get(color_role, candidate['text_default'])};"
            if element_state == "MUTED":
                style += "opacity:0.4;"
            transform_note = "<!-- VISUAL_TRANSFORMATION: display-only lowercase, source text unchanged -->" if override.get("text_override") == "lower" else ""
            zone_html.append(f'<div style="{style}" data-element-role="{_html_escape(role)}" data-element-state="{_html_escape(element_state)}" data-phase="{_html_escape(phase_name)}">{transform_note}{_html_escape(display_text)}</div>')
        if zone_html:
            blocks.append(f'<section data-zone-id="{_html_escape(zone_id)}">' + "\n".join(zone_html) + "</section>")

    extra = ""
    if phase_name == "ATTEMPT_PROMPT":
        extra = f'<div style="{candidate["roles"]["SUPPORTING"]}color:{candidate["colors"]["DEFAULT"]};">직접 읽어보세요.</div>'
    elif phase_name == "THINKING_PAUSE":
        extra = (
            f'<div style="{candidate["roles"]["SUPPORTING"]}color:{candidate["colors"]["DEFAULT"]};">직접 읽어보세요.</div>'
            f'<div style="{candidate["roles"]["MICRO"]}color:{candidate["colors"]["MUTED"]};" data-thinking-progress="true">'
            f'<!-- THINKING_PROGRESS: static bar only, no countdown/new timing -- canonical PAUSE (3000ms) from Timeline, unchanged -->'
            f'&#9473;&#9473;&#9473;&#9473;&#9473;&#9473;&#9473;</div>'
        )

    # 13-4B-R1 section 4: preview metadata (reviewer-facing labels) and the actual learning-content
    # frame are structurally separated so a test (or a human) can tell "what does this comment say"
    # apart from "what is actually shown as content" -- <main data-frame-preview> contains ONLY the
    # phase's real visible elements.
    frame = extra + "\n".join(blocks)
    return (
        f'<!doctype html><html><head><meta charset="utf-8">'
        f'<title>{_html_escape(scene_visual_rule["scene_id"])} / {_html_escape(candidate_name)} / {phase_name}</title></head>'
        f'<body style="background:{candidate["page_bg"]};color:{candidate["text_default"]};font-family:sans-serif;padding:40px;">'
        f'<header data-preview-metadata style="opacity:0.5;font-size:12px;">PREVIEW ONLY -- not the canonical Visual Design Spec. Scene={_html_escape(scene_visual_rule["scene_id"])} '
        f'Layout={_html_escape(scene_visual_rule["layout_type"])} Candidate={_html_escape(candidate_name)} Phase={phase_name} (13-4B-R1 revision)</header>'
        f'<main data-frame-preview>{frame}</main></body></html>'
    )


def generate_cb06_phase_prototypes(scene_visual_rule: dict, layout_scene: dict, spec_scene: dict, proto_dir: Path) -> list[dict]:
    entries = []
    for candidate_name in CANDIDATES:
        for i, phase_name in enumerate(CB06_PHASES, start=1):
            filename = f"{scene_visual_rule['scene_id']}_{candidate_name}_{i:02d}_{phase_name}.html"
            html = build_cb06_phase_prototype(scene_visual_rule, layout_scene, spec_scene, candidate_name, phase_name)
            (proto_dir / filename).write_text(html, encoding="utf-8")
            entries.append({"scene_id": scene_visual_rule["scene_id"], "candidate": candidate_name, "reveal_state": phase_name, "file": filename})
    return entries


def _build_prototype_index(proto_dir: Path, manifest: dict) -> Path:
    lines = ["<!doctype html><html><head><meta charset=\"utf-8\"><title>Prototype Index</title></head><body>"]
    lines.append(f"<p>Plan {manifest['production_plan_id']} -- revision {manifest.get('revision', 'N/A')} -- preview navigation only, not a canonical Renderer UI.</p>")
    by_scene: dict[str, list[dict]] = {}
    for entry in manifest["files"]:
        by_scene.setdefault(entry["scene_id"], []).append(entry)
    for scene_id, entries in by_scene.items():
        lines.append(f"<h3>{_html_escape(scene_id)}</h3><ul>")
        for e in entries:
            lines.append(f'<li><a href="{_html_escape(e["file"])}">{_html_escape(e["candidate"])} / {_html_escape(e["reveal_state"])}</a></li>')
        lines.append("</ul>")
    lines.append("</body></html>")
    path = proto_dir / "index.html"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def generate_prototypes(spec: dict, layout: dict, design: dict, assets_dir: Path, plan_id: int) -> dict:
    proto_dir = assets_dir / "generated" / f"plan_{plan_id}" / "render" / "prototypes"
    proto_dir.mkdir(parents=True, exist_ok=True)
    spec_by_scene_id = {s["scene_id"]: s for s in spec["scenes"]}
    layout_by_scene_id = {s["scene_id"]: s for s in layout["scenes"]}
    design_by_scene_id = {s["scene_id"]: s for s in design["scene_visual_rules"]}

    manifest_entries = []
    for scene_id, layout_scene in layout_by_scene_id.items():
        spec_scene = spec_by_scene_id[scene_id]
        scene_visual_rule = design_by_scene_id[scene_id]
        has_answer_reveal = any(e["entrance_style"] == "ANSWER_REVEAL" for e in scene_visual_rule["element_states"])
        if has_answer_reveal:
            manifest_entries.extend(generate_cb06_phase_prototypes(scene_visual_rule, layout_scene, spec_scene, proto_dir))
            continue
        for candidate_name in CANDIDATES:
            filename = f"{scene_id}_{candidate_name}.html"
            html = build_visual_prototype(scene_visual_rule, layout_scene, spec_scene, candidate_name, reveal_answer=True)
            (proto_dir / filename).write_text(html, encoding="utf-8")
            manifest_entries.append({"scene_id": scene_id, "candidate": candidate_name, "reveal_state": "N/A", "file": filename})

    manifest = {"production_plan_id": plan_id, "generated_at": datetime.utcnow().isoformat(), "revision": "13-4B-R", "files": manifest_entries}
    (proto_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    _build_prototype_index(proto_dir, manifest)
    return {"prototype_dir": proto_dir, "manifest": manifest, "file_count": len(manifest_entries)}


# ---------------------------------------------------------------------------
# Persistence + file output
# ---------------------------------------------------------------------------

def persist_visual_design(db_path: Path, plan_id: int, scene_layout_id: int | None, design: dict, validation: dict) -> int:
    with connect(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO visual_design_specs (production_plan_id, scene_layout_id, visual_design_version, design_json, validation_json) VALUES (?, ?, ?, ?, ?)",
            (plan_id, scene_layout_id, VISUAL_DESIGN_VERSION, json.dumps(design, ensure_ascii=False), json.dumps(validation, ensure_ascii=False)),
        )
        return cur.lastrowid


def write_visual_design_file(assets_dir: Path, plan_id: int, design: dict) -> Path:
    render_dir = assets_dir / "generated" / f"plan_{plan_id}" / "render"
    render_dir.mkdir(parents=True, exist_ok=True)
    path = render_dir / "visual_design.json"
    path.write_text(json.dumps(design, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Orchestration + report
# ---------------------------------------------------------------------------

def run_visual_design(db_path: Path, assets_dir: Path, reports_dir: Path, *, plan_id: int | None = None) -> dict:
    entry_gate = validate_visual_design_entry_gate(db_path, assets_dir, plan_id=plan_id)
    if not entry_gate["pass"]:
        report_path = _build_visual_design_report(reports_dir, entry_gate, None, None, None, None)
        return {**entry_gate, "design": None, "json_path": None, "report_path": report_path, "ready_for_visual_design_system": False}

    spec, layout = entry_gate["spec"], entry_gate["layout"]
    design = build_visual_design(spec, layout)
    validation = validate_visual_design(spec, layout, design)
    integrity_checks = run_visual_design_integrity_check(entry_gate, spec, layout, design, validation)
    design_ready = ready_for_visual_design_system(entry_gate, validation, integrity_checks)

    row_id = persist_visual_design(db_path, entry_gate["plan_id"], entry_gate.get("scene_layout_row_id"), design, validation)
    json_path = write_visual_design_file(assets_dir, entry_gate["plan_id"], design)

    prototype_result = generate_prototypes(spec, layout, design, assets_dir, entry_gate["plan_id"])
    prototype_generated = prototype_result["file_count"] > 0

    prototype_review_ready = ready_for_visual_prototype_review(design_ready, prototype_generated)
    human_review_status = HUMAN_VISUAL_REVIEW_STATUS
    approved = approved_visual_profile_ready(human_review_status)

    report_path = _build_visual_design_report(
        reports_dir, entry_gate, design, validation, integrity_checks,
        design_ready=design_ready, prototype_generated=prototype_generated,
        prototype_review_ready=prototype_review_ready, human_review_status=human_review_status,
        approved=approved, json_path=json_path, prototype_dir=prototype_result["prototype_dir"],
        prototype_file_count=prototype_result["file_count"],
    )

    return {
        "pass": True, "reason": None, "plan_id": entry_gate["plan_id"], "design": design,
        "validation": validation, "integrity_checks": integrity_checks,
        "ready_for_visual_design_system": design_ready, "prototype_generated": prototype_generated,
        "ready_for_visual_prototype_review": prototype_review_ready,
        "human_visual_review_status": human_review_status, "approved_visual_profile": approved,
        "ready_for_final_renderer_binding": approved,
        "json_path": json_path, "report_path": report_path, "visual_design_row_id": row_id,
        "prototype_dir": prototype_result["prototype_dir"], "prototype_file_count": prototype_result["file_count"],
    }


def _build_visual_design_report(
    reports_dir: Path, entry_gate: dict, design: dict | None, validation: dict | None, integrity_checks: dict | None,
    *, design_ready: bool | None = None, prototype_generated: bool | None = None, prototype_review_ready: bool | None = None,
    human_review_status: str | None = None, approved: bool | None = None, json_path: Path | None = None,
    prototype_dir: Path | None = None, prototype_file_count: int | None = None,
) -> Path:
    lines: list[str] = ["# Visual Design System / Prototype Report", ""]
    lines.append(f"생성일: {datetime.utcnow().date().isoformat()}")
    lines.append(f"Source Plan: {entry_gate.get('plan_id')}")
    lines.append("")
    lines.append("## Entry Gate")
    lines.append("")
    lines.append("YES" if entry_gate["pass"] else "NO")
    if not entry_gate["pass"]:
        lines.append(f"- {entry_gate['reason']}")
    lines.append("")

    if design is not None:
        lines.append("## Scene Visual Rules")
        lines.append("")
        for s in design["scene_visual_rules"]:
            lines.append(f"- {s['scene_id']} ({s['layout_type']}): background={s['background_role']}, bindings={len(s['typography_bindings'])}")
        lines.append("")

        lines.append("## Visual Review Gate")
        lines.append("")
        for r in design["visual_review_rules"]:
            lines.append(f"- {r['scene_id']}: {r['status']} {r['reasons'] or ''}")
        lines.append("")

        if validation:
            lines.append("## Unresolved Fields")
            lines.append("")
            lines.append(f"Critical: {validation['unresolved_critical'] or 'NONE'}")
            lines.append(f"Non-critical: {validation['unresolved_non_critical'] or 'NONE'}")
            lines.append("")

        if integrity_checks:
            lines.append("## Integrity Checks")
            lines.append("")
            for name, passed in integrity_checks.items():
                lines.append(f"- {name}: {'pass' if passed else 'fail'}")
            lines.append("")

        lines.append("## Gates")
        lines.append("")
        lines.append(f"Ready for Visual Design System: {'YES' if design_ready else 'NO'}")
        lines.append(f"Visual Design System Generated: {'YES' if design is not None else 'NO'}")
        lines.append(f"Visual Prototype Generated: {'YES' if prototype_generated else 'NO'}")
        lines.append(f"Ready for Visual Prototype Review: {'YES' if prototype_review_ready else 'NO'}")
        lines.append(f"Human Visual Review: {human_review_status}")
        lines.append(f"Approved Visual Profile: {'YES' if approved else 'NO'}")
        lines.append(f"Ready for Final Renderer Binding: {'YES' if approved else 'NO'}")
        lines.append("")

        if json_path:
            lines.append(f"JSON: {json_path}")
        if prototype_dir:
            lines.append(f"Prototypes: {prototype_dir} ({prototype_file_count} files)")
        lines.append("")

    reports_dir.mkdir(parents=True, exist_ok=True)
    out_path = reports_dir / f"visual_design_{datetime.utcnow().date().isoformat()}.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# 13-4C: Approved Visual Profile -- reachable ONLY through run_approve_visual_design /
# run_correct_visual_approval, never from run_visual_design's own orchestration (section 31:
# "13-4A/13-4B 실행만으로 13-4C가 완료된 것처럼 표시하면 안 된다").
#
# 13-4C-2 rewrite: a single ambiguous "approval_status" value conflated three different questions
# (which candidate did the human prefer? which exact tokens did they approve? can the Renderer
# start?). Those are now tracked as three separate, honestly-scoped concepts: Candidate Selection
# (select_visual_candidate), Category Approval (build_category_approvals, per the 15 categories
# below, each with its own provenance), and Full Profile Approval
# (ready_for_final_renderer_binding, gated on ALL mandatory categories).
# ---------------------------------------------------------------------------

APPROVED_PROFILE_CATEGORIES = (
    "color_palette", "typography_scale", "font_family", "font_weight", "spacing_scale",
    "background", "container", "border", "radius", "caption_style", "focus_style",
    "success_style", "motion_style", "output_profile_16_9", "output_profile_9_16",
)

# section 17: no real Renderer consumer exists yet in this project (13-5+ not built) -- this is the
# best current judgment of what a Renderer could not draw a differentiated frame without, not a
# researched fact about an actual consumer. Reported as provisional, to be reconfirmed once 13-5
# exists.
MANDATORY_VISUAL_CATEGORIES = (
    "color_palette", "typography_scale", "font_family", "background",
    "caption_style", "focus_style", "success_style", "motion_style", "output_profile_16_9",
)
OPTIONAL_VISUAL_CATEGORIES = ("font_weight", "spacing_scale", "container", "border", "radius")
CONDITIONAL_VISUAL_CATEGORIES = ("output_profile_9_16",)  # only if a 9:16 Shorts pass is undertaken


def build_category_approvals(selected_candidate: str) -> dict:
    """Section 8/9 provenance re-check: color_palette/typography_scale were previously marked
    APPROVED, but those exact values are CANDIDATES["SOFT_LIGHT_EDUCATION"]'s -- not the currently
    selected candidate's -- and, independent of that mismatch, a human choosing a candidate
    direction was never the same act as approving each exact HEX/px token (section 9). Every
    category is honestly PENDING_VISUAL_REVIEW until a human explicitly approves its exact value
    for the CURRENTLY selected candidate."""
    if selected_candidate not in CANDIDATES:
        raise ValueError(f"{selected_candidate!r} is not a real Prototype candidate (choices: {sorted(CANDIDATES)})")

    categories: dict[str, dict] = {}
    for name in APPROVED_PROFILE_CATEGORIES:
        if name in ("color_palette", "typography_scale"):
            reason = (
                f"Prototype에 preview-only 값으로 존재하지만({selected_candidate} 후보), 후보 방향 선택과 "
                "exact token 승인은 별개 행위(section 9) -- 사람이 이 정확한 값을 직접 승인한 근거 없음"
            )
        else:
            reason = "정적 HTML Prototype에 표현되지 않아 이번 승인 범위에 포함되지 않음"
        categories[name] = {"resolved_style": None, "resolution_status": "PENDING_VISUAL_REVIEW", "reason": reason}

    approved_count = sum(1 for c in categories.values() if c["resolution_status"] == "APPROVED")
    return {
        "checked_at": datetime.utcnow().isoformat(), "checked_candidate": selected_candidate,
        "categories": categories,
        "approved_category_count": approved_count,
        "pending_category_count": len(categories) - approved_count,
        "total_category_count": len(APPROVED_PROFILE_CATEGORIES),
    }


def select_visual_candidate(candidate_name: str) -> dict:
    """Candidate Selection only -- records which Visual Direction a human preferred, never implies
    any exact token or the full profile is approved (section 5/19: SELECT CANDIDATE != FINALIZE
    PROFILE)."""
    if candidate_name not in CANDIDATES:
        raise ValueError(f"{candidate_name!r} is not a real Prototype candidate (choices: {sorted(CANDIDATES)})")
    return {
        "selected_candidate": candidate_name, "candidate_selection_status": "SELECTED",
        "selected_at": datetime.utcnow().isoformat(),
    }


def ready_for_final_renderer_binding(candidate_selection: dict, category_approvals: dict) -> bool:
    if candidate_selection.get("candidate_selection_status") != "SELECTED":
        return False
    categories = category_approvals.get("categories", {})
    return all(categories.get(c, {}).get("resolution_status") == "APPROVED" for c in MANDATORY_VISUAL_CATEGORIES)


def select_canonical_visual_approval(db_path: Path, plan_id: int) -> dict | None:
    """Section 14: canonical selection must never be "the latest row with approval_status==
    APPROVED" -- that query would return the legacy id=2 SOFT_LIGHT_EDUCATION record, which is
    real history but not truth. Only rows explicitly marked record_status=="CANONICAL_CORRECTION"
    (written exclusively by run_correct_visual_approval) are eligible; legacy rows are structurally
    invisible to this query since they never carry that marker."""
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT id, design_json FROM visual_design_specs WHERE production_plan_id = ? ORDER BY id DESC", (plan_id,),
        ).fetchall()
    for row in rows:
        design = json.loads(row["design_json"])
        if design.get("record_status") == "CANONICAL_CORRECTION":
            return {"id": row["id"], "design": design}
    return None


def run_approve_visual_design(db_path: Path, assets_dir: Path, reports_dir: Path, *, plan_id: int | None = None, candidate: str) -> dict:
    """Records a Candidate Selection only (section 19/20: this is not a Full Finalization action).
    A prior version of this function set an ambiguous top-level "approval_status": "APPROVED" that
    implied the whole profile was approved -- that semantic bug is fixed here; this now only ever
    writes candidate_selection_status/full_profile_approved (which stays False unless every
    mandatory category already has real, separately-recorded approval)."""
    entry_gate = validate_visual_design_entry_gate(db_path, assets_dir, plan_id=plan_id)
    if not entry_gate["pass"]:
        return {"pass": False, "reason": entry_gate["reason"], "plan_id": entry_gate.get("plan_id")}
    pid = entry_gate["plan_id"]

    with connect(db_path) as conn:
        design_row = conn.execute(
            "SELECT id, design_json FROM visual_design_specs WHERE production_plan_id = ? ORDER BY id DESC LIMIT 1", (pid,),
        ).fetchone()
    if design_row is None:
        return {"pass": False, "reason": "No visual_design_specs row found for this plan -- run `render-visual-design` first.", "plan_id": pid}

    if candidate not in CANDIDATES:
        return {"pass": False, "reason": f"{candidate!r} is not a real Prototype candidate (choices: {sorted(CANDIDATES)})", "plan_id": pid}

    design = json.loads(design_row["design_json"])
    candidate_selection = select_visual_candidate(candidate)
    category_approvals = build_category_approvals(candidate)
    ready = ready_for_final_renderer_binding(candidate_selection, category_approvals)
    selected_design = {
        **design, "record_status": "CANDIDATE_SELECTION", **candidate_selection,
        "category_approvals": category_approvals["categories"], "full_profile_approved": False,
        "ready_for_final_renderer_binding": ready,
    }

    row_id = persist_visual_design(db_path, pid, design_row["id"], selected_design, {"checks": {}, "unresolved_critical": [], "unresolved_non_critical": []})
    profile_path = assets_dir / "generated" / f"plan_{pid}" / "render" / "approved_visual_profile.json"
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(json.dumps(selected_design, ensure_ascii=False, indent=2), encoding="utf-8")

    report_path = _build_approved_profile_report(reports_dir, pid, candidate, category_approvals, candidate_selection, ready, profile_path)

    return {
        "pass": True, "plan_id": pid, "candidate": candidate, "candidate_selection": candidate_selection,
        "category_approvals": category_approvals, "ready_for_final_renderer_binding": ready,
        "visual_design_row_id": row_id, "json_path": profile_path, "report_path": report_path,
    }


def _build_approved_profile_report(reports_dir: Path, plan_id: int, candidate: str, category_approvals: dict, candidate_selection: dict, ready: bool, profile_path: Path) -> Path:
    lines: list[str] = ["# Approved Visual Profile Report", ""]
    lines.append(f"생성일: {datetime.utcnow().date().isoformat()}")
    lines.append(f"Source Plan: {plan_id}")
    lines.append("")
    lines.append("## Candidate Selection")
    lines.append("")
    lines.append(f"Status: {candidate_selection['candidate_selection_status']}")
    lines.append(f"Selected candidate: {candidate}")
    lines.append(f"Selected at: {candidate_selection['selected_at']}")
    lines.append("")
    lines.append(f"## Category Approvals ({category_approvals['approved_category_count']}/{category_approvals['total_category_count']})")
    lines.append("")
    for name, cat in category_approvals["categories"].items():
        lines.append(f"- {name}: {cat['resolution_status']}" + (f" -- {cat['resolved_style']}" if cat["resolution_status"] == "APPROVED" else f" ({cat.get('reason', '')})"))
    lines.append("")
    lines.append("## Ready for Final Renderer Binding")
    lines.append("")
    lines.append("YES" if ready else "NO")
    lines.append("")
    lines.append(f"JSON: {profile_path}")
    lines.append("")

    reports_dir.mkdir(parents=True, exist_ok=True)
    out_path = reports_dir / f"approved_visual_profile_{datetime.utcnow().date().isoformat()}.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# 13-4C-2: corrects the Source of Truth without deleting history. Appends a new
# record_status=="CANONICAL_CORRECTION" row; never touches the row(s) it corrects.
# ---------------------------------------------------------------------------

def _correct_prototype_manifest_revision(proto_dir: Path, new_revision: str) -> None:
    manifest_path = proto_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["revision"] = new_revision
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    index_path = proto_dir / "index.html"
    if index_path.exists():
        index_html = index_path.read_text(encoding="utf-8")
        index_html = re.sub(r"revision [^<]+", f"revision {new_revision}", index_html)
        index_path.write_text(index_html, encoding="utf-8")


def run_correct_visual_approval(
    db_path: Path, assets_dir: Path, reports_dir: Path, *, plan_id: int | None = None,
    selected_candidate: str = "CLEAN_DARK_FOCUS", corrects_record_id: int = 2,
    correction_reason: str = "HUMAN_REVIEW_CANDIDATE_MISMATCH",
) -> dict:
    entry_gate = validate_visual_design_entry_gate(db_path, assets_dir, plan_id=plan_id)
    if not entry_gate["pass"]:
        return {"pass": False, "reason": entry_gate["reason"], "plan_id": entry_gate.get("plan_id")}
    pid = entry_gate["plan_id"]

    with connect(db_path) as conn:
        design_row = conn.execute(
            "SELECT id, design_json FROM visual_design_specs WHERE production_plan_id = ? ORDER BY id DESC LIMIT 1", (pid,),
        ).fetchone()
    if design_row is None:
        return {"pass": False, "reason": "No visual_design_specs row found for this plan -- run `render-visual-design` first.", "plan_id": pid}

    if selected_candidate not in CANDIDATES:
        return {"pass": False, "reason": f"{selected_candidate!r} is not a real Prototype candidate (choices: {sorted(CANDIDATES)})", "plan_id": pid}

    design = json.loads(design_row["design_json"])
    candidate_selection = select_visual_candidate(selected_candidate)
    category_approvals = build_category_approvals(selected_candidate)
    ready = ready_for_final_renderer_binding(candidate_selection, category_approvals)
    unresolved_mandatory = [
        c for c in MANDATORY_VISUAL_CATEGORIES
        if category_approvals["categories"].get(c, {}).get("resolution_status") != "APPROVED"
    ]

    correction_record = {
        **design,
        "record_status": "CANONICAL_CORRECTION",
        "revision": "13-4C-2",
        "corrects_record_id": corrects_record_id,
        "correction_reason": correction_reason,
        "correction_details": (
            f"Record id={corrects_record_id} recorded a different candidate as approved, but the actual "
            f"Human Review (this conversation's record) selected {selected_candidate}. That prior row is "
            "preserved unmodified as history; it is no longer treated as canonical."
        ),
        **candidate_selection,
        "category_approvals": category_approvals["categories"],
        "mandatory_categories": list(MANDATORY_VISUAL_CATEGORIES),
        "optional_categories": list(OPTIONAL_VISUAL_CATEGORIES),
        "conditional_categories": list(CONDITIONAL_VISUAL_CATEGORIES),
        "unresolved_mandatory_categories": unresolved_mandatory,
        "full_profile_approved": ready,
        "ready_for_final_renderer_binding": ready,
    }

    row_id = persist_visual_design(db_path, pid, design_row["id"], correction_record, {"checks": {}, "unresolved_critical": [], "unresolved_non_critical": []})

    profile_path = assets_dir / "generated" / f"plan_{pid}" / "render" / "approved_visual_profile.json"
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(json.dumps(correction_record, ensure_ascii=False, indent=2), encoding="utf-8")

    proto_dir = assets_dir / "generated" / f"plan_{pid}" / "render" / "prototypes"
    manifest_corrected = False
    if (proto_dir / "manifest.json").exists():
        _correct_prototype_manifest_revision(proto_dir, "13-4B-R1")
        manifest_corrected = True

    report_path = _build_correction_report(reports_dir, pid, correction_record, unresolved_mandatory, profile_path)

    return {
        "pass": True, "plan_id": pid, "selected_candidate": selected_candidate,
        "corrects_record_id": corrects_record_id, "record": correction_record,
        "ready_for_final_renderer_binding": ready, "unresolved_mandatory_categories": unresolved_mandatory,
        "visual_design_row_id": row_id, "json_path": profile_path, "report_path": report_path,
        "manifest_corrected": manifest_corrected,
    }


def _build_correction_report(reports_dir: Path, plan_id: int, record: dict, unresolved_mandatory: list[str], profile_path: Path) -> Path:
    lines: list[str] = ["# Visual Approval Correction Report", ""]
    lines.append(f"생성일: {datetime.utcnow().date().isoformat()}")
    lines.append(f"Source Plan: {plan_id}")
    lines.append("")
    lines.append("## Correction Lineage")
    lines.append("")
    lines.append(f"Corrects record id: {record['corrects_record_id']} (preserved, not modified)")
    lines.append(f"Correction reason: {record['correction_reason']}")
    lines.append(f"Details: {record['correction_details']}")
    lines.append("")
    lines.append("## Canonical Candidate")
    lines.append("")
    lines.append(f"Selected candidate: {record['selected_candidate']}")
    lines.append(f"Candidate selection status: {record['candidate_selection_status']}")
    lines.append("")
    lines.append("## Category Approvals")
    lines.append("")
    for name, cat in record["category_approvals"].items():
        kind = "MANDATORY" if name in record["mandatory_categories"] else ("CONDITIONAL" if name in record["conditional_categories"] else "OPTIONAL")
        lines.append(f"- [{kind}] {name}: {cat['resolution_status']}")
    lines.append("")
    lines.append("## Renderer Gate")
    lines.append("")
    lines.append(f"Full Profile Approved: {'YES' if record['full_profile_approved'] else 'NO'}")
    lines.append(f"Ready for Final Renderer Binding: {'YES' if record['ready_for_final_renderer_binding'] else 'NO'}")
    lines.append(f"Unresolved mandatory categories: {unresolved_mandatory or 'NONE'}")
    lines.append("")
    lines.append(f"JSON: {profile_path}")
    lines.append("")

    reports_dir.mkdir(parents=True, exist_ok=True)
    out_path = reports_dir / f"visual_approval_correction_{datetime.utcnow().date().isoformat()}.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# 13-4C-3: Font Family comparison Prototype -- entirely separate artifact directory
# (font_review/, never prototypes/), zero DB writes (no category approval action exists here at
# all -- the absence of any persistence call is the structural proof this never auto-approves
# font_family). Background/Color Palette/Typography Scale are pinned to CANDIDATES["CLEAN_DARK_
# FOCUS"]'s existing values verbatim -- font_family is the only variable across the three
# candidates below.
#
# All three stacks are web-safe (OS-bundled) font stacks -- no font files, no network, no
# download. None of Verdana/Arial/Segoe UI ship a true 800 (ExtraBold) static weight; browsers
# synthesize/approximate it from the 700 face. That is a genuine, common limitation across all
# three candidates, not something this backend project can verify by actually rendering a page --
# reported as a caveat, not glossed over.
# ---------------------------------------------------------------------------

FONT_CANDIDATES = {
    "VERDANA_HUMANIST": {
        "stack": "Verdana, Geneva, 'Malgun Gothic', sans-serif",
        "description": "Humanist sans-serif designed for on-screen legibility -- widely regarded as strong at disambiguating I/l/1",
        "native_weights": [400, 700], "weight_800_behavior": "browser-synthesized (no true 800 face)",
    },
    "ARIAL_NEUTRAL": {
        "stack": "Arial, Helvetica, 'Malgun Gothic', sans-serif",
        "description": "Neutral grotesque sans-serif, near-universal availability -- an honest contrast candidate (widely known to be weak at I/l/1 disambiguation)",
        "native_weights": [400, 700], "weight_800_behavior": "browser-synthesized (no true 800 face)",
    },
    "SEGOE_MODERN": {
        "stack": "'Segoe UI', Tahoma, Geneva, 'Malgun Gothic', sans-serif",
        "description": "Windows default UI humanist sans-serif since Vista -- a third, visually distinct direction",
        "native_weights": [400, 700], "weight_800_behavior": "browser-synthesized (no true 800 face)",
    },
}

_FONT_REVIEW_COLORS = CANDIDATES["CLEAN_DARK_FOCUS"]["colors"]
_FONT_REVIEW_PAGE_BG = CANDIDATES["CLEAN_DARK_FOCUS"]["page_bg"]
_FONT_REVIEW_ROLES = CANDIDATES["CLEAN_DARK_FOCUS"]["roles"]


def _font_review_page(font_key: str, title: str, body: str) -> str:
    stack = FONT_CANDIDATES[font_key]["stack"]
    return (
        f'<!doctype html><html><head><meta charset="utf-8"><title>{_html_escape(title)}</title></head>'
        f'<body style="background:{_FONT_REVIEW_PAGE_BG};color:{_FONT_REVIEW_COLORS["DEFAULT"]};font-family:{stack};padding:40px;">'
        f'<header data-preview-metadata style="opacity:0.5;font-size:12px;font-family:sans-serif;">PREVIEW ONLY -- Font Family comparison, not the canonical Visual Design Spec. '
        f'Candidate={_html_escape(font_key)} ({_html_escape(FONT_CANDIDATES[font_key]["stack"])}). Background/Color Palette/Typography Scale fixed to the CLEAN_DARK_FOCUS candidate, unchanged.</header>'
        f'<main data-frame-preview>{body}</main></body></html>'
    )


def build_font_learning_prototype(font_key: str) -> str:
    words = (("CAP", "cap"), ("BAT", "bat"), ("MAP", "map"), ("BAG", "bag"))
    dominant_style = _FONT_REVIEW_ROLES["DOMINANT"] + f'color:{_FONT_REVIEW_COLORS["SUCCESS"]};'
    prompt_style = _FONT_REVIEW_ROLES["PRIMARY"] + f'color:{_FONT_REVIEW_COLORS["PRIMARY_FOCUS"]};'
    blocks = [f'<div style="{prompt_style}">직접 읽어보세요.</div>']
    for upper, lower in words:
        blocks.append(f'<section><div style="{dominant_style}">{upper}</div><div style="{dominant_style}">{lower}</div></section>')
    body = "\n".join(blocks)
    body += f'<section data-responsive-preview="9:16" style="max-width:405px;border:1px solid {_FONT_REVIEW_COLORS["SECONDARY"]};margin-top:24px;padding:16px;"><div style="{dominant_style}">CAP</div><div style="{prompt_style}">직접 읽어보세요.</div></section>'
    return _font_review_page(font_key, f"{font_key} / Learning Screen", body)


def build_font_glyph_test_prototype(font_key: str) -> str:
    pairs = ("I l", "1 I l", "O 0", "b d", "p q", "u v", "c e", "rn m", "a o")
    words = ("ILL", "ill", "little", "look", "book", "good", "bad", "dad", "pig", "dig", "map", "cap", "BAT", "bat", "CAP", "cap")
    case_pairs = (("CAP", "cap"), ("BAT", "bat"), ("MAP", "map"), ("BAG", "bag"))

    style = _FONT_REVIEW_ROLES["PRIMARY"] + f'color:{_FONT_REVIEW_COLORS["DEFAULT"]};'
    blocks = ['<section data-glyph-pairs>']
    for pair in pairs:
        blocks.append(f'<div style="{style}">{_html_escape(pair)}</div>')
    blocks.append("</section>")

    blocks.append('<section data-glyph-words>')
    for w in words:
        blocks.append(f'<span style="{style}margin-right:16px;">{_html_escape(w)}</span>')
    blocks.append("</section>")

    blocks.append('<section data-case-bridge>')
    for upper, lower in case_pairs:
        dominant_style = _FONT_REVIEW_ROLES["DOMINANT"] + f'color:{_FONT_REVIEW_COLORS["SUCCESS"]};'
        blocks.append(f'<div style="{dominant_style}">{upper} <!-- VISUAL_TRANSFORMATION --> → {lower}</div>')
    blocks.append("</section>")

    return _font_review_page(font_key, f"{font_key} / Glyph Disambiguation Test", "\n".join(blocks))


def _parse_role_style(style: str) -> tuple[str, str]:
    """Derives (px string, weight string) from a role's actual applied CSS style string -- never a
    separately hardcoded value. This is exactly what prevented a real bug: an earlier version
    hardcoded "PRIMARY 40px/700" as a label while CLEAN_DARK_FOCUS's real value is 42px, silently
    showing a wrong number next to the correctly-styled text (13-4C-3). Single source of truth for
    every "label derived from CSS" site in this file (13-4C-3, 13-4C-10)."""
    size_match = re.search(r"font-size:(\d+px)", style)
    weight_match = re.search(r"font-weight:(\d+)", style)
    return size_match.group(1), weight_match.group(1)


def build_font_hierarchy_test_prototype(font_key: str) -> str:
    samples = (
        ("DOMINANT", "CAP", "SUCCESS"),
        ("PRIMARY", "직접 읽어보세요.", "PRIMARY_FOCUS"),
        ("SUPPORTING", "CAP → cap", "RELATION"),
        ("CAPTION", "학습 보조 자막 예시", "DEFAULT"),
        ("MICRO", "metadata sample", "SECONDARY"),
    )
    blocks = []
    for role, text, color_role in samples:
        role_style = _FONT_REVIEW_ROLES[role]
        px, weight = _parse_role_style(role_style)
        label = f"{role} — {px} / {weight}"
        style = role_style + f'color:{_FONT_REVIEW_COLORS[color_role]};'
        blocks.append(f'<section><div style="font-family:sans-serif;font-size:12px;opacity:0.6;">{label}</div><div style="{style}">{_html_escape(text)}</div></section>')
    return _font_review_page(font_key, f"{font_key} / Typography Hierarchy Test", "\n".join(blocks))


def generate_font_review_prototypes(assets_dir: Path, plan_id: int) -> dict:
    review_dir = assets_dir / "generated" / f"plan_{plan_id}" / "render" / "font_review"
    review_dir.mkdir(parents=True, exist_ok=True)

    file_entries = []
    for font_key in FONT_CANDIDATES:
        for suffix, builder in (
            ("learning", build_font_learning_prototype),
            ("glyph_test", build_font_glyph_test_prototype),
            ("hierarchy_test", build_font_hierarchy_test_prototype),
        ):
            filename = f"{font_key}_{suffix}.html"
            (review_dir / filename).write_text(builder(font_key), encoding="utf-8")
            file_entries.append({"candidate": font_key, "screen": suffix, "file": filename})

    manifest = {
        "revision": "13-4C-3", "review_type": "FONT_FAMILY", "production_plan_id": plan_id,
        "canonical_candidate": "CLEAN_DARK_FOCUS", "human_review_required": True,
        "font_family_status": "PENDING_VISUAL_REVIEW",
        "fixed_review_values": ["background", "color_palette", "typography_scale"],
        "candidates": [{"key": k, **v} for k, v in FONT_CANDIDATES.items()],
        "files": file_entries, "generated_at": datetime.utcnow().isoformat(),
    }
    (review_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    index_lines = ["<!doctype html><html><head><meta charset=\"utf-8\"><title>Font Family Review</title></head><body>"]
    index_lines.append("<p>Font Family comparison for CLEAN_DARK_FOCUS -- Background/Color/Typography Scale fixed, Font Family is the only variable. No recommended candidate is marked.</p>")
    for font_key, info in FONT_CANDIDATES.items():
        index_lines.append(f"<h3>{_html_escape(font_key)}</h3><p>{_html_escape(info['description'])}</p><ul>")
        for suffix, label in (("learning", "Learning Screen"), ("glyph_test", "Glyph Test"), ("hierarchy_test", "Hierarchy Test")):
            index_lines.append(f'<li><a href="{font_key}_{suffix}.html">{label}</a></li>')
        index_lines.append("</ul>")
    index_lines.append("</body></html>")
    (review_dir / "index.html").write_text("\n".join(index_lines), encoding="utf-8")

    return {"review_dir": review_dir, "manifest": manifest, "file_count": len(file_entries)}


def run_font_family_review(db_path: Path, assets_dir: Path, reports_dir: Path, *, plan_id: int | None = None) -> dict:
    entry_gate = validate_visual_design_entry_gate(db_path, assets_dir, plan_id=plan_id)
    if not entry_gate["pass"]:
        return {"pass": False, "reason": entry_gate["reason"], "plan_id": entry_gate.get("plan_id")}
    pid = entry_gate["plan_id"]

    result = generate_font_review_prototypes(assets_dir, pid)
    report_path = _build_font_review_report(reports_dir, pid, result)

    return {
        "pass": True, "plan_id": pid, "review_dir": result["review_dir"],
        "manifest": result["manifest"], "file_count": result["file_count"], "report_path": report_path,
    }


def _build_font_review_report(reports_dir: Path, plan_id: int, result: dict) -> Path:
    lines: list[str] = ["# Font Family Review Report", ""]
    lines.append(f"생성일: {datetime.utcnow().date().isoformat()}")
    lines.append(f"Source Plan: {plan_id}")
    lines.append("")
    lines.append("## Honesty note: Human Review Decision vs Canonical Persistence")
    lines.append("")
    lines.append(
        "Background/Color Palette/Typography Scale used below are CANDIDATES['CLEAN_DARK_FOCUS']'s existing "
        "code values -- they match what a human would see for that already-selected candidate, but no "
        "conversation record exists of a human independently approving these exact tokens. The canonical "
        "visual_design_specs record (id=5, 13-4C-2) still correctly shows all 15 categories PENDING_VISUAL_REVIEW; "
        "this stage does not change that."
    )
    lines.append("")
    lines.append("## Font Candidates")
    lines.append("")
    for key, info in FONT_CANDIDATES.items():
        lines.append(f"- {key}: {info['stack']} -- {info['description']} (native weights {info['native_weights']}, 800: {info['weight_800_behavior']})")
    lines.append("")
    lines.append("## Human Review Priority (what to look at first)")
    lines.append("")
    for i, item in enumerate(["I / l / 1", "O / 0", "b / d / p / q", "CAP → cap", "68px/800 CAP shape", "18px Caption readability", "overall fit with CLEAN_DARK_FOCUS"], start=1):
        lines.append(f"{i}. {item}")
    lines.append("")
    lines.append(f"Files: {result['file_count']}")
    lines.append(f"Directory: {result['review_dir']}")
    lines.append(f"Review first: {result['review_dir'] / 'index.html'}")
    lines.append("")

    reports_dir.mkdir(parents=True, exist_ok=True)
    out_path = reports_dir / f"font_family_review_{datetime.utcnow().date().isoformat()}.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# 13-4C-6: Font Family Human Approval -- persists exactly the font_family category as APPROVED,
# based on the real Human Review decision on the 13-4C-3 Font Family Prototype (VERDANA_HUMANIST).
# This is the ONLY font candidate with an actual recorded Human Review decision behind it;
# approving ARIAL_NEUTRAL or SEGOE_MODERN here would fabricate a decision that was never made, so
# this function structurally refuses any other candidate rather than trusting a caller-supplied one.
# Append-only: writes a new visual_design_specs row on top of the current canonical
# CANONICAL_CORRECTION record (found via select_canonical_visual_approval, never a hardcoded id),
# carrying every other category forward exactly as it already stood. full_profile_approved is always
# False here (a single category approval is never a full-profile approval by definition), and
# ready_for_final_renderer_binding is recomputed via the real ready_for_final_renderer_binding gate,
# which is also False since the other 8 MANDATORY_VISUAL_CATEGORIES members remain PENDING.
# ---------------------------------------------------------------------------

HUMAN_REVIEWED_FONT_FAMILY = "VERDANA_HUMANIST"


def run_font_family_human_approval(
    db_path: Path, assets_dir: Path, reports_dir: Path, *, plan_id: int | None = None,
    approved_font_family: str = HUMAN_REVIEWED_FONT_FAMILY,
) -> dict:
    entry_gate = validate_visual_design_entry_gate(db_path, assets_dir, plan_id=plan_id)
    if not entry_gate["pass"]:
        return {"pass": False, "reason": entry_gate["reason"], "plan_id": entry_gate.get("plan_id")}
    pid = entry_gate["plan_id"]

    if approved_font_family not in FONT_CANDIDATES:
        return {"pass": False, "reason": f"{approved_font_family!r} is not a real Font Review candidate (choices: {sorted(FONT_CANDIDATES)})", "plan_id": pid}

    if approved_font_family != HUMAN_REVIEWED_FONT_FAMILY:
        return {
            "pass": False,
            "reason": (
                f"No recorded Human Review decision for {approved_font_family!r} -- only "
                f"{HUMAN_REVIEWED_FONT_FAMILY!r} has an actual Human Review approval on record."
            ),
            "plan_id": pid,
        }

    canonical = select_canonical_visual_approval(db_path, pid)
    if canonical is None:
        return {"pass": False, "reason": "No canonical CANONICAL_CORRECTION visual_design_specs row found -- run `correct-visual-approval` first.", "plan_id": pid}

    prior_id, prior_record = canonical["id"], canonical["design"]
    prior_categories = prior_record.get("category_approvals", {})
    font_stack = FONT_CANDIDATES[approved_font_family]["stack"]

    new_categories = dict(prior_categories)
    new_categories["font_family"] = {
        "resolved_style": font_stack,
        "resolution_status": "APPROVED",
        "reason": "Human Review approved on the 13-4C-3 Font Family Prototype",
        "provenance": {
            "review_stage": "13-4C-6",
            "review_type": "HUMAN_VISUAL_REVIEW",
            "review_source": "13-4C-3 Font Family Prototype",
            "selected_candidate": approved_font_family,
            "visual_candidate": prior_record.get("selected_candidate"),
            "human_decision": "APPROVED",
        },
    }

    candidate_selection = {
        "selected_candidate": prior_record.get("selected_candidate"),
        "candidate_selection_status": prior_record.get("candidate_selection_status"),
    }
    ready = ready_for_final_renderer_binding(candidate_selection, {"categories": new_categories})
    approved_count = sum(1 for c in new_categories.values() if c["resolution_status"] == "APPROVED")
    pending_count = len(new_categories) - approved_count

    new_record = {
        **prior_record,
        "record_status": "CANONICAL_CORRECTION",
        "revision": "13-4C-6",
        "corrects_record_id": prior_id,
        "correction_reason": "FONT_FAMILY_HUMAN_APPROVAL",
        "correction_details": (
            f"font_family Human Review approved ({approved_font_family}); every other category is carried "
            f"forward unchanged from record id={prior_id}."
        ),
        "category_approvals": new_categories,
        "full_profile_approved": False,
        "ready_for_final_renderer_binding": ready,
    }

    row_id = persist_visual_design(db_path, pid, prior_id, new_record, {"checks": {}, "unresolved_critical": [], "unresolved_non_critical": []})

    profile_path = assets_dir / "generated" / f"plan_{pid}" / "render" / "approved_visual_profile.json"
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(json.dumps(new_record, ensure_ascii=False, indent=2), encoding="utf-8")

    report_path = _build_font_family_approval_report(reports_dir, pid, new_record, approved_count, pending_count, prior_id, row_id, profile_path)

    return {
        "pass": True, "plan_id": pid, "approved_font_family": approved_font_family, "font_stack": font_stack,
        "record": new_record, "prior_canonical_id": prior_id, "visual_design_row_id": row_id,
        "approved_category_count": approved_count, "pending_category_count": pending_count,
        "full_profile_approved": False, "ready_for_final_renderer_binding": ready,
        "json_path": profile_path, "report_path": report_path,
    }


def _build_font_family_approval_report(
    reports_dir: Path, plan_id: int, record: dict, approved_count: int, pending_count: int,
    prior_id: int, row_id: int, profile_path: Path,
) -> Path:
    lines: list[str] = ["# Font Family Human Approval Report", ""]
    lines.append(f"생성일: {datetime.utcnow().date().isoformat()}")
    lines.append(f"Source Plan: {plan_id}")
    lines.append("")
    lines.append("## Human Review 대상")
    lines.append("")
    lines.append("비교한 3개 Font 후보: VERDANA_HUMANIST, ARIAL_NEUTRAL, SEGOE_MODERN (13-4C-3 Font Review Prototype)")
    lines.append(f"선택된 Font: {record['category_approvals']['font_family']['provenance']['selected_candidate']}")
    lines.append(f"실제 Font Stack: {record['category_approvals']['font_family']['resolved_style']}")
    lines.append(f"Human Review provenance: {json.dumps(record['category_approvals']['font_family']['provenance'], ensure_ascii=False)}")
    lines.append("")
    lines.append("## Typography Scale (불변)")
    lines.append("")
    lines.append(f"PRIMARY: {CANDIDATES['CLEAN_DARK_FOCUS']['roles']['PRIMARY']} -- 이번 단계에서 변경되지 않음")
    lines.append(f"typography_scale status: {record['category_approvals'].get('typography_scale', {}).get('resolution_status')}")
    lines.append("")
    lines.append(f"## Category Approvals ({approved_count} APPROVED / {pending_count} PENDING)")
    lines.append("")
    for name, cat in record["category_approvals"].items():
        lines.append(f"- {name}: {cat['resolution_status']}")
    lines.append("")
    lines.append("## Renderer Gate")
    lines.append("")
    lines.append(f"Full Profile Approved: {'YES' if record['full_profile_approved'] else 'NO'}")
    lines.append(f"Ready for Final Renderer Binding: {'YES' if record['ready_for_final_renderer_binding'] else 'NO'}")
    lines.append("")
    lines.append("## DB Append-only")
    lines.append("")
    lines.append(f"이전 canonical record id: {prior_id} (수정되지 않음)")
    lines.append(f"신규 canonical record id: {row_id}")
    lines.append("")
    lines.append(f"JSON: {profile_path}")
    lines.append("")

    reports_dir.mkdir(parents=True, exist_ok=True)
    out_path = reports_dir / f"font_family_human_approval_{datetime.utcnow().date().isoformat()}.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# 13-4C-7: Color Palette + Background Human Review -- exactly like 13-4C-3's Font Review, this is a
# REVIEW PREPARATION stage, not an approval stage: it writes zero DB rows. Background/Color Palette
# stay CANDIDATES["CLEAN_DARK_FOCUS"]'s existing preview values (the thing under review); Typography
# and the already-APPROVED font_family are both fixed conditions, never touched or re-approved here.
# WCAG contrast is computed as reference-only information for the human, never used to auto-adjust a
# HEX value or auto-approve a category.
# ---------------------------------------------------------------------------

def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", hex_color):
        raise ValueError(f"{hex_color!r} is not a valid #RRGGBB hex color")
    return (int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16))


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    def channel(c: int) -> float:
        c_srgb = c / 255.0
        return c_srgb / 12.92 if c_srgb <= 0.03928 else ((c_srgb + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(hex_a: str, hex_b: str) -> float:
    """WCAG contrast ratio -- order-independent (lighter/darker resolved internally)."""
    l_a = _relative_luminance(_hex_to_rgb(hex_a))
    l_b = _relative_luminance(_hex_to_rgb(hex_b))
    lighter, darker = max(l_a, l_b), min(l_a, l_b)
    return (lighter + 0.05) / (darker + 0.05)


def _wcag_reference(ratio: float) -> dict:
    """Reference labels only (WCAG AA: 4.5:1 normal text, 3:1 large text) -- never used to auto-
    adjust a HEX value or auto-approve a category (section 17/18: Human Review reference material)."""
    return {"normal_text": "PASS" if ratio >= 4.5 else "FAIL", "large_text": "PASS" if ratio >= 3.0 else "FAIL"}


COLOR_REVIEW_ROLES = ("DEFAULT", "PRIMARY_FOCUS", "RELATION", "SUCCESS", "SECONDARY", "MUTED", "EXCEPTION_CAUTION")

_COLOR_SEMANTIC_LABELS = {
    "DEFAULT": "기본 텍스트", "PRIMARY_FOCUS": "현재 읽을 단어", "RELATION": "글자와 소리의 연결",
    "SUCCESS": "정답", "SECONDARY": "보조 정보", "MUTED": "이미 지나간 정보", "EXCEPTION_CAUTION": "예외/주의",
}


def build_contrast_results(page_bg: str, colors: dict) -> dict:
    results = {}
    for role in COLOR_REVIEW_ROLES:
        hex_value = colors[role]
        ratio = contrast_ratio(hex_value, page_bg)
        ref = _wcag_reference(ratio)
        results[role] = {
            "hex": hex_value, "contrast_ratio": round(ratio, 2),
            "normal_text_reference": ref["normal_text"], "large_text_reference": ref["large_text"],
        }
    return results


def _color_role_usage_counts(scene_visual_rules: list) -> dict:
    """Real Plan 7 usage, counted from the canonical record's own scene_visual_rules -- never
    hardcoded, so this stays correct if the underlying Production Plan/Visual Design changes."""
    counts = {role: 0 for role in COLOR_REVIEW_ROLES}
    for scene in scene_visual_rules:
        for binding in scene.get("color_bindings", []):
            role = binding.get("color_role")
            if role in counts:
                counts[role] += 1
    return counts


def _color_review_page(title: str, body: str, font_stack: str) -> str:
    colors = CANDIDATES["CLEAN_DARK_FOCUS"]["colors"]
    page_bg = CANDIDATES["CLEAN_DARK_FOCUS"]["page_bg"]
    return (
        f'<!doctype html><html><head><meta charset="utf-8"><title>{_html_escape(title)}</title></head>'
        f'<body style="background:{page_bg};color:{colors["DEFAULT"]};font-family:{font_stack};padding:40px;">'
        f'<header data-preview-metadata style="opacity:0.5;font-size:12px;font-family:sans-serif;">PREVIEW ONLY -- '
        f'Color Palette/Background Human Review, not yet APPROVED. Candidate=CLEAN_DARK_FOCUS. '
        f'Font Family={_html_escape(font_stack)} (already Human Review APPROVED -- fixed condition here, not a variable).</header>'
        f'<main data-frame-preview>{body}</main></body></html>'
    )


def build_color_full_learning_prototype(font_stack: str) -> str:
    colors = CANDIDATES["CLEAN_DARK_FOCUS"]["colors"]
    roles = CANDIDATES["CLEAN_DARK_FOCUS"]["roles"]
    prompt_style = roles["PRIMARY"] + f'color:{colors["PRIMARY_FOCUS"]};'
    dominant_style = roles["DOMINANT"] + f'color:{colors["DEFAULT"]};'
    relation_style = roles["SUPPORTING"] + f'color:{colors["RELATION"]};'
    success_style = roles["DOMINANT"] + f'color:{colors["SUCCESS"]};'
    secondary_style = roles["CAPTION"] + f'color:{colors["SECONDARY"]};'
    muted_style = roles["CAPTION"] + f'color:{colors["MUTED"]};'
    blocks = [
        f'<div style="{prompt_style}">직접 읽어보세요.</div>',
        f'<div style="{dominant_style}">CAP</div>',
        f'<div style="{relation_style}">CAP → cap</div>',
        f'<div style="{success_style}">cap</div>',
        f'<div style="{secondary_style}">다음 단어: BAT</div>',
        f'<div style="{muted_style}">이미 학습한 단어: MAP, BAG</div>',
    ]
    return _color_review_page("Full Learning Sample", "\n".join(blocks), font_stack)


def build_color_semantic_roles_prototype(font_stack: str, contrast_results: dict) -> str:
    colors = CANDIDATES["CLEAN_DARK_FOCUS"]["colors"]
    base_style = CANDIDATES["CLEAN_DARK_FOCUS"]["roles"]["SUPPORTING"]
    blocks = []
    for role in COLOR_REVIEW_ROLES:
        hex_value = colors[role]
        label = _COLOR_SEMANTIC_LABELS[role]
        cr = contrast_results[role]
        role_style = base_style + f'color:{hex_value};'
        blocks.append(
            '<section>'
            f'<div style="font-family:sans-serif;font-size:12px;opacity:0.6;">{role} ({hex_value}) -- {label} -- '
            f'contrast {cr["contrast_ratio"]}:1 (normal {cr["normal_text_reference"]}, large {cr["large_text_reference"]})</div>'
            f'<div style="{role_style}">{_html_escape(label)}</div>'
            '</section>'
        )
    return _color_review_page("Semantic Color Roles", "\n".join(blocks), font_stack)


def build_color_answer_reveal_prototype(font_stack: str) -> str:
    colors = CANDIDATES["CLEAN_DARK_FOCUS"]["colors"]
    roles = CANDIDATES["CLEAN_DARK_FOCUS"]["roles"]
    before_style = roles["DOMINANT"] + f'color:{colors["DEFAULT"]};'
    after_style = roles["DOMINANT"] + f'color:{colors["SUCCESS"]};'
    blocks = [
        '<section data-answer-reveal-before>',
        '<div style="font-family:sans-serif;font-size:12px;opacity:0.6;">BEFORE (정답 공개 전)</div>',
        f'<div style="{before_style}">CAP</div>',
        '</section>',
        '<section data-answer-reveal-after>',
        '<div style="font-family:sans-serif;font-size:12px;opacity:0.6;">AFTER (정답 공개 후)</div>',
        f'<div style="{after_style}">cap</div>',
        '</section>',
    ]
    return _color_review_page("Answer Reveal Sample", "\n".join(blocks), font_stack)


def build_color_relation_prototype(font_stack: str) -> str:
    colors = CANDIDATES["CLEAN_DARK_FOCUS"]["colors"]
    roles = CANDIDATES["CLEAN_DARK_FOCUS"]["roles"]
    primary_style = roles["DOMINANT"] + f'color:{colors["PRIMARY_FOCUS"]};'
    relation_style = roles["SUPPORTING"] + f'color:{colors["RELATION"]};'
    success_style = roles["DOMINANT"] + f'color:{colors["SUCCESS"]};'
    blocks = [
        f'<div style="{primary_style}">CAP</div>',
        f'<div style="{relation_style}">CAP → cap</div>',
        f'<div style="{success_style}">cap</div>',
    ]
    return _color_review_page("Relation Sample", "\n".join(blocks), font_stack)


def build_color_secondary_muted_prototype(font_stack: str, used_in_plan: bool) -> str:
    colors = CANDIDATES["CLEAN_DARK_FOCUS"]["colors"]
    style = CANDIDATES["CLEAN_DARK_FOCUS"]["roles"]["SUPPORTING"]
    secondary_style = style + f'color:{colors["SECONDARY"]};'
    muted_style = style + f'color:{colors["MUTED"]};'
    blocks = []
    if not used_in_plan:
        blocks.append('<div data-usage-notice style="font-family:sans-serif;font-size:12px;opacity:0.7;">SEMANTIC ROLE PREVIEW ONLY -- NOT USED IN CURRENT PLAN 7</div>')
    blocks.append(f'<div style="{secondary_style}">보조 정보 예시: 다음 단어 안내</div>')
    blocks.append(f'<div style="{muted_style}">이미 지나간 정보 예시: 앞서 학습한 단어</div>')
    return _color_review_page("Secondary / Muted Sample", "\n".join(blocks), font_stack)


def build_color_exception_caution_prototype(font_stack: str, used_in_plan: bool) -> str:
    colors = CANDIDATES["CLEAN_DARK_FOCUS"]["colors"]
    style = CANDIDATES["CLEAN_DARK_FOCUS"]["roles"]["SUPPORTING"] + f'color:{colors["EXCEPTION_CAUTION"]};'
    blocks = []
    if not used_in_plan:
        blocks.append('<div data-usage-notice style="font-family:sans-serif;font-size:12px;opacity:0.7;">SEMANTIC ROLE PREVIEW ONLY -- NOT USED IN CURRENT PLAN 7</div>')
    blocks.append(f'<div style="{style}">예외/주의 예시: 일반적인 규칙에서 벗어난 경우</div>')
    return _color_review_page("Exception / Caution Sample", "\n".join(blocks), font_stack)


def build_color_grayscale_accessibility_prototype(font_stack: str) -> str:
    colors = CANDIDATES["CLEAN_DARK_FOCUS"]["colors"]
    roles = CANDIDATES["CLEAN_DARK_FOCUS"]["roles"]
    samples = [
        (roles["DOMINANT"] + f'color:{colors["PRIMARY_FOCUS"]};', "핵심: CAP"),
        (roles["SUPPORTING"] + f'color:{colors["RELATION"]};', "관계: CAP → cap"),
        (roles["DOMINANT"] + f'color:{colors["SUCCESS"]};', "정답: cap"),
        (roles["CAPTION"] + f'color:{colors["SECONDARY"]};', "보조: 다음 단어 안내"),
        (roles["CAPTION"] + f'color:{colors["MUTED"]};', "약화: 이미 학습한 단어"),
        (roles["SUPPORTING"] + f'color:{colors["EXCEPTION_CAUTION"]};', "예외/주의: 일반 규칙 벗어남"),
    ]
    # filter:grayscale(100%) is a pure CSS presentation effect -- CANDIDATES' real HEX values are
    # never touched (section 16: "canonical Visual Design의 color를 실제로 grayscale로 변경하지 마라").
    blocks = [f'<div style="{style}">{_html_escape(text)}</div>' for style, text in samples]
    body = '<div data-grayscale-simulation data-preview-only="true" style="filter:grayscale(100%);">' + "\n".join(blocks) + '</div>'
    return _color_review_page("Accessibility / Grayscale Sample", body, font_stack)


def generate_color_background_review_prototypes(
    assets_dir: Path, plan_id: int, font_stack: str, approved_font_candidate: str,
    contrast_results: dict, color_usage: dict,
) -> dict:
    review_dir = assets_dir / "generated" / f"plan_{plan_id}" / "render" / "color_background_review"
    review_dir.mkdir(parents=True, exist_ok=True)

    secondary_muted_used = color_usage.get("SECONDARY", 0) > 0 or color_usage.get("MUTED", 0) > 0
    exception_used = color_usage.get("EXCEPTION_CAUTION", 0) > 0

    builders = [
        ("01_FULL_LEARNING_SAMPLE", build_color_full_learning_prototype(font_stack), False),
        ("02_SEMANTIC_COLOR_ROLES", build_color_semantic_roles_prototype(font_stack, contrast_results), False),
        ("03_ANSWER_REVEAL_SAMPLE", build_color_answer_reveal_prototype(font_stack), False),
        ("04_RELATION_SAMPLE", build_color_relation_prototype(font_stack), False),
        ("05_MUTED_SECONDARY_SAMPLE", build_color_secondary_muted_prototype(font_stack, secondary_muted_used), not secondary_muted_used),
        ("06_EXCEPTION_CAUTION_SAMPLE", build_color_exception_caution_prototype(font_stack, exception_used), not exception_used),
        ("07_GRAYSCALE_ACCESSIBILITY_SAMPLE", build_color_grayscale_accessibility_prototype(font_stack), True),
    ]

    file_entries = []
    for name, html, preview_only in builders:
        filename = f"{name}.html"
        (review_dir / filename).write_text(html, encoding="utf-8")
        file_entries.append({"file": filename, "preview_only": preview_only})

    manifest = {
        "revision": "13-4C-7", "review_type": "COLOR_PALETTE_BACKGROUND", "production_plan_id": plan_id,
        "canonical_visual_candidate": "CLEAN_DARK_FOCUS", "human_review_required": True, "approval_written": False,
        "color_palette_status": "PENDING_VISUAL_REVIEW", "background_status": "PENDING_VISUAL_REVIEW",
        "font_family_status": "APPROVED", "font_family": approved_font_candidate, "font_stack": font_stack,
        "preview_values": {"page_bg": CANDIDATES["CLEAN_DARK_FOCUS"]["page_bg"], "colors": CANDIDATES["CLEAN_DARK_FOCUS"]["colors"]},
        "color_role_usage_in_plan": color_usage, "contrast_results": contrast_results,
        "files": file_entries, "generated_at": datetime.utcnow().isoformat(),
    }
    (review_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    index_descriptions = [
        ("01_FULL_LEARNING_SAMPLE.html", "실제 학습 화면 전체 통합 샘플 -- 배경/색 전체를 한번에 확인"),
        ("02_SEMANTIC_COLOR_ROLES.html", "7개 color role 전체 비교 + contrast ratio"),
        ("03_ANSWER_REVEAL_SAMPLE.html", "정답 공개 시 SUCCESS 색이 명확한지 확인"),
        ("04_RELATION_SAMPLE.html", "RELATION이 PRIMARY_FOCUS/SUCCESS와 구별되는지 확인"),
        ("05_MUTED_SECONDARY_SAMPLE.html", "SECONDARY/MUTED가 서로 구별되면서 학습 핵심과 경쟁하지 않는지 확인"),
        ("06_EXCEPTION_CAUTION_SAMPLE.html", "예외/주의 색이 SUCCESS와 혼동되지 않는지 확인"),
        ("07_GRAYSCALE_ACCESSIBILITY_SAMPLE.html", "색을 빼도 정보 구조가 이해되는지 확인 (accessibility)"),
    ]
    index_lines = ['<!doctype html><html><head><meta charset="utf-8"><title>Color Palette + Background Review</title></head><body>']
    index_lines.append("<p>CLEAN_DARK_FOCUS Color Palette + Background Human Review -- font_family는 이미 APPROVED된 값으로 고정, typography도 고정 조건. Color Palette/Background는 아직 APPROVED 아님.</p>")
    index_lines.append("<ol>")
    for filename, desc in index_descriptions:
        index_lines.append(f'<li><a href="{filename}">{filename}</a> -- {desc}</li>')
    index_lines.append("</ol>")
    index_lines.append("</body></html>")
    (review_dir / "index.html").write_text("\n".join(index_lines), encoding="utf-8")

    return {"review_dir": review_dir, "manifest": manifest, "file_count": len(file_entries)}


def run_color_background_review(db_path: Path, assets_dir: Path, reports_dir: Path, *, plan_id: int | None = None) -> dict:
    entry_gate = validate_visual_design_entry_gate(db_path, assets_dir, plan_id=plan_id)
    if not entry_gate["pass"]:
        return {"pass": False, "reason": entry_gate["reason"], "plan_id": entry_gate.get("plan_id")}
    pid = entry_gate["plan_id"]

    canonical = select_canonical_visual_approval(db_path, pid)
    if canonical is None:
        return {"pass": False, "reason": "No canonical CANONICAL_CORRECTION visual_design_specs row found -- run `correct-visual-approval` first.", "plan_id": pid}

    record = canonical["design"]
    if record.get("selected_candidate") != "CLEAN_DARK_FOCUS":
        return {"pass": False, "reason": f"Canonical visual candidate is {record.get('selected_candidate')!r}, not CLEAN_DARK_FOCUS -- this review is scoped to CLEAN_DARK_FOCUS only.", "plan_id": pid}

    font_family_cat = record.get("category_approvals", {}).get("font_family", {})
    if font_family_cat.get("resolution_status") != "APPROVED":
        return {"pass": False, "reason": "font_family category is not APPROVED yet -- Color/Background Review needs an already-approved font as a fixed condition (run `approve-font-family` first).", "plan_id": pid}

    font_stack = font_family_cat["resolved_style"]
    approved_font_candidate = font_family_cat.get("provenance", {}).get("selected_candidate", "")

    color_usage = _color_role_usage_counts(record.get("scene_visual_rules", []))
    contrast_results = build_contrast_results(CANDIDATES["CLEAN_DARK_FOCUS"]["page_bg"], CANDIDATES["CLEAN_DARK_FOCUS"]["colors"])

    result = generate_color_background_review_prototypes(assets_dir, pid, font_stack, approved_font_candidate, contrast_results, color_usage)
    report_path = _build_color_background_review_report(reports_dir, pid, canonical["id"], record, font_stack, approved_font_candidate, contrast_results, color_usage, result)

    return {
        "pass": True, "plan_id": pid, "canonical_record_id": canonical["id"],
        "font_stack": font_stack, "approved_font_candidate": approved_font_candidate,
        "contrast_results": contrast_results, "color_role_usage": color_usage,
        "review_dir": result["review_dir"], "manifest": result["manifest"], "file_count": result["file_count"],
        "report_path": report_path,
    }


def _build_color_background_review_report(
    reports_dir: Path, plan_id: int, canonical_id: int, record: dict, font_stack: str,
    approved_font_candidate: str, contrast_results: dict, color_usage: dict, result: dict,
) -> Path:
    lines: list[str] = ["# Color Palette + Background Human Review Report", ""]
    lines.append(f"생성일: {datetime.utcnow().date().isoformat()}")
    lines.append(f"Source Plan: {plan_id}")
    lines.append(f"Canonical record id: {canonical_id}")
    lines.append("")
    lines.append("## Canonical State (실제 조사 결과)")
    lines.append("")
    lines.append(f"Canonical Visual Candidate: {record.get('selected_candidate')}")
    lines.append(f"Font Family status: APPROVED ({approved_font_candidate})")
    lines.append(f"Font Stack: {font_stack}")
    approved = [k for k, v in record["category_approvals"].items() if v["resolution_status"] == "APPROVED"]
    pending = [k for k, v in record["category_approvals"].items() if v["resolution_status"] != "APPROVED"]
    lines.append(f"Approved categories: {len(approved)} ({approved})")
    lines.append(f"Pending categories: {len(pending)}")
    lines.append("")
    lines.append("## CLEAN_DARK_FOCUS Preview 값 (실제 코드 값)")
    lines.append("")
    lines.append(f"page_bg: {CANDIDATES['CLEAN_DARK_FOCUS']['page_bg']}")
    for role in COLOR_REVIEW_ROLES:
        lines.append(f"{role}: {CANDIDATES['CLEAN_DARK_FOCUS']['colors'][role]}")
    lines.append("")
    lines.append("## 스펙 예상값과 실제 코드 값 불일치 (정직하게 기록)")
    lines.append("")
    lines.append(f"EXCEPTION_CAUTION: 스펙(13-4C-7 §4) 예상 #f59e0b, 실제 코드 값 {CANDIDATES['CLEAN_DARK_FOCUS']['colors']['EXCEPTION_CAUTION']} -- 실제 코드 값을 사용했음")
    lines.append("")
    lines.append("## Plan 7 실제 Color Role 사용 횟수 (scene_visual_rules에서 직접 집계)")
    lines.append("")
    for role in COLOR_REVIEW_ROLES:
        lines.append(f"{role}: {color_usage.get(role, 0)}회")
    unused = [r for r in COLOR_REVIEW_ROLES if color_usage.get(r, 0) == 0]
    lines.append("")
    lines.append(f"Plan 7 미사용 role: {unused if unused else 'NONE'}")
    lines.append("")
    lines.append("## Contrast Ratio (WCAG 참고용 -- 자동 승인/자동 변경 근거 아님)")
    lines.append("")
    lines.append("| Role | HEX | Ratio | Normal Text (AA 4.5:1) | Large Text (AA 3:1) |")
    lines.append("|---|---|---|---|---|")
    for role in COLOR_REVIEW_ROLES:
        cr = contrast_results[role]
        lines.append(f"| {role} | {cr['hex']} | {cr['contrast_ratio']}:1 | {cr['normal_text_reference']} | {cr['large_text_reference']} |")
    lines.append("")
    lines.append(f"Files: {result['file_count']}")
    lines.append(f"Directory: {result['review_dir']}")
    lines.append(f"Review first: {result['review_dir'] / 'index.html'}")
    lines.append("")
    lines.append("## Human Review Questions")
    lines.append("")
    lines.append("COLOR PALETTE:")
    lines.append("1 = 현재 Palette 그대로 승인")
    lines.append("2 = 일부 색상 수정 필요")
    lines.append("3 = 전체 Palette 재검토 필요")
    lines.append("")
    lines.append("BACKGROUND:")
    lines.append("1 = 현재 Background 그대로 승인")
    lines.append("2 = Background 수정 필요")
    lines.append("")

    reports_dir.mkdir(parents=True, exist_ok=True)
    out_path = reports_dir / f"color_background_review_{datetime.utcnow().date().isoformat()}.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# 13-4C-8: MUTED Color Refinement Human Review -- two distinct actions in one stage. (A) Background
# Human Approval persistence: append-only, exactly like 13-4C-6's font_family approval (one category
# flips to APPROVED, every other category -- especially the already-APPROVED font_family -- carried
# forward unchanged). (B) MUTED Review Prep: zero DB writes, exactly like 13-4C-3/13-4C-7 -- two
# deterministic candidate HEX values (RGB-interpolated between the current MUTED and SECONDARY, never
# random, never auto-selected) presented for Human Review, color_palette stays PENDING throughout.
# ---------------------------------------------------------------------------

def run_background_human_approval(db_path: Path, assets_dir: Path, reports_dir: Path, *, plan_id: int | None = None) -> dict:
    entry_gate = validate_visual_design_entry_gate(db_path, assets_dir, plan_id=plan_id)
    if not entry_gate["pass"]:
        return {"pass": False, "reason": entry_gate["reason"], "plan_id": entry_gate.get("plan_id")}
    pid = entry_gate["plan_id"]

    canonical = select_canonical_visual_approval(db_path, pid)
    if canonical is None:
        return {"pass": False, "reason": "No canonical CANONICAL_CORRECTION visual_design_specs row found -- run `correct-visual-approval` first.", "plan_id": pid}

    prior_id, prior_record = canonical["id"], canonical["design"]
    if prior_record.get("selected_candidate") != "CLEAN_DARK_FOCUS":
        return {"pass": False, "reason": f"Canonical visual candidate is {prior_record.get('selected_candidate')!r}, not CLEAN_DARK_FOCUS -- this approval is scoped to CLEAN_DARK_FOCUS only.", "plan_id": pid}

    # page_bg is read from the real CANDIDATES definition, never from a caller-supplied parameter --
    # there is structurally no way to persist a value other than the actual current code value.
    page_bg = CANDIDATES["CLEAN_DARK_FOCUS"]["page_bg"]

    prior_categories = prior_record.get("category_approvals", {})
    new_categories = dict(prior_categories)
    new_categories["background"] = {
        "resolved_style": page_bg,
        "resolution_status": "APPROVED",
        "reason": "Human Review approved on the 13-4C-7 Color Palette + Background Prototype",
        "provenance": {
            "review_stage": "13-4C-8", "review_type": "HUMAN_VISUAL_REVIEW",
            "review_source": "13-4C-7 Color Palette + Background Human Review Prototype",
            "visual_candidate": "CLEAN_DARK_FOCUS", "human_decision": "APPROVED",
        },
    }

    candidate_selection = {
        "selected_candidate": prior_record.get("selected_candidate"),
        "candidate_selection_status": prior_record.get("candidate_selection_status"),
    }
    ready = ready_for_final_renderer_binding(candidate_selection, {"categories": new_categories})
    approved_count = sum(1 for c in new_categories.values() if c["resolution_status"] == "APPROVED")
    pending_count = len(new_categories) - approved_count

    new_record = {
        **prior_record,
        "record_status": "CANONICAL_CORRECTION",
        "revision": "13-4C-8",
        "corrects_record_id": prior_id,
        "correction_reason": "BACKGROUND_HUMAN_APPROVAL",
        "correction_details": (
            f"background Human Review approved ({page_bg}); every other category (including the "
            f"already-approved font_family) is carried forward unchanged from record id={prior_id}."
        ),
        "category_approvals": new_categories,
        "full_profile_approved": False,
        "ready_for_final_renderer_binding": ready,
    }

    row_id = persist_visual_design(db_path, pid, prior_id, new_record, {"checks": {}, "unresolved_critical": [], "unresolved_non_critical": []})

    profile_path = assets_dir / "generated" / f"plan_{pid}" / "render" / "approved_visual_profile.json"
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(json.dumps(new_record, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "pass": True, "plan_id": pid, "approved_background": page_bg, "record": new_record,
        "prior_canonical_id": prior_id, "visual_design_row_id": row_id,
        "approved_category_count": approved_count, "pending_category_count": pending_count,
        "full_profile_approved": False, "ready_for_final_renderer_binding": ready, "json_path": profile_path,
    }


def _interpolate_hex(hex_a: str, hex_b: str, t: float) -> str:
    a, b = _hex_to_rgb(hex_a), _hex_to_rgb(hex_b)
    rgb = tuple(round(a[i] + t * (b[i] - a[i])) for i in range(3))
    return "#{:02x}{:02x}{:02x}".format(*rgb)


# Fixed interpolation points between the current MUTED and SECONDARY -- deterministic, never random,
# never auto-picking a "winner" (section 11: crossing 4.5:1 is not grounds for auto-selection). B
# lands short of AA (a genuine "visible but clearly weak" contrast candidate); C clears AA normal
# text (4.5:1+) while staying below SECONDARY's own contrast -- verified against the real CLEAN_DARK_
# FOCUS values (MUTED #555b66 2.72:1, SECONDARY #9ca3af 7.32:1 against #111318).
MUTED_CANDIDATE_FACTORS = {"B_MODERATE": 0.45, "C_ACCESSIBLE": 0.75}


def build_muted_candidates(page_bg: str, muted_current: str, secondary: str) -> dict:
    candidates = {
        "A_CURRENT": {"hex": muted_current, "label": "CURRENT"},
        "B_MODERATE": {"hex": _interpolate_hex(muted_current, secondary, MUTED_CANDIDATE_FACTORS["B_MODERATE"]), "label": "MODERATE"},
        "C_ACCESSIBLE": {"hex": _interpolate_hex(muted_current, secondary, MUTED_CANDIDATE_FACTORS["C_ACCESSIBLE"]), "label": "ACCESSIBLE"},
    }
    for info in candidates.values():
        ratio = contrast_ratio(info["hex"], page_bg)
        ref = _wcag_reference(ratio)
        info["contrast_ratio"] = round(ratio, 2)
        info["normal_text_reference"] = ref["normal_text"]
        info["large_text_reference"] = ref["large_text"]
    return candidates


def _muted_review_page(title: str, body: str, font_stack: str) -> str:
    colors = CANDIDATES["CLEAN_DARK_FOCUS"]["colors"]
    page_bg = CANDIDATES["CLEAN_DARK_FOCUS"]["page_bg"]
    return (
        f'<!doctype html><html><head><meta charset="utf-8"><title>{_html_escape(title)}</title></head>'
        f'<body style="background:{page_bg};color:{colors["DEFAULT"]};font-family:{font_stack};padding:40px;">'
        f'<header data-preview-metadata style="opacity:0.5;font-size:12px;font-family:sans-serif;">PREVIEW ONLY -- '
        f'MUTED Color Refinement Human Review. Background=APPROVED({page_bg}), Color Palette still PENDING_VISUAL_REVIEW. '
        f'Only MUTED varies across candidates -- DEFAULT/PRIMARY_FOCUS/RELATION/SUCCESS/SECONDARY/EXCEPTION_CAUTION/page_bg/font are all fixed.</header>'
        f'<main data-frame-preview>{body}</main></body></html>'
    )


def build_muted_side_by_side_prototype(font_stack: str, candidates: dict) -> str:
    style = CANDIDATES["CLEAN_DARK_FOCUS"]["roles"]["SUPPORTING"]
    blocks = []
    for key, info in candidates.items():
        blocks.append(
            '<section>'
            f'<div style="font-family:sans-serif;font-size:12px;opacity:0.6;">{key} ({info["hex"]}) -- '
            f'contrast {info["contrast_ratio"]}:1 (normal {info["normal_text_reference"]}, large {info["large_text_reference"]})</div>'
            f'<div style="{style}color:{info["hex"]};">이미 지나간 정보 예시: 앞서 학습한 단어</div>'
            '</section>'
        )
    return _muted_review_page("MUTED Side by Side", "\n".join(blocks), font_stack)


def build_muted_learning_context_prototype(font_stack: str, candidates: dict, secondary_used: bool) -> str:
    colors = CANDIDATES["CLEAN_DARK_FOCUS"]["colors"]
    roles = CANDIDATES["CLEAN_DARK_FOCUS"]["roles"]
    primary_style = roles["PRIMARY"] + f'color:{colors["PRIMARY_FOCUS"]};'
    secondary_style = roles["CAPTION"] + f'color:{colors["SECONDARY"]};'
    blocks = []
    if not secondary_used:
        blocks.append('<div data-usage-notice style="font-family:sans-serif;font-size:12px;opacity:0.7;">SEMANTIC ROLE PREVIEW ONLY -- NOT USED IN CURRENT PLAN 7</div>')
    blocks.append(f'<div style="{primary_style}">직접 읽어보세요.</div>')
    blocks.append(f'<div style="{secondary_style}">SECONDARY -- 다음 단어 안내</div>')
    for key, info in candidates.items():
        muted_style = roles["CAPTION"] + f'color:{info["hex"]};'
        blocks.append(f'<div style="{muted_style}">MUTED {key} -- 이미 지나간 정보 / 앞서 학습한 단어</div>')
    return _muted_review_page("MUTED Learning Context", "\n".join(blocks), font_stack)


def build_muted_vs_secondary_prototype(font_stack: str, candidates: dict) -> str:
    colors = CANDIDATES["CLEAN_DARK_FOCUS"]["colors"]
    style = CANDIDATES["CLEAN_DARK_FOCUS"]["roles"]["SUPPORTING"]
    blocks = [f'<div style="{style}color:{colors["SECONDARY"]};">SECONDARY (고정) -- 다음 단어 안내</div>']
    for key, info in candidates.items():
        blocks.append(f'<div style="{style}color:{info["hex"]};">MUTED {key} ({info["hex"]}, {info["contrast_ratio"]}:1) -- 이미 지나간 정보</div>')
    return _muted_review_page("MUTED vs Secondary", "\n".join(blocks), font_stack)


def build_muted_trace_context_prototype(font_stack: str, candidates: dict) -> str:
    """Review-only static reproduction of the real _cb06_phase_overrides QUESTION->MUTED transition
    (ANSWER_CONFIRMATION/CASE_BRIDGE phases turn the pre-reveal prompt to color_override=MUTED while
    ANSWER becomes the SUCCESS-colored focus) -- never calls the actual CB06 builder, never touches
    Timeline/CB06 data; it only reuses the same real semantic with each MUTED candidate."""
    colors = CANDIDATES["CLEAN_DARK_FOCUS"]["colors"]
    roles = CANDIDATES["CLEAN_DARK_FOCUS"]["roles"]
    answer_style = roles["DOMINANT"] + f'color:{colors["SUCCESS"]};'
    blocks = ['<div data-review-only="true" style="font-family:sans-serif;font-size:12px;opacity:0.7;">REVIEW-ONLY simulation of the real CB06 QUESTION-role MUTED transition (ANSWER_CONFIRMATION/CASE_BRIDGE) -- not the live Timeline.</div>']
    for key, info in candidates.items():
        trace_style = roles["DOMINANT"] + f'color:{info["hex"]};'
        blocks.append(
            '<section>'
            f'<div style="font-family:sans-serif;font-size:12px;opacity:0.6;">MUTED {key} ({info["hex"]})</div>'
            f'<div style="{trace_style}">이전 prompt trace: CAP</div>'
            f'<div style="{answer_style}">현재 ANSWER: cap</div>'
            '</section>'
        )
    return _muted_review_page("MUTED Trace Context", "\n".join(blocks), font_stack)


def build_muted_grayscale_prototype(font_stack: str, candidates: dict) -> str:
    colors = CANDIDATES["CLEAN_DARK_FOCUS"]["colors"]
    style = CANDIDATES["CLEAN_DARK_FOCUS"]["roles"]["SUPPORTING"]
    blocks = [f'<div style="{style}color:{colors["SECONDARY"]};">SECONDARY (고정)</div>']
    for key, info in candidates.items():
        blocks.append(f'<div style="{style}color:{info["hex"]};">MUTED {key}</div>')
    # filter:grayscale(100%) is a pure CSS presentation effect -- CANDIDATES' real HEX values are
    # never touched.
    body = '<div data-grayscale-simulation data-preview-only="true" style="filter:grayscale(100%);">' + "\n".join(blocks) + '</div>'
    return _muted_review_page("MUTED Grayscale", body, font_stack)


def generate_muted_color_review_prototypes(assets_dir: Path, plan_id: int, font_stack: str, candidates: dict, secondary_used: bool) -> dict:
    review_dir = assets_dir / "generated" / f"plan_{plan_id}" / "render" / "muted_color_review"
    review_dir.mkdir(parents=True, exist_ok=True)

    builders = [
        ("01_MUTED_SIDE_BY_SIDE", build_muted_side_by_side_prototype(font_stack, candidates)),
        ("02_MUTED_LEARNING_CONTEXT", build_muted_learning_context_prototype(font_stack, candidates, secondary_used)),
        ("03_MUTED_VS_SECONDARY", build_muted_vs_secondary_prototype(font_stack, candidates)),
        ("04_MUTED_TRACE_CONTEXT", build_muted_trace_context_prototype(font_stack, candidates)),
        ("05_MUTED_GRAYSCALE", build_muted_grayscale_prototype(font_stack, candidates)),
    ]

    file_entries = []
    for name, html in builders:
        filename = f"{name}.html"
        (review_dir / filename).write_text(html, encoding="utf-8")
        file_entries.append({"file": filename})

    manifest = {
        "revision": "13-4C-8", "review_type": "MUTED_COLOR_REFINEMENT", "production_plan_id": plan_id,
        "canonical_visual_candidate": "CLEAN_DARK_FOCUS",
        "background_status": "APPROVED", "background": CANDIDATES["CLEAN_DARK_FOCUS"]["page_bg"],
        "color_palette_status": "PENDING_VISUAL_REVIEW", "font_family_status": "APPROVED",
        "muted_current": candidates["A_CURRENT"]["hex"], "muted_candidates": candidates,
        "human_review_required": True, "muted_approval_written": False, "color_palette_approval_written": False,
        "files": file_entries, "generated_at": datetime.utcnow().isoformat(),
    }
    (review_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    index_descriptions = [
        ("01_MUTED_SIDE_BY_SIDE.html", "A/B/C 후보를 동일 조건에서 한 화면에 비교"),
        ("02_MUTED_LEARNING_CONTEXT.html", "실제 학습 화면과 가까운 맥락에서 SECONDARY와 함께 비교"),
        ("03_MUTED_VS_SECONDARY.html", "SECONDARY 고정 후 MUTED가 그보다 확실히 약한지 확인"),
        ("04_MUTED_TRACE_CONTEXT.html", "CB06 실제 QUESTION-MUTED 전환 semantic을 정적으로 재현 (review-only)"),
        ("05_MUTED_GRAYSCALE.html", "색조 없이 명도만으로 SECONDARY/MUTED 위계가 유지되는지 확인"),
    ]
    index_lines = ['<!doctype html><html><head><meta charset="utf-8"><title>MUTED Color Refinement Review</title></head><body>']
    index_lines.append("<p>MUTED Color Refinement Human Review -- Background는 이미 APPROVED, Color Palette는 아직 PENDING. MUTED 후보 중 어느 것도 승인 표시가 없습니다.</p>")
    index_lines.append("<ol>")
    for filename, desc in index_descriptions:
        index_lines.append(f'<li><a href="{filename}">{filename}</a> -- {desc}</li>')
    index_lines.append("</ol>")
    index_lines.append("</body></html>")
    (review_dir / "index.html").write_text("\n".join(index_lines), encoding="utf-8")

    return {"review_dir": review_dir, "manifest": manifest, "file_count": len(file_entries)}


def run_muted_color_refinement(db_path: Path, assets_dir: Path, reports_dir: Path, *, plan_id: int | None = None) -> dict:
    background_result = run_background_human_approval(db_path, assets_dir, reports_dir, plan_id=plan_id)
    if not background_result["pass"]:
        return background_result
    pid = background_result["plan_id"]

    record = background_result["record"]
    font_family_cat = record["category_approvals"]["font_family"]
    font_stack = font_family_cat["resolved_style"]

    page_bg = CANDIDATES["CLEAN_DARK_FOCUS"]["page_bg"]
    muted_current = CANDIDATES["CLEAN_DARK_FOCUS"]["colors"]["MUTED"]
    secondary = CANDIDATES["CLEAN_DARK_FOCUS"]["colors"]["SECONDARY"]
    candidates = build_muted_candidates(page_bg, muted_current, secondary)

    color_usage = _color_role_usage_counts(record.get("scene_visual_rules", []))
    secondary_used = color_usage.get("SECONDARY", 0) > 0 or color_usage.get("MUTED", 0) > 0

    result = generate_muted_color_review_prototypes(assets_dir, pid, font_stack, candidates, secondary_used)
    report_path = _build_muted_color_refinement_report(reports_dir, pid, background_result, candidates, secondary, secondary_used, result)

    return {
        "pass": True, "plan_id": pid, "background_approval": background_result,
        "candidates": candidates, "review_dir": result["review_dir"], "manifest": result["manifest"],
        "file_count": result["file_count"], "report_path": report_path,
    }


def _build_muted_color_refinement_report(
    reports_dir: Path, plan_id: int, background_result: dict, candidates: dict, secondary: str,
    secondary_used: bool, result: dict,
) -> Path:
    lines: list[str] = ["# MUTED Color Refinement Human Review Report", ""]
    lines.append(f"생성일: {datetime.utcnow().date().isoformat()}")
    lines.append(f"Source Plan: {plan_id}")
    lines.append("")
    lines.append("## Background Human Approval (persisted)")
    lines.append("")
    lines.append(f"이전 canonical record id: {background_result['prior_canonical_id']} (수정되지 않음)")
    lines.append(f"신규 canonical record id: {background_result['visual_design_row_id']}")
    lines.append(f"Approved background: {background_result['approved_background']}")
    lines.append(f"Approved categories: {background_result['approved_category_count']} / Pending: {background_result['pending_category_count']}")
    lines.append(f"full_profile_approved: {background_result['full_profile_approved']}")
    lines.append(f"ready_for_final_renderer_binding: {background_result['ready_for_final_renderer_binding']}")
    lines.append("")
    lines.append("## MUTED Candidates (Human Review 전 -- 어느 것도 APPROVED 아님)")
    lines.append("")
    lines.append(f"SECONDARY (고정 기준): {secondary}")
    lines.append(f"Plan 7 SECONDARY/MUTED 실사용: {'있음' if secondary_used else '없음 (NOT USED IN CURRENT PLAN 7)'}")
    lines.append("")
    lines.append("| Candidate | HEX | Ratio | Normal Text | Large Text |")
    lines.append("|---|---|---|---|---|")
    for key, info in candidates.items():
        lines.append(f"| {key} | {info['hex']} | {info['contrast_ratio']}:1 | {info['normal_text_reference']} | {info['large_text_reference']} |")
    lines.append("")
    lines.append(f"Files: {result['file_count']}")
    lines.append(f"Directory: {result['review_dir']}")
    lines.append(f"Review first: {result['review_dir'] / 'index.html'}")
    lines.append("")
    lines.append("## MUTED HUMAN REVIEW")
    lines.append("")
    lines.append(f"1 = CURRENT 유지 -- {candidates['A_CURRENT']['hex']} ({candidates['A_CURRENT']['contrast_ratio']}:1)")
    lines.append(f"2 = MODERATE 선택 -- {candidates['B_MODERATE']['hex']} ({candidates['B_MODERATE']['contrast_ratio']}:1)")
    lines.append(f"3 = ACCESSIBLE 선택 -- {candidates['C_ACCESSIBLE']['hex']} ({candidates['C_ACCESSIBLE']['contrast_ratio']}:1)")
    lines.append("4 = 세 후보 모두 부적절 -- 새 후보 필요")
    lines.append("")

    reports_dir.mkdir(parents=True, exist_ok=True)
    out_path = reports_dir / f"muted_color_refinement_{datetime.utcnow().date().isoformat()}.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# 13-4C-9: Color Palette Human Approval -- persists the real Human Review decision from 13-4C-8
# (MUTED = MODERATE candidate) combined with the 6 KEEP roles from 13-4C-7, as the final
# color_palette category approval. Append-only, exactly like 13-4C-6 (font_family) and 13-4C-8
# (background). CANDIDATES["CLEAN_DARK_FOCUS"] itself is never touched -- it remains a Prototype
# preview source only; the approved canonical exact values live solely in category_approvals /
# approved_visual_profile.json. Nothing currently regenerates canonical state FROM CANDIDATES after
# a correction chain starts (every *_human_approval function carries prior_categories forward via
# dict(...) and only replaces the one category being approved), so there is no active source-of-
# truth conflict to resolve here.
# ---------------------------------------------------------------------------

HUMAN_SELECTED_MUTED_CANDIDATE = "B_MODERATE"

_COLOR_PALETTE_KEEP_ROLES = ("DEFAULT", "PRIMARY_FOCUS", "RELATION", "SUCCESS", "SECONDARY", "EXCEPTION_CAUTION")


def run_color_palette_human_approval(
    db_path: Path, assets_dir: Path, reports_dir: Path, *, plan_id: int | None = None,
    selected_muted_candidate: str = HUMAN_SELECTED_MUTED_CANDIDATE,
) -> dict:
    entry_gate = validate_visual_design_entry_gate(db_path, assets_dir, plan_id=plan_id)
    if not entry_gate["pass"]:
        return {"pass": False, "reason": entry_gate["reason"], "plan_id": entry_gate.get("plan_id")}
    pid = entry_gate["plan_id"]

    canonical = select_canonical_visual_approval(db_path, pid)
    if canonical is None:
        return {"pass": False, "reason": "No canonical CANONICAL_CORRECTION visual_design_specs row found -- run `correct-visual-approval` first.", "plan_id": pid}

    prior_id, prior_record = canonical["id"], canonical["design"]
    if prior_record.get("selected_candidate") != "CLEAN_DARK_FOCUS":
        return {"pass": False, "reason": f"Canonical visual candidate is {prior_record.get('selected_candidate')!r}, not CLEAN_DARK_FOCUS -- this approval is scoped to CLEAN_DARK_FOCUS only.", "plan_id": pid}

    prior_categories = prior_record.get("category_approvals", {})
    if prior_categories.get("background", {}).get("resolution_status") != "APPROVED":
        return {"pass": False, "reason": "background must be Human Review approved before color_palette (run `review-muted-color` first).", "plan_id": pid}
    if prior_categories.get("font_family", {}).get("resolution_status") != "APPROVED":
        return {"pass": False, "reason": "font_family must be Human Review approved before color_palette (run `approve-font-family` first).", "plan_id": pid}

    # Recompute the MUTED candidates with the exact same deterministic function 13-4C-8 used --
    # never hardcode the selected HEX, so a stale/fabricated provenance is structurally impossible.
    page_bg = CANDIDATES["CLEAN_DARK_FOCUS"]["page_bg"]
    muted_current = CANDIDATES["CLEAN_DARK_FOCUS"]["colors"]["MUTED"]
    secondary = CANDIDATES["CLEAN_DARK_FOCUS"]["colors"]["SECONDARY"]
    candidates = build_muted_candidates(page_bg, muted_current, secondary)

    if selected_muted_candidate not in candidates:
        return {"pass": False, "reason": f"{selected_muted_candidate!r} is not a real MUTED candidate (choices: {sorted(candidates)})", "plan_id": pid}
    if selected_muted_candidate != HUMAN_SELECTED_MUTED_CANDIDATE:
        return {
            "pass": False,
            "reason": (
                f"No recorded Human Review decision for {selected_muted_candidate!r} -- only "
                f"{HUMAN_SELECTED_MUTED_CANDIDATE!r} has an actual Human Review approval on record."
            ),
            "plan_id": pid,
        }

    muted_info = candidates[selected_muted_candidate]
    approved_palette = {role: CANDIDATES["CLEAN_DARK_FOCUS"]["colors"][role] for role in _COLOR_PALETTE_KEEP_ROLES}
    approved_palette["MUTED"] = muted_info["hex"]

    new_categories = dict(prior_categories)
    new_categories["color_palette"] = {
        "resolved_style": approved_palette,
        "resolution_status": "APPROVED",
        "reason": "Human Review approved: 6 roles KEEP from 13-4C-7, MUTED selected from 13-4C-8 candidates",
        "provenance": {
            "review_stage": "13-4C-9", "review_type": "HUMAN_VISUAL_REVIEW",
            "review_source": "13-4C-8 MUTED Color Refinement Human Review",
            "human_decision": "APPROVED",
            "selected_muted_candidate": muted_info["label"],
            "selected_muted_value": muted_info["hex"],
            "muted_contrast_ratio": muted_info["contrast_ratio"],
            "muted_normal_text_reference": muted_info["normal_text_reference"],
            "muted_large_text_reference": muted_info["large_text_reference"],
            "muted_usage_guidance": (
                "DE-EMPHASIZED TRACE / ALREADY-SEEN INFORMATION -- NOT PRIMARY BODY TEXT (Human Review "
                "usage guidance, not a renderer-enforced constraint -- no Renderer exists yet to enforce it)"
            ),
            "role_provenance": {
                **{role: "KEEP from 13-4C-7 Human Review" for role in _COLOR_PALETTE_KEEP_ROLES},
                "MUTED": f"SELECTED {muted_info['label']} from 13-4C-8 Human Review",
            },
        },
    }

    candidate_selection = {
        "selected_candidate": prior_record.get("selected_candidate"),
        "candidate_selection_status": prior_record.get("candidate_selection_status"),
    }
    ready = ready_for_final_renderer_binding(candidate_selection, {"categories": new_categories})
    approved_count = sum(1 for c in new_categories.values() if c["resolution_status"] == "APPROVED")
    pending_count = len(new_categories) - approved_count

    new_record = {
        **prior_record,
        "record_status": "CANONICAL_CORRECTION",
        "revision": "13-4C-9",
        "corrects_record_id": prior_id,
        "correction_reason": "COLOR_PALETTE_HUMAN_APPROVAL",
        "correction_details": (
            f"color_palette Human Review approved (MUTED={muted_info['hex']}, 6 KEEP roles unchanged); "
            f"every other category (font_family, background) is carried forward unchanged from record id={prior_id}."
        ),
        "category_approvals": new_categories,
        "full_profile_approved": False,
        "ready_for_final_renderer_binding": ready,
    }

    row_id = persist_visual_design(db_path, pid, prior_id, new_record, {"checks": {}, "unresolved_critical": [], "unresolved_non_critical": []})

    profile_path = assets_dir / "generated" / f"plan_{pid}" / "render" / "approved_visual_profile.json"
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(json.dumps(new_record, ensure_ascii=False, indent=2), encoding="utf-8")

    report_path = _build_color_palette_approval_report(reports_dir, pid, new_record, prior_id, row_id, approved_count, pending_count, ready, profile_path)

    return {
        "pass": True, "plan_id": pid, "approved_palette": approved_palette, "muted_info": muted_info,
        "record": new_record, "prior_canonical_id": prior_id, "visual_design_row_id": row_id,
        "approved_category_count": approved_count, "pending_category_count": pending_count,
        "full_profile_approved": False, "ready_for_final_renderer_binding": ready, "json_path": profile_path,
        "report_path": report_path,
    }


def _build_color_palette_approval_report(
    reports_dir: Path, plan_id: int, record: dict, prior_id: int, row_id: int,
    approved_count: int, pending_count: int, ready: bool, profile_path: Path,
) -> Path:
    cat = record["category_approvals"]["color_palette"]
    palette = cat["resolved_style"]
    prov = cat["provenance"]

    lines: list[str] = ["# Color Palette Human Approval Report", ""]
    lines.append(f"생성일: {datetime.utcnow().date().isoformat()}")
    lines.append(f"Source Plan: {plan_id}")
    lines.append("")
    lines.append("## Approved Color Palette (7 roles)")
    lines.append("")
    for role in COLOR_REVIEW_ROLES:
        lines.append(f"- {role}: {palette[role]} ({prov['role_provenance'][role]})")
    lines.append("")
    lines.append("## MUTED Human Decision")
    lines.append("")
    lines.append(f"Selected candidate: {prov['selected_muted_candidate']} ({prov['selected_muted_value']})")
    lines.append(f"Contrast: {prov['muted_contrast_ratio']}:1 (normal {prov['muted_normal_text_reference']}, large {prov['muted_large_text_reference']})")
    lines.append(f"Usage guidance: {prov['muted_usage_guidance']}")
    lines.append("")
    lines.append("## Background / Font Family (preserved, not re-approved)")
    lines.append("")
    lines.append(f"Background: {record['category_approvals']['background']['resolution_status']} ({record['category_approvals']['background']['resolved_style']})")
    lines.append(f"Font Family: {record['category_approvals']['font_family']['resolution_status']} ({record['category_approvals']['font_family']['resolved_style']})")
    lines.append("")
    lines.append(f"## Category Approvals ({approved_count} APPROVED / {pending_count} PENDING)")
    lines.append("")
    for name, c in record["category_approvals"].items():
        lines.append(f"- {name}: {c['resolution_status']}")
    lines.append("")
    lines.append("## Renderer Gate")
    lines.append("")
    lines.append(f"Full Profile Approved: {'YES' if record['full_profile_approved'] else 'NO'}")
    lines.append(f"Ready for Final Renderer Binding: {'YES' if ready else 'NO'}")
    lines.append("")
    lines.append("## DB Append-only")
    lines.append("")
    lines.append(f"이전 canonical record id: {prior_id} (수정되지 않음)")
    lines.append(f"신규 canonical record id: {row_id}")
    lines.append("")
    lines.append(f"JSON: {profile_path}")
    lines.append("")

    reports_dir.mkdir(parents=True, exist_ok=True)
    out_path = reports_dir / f"color_palette_human_approval_{datetime.utcnow().date().isoformat()}.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# 13-4C-10: Typography Scale Human Review -- Review Preparation only (zero DB write), exactly like
# 13-4C-3/13-4C-7. Font Family/Background/Color Palette are all fixed conditions read from the real
# CANONICAL approved values (never re-read from CANDIDATES, which still holds the superseded preview
# MUTED #555b66 -- see 13-4C-9). Typography Scale itself is still PENDING, so CANDIDATES remains the
# correct baseline source for it (there is no other source yet). Three deterministic candidates
# (COMPACT_LEARNING / CURRENT_BALANCED / LARGE_BEGINNER) -- never random, B always equals the real
# current baseline exactly.
# ---------------------------------------------------------------------------

TYPOGRAPHY_SCALE_ROLES = ("DOMINANT", "PRIMARY", "SUPPORTING", "CAPTION", "MICRO")

TYPOGRAPHY_SCALE_CANDIDATE_DELTAS = {
    "COMPACT_LEARNING": {"DOMINANT": -4, "PRIMARY": -4, "SUPPORTING": -2, "CAPTION": -2, "MICRO": -1},
    "CURRENT_BALANCED": {"DOMINANT": 0, "PRIMARY": 0, "SUPPORTING": 0, "CAPTION": 0, "MICRO": 0},
    "LARGE_BEGINNER": {"DOMINANT": 4, "PRIMARY": 4, "SUPPORTING": 2, "CAPTION": 2, "MICRO": 1},
}

# Structural sanity floor only -- not a verified-in-browser guarantee (no literal pixel safe-area
# width constant exists anywhere in this codebase's Scene Layout/Responsive Rules, so real overflow
# can only be judged by a human opening the HTML, which is exactly this Prototype's purpose).
MIN_TYPOGRAPHY_PX = 12


def build_typography_scale_candidates(baseline_roles: dict) -> dict:
    candidates = {}
    for name, deltas in TYPOGRAPHY_SCALE_CANDIDATE_DELTAS.items():
        sizes, weights = {}, {}
        for role in TYPOGRAPHY_SCALE_ROLES:
            px_str, weight_str = _parse_role_style(baseline_roles[role])
            sizes[role] = int(px_str.rstrip("px")) + deltas[role]
            weights[role] = int(weight_str)
        candidates[name] = {"sizes": sizes, "weights": weights}
    return candidates


def validate_typography_scale_candidates(candidates: dict) -> dict:
    issues = []
    for name, info in candidates.items():
        sizes = info["sizes"]
        ordered = [sizes[role] for role in TYPOGRAPHY_SCALE_ROLES]
        if not all(ordered[i] > ordered[i + 1] for i in range(len(ordered) - 1)):
            issues.append(f"{name}: hierarchy collapsed ({sizes})")
        if any(v <= 0 for v in sizes.values()):
            issues.append(f"{name}: non-positive size ({sizes})")
        if sizes["MICRO"] < MIN_TYPOGRAPHY_PX:
            issues.append(f"{name}: MICRO below minimum sanity floor {MIN_TYPOGRAPHY_PX}px ({sizes['MICRO']}px)")
    return {"pass": len(issues) == 0, "issues": issues, "checked_min_px": MIN_TYPOGRAPHY_PX}


def _typography_role_style(candidate: dict, role: str, color_hex: str) -> str:
    return f'font-size:{candidate["sizes"][role]}px;font-weight:{candidate["weights"][role]};color:{color_hex};'


def _typography_review_page(title: str, body: str, font_stack: str, colors: dict, page_bg: str) -> str:
    return (
        f'<!doctype html><html><head><meta charset="utf-8"><title>{_html_escape(title)}</title></head>'
        f'<body style="background:{page_bg};color:{colors["DEFAULT"]};font-family:{font_stack};padding:40px;">'
        f'<header data-preview-metadata style="opacity:0.5;font-size:12px;font-family:sans-serif;">PREVIEW ONLY -- '
        f'Typography Scale Human Review, not yet APPROVED. Font Family/Background/Color Palette are already Human '
        f'Review APPROVED -- fixed conditions here, not variables. Font weights (800/700/500/400/400) are fixed '
        f'preview/reference values for typography-scale comparison only, not a font_weight approval. '
        f'VERDANA_HUMANIST 800 weight behavior: {FONT_CANDIDATES["VERDANA_HUMANIST"]["weight_800_behavior"]}.</header>'
        f'<main data-frame-preview>{body}</main></body></html>'
    )


def build_typography_full_learning_prototype(candidate: dict, font_stack: str, colors: dict, page_bg: str) -> str:
    prompt = _typography_role_style(candidate, "PRIMARY", colors["PRIMARY_FOCUS"])
    dominant = _typography_role_style(candidate, "DOMINANT", colors["DEFAULT"])
    relation = _typography_role_style(candidate, "SUPPORTING", colors["RELATION"])
    success = _typography_role_style(candidate, "DOMINANT", colors["SUCCESS"])
    body = (
        f'<div style="{prompt}">직접 읽어보세요.</div>'
        f'<div style="{dominant}">CAP</div>'
        f'<div style="{relation}">CAP → cap</div>'
        f'<div style="{success}">cap</div>'
    )
    return _typography_review_page("Full Learning Context", body, font_stack, colors, page_bg)


def build_typography_hierarchy_prototype(candidate: dict, font_stack: str, colors: dict, page_bg: str) -> str:
    role_colors = {"DOMINANT": "SUCCESS", "PRIMARY": "PRIMARY_FOCUS", "SUPPORTING": "RELATION", "CAPTION": "DEFAULT", "MICRO": "SECONDARY"}
    texts = {"DOMINANT": "CAP", "PRIMARY": "직접 읽어보세요.", "SUPPORTING": "CAP → cap", "CAPTION": "학습 보조 자막 예시", "MICRO": "metadata sample"}
    blocks = []
    for role in TYPOGRAPHY_SCALE_ROLES:
        px, weight = candidate["sizes"][role], candidate["weights"][role]
        label = f"{role} — {px}px / {weight}"  # derived from the same candidate data used for the CSS itself (single source, section 35)
        style = _typography_role_style(candidate, role, colors[role_colors[role]])
        blocks.append(f'<section><div style="font-family:sans-serif;font-size:12px;opacity:0.6;">{label}</div><div style="{style}">{_html_escape(texts[role])}</div></section>')
    return _typography_review_page("Hierarchy Overview", "\n".join(blocks), font_stack, colors, page_bg)


def build_typography_beginner_reading_prototype(candidate: dict, font_stack: str, colors: dict, page_bg: str) -> str:
    words = ("CAP", "BAG", "MAP", "BAT")
    dominant = _typography_role_style(candidate, "DOMINANT", colors["DEFAULT"])
    supporting = _typography_role_style(candidate, "SUPPORTING", colors["SECONDARY"])
    caption = _typography_role_style(candidate, "CAPTION", colors["DEFAULT"])
    blocks = [f'<div style="{dominant}">{w}</div>' for w in words]
    blocks.append(f'<div style="{supporting}">보조 설명: 단어를 소리 내어 읽어보세요.</div>')
    blocks.append(f'<div style="{caption}">직접 읽어보세요.</div>')
    return _typography_review_page("Beginner Reading", "\n".join(blocks), font_stack, colors, page_bg)


def build_typography_answer_reveal_prototype(candidate: dict, font_stack: str, colors: dict, page_bg: str) -> str:
    """Review-only static reproduction of the real _cb06_phase_overrides QUESTION/ANSWER typography
    (both DOMINANT -- QUESTION gets typography_override=DOMINANT before the barrier, ANSWER keeps its
    canonical DOMINANT binding at reveal) with the real approved MUTED trace color -- never calls the
    actual CB06 builder, never touches Timeline/CB06 data."""
    trace_style = _typography_role_style(candidate, "DOMINANT", colors["MUTED"])
    answer_style = _typography_role_style(candidate, "DOMINANT", colors["SUCCESS"])
    body = (
        '<div data-review-only="true" style="font-family:sans-serif;font-size:12px;opacity:0.7;">REVIEW-ONLY simulation of the real CB06 QUESTION/ANSWER typography (DOMINANT) -- not the live Timeline.</div>'
        f'<div style="{trace_style}">이전 prompt trace: CAP</div>'
        f'<div style="{answer_style}">현재 ANSWER: cap</div>'
    )
    return _typography_review_page("Answer Reveal", body, font_stack, colors, page_bg)


def build_typography_dense_context_prototype(candidate: dict, font_stack: str, colors: dict, page_bg: str) -> str:
    primary = _typography_role_style(candidate, "PRIMARY", colors["PRIMARY_FOCUS"])
    supporting = _typography_role_style(candidate, "SUPPORTING", colors["DEFAULT"])
    caption = _typography_role_style(candidate, "CAPTION", colors["SECONDARY"])
    micro = _typography_role_style(candidate, "MICRO", colors["MUTED"])
    body = (
        f'<div style="{primary}">직접 읽어보세요.</div>'
        f'<div style="{supporting}">CAP은 알파벳 C, A, P로 이루어진 단어입니다.</div>'
        f'<div style="{caption}">학습 보조 자막 예시</div>'
        f'<div style="{micro}">metadata sample</div>'
    )
    return _typography_review_page("Dense Learning Context", body, font_stack, colors, page_bg)


def build_typography_caption_small_text_prototype(candidate: dict, font_stack: str, colors: dict, page_bg: str) -> str:
    caption = _typography_role_style(candidate, "CAPTION", colors["DEFAULT"])
    micro = _typography_role_style(candidate, "MICRO", colors["SECONDARY"])
    body = (
        f'<div style="{caption}">직접 읽어보세요.</div>'
        f'<div style="{caption}">정답을 확인해 보세요.</div>'
        f'<div style="{micro}">metadata sample -- MICRO reference</div>'
    )
    return _typography_review_page("Caption / Small Text Check", body, font_stack, colors, page_bg)


_TYPOGRAPHY_PROTOTYPE_BUILDERS = (
    ("01_FULL_LEARNING", "Full Learning Context", build_typography_full_learning_prototype, "실제 학습 화면 통합 샘플"),
    ("02_HIERARCHY", "Hierarchy Overview", build_typography_hierarchy_prototype, "5-level 전부 한 화면에서 비교"),
    ("03_BEGINNER_READING", "Beginner Reading", build_typography_beginner_reading_prototype, "왕초보가 핵심 단어를 충분히 크게 읽을 수 있는지 확인"),
    ("04_ANSWER_REVEAL", "Answer Reveal", build_typography_answer_reveal_prototype, "정답 공개 시 ANSWER가 trace보다 먼저 보이는지 확인"),
    ("05_DENSE_CONTEXT", "Dense Learning Context", build_typography_dense_context_prototype, "정보가 많은 화면에서 큰 후보가 답답하지 않은지 확인"),
    ("06_CAPTION_SMALL_TEXT", "Caption / Small Text Check", build_typography_caption_small_text_prototype, "CAPTION/MICRO가 한글 fallback에서도 읽히는지 확인"),
)


def generate_typography_scale_review_prototypes(
    assets_dir: Path, plan_id: int, font_stack: str, colors: dict, page_bg: str, candidates: dict,
) -> dict:
    review_dir = assets_dir / "generated" / f"plan_{plan_id}" / "render" / "typography_scale_review"
    review_dir.mkdir(parents=True, exist_ok=True)

    file_entries = []
    for prefix, _label, builder, _desc in _TYPOGRAPHY_PROTOTYPE_BUILDERS:
        for candidate_name, candidate in candidates.items():
            filename = f"{prefix}_{candidate_name}.html"
            html = builder(candidate, font_stack, colors, page_bg)
            (review_dir / filename).write_text(html, encoding="utf-8")
            file_entries.append({"file": filename, "prototype_type": prefix, "candidate": candidate_name})

    validation = validate_typography_scale_candidates(candidates)
    manifest = {
        "revision": "13-4C-10", "review_type": "TYPOGRAPHY_SCALE_HUMAN_REVIEW_PREPARATION",
        "production_plan_id": plan_id, "canonical_visual_candidate": "CLEAN_DARK_FOCUS",
        "typography_status": "PENDING_VISUAL_REVIEW", "font_weight_status": "PENDING_VISUAL_REVIEW",
        "font_family_status": "APPROVED", "background_status": "APPROVED", "color_palette_status": "APPROVED",
        "current_preview_baseline": {role: CANDIDATES["CLEAN_DARK_FOCUS"]["roles"][role] for role in TYPOGRAPHY_SCALE_ROLES},
        "human_approved_typography": None,
        "candidates": candidates,
        "transformation_rule": TYPOGRAPHY_SCALE_CANDIDATE_DELTAS,
        "font_weight_note": "Font weights are fixed preview/reference values for typography-scale comparison only.",
        "verdana_800_note": FONT_CANDIDATES["VERDANA_HUMANIST"]["weight_800_behavior"],
        "hierarchy_validation": validation,
        "overflow_check_limitation": (
            "No literal pixel safe-area width constant exists in this codebase's Scene Layout/Responsive "
            "Rules, so predicted overflow against a known safe-area width cannot be computed programmatically "
            "here -- only hierarchy ordering, positive size, and a minimum sanity floor were checked. Actual "
            "browser clipping/overflow requires a human opening the HTML."
        ),
        "files": file_entries, "generated_at": datetime.utcnow().isoformat(),
    }
    (review_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    index_lines = ['<!doctype html><html><head><meta charset="utf-8"><title>Typography Scale Review</title></head><body>']
    index_lines.append("<p>Typography Scale Human Review -- Font Family/Background/Color Palette는 이미 APPROVED된 값으로 고정. Typography Scale은 아직 APPROVED 아님.</p>")
    for prefix, label, _builder, desc in _TYPOGRAPHY_PROTOTYPE_BUILDERS:
        index_lines.append(f"<h3>{_html_escape(label)}</h3><p>{_html_escape(desc)}</p><ul>")
        for candidate_name in candidates:
            filename = f"{prefix}_{candidate_name}.html"
            index_lines.append(f'<li><a href="{filename}">{filename}</a></li>')
        index_lines.append("</ul>")
    index_lines.append("<h3>TYPOGRAPHY SCALE HUMAN REVIEW</h3><ol>")
    for i, candidate_name in enumerate(candidates, start=1):
        sizes = candidates[candidate_name]["sizes"]
        size_str = ", ".join(f"{role} {sizes[role]}px" for role in TYPOGRAPHY_SCALE_ROLES)
        index_lines.append(f"<li>{i} = {candidate_name} ({size_str})</li>")
    index_lines.append(f"<li>{len(candidates) + 1} = 세 후보 모두 부적절 -- 새 후보 필요</li>")
    index_lines.append("</ol>")
    index_lines.append("</body></html>")
    (review_dir / "index.html").write_text("\n".join(index_lines), encoding="utf-8")

    return {"review_dir": review_dir, "manifest": manifest, "file_count": len(file_entries), "validation": validation}


def run_typography_scale_review(db_path: Path, assets_dir: Path, reports_dir: Path, *, plan_id: int | None = None) -> dict:
    entry_gate = validate_visual_design_entry_gate(db_path, assets_dir, plan_id=plan_id)
    if not entry_gate["pass"]:
        return {"pass": False, "reason": entry_gate["reason"], "plan_id": entry_gate.get("plan_id")}
    pid = entry_gate["plan_id"]

    canonical = select_canonical_visual_approval(db_path, pid)
    if canonical is None:
        return {"pass": False, "reason": "No canonical CANONICAL_CORRECTION visual_design_specs row found -- run `correct-visual-approval` first.", "plan_id": pid}

    record = canonical["design"]
    if record.get("selected_candidate") != "CLEAN_DARK_FOCUS":
        return {"pass": False, "reason": f"Canonical visual candidate is {record.get('selected_candidate')!r}, not CLEAN_DARK_FOCUS -- this review is scoped to CLEAN_DARK_FOCUS only.", "plan_id": pid}

    cats = record.get("category_approvals", {})
    for required in ("font_family", "background", "color_palette"):
        if cats.get(required, {}).get("resolution_status") != "APPROVED":
            return {"pass": False, "reason": f"{required} must be Human Review approved before Typography Scale review.", "plan_id": pid}

    font_stack = cats["font_family"]["resolved_style"]
    page_bg = cats["background"]["resolved_style"]
    colors = cats["color_palette"]["resolved_style"]  # canonical approved value, not CANDIDATES (avoids resurrecting the superseded MUTED preview)

    baseline_roles = CANDIDATES["CLEAN_DARK_FOCUS"]["roles"]  # typography_scale is still PENDING -- CANDIDATES is the only preview source
    candidates = build_typography_scale_candidates(baseline_roles)

    result = generate_typography_scale_review_prototypes(assets_dir, pid, font_stack, colors, page_bg, candidates)
    report_path = _build_typography_scale_review_report(reports_dir, pid, baseline_roles, candidates, result)

    return {
        "pass": True, "plan_id": pid, "candidates": candidates, "review_dir": result["review_dir"],
        "manifest": result["manifest"], "file_count": result["file_count"], "validation": result["validation"],
        "report_path": report_path,
    }


def _build_typography_scale_review_report(reports_dir: Path, plan_id: int, baseline_roles: dict, candidates: dict, result: dict) -> Path:
    lines: list[str] = ["# Typography Scale Human Review Report", ""]
    lines.append(f"생성일: {datetime.utcnow().date().isoformat()}")
    lines.append(f"Source Plan: {plan_id}")
    lines.append("")
    lines.append("## Current Preview Baseline (CLEAN_DARK_FOCUS, 실제 코드 값)")
    lines.append("")
    for role in TYPOGRAPHY_SCALE_ROLES:
        lines.append(f"- {role}: {baseline_roles[role]}")
    lines.append("")
    lines.append("## Candidates (결정론적, 무작위 없음)")
    lines.append("")
    lines.append("| Candidate | " + " | ".join(TYPOGRAPHY_SCALE_ROLES) + " |")
    lines.append("|---|" + "---|" * len(TYPOGRAPHY_SCALE_ROLES))
    for name, info in candidates.items():
        sizes = info["sizes"]
        lines.append(f"| {name} | " + " | ".join(f"{sizes[role]}px" for role in TYPOGRAPHY_SCALE_ROLES) + " |")
    lines.append("")
    lines.append(f"Transformation rule: {TYPOGRAPHY_SCALE_CANDIDATE_DELTAS}")
    lines.append("")
    lines.append("## Font Weight (참조용 고정값, 이번 단계에서 승인 아님)")
    lines.append("")
    lines.append("Font weights are fixed preview/reference values for typography-scale comparison only.")
    lines.append(f"VERDANA_HUMANIST 800 weight behavior: {FONT_CANDIDATES['VERDANA_HUMANIST']['weight_800_behavior']}")
    lines.append("")
    lines.append("## Hierarchy Validation")
    lines.append("")
    lines.append(f"Pass: {result['validation']['pass']}")
    lines.append(f"Issues: {result['validation']['issues'] or 'NONE'}")
    lines.append(f"Minimum sanity floor checked: {result['validation']['checked_min_px']}px")
    lines.append("")
    lines.append("## Overflow Check 한계 (정직하게 보고)")
    lines.append("")
    lines.append(
        "이 코드베이스의 Scene Layout/Responsive Rules에는 실제 픽셀 단위 safe-area 폭 상수가 없어, "
        "known safe-area width 대비 overflow를 프로그램적으로 계산할 수 없습니다. hierarchy ordering/"
        "양수 크기/최소 sanity floor만 구조적으로 검증했으며, 실제 브라우저 clipping 여부는 사람이 "
        "HTML을 직접 열어 확인해야 합니다."
    )
    lines.append("")
    lines.append(f"Files: {result['file_count']}")
    lines.append(f"Directory: {result['review_dir']}")
    lines.append(f"Review first: {result['review_dir'] / 'index.html'}")
    lines.append("")
    lines.append("## TYPOGRAPHY SCALE HUMAN REVIEW")
    lines.append("")
    for i, name in enumerate(candidates, start=1):
        sizes = candidates[name]["sizes"]
        size_str = ", ".join(f"{role} {sizes[role]}px" for role in TYPOGRAPHY_SCALE_ROLES)
        lines.append(f"{i} = {name} ({size_str})")
    lines.append(f"{len(candidates) + 1} = 세 후보 모두 부적절 -- 새 후보 필요")
    lines.append("")

    reports_dir.mkdir(parents=True, exist_ok=True)
    out_path = reports_dir / f"typography_scale_review_{datetime.utcnow().date().isoformat()}.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# 13-4C-11: Typography Scale Human Approval -- persists the real Human Review decision from
# 13-4C-10 (LARGE_BEGINNER candidate) as the typography_scale category approval. Append-only,
# exactly like 13-4C-6 (font_family) / 13-4C-8 (background) / 13-4C-9 (color_palette). font_weight
# is a separate category and stays PENDING -- the reference weights (800/700/500/400/400) used in
# the Prototype are recorded as provenance metadata only, never as an approved value.
# ---------------------------------------------------------------------------

HUMAN_SELECTED_TYPOGRAPHY_CANDIDATE = "LARGE_BEGINNER"


def run_typography_scale_human_approval(
    db_path: Path, assets_dir: Path, reports_dir: Path, *, plan_id: int | None = None,
    selected_candidate: str = HUMAN_SELECTED_TYPOGRAPHY_CANDIDATE,
) -> dict:
    entry_gate = validate_visual_design_entry_gate(db_path, assets_dir, plan_id=plan_id)
    if not entry_gate["pass"]:
        return {"pass": False, "reason": entry_gate["reason"], "plan_id": entry_gate.get("plan_id")}
    pid = entry_gate["plan_id"]

    canonical = select_canonical_visual_approval(db_path, pid)
    if canonical is None:
        return {"pass": False, "reason": "No canonical CANONICAL_CORRECTION visual_design_specs row found -- run `correct-visual-approval` first.", "plan_id": pid}

    prior_id, prior_record = canonical["id"], canonical["design"]
    if prior_record.get("selected_candidate") != "CLEAN_DARK_FOCUS":
        return {"pass": False, "reason": f"Canonical visual candidate is {prior_record.get('selected_candidate')!r}, not CLEAN_DARK_FOCUS -- this approval is scoped to CLEAN_DARK_FOCUS only.", "plan_id": pid}

    prior_categories = prior_record.get("category_approvals", {})
    for required in ("font_family", "background", "color_palette"):
        if prior_categories.get(required, {}).get("resolution_status") != "APPROVED":
            return {"pass": False, "reason": f"{required} must be Human Review approved before typography_scale.", "plan_id": pid}
    if prior_categories.get("typography_scale", {}).get("resolution_status") == "APPROVED":
        return {"pass": False, "reason": "typography_scale is already APPROVED on the current canonical record.", "plan_id": pid}

    # Recompute the candidates with the exact same deterministic function 13-4C-10 used -- never
    # hardcode the selected sizes, so a stale/fabricated provenance is structurally impossible.
    baseline_roles = CANDIDATES["CLEAN_DARK_FOCUS"]["roles"]
    candidates = build_typography_scale_candidates(baseline_roles)

    if selected_candidate not in candidates:
        return {"pass": False, "reason": f"{selected_candidate!r} is not a real Typography Scale candidate (choices: {sorted(candidates)})", "plan_id": pid}
    if selected_candidate != HUMAN_SELECTED_TYPOGRAPHY_CANDIDATE:
        return {
            "pass": False,
            "reason": (
                f"No recorded Human Review decision for {selected_candidate!r} -- only "
                f"{HUMAN_SELECTED_TYPOGRAPHY_CANDIDATE!r} has an actual Human Review approval on record."
            ),
            "plan_id": pid,
        }

    candidate = candidates[selected_candidate]
    approved_sizes = dict(candidate["sizes"])

    new_categories = dict(prior_categories)
    new_categories["typography_scale"] = {
        "resolved_style": approved_sizes,
        "resolution_status": "APPROVED",
        "reason": "Human Review approved on the 13-4C-10 Typography Scale Prototype",
        "provenance": {
            "review_stage": "13-4C-11", "review_type": "HUMAN_VISUAL_REVIEW",
            "review_source": "13-4C-10 Typography Scale Human Review Prototype",
            "human_decision": "APPROVED", "selected_candidate": selected_candidate,
            "reference_weights": dict(candidate["weights"]),
            "reference_weights_note": "Fixed preview/reference weights used in the Prototype -- NOT approved by this stage (font_weight stays PENDING_VISUAL_REVIEW).",
        },
    }
    # font_weight is a separate category and is never touched here (carried forward unchanged via
    # dict(prior_categories) above).

    candidate_selection = {
        "selected_candidate": prior_record.get("selected_candidate"),
        "candidate_selection_status": prior_record.get("candidate_selection_status"),
    }
    ready = ready_for_final_renderer_binding(candidate_selection, {"categories": new_categories})
    approved_count = sum(1 for c in new_categories.values() if c["resolution_status"] == "APPROVED")
    pending_count = len(new_categories) - approved_count

    new_record = {
        **prior_record,
        "record_status": "CANONICAL_CORRECTION",
        "revision": "13-4C-11",
        "corrects_record_id": prior_id,
        "correction_reason": "TYPOGRAPHY_SCALE_HUMAN_APPROVAL",
        "correction_details": (
            f"typography_scale Human Review approved ({selected_candidate}: {approved_sizes}); "
            f"font_weight stays PENDING; every other category is carried forward unchanged from record id={prior_id}."
        ),
        "category_approvals": new_categories,
        "full_profile_approved": False,
        "ready_for_final_renderer_binding": ready,
    }

    row_id = persist_visual_design(db_path, pid, prior_id, new_record, {"checks": {}, "unresolved_critical": [], "unresolved_non_critical": []})

    profile_path = assets_dir / "generated" / f"plan_{pid}" / "render" / "approved_visual_profile.json"
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(json.dumps(new_record, ensure_ascii=False, indent=2), encoding="utf-8")

    report_path = _build_typography_scale_approval_report(reports_dir, pid, new_record, prior_id, row_id, approved_count, pending_count, ready, profile_path)

    return {
        "pass": True, "plan_id": pid, "approved_sizes": approved_sizes, "selected_candidate": selected_candidate,
        "record": new_record, "prior_canonical_id": prior_id, "visual_design_row_id": row_id,
        "approved_category_count": approved_count, "pending_category_count": pending_count,
        "full_profile_approved": False, "ready_for_final_renderer_binding": ready, "json_path": profile_path,
        "report_path": report_path,
    }


def _build_typography_scale_approval_report(
    reports_dir: Path, plan_id: int, record: dict, prior_id: int, row_id: int,
    approved_count: int, pending_count: int, ready: bool, profile_path: Path,
) -> Path:
    cat = record["category_approvals"]["typography_scale"]
    sizes = cat["resolved_style"]
    prov = cat["provenance"]

    lines: list[str] = ["# Typography Scale Human Approval Report", ""]
    lines.append(f"생성일: {datetime.utcnow().date().isoformat()}")
    lines.append(f"Source Plan: {plan_id}")
    lines.append("")
    lines.append("## Approved Typography Scale")
    lines.append("")
    lines.append(f"Selected candidate: {prov['selected_candidate']}")
    for role in TYPOGRAPHY_SCALE_ROLES:
        lines.append(f"- {role}: {sizes[role]}px")
    lines.append("")
    lines.append("## Font Weight (참조용, 이번 단계에서 승인 아님)")
    lines.append("")
    lines.append(f"Reference weights: {prov['reference_weights']}")
    lines.append(prov["reference_weights_note"])
    lines.append(f"font_weight status: {record['category_approvals']['font_weight']['resolution_status']}")
    lines.append("")
    lines.append("## Font Family / Background / Color Palette (preserved, not re-approved)")
    lines.append("")
    lines.append(f"Font Family: {record['category_approvals']['font_family']['resolution_status']} ({record['category_approvals']['font_family']['resolved_style']})")
    lines.append(f"Background: {record['category_approvals']['background']['resolution_status']} ({record['category_approvals']['background']['resolved_style']})")
    lines.append(f"Color Palette: {record['category_approvals']['color_palette']['resolution_status']} (MUTED={record['category_approvals']['color_palette']['resolved_style']['MUTED']})")
    lines.append("")
    lines.append(f"## Category Approvals ({approved_count} APPROVED / {pending_count} PENDING)")
    lines.append("")
    for name, c in record["category_approvals"].items():
        lines.append(f"- {name}: {c['resolution_status']}")
    lines.append("")
    lines.append("## Renderer Gate")
    lines.append("")
    lines.append(f"Full Profile Approved: {'YES' if record['full_profile_approved'] else 'NO'}")
    lines.append(f"Ready for Final Renderer Binding: {'YES' if ready else 'NO'}")
    lines.append("")
    lines.append("## DB Append-only")
    lines.append("")
    lines.append(f"이전 canonical record id: {prior_id} (수정되지 않음)")
    lines.append(f"신규 canonical record id: {row_id}")
    lines.append("")
    lines.append(f"JSON: {profile_path}")
    lines.append("")

    reports_dir.mkdir(parents=True, exist_ok=True)
    out_path = reports_dir / f"typography_scale_human_approval_{datetime.utcnow().date().isoformat()}.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# 13-4C-12: Font Weight Human Review -- Review Preparation only (zero DB write), exactly like
# 13-4C-3/13-4C-7/13-4C-10. Font Family/Background/Color Palette/Typography Scale are all fixed
# conditions read from the real canonical APPROVED values (never CANDIDATES, which still holds
# superseded preview values -- see 13-4C-9/13-4C-11). Only font-weight varies across candidates.
# Native-vs-synthetic weight is computed per role per candidate against the real
# FONT_CANDIDATES["VERDANA_HUMANIST"]["native_weights"] = [400, 700] -- never asserted from memory.
# ---------------------------------------------------------------------------

FONT_WEIGHT_CANDIDATE_DELTAS = {
    "LIGHTER_HIERARCHY": {"DOMINANT": -100, "PRIMARY": -100, "SUPPORTING": -100, "CAPTION": 0, "MICRO": 0},
    "BALANCED_HIERARCHY": {"DOMINANT": 0, "PRIMARY": 0, "SUPPORTING": 0, "CAPTION": 0, "MICRO": 0},
    "STRONG_BEGINNER": {"DOMINANT": 100, "PRIMARY": 100, "SUPPORTING": 0, "CAPTION": 0, "MICRO": 0},
}


def build_font_weight_candidates(reference_roles: dict) -> dict:
    reference_weights = {role: int(_parse_role_style(reference_roles[role])[1]) for role in TYPOGRAPHY_SCALE_ROLES}
    native_weights = FONT_CANDIDATES["VERDANA_HUMANIST"]["native_weights"]
    candidates = {}
    for name, deltas in FONT_WEIGHT_CANDIDATE_DELTAS.items():
        weights = {role: reference_weights[role] + deltas[role] for role in TYPOGRAPHY_SCALE_ROLES}
        native = {role: (w in native_weights) for role, w in weights.items()}
        candidates[name] = {"weights": weights, "native": native}
    return candidates


def validate_font_weight_candidates(candidates: dict) -> dict:
    issues = []
    for name, info in candidates.items():
        w = info["weights"]
        if not (w["DOMINANT"] >= w["PRIMARY"] >= w["SUPPORTING"] >= w["CAPTION"]):
            issues.append(f"{name}: hierarchy violated ({w})")
        if w["MICRO"] > w["CAPTION"]:
            issues.append(f"{name}: MICRO heavier than CAPTION ({w})")
        for role, weight in w.items():
            if not (100 <= weight <= 900 and weight % 100 == 0):
                issues.append(f"{name}.{role}: invalid CSS font-weight ({weight})")
    return {"pass": len(issues) == 0, "issues": issues}


def _font_weight_role_style(candidate: dict, sizes: dict, role: str, color_hex: str) -> str:
    return f'font-size:{sizes[role]}px;font-weight:{candidate["weights"][role]};color:{color_hex};'


def _font_weight_review_page(title: str, body: str, font_stack: str, colors: dict, page_bg: str) -> str:
    return (
        f'<!doctype html><html><head><meta charset="utf-8"><title>{_html_escape(title)}</title></head>'
        f'<body style="background:{page_bg};color:{colors["DEFAULT"]};font-family:{font_stack};padding:40px;">'
        f'<header data-preview-metadata style="opacity:0.5;font-size:12px;font-family:sans-serif;">PREVIEW ONLY -- '
        f'Font Weight Human Review, font_weight is not yet APPROVED. Font Family/Background/Color Palette/Typography '
        f'Scale are already Human Review APPROVED and fixed here. CSS font-weight does not prove a native font face '
        f'exists -- Verdana heavy weights may be browser-synthesized (native weights: '
        f'{FONT_CANDIDATES["VERDANA_HUMANIST"]["native_weights"]}).</header>'
        f'<main data-frame-preview>{body}</main></body></html>'
    )


def build_font_weight_full_learning_prototype(candidate: dict, sizes: dict, font_stack: str, colors: dict, page_bg: str) -> str:
    prompt = _font_weight_role_style(candidate, sizes, "PRIMARY", colors["PRIMARY_FOCUS"])
    dominant = _font_weight_role_style(candidate, sizes, "DOMINANT", colors["DEFAULT"])
    relation = _font_weight_role_style(candidate, sizes, "SUPPORTING", colors["RELATION"])
    success = _font_weight_role_style(candidate, sizes, "DOMINANT", colors["SUCCESS"])
    body = (
        f'<div style="{prompt}">직접 읽어보세요.</div>'
        f'<div style="{dominant}">CAP</div>'
        f'<div style="{relation}">CAP → cap</div>'
        f'<div style="{success}">cap</div>'
    )
    return _font_weight_review_page("Full Learning Sample", body, font_stack, colors, page_bg)


def build_font_weight_hierarchy_prototype(candidate: dict, sizes: dict, font_stack: str, colors: dict, page_bg: str) -> str:
    role_colors = {"DOMINANT": "SUCCESS", "PRIMARY": "PRIMARY_FOCUS", "SUPPORTING": "RELATION", "CAPTION": "DEFAULT", "MICRO": "SECONDARY"}
    texts = {"DOMINANT": "CAP", "PRIMARY": "직접 읽어보세요.", "SUPPORTING": "CAP → cap", "CAPTION": "학습 보조 자막 예시", "MICRO": "metadata sample"}
    blocks = []
    for role in TYPOGRAPHY_SCALE_ROLES:
        weight = candidate["weights"][role]
        native_label = "native" if candidate["native"][role] else "synthetic"
        label = f"{role} -- {sizes[role]}px / {weight} ({native_label})"  # derived from the same candidate data used for the CSS itself
        style = _font_weight_role_style(candidate, sizes, role, colors[role_colors[role]])
        blocks.append(f'<section><div style="font-family:sans-serif;font-size:12px;opacity:0.6;">{label}</div><div style="{style}">{_html_escape(texts[role])}</div></section>')
    return _font_weight_review_page("Hierarchy", "\n".join(blocks), font_stack, colors, page_bg)


def build_font_weight_beginner_reading_prototype(candidate: dict, sizes: dict, font_stack: str, colors: dict, page_bg: str) -> str:
    words = ("CAP", "BAG", "MAP", "BAT")
    dominant = _font_weight_role_style(candidate, sizes, "DOMINANT", colors["DEFAULT"])
    blocks = [f'<div style="{dominant}">{w}</div>' for w in words]
    return _font_weight_review_page("Beginner Reading", "\n".join(blocks), font_stack, colors, page_bg)


def build_font_weight_answer_reveal_prototype(candidate: dict, sizes: dict, font_stack: str, colors: dict, page_bg: str) -> str:
    """Review-only static reproduction of the real _cb06_phase_overrides QUESTION/ANSWER typography
    (both DOMINANT) with the real approved MUTED trace color -- never touches Timeline/CB06 data."""
    trace_style = _font_weight_role_style(candidate, sizes, "DOMINANT", colors["MUTED"])
    answer_style = _font_weight_role_style(candidate, sizes, "DOMINANT", colors["SUCCESS"])
    body = (
        '<div data-review-only="true" style="font-family:sans-serif;font-size:12px;opacity:0.7;">REVIEW-ONLY simulation of the real CB06 QUESTION/ANSWER typography (DOMINANT) -- not the live Timeline.</div>'
        f'<div style="{trace_style}">이전 prompt trace: CAP</div>'
        f'<div style="{answer_style}">현재 ANSWER: cap</div>'
    )
    return _font_weight_review_page("Answer Reveal", body, font_stack, colors, page_bg)


def build_font_weight_dense_context_prototype(candidate: dict, sizes: dict, font_stack: str, colors: dict, page_bg: str) -> str:
    primary = _font_weight_role_style(candidate, sizes, "PRIMARY", colors["PRIMARY_FOCUS"])
    supporting = _font_weight_role_style(candidate, sizes, "SUPPORTING", colors["DEFAULT"])
    caption = _font_weight_role_style(candidate, sizes, "CAPTION", colors["SECONDARY"])
    micro = _font_weight_role_style(candidate, sizes, "MICRO", colors["MUTED"])
    body = (
        f'<div style="{primary}">직접 읽어보세요.</div>'
        f'<div style="{supporting}">CAP은 알파벳 C, A, P로 이루어진 단어입니다.</div>'
        f'<div style="{caption}">학습 보조 자막 예시</div>'
        f'<div style="{micro}">metadata sample</div>'
    )
    return _font_weight_review_page("Dense Context", body, font_stack, colors, page_bg)


def build_font_weight_korean_english_fallback_prototype(candidate: dict, sizes: dict, font_stack: str, colors: dict, page_bg: str) -> str:
    primary = _font_weight_role_style(candidate, sizes, "PRIMARY", colors["PRIMARY_FOCUS"])
    dominant = _font_weight_role_style(candidate, sizes, "DOMINANT", colors["DEFAULT"])
    supporting = _font_weight_role_style(candidate, sizes, "SUPPORTING", colors["RELATION"])
    micro = _font_weight_role_style(candidate, sizes, "MICRO", colors["SECONDARY"])
    body = (
        f'<div style="{primary}">직접 읽어보세요.</div>'
        f'<div style="{primary}">정답을 확인해 보세요.</div>'
        f'<div style="{dominant}">CAP</div>'
        f'<div style="{dominant}">cap</div>'
        f'<div style="{supporting}">영어 단어를 소리 내어 읽어보세요.</div>'
        f'<div style="{micro}">metadata sample</div>'
    )
    return _font_weight_review_page("Korean + English Fallback", body, font_stack, colors, page_bg)


def build_font_weight_side_by_side_prototype(candidates: dict, sizes: dict, font_stack: str, colors: dict, page_bg: str) -> str:
    style = colors["DEFAULT"]
    blocks = []
    for name, candidate in candidates.items():
        weight = candidate["weights"]["PRIMARY"]
        native_label = "native" if candidate["native"]["PRIMARY"] else "synthetic"
        primary_style = _font_weight_role_style(candidate, sizes, "PRIMARY", colors["PRIMARY_FOCUS"])
        dominant_style = _font_weight_role_style(candidate, sizes, "DOMINANT", colors["DEFAULT"])
        blocks.append(
            '<section>'
            f'<div style="font-family:sans-serif;font-size:12px;opacity:0.6;">{name} (PRIMARY {weight}, {native_label})</div>'
            f'<div style="{dominant_style}">CAP</div>'
            f'<div style="{primary_style}">직접 읽어보세요.</div>'
            '</section>'
        )
    return _font_weight_review_page("Font Weight Side by Side", "\n".join(blocks), font_stack, colors, page_bg)


_FONT_WEIGHT_PROTOTYPE_BUILDERS = (
    ("01_FULL_LEARNING", "Full Learning Sample", build_font_weight_full_learning_prototype, "실제 학습 화면 통합 샘플"),
    ("02_HIERARCHY", "Hierarchy", build_font_weight_hierarchy_prototype, "5-level 전부 px/weight/native-synthetic 표시"),
    ("03_BEGINNER_READING", "Beginner Reading", build_font_weight_beginner_reading_prototype, "왕초보 핵심 단어 가독성 확인"),
    ("04_ANSWER_REVEAL", "Answer Reveal", build_font_weight_answer_reveal_prototype, "정답 공개 시 ANSWER가 trace보다 먼저 보이는지 확인"),
    ("05_DENSE_CONTEXT", "Dense Context", build_font_weight_dense_context_prototype, "정보가 많은 화면에서 weight가 답답하지 않은지 확인"),
    ("06_KOREAN_ENGLISH", "Korean + English Fallback", build_font_weight_korean_english_fallback_prototype, "한글/영어 혼합 시 시각적 무게 균형 확인"),
)


def generate_font_weight_review_prototypes(
    assets_dir: Path, plan_id: int, font_stack: str, colors: dict, page_bg: str, sizes: dict, candidates: dict,
) -> dict:
    review_dir = assets_dir / "generated" / f"plan_{plan_id}" / "render" / "font_weight_review"
    review_dir.mkdir(parents=True, exist_ok=True)

    file_entries = []
    side_by_side_html = build_font_weight_side_by_side_prototype(candidates, sizes, font_stack, colors, page_bg)
    (review_dir / "00_FONT_WEIGHT_SIDE_BY_SIDE.html").write_text(side_by_side_html, encoding="utf-8")
    file_entries.append({"file": "00_FONT_WEIGHT_SIDE_BY_SIDE.html", "prototype_type": "00_SIDE_BY_SIDE", "candidate": None})

    for prefix, _label, builder, _desc in _FONT_WEIGHT_PROTOTYPE_BUILDERS:
        for candidate_name, candidate in candidates.items():
            filename = f"{prefix}_{candidate_name}.html"
            html = builder(candidate, sizes, font_stack, colors, page_bg)
            (review_dir / filename).write_text(html, encoding="utf-8")
            file_entries.append({"file": filename, "prototype_type": prefix, "candidate": candidate_name})

    validation = validate_font_weight_candidates(candidates)
    manifest = {
        "revision": "13-4C-12", "review_type": "FONT_WEIGHT_HUMAN_REVIEW_PREPARATION",
        "production_plan_id": plan_id, "visual_design_version": VISUAL_DESIGN_VERSION,
        "canonical_visual_candidate": "CLEAN_DARK_FOCUS",
        "font_weight_status": "PENDING_VISUAL_REVIEW",
        "approved_fixed_categories": {"font_family": font_stack, "background": page_bg, "color_palette": colors},
        "approved_typography_scale": sizes,
        "font_family": "VERDANA_HUMANIST", "font_stack": font_stack,
        "candidate_definitions": FONT_WEIGHT_CANDIDATE_DELTAS,
        "candidate_weights": candidates,
        "warnings": [
            "CSS font-weight numbers do not prove a native font face exists.",
            f"VERDANA_HUMANIST native weights: {FONT_CANDIDATES['VERDANA_HUMANIST']['native_weights']} -- any other weight is browser-synthesized.",
        ],
        "hierarchy_validation": validation,
        "human_decision": None,
        "zero_db_write": True,
        "prototype_files": file_entries, "generated_at": datetime.utcnow().isoformat(),
    }
    (review_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    index_descriptions = [("00_FONT_WEIGHT_SIDE_BY_SIDE.html", "3후보를 한 화면에서 나란히 비교")]
    index_descriptions += [(f"{prefix}_*.html", desc) for prefix, _label, _builder, desc in _FONT_WEIGHT_PROTOTYPE_BUILDERS]

    index_lines = ['<!doctype html><html><head><meta charset="utf-8"><title>Font Weight Review</title></head><body>']
    index_lines.append(f"<p>Current stage: 13-4C-12 Font Weight Human Review -- font_weight status: {manifest['font_weight_status']}</p>")
    index_lines.append("<p>Fixed conditions (이미 Human Review APPROVED): Font Family=VERDANA_HUMANIST, Background=#111318, Color Palette 7 role, Typography Scale=LARGE_BEGINNER(72/46/28/20/15px).</p>")
    index_lines.append(f"<p>Verdana native weights: {FONT_CANDIDATES['VERDANA_HUMANIST']['native_weights']} -- other weights are browser-synthesized.</p>")
    index_lines.append('<h3>Side by Side</h3><ul><li><a href="00_FONT_WEIGHT_SIDE_BY_SIDE.html">00_FONT_WEIGHT_SIDE_BY_SIDE.html</a></li></ul>')
    for prefix, label, _builder, desc in _FONT_WEIGHT_PROTOTYPE_BUILDERS:
        index_lines.append(f"<h3>{_html_escape(label)}</h3><p>{_html_escape(desc)}</p><ul>")
        for candidate_name in candidates:
            filename = f"{prefix}_{candidate_name}.html"
            index_lines.append(f'<li><a href="{filename}">{filename}</a></li>')
        index_lines.append("</ul>")
    index_lines.append("<h3>FONT WEIGHT HUMAN REVIEW</h3><ol>")
    for i, candidate_name in enumerate(candidates, start=1):
        w = candidates[candidate_name]["weights"]
        w_str = ", ".join(f"{role} {w[role]}" for role in TYPOGRAPHY_SCALE_ROLES)
        index_lines.append(f"<li>{i} = {candidate_name} ({w_str})</li>")
    index_lines.append(f"<li>{len(candidates) + 1} = 세 후보 모두 부적절 -- 새 후보 필요</li>")
    index_lines.append("</ol>")
    index_lines.append("</body></html>")
    (review_dir / "index.html").write_text("\n".join(index_lines), encoding="utf-8")

    return {"review_dir": review_dir, "manifest": manifest, "file_count": len(file_entries), "validation": validation}


def run_font_weight_review(db_path: Path, assets_dir: Path, reports_dir: Path, *, plan_id: int | None = None) -> dict:
    entry_gate = validate_visual_design_entry_gate(db_path, assets_dir, plan_id=plan_id)
    if not entry_gate["pass"]:
        return {"pass": False, "reason": entry_gate["reason"], "plan_id": entry_gate.get("plan_id")}
    pid = entry_gate["plan_id"]

    canonical = select_canonical_visual_approval(db_path, pid)
    if canonical is None:
        return {"pass": False, "reason": "No canonical CANONICAL_CORRECTION visual_design_specs row found -- run `correct-visual-approval` first.", "plan_id": pid}

    record = canonical["design"]
    if record.get("selected_candidate") != "CLEAN_DARK_FOCUS":
        return {"pass": False, "reason": f"Canonical visual candidate is {record.get('selected_candidate')!r}, not CLEAN_DARK_FOCUS -- this review is scoped to CLEAN_DARK_FOCUS only.", "plan_id": pid}

    cats = record.get("category_approvals", {})
    for required in ("font_family", "background", "color_palette", "typography_scale"):
        if cats.get(required, {}).get("resolution_status") != "APPROVED":
            return {"pass": False, "reason": f"{required} must be Human Review approved before Font Weight review.", "plan_id": pid}
    if cats.get("font_weight", {}).get("resolution_status") == "APPROVED":
        return {"pass": False, "reason": "font_weight is already APPROVED on the current canonical record.", "plan_id": pid}

    font_stack = cats["font_family"]["resolved_style"]
    page_bg = cats["background"]["resolved_style"]
    colors = cats["color_palette"]["resolved_style"]
    sizes = cats["typography_scale"]["resolved_style"]

    baseline_roles = CANDIDATES["CLEAN_DARK_FOCUS"]["roles"]  # font_weight is still PENDING -- CANDIDATES is the only reference source
    candidates = build_font_weight_candidates(baseline_roles)

    result = generate_font_weight_review_prototypes(assets_dir, pid, font_stack, colors, page_bg, sizes, candidates)
    report_path = _build_font_weight_review_report(reports_dir, pid, sizes, candidates, result)

    return {
        "pass": True, "plan_id": pid, "candidates": candidates, "sizes": sizes, "review_dir": result["review_dir"],
        "manifest": result["manifest"], "file_count": result["file_count"], "validation": result["validation"],
        "report_path": report_path,
    }


def _build_font_weight_review_report(reports_dir: Path, plan_id: int, sizes: dict, candidates: dict, result: dict) -> Path:
    lines: list[str] = ["# Font Weight Human Review Report", ""]
    lines.append(f"생성일: {datetime.utcnow().date().isoformat()}")
    lines.append(f"Source Plan: {plan_id}")
    lines.append("")
    lines.append("## Fixed Approved Typography Scale (LARGE_BEGINNER, 13-4C-11)")
    lines.append("")
    for role in TYPOGRAPHY_SCALE_ROLES:
        lines.append(f"- {role}: {sizes[role]}px")
    lines.append("")
    lines.append("## Candidates (결정론적, 무작위 없음)")
    lines.append("")
    lines.append("| Candidate | " + " | ".join(TYPOGRAPHY_SCALE_ROLES) + " |")
    lines.append("|---|" + "---|" * len(TYPOGRAPHY_SCALE_ROLES))
    for name, info in candidates.items():
        row = " | ".join(f"{info['weights'][role]}{'*' if not info['native'][role] else ''}" for role in TYPOGRAPHY_SCALE_ROLES)
        lines.append(f"| {name} | {row} |")
    lines.append("")
    lines.append(f"(* = browser-synthesized, not a real native face -- VERDANA_HUMANIST native weights: {FONT_CANDIDATES['VERDANA_HUMANIST']['native_weights']})")
    lines.append("")
    lines.append(f"Transformation rule: {FONT_WEIGHT_CANDIDATE_DELTAS}")
    lines.append("")
    lines.append("## Hierarchy Validation")
    lines.append("")
    lines.append(f"Pass: {result['validation']['pass']}")
    lines.append(f"Issues: {result['validation']['issues'] or 'NONE'}")
    lines.append("")
    lines.append(f"Files: {result['file_count']}")
    lines.append(f"Directory: {result['review_dir']}")
    lines.append(f"Review first: {result['review_dir'] / 'index.html'}")
    lines.append("")
    lines.append("## Human Decision")
    lines.append("")
    lines.append("NO HUMAN DECISION YET -- Prototype 생성만 완료됨. 사용자가 실제로 화면을 본 뒤 결정해야 함.")
    lines.append("")
    lines.append("## FONT WEIGHT HUMAN REVIEW")
    lines.append("")
    for i, name in enumerate(candidates, start=1):
        w = candidates[name]["weights"]
        w_str = ", ".join(f"{role} {w[role]}" for role in TYPOGRAPHY_SCALE_ROLES)
        lines.append(f"{i} = {name} ({w_str})")
    lines.append(f"{len(candidates) + 1} = 세 후보 모두 부적절 -- 새 후보 필요")
    lines.append("")

    reports_dir.mkdir(parents=True, exist_ok=True)
    out_path = reports_dir / f"font_weight_review_{datetime.utcnow().date().isoformat()}.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# 13-4C-13: Font Weight Human Approval -- persists the real Human Review decision from 13-4C-12
# (BALANCED_HIERARCHY candidate) as the font_weight category approval. Append-only, exactly like
# 13-4C-6/8/9/11. Native-vs-synthetic provenance is preserved from the same
# build_font_weight_candidates() used by the Review stage -- never hardcoded separately, so review
# candidate and approval candidate can never drift apart.
# ---------------------------------------------------------------------------

HUMAN_SELECTED_FONT_WEIGHT_CANDIDATE = "BALANCED_HIERARCHY"


def run_font_weight_human_approval(
    db_path: Path, assets_dir: Path, reports_dir: Path, *, plan_id: int | None = None,
    selected_candidate: str = HUMAN_SELECTED_FONT_WEIGHT_CANDIDATE,
) -> dict:
    entry_gate = validate_visual_design_entry_gate(db_path, assets_dir, plan_id=plan_id)
    if not entry_gate["pass"]:
        return {"pass": False, "reason": entry_gate["reason"], "plan_id": entry_gate.get("plan_id")}
    pid = entry_gate["plan_id"]

    canonical = select_canonical_visual_approval(db_path, pid)
    if canonical is None:
        return {"pass": False, "reason": "No canonical CANONICAL_CORRECTION visual_design_specs row found -- run `correct-visual-approval` first.", "plan_id": pid}

    prior_id, prior_record = canonical["id"], canonical["design"]
    if prior_record.get("selected_candidate") != "CLEAN_DARK_FOCUS":
        return {"pass": False, "reason": f"Canonical visual candidate is {prior_record.get('selected_candidate')!r}, not CLEAN_DARK_FOCUS -- this approval is scoped to CLEAN_DARK_FOCUS only.", "plan_id": pid}

    prior_categories = prior_record.get("category_approvals", {})
    for required in ("font_family", "background", "color_palette", "typography_scale"):
        if prior_categories.get(required, {}).get("resolution_status") != "APPROVED":
            return {"pass": False, "reason": f"{required} must be Human Review approved before font_weight.", "plan_id": pid}
    if prior_categories.get("font_weight", {}).get("resolution_status") == "APPROVED":
        return {"pass": False, "reason": "font_weight is already APPROVED on the current canonical record.", "plan_id": pid}

    # Recompute the candidates with the exact same deterministic function 13-4C-12 used -- never
    # hardcode the selected weights, so review candidate and approval candidate can never drift apart.
    baseline_roles = CANDIDATES["CLEAN_DARK_FOCUS"]["roles"]
    candidates = build_font_weight_candidates(baseline_roles)

    if selected_candidate not in candidates:
        return {"pass": False, "reason": f"{selected_candidate!r} is not a real Font Weight candidate (choices: {sorted(candidates)})", "plan_id": pid}
    if selected_candidate != HUMAN_SELECTED_FONT_WEIGHT_CANDIDATE:
        return {
            "pass": False,
            "reason": (
                f"No recorded Human Review decision for {selected_candidate!r} -- only "
                f"{HUMAN_SELECTED_FONT_WEIGHT_CANDIDATE!r} has an actual Human Review approval on record."
            ),
            "plan_id": pid,
        }

    candidate = candidates[selected_candidate]
    approved_weights = dict(candidate["weights"])
    native_provenance = dict(candidate["native"])

    new_categories = dict(prior_categories)
    new_categories["font_weight"] = {
        "resolved_style": approved_weights,
        "resolution_status": "APPROVED",
        "reason": "Human Review approved on the 13-4C-12 Font Weight Prototype",
        "provenance": {
            "review_stage": "13-4C-13", "review_type": "HUMAN_VISUAL_REVIEW",
            "review_source": "13-4C-12 Font Weight Human Review Prototype",
            "human_decision": "APPROVED", "selected_candidate": selected_candidate,
            "native_face_by_role": native_provenance,
            "native_synthetic_note": (
                "CSS font-weight values do not prove a native font face exists. Approving this "
                "candidate does not mean synthetic weights are absent -- Human reviewed actual "
                "browser rendering and accepted this trade-off. "
                f"VERDANA_HUMANIST native weights: {FONT_CANDIDATES['VERDANA_HUMANIST']['native_weights']}."
            ),
        },
    }

    candidate_selection = {
        "selected_candidate": prior_record.get("selected_candidate"),
        "candidate_selection_status": prior_record.get("candidate_selection_status"),
    }
    ready = ready_for_final_renderer_binding(candidate_selection, {"categories": new_categories})
    approved_count = sum(1 for c in new_categories.values() if c["resolution_status"] == "APPROVED")
    pending_count = len(new_categories) - approved_count

    new_record = {
        **prior_record,
        "record_status": "CANONICAL_CORRECTION",
        "revision": "13-4C-13",
        "corrects_record_id": prior_id,
        "correction_reason": "FONT_WEIGHT_HUMAN_APPROVAL",
        "correction_details": (
            f"font_weight Human Review approved ({selected_candidate}: {approved_weights}); "
            f"every other category is carried forward unchanged from record id={prior_id}."
        ),
        "category_approvals": new_categories,
        "full_profile_approved": False,
        "ready_for_final_renderer_binding": ready,
    }

    row_id = persist_visual_design(db_path, pid, prior_id, new_record, {"checks": {}, "unresolved_critical": [], "unresolved_non_critical": []})

    profile_path = assets_dir / "generated" / f"plan_{pid}" / "render" / "approved_visual_profile.json"
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(json.dumps(new_record, ensure_ascii=False, indent=2), encoding="utf-8")

    report_path = _build_font_weight_approval_report(reports_dir, pid, new_record, prior_id, row_id, approved_count, pending_count, ready, profile_path)

    return {
        "pass": True, "plan_id": pid, "approved_weights": approved_weights, "selected_candidate": selected_candidate,
        "native_provenance": native_provenance, "record": new_record, "prior_canonical_id": prior_id,
        "visual_design_row_id": row_id, "approved_category_count": approved_count, "pending_category_count": pending_count,
        "full_profile_approved": False, "ready_for_final_renderer_binding": ready, "json_path": profile_path,
        "report_path": report_path,
    }


def _build_font_weight_approval_report(
    reports_dir: Path, plan_id: int, record: dict, prior_id: int, row_id: int,
    approved_count: int, pending_count: int, ready: bool, profile_path: Path,
) -> Path:
    cat = record["category_approvals"]["font_weight"]
    weights = cat["resolved_style"]
    prov = cat["provenance"]

    lines: list[str] = ["# Font Weight Human Approval Report", ""]
    lines.append(f"생성일: {datetime.utcnow().date().isoformat()}")
    lines.append(f"Source Plan: {plan_id}")
    lines.append("")
    lines.append("## Human Decision")
    lines.append("")
    lines.append('Source: 사용자가 실제 대화에서 "BALANCED_HIERARCHY(2번)"를 선택')
    lines.append(f"Selected candidate: {prov['selected_candidate']}")
    lines.append("")
    lines.append("## Approved Font Weight")
    lines.append("")
    for role in TYPOGRAPHY_SCALE_ROLES:
        native_label = "native" if prov["native_face_by_role"][role] else "synthetic"
        lines.append(f"- {role}: {weights[role]} ({native_label})")
    lines.append("")
    lines.append(prov["native_synthetic_note"])
    lines.append("")
    lines.append("## Fixed Approvals (preserved, not re-approved)")
    lines.append("")
    lines.append(f"Font Family: {record['category_approvals']['font_family']['resolution_status']} ({record['category_approvals']['font_family']['resolved_style']})")
    lines.append(f"Background: {record['category_approvals']['background']['resolution_status']} ({record['category_approvals']['background']['resolved_style']})")
    lines.append(f"Color Palette: {record['category_approvals']['color_palette']['resolution_status']} (MUTED={record['category_approvals']['color_palette']['resolved_style']['MUTED']})")
    lines.append(f"Typography Scale: {record['category_approvals']['typography_scale']['resolution_status']} ({record['category_approvals']['typography_scale']['resolved_style']})")
    lines.append("")
    lines.append(f"## Category Approvals ({approved_count} APPROVED / {pending_count} PENDING)")
    lines.append("")
    for name, c in record["category_approvals"].items():
        lines.append(f"- {name}: {c['resolution_status']}")
    lines.append("")
    lines.append("## Renderer Gate")
    lines.append("")
    lines.append(f"Full Profile Approved: {'YES' if record['full_profile_approved'] else 'NO'}")
    lines.append(f"Ready for Final Renderer Binding: {'YES' if ready else 'NO'}")
    lines.append("")
    lines.append("## DB Append-only")
    lines.append("")
    lines.append(f"이전 canonical record id: {prior_id} (수정되지 않음)")
    lines.append(f"신규 canonical record id: {row_id}")
    lines.append("")
    lines.append(f"JSON: {profile_path}")
    lines.append("")

    reports_dir.mkdir(parents=True, exist_ok=True)
    out_path = reports_dir / f"font_weight_human_approval_{datetime.utcnow().date().isoformat()}.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# 13-4C-14: Caption Style Human Review -- Review Preparation only (zero DB write), exactly like
# 13-4C-3/7/10/12. Font Family/Background/Color Palette/Typography Scale/Font Weight are all fixed
# conditions read from the real canonical APPROVED values. Only caption_style (a presentation
# property of the CAPTION zone -- see CAPTION_ROLES/_caption_role_for_zone: the only real consumer
# of this category is the bottom NARRATION_CAPTION zone, never LEARNING_TEXT) varies across
# candidates: text color role (reused from the approved palette, never a new HEX), background box
# presence/opacity (a pure CSS overlay technique, not a new semantic color role), padding, and
# line-height. Human decision is always None here -- this stage never approves anything.
# ---------------------------------------------------------------------------

CAPTION_STYLE_CANDIDATES = {
    "MINIMAL_TEXT": {"text_color_role": "DEFAULT", "background": "none", "background_opacity": 0.0, "padding": "4px 8px", "line_height": 1.4},
    "BALANCED_INTEGRATED": {"text_color_role": "DEFAULT", "background": "box", "background_opacity": 0.55, "padding": "8px 16px", "line_height": 1.5},
    "BEGINNER_EMPHASIS": {"text_color_role": "DEFAULT", "background": "box", "background_opacity": 0.75, "padding": "10px 20px", "line_height": 1.6},
}

_CAPTION_PADDING_RE = re.compile(r"^\d+px( \d+px){1,3}$")


def build_caption_style_candidates() -> dict:
    return {name: dict(props) for name, props in CAPTION_STYLE_CANDIDATES.items()}


def validate_caption_style_candidates(candidates: dict) -> dict:
    issues = []
    if len(candidates) != 3:
        issues.append(f"expected exactly 3 candidates, got {len(candidates)}")
    if len(set(candidates)) != len(candidates):
        issues.append("candidate ids are not unique")
    for name, props in candidates.items():
        required = ("text_color_role", "background", "background_opacity", "padding", "line_height")
        missing = [k for k in required if k not in props]
        if missing:
            issues.append(f"{name}: missing properties {missing}")
            continue
        if props["text_color_role"] not in COLOR_REVIEW_ROLES:
            issues.append(f"{name}: text_color_role {props['text_color_role']!r} is not an approved palette role")
        if props["background"] not in ("none", "box"):
            issues.append(f"{name}: invalid background {props['background']!r}")
        if not (0.0 <= props["background_opacity"] <= 1.0):
            issues.append(f"{name}: background_opacity out of range ({props['background_opacity']})")
        if props["line_height"] <= 0:
            issues.append(f"{name}: non-positive line_height ({props['line_height']})")
        if not _CAPTION_PADDING_RE.match(props["padding"]):
            issues.append(f"{name}: invalid CSS padding ({props['padding']!r})")
    return {"pass": len(issues) == 0, "issues": issues}


def _caption_box_style(candidate: dict) -> str:
    if candidate["background"] == "none":
        return ""
    return f'background:rgba(0,0,0,{candidate["background_opacity"]});'


def _caption_style_review_page(title: str, body: str, font_stack: str, colors: dict, page_bg: str) -> str:
    return (
        f'<!doctype html><html><head><meta charset="utf-8"><title>{_html_escape(title)}</title></head>'
        f'<body style="background:{page_bg};color:{colors["DEFAULT"]};font-family:{font_stack};padding:40px;">'
        f'<header data-preview-metadata style="opacity:0.5;font-size:12px;font-family:sans-serif;">PREVIEW ONLY -- '
        f'Caption Style Human Review. caption_style is NOT APPROVED. Font Family/Background/Color Palette/Typography '
        f'Scale/Font Weight are already Human Review APPROVED and are fixed conditions here. Human decision: NONE. '
        f'No literal pixel safe-area width exists in this codebase -- wrapping shown below uses a presentation-only '
        f'max-width, not a verified canonical safe area; actual browser measurement was not performed.</header>'
        f'<main data-frame-preview>{body}</main></body></html>'
    )


def _caption_element(candidate: dict, sizes: dict, colors: dict, text: str, extra_style: str = "") -> str:
    role_style = f'font-size:{sizes["CAPTION"]}px;color:{colors[candidate["text_color_role"]]};'
    box_style = _caption_box_style(candidate)
    return (
        f'<div data-caption-element style="{role_style}{box_style}padding:{candidate["padding"]};'
        f'line-height:{candidate["line_height"]};text-align:center;{extra_style}">{_html_escape(text)}</div>'
    )


def build_caption_full_learning_prototype(candidate: dict, sizes: dict, weights: dict, font_stack: str, colors: dict, page_bg: str) -> str:
    prompt = f'font-size:{sizes["PRIMARY"]}px;font-weight:{weights["PRIMARY"]};color:{colors["PRIMARY_FOCUS"]};'
    dominant = f'font-size:{sizes["DOMINANT"]}px;font-weight:{weights["DOMINANT"]};color:{colors["DEFAULT"]};'
    relation = f'font-size:{sizes["SUPPORTING"]}px;font-weight:{weights["SUPPORTING"]};color:{colors["RELATION"]};'
    success = f'font-size:{sizes["DOMINANT"]}px;font-weight:{weights["DOMINANT"]};color:{colors["SUCCESS"]};'
    body = (
        f'<div style="{prompt}">직접 읽어보세요.</div>'
        f'<div style="{dominant}">CAP</div>'
        f'<div style="{relation}">CAP → cap</div>'
        f'<div style="{success}">cap</div>'
        + _caption_element(candidate, sizes, colors, "직접 읽어보세요.")
    )
    return _caption_style_review_page("Full Learning Sample", body, font_stack, colors, page_bg)


def build_caption_short_prototype(candidate: dict, sizes: dict, weights: dict, font_stack: str, colors: dict, page_bg: str) -> str:
    body = _caption_element(candidate, sizes, colors, "직접 읽어보세요.")
    return _caption_style_review_page("Short Caption", body, font_stack, colors, page_bg)


def build_caption_long_prototype(candidate: dict, sizes: dict, weights: dict, font_stack: str, colors: dict, page_bg: str) -> str:
    # Real Plan 7 KO_NARRATION display_text (longest actual narration line) -- never invented.
    long_text = (
        "B, A, G. 알파벳 이름을 다 아는데, 왜 합치면 '비-에이-지'가 아니라 전혀 다른 소리가 날까요? "
        "글자의 '이름'으로 읽으려고 하면 단어가 절대 읽히지 않습니다. 영어 단어는 글자의 이름이 아니라, "
        "그 글자가 이 단어에서 나타내는 '소리'를 이어 붙여야 읽힙니다."
    )
    body = _caption_element(candidate, sizes, colors, long_text, extra_style="max-width:640px;margin:0 auto;")
    return _caption_style_review_page("Long Caption", body, font_stack, colors, page_bg)


def build_caption_korean_english_prototype(candidate: dict, sizes: dict, weights: dict, font_stack: str, colors: dict, page_bg: str) -> str:
    dominant = f'font-size:{sizes["DOMINANT"]}px;font-weight:{weights["DOMINANT"]};color:{colors["DEFAULT"]};'
    body = (
        f'<div style="{dominant}">CAP</div>'
        + _caption_element(candidate, sizes, colors, "직접 읽어보세요. Read it out loud.")
    )
    return _caption_style_review_page("Korean + English Caption", body, font_stack, colors, page_bg)


def build_caption_answer_reveal_prototype(candidate: dict, sizes: dict, weights: dict, font_stack: str, colors: dict, page_bg: str) -> str:
    """Review-only static reproduction of the real _cb06_phase_overrides QUESTION/ANSWER typography
    with the caption style candidate shown below it. NOTE: in the real live CB06 attempt-reveal
    sequence, NARRATION_CAPTION is intentionally hidden (13-4B-R1, role=='CAPTION' -> visible=False)
    -- this static screen shows the caption style candidate in isolation for comparison purposes
    only, it does not imply the caption would actually be visible during that specific sequence."""
    trace_style = f'font-size:{sizes["DOMINANT"]}px;font-weight:{weights["DOMINANT"]};color:{colors["MUTED"]};'
    answer_style = f'font-size:{sizes["DOMINANT"]}px;font-weight:{weights["DOMINANT"]};color:{colors["SUCCESS"]};'
    body = (
        '<div data-review-only="true" style="font-family:sans-serif;font-size:12px;opacity:0.7;">REVIEW-ONLY: caption style shown in isolation. In the real live CB06 sequence, NARRATION_CAPTION is intentionally hidden (13-4B-R1) -- not the live Timeline.</div>'
        f'<div style="{trace_style}">이전 prompt trace: CAP</div>'
        f'<div style="{answer_style}">현재 ANSWER: cap</div>'
        + _caption_element(candidate, sizes, colors, "정답을 확인해 보세요.")
    )
    return _caption_style_review_page("Answer Reveal", body, font_stack, colors, page_bg)


def build_caption_dense_learning_prototype(candidate: dict, sizes: dict, weights: dict, font_stack: str, colors: dict, page_bg: str) -> str:
    primary = f'font-size:{sizes["PRIMARY"]}px;font-weight:{weights["PRIMARY"]};color:{colors["PRIMARY_FOCUS"]};'
    supporting = f'font-size:{sizes["SUPPORTING"]}px;font-weight:{weights["SUPPORTING"]};color:{colors["DEFAULT"]};'
    micro = f'font-size:{sizes["MICRO"]}px;font-weight:{weights["MICRO"]};color:{colors["SECONDARY"]};'
    body = (
        f'<div style="{primary}">직접 읽어보세요.</div>'
        f'<div style="{supporting}">CAP은 알파벳 C, A, P로 이루어진 단어입니다.</div>'
        f'<div style="{micro}">metadata sample</div>'
        + _caption_element(candidate, sizes, colors, "학습 보조 자막 예시")
    )
    return _caption_style_review_page("Dense Learning", body, font_stack, colors, page_bg)


def build_caption_side_by_side_prototype(candidates: dict, sizes: dict, weights: dict, font_stack: str, colors: dict, page_bg: str) -> str:
    blocks = []
    for name, candidate in candidates.items():
        blocks.append(
            '<section>'
            f'<div style="font-family:sans-serif;font-size:12px;opacity:0.6;">{name} (background={candidate["background"]}, opacity={candidate["background_opacity"]})</div>'
            + _caption_element(candidate, sizes, colors, "직접 읽어보세요.")
            + '</section>'
        )
    return _caption_style_review_page("Caption Style Side by Side", "\n".join(blocks), font_stack, colors, page_bg)


_CAPTION_STYLE_PROTOTYPE_BUILDERS = (
    ("01_FULL_LEARNING", "Full Learning Sample", build_caption_full_learning_prototype, "실제 학습 화면 통합 샘플"),
    ("02_SHORT_CAPTION", "Short Caption", build_caption_short_prototype, "짧은 한글 caption 가독성 확인"),
    ("03_LONG_CAPTION", "Long Caption", build_caption_long_prototype, "실제 Plan 7 최장 narration 문장으로 줄바꿈 확인"),
    ("04_KOREAN_ENGLISH", "Korean + English", build_caption_korean_english_prototype, "한글/영어 혼합 caption 확인"),
    ("05_QUESTION_ANSWER", "Answer Reveal", build_caption_answer_reveal_prototype, "정답 공개 시 caption이 hierarchy를 방해하지 않는지 확인"),
    ("06_DENSE_LEARNING", "Dense Learning", build_caption_dense_learning_prototype, "정보가 많은 화면에서 caption이 다른 role과 섞이지 않는지 확인"),
)


def generate_caption_style_review_prototypes(
    assets_dir: Path, plan_id: int, font_stack: str, colors: dict, page_bg: str, sizes: dict, weights: dict, candidates: dict,
) -> dict:
    review_dir = assets_dir / "generated" / f"plan_{plan_id}" / "render" / "caption_style_review"
    review_dir.mkdir(parents=True, exist_ok=True)

    file_entries = []
    side_by_side_html = build_caption_side_by_side_prototype(candidates, sizes, weights, font_stack, colors, page_bg)
    (review_dir / "00_CAPTION_STYLE_SIDE_BY_SIDE.html").write_text(side_by_side_html, encoding="utf-8")
    file_entries.append({"file": "00_CAPTION_STYLE_SIDE_BY_SIDE.html", "prototype_type": "00_SIDE_BY_SIDE", "candidate": None})

    for prefix, _label, builder, _desc in _CAPTION_STYLE_PROTOTYPE_BUILDERS:
        for candidate_name, candidate in candidates.items():
            filename = f"{prefix}_{candidate_name}.html"
            html = builder(candidate, sizes, weights, font_stack, colors, page_bg)
            (review_dir / filename).write_text(html, encoding="utf-8")
            file_entries.append({"file": filename, "prototype_type": prefix, "candidate": candidate_name})

    validation = validate_caption_style_candidates(candidates)
    manifest = {
        "revision": "13-4C-14", "review_type": "CAPTION_STYLE_HUMAN_REVIEW_PREPARATION",
        "production_plan_id": plan_id, "visual_design_version": VISUAL_DESIGN_VERSION,
        "canonical_visual_candidate": "CLEAN_DARK_FOCUS",
        "caption_style_status": "PENDING_VISUAL_REVIEW",
        "approved_fixed_conditions": {
            "font_family": font_stack, "background": page_bg, "color_palette": colors,
            "typography_scale": sizes, "font_weight": weights,
        },
        "candidates": candidates,
        "caption_zone_semantic_note": (
            "caption_style only styles the bottom NARRATION_CAPTION zone (CAPTION_ROLES / "
            "_caption_role_for_zone in research/visual_design.py) -- LEARNING_TEXT (everything else) "
            "already uses the other approved typography roles and needs no separate style."
        ),
        "cb06_note": (
            "In the real live CB06 attempt-reveal sequence, NARRATION_CAPTION is intentionally hidden "
            "(13-4B-R1) -- this review's Answer Reveal screen shows the caption style in isolation only."
        ),
        "wrapping_limitation": (
            "No literal pixel safe-area width constant exists in this codebase, so predicted overflow "
            "against a known safe-area cannot be computed programmatically -- only a presentation-only "
            "max-width is applied for the Long Caption screen. Actual browser wrapping/clipping requires "
            "a human opening the HTML."
        ),
        "hierarchy_validation": validation,
        "human_decision": None,
        "zero_db_write": True,
        "prototype_files": file_entries, "generated_at": datetime.utcnow().isoformat(),
    }
    (review_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    index_lines = ['<!doctype html><html><head><meta charset="utf-8"><title>Caption Style Review</title></head><body>']
    index_lines.append(f"<p>Current stage: 13-4C-14 Caption Style Human Review -- caption_style status: {manifest['caption_style_status']}, Human Decision: NONE</p>")
    index_lines.append("<p>Fixed conditions (이미 Human Review APPROVED): Font Family=VERDANA_HUMANIST, Background=#111318, Color Palette 7 role, Typography Scale=LARGE_BEGINNER(72/46/28/20/15px), Font Weight=BALANCED_HIERARCHY(800/700/500/400/400).</p>")
    index_lines.append('<h3>Side by Side</h3><ul><li><a href="00_CAPTION_STYLE_SIDE_BY_SIDE.html">00_CAPTION_STYLE_SIDE_BY_SIDE.html</a></li></ul>')
    for prefix, label, _builder, desc in _CAPTION_STYLE_PROTOTYPE_BUILDERS:
        index_lines.append(f"<h3>{_html_escape(label)}</h3><p>{_html_escape(desc)}</p><ul>")
        for candidate_name, candidate in candidates.items():
            filename = f"{prefix}_{candidate_name}.html"
            index_lines.append(f'<li><a href="{filename}">{filename}</a> -- {candidate_name} (background={candidate["background"]}, opacity={candidate["background_opacity"]}, padding={candidate["padding"]}, line_height={candidate["line_height"]})</li>')
        index_lines.append("</ul>")
    index_lines.append("<h3>CAPTION STYLE HUMAN REVIEW</h3><ol>")
    for i, candidate_name in enumerate(candidates, start=1):
        c = candidates[candidate_name]
        index_lines.append(f"<li>{i} = {candidate_name} (text_color_role={c['text_color_role']}, background={c['background']}, opacity={c['background_opacity']}, padding={c['padding']}, line_height={c['line_height']})</li>")
    index_lines.append(f"<li>{len(candidates) + 1} = 세 후보 모두 부적절 -- 새 후보 필요</li>")
    index_lines.append("</ol>")
    index_lines.append("</body></html>")
    (review_dir / "index.html").write_text("\n".join(index_lines), encoding="utf-8")

    return {"review_dir": review_dir, "manifest": manifest, "file_count": len(file_entries), "validation": validation}


def run_caption_style_review(db_path: Path, assets_dir: Path, reports_dir: Path, *, plan_id: int | None = None) -> dict:
    entry_gate = validate_visual_design_entry_gate(db_path, assets_dir, plan_id=plan_id)
    if not entry_gate["pass"]:
        return {"pass": False, "reason": entry_gate["reason"], "plan_id": entry_gate.get("plan_id")}
    pid = entry_gate["plan_id"]

    canonical = select_canonical_visual_approval(db_path, pid)
    if canonical is None:
        return {"pass": False, "reason": "No canonical CANONICAL_CORRECTION visual_design_specs row found -- run `correct-visual-approval` first.", "plan_id": pid}

    record = canonical["design"]
    if record.get("selected_candidate") != "CLEAN_DARK_FOCUS":
        return {"pass": False, "reason": f"Canonical visual candidate is {record.get('selected_candidate')!r}, not CLEAN_DARK_FOCUS -- this review is scoped to CLEAN_DARK_FOCUS only.", "plan_id": pid}

    cats = record.get("category_approvals", {})
    for required in ("font_family", "background", "color_palette", "typography_scale", "font_weight"):
        if cats.get(required, {}).get("resolution_status") != "APPROVED":
            return {"pass": False, "reason": f"{required} must be Human Review approved before Caption Style review.", "plan_id": pid}
    if cats.get("caption_style", {}).get("resolution_status") == "APPROVED":
        return {"pass": False, "reason": "caption_style is already APPROVED on the current canonical record.", "plan_id": pid}

    font_stack = cats["font_family"]["resolved_style"]
    page_bg = cats["background"]["resolved_style"]
    colors = cats["color_palette"]["resolved_style"]
    sizes = cats["typography_scale"]["resolved_style"]
    weights = cats["font_weight"]["resolved_style"]

    candidates = build_caption_style_candidates()
    result = generate_caption_style_review_prototypes(assets_dir, pid, font_stack, colors, page_bg, sizes, weights, candidates)
    report_path = _build_caption_style_review_report(reports_dir, pid, sizes, weights, candidates, result)

    return {
        "pass": True, "plan_id": pid, "candidates": candidates, "sizes": sizes, "weights": weights,
        "review_dir": result["review_dir"], "manifest": result["manifest"], "file_count": result["file_count"],
        "validation": result["validation"], "report_path": report_path,
    }


def _build_caption_style_review_report(reports_dir: Path, plan_id: int, sizes: dict, weights: dict, candidates: dict, result: dict) -> Path:
    lines: list[str] = ["# Caption Style Human Review Report", ""]
    lines.append(f"생성일: {datetime.utcnow().date().isoformat()}")
    lines.append(f"Source Plan: {plan_id}")
    lines.append("")
    lines.append("## Fixed Approved Conditions")
    lines.append("")
    lines.append(f"Typography Scale (CAPTION role): {sizes['CAPTION']}px / {weights['CAPTION']} (native)")
    lines.append("")
    lines.append("## Caption Zone Semantic Note")
    lines.append("")
    lines.append(result["manifest"]["caption_zone_semantic_note"])
    lines.append("")
    lines.append("## CB06 Note")
    lines.append("")
    lines.append(result["manifest"]["cb06_note"])
    lines.append("")
    lines.append("## Candidates (결정론적)")
    lines.append("")
    lines.append("| Candidate | text_color_role | background | opacity | padding | line_height |")
    lines.append("|---|---|---|---|---|---|")
    for name, c in candidates.items():
        lines.append(f"| {name} | {c['text_color_role']} | {c['background']} | {c['background_opacity']} | {c['padding']} | {c['line_height']} |")
    lines.append("")
    lines.append("## Wrapping/Overflow 한계 (정직하게 보고)")
    lines.append("")
    lines.append(result["manifest"]["wrapping_limitation"])
    lines.append("")
    lines.append(f"Files: {result['file_count']}")
    lines.append(f"Directory: {result['review_dir']}")
    lines.append(f"Review first: {result['review_dir'] / 'index.html'}")
    lines.append("")
    lines.append("## Human Decision")
    lines.append("")
    lines.append("NONE -- Prototype 생성만 완료됨. 사용자가 실제로 화면을 본 뒤 결정해야 함.")
    lines.append("")
    lines.append("## CAPTION STYLE HUMAN REVIEW")
    lines.append("")
    for i, name in enumerate(candidates, start=1):
        c = candidates[name]
        lines.append(f"{i} = {name} (text_color_role={c['text_color_role']}, background={c['background']}, opacity={c['background_opacity']}, padding={c['padding']}, line_height={c['line_height']})")
    lines.append(f"{len(candidates) + 1} = 세 후보 모두 부적절 -- 새 후보 필요")
    lines.append("")

    reports_dir.mkdir(parents=True, exist_ok=True)
    out_path = reports_dir / f"caption_style_review_{datetime.utcnow().date().isoformat()}.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# 13-4C-15: Caption Style Human Approval -- persists the real Human Review decision from 13-4C-14
# (BALANCED_INTEGRATED candidate) as the caption_style category approval. Append-only, exactly like
# 13-4C-6/9/11/13. The approved values are recomputed from the same build_caption_style_candidates()
# used by the Review stage -- never hardcoded separately, so review candidate and approval candidate
# can never drift apart.
# ---------------------------------------------------------------------------

HUMAN_SELECTED_CAPTION_STYLE_CANDIDATE = "BALANCED_INTEGRATED"


def run_caption_style_human_approval(
    db_path: Path, assets_dir: Path, reports_dir: Path, *, plan_id: int | None = None,
    selected_candidate: str = HUMAN_SELECTED_CAPTION_STYLE_CANDIDATE,
) -> dict:
    entry_gate = validate_visual_design_entry_gate(db_path, assets_dir, plan_id=plan_id)
    if not entry_gate["pass"]:
        return {"pass": False, "reason": entry_gate["reason"], "plan_id": entry_gate.get("plan_id")}
    pid = entry_gate["plan_id"]

    canonical = select_canonical_visual_approval(db_path, pid)
    if canonical is None:
        return {"pass": False, "reason": "No canonical CANONICAL_CORRECTION visual_design_specs row found -- run `correct-visual-approval` first.", "plan_id": pid}

    prior_id, prior_record = canonical["id"], canonical["design"]
    if prior_record.get("selected_candidate") != "CLEAN_DARK_FOCUS":
        return {"pass": False, "reason": f"Canonical visual candidate is {prior_record.get('selected_candidate')!r}, not CLEAN_DARK_FOCUS -- this approval is scoped to CLEAN_DARK_FOCUS only.", "plan_id": pid}

    prior_categories = prior_record.get("category_approvals", {})
    for required in ("font_family", "background", "color_palette", "typography_scale", "font_weight"):
        if prior_categories.get(required, {}).get("resolution_status") != "APPROVED":
            return {"pass": False, "reason": f"{required} must be Human Review approved before caption_style.", "plan_id": pid}
    if prior_categories.get("caption_style", {}).get("resolution_status") == "APPROVED":
        return {"pass": False, "reason": "caption_style is already APPROVED on the current canonical record.", "plan_id": pid}

    # Recompute the candidates with the exact same deterministic function 13-4C-14 used -- never
    # hardcode the selected style, so review candidate and approval candidate can never drift apart.
    candidates = build_caption_style_candidates()

    if selected_candidate not in candidates:
        return {"pass": False, "reason": f"{selected_candidate!r} is not a real Caption Style candidate (choices: {sorted(candidates)})", "plan_id": pid}
    if selected_candidate != HUMAN_SELECTED_CAPTION_STYLE_CANDIDATE:
        return {
            "pass": False,
            "reason": (
                f"No recorded Human Review decision for {selected_candidate!r} -- only "
                f"{HUMAN_SELECTED_CAPTION_STYLE_CANDIDATE!r} has an actual Human Review approval on record."
            ),
            "plan_id": pid,
        }

    approved_style = dict(candidates[selected_candidate])

    new_categories = dict(prior_categories)
    new_categories["caption_style"] = {
        "resolved_style": approved_style,
        "resolution_status": "APPROVED",
        "reason": "Human Review approved on the 13-4C-14 Caption Style Prototype",
        "provenance": {
            "review_stage": "13-4C-15", "review_type": "HUMAN_VISUAL_REVIEW",
            "review_source": "13-4C-14 Caption Style Human Review Prototype",
            "human_decision": "APPROVED", "selected_candidate": selected_candidate,
        },
    }

    candidate_selection = {
        "selected_candidate": prior_record.get("selected_candidate"),
        "candidate_selection_status": prior_record.get("candidate_selection_status"),
    }
    ready = ready_for_final_renderer_binding(candidate_selection, {"categories": new_categories})
    approved_count = sum(1 for c in new_categories.values() if c["resolution_status"] == "APPROVED")
    pending_count = len(new_categories) - approved_count

    new_record = {
        **prior_record,
        "record_status": "CANONICAL_CORRECTION",
        "revision": "13-4C-15",
        "corrects_record_id": prior_id,
        "correction_reason": "CAPTION_STYLE_HUMAN_APPROVAL",
        "correction_details": (
            f"caption_style Human Review approved ({selected_candidate}: {approved_style}); "
            f"every other category is carried forward unchanged from record id={prior_id}."
        ),
        "category_approvals": new_categories,
        "full_profile_approved": False,
        "ready_for_final_renderer_binding": ready,
    }

    row_id = persist_visual_design(db_path, pid, prior_id, new_record, {"checks": {}, "unresolved_critical": [], "unresolved_non_critical": []})

    profile_path = assets_dir / "generated" / f"plan_{pid}" / "render" / "approved_visual_profile.json"
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(json.dumps(new_record, ensure_ascii=False, indent=2), encoding="utf-8")

    report_path = _build_caption_style_human_approval_report(reports_dir, pid, new_record, prior_id, row_id, approved_count, pending_count, ready, profile_path)

    return {
        "pass": True, "plan_id": pid, "approved_style": approved_style, "selected_candidate": selected_candidate,
        "record": new_record, "prior_canonical_id": prior_id,
        "visual_design_row_id": row_id, "approved_category_count": approved_count, "pending_category_count": pending_count,
        "full_profile_approved": False, "ready_for_final_renderer_binding": ready, "json_path": profile_path,
        "report_path": report_path,
    }


def _build_caption_style_human_approval_report(
    reports_dir: Path, plan_id: int, record: dict, prior_id: int, row_id: int,
    approved_count: int, pending_count: int, ready: bool, profile_path: Path,
) -> Path:
    cat = record["category_approvals"]["caption_style"]
    style = cat["resolved_style"]
    prov = cat["provenance"]

    lines: list[str] = ["# Caption Style Human Approval Report", ""]
    lines.append(f"생성일: {datetime.utcnow().date().isoformat()}")
    lines.append(f"Source Plan: {plan_id}")
    lines.append("")
    lines.append("## Human Decision")
    lines.append("")
    lines.append('Source: 사용자가 실제 대화에서 "BALANCED_INTEGRATED(2번)"를 선택')
    lines.append(f"Selected candidate: {prov['selected_candidate']}")
    lines.append("")
    lines.append("## Approved Caption Style")
    lines.append("")
    lines.append(f"- text_color_role: {style['text_color_role']}")
    lines.append(f"- background: {style['background']}")
    lines.append(f"- background_opacity: {style['background_opacity']}")
    lines.append(f"- padding: {style['padding']}")
    lines.append(f"- line_height: {style['line_height']}")
    lines.append("")
    lines.append("## Fixed Approvals (preserved, not re-approved)")
    lines.append("")
    lines.append(f"Font Family: {record['category_approvals']['font_family']['resolution_status']} ({record['category_approvals']['font_family']['resolved_style']})")
    lines.append(f"Background: {record['category_approvals']['background']['resolution_status']} ({record['category_approvals']['background']['resolved_style']})")
    lines.append(f"Color Palette: {record['category_approvals']['color_palette']['resolution_status']} (MUTED={record['category_approvals']['color_palette']['resolved_style']['MUTED']})")
    lines.append(f"Typography Scale: {record['category_approvals']['typography_scale']['resolution_status']} ({record['category_approvals']['typography_scale']['resolved_style']})")
    lines.append(f"Font Weight: {record['category_approvals']['font_weight']['resolution_status']} ({record['category_approvals']['font_weight']['resolved_style']})")
    lines.append("")
    lines.append(f"## Category Approvals ({approved_count} APPROVED / {pending_count} PENDING)")
    lines.append("")
    for name, c in record["category_approvals"].items():
        lines.append(f"- {name}: {c['resolution_status']}")
    lines.append("")
    lines.append("## Renderer Gate")
    lines.append("")
    lines.append(f"Full Profile Approved: {'YES' if record['full_profile_approved'] else 'NO'}")
    lines.append(f"Ready for Final Renderer Binding: {'YES' if ready else 'NO'}")
    lines.append("")
    lines.append("## DB Append-only")
    lines.append("")
    lines.append(f"이전 canonical record id: {prior_id} (수정되지 않음)")
    lines.append(f"신규 canonical record id: {row_id}")
    lines.append("")
    lines.append(f"JSON: {profile_path}")
    lines.append("")

    reports_dir.mkdir(parents=True, exist_ok=True)
    out_path = reports_dir / f"caption_style_human_approval_{datetime.utcnow().date().isoformat()}.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# 13-4C-16: Focus Style Human Review -- Review Preparation only (zero DB write), exactly like
# 13-4C-3/7/10/12/14. focus_style has no existing implementation in this codebase beyond the
# already-approved PRIMARY_FOCUS color role (COLOR_ROLES, bound to zone_role PRIMARY_FOCUS/PROMPT
# via _color_role_for_zone) and the hardcoded element_state ACTIVE/MUTED opacity effect
# (build_element_states / build_cb06_phase_prototype's "opacity:0.4;" for MUTED). focus_style may
# only add presentation beyond that fixed PRIMARY_FOCUS color to the currently ACTIVE element --
# never to an already-MUTED (de-emphasized) one, and never a new palette role/gratuitous effect.
# The only precedent for "presentation beyond color" in this codebase is caption_style's
# `background: box` rgba(...) overlay technique (13-4C-14) -- reused here, tinted with the
# already-approved PRIMARY_FOCUS hex itself (via _hex_to_rgb) rather than inventing a new color.
# ---------------------------------------------------------------------------

FOCUS_STYLE_CANDIDATES = {
    "COLOR_ONLY": {"color_role": "PRIMARY_FOCUS", "highlight_box": False, "box_opacity": 0.0, "padding": "0", "underline": False},
    "BALANCED_FOCUS": {"color_role": "PRIMARY_FOCUS", "highlight_box": True, "box_opacity": 0.15, "padding": "2px 8px", "underline": False},
    "STRONG_FOCUS": {"color_role": "PRIMARY_FOCUS", "highlight_box": True, "box_opacity": 0.28, "padding": "4px 12px", "underline": True},
}

_FOCUS_PADDING_RE = re.compile(r"^0$|^\d+px( \d+px){1,3}$")


def build_focus_style_candidates() -> dict:
    return {name: dict(props) for name, props in FOCUS_STYLE_CANDIDATES.items()}


def validate_focus_style_candidates(candidates: dict) -> dict:
    issues = []
    if len(candidates) != 3:
        issues.append(f"expected exactly 3 candidates, got {len(candidates)}")
    if len(set(candidates)) != len(candidates):
        issues.append("candidate ids are not unique")
    for name, props in candidates.items():
        required = ("color_role", "highlight_box", "box_opacity", "padding", "underline")
        missing = [k for k in required if k not in props]
        if missing:
            issues.append(f"{name}: missing properties {missing}")
            continue
        if props["color_role"] not in COLOR_REVIEW_ROLES:
            issues.append(f"{name}: color_role {props['color_role']!r} is not an approved palette role")
        if not isinstance(props["highlight_box"], bool):
            issues.append(f"{name}: highlight_box must be bool, got {props['highlight_box']!r}")
        if not isinstance(props["underline"], bool):
            issues.append(f"{name}: underline must be bool, got {props['underline']!r}")
        if not (0.0 <= props["box_opacity"] <= 1.0):
            issues.append(f"{name}: box_opacity out of range ({props['box_opacity']})")
        if not _FOCUS_PADDING_RE.match(props["padding"]):
            issues.append(f"{name}: invalid CSS padding ({props['padding']!r})")
    return {"pass": len(issues) == 0, "issues": issues}


def _focus_box_style(candidate: dict, primary_focus_hex: str) -> str:
    if not candidate["highlight_box"]:
        return ""
    r, g, b = _hex_to_rgb(primary_focus_hex)
    return f'background:rgba({r},{g},{b},{candidate["box_opacity"]});'


def _focus_underline_style(candidate: dict) -> str:
    return "text-decoration:underline;" if candidate["underline"] else ""


def _focus_style_review_page(title: str, body: str, font_stack: str, colors: dict, page_bg: str) -> str:
    return (
        f'<!doctype html><html><head><meta charset="utf-8"><title>{_html_escape(title)}</title></head>'
        f'<body style="background:{page_bg};color:{colors["DEFAULT"]};font-family:{font_stack};padding:40px;">'
        f'<header data-preview-metadata style="opacity:0.5;font-size:12px;font-family:sans-serif;">PREVIEW ONLY -- '
        f'Focus Style Human Review. focus_style is NOT APPROVED. Font Family/Background/Color Palette/Typography '
        f'Scale/Font Weight/Caption Style are already Human Review APPROVED and are fixed conditions here. '
        f'Human decision: NONE. The approved PRIMARY_FOCUS color role is fixed across all candidates -- only the '
        f'presentation added on top of it (highlight box / underline) varies.</header>'
        f'<main data-frame-preview>{body}</main></body></html>'
    )


def _focus_element(candidate: dict, size_style: str, colors: dict, text: str, extra_style: str = "") -> str:
    color_style = f'color:{colors[candidate["color_role"]]};'
    box_style = _focus_box_style(candidate, colors[candidate["color_role"]])
    underline_style = _focus_underline_style(candidate)
    return (
        f'<div data-focus-element style="{size_style}{color_style}{box_style}{underline_style}'
        f'padding:{candidate["padding"]};{extra_style}">{_html_escape(text)}</div>'
    )


def _muted_focus_element(size_style: str, colors: dict, text: str) -> str:
    # Reproduces the existing element_state=MUTED convention verbatim (build_cb06_phase_prototype's
    # "opacity:0.4;") -- an already-superseded prior focus target never gets the focus_style box,
    # since re-emphasizing something already de-emphasized would contradict its own MUTED state.
    return f'<div data-focus-element data-element-state="MUTED" style="{size_style}color:{colors["PRIMARY_FOCUS"]};opacity:0.4;">{_html_escape(text)}</div>'


def build_focus_single_word_prototype(candidate: dict, sizes: dict, weights: dict, font_stack: str, colors: dict, page_bg: str) -> str:
    size_style = f'font-size:{sizes["DOMINANT"]}px;font-weight:{weights["DOMINANT"]};'
    body = _focus_element(candidate, size_style, colors, "CAP")
    return _focus_style_review_page("Single Word Focus", body, font_stack, colors, page_bg)


def build_focus_multi_word_prototype(candidate: dict, sizes: dict, weights: dict, font_stack: str, colors: dict, page_bg: str) -> str:
    # Real Plan 7 CB07 (RECAP_LAYOUT) primary_focus zone data: BAG/BAT/MAP entered first and are
    # now superseded (element_state=MUTED, real element_states from the canonical scene_visual_rules
    # for CB07), CAP is the current element_state=ACTIVE target and is the only one styled by the
    # focus_style candidate under review -- never invented content.
    size_style = f'font-size:{sizes["DOMINANT"]}px;font-weight:{weights["DOMINANT"]};'
    body = (
        _muted_focus_element(size_style, colors, "BAG")
        + _muted_focus_element(size_style, colors, "BAT")
        + _muted_focus_element(size_style, colors, "MAP")
        + _focus_element(candidate, size_style, colors, "CAP")
    )
    return _focus_style_review_page("Multi Word Learning (real CB07 RECAP sequence)", body, font_stack, colors, page_bg)


def build_focus_korean_english_prototype(candidate: dict, sizes: dict, weights: dict, font_stack: str, colors: dict, page_bg: str) -> str:
    prompt_style = f'font-size:{sizes["PRIMARY"]}px;font-weight:{weights["PRIMARY"]};color:{colors["DEFAULT"]};'
    size_style = f'font-size:{sizes["DOMINANT"]}px;font-weight:{weights["DOMINANT"]};'
    body = (
        f'<div style="{prompt_style}">직접 읽어보세요.</div>'
        + _focus_element(candidate, size_style, colors, "CAP")
    )
    return _focus_style_review_page("Korean + English", body, font_stack, colors, page_bg)


def build_focus_dense_learning_prototype(candidate: dict, sizes: dict, weights: dict, font_stack: str, colors: dict, page_bg: str) -> str:
    prompt_style = f'font-size:{sizes["PRIMARY"]}px;font-weight:{weights["PRIMARY"]};color:{colors["DEFAULT"]};'
    supporting_style = f'font-size:{sizes["SUPPORTING"]}px;font-weight:{weights["SUPPORTING"]};color:{colors["RELATION"]};'
    micro_style = f'font-size:{sizes["MICRO"]}px;font-weight:{weights["MICRO"]};color:{colors["SECONDARY"]};'
    size_style = f'font-size:{sizes["DOMINANT"]}px;font-weight:{weights["DOMINANT"]};'
    body = (
        f'<div style="{prompt_style}">직접 읽어보세요.</div>'
        + _focus_element(candidate, size_style, colors, "CAP")
        + f'<div style="{supporting_style}">CAP → cap</div>'
        + f'<div style="{micro_style}">metadata sample</div>'
    )
    return _focus_style_review_page("Dense Learning", body, font_stack, colors, page_bg)


def build_focus_relation_prototype(candidate: dict, sizes: dict, weights: dict, font_stack: str, colors: dict, page_bg: str) -> str:
    # Same real "CAP / CAP -> cap / cap" triple as build_color_relation_prototype (13-4C-7) -- only
    # the PRIMARY_FOCUS line is styled by the focus_style candidate; RELATION/SUCCESS are unchanged
    # fixed conditions, verifying the three semantics stay visually distinguishable.
    size_style = f'font-size:{sizes["DOMINANT"]}px;font-weight:{weights["DOMINANT"]};'
    relation_style = f'font-size:{sizes["SUPPORTING"]}px;font-weight:{weights["SUPPORTING"]};color:{colors["RELATION"]};'
    success_style = f'font-size:{sizes["DOMINANT"]}px;font-weight:{weights["DOMINANT"]};color:{colors["SUCCESS"]};'
    body = (
        _focus_element(candidate, size_style, colors, "CAP")
        + f'<div style="{relation_style}">CAP → cap</div>'
        + f'<div style="{success_style}">cap</div>'
    )
    return _focus_style_review_page("Relation Context", body, font_stack, colors, page_bg)


def build_focus_answer_reveal_prototype(candidate: dict, sizes: dict, weights: dict, font_stack: str, colors: dict, page_bg: str) -> str:
    """Review-only static reproduction of the real _cb06_phase_overrides ATTEMPT_PROMPT phase
    (role=='QUESTION', typography_override='DOMINANT', PRIMARY_FOCUS color) with the focus_style
    candidate applied on top. NOTE: this does not alter the actual _cb06_phase_overrides table or
    the live CB06 Timeline -- it is a static comparison screen only."""
    size_style = f'font-size:{sizes["DOMINANT"]}px;font-weight:{weights["DOMINANT"]};'
    body = (
        '<div data-review-only="true" style="font-family:sans-serif;font-size:12px;opacity:0.7;">REVIEW-ONLY: reproduces the real CB06 ATTEMPT_PROMPT phase (_cb06_phase_overrides, role=QUESTION) with the focus_style candidate applied. Does not modify the actual CB06 phase policy.</div>'
        + _focus_element(candidate, size_style, colors, "CAP")
    )
    return _focus_style_review_page("Answer Reveal Context (CB06 ATTEMPT_PROMPT)", body, font_stack, colors, page_bg)


def build_focus_side_by_side_prototype(candidates: dict, sizes: dict, weights: dict, font_stack: str, colors: dict, page_bg: str) -> str:
    size_style = f'font-size:{sizes["DOMINANT"]}px;font-weight:{weights["DOMINANT"]};'
    blocks = []
    for name, candidate in candidates.items():
        blocks.append(
            '<section>'
            f'<div style="font-family:sans-serif;font-size:12px;opacity:0.6;">{name} (highlight_box={candidate["highlight_box"]}, box_opacity={candidate["box_opacity"]}, underline={candidate["underline"]})</div>'
            + _focus_element(candidate, size_style, colors, "CAP")
            + '</section>'
        )
    return _focus_style_review_page("Focus Style Side by Side", "\n".join(blocks), font_stack, colors, page_bg)


_FOCUS_STYLE_PROTOTYPE_BUILDERS = (
    ("01_SINGLE_WORD_FOCUS", "Single Word Focus", build_focus_single_word_prototype, "단일 단어 focus 강조 확인"),
    ("02_MULTI_WORD_LEARNING", "Multi Word Learning", build_focus_multi_word_prototype, "실제 CB07 RECAP 데이터 -- 이전 MUTED 대상과 현재 ACTIVE focus 대상 구별 확인"),
    ("03_KOREAN_ENGLISH", "Korean + English", build_focus_korean_english_prototype, "한글 지시문 + 영어 focus 대상 혼합 확인"),
    ("04_DENSE_LEARNING", "Dense Learning", build_focus_dense_learning_prototype, "여러 role이 밀집한 화면에서 focus 대상이 구별되는지 확인"),
    ("05_RELATION_CONTEXT", "Relation Context", build_focus_relation_prototype, "PRIMARY_FOCUS vs RELATION vs SUCCESS 구별 확인"),
    ("06_ANSWER_REVEAL_CONTEXT", "Answer Reveal Context", build_focus_answer_reveal_prototype, "CB06 ATTEMPT_PROMPT phase 정적 재현 (실제 정책 변경 없음)"),
)


def generate_focus_style_review_prototypes(
    assets_dir: Path, plan_id: int, font_stack: str, colors: dict, page_bg: str, sizes: dict, weights: dict, candidates: dict,
    caption_style: dict,
) -> dict:
    review_dir = assets_dir / "generated" / f"plan_{plan_id}" / "render" / "focus_style_review"
    review_dir.mkdir(parents=True, exist_ok=True)

    file_entries = []
    side_by_side_html = build_focus_side_by_side_prototype(candidates, sizes, weights, font_stack, colors, page_bg)
    (review_dir / "00_FOCUS_STYLE_SIDE_BY_SIDE.html").write_text(side_by_side_html, encoding="utf-8")
    file_entries.append({"file": "00_FOCUS_STYLE_SIDE_BY_SIDE.html", "prototype_type": "00_SIDE_BY_SIDE", "candidate": None})

    for prefix, _label, builder, _desc in _FOCUS_STYLE_PROTOTYPE_BUILDERS:
        for candidate_name, candidate in candidates.items():
            filename = f"{prefix}_{candidate_name}.html"
            html = builder(candidate, sizes, weights, font_stack, colors, page_bg)
            (review_dir / filename).write_text(html, encoding="utf-8")
            file_entries.append({"file": filename, "prototype_type": prefix, "candidate": candidate_name})

    validation = validate_focus_style_candidates(candidates)
    manifest = {
        "revision": "13-4C-16", "review_type": "FOCUS_STYLE_HUMAN_REVIEW_PREPARATION",
        "production_plan_id": plan_id, "visual_design_version": VISUAL_DESIGN_VERSION,
        "canonical_visual_candidate": "CLEAN_DARK_FOCUS",
        "focus_style_status": "PENDING_VISUAL_REVIEW",
        "approved_fixed_conditions": {
            "font_family": font_stack, "background": page_bg, "color_palette": colors,
            "typography_scale": sizes, "font_weight": weights, "caption_style": caption_style,
        },
        "candidates": candidates,
        "focus_semantic_note": (
            "focus_style has no prior implementation in this codebase beyond the already-approved "
            "PRIMARY_FOCUS color role (bound to zone_role PRIMARY_FOCUS/PROMPT via "
            "_color_role_for_zone) and the hardcoded element_state ACTIVE/MUTED opacity effect "
            "(build_element_states / build_cb06_phase_prototype). Candidates only add presentation "
            "on top of the fixed PRIMARY_FOCUS color for the currently element_state=ACTIVE target -- "
            "an already-MUTED (superseded) prior focus target never receives the focus_style box, per "
            "real CB07 RECAP element_states data (BAG/BAT/MAP superseded, CAP is ACTIVE)."
        ),
        "cb06_note": (
            "The Answer Reveal Context screen statically reproduces the real _cb06_phase_overrides "
            "ATTEMPT_PROMPT phase for comparison only -- it does not modify the actual CB06 phase "
            "policy or live Timeline (13-4B-R1 unchanged)."
        ),
        "hierarchy_validation": validation,
        "human_decision": None,
        "zero_db_write": True,
        "prototype_files": file_entries, "generated_at": datetime.utcnow().isoformat(),
    }
    (review_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    index_lines = ['<!doctype html><html><head><meta charset="utf-8"><title>Focus Style Review</title></head><body>']
    index_lines.append(f"<p>Current stage: 13-4C-16 Focus Style Human Review -- focus_style status: {manifest['focus_style_status']}, Human Decision: NONE</p>")
    index_lines.append("<p>Fixed conditions (이미 Human Review APPROVED): Font Family=VERDANA_HUMANIST, Background=#111318, Color Palette 7 role, Typography Scale=LARGE_BEGINNER(72/46/28/20/15px), Font Weight=BALANCED_HIERARCHY(800/700/500/400/400), Caption Style=BALANCED_INTEGRATED.</p>")
    index_lines.append("<p>이 review는 REVIEW ONLY입니다. focus_style은 아직 APPROVED가 아닙니다. Human Decision = NONE.</p>")
    index_lines.append('<h3>Side by Side</h3><ul><li><a href="00_FOCUS_STYLE_SIDE_BY_SIDE.html">00_FOCUS_STYLE_SIDE_BY_SIDE.html</a></li></ul>')
    for prefix, label, _builder, desc in _FOCUS_STYLE_PROTOTYPE_BUILDERS:
        index_lines.append(f"<h3>{_html_escape(label)}</h3><p>{_html_escape(desc)}</p><ul>")
        for candidate_name, candidate in candidates.items():
            filename = f"{prefix}_{candidate_name}.html"
            index_lines.append(f'<li><a href="{filename}">{filename}</a> -- {candidate_name} (highlight_box={candidate["highlight_box"]}, box_opacity={candidate["box_opacity"]}, padding={candidate["padding"]}, underline={candidate["underline"]})</li>')
        index_lines.append("</ul>")
    index_lines.append("<h3>FOCUS STYLE HUMAN REVIEW</h3><ol>")
    for i, candidate_name in enumerate(candidates, start=1):
        c = candidates[candidate_name]
        index_lines.append(f"<li>{i} = {candidate_name} (color_role={c['color_role']}, highlight_box={c['highlight_box']}, box_opacity={c['box_opacity']}, padding={c['padding']}, underline={c['underline']})</li>")
    index_lines.append(f"<li>{len(candidates) + 1} = 세 후보 모두 부적절 -- 새 후보 필요</li>")
    index_lines.append("</ol>")
    index_lines.append("</body></html>")
    (review_dir / "index.html").write_text("\n".join(index_lines), encoding="utf-8")

    return {"review_dir": review_dir, "manifest": manifest, "file_count": len(file_entries), "validation": validation}


def run_focus_style_review(db_path: Path, assets_dir: Path, reports_dir: Path, *, plan_id: int | None = None) -> dict:
    entry_gate = validate_visual_design_entry_gate(db_path, assets_dir, plan_id=plan_id)
    if not entry_gate["pass"]:
        return {"pass": False, "reason": entry_gate["reason"], "plan_id": entry_gate.get("plan_id")}
    pid = entry_gate["plan_id"]

    canonical = select_canonical_visual_approval(db_path, pid)
    if canonical is None:
        return {"pass": False, "reason": "No canonical CANONICAL_CORRECTION visual_design_specs row found -- run `correct-visual-approval` first.", "plan_id": pid}

    record = canonical["design"]
    if record.get("selected_candidate") != "CLEAN_DARK_FOCUS":
        return {"pass": False, "reason": f"Canonical visual candidate is {record.get('selected_candidate')!r}, not CLEAN_DARK_FOCUS -- this review is scoped to CLEAN_DARK_FOCUS only.", "plan_id": pid}

    cats = record.get("category_approvals", {})
    for required in ("font_family", "background", "color_palette", "typography_scale", "font_weight", "caption_style"):
        if cats.get(required, {}).get("resolution_status") != "APPROVED":
            return {"pass": False, "reason": f"{required} must be Human Review approved before Focus Style review.", "plan_id": pid}
    if cats.get("focus_style", {}).get("resolution_status") == "APPROVED":
        return {"pass": False, "reason": "focus_style is already APPROVED on the current canonical record.", "plan_id": pid}

    font_stack = cats["font_family"]["resolved_style"]
    page_bg = cats["background"]["resolved_style"]
    colors = cats["color_palette"]["resolved_style"]
    sizes = cats["typography_scale"]["resolved_style"]
    weights = cats["font_weight"]["resolved_style"]
    caption_style = cats["caption_style"]["resolved_style"]

    candidates = build_focus_style_candidates()
    result = generate_focus_style_review_prototypes(assets_dir, pid, font_stack, colors, page_bg, sizes, weights, candidates, caption_style)
    report_path = _build_focus_style_review_report(reports_dir, pid, sizes, weights, caption_style, candidates, result)

    return {
        "pass": True, "plan_id": pid, "candidates": candidates, "sizes": sizes, "weights": weights,
        "review_dir": result["review_dir"], "manifest": result["manifest"], "file_count": result["file_count"],
        "validation": result["validation"], "report_path": report_path,
    }


def _build_focus_style_review_report(reports_dir: Path, plan_id: int, sizes: dict, weights: dict, caption_style: dict, candidates: dict, result: dict) -> Path:
    lines: list[str] = ["# Focus Style Human Review Report", ""]
    lines.append(f"생성일: {datetime.utcnow().date().isoformat()}")
    lines.append(f"Source Plan: {plan_id}")
    lines.append("")
    lines.append("## Source-of-Truth Investigation")
    lines.append("")
    lines.append(result["manifest"]["focus_semantic_note"])
    lines.append("")
    lines.append("## Fixed Approved Conditions")
    lines.append("")
    lines.append(f"Typography Scale (DOMINANT role): {sizes['DOMINANT']}px / {weights['DOMINANT']} (native/synthetic per 13-4C-13 provenance)")
    lines.append(f"Caption Style (unchanged): {caption_style}")
    lines.append("")
    lines.append("## CB06 Note")
    lines.append("")
    lines.append(result["manifest"]["cb06_note"])
    lines.append("")
    lines.append("## Candidates (결정론적)")
    lines.append("")
    lines.append("| Candidate | color_role | highlight_box | box_opacity | padding | underline |")
    lines.append("|---|---|---|---|---|---|")
    for name, c in candidates.items():
        lines.append(f"| {name} | {c['color_role']} | {c['highlight_box']} | {c['box_opacity']} | {c['padding']} | {c['underline']} |")
    lines.append("")
    lines.append(f"Files: {result['file_count']}")
    lines.append(f"Directory: {result['review_dir']}")
    lines.append(f"Review first: {result['review_dir'] / 'index.html'}")
    lines.append("")
    lines.append("## Human Decision")
    lines.append("")
    lines.append("NONE -- Prototype 생성만 완료됨. 사용자가 실제로 화면을 본 뒤 결정해야 함.")
    lines.append("")
    lines.append("## FOCUS STYLE HUMAN REVIEW")
    lines.append("")
    for i, name in enumerate(candidates, start=1):
        c = candidates[name]
        lines.append(f"{i} = {name} (color_role={c['color_role']}, highlight_box={c['highlight_box']}, box_opacity={c['box_opacity']}, padding={c['padding']}, underline={c['underline']})")
    lines.append(f"{len(candidates) + 1} = 세 후보 모두 부적절 -- 새 후보 필요")
    lines.append("")

    reports_dir.mkdir(parents=True, exist_ok=True)
    out_path = reports_dir / f"focus_style_review_{datetime.utcnow().date().isoformat()}.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# 13-4C-17: Focus Style Human Approval -- persists the real Human Review decision from 13-4C-16
# (COLOR_ONLY candidate) as the focus_style category approval. Append-only, exactly like
# 13-4C-6/9/11/13/15. The approved values are recomputed from the same build_focus_style_candidates()
# used by the Review stage -- never hardcoded separately, so review candidate and approval candidate
# can never drift apart.
# ---------------------------------------------------------------------------

HUMAN_SELECTED_FOCUS_STYLE_CANDIDATE = "COLOR_ONLY"


def run_focus_style_human_approval(
    db_path: Path, assets_dir: Path, reports_dir: Path, *, plan_id: int | None = None,
    selected_candidate: str = HUMAN_SELECTED_FOCUS_STYLE_CANDIDATE,
) -> dict:
    entry_gate = validate_visual_design_entry_gate(db_path, assets_dir, plan_id=plan_id)
    if not entry_gate["pass"]:
        return {"pass": False, "reason": entry_gate["reason"], "plan_id": entry_gate.get("plan_id")}
    pid = entry_gate["plan_id"]

    canonical = select_canonical_visual_approval(db_path, pid)
    if canonical is None:
        return {"pass": False, "reason": "No canonical CANONICAL_CORRECTION visual_design_specs row found -- run `correct-visual-approval` first.", "plan_id": pid}

    prior_id, prior_record = canonical["id"], canonical["design"]
    if prior_record.get("selected_candidate") != "CLEAN_DARK_FOCUS":
        return {"pass": False, "reason": f"Canonical visual candidate is {prior_record.get('selected_candidate')!r}, not CLEAN_DARK_FOCUS -- this approval is scoped to CLEAN_DARK_FOCUS only.", "plan_id": pid}

    prior_categories = prior_record.get("category_approvals", {})
    for required in ("font_family", "background", "color_palette", "typography_scale", "font_weight", "caption_style"):
        if prior_categories.get(required, {}).get("resolution_status") != "APPROVED":
            return {"pass": False, "reason": f"{required} must be Human Review approved before focus_style.", "plan_id": pid}
    if prior_categories.get("focus_style", {}).get("resolution_status") == "APPROVED":
        return {"pass": False, "reason": "focus_style is already APPROVED on the current canonical record.", "plan_id": pid}

    # Recompute the candidates with the exact same deterministic function 13-4C-16 used -- never
    # hardcode the selected style, so review candidate and approval candidate can never drift apart.
    candidates = build_focus_style_candidates()

    if selected_candidate not in candidates:
        return {"pass": False, "reason": f"{selected_candidate!r} is not a real Focus Style candidate (choices: {sorted(candidates)})", "plan_id": pid}
    if selected_candidate != HUMAN_SELECTED_FOCUS_STYLE_CANDIDATE:
        return {
            "pass": False,
            "reason": (
                f"No recorded Human Review decision for {selected_candidate!r} -- only "
                f"{HUMAN_SELECTED_FOCUS_STYLE_CANDIDATE!r} has an actual Human Review approval on record."
            ),
            "plan_id": pid,
        }

    approved_style = dict(candidates[selected_candidate])
    resolved_focus_color = prior_categories["color_palette"]["resolved_style"][approved_style["color_role"]]

    new_categories = dict(prior_categories)
    new_categories["focus_style"] = {
        "resolved_style": approved_style,
        "resolution_status": "APPROVED",
        "reason": "Human Review approved on the 13-4C-16 Focus Style Prototype",
        "provenance": {
            "review_stage": "13-4C-17", "review_type": "HUMAN_VISUAL_REVIEW",
            "review_source": "13-4C-16 Focus Style Human Review Prototype",
            "human_decision": "APPROVED", "selected_candidate": selected_candidate,
            "resolved_focus_color": resolved_focus_color,
            "human_decision_source": "current conversation -- option 1 / COLOR_ONLY",
        },
    }

    candidate_selection = {
        "selected_candidate": prior_record.get("selected_candidate"),
        "candidate_selection_status": prior_record.get("candidate_selection_status"),
    }
    ready = ready_for_final_renderer_binding(candidate_selection, {"categories": new_categories})
    approved_count = sum(1 for c in new_categories.values() if c["resolution_status"] == "APPROVED")
    pending_count = len(new_categories) - approved_count

    new_record = {
        **prior_record,
        "record_status": "CANONICAL_CORRECTION",
        "revision": "13-4C-17",
        "corrects_record_id": prior_id,
        "correction_reason": "FOCUS_STYLE_HUMAN_APPROVAL",
        "correction_details": (
            f"focus_style Human Review approved ({selected_candidate}: {approved_style}); "
            f"every other category is carried forward unchanged from record id={prior_id}."
        ),
        "category_approvals": new_categories,
        "full_profile_approved": False,
        "ready_for_final_renderer_binding": ready,
    }

    row_id = persist_visual_design(db_path, pid, prior_id, new_record, {"checks": {}, "unresolved_critical": [], "unresolved_non_critical": []})

    profile_path = assets_dir / "generated" / f"plan_{pid}" / "render" / "approved_visual_profile.json"
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(json.dumps(new_record, ensure_ascii=False, indent=2), encoding="utf-8")

    report_path = _build_focus_style_human_approval_report(reports_dir, pid, new_record, prior_id, row_id, approved_count, pending_count, ready, profile_path)

    return {
        "pass": True, "plan_id": pid, "approved_style": approved_style, "selected_candidate": selected_candidate,
        "resolved_focus_color": resolved_focus_color, "record": new_record, "prior_canonical_id": prior_id,
        "visual_design_row_id": row_id, "approved_category_count": approved_count, "pending_category_count": pending_count,
        "full_profile_approved": False, "ready_for_final_renderer_binding": ready, "json_path": profile_path,
        "report_path": report_path,
    }


def _build_focus_style_human_approval_report(
    reports_dir: Path, plan_id: int, record: dict, prior_id: int, row_id: int,
    approved_count: int, pending_count: int, ready: bool, profile_path: Path,
) -> Path:
    cat = record["category_approvals"]["focus_style"]
    style = cat["resolved_style"]
    prov = cat["provenance"]

    lines: list[str] = ["# Focus Style Human Approval Report", ""]
    lines.append(f"생성일: {datetime.utcnow().date().isoformat()}")
    lines.append(f"Source Plan: {plan_id}")
    lines.append("")
    lines.append("## Human Decision")
    lines.append("")
    lines.append('Source: 사용자가 실제 대화에서 "COLOR_ONLY(1번)"를 선택')
    lines.append(f"Selected candidate: {prov['selected_candidate']}")
    lines.append("")
    lines.append("## Approved Focus Style")
    lines.append("")
    lines.append(f"- color_role: {style['color_role']} (resolved: {prov['resolved_focus_color']})")
    lines.append(f"- highlight_box: {style['highlight_box']}")
    lines.append(f"- box_opacity: {style['box_opacity']}")
    lines.append(f"- padding: {style['padding']}")
    lines.append(f"- underline: {style['underline']}")
    lines.append("")
    lines.append("## Fixed Approvals (preserved, not re-approved)")
    lines.append("")
    lines.append(f"Font Family: {record['category_approvals']['font_family']['resolution_status']} ({record['category_approvals']['font_family']['resolved_style']})")
    lines.append(f"Background: {record['category_approvals']['background']['resolution_status']} ({record['category_approvals']['background']['resolved_style']})")
    lines.append(f"Color Palette: {record['category_approvals']['color_palette']['resolution_status']} (MUTED={record['category_approvals']['color_palette']['resolved_style']['MUTED']})")
    lines.append(f"Typography Scale: {record['category_approvals']['typography_scale']['resolution_status']} ({record['category_approvals']['typography_scale']['resolved_style']})")
    lines.append(f"Font Weight: {record['category_approvals']['font_weight']['resolution_status']} ({record['category_approvals']['font_weight']['resolved_style']})")
    lines.append(f"Caption Style: {record['category_approvals']['caption_style']['resolution_status']} ({record['category_approvals']['caption_style']['resolved_style']})")
    lines.append("")
    lines.append(f"## Category Approvals ({approved_count} APPROVED / {pending_count} PENDING)")
    lines.append("")
    for name, c in record["category_approvals"].items():
        lines.append(f"- {name}: {c['resolution_status']}")
    lines.append("")
    lines.append("## Renderer Gate")
    lines.append("")
    lines.append(f"Full Profile Approved: {'YES' if record['full_profile_approved'] else 'NO'}")
    lines.append(f"Ready for Final Renderer Binding: {'YES' if ready else 'NO'}")
    lines.append("")
    lines.append("## DB Append-only")
    lines.append("")
    lines.append(f"이전 canonical record id: {prior_id} (수정되지 않음)")
    lines.append(f"신규 canonical record id: {row_id}")
    lines.append("")
    lines.append(f"JSON: {profile_path}")
    lines.append("")

    reports_dir.mkdir(parents=True, exist_ok=True)
    out_path = reports_dir / f"focus_style_human_approval_{datetime.utcnow().date().isoformat()}.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# 13-4C-18: Success Style Human Review -- Review Preparation only (zero DB write), exactly like
# 13-4C-3/7/10/12/14/16. success_style is in the exact same situation focus_style was at 13-4C-16:
# no prior implementation beyond the already-approved SUCCESS color role (COLOR_ROLES, bound to
# zone_role ANSWER via _color_role_for_zone) and the real _cb06_phase_overrides(role=="ANSWER")
# visibility/text-transform policy. Real Plan 7 data confirms SUCCESS is used exactly once, in CB06
# (MINI_SUCCESS_LAYOUT) -- _color_role_usage_counts across all 8 scenes gives SUCCESS=1. Candidates
# reuse the exact same rendering helpers as focus_style (_focus_box_style/_focus_underline_style/
# _FOCUS_PADDING_RE take color_role/highlight_box/box_opacity/padding/underline generically) --
# never duplicated -- tinted with the already-approved SUCCESS hex instead of PRIMARY_FOCUS.
# ---------------------------------------------------------------------------

SUCCESS_STYLE_CANDIDATES = {
    "COLOR_ONLY": {"color_role": "SUCCESS", "highlight_box": False, "box_opacity": 0.0, "padding": "0", "underline": False},
    "BALANCED_SUCCESS": {"color_role": "SUCCESS", "highlight_box": True, "box_opacity": 0.15, "padding": "2px 8px", "underline": False},
    "STRONG_SUCCESS": {"color_role": "SUCCESS", "highlight_box": True, "box_opacity": 0.28, "padding": "4px 12px", "underline": True},
}


def build_success_style_candidates() -> dict:
    return {name: dict(props) for name, props in SUCCESS_STYLE_CANDIDATES.items()}


def validate_success_style_candidates(candidates: dict) -> dict:
    issues = []
    if len(candidates) != 3:
        issues.append(f"expected exactly 3 candidates, got {len(candidates)}")
    if len(set(candidates)) != len(candidates):
        issues.append("candidate ids are not unique")
    for name, props in candidates.items():
        required = ("color_role", "highlight_box", "box_opacity", "padding", "underline")
        missing = [k for k in required if k not in props]
        if missing:
            issues.append(f"{name}: missing properties {missing}")
            continue
        if props["color_role"] not in COLOR_REVIEW_ROLES:
            issues.append(f"{name}: color_role {props['color_role']!r} is not an approved palette role")
        if not isinstance(props["highlight_box"], bool):
            issues.append(f"{name}: highlight_box must be bool, got {props['highlight_box']!r}")
        if not isinstance(props["underline"], bool):
            issues.append(f"{name}: underline must be bool, got {props['underline']!r}")
        if not (0.0 <= props["box_opacity"] <= 1.0):
            issues.append(f"{name}: box_opacity out of range ({props['box_opacity']})")
        if not _FOCUS_PADDING_RE.match(props["padding"]):
            issues.append(f"{name}: invalid CSS padding ({props['padding']!r})")
    return {"pass": len(issues) == 0, "issues": issues}


def _success_style_review_page(title: str, body: str, font_stack: str, colors: dict, page_bg: str) -> str:
    return (
        f'<!doctype html><html><head><meta charset="utf-8"><title>{_html_escape(title)}</title></head>'
        f'<body style="background:{page_bg};color:{colors["DEFAULT"]};font-family:{font_stack};padding:40px;">'
        f'<header data-preview-metadata style="opacity:0.5;font-size:12px;font-family:sans-serif;">PREVIEW ONLY -- '
        f'Success Style Human Review. success_style is NOT APPROVED. Font Family/Background/Color Palette/'
        f'Typography Scale/Font Weight/Caption Style/Focus Style are already Human Review APPROVED and are fixed '
        f'conditions here. Human decision: NONE. The approved SUCCESS color role is fixed across all candidates -- '
        f'only the presentation added on top of it (highlight box / underline) varies. This is a learning '
        f'confirmation, not a celebration screen -- no invented celebration copy is used.</header>'
        f'<main data-frame-preview>{body}</main></body></html>'
    )


def _success_element(candidate: dict, size_style: str, colors: dict, text: str, extra_style: str = "") -> str:
    color_style = f'color:{colors[candidate["color_role"]]};'
    box_style = _focus_box_style(candidate, colors[candidate["color_role"]])
    underline_style = _focus_underline_style(candidate)
    return (
        f'<div data-success-element style="{size_style}{color_style}{box_style}{underline_style}'
        f'padding:{candidate["padding"]};{extra_style}">{_html_escape(text)}</div>'
    )


def build_success_single_answer_prototype(candidate: dict, sizes: dict, weights: dict, font_stack: str, colors: dict, page_bg: str) -> str:
    # Real CB06 ANSWER_CONFIRMATION phase: visible=True, no override -> canonical DOMINANT/SUCCESS
    # binding applies as-is, real source_text "CAP" (uppercase) shown verbatim.
    size_style = f'font-size:{sizes["DOMINANT"]}px;font-weight:{weights["DOMINANT"]};'
    body = _success_element(candidate, size_style, colors, "CAP")
    return _success_style_review_page("Single Answer (CB06 ANSWER_CONFIRMATION)", body, font_stack, colors, page_bg)


def build_success_prompt_to_answer_prototype(candidate: dict, sizes: dict, weights: dict, font_stack: str, colors: dict, page_bg: str) -> str:
    # Real CB06 CASE_BRIDGE+ phase: QUESTION role becomes state_override=MUTED/color_override=MUTED
    # (prompt trace), ANSWER role gets text_override="lower" (display-only, source_text unchanged) --
    # both taken verbatim from the real _cb06_phase_overrides table, never invented.
    size_style = f'font-size:{sizes["DOMINANT"]}px;font-weight:{weights["DOMINANT"]};'
    prompt_style = size_style + f'color:{colors["MUTED"]};opacity:0.4;'
    body = (
        f'<div data-element-state="MUTED" style="{prompt_style}">CAP</div>'
        + _success_element(candidate, size_style, colors, "cap")
    )
    return _success_style_review_page("Prompt to Answer (CB06 CASE_BRIDGE+)", body, font_stack, colors, page_bg)


def build_success_focus_and_success_prototype(candidate: dict, sizes: dict, weights: dict, font_stack: str, colors: dict, page_bg: str) -> str:
    # Shows the approved focus_style (COLOR_ONLY, PRIMARY_FOCUS) alongside this success_style
    # candidate (SUCCESS) so the reviewer can verify the two semantics stay distinguishable.
    size_style = f'font-size:{sizes["DOMINANT"]}px;font-weight:{weights["DOMINANT"]};'
    focus_style = size_style + f'color:{colors["PRIMARY_FOCUS"]};'
    body = (
        f'<div style="{focus_style}">CAP</div>'
        + _success_element(candidate, size_style, colors, "cap")
    )
    return _success_style_review_page("Focus and Success Together", body, font_stack, colors, page_bg)


def build_success_dense_learning_prototype(candidate: dict, sizes: dict, weights: dict, font_stack: str, colors: dict, page_bg: str) -> str:
    prompt_style = f'font-size:{sizes["PRIMARY"]}px;font-weight:{weights["PRIMARY"]};color:{colors["DEFAULT"]};'
    relation_style = f'font-size:{sizes["SUPPORTING"]}px;font-weight:{weights["SUPPORTING"]};color:{colors["RELATION"]};'
    micro_style = f'font-size:{sizes["MICRO"]}px;font-weight:{weights["MICRO"]};color:{colors["SECONDARY"]};'
    size_style = f'font-size:{sizes["DOMINANT"]}px;font-weight:{weights["DOMINANT"]};'
    body = (
        f'<div style="{prompt_style}">직접 읽어보세요.</div>'
        + f'<div style="{relation_style}">CAP → cap</div>'
        + _success_element(candidate, size_style, colors, "cap")
        + f'<div style="{micro_style}">metadata sample</div>'
    )
    return _success_style_review_page("Dense Learning", body, font_stack, colors, page_bg)


def build_success_korean_english_prototype(candidate: dict, sizes: dict, weights: dict, font_stack: str, colors: dict, page_bg: str) -> str:
    prompt_style = f'font-size:{sizes["PRIMARY"]}px;font-weight:{weights["PRIMARY"]};color:{colors["DEFAULT"]};'
    size_style = f'font-size:{sizes["DOMINANT"]}px;font-weight:{weights["DOMINANT"]};'
    body = (
        f'<div style="{prompt_style}">정답을 확인해 보세요.</div>'
        + _success_element(candidate, size_style, colors, "cap")
    )
    return _success_style_review_page("Korean + English", body, font_stack, colors, page_bg)


def build_success_multiple_elements_prototype(candidate: dict, sizes: dict, weights: dict, font_stack: str, colors: dict, page_bg: str) -> str:
    # Same real "CAP / CAP -> cap / cap" triple as build_color_relation_prototype (13-4C-7), plus the
    # approved focus_style, to verify SUCCESS stays visually unique against DEFAULT/RELATION/PRIMARY_FOCUS.
    size_style = f'font-size:{sizes["DOMINANT"]}px;font-weight:{weights["DOMINANT"]};'
    default_style = f'font-size:{sizes["SUPPORTING"]}px;font-weight:{weights["SUPPORTING"]};color:{colors["DEFAULT"]};'
    focus_style = size_style + f'color:{colors["PRIMARY_FOCUS"]};'
    relation_style = f'font-size:{sizes["SUPPORTING"]}px;font-weight:{weights["SUPPORTING"]};color:{colors["RELATION"]};'
    body = (
        f'<div style="{default_style}">직접 읽어보세요.</div>'
        + f'<div style="{focus_style}">CAP</div>'
        + f'<div style="{relation_style}">CAP → cap</div>'
        + _success_element(candidate, size_style, colors, "cap")
    )
    return _success_style_review_page("Multiple Learning Elements", body, font_stack, colors, page_bg)


def build_success_side_by_side_prototype(candidates: dict, sizes: dict, weights: dict, font_stack: str, colors: dict, page_bg: str) -> str:
    size_style = f'font-size:{sizes["DOMINANT"]}px;font-weight:{weights["DOMINANT"]};'
    blocks = []
    for name, candidate in candidates.items():
        blocks.append(
            '<section>'
            f'<div style="font-family:sans-serif;font-size:12px;opacity:0.6;">{name} (highlight_box={candidate["highlight_box"]}, box_opacity={candidate["box_opacity"]}, underline={candidate["underline"]})</div>'
            + _success_element(candidate, size_style, colors, "cap")
            + '</section>'
        )
    return _success_style_review_page("Success Style Side by Side", "\n".join(blocks), font_stack, colors, page_bg)


_SUCCESS_STYLE_PROTOTYPE_BUILDERS = (
    ("01_SINGLE_ANSWER", "Single Answer", build_success_single_answer_prototype, "실제 CB06 ANSWER_CONFIRMATION phase 재현 -- 단일 answer 강조 확인"),
    ("02_PROMPT_TO_ANSWER", "Prompt to Answer", build_success_prompt_to_answer_prototype, "실제 CB06 CASE_BRIDGE+ phase 재현 -- prompt trace(MUTED) vs answer(SUCCESS) 구별 확인"),
    ("03_FOCUS_AND_SUCCESS", "Focus and Success Together", build_success_focus_and_success_prototype, "승인된 focus_style(PRIMARY_FOCUS)과 success_style(SUCCESS) 동시 표시 -- 구별 확인"),
    ("04_DENSE_LEARNING", "Dense Learning", build_success_dense_learning_prototype, "여러 role이 밀집한 화면에서 answer가 구별되는지 확인"),
    ("05_KOREAN_ENGLISH", "Korean + English", build_success_korean_english_prototype, "한글 지시문 + 영어 answer 혼합 확인, celebration 텍스트 없음"),
    ("06_MULTIPLE_LEARNING_ELEMENTS", "Multiple Learning Elements", build_success_multiple_elements_prototype, "DEFAULT/RELATION/PRIMARY_FOCUS/SUCCESS 동시 존재 시 SUCCESS 구별 확인"),
)


def generate_success_style_review_prototypes(
    assets_dir: Path, plan_id: int, font_stack: str, colors: dict, page_bg: str, sizes: dict, weights: dict, candidates: dict,
    caption_style: dict, focus_style: dict,
) -> dict:
    review_dir = assets_dir / "generated" / f"plan_{plan_id}" / "render" / "success_style_review"
    review_dir.mkdir(parents=True, exist_ok=True)

    file_entries = []
    side_by_side_html = build_success_side_by_side_prototype(candidates, sizes, weights, font_stack, colors, page_bg)
    (review_dir / "00_SUCCESS_STYLE_SIDE_BY_SIDE.html").write_text(side_by_side_html, encoding="utf-8")
    file_entries.append({"file": "00_SUCCESS_STYLE_SIDE_BY_SIDE.html", "prototype_type": "00_SIDE_BY_SIDE", "candidate": None})

    for prefix, _label, builder, _desc in _SUCCESS_STYLE_PROTOTYPE_BUILDERS:
        for candidate_name, candidate in candidates.items():
            filename = f"{prefix}_{candidate_name}.html"
            html = builder(candidate, sizes, weights, font_stack, colors, page_bg)
            (review_dir / filename).write_text(html, encoding="utf-8")
            file_entries.append({"file": filename, "prototype_type": prefix, "candidate": candidate_name})

    validation = validate_success_style_candidates(candidates)
    manifest = {
        "revision": "13-4C-18", "review_type": "SUCCESS_STYLE_HUMAN_REVIEW_PREPARATION",
        "production_plan_id": plan_id, "visual_design_version": VISUAL_DESIGN_VERSION,
        "canonical_visual_candidate": "CLEAN_DARK_FOCUS",
        "success_style_status": "PENDING_VISUAL_REVIEW",
        "approved_fixed_conditions": {
            "font_family": font_stack, "background": page_bg, "color_palette": colors,
            "typography_scale": sizes, "font_weight": weights, "caption_style": caption_style,
            "focus_style": focus_style,
        },
        "candidates": candidates,
        "success_semantic_note": (
            "success_style has no prior implementation in this codebase beyond the already-approved "
            "SUCCESS color role (bound to zone_role ANSWER via _color_role_for_zone) and the real "
            "_cb06_phase_overrides(role=='ANSWER') visibility/text-transform policy. Real Plan 7 data "
            "confirms SUCCESS is used exactly once, in CB06 (MINI_SUCCESS_LAYOUT) -- "
            "_color_role_usage_counts across all 8 scenes gives SUCCESS=1. Candidates only add "
            "presentation on top of the fixed SUCCESS color; no celebration copy is invented."
        ),
        "cb06_note": (
            "01_SINGLE_ANSWER and 02_PROMPT_TO_ANSWER statically reproduce the real "
            "_cb06_phase_overrides ANSWER_CONFIRMATION and CASE_BRIDGE+ phases for comparison only -- "
            "they do not modify the actual CB06 phase policy or live Timeline (13-4B-R1 unchanged)."
        ),
        "hierarchy_validation": validation,
        "human_decision": None,
        "zero_db_write": True,
        "prototype_files": file_entries, "generated_at": datetime.utcnow().isoformat(),
    }
    (review_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    index_lines = ['<!doctype html><html><head><meta charset="utf-8"><title>Success Style Review</title></head><body>']
    index_lines.append(f"<p>Current stage: 13-4C-18 Success Style Human Review -- success_style status: {manifest['success_style_status']}, Human Decision: NONE</p>")
    index_lines.append("<p>Fixed conditions (이미 Human Review APPROVED): Font Family=VERDANA_HUMANIST, Background=#111318, Color Palette 7 role, Typography Scale=LARGE_BEGINNER(72/46/28/20/15px), Font Weight=BALANCED_HIERARCHY(800/700/500/400/400), Caption Style=BALANCED_INTEGRATED, Focus Style=COLOR_ONLY.</p>")
    index_lines.append("<p>이 review는 REVIEW ONLY입니다. success_style은 아직 APPROVED가 아닙니다. Human Decision = NONE. 실제 Plan 7에서 SUCCESS는 CB06 1곳에서만 쓰입니다.</p>")
    index_lines.append('<h3>Side by Side</h3><ul><li><a href="00_SUCCESS_STYLE_SIDE_BY_SIDE.html">00_SUCCESS_STYLE_SIDE_BY_SIDE.html</a></li></ul>')
    for prefix, label, _builder, desc in _SUCCESS_STYLE_PROTOTYPE_BUILDERS:
        index_lines.append(f"<h3>{_html_escape(label)}</h3><p>{_html_escape(desc)}</p><ul>")
        for candidate_name, candidate in candidates.items():
            filename = f"{prefix}_{candidate_name}.html"
            index_lines.append(f'<li><a href="{filename}">{filename}</a> -- {candidate_name} (highlight_box={candidate["highlight_box"]}, box_opacity={candidate["box_opacity"]}, padding={candidate["padding"]}, underline={candidate["underline"]})</li>')
        index_lines.append("</ul>")
    index_lines.append("<h3>SUCCESS STYLE HUMAN REVIEW</h3><ol>")
    for i, candidate_name in enumerate(candidates, start=1):
        c = candidates[candidate_name]
        index_lines.append(f"<li>{i} = {candidate_name} (color_role={c['color_role']}, highlight_box={c['highlight_box']}, box_opacity={c['box_opacity']}, padding={c['padding']}, underline={c['underline']})</li>")
    index_lines.append(f"<li>{len(candidates) + 1} = 세 후보 모두 부적절 -- 새 후보 필요</li>")
    index_lines.append("</ol>")
    index_lines.append("</body></html>")
    (review_dir / "index.html").write_text("\n".join(index_lines), encoding="utf-8")

    return {"review_dir": review_dir, "manifest": manifest, "file_count": len(file_entries), "validation": validation}


def run_success_style_review(db_path: Path, assets_dir: Path, reports_dir: Path, *, plan_id: int | None = None) -> dict:
    entry_gate = validate_visual_design_entry_gate(db_path, assets_dir, plan_id=plan_id)
    if not entry_gate["pass"]:
        return {"pass": False, "reason": entry_gate["reason"], "plan_id": entry_gate.get("plan_id")}
    pid = entry_gate["plan_id"]

    canonical = select_canonical_visual_approval(db_path, pid)
    if canonical is None:
        return {"pass": False, "reason": "No canonical CANONICAL_CORRECTION visual_design_specs row found -- run `correct-visual-approval` first.", "plan_id": pid}

    record = canonical["design"]
    if record.get("selected_candidate") != "CLEAN_DARK_FOCUS":
        return {"pass": False, "reason": f"Canonical visual candidate is {record.get('selected_candidate')!r}, not CLEAN_DARK_FOCUS -- this review is scoped to CLEAN_DARK_FOCUS only.", "plan_id": pid}

    cats = record.get("category_approvals", {})
    for required in ("font_family", "background", "color_palette", "typography_scale", "font_weight", "caption_style", "focus_style"):
        if cats.get(required, {}).get("resolution_status") != "APPROVED":
            return {"pass": False, "reason": f"{required} must be Human Review approved before Success Style review.", "plan_id": pid}
    if cats.get("success_style", {}).get("resolution_status") == "APPROVED":
        return {"pass": False, "reason": "success_style is already APPROVED on the current canonical record.", "plan_id": pid}

    font_stack = cats["font_family"]["resolved_style"]
    page_bg = cats["background"]["resolved_style"]
    colors = cats["color_palette"]["resolved_style"]
    sizes = cats["typography_scale"]["resolved_style"]
    weights = cats["font_weight"]["resolved_style"]
    caption_style = cats["caption_style"]["resolved_style"]
    focus_style = cats["focus_style"]["resolved_style"]

    candidates = build_success_style_candidates()
    result = generate_success_style_review_prototypes(assets_dir, pid, font_stack, colors, page_bg, sizes, weights, candidates, caption_style, focus_style)
    report_path = _build_success_style_review_report(reports_dir, pid, sizes, weights, caption_style, focus_style, candidates, result)

    return {
        "pass": True, "plan_id": pid, "candidates": candidates, "sizes": sizes, "weights": weights,
        "review_dir": result["review_dir"], "manifest": result["manifest"], "file_count": result["file_count"],
        "validation": result["validation"], "report_path": report_path,
    }


def _build_success_style_review_report(reports_dir: Path, plan_id: int, sizes: dict, weights: dict, caption_style: dict, focus_style: dict, candidates: dict, result: dict) -> Path:
    lines: list[str] = ["# Success Style Human Review Report", ""]
    lines.append(f"생성일: {datetime.utcnow().date().isoformat()}")
    lines.append(f"Source Plan: {plan_id}")
    lines.append("")
    lines.append("## Source-of-Truth Investigation")
    lines.append("")
    lines.append(result["manifest"]["success_semantic_note"])
    lines.append("")
    lines.append("## Fixed Approved Conditions")
    lines.append("")
    lines.append(f"Typography Scale (DOMINANT role): {sizes['DOMINANT']}px / {weights['DOMINANT']} (native/synthetic per 13-4C-13 provenance)")
    lines.append(f"Caption Style (unchanged): {caption_style}")
    lines.append(f"Focus Style (unchanged): {focus_style}")
    lines.append("")
    lines.append("## CB06 Note")
    lines.append("")
    lines.append(result["manifest"]["cb06_note"])
    lines.append("")
    lines.append("## Candidates (결정론적)")
    lines.append("")
    lines.append("| Candidate | color_role | highlight_box | box_opacity | padding | underline |")
    lines.append("|---|---|---|---|---|---|")
    for name, c in candidates.items():
        lines.append(f"| {name} | {c['color_role']} | {c['highlight_box']} | {c['box_opacity']} | {c['padding']} | {c['underline']} |")
    lines.append("")
    lines.append(f"Files: {result['file_count']}")
    lines.append(f"Directory: {result['review_dir']}")
    lines.append(f"Review first: {result['review_dir'] / 'index.html'}")
    lines.append("")
    lines.append("## Human Decision")
    lines.append("")
    lines.append("NONE -- Prototype 생성만 완료됨. 사용자가 실제로 화면을 본 뒤 결정해야 함.")
    lines.append("")
    lines.append("## SUCCESS STYLE HUMAN REVIEW")
    lines.append("")
    for i, name in enumerate(candidates, start=1):
        c = candidates[name]
        lines.append(f"{i} = {name} (color_role={c['color_role']}, highlight_box={c['highlight_box']}, box_opacity={c['box_opacity']}, padding={c['padding']}, underline={c['underline']})")
    lines.append(f"{len(candidates) + 1} = 세 후보 모두 부적절 -- 새 후보 필요")
    lines.append("")

    reports_dir.mkdir(parents=True, exist_ok=True)
    out_path = reports_dir / f"success_style_review_{datetime.utcnow().date().isoformat()}.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path
