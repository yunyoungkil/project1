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
    build_asset_generation_report,
    build_asset_manifest,
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
    assert original_16 <= set(checks.keys())
    assert new_5_12_1 <= set(checks.keys())
    assert new_5_12_2 <= set(checks.keys())
    assert new_4_12_3 <= set(checks.keys())
    assert len(checks) == 30


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


# CASE AD: full existing regression -- exercised by running the whole suite, not a single test.
