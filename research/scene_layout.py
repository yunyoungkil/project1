"""13-3: compiles a 13-2-verified-ready Timeline into a Renderer-neutral Scene/Layout Model --
WHERE each visual element belongs on screen, as logical Zones (never pixel coordinates, colors,
fonts, or renderer-specific structure). 13-2 Timeline is the only canonical timing source; this
module copies start_ms/end_ms/duration_ms/reveal_not_before_ms verbatim and never recomputes them.
No Gemini TTS, YouTube, or video-generation API calls -- it only reads existing DB rows/JSON files.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from research.asset_generator import _load_production_blocks, _load_speech_assets, select_target_plan
from research.db import connect
from research.render_spec import (
    SPEC_VERSION,
    _RENDERER_SPECIFIC_MARKERS,
    ready_for_timeline_compilation_gate,
    run_render_spec_integrity_check,
    validate_render_spec,
)
from research.timeline_compiler import (
    TIMELINE_VERSION,
    ready_for_scene_layout_gate,
    run_timeline_integrity_check,
    validate_timeline,
    validate_timeline_entry_gate,
)

LAYOUT_VERSION = "13.3"

# ---------------------------------------------------------------------------
# Layout Type Taxonomy -- a fixed 1:1 rename of 13-1's scene_role (section: prompts/13-3 section 6
# design note). scene_role is already a semantic classification derived from real production_intent
# and EN_PHONEME_DEMO composition (13-1 section 8) -- reclassifying it here from scratch would
# duplicate that logic and risk the two stages disagreeing on the same scene. This is the same
# "fixed mapping off scene_role" principle 13-1's classify_visual_intent already uses.
# ---------------------------------------------------------------------------

LAYOUT_TYPES = {
    "OPENING_LAYOUT", "EXPLANATION_LAYOUT", "WORD_FOCUS_LAYOUT", "PHONEME_LAYOUT", "BLENDING_LAYOUT",
    "PRACTICE_LAYOUT", "MINI_SUCCESS_LAYOUT", "RECAP_LAYOUT", "RESOLUTION_LAYOUT", "UNRESOLVED_LAYOUT",
}
_SCENE_ROLE_TO_LAYOUT_TYPE = {
    "OPENING": "OPENING_LAYOUT", "EXPLANATION": "EXPLANATION_LAYOUT", "WORD_DEMO": "WORD_FOCUS_LAYOUT",
    "PHONEME_DEMO": "PHONEME_LAYOUT", "BLENDING": "BLENDING_LAYOUT", "PRACTICE": "PRACTICE_LAYOUT",
    "MINI_SUCCESS": "MINI_SUCCESS_LAYOUT", "RECAP": "RECAP_LAYOUT", "RESOLUTION": "RESOLUTION_LAYOUT",
    "UNRESOLVED": "UNRESOLVED_LAYOUT",
}


def classify_layout_type(scene_role: str) -> str:
    return _SCENE_ROLE_TO_LAYOUT_TYPE.get(scene_role, "UNRESOLVED_LAYOUT")


# ---------------------------------------------------------------------------
# Zone Model -- logical screen regions, never pixel coordinates (section 8). Element -> Zone is a
# fixed total mapping over 13-1's 7 text_element roles (section 9: reuse the 13-1 taxonomy, do not
# invent new text roles). Not every Zone in ZONE_ROLES is populated by every Scene -- real Plan 7
# data never needs HEADER/CONTEXT/MAIN/SECONDARY/FOOTER (section 7: adjust taxonomy usage to real
# data, report why rather than force-filling empty zones).
# ---------------------------------------------------------------------------

ZONE_ROLES = {
    "HEADER", "CONTEXT", "MAIN", "PRIMARY_FOCUS", "SECONDARY", "PHONEME", "BUILD_SEQUENCE",
    "CAPTION", "EXPLANATION", "PROMPT", "ANSWER", "FOOTER",
}
_ELEMENT_ROLE_TO_ZONE = {
    "TARGET_WORD": "PRIMARY_FOCUS", "PHONEME": "PHONEME", "BLEND_SEQUENCE": "BUILD_SEQUENCE",
    "CAPTION": "CAPTION", "EXPLANATION": "EXPLANATION", "QUESTION": "PROMPT", "ANSWER": "ANSWER",
}
_ZONE_ALIGNMENT_INTENT = {
    "PRIMARY_FOCUS": "CENTER", "ANSWER": "CENTER", "PROMPT": "CENTER", "CAPTION": "BOTTOM",
    "PHONEME": "SUPPORTING", "BUILD_SEQUENCE": "SUPPORTING", "EXPLANATION": "SUPPORTING",
    "HEADER": "TOP", "CONTEXT": "TOP", "MAIN": "CENTER", "SECONDARY": "SUPPORTING", "FOOTER": "BOTTOM",
}
_ZONE_SIZE_INTENT = {"PRIMARY_FOCUS": "DOMINANT", "ANSWER": "DOMINANT"}

_PRIMARY_ROLES = {"TARGET_WORD", "QUESTION", "ANSWER"}
_SECONDARY_ROLES = {"PHONEME", "BLEND_SEQUENCE"}
PRIORITY_PRIMARY, PRIORITY_SECONDARY, PRIORITY_SUPPORT = 100, 70, 40


def _element_priority(text_element: dict) -> int:
    if text_element.get("emphasis") or text_element.get("role") in _PRIMARY_ROLES:
        return PRIORITY_PRIMARY
    if text_element.get("role") in _SECONDARY_ROLES:
        return PRIORITY_SECONDARY
    return PRIORITY_SUPPORT


# ---------------------------------------------------------------------------
# Input Gate (section 2) -- reuses 13-2's own validate_timeline_entry_gate rather than inventing a
# second judgment of readiness; adds a fresh re-verification of 13-1 spec validity too, since this
# module needs render_spec lineage (text_elements/emphasis_targets) as well as Timeline timing.
# ---------------------------------------------------------------------------

def validate_layout_entry_gate(db_path: Path, assets_dir: Path, plan_id: int | None = None) -> dict:
    timeline_gate = validate_timeline_entry_gate(db_path, assets_dir, plan_id=plan_id)
    if not timeline_gate["pass"]:
        return {"pass": False, "reason": timeline_gate["reason"], "spec": None, "timeline": None, "plan_id": timeline_gate.get("plan_id")}

    pid = timeline_gate["plan_id"]
    spec = timeline_gate["spec"]

    with connect(db_path) as conn:
        timeline_row = conn.execute(
            "SELECT id, timeline_json, validation_json FROM render_timelines WHERE production_plan_id = ? ORDER BY id DESC LIMIT 1",
            (pid,),
        ).fetchone()
    if timeline_row is None:
        return {"pass": False, "reason": "No render_timelines row found for this plan -- run `render-timeline` first.", "spec": spec, "timeline": None, "plan_id": pid}

    db_timeline = json.loads(timeline_row["timeline_json"])
    json_path = assets_dir / "generated" / f"plan_{pid}" / "render" / "timeline.json"
    if not json_path.exists():
        return {"pass": False, "reason": f"timeline.json not found at {json_path}.", "spec": spec, "timeline": None, "plan_id": pid}
    file_timeline = json.loads(json_path.read_text(encoding="utf-8"))

    if db_timeline != file_timeline:
        return {
            "pass": False, "spec": spec, "timeline": None, "plan_id": pid,
            "reason": "render_timelines DB row and timeline.json file content differ -- refusing to guess which is authoritative (section 3).",
        }

    timeline = db_timeline
    if timeline.get("timeline_version") != TIMELINE_VERSION:
        return {"pass": False, "reason": f"timeline_version {timeline.get('timeline_version')!r} != {TIMELINE_VERSION!r}", "spec": spec, "timeline": timeline, "plan_id": pid}
    if timeline.get("production_plan_id") != pid:
        return {"pass": False, "reason": "timeline.production_plan_id does not match the selected Production Plan.", "spec": spec, "timeline": timeline, "plan_id": pid}

    stored_validation = json.loads(timeline_row["validation_json"] or "{}")
    if stored_validation.get("unresolved_critical"):
        return {"pass": False, "spec": spec, "timeline": timeline, "plan_id": pid, "reason": f"13-2 validation has unresolved critical fields: {stored_validation['unresolved_critical']}"}

    # Re-verify fresh against current DB state -- never trust a stale stored boolean (same
    # discipline 13-2 applied to 13-1).
    production_blocks = _load_production_blocks(db_path, pid)
    speech_assets = _load_speech_assets(db_path, pid)
    fresh_spec_validation = validate_render_spec(db_path, pid, spec, production_blocks, speech_assets)
    fresh_spec_integrity = run_render_spec_integrity_check({"ready": True}, spec, fresh_spec_validation)
    ready_for_tc = ready_for_timeline_compilation_gate({"ready": True}, spec, fresh_spec_validation, fresh_spec_integrity)
    if not ready_for_tc:
        return {"pass": False, "spec": spec, "timeline": timeline, "plan_id": pid, "reason": "13-1 Ready for Timeline Compilation is not YES when re-verified against current DB state."}

    fresh_timeline_validation = validate_timeline(spec, timeline)
    fresh_timeline_entry_gate = {"pass": True}
    fresh_timeline_integrity = run_timeline_integrity_check(fresh_timeline_entry_gate, spec, timeline, fresh_timeline_validation)
    ready_for_layout = ready_for_scene_layout_gate(fresh_timeline_entry_gate, fresh_timeline_validation, fresh_timeline_integrity)
    if not ready_for_layout:
        return {"pass": False, "spec": spec, "timeline": timeline, "plan_id": pid, "reason": "Ready for Scene/Layout is not YES when re-verified against current DB state."}

    return {"pass": True, "reason": None, "spec": spec, "timeline": timeline, "plan_id": pid, "timeline_row_id": timeline_row["id"]}


# ---------------------------------------------------------------------------
# Scene Layout compilation (sections 5, 9-13, 28)
# ---------------------------------------------------------------------------

def bind_elements_to_zones(spec_scene: dict) -> list[dict]:
    bindings = []
    for i, t in enumerate(spec_scene.get("text_elements") or []):
        zone_role = _ELEMENT_ROLE_TO_ZONE.get(t["role"])
        if zone_role is None:
            continue
        bindings.append({
            "element_id": f"{spec_scene['scene_id']}-BIND{i + 1}",
            "source_element_id": t["element_id"],
            "element_role": t["role"],
            "zone_id": zone_role.lower(),
            "priority": _element_priority(t),
        })
    return bindings


def _scene_answer_reveal_barrier(timeline_scene: dict) -> dict | None:
    """Section 12/critical safeguard: whether a Scene needs an answer-hidden constraint is decided
    from the Timeline's OWN events, never from render_spec.scene.answer_reveal_policy. Real Plan 7
    data shows why: is_mini_success_answer_asset() is asset-scoped, not block-scoped, so CB07
    (RECAP, replays the CAP answer asset with no PAUE/barrier at all) ends up with a non-null
    render_spec.scene.answer_reveal_policy too -- trusting that field here would wrongly attach an
    ANSWER_HIDDEN_BEFORE_BARRIER constraint to CB07. The Timeline only ever materializes a real
    ANSWER_REVEAL_BARRIER event for scenes that actually have one (CB06)."""
    return next((e for e in timeline_scene.get("events") or [] if e["event_type"] == "ANSWER_REVEAL_BARRIER"), None)


def build_visibility_rules(spec_scene: dict, timeline_scene: dict) -> list[dict]:
    barrier = _scene_answer_reveal_barrier(timeline_scene)
    rules = []
    for t in spec_scene.get("text_elements") or []:
        if t.get("reveal_policy") == "AFTER_PAUSE" and barrier is not None:
            rules.append({
                "element_id": t["element_id"],
                "visibility": {"policy": "AFTER_BARRIER", "barrier_event_type": "ANSWER_REVEAL_BARRIER", "not_before_ms": barrier["reveal_not_before_ms"]},
            })
        else:
            rules.append({"element_id": t["element_id"], "visibility": {"policy": "SCENE_DEFAULT"}})
    return rules


def bind_emphasis_targets(spec_scene: dict) -> list[dict]:
    """Section 24: preserve emphasis_targets lineage without inventing an actual emphasis technique
    (color/scale/bounce/glow are all forbidden) -- a single semantic "PRIMARY" intent is all
    upstream data supports."""
    text_by_event_order = {t["event_order"]: t for t in spec_scene.get("text_elements") or []}
    bindings = []
    for e in spec_scene.get("emphasis_targets") or []:
        matched = text_by_event_order.get(e["event_order"])
        zone_role = _ELEMENT_ROLE_TO_ZONE.get(matched["role"]) if matched else None
        bindings.append({
            "emphasis_event_order": e["event_order"], "content": e.get("content"), "role": e.get("role"),
            "bound_element_id": matched["element_id"] if matched else None,
            "zone_id": zone_role.lower() if zone_role else None,
            "emphasis_intent": "PRIMARY",
        })
    return bindings


def build_layout_constraints(spec_scene: dict, timeline_scene: dict, zones_present: set[str], visibility_rules: list[dict]) -> list[dict]:
    """Section 27: only constraints real upstream data actually requires -- no invented rules."""
    constraints = []
    for rule in visibility_rules:
        if rule["visibility"]["policy"] == "AFTER_BARRIER":
            barrier = _scene_answer_reveal_barrier(timeline_scene)
            constraints.append({
                "constraint_type": "ANSWER_HIDDEN_BEFORE_BARRIER",
                "target_element_id": rule["element_id"],
                "source_event_id": barrier["event_id"] if barrier else None,
                "not_before_ms": rule["visibility"]["not_before_ms"],
            })

    if "PRIMARY_FOCUS" in zones_present:
        constraints.append({"constraint_type": "PRIMARY_FOCUS_REQUIRED", "zone_id": "primary_focus"})

    if spec_scene.get("scene_role") == "BLENDING":
        blend_elements = [t for t in spec_scene.get("text_elements") or [] if t["role"] == "BLEND_SEQUENCE"]
        target_elements = [t for t in spec_scene.get("text_elements") or [] if t["role"] == "TARGET_WORD"]
        for blend in blend_elements:
            later_targets = [t for t in target_elements if t["event_order"] > blend["event_order"]]
            if later_targets:
                constraints.append({
                    "constraint_type": "BUILD_SEQUENCE_PRECEDES_TARGET",
                    "source_zone": "build_sequence", "target_zone": "primary_focus",
                    "source_element_id": blend["element_id"], "target_element_id": later_targets[0]["element_id"],
                })

    if spec_scene.get("viewer_action") and "PROMPT" in zones_present:
        barrier = _scene_answer_reveal_barrier(timeline_scene)
        first_pause_start = next((e["start_ms"] for e in timeline_scene.get("events") or [] if e["event_type"] == "PAUSE"), None)
        if first_pause_start is not None:
            constraints.append({
                "constraint_type": "PROMPT_VISIBLE_DURING_ATTEMPT", "zone_id": "prompt",
                "active_before_ms": first_pause_start,
                "not_before_ms": barrier["reveal_not_before_ms"] if barrier else None,
            })

    return constraints


def compile_scene_layout(spec_scene: dict, timeline_scene: dict) -> dict:
    layout_type = classify_layout_type(spec_scene["scene_role"])
    element_bindings = bind_elements_to_zones(spec_scene)
    zones_present = {b["element_role"] and _ELEMENT_ROLE_TO_ZONE[b["element_role"]] for b in element_bindings}
    zones_present.discard(None)

    zones = []
    for zone_role in sorted(zones_present):
        zone_id = zone_role.lower()
        zone_priority = max((b["priority"] for b in element_bindings if b["zone_id"] == zone_id), default=PRIORITY_SUPPORT)
        zones.append({
            "zone_id": zone_id, "zone_role": zone_role, "priority": zone_priority,
            "alignment_intent": _ZONE_ALIGNMENT_INTENT.get(zone_role, "CENTER"),
            "size_intent": _ZONE_SIZE_INTENT.get(zone_role, "SUPPORTING"),
        })

    visibility_rules = build_visibility_rules(spec_scene, timeline_scene)
    layout_constraints = build_layout_constraints(spec_scene, timeline_scene, zones_present, visibility_rules)
    emphasis_bindings = bind_emphasis_targets(spec_scene)

    return {
        "scene_id": spec_scene["scene_id"], "content_block_id": spec_scene["content_block_id"],
        "scene_role": spec_scene["scene_role"], "visual_intent": spec_scene["visual_intent"],
        "start_ms": timeline_scene["start_ms"], "end_ms": timeline_scene["end_ms"], "duration_ms": timeline_scene["duration_ms"],
        "layout_type": layout_type, "zones": zones, "element_bindings": element_bindings,
        "visibility_rules": visibility_rules, "layout_constraints": layout_constraints,
        "emphasis_bindings": emphasis_bindings,
    }


def compile_scene_layouts(spec: dict, timeline: dict) -> list[dict]:
    timeline_by_scene_id = {s["scene_id"]: s for s in timeline["scenes"]}
    return [
        compile_scene_layout(spec_scene, timeline_by_scene_id[spec_scene["scene_id"]])
        for spec_scene in spec["scenes"] if spec_scene["scene_id"] in timeline_by_scene_id
    ]


def build_scene_layout(spec: dict, timeline: dict) -> dict:
    return {
        "layout_version": LAYOUT_VERSION, "production_plan_id": spec["production_plan_id"],
        "timeline_version": timeline["timeline_version"], "scenes": compile_scene_layouts(spec, timeline),
    }


# ---------------------------------------------------------------------------
# Validation (section 30, 18 items)
# ---------------------------------------------------------------------------

def validate_scene_layout(db_path: Path, plan_id: int, spec: dict, timeline: dict, layout: dict) -> dict:
    checks: dict[str, bool] = {}
    layout_scenes = layout["scenes"]
    timeline_by_scene_id = {s["scene_id"]: s for s in timeline["scenes"]}
    spec_by_scene_id = {s["scene_id"]: s for s in spec["scenes"]}

    checks["timeline_version_matches"] = layout.get("timeline_version") == TIMELINE_VERSION
    checks["scene_count_preserved"] = len(layout_scenes) == len(timeline["scenes"]) == len(spec["scenes"])
    scene_ids = [s["scene_id"] for s in layout_scenes]
    checks["scene_ids_preserved"] = set(scene_ids) == set(timeline_by_scene_id.keys()) and len(scene_ids) == len(set(scene_ids))
    checks["content_block_lineage_preserved"] = all(s["content_block_id"] == s["scene_id"] for s in layout_scenes)

    checks["scene_timing_preserved"] = all(
        s["start_ms"] == timeline_by_scene_id[s["scene_id"]]["start_ms"]
        and s["end_ms"] == timeline_by_scene_id[s["scene_id"]]["end_ms"]
        and s["duration_ms"] == timeline_by_scene_id[s["scene_id"]]["duration_ms"]
        for s in layout_scenes
    )

    element_lineage_ok = True
    for s in layout_scenes:
        spec_scene = spec_by_scene_id[s["scene_id"]]
        text_ids = {t["element_id"] for t in spec_scene.get("text_elements") or []}
        for b in s["element_bindings"]:
            if b["source_element_id"] not in text_ids:
                element_lineage_ok = False
    checks["element_lineage_preserved"] = element_lineage_ok

    # 13-3 never reads or writes AUDIO/PAUSE events -- this confirms the Timeline scenes it
    # compiled against are byte-identical to the original timeline.json content (no accidental
    # mutation happened during compilation).
    checks["audio_lineage_undisturbed"] = all(
        timeline_by_scene_id[s["scene_id"]]["events"] == next(ts for ts in timeline["scenes"] if ts["scene_id"] == s["scene_id"])["events"]
        for s in layout_scenes
    )

    checks["required_elements_bound_exactly_once"] = all(
        len({b["source_element_id"] for b in s["element_bindings"]}) == len(s["element_bindings"])
        for s in layout_scenes
    )
    checks["no_unknown_critical_layout_type"] = all(s["layout_type"] != "UNRESOLVED_LAYOUT" for s in layout_scenes)

    answer_ok = True
    for s in layout_scenes:
        if s["scene_role"] != "MINI_SUCCESS":
            continue
        barrier = _scene_answer_reveal_barrier(timeline_by_scene_id[s["scene_id"]])
        if barrier is None:
            answer_ok = False
            continue
        for rule in s["visibility_rules"]:
            if rule["visibility"]["policy"] == "AFTER_BARRIER" and rule["visibility"]["not_before_ms"] != barrier["reveal_not_before_ms"]:
                answer_ok = False
    checks["mini_success_answer_not_revealed_before_barrier"] = answer_ok

    # viewer_action itself is not copied onto the layout scene dict (it lives only in the Render
    # Spec/Timeline, per spec section 13's "don't rephrase the wording") -- what 13-3 must actually
    # preserve is that a PROMPT_VISIBLE_DURING_ATTEMPT constraint exists whenever the source scene
    # genuinely has a viewer_action (never silently dropped), and is never invented otherwise.
    checks["viewer_action_preserved"] = all(
        bool(spec_by_scene_id[s["scene_id"]].get("viewer_action"))
        == any(c["constraint_type"] == "PROMPT_VISIBLE_DURING_ATTEMPT" for c in s["layout_constraints"])
        for s in layout_scenes
    )

    pause_ok = True
    for s in layout_scenes:
        timeline_scene = timeline_by_scene_id[s["scene_id"]]
        spec_pauses = spec_by_scene_id[s["scene_id"]].get("pause_requirements") or []
        timeline_pauses = [e for e in timeline_scene["events"] if e["event_type"] == "PAUSE"]
        if len(spec_pauses) != len(timeline_pauses):
            pause_ok = False
            continue
        for sp, tp in zip(spec_pauses, timeline_pauses):
            if sp.get("duration_ms") != tp.get("duration_ms"):
                pause_ok = False
    checks["pause_duration_preserved"] = pause_ok

    # 13-3 never selects a new asset -- it only reads 13-1's text_elements/emphasis_targets, which
    # are already scoped to the exact audio_elements 13-1 resolved. So the only way a failed/
    # rejected/experimental variant could appear here is if 13-1 itself had already selected one --
    # re-checking spec.scenes[].audio_elements directly (the same source 13-1's own validation
    # checks) confirms that didn't happen, rather than trusting "13-3 doesn't touch it" as proof.
    from research.asset_generator import _NON_REUSABLE_REVIEW_STATES, _latest_row_for_asset_id
    _EXPERIMENTAL_MARKERS = ("LOWERCASE_WORD", "MINIMAL_CONTEXT_WORD", "CONTEXT_RESTRICTED")
    all_audio = [a for s in spec["scenes"] for a in s.get("audio_elements") or []]
    checks["no_experimental_variant_reintroduced"] = not any(
        marker in (a.get("generation_unit_id") or "") for a in all_audio for marker in _EXPERIMENTAL_MARKERS
    )
    failed_used = False
    for a in all_audio:
        row = _latest_row_for_asset_id(db_path, plan_id, a["generation_unit_id"])
        if row:
            try:
                metadata = json.loads(row.get("metadata_json") or "{}")
            except (TypeError, ValueError):
                metadata = {}
            if metadata.get("pronunciation_review") in _NON_REUSABLE_REVIEW_STATES:
                failed_used = True
    checks["no_failed_or_rejected_asset_reintroduced"] = not failed_used

    text = json.dumps(layout, ensure_ascii=False).lower()
    checks["renderer_neutral"] = _SCENE_LAYOUT_RENDERER_MARKER_RE.search(text) is None

    pixel_keys = {"x", "y", "width", "height", "px", "font_size", "color"}
    checks["no_pixel_or_resolution_invented"] = not any(
        pixel_keys & set(zone.keys()) for s in layout_scenes for zone in s["zones"]
    )

    unresolved_critical = [name for name, passed in checks.items() if not passed]
    return {"checks": checks, "unresolved_critical": unresolved_critical, "unresolved_non_critical": ["video.width/height/fps/orientation", "max_simultaneous_elements"]}


# ---------------------------------------------------------------------------
# Renderer-neutral guard (section 25) -- extends 13-1's word-boundary marker set with the additional
# terms 13-3 explicitly forbids, without touching 13-1/13-2's own regex/constant (their checks must
# keep producing the same results).
# ---------------------------------------------------------------------------

import re

_SCENE_LAYOUT_RENDERER_MARKERS = _RENDERER_SPECIFIC_MARKERS + ("div", "flexbox", "grid-template", "motion canvas", "css class")
_SCENE_LAYOUT_RENDERER_MARKER_RE = re.compile(r"\b(?:" + "|".join(re.escape(m) for m in _SCENE_LAYOUT_RENDERER_MARKERS) + r")\b")


# ---------------------------------------------------------------------------
# Integrity Check (section 31, 17 items) -- entirely separate dict from 13-1's 13 and 13-2's 16.
# ---------------------------------------------------------------------------

def run_scene_layout_integrity_check(entry_gate: dict, spec: dict | None, timeline: dict | None, layout: dict | None, validation: dict) -> dict:
    v = validation["checks"]
    checks = {
        "scene_layout_entry_gate_safe": bool(entry_gate.get("pass")),
        "scene_layout_scene_lineage_safe": v.get("scene_count_preserved", False) and v.get("scene_ids_preserved", False),
        "scene_layout_timing_preserved": v.get("scene_timing_preserved", False),
        "scene_layout_element_lineage_safe": v.get("element_lineage_preserved", False),
        "scene_layout_zone_binding_safe": v.get("required_elements_bound_exactly_once", False),
        "scene_layout_role_safe": v.get("no_unknown_critical_layout_type", False),
        "scene_layout_mini_success_safe": v.get("mini_success_answer_not_revealed_before_barrier", False),
        "scene_layout_answer_reveal_safe": v.get("mini_success_answer_not_revealed_before_barrier", False),
        "scene_layout_viewer_action_preserved": v.get("viewer_action_preserved", False),
        "scene_layout_pause_preserved": v.get("pause_duration_preserved", False),
        "scene_layout_emphasis_preserved": all(
            eb.get("bound_element_id") is not None for s in (layout["scenes"] if layout else []) for eb in s.get("emphasis_bindings") or []
        ),
        "scene_layout_no_failed_variant": v.get("no_failed_or_rejected_asset_reintroduced", False),
        "scene_layout_no_experimental_variant": v.get("no_experimental_variant_reintroduced", False),
        "scene_layout_renderer_neutral": v.get("renderer_neutral", False),
        "scene_layout_resolution_independent": v.get("no_pixel_or_resolution_invented", False),
    }
    if spec is not None and timeline is not None and layout is not None:
        recompiled = build_scene_layout(spec, timeline)
        checks["scene_layout_deterministic"] = json.dumps(layout, sort_keys=True, ensure_ascii=False) == json.dumps(recompiled, sort_keys=True, ensure_ascii=False)
    else:
        checks["scene_layout_deterministic"] = False
    checks["scene_layout_complete"] = bool(layout) and not validation["unresolved_critical"] and all(checks.values())
    return checks


def ready_for_visual_design_gate(entry_gate: dict, validation: dict, integrity_checks: dict) -> bool:
    return bool(
        entry_gate.get("pass") and not validation["unresolved_critical"]
        and all(v is True for v in integrity_checks.values())
    )


# ---------------------------------------------------------------------------
# Persistence + file output
# ---------------------------------------------------------------------------

def persist_scene_layout(db_path: Path, plan_id: int, timeline_id: int | None, layout: dict, validation: dict) -> int:
    with connect(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO scene_layouts (production_plan_id, timeline_id, layout_version, layout_json, validation_json) VALUES (?, ?, ?, ?, ?)",
            (plan_id, timeline_id, LAYOUT_VERSION, json.dumps(layout, ensure_ascii=False), json.dumps(validation, ensure_ascii=False)),
        )
        return cur.lastrowid


def write_scene_layout_file(assets_dir: Path, plan_id: int, layout: dict) -> Path:
    render_dir = assets_dir / "generated" / f"plan_{plan_id}" / "render"
    render_dir.mkdir(parents=True, exist_ok=True)
    path = render_dir / "scene_layout.json"
    path.write_text(json.dumps(layout, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Orchestration + report
# ---------------------------------------------------------------------------

def run_scene_layout(db_path: Path, assets_dir: Path, reports_dir: Path, *, plan_id: int | None = None) -> dict:
    entry_gate = validate_layout_entry_gate(db_path, assets_dir, plan_id=plan_id)
    if not entry_gate["pass"]:
        report_path = _build_scene_layout_report(reports_dir, entry_gate, None, None, None)
        return {**entry_gate, "layout": None, "json_path": None, "report_path": report_path, "ready_for_visual_design": False}

    spec, timeline = entry_gate["spec"], entry_gate["timeline"]
    layout = build_scene_layout(spec, timeline)
    validation = validate_scene_layout(db_path, entry_gate["plan_id"], spec, timeline, layout)
    integrity_checks = run_scene_layout_integrity_check(entry_gate, spec, timeline, layout, validation)
    ready = ready_for_visual_design_gate(entry_gate, validation, integrity_checks)

    row_id = persist_scene_layout(db_path, entry_gate["plan_id"], entry_gate.get("timeline_row_id"), layout, validation)
    json_path = write_scene_layout_file(assets_dir, entry_gate["plan_id"], layout)
    report_path = _build_scene_layout_report(reports_dir, entry_gate, layout, validation, integrity_checks, ready=ready, json_path=json_path)

    return {
        "pass": True, "reason": None, "plan_id": entry_gate["plan_id"], "layout": layout,
        "validation": validation, "integrity_checks": integrity_checks, "ready_for_visual_design": ready,
        "json_path": json_path, "report_path": report_path, "scene_layout_row_id": row_id,
    }


def _build_scene_layout_report(
    reports_dir: Path, entry_gate: dict, layout: dict | None, validation: dict | None,
    integrity_checks: dict | None, *, ready: bool | None = None, json_path: Path | None = None,
) -> Path:
    lines: list[str] = ["# Scene / Layout Model Report", ""]
    lines.append(f"생성일: {datetime.utcnow().date().isoformat()}")
    lines.append(f"Source Plan: {entry_gate.get('plan_id')}")
    lines.append("")
    lines.append("## Entry Gate")
    lines.append("")
    lines.append("YES" if entry_gate["pass"] else "NO")
    if not entry_gate["pass"]:
        lines.append(f"- {entry_gate['reason']}")
    lines.append("")

    if layout is not None:
        scenes = layout["scenes"]
        lines.append(f"Layout version: {layout['layout_version']} / Timeline version: {layout['timeline_version']}")
        lines.append("")
        lines.append("## Scenes")
        lines.append("")
        for s in scenes:
            zone_ids = [z["zone_id"] for z in s["zones"]]
            lines.append(f"- {s['scene_id']} ({s['scene_role']} -> {s['layout_type']}): zones={zone_ids} bindings={len(s['element_bindings'])}")
        lines.append("")

        total_zones = sum(len(s["zones"]) for s in scenes)
        total_bindings = sum(len(s["element_bindings"]) for s in scenes)
        total_visibility = sum(len(s["visibility_rules"]) for s in scenes)
        total_constraints = sum(len(s["layout_constraints"]) for s in scenes)
        lines.append("## Counts")
        lines.append("")
        lines.append(f"Zones: {total_zones}, Element Bindings: {total_bindings}, Visibility Rules: {total_visibility}, Layout Constraints: {total_constraints}")
        lines.append("")

        mini_success = next((s for s in scenes if s["scene_role"] == "MINI_SUCCESS"), None)
        if mini_success:
            lines.append("## Mini Success Structure")
            lines.append("")
            lines.append(f"Scene: {mini_success['scene_id']}")
            lines.append(f"Zones: {[z['zone_id'] for z in mini_success['zones']]}")
            lines.append(f"Visibility Rules: {mini_success['visibility_rules']}")
            lines.append(f"Layout Constraints: {mini_success['layout_constraints']}")
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

        lines.append("## Ready for Visual Design")
        lines.append("")
        lines.append("YES" if ready else "NO")
        lines.append("")

        if json_path:
            lines.append(f"JSON: {json_path}")
            lines.append("")

    reports_dir.mkdir(parents=True, exist_ok=True)
    out_path = reports_dir / f"scene_layout_{datetime.utcnow().date().isoformat()}.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path
