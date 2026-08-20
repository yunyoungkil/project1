import base64
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
from research.render_spec import (
    build_render_spec,
    classify_scene_role,
    classify_visual_intent,
    ready_for_timeline_compilation_gate,
    run_render_spec_integrity_check,
    validate_render_spec,
)

_SILENCE_PCM = b"\x00\x00" * 24000


class FakeTTSClient:
    def __init__(self):
        self.calls = []

    def synthesize(self, prompt, voice_name):
        self.calls.append((prompt, voice_name))
        return {"audio_base64": base64.b64encode(_SILENCE_PCM).decode("ascii"), "mime_type": "audio/L16;rate=24000", "attempts": 1}


def _seed_render_plan(conn) -> int:
    """A minimal but real plan: CB01 = plain EXPLANATION (KO_NARRATION + EN_NATIVE BAG), CB02 =
    Mini Success (VISUAL -> PAUSE(3000ms) -> SPEECH answer, mirrors the real CB06)."""
    plan_cur = conn.execute(
        """
        INSERT INTO production_plans (video_direction_id, video_script_id, final_format, plan_json,
            estimated_duration_seconds, production_complexity, generation_method, integrity_check_json,
            planner_score, ready_for_asset_generation)
        VALUES (1, 1, 'EDUCATION', '{}', 60.0, 'low', 'deterministic', '{}', 90.0, 1)
        """,
    )
    plan_id = plan_cur.lastrowid

    conn.execute(
        """
        INSERT INTO production_blocks (production_plan_id, content_block_id, block_order, delivery_mode,
            production_intent, timeline_spec_json, speech_segments_json, visual_spec_json, caption_spec_json,
            clip_spec_json, interaction_spec_json)
        VALUES (?, 'CB01', 1, 'EDUCATION', 'explain_core_principle', ?, '[]',
            '{"primary_visual_type": "KEY_CONCEPT"}', '{}', NULL, '{"has_pause": false, "viewer_action": null, "thinking_time_seconds": 0}')
        """,
        (plan_id, json.dumps([
            {"event_order": 1, "type": "SPEECH", "speech_asset_id": "SP001"},
            {"event_order": 2, "type": "SPEECH", "speech_asset_id": "SP002"},
        ])),
    )
    conn.execute(
        """
        INSERT INTO production_blocks (production_plan_id, content_block_id, block_order, delivery_mode,
            production_intent, timeline_spec_json, speech_segments_json, visual_spec_json, caption_spec_json,
            clip_spec_json, interaction_spec_json)
        VALUES (?, 'CB02', 2, 'EDUCATION', 'viewer_must_attempt_before_answer', ?, '[]',
            '{"primary_visual_type": "QUESTION"}', '{}', NULL,
            '{"has_pause": true, "viewer_action": "\352\262\214\355\232\224\354\212\244\355\212\270", "thinking_time_seconds": 3}')
        """,
        (plan_id, json.dumps([
            {"event_order": 1, "type": "VISUAL", "visual_role": "TARGET_WORD", "content": "CAP"},
            {"event_order": 2, "type": "PAUSE", "duration_ms": 3000, "pause_visual_behavior": "THINKING_DOTS"},
            {"event_order": 3, "type": "SPEECH", "speech_asset_id": "SP003"},
        ])),
    )

    assets = [
        ("SP001", "KO_NARRATION", "Charon", "안녕하세요."),
        ("SP002", "EN_NATIVE", "Charon", "BAG"),
        ("SP003", "EN_NATIVE", "Charon", "CAP"),
    ]
    for asset_id, mode, voice, text in assets:
        conn.execute(
            """
            INSERT INTO speech_assets (production_plan_id, content_block_id, speech_asset_id, speech_mode,
                voice_name, language_code, source_text, tts_input_text, display_text, approximation_only,
                pause_before_ms, pause_after_ms)
            VALUES (?, '', ?, ?, ?, 'en-US', ?, ?, ?, 0, 0, 0)
            """,
            (plan_id, asset_id, mode, voice, text, text, text),
        )
    return plan_id


def _speech_assets_for(db_path, plan_id):
    with connect(db_path) as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM speech_assets WHERE production_plan_id = ? ORDER BY speech_asset_id", (plan_id,)
        ).fetchall()]


def _asset_by_id(assets, sid):
    return next(a for a in assets if a["speech_asset_id"] == sid)


def _gen(db_path, plan_id, speech_asset, client, tmp_path, **kwargs):
    row = synthesize_asset(db_path, speech_asset, client, audio_dir=tmp_path / "audio", tts_model="m", **kwargs)
    _persist_generated_assets(db_path, plan_id, [row])
    return row


def _make_ready_plan(tmp_path, db_path):
    """Full CAP fallback story (DIRECT_WORD REGENERATE_REQUIRED, CONTEXTUAL_WORD approved fallback)
    -- mirrors the exact real Plan 7 CAP situation -- so tests exercise the real selection path,
    not a simplified stand-in."""
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

    run_asset_generation(db_path, client, mode="SAMPLE", tts_model="m", assets_dir=tmp_path / "assets", plan_id=plan_id)
    run_asset_generation(db_path, client, mode="FULL", tts_model="m", assets_dir=tmp_path / "assets", plan_id=plan_id)
    return plan_id


# CASE A: Ready for Rendering=NO -> spec generation blocked
def test_case_a_not_ready_blocks_spec_generation(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_render_plan(conn)
    result = build_render_spec(db_path, plan_id=plan_id)
    assert result["blocked"] is True
    assert result["spec"] is None
    assert result["reasons"]


# CASE B: Ready=YES -> spec is generated
def test_case_b_ready_generates_spec(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id = _make_ready_plan(tmp_path, db_path)
    result = build_render_spec(db_path, plan_id=plan_id)
    assert result["blocked"] is False
    assert result["spec"] is not None
    assert len(result["spec"]["scenes"]) == 2


# CASE C: every scene has real Production Block lineage
def test_case_c_scene_block_lineage_complete(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id = _make_ready_plan(tmp_path, db_path)
    result = build_render_spec(db_path, plan_id=plan_id)
    scene_ids = {s["content_block_id"] for s in result["spec"]["scenes"]}
    assert scene_ids == {"CB01", "CB02"}


# CASE D: audio elements reference real Generation Units with resolvable files
def test_case_d_generation_unit_audio_lineage(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id = _make_ready_plan(tmp_path, db_path)
    result = build_render_spec(db_path, plan_id=plan_id)
    cb01 = next(s for s in result["spec"]["scenes"] if s["scene_id"] == "CB01")
    assert len(cb01["audio_elements"]) == 2
    for a in cb01["audio_elements"]:
        assert a["file_path"] and Path(a["file_path"]).exists()
        assert a["status"] in {"AVAILABLE", "REUSED"}


# CASE J: CAP scene picks the approved CONTEXTUAL_WORD fallback, not the failed DIRECT_WORD
def test_case_j_cap_approved_fallback_selected(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id = _make_ready_plan(tmp_path, db_path)
    result = build_render_spec(db_path, plan_id=plan_id)
    cb02 = next(s for s in result["spec"]["scenes"] if s["scene_id"] == "CB02")
    cap_audio = [a for a in cb02["audio_elements"] if a["source_speech_asset_id"] == "SP003"]
    assert len(cap_audio) == 1
    assert cap_audio[0]["asset_id"] == "SP003::CONTEXTUAL_WORD"
    assert cap_audio[0]["generation_unit_id"] != "SP003"


# CASE H/I: failed/rejected variant selected -> validation fails
def test_case_h_i_failed_or_rejected_variant_selected_fails_validation(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id = _make_ready_plan(tmp_path, db_path)
    result = build_render_spec(db_path, plan_id=plan_id)
    spec = result["spec"]
    # Manually corrupt one audio_element to point at the known-failed DIRECT_WORD variant --
    # simulates a selection-logic regression, verifying validation actually catches it.
    for scene in spec["scenes"]:
        for a in scene["audio_elements"]:
            if a["source_speech_asset_id"] == "SP003":
                a["asset_id"] = a["generation_unit_id"] = "SP003"
    from research.asset_generator import _load_production_blocks, _load_speech_assets
    blocks = _load_production_blocks(db_path, plan_id)
    assets = _load_speech_assets(db_path, plan_id)
    validation = validate_render_spec(db_path, plan_id, spec, blocks, assets)
    assert validation["checks"]["no_failed_or_rejected_variant_used"] is False
    assert "no_failed_or_rejected_variant_used" in validation["unresolved_critical"]


# CASE K/L: experimental variants are never auto-selected
def test_case_k_l_experimental_variants_never_used(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id = _make_ready_plan(tmp_path, db_path)
    assets = _speech_assets_for(db_path, plan_id)
    cap = _asset_by_id(assets, "SP003")
    client = FakeTTSClient()
    for strategy in ("LOWERCASE_WORD", "MINIMAL_CONTEXT_WORD"):
        _gen(db_path, plan_id, cap, client, tmp_path, asset_id=f"SP003::{strategy}", pronunciation_strategy=strategy)
        record_pronunciation_review(db_path, plan_id, f"SP003::{strategy}", "APPROVED")
    result = build_render_spec(db_path, plan_id=plan_id)
    all_gids = [a["generation_unit_id"] for s in result["spec"]["scenes"] for a in s["audio_elements"]]
    assert not any("LOWERCASE_WORD" in g or "MINIMAL_CONTEXT_WORD" in g or "CONTEXT_RESTRICTED" in g for g in all_gids)


# CASE M: PAUSE 3000ms preserved
def test_case_m_pause_preserved(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id = _make_ready_plan(tmp_path, db_path)
    result = build_render_spec(db_path, plan_id=plan_id)
    cb02 = next(s for s in result["spec"]["scenes"] if s["scene_id"] == "CB02")
    assert len(cb02["pause_requirements"]) == 1
    assert cb02["pause_requirements"][0]["duration_ms"] == 3000
    assert cb02["pause_requirements"][0]["answer_reveal_allowed"] is False


# CASE N: viewer_action preserved
def test_case_n_viewer_action_preserved(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id = _make_ready_plan(tmp_path, db_path)
    result = build_render_spec(db_path, plan_id=plan_id)
    cb02 = next(s for s in result["spec"]["scenes"] if s["scene_id"] == "CB02")
    assert cb02["viewer_action"] is not None
    assert cb02["attempt_required"] is True


# CASE O: answer reveal barrier preserved
def test_case_o_answer_reveal_barrier_preserved(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id = _make_ready_plan(tmp_path, db_path)
    result = build_render_spec(db_path, plan_id=plan_id)
    cb02 = next(s for s in result["spec"]["scenes"] if s["scene_id"] == "CB02")
    assert cb02["answer_reveal_policy"]["reveal_before_pause_allowed"] is False
    assert cb02["answer_reveal_policy"]["reveal_after_pause"] is True


# CASE P: Mini Success scene preserved with an ANSWER text element after the pause
def test_case_p_mini_success_scene_preserved(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id = _make_ready_plan(tmp_path, db_path)
    result = build_render_spec(db_path, plan_id=plan_id)
    cb02 = next(s for s in result["spec"]["scenes"] if s["scene_id"] == "CB02")
    assert cb02["scene_role"] == "MINI_SUCCESS"
    answer_texts = [t for t in cb02["text_elements"] if t["role"] == "ANSWER"]
    assert len(answer_texts) == 1
    assert answer_texts[0]["reveal_policy"] == "AFTER_PAUSE"
    assert answer_texts[0]["emphasis"] is True


# CASE Q: a renderer-specific technical term leaking into the spec fails the neutrality check
def test_case_q_renderer_specific_field_fails_neutrality_check(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id = _make_ready_plan(tmp_path, db_path)
    result = build_render_spec(db_path, plan_id=plan_id)
    spec = result["spec"]
    from research.asset_generator import _load_production_blocks, _load_speech_assets
    blocks = _load_production_blocks(db_path, plan_id)
    assets = _load_speech_assets(db_path, plan_id)
    validation = validate_render_spec(db_path, plan_id, spec, blocks, assets)
    clean_checks = run_render_spec_integrity_check(result["readiness"], spec, validation)
    assert clean_checks["render_spec_renderer_neutral"] is True

    dirty_spec = json.loads(json.dumps(spec))
    dirty_spec["scenes"][0]["renderer_hint"] = "Use a Remotion Sequence component here"
    dirty_checks = run_render_spec_integrity_check(result["readiness"], dirty_spec, validation)
    assert dirty_checks["render_spec_renderer_neutral"] is False


# render_spec_renderer_neutral does NOT false-positive on this project's own legitimate vocabulary
def test_renderer_neutral_check_does_not_false_positive_on_own_vocabulary(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id = _make_ready_plan(tmp_path, db_path)
    result = build_render_spec(db_path, plan_id=plan_id)
    spec = result["spec"]
    from research.asset_generator import _load_production_blocks, _load_speech_assets
    blocks = _load_production_blocks(db_path, plan_id)
    assets = _load_speech_assets(db_path, plan_id)
    validation = validate_render_spec(db_path, plan_id, spec, blocks, assets)
    checks = run_render_spec_integrity_check(result["readiness"], spec, validation)
    assert checks["render_spec_renderer_neutral"] is True


# CASE R: an unresolved critical field blocks the Ready for Timeline Compilation gate
def test_case_r_unresolved_critical_field_blocks_gate(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id = _make_ready_plan(tmp_path, db_path)
    result = build_render_spec(db_path, plan_id=plan_id)
    spec = result["spec"]
    for scene in spec["scenes"]:
        for a in scene["audio_elements"]:
            if a["source_speech_asset_id"] == "SP003":
                a["asset_id"] = a["generation_unit_id"] = "SP003"  # force a real validation failure
    from research.asset_generator import _load_production_blocks, _load_speech_assets
    blocks = _load_production_blocks(db_path, plan_id)
    assets = _load_speech_assets(db_path, plan_id)
    validation = validate_render_spec(db_path, plan_id, spec, blocks, assets)
    checks = run_render_spec_integrity_check(result["readiness"], spec, validation)
    ready = ready_for_timeline_compilation_gate(result["readiness"], spec, validation, checks)
    assert validation["unresolved_critical"]
    assert ready is False


# CASE S: unresolved non-critical output profile (width/height/fps) does not block the gate
def test_case_s_non_critical_unresolved_output_profile_allowed(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id = _make_ready_plan(tmp_path, db_path)
    result = build_render_spec(db_path, plan_id=plan_id)
    spec = result["spec"]
    assert spec["video"]["width"] is None
    assert spec["video"]["height"] is None
    assert spec["video"]["fps"] is None
    assert spec["video"]["resolution_policy"] == "UNRESOLVED_NON_BLOCKING"
    from research.asset_generator import _load_production_blocks, _load_speech_assets
    blocks = _load_production_blocks(db_path, plan_id)
    assets = _load_speech_assets(db_path, plan_id)
    validation = validate_render_spec(db_path, plan_id, spec, blocks, assets)
    checks = run_render_spec_integrity_check(result["readiness"], spec, validation)
    ready = ready_for_timeline_compilation_gate(result["readiness"], spec, validation, checks)
    assert "video.width/height/fps/orientation" in validation["unresolved_non_critical"]
    assert ready is True  # not blocked by the non-critical field


# CASE T: Production Plan/Block/Speech Asset rows unchanged by building a render spec
def test_case_t_production_plan_block_speech_asset_unchanged(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id = _make_ready_plan(tmp_path, db_path)
    with connect(db_path) as conn:
        before_plan = dict(conn.execute("SELECT * FROM production_plans WHERE id = ?", (plan_id,)).fetchone())
        before_blocks = [dict(r) for r in conn.execute(
            "SELECT * FROM production_blocks WHERE production_plan_id = ? ORDER BY block_order", (plan_id,)
        ).fetchall()]
        before_assets = [dict(r) for r in conn.execute(
            "SELECT * FROM speech_assets WHERE production_plan_id = ? ORDER BY speech_asset_id", (plan_id,)
        ).fetchall()]
    build_render_spec(db_path, plan_id=plan_id)
    with connect(db_path) as conn:
        after_plan = dict(conn.execute("SELECT * FROM production_plans WHERE id = ?", (plan_id,)).fetchone())
        after_blocks = [dict(r) for r in conn.execute(
            "SELECT * FROM production_blocks WHERE production_plan_id = ? ORDER BY block_order", (plan_id,)
        ).fetchall()]
        after_assets = [dict(r) for r in conn.execute(
            "SELECT * FROM speech_assets WHERE production_plan_id = ? ORDER BY speech_asset_id", (plan_id,)
        ).fetchall()]
    assert before_plan == after_plan
    assert before_blocks == after_blocks
    assert before_assets == after_assets


# classify_scene_role: Mini Success sentinel always wins regardless of keyword content
def test_classify_scene_role_mini_success_sentinel():
    block = {"production_intent": "viewer_must_attempt_before_answer"}
    role, reason = classify_scene_role(block, {})
    assert role == "MINI_SUCCESS"
    assert reason is None


# classify_scene_role: unmatched production_intent is UNRESOLVED with an explicit reason, never a
# silent UNKNOWN
def test_classify_scene_role_unresolved_has_reason():
    block = {"production_intent": "some_totally_novel_purpose_xyz"}
    role, reason = classify_scene_role(block, {})
    assert role == "UNRESOLVED"
    assert reason is not None and "some_totally_novel_purpose_xyz" in reason


# classify_visual_intent is a pure function, separate from scene_role classification
def test_classify_visual_intent_separated_from_scene_role():
    assert classify_visual_intent("MINI_SUCCESS", "QUESTION") == "QUESTION_THEN_REVEAL"
    assert classify_visual_intent("EXPLANATION", "COMPARISON") == "COMPARE"
    assert classify_visual_intent("EXPLANATION", "KEY_CONCEPT") == "SUPPORT_NARRATION"


# ---------------------------------------------------------------------------
# 13-3A fixtures -- a RECAP-like block (CB03) that reuses CB02's Mini Success answer asset (SP003,
# "CAP") with no PAUSE at all, mirroring the real CB07 situation exactly (SP039::CONTEXTUAL_WORD
# reused in a RECAP block with no PAUSE/barrier of its own).
# ---------------------------------------------------------------------------

def _add_recap_block_reusing_answer(conn, plan_id):
    conn.execute(
        """
        INSERT INTO production_blocks (production_plan_id, content_block_id, block_order, delivery_mode,
            production_intent, timeline_spec_json, speech_segments_json, visual_spec_json, caption_spec_json,
            clip_spec_json, interaction_spec_json)
        VALUES (?, 'CB03', 3, 'EDUCATION', 'summarize_key_principle', ?, '[]',
            '{"primary_visual_type": "RECAP"}', '{}', NULL, '{"has_pause": false, "viewer_action": null, "thinking_time_seconds": 0}')
        """,
        (plan_id, json.dumps([
            {"event_order": 1, "type": "SPEECH", "speech_asset_id": "SP003"},
        ])),
    )


# CASE A/H: a real Mini Success scene gets answer_reveal_policy with the correct shape
def test_case_a_h_mini_success_scene_gets_answer_reveal_policy(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id = _make_ready_plan(tmp_path, db_path)
    result = build_render_spec(db_path, plan_id=plan_id)
    cb02 = next(s for s in result["spec"]["scenes"] if s["scene_id"] == "CB02")
    assert cb02["answer_reveal_policy"] == {"reveal_after_pause": True, "reveal_before_pause_allowed": False}


# CASE B/C/D/I: the same answer asset reused in a RECAP-like scene with no PAUSE at all does NOT
# inherit answer_reveal_policy -- even though is_mini_success_answer_asset(SP003) would return True
# at the asset level (SP003 genuinely is CB02's Mini Success answer), CB03 has no scene-level
# evidence (no PAUSE, no viewer_action) so it must get no policy.
def test_case_b_c_d_i_recap_reuse_gets_no_answer_reveal_policy(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_render_plan(conn)
        _add_recap_block_reusing_answer(conn, plan_id)
    assets = _speech_assets_for(db_path, plan_id)
    ko, bag, cap = _asset_by_id(assets, "SP001"), _asset_by_id(assets, "SP002"), _asset_by_id(assets, "SP003")
    client = FakeTTSClient()
    _gen(db_path, plan_id, ko, client, tmp_path)
    _gen(db_path, plan_id, bag, client, tmp_path)
    record_pronunciation_review(db_path, plan_id, "SP002", "APPROVED")
    record_tone_consistency_review(db_path, plan_id, "SP002", "APPROVED")
    _gen(db_path, plan_id, cap, client, tmp_path)
    record_pronunciation_review(db_path, plan_id, "SP003", "APPROVED")
    record_tone_consistency_review(db_path, plan_id, "SP003", "APPROVED")
    run_asset_generation(db_path, client, mode="SAMPLE", tts_model="m", assets_dir=tmp_path / "assets", plan_id=plan_id)
    run_asset_generation(db_path, client, mode="FULL", tts_model="m", assets_dir=tmp_path / "assets", plan_id=plan_id)

    from research.asset_generator import is_mini_success_answer_asset
    blocks = _load_production_blocks_for_test(db_path, plan_id)
    assert is_mini_success_answer_asset(blocks, "SP003") is True  # asset-scoped: genuinely True

    result = build_render_spec(db_path, plan_id=plan_id)
    assert result["blocked"] is False
    cb02 = next(s for s in result["spec"]["scenes"] if s["scene_id"] == "CB02")
    cb03 = next(s for s in result["spec"]["scenes"] if s["scene_id"] == "CB03")
    assert cb02["answer_reveal_policy"] is not None  # Mini Success scene keeps its policy
    assert cb03["answer_reveal_policy"] is None  # RECAP reuse of the same asset gets none
    assert cb03["scene_role"] != "MINI_SUCCESS"
    # text_element level stays consistent with scene level too (section 8 alignment)
    assert all(t["reveal_policy"] == "IMMEDIATE" for t in cb03["text_elements"])
    assert all(t["role"] != "ANSWER" for t in cb03["text_elements"])


def _load_production_blocks_for_test(db_path, plan_id):
    from research.asset_generator import _load_production_blocks
    return _load_production_blocks(db_path, plan_id)


# CASE J: text_element reveal_policy and scene-level answer_reveal_policy always agree on whether
# a Scene has a reveal constraint
def test_case_j_text_element_and_scene_level_policy_agree(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id = _make_ready_plan(tmp_path, db_path)
    result = build_render_spec(db_path, plan_id=plan_id)
    for s in result["spec"]["scenes"]:
        has_scene_policy = s["answer_reveal_policy"] is not None
        has_after_pause_element = any(t["reveal_policy"] == "AFTER_PAUSE" for t in s["text_elements"])
        assert has_scene_policy == has_after_pause_element


# CASE O/P: CAP fallback asset identity is unaffected by this fix
def test_case_o_p_cap_fallback_identity_unchanged(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id = _make_ready_plan(tmp_path, db_path)
    result = build_render_spec(db_path, plan_id=plan_id)
    cb02 = next(s for s in result["spec"]["scenes"] if s["scene_id"] == "CB02")
    cap_audio = [a for a in cb02["audio_elements"] if a["source_speech_asset_id"] == "SP003"]
    assert len(cap_audio) == 1
    assert cap_audio[0]["asset_id"] == "SP003::CONTEXTUAL_WORD"


# answer_reveal_policy_scene_scoped / render_spec_answer_reveal_scene_scope_safe: normal case pass
def test_answer_reveal_policy_scene_scoped_check_passes_normally(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id = _make_ready_plan(tmp_path, db_path)
    result = build_render_spec(db_path, plan_id=plan_id)
    spec = result["spec"]
    from research.asset_generator import _load_production_blocks, _load_speech_assets
    blocks = _load_production_blocks(db_path, plan_id)
    assets = _load_speech_assets(db_path, plan_id)
    validation = validate_render_spec(db_path, plan_id, spec, blocks, assets)
    checks = run_render_spec_integrity_check(result["readiness"], spec, validation)
    assert validation["checks"]["answer_reveal_policy_scene_scoped"] is True
    assert checks["render_spec_answer_reveal_scene_scope_safe"] is True


# answer_reveal_policy_scene_scoped: a manually corrupted spec (policy injected onto a scene with
# no real evidence) is caught, not silently accepted
def test_answer_reveal_policy_scene_scoped_check_catches_corruption(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id = _make_ready_plan(tmp_path, db_path)
    result = build_render_spec(db_path, plan_id=plan_id)
    spec = result["spec"]
    cb01 = next(s for s in spec["scenes"] if s["scene_id"] == "CB01")
    cb01["answer_reveal_policy"] = {"reveal_after_pause": True, "reveal_before_pause_allowed": False}
    from research.asset_generator import _load_production_blocks, _load_speech_assets
    blocks = _load_production_blocks(db_path, plan_id)
    assets = _load_speech_assets(db_path, plan_id)
    validation = validate_render_spec(db_path, plan_id, spec, blocks, assets)
    checks = run_render_spec_integrity_check(result["readiness"], spec, validation)
    assert validation["checks"]["answer_reveal_policy_scene_scoped"] is False
    assert checks["render_spec_answer_reveal_scene_scope_safe"] is False


# 13-2 regression: event_order (added by the 13-2 additive patch) is present and correct on
# audio_elements/pause_requirements, structurally recoverable in the exact original timeline order
# without any string-join through text_elements
def test_event_order_present_and_recovers_original_timeline_order(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id = _make_ready_plan(tmp_path, db_path)
    result = build_render_spec(db_path, plan_id=plan_id)
    cb02 = next(s for s in result["spec"]["scenes"] if s["scene_id"] == "CB02")
    for a in cb02["audio_elements"]:
        assert a["event_order"] is not None
    for p in cb02["pause_requirements"]:
        assert p["event_order"] is not None
    # Original CB02 timeline: VISUAL(1) -> PAUSE(2) -> SPEECH SP003(3)
    pause_order = cb02["pause_requirements"][0]["event_order"]
    cap_audio = next(a for a in cb02["audio_elements"] if a["source_speech_asset_id"] == "SP003")
    assert cap_audio["event_order"] > pause_order


# 13-2 regression: emphasis_targets/text_elements also carry event_order after the patch
def test_event_order_present_on_emphasis_and_text_elements(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id = _make_ready_plan(tmp_path, db_path)
    result = build_render_spec(db_path, plan_id=plan_id)
    cb02 = next(s for s in result["spec"]["scenes"] if s["scene_id"] == "CB02")
    assert cb02["emphasis_targets"]
    for t in cb02["emphasis_targets"]:
        assert t["event_order"] is not None
    for t in cb02["text_elements"]:
        assert t["event_order"] is not None


# Renderer Entry Gate integrity check reflects the persistent readiness, not a run-local shortcut
def test_renderer_entry_gate_safe_reflects_persistent_readiness(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    plan_id = _make_ready_plan(tmp_path, db_path)
    result = build_render_spec(db_path, plan_id=plan_id)
    spec = result["spec"]
    from research.asset_generator import _load_production_blocks, _load_speech_assets
    blocks = _load_production_blocks(db_path, plan_id)
    assets = _load_speech_assets(db_path, plan_id)
    validation = validate_render_spec(db_path, plan_id, spec, blocks, assets)
    checks = run_render_spec_integrity_check(result["readiness"], spec, validation)
    assert checks["renderer_entry_gate_safe"] is True
    assert result["readiness"]["ready"] is True
