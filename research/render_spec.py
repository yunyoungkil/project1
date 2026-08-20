"""13-1: compiles a 12-9-verified-ready Production Plan into a Renderer-neutral Render
Specification. Reads production_plans/production_blocks/speech_assets/generated_assets read-only
and never invents a new selection/segmentation/strategy decision -- every audio reference is
resolved through the exact same functions 12-4~12-6 already use for real FULL execution
(build_full_generation_plan / _resolve_full_execution_asset_id / build_generation_units), so a
Render Specification can never select a different asset than the one Gemini TTS actually produced
for FULL. This module makes no Gemini TTS, YouTube, or video-generation API calls -- it only reads
existing DB rows and existing WAV file metadata.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from research.asset_generator import (
    DEFAULT_BLENDING_STRATEGY,
    DEFAULT_EN_NATIVE_STRATEGY,
    _NON_REUSABLE_REVIEW_STATES,
    _has_full_run,
    _latest_row_for_asset_id,
    _load_production_blocks,
    _load_speech_assets,
    _resolve_full_execution_asset_id,
    _source_block_ids_for_speech_asset,
    build_full_generation_plan,
    build_generation_units,
    classify_phoneme_demo_type,
    compute_persistent_rendering_readiness,
    select_target_plan,
)
from research.db import connect

SPEC_VERSION = "13.1"

# ---------------------------------------------------------------------------
# Scene Role / Visual Intent taxonomy -- derived from the actual production_blocks data in Plan 7
# (section: prompts/13-1 section 8), not invented in the abstract. production_intent is free-text
# (not a fixed enum) except for the one sentinel value 11/12 already treat specially, so
# classification is keyword-based with an explicit UNRESOLVED fallback (never silent UNKNOWN).
# ---------------------------------------------------------------------------

SCENE_ROLES = {
    "OPENING", "EXPLANATION", "WORD_DEMO", "PHONEME_DEMO", "BLENDING", "PRACTICE",
    "MINI_SUCCESS", "RECAP", "RESOLUTION", "UNRESOLVED",
}
VISUAL_INTENTS = {
    "FOCUS_WORD", "FOCUS_PHONEME", "BUILD_SEQUENCE", "QUESTION_THEN_REVEAL", "COMPARE",
    "SUPPORT_NARRATION", "RECAP",
}
TEXT_ELEMENT_ROLES = {"TARGET_WORD", "PHONEME", "BLEND_SEQUENCE", "CAPTION", "EXPLANATION", "QUESTION", "ANSWER"}

_MINI_SUCCESS_INTENT = "viewer_must_attempt_before_answer"
_SCENE_ROLE_KEYWORDS = (
    # (substring to match in production_intent, resulting scene_role) -- first match wins.
    ("establish", "OPENING"),
    ("summarize", "RECAP"),
    ("recap", "RECAP"),
    ("transfer", "RESOLUTION"),
    ("practice", "PRACTICE"),
    ("demonstrate", "WORD_DEMO"),  # refined to PHONEME_DEMO/BLENDING below when applicable
    ("explain", "EXPLANATION"),
    ("highlight", "EXPLANATION"),
)


def classify_scene_role(production_block: dict, speech_assets_by_id: dict[str, dict]) -> tuple[str, str | None]:
    """Returns (scene_role, unresolved_reason). unresolved_reason is None unless scene_role is
    UNRESOLVED (section 8: never a silent UNKNOWN -- a reason is always recorded)."""
    production_intent = (production_block.get("production_intent") or "").strip()
    if production_intent == _MINI_SUCCESS_INTENT:
        return "MINI_SUCCESS", None

    matched_role = None
    for keyword, role in _SCENE_ROLE_KEYWORDS:
        if keyword in production_intent:
            matched_role = role
            break

    if matched_role is None:
        return "UNRESOLVED", f"production_intent '{production_intent}' matched no known scene role keyword"

    if matched_role == "WORD_DEMO":
        # Refine using the block's actual EN_PHONEME_DEMO assets (section 8: real data, not a
        # guess) -- classify_phoneme_demo_type is the same 12-1 classifier FULL execution uses.
        block_sids = _block_speech_asset_ids(production_block)
        phoneme_types = {
            classify_phoneme_demo_type(speech_assets_by_id[sid]["source_text"])
            for sid in block_sids if sid in speech_assets_by_id and speech_assets_by_id[sid]["speech_mode"] == "EN_PHONEME_DEMO"
        }
        if "BLENDED_SEQUENCE" in phoneme_types:
            return "BLENDING", None
        if phoneme_types:
            return "PHONEME_DEMO", None
        return "WORD_DEMO", None

    return matched_role, None


def classify_visual_intent(scene_role: str, primary_visual_type: str | None) -> str:
    if primary_visual_type == "COMPARISON":
        return "COMPARE"
    return {
        "MINI_SUCCESS": "QUESTION_THEN_REVEAL",
        "PHONEME_DEMO": "FOCUS_PHONEME",
        "BLENDING": "BUILD_SEQUENCE",
        "WORD_DEMO": "FOCUS_WORD",
        "RECAP": "RECAP",
    }.get(scene_role, "SUPPORT_NARRATION")


def _block_speech_asset_ids(production_block: dict) -> list[str]:
    """SPEECH event speech_asset_ids in timeline order, duplicates preserved (a sound can
    legitimately be spoken more than once within one block -- section 2 real-data finding)."""
    return [ev["speech_asset_id"] for ev in production_block.get("timeline") or [] if ev.get("type") == "SPEECH"]


# ---------------------------------------------------------------------------
# Generation Unit resolution -- reuses 12-4/12-5/12-6's exact FULL-execution selection logic, so
# a Render Specification can never point at a different asset than what FULL actually produced.
# ---------------------------------------------------------------------------

def _resolved_units_by_source(
    db_path: Path, plan_id: int, speech_assets: list[dict], production_blocks: list[dict], *,
    primary_en_native_strategy: str, fallback_en_native_strategy: str, default_blending_strategy: str,
    max_segment_seconds: float,
) -> dict[str, list[dict]]:
    plan_result = build_full_generation_plan(
        db_path, plan_id, speech_assets, production_blocks,
        primary_en_native_strategy=primary_en_native_strategy, fallback_en_native_strategy=fallback_en_native_strategy,
        default_blending_strategy=default_blending_strategy, max_segment_seconds=max_segment_seconds,
    )
    by_source: dict[str, list[dict]] = {}
    for entry in plan_result["generation_plan"]:
        resolved_id = _resolve_full_execution_asset_id(
            entry, primary_en_native_strategy=primary_en_native_strategy, default_blending_strategy=default_blending_strategy,
        )
        by_source.setdefault(entry["source_speech_asset_id"], []).append({
            "generation_unit_id": resolved_id, "segment_index": entry.get("segment_index"),
            "segment_count": entry.get("segment_count"), "action": entry["action"],
            "selection_reason": entry.get("selection_reason"),
        })
    return by_source


def _audio_element_from_unit(db_path: Path, plan_id: int, source_speech_asset_id: str, speech_mode: str, unit: dict, event_order: int) -> dict:
    """`event_order` (13-2 section 0 patch): the original production_blocks.timeline event_order
    this element came from. Without it, a downstream Timeline Compiler cannot determine where a
    PAUSE/VISUAL marker falls relative to this audio element other than by a fragile indirect join
    through text_elements -- this field makes that ordering a direct, structural fact instead.
    `segment_index` (already on the unit) is the tie-breaker for multiple segments of the same
    source (which all share one event_order)."""
    row = _latest_row_for_asset_id(db_path, plan_id, unit["generation_unit_id"])
    if not row or row["status"] not in {"AVAILABLE", "REUSED"}:
        return {
            "asset_id": unit["generation_unit_id"], "source_speech_asset_id": source_speech_asset_id,
            "generation_unit_id": unit["generation_unit_id"], "speech_mode": speech_mode,
            "file_path": None, "duration_ms": None, "voice_name": None, "checksum": None,
            "status": "MISSING", "event_order": event_order, "segment_index": unit.get("segment_index"),
        }
    return {
        "asset_id": unit["generation_unit_id"], "source_speech_asset_id": source_speech_asset_id,
        "generation_unit_id": unit["generation_unit_id"], "speech_mode": speech_mode,
        "file_path": row.get("file_path"), "duration_ms": row.get("duration_ms"),
        "voice_name": row.get("voice_name"), "checksum": row.get("checksum"), "status": row["status"],
        "event_order": event_order, "segment_index": unit.get("segment_index"),
    }


# ---------------------------------------------------------------------------
# Text Elements -- text is always taken verbatim from speech_assets, never invented (section 11).
# ---------------------------------------------------------------------------

_TEXT_ROLE_BY_SPEECH_MODE = {
    "EN_NATIVE": "TARGET_WORD",
    "KO_NARRATION": "CAPTION",
    "KO_PRONUNCIATION_GUIDE": "EXPLANATION",
}


def _text_role_for(speech_asset: dict) -> str:
    if speech_asset["speech_mode"] == "EN_PHONEME_DEMO":
        return "BLEND_SEQUENCE" if classify_phoneme_demo_type(speech_asset["source_text"]) == "BLENDED_SEQUENCE" else "PHONEME"
    return _TEXT_ROLE_BY_SPEECH_MODE.get(speech_asset["speech_mode"], "EXPLANATION")


# ---------------------------------------------------------------------------
# Scene compilation
# ---------------------------------------------------------------------------

def compile_scene(
    production_block: dict, speech_assets_by_id: dict[str, dict], units_by_source: dict[str, list[dict]],
    db_path: Path, plan_id: int,
) -> dict:
    content_block_id = production_block["content_block_id"]
    timeline = production_block.get("timeline") or []
    visual_spec = json.loads(production_block.get("visual_spec_json") or "{}")
    interaction_spec = json.loads(production_block.get("interaction_spec_json") or "{}")

    scene_role, unresolved_reason = classify_scene_role(production_block, speech_assets_by_id)
    visual_intent = classify_visual_intent(scene_role, visual_spec.get("primary_visual_type"))

    source_speech_asset_ids: list[str] = []
    audio_elements: list[dict] = []
    text_elements: list[dict] = []
    emphasis_targets: list[dict] = []
    element_counter = 0

    pause_events = [ev for ev in timeline if ev.get("type") == "PAUSE"]
    first_pause_order = min((ev["event_order"] for ev in pause_events), default=None)

    # 13-3A: whether THIS Scene has a genuine Mini Success answer-reveal structure is decided
    # purely from this Scene's own timeline evidence -- never from whether some OTHER Scene treats
    # the same underlying Speech Asset as its Mini Success answer (asset identity != scene
    # semantics; the same CAP asset is a real answer in one Scene and a plain RECAP replay in
    # another). is_mini_success_answer_asset() (12-2) stays asset-scoped and untouched -- it is
    # correctly used elsewhere (12-x review-priority/tone-approval policy) for exactly that
    # asset-level question, which is a different question from this one.
    has_answer_after_pause = first_pause_order is not None and any(
        ev.get("type") == "SPEECH" and ev["event_order"] > first_pause_order
        and (speech_assets_by_id.get(ev.get("speech_asset_id")) or {}).get("speech_mode") == "EN_NATIVE"
        for ev in timeline
    )
    is_mini_success_scene = (
        scene_role == "MINI_SUCCESS" and bool(interaction_spec.get("viewer_action"))
        and bool(pause_events) and has_answer_after_pause
    )

    for ev in timeline:
        if ev.get("type") == "SPEECH":
            sid = ev["speech_asset_id"]
            source_speech_asset_ids.append(sid)
            speech_asset = speech_assets_by_id.get(sid)
            units = units_by_source.get(sid, [])
            after_pause = first_pause_order is not None and ev["event_order"] > first_pause_order
            for unit in units:
                audio_elements.append(_audio_element_from_unit(
                    db_path, plan_id, sid, speech_asset["speech_mode"] if speech_asset else "UNKNOWN", unit, ev["event_order"],
                ))
            if speech_asset:
                element_counter += 1
                is_answer = is_mini_success_scene and after_pause and speech_asset["speech_mode"] == "EN_NATIVE"
                text_elements.append({
                    "element_id": f"{content_block_id}-TXT{element_counter}",
                    "role": "ANSWER" if is_answer else _text_role_for(speech_asset),
                    "text": speech_asset.get("display_text") or speech_asset.get("source_text"),
                    "source": sid,
                    "emphasis": is_answer,
                    "reveal_policy": "AFTER_PAUSE" if after_pause else "IMMEDIATE",
                    "event_order": ev["event_order"],
                })
        elif ev.get("type") == "VISUAL":
            element_counter += 1
            role = ev.get("visual_role") or "EXPLANATION"
            text_elements.append({
                "element_id": f"{content_block_id}-TXT{element_counter}",
                "role": "QUESTION" if is_mini_success_scene and role == "TARGET_WORD" else role,
                "text": ev.get("content"), "source": None,
                "emphasis": role == "TARGET_WORD",
                "reveal_policy": "IMMEDIATE",
                "event_order": ev["event_order"],
            })
            emphasis_targets.append({"role": role, "content": ev.get("content"), "event_order": ev["event_order"]})

    pause_requirements = [
        {
            "type": "PAUSE", "duration_ms": ev.get("duration_ms"),
            "purpose": "VIEWER_ATTEMPT" if interaction_spec.get("viewer_action") else "NARRATION_BREATH",
            "answer_reveal_allowed": False, "event_order": ev["event_order"],
        }
        for ev in pause_events
    ]

    answer_reveal_policy = None
    if is_mini_success_scene:
        answer_reveal_policy = {"reveal_after_pause": True, "reveal_before_pause_allowed": False}

    return {
        "scene_id": content_block_id, "production_plan_id": plan_id, "content_block_id": content_block_id,
        "source_speech_asset_ids": source_speech_asset_ids,
        "generation_unit_ids": [a["generation_unit_id"] for a in audio_elements],
        "scene_role": scene_role, "scene_role_unresolved_reason": unresolved_reason,
        "visual_intent": visual_intent, "content_intent": production_block.get("production_intent"),
        "viewer_action": interaction_spec.get("viewer_action"),
        "attempt_required": bool(interaction_spec.get("viewer_action")),
        "answer_reveal_policy": answer_reveal_policy,
        "text_elements": text_elements, "audio_elements": audio_elements,
        "pause_requirements": pause_requirements, "emphasis_targets": emphasis_targets,
    }


# ---------------------------------------------------------------------------
# Top-level Render Specification builder
# ---------------------------------------------------------------------------

def build_render_spec(
    db_path: Path, plan_id: int | None = None, *,
    primary_en_native_strategy: str = DEFAULT_EN_NATIVE_STRATEGY, fallback_en_native_strategy: str = "CONTEXTUAL_WORD",
    default_blending_strategy: str = DEFAULT_BLENDING_STRATEGY, max_segment_seconds: float = 12.0,
) -> dict:
    """13-1 section 1: the ONLY entry gate is compute_persistent_rendering_readiness -- never
    run_local readiness, never the current CLI mode. If the plan isn't ready, no spec is built and
    the exact blockers are returned instead."""
    plan_row = select_target_plan(db_path, plan_id=plan_id)
    if plan_row is None:
        return {"blocked": True, "reasons": ["No production_plans row found for the given plan_id."], "spec": None}

    speech_assets = _load_speech_assets(db_path, plan_row["id"])
    production_blocks = _load_production_blocks(db_path, plan_row["id"])

    readiness = compute_persistent_rendering_readiness(
        db_path, plan_row["id"], speech_assets, production_blocks,
        primary_en_native_strategy=primary_en_native_strategy, fallback_en_native_strategy=fallback_en_native_strategy,
        default_blending_strategy=default_blending_strategy, max_segment_seconds=max_segment_seconds,
    )
    if not readiness["ready"]:
        return {"blocked": True, "reasons": readiness["reasons"], "spec": None, "readiness": readiness}

    speech_assets_by_id = {a["speech_asset_id"]: a for a in speech_assets}
    units_by_source = _resolved_units_by_source(
        db_path, plan_row["id"], speech_assets, production_blocks,
        primary_en_native_strategy=primary_en_native_strategy, fallback_en_native_strategy=fallback_en_native_strategy,
        default_blending_strategy=default_blending_strategy, max_segment_seconds=max_segment_seconds,
    )

    scenes = []
    for pb in production_blocks:
        scenes.append(compile_scene(pb, speech_assets_by_id, units_by_source, db_path, plan_row["id"]))

    spec = {
        "spec_version": SPEC_VERSION,
        "production_plan_id": plan_row["id"],
        "rendering_readiness": {"ready": True, "source": "persistent"},
        "video": {
            "format": plan_row.get("final_format"),
            "orientation": None, "width": None, "height": None, "fps": None,
            "resolution_policy": "UNRESOLVED_NON_BLOCKING",
        },
        "scenes": scenes,
    }
    return {"blocked": False, "reasons": [], "spec": spec, "readiness": readiness}


# ---------------------------------------------------------------------------
# Validation (section 19, 17 items) -- re-verified against the DB, never trusted just because the
# code produced it (section 29: "코드에서 만들었다는 이유만으로 PASS 처리하지 않는다").
# ---------------------------------------------------------------------------

_EXPERIMENTAL_MARKERS = ("LOWERCASE_WORD", "MINIMAL_CONTEXT_WORD", "CONTEXT_RESTRICTED")


def validate_render_spec(
    db_path: Path, plan_id: int, spec: dict, production_blocks: list[dict], speech_assets: list[dict], *,
    primary_en_native_strategy: str = DEFAULT_EN_NATIVE_STRATEGY, fallback_en_native_strategy: str = "CONTEXTUAL_WORD",
    default_blending_strategy: str = DEFAULT_BLENDING_STRATEGY, max_segment_seconds: float = 12.0,
) -> dict:
    checks: dict[str, bool] = {}
    unresolved_critical: list[str] = []
    unresolved_non_critical: list[str] = []

    scenes = spec.get("scenes") or []
    speech_assets_by_id = {a["speech_asset_id"]: a for a in speech_assets}
    block_ids = {pb["content_block_id"] for pb in production_blocks}

    # 1. canonical rendering readiness = YES
    checks["canonical_readiness_yes"] = bool(spec.get("rendering_readiness", {}).get("ready"))

    # 2. every scene has content_block lineage / 16. no orphan scene
    checks["scene_block_lineage_complete"] = all(
        s.get("content_block_id") in block_ids and s.get("scene_id") for s in scenes
    )
    checks["no_orphan_scenes"] = {s["content_block_id"] for s in scenes} <= block_ids

    # 3. every audio reference points to a real AVAILABLE/REUSED asset
    all_audio = [a for s in scenes for a in s.get("audio_elements") or []]
    checks["audio_references_materialized"] = all(a.get("status") in {"AVAILABLE", "REUSED"} for a in all_audio)

    # 4. every generation_unit file_path exists on disk
    checks["audio_files_exist"] = all(a.get("file_path") and Path(a["file_path"]).exists() for a in all_audio)

    # 5. duration_ms > 0
    checks["audio_durations_positive"] = all((a.get("duration_ms") or 0) > 0 for a in all_audio)

    # 6. segmented narration ordering complete (segment_index 0..N-1 present exactly once, in order)
    segment_order_ok = True
    units_by_source = _resolved_units_by_source(
        db_path, plan_id, speech_assets, production_blocks,
        primary_en_native_strategy=primary_en_native_strategy, fallback_en_native_strategy=fallback_en_native_strategy,
        default_blending_strategy=default_blending_strategy, max_segment_seconds=max_segment_seconds,
    )
    for sid, units in units_by_source.items():
        if len(units) <= 1:
            continue
        indices = [u["segment_index"] for u in units]
        if indices != list(range(len(units))) or len({u["segment_count"] for u in units}) != 1:
            segment_order_ok = False
    checks["segment_ordering_complete"] = segment_order_ok

    # 7. source_speech_asset lineage complete
    checks["source_speech_asset_lineage_complete"] = all(
        sid in speech_assets_by_id for s in scenes for sid in s.get("source_speech_asset_ids") or []
    )

    # 8. active strategy selection matches the Full Generation Plan (recomputed fresh, not trusted)
    fresh_units_by_source = units_by_source  # already recomputed above from live DB state
    active_selection_ok = True
    for s in scenes:
        for sid in s.get("source_speech_asset_ids") or []:
            expected_ids = {u["generation_unit_id"] for u in fresh_units_by_source.get(sid, [])}
            actual_ids = {a["generation_unit_id"] for a in (s.get("audio_elements") or []) if a["source_speech_asset_id"] == sid}
            if actual_ids and not actual_ids <= expected_ids:
                active_selection_ok = False
    checks["active_strategy_selection_matches_plan"] = active_selection_ok

    # 9. no failed/rejected variant used
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
    checks["no_failed_or_rejected_variant_used"] = not failed_used

    # 10. no experimental variant auto-selected
    checks["no_experimental_variant_used"] = not any(
        marker in (a.get("generation_unit_id") or "") for a in all_audio for marker in _EXPERIMENTAL_MARKERS
    )

    # 11. PAUSE 3000ms preserved (re-read fresh from DB, not from the spec's own copy)
    fresh_blocks = _load_production_blocks(db_path, plan_id)
    fresh_pause_by_block = {
        pb["content_block_id"]: [ev for ev in (pb.get("timeline") or []) if ev.get("type") == "PAUSE"]
        for pb in fresh_blocks
    }
    pause_ok = True
    for s in scenes:
        fresh_pauses = fresh_pause_by_block.get(s["content_block_id"], [])
        spec_pauses = s.get("pause_requirements") or []
        if len(fresh_pauses) != len(spec_pauses):
            pause_ok = False
            continue
        for fresh_ev, spec_pause in zip(fresh_pauses, spec_pauses):
            if fresh_ev.get("duration_ms") != spec_pause.get("duration_ms"):
                pause_ok = False
    checks["pause_preserved"] = pause_ok

    # 12. viewer_action preserved
    fresh_interaction_by_block = {pb["content_block_id"]: json.loads(pb.get("interaction_spec_json") or "{}") for pb in fresh_blocks}
    checks["viewer_action_preserved"] = all(
        s.get("viewer_action") == fresh_interaction_by_block.get(s["content_block_id"], {}).get("viewer_action") for s in scenes
    )

    # 13. answer reveal constraint preserved
    checks["answer_reveal_constraint_preserved"] = all(
        (s.get("answer_reveal_policy") or {}).get("reveal_before_pause_allowed") is False
        for s in scenes if s.get("scene_role") == "MINI_SUCCESS"
    )

    # 14. Mini Success lineage preserved
    mini_success_scenes = [s for s in scenes if s.get("scene_role") == "MINI_SUCCESS"]
    checks["mini_success_lineage_preserved"] = all(
        any(t.get("role") == "ANSWER" for t in s.get("text_elements") or []) for s in mini_success_scenes
    ) if mini_success_scenes else True

    # 13-3A: answer_reveal_policy is scoped to a Scene's own evidence, never inherited merely
    # because a Scene reuses an asset that is the Mini Success answer somewhere else (e.g. a RECAP
    # scene replaying the same CAP asset CB06 uses as its answer). A Scene has the policy iff it
    # actually has scene_role MINI_SUCCESS + a real viewer_action + a real PAUSE + an ANSWER text
    # element -- and never otherwise.
    policy_scene_scoped_ok = True
    for s in scenes:
        has_policy = s.get("answer_reveal_policy") is not None
        fresh_interaction = fresh_interaction_by_block.get(s["content_block_id"], {})
        fresh_pauses = fresh_pause_by_block.get(s["content_block_id"], [])
        has_evidence = (
            s.get("scene_role") == "MINI_SUCCESS" and bool(fresh_interaction.get("viewer_action"))
            and bool(fresh_pauses) and any(t.get("role") == "ANSWER" for t in s.get("text_elements") or [])
        )
        if has_policy != has_evidence:
            policy_scene_scoped_ok = False
    checks["answer_reveal_policy_scene_scoped"] = policy_scene_scoped_ok

    # 15. no Production Block missing
    checks["all_production_blocks_covered"] = {s["content_block_id"] for s in scenes} == block_ids

    # 17. no unintended cross-scene duplicate use of the same Generation Unit.
    # The same Generation Unit legitimately appears in multiple scenes for real pedagogical
    # reasons (a RECAP scene replays earlier answers verbatim; a shared phoneme like /ae/ is
    # reused across several word-demo scenes) -- confirmed against live Plan 7 data, where
    # SP003/SP007/SP009/SP011/SP016/SP029/SP039::CONTEXTUAL_WORD all legitimately recur. What
    # would actually indicate a bug is a cache/resolution COLLISION: the same generation_unit_id
    # tracing back to two DIFFERENT logical source_speech_asset_ids (i.e. two unrelated words
    # accidentally sharing one cached file) -- that is what this check actually verifies.
    gid_to_source: dict[str, str] = {}
    collision_free = True
    for s in scenes:
        for a in s.get("audio_elements") or []:
            gid, sid = a["generation_unit_id"], a["source_speech_asset_id"]
            if gid in gid_to_source and gid_to_source[gid] != sid:
                collision_free = False
            gid_to_source.setdefault(gid, sid)
    checks["no_unintended_cross_scene_duplicate_units"] = collision_free

    # width/height/fps are explicitly non-critical (section 25) -- always UNRESOLVED_NON_BLOCKING here
    if spec.get("video", {}).get("resolution_policy") == "UNRESOLVED_NON_BLOCKING":
        unresolved_non_critical.append("video.width/height/fps/orientation")

    for name, passed in checks.items():
        if not passed:
            unresolved_critical.append(name)

    return {"checks": checks, "unresolved_critical": unresolved_critical, "unresolved_non_critical": unresolved_non_critical}


# ---------------------------------------------------------------------------
# 13-1 Integrity Check (section 20, 13 items) -- entirely separate dict from the 12-series 67
# checks, none of those names touched.
# ---------------------------------------------------------------------------

_RENDERER_SPECIFIC_MARKERS = ("remotion", "react", "absolutefill", "sequence", "css_class", "html_tag", "ffmpeg_filter", "canvas_context")
# Word-boundary matching, not bare substring: this project's own semantic vocabulary legitimately
# contains "sequence" inside compound identifiers (PHONEME_SEQUENCE/BLEND_SEQUENCE) -- underscore
# is a \w character, so \bsequence\b correctly does NOT match inside "phoneme_sequence" while still
# catching a genuinely standalone "Sequence" (Remotion's own component name) leaking into the spec.
_RENDERER_SPECIFIC_MARKER_RE = re.compile(r"\b(?:" + "|".join(_RENDERER_SPECIFIC_MARKERS) + r")\b")


def run_render_spec_integrity_check(readiness: dict, spec: dict | None, validation: dict) -> dict:
    v = validation["checks"]
    checks = {
        "renderer_entry_gate_safe": bool(readiness.get("ready")),
        "render_spec_block_lineage_safe": v.get("scene_block_lineage_complete", False) and v.get("no_orphan_scenes", False),
        "render_spec_audio_lineage_safe": v.get("audio_references_materialized", False) and v.get("audio_files_exist", False) and v.get("audio_durations_positive", False),
        "render_spec_generation_unit_safe": v.get("source_speech_asset_lineage_complete", False),
        "render_spec_active_asset_selection_safe": v.get("active_strategy_selection_matches_plan", False),
        "render_spec_segment_order_safe": v.get("segment_ordering_complete", False),
        "render_spec_pause_preserved": v.get("pause_preserved", False),
        "render_spec_viewer_action_preserved": v.get("viewer_action_preserved", False),
        "render_spec_answer_reveal_safe": v.get("answer_reveal_constraint_preserved", False),
        "render_spec_mini_success_safe": v.get("mini_success_lineage_preserved", False),
        "render_spec_no_experimental_variant": v.get("no_experimental_variant_used", False) and v.get("no_failed_or_rejected_variant_used", False),
        "render_spec_answer_reveal_scene_scope_safe": v.get("answer_reveal_policy_scene_scoped", False),
    }
    spec_text = json.dumps(spec or {}, ensure_ascii=False).lower()
    checks["render_spec_renderer_neutral"] = _RENDERER_SPECIFIC_MARKER_RE.search(spec_text) is None
    checks["render_spec_complete"] = bool(spec) and not validation["unresolved_critical"] and all(checks.values())
    return checks


def ready_for_timeline_compilation_gate(readiness: dict, spec: dict | None, validation: dict, integrity_checks: dict) -> bool:
    return bool(
        readiness.get("ready") and spec is not None and not validation["unresolved_critical"]
        and all(v == "pass" or v is True for v in integrity_checks.values())
    )


# ---------------------------------------------------------------------------
# Persistence + file output
# ---------------------------------------------------------------------------

def persist_render_spec(db_path: Path, plan_id: int, spec: dict, validation: dict) -> int:
    with connect(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO render_specs (production_plan_id, spec_version, spec_json, validation_json) VALUES (?, ?, ?, ?)",
            (plan_id, SPEC_VERSION, json.dumps(spec, ensure_ascii=False), json.dumps(validation, ensure_ascii=False)),
        )
        return cur.lastrowid


def write_render_spec_file(assets_dir: Path, plan_id: int, spec: dict) -> Path:
    render_dir = assets_dir / "generated" / f"plan_{plan_id}" / "render"
    render_dir.mkdir(parents=True, exist_ok=True)
    path = render_dir / "render_spec.json"
    path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Orchestration + report
# ---------------------------------------------------------------------------

def run_render_spec(
    db_path: Path, assets_dir: Path, reports_dir: Path, *, plan_id: int | None = None,
    primary_en_native_strategy: str = DEFAULT_EN_NATIVE_STRATEGY, fallback_en_native_strategy: str = "CONTEXTUAL_WORD",
    default_blending_strategy: str = DEFAULT_BLENDING_STRATEGY, max_segment_seconds: float = 12.0,
) -> dict:
    result = build_render_spec(
        db_path, plan_id=plan_id, primary_en_native_strategy=primary_en_native_strategy,
        fallback_en_native_strategy=fallback_en_native_strategy, default_blending_strategy=default_blending_strategy,
        max_segment_seconds=max_segment_seconds,
    )
    plan_row = select_target_plan(db_path, plan_id=plan_id)
    report_path = _build_render_spec_report(db_path, reports_dir, plan_row, result)
    if result["blocked"]:
        return {**result, "report_path": report_path, "json_path": None, "ready_for_timeline_compilation": False}

    speech_assets = _load_speech_assets(db_path, plan_row["id"])
    production_blocks = _load_production_blocks(db_path, plan_row["id"])
    validation = validate_render_spec(
        db_path, plan_row["id"], result["spec"], production_blocks, speech_assets,
        primary_en_native_strategy=primary_en_native_strategy, fallback_en_native_strategy=fallback_en_native_strategy,
        default_blending_strategy=default_blending_strategy, max_segment_seconds=max_segment_seconds,
    )
    integrity_checks = run_render_spec_integrity_check(result["readiness"], result["spec"], validation)
    ready = ready_for_timeline_compilation_gate(result["readiness"], result["spec"], validation, integrity_checks)

    persist_render_spec(db_path, plan_row["id"], result["spec"], validation)
    json_path = write_render_spec_file(assets_dir, plan_row["id"], result["spec"])
    report_path = _build_render_spec_report(db_path, reports_dir, plan_row, result, validation=validation, integrity_checks=integrity_checks, ready=ready, json_path=json_path)

    return {
        **result, "validation": validation, "integrity_checks": integrity_checks,
        "ready_for_timeline_compilation": ready, "json_path": json_path, "report_path": report_path,
    }


def _build_render_spec_report(
    db_path: Path, reports_dir: Path, plan_row: dict | None, result: dict, *,
    validation: dict | None = None, integrity_checks: dict | None = None, ready: bool = False, json_path: Path | None = None,
) -> Path:
    lines: list[str] = ["# Render Specification Report", ""]
    lines.append(f"생성일: {datetime.utcnow().date().isoformat()}")
    lines.append(f"Source Plan: {plan_row['id'] if plan_row else 'N/A'}")
    lines.append("")

    lines.append("## Renderer Entry Gate")
    lines.append("")
    lines.append("YES" if not result["blocked"] else "NO")
    if result["blocked"]:
        for reason in result["reasons"]:
            lines.append(f"- {reason}")
    lines.append("")

    if not result["blocked"]:
        spec = result["spec"]
        scenes = spec["scenes"]
        all_audio = [a for s in scenes for a in s.get("audio_elements") or []]
        segmented = sum(1 for s in scenes for t in s.get("text_elements") or [] if t.get("role") == "CAPTION")
        mini_success_scenes = [s for s in scenes if s["scene_role"] == "MINI_SUCCESS"]
        pause_count = sum(len(s.get("pause_requirements") or []) for s in scenes)
        pause_total_ms = sum(p.get("duration_ms") or 0 for s in scenes for p in s.get("pause_requirements") or [])

        lines.append("## Scene Count")
        lines.append("")
        lines.append(str(len(scenes)))
        lines.append("")

        lines.append("## Block Coverage")
        lines.append("")
        lines.append(f"{len(scenes)} scenes / {len(scenes)} production blocks")
        lines.append("")

        lines.append("## Audio Asset Coverage")
        lines.append("")
        lines.append(f"{len(all_audio)} audio element references")
        lines.append("")

        lines.append("## Generation Unit Coverage")
        lines.append("")
        lines.append(f"{len({a['generation_unit_id'] for a in all_audio})} distinct Generation Units referenced")
        lines.append("")

        lines.append("## Pause Preservation")
        lines.append("")
        lines.append(f"{pause_count} PAUSE(s), total {pause_total_ms}ms")
        lines.append("")

        lines.append("## Mini Success / Answer Reveal")
        lines.append("")
        lines.append(f"{len(mini_success_scenes)} Mini Success scene(s): {[s['scene_id'] for s in mini_success_scenes]}")
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

        lines.append("## Ready for Timeline Compilation")
        lines.append("")
        lines.append("YES" if ready else "NO")
        lines.append("")

        if json_path:
            lines.append(f"JSON: {json_path}")
            lines.append("")

    reports_dir.mkdir(parents=True, exist_ok=True)
    out_path = reports_dir / f"render_spec_{datetime.utcnow().date().isoformat()}.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path
