"""13-2: compiles a 13-1-validated Render Specification into a deterministic millisecond timeline.
Never invents timing -- every start_ms/end_ms is derived from audio_elements[].duration_ms,
pause_requirements[].duration_ms, and the event_order/segment_index lineage 13-1 already preserves
(patched in 13-2 section 0 specifically so this module never has to guess where a PAUSE or VISUAL
marker falls relative to audio events). No Gemini TTS, YouTube, or video-generation API calls.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from research.asset_generator import _load_production_blocks, _load_speech_assets, select_target_plan
from research.db import connect
from research.render_spec import (
    SPEC_VERSION,
    _RENDERER_SPECIFIC_MARKER_RE,
    ready_for_timeline_compilation_gate,
    run_render_spec_integrity_check,
    validate_render_spec,
)

TIMELINE_VERSION = "13.2"
TIMELINE_EVENT_TYPES = {"AUDIO", "PAUSE", "ANSWER_REVEAL_BARRIER", "VIEWER_ACTION", "VISUAL_CUE"}
_TIMED_EVENT_TYPES = {"AUDIO", "PAUSE"}  # advance the cursor; the rest are zero-duration markers


# ---------------------------------------------------------------------------
# Input Gate (section 3) -- never guesses between the DB row and the JSON file; a mismatch is a
# hard FAIL, not a coin flip. Reuses 13-1's own validate_render_spec/run_render_spec_integrity_check/
# ready_for_timeline_compilation_gate rather than inventing a second judgment of readiness.
# ---------------------------------------------------------------------------

def validate_timeline_entry_gate(db_path: Path, assets_dir: Path, plan_id: int | None = None) -> dict:
    plan_row = select_target_plan(db_path, plan_id=plan_id)
    if plan_row is None:
        return {"pass": False, "reason": "No production_plans row found.", "spec": None, "plan_id": None}
    pid = plan_row["id"]

    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT id, spec_json, validation_json FROM render_specs WHERE production_plan_id = ? ORDER BY id DESC LIMIT 1",
            (pid,),
        ).fetchone()
    if row is None:
        return {"pass": False, "reason": "No render_specs row found for this plan -- run `render-spec` first.", "spec": None, "plan_id": pid}

    db_spec = json.loads(row["spec_json"])
    json_path = assets_dir / "generated" / f"plan_{pid}" / "render" / "render_spec.json"
    if not json_path.exists():
        return {"pass": False, "reason": f"render_spec.json not found at {json_path}.", "spec": None, "plan_id": pid}
    file_spec = json.loads(json_path.read_text(encoding="utf-8"))

    if db_spec != file_spec:
        return {
            "pass": False, "spec": None, "plan_id": pid,
            "reason": "render_specs DB row and render_spec.json file content differ -- refusing to guess which is authoritative (section 3).",
        }

    spec = db_spec
    if spec.get("spec_version") != SPEC_VERSION:
        return {"pass": False, "reason": f"spec_version {spec.get('spec_version')!r} != {SPEC_VERSION!r}", "spec": spec, "plan_id": pid}
    if not spec.get("rendering_readiness", {}).get("ready"):
        return {"pass": False, "reason": "render_spec.rendering_readiness.ready is not true.", "spec": spec, "plan_id": pid}
    if not spec.get("scenes"):
        return {"pass": False, "reason": "render_spec has no scenes.", "spec": spec, "plan_id": pid}

    stored_validation = json.loads(row["validation_json"] or "{}")
    if stored_validation.get("unresolved_critical"):
        return {"pass": False, "spec": spec, "plan_id": pid, "reason": f"13-1 validation has unresolved critical fields: {stored_validation['unresolved_critical']}"}

    # Re-verify fresh against current DB state -- never trust a stale stored boolean.
    production_blocks = _load_production_blocks(db_path, pid)
    speech_assets = _load_speech_assets(db_path, pid)
    fresh_validation = validate_render_spec(db_path, pid, spec, production_blocks, speech_assets)
    fresh_integrity_checks = run_render_spec_integrity_check({"ready": True}, spec, fresh_validation)
    ready_for_tc = ready_for_timeline_compilation_gate({"ready": True}, spec, fresh_validation, fresh_integrity_checks)
    if not ready_for_tc:
        return {"pass": False, "spec": spec, "plan_id": pid, "reason": "Ready for Timeline Compilation is not YES when re-verified against current DB state."}

    return {"pass": True, "reason": None, "spec": spec, "plan_id": pid, "render_spec_row_id": row["id"]}


# ---------------------------------------------------------------------------
# Event compilation (sections 6-9)
# ---------------------------------------------------------------------------

def compile_scene_events(scene: dict) -> list[dict]:
    """Merges audio_elements/pause_requirements/emphasis_targets by (event_order, segment_index)
    -- the exact original production_blocks timeline order, structurally preserved by the 13-2
    section 0 patch to render_spec.py, never re-inferred by string-joining through text_elements or
    by any other guess. Returns scene-LOCAL events (cursor starts at 0); compile_global_timeline
    shifts these to absolute positions."""
    candidates: list[tuple[tuple[int, int], str, dict]] = []
    for a in scene.get("audio_elements") or []:
        key = (a.get("event_order") or 0, a.get("segment_index") or 0)
        candidates.append((key, "AUDIO", a))
    for p in scene.get("pause_requirements") or []:
        key = (p.get("event_order") or 0, 0)
        candidates.append((key, "PAUSE", p))
    for v in scene.get("emphasis_targets") or []:
        key = (v.get("event_order") or 0, 0)
        candidates.append((key, "VISUAL_CUE", v))
    candidates.sort(key=lambda item: item[0])

    events: list[dict] = []
    cursor_ms = 0
    event_counter = 0
    last_pause_end_ms: int | None = None
    for _, kind, source in candidates:
        event_counter += 1
        event_id = f"{scene['scene_id']}-EV{event_counter}"
        if kind == "AUDIO":
            duration = source.get("duration_ms") or 0
            events.append({
                "event_id": event_id, "event_type": "AUDIO", "scene_id": scene["scene_id"],
                "content_block_id": scene["content_block_id"], "asset_id": source.get("asset_id"),
                "source_speech_asset_id": source.get("source_speech_asset_id"),
                "generation_unit_id": source.get("generation_unit_id"), "speech_mode": source.get("speech_mode"),
                "file_path": source.get("file_path"), "start_ms": cursor_ms, "end_ms": cursor_ms + duration,
                "duration_ms": duration,
            })
            cursor_ms += duration
        elif kind == "PAUSE":
            duration = source.get("duration_ms") or 0
            events.append({
                "event_id": event_id, "event_type": "PAUSE", "scene_id": scene["scene_id"],
                "content_block_id": scene["content_block_id"], "start_ms": cursor_ms, "end_ms": cursor_ms + duration,
                "duration_ms": duration, "answer_reveal_allowed": source.get("answer_reveal_allowed", False),
            })
            cursor_ms += duration
            last_pause_end_ms = cursor_ms
        else:  # VISUAL_CUE -- zero-duration marker, does not advance the cursor
            events.append({
                "event_id": event_id, "event_type": "VISUAL_CUE", "scene_id": scene["scene_id"],
                "content_block_id": scene["content_block_id"], "role": source.get("role"),
                "content": source.get("content"), "at_ms": cursor_ms,
            })

    answer_reveal_policy = scene.get("answer_reveal_policy")
    if answer_reveal_policy and last_pause_end_ms is not None:
        event_counter += 1
        events.append({
            "event_id": f"{scene['scene_id']}-EV{event_counter}", "event_type": "ANSWER_REVEAL_BARRIER",
            "scene_id": scene["scene_id"], "content_block_id": scene["content_block_id"],
            "reveal_not_before_ms": last_pause_end_ms,
        })

    if scene.get("viewer_action") and last_pause_end_ms is not None:
        first_pause = next((e for e in events if e["event_type"] == "PAUSE"), None)
        event_counter += 1
        events.append({
            "event_id": f"{scene['scene_id']}-EV{event_counter}", "event_type": "VIEWER_ACTION",
            "scene_id": scene["scene_id"], "content_block_id": scene["content_block_id"],
            "viewer_action": scene["viewer_action"],
            "active_before_ms": first_pause["start_ms"] if first_pause else None,
            "answer_reveal_not_before_ms": last_pause_end_ms,
        })

    return events


def compile_scene_timeline(scene: dict, local_events: list[dict]) -> dict:
    timed = [e for e in local_events if e["event_type"] in _TIMED_EVENT_TYPES]
    duration_ms = max((e["end_ms"] for e in timed), default=0)
    return {
        "scene_id": scene["scene_id"], "content_block_id": scene["content_block_id"],
        "scene_role": scene["scene_role"], "visual_intent": scene["visual_intent"],
        "duration_ms": duration_ms, "events": local_events,
    }


_SHIFTABLE_TIME_FIELDS = ("start_ms", "end_ms", "reveal_not_before_ms", "active_before_ms", "answer_reveal_not_before_ms", "at_ms")


def compile_global_timeline(scene_timelines: list[dict]) -> dict:
    """Section 10: chains scenes sequentially with zero gap (scene[n].end_ms ==
    scene[n+1].start_ms by construction) and shifts every nested event's time fields by the
    running offset. Starts at 0ms; only ever adds non-negative durations, so a negative timestamp
    is structurally impossible."""
    running_cursor = 0
    placed_scenes = []
    for scene in scene_timelines:
        start_ms = running_cursor
        end_ms = start_ms + scene["duration_ms"]
        shifted_events = []
        for ev in scene["events"]:
            shifted = dict(ev)
            for field in _SHIFTABLE_TIME_FIELDS:
                if shifted.get(field) is not None:
                    shifted[field] = shifted[field] + start_ms
            shifted_events.append(shifted)
        placed_scenes.append({**scene, "start_ms": start_ms, "end_ms": end_ms, "events": shifted_events})
        running_cursor = end_ms

    video_duration_ms = placed_scenes[-1]["end_ms"] if placed_scenes else 0
    return {"scenes": placed_scenes, "video_duration_ms": video_duration_ms}


def build_timeline(spec: dict) -> dict:
    scene_timelines = []
    for scene in spec["scenes"]:
        local_events = compile_scene_events(scene)
        scene_timelines.append(compile_scene_timeline(scene, local_events))
    global_timeline = compile_global_timeline(scene_timelines)

    return {
        "timeline_version": TIMELINE_VERSION,
        "production_plan_id": spec["production_plan_id"],
        "render_spec_version": spec["spec_version"],
        "timebase": "milliseconds",
        "video": {
            "start_ms": 0, "end_ms": global_timeline["video_duration_ms"],
            "duration_ms": global_timeline["video_duration_ms"], "fps": None, "frame_count": None,
        },
        "scenes": global_timeline["scenes"],
        "constraints": {"renderer_neutral": True},
    }


# ---------------------------------------------------------------------------
# Timeline Validation (section 18)
# ---------------------------------------------------------------------------

def validate_timeline(spec: dict, timeline: dict) -> dict:
    checks: dict[str, bool] = {}
    scenes = timeline["scenes"]
    all_events = [e for s in scenes for e in s["events"]]

    # Structural
    checks["scene_count_matches_spec"] = len(scenes) == len(spec["scenes"])
    scene_ids = [s["scene_id"] for s in scenes]
    checks["scene_ids_unique"] = len(scene_ids) == len(set(scene_ids))
    event_ids = [e["event_id"] for e in all_events]
    checks["event_ids_unique"] = len(event_ids) == len(set(event_ids))
    checks["durations_non_negative"] = all((s.get("duration_ms") or 0) >= 0 for s in scenes) and all(
        (e.get("duration_ms") or 0) >= 0 for e in all_events if "duration_ms" in e
    )
    checks["end_after_or_equal_start"] = all(
        e["end_ms"] >= e["start_ms"] for e in all_events if e["event_type"] in _TIMED_EVENT_TYPES
    )
    overlap_ok = True
    for s in scenes:
        timed = sorted((e for e in s["events"] if e["event_type"] in _TIMED_EVENT_TYPES), key=lambda e: e["start_ms"])
        for prev, cur in zip(timed, timed[1:]):
            if cur["start_ms"] < prev["end_ms"]:
                overlap_ok = False
    checks["no_unintended_timed_event_overlap"] = overlap_ok
    scene_overlap_ok = all(scenes[i]["end_ms"] <= scenes[i + 1]["start_ms"] for i in range(len(scenes) - 1))
    checks["no_scene_overlap"] = scene_overlap_ok
    checks["no_negative_timestamps"] = all(
        (e.get("start_ms") or 0) >= 0 and (e.get("end_ms") or 0) >= 0 for e in all_events
    ) and all(s["start_ms"] >= 0 and s["end_ms"] >= 0 for s in scenes)

    # Audio lineage + Duration
    spec_audio_by_asset: dict[str, dict] = {a["asset_id"]: a for s in spec["scenes"] for a in s.get("audio_elements") or []}
    audio_events = [e for e in all_events if e["event_type"] == "AUDIO"]
    checks["audio_lineage_matches_spec"] = all(e["asset_id"] in spec_audio_by_asset for e in audio_events)
    checks["audio_duration_matches_spec"] = all(
        e["duration_ms"] == (spec_audio_by_asset.get(e["asset_id"]) or {}).get("duration_ms") for e in audio_events
    )

    # Segmentation
    segment_order_ok = True
    by_source: dict[str, list[dict]] = {}
    for e in audio_events:
        by_source.setdefault(e["source_speech_asset_id"], []).append(e)
    for sid, evs in by_source.items():
        ordered = sorted(evs, key=lambda e: e["start_ms"])
        if evs != ordered:
            segment_order_ok = False
    checks["segment_order_preserved"] = segment_order_ok

    # PAUSE
    pause_events = [e for e in all_events if e["event_type"] == "PAUSE"]
    checks["pause_durations_exact"] = all(
        e["end_ms"] - e["start_ms"] == e["duration_ms"] for e in pause_events
    )

    # Answer Reveal (section 12 invariant, exactly): for every scene with a reveal barrier, no
    # EN_NATIVE audio event starts before it (the answer must not be audible early), and at least
    # one EN_NATIVE audio event actually plays at/after it (the barrier must gate a real answer,
    # not float disconnected from any audio).
    answer_reveal_ok = True
    for scene in scenes:
        barriers = [e for e in scene["events"] if e["event_type"] == "ANSWER_REVEAL_BARRIER"]
        if not barriers:
            continue
        reveal_not_before = barriers[0]["reveal_not_before_ms"]
        en_native_audio = [e for e in scene["events"] if e["event_type"] == "AUDIO" and e.get("speech_mode") == "EN_NATIVE"]
        if any(e["start_ms"] < reveal_not_before for e in en_native_audio):
            answer_reveal_ok = False
        if not any(e["start_ms"] >= reveal_not_before for e in en_native_audio):
            answer_reveal_ok = False
    checks["answer_not_revealed_before_pause"] = answer_reveal_ok

    # Viewer Action
    viewer_action_ok = True
    spec_by_scene = {s["scene_id"]: s for s in spec["scenes"]}
    for scene in scenes:
        spec_scene = spec_by_scene.get(scene["scene_id"], {})
        va_events = [e for e in scene["events"] if e["event_type"] == "VIEWER_ACTION"]
        if spec_scene.get("viewer_action") and not va_events:
            viewer_action_ok = False
        for e in va_events:
            if e["viewer_action"] != spec_scene.get("viewer_action"):
                viewer_action_ok = False
    checks["viewer_action_text_preserved"] = viewer_action_ok

    # Global Duration
    checks["global_duration_matches_last_scene"] = (
        timeline["video"]["duration_ms"] == (scenes[-1]["end_ms"] if scenes else 0)
    )

    unresolved_critical = [name for name, passed in checks.items() if not passed]
    return {"checks": checks, "unresolved_critical": unresolved_critical, "unresolved_non_critical": ["video.fps/frame_count"]}


# ---------------------------------------------------------------------------
# Integrity Check (section 24, 16 items) -- entirely separate dict from 13-1's 13 checks.
# ---------------------------------------------------------------------------

def run_timeline_integrity_check(entry_gate: dict, spec: dict | None, timeline: dict | None, validation: dict) -> dict:
    v = validation["checks"]
    checks = {
        "timeline_entry_gate_safe": bool(entry_gate.get("pass")),
        "timeline_scene_lineage_safe": v.get("scene_count_matches_spec", False) and v.get("scene_ids_unique", False),
        "timeline_audio_lineage_safe": v.get("audio_lineage_matches_spec", False),
        "timeline_audio_duration_preserved": v.get("audio_duration_matches_spec", False),
        "timeline_generation_unit_order_safe": v.get("segment_order_preserved", False),
        "timeline_segment_order_safe": v.get("segment_order_preserved", False),
        "timeline_pause_preserved": v.get("pause_durations_exact", False),
        "timeline_viewer_action_preserved": v.get("viewer_action_text_preserved", False),
        "timeline_answer_reveal_barrier_safe": v.get("answer_not_revealed_before_pause", False),
        "timeline_no_unintended_overlap": v.get("no_unintended_timed_event_overlap", False) and v.get("no_scene_overlap", False),
        "timeline_monotonic_safe": v.get("end_after_or_equal_start", False) and v.get("no_negative_timestamps", False),
        "timeline_scene_duration_safe": v.get("durations_non_negative", False),
        "timeline_global_duration_safe": v.get("global_duration_matches_last_scene", False),
    }
    if spec is not None and timeline is not None:
        # section 17: compiling the same spec twice must yield the same timeline -- recompile
        # fresh (no cached/global state) and compare, excluding nothing but this function's own
        # non-existence of a created_at field (timeline_json itself carries none).
        recompiled = build_timeline(spec)
        checks["timeline_deterministic"] = _semantic_equal(timeline, recompiled)
        text = json.dumps(timeline, ensure_ascii=False).lower()
        checks["timeline_renderer_neutral"] = _RENDERER_SPECIFIC_MARKER_RE.search(text) is None
    else:
        checks["timeline_deterministic"] = False
        checks["timeline_renderer_neutral"] = False
    checks["timeline_complete"] = bool(timeline) and not validation["unresolved_critical"] and all(checks.values())
    return checks


def _semantic_equal(a: dict, b: dict) -> bool:
    return json.dumps(a, sort_keys=True, ensure_ascii=False) == json.dumps(b, sort_keys=True, ensure_ascii=False)


def ready_for_scene_layout_gate(entry_gate: dict, validation: dict, integrity_checks: dict) -> bool:
    return bool(
        entry_gate.get("pass") and not validation["unresolved_critical"]
        and all(v is True for v in integrity_checks.values())
    )


# ---------------------------------------------------------------------------
# Persistence + file output
# ---------------------------------------------------------------------------

def persist_timeline(db_path: Path, plan_id: int, render_spec_row_id: int | None, timeline: dict, validation: dict) -> int:
    with connect(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO render_timelines (production_plan_id, render_spec_id, timeline_version, timeline_json, validation_json) "
            "VALUES (?, ?, ?, ?, ?)",
            (plan_id, render_spec_row_id, TIMELINE_VERSION, json.dumps(timeline, ensure_ascii=False), json.dumps(validation, ensure_ascii=False)),
        )
        return cur.lastrowid


def write_timeline_file(assets_dir: Path, plan_id: int, timeline: dict) -> Path:
    render_dir = assets_dir / "generated" / f"plan_{plan_id}" / "render"
    render_dir.mkdir(parents=True, exist_ok=True)
    path = render_dir / "timeline.json"
    path.write_text(json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Orchestration + report
# ---------------------------------------------------------------------------

def run_timeline_compiler(db_path: Path, assets_dir: Path, reports_dir: Path, *, plan_id: int | None = None) -> dict:
    entry_gate = validate_timeline_entry_gate(db_path, assets_dir, plan_id=plan_id)
    if not entry_gate["pass"]:
        report_path = _build_timeline_report(reports_dir, entry_gate, None, None, None, None)
        return {**entry_gate, "timeline": None, "json_path": None, "report_path": report_path, "ready_for_scene_layout": False}

    spec = entry_gate["spec"]
    timeline = build_timeline(spec)
    validation = validate_timeline(spec, timeline)
    integrity_checks = run_timeline_integrity_check(entry_gate, spec, timeline, validation)
    ready = ready_for_scene_layout_gate(entry_gate, validation, integrity_checks)

    row_id = persist_timeline(db_path, entry_gate["plan_id"], entry_gate.get("render_spec_row_id"), timeline, validation)
    json_path = write_timeline_file(assets_dir, entry_gate["plan_id"], timeline)
    report_path = _build_timeline_report(reports_dir, entry_gate, timeline, validation, integrity_checks, ready, json_path=json_path)

    return {
        "pass": True, "reason": None, "plan_id": entry_gate["plan_id"], "timeline": timeline,
        "validation": validation, "integrity_checks": integrity_checks, "ready_for_scene_layout": ready,
        "json_path": json_path, "report_path": report_path, "timeline_row_id": row_id,
    }


def _build_timeline_report(
    reports_dir: Path, entry_gate: dict, timeline: dict | None, validation: dict | None,
    integrity_checks: dict | None, ready: bool | None, *, json_path: Path | None = None,
) -> Path:
    lines: list[str] = ["# Render Timeline Report", ""]
    lines.append(f"생성일: {datetime.utcnow().date().isoformat()}")
    lines.append(f"Source Plan: {entry_gate.get('plan_id')}")
    lines.append("")
    lines.append("## Timeline Entry Gate")
    lines.append("")
    lines.append("YES" if entry_gate["pass"] else "NO")
    if not entry_gate["pass"]:
        lines.append(f"- {entry_gate['reason']}")
    lines.append("")

    if timeline is not None:
        scenes = timeline["scenes"]
        all_events = [e for s in scenes for e in s["events"]]
        audio_events = [e for e in all_events if e["event_type"] == "AUDIO"]
        pause_events = [e for e in all_events if e["event_type"] == "PAUSE"]
        marker_events = [e for e in all_events if e["event_type"] not in _TIMED_EVENT_TYPES]

        lines.append("## Scenes")
        lines.append("")
        for s in scenes:
            lines.append(f"- {s['scene_id']} ({s['scene_role']}): start={s['start_ms']} end={s['end_ms']} duration={s['duration_ms']}")
        lines.append("")

        lines.append("## Video Duration")
        lines.append("")
        lines.append(f"{timeline['video']['duration_ms']}ms")
        lines.append("")

        lines.append("## Event Counts")
        lines.append("")
        lines.append(f"Total: {len(all_events)}, Audio: {len(audio_events)}, Pause: {len(pause_events)}, Marker/constraint: {len(marker_events)}")
        lines.append("")

        cb06_pause = next((e for s in scenes for e in s["events"] if e["event_type"] == "PAUSE" and s["scene_role"] == "MINI_SUCCESS"), None)
        if cb06_pause:
            lines.append("## Mini Success PAUSE")
            lines.append("")
            lines.append(f"start_ms={cb06_pause['start_ms']} end_ms={cb06_pause['end_ms']} duration_ms={cb06_pause['duration_ms']}")
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

        lines.append("## Ready for Scene/Layout")
        lines.append("")
        lines.append("YES" if ready else "NO")
        lines.append("")

        if json_path:
            lines.append(f"JSON: {json_path}")
            lines.append("")

    reports_dir.mkdir(parents=True, exist_ok=True)
    out_path = reports_dir / f"render_timeline_{datetime.utcnow().date().isoformat()}.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path
