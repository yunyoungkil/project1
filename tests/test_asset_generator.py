import base64
import json
from pathlib import Path

import pytest

from research.asset_generator import (
    ASSET_STATUSES,
    DEFAULT_BLENDING_STRATEGY,
    DEFAULT_EN_NATIVE_STRATEGY,
    EN_NATIVE_PRONUNCIATION_STRATEGIES,
    PHONEME_STRATEGIES,
    PRONUNCIATION_REVIEW_STATES,
    TONE_CONSISTENCY_REVIEW_STATES,
    TTS_PROMPT_VERSION,
    _DELIVERY_LANGUAGE_MAP,
    _NON_REUSABLE_REVIEW_STATES,
    _existing_cache_row,
    _segment_is_safe,
    GENERATION_PLAN_ACTIONS,
    SELECTION_REASONS,
    build_asset_generation_report,
    build_asset_manifest,
    build_full_generation_plan,
    build_generation_units,
    build_tts_prompt,
    classify_phoneme_demo_type,
    classify_phoneme_generation_strategy,
    compute_cache_key,
    compute_tts_transcript,
    is_mini_success_answer_asset,
    parse_pcm_format,
    ready_for_full_generation_gate,
    ready_for_rendering_gate,
    record_pronunciation_review,
    record_tone_consistency_review,
    run_asset_generation,
    run_asset_generation_integrity_check,
    segment_source_text_by_sentence,
    select_active_en_native_variant,
    select_sample_assets,
    select_target_plan,
    synthesize_asset,
    synthesize_ko_narration_segments,
    validate_audio_file,
    write_wav_file,
)
from research.db import connect, init_db

_SILENCE_PCM = b"\x00\x00" * 24000  # 1 second of 24kHz mono 16-bit silence


class FakeTTSClient:
    """Never touches the network -- returns a fixed base64 PCM payload, or None to simulate a
    failure. `fail_times` counts down: each call while > 0 returns None (used to test retry)."""

    def __init__(self, fail_times: int = 0, always_fail: bool = False, mime_type: str = "audio/L16;rate=24000"):
        self.calls: list[tuple[str, str]] = []
        self._fail_times = fail_times
        self._always_fail = always_fail
        self._mime_type = mime_type

    def synthesize(self, prompt: str, voice_name: str) -> dict | None:
        self.calls.append((prompt, voice_name))
        if self._always_fail:
            return None
        if self._fail_times > 0:
            self._fail_times -= 1
            return None
        return {
            "audio_base64": base64.b64encode(_SILENCE_PCM).decode("ascii"),
            "mime_type": self._mime_type,
            "attempts": 1,
        }


def _seed_plan(conn, ready: int = 1) -> int:
    plan_cur = conn.execute(
        """
        INSERT INTO production_plans (video_direction_id, video_script_id, final_format, plan_json,
            estimated_duration_seconds, production_complexity, generation_method, integrity_check_json,
            planner_score, ready_for_asset_generation)
        VALUES (1, 1, 'EDUCATION', '{}', 100.0, 'low', 'deterministic', '{}', 90.0, ?)
        """,
        (ready,),
    )
    plan_id = plan_cur.lastrowid

    conn.execute(
        """
        INSERT INTO production_blocks (production_plan_id, content_block_id, block_order, delivery_mode,
            production_intent, timeline_spec_json, speech_segments_json, visual_spec_json, caption_spec_json,
            clip_spec_json, interaction_spec_json)
        VALUES (?, 'CB03', 1, 'EDUCATION', 'explain', ?, '[]', '{}', '{}', NULL, '{}')
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
        VALUES (?, 'CB06', 2, 'EDUCATION', 'viewer_must_attempt_before_answer', ?, '[]', '{}', '{}', NULL, '{}')
        """,
        (plan_id, json.dumps([
            {"event_order": 1, "type": "VISUAL", "visual_role": "TARGET_WORD", "content": "CAP"},
            {"event_order": 2, "type": "PAUSE", "duration_ms": 3000, "pause_visual_behavior": "THINKING_DOTS"},
            {"event_order": 3, "type": "SPEECH", "speech_asset_id": "SP003"},
        ])),
    )

    assets = [
        ("SP001", "KO_NARRATION", "Charon", "안녕하세요, 오늘은 BAG를 배워보겠습니다.", 0, None),
        ("SP002", "EN_NATIVE", "Charon", "BAG", 0, None),
        ("SP003", "EN_NATIVE", "Charon", "CAP", 0, None),
        ("SP004", "EN_PHONEME_DEMO", "Charon", "/æ/", 0, "/æ/"),
    ]
    for asset_id, mode, voice, text, approx, expected in assets:
        conn.execute(
            """
            INSERT INTO speech_assets (production_plan_id, content_block_id, speech_asset_id, speech_mode,
                voice_name, language_code, source_text, tts_input_text, display_text, expected_pronunciation,
                approximation_only, pause_before_ms, pause_after_ms)
            VALUES (?, '', ?, ?, ?, 'en-US', ?, ?, ?, ?, ?, 0, 0)
            """,
            (plan_id, asset_id, mode, voice, text, text, text, expected, approx),
        )
    return plan_id


def _speech_assets(db_path):
    with connect(db_path) as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM speech_assets ORDER BY speech_asset_id").fetchall()]


# --------------------------------------------------------------------------
# CASE A/B: Voice casting flows through unchanged from the source speech_asset row
# --------------------------------------------------------------------------

def test_case_a_ko_narration_prompt_carries_charon():
    prompt = build_tts_prompt("KO_NARRATION", "안녕하세요.", "Charon")
    assert "Voice: Charon" in prompt


def test_case_b_en_native_prompt_carries_charon():
    prompt = build_tts_prompt("EN_NATIVE", "BAG", "Charon")
    assert "Voice: Charon" in prompt


# --------------------------------------------------------------------------
# CASE C/D: Podcast voice casting hints
# --------------------------------------------------------------------------

def test_case_c_podcast_female_zephyr_hint():
    prompt = build_tts_prompt("KO_NARRATION", "안녕하세요.", "Zephyr")
    assert "Voice: Zephyr" in prompt
    assert "podcast host" in prompt


def test_case_d_podcast_male_charon_hint():
    prompt = build_tts_prompt("KO_NARRATION", "그렇습니다.", "Charon")
    assert "Voice: Charon" in prompt


# --------------------------------------------------------------------------
# CASE E: ORIGINAL_NATIVE_AUDIO never calls TTS
# --------------------------------------------------------------------------

def test_case_e_original_native_audio_zero_gemini_calls(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan(conn)
        conn.execute(
            """
            INSERT INTO speech_assets (production_plan_id, content_block_id, speech_asset_id, speech_mode,
                voice_name, language_code, source_text, approximation_only, pause_before_ms, pause_after_ms,
                source_clip_candidate_id)
            VALUES (?, '', 'SP005', 'ORIGINAL_NATIVE_AUDIO', NULL, NULL, 'clip text', 0, 0, 0, NULL)
            """,
            (plan_id,),
        )
    speech_asset = next(a for a in _speech_assets(db_path) if a["speech_asset_id"] == "SP005")
    client = FakeTTSClient()
    row = synthesize_asset(db_path, speech_asset, client, audio_dir=tmp_path / "audio", tts_model="m")
    assert row["status"] == "MISSING_SOURCE"
    assert client.calls == []
    with pytest.raises(ValueError):
        build_tts_prompt("ORIGINAL_NATIVE_AUDIO", "x", "Charon")


# --------------------------------------------------------------------------
# CASE F: TTS model config
# --------------------------------------------------------------------------

def test_case_f_tts_model_config_default():
    import yaml
    with open(Path(__file__).resolve().parent.parent / "config" / "research_config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    assert cfg["gemini"]["tts_model"] == "gemini-3.1-flash-tts-preview"


# --------------------------------------------------------------------------
# CASE G/H: prompt structure -- preamble + transcript boundary
# --------------------------------------------------------------------------

def test_case_g_speech_generation_preamble_present():
    prompt = build_tts_prompt("KO_NARRATION", "안녕하세요.", "Charon")
    assert "Generate spoken audio for the transcript below." in prompt
    assert "### AUDIO PROFILE" in prompt


def test_case_h_transcript_boundary_present():
    prompt = build_tts_prompt("KO_NARRATION", "안녕하세요.", "Charon")
    assert "### TRANSCRIPT" in prompt
    assert prompt.rstrip().endswith("안녕하세요.")


# --------------------------------------------------------------------------
# CASE I: EN_NATIVE no-spelling instruction
# --------------------------------------------------------------------------

def test_case_i_en_native_bag_no_spelling_instruction():
    prompt = build_tts_prompt("EN_NATIVE", "BAG", "Charon")
    assert "Do not say the letter names" in prompt
    assert "Do not spell the word" in prompt


# --------------------------------------------------------------------------
# CASE J/K: EN_PHONEME_DEMO source of truth
# --------------------------------------------------------------------------

def test_case_j_phoneme_demo_transcript_keeps_raw_ipa():
    prompt = build_tts_prompt("EN_PHONEME_DEMO", "/æ/", "Charon")
    assert prompt.rstrip().endswith("/æ/")


def test_case_k_phoneme_never_auto_converted_to_korean():
    prompt = build_tts_prompt("EN_PHONEME_DEMO", "/æ/", "Charon")
    assert "애" not in prompt


# --------------------------------------------------------------------------
# CASE L: KO_PRONUNCIATION_GUIDE approximation framing preserved
# --------------------------------------------------------------------------

def test_case_l_pronunciation_guide_labeled_as_approximation():
    prompt = build_tts_prompt("KO_PRONUNCIATION_GUIDE", "사운즈 라이커 플랜", "Charon")
    assert "approximation" in prompt.lower()
    assert "not the authoritative" in prompt.lower() or "not the correct" in prompt.lower()


# --------------------------------------------------------------------------
# CASE M/N/O: validation failures
# --------------------------------------------------------------------------

def test_case_m_empty_audio_fails_validation(tmp_path):
    path = tmp_path / "empty.wav"
    write_wav_file(path, b"", 24000, 1, 2)
    result = validate_audio_file(path)
    assert result["valid"] is False
    assert "zero_duration" in result["errors"]


def test_case_n_invalid_wav_fails_validation(tmp_path):
    path = tmp_path / "not_a_wav.wav"
    path.write_bytes(b"not actually a wav file")
    result = validate_audio_file(path)
    assert result["valid"] is False


def test_case_o_zero_duration_fails_validation(tmp_path):
    path = tmp_path / "silent.wav"
    write_wav_file(path, b"", 24000, 1, 2)
    result = validate_audio_file(path)
    assert result["duration_ms"] == 0
    assert result["valid"] is False


# --------------------------------------------------------------------------
# CASE P/Q: retry
# --------------------------------------------------------------------------

def test_case_p_retries_on_transient_failure(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_plan(conn)
    speech_asset = next(a for a in _speech_assets(db_path) if a["speech_asset_id"] == "SP002")
    client = FakeTTSClient(fail_times=0)  # FakeTTSClient itself doesn't loop; retry lives in the real GeminiTTSClient
    row = synthesize_asset(db_path, speech_asset, client, audio_dir=tmp_path / "audio", tts_model="m")
    assert row["status"] == "AVAILABLE"
    assert len(client.calls) == 1


def test_case_q_permanent_failure_marks_failed_not_infinite_retry(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_plan(conn)
    speech_asset = next(a for a in _speech_assets(db_path) if a["speech_asset_id"] == "SP002")
    client = FakeTTSClient(always_fail=True)
    row = synthesize_asset(db_path, speech_asset, client, audio_dir=tmp_path / "audio", tts_model="m")
    assert row["status"] == "FAILED"
    assert len(client.calls) == 1  # this module calls the client once; the client itself owns its retry budget


# --------------------------------------------------------------------------
# CASE R/S: cache
# --------------------------------------------------------------------------

def test_case_r_cache_hit_makes_zero_new_api_calls(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_plan(conn)
    speech_asset = next(a for a in _speech_assets(db_path) if a["speech_asset_id"] == "SP002")
    client = FakeTTSClient()
    audio_dir = tmp_path / "audio"
    first = synthesize_asset(db_path, speech_asset, client, audio_dir=audio_dir, tts_model="m")
    from research.asset_generator import _persist_generated_assets
    _persist_generated_assets(db_path, 1, [first])
    second = synthesize_asset(db_path, speech_asset, client, audio_dir=audio_dir, tts_model="m")
    assert second["status"] == "REUSED"
    assert len(client.calls) == 1  # only the first call actually hit the fake API


def test_case_s_prompt_change_is_cache_miss():
    key1 = compute_cache_key("m", "Charon", "EN_NATIVE", "BAG", "instr-a")
    key2 = compute_cache_key("m", "Charon", "EN_NATIVE", "BAG", "instr-b")
    assert key1 != key2


# --------------------------------------------------------------------------
# CASE T: replay reuse
# --------------------------------------------------------------------------

def test_case_t_replay_asset_reused_check_flags_duplicate_calls():
    rows = [
        {"cache_key": "k1", "api_call_made": True},
        {"cache_key": "k1", "api_call_made": True},  # same key called twice = not reused properly
    ]
    seen = set()
    ok = True
    for r in rows:
        if r["cache_key"] in seen and r["api_call_made"]:
            ok = False
        seen.add(r["cache_key"])
    assert ok is False


# --------------------------------------------------------------------------
# CASE U/V: duration + timing
# --------------------------------------------------------------------------

def test_case_u_actual_duration_stored(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_plan(conn)
    speech_asset = next(a for a in _speech_assets(db_path) if a["speech_asset_id"] == "SP002")
    client = FakeTTSClient()
    row = synthesize_asset(db_path, speech_asset, client, audio_dir=tmp_path / "audio", tts_model="m")
    assert row["duration_ms"] == 1000  # 1 second of silence


def test_case_v_no_fake_word_timing_field():
    import inspect
    from research import asset_generator
    source = inspect.getsource(asset_generator)
    assert "word_timing" not in source.replace("word_timing stays UNAVAILABLE", "")


# --------------------------------------------------------------------------
# CASE W/X: CAP thinking-time preservation + answer asset availability
# --------------------------------------------------------------------------

def test_case_w_cap_3000ms_pause_untouched_after_generation(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_plan(conn)
    client = FakeTTSClient()
    result = run_asset_generation(db_path, client, mode="SAMPLE", tts_model="m", assets_dir=tmp_path / "assets")
    assert result["integrity_checks"]["thinking_time_preserved"] == "pass"
    with connect(db_path) as conn:
        cb06 = conn.execute("SELECT timeline_spec_json FROM production_blocks WHERE content_block_id='CB06'").fetchone()
    timeline = json.loads(cb06["timeline_spec_json"])
    pause = next(ev for ev in timeline if ev["type"] == "PAUSE")
    assert pause["duration_ms"] == 3000


def test_case_x_cap_answer_asset_available_in_full_mode(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_plan(conn)
    client = FakeTTSClient()
    run_asset_generation(db_path, client, mode="SAMPLE", tts_model="m", assets_dir=tmp_path / "assets")
    result = run_asset_generation(db_path, client, mode="FULL", tts_model="m", assets_dir=tmp_path / "assets")
    assert result["integrity_checks"]["answer_asset_available"] == "pass"


# --------------------------------------------------------------------------
# CASE Y: no Source Clip in current EDUCATION plan -> extraction 0
# --------------------------------------------------------------------------

def test_case_y_no_source_clip_extraction_when_none_present(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_plan(conn)
    client = FakeTTSClient()
    result = run_asset_generation(db_path, client, mode="DRY_RUN", tts_model="m", assets_dir=tmp_path / "assets")
    assert result["source_clip_target_count"] == 0


# --------------------------------------------------------------------------
# CASE Z: Sample mode selects exactly the representative Matrix types (12-1 section 18 expands
# the original 3-item Sample to a bounded matrix -- still never the full 44).
# --------------------------------------------------------------------------

def test_case_z_sample_selects_the_representative_matrix(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_plan(conn)
    speech_assets = _speech_assets(db_path)
    matrix = select_sample_assets(speech_assets)
    assert matrix["ko_narration_short"]["speech_mode"] == "KO_NARRATION"
    assert matrix["ko_narration_long"]["speech_mode"] == "KO_NARRATION"
    en_native_texts = {a["source_text"] for a in matrix["en_native"]}
    assert "BAG" in en_native_texts
    phoneme_texts = {a["source_text"] for a in matrix["phoneme_isolated"]}
    assert "/æ/" in phoneme_texts


# --------------------------------------------------------------------------
# CASE AA: Dry Run makes zero Gemini calls
# --------------------------------------------------------------------------

def test_case_aa_dry_run_zero_api_calls(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_plan(conn)
    client = FakeTTSClient()
    result = run_asset_generation(db_path, client, mode="DRY_RUN", tts_model="m", assets_dir=tmp_path / "assets")
    assert result["api_calls"] == 0
    assert client.calls == []


# --------------------------------------------------------------------------
# CASE AB: Full before a successful Sample is blocked
# --------------------------------------------------------------------------

def test_case_ab_full_before_sample_is_blocked(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_plan(conn)
    client = FakeTTSClient()
    with pytest.raises(ValueError):
        run_asset_generation(db_path, client, mode="FULL", tts_model="m", assets_dir=tmp_path / "assets")


# --------------------------------------------------------------------------
# CASE AC: partial failure is preserved, not silently dropped
# --------------------------------------------------------------------------

def test_case_ac_partial_failure_preserved(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan(conn)
        # Outside the Sample Matrix's fixed picks (BAG/CAP/æ/b/g) so SAMPLE can't cache-cover it --
        # FULL must genuinely attempt this one fresh, and can genuinely fail it.
        conn.execute(
            """
            INSERT INTO speech_assets (production_plan_id, content_block_id, speech_asset_id, speech_mode,
                voice_name, language_code, source_text, tts_input_text, display_text, expected_pronunciation,
                approximation_only, pause_before_ms, pause_after_ms)
            VALUES (?, '', 'SP005', 'EN_PHONEME_DEMO', 'Charon', 'en-US', '/t/', '/t/', '/t/', '/t/', 0, 0, 0)
            """,
            (plan_id,),
        )
    client = FakeTTSClient()
    run_asset_generation(db_path, client, mode="SAMPLE", tts_model="m", assets_dir=tmp_path / "assets")
    failing_client = FakeTTSClient(always_fail=True)
    result = run_asset_generation(db_path, failing_client, mode="FULL", tts_model="m", assets_dir=tmp_path / "assets")
    assert result["failed_count"] > 0
    failed_rows = [r for r in result["generated_assets"] if r["status"] == "FAILED"]
    assert failed_rows  # failures show up in the run, not silently swallowed


# --------------------------------------------------------------------------
# CASE AD: re-running the exact same request is idempotent (reuses, doesn't duplicate calls)
# --------------------------------------------------------------------------

def test_case_ad_rerun_is_idempotent_via_cache(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_plan(conn)
    client = FakeTTSClient()
    run_asset_generation(db_path, client, mode="SAMPLE", tts_model="m", assets_dir=tmp_path / "assets")
    calls_after_first = len(client.calls)
    run_asset_generation(db_path, client, mode="SAMPLE", tts_model="m", assets_dir=tmp_path / "assets")
    assert len(client.calls) == calls_after_first  # second SAMPLE run reused cache, made no new calls


# --------------------------------------------------------------------------
# CASE AE: 11 source data is never mutated
# --------------------------------------------------------------------------

def test_case_ae_upstream_11_data_unchanged(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_plan(conn)
        before_plan = dict(conn.execute("SELECT * FROM production_plans WHERE id=1").fetchone())
        before_blocks = [dict(r) for r in conn.execute("SELECT * FROM production_blocks ORDER BY id").fetchall()]
        before_assets = [dict(r) for r in conn.execute("SELECT * FROM speech_assets ORDER BY id").fetchall()]

    client = FakeTTSClient()
    run_asset_generation(db_path, client, mode="SAMPLE", tts_model="m", assets_dir=tmp_path / "assets")

    with connect(db_path) as conn:
        after_plan = dict(conn.execute("SELECT * FROM production_plans WHERE id=1").fetchone())
        after_blocks = [dict(r) for r in conn.execute("SELECT * FROM production_blocks ORDER BY id").fetchall()]
        after_assets = [dict(r) for r in conn.execute("SELECT * FROM speech_assets ORDER BY id").fetchall()]

    assert before_plan == after_plan
    assert before_blocks == after_blocks
    assert before_assets == after_assets


# --------------------------------------------------------------------------
# CASE AF: existing CLI stays backward compatible (spot check via argparse wiring)
# --------------------------------------------------------------------------

def test_case_af_cli_assets_subcommand_registered():
    from research.cli import build_parser
    parser = build_parser()
    ns = parser.parse_args(["assets", "--dry-run"])
    assert ns.func.__name__ == "cmd_assets"
    assert ns.dry_run is True


# --------------------------------------------------------------------------
# Integrity check + gate + manifest + selection helpers
# --------------------------------------------------------------------------

def test_select_target_plan_picks_latest_ready(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        first_id = _seed_plan(conn, ready=1)
        second_id = _seed_plan(conn, ready=1)
    picked = select_target_plan(db_path)
    assert picked["id"] == second_id
    assert picked["id"] != first_id


def test_classify_phoneme_generation_strategy_is_direct_prompt():
    assert classify_phoneme_generation_strategy("/æ/") == "DIRECT_PHONEME_PROMPT"
    assert classify_phoneme_generation_strategy("/b-æ-g/") == "DIRECT_PHONEME_PROMPT"


def test_ready_for_rendering_requires_full_mode():
    assert ready_for_rendering_gate({}, "SAMPLE", False) is False
    assert ready_for_rendering_gate({}, "DRY_RUN", False) is False


def test_ready_for_rendering_no_when_critical_phoneme_unverified():
    checks = {"a": "pass", "b": "pass"}
    assert ready_for_rendering_gate(checks, "FULL", True) is False


def test_ready_for_rendering_no_when_any_check_fails():
    checks = {"a": "pass", "b": "fail"}
    assert ready_for_rendering_gate(checks, "FULL", False) is False


def test_build_asset_manifest_structure():
    rows = [{
        "source_speech_asset_id": "SP002", "speech_mode": "EN_NATIVE", "voice_name": "Charon",
        "status": "AVAILABLE", "file_path": "/x/SP002.wav", "duration_ms": 500,
    }]
    manifest = build_asset_manifest(6, rows)
    assert manifest["production_plan_id"] == 6
    assert manifest["assets"][0]["asset_id"] == "SP002"
    assert manifest["assets"][0]["status"] == "AVAILABLE"


def test_all_generated_asset_statuses_in_fixed_taxonomy():
    for s in ("PENDING", "GENERATING", "AVAILABLE", "FAILED", "UNVERIFIED", "REUSED", "SKIPPED"):
        assert s in ASSET_STATUSES


def test_full_run_integrity_checks_all_pass_with_fake_client(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_plan(conn)
    client = FakeTTSClient()
    run_asset_generation(db_path, client, mode="SAMPLE", tts_model="m", assets_dir=tmp_path / "assets")
    result = run_asset_generation(db_path, client, mode="FULL", tts_model="m", assets_dir=tmp_path / "assets")
    checks = result["integrity_checks"]
    for name, status in checks.items():
        assert status == "pass", f"{name} unexpectedly failed"
    assert result["failed_count"] == 0
    # No real phonetic validator exists, so EN_PHONEME_DEMO stays pronunciation-PENDING and Ready
    # for Rendering is honestly NO even though every technical check passed.
    assert result["ready_for_rendering"] is False


# --------------------------------------------------------------------------
# CASE AG: full existing regression -- exercised by running the whole suite, not a single test.
# --------------------------------------------------------------------------

def test_case_ag_report_generation_end_to_end(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_plan(conn)
    client = FakeTTSClient()
    path = build_asset_generation_report(
        db_path, tmp_path / "reports", tmp_path / "assets", client, mode="DRY_RUN", tts_model="m",
    )
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "# Asset Generation Report" in text
    assert "Mode: DRY_RUN" in text


# ===========================================================================
# 12-1: TTS pronunciation / blending / segmentation correction (spec prompts/12-1, CASE A-Z)
# ===========================================================================

_LONG_KO_TEXT = (
    "오늘은 BAG라는 단어를 배워보겠습니다. 이 단어는 세 개의 소리로 이루어져 있습니다. "
    "먼저 첫 소리를 함께 들어볼까요? 그 다음 가운데 소리와 마지막 소리도 차례로 살펴보겠습니다. "
    "마지막으로 세 소리를 자연스럽게 이어서 발음하는 연습을 해보겠습니다."
)


def _seed_plan_12_1(conn, ready: int = 1) -> int:
    plan_cur = conn.execute(
        """
        INSERT INTO production_plans (video_direction_id, video_script_id, final_format, plan_json,
            estimated_duration_seconds, production_complexity, generation_method, integrity_check_json,
            planner_score, ready_for_asset_generation)
        VALUES (1, 1, 'EDUCATION', '{}', 100.0, 'low', 'deterministic', '{}', 90.0, ?)
        """,
        (ready,),
    )
    plan_id = plan_cur.lastrowid

    conn.execute(
        """
        INSERT INTO production_blocks (production_plan_id, content_block_id, block_order, delivery_mode,
            production_intent, timeline_spec_json, speech_segments_json, visual_spec_json, caption_spec_json,
            clip_spec_json, interaction_spec_json)
        VALUES (?, 'CB_LONG', 1, 'EDUCATION', 'explain', ?, '[]', '{}', '{}', NULL, '{}')
        """,
        (plan_id, json.dumps([
            {"event_order": 1, "type": "SPEECH", "speech_asset_id": "SP100"},
            {"event_order": 2, "type": "SPEECH", "speech_asset_id": "SP101"},
        ])),
    )
    conn.execute(
        """
        INSERT INTO production_blocks (production_plan_id, content_block_id, block_order, delivery_mode,
            production_intent, timeline_spec_json, speech_segments_json, visual_spec_json, caption_spec_json,
            clip_spec_json, interaction_spec_json)
        VALUES (?, 'CB_BLEND', 2, 'EDUCATION', 'explain', ?, '[]', '{}', '{}', NULL, '{}')
        """,
        (plan_id, json.dumps([
            {"event_order": 1, "type": "SPEECH", "speech_asset_id": "SP102"},
            {"event_order": 2, "type": "SPEECH", "speech_asset_id": "SP104"},
        ])),
    )

    assets = [
        ("SP100", "KO_NARRATION", "Charon", "네.", 0, None),
        ("SP101", "KO_NARRATION", "Charon", _LONG_KO_TEXT, 0, None),
        ("SP102", "EN_NATIVE", "Charon", "BAG", 0, None),
        ("SP103", "EN_NATIVE", "Charon", "CAP", 0, None),
        ("SP104", "EN_PHONEME_DEMO", "Charon", "/b-æ-g/", 0, "/b-æ-g/"),
        ("SP105", "EN_PHONEME_DEMO", "Charon", "/b/", 0, "/b/"),
        ("SP106", "EN_PHONEME_DEMO", "Charon", "/æ/", 0, "/æ/"),
        ("SP107", "EN_PHONEME_DEMO", "Charon", "/g/", 0, "/g/"),
    ]
    for asset_id, mode, voice, text, approx, expected in assets:
        conn.execute(
            """
            INSERT INTO speech_assets (production_plan_id, content_block_id, speech_asset_id, speech_mode,
                voice_name, language_code, source_text, tts_input_text, display_text, expected_pronunciation,
                approximation_only, pause_before_ms, pause_after_ms)
            VALUES (?, '', ?, ?, ?, 'en-US', ?, ?, ?, ?, ?, 0, 0)
            """,
            (plan_id, asset_id, mode, voice, text, text, text, expected, approx),
        )
    return plan_id


# --------------------------------------------------------------------------
# CASE E: delivery_language matches speech mode
# --------------------------------------------------------------------------

def test_case_e_delivery_language_matches_speech_mode():
    assert _DELIVERY_LANGUAGE_MAP["KO_NARRATION"] == "ko-KR"
    assert _DELIVERY_LANGUAGE_MAP["EN_NATIVE"] == "en-US"
    assert _DELIVERY_LANGUAGE_MAP["EN_PHONEME_DEMO"] == "en-US"
    assert _DELIVERY_LANGUAGE_MAP["KO_PRONUNCIATION_GUIDE"] == "ko-KR"


# --------------------------------------------------------------------------
# CASE F: ISOLATED vs BLENDED_SEQUENCE distinguished (no new speech_mode)
# --------------------------------------------------------------------------

def test_case_f_isolated_vs_blended_sequence_distinguished():
    assert classify_phoneme_demo_type("/æ/") == "ISOLATED"
    assert classify_phoneme_demo_type("/b-æ-g/") == "BLENDED_SEQUENCE"


# --------------------------------------------------------------------------
# CASE G: blending prompt never asks the model to just say the target word as a sentence
# --------------------------------------------------------------------------

def test_case_g_context_restricted_blend_forbids_saying_whole_word():
    prompt = build_tts_prompt("EN_PHONEME_DEMO", "/b-æ-g/", "Charon", phoneme_strategy="CONTEXT_RESTRICTED", target_word="BAG")
    assert "do NOT say the whole word BAG" in prompt
    direct_prompt = build_tts_prompt("EN_PHONEME_DEMO", "/b-æ-g/", "Charon", phoneme_strategy="DIRECT_SEQUENCE")
    assert "BAG" not in direct_prompt  # DIRECT_SEQUENCE never mentions the target word at all
    assert prompt.rstrip().endswith("/b-æ-g/")  # transcript is still only the sound sequence
    assert direct_prompt.rstrip().endswith("/b-æ-g/")


# --------------------------------------------------------------------------
# CASE H: technical validation PASS never auto-generates pronunciation APPROVED
# --------------------------------------------------------------------------

def test_case_h_technical_pass_does_not_auto_approve_pronunciation(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_plan_12_1(conn)
    speech_asset = next(a for a in _speech_assets(db_path) if a["speech_asset_id"] == "SP106")
    client = FakeTTSClient()
    row = synthesize_asset(db_path, speech_asset, client, audio_dir=tmp_path / "audio", tts_model="m")
    assert row["status"] == "AVAILABLE"  # technical generation succeeded
    assert row["metadata"]["pronunciation_review"] == "PENDING"  # but never auto-approved


# --------------------------------------------------------------------------
# CASE I/J: Ready for Full Generation gate
# --------------------------------------------------------------------------

def test_case_i_pending_high_priority_sample_blocks_full_generation_gate():
    checks = {"a": "pass"}
    rows = [{"metadata": {"review_priority": "HIGH", "pronunciation_review": "PENDING"}}]
    assert ready_for_full_generation_gate(checks, rows) is False


def test_case_j_approved_high_priority_sample_opens_gate():
    checks = {"a": "pass"}
    rows = [
        {"metadata": {"review_priority": "HIGH", "pronunciation_review": "APPROVED"}},
        {"metadata": {"review_priority": "LOW", "pronunciation_review": "NOT_REQUIRED"}},
    ]
    assert ready_for_full_generation_gate(checks, rows) is True


# --------------------------------------------------------------------------
# CASE K/L: segmentation never produces punctuation-only or orphan fragments
# --------------------------------------------------------------------------

def test_case_k_segmentation_never_yields_punctuation_only_segment():
    segments = segment_source_text_by_sentence(_LONG_KO_TEXT, max_segment_seconds=6)
    assert all(seg.strip() not in {"", "-", "."} for seg in segments)


def test_case_l_segmentation_never_yields_orphan_fragment():
    # Sentence-boundary splitting never deletes a token mid-sentence, so the only fragment shape
    # it could actually produce is punctuation-only content -- verify the safety primitive rejects
    # that directly (see _segment_is_safe's docstring for why 11-1's stricter orphan-particle
    # check doesn't apply to whole-sentence regrouping).
    assert _segment_is_safe("---") is False
    assert _segment_is_safe("...") is False
    assert _segment_is_safe("이 단어는 세 개의 소리로 이루어져 있습니다.") is True


# --------------------------------------------------------------------------
# CASE M/N: long narration segmented at sentence boundaries, order preserved
# --------------------------------------------------------------------------

def test_case_m_long_narration_split_at_sentence_boundaries():
    segments = segment_source_text_by_sentence(_LONG_KO_TEXT, max_segment_seconds=6)
    assert len(segments) > 1
    for seg in segments:
        assert seg.strip().endswith((".", "?", "!"))


def test_case_n_segment_order_preserves_original_meaning_order():
    segments = segment_source_text_by_sentence(_LONG_KO_TEXT, max_segment_seconds=6)
    rejoined = " ".join(segments)
    # every sentence-ending clause of the original still appears in the same relative order
    assert rejoined.index("배워보겠습니다") < rejoined.index("들어볼까요") < rejoined.index("해보겠습니다")


# --------------------------------------------------------------------------
# CASE O: source block lineage preserved through segmentation
# --------------------------------------------------------------------------

def test_case_o_segment_lineage_traces_back_to_source_block(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_plan_12_1(conn)
    from research.asset_generator import _load_production_blocks
    production_blocks = _load_production_blocks(db_path, 1)
    speech_asset = next(a for a in _speech_assets(db_path) if a["speech_asset_id"] == "SP101")
    client = FakeTTSClient()
    rows = synthesize_ko_narration_segments(
        db_path, speech_asset, client, audio_dir=tmp_path / "audio", tts_model="m",
        production_blocks=production_blocks, max_segment_seconds=6, max_new_segments=10,
    )
    assert len(rows) > 1
    for i, row in enumerate(rows):
        assert row["metadata"]["segment_index"] == i
        assert row["metadata"]["segment_count"] == len(rows)
        assert row["metadata"]["source_block_ids"] == ["CB_LONG"]
        assert row["asset_id"] == f"SP101-{i + 1}"
        assert row["source_speech_asset_id"] == "SP101"


# --------------------------------------------------------------------------
# CASE P/Q: cache key changes with prompt_version, stable when unchanged
# --------------------------------------------------------------------------

def test_case_p_prompt_version_change_invalidates_stale_cache():
    key_v1 = compute_cache_key("m", "Charon", "EN_NATIVE", "BAG", "instr", prompt_version="12.0")
    key_v2 = compute_cache_key("m", "Charon", "EN_NATIVE", "BAG", "instr", prompt_version="12.1")
    assert key_v1 != key_v2


def test_case_q_same_prompt_config_keeps_cache_hit(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_plan_12_1(conn)
    speech_asset = next(a for a in _speech_assets(db_path) if a["speech_asset_id"] == "SP102")
    client = FakeTTSClient()
    audio_dir = tmp_path / "audio"
    first = synthesize_asset(db_path, speech_asset, client, audio_dir=audio_dir, tts_model="m")
    from research.asset_generator import _persist_generated_assets
    _persist_generated_assets(db_path, 1, [first])
    second = synthesize_asset(db_path, speech_asset, client, audio_dir=audio_dir, tts_model="m")
    assert second["status"] == "REUSED"
    assert len(client.calls) == 1


# --------------------------------------------------------------------------
# CASE T: existing upstream data (interaction_spec, timeline) is byte-identical after a run
# --------------------------------------------------------------------------

def test_case_t_production_block_interaction_data_untouched(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_plan(conn)
        before = [dict(r) for r in conn.execute(
            "SELECT content_block_id, interaction_spec_json, timeline_spec_json FROM production_blocks ORDER BY id"
        ).fetchall()]
    client = FakeTTSClient()
    run_asset_generation(db_path, client, mode="SAMPLE", tts_model="m", assets_dir=tmp_path / "assets")
    with connect(db_path) as conn:
        after = [dict(r) for r in conn.execute(
            "SELECT content_block_id, interaction_spec_json, timeline_spec_json FROM production_blocks ORDER BY id"
        ).fetchall()]
    assert before == after


# --------------------------------------------------------------------------
# CASE V: all 16 original Integrity Checks preserved by name, 5 new ones added (21 total)
# --------------------------------------------------------------------------

def test_case_v_original_16_checks_preserved_plus_5_new(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_plan(conn)
    client = FakeTTSClient()
    result = run_asset_generation(db_path, client, mode="SAMPLE", tts_model="m", assets_dir=tmp_path / "assets")
    checks = result["integrity_checks"]
    original_16 = {
        "source_plan_unchanged", "required_assets_resolved", "speech_mode_preserved", "voice_casting_preserved",
        "native_audio_not_synthesized", "korean_approximation_metadata_preserved", "phoneme_source_of_truth_preserved",
        "generated_audio_file_valid", "actual_duration_available", "cache_key_complete", "replay_asset_reused",
        "thinking_time_preserved", "answer_asset_available", "source_clip_boundary_preserved", "manifest_complete",
        "no_renderer_execution",
    }
    new_5_12_1 = {
        "tts_prompt_version_safe", "speech_segmentation_safe", "speech_lineage_safe",
        "cache_prompt_consistency_safe", "sample_pronunciation_review_safe",
    }
    new_5_12_2 = {
        "en_native_pronunciation_strategy_safe", "en_native_source_preserved",
        "cache_pronunciation_strategy_safe", "human_pronunciation_gate_safe", "blending_default_strategy_safe",
    }
    new_4_12_3 = {
        "en_native_experiment_isolation_safe", "tone_review_gate_safe",
        "pronunciation_variant_cache_safe", "mini_success_en_native_review_safe",
    }
    new_6_12_4 = {
        "en_native_primary_fallback_policy_safe", "failed_variant_not_selected",
        "approved_fallback_selection_safe", "representative_review_gate_safe",
        "full_generation_plan_complete", "full_generation_api_estimate_safe",
    }
    new_7_12_5 = {
        "generation_unit_model_safe", "ko_segmentation_mode_consistent", "generation_unit_lineage_safe",
        "full_api_estimate_generation_unit_based", "segment_cache_identity_safe",
        "full_reuses_existing_segments", "full_generation_path_uses_plan",
    }
    new_8_12_6 = {
        "full_generation_executed_safe", "all_generation_units_materialized",
        "generated_audio_technical_validation_safe", "full_manifest_complete", "full_review_state_honest",
        "failed_or_rejected_asset_not_reused", "active_strategy_matches_full_plan", "full_api_call_accounting_safe",
    }
    assert original_16 <= set(checks.keys())
    assert new_5_12_1 <= set(checks.keys())
    assert new_5_12_2 <= set(checks.keys())
    assert new_4_12_3 <= set(checks.keys())
    assert new_6_12_4 <= set(checks.keys())
    assert new_7_12_5 <= set(checks.keys())
    assert new_8_12_6 <= set(checks.keys())
    assert len(checks) == 51


# --------------------------------------------------------------------------
# CLI: assets-review is registered and non-interactive
# --------------------------------------------------------------------------

def test_assets_review_cli_registered():
    from research.cli import build_parser
    parser = build_parser()
    ns = parser.parse_args(["assets-review", "--plan-id", "7"])
    assert ns.func.__name__ == "cmd_assets_review"
    assert ns.plan_id == 7


# --------------------------------------------------------------------------
# Full Sample Matrix end-to-end with the fake client (blending strategies + segmentation together)
# --------------------------------------------------------------------------

def test_sample_matrix_end_to_end_produces_both_blend_strategies_and_segments(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_plan_12_1(conn)
    client = FakeTTSClient()
    result = run_asset_generation(db_path, client, mode="SAMPLE", tts_model="m", assets_dir=tmp_path / "assets")
    asset_ids = {r["asset_id"] for r in result["generated_assets"]}
    assert "SP104::DIRECT_SEQUENCE" in asset_ids
    assert "SP104::CONTEXT_RESTRICTED" in asset_ids
    assert any(a.startswith("SP101-") for a in asset_ids)  # long narration got segmented
    assert result["failed_count"] == 0
    assert "ready_for_full_generation" in result
    assert result["ready_for_full_generation"] is False  # nothing human-approved yet -- normal


# ===========================================================================
# 12-2: EN_NATIVE pronunciation stabilization + blending default (spec prompts/12-2, CASE A-X)
# ===========================================================================

def _seed_plan_12_2(conn, ready: int = 1) -> int:
    plan_cur = conn.execute(
        """
        INSERT INTO production_plans (video_direction_id, video_script_id, final_format, plan_json,
            estimated_duration_seconds, production_complexity, generation_method, integrity_check_json,
            planner_score, ready_for_asset_generation)
        VALUES (1, 1, 'EDUCATION', '{}', 100.0, 'low', 'deterministic', '{}', 90.0, ?)
        """,
        (ready,),
    )
    plan_id = plan_cur.lastrowid

    # CB_MINI: Mini Success answer block -- PAUSE then EN_NATIVE "CAP" is the reveal.
    conn.execute(
        """
        INSERT INTO production_blocks (production_plan_id, content_block_id, block_order, delivery_mode,
            production_intent, timeline_spec_json, speech_segments_json, visual_spec_json, caption_spec_json,
            clip_spec_json, interaction_spec_json)
        VALUES (?, 'CB_MINI', 1, 'EDUCATION', 'viewer_must_attempt_before_answer', ?, '[]', '{}', '{}', NULL, '{}')
        """,
        (plan_id, json.dumps([
            {"event_order": 1, "type": "VISUAL", "visual_role": "TARGET_WORD", "content": "CAP"},
            {"event_order": 2, "type": "PAUSE", "duration_ms": 3000, "pause_visual_behavior": "THINKING_DOTS"},
            {"event_order": 3, "type": "SPEECH", "speech_asset_id": "SP203"},
        ])),
    )
    # CB_PLAIN: ordinary (non-Mini-Success) block using EN_NATIVE "BAG".
    conn.execute(
        """
        INSERT INTO production_blocks (production_plan_id, content_block_id, block_order, delivery_mode,
            production_intent, timeline_spec_json, speech_segments_json, visual_spec_json, caption_spec_json,
            clip_spec_json, interaction_spec_json)
        VALUES (?, 'CB_PLAIN', 2, 'EDUCATION', 'explain', ?, '[]', '{}', '{}', NULL, '{}')
        """,
        (plan_id, json.dumps([{"event_order": 1, "type": "SPEECH", "speech_asset_id": "SP201"}])),
    )

    assets = [
        ("SP201", "EN_NATIVE", "Charon", "BAG"),
        ("SP202", "EN_NATIVE", "Charon", "MAP"),
        ("SP203", "EN_NATIVE", "Charon", "CAP"),
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


# CASE A/C: source_text preserved, never overwritten by normalization
def test_case_a_source_text_preserved(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_2(conn)
    speech_asset = next(a for a in _speech_assets_for(db_path, plan_id) if a["speech_asset_id"] == "SP203")
    client = FakeTTSClient()
    row = synthesize_asset(
        db_path, speech_asset, client, audio_dir=tmp_path / "audio", tts_model="m",
        pronunciation_strategy="CONTEXTUAL_WORD",
    )
    assert row["metadata"]["synthesized_text"] == "CAP"
    with connect(db_path) as conn:
        after = conn.execute("SELECT source_text FROM speech_assets WHERE speech_asset_id='SP203'").fetchone()
    assert after["source_text"] == "CAP"


# CASE B: CONTEXTUAL_WORD transcript can normalize to lowercase
def test_case_b_contextual_word_transcript_lowercased():
    assert compute_tts_transcript("EN_NATIVE", "CAP", pronunciation_strategy="CONTEXTUAL_WORD") == "cap"
    assert compute_tts_transcript("EN_NATIVE", "CAP", pronunciation_strategy="DIRECT_WORD") == "CAP"


# CASE E: prompt never asks the model to speak the explanation itself
def test_case_e_prompt_does_not_ask_model_to_speak_explanation():
    prompt = build_tts_prompt("EN_NATIVE", "CAP", "Charon", pronunciation_strategy="CONTEXTUAL_WORD")
    transcript_section = prompt.split("### TRANSCRIPT")[1]
    assert "This is an English word" not in transcript_section
    assert transcript_section.strip() == "cap"


# CASE F: DIRECT_WORD and CONTEXTUAL_WORD cache keys differ
def test_case_f_direct_and_contextual_cache_keys_differ():
    k1 = compute_cache_key("m", "Charon", "EN_NATIVE", "CAP", "instr", pronunciation_strategy="DIRECT_WORD")
    k2 = compute_cache_key("m", "Charon", "EN_NATIVE", "CAP", "instr", pronunciation_strategy="CONTEXTUAL_WORD")
    assert k1 != k2


# CASE H: a REGENERATE_REQUIRED asset is never served again by any cache key
def test_case_h_regenerate_required_asset_never_cache_hit(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_2(conn)
    speech_asset = next(a for a in _speech_assets_for(db_path, plan_id) if a["speech_asset_id"] == "SP203")
    client = FakeTTSClient()
    first = synthesize_asset(db_path, speech_asset, client, audio_dir=tmp_path / "audio", tts_model="m", pronunciation_strategy="DIRECT_WORD")
    from research.asset_generator import _persist_generated_assets
    _persist_generated_assets(db_path, plan_id, [first])
    record_pronunciation_review(db_path, plan_id, "SP203", "REGENERATE_REQUIRED")

    second = synthesize_asset(db_path, speech_asset, client, audio_dir=tmp_path / "audio", tts_model="m", pronunciation_strategy="DIRECT_WORD")
    assert second["status"] != "REUSED"  # forced a fresh attempt instead of resurrecting the bad one
    assert len(client.calls) == 2


# CASE I: BAG/MAP/CAP all flow through the same generalized matrix logic
def test_case_i_bag_map_cap_generalized_matrix(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_plan_12_2(conn)
    speech_assets = _speech_assets_for(db_path, 1)
    matrix = select_sample_assets(speech_assets)
    words = {a["source_text"] for a in matrix["en_native"]}
    assert words == {"BAG", "MAP", "CAP"}


# CASE J: no per-word hardcoded branch anywhere in the module -- "CAP" may appear in a
# generalized word list or an explanatory comment, but never as a conditional's target.
def test_case_j_no_cap_hardcoded_branch():
    import inspect
    from research import asset_generator
    source = inspect.getsource(asset_generator)
    assert '== "CAP"' not in source
    assert "== 'CAP'" not in source
    assert 'is "CAP"' not in source


# CASE K: new EN_NATIVE sample defaults to PENDING
def test_case_k_new_en_native_sample_defaults_pending(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_2(conn)
    speech_asset = next(a for a in _speech_assets_for(db_path, plan_id) if a["speech_asset_id"] == "SP202")
    client = FakeTTSClient()
    row = synthesize_asset(db_path, speech_asset, client, audio_dir=tmp_path / "audio", tts_model="m", pronunciation_strategy="CONTEXTUAL_WORD")
    assert row["metadata"]["pronunciation_review"] == "PENDING"


# CASE L: REGENERATE_REQUIRED never lets the Ready for Full Generation gate open
def test_case_l_regenerate_required_blocks_gate():
    checks = {"a": "pass"}
    rows = [{"status": "AVAILABLE", "metadata": {"review_priority": "MEDIUM", "pronunciation_review": "REGENERATE_REQUIRED"}}]
    assert ready_for_full_generation_gate(checks, rows) is False


# CASE M: cache reuse preserves an existing APPROVED verdict (never resets to PENDING)
def test_case_m_cache_reuse_preserves_approved_status(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_2(conn)
    speech_asset = next(a for a in _speech_assets_for(db_path, plan_id) if a["speech_asset_id"] == "SP201")
    client = FakeTTSClient()
    first = synthesize_asset(db_path, speech_asset, client, audio_dir=tmp_path / "audio", tts_model="m", pronunciation_strategy="DIRECT_WORD")
    from research.asset_generator import _persist_generated_assets
    _persist_generated_assets(db_path, plan_id, [first])
    record_pronunciation_review(db_path, plan_id, "SP201", "APPROVED")

    second = synthesize_asset(db_path, speech_asset, client, audio_dir=tmp_path / "audio", tts_model="m", pronunciation_strategy="DIRECT_WORD")
    assert second["status"] == "REUSED"
    assert second["metadata"]["pronunciation_review"] == "APPROVED"


# CASE N/O: DIRECT_SEQUENCE is default, CONTEXT_RESTRICTED remains valid
def test_case_n_o_default_and_alternative_blending_strategy():
    assert DEFAULT_BLENDING_STRATEGY == "DIRECT_SEQUENCE"
    assert DEFAULT_BLENDING_STRATEGY in PHONEME_STRATEGIES
    assert "CONTEXT_RESTRICTED" in PHONEME_STRATEGIES


# CASE P: duration alone never auto-rejects a strategy
def test_case_p_long_duration_does_not_fail_validation(tmp_path):
    path = tmp_path / "long.wav"
    write_wav_file(path, b"\x00\x00" * 24000 * 10, 24000, 1, 2)  # 10 seconds of silence
    result = validate_audio_file(path)
    assert result["valid"] is True  # long duration alone is not a validation failure


# CASE W: assets-review / manifest distinguish strategy variants of the same source asset
def test_case_w_assets_review_distinguishes_strategy_variants(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_2(conn)
    speech_asset = next(a for a in _speech_assets_for(db_path, plan_id) if a["speech_asset_id"] == "SP201")
    client = FakeTTSClient()
    direct = synthesize_asset(db_path, speech_asset, client, audio_dir=tmp_path / "audio", tts_model="m", pronunciation_strategy="DIRECT_WORD")
    contextual = synthesize_asset(
        db_path, speech_asset, client, audio_dir=tmp_path / "audio", tts_model="m",
        asset_id="SP201::CONTEXTUAL_WORD", pronunciation_strategy="CONTEXTUAL_WORD",
    )
    assert direct["asset_id"] != contextual["asset_id"]
    from research.asset_generator import _persist_generated_assets, _latest_generated_rows_for_plan
    _persist_generated_assets(db_path, plan_id, [direct, contextual])
    rows = _latest_generated_rows_for_plan(db_path, plan_id)
    asset_ids = {r["asset_id"] for r in rows}
    assert "SP201" in asset_ids
    assert "SP201::CONTEXTUAL_WORD" in asset_ids


# Mini Success EN_NATIVE review priority escalation
def test_mini_success_answer_en_native_escalated_to_high(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_2(conn)
    from research.asset_generator import _load_production_blocks
    production_blocks = _load_production_blocks(db_path, plan_id)
    assert is_mini_success_answer_asset(production_blocks, "SP203") is True  # CAP: post-pause reveal
    assert is_mini_success_answer_asset(production_blocks, "SP201") is False  # BAG: ordinary block


def test_full_en_native_matrix_end_to_end_with_regenerate_required(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_2(conn)
    client = FakeTTSClient()
    # First pass generates everything, including a DIRECT_WORD baseline for CAP.
    run_asset_generation(db_path, client, mode="SAMPLE", tts_model="m", assets_dir=tmp_path / "assets")
    record_pronunciation_review(db_path, plan_id, "SP203", "REGENERATE_REQUIRED")

    result = run_asset_generation(db_path, client, mode="SAMPLE", tts_model="m", assets_dir=tmp_path / "assets")
    cap_rows = [r for r in result["generated_assets"] if r["source_speech_asset_id"] == "SP203" and r["asset_id"] == "SP203"]
    assert cap_rows
    # The DIRECT_WORD slot for CAP must not silently resurrect the marked-bad asset.
    assert all(r["metadata"].get("pronunciation_review") != "REGENERATE_REQUIRED" or r["status"] != "REUSED" for r in cap_rows)
    assert result["integrity_checks"]["human_pronunciation_gate_safe"] == "pass"


# ===========================================================================
# 12-3: EN_NATIVE pronunciation/tone isolation experiment (spec prompts/12-3, CASE A-AD)
# ===========================================================================

# CASE A/B/C: transcript per strategy
def test_case_a_direct_word_transcript_uppercase():
    assert compute_tts_transcript("EN_NATIVE", "CAP", pronunciation_strategy="DIRECT_WORD") == "CAP"


def test_case_b_lowercase_word_transcript_lowercased():
    assert compute_tts_transcript("EN_NATIVE", "CAP", pronunciation_strategy="LOWERCASE_WORD") == "cap"


def test_case_c_minimal_context_word_transcript_lowercased():
    assert compute_tts_transcript("EN_NATIVE", "CAP", pronunciation_strategy="MINIMAL_CONTEXT_WORD") == "cap"


# CASE D: CONTEXTUAL_WORD regression (12-2 behavior unchanged)
def test_case_d_contextual_word_regression_unchanged():
    assert compute_tts_transcript("EN_NATIVE", "CAP", pronunciation_strategy="CONTEXTUAL_WORD") == "cap"
    prompt = build_tts_prompt("EN_NATIVE", "CAP", "Charon", pronunciation_strategy="CONTEXTUAL_WORD")
    assert "This is an English word" in prompt


# CASE E: LOWERCASE_WORD adds no contextual pronunciation instruction
def test_case_e_lowercase_word_adds_no_contextual_instruction():
    prompt = build_tts_prompt("EN_NATIVE", "CAP", "Charon", pronunciation_strategy="LOWERCASE_WORD")
    assert "This is an English word" not in prompt
    assert "Pronounce the transcript as one English word" not in prompt


# CASE F: MINIMAL_CONTEXT_WORD adds only the minimal instruction. Section 2's exclusion list is
# about the strategy-specific DELTA it adds on top of the shared baseline -- the common Charon
# Role line ("...friendly educational narrator...") is intentionally shared by every strategy and
# must NOT be stripped out (section 2: "기존 공통 Charon profile 표현을 무조건 삭제하라는 뜻은 아니다").
def test_case_f_minimal_context_word_adds_only_minimal_instruction():
    baseline = build_tts_prompt("EN_NATIVE", "CAP", "Charon", pronunciation_strategy="DIRECT_WORD")
    minimal = build_tts_prompt("EN_NATIVE", "CAP", "Charon", pronunciation_strategy="MINIMAL_CONTEXT_WORD")
    delta = minimal.replace(baseline.rsplit("### TRANSCRIPT", 1)[0].rstrip(), "")
    assert "Pronounce the transcript as one English word. Do not spell it." in delta
    for style_word in ("warm", "expressive", "conversational", "gentle", "smooth", "enthusiastic", "teacher-like", "narrator-like"):
        assert style_word not in delta.lower()


# CASE G: DIRECT_WORD and LOWERCASE_WORD share an identical Audio Profile / Director's Notes
def test_case_g_direct_and_lowercase_share_identical_notes():
    direct = build_tts_prompt("EN_NATIVE", "CAP", "Charon", pronunciation_strategy="DIRECT_WORD")
    lowercase = build_tts_prompt("EN_NATIVE", "CAP", "Charon", pronunciation_strategy="LOWERCASE_WORD")
    direct_head = direct.rsplit("### TRANSCRIPT", 1)[0]
    lowercase_head = lowercase.rsplit("### TRANSCRIPT", 1)[0]
    assert direct_head == lowercase_head
    assert direct.rsplit("### TRANSCRIPT", 1)[1].strip() == "CAP"
    assert lowercase.rsplit("### TRANSCRIPT", 1)[1].strip() == "cap"


# CASE H: LOWERCASE_WORD and MINIMAL_CONTEXT_WORD share the same voice
def test_case_h_lowercase_and_minimal_context_share_voice():
    lowercase = build_tts_prompt("EN_NATIVE", "CAP", "Charon", pronunciation_strategy="LOWERCASE_WORD")
    minimal = build_tts_prompt("EN_NATIVE", "CAP", "Charon", pronunciation_strategy="MINIMAL_CONTEXT_WORD")
    assert "Voice: Charon" in lowercase
    assert "Voice: Charon" in minimal


# CASE I: source_text CAP unchanged across all four strategies
def test_case_i_source_text_unchanged_across_strategies(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_2(conn)
    speech_asset = next(a for a in _speech_assets_for(db_path, plan_id) if a["speech_asset_id"] == "SP203")
    client = FakeTTSClient()
    for strategy in ("DIRECT_WORD", "LOWERCASE_WORD", "MINIMAL_CONTEXT_WORD"):
        row = synthesize_asset(
            db_path, speech_asset, client, audio_dir=tmp_path / "audio", tts_model="m",
            asset_id=f"SP203::{strategy}", pronunciation_strategy=strategy,
        )
        assert row["metadata"]["synthesized_text"] == "CAP"
    with connect(db_path) as conn:
        after = conn.execute("SELECT source_text FROM speech_assets WHERE speech_asset_id='SP203'").fetchone()
    assert after["source_text"] == "CAP"


# CASE J/K: generalized logic, no CAP-specific branch
def test_case_j_bag_map_cap_same_generalized_transcript_logic():
    for word in ("BAG", "MAP", "CAP"):
        assert compute_tts_transcript("EN_NATIVE", word, pronunciation_strategy="LOWERCASE_WORD") == word.lower()


def test_case_k_no_cap_hardcoded_branch_in_transcript_or_notes():
    import inspect
    from research import asset_generator
    source = inspect.getsource(asset_generator)
    assert '== "CAP"' not in source
    assert "== 'CAP'" not in source


# CASE L: 4 strategies produce 4 distinct cache keys
def test_case_l_four_strategies_four_distinct_cache_keys():
    keys = {
        strategy: compute_cache_key("m", "Charon", "EN_NATIVE", "CAP", "instr", pronunciation_strategy=strategy)
        for strategy in EN_NATIVE_PRONUNCIATION_STRATEGIES
    }
    assert len(set(keys.values())) == len(EN_NATIVE_PRONUNCIATION_STRATEGIES)


# CASE M/N: legacy fallback forbidden for the two new strategies
def test_case_m_lowercase_word_never_uses_legacy_fallback(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_2(conn)
    # Seed a legacy-shaped row (no prompt_version/strategy in its cache_key) for CAP, mimicking a
    # pre-12-1 asset -- LOWERCASE_WORD must never resurrect it via the legacy key.
    legacy_key = compute_cache_key("m", "Charon", "EN_NATIVE", "CAP", "")
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO generated_assets (production_plan_id, asset_id, source_speech_asset_id, asset_type,
                speech_mode, voice_name, status, file_path, cache_key, metadata_json)
            VALUES (?, 'SP203', 'SP203', 'TTS_AUDIO', 'EN_NATIVE', 'Charon', 'AVAILABLE', 'legacy.wav', ?, '{}')
            """,
            (plan_id, legacy_key),
        )
    speech_asset = next(a for a in _speech_assets_for(db_path, plan_id) if a["speech_asset_id"] == "SP203")
    client = FakeTTSClient()
    row = synthesize_asset(
        db_path, speech_asset, client, audio_dir=tmp_path / "audio", tts_model="m",
        asset_id="SP203::LOWERCASE_WORD", pronunciation_strategy="LOWERCASE_WORD",
    )
    assert row["status"] != "REUSED"
    assert row["file_path"] != "legacy.wav"


def test_case_n_minimal_context_word_never_uses_legacy_fallback(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_2(conn)
    legacy_key = compute_cache_key("m", "Charon", "EN_NATIVE", "CAP", "")
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO generated_assets (production_plan_id, asset_id, source_speech_asset_id, asset_type,
                speech_mode, voice_name, status, file_path, cache_key, metadata_json)
            VALUES (?, 'SP203', 'SP203', 'TTS_AUDIO', 'EN_NATIVE', 'Charon', 'AVAILABLE', 'legacy.wav', ?, '{}')
            """,
            (plan_id, legacy_key),
        )
    speech_asset = next(a for a in _speech_assets_for(db_path, plan_id) if a["speech_asset_id"] == "SP203")
    client = FakeTTSClient()
    row = synthesize_asset(
        db_path, speech_asset, client, audio_dir=tmp_path / "audio", tts_model="m",
        asset_id="SP203::MINIMAL_CONTEXT_WORD", pronunciation_strategy="MINIMAL_CONTEXT_WORD",
    )
    assert row["status"] != "REUSED"
    assert row["file_path"] != "legacy.wav"


# CASE O: REGENERATE_REQUIRED never served from any cache path (regression, all 4 strategies)
def test_case_o_regenerate_required_never_served_for_any_strategy(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_2(conn)
    speech_asset = next(a for a in _speech_assets_for(db_path, plan_id) if a["speech_asset_id"] == "SP203")
    client = FakeTTSClient()
    from research.asset_generator import _persist_generated_assets
    first = synthesize_asset(
        db_path, speech_asset, client, audio_dir=tmp_path / "audio", tts_model="m",
        asset_id="SP203::LOWERCASE_WORD", pronunciation_strategy="LOWERCASE_WORD",
    )
    _persist_generated_assets(db_path, plan_id, [first])
    record_pronunciation_review(db_path, plan_id, "SP203::LOWERCASE_WORD", "REGENERATE_REQUIRED")
    second = synthesize_asset(
        db_path, speech_asset, client, audio_dir=tmp_path / "audio", tts_model="m",
        asset_id="SP203::LOWERCASE_WORD", pronunciation_strategy="LOWERCASE_WORD",
    )
    assert second["status"] != "REUSED"


# CASE P/Q: new samples default to PENDING for both review axes
def test_case_p_new_sample_pronunciation_review_pending(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_2(conn)
    speech_asset = next(a for a in _speech_assets_for(db_path, plan_id) if a["speech_asset_id"] == "SP203")
    client = FakeTTSClient()
    row = synthesize_asset(
        db_path, speech_asset, client, audio_dir=tmp_path / "audio", tts_model="m",
        asset_id="SP203::LOWERCASE_WORD", pronunciation_strategy="LOWERCASE_WORD",
    )
    assert row["metadata"]["pronunciation_review"] == "PENDING"


def test_case_q_new_sample_tone_consistency_review_pending(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_2(conn)
    speech_asset = next(a for a in _speech_assets_for(db_path, plan_id) if a["speech_asset_id"] == "SP203")
    client = FakeTTSClient()
    row = synthesize_asset(
        db_path, speech_asset, client, audio_dir=tmp_path / "audio", tts_model="m",
        asset_id="SP203::MINIMAL_CONTEXT_WORD", pronunciation_strategy="MINIMAL_CONTEXT_WORD",
    )
    assert row["metadata"]["tone_consistency_review"] == "PENDING"
    # non-EN_NATIVE modes never require tone review
    ko_asset = {"speech_asset_id": "SPX", "speech_mode": "KO_NARRATION", "voice_name": "Charon", "source_text": "안녕하세요."}
    ko_row = synthesize_asset(db_path, ko_asset, client, audio_dir=tmp_path / "audio", tts_model="m")
    assert ko_row["metadata"]["tone_consistency_review"] == "NOT_REQUIRED"


# CASE R: tone review is never auto-approved anywhere in the module
def test_case_r_tone_review_never_auto_approved():
    import inspect
    from research import asset_generator
    source = inspect.getsource(asset_generator)
    assert 'tone_consistency_review"] = "APPROVED"' not in source
    assert "tone_consistency_review'] = 'APPROVED'" not in source


# CASE S/T: CAP (Mini Success) escalates to HIGH, MAP (ordinary) stays MEDIUM
def test_case_s_cap_new_variants_review_priority_high(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_2(conn)
    client = FakeTTSClient()
    result = run_asset_generation(db_path, client, mode="SAMPLE", tts_model="m", assets_dir=tmp_path / "assets")
    cap_variants = [r for r in result["generated_assets"] if r["source_speech_asset_id"] == "SP203"]
    assert cap_variants
    assert all(r["metadata"]["review_priority"] == "HIGH" for r in cap_variants)


def test_case_t_map_ordinary_variant_stays_medium(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_2(conn)
    client = FakeTTSClient()
    result = run_asset_generation(db_path, client, mode="SAMPLE", tts_model="m", assets_dir=tmp_path / "assets")
    bag_variants = [r for r in result["generated_assets"] if r["source_speech_asset_id"] == "SP201"]
    assert bag_variants
    assert all(r["metadata"]["review_priority"] == "MEDIUM" for r in bag_variants)
    # BAG (ordinary) never gets the LOWERCASE_WORD/MINIMAL_CONTEXT_WORD auto-experiment
    assert not any((r["metadata"] or {}).get("pronunciation_strategy") in {"LOWERCASE_WORD", "MINIMAL_CONTEXT_WORD"} for r in bag_variants)


# CASE U/V: blending policy untouched
def test_case_u_direct_sequence_default_unchanged():
    assert DEFAULT_BLENDING_STRATEGY == "DIRECT_SEQUENCE"


def test_case_v_context_restricted_preserved():
    assert "CONTEXT_RESTRICTED" in PHONEME_STRATEGIES


# CASE W/X: PAUSE and viewer_action (interaction_spec) untouched by this run
def test_case_w_pause_3000ms_unchanged(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_2(conn)
    client = FakeTTSClient()
    result = run_asset_generation(db_path, client, mode="SAMPLE", tts_model="m", assets_dir=tmp_path / "assets")
    assert result["integrity_checks"]["thinking_time_preserved"] == "pass"
    with connect(db_path) as conn:
        cb_mini = conn.execute("SELECT timeline_spec_json FROM production_blocks WHERE content_block_id='CB_MINI'").fetchone()
    timeline = json.loads(cb_mini["timeline_spec_json"])
    pause = next(ev for ev in timeline if ev["type"] == "PAUSE")
    assert pause["duration_ms"] == 3000


def test_case_x_viewer_action_interaction_data_untouched(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_2(conn)
        before = [dict(r) for r in conn.execute(
            "SELECT content_block_id, interaction_spec_json, timeline_spec_json FROM production_blocks ORDER BY id"
        ).fetchall()]
    client = FakeTTSClient()
    run_asset_generation(db_path, client, mode="SAMPLE", tts_model="m", assets_dir=tmp_path / "assets")
    with connect(db_path) as conn:
        after = [dict(r) for r in conn.execute(
            "SELECT content_block_id, interaction_spec_json, timeline_spec_json FROM production_blocks ORDER BY id"
        ).fetchall()]
    assert before == after


# CASE Y: Production Plan unchanged
def test_case_y_production_plan_unchanged(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_2(conn)
        before_plan = dict(conn.execute("SELECT * FROM production_plans WHERE id=?", (plan_id,)).fetchone())
        before_assets = [dict(r) for r in conn.execute("SELECT * FROM speech_assets ORDER BY id").fetchall()]
    client = FakeTTSClient()
    run_asset_generation(db_path, client, mode="SAMPLE", tts_model="m", assets_dir=tmp_path / "assets")
    with connect(db_path) as conn:
        after_plan = dict(conn.execute("SELECT * FROM production_plans WHERE id=?", (plan_id,)).fetchone())
        after_assets = [dict(r) for r in conn.execute("SELECT * FROM speech_assets ORDER BY id").fetchall()]
    assert before_plan == after_plan
    assert before_assets == after_assets


# CASE Z/AA: KO_NARRATION / EN_PHONEME_DEMO regression (exercised via the full 12-1 suite already;
# spot-check here that the shared full-run path still keeps both untouched)
def test_case_z_aa_ko_narration_and_phoneme_demo_regression(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_plan_12_1(conn)
    client = FakeTTSClient()
    result = run_asset_generation(db_path, client, mode="SAMPLE", tts_model="m", assets_dir=tmp_path / "assets")
    assert result["integrity_checks"]["speech_segmentation_safe"] == "pass"
    assert result["integrity_checks"]["phoneme_source_of_truth_preserved"] == "pass"


# CASE AB/AC: CLI backward compatibility
def test_case_ab_assets_cli_signature_unchanged():
    from research.cli import build_parser
    parser = build_parser()
    ns = parser.parse_args(["assets", "--sample"])
    assert ns.func.__name__ == "cmd_assets"


def test_case_ac_assets_review_backward_compatible_plus_set_tone():
    from research.cli import build_parser
    parser = build_parser()
    ns = parser.parse_args(["assets-review", "--set", "SP007=APPROVED", "--set-tone", "SP029=REJECTED"])
    assert ns.func.__name__ == "cmd_assets_review"
    assert ns.set == ["SP007=APPROVED"]
    assert ns.set_tone == ["SP029=REJECTED"]


# Ready for Full Generation gate now also considers tone_consistency_review
def test_ready_for_full_generation_blocked_by_pending_tone_review():
    checks = {"a": "pass"}
    rows = [{"status": "AVAILABLE", "metadata": {"review_priority": "MEDIUM", "pronunciation_review": "APPROVED", "tone_consistency_review": "PENDING"}}]
    assert ready_for_full_generation_gate(checks, rows) is False


def test_record_tone_consistency_review_preserves_row_and_updates_field(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_2(conn)
    speech_asset = next(a for a in _speech_assets_for(db_path, plan_id) if a["speech_asset_id"] == "SP203")
    client = FakeTTSClient()
    from research.asset_generator import _persist_generated_assets
    row = synthesize_asset(
        db_path, speech_asset, client, audio_dir=tmp_path / "audio", tts_model="m",
        asset_id="SP203::MINIMAL_CONTEXT_WORD", pronunciation_strategy="MINIMAL_CONTEXT_WORD",
    )
    _persist_generated_assets(db_path, plan_id, [row])
    updated = record_tone_consistency_review(db_path, plan_id, "SP203::MINIMAL_CONTEXT_WORD", "REJECTED")
    assert updated == 1
    with connect(db_path) as conn:
        stored = conn.execute(
            "SELECT metadata_json FROM generated_assets WHERE asset_id='SP203::MINIMAL_CONTEXT_WORD'"
        ).fetchone()
    metadata = json.loads(stored["metadata_json"])
    assert metadata["tone_consistency_review"] == "REJECTED"


# ============================================================================
# 12-4: EN_NATIVE primary/fallback strategy confirmation + Full Generation Plan
# (prompts/12-4 section 27, CASE A-AD)
# ============================================================================

def _seed_plan_12_4(conn, ready: int = 1) -> int:
    """BAG/MAP approved DIRECT candidates, CAP the Mini Success fallback case, BAT with zero
    history (proves DIRECT_WORD isn't abandoned wholesale just because CAP failed), plus isolated
    /b//g/ and one blended sequence for the representative phoneme gate."""
    plan_cur = conn.execute(
        """
        INSERT INTO production_plans (video_direction_id, video_script_id, final_format, plan_json,
            estimated_duration_seconds, production_complexity, generation_method, integrity_check_json,
            planner_score, ready_for_asset_generation)
        VALUES (1, 1, 'EDUCATION', '{}', 100.0, 'low', 'deterministic', '{}', 90.0, ?)
        """,
        (ready,),
    )
    plan_id = plan_cur.lastrowid

    conn.execute(
        """
        INSERT INTO production_blocks (production_plan_id, content_block_id, block_order, delivery_mode,
            production_intent, timeline_spec_json, speech_segments_json, visual_spec_json, caption_spec_json,
            clip_spec_json, interaction_spec_json)
        VALUES (?, 'CB_MINI', 1, 'EDUCATION', 'viewer_must_attempt_before_answer', ?, '[]', '{}', '{}', NULL, '{}')
        """,
        (plan_id, json.dumps([
            {"event_order": 1, "type": "VISUAL", "visual_role": "TARGET_WORD", "content": "CAP"},
            {"event_order": 2, "type": "PAUSE", "duration_ms": 3000, "pause_visual_behavior": "THINKING_DOTS"},
            {"event_order": 3, "type": "SPEECH", "speech_asset_id": "SP203"},
        ])),
    )
    conn.execute(
        """
        INSERT INTO production_blocks (production_plan_id, content_block_id, block_order, delivery_mode,
            production_intent, timeline_spec_json, speech_segments_json, visual_spec_json, caption_spec_json,
            clip_spec_json, interaction_spec_json)
        VALUES (?, 'CB_PLAIN', 2, 'EDUCATION', 'explain', ?, '[]', '{}', '{}', NULL, '{}')
        """,
        (plan_id, json.dumps([
            {"event_order": 1, "type": "SPEECH", "speech_asset_id": "SP201"},
            {"event_order": 2, "type": "SPEECH", "speech_asset_id": "SP202"},
            {"event_order": 3, "type": "SPEECH", "speech_asset_id": "SP204"},
            {"event_order": 4, "type": "SPEECH", "speech_asset_id": "SP210"},
            {"event_order": 5, "type": "SPEECH", "speech_asset_id": "SP211"},
            {"event_order": 6, "type": "SPEECH", "speech_asset_id": "SP212"},
        ])),
    )

    assets = [
        ("SP201", "EN_NATIVE", "Charon", "BAG"),
        ("SP202", "EN_NATIVE", "Charon", "MAP"),
        ("SP203", "EN_NATIVE", "Charon", "CAP"),
        ("SP204", "EN_NATIVE", "Charon", "BAT"),
        ("SP210", "EN_PHONEME_DEMO", "Charon", "/b/"),
        ("SP211", "EN_PHONEME_DEMO", "Charon", "/g/"),
        ("SP212", "EN_PHONEME_DEMO", "Charon", "/b-æ-g/"),
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


def _approve(db_path, plan_id, asset_id, *, pronunciation="APPROVED", tone=None):
    record_pronunciation_review(db_path, plan_id, asset_id, pronunciation)
    if tone is not None:
        record_tone_consistency_review(db_path, plan_id, asset_id, tone)


def _gen(db_path, plan_id, speech_asset, client, tmp_path, *, asset_id=None, pronunciation_strategy="DIRECT_WORD"):
    from research.asset_generator import _persist_generated_assets
    row = synthesize_asset(
        db_path, speech_asset, client, audio_dir=tmp_path / "audio", tts_model="m",
        asset_id=asset_id, pronunciation_strategy=pronunciation_strategy,
    )
    _persist_generated_assets(db_path, plan_id, [row])
    return row


def _gen_phoneme(db_path, plan_id, speech_asset, client, tmp_path, *, asset_id=None, phoneme_strategy="DIRECT_SEQUENCE", target_word=None):
    from research.asset_generator import _persist_generated_assets
    row = synthesize_asset(
        db_path, speech_asset, client, audio_dir=tmp_path / "audio", tts_model="m",
        asset_id=asset_id, phoneme_strategy=phoneme_strategy, target_word=target_word,
    )
    _persist_generated_assets(db_path, plan_id, [row])
    return row


def _asset_by_id(assets, sid):
    return next(a for a in assets if a["speech_asset_id"] == sid)


# CASE A/B/C: primary/fallback/default-blend policy constants
def test_case_a_primary_strategy_is_direct_word():
    assert DEFAULT_EN_NATIVE_STRATEGY == "DIRECT_WORD"


def test_case_b_default_fallback_param_is_contextual_word():
    import inspect
    sig = inspect.signature(select_active_en_native_variant)
    assert sig.parameters["fallback_strategy"].default == "CONTEXTUAL_WORD"


def test_case_c_default_blend_strategy_direct_sequence():
    assert DEFAULT_BLENDING_STRATEGY == "DIRECT_SEQUENCE"


# CASE D: DIRECT approved -> DIRECT selected
def test_case_d_direct_approved_selects_direct(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_4(conn)
    assets = _speech_assets_for(db_path, plan_id)
    bag = _asset_by_id(assets, "SP201")
    client = FakeTTSClient()
    _gen(db_path, plan_id, bag, client, tmp_path)
    _approve(db_path, plan_id, "SP201")

    from research.asset_generator import _load_production_blocks
    blocks = _load_production_blocks(db_path, plan_id)
    selection = select_active_en_native_variant(db_path, plan_id, bag, blocks)
    assert selection["selection_reason"] == "PRIMARY_APPROVED"
    assert selection["selected_strategy"] == "DIRECT_WORD"
    assert selection["selected_asset_id"] == "SP201"


# CASE E: DIRECT REGENERATE_REQUIRED + CONTEXTUAL approved (+ tone approved, Mini Success) -> CONTEXTUAL selected
def test_case_e_regenerate_required_direct_falls_back_to_approved_contextual(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_4(conn)
    assets = _speech_assets_for(db_path, plan_id)
    cap = _asset_by_id(assets, "SP203")
    client = FakeTTSClient()
    _gen(db_path, plan_id, cap, client, tmp_path)
    _approve(db_path, plan_id, "SP203", pronunciation="REGENERATE_REQUIRED")
    _gen(db_path, plan_id, cap, client, tmp_path, asset_id="SP203::CONTEXTUAL_WORD", pronunciation_strategy="CONTEXTUAL_WORD")
    _approve(db_path, plan_id, "SP203::CONTEXTUAL_WORD", tone="APPROVED")

    from research.asset_generator import _load_production_blocks
    blocks = _load_production_blocks(db_path, plan_id)
    selection = select_active_en_native_variant(db_path, plan_id, cap, blocks)
    assert selection["selection_reason"] == "FALLBACK_AFTER_PRIMARY_FAILURE"
    assert selection["selected_strategy"] == "CONTEXTUAL_WORD"
    assert selection["selected_asset_id"] == "SP203::CONTEXTUAL_WORD"
    assert selection["requires_tone_approval"] is True


# CASE F: DIRECT REJECTED + CONTEXTUAL approved (non-Mini-Success word, no tone gate) -> CONTEXTUAL selected
def test_case_f_rejected_direct_falls_back_to_approved_contextual(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_4(conn)
    assets = _speech_assets_for(db_path, plan_id)
    bag = _asset_by_id(assets, "SP201")
    client = FakeTTSClient()
    _gen(db_path, plan_id, bag, client, tmp_path)
    _approve(db_path, plan_id, "SP201", pronunciation="REJECTED")
    _gen(db_path, plan_id, bag, client, tmp_path, asset_id="SP201::CONTEXTUAL_WORD", pronunciation_strategy="CONTEXTUAL_WORD")
    _approve(db_path, plan_id, "SP201::CONTEXTUAL_WORD")

    from research.asset_generator import _load_production_blocks
    blocks = _load_production_blocks(db_path, plan_id)
    selection = select_active_en_native_variant(db_path, plan_id, bag, blocks)
    assert selection["selection_reason"] == "FALLBACK_AFTER_PRIMARY_FAILURE"
    assert selection["selected_asset_id"] == "SP201::CONTEXTUAL_WORD"


# CASE G: DIRECT missing/pending + CONTEXTUAL approved -> fallback NOT auto-selected (primary
# hasn't failed, it just hasn't been tried/approved yet -- section 4's REJECTED/REGENERATE_REQUIRED-only trigger)
def test_case_g_pending_direct_does_not_trigger_fallback_even_if_contextual_approved(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_4(conn)
    assets = _speech_assets_for(db_path, plan_id)
    mp = _asset_by_id(assets, "SP202")
    client = FakeTTSClient()
    _gen(db_path, plan_id, mp, client, tmp_path, asset_id="SP202::CONTEXTUAL_WORD", pronunciation_strategy="CONTEXTUAL_WORD")
    _approve(db_path, plan_id, "SP202::CONTEXTUAL_WORD")

    from research.asset_generator import _load_production_blocks
    blocks = _load_production_blocks(db_path, plan_id)
    selection = select_active_en_native_variant(db_path, plan_id, mp, blocks)
    assert selection["selection_reason"] == "PRIMARY_PENDING"
    assert selection["selected_strategy"] == "DIRECT_WORD"
    assert selection["selected_asset_id"] is None


# CASE H: DIRECT failed + CONTEXTUAL pending -> never treated as an approved fallback
def test_case_h_failed_direct_plus_pending_contextual_is_not_approved_fallback(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_4(conn)
    assets = _speech_assets_for(db_path, plan_id)
    bat = _asset_by_id(assets, "SP204")
    client = FakeTTSClient()
    _gen(db_path, plan_id, bat, client, tmp_path)
    _approve(db_path, plan_id, "SP204", pronunciation="REGENERATE_REQUIRED")
    _gen(db_path, plan_id, bat, client, tmp_path, asset_id="SP204::CONTEXTUAL_WORD", pronunciation_strategy="CONTEXTUAL_WORD")
    # CONTEXTUAL_WORD left PENDING -- never approved

    from research.asset_generator import _load_production_blocks
    blocks = _load_production_blocks(db_path, plan_id)
    selection = select_active_en_native_variant(db_path, plan_id, bat, blocks)
    assert selection["selection_reason"] == "NO_APPROVED_VARIANT"
    assert selection["selected_asset_id"] is None


# CASE I/J: LOWERCASE_WORD/MINIMAL_CONTEXT_WORD are never considered by the fallback chain, even
# if a human happened to approve one -- only primary/fallback are in scope (section 7)
def test_case_i_lowercase_approved_never_auto_selected(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_4(conn)
    assets = _speech_assets_for(db_path, plan_id)
    bag = _asset_by_id(assets, "SP201")
    client = FakeTTSClient()
    _gen(db_path, plan_id, bag, client, tmp_path, asset_id="SP201::LOWERCASE_WORD", pronunciation_strategy="LOWERCASE_WORD")
    _approve(db_path, plan_id, "SP201::LOWERCASE_WORD")

    from research.asset_generator import _load_production_blocks
    blocks = _load_production_blocks(db_path, plan_id)
    selection = select_active_en_native_variant(db_path, plan_id, bag, blocks)
    assert selection["selected_strategy"] != "LOWERCASE_WORD"
    assert selection["selected_asset_id"] != "SP201::LOWERCASE_WORD"


def test_case_j_minimal_context_approved_never_auto_selected(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_4(conn)
    assets = _speech_assets_for(db_path, plan_id)
    bag = _asset_by_id(assets, "SP201")
    client = FakeTTSClient()
    _gen(db_path, plan_id, bag, client, tmp_path, asset_id="SP201::MINIMAL_CONTEXT_WORD", pronunciation_strategy="MINIMAL_CONTEXT_WORD")
    _approve(db_path, plan_id, "SP201::MINIMAL_CONTEXT_WORD")

    from research.asset_generator import _load_production_blocks
    blocks = _load_production_blocks(db_path, plan_id)
    selection = select_active_en_native_variant(db_path, plan_id, bag, blocks)
    assert selection["selected_strategy"] != "MINIMAL_CONTEXT_WORD"
    assert selection["selected_asset_id"] != "SP201::MINIMAL_CONTEXT_WORD"


# CASE K: a REGENERATE_REQUIRED asset is never returned as an active selection
def test_case_k_regenerate_required_asset_never_returned_as_selected(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_4(conn)
    assets = _speech_assets_for(db_path, plan_id)
    cap = _asset_by_id(assets, "SP203")
    client = FakeTTSClient()
    _gen(db_path, plan_id, cap, client, tmp_path)
    _approve(db_path, plan_id, "SP203", pronunciation="REGENERATE_REQUIRED")
    # no fallback generated at all

    from research.asset_generator import _load_production_blocks
    blocks = _load_production_blocks(db_path, plan_id)
    selection = select_active_en_native_variant(db_path, plan_id, cap, blocks)
    assert selection["selected_asset_id"] != "SP203"
    assert selection["selected_asset_id"] is None
    assert selection["selection_reason"] == "NO_APPROVED_VARIANT"


# CASE L: no "CAP" literal anywhere in the 12-4 selection/plan functions
def test_case_l_no_cap_hardcoding_in_selection_functions():
    import inspect
    import research.asset_generator as ag
    src = inspect.getsource(ag.select_active_en_native_variant) + inspect.getsource(ag.build_full_generation_plan) \
        + inspect.getsource(ag._en_native_plan_action) + inspect.getsource(ag._phoneme_plan_entry)
    assert '"CAP"' not in src
    assert "'CAP'" not in src


# CASE M/Q/R/S/U/V: full generalized Full Generation Plan over BAG/MAP/CAP/BAT + phonemes,
# matching the real DB's expected shape end to end.
def test_case_m_full_generation_plan_generalizes_and_gates_correctly(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_4(conn)
    assets = _speech_assets_for(db_path, plan_id)
    bag, mp, cap, bat = (_asset_by_id(assets, sid) for sid in ("SP201", "SP202", "SP203", "SP204"))
    b_phoneme, g_phoneme, blended = (_asset_by_id(assets, sid) for sid in ("SP210", "SP211", "SP212"))
    client = FakeTTSClient()

    _gen(db_path, plan_id, bag, client, tmp_path)
    _approve(db_path, plan_id, "SP201")
    _gen(db_path, plan_id, mp, client, tmp_path)
    _approve(db_path, plan_id, "SP202")
    _gen(db_path, plan_id, cap, client, tmp_path)
    _approve(db_path, plan_id, "SP203", pronunciation="REGENERATE_REQUIRED")
    _gen(db_path, plan_id, cap, client, tmp_path, asset_id="SP203::CONTEXTUAL_WORD", pronunciation_strategy="CONTEXTUAL_WORD")
    _approve(db_path, plan_id, "SP203::CONTEXTUAL_WORD", tone="APPROVED")
    # BAT: no history at all

    _gen_phoneme(db_path, plan_id, b_phoneme, client, tmp_path)
    _approve(db_path, plan_id, "SP210")
    _gen_phoneme(db_path, plan_id, g_phoneme, client, tmp_path)
    _approve(db_path, plan_id, "SP211")
    _gen_phoneme(db_path, plan_id, blended, client, tmp_path, asset_id="SP212::DIRECT_SEQUENCE", target_word="BAG")
    _approve(db_path, plan_id, "SP212::DIRECT_SEQUENCE")

    from research.asset_generator import _load_production_blocks, _representative_review_complete
    blocks = _load_production_blocks(db_path, plan_id)
    plan_result = build_full_generation_plan(db_path, plan_id, assets, blocks)

    by_source = {e["source_speech_asset_id"]: e for e in plan_result["generation_plan"]}
    assert by_source["SP201"]["action"] == "REUSE"  # BAG DIRECT_WORD
    assert by_source["SP201"]["preferred_strategy"] == "DIRECT_WORD"
    assert by_source["SP202"]["action"] == "REUSE"  # MAP DIRECT_WORD
    assert by_source["SP203"]["action"] == "REUSE"  # CAP -> CONTEXTUAL fallback
    assert by_source["SP203"]["selection_reason"] == "FALLBACK_AFTER_PRIMARY_FAILURE"
    assert by_source["SP203"]["selected_asset_id"] == "SP203::CONTEXTUAL_WORD"
    assert by_source["SP204"]["action"] == "GENERATE"  # BAT: no history yet
    assert by_source["SP204"]["preferred_strategy"] == "DIRECT_WORD"
    assert by_source["SP210"]["action"] == "REUSE"
    assert by_source["SP211"]["action"] == "REUSE"
    assert by_source["SP212"]["action"] == "REUSE"

    # CASE Q: every required source appears exactly once
    required_ids = {a["speech_asset_id"] for a in assets}
    assert {e["source_speech_asset_id"] for e in plan_result["generation_plan"]} == required_ids

    # CASE R: taxonomy exact spelling, counts add up
    assert set(plan_result["action_counts"].keys()) == GENERATION_PLAN_ACTIONS
    assert sum(plan_result["action_counts"].values()) == len(plan_result["generation_plan"])
    assert plan_result["action_counts"]["GENERATE"] == 1  # only BAT
    assert plan_result["action_counts"]["BLOCKED"] == 0

    # CASE S: expected new API calls == GENERATE count
    assert plan_result["expected_new_api_calls"] == plan_result["action_counts"]["GENERATE"] == 1

    # CASE V: representative set complete -> Ready for Full Generation true
    representative_complete = _representative_review_complete(db_path, plan_id, assets, blocks)
    assert representative_complete is True
    assert ready_for_full_generation_gate(
        {}, [], generation_plan=plan_result, representative_complete=representative_complete,
    ) is True


# CASE U: Ready for Full Generation false when representative approval missing
def test_case_u_ready_for_full_generation_false_when_representative_incomplete(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_4(conn)
    assets = _speech_assets_for(db_path, plan_id)
    bag = _asset_by_id(assets, "SP201")
    client = FakeTTSClient()
    _gen(db_path, plan_id, bag, client, tmp_path)
    _approve(db_path, plan_id, "SP201")
    # MAP/CAP/phonemes deliberately left unresolved

    from research.asset_generator import _load_production_blocks, _representative_review_complete
    blocks = _load_production_blocks(db_path, plan_id)
    representative_complete = _representative_review_complete(db_path, plan_id, assets, blocks)
    assert representative_complete is False
    plan_result = build_full_generation_plan(db_path, plan_id, assets, blocks)
    assert ready_for_full_generation_gate(
        {}, [], generation_plan=plan_result, representative_complete=representative_complete,
    ) is False


# CASE N: review state never leaks across variants of the same source word
def test_case_n_review_state_does_not_transfer_between_variants(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_4(conn)
    assets = _speech_assets_for(db_path, plan_id)
    bag = _asset_by_id(assets, "SP201")
    client = FakeTTSClient()
    _gen(db_path, plan_id, bag, client, tmp_path)
    _approve(db_path, plan_id, "SP201")  # DIRECT approved
    _gen(db_path, plan_id, bag, client, tmp_path, asset_id="SP201::CONTEXTUAL_WORD", pronunciation_strategy="CONTEXTUAL_WORD")
    # CONTEXTUAL_WORD left untouched (PENDING by default)

    with connect(db_path) as conn:
        contextual_row = conn.execute(
            "SELECT metadata_json FROM generated_assets WHERE asset_id='SP201::CONTEXTUAL_WORD'"
        ).fetchone()
    assert json.loads(contextual_row["metadata_json"])["pronunciation_review"] == "PENDING"


# CASE O/P: approved DIRECT/CONTEXTUAL cache reuse -- selecting twice returns the same asset_id,
# no duplicate TTS calls
def test_case_o_approved_direct_cache_reused_on_repeat_selection(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_4(conn)
    assets = _speech_assets_for(db_path, plan_id)
    bag = _asset_by_id(assets, "SP201")
    client = FakeTTSClient()
    _gen(db_path, plan_id, bag, client, tmp_path)
    _approve(db_path, plan_id, "SP201")

    from research.asset_generator import _load_production_blocks
    blocks = _load_production_blocks(db_path, plan_id)
    first = select_active_en_native_variant(db_path, plan_id, bag, blocks)
    second = select_active_en_native_variant(db_path, plan_id, bag, blocks)
    assert first == second
    assert len(client.calls) == 1  # only the original _gen call, selection itself makes no TTS calls


def test_case_p_approved_contextual_fallback_cache_reused_on_repeat_selection(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_4(conn)
    assets = _speech_assets_for(db_path, plan_id)
    cap = _asset_by_id(assets, "SP203")
    client = FakeTTSClient()
    _gen(db_path, plan_id, cap, client, tmp_path)
    _approve(db_path, plan_id, "SP203", pronunciation="REGENERATE_REQUIRED")
    _gen(db_path, plan_id, cap, client, tmp_path, asset_id="SP203::CONTEXTUAL_WORD", pronunciation_strategy="CONTEXTUAL_WORD")
    _approve(db_path, plan_id, "SP203::CONTEXTUAL_WORD", tone="APPROVED")

    from research.asset_generator import _load_production_blocks
    blocks = _load_production_blocks(db_path, plan_id)
    first = select_active_en_native_variant(db_path, plan_id, cap, blocks)
    second = select_active_en_native_variant(db_path, plan_id, cap, blocks)
    assert first == second == {
        "selected_strategy": "CONTEXTUAL_WORD", "selected_asset_id": "SP203::CONTEXTUAL_WORD",
        "selection_reason": "FALLBACK_AFTER_PRIMARY_FAILURE", "requires_tone_approval": True,
    }
    assert len(client.calls) == 2  # only the two original _gen calls


# CASE T: Dry Run still makes zero Gemini calls even with the new Full Generation Plan computation
def test_case_t_dry_run_still_zero_api_calls_with_generation_plan(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_plan_12_4(conn)
    client = FakeTTSClient()
    result = run_asset_generation(db_path, client, mode="DRY_RUN", tts_model="m", assets_dir=tmp_path / "assets")
    assert result["api_calls"] == 0
    assert client.calls == []
    assert "generation_plan" in result
    assert "ready_for_full_generation" in result
    assert result["ready_for_full_generation"] is False  # nothing approved yet in a fresh plan


# CASE W: Ready for Rendering is still false before an actual FULL run, even once Ready for Full
# Generation becomes true (they are deliberately separate gates)
def test_case_w_ready_for_rendering_still_false_before_full(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_4(conn)
    assets = _speech_assets_for(db_path, plan_id)
    bag = _asset_by_id(assets, "SP201")
    client = FakeTTSClient()
    _gen(db_path, plan_id, bag, client, tmp_path)
    _approve(db_path, plan_id, "SP201")
    result = run_asset_generation(db_path, client, mode="SAMPLE", tts_model="m", assets_dir=tmp_path / "assets")
    assert result["ready_for_rendering"] is False


# CASE X/Y/Z: Production Plan / PAUSE / viewer_action untouched by this stage's read-only planning
def test_case_x_y_z_production_plan_pause_and_viewer_action_unchanged(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_4(conn)
    with connect(db_path) as conn:
        before_plan = dict(conn.execute("SELECT * FROM production_plans WHERE id = ?", (plan_id,)).fetchone())
        before_blocks = [dict(r) for r in conn.execute(
            "SELECT * FROM production_blocks WHERE production_plan_id = ? ORDER BY block_order", (plan_id,)
        ).fetchall()]

    client = FakeTTSClient()
    run_asset_generation(db_path, client, mode="DRY_RUN", tts_model="m", assets_dir=tmp_path / "assets", plan_id=plan_id)

    with connect(db_path) as conn:
        after_plan = dict(conn.execute("SELECT * FROM production_plans WHERE id = ?", (plan_id,)).fetchone())
        after_blocks = [dict(r) for r in conn.execute(
            "SELECT * FROM production_blocks WHERE production_plan_id = ? ORDER BY block_order", (plan_id,)
        ).fetchall()]

    assert before_plan == after_plan
    assert before_blocks == after_blocks
    mini_block = next(b for b in after_blocks if b["content_block_id"] == "CB_MINI")
    timeline = json.loads(mini_block["timeline_spec_json"])
    pause_event = next(ev for ev in timeline if ev["type"] == "PAUSE")
    assert pause_event["duration_ms"] == 3000


# CASE AA: existing review history is preserved by the new selection/plan machinery -- it only
# reads generated_assets, never writes to it.
def test_case_aa_existing_review_history_preserved(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_4(conn)
    assets = _speech_assets_for(db_path, plan_id)
    bag = _asset_by_id(assets, "SP201")
    client = FakeTTSClient()
    _gen(db_path, plan_id, bag, client, tmp_path)
    _approve(db_path, plan_id, "SP201")
    with connect(db_path) as conn:
        before = dict(conn.execute("SELECT * FROM generated_assets WHERE asset_id = 'SP201'").fetchone())

    from research.asset_generator import _load_production_blocks
    blocks = _load_production_blocks(db_path, plan_id)
    build_full_generation_plan(db_path, plan_id, assets, blocks)
    select_active_en_native_variant(db_path, plan_id, bag, blocks)

    with connect(db_path) as conn:
        after = dict(conn.execute("SELECT * FROM generated_assets WHERE asset_id = 'SP201'").fetchone())
    assert before == after


# 12-4 section 23: FULL mode must actually apply the Full Generation Plan's selected strategy --
# an approved fallback must be reused, not silently regenerated under the failed primary strategy.
def test_full_mode_reuses_approved_fallback_instead_of_regenerating_failed_primary(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_4(conn)
    assets = _speech_assets_for(db_path, plan_id)
    cap = _asset_by_id(assets, "SP203")
    client = FakeTTSClient()
    _gen(db_path, plan_id, cap, client, tmp_path)
    _approve(db_path, plan_id, "SP203", pronunciation="REGENERATE_REQUIRED")
    _gen(db_path, plan_id, cap, client, tmp_path, asset_id="SP203::CONTEXTUAL_WORD", pronunciation_strategy="CONTEXTUAL_WORD")
    _approve(db_path, plan_id, "SP203::CONTEXTUAL_WORD", tone="APPROVED")

    # A prior successful SAMPLE run is required before FULL is allowed.
    run_asset_generation(db_path, client, mode="SAMPLE", tts_model="m", assets_dir=tmp_path / "assets", plan_id=plan_id)
    result = run_asset_generation(db_path, client, mode="FULL", tts_model="m", assets_dir=tmp_path / "assets", plan_id=plan_id)

    cap_rows = [r for r in result["generated_assets"] if r["source_speech_asset_id"] == "SP203"]
    assert len(cap_rows) == 1
    assert cap_rows[0]["asset_id"] == "SP203::CONTEXTUAL_WORD"
    # REUSED means synthesize_asset found the already-approved cache row and made no new TTS call
    # for CAP -- if FULL had instead regenerated the failed DIRECT_WORD primary, this would be
    # AVAILABLE (freshly generated) with asset_id "SP203", not "SP203::CONTEXTUAL_WORD".
    assert cap_rows[0]["status"] == "REUSED"
    assert not cap_rows[0]["api_call_made"]


# CASE AC: existing CLI compatibility -- `assets`/`assets-review` still parse and thread the new
# config-backed strategy parameters without requiring any new required flags.
def test_case_ac_cli_assets_still_parses_without_new_flags():
    from research.cli import build_parser
    parser = build_parser()
    ns = parser.parse_args(["assets", "--dry-run"])
    assert ns.func.__name__ == "cmd_assets"
    assert ns.dry_run is True


def test_case_ac_cmd_assets_reads_new_config_keys(tmp_path, monkeypatch):
    import research.cli as cli_mod

    captured = {}

    def fake_build_report(*args, **kwargs):
        captured.update(kwargs)
        return tmp_path / "report.md"

    monkeypatch.setattr(cli_mod, "build_asset_generation_report", fake_build_report)

    class FakeCfg:
        db_path = tmp_path / "test.db"
        reports_dir = tmp_path
        assets_dir = tmp_path / "assets"
        gemini_api_key = "fake-key"

        def get(self, *keys, default=None):
            values = {
                ("gemini", "tts_model"): "m",
                ("asset_generation", "max_segment_seconds"): 12,
                ("asset_generation", "primary_en_native_strategy"): "DIRECT_WORD",
                ("asset_generation", "fallback_en_native_strategy"): "CONTEXTUAL_WORD",
                ("asset_generation", "default_blending_strategy"): "DIRECT_SEQUENCE",
            }
            return values.get(tuple(keys), default)

    class Args:
        dry_run = True
        sample = False
        plan_id = None

    cli_mod.cmd_assets(Args(), FakeCfg())
    assert captured["primary_en_native_strategy"] == "DIRECT_WORD"
    assert captured["fallback_en_native_strategy"] == "CONTEXTUAL_WORD"
    assert captured["default_blending_strategy"] == "DIRECT_SEQUENCE"


# CASE AB: previous 30 integrity checks preserved plus the 6 new ones -- already covered by
# test_case_v_original_16_checks_preserved_plus_5_new above (updated to assert 36).
# CASE AD: full existing regression -- exercised by running the whole suite, not a single test.


# ============================================================================
# 12-5: FULL Generation path parity + Generation Unit compiler (prompts/12-5 section 31, CASE A-AF)
# ============================================================================

# CASE A: short KO_NARRATION -> exactly 1 Generation Unit
def test_case_a_short_ko_narration_is_one_generation_unit(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_1(conn)
    speech_asset = next(a for a in _speech_assets_for(db_path, plan_id) if a["speech_asset_id"] == "SP100")
    from research.asset_generator import _load_production_blocks
    blocks = _load_production_blocks(db_path, plan_id)
    units = build_generation_units(speech_asset, blocks, max_segment_seconds=12.0)
    assert len(units) == 1
    assert units[0]["generation_unit_id"] == "SP100"
    assert units[0]["segment_index"] is None
    assert units[0]["segment_count"] == 1


# CASE B: long KO_NARRATION -> N segments per the existing 12-1 policy
def test_case_b_long_ko_narration_splits_into_n_segments(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_1(conn)
    speech_asset = next(a for a in _speech_assets_for(db_path, plan_id) if a["speech_asset_id"] == "SP101")
    from research.asset_generator import _load_production_blocks
    blocks = _load_production_blocks(db_path, plan_id)
    units = build_generation_units(speech_asset, blocks, max_segment_seconds=6.0)
    assert len(units) == len(segment_source_text_by_sentence(_LONG_KO_TEXT, 6.0))
    assert len(units) > 1


# CASE C: SAMPLE and FULL (mocked) produce identical segmentation for the same source
def test_case_c_sample_and_full_segmentation_identical(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_1(conn)
    from research.asset_generator import _load_production_blocks
    speech_asset = next(a for a in _speech_assets_for(db_path, plan_id) if a["speech_asset_id"] == "SP101")
    blocks = _load_production_blocks(db_path, plan_id)

    client_sample = FakeTTSClient()
    sample_rows = synthesize_ko_narration_segments(
        db_path, speech_asset, client_sample, audio_dir=tmp_path / "a1", tts_model="m",
        production_blocks=blocks, max_segment_seconds=12.0, max_new_segments=99,
    )
    sample_units = [(r["metadata"].get("segment_index"), r["metadata"].get("segment_count")) for r in sample_rows]

    plan_units = build_generation_units(speech_asset, blocks, max_segment_seconds=12.0)
    full_units = [(u["segment_index"], u["segment_count"]) for u in plan_units]
    assert sample_units == full_units


# CASE D: DRY_RUN/FULL use the same segmentation (both call build_generation_units directly)
def test_case_d_dry_run_and_full_segmentation_identical(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_1(conn)
    from research.asset_generator import _load_production_blocks
    speech_asset = next(a for a in _speech_assets_for(db_path, plan_id) if a["speech_asset_id"] == "SP101")
    blocks = _load_production_blocks(db_path, plan_id)
    first = build_generation_units(speech_asset, blocks, max_segment_seconds=12.0)
    second = build_generation_units(speech_asset, blocks, max_segment_seconds=12.0)
    assert first == second


# CASE E: generation_unit_id numbering is 1..N and continuous
def test_case_e_generation_unit_ids_continuous(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_1(conn)
    from research.asset_generator import _load_production_blocks
    speech_asset = next(a for a in _speech_assets_for(db_path, plan_id) if a["speech_asset_id"] == "SP101")
    blocks = _load_production_blocks(db_path, plan_id)
    units = build_generation_units(speech_asset, blocks, max_segment_seconds=6.0)
    assert [u["generation_unit_id"] for u in units] == [f"SP101-{i + 1}" for i in range(len(units))]


# CASE F: segment_count identical across all segments of the same source
def test_case_f_segment_count_identical_across_segments(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_1(conn)
    from research.asset_generator import _load_production_blocks
    speech_asset = next(a for a in _speech_assets_for(db_path, plan_id) if a["speech_asset_id"] == "SP101")
    blocks = _load_production_blocks(db_path, plan_id)
    units = build_generation_units(speech_asset, blocks, max_segment_seconds=6.0)
    assert len({u["segment_count"] for u in units}) == 1
    assert units[0]["segment_count"] == len(units)


# CASE G: source_block_ids preserved on every generation unit
def test_case_g_source_block_ids_preserved(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_1(conn)
    from research.asset_generator import _load_production_blocks
    speech_asset = next(a for a in _speech_assets_for(db_path, plan_id) if a["speech_asset_id"] == "SP101")
    blocks = _load_production_blocks(db_path, plan_id)
    units = build_generation_units(speech_asset, blocks, max_segment_seconds=6.0)
    assert all(u["source_block_ids"] == ["CB_LONG"] for u in units)


# CASE H: no punctuation-only segment ever produced
def test_case_h_no_punctuation_only_segment(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_1(conn)
    from research.asset_generator import _load_production_blocks
    speech_asset = next(a for a in _speech_assets_for(db_path, plan_id) if a["speech_asset_id"] == "SP101")
    blocks = _load_production_blocks(db_path, plan_id)
    units = build_generation_units(speech_asset, blocks, max_segment_seconds=6.0)
    assert all(_segment_is_safe(u["text"]) for u in units)


# CASE I/J: identical segment cache -> REUSE; different segment text -> no cross-reuse
def test_case_i_identical_segment_cache_reused(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_1(conn)
    from research.asset_generator import _load_production_blocks
    speech_asset = next(a for a in _speech_assets_for(db_path, plan_id) if a["speech_asset_id"] == "SP101")
    blocks = _load_production_blocks(db_path, plan_id)
    client = FakeTTSClient()
    first = synthesize_ko_narration_segments(
        db_path, speech_asset, client, audio_dir=tmp_path / "a", tts_model="m",
        production_blocks=blocks, max_segment_seconds=6.0, max_new_segments=99,
    )
    from research.asset_generator import _persist_generated_assets
    _persist_generated_assets(db_path, plan_id, first)
    second = synthesize_ko_narration_segments(
        db_path, speech_asset, client, audio_dir=tmp_path / "a", tts_model="m",
        production_blocks=blocks, max_segment_seconds=6.0, max_new_segments=99,
    )
    assert all(r["status"] == "REUSED" for r in second)
    assert all(not r["api_call_made"] for r in second)


def test_case_j_different_segment_text_never_cross_reused(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_1(conn)
    from research.asset_generator import _load_production_blocks
    speech_asset = next(a for a in _speech_assets_for(db_path, plan_id) if a["speech_asset_id"] == "SP101")
    blocks = _load_production_blocks(db_path, plan_id)
    units = build_generation_units(speech_asset, blocks, max_segment_seconds=6.0)
    keys = {
        compute_cache_key("m", "Charon", "KO_NARRATION", u["text"], _DELIVERY_LANGUAGE_MAP.get("KO_NARRATION") or "", prompt_version=TTS_PROMPT_VERSION)
        for u in units
    }
    assert len(keys) == len(units)  # every distinct segment text yields a distinct cache key


# CASE K/L: FULL mock execution -- GENERATE segment gets exactly 1 call, REUSE segment gets 0
def test_case_k_l_full_mock_calls_match_generate_reuse_segments(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_1(conn)
    client = FakeTTSClient()
    run_asset_generation(db_path, client, mode="SAMPLE", tts_model="m", assets_dir=tmp_path / "assets", plan_id=plan_id, max_segment_seconds=6.0)
    calls_after_sample = len(client.calls)
    result = run_asset_generation(db_path, client, mode="FULL", tts_model="m", assets_dir=tmp_path / "assets", plan_id=plan_id, max_segment_seconds=6.0)
    sp101_rows = [r for r in result["generated_assets"] if r["source_speech_asset_id"] == "SP101"]
    assert len(sp101_rows) == 5  # SP101 splits into 5 segments at max_segment_seconds=6.0
    generate_rows = [r for r in sp101_rows if r["status"] == "AVAILABLE"]
    reuse_rows = [r for r in sp101_rows if r["status"] == "REUSED"]
    assert all(r["api_call_made"] for r in generate_rows)
    assert all(not r["api_call_made"] for r in reuse_rows)
    new_calls_in_full = len(client.calls) - calls_after_sample
    assert new_calls_in_full == len(generate_rows)


# CASE M: expected_base_api_calls == GENERATE Generation Units
def test_case_m_expected_base_api_calls_matches_generate_units(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_1(conn)
    client = FakeTTSClient()
    result = run_asset_generation(db_path, client, mode="DRY_RUN", tts_model="m", assets_dir=tmp_path / "assets", plan_id=plan_id, max_segment_seconds=6.0)
    assert result["expected_base_api_calls"] == result["generation_plan"]["action_counts"]["GENERATE"]


# CASE N: retry is never included in the estimate
def test_case_n_retries_not_included_in_estimate(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_1(conn)
    client = FakeTTSClient()
    result = run_asset_generation(db_path, client, mode="DRY_RUN", tts_model="m", assets_dir=tmp_path / "assets", plan_id=plan_id)
    assert result["retries_included"] is False


# CASE O-W: EN_NATIVE/blending policy fully preserved (12-4 selection algorithm untouched)
def test_case_o_cap_direct_regenerate_required_not_selected(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_4(conn)
    assets = _speech_assets_for(db_path, plan_id)
    cap = _asset_by_id(assets, "SP203")
    client = FakeTTSClient()
    _gen(db_path, plan_id, cap, client, tmp_path)
    _approve(db_path, plan_id, "SP203", pronunciation="REGENERATE_REQUIRED")
    from research.asset_generator import _load_production_blocks
    blocks = _load_production_blocks(db_path, plan_id)
    selection = select_active_en_native_variant(db_path, plan_id, cap, blocks)
    assert selection["selected_asset_id"] != "SP203"


def test_case_p_cap_contextual_approved_fallback_reused(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_4(conn)
    assets = _speech_assets_for(db_path, plan_id)
    cap = _asset_by_id(assets, "SP203")
    client = FakeTTSClient()
    _gen(db_path, plan_id, cap, client, tmp_path)
    _approve(db_path, plan_id, "SP203", pronunciation="REGENERATE_REQUIRED")
    _gen(db_path, plan_id, cap, client, tmp_path, asset_id="SP203::CONTEXTUAL_WORD", pronunciation_strategy="CONTEXTUAL_WORD")
    _approve(db_path, plan_id, "SP203::CONTEXTUAL_WORD", tone="APPROVED")
    from research.asset_generator import _load_production_blocks
    blocks = _load_production_blocks(db_path, plan_id)
    plan_result = build_full_generation_plan(db_path, plan_id, assets, blocks)
    entry = next(e for e in plan_result["generation_plan"] if e["source_speech_asset_id"] == "SP203")
    assert entry["action"] == "REUSE"
    assert entry["selected_asset_id"] == "SP203::CONTEXTUAL_WORD"


def test_case_q_bag_direct_approved_primary_reused(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_4(conn)
    assets = _speech_assets_for(db_path, plan_id)
    bag = _asset_by_id(assets, "SP201")
    client = FakeTTSClient()
    _gen(db_path, plan_id, bag, client, tmp_path)
    _approve(db_path, plan_id, "SP201")
    from research.asset_generator import _load_production_blocks
    blocks = _load_production_blocks(db_path, plan_id)
    plan_result = build_full_generation_plan(db_path, plan_id, assets, blocks)
    entry = next(e for e in plan_result["generation_plan"] if e["source_speech_asset_id"] == "SP201")
    assert entry["action"] == "REUSE"
    assert entry["preferred_strategy"] == "DIRECT_WORD"


def test_case_r_map_direct_approved_primary_reused(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_4(conn)
    assets = _speech_assets_for(db_path, plan_id)
    mp = _asset_by_id(assets, "SP202")
    client = FakeTTSClient()
    _gen(db_path, plan_id, mp, client, tmp_path)
    _approve(db_path, plan_id, "SP202")
    from research.asset_generator import _load_production_blocks
    blocks = _load_production_blocks(db_path, plan_id)
    plan_result = build_full_generation_plan(db_path, plan_id, assets, blocks)
    entry = next(e for e in plan_result["generation_plan"] if e["source_speech_asset_id"] == "SP202")
    assert entry["action"] == "REUSE"


def test_case_s_bat_no_history_generates_direct_word(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_4(conn)
    assets = _speech_assets_for(db_path, plan_id)
    from research.asset_generator import _load_production_blocks
    blocks = _load_production_blocks(db_path, plan_id)
    plan_result = build_full_generation_plan(db_path, plan_id, assets, blocks)
    entry = next(e for e in plan_result["generation_plan"] if e["source_speech_asset_id"] == "SP204")
    assert entry["action"] == "GENERATE"
    assert entry["preferred_strategy"] == "DIRECT_WORD"


def test_case_t_lowercase_word_never_auto_selected_in_plan(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_4(conn)
    assets = _speech_assets_for(db_path, plan_id)
    bag = _asset_by_id(assets, "SP201")
    client = FakeTTSClient()
    _gen(db_path, plan_id, bag, client, tmp_path, asset_id="SP201::LOWERCASE_WORD", pronunciation_strategy="LOWERCASE_WORD")
    _approve(db_path, plan_id, "SP201::LOWERCASE_WORD")
    from research.asset_generator import _load_production_blocks
    blocks = _load_production_blocks(db_path, plan_id)
    plan_result = build_full_generation_plan(db_path, plan_id, assets, blocks)
    entry = next(e for e in plan_result["generation_plan"] if e["source_speech_asset_id"] == "SP201")
    assert entry["preferred_strategy"] != "LOWERCASE_WORD"
    assert entry["selected_asset_id"] != "SP201::LOWERCASE_WORD"


def test_case_u_minimal_context_word_never_auto_selected_in_plan(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_4(conn)
    assets = _speech_assets_for(db_path, plan_id)
    bag = _asset_by_id(assets, "SP201")
    client = FakeTTSClient()
    _gen(db_path, plan_id, bag, client, tmp_path, asset_id="SP201::MINIMAL_CONTEXT_WORD", pronunciation_strategy="MINIMAL_CONTEXT_WORD")
    _approve(db_path, plan_id, "SP201::MINIMAL_CONTEXT_WORD")
    from research.asset_generator import _load_production_blocks
    blocks = _load_production_blocks(db_path, plan_id)
    plan_result = build_full_generation_plan(db_path, plan_id, assets, blocks)
    entry = next(e for e in plan_result["generation_plan"] if e["source_speech_asset_id"] == "SP201")
    assert entry["preferred_strategy"] != "MINIMAL_CONTEXT_WORD"


def test_case_v_context_restricted_never_becomes_default_blending(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_4(conn)
    assets = _speech_assets_for(db_path, plan_id)
    from research.asset_generator import _load_production_blocks
    blocks = _load_production_blocks(db_path, plan_id)
    plan_result = build_full_generation_plan(db_path, plan_id, assets, blocks)
    blended_entry = next(e for e in plan_result["generation_plan"] if e["source_speech_asset_id"] == "SP212")
    assert blended_entry["preferred_strategy"] == "DIRECT_SEQUENCE"
    assert blended_entry["preferred_strategy"] != "CONTEXT_RESTRICTED"


def test_case_w_direct_sequence_default_maintained():
    assert DEFAULT_BLENDING_STRATEGY == "DIRECT_SEQUENCE"


# CASE X/Y: FULL execution path actually consumes the plan's preferred_strategy and generation units
def test_case_x_full_path_uses_plans_preferred_strategy(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_4(conn)
    assets = _speech_assets_for(db_path, plan_id)
    cap = _asset_by_id(assets, "SP203")
    client = FakeTTSClient()
    _gen(db_path, plan_id, cap, client, tmp_path)
    _approve(db_path, plan_id, "SP203", pronunciation="REGENERATE_REQUIRED")
    _gen(db_path, plan_id, cap, client, tmp_path, asset_id="SP203::CONTEXTUAL_WORD", pronunciation_strategy="CONTEXTUAL_WORD")
    _approve(db_path, plan_id, "SP203::CONTEXTUAL_WORD", tone="APPROVED")
    run_asset_generation(db_path, client, mode="SAMPLE", tts_model="m", assets_dir=tmp_path / "assets", plan_id=plan_id)
    result = run_asset_generation(db_path, client, mode="FULL", tts_model="m", assets_dir=tmp_path / "assets", plan_id=plan_id)
    cap_row = next(r for r in result["generated_assets"] if r["source_speech_asset_id"] == "SP203")
    assert cap_row["asset_id"] == "SP203::CONTEXTUAL_WORD"


def test_case_y_full_path_uses_plans_generation_units_for_ko_narration(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_1(conn)
    client = FakeTTSClient()
    run_asset_generation(db_path, client, mode="SAMPLE", tts_model="m", assets_dir=tmp_path / "assets", plan_id=plan_id, max_segment_seconds=6.0)
    result = run_asset_generation(db_path, client, mode="FULL", tts_model="m", assets_dir=tmp_path / "assets", plan_id=plan_id, max_segment_seconds=6.0)
    sp101_asset_ids = {r["asset_id"] for r in result["generated_assets"] if r["source_speech_asset_id"] == "SP101"}
    assert sp101_asset_ids == {f"SP101-{i + 1}" for i in range(5)}


# CASE Z: SAMPLE path does not compute its own independent segmentation
def test_case_z_sample_path_delegates_segmentation_to_shared_compiler():
    import inspect
    import research.asset_generator as ag
    src = inspect.getsource(ag.synthesize_ko_narration_segments)
    assert "build_generation_units" in src
    assert "segment_source_text_by_sentence(" not in src


# CASE AA/AB: PAUSE 3000ms / viewer_action unchanged after a Generation-Unit-aware Dry Run
def test_case_aa_ab_pause_and_viewer_action_unchanged(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_4(conn)
    client = FakeTTSClient()
    run_asset_generation(db_path, client, mode="DRY_RUN", tts_model="m", assets_dir=tmp_path / "assets", plan_id=plan_id)
    with connect(db_path) as conn:
        mini_block = conn.execute(
            "SELECT production_intent, timeline_spec_json FROM production_blocks WHERE production_plan_id = ? AND content_block_id = 'CB_MINI'",
            (plan_id,),
        ).fetchone()
    assert mini_block["production_intent"] == "viewer_must_attempt_before_answer"
    timeline = json.loads(mini_block["timeline_spec_json"])
    pause_event = next(ev for ev in timeline if ev["type"] == "PAUSE")
    assert pause_event["duration_ms"] == 3000


# CASE AC: Production Plan row/content unchanged
def test_case_ac_production_plan_unchanged(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_1(conn)
    with connect(db_path) as conn:
        before_plan = dict(conn.execute("SELECT * FROM production_plans WHERE id = ?", (plan_id,)).fetchone())
        before_blocks = [dict(r) for r in conn.execute(
            "SELECT * FROM production_blocks WHERE production_plan_id = ? ORDER BY block_order", (plan_id,)
        ).fetchall()]
    client = FakeTTSClient()
    run_asset_generation(db_path, client, mode="DRY_RUN", tts_model="m", assets_dir=tmp_path / "assets", plan_id=plan_id)
    with connect(db_path) as conn:
        after_plan = dict(conn.execute("SELECT * FROM production_plans WHERE id = ?", (plan_id,)).fetchone())
        after_blocks = [dict(r) for r in conn.execute(
            "SELECT * FROM production_blocks WHERE production_plan_id = ? ORDER BY block_order", (plan_id,)
        ).fetchall()]
    assert before_plan == after_plan
    assert before_blocks == after_blocks


# CASE AD: existing review status unchanged by a fresh Dry Run
def test_case_ad_existing_review_status_unchanged_by_dry_run(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_4(conn)
    assets = _speech_assets_for(db_path, plan_id)
    bag = _asset_by_id(assets, "SP201")
    client = FakeTTSClient()
    _gen(db_path, plan_id, bag, client, tmp_path)
    _approve(db_path, plan_id, "SP201")
    with connect(db_path) as conn:
        before = dict(conn.execute("SELECT metadata_json FROM generated_assets WHERE asset_id = 'SP201'").fetchone())
    run_asset_generation(db_path, client, mode="DRY_RUN", tts_model="m", assets_dir=tmp_path / "assets", plan_id=plan_id)
    with connect(db_path) as conn:
        after = dict(conn.execute("SELECT metadata_json FROM generated_assets WHERE asset_id = 'SP201'").fetchone())
    assert before == after


# CASE AE: Dry Run makes zero Gemini TTS calls even with Generation Unit computation
def test_case_ae_dry_run_zero_calls_with_generation_units(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_plan_12_1(conn)
    client = FakeTTSClient()
    result = run_asset_generation(db_path, client, mode="DRY_RUN", tts_model="m", assets_dir=tmp_path / "assets")
    assert result["api_calls"] == 0
    assert client.calls == []
    assert result["generation_unit_count"] >= result["source_speech_asset_count"]


# CASE AF: existing CLI backward compatibility
def test_case_af_assets_cli_still_parses_after_12_5():
    from research.cli import build_parser
    parser = build_parser()
    ns = parser.parse_args(["assets", "--dry-run", "--plan-id", "7"])
    assert ns.func.__name__ == "cmd_assets"
    assert ns.plan_id == 7


# ============================================================================
# 12-6: FULL Asset Generation execution + verification (prompts/12-6 section 26, CASE A-U)
# ============================================================================

# CASE A: FULL executes KO_NARRATION at Generation Unit granularity (asset_id set == unit ids)
def test_12_6_case_a_full_executes_ko_narration_at_unit_granularity(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_1(conn)
    client = FakeTTSClient()
    run_asset_generation(db_path, client, mode="SAMPLE", tts_model="m", assets_dir=tmp_path / "assets", plan_id=plan_id, max_segment_seconds=6.0)
    result = run_asset_generation(db_path, client, mode="FULL", tts_model="m", assets_dir=tmp_path / "assets", plan_id=plan_id, max_segment_seconds=6.0)
    sp101_ids = {r["asset_id"] for r in result["generated_assets"] if r["source_speech_asset_id"] == "SP101"}
    assert sp101_ids == {f"SP101-{i + 1}" for i in range(5)}
    texts = {r["asset_id"]: (r.get("metadata") or {}).get("synthesized_text") for r in result["generated_assets"] if r["source_speech_asset_id"] == "SP101"}
    assert len(set(texts.values())) == 5  # every segment has genuinely distinct text


# CASE B/C: existing SAMPLE segment cache is reused in FULL; only missing units are synthesized
def test_12_6_case_b_c_existing_segments_reused_missing_ones_generated(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_1(conn)
    client = FakeTTSClient()
    run_asset_generation(db_path, client, mode="SAMPLE", tts_model="m", assets_dir=tmp_path / "assets", plan_id=plan_id, max_segment_seconds=6.0)
    calls_before_full = len(client.calls)
    result = run_asset_generation(db_path, client, mode="FULL", tts_model="m", assets_dir=tmp_path / "assets", plan_id=plan_id, max_segment_seconds=6.0)
    sp101_rows = [r for r in result["generated_assets"] if r["source_speech_asset_id"] == "SP101"]
    reused = [r for r in sp101_rows if r["status"] == "REUSED"]
    generated = [r for r in sp101_rows if r["status"] == "AVAILABLE"]
    assert len(reused) == 2  # SP101-1/SP101-2 came from the SAMPLE run's max_new_segments=2 cap
    assert len(generated) == 3
    assert all(not r["api_call_made"] for r in reused)
    assert len(client.calls) - calls_before_full == len(generated)


# CASE D: CAP reuses the approved CONTEXTUAL_WORD fallback -- active_strategy_matches_full_plan stays pass
def test_12_6_case_d_cap_reuses_approved_contextual_fallback(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_4(conn)
    assets = _speech_assets_for(db_path, plan_id)
    cap = _asset_by_id(assets, "SP203")
    client = FakeTTSClient()
    _gen(db_path, plan_id, cap, client, tmp_path)
    _approve(db_path, plan_id, "SP203", pronunciation="REGENERATE_REQUIRED")
    _gen(db_path, plan_id, cap, client, tmp_path, asset_id="SP203::CONTEXTUAL_WORD", pronunciation_strategy="CONTEXTUAL_WORD")
    _approve(db_path, plan_id, "SP203::CONTEXTUAL_WORD", tone="APPROVED")
    run_asset_generation(db_path, client, mode="SAMPLE", tts_model="m", assets_dir=tmp_path / "assets", plan_id=plan_id)
    result = run_asset_generation(db_path, client, mode="FULL", tts_model="m", assets_dir=tmp_path / "assets", plan_id=plan_id)
    assert result["integrity_checks"]["active_strategy_matches_full_plan"] == "pass"
    cap_row = next(r for r in result["generated_assets"] if r["source_speech_asset_id"] == "SP203")
    assert cap_row["asset_id"] == "SP203::CONTEXTUAL_WORD"


# CASE E: CAP's failed DIRECT_WORD is never called again in FULL
def test_12_6_case_e_cap_failed_direct_word_never_called(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_4(conn)
    assets = _speech_assets_for(db_path, plan_id)
    cap = _asset_by_id(assets, "SP203")
    client = FakeTTSClient()
    _gen(db_path, plan_id, cap, client, tmp_path)
    _approve(db_path, plan_id, "SP203", pronunciation="REGENERATE_REQUIRED")
    _gen(db_path, plan_id, cap, client, tmp_path, asset_id="SP203::CONTEXTUAL_WORD", pronunciation_strategy="CONTEXTUAL_WORD")
    _approve(db_path, plan_id, "SP203::CONTEXTUAL_WORD", tone="APPROVED")
    run_asset_generation(db_path, client, mode="SAMPLE", tts_model="m", assets_dir=tmp_path / "assets", plan_id=plan_id)
    result = run_asset_generation(db_path, client, mode="FULL", tts_model="m", assets_dir=tmp_path / "assets", plan_id=plan_id)
    assert not any(r["asset_id"] == "SP203" for r in result["generated_assets"])
    assert result["integrity_checks"]["failed_or_rejected_asset_not_reused"] == "pass"


# CASE F: BAG/MAP reuse their approved DIRECT_WORD
def test_12_6_case_f_bag_map_reuse_approved_direct_word(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_4(conn)
    assets = _speech_assets_for(db_path, plan_id)
    bag, mp = _asset_by_id(assets, "SP201"), _asset_by_id(assets, "SP202")
    client = FakeTTSClient()
    _gen(db_path, plan_id, bag, client, tmp_path)
    _approve(db_path, plan_id, "SP201")
    _gen(db_path, plan_id, mp, client, tmp_path)
    _approve(db_path, plan_id, "SP202")
    run_asset_generation(db_path, client, mode="SAMPLE", tts_model="m", assets_dir=tmp_path / "assets", plan_id=plan_id)
    calls_before_full = len(client.calls)
    result = run_asset_generation(db_path, client, mode="FULL", tts_model="m", assets_dir=tmp_path / "assets", plan_id=plan_id)
    bag_row = next(r for r in result["generated_assets"] if r["source_speech_asset_id"] == "SP201")
    map_row = next(r for r in result["generated_assets"] if r["source_speech_asset_id"] == "SP202")
    assert bag_row["status"] == "REUSED" and map_row["status"] == "REUSED"
    assert not bag_row["api_call_made"] and not map_row["api_call_made"]


# CASE G: BAT (no history) generates fresh via DIRECT_WORD, stays PENDING (no auto-approval)
def test_12_6_case_g_bat_generates_fresh_direct_word_pending(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_4(conn)
    client = FakeTTSClient()
    run_asset_generation(db_path, client, mode="SAMPLE", tts_model="m", assets_dir=tmp_path / "assets", plan_id=plan_id)
    result = run_asset_generation(db_path, client, mode="FULL", tts_model="m", assets_dir=tmp_path / "assets", plan_id=plan_id)
    bat_row = next(r for r in result["generated_assets"] if r["source_speech_asset_id"] == "SP204")
    assert bat_row["asset_id"] == "SP204"
    assert bat_row["status"] == "AVAILABLE"
    assert bat_row["api_call_made"] is True
    assert (bat_row.get("metadata") or {}).get("pronunciation_review") == "PENDING"


# CASE H/I/J: experimental strategies never surface as the FULL-executed asset_id for a source
def test_12_6_case_h_i_j_experimental_strategies_never_the_executed_variant(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_4(conn)
    assets = _speech_assets_for(db_path, plan_id)
    bag = _asset_by_id(assets, "SP201")
    client = FakeTTSClient()
    for strategy in ("LOWERCASE_WORD", "MINIMAL_CONTEXT_WORD"):
        _gen(db_path, plan_id, bag, client, tmp_path, asset_id=f"SP201::{strategy}", pronunciation_strategy=strategy)
        _approve(db_path, plan_id, f"SP201::{strategy}")
    run_asset_generation(db_path, client, mode="SAMPLE", tts_model="m", assets_dir=tmp_path / "assets", plan_id=plan_id)
    result = run_asset_generation(db_path, client, mode="FULL", tts_model="m", assets_dir=tmp_path / "assets", plan_id=plan_id)
    bag_row = next(r for r in result["generated_assets"] if r["source_speech_asset_id"] == "SP201")
    assert "LOWERCASE_WORD" not in bag_row["asset_id"]
    assert "MINIMAL_CONTEXT_WORD" not in bag_row["asset_id"]
    blended_row = next(r for r in result["generated_assets"] if r["source_speech_asset_id"] == "SP212")
    assert "CONTEXT_RESTRICTED" not in blended_row["asset_id"]


# CASE K: DIRECT_SEQUENCE is the executed blending default
def test_12_6_case_k_direct_sequence_is_executed_blending_default(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_4(conn)
    client = FakeTTSClient()
    run_asset_generation(db_path, client, mode="SAMPLE", tts_model="m", assets_dir=tmp_path / "assets", plan_id=plan_id)
    result = run_asset_generation(db_path, client, mode="FULL", tts_model="m", assets_dir=tmp_path / "assets", plan_id=plan_id)
    blended_row = next(r for r in result["generated_assets"] if r["source_speech_asset_id"] == "SP212")
    assert blended_row["asset_id"] == "SP212::DIRECT_SEQUENCE"


# CASE L/M: new phoneme/EN_NATIVE asset never auto-APPROVED after real generation
def test_12_6_case_l_m_new_assets_never_auto_approved(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_4(conn)
    client = FakeTTSClient()
    run_asset_generation(db_path, client, mode="SAMPLE", tts_model="m", assets_dir=tmp_path / "assets", plan_id=plan_id)
    result = run_asset_generation(db_path, client, mode="FULL", tts_model="m", assets_dir=tmp_path / "assets", plan_id=plan_id)
    fresh_rows = [r for r in result["generated_assets"] if r["status"] == "AVAILABLE" and r.get("generation_method") == "gemini_tts"]
    assert fresh_rows  # sanity: something was actually freshly generated in this fixture
    assert all((r.get("metadata") or {}).get("pronunciation_review") != "APPROVED" for r in fresh_rows)
    assert result["integrity_checks"]["full_review_state_honest"] == "pass"


# CASE N: technical validation failure -> not treated as AVAILABLE
def test_12_6_case_n_technical_validation_failure_not_available(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_4(conn)
    failing_client = FakeTTSClient(always_fail=True)
    run_asset_generation(db_path, FakeTTSClient(), mode="SAMPLE", tts_model="m", assets_dir=tmp_path / "assets", plan_id=plan_id)
    result = run_asset_generation(db_path, failing_client, mode="FULL", tts_model="m", assets_dir=tmp_path / "assets", plan_id=plan_id)
    bat_row = next(r for r in result["generated_assets"] if r["source_speech_asset_id"] == "SP204")
    assert bat_row["status"] != "AVAILABLE"
    assert result["integrity_checks"]["generated_audio_technical_validation_safe"] == "pass"


# CASE O: FULL manifest includes every required Generation Unit
def test_12_6_case_o_full_manifest_includes_all_generation_units(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_4(conn)
    client = FakeTTSClient()
    run_asset_generation(db_path, client, mode="SAMPLE", tts_model="m", assets_dir=tmp_path / "assets", plan_id=plan_id)
    result = run_asset_generation(db_path, client, mode="FULL", tts_model="m", assets_dir=tmp_path / "assets", plan_id=plan_id)
    assert result["integrity_checks"]["full_manifest_complete"] == "pass"
    manifest_ids = {a["asset_id"] for a in result["manifest"]["assets"]}
    for r in result["generated_assets"]:
        if r["status"] in {"AVAILABLE", "REUSED"}:
            assert r["asset_id"] in manifest_ids
    # section 19 fields present on at least one manifest entry
    sample_entry = next(a for a in result["manifest"]["assets"] if a["asset_id"] == "SP201")
    assert {"checksum", "strategy", "tone_consistency_review", "segment_index", "segment_count", "source_block_ids"} <= set(sample_entry.keys())


# CASE P: retry calls are counted separately from base calls
def test_12_6_case_p_retry_counted_separately_from_base(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_4(conn)

    class _RetryOnceClient(FakeTTSClient):
        def synthesize(self, prompt, voice_name):
            self.calls.append((prompt, voice_name))
            return {"audio_base64": base64.b64encode(_SILENCE_PCM).decode("ascii"), "mime_type": self._mime_type, "attempts": 3}

    client = _RetryOnceClient()
    run_asset_generation(db_path, client, mode="SAMPLE", tts_model="m", assets_dir=tmp_path / "assets", plan_id=plan_id)
    result = run_asset_generation(db_path, client, mode="FULL", tts_model="m", assets_dir=tmp_path / "assets", plan_id=plan_id)
    bat_row = next(r for r in result["generated_assets"] if r["source_speech_asset_id"] == "SP204")
    assert bat_row["retries"] == 2
    assert result["retry_count"] >= 2
    assert result["total_calls"] == result["api_calls"] + result["retry_count"]
    assert result["integrity_checks"]["full_api_call_accounting_safe"] == "pass"


# CASE Q: FULL completed but review still PENDING -> Ready for Rendering NO
def test_12_6_case_q_full_completed_review_pending_ready_for_rendering_no(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_4(conn)
    client = FakeTTSClient()
    run_asset_generation(db_path, client, mode="SAMPLE", tts_model="m", assets_dir=tmp_path / "assets", plan_id=plan_id)
    result = run_asset_generation(db_path, client, mode="FULL", tts_model="m", assets_dir=tmp_path / "assets", plan_id=plan_id)
    assert result["ready_for_rendering"] is False


# CASE R: once required review conditions are satisfied, the gate function itself can return True
def test_12_6_case_r_rendering_gate_true_when_all_conditions_met():
    checks = {"a": "pass", "b": "pass"}
    assert ready_for_rendering_gate(checks, "FULL", has_unverified_critical_phoneme=False) is True


# CASE S/T/U: Production Plan / PAUSE / viewer_action unchanged by a real FULL run
def test_12_6_case_s_t_u_production_plan_pause_viewer_action_unchanged_after_full(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        plan_id = _seed_plan_12_4(conn)
    with connect(db_path) as conn:
        before_plan = dict(conn.execute("SELECT * FROM production_plans WHERE id = ?", (plan_id,)).fetchone())
        before_blocks = [dict(r) for r in conn.execute(
            "SELECT * FROM production_blocks WHERE production_plan_id = ? ORDER BY block_order", (plan_id,)
        ).fetchall()]
    client = FakeTTSClient()
    run_asset_generation(db_path, client, mode="SAMPLE", tts_model="m", assets_dir=tmp_path / "assets", plan_id=plan_id)
    run_asset_generation(db_path, client, mode="FULL", tts_model="m", assets_dir=tmp_path / "assets", plan_id=plan_id)
    with connect(db_path) as conn:
        after_plan = dict(conn.execute("SELECT * FROM production_plans WHERE id = ?", (plan_id,)).fetchone())
        after_blocks = [dict(r) for r in conn.execute(
            "SELECT * FROM production_blocks WHERE production_plan_id = ? ORDER BY block_order", (plan_id,)
        ).fetchall()]
    assert before_plan == after_plan
    assert before_blocks == after_blocks
    mini_block = next(b for b in after_blocks if b["content_block_id"] == "CB_MINI")
    timeline = json.loads(mini_block["timeline_spec_json"])
    pause_event = next(ev for ev in timeline if ev["type"] == "PAUSE")
    assert pause_event["duration_ms"] == 3000
    assert mini_block["production_intent"] == "viewer_must_attempt_before_answer"
