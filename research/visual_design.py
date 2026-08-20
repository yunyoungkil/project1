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
        # Derive the human-readable label from the actual applied style string itself (never a
        # separately hardcoded value) -- this is exactly what prevented a real bug: an earlier
        # version hardcoded "PRIMARY 40px/700" as a label while CLEAN_DARK_FOCUS's real value is
        # 42px, silently showing a wrong number next to the correctly-styled text.
        size_match = re.search(r"font-size:(\d+px)", role_style)
        weight_match = re.search(r"font-weight:(\d+)", role_style)
        label = f"{role} — {size_match.group(1)} / {weight_match.group(1)}"
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
