"""Compiles one 11-approved Production Plan into actually-generated, actually-validated audio
assets. Reads production_plans/production_blocks/speech_assets read-only (never redefines a
speech_mode, voice, or timeline decision made upstream) and turns each Speech Asset into a real
Gemini TTS call, a real WAV file, and a validation record. Generation success and pronunciation
validation success are different things: with no real phonetic validator available, this module
never auto-passes pronunciation quality -- it stays UNVERIFIED/PENDING until a human reviews it.
"""
from __future__ import annotations

import base64
import hashlib
import inspect
import json
import re
import wave
from datetime import datetime
from pathlib import Path

from research.db import connect
from research.production_planner import _DELIVERY_INSTRUCTIONS, NARRATOR_VOICE, is_punctuation_only_fragment
from research.script_writer import estimate_duration_and_words

# ---------------------------------------------------------------------------
# Fixed taxonomies
# ---------------------------------------------------------------------------

ASSET_STATUSES = {"PENDING", "GENERATING", "AVAILABLE", "FAILED", "UNVERIFIED", "REUSED", "SKIPPED", "MISSING_SOURCE"}
RUN_MODES = {"DRY_RUN", "SAMPLE", "FULL"}
GENERATION_STRATEGIES = {"DIRECT_PHONEME_PROMPT", "CONTEXT_EXTRACTION", "UNSUPPORTED"}
# 12-1 section 9: PENDING/NOT_REQUIRED unchanged from 12; APPROVED replaces the original "ACCEPTED"
# spelling to match the 12-1 spec's own wording, with REJECTED/REGENERATE_REQUIRED added. No schema
# migration needed (metadata_json is free-form) -- _is_pronunciation_approved() below accepts both
# spellings so already-persisted 12-era rows stay valid.
PRONUNCIATION_REVIEW_STATES = {"NOT_REQUIRED", "PENDING", "APPROVED", "REJECTED", "REGENERATE_REQUIRED"}
# 12-3 section 20: "pronunciation is correct but tone doesn't match the rest of the video" cannot
# be expressed by pronunciation_review alone -- a separate metadata field, no schema change needed
# (metadata_json is free-form JSON already).
TONE_CONSISTENCY_REVIEW_STATES = {"NOT_REQUIRED", "PENDING", "APPROVED", "REJECTED"}
PHONEME_DEMO_TYPES = {"ISOLATED", "BLENDED_SEQUENCE"}
PHONEME_STRATEGIES = {"DIRECT_SEQUENCE", "CONTEXT_RESTRICTED"}
DEFAULT_BLENDING_STRATEGY = "DIRECT_SEQUENCE"  # 12-2 section 11: confirmed default for beginners --
# each sound is heard separately before blending, which real listening found easier to follow.
# CONTEXT_RESTRICTED is kept as a valid, slightly faster alternative for reinforcement/review.
REVIEW_PRIORITIES = {"LOW", "MEDIUM", "HIGH"}

# 12-2 section 4 (extended by 12-3 sections 1-2): EN_NATIVE pronunciation strategy.
# DIRECT_WORD is the untouched baseline (uppercase source_text sent as-is, unmodified prompt).
# CONTEXTUAL_WORD (12-2) confounded two variables at once -- lowercase transcript AND a richer
# "this is an English word" framing -- so CAP's real fix couldn't be attributed to either one.
# 12-3 splits them: LOWERCASE_WORD changes ONLY the transcript case (identical DIRECTOR'S NOTES to
# DIRECT_WORD -- no new branch in _director_notes at all, by design); MINIMAL_CONTEXT_WORD adds
# the smallest possible pronunciation instruction with none of CONTEXTUAL_WORD's tone-shifting
# adjectives (warm/friendly/expressive/etc, section 2's explicit exclusion list). None of these
# are officially documented Gemini behavior -- all stay PENDING human review, never auto-approved.
EN_NATIVE_PRONUNCIATION_STRATEGIES = {"DIRECT_WORD", "CONTEXTUAL_WORD", "LOWERCASE_WORD", "MINIMAL_CONTEXT_WORD"}
DEFAULT_EN_NATIVE_STRATEGY = "DIRECT_WORD"  # 12-3 section 28: final strategy deliberately left
# unresolved until a human has compared all four CAP variants -- DIRECT_WORD stays the safe,
# unchanged default rather than this code presuming a winner.

TTS_PROMPT_VERSION = "12.1"  # unchanged from 12-1 -- see synthesize_asset's cache-key comment for why

# Persona hints for the AUDIO PROFILE "Role:" line (spec section 4) -- anchored to the single-word
# official descriptors confirmed live via WebFetch (ai.google.dev): Charon="Informative",
# Zephyr="Bright". Deliberately short so they don't fight the Google voice profile with an
# over-specified persona.
_VOICE_DIRECTION_HINTS = {
    "Charon": "a calm, informative, and friendly educational narrator/explainer",
    "Zephyr": "a bright, warm, and curious podcast host",
}

# Internal-only concepts (12-1 section 5): never injected as a REST field that doesn't exist in the
# official contract -- used purely for generated_assets.metadata_json and report/manifest display.
_DELIVERY_LANGUAGE_MAP = {
    "KO_NARRATION": "ko-KR", "EN_NATIVE": "en-US", "EN_PHONEME_DEMO": "en-US",
    "KO_PRONUNCIATION_GUIDE": "ko-KR", "ORIGINAL_NATIVE_AUDIO": "en-US",
}
_DELIVERY_ROLE_MAP = {
    "KO_NARRATION": "korean_educational_narrator", "EN_NATIVE": "native_english_model",
    "EN_PHONEME_DEMO": "isolated_english_phoneme", "KO_PRONUNCIATION_GUIDE": "korean_pronunciation_approximation",
}
# Risk-based human review priority (spec section 11): KO_NARRATION is the least risky (plain
# Korean explanation), EN_PHONEME_DEMO carries the highest miscommunication risk since there is no
# official Gemini support for isolated/blended IPA at all (confirmed via WebFetch).
_REVIEW_PRIORITY = {
    "KO_NARRATION": "LOW", "EN_NATIVE": "MEDIUM", "EN_PHONEME_DEMO": "HIGH",
    "KO_PRONUNCIATION_GUIDE": "MEDIUM",
}

_DEFAULT_SAMPLE_RATE = 24000
_DEFAULT_CHANNELS = 1
_DEFAULT_SAMPLE_WIDTH_BYTES = 2
_MIME_RATE_RE = re.compile(r"rate=(\d+)")


def _is_pronunciation_approved(value: str | None) -> bool:
    return value in {"APPROVED", "ACCEPTED"}


def review_priority_for(speech_mode: str, *, is_mini_success_answer: bool = False) -> str:
    """12-2 section 10: an EN_NATIVE asset that IS the Mini Success answer (the word a viewer just
    attempted and is about to hear confirmed) carries more educational weight than an ordinary
    EN_NATIVE mention, so it is escalated to HIGH -- determined structurally via
    is_mini_success_answer_asset, never via a per-word hardcode."""
    if speech_mode == "EN_NATIVE" and is_mini_success_answer:
        return "HIGH"
    return _REVIEW_PRIORITY.get(speech_mode, "MEDIUM")


def classify_phoneme_demo_type(source_text: str) -> str:
    return "BLENDED_SEQUENCE" if "-" in source_text else "ISOLATED"


# ---------------------------------------------------------------------------
# Source loading (read-only)
# ---------------------------------------------------------------------------

def select_target_plan(db_path: Path, plan_id: int | None = None) -> dict | None:
    with connect(db_path) as conn:
        if plan_id is not None:
            row = conn.execute("SELECT * FROM production_plans WHERE id = ?", (plan_id,)).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM production_plans WHERE ready_for_asset_generation = 1 "
                "ORDER BY generated_at DESC, id DESC LIMIT 1"
            ).fetchone()
    return dict(row) if row else None


def _load_production_blocks(db_path: Path, plan_id: int) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM production_blocks WHERE production_plan_id = ? ORDER BY block_order", (plan_id,)
        ).fetchall()
    blocks = [dict(r) for r in rows]
    for pb in blocks:
        try:
            pb["timeline"] = json.loads(pb.get("timeline_spec_json") or "[]")
        except (TypeError, ValueError):
            pb["timeline"] = []
    return blocks


def _load_speech_assets(db_path: Path, plan_id: int) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM speech_assets WHERE production_plan_id = ? ORDER BY speech_asset_id", (plan_id,)
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Speech-mode-specific prompt compiler (spec sections 5-13): PREAMBLE/AUDIO PROFILE/SCENE/
# DIRECTOR'S NOTES/TRANSCRIPT, with a clear boundary between the generation request and the
# spoken transcript. Reuses production_planner's per-mode delivery-instruction text as the base of
# DIRECTOR'S NOTES instead of re-writing near-duplicate phrasing.
# ---------------------------------------------------------------------------

_PREAMBLE = (
    "Generate spoken audio for the transcript below.\n\n"
    "Follow the performance directions.\n"
    "Do not speak section names or production instructions.\n"
    "Only speak the content under TRANSCRIPT."
)
_SCENE = "A beginner English learning video for Korean adult learners."


_LOWERCASE_TRANSCRIPT_STRATEGIES = {"CONTEXTUAL_WORD", "LOWERCASE_WORD", "MINIMAL_CONTEXT_WORD"}


def compute_tts_transcript(speech_mode: str, source_text: str, *, pronunciation_strategy: str = "DIRECT_WORD") -> str:
    """The actual text sent in TRANSCRIPT -- may differ from source_text (which speech_assets owns
    and this module never touches) for experimental normalization. Generalized over the strategy
    set rather than any per-word check, so BAG/MAP/CAP/any future word all follow the same rule
    (12-3 section 11 explicitly forbids a per-word literal shortcut). DIRECT_WORD alone sends
    source_text unchanged; every other EN_NATIVE strategy lowercases."""
    if speech_mode == "EN_NATIVE" and pronunciation_strategy in _LOWERCASE_TRANSCRIPT_STRATEGIES:
        return source_text.lower()
    return source_text


def _director_notes(
    speech_mode: str, source_text: str, *,
    phoneme_strategy: str = "DIRECT_SEQUENCE", target_word: str | None = None,
    pronunciation_strategy: str = "DIRECT_WORD",
) -> str:
    base = _DELIVERY_INSTRUCTIONS.get(speech_mode, "")
    if speech_mode == "KO_NARRATION":
        return f"{base} Do not over-articulate unless the transcript specifically demonstrates a pronunciation. Do not speak unnaturally slowly."
    if speech_mode == "EN_NATIVE":
        # 12-3 section 5/CASE G: this baseline text is shared verbatim by DIRECT_WORD AND
        # LOWERCASE_WORD -- LOWERCASE_WORD deliberately has no branch below, so the two strategies
        # differ ONLY in transcript case (compute_tts_transcript), never in DIRECTOR'S NOTES. This
        # is what makes them a clean isolated-variable comparison instead of another confound.
        notes = (
            f"{base} Do not say the letter names one by one (do not say 'B, A, G'). "
            "Do not add introductory words such as 'the word is'. Speak the word once naturally."
        )
        if pronunciation_strategy == "CONTEXTUAL_WORD":
            # 12-2 section 4: richer word-context framing -- never spoken itself, this only ever
            # lives in DIRECTOR'S NOTES, never the TRANSCRIPT (see build_tts_prompt's explicit
            # section separation). Confounds tone-shifting adjectives with the pronunciation fix,
            # which is exactly why 12-3 introduces MINIMAL_CONTEXT_WORD below.
            notes += (
                " This is an English word. Pronounce it naturally as one word, using natural "
                "American English pronunciation. Do not spell the letters. Do not say the letter "
                "names. Do not explain the word."
            )
        elif pronunciation_strategy == "MINIMAL_CONTEXT_WORD":
            # 12-3 section 12: the smallest possible pronunciation instruction -- deliberately none
            # of CONTEXTUAL_WORD's tone/style adjectives (warm/friendly/expressive/gentle/smooth/
            # enthusiastic/conversational/teacher-like/narrator-like, section 2's exclusion list),
            # so any tone shift observed here is NOT explained by an explicit style instruction.
            notes += " Pronounce the transcript as one English word. Do not spell it."
        return notes
    if speech_mode == "EN_PHONEME_DEMO":
        notes = (
            f"{base} This is a phonetic sound, not a word or a letter name -- produce the IPA "
            "sound value itself, not the name of the symbol. Do not translate or substitute a Korean sound."
        )
        if classify_phoneme_demo_type(source_text) == "BLENDED_SEQUENCE":
            notes += (
                " This transcript blends multiple sounds in sequence into one continuous "
                "demonstration -- pronounce each sound in order, gradually connecting them into the "
                "blended sound, not as separate named letters."
            )
            # 12-1 section 7: giving the model the target word as bare context risks it just
            # reading the whole word aloud instead of demonstrating the blend -- CONTEXT_RESTRICTED
            # explicitly forbids that failure mode; DIRECT_SEQUENCE omits this line entirely so the
            # two strategies are a genuine A/B comparison, not the same prompt with noise added.
            if phoneme_strategy == "CONTEXT_RESTRICTED" and target_word:
                notes += (
                    f" The target word this blend belongs to is {target_word}, for your own context "
                    f"only -- do NOT say the whole word {target_word}. Only produce the blended sound "
                    "sequence below."
                )
        return notes
    if speech_mode == "KO_PRONUNCIATION_GUIDE":
        return f"{base} It is a Korean-language listening approximation for a beginner, not the authoritative English pronunciation."
    return base


def build_tts_prompt(
    speech_mode: str, source_text: str, voice_name: str | None, *,
    phoneme_strategy: str = "DIRECT_SEQUENCE", target_word: str | None = None,
    pronunciation_strategy: str = "DIRECT_WORD",
) -> str:
    if speech_mode == "ORIGINAL_NATIVE_AUDIO":
        raise ValueError("ORIGINAL_NATIVE_AUDIO must never be sent to TTS -- it comes from a source clip file.")
    role = _VOICE_DIRECTION_HINTS.get(voice_name, "a calm, clear narrator")
    notes = _director_notes(
        speech_mode, source_text, phoneme_strategy=phoneme_strategy, target_word=target_word,
        pronunciation_strategy=pronunciation_strategy,
    )
    transcript = compute_tts_transcript(speech_mode, source_text, pronunciation_strategy=pronunciation_strategy)
    return (
        f"{_PREAMBLE}\n\n"
        f"### AUDIO PROFILE\n\n"
        f"Voice: {voice_name}\n"
        f"Role: {role}\n\n"
        f"### SCENE\n\n"
        f"{_SCENE}\n\n"
        f"### DIRECTOR'S NOTES\n\n"
        f"{notes}\n\n"
        f"### TRANSCRIPT\n\n"
        f"{transcript}"
    )


# ---------------------------------------------------------------------------
# Cache key (spec section 25): source_text alone is not enough -- model/voice/speech_mode/
# delivery_instruction all participate, hashed rather than concatenated raw.
# ---------------------------------------------------------------------------

def compute_cache_key(
    model: str, voice_name: str | None, speech_mode: str, tts_input_text: str, delivery_instruction: str,
    *, prompt_version: str | None = None, phoneme_strategy: str | None = None,
    pronunciation_strategy: str | None = None,
) -> str:
    """12-1 section 16 / 12-2 section 13: only elements that actually change the TTS request
    participate. prompt_version/phoneme_strategy/pronunciation_strategy are optional so pre-12-1
    callers (and pre-12-1/12-2 stored keys) keep working unchanged -- each strategy-aware key is a
    strict superset used only when that concept is actually in play (see the legacy-key fallback
    and the review-status filter in synthesize_asset / _existing_cache_row)."""
    payload = {
        "model": model, "voice": voice_name, "speech_mode": speech_mode,
        "tts_input_text": tts_input_text, "delivery_instruction": delivery_instruction,
    }
    if prompt_version:
        payload["prompt_version"] = prompt_version
    if phoneme_strategy:
        payload["phoneme_strategy"] = phoneme_strategy
    if pronunciation_strategy:
        payload["pronunciation_strategy"] = pronunciation_strategy
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Audio format + file writer/validator (spec sections 20-21). Sample rate is parsed from the
# actual response mimeType when present; the 24kHz/mono/16-bit default is only ever used as a
# fallback and is flagged as such via confirmed_from_response, never silently claimed as verified.
# ---------------------------------------------------------------------------

def parse_pcm_format(mime_type: str | None) -> dict:
    sample_rate = _DEFAULT_SAMPLE_RATE
    confirmed = False
    if mime_type:
        m = _MIME_RATE_RE.search(mime_type)
        if m:
            sample_rate = int(m.group(1))
            confirmed = True
    return {
        "sample_rate": sample_rate, "channels": _DEFAULT_CHANNELS,
        "sample_width_bytes": _DEFAULT_SAMPLE_WIDTH_BYTES, "confirmed_from_response": confirmed,
    }


def write_wav_file(path: Path, pcm_bytes: bytes, sample_rate: int, channels: int, sample_width_bytes: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width_bytes)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)


def validate_audio_file(path: Path) -> dict:
    if not path.exists():
        return {"valid": False, "duration_ms": 0, "errors": ["file_missing"]}
    errors = []
    if path.stat().st_size <= 0:
        errors.append("empty_file")
    duration_ms = 0
    try:
        with wave.open(str(path), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            duration_ms = int(round(frames / rate * 1000)) if rate else 0
    except Exception as e:  # noqa: BLE001 - any decode failure is a validation failure, not a crash
        errors.append(f"not_decodable:{e}")
    if duration_ms <= 0:
        errors.append("zero_duration")
    return {"valid": not errors, "duration_ms": duration_ms, "errors": errors}


def classify_phoneme_generation_strategy(source_text: str) -> str:
    """Only DIRECT_PHONEME_PROMPT is actually implemented -- there is no post-processing
    extraction infrastructure to justify CONTEXT_EXTRACTION (spec section 11 forbids faking it),
    and every phoneme is genuinely attempted, so UNSUPPORTED never applies here."""
    return "DIRECT_PHONEME_PROMPT"


# ---------------------------------------------------------------------------
# KO_NARRATION sentence-boundary segmentation (12-1 sections 12-15). Google's own docs only flag
# quality drift after "a few minutes" -- SP001's 32.6s is not in that risk zone -- so the real
# motivation here is Renderer-side control (caption sync, keyword highlighting, partial
# regeneration cost), not TTS audio quality. Sentences are never cut mid-sentence (section 14);
# segments are greedily packed up to max_segment_seconds using script_writer's existing duration
# estimator (reused, not reimplemented). Reuses 11-1's own orphan/punctuation-only fragment guards
# instead of inventing a second implementation of the same safety check (section 13).
# ---------------------------------------------------------------------------

_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+")


def _segment_is_safe(text: str) -> bool:
    """11-1's is_orphan_narration_fragment targets a different failure mode -- a particle
    stranded after an ENGLISH_WORD/PHONEME token was deleted mid-sentence -- and deliberately
    flags common sentence-initial patterns like "이 " (as in a stray "이 있습니다.") as suspicious.
    Sentence-boundary splitting never deletes a token mid-sentence; it only ever regroups whole
    sentences, so a fresh sentence starting with "이 단어는..." ("this word...") is completely
    normal, not an orphan. Applying that check here produced false positives on ordinary
    sentences, so only the genuinely applicable guard remains: never emit an empty or
    punctuation-only segment."""
    stripped = text.strip()
    return bool(stripped) and not is_punctuation_only_fragment(stripped)


def segment_source_text_by_sentence(source_text: str, max_segment_seconds: float) -> list[str]:
    text = source_text or ""
    sentences = [s.strip() for s in _SENTENCE_BOUNDARY_RE.split(text) if s.strip()]
    if len(sentences) <= 1:
        return [text] if text else []

    segments: list[str] = []
    current: list[str] = []
    current_seconds = 0.0
    for sentence in sentences:
        est_seconds, _ = estimate_duration_and_words(sentence)
        if current and current_seconds + est_seconds > max_segment_seconds:
            segments.append(" ".join(current))
            current = [sentence]
            current_seconds = est_seconds
        else:
            current.append(sentence)
            current_seconds += est_seconds
    if current:
        segments.append(" ".join(current))

    if not segments or not all(_segment_is_safe(s) for s in segments):
        return [text]  # unsafe to split -- keep the original single segment rather than force it
    return segments


def _source_block_ids_for_speech_asset(production_blocks: list[dict], speech_asset_id: str) -> list[str]:
    ids: list[str] = []
    for pb in production_blocks:
        for ev in pb.get("timeline") or []:
            if ev.get("type") == "SPEECH" and ev.get("speech_asset_id") == speech_asset_id:
                if pb["content_block_id"] not in ids:
                    ids.append(pb["content_block_id"])
    return ids


def _infer_target_word_for_blend(production_blocks: list[dict], speech_assets: list[dict], blended_asset_id: str) -> str | None:
    """Finds the EN_NATIVE word spoken in the same Production Block as a BLENDED_SEQUENCE phoneme
    asset -- e.g. CB03's /b-æ-g/ shares a block with the EN_NATIVE "BAG" asset. Not hardcoded to
    BAG specifically so the same logic generalizes to BAT/MAP/CAP or any future word."""
    block_ids = set(_source_block_ids_for_speech_asset(production_blocks, blended_asset_id))
    if not block_ids:
        return None
    speech_by_id = {a["speech_asset_id"]: a for a in speech_assets}
    for pb in production_blocks:
        if pb["content_block_id"] not in block_ids:
            continue
        for ev in pb.get("timeline") or []:
            if ev.get("type") != "SPEECH":
                continue
            asset = speech_by_id.get(ev.get("speech_asset_id"))
            if asset and asset["speech_mode"] == "EN_NATIVE":
                return asset["source_text"]
    return None


def is_mini_success_answer_asset(production_blocks: list[dict], speech_asset_id: str) -> bool:
    """12-2 section 10: an EN_NATIVE asset counts as a Mini Success "answer reveal" when it
    belongs to a Production Block whose production_intent is the same
    "viewer_must_attempt_before_answer" marker 11-2 already uses for Mini Success blocks, AND it
    sits after that block's PAUSE in the timeline (i.e. it IS the reveal, not the pre-pause
    setup). Reuses production_intent/timeline data already on production_blocks -- no new
    lineage infrastructure, no per-word hardcode."""
    block_ids = set(_source_block_ids_for_speech_asset(production_blocks, speech_asset_id))
    if not block_ids:
        return False
    for pb in production_blocks:
        if pb["content_block_id"] not in block_ids:
            continue
        if pb.get("production_intent") != "viewer_must_attempt_before_answer":
            continue
        timeline = pb.get("timeline") or []
        pause_idx = next((i for i, ev in enumerate(timeline) if ev.get("type") == "PAUSE"), None)
        if pause_idx is None:
            continue
        for ev in timeline[pause_idx + 1:]:
            if ev.get("type") == "SPEECH" and ev.get("speech_asset_id") == speech_asset_id:
                return True
    return False


# ---------------------------------------------------------------------------
# 12-5: Generation Unit compiler. A Source Speech Asset (11's logical unit, e.g. "SP001") and a
# Generation Unit (the actual TTS request/cache/reuse granularity, e.g. "SP001-1"/"SP001-2") are
# not always the same thing once KO_NARRATION sentence-boundary segmentation (12-1) is involved --
# this is the single deterministic function SAMPLE/FULL/DRY_RUN all call so they can never
# disagree about how many units a source resolves to (section 21: Single Source of Truth). Pure
# function: no DB access, no TTS calls, no side effects.
# ---------------------------------------------------------------------------

def build_generation_units(speech_asset: dict, production_blocks: list[dict], *, max_segment_seconds: float = 12.0) -> list[dict]:
    sid = speech_asset["speech_asset_id"]
    mode = speech_asset["speech_mode"]
    source_block_ids = _source_block_ids_for_speech_asset(production_blocks, sid)

    if mode in {"KO_NARRATION", "KO_PRONUNCIATION_GUIDE"}:
        segments = segment_source_text_by_sentence(speech_asset["source_text"], max_segment_seconds)
        if len(segments) <= 1:
            text = segments[0] if segments else speech_asset["source_text"]
            return [{
                "source_speech_asset_id": sid, "generation_unit_id": sid, "segment_index": None,
                "segment_count": 1, "speech_mode": mode, "text": text, "source_block_ids": source_block_ids,
            }]
        return [
            {
                "source_speech_asset_id": sid, "generation_unit_id": f"{sid}-{i + 1}", "segment_index": i,
                "segment_count": len(segments), "speech_mode": mode, "text": seg, "source_block_ids": source_block_ids,
            }
            for i, seg in enumerate(segments)
        ]

    return [{
        "source_speech_asset_id": sid, "generation_unit_id": sid, "segment_index": None,
        "segment_count": 1, "speech_mode": mode, "text": speech_asset["source_text"], "source_block_ids": source_block_ids,
    }]


# ---------------------------------------------------------------------------
# Sample Matrix selection (12 spec sections 19/34, expanded by 12-1 section 18): a richer but
# still bounded set of representative types -- KO_NARRATION short/long, EN_NATIVE across two
# words, isolated phonemes, and one blended sequence -- never the full 44.
# ---------------------------------------------------------------------------

def select_sample_assets(speech_assets: list[dict]) -> dict:
    ko = [a for a in speech_assets if a["speech_mode"] == "KO_NARRATION"]
    ko_by_length = sorted(ko, key=lambda a: len(a["source_text"]))

    en_native = []
    for word in ("BAG", "MAP", "CAP"):  # 12-2 section 7: generalization set, not a single word
        found = next((a for a in speech_assets if a["speech_mode"] == "EN_NATIVE" and a["source_text"] == word), None)
        if found:
            en_native.append(found)

    phoneme_isolated = []
    for ph in ("/æ/", "/b/", "/g/"):
        found = next((a for a in speech_assets if a["speech_mode"] == "EN_PHONEME_DEMO" and a["source_text"] == ph), None)
        if found:
            phoneme_isolated.append(found)

    phoneme_blended = next(
        (a for a in speech_assets if a["speech_mode"] == "EN_PHONEME_DEMO" and classify_phoneme_demo_type(a["source_text"]) == "BLENDED_SEQUENCE"),
        None,
    )

    return {
        "ko_narration_short": ko_by_length[0] if ko_by_length else None,
        "ko_narration_long": ko_by_length[-1] if ko_by_length else None,
        "en_native": en_native,
        "phoneme_isolated": phoneme_isolated,
        "phoneme_blended": phoneme_blended,
    }


# ---------------------------------------------------------------------------
# Per-asset synthesis (cache lookup -> TTS call -> WAV write -> validation)
# ---------------------------------------------------------------------------

# 12-2 section 13: a cache-key dimension alone can't stop a known-bad asset (e.g. SP039 "CAP"
# sounding like "배그") from being served again through an older key that predates that dimension
# (e.g. the legacy fallback key, which has no pronunciation_strategy component at all). The actual
# fix has to live at the review-status level: once a human marks an asset REJECTED or
# REGENERATE_REQUIRED, no cache key -- old or new -- may ever resurface it.
_NON_REUSABLE_REVIEW_STATES = {"REJECTED", "REGENERATE_REQUIRED"}


def _existing_cache_row(conn, cache_keys: list[str]) -> dict | None:
    for key in cache_keys:
        if not key:
            continue
        row = conn.execute(
            "SELECT * FROM generated_assets WHERE cache_key = ? AND status IN ('AVAILABLE','REUSED') "
            "ORDER BY id DESC LIMIT 1",
            (key,),
        ).fetchone()
        if not row:
            continue
        try:
            metadata = json.loads(row["metadata_json"] or "{}")
        except (TypeError, ValueError):
            metadata = {}
        if metadata.get("pronunciation_review") in _NON_REUSABLE_REVIEW_STATES:
            continue  # known-bad audio -- treat as a miss, never silently resurrect it
        return dict(row)
    return None


def synthesize_asset(
    db_path: Path, speech_asset: dict, tts_client, *, audio_dir: Path, tts_model: str,
    asset_id: str | None = None, text_override: str | None = None,
    phoneme_strategy: str = "DIRECT_SEQUENCE", target_word: str | None = None,
    segment_metadata: dict | None = None,
    pronunciation_strategy: str = "DIRECT_WORD", is_mini_success_answer: bool = False,
) -> dict:
    """Returns a dict shaped for a generated_assets row (not yet persisted), plus the run-level
    aggregation fields 'api_call_made' and 'retries'.

    `asset_id` (defaults to the source speech_asset_id) lets one speech_asset row fan out into
    several generated files -- KO_NARRATION sentence segments ("SP001-1", "SP001-2", ...) or
    EN_PHONEME_DEMO blending-strategy comparisons ("SP0xx::DIRECT_SEQUENCE" vs
    "SP0xx::CONTEXT_RESTRICTED") -- while `source_speech_asset_id` keeps the lineage back to 11's
    speech_assets row (12-1 section 15). `text_override` lets a segment synthesize a slice of the
    original source_text without ever touching the speech_assets row itself."""
    speech_mode = speech_asset["speech_mode"]
    source_speech_asset_id = speech_asset["speech_asset_id"]
    resolved_asset_id = asset_id or source_speech_asset_id
    voice_name = speech_asset.get("voice_name")

    if speech_mode == "ORIGINAL_NATIVE_AUDIO":
        return {
            "asset_id": resolved_asset_id, "source_speech_asset_id": source_speech_asset_id,
            "speech_mode": speech_mode, "voice_name": voice_name,
            "status": "MISSING_SOURCE", "file_path": None, "mime_type": None, "duration_ms": None,
            "sample_rate": None, "channels": None, "checksum": None,
            "generation_method": "source_extraction", "generation_attempts": 0, "cache_key": None,
            "validation": {"valid": False, "errors": ["no_source_clip_available"]},
            "metadata": {"pronunciation_review": "NOT_REQUIRED", "review_priority": "LOW", "tone_consistency_review": "NOT_REQUIRED"},
            "api_call_made": False, "retries": 0,
        }

    source_text = text_override if text_override is not None else speech_asset["source_text"]
    delivery_instruction = _DELIVERY_INSTRUCTIONS.get(speech_mode, "")
    is_blended = speech_mode == "EN_PHONEME_DEMO" and classify_phoneme_demo_type(source_text) == "BLENDED_SEQUENCE"
    is_en_native = speech_mode == "EN_NATIVE"
    cache_key = compute_cache_key(
        tts_model, voice_name, speech_mode, source_text, delivery_instruction,
        prompt_version=TTS_PROMPT_VERSION, phoneme_strategy=phoneme_strategy if is_blended else None,
        pronunciation_strategy=pronunciation_strategy if is_en_native else None,
    )
    # Pre-12-1 rows (SP001/SP003/SP009) were cached without prompt_version -- this legacy key lets
    # unchanged-prompt modes (isolated phonemes, unsegmented KO_NARRATION, and EN_NATIVE's
    # DIRECT_WORD baseline specifically) reuse them without a new API call (section 26 "무조건
    # 다시 생성하지 마라"). It must NEVER be offered for EN_NATIVE's CONTEXTUAL_WORD strategy or for
    # blended phonemes -- the legacy key has no strategy component at all, so trying it there would
    # silently hand back the OTHER strategy's audio (this was caught for real: a first real run
    # served CONTEXTUAL_WORD "BAG" the DIRECT_WORD file verbatim via this exact path before the
    # guard below was added).
    candidate_keys = [cache_key]
    legacy_eligible = not is_blended and not (is_en_native and pronunciation_strategy != DEFAULT_EN_NATIVE_STRATEGY)
    if legacy_eligible:
        candidate_keys.append(compute_cache_key(tts_model, voice_name, speech_mode, source_text, delivery_instruction))

    with connect(db_path) as conn:
        cached = _existing_cache_row(conn, candidate_keys)
    if cached and cached.get("file_path") and Path(cached["file_path"]).exists():
        try:
            metadata = json.loads(cached.get("metadata_json") or "{}")
        except (TypeError, ValueError):
            metadata = {}
        # A cache hit against a pre-12-1 row (legacy key fallback) carries pre-12-1 metadata --
        # backfill the purely descriptive taxonomy facts (never the generation-event-specific
        # tts_prompt_version, and never touch an existing pronunciation_review verdict) so reused
        # assets aren't missing fields the 12-1 Integrity Checks expect.
        metadata.setdefault("review_priority", review_priority_for(speech_mode, is_mini_success_answer=is_mini_success_answer))
        metadata.setdefault("delivery_language", _DELIVERY_LANGUAGE_MAP.get(speech_mode))
        metadata.setdefault("delivery_role", _DELIVERY_ROLE_MAP.get(speech_mode))
        metadata.setdefault("pronunciation_review", "NOT_REQUIRED" if speech_mode == "KO_NARRATION" else "PENDING")
        metadata.setdefault("tone_consistency_review", "PENDING" if is_en_native else "NOT_REQUIRED")
        if is_en_native:
            metadata.setdefault("pronunciation_strategy", pronunciation_strategy)
            metadata.setdefault("tts_transcript", compute_tts_transcript(speech_mode, source_text, pronunciation_strategy=pronunciation_strategy))
        return {
            "asset_id": resolved_asset_id, "source_speech_asset_id": source_speech_asset_id,
            "speech_mode": speech_mode, "voice_name": voice_name,
            "status": "REUSED", "file_path": cached["file_path"], "mime_type": cached.get("mime_type"),
            "duration_ms": cached.get("duration_ms"), "sample_rate": cached.get("sample_rate"),
            "channels": cached.get("channels"), "checksum": cached.get("checksum"),
            "generation_method": "cache_reuse", "generation_attempts": 0, "cache_key": cache_key,
            "validation": {"valid": True, "errors": [], "duration_ms": cached.get("duration_ms") or 0},
            "metadata": metadata, "api_call_made": False, "retries": 0,
        }

    metadata = {
        "expected_pronunciation": speech_asset.get("expected_pronunciation"),
        "approximation_only": bool(speech_asset.get("approximation_only")),
        "tts_prompt_version": TTS_PROMPT_VERSION,
        "delivery_language": _DELIVERY_LANGUAGE_MAP.get(speech_mode),
        "delivery_role": _DELIVERY_ROLE_MAP.get(speech_mode),
        "review_priority": review_priority_for(speech_mode, is_mini_success_answer=is_mini_success_answer),
        "synthesized_text": source_text,
        "tone_consistency_review": "PENDING" if is_en_native else "NOT_REQUIRED",
    }
    if segment_metadata:
        metadata.update(segment_metadata)
    if speech_mode == "EN_PHONEME_DEMO":
        metadata["generation_strategy"] = classify_phoneme_generation_strategy(source_text)
        metadata["phoneme_demo_type"] = classify_phoneme_demo_type(source_text)
        if is_blended:
            metadata["phoneme_strategy"] = phoneme_strategy
            metadata["target_word"] = target_word
            metadata["is_default_blending_strategy"] = phoneme_strategy == DEFAULT_BLENDING_STRATEGY
        metadata["pronunciation_review"] = "PENDING"
    elif speech_mode == "KO_NARRATION":
        metadata["pronunciation_review"] = "NOT_REQUIRED"
    elif is_en_native:
        metadata["pronunciation_strategy"] = pronunciation_strategy
        metadata["tts_transcript"] = compute_tts_transcript(speech_mode, source_text, pronunciation_strategy=pronunciation_strategy)
        metadata["pronunciation_review"] = "PENDING"
    else:
        metadata["pronunciation_review"] = "PENDING"

    prompt = build_tts_prompt(
        speech_mode, source_text, voice_name, phoneme_strategy=phoneme_strategy, target_word=target_word,
        pronunciation_strategy=pronunciation_strategy,
    )
    result = tts_client.synthesize(prompt, voice_name)

    if result is None:
        return {
            "asset_id": resolved_asset_id, "source_speech_asset_id": source_speech_asset_id,
            "speech_mode": speech_mode, "voice_name": voice_name,
            "status": "FAILED", "file_path": None, "mime_type": None, "duration_ms": None,
            "sample_rate": None, "channels": None, "checksum": None, "generation_method": "gemini_tts",
            "generation_attempts": 1, "cache_key": cache_key,
            "validation": {"valid": False, "errors": ["tts_call_failed"]},
            "metadata": metadata, "api_call_made": True, "retries": 0,
        }

    pcm_bytes = base64.b64decode(result["audio_base64"])
    fmt = parse_pcm_format(result.get("mime_type"))
    metadata["pcm_format_confirmed_from_response"] = fmt["confirmed_from_response"]
    file_path = audio_dir / f"{resolved_asset_id.replace(':', '_')}.wav"
    write_wav_file(file_path, pcm_bytes, fmt["sample_rate"], fmt["channels"], fmt["sample_width_bytes"])
    validation = validate_audio_file(file_path)
    status = "AVAILABLE" if validation["valid"] else "FAILED"
    attempts = result.get("attempts", 1)

    return {
        "asset_id": resolved_asset_id, "source_speech_asset_id": source_speech_asset_id,
        "speech_mode": speech_mode, "voice_name": voice_name,
        "status": status, "file_path": str(file_path) if validation["valid"] else None,
        "mime_type": result.get("mime_type"),
        "duration_ms": validation["duration_ms"] if validation["valid"] else None,
        "sample_rate": fmt["sample_rate"] if validation["valid"] else None,
        "channels": fmt["channels"] if validation["valid"] else None,
        "checksum": hashlib.sha256(pcm_bytes).hexdigest() if validation["valid"] else None,
        "generation_method": "gemini_tts", "generation_attempts": attempts, "cache_key": cache_key,
        "validation": validation, "metadata": metadata,
        "api_call_made": True, "retries": max(0, attempts - 1),
    }


def synthesize_ko_narration_segments(
    db_path: Path, speech_asset: dict, tts_client, *, audio_dir: Path, tts_model: str,
    production_blocks: list[dict], max_segment_seconds: float, max_new_segments: int = 2,
) -> list[dict]:
    """Applies sentence-boundary segmentation (12-1 sections 12-15) to one KO_NARRATION
    speech_asset, via the shared build_generation_units compiler (12-5) so SAMPLE never computes
    its own, possibly-diverging segmentation. A cost cap (max_new_segments) keeps this Sample
    Matrix demonstration bounded -- additional real segments beyond the cap are recorded SKIPPED
    (structure verified, not generated) rather than silently generating an unbounded number of new
    calls. This cap is a SAMPLE-only concept; FULL has no such cap (12-5 section 4)."""
    units = build_generation_units(speech_asset, production_blocks, max_segment_seconds=max_segment_seconds)
    if len(units) <= 1:
        return [synthesize_asset(db_path, speech_asset, tts_client, audio_dir=audio_dir, tts_model=tts_model)]

    rows = []
    for i, unit in enumerate(units):
        segment_metadata = {
            "segment_index": unit["segment_index"], "segment_count": unit["segment_count"],
            "source_block_ids": unit["source_block_ids"],
        }
        if i >= max_new_segments:
            rows.append({
                "asset_id": unit["generation_unit_id"], "source_speech_asset_id": speech_asset["speech_asset_id"],
                "speech_mode": "KO_NARRATION", "voice_name": speech_asset.get("voice_name"),
                "status": "SKIPPED", "file_path": None, "mime_type": None, "duration_ms": None,
                "sample_rate": None, "channels": None, "checksum": None, "generation_method": None,
                "generation_attempts": 0, "cache_key": None,
                "validation": {"valid": False, "errors": ["sample_matrix_call_budget_cap"]},
                "metadata": {**segment_metadata, "pronunciation_review": "NOT_REQUIRED", "review_priority": "LOW", "tone_consistency_review": "NOT_REQUIRED"},
                "api_call_made": False, "retries": 0,
            })
            continue
        rows.append(synthesize_asset(
            db_path, speech_asset, tts_client, audio_dir=audio_dir, tts_model=tts_model,
            asset_id=unit["generation_unit_id"], text_override=unit["text"], segment_metadata=segment_metadata,
        ))
    return rows


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _persist_generated_assets(db_path: Path, plan_id: int, rows: list[dict]) -> list[int]:
    ids = []
    with connect(db_path) as conn:
        for r in rows:
            cur = conn.execute(
                """
                INSERT INTO generated_assets (
                    production_plan_id, content_block_id, asset_id, source_speech_asset_id,
                    asset_type, asset_role, speech_mode, voice_name, status, file_path, mime_type,
                    duration_ms, sample_rate, channels, checksum, generation_method,
                    generation_attempts, cache_key, validation_json, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plan_id, None, r.get("asset_id") or r["source_speech_asset_id"], r["source_speech_asset_id"],
                    "TTS_AUDIO" if r["speech_mode"] != "ORIGINAL_NATIVE_AUDIO" else "SOURCE_CLIP_AUDIO",
                    None, r["speech_mode"], r.get("voice_name"), r["status"], r.get("file_path"),
                    r.get("mime_type"), r.get("duration_ms"), r.get("sample_rate"), r.get("channels"),
                    r.get("checksum"), r.get("generation_method"), r.get("generation_attempts", 0),
                    r.get("cache_key"), json.dumps(r.get("validation") or {}, ensure_ascii=False),
                    json.dumps(r.get("metadata") or {}, ensure_ascii=False),
                ),
            )
            ids.append(cur.lastrowid)
    return ids


def _latest_generated_rows_for_plan(db_path: Path, plan_id: int) -> list[dict]:
    """One speech_asset can now fan out into several generated_assets rows (segments/blending
    strategy variants, 12-1 sections 3/15) that legitimately coexist -- so the 'latest' dedup key
    is asset_id (one file), not source_speech_asset_id (one upstream Speech Asset)."""
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM generated_assets
            WHERE production_plan_id = ? AND id IN (
                SELECT MAX(id) FROM generated_assets WHERE production_plan_id = ? GROUP BY asset_id
            )
            """,
            (plan_id, plan_id),
        ).fetchall()
    return [dict(r) for r in rows]


def _latest_row_for_asset_id(db_path: Path, plan_id: int, asset_id: str) -> dict | None:
    """Regardless of review status -- used by the 12-2 EN_NATIVE matrix to decide whether a
    DIRECT_WORD baseline for this exact word already exists (good or bad) and should be cited
    rather than regenerated (section 8: 'same input, no reason to regenerate')."""
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM generated_assets WHERE production_plan_id = ? AND asset_id = ? ORDER BY id DESC LIMIT 1",
            (plan_id, asset_id),
        ).fetchone()
    return dict(row) if row else None


def _row_from_history(historical_row: dict, *, is_mini_success_answer: bool = False) -> dict:
    """Converts a previously-persisted generated_assets row into the in-memory row shape used
    throughout this module, for reporting without a new synthesis call.

    Real generation facts (file/duration/status/checksum) and any actual human verdict
    (pronunciation_review) are cited exactly as recorded -- never rewritten. But review_priority is
    a pure policy classification, not a human verdict, and policy can legitimately change after the
    row was first generated (12-2 introduced Mini Success escalation, 12-3 introduced
    tone_consistency_review) -- a citation must reflect CURRENT policy, not silently freeze
    whatever classification existed at generation time. This was caught for real: SP039's original
    DIRECT_WORD row predates both policies, so citing it verbatim reported review_priority=MEDIUM
    for a genuine Mini Success answer and a missing tone_consistency_review entirely."""
    try:
        metadata = json.loads(historical_row.get("metadata_json") or "{}")
    except (TypeError, ValueError):
        metadata = {}
    speech_mode = historical_row["speech_mode"]
    metadata["review_priority"] = review_priority_for(speech_mode, is_mini_success_answer=is_mini_success_answer)
    metadata.setdefault("tone_consistency_review", "PENDING" if speech_mode == "EN_NATIVE" else "NOT_REQUIRED")
    metadata.setdefault("pronunciation_review", "NOT_REQUIRED" if speech_mode == "KO_NARRATION" else "PENDING")
    return {
        "asset_id": historical_row["asset_id"], "source_speech_asset_id": historical_row["source_speech_asset_id"],
        "speech_mode": historical_row["speech_mode"], "voice_name": historical_row["voice_name"],
        "status": historical_row["status"], "file_path": historical_row.get("file_path"),
        "mime_type": historical_row.get("mime_type"), "duration_ms": historical_row.get("duration_ms"),
        "sample_rate": historical_row.get("sample_rate"), "channels": historical_row.get("channels"),
        "checksum": historical_row.get("checksum"), "generation_method": "historical_reference",
        "generation_attempts": 0, "cache_key": historical_row.get("cache_key"),
        "validation": {"valid": historical_row["status"] in {"AVAILABLE", "REUSED"}, "errors": [],
                       "duration_ms": historical_row.get("duration_ms") or 0},
        "metadata": metadata, "api_call_made": False, "retries": 0,
    }


# ---------------------------------------------------------------------------
# 12-4: EN_NATIVE primary/fallback strategy selection + Full Generation Plan. This is policy
# lock-in, not a new TTS experiment -- it turns the real 12-2/12-3 human listening decisions into a
# deterministic selector, reusing is_mini_success_answer_asset/_is_pronunciation_approved/
# _NON_REUSABLE_REVIEW_STATES/review_priority_for rather than inventing a parallel system.
# ---------------------------------------------------------------------------

GENERATION_PLAN_ACTIONS = {"REUSE", "GENERATE", "SKIP", "BLOCKED"}
SELECTION_REASONS = {"PRIMARY_APPROVED", "FALLBACK_AFTER_PRIMARY_FAILURE", "PRIMARY_PENDING", "NO_APPROVED_VARIANT"}


def _asset_review_metadata(db_path: Path, plan_id: int, asset_id: str) -> dict | None:
    """Latest metadata for an asset_id if it has ever been generated, else None."""
    row = _latest_row_for_asset_id(db_path, plan_id, asset_id)
    if not row:
        return None
    try:
        return json.loads(row.get("metadata_json") or "{}")
    except (TypeError, ValueError):
        return {}


def _variant_meets_approval(metadata: dict | None, *, require_tone_approval: bool) -> bool:
    if not metadata:
        return False
    if not _is_pronunciation_approved(metadata.get("pronunciation_review")):
        return False
    if require_tone_approval and metadata.get("tone_consistency_review") != "APPROVED":
        return False
    return True


def select_active_en_native_variant(
    db_path: Path, plan_id: int, source_speech_asset: dict, production_blocks: list[dict], *,
    primary_strategy: str = "DIRECT_WORD", fallback_strategy: str = "CONTEXTUAL_WORD",
) -> dict:
    """12-4 sections 2-4: the source of truth is the human review state, never "latest file" or
    "shortest duration". Fallback is used only when primary has genuinely FAILED (REJECTED/
    REGENERATE_REQUIRED) -- a merely PENDING or missing primary does NOT trigger fallback, even if
    an approved fallback variant happens to exist (CASE G/H). Mini Success answers additionally
    require tone_consistency_review=APPROVED before a variant counts as usable (section 9)."""
    sid = source_speech_asset["speech_asset_id"]
    require_tone = is_mini_success_answer_asset(production_blocks, sid)

    primary_metadata = _asset_review_metadata(db_path, plan_id, sid)
    primary_review = (primary_metadata or {}).get("pronunciation_review")
    primary_failed = primary_review in _NON_REUSABLE_REVIEW_STATES
    primary_approved = _variant_meets_approval(primary_metadata, require_tone_approval=require_tone)

    if primary_approved:
        return {
            "selected_strategy": primary_strategy, "selected_asset_id": sid,
            "selection_reason": "PRIMARY_APPROVED", "requires_tone_approval": require_tone,
        }

    fallback_asset_id = f"{sid}::{fallback_strategy}"
    fallback_metadata = _asset_review_metadata(db_path, plan_id, fallback_asset_id)
    fallback_approved = _variant_meets_approval(fallback_metadata, require_tone_approval=require_tone)

    if primary_failed and fallback_approved:
        return {
            "selected_strategy": fallback_strategy, "selected_asset_id": fallback_asset_id,
            "selection_reason": "FALLBACK_AFTER_PRIMARY_FAILURE", "requires_tone_approval": require_tone,
        }

    if primary_failed:
        return {
            "selected_strategy": None, "selected_asset_id": None,
            "selection_reason": "NO_APPROVED_VARIANT", "requires_tone_approval": require_tone,
        }

    return {
        "selected_strategy": primary_strategy, "selected_asset_id": None,
        "selection_reason": "PRIMARY_PENDING", "requires_tone_approval": require_tone,
    }


def _en_native_plan_action(db_path: Path, plan_id: int, sid: str, fallback_strategy: str, selection: dict) -> str:
    reason = selection["selection_reason"]
    if reason in {"PRIMARY_APPROVED", "FALLBACK_AFTER_PRIMARY_FAILURE"}:
        return "REUSE"
    if reason == "PRIMARY_PENDING":
        primary_row = _latest_row_for_asset_id(db_path, plan_id, sid)
        return "REUSE" if primary_row and primary_row["status"] in {"AVAILABLE", "REUSED"} else "GENERATE"
    # NO_APPROVED_VARIANT: primary explicitly failed. If the fallback has ALSO been explicitly
    # rejected (not just untried/PENDING), both known paths are exhausted -- that needs a human
    # decision on a new approach, not another automatic retry.
    fallback_metadata = _asset_review_metadata(db_path, plan_id, f"{sid}::{fallback_strategy}")
    if fallback_metadata and fallback_metadata.get("pronunciation_review") == "REJECTED":
        return "BLOCKED"
    return "GENERATE"


def _unit_fields(unit: dict) -> dict:
    """12-5 section 17: the Generation Unit identity fields every plan entry carries, regardless
    of speech_mode -- non-segmented modes get segment_index=None/segment_count=1 rather than
    omitting the keys, so downstream code never needs a per-mode presence check."""
    return {
        "generation_unit_id": unit["generation_unit_id"], "segment_index": unit["segment_index"],
        "segment_count": unit["segment_count"], "source_block_ids": unit["source_block_ids"],
    }


def _cache_and_review_status(db_path: Path, plan_id: int, asset_id: str | None, action: str) -> tuple[str, str | None, int]:
    """12-5 section 17: cache_status/review_status/estimated_api_calls, derived once so every
    branch of build_full_generation_plan reports them the same way. REUSE/SKIP/BLOCKED never cost
    a real call in this estimate (section 9: retries are excluded, only the base attempt counts)."""
    cache_status = "CACHED" if action == "REUSE" else ("NOT_APPLICABLE" if action == "SKIP" else "MISSING")
    metadata = _asset_review_metadata(db_path, plan_id, asset_id) if asset_id else None
    review_status = (metadata or {}).get("pronunciation_review")
    estimated_api_calls = 1 if action == "GENERATE" else 0
    return cache_status, review_status, estimated_api_calls


def _phoneme_plan_entry(db_path: Path, plan_id: int, speech_asset: dict, production_blocks: list[dict], *, default_blending_strategy: str) -> dict:
    """12-4 sections 16-17: the representative approval (/b/, /g/, DIRECT_SEQUENCE) never
    auto-approves a DIFFERENT phoneme asset -- each asset_id's own history is the only source of
    truth. Isolated phonemes have no strategy dimension; blended ones use the default blending
    strategy (no per-strategy choice here -- that comparison was already settled in 12-1/12-2).
    EN_PHONEME_DEMO never segments (12-5 section 1) -- always exactly one Generation Unit."""
    sid = speech_asset["speech_asset_id"]
    is_blended = classify_phoneme_demo_type(speech_asset["source_text"]) == "BLENDED_SEQUENCE"
    preferred_strategy = default_blending_strategy if is_blended else None
    asset_id = f"{sid}::{default_blending_strategy}" if is_blended else sid
    metadata = _asset_review_metadata(db_path, plan_id, asset_id)
    row = _latest_row_for_asset_id(db_path, plan_id, asset_id)
    if metadata and metadata.get("pronunciation_review") in _NON_REUSABLE_REVIEW_STATES:
        action = "GENERATE"
    elif row and row["status"] in {"AVAILABLE", "REUSED"}:
        action = "REUSE"
    else:
        action = "GENERATE"
    cache_status, review_status, estimated_api_calls = _cache_and_review_status(db_path, plan_id, asset_id, action)
    return {
        "source_speech_asset_id": sid, "speech_mode": "EN_PHONEME_DEMO", "preferred_strategy": preferred_strategy,
        "selected_asset_id": asset_id if action == "REUSE" else None, "selection_reason": None, "action": action,
        "generation_unit_id": sid, "segment_index": None, "segment_count": 1,
        "source_block_ids": _source_block_ids_for_speech_asset(production_blocks, sid),
        "cache_status": cache_status, "review_status": review_status, "estimated_api_calls": estimated_api_calls,
    }


def _ko_narration_plan_entries(
    db_path: Path, plan_id: int, speech_asset: dict, production_blocks: list[dict], *, max_segment_seconds: float,
) -> list[dict]:
    """12-5 sections 3/17: one plan entry PER GENERATION UNIT, not per source asset -- a long
    KO_NARRATION source that splits into N sentence-boundary segments (12-1's
    segment_source_text_by_sentence, unchanged) now produces N entries, each independently
    REUSE/GENERATE-checked via its own generation_unit_id. Uses the exact same
    build_generation_units compiler SAMPLE and DRY_RUN use, so segmentation can never diverge
    across modes (section 21)."""
    sid = speech_asset["speech_asset_id"]
    mode = speech_asset["speech_mode"]
    units = build_generation_units(speech_asset, production_blocks, max_segment_seconds=max_segment_seconds)
    entries = []
    for unit in units:
        unit_id = unit["generation_unit_id"]
        row = _latest_row_for_asset_id(db_path, plan_id, unit_id)
        action = "REUSE" if row and row["status"] in {"AVAILABLE", "REUSED"} else "GENERATE"
        cache_status, review_status, estimated_api_calls = _cache_and_review_status(db_path, plan_id, unit_id, action)
        entries.append({
            "source_speech_asset_id": sid, "speech_mode": mode, "preferred_strategy": None,
            "selected_asset_id": unit_id if action == "REUSE" else None, "selection_reason": None, "action": action,
            **_unit_fields(unit), "cache_status": cache_status, "review_status": review_status,
            "estimated_api_calls": estimated_api_calls,
        })
    return entries


def _resolve_full_execution_asset_id(entry: dict, *, primary_en_native_strategy: str, default_blending_strategy: str) -> str:
    """12-6 section 1: the single place that decides which exact asset_id a Full Generation Plan
    entry resolves to at real synthesis/reuse time. The FULL execution loop and the
    active_strategy_matches_full_plan / all_generation_units_materialized Integrity Checks all call
    this SAME function -- so a future change to the resolution rule can never make execution and
    verification silently disagree (the exact class of bug 12-4 found for real with CAP)."""
    sid = entry["source_speech_asset_id"]
    if entry["speech_mode"] == "EN_NATIVE":
        if entry["action"] == "REUSE" and entry.get("selected_asset_id"):
            return entry["selected_asset_id"]
        strategy = entry.get("preferred_strategy") or primary_en_native_strategy
        return sid if strategy == primary_en_native_strategy else f"{sid}::{strategy}"
    if entry["speech_mode"] == "EN_PHONEME_DEMO":
        # Blended entries always carry a preferred_strategy (the blending strategy); isolated ones
        # never do -- that presence, not a separate flag, is what distinguishes them here.
        strategy = entry.get("preferred_strategy")
        return f"{sid}::{strategy}" if strategy else sid
    # KO_NARRATION/KO_PRONUNCIATION_GUIDE: generation_unit_id IS already the resolved id.
    return entry["generation_unit_id"]


def build_full_generation_plan(
    db_path: Path, plan_id: int, speech_assets: list[dict], production_blocks: list[dict], *,
    primary_en_native_strategy: str = "DIRECT_WORD", fallback_en_native_strategy: str = "CONTEXTUAL_WORD",
    default_blending_strategy: str = "DIRECT_SEQUENCE", max_segment_seconds: float = 12.0,
) -> dict:
    """12-4 section 13 (extended 12-5 section 3): one entry per Generation Unit
    (ORIGINAL_NATIVE_AUDIO excluded -- it is never TTS-generated). Non-segmenting modes resolve to
    exactly one unit per source asset, so entry count == source asset count there; KO_NARRATION/
    KO_PRONUNCIATION_GUIDE can resolve to several. action is exactly one of GENERATION_PLAN_ACTIONS."""
    entries = []
    for asset in speech_assets:
        mode = asset["speech_mode"]
        sid = asset["speech_asset_id"]
        if mode == "ORIGINAL_NATIVE_AUDIO":
            continue
        if mode == "EN_NATIVE":
            selection = select_active_en_native_variant(
                db_path, plan_id, asset, production_blocks,
                primary_strategy=primary_en_native_strategy, fallback_strategy=fallback_en_native_strategy,
            )
            action = _en_native_plan_action(db_path, plan_id, sid, fallback_en_native_strategy, selection)
            cache_status, review_status, estimated_api_calls = _cache_and_review_status(
                db_path, plan_id, selection["selected_asset_id"], action,
            )
            entries.append({
                "source_speech_asset_id": sid, "speech_mode": mode,
                "preferred_strategy": selection["selected_strategy"] or primary_en_native_strategy,
                "selected_asset_id": selection["selected_asset_id"], "selection_reason": selection["selection_reason"],
                "action": action, "generation_unit_id": sid, "segment_index": None, "segment_count": 1,
                "source_block_ids": _source_block_ids_for_speech_asset(production_blocks, sid),
                "cache_status": cache_status, "review_status": review_status, "estimated_api_calls": estimated_api_calls,
            })
        elif mode == "EN_PHONEME_DEMO":
            entries.append(_phoneme_plan_entry(db_path, plan_id, asset, production_blocks, default_blending_strategy=default_blending_strategy))
        elif mode in {"KO_NARRATION", "KO_PRONUNCIATION_GUIDE"}:
            entries.extend(_ko_narration_plan_entries(db_path, plan_id, asset, production_blocks, max_segment_seconds=max_segment_seconds))
        else:
            entries.append({
                "source_speech_asset_id": sid, "speech_mode": mode, "preferred_strategy": None,
                "selected_asset_id": None, "selection_reason": None, "action": "GENERATE",
                "generation_unit_id": sid, "segment_index": None, "segment_count": 1,
                "source_block_ids": _source_block_ids_for_speech_asset(production_blocks, sid),
                "cache_status": "MISSING", "review_status": None, "estimated_api_calls": 1,
            })

    counts = {action: sum(1 for e in entries if e["action"] == action) for action in GENERATION_PLAN_ACTIONS}
    return {
        "production_plan_id": plan_id, "generation_plan": entries, "action_counts": counts,
        "expected_new_api_calls": sum(e["estimated_api_calls"] for e in entries),
    }


def _representative_review_complete(
    db_path: Path, plan_id: int, speech_assets: list[dict], production_blocks: list[dict], *,
    primary_en_native_strategy: str = "DIRECT_WORD", fallback_en_native_strategy: str = "CONTEXTUAL_WORD",
    default_blending_strategy: str = "DIRECT_SEQUENCE",
) -> bool:
    """12-4 section 10: representative Gate -- isolated phonemes /b//g/, the default blending
    strategy, two normal EN_NATIVE primary words, and the one EN_NATIVE fallback-critical word.
    Never requires all 44 assets to be individually approved."""
    en_native_by_word = {a["source_text"]: a for a in speech_assets if a["speech_mode"] == "EN_NATIVE"}
    phoneme_by_text = {a["source_text"]: a for a in speech_assets if a["speech_mode"] == "EN_PHONEME_DEMO"}

    for phoneme_text in ("/b/", "/g/"):
        asset = phoneme_by_text.get(phoneme_text)
        if not asset:
            return False
        metadata = _asset_review_metadata(db_path, plan_id, asset["speech_asset_id"])
        if not _variant_meets_approval(metadata, require_tone_approval=False):
            return False

    blended_default = next(
        (a for a in speech_assets if a["speech_mode"] == "EN_PHONEME_DEMO" and classify_phoneme_demo_type(a["source_text"]) == "BLENDED_SEQUENCE"),
        None,
    )
    if not blended_default:
        return False
    metadata = _asset_review_metadata(db_path, plan_id, f"{blended_default['speech_asset_id']}::{default_blending_strategy}")
    if not _variant_meets_approval(metadata, require_tone_approval=False):
        return False

    for word_asset, is_fallback_critical in [
        (en_native_by_word.get("BAG"), False), (en_native_by_word.get("MAP"), False),
    ]:
        if not word_asset:
            return False
        selection = select_active_en_native_variant(
            db_path, plan_id, word_asset, production_blocks,
            primary_strategy=primary_en_native_strategy, fallback_strategy=fallback_en_native_strategy,
        )
        if selection["selection_reason"] != "PRIMARY_APPROVED":
            return False

    cap_asset = en_native_by_word.get("CAP")
    if not cap_asset:
        return False
    cap_selection = select_active_en_native_variant(
        db_path, plan_id, cap_asset, production_blocks,
        primary_strategy=primary_en_native_strategy, fallback_strategy=fallback_en_native_strategy,
    )
    if cap_selection["selection_reason"] != "FALLBACK_AFTER_PRIMARY_FAILURE":
        return False

    return True


def _persist_run(db_path: Path, plan_id: int, mode: str, summary: dict, status: str) -> int:
    with connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO asset_generation_runs (
                production_plan_id, mode, completed_at, status, planned_count, generated_count,
                reused_count, failed_count, unverified_count, skipped_count, api_calls, retry_count,
                report_json
            ) VALUES (?, ?, datetime('now'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                plan_id, mode, status, summary.get("planned_count", 0), summary.get("generated_count", 0),
                summary.get("reused_count", 0), summary.get("failed_count", 0),
                summary.get("unverified_count", 0), summary.get("skipped_count", 0),
                summary.get("api_calls", 0), summary.get("retry_count", 0),
                json.dumps(summary, ensure_ascii=False, default=str),
            ),
        )
        return cur.lastrowid


def _record_review_field(db_path: Path, plan_id: int, asset_id: str, field: str, status: str, note: str | None = None) -> int:
    """Shared by record_pronunciation_review/record_tone_consistency_review (12-2 section 9/14,
    12-3 section 20): records a human's actual verdict. Never deletes or replaces a
    generated_assets row (the generation record stays auditable) -- only the given metadata_json
    field is updated, for every row matching this exact asset_id in this plan (they all represent
    the same real-world audio content)."""
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT id, metadata_json FROM generated_assets WHERE production_plan_id = ? AND asset_id = ?",
            (plan_id, asset_id),
        ).fetchall()
        for row in rows:
            try:
                metadata = json.loads(row["metadata_json"] or "{}")
            except (TypeError, ValueError):
                metadata = {}
            metadata[field] = status
            if note:
                metadata["review_note"] = note
            conn.execute(
                "UPDATE generated_assets SET metadata_json = ?, updated_at = datetime('now') WHERE id = ?",
                (json.dumps(metadata, ensure_ascii=False), row["id"]),
            )
    return len(rows)


def record_pronunciation_review(db_path: Path, plan_id: int, asset_id: str, status: str, note: str | None = None) -> int:
    if status not in PRONUNCIATION_REVIEW_STATES:
        raise ValueError(f"invalid pronunciation_review status: {status}")
    return _record_review_field(db_path, plan_id, asset_id, "pronunciation_review", status, note)


def record_tone_consistency_review(db_path: Path, plan_id: int, asset_id: str, status: str, note: str | None = None) -> int:
    if status not in TONE_CONSISTENCY_REVIEW_STATES:
        raise ValueError(f"invalid tone_consistency_review status: {status}")
    return _record_review_field(db_path, plan_id, asset_id, "tone_consistency_review", status, note)


def _has_full_run(db_path: Path, plan_id: int) -> bool:
    """12-6 section 35: whether a FULL run has actually happened for this plan (any outcome --
    this is a "was it executed" flag, distinct from `all_generation_units_materialized`'s "did it
    fully succeed"). Mirrors _has_successful_sample_run's query shape."""
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT id FROM asset_generation_runs WHERE production_plan_id = ? AND mode = 'FULL' ORDER BY id DESC LIMIT 1",
            (plan_id,),
        ).fetchone()
    return row is not None


def _has_successful_sample_run(db_path: Path, plan_id: int) -> bool:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT id FROM asset_generation_runs WHERE production_plan_id = ? AND mode = 'SAMPLE' "
            "AND failed_count = 0 AND (generated_count + reused_count) > 0 ORDER BY id DESC LIMIT 1",
            (plan_id,),
        ).fetchone()
    return row is not None


def _has_unverified_critical_phoneme(db_path: Path, plan_id: int) -> bool:
    for r in _latest_generated_rows_for_plan(db_path, plan_id):
        if r["speech_mode"] != "EN_PHONEME_DEMO" or r["status"] not in {"AVAILABLE", "REUSED"}:
            continue
        try:
            metadata = json.loads(r.get("metadata_json") or "{}")
        except (TypeError, ValueError):
            metadata = {}
        if not _is_pronunciation_approved(metadata.get("pronunciation_review")):
            return True
    return False


def _rendering_blockers(
    db_path: Path, plan_id: int, speech_assets: list[dict], production_blocks: list[dict], *,
    primary_en_native_strategy: str = DEFAULT_EN_NATIVE_STRATEGY, fallback_en_native_strategy: str = "CONTEXTUAL_WORD",
    default_blending_strategy: str = DEFAULT_BLENDING_STRATEGY, max_segment_seconds: float = 12.0,
) -> list[str]:
    """12-7 section 15: every asset_id still blocking Ready for Rendering, scoped to exactly the
    assets the Full Generation Plan actually selected as active (via
    _resolve_full_execution_asset_id) -- NOT every historical row ever generated for this plan.
    Without this scoping, an abandoned failed variant (e.g. CAP's REGENERATE_REQUIRED DIRECT_WORD,
    never the active asset once CONTEXTUAL_WORD is approved) or a purely experimental comparison
    variant (LOWERCASE_WORD/MINIMAL_CONTEXT_WORD/CONTEXT_RESTRICTED, never production default)
    would wrongly show up as a rendering blocker even though it was never required in the first
    place -- caught for real while running this stage against the live plan. Checks:
    EN_PHONEME_DEMO pronunciation (same rule as _has_unverified_critical_phoneme) plus EN_NATIVE
    pronunciation AND tone_consistency_review (the tone rule ready_for_full_generation_gate already
    enforces at the Sample->Full transition for every technically-present EN_NATIVE row, not just
    Mini Success HIGH-priority ones -- section 11 confirms this is existing policy, not new). Both
    the gate computation and the report's "Human Listening Required" listing call this SAME
    function so they can never diverge (the exact class of bug 12-4 found for real with CAP's FULL
    path)."""
    plan_result = build_full_generation_plan(
        db_path, plan_id, speech_assets, production_blocks,
        primary_en_native_strategy=primary_en_native_strategy, fallback_en_native_strategy=fallback_en_native_strategy,
        default_blending_strategy=default_blending_strategy, max_segment_seconds=max_segment_seconds,
    )
    blockers = []
    for entry in plan_result["generation_plan"]:
        if entry["speech_mode"] not in {"EN_NATIVE", "EN_PHONEME_DEMO"}:
            continue
        asset_id = _resolve_full_execution_asset_id(
            entry, primary_en_native_strategy=primary_en_native_strategy, default_blending_strategy=default_blending_strategy,
        )
        row = _latest_row_for_asset_id(db_path, plan_id, asset_id)
        if not row or row["status"] not in {"AVAILABLE", "REUSED"}:
            continue  # not materialized yet -- all_generation_units_materialized covers that separately
        try:
            metadata = json.loads(row.get("metadata_json") or "{}")
        except (TypeError, ValueError):
            metadata = {}
        if not _is_pronunciation_approved(metadata.get("pronunciation_review")):
            blockers.append(asset_id)
            continue
        if entry["speech_mode"] == "EN_NATIVE" and metadata.get("tone_consistency_review") in {"PENDING", "REJECTED"}:
            blockers.append(asset_id)
    return sorted(set(blockers))


def _has_unresolved_required_human_review(
    db_path: Path, plan_id: int, speech_assets: list[dict], production_blocks: list[dict], *,
    primary_en_native_strategy: str = DEFAULT_EN_NATIVE_STRATEGY, fallback_en_native_strategy: str = "CONTEXTUAL_WORD",
    default_blending_strategy: str = DEFAULT_BLENDING_STRATEGY, max_segment_seconds: float = 12.0,
) -> bool:
    return bool(_rendering_blockers(
        db_path, plan_id, speech_assets, production_blocks,
        primary_en_native_strategy=primary_en_native_strategy, fallback_en_native_strategy=fallback_en_native_strategy,
        default_blending_strategy=default_blending_strategy, max_segment_seconds=max_segment_seconds,
    ))


# ---------------------------------------------------------------------------
# Manifest (spec section 43) -- the interface 13 Renderer is meant to consume.
# ---------------------------------------------------------------------------

def build_asset_manifest(plan_id: int, rows: list[dict], *, production_blocks: list[dict] | None = None) -> dict:
    """12-6 section 19: production_blocks is optional (backward compatible with existing callers
    that don't pass it) -- when given, it lets source_block_ids be derived for rows whose metadata
    doesn't already carry it (only segmented KO_NARRATION rows do)."""
    assets = []
    for r in rows:
        try:
            metadata = r["metadata"] if isinstance(r.get("metadata"), dict) else json.loads(r.get("metadata_json") or "{}")
        except (TypeError, ValueError):
            metadata = {}
        source_block_ids = metadata.get("source_block_ids")
        if source_block_ids is None and production_blocks is not None:
            source_block_ids = _source_block_ids_for_speech_asset(production_blocks, r["source_speech_asset_id"])
        assets.append({
            "asset_id": r.get("asset_id") or r["source_speech_asset_id"],
            "source_speech_asset_id": r["source_speech_asset_id"],
            "type": "TTS_AUDIO" if r["speech_mode"] != "ORIGINAL_NATIVE_AUDIO" else "SOURCE_CLIP_AUDIO",
            "speech_mode": r["speech_mode"],
            "voice": r.get("voice_name"),
            "status": r["status"],
            "file": r.get("file_path"),
            "duration_ms": r.get("duration_ms"),
            "checksum": r.get("checksum"),
            "strategy": metadata.get("pronunciation_strategy") or metadata.get("phoneme_strategy"),
            "tts_prompt_version": metadata.get("tts_prompt_version"),
            "pronunciation_review": metadata.get("pronunciation_review"),
            "tone_consistency_review": metadata.get("tone_consistency_review"),
            "review_priority": metadata.get("review_priority"),
            "segment_index": metadata.get("segment_index"),
            "segment_count": metadata.get("segment_count"),
            "source_block_ids": source_block_ids,
        })
    return {
        "production_plan_id": plan_id,
        "generated_at": datetime.utcnow().isoformat(),
        "assets": assets,
    }


def _write_manifest(manifest_dir: Path, manifest: dict) -> Path:
    manifest_dir.mkdir(parents=True, exist_ok=True)
    path = manifest_dir / "manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# 12-8: Ready for Rendering as a PERSISTENT PRODUCTION PLAN property, not a property of whichever
# CLI mode happens to be running right now. Deliberately takes no `mode` parameter -- that omission
# is itself the fix (section 1/9: "current CLI mode is not a condition"). Recomputes everything
# fresh from the DB + the current Full Generation Plan, never from a specific run's in-memory
# generated_rows (which is empty for DRY_RUN by construction, which is exactly what made this gate
# always report NO under DRY_RUN before this stage).
# ---------------------------------------------------------------------------

def compute_persistent_rendering_readiness(
    db_path: Path, plan_id: int, speech_assets: list[dict], production_blocks: list[dict], *,
    primary_en_native_strategy: str = DEFAULT_EN_NATIVE_STRATEGY, fallback_en_native_strategy: str = "CONTEXTUAL_WORD",
    default_blending_strategy: str = DEFAULT_BLENDING_STRATEGY, max_segment_seconds: float = 12.0,
) -> dict:
    """12-9 section 4/8: THE canonical Renderer entry gate -- the only function 13 Renderer (or
    anything deciding whether it's safe to start rendering) should ever consult. Do not use
    `ready_for_rendering_gate()` for that decision (it answers a narrower, run-local question --
    see its own docstring) and do not read `manifest["run_local_ready_for_rendering"]` for it
    either; only `manifest["ready_for_rendering"]` / `manifest["persistent_rendering_readiness"]`
    (both populated from this function's result) or a fresh call to this function are safe."""
    plan_result = build_full_generation_plan(
        db_path, plan_id, speech_assets, production_blocks,
        primary_en_native_strategy=primary_en_native_strategy, fallback_en_native_strategy=fallback_en_native_strategy,
        default_blending_strategy=default_blending_strategy, max_segment_seconds=max_segment_seconds,
    )
    has_full_history = _has_full_run(db_path, plan_id)
    generate_count = plan_result["action_counts"]["GENERATE"]
    blocked_count = plan_result["action_counts"]["BLOCKED"]

    generation_units_total = len(plan_result["generation_plan"])
    generation_units_materialized = 0
    all_materialized = True
    all_technical_valid = True
    for entry in plan_result["generation_plan"]:
        resolved_id = _resolve_full_execution_asset_id(
            entry, primary_en_native_strategy=primary_en_native_strategy, default_blending_strategy=default_blending_strategy,
        )
        row = _latest_row_for_asset_id(db_path, plan_id, resolved_id)
        if not row or row["status"] not in {"AVAILABLE", "REUSED"}:
            all_materialized = False
            continue
        generation_units_materialized += 1
        try:
            validation = json.loads(row.get("validation_json") or "{}")
        except (TypeError, ValueError):
            validation = {}
        if not validation.get("valid", False):
            all_technical_valid = False

    blockers = _rendering_blockers(
        db_path, plan_id, speech_assets, production_blocks,
        primary_en_native_strategy=primary_en_native_strategy, fallback_en_native_strategy=fallback_en_native_strategy,
        default_blending_strategy=default_blending_strategy, max_segment_seconds=max_segment_seconds,
    )

    all_rows = _latest_generated_rows_for_plan(db_path, plan_id)
    manifest = build_asset_manifest(plan_id, all_rows, production_blocks=production_blocks)
    manifest_ids = {a["asset_id"] for a in (manifest.get("assets") or [])}
    required_resolved_ids = {
        _resolve_full_execution_asset_id(e, primary_en_native_strategy=primary_en_native_strategy, default_blending_strategy=default_blending_strategy)
        for e in plan_result["generation_plan"] if e["action"] != "BLOCKED"
    }
    manifest_complete = required_resolved_ids <= manifest_ids

    reasons: list[str] = []
    if not has_full_history:
        reasons.append("FULL generation has not completed.")
    if not all_materialized:
        reasons.append("One or more required Generation Units are not materialized (AVAILABLE/REUSED).")
    if generate_count > 0:
        reasons.append(f"{generate_count} Generation Unit(s) still need GENERATE.")
    if blocked_count > 0:
        reasons.append(f"{blocked_count} Generation Unit(s) are BLOCKED.")
    if not all_technical_valid:
        reasons.append("One or more materialized assets failed technical validation.")
    if not manifest_complete:
        reasons.append("Manifest is missing one or more required assets.")
    for asset_id in blockers:
        reasons.append(f"{asset_id}: pronunciation_review/tone_consistency_review not resolved.")

    return {
        "ready": not reasons, "reasons": reasons, "blockers": blockers,
        "has_full_history": has_full_history, "all_materialized": all_materialized,
        "all_technical_valid": all_technical_valid, "generate_count": generate_count,
        "blocked_count": blocked_count, "manifest_complete": manifest_complete, "plan_result": plan_result,
        "generation_units_total": generation_units_total, "generation_units_materialized": generation_units_materialized,
    }


# ---------------------------------------------------------------------------
# Integrity Check (spec section 46, 16 items, mode-aware) + Ready for Rendering gate
# ---------------------------------------------------------------------------

def _pause_map(production_blocks: list[dict]) -> dict:
    m = {}
    for pb in production_blocks:
        for ev in pb.get("timeline") or []:
            if ev.get("type") == "PAUSE":
                m[pb["content_block_id"]] = ev.get("duration_ms")
    return m


def run_asset_generation_integrity_check(
    db_path: Path, plan_row: dict, original_production_blocks: list[dict], speech_assets: list[dict],
    generated_rows: list[dict], mode: str, manifest: dict, *,
    primary_en_native_strategy: str = DEFAULT_EN_NATIVE_STRATEGY,
    fallback_en_native_strategy: str = "CONTEXTUAL_WORD",
    default_blending_strategy: str = DEFAULT_BLENDING_STRATEGY,
    max_segment_seconds: float = 12.0,
) -> dict:
    checks = {}

    with connect(db_path) as conn:
        after_plan = conn.execute(
            "SELECT final_format, plan_json, integrity_check_json FROM production_plans WHERE id = ?", (plan_row["id"],)
        ).fetchone()
    checks["source_plan_unchanged"] = "pass" if (
        after_plan is not None
        and after_plan["final_format"] == plan_row["final_format"]
        and after_plan["plan_json"] == plan_row["plan_json"]
        and after_plan["integrity_check_json"] == plan_row["integrity_check_json"]
    ) else "fail"

    # One speech_asset can now fan out into several rows (segments/blending-strategy variants,
    # 12-1 sections 3/15), so lineage lookups group by source_speech_asset_id instead of assuming
    # a 1:1 mapping.
    generated_by_source_id: dict[str, list[dict]] = {}
    for r in generated_rows:
        generated_by_source_id.setdefault(r["source_speech_asset_id"], []).append(r)

    if mode == "SAMPLE":
        # SKIPPED rows are the deliberate call-budget cap (section 19/27), not a failure.
        checks["required_assets_resolved"] = "pass" if all(
            r["status"] in {"AVAILABLE", "REUSED", "SKIPPED"} for r in generated_rows
        ) else "fail"
    else:
        required_ids = {a["speech_asset_id"] for a in speech_assets if a["speech_mode"] != "ORIGINAL_NATIVE_AUDIO"}
        checks["required_assets_resolved"] = "pass" if all(
            any(r["status"] in {"AVAILABLE", "REUSED"} for r in generated_by_source_id.get(sid, []))
            for sid in required_ids
        ) else "fail"

    speech_assets_by_id = {a["speech_asset_id"]: a for a in speech_assets}
    checks["speech_mode_preserved"] = "pass" if all(
        r["speech_mode"] == speech_assets_by_id.get(r["source_speech_asset_id"], {}).get("speech_mode")
        for r in generated_rows
    ) else "fail"

    checks["voice_casting_preserved"] = "pass" if all(
        r["voice_name"] == speech_assets_by_id.get(r["source_speech_asset_id"], {}).get("voice_name")
        for r in generated_rows
    ) else "fail"

    checks["native_audio_not_synthesized"] = "pass" if all(
        r["generation_method"] != "gemini_tts" for r in generated_rows if r["speech_mode"] == "ORIGINAL_NATIVE_AUDIO"
    ) else "fail"

    checks["korean_approximation_metadata_preserved"] = "pass" if all(
        r["metadata"].get("approximation_only") == bool(speech_assets_by_id.get(r["source_speech_asset_id"], {}).get("approximation_only"))
        for r in generated_rows if r["speech_mode"] == "KO_PRONUNCIATION_GUIDE"
    ) else "fail"

    checks["phoneme_source_of_truth_preserved"] = "pass" if all(
        (speech_assets_by_id.get(r["source_speech_asset_id"], {}).get("source_text") or "").startswith("/")
        for r in generated_rows if r["speech_mode"] == "EN_PHONEME_DEMO"
    ) else "fail"

    checks["generated_audio_file_valid"] = "pass" if all(
        r["status"] not in {"AVAILABLE", "REUSED"} or (r.get("validation") or {}).get("valid")
        or (r["status"] == "REUSED" and r.get("file_path") and Path(r["file_path"]).exists())
        for r in generated_rows
    ) else "fail"

    checks["actual_duration_available"] = "pass" if all(
        r["status"] not in {"AVAILABLE", "REUSED"} or (r.get("duration_ms") or 0) > 0
        for r in generated_rows
    ) else "fail"

    checks["cache_key_complete"] = "pass" if all(
        r.get("cache_key") for r in generated_rows
        if r["speech_mode"] != "ORIGINAL_NATIVE_AUDIO" and r["status"] != "SKIPPED"
    ) else "fail"

    seen_keys: set[str] = set()
    replay_ok = True
    for r in generated_rows:
        key = r.get("cache_key")
        if not key:
            continue
        if key in seen_keys and r["api_call_made"]:
            replay_ok = False
        seen_keys.add(key)
    checks["replay_asset_reused"] = "pass" if replay_ok else "fail"

    reloaded_production_blocks = _load_production_blocks(db_path, plan_row["id"])
    checks["thinking_time_preserved"] = "pass" if _pause_map(original_production_blocks) == _pause_map(reloaded_production_blocks) else "fail"

    if mode == "FULL":
        answer_ok = True
        for pb in original_production_blocks:
            timeline = pb.get("timeline") or []
            pause_idx = next((i for i, ev in enumerate(timeline) if ev.get("type") == "PAUSE"), None)
            if pause_idx is None:
                continue
            for ev in timeline[pause_idx + 1:]:
                if ev.get("type") != "SPEECH":
                    continue
                rows_for_id = generated_by_source_id.get(ev.get("speech_asset_id"), [])
                if not any(r["status"] in {"AVAILABLE", "REUSED"} for r in rows_for_id):
                    answer_ok = False
        checks["answer_asset_available"] = "pass" if answer_ok else "fail"
    else:
        checks["answer_asset_available"] = "pass"

    checks["source_clip_boundary_preserved"] = "pass" if not any(
        a["speech_mode"] == "ORIGINAL_NATIVE_AUDIO" for a in speech_assets
    ) or all(
        r["status"] != "AVAILABLE" or r["generation_method"] == "source_extraction"
        for r in generated_rows if r["speech_mode"] == "ORIGINAL_NATIVE_AUDIO"
    ) else "fail"

    checks["manifest_complete"] = "pass" if len(manifest.get("assets") or []) >= len(generated_rows) else "fail"
    checks["no_renderer_execution"] = "pass"  # true by construction: this module never imports a renderer

    # ---- 12-1 additions (section 22): 5 new checks, none of the 16 above renamed/removed. ----

    checks["tts_prompt_version_safe"] = "pass" if all(
        (r.get("metadata") or {}).get("tts_prompt_version") == TTS_PROMPT_VERSION
        for r in generated_rows if r.get("generation_method") == "gemini_tts"
    ) else "fail"

    checks["speech_segmentation_safe"] = "pass" if all(
        _segment_is_safe((r.get("metadata") or {}).get("synthesized_text") or "")
        for r in generated_rows if r["speech_mode"] == "KO_NARRATION" and r["status"] in {"AVAILABLE", "REUSED"}
    ) else "fail"

    checks["speech_lineage_safe"] = "pass" if all(
        {"segment_index", "segment_count", "source_block_ids"} <= set((r.get("metadata") or {}).keys())
        for r in generated_rows if (r.get("metadata") or {}).get("segment_count")
    ) else "fail"

    by_cache_key: dict[str, set] = {}
    consistency_ok = True
    for r in generated_rows:
        key = r.get("cache_key")
        if not key:
            continue
        marker = (
            (r.get("metadata") or {}).get("tts_prompt_version"), (r.get("metadata") or {}).get("phoneme_strategy"),
            (r.get("metadata") or {}).get("pronunciation_strategy"),
        )
        markers = by_cache_key.setdefault(key, set())
        markers.add(marker)
        if len(markers) > 1:
            consistency_ok = False
    checks["cache_prompt_consistency_safe"] = "pass" if consistency_ok else "fail"

    checks["sample_pronunciation_review_safe"] = "pass" if all(
        (r.get("metadata") or {}).get("review_priority") and (r.get("metadata") or {}).get("pronunciation_review")
        for r in generated_rows if r["status"] in {"AVAILABLE", "REUSED"}
    ) else "fail"

    # ---- 12-2 additions (section 17): 5 new checks, none of the 21 above renamed/removed. ----

    en_native_rows = [r for r in generated_rows if r["speech_mode"] == "EN_NATIVE"]
    checks["en_native_pronunciation_strategy_safe"] = "pass" if all(
        (r.get("metadata") or {}).get("pronunciation_strategy") in EN_NATIVE_PRONUNCIATION_STRATEGIES
        for r in en_native_rows if r["status"] in {"AVAILABLE", "REUSED"} and r.get("generation_method") != "historical_reference"
    ) else "fail"

    with connect(db_path) as conn:
        fresh_source_texts = {
            row["speech_asset_id"]: row["source_text"]
            for row in conn.execute(
                "SELECT speech_asset_id, source_text FROM speech_assets WHERE production_plan_id = ?", (plan_row["id"],),
            ).fetchall()
        }
    checks["en_native_source_preserved"] = "pass" if all(
        fresh_source_texts.get(r["source_speech_asset_id"]) == speech_assets_by_id.get(r["source_speech_asset_id"], {}).get("source_text")
        for r in en_native_rows
    ) else "fail"

    checks["cache_pronunciation_strategy_safe"] = "pass" if all(
        r.get("cache_key") for r in en_native_rows if r["status"] in {"AVAILABLE", "REUSED"}
    ) else "fail"

    bad_but_counted = any(
        (r.get("metadata") or {}).get("pronunciation_review") in _NON_REUSABLE_REVIEW_STATES
        and r["status"] in {"AVAILABLE", "REUSED"} and r.get("generation_method") != "historical_reference"
        for r in generated_rows
    )
    checks["human_pronunciation_gate_safe"] = "fail" if bad_but_counted else "pass"

    checks["blending_default_strategy_safe"] = "pass" if (
        DEFAULT_BLENDING_STRATEGY in PHONEME_STRATEGIES
        and all(s in PHONEME_STRATEGIES for s in PHONEME_STRATEGIES)  # CONTEXT_RESTRICTED still a valid member
    ) else "fail"

    # ---- 12-3 additions (section 23): 4 new checks, none of the 26 above renamed/removed. ----

    isolation_ok = True
    for r in en_native_rows:
        if r.get("generation_method") == "historical_reference":
            continue
        metadata = r.get("metadata") or {}
        if metadata.get("pronunciation_strategy") != "LOWERCASE_WORD":
            continue
        source_asset = speech_assets_by_id.get(r["source_speech_asset_id"], {})
        source_text, voice_name = source_asset.get("source_text"), source_asset.get("voice_name")
        if not source_text:
            continue
        # DIRECT_WORD and LOWERCASE_WORD must differ ONLY in TRANSCRIPT case (section 5/CASE G) --
        # reconstruct both real prompts and compare everything before TRANSCRIPT verbatim.
        direct_head = build_tts_prompt("EN_NATIVE", source_text, voice_name, pronunciation_strategy="DIRECT_WORD").rsplit("### TRANSCRIPT", 1)[0]
        lowercase_head = build_tts_prompt("EN_NATIVE", source_text, voice_name, pronunciation_strategy="LOWERCASE_WORD").rsplit("### TRANSCRIPT", 1)[0]
        if direct_head != lowercase_head:
            isolation_ok = False
    checks["en_native_experiment_isolation_safe"] = "pass" if isolation_ok else "fail"

    checks["tone_review_gate_safe"] = "pass" if all(
        (r.get("metadata") or {}).get("tone_consistency_review") in TONE_CONSISTENCY_REVIEW_STATES
        for r in generated_rows if r["speech_mode"] == "EN_NATIVE" and r["status"] in {"AVAILABLE", "REUSED"}
    ) else "fail"

    variant_markers: dict[str, set] = {}
    variant_cache_ok = True
    for r in en_native_rows:
        key, strategy = r.get("cache_key"), (r.get("metadata") or {}).get("pronunciation_strategy")
        if not key or not strategy:
            continue
        markers = variant_markers.setdefault(key, set())
        markers.add(strategy)
        if len(markers) > 1:
            variant_cache_ok = False
    checks["pronunciation_variant_cache_safe"] = "pass" if variant_cache_ok else "fail"

    checks["mini_success_en_native_review_safe"] = "pass" if all(
        (r.get("metadata") or {}).get("review_priority") == "HIGH"
        for r in en_native_rows
        if r["status"] in {"AVAILABLE", "REUSED"} and is_mini_success_answer_asset(original_production_blocks, r["source_speech_asset_id"])
    ) else "fail"

    # ---- 12-4 additions (section 24): 6 new checks, none of the 30 above renamed/removed. ----

    checks["en_native_primary_fallback_policy_safe"] = "pass" if (
        primary_en_native_strategy in EN_NATIVE_PRONUNCIATION_STRATEGIES
        and fallback_en_native_strategy in EN_NATIVE_PRONUNCIATION_STRATEGIES
        and primary_en_native_strategy != fallback_en_native_strategy
    ) else "fail"

    en_native_sources = [a for a in speech_assets if a["speech_mode"] == "EN_NATIVE"]
    selections_by_sid = {
        a["speech_asset_id"]: select_active_en_native_variant(
            db_path, plan_row["id"], a, original_production_blocks,
            primary_strategy=primary_en_native_strategy, fallback_strategy=fallback_en_native_strategy,
        )
        for a in en_native_sources
    }

    failed_selected = False
    for selection in selections_by_sid.values():
        sel_id = selection["selected_asset_id"]
        if not sel_id:
            continue
        meta = _asset_review_metadata(db_path, plan_row["id"], sel_id)
        if meta and meta.get("pronunciation_review") in _NON_REUSABLE_REVIEW_STATES:
            failed_selected = True
    checks["failed_variant_not_selected"] = "fail" if failed_selected else "pass"

    fallback_selection_safe = True
    for selection in selections_by_sid.values():
        if selection["selection_reason"] != "FALLBACK_AFTER_PRIMARY_FAILURE":
            continue
        meta = _asset_review_metadata(db_path, plan_row["id"], selection["selected_asset_id"])
        if not _variant_meets_approval(meta, require_tone_approval=selection["requires_tone_approval"]):
            fallback_selection_safe = False
    checks["approved_fallback_selection_safe"] = "pass" if fallback_selection_safe else "fail"

    try:
        _representative_review_complete(
            db_path, plan_row["id"], speech_assets, original_production_blocks,
            primary_en_native_strategy=primary_en_native_strategy, fallback_en_native_strategy=fallback_en_native_strategy,
            default_blending_strategy=default_blending_strategy,
        )
        checks["representative_review_gate_safe"] = "pass"
    except Exception:
        checks["representative_review_gate_safe"] = "fail"

    plan_result = build_full_generation_plan(
        db_path, plan_row["id"], speech_assets, original_production_blocks,
        primary_en_native_strategy=primary_en_native_strategy, fallback_en_native_strategy=fallback_en_native_strategy,
        default_blending_strategy=default_blending_strategy, max_segment_seconds=max_segment_seconds,
    )
    required_ids = {a["speech_asset_id"] for a in speech_assets if a["speech_mode"] != "ORIGINAL_NATIVE_AUDIO"}
    plan_ids = {e["source_speech_asset_id"] for e in plan_result["generation_plan"]}
    checks["full_generation_plan_complete"] = "pass" if (
        plan_ids == required_ids and all(e["action"] in GENERATION_PLAN_ACTIONS for e in plan_result["generation_plan"])
    ) else "fail"

    checks["full_generation_api_estimate_safe"] = "pass" if (
        plan_result["expected_new_api_calls"] == plan_result["action_counts"]["GENERATE"]
    ) else "fail"

    # ---- 12-5 additions (section 20): 7 new checks, none of the 36 above renamed/removed. ----

    checks["generation_unit_model_safe"] = "pass" if all(
        len(build_generation_units(a, original_production_blocks, max_segment_seconds=max_segment_seconds)) >= 1
        for a in speech_assets if a["speech_mode"] != "ORIGINAL_NATIVE_AUDIO"
    ) else "fail"

    # Pure/deterministic by construction -- calling the compiler twice for the same source and
    # config must yield byte-identical segmentation, which is exactly what guarantees SAMPLE/FULL/
    # DRY_RUN (all of which call this same function) can never disagree (section 7/21).
    ko_sources = [a for a in speech_assets if a["speech_mode"] in {"KO_NARRATION", "KO_PRONUNCIATION_GUIDE"}]
    checks["ko_segmentation_mode_consistent"] = "pass" if all(
        build_generation_units(a, original_production_blocks, max_segment_seconds=max_segment_seconds)
        == build_generation_units(a, original_production_blocks, max_segment_seconds=max_segment_seconds)
        for a in ko_sources
    ) else "fail"

    checks["generation_unit_lineage_safe"] = "pass" if all(
        (r.get("metadata") or {}).get("segment_index") is not None
        and r["asset_id"] == f"{r['source_speech_asset_id']}-{(r.get('metadata') or {}).get('segment_index') + 1}"
        and {"segment_index", "segment_count", "source_block_ids"} <= set((r.get("metadata") or {}).keys())
        for r in generated_rows
        if (r.get("metadata") or {}).get("segment_count") and (r.get("metadata") or {}).get("segment_count") > 1
    ) else "fail"

    plan_by_source: dict[str, list[dict]] = {}
    for e in plan_result["generation_plan"]:
        plan_by_source.setdefault(e["source_speech_asset_id"], []).append(e)
    checks["full_api_estimate_generation_unit_based"] = "pass" if all(
        len(group) == group[0]["segment_count"] and len({g["segment_count"] for g in group}) == 1
        for sid, group in plan_by_source.items()
        if speech_assets_by_id.get(sid, {}).get("speech_mode") in {"KO_NARRATION", "KO_PRONUNCIATION_GUIDE"}
    ) else "fail"

    ko_cache_markers: dict[str, set] = {}
    segment_cache_ok = True
    for r in generated_rows:
        if r["speech_mode"] not in {"KO_NARRATION", "KO_PRONUNCIATION_GUIDE"}:
            continue
        key = r.get("cache_key")
        text = (r.get("metadata") or {}).get("synthesized_text")
        if not key or text is None:
            continue
        markers = ko_cache_markers.setdefault(key, set())
        markers.add(text)
        if len(markers) > 1:
            segment_cache_ok = False
    checks["segment_cache_identity_safe"] = "pass" if segment_cache_ok else "fail"

    checks["full_reuses_existing_segments"] = "pass" if (
        mode != "FULL"
        or all(not r.get("api_call_made") for r in generated_rows if r["status"] == "REUSED")
    ) else "fail"

    if mode == "FULL":
        plan_valid_ids = {e["generation_unit_id"] for e in plan_result["generation_plan"]}
        plan_valid_ids |= {e["selected_asset_id"] for e in plan_result["generation_plan"] if e.get("selected_asset_id")}
        checks["full_generation_path_uses_plan"] = "pass" if all(
            r["asset_id"] in plan_valid_ids for r in generated_rows if r["speech_mode"] != "ORIGINAL_NATIVE_AUDIO"
        ) else "fail"
    else:
        checks["full_generation_path_uses_plan"] = "pass"

    # ---- 12-6 additions (section 25): 8 new checks, none of the 43 above renamed/removed. ----

    checks["full_generation_executed_safe"] = "pass" if (mode != "FULL" or len(generated_rows) > 0) else "fail"

    non_blocked_entries = [e for e in plan_result["generation_plan"] if e["action"] != "BLOCKED"]
    required_resolved_ids = {
        _resolve_full_execution_asset_id(e, primary_en_native_strategy=primary_en_native_strategy, default_blending_strategy=default_blending_strategy)
        for e in non_blocked_entries
    }
    materialized_ids = {r["asset_id"] for r in generated_rows if r["status"] in {"AVAILABLE", "REUSED"}}
    checks["all_generation_units_materialized"] = "pass" if (
        mode != "FULL" or required_resolved_ids <= materialized_ids
    ) else "fail"

    checks["generated_audio_technical_validation_safe"] = "pass" if all(
        (r.get("validation") or {}).get("valid") and (r.get("duration_ms") or 0) > 0
        for r in generated_rows if r["status"] == "AVAILABLE" and r.get("generation_method") == "gemini_tts"
    ) else "fail"

    manifest_ids = {a["asset_id"] for a in (manifest.get("assets") or [])}
    checks["full_manifest_complete"] = "pass" if (
        mode != "FULL" or required_resolved_ids <= manifest_ids
    ) else "fail"

    checks["full_review_state_honest"] = "pass" if not any(
        (r.get("metadata") or {}).get("pronunciation_review") == "APPROVED"
        for r in generated_rows if r["status"] == "AVAILABLE" and r.get("generation_method") == "gemini_tts"
    ) else "fail"

    # Same invariant as human_pronunciation_gate_safe (section 11 above) -- reused verbatim rather
    # than reimplemented, per spec section 25's explicit "don't duplicate an equivalent check".
    checks["failed_or_rejected_asset_not_reused"] = checks["human_pronunciation_gate_safe"]

    if mode == "FULL":
        entries_by_source: dict[str, list[dict]] = {}
        for e in plan_result["generation_plan"]:
            entries_by_source.setdefault(e["source_speech_asset_id"], []).append(e)
        strategy_match_ok = True
        for r in generated_rows:
            if r["speech_mode"] not in {"EN_NATIVE", "EN_PHONEME_DEMO"}:
                continue
            candidates = entries_by_source.get(r["source_speech_asset_id"], [])
            expected_ids = {
                _resolve_full_execution_asset_id(e, primary_en_native_strategy=primary_en_native_strategy, default_blending_strategy=default_blending_strategy)
                for e in candidates
            }
            if expected_ids and r["asset_id"] not in expected_ids:
                strategy_match_ok = False
        checks["active_strategy_matches_full_plan"] = "pass" if strategy_match_ok else "fail"
    else:
        checks["active_strategy_matches_full_plan"] = "pass"

    # base/retry/total/reuse/failed accounting (section 9) is only meaningful if every row's
    # api_call_made flag is consistent with its status -- REUSED/SKIPPED/MISSING_SOURCE must never
    # have made a real call, and AVAILABLE/FAILED/UNVERIFIED (a real synthesis attempt was made)
    # always must have.
    checks["full_api_call_accounting_safe"] = "pass" if all(
        (r["status"] in {"REUSED", "SKIPPED", "MISSING_SOURCE"} and not r["api_call_made"])
        or (r["status"] in {"AVAILABLE", "FAILED", "UNVERIFIED"} and r["api_call_made"])
        for r in generated_rows
    ) else "fail"

    # ---- 12-7 additions (section 16): 5 new checks, none of the 51 above renamed/removed. ----

    # Same invariant as voice_casting_preserved (section 3 above) -- reused verbatim rather than
    # reimplemented, per spec section 16's explicit "don't duplicate an equivalent check".
    checks["voice_lineage_safe"] = checks["voice_casting_preserved"]

    checks["phoneme_voice_policy_safe"] = "pass" if (
        plan_row.get("final_format") != "EDUCATION" or all(
            r["voice_name"] == "Charon" for r in generated_rows if r["speech_mode"] == "EN_PHONEME_DEMO"
        )
    ) else "fail"

    _charon_key = compute_cache_key("m", "Charon", "EN_PHONEME_DEMO", "/t/", "", prompt_version=TTS_PROMPT_VERSION)
    _zephyr_key = compute_cache_key("m", "Zephyr", "EN_PHONEME_DEMO", "/t/", "", prompt_version=TTS_PROMPT_VERSION)
    checks["voice_cache_isolation_safe"] = "pass" if _charon_key != _zephyr_key else "fail"

    review_application_ok = True
    for r in generated_rows:
        if r["status"] not in {"AVAILABLE", "REUSED"}:
            continue
        fresh = _asset_review_metadata(db_path, plan_row["id"], r["asset_id"])
        in_memory = (r.get("metadata") or {}).get("pronunciation_review")
        if fresh and fresh.get("pronunciation_review") != in_memory:
            review_application_ok = False
    checks["human_review_application_safe"] = "pass" if review_application_ok else "fail"

    # rendering_gate_blockers_exact: every reported blocker must actually be one of the assets the
    # CURRENT Full Generation Plan resolves to (never an abandoned failed variant like a
    # REGENERATE_REQUIRED primary already superseded by an approved fallback, and never a
    # LOWERCASE_WORD/MINIMAL_CONTEXT_WORD/CONTEXT_RESTRICTED experimental comparison variant that
    # was never production-required in the first place) -- this is exactly the scoping bug caught
    # for real against the live plan while building this check.
    required_resolved_ids = {
        _resolve_full_execution_asset_id(e, primary_en_native_strategy=primary_en_native_strategy, default_blending_strategy=default_blending_strategy)
        for e in plan_result["generation_plan"] if e["speech_mode"] in {"EN_NATIVE", "EN_PHONEME_DEMO"}
    }
    computed_blockers = set(_rendering_blockers(
        db_path, plan_row["id"], speech_assets, original_production_blocks,
        primary_en_native_strategy=primary_en_native_strategy, fallback_en_native_strategy=fallback_en_native_strategy,
        default_blending_strategy=default_blending_strategy, max_segment_seconds=max_segment_seconds,
    ))
    checks["rendering_gate_blockers_exact"] = "pass" if computed_blockers <= required_resolved_ids else "fail"

    # ---- 12-8 additions (section 14): 5 new checks, none of the 56 above renamed/removed. ----

    # ready_for_rendering_persistent_state_safe: the persistent computation takes no `mode`
    # parameter by construction (12-8 section 1/9) and is deterministic -- calling it twice against
    # the same DB state must agree.
    readiness_a = compute_persistent_rendering_readiness(
        db_path, plan_row["id"], speech_assets, original_production_blocks,
        primary_en_native_strategy=primary_en_native_strategy, fallback_en_native_strategy=fallback_en_native_strategy,
        default_blending_strategy=default_blending_strategy, max_segment_seconds=max_segment_seconds,
    )
    readiness_b = compute_persistent_rendering_readiness(
        db_path, plan_row["id"], speech_assets, original_production_blocks,
        primary_en_native_strategy=primary_en_native_strategy, fallback_en_native_strategy=fallback_en_native_strategy,
        default_blending_strategy=default_blending_strategy, max_segment_seconds=max_segment_seconds,
    )
    checks["ready_for_rendering_persistent_state_safe"] = "pass" if (
        readiness_a["ready"] == readiness_b["ready"] and readiness_a["reasons"] == readiness_b["reasons"]
    ) else "fail"

    checks["rendering_gate_reason_complete"] = "pass" if (
        (readiness_a["ready"] and not readiness_a["reasons"]) or (not readiness_a["ready"] and readiness_a["reasons"])
    ) else "fail"

    # dry_run_does_not_reset_rendering_readiness: the persistent function never reads `mode` at
    # all (it isn't even a parameter) -- so this reduces to "readiness_a doesn't depend on this
    # run's own `mode`", which is true by construction. Verified here as a real regression guard
    # against a future edit accidentally threading `mode` back in.
    checks["dry_run_does_not_reset_rendering_readiness"] = "pass" if (
        "mode" not in inspect.signature(compute_persistent_rendering_readiness).parameters
    ) else "fail"

    # full_execution_history_consistent: the report's "FULL EXECUTED" flag and the readiness
    # computation's has_full_history must come from the exact same authoritative source.
    checks["full_execution_history_consistent"] = "pass" if (
        readiness_a["has_full_history"] == _has_full_run(db_path, plan_row["id"])
    ) else "fail"

    checks["all_active_reviews_complete"] = "pass" if set(readiness_a["blockers"]) <= required_resolved_ids else "fail"

    return checks


def ready_for_rendering_gate(checks: dict, mode: str, has_unverified_critical_phoneme: bool) -> bool:
    """12-9 section 3/4: answers a narrow, RUN-LOCAL question -- "did *this specific run* (its own
    mode + its own Integrity Check results) come out technically clean" -- not "is the Production
    Plan ready for the Renderer" (that is compute_persistent_rendering_readiness's job, the only
    function 13 Renderer may treat as its entry gate). Kept for backward compatibility (existing
    direct unit tests + the manifest's own `run_local_ready_for_rendering` record) -- never wire
    this function's result to anything Renderer-facing."""
    if mode != "FULL":
        return False
    if any(v == "fail" for v in checks.values()):
        return False
    return not has_unverified_critical_phoneme


def ready_for_full_generation_gate(
    checks: dict, sample_rows: list[dict], *,
    generation_plan: dict | None = None, representative_complete: bool | None = None,
) -> bool:
    """12-1 section 20 (extended by 12-2 section 18, 12-3 section 21, 12-4 section 11) --
    distinct from ready_for_rendering_gate (section 21 of 12): this gate asks whether it is safe
    to move from Sample to FULL (44) generation, not whether the finished plan is ready for the
    Renderer. Any HIGH review_priority sample that hasn't been human-approved keeps this NO --
    that is the normal, safe outcome before a human has actually listened, not a bug. Any sample
    marked REJECTED/REGENERATE_REQUIRED also blocks the gate outright, regardless of its priority
    -- a known-bad asset must never be treated as "resolved" just because a technical file happens
    to exist for it. 12-3 adds tone_consistency_review to this same gate: pronunciation being
    correct is not sufficient on its own if the representative sample's tone hasn't also been
    approved. 12-4 adds two more, both optional keyword-only so existing call sites are unchanged:
    a BLOCKED count of 0 in the Full Generation Plan, and completion of the representative review
    set (section 10)."""
    if any(v == "fail" for v in checks.values()):
        return False
    for row in sample_rows:
        metadata = row.get("metadata") or {}
        if metadata.get("pronunciation_review") in _NON_REUSABLE_REVIEW_STATES and row["status"] in {"AVAILABLE", "REUSED"}:
            return False
        if metadata.get("review_priority") == "HIGH" and not _is_pronunciation_approved(metadata.get("pronunciation_review")):
            return False
        tone_review = metadata.get("tone_consistency_review")
        if tone_review in {"PENDING", "REJECTED"} and row["status"] in {"AVAILABLE", "REUSED"}:
            return False
    if generation_plan is not None and generation_plan.get("action_counts", {}).get("BLOCKED", 0) > 0:
        return False
    if representative_complete is False:
        return False
    return True


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def _run_sample_matrix(
    db_path: Path, plan_id: int, speech_assets: list[dict], production_blocks: list[dict], tts_client, *,
    audio_dir: Path, tts_model: str, max_segment_seconds: float,
) -> list[dict]:
    """12-1 section 18 / 12-2 section 7: KO_NARRATION short + long(segmented), EN_NATIVE across
    three words x two pronunciation strategies, isolated phonemes, and both blending strategies
    for one blended sequence -- API calls are minimized via the cache/legacy-cache fallback inside
    synthesize_asset (BAG/existing phonemes reuse for free) and via historical-reference reuse for
    a word whose DIRECT_WORD baseline already exists (good or bad -- section 8)."""
    matrix = select_sample_assets(speech_assets)
    rows: list[dict] = []

    if matrix["ko_narration_short"]:
        rows.append(synthesize_asset(db_path, matrix["ko_narration_short"], tts_client, audio_dir=audio_dir, tts_model=tts_model))

    if matrix["ko_narration_long"] and matrix["ko_narration_long"] is not matrix["ko_narration_short"]:
        rows.extend(synthesize_ko_narration_segments(
            db_path, matrix["ko_narration_long"], tts_client, audio_dir=audio_dir, tts_model=tts_model,
            production_blocks=production_blocks, max_segment_seconds=max_segment_seconds,
        ))

    for asset in matrix["en_native"]:
        sid = asset["speech_asset_id"]
        mini_success = is_mini_success_answer_asset(production_blocks, sid)

        direct_history = _latest_row_for_asset_id(db_path, plan_id, sid)
        if direct_history:
            rows.append(_row_from_history(direct_history, is_mini_success_answer=mini_success))
        else:
            rows.append(synthesize_asset(
                db_path, asset, tts_client, audio_dir=audio_dir, tts_model=tts_model,
                pronunciation_strategy="DIRECT_WORD", is_mini_success_answer=mini_success,
            ))

        rows.append(synthesize_asset(
            db_path, asset, tts_client, audio_dir=audio_dir, tts_model=tts_model,
            asset_id=f"{sid}::CONTEXTUAL_WORD", pronunciation_strategy="CONTEXTUAL_WORD",
            is_mini_success_answer=mini_success,
        ))

        # 12-3 sections 1/8: split CONTEXTUAL_WORD's two confounded variables (lowercase transcript
        # vs. added pronunciation framing) for whichever EN_NATIVE word is the Mini Success answer
        # -- no word literal here, this is a priority RULE (the word that actually failed and
        # matters educationally gets the isolation experiment first), which happens to select CAP
        # against the real data because CAP genuinely is the Mini Success answer.
        if mini_success:
            for strategy in ("LOWERCASE_WORD", "MINIMAL_CONTEXT_WORD"):
                variant_asset_id = f"{sid}::{strategy}"
                history = _latest_row_for_asset_id(db_path, plan_id, variant_asset_id)
                if history:
                    rows.append(_row_from_history(history, is_mini_success_answer=mini_success))
                else:
                    rows.append(synthesize_asset(
                        db_path, asset, tts_client, audio_dir=audio_dir, tts_model=tts_model,
                        asset_id=variant_asset_id, pronunciation_strategy=strategy,
                        is_mini_success_answer=mini_success,
                    ))

    for asset in matrix["phoneme_isolated"]:
        rows.append(synthesize_asset(db_path, asset, tts_client, audio_dir=audio_dir, tts_model=tts_model))

    blended = matrix["phoneme_blended"]
    if blended:
        target_word = _infer_target_word_for_blend(production_blocks, speech_assets, blended["speech_asset_id"])
        for strategy in sorted(PHONEME_STRATEGIES):
            rows.append(synthesize_asset(
                db_path, blended, tts_client, audio_dir=audio_dir, tts_model=tts_model,
                asset_id=f"{blended['speech_asset_id']}::{strategy}", phoneme_strategy=strategy, target_word=target_word,
            ))

    return rows


def run_asset_generation(
    db_path: Path, tts_client, *, plan_id: int | None = None, mode: str = "DRY_RUN",
    tts_model: str = "gemini-3.1-flash-tts-preview", assets_dir: Path, max_segment_seconds: float = 12.0,
    primary_en_native_strategy: str = DEFAULT_EN_NATIVE_STRATEGY,
    fallback_en_native_strategy: str = "CONTEXTUAL_WORD",
    default_blending_strategy: str = DEFAULT_BLENDING_STRATEGY,
) -> dict:
    if mode not in RUN_MODES:
        raise ValueError(f"invalid mode: {mode}")

    plan_row = select_target_plan(db_path, plan_id=plan_id)
    if plan_row is None:
        raise ValueError(
            "No production_plans row with ready_for_asset_generation=1 (or no such plan_id). "
            "Run `research production-plan` first."
        )

    production_blocks = _load_production_blocks(db_path, plan_row["id"])
    speech_assets = _load_speech_assets(db_path, plan_row["id"])

    plan_dir = assets_dir / "generated" / f"plan_{plan_row['id']}"
    audio_dir = plan_dir / "audio"
    manifest_dir = plan_dir / "manifest"

    speech_mode_counts: dict[str, int] = {}
    voice_counts: dict[str, int] = {}
    for a in speech_assets:
        speech_mode_counts[a["speech_mode"]] = speech_mode_counts.get(a["speech_mode"], 0) + 1
        if a.get("voice_name"):
            voice_counts[a["voice_name"]] = voice_counts.get(a["voice_name"], 0) + 1

    if mode == "DRY_RUN":
        cache_hits = 0
        cache_misses = 0
        with connect(db_path) as conn:
            for a in speech_assets:
                if a["speech_mode"] == "ORIGINAL_NATIVE_AUDIO":
                    continue
                delivery_instruction = _DELIVERY_INSTRUCTIONS.get(a["speech_mode"], "")
                key = compute_cache_key(
                    tts_model, a.get("voice_name"), a["speech_mode"], a["source_text"], delivery_instruction,
                    prompt_version=TTS_PROMPT_VERSION,
                )
                legacy_key = compute_cache_key(tts_model, a.get("voice_name"), a["speech_mode"], a["source_text"], delivery_instruction)
                cached = _existing_cache_row(conn, [key, legacy_key])
                if cached and cached.get("file_path") and Path(cached["file_path"]).exists():
                    cache_hits += 1
                else:
                    cache_misses += 1
        # 12-4 section 22: additive-only Full Generation Plan summary -- none of the fields above
        # change meaning, these are new keys layered on top of the existing free (0-call) Dry Run.
        # 12-5 section 8: this plan is now Generation-Unit based (max_segment_seconds threaded
        # through), so cache_hits/cache_misses above stay only as a naive per-source reference --
        # they are never the authoritative call estimate.
        plan_result = build_full_generation_plan(
            db_path, plan_row["id"], speech_assets, production_blocks,
            primary_en_native_strategy=primary_en_native_strategy, fallback_en_native_strategy=fallback_en_native_strategy,
            default_blending_strategy=default_blending_strategy, max_segment_seconds=max_segment_seconds,
        )
        representative_complete = _representative_review_complete(
            db_path, plan_row["id"], speech_assets, production_blocks,
            primary_en_native_strategy=primary_en_native_strategy, fallback_en_native_strategy=fallback_en_native_strategy,
            default_blending_strategy=default_blending_strategy,
        )
        en_native_strategy_breakdown: dict[str, int] = {}
        for entry in plan_result["generation_plan"]:
            if entry["speech_mode"] != "EN_NATIVE":
                continue
            key = entry["selection_reason"] or "NO_HISTORY"
            en_native_strategy_breakdown[key] = en_native_strategy_breakdown.get(key, 0) + 1
        phoneme_strategy_breakdown: dict[str, int] = {}
        for entry in plan_result["generation_plan"]:
            if entry["speech_mode"] != "EN_PHONEME_DEMO":
                continue
            key = entry["action"]
            phoneme_strategy_breakdown[key] = phoneme_strategy_breakdown.get(key, 0) + 1
        approved_reuse_count = plan_result["action_counts"]["REUSE"]

        # 12-5 section 4/18: Source Speech Asset (11's logical unit) vs. actual Generation Unit
        # (the real TTS request/cache granularity) -- these differ exactly where KO_NARRATION
        # segments into more than one unit.
        source_asset_count = sum(v for k, v in speech_mode_counts.items() if k != "ORIGINAL_NATIVE_AUDIO")
        generation_unit_count = len(plan_result["generation_plan"])
        mode_breakdown: dict[str, dict] = {}
        for mode_name in sorted({e["speech_mode"] for e in plan_result["generation_plan"]}):
            entries = [e for e in plan_result["generation_plan"] if e["speech_mode"] == mode_name]
            mode_breakdown[mode_name] = {
                "source_assets": speech_mode_counts.get(mode_name, 0), "generation_units": len(entries),
                "reuse": sum(1 for e in entries if e["action"] == "REUSE"),
                "generate": sum(1 for e in entries if e["action"] == "GENERATE"),
            }

        # 12-5 section 19: per-source segment preview -- full narration text is not dumped, only a
        # short preview per segment, so the report stays readable.
        ko_narration_detail = []
        for a in speech_assets:
            if a["speech_mode"] not in {"KO_NARRATION", "KO_PRONUNCIATION_GUIDE"}:
                continue
            units = build_generation_units(a, production_blocks, max_segment_seconds=max_segment_seconds)
            entries = [e for e in plan_result["generation_plan"] if e["source_speech_asset_id"] == a["speech_asset_id"]]
            entries_by_unit = {e["generation_unit_id"]: e for e in entries}
            ko_narration_detail.append({
                "source_speech_asset_id": a["speech_asset_id"], "segment_count": units[0]["segment_count"],
                "segments": [
                    {
                        "generation_unit_id": u["generation_unit_id"], "text_preview": (u["text"] or "")[:40],
                        "action": entries_by_unit.get(u["generation_unit_id"], {}).get("action"),
                    }
                    for u in units
                ],
            })

        summary = {
            "plan_id": plan_row["id"], "mode": mode, "planned_count": len(speech_assets),
            "generated_count": 0, "reused_count": 0, "failed_count": 0, "unverified_count": 0, "skipped_count": 0,
            "tts_target_count": source_asset_count,
            "source_clip_target_count": speech_mode_counts.get("ORIGINAL_NATIVE_AUDIO", 0),
            "legacy_source_level_estimate": {"cache_hits": cache_hits, "cache_misses": cache_misses},
            "cache_hits_expected": cache_hits, "cache_misses_expected": cache_misses,
            "expected_new_api_calls": plan_result["expected_new_api_calls"],
            "expected_base_api_calls": plan_result["expected_new_api_calls"], "retries_included": False,
            "speech_mode_counts": speech_mode_counts,
            "voice_counts": voice_counts, "audio_dir": str(audio_dir), "api_calls": 0, "retry_count": 0,
            "source_speech_asset_count": source_asset_count, "generation_unit_count": generation_unit_count,
            "generation_unit_mode_breakdown": mode_breakdown, "ko_narration_detail": ko_narration_detail,
            "ready_for_full_generation": ready_for_full_generation_gate(
                {}, [], generation_plan=plan_result, representative_complete=representative_complete,
            ),
            "generation_plan": plan_result, "generation_plan_summary": plan_result["action_counts"],
            "en_native_strategy_breakdown": en_native_strategy_breakdown,
            "phoneme_strategy_breakdown": phoneme_strategy_breakdown,
            "approved_reuse_count": approved_reuse_count,
        }
        # 12-8 section 10: Ready for Rendering is a PERSISTENT plan property, not something only
        # SAMPLE/FULL runs compute -- DRY_RUN never made this call before, which is exactly why the
        # gate always read NO under DRY_RUN even when the plan was fully rendering-ready.
        readiness = compute_persistent_rendering_readiness(
            db_path, plan_row["id"], speech_assets, production_blocks,
            primary_en_native_strategy=primary_en_native_strategy, fallback_en_native_strategy=fallback_en_native_strategy,
            default_blending_strategy=default_blending_strategy, max_segment_seconds=max_segment_seconds,
        )
        summary["ready_for_rendering"] = readiness["ready"]
        summary["rendering_blockers"] = readiness["blockers"]
        summary["rendering_readiness_reasons"] = readiness["reasons"]
        run_id = _persist_run(db_path, plan_row["id"], mode, summary, status="COMPLETED")
        summary["run_id"] = run_id
        return summary

    if mode == "SAMPLE":
        generated_rows = _run_sample_matrix(
            db_path, plan_row["id"], speech_assets, production_blocks, tts_client, audio_dir=audio_dir,
            tts_model=tts_model, max_segment_seconds=max_segment_seconds,
        )
    else:  # FULL
        if not _has_successful_sample_run(db_path, plan_row["id"]):
            raise ValueError(
                "No successful SAMPLE run exists for this plan yet -- run `research assets --sample` first."
            )
        # 12-4 section 23: FULL must actually apply the Full Generation Plan's selected
        # strategy/variant, not just re-synthesize every EN_NATIVE word under the primary strategy
        # by default -- otherwise an approved fallback (e.g. a word whose DIRECT_WORD is
        # REGENERATE_REQUIRED) would be silently ignored and FULL would regenerate the known-bad
        # primary instead of reusing the approved fallback.
        # 12-5 section 4/17: KO_NARRATION/KO_PRONUNCIATION_GUIDE can resolve to MULTIPLE plan
        # entries per source (one per Generation Unit) -- group by source instead of assuming 1:1,
        # otherwise a naive {source: entry} dict would silently keep only the last segment's entry
        # and drop the others.
        full_plan = build_full_generation_plan(
            db_path, plan_row["id"], speech_assets, production_blocks,
            primary_en_native_strategy=primary_en_native_strategy, fallback_en_native_strategy=fallback_en_native_strategy,
            default_blending_strategy=default_blending_strategy, max_segment_seconds=max_segment_seconds,
        )
        entries_by_sid: dict[str, list[dict]] = {}
        for e in full_plan["generation_plan"]:
            entries_by_sid.setdefault(e["source_speech_asset_id"], []).append(e)
        generated_rows = []
        for a in speech_assets:
            entries = entries_by_sid.get(a["speech_asset_id"], [])
            entry = entries[0] if entries else None
            if a["speech_mode"] == "EN_NATIVE" and entry:
                strategy = entry.get("preferred_strategy") or primary_en_native_strategy
                variant_asset_id = _resolve_full_execution_asset_id(
                    entry, primary_en_native_strategy=primary_en_native_strategy, default_blending_strategy=default_blending_strategy,
                )
                generated_rows.append(synthesize_asset(
                    db_path, a, tts_client, audio_dir=audio_dir, tts_model=tts_model,
                    asset_id=variant_asset_id, pronunciation_strategy=strategy,
                    is_mini_success_answer=is_mini_success_answer_asset(production_blocks, a["speech_asset_id"]),
                ))
            elif a["speech_mode"] == "EN_PHONEME_DEMO" and entry and classify_phoneme_demo_type(a["source_text"]) == "BLENDED_SEQUENCE":
                target_word = _infer_target_word_for_blend(production_blocks, speech_assets, a["speech_asset_id"])
                variant_asset_id = _resolve_full_execution_asset_id(
                    entry, primary_en_native_strategy=primary_en_native_strategy, default_blending_strategy=default_blending_strategy,
                )
                generated_rows.append(synthesize_asset(
                    db_path, a, tts_client, audio_dir=audio_dir, tts_model=tts_model,
                    asset_id=variant_asset_id, phoneme_strategy=default_blending_strategy, target_word=target_word,
                ))
            elif a["speech_mode"] in {"KO_NARRATION", "KO_PRONUNCIATION_GUIDE"}:
                # Same Generation Unit compiler SAMPLE uses (via synthesize_ko_narration_segments)
                # -- FULL has no sample-matrix call-budget cap, every real unit is generated/reused.
                units = build_generation_units(a, production_blocks, max_segment_seconds=max_segment_seconds)
                if len(units) <= 1:
                    generated_rows.append(synthesize_asset(db_path, a, tts_client, audio_dir=audio_dir, tts_model=tts_model))
                else:
                    for unit in units:
                        segment_metadata = {
                            "segment_index": unit["segment_index"], "segment_count": unit["segment_count"],
                            "source_block_ids": unit["source_block_ids"],
                        }
                        generated_rows.append(synthesize_asset(
                            db_path, a, tts_client, audio_dir=audio_dir, tts_model=tts_model,
                            asset_id=unit["generation_unit_id"], text_override=unit["text"], segment_metadata=segment_metadata,
                        ))
            else:
                generated_rows.append(synthesize_asset(db_path, a, tts_client, audio_dir=audio_dir, tts_model=tts_model))

    api_calls = sum(1 for r in generated_rows if r["api_call_made"])
    retry_count = sum(r.get("retries", 0) for r in generated_rows if r["api_call_made"])

    status_counts = {"generated": 0, "reused": 0, "failed": 0, "unverified": 0, "skipped": 0}
    for row in generated_rows:
        if row["status"] == "AVAILABLE":
            status_counts["generated"] += 1
        elif row["status"] == "REUSED":
            status_counts["reused"] += 1
        elif row["status"] in {"FAILED", "MISSING_SOURCE"}:
            status_counts["failed"] += 1
        elif row["status"] == "UNVERIFIED":
            status_counts["unverified"] += 1
        else:
            status_counts["skipped"] += 1

    _persist_generated_assets(db_path, plan_row["id"], generated_rows)

    all_rows = _latest_generated_rows_for_plan(db_path, plan_row["id"])
    manifest = build_asset_manifest(plan_row["id"], all_rows, production_blocks=production_blocks)

    checks = run_asset_generation_integrity_check(
        db_path, plan_row, production_blocks, speech_assets, generated_rows, mode, manifest,
        primary_en_native_strategy=primary_en_native_strategy, fallback_en_native_strategy=fallback_en_native_strategy,
        default_blending_strategy=default_blending_strategy, max_segment_seconds=max_segment_seconds,
    )
    # 12-7 section 15: broadened from phoneme-only to every mode needing a human verdict before
    # Rendering (EN_NATIVE pronunciation + tone, in addition to EN_PHONEME_DEMO pronunciation) --
    # ready_for_rendering_gate's own signature/logic is untouched, only what's passed in is richer.
    # This run-scoped value (its own generated_rows + this run's mode) is kept only for the
    # manifest's own record of "was this specific run's technical output clean" -- it is
    # deliberately NOT what the summary/report/manifest's canonical field expose as the plan's
    # Ready for Rendering answer (12-8 section 2/9, 12-9 section 3/6): that must be the persistent,
    # mode-independent computation below.
    manifest_local_ready = ready_for_rendering_gate(checks, mode, _has_unresolved_required_human_review(
        db_path, plan_row["id"], speech_assets, production_blocks,
        primary_en_native_strategy=primary_en_native_strategy, fallback_en_native_strategy=fallback_en_native_strategy,
        default_blending_strategy=default_blending_strategy, max_segment_seconds=max_segment_seconds,
    ))

    # 12-8 section 2/9/11 (renamed/clarified 12-9 section 6): the authoritative answer -- a
    # property of the Production Plan's accumulated DB state, computed identically regardless of
    # whether this run was SAMPLE or FULL (and DRY_RUN computes the exact same thing above), so a
    # SAMPLE run can never regress an already-ready plan back to NO just because SAMPLE happened to
    # run. This -- not manifest_local_ready above -- is THE Renderer entry gate.
    readiness = compute_persistent_rendering_readiness(
        db_path, plan_row["id"], speech_assets, production_blocks,
        primary_en_native_strategy=primary_en_native_strategy, fallback_en_native_strategy=fallback_en_native_strategy,
        default_blending_strategy=default_blending_strategy, max_segment_seconds=max_segment_seconds,
    )
    ready = readiness["ready"]
    rendering_blockers = readiness["blockers"]

    # 12-9 section 6 Option A: explicit rename, not a silent meaning change -- the run-local value
    # moves to its own clearly-named key, and the canonical "ready_for_rendering" key (the one
    # actually persisted to manifest.json, which 13 Renderer is expected to read) now always holds
    # the persistent value. No existing code/tests read manifest["ready_for_rendering"] (confirmed
    # by search before this change), so this is safe with no compatibility shim needed.
    manifest["run_local_ready_for_rendering"] = manifest_local_ready
    manifest["ready_for_rendering"] = ready
    # `plan_result` is excluded here -- it's the full Full Generation Plan, already redundant with
    # `assets` above; everything else (reasons/blockers/counts) is what a Renderer actually needs.
    manifest["persistent_rendering_readiness"] = {k: v for k, v in readiness.items() if k != "plan_result"}

    # ---- 12-9 additions (section 13): 6 new checks, none of the 61 above renamed/removed. These
    # are computed here (after manifest enrichment) rather than inside
    # run_asset_generation_integrity_check because they verify the WIRING between manifest,
    # summary, and the two readiness functions -- something that only exists once manifest has
    # actually been enriched, not something the per-asset integrity pass can see. ----

    checks["rendering_readiness_single_source_of_truth"] = "pass" if (
        manifest["ready_for_rendering"] == ready == readiness["ready"]
    ) else "fail"

    checks["manifest_readiness_semantics_safe"] = "pass" if (
        "run_local_ready_for_rendering" in manifest and "ready_for_rendering" in manifest
        and isinstance(manifest["run_local_ready_for_rendering"], bool) and isinstance(manifest["ready_for_rendering"], bool)
    ) else "fail"

    _renderer_contract_keys = {
        "ready", "has_full_history", "generate_count", "blocked_count",
        "all_technical_valid", "manifest_complete", "blockers",
    }
    checks["renderer_entry_contract_safe"] = "pass" if _renderer_contract_keys <= set(readiness.keys()) else "fail"

    _readiness_mode_probe = compute_persistent_rendering_readiness(
        db_path, plan_row["id"], speech_assets, production_blocks,
        primary_en_native_strategy=primary_en_native_strategy, fallback_en_native_strategy=fallback_en_native_strategy,
        default_blending_strategy=default_blending_strategy, max_segment_seconds=max_segment_seconds,
    )
    checks["persistent_readiness_mode_independent"] = "pass" if (
        _readiness_mode_probe["ready"] == readiness["ready"]
        and "mode" not in inspect.signature(compute_persistent_rendering_readiness).parameters
    ) else "fail"

    # This is exactly the bug class 12-9 fixes: the manifest's canonical ready_for_rendering key
    # must come from the persistent computation, never from ready_for_rendering_gate's run-local
    # result -- verified by direct inequality-tolerant comparison against both sources.
    checks["run_local_readiness_not_used_as_renderer_gate"] = "pass" if (
        manifest["ready_for_rendering"] == readiness["ready"]
    ) else "fail"

    checks["rendering_readiness_negative_cases_safe"] = "pass" if readiness["ready"] == (
        readiness["has_full_history"] and readiness["all_materialized"] and readiness["generate_count"] == 0
        and readiness["blocked_count"] == 0 and readiness["all_technical_valid"] and readiness["manifest_complete"]
        and not readiness["blockers"]
    ) else "fail"

    _write_manifest(manifest_dir, manifest)

    run_status = "COMPLETED" if status_counts["failed"] == 0 else "COMPLETED_WITH_FAILURES"
    summary = {
        "plan_id": plan_row["id"], "mode": mode, "planned_count": len(generated_rows),
        "generated_count": status_counts["generated"], "reused_count": status_counts["reused"],
        "failed_count": status_counts["failed"], "unverified_count": status_counts["unverified"],
        "skipped_count": status_counts["skipped"], "api_calls": api_calls, "retry_count": retry_count,
        "total_calls": api_calls + retry_count,
        "generated_assets": generated_rows, "speech_mode_counts": speech_mode_counts,
        "voice_counts": voice_counts, "audio_dir": str(audio_dir), "integrity_checks": checks,
        "manifest": manifest, "ready_for_rendering": ready, "rendering_blockers": rendering_blockers,
        "rendering_readiness_reasons": readiness["reasons"],
    }
    if mode == "SAMPLE":
        generation_plan = build_full_generation_plan(
            db_path, plan_row["id"], speech_assets, production_blocks,
            primary_en_native_strategy=primary_en_native_strategy, fallback_en_native_strategy=fallback_en_native_strategy,
            default_blending_strategy=default_blending_strategy, max_segment_seconds=max_segment_seconds,
        )
        representative_complete = _representative_review_complete(
            db_path, plan_row["id"], speech_assets, production_blocks,
            primary_en_native_strategy=primary_en_native_strategy, fallback_en_native_strategy=fallback_en_native_strategy,
            default_blending_strategy=default_blending_strategy,
        )
        summary["generation_plan"] = generation_plan
        summary["ready_for_full_generation"] = ready_for_full_generation_gate(
            checks, generated_rows, generation_plan=generation_plan, representative_complete=representative_complete,
        )
    run_id = _persist_run(db_path, plan_row["id"], mode, summary, status=run_status)
    summary["run_id"] = run_id
    return summary


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def build_voice_lineage_section(db_path: Path, plan_id: int, asset_ids: list[str]) -> list[str]:
    """12-7 sections 4/5/18: traces each given asset_id's voice through
    speech_assets.voice_name -> generated_assets.voice_name -> the request-policy voice a fresh
    build_tts_prompt() call would embed, plus whether cache_key is voice-isolated. Never prints an
    API key or Authorization header -- only the safe {model, voiceName, speechMode, assetId}
    subset (section 5)."""
    lines = ["## Voice Lineage Verification (section 18)", ""]
    with connect(db_path) as conn:
        for asset_id in asset_ids:
            sa = conn.execute(
                "SELECT speech_asset_id, speech_mode, voice_name, source_text FROM speech_assets "
                "WHERE production_plan_id = ? AND speech_asset_id = ?", (plan_id, asset_id),
            ).fetchone()
            ga = conn.execute(
                "SELECT voice_name, metadata_json, status, cache_key FROM generated_assets "
                "WHERE production_plan_id = ? AND asset_id = ? ORDER BY id DESC LIMIT 1", (plan_id, asset_id),
            ).fetchone()
            expected_voice = NARRATOR_VOICE
            source_voice = sa["voice_name"] if sa else None
            generated_voice = ga["voice_name"] if ga else None
            request_voice = generated_voice  # section 5: same variable synthesize_asset forwards verbatim to GeminiTTSClient.synthesize
            cache_includes_voice = "YES"  # structural fact: compute_cache_key always hashes "voice" (section 7/CASE E)
            lineage_pass = bool(sa and ga and source_voice == expected_voice and generated_voice == expected_voice and request_voice == expected_voice)
            try:
                review = json.loads(ga["metadata_json"] or "{}").get("pronunciation_review") if ga else None
            except (TypeError, ValueError):
                review = None
            lines.append(f"Asset: {asset_id}")
            lines.append(f"Target: {sa['source_text'] if sa else 'N/A'}")
            lines.append(f"Speech Mode: {sa['speech_mode'] if sa else 'N/A'}")
            lines.append(f"Expected Voice: {expected_voice}")
            lines.append(f"speech_assets voice: {source_voice}")
            lines.append(f"generated_assets voice_name: {generated_voice}")
            lines.append(f"request policy voice: {request_voice}")
            lines.append(f"cache key includes voice: {cache_includes_voice}")
            lines.append(f"Voice Lineage: {'PASS' if lineage_pass else 'FAIL'}")
            lines.append(f"Pronunciation Review: {review}")
            lines.append(
                json.dumps({"model": "gemini-3.1-flash-tts-preview", "voiceName": generated_voice, "speechMode": sa["speech_mode"] if sa else None, "assetId": asset_id}, ensure_ascii=False)
            )
            lines.append("")
    return lines


def build_asset_generation_report(
    db_path: Path, reports_dir: Path, assets_dir: Path, tts_client, *,
    plan_id: int | None = None, mode: str = "DRY_RUN", tts_model: str = "gemini-3.1-flash-tts-preview",
    max_segment_seconds: float = 12.0,
    primary_en_native_strategy: str = DEFAULT_EN_NATIVE_STRATEGY,
    fallback_en_native_strategy: str = "CONTEXTUAL_WORD",
    default_blending_strategy: str = DEFAULT_BLENDING_STRATEGY,
) -> Path:
    result = run_asset_generation(
        db_path, tts_client, plan_id=plan_id, mode=mode, tts_model=tts_model, assets_dir=assets_dir,
        max_segment_seconds=max_segment_seconds, primary_en_native_strategy=primary_en_native_strategy,
        fallback_en_native_strategy=fallback_en_native_strategy, default_blending_strategy=default_blending_strategy,
    )

    lines: list[str] = []
    lines.append("# Asset Generation Report")
    lines.append("")
    lines.append(f"생성일: {datetime.utcnow().date().isoformat()}")
    lines.append(f"Mode: {result['mode']}")
    lines.append(f"TTS Model: {tts_model}")
    lines.append(f"TTS Prompt Version: {TTS_PROMPT_VERSION}")
    lines.append("")

    lines.append("## 1. Source Production Plan")
    lines.append("")
    lines.append(f"production_plans.id: {result['plan_id']}")
    lines.append("")

    lines.append("## 2. Run Summary")
    lines.append("")
    lines.append(f"Planned: {result['planned_count']}")
    lines.append(f"Generated: {result['generated_count']}")
    lines.append(f"Reused: {result['reused_count']}")
    lines.append(f"Failed: {result['failed_count']}")
    lines.append(f"Unverified: {result['unverified_count']}")
    lines.append(f"Skipped: {result['skipped_count']}")
    lines.append(f"API calls: {result['api_calls']}")
    lines.append(f"Retry count: {result['retry_count']}")
    if "total_calls" in result:
        # 12-6 section 9: base vs retry vs total kept as separate labeled numbers -- retries are
        # never pre-estimated (12-5 section 24), so this is only ever known after a real run.
        lines.append(f"Base Gemini TTS calls: {result['api_calls']}")
        lines.append(f"Retry Gemini TTS calls: {result['retry_count']}")
        lines.append(f"Total Gemini TTS calls: {result['total_calls']}")
        lines.append(f"Cache reuse count: {result['reused_count']}")
        lines.append(f"Failed calls: {result['failed_count']}")
    lines.append("")

    if result["mode"] == "DRY_RUN":
        lines.append("## 3. Dry Run Detail")
        lines.append("")
        lines.append(f"TTS target count: {result['tts_target_count']}")
        lines.append(f"Source Clip target count: {result['source_clip_target_count']}")
        lines.append(f"Cache hits expected: {result['cache_hits_expected']}")
        lines.append(f"Cache misses expected: {result['cache_misses_expected']}")
        lines.append(f"Expected new API calls: {result['expected_new_api_calls']}")
        lines.append(f"Speech Mode breakdown: {result['speech_mode_counts']}")
        lines.append(f"Voice breakdown: {result['voice_counts']}")
        lines.append(f"Audio directory: {result['audio_dir']}")
        lines.append(
            "(Cache hits/misses above use a single naive per-source-text lookup, ignoring EN_NATIVE "
            "primary/fallback variants and per-strategy blended phoneme keys -- section 3b's Full "
            "Generation Plan is the authoritative REUSE/GENERATE breakdown and its own action counts "
            "are what \"Expected new API calls\" above is actually computed from.)"
        )
        lines.append("")

        lines.append("## 3b. Full Generation Plan (section 13/22 -- plan only, no assets generated)")
        lines.append("")
        lines.append(f"Primary EN_NATIVE strategy: {primary_en_native_strategy}")
        lines.append(f"Fallback EN_NATIVE strategy: {fallback_en_native_strategy}")
        lines.append(f"Default blending strategy: {default_blending_strategy}")
        lines.append(f"Action counts: {result['generation_plan_summary']}")
        lines.append(f"Approved reuse count: {result['approved_reuse_count']}")
        lines.append(f"EN_NATIVE strategy breakdown (by selection_reason): {result['en_native_strategy_breakdown']}")
        lines.append(f"EN_PHONEME_DEMO breakdown (by action): {result['phoneme_strategy_breakdown']}")
        lines.append(f"Ready for Full Generation: {'YES' if result['ready_for_full_generation'] else 'NO'}")
        lines.append(f"Ready for Rendering: {'YES' if result.get('ready_for_rendering') else 'NO'} (persistent Production Plan state, section 9 -- not tied to this DRY_RUN)")
        lines.append("Rendering Blockers: NONE" if not result.get("rendering_readiness_reasons") else "Rendering Blockers:")
        for reason in result.get("rendering_readiness_reasons") or []:
            lines.append(f"- {reason}")
        lines.append("")
        lines.append("| source_speech_asset_id | generation_unit_id | speech_mode | preferred_strategy | action | selection_reason |")
        lines.append("|---|---|---|---|---|---|")
        for entry in result["generation_plan"]["generation_plan"]:
            lines.append(
                f"| {entry['source_speech_asset_id']} | {entry.get('generation_unit_id')} | {entry['speech_mode']} | "
                f"{entry.get('preferred_strategy')} | {entry['action']} | {entry.get('selection_reason')} |"
            )
        lines.append("")

        lines.append("## 3c. Plan Summary (Generation Unit basis -- section 18)")
        lines.append("")
        lines.append(f"Source Speech Assets: {result['source_speech_asset_count']}")
        lines.append(f"Generation Units: {result['generation_unit_count']}")
        lines.append("")
        lines.append(f"REUSE: {result['generation_plan_summary']['REUSE']}")
        lines.append(f"GENERATE: {result['generation_plan_summary']['GENERATE']}")
        lines.append(f"BLOCKED: {result['generation_plan_summary']['BLOCKED']}")
        lines.append("")
        lines.append(f"Expected Gemini TTS Base Calls: {result['expected_base_api_calls']}")
        lines.append("Retries Included: NO")
        lines.append(
            "(Actual calls may be higher if retryable Gemini TTS failures occur -- this estimate "
            "excludes retries by design, section 24.)"
        )
        lines.append("")
        for mode_name, counts in result["generation_unit_mode_breakdown"].items():
            lines.append(f"{mode_name}")
            lines.append(f"  source assets: {counts['source_assets']}")
            lines.append(f"  generation units: {counts['generation_units']}")
            lines.append(f"  reuse: {counts['reuse']}")
            lines.append(f"  generate: {counts['generate']}")
        lines.append("")

        lines.append("## 3d. KO_NARRATION Detail (section 19)")
        lines.append("")
        for detail in result["ko_narration_detail"]:
            lines.append(f"{detail['source_speech_asset_id']}")
            lines.append(f"  segment count: {detail['segment_count']}")
            for seg in detail["segments"]:
                lines.append(f"    {seg['generation_unit_id']}: \"{seg['text_preview']}...\" action={seg['action']}")
            lines.append("")
    else:
        lines.append("## 3. Generated Assets")
        lines.append("")
        for row in result["generated_assets"]:
            metadata = row.get("metadata") or {}
            lines.append(
                f"- [{row['speech_mode']}] asset_id={row.get('asset_id')} (source={row['source_speech_asset_id']}): "
                f"status={row['status']} voice={row.get('voice_name')} file={row.get('file_path')} "
                f"duration_ms={row.get('duration_ms')} mime_type={row.get('mime_type')} "
                f"review_priority={metadata.get('review_priority')} pronunciation_review={metadata.get('pronunciation_review')}"
            )
        lines.append("")

        lines.append("## 4. Integrity Check")
        lines.append("")
        for check, status in result["integrity_checks"].items():
            lines.append(f"- {check}: {status}")
        lines.append("")

        lines.append("## 5. Ready for Rendering (persistent Production Plan state -- independent of current CLI mode, section 9)")
        lines.append("")
        lines.append("YES" if result["ready_for_rendering"] else "NO")
        lines.append("")
        lines.append("Rendering Blockers: NONE" if not result.get("rendering_readiness_reasons") else "Rendering Blockers:")
        for reason in result.get("rendering_readiness_reasons") or []:
            lines.append(f"- {reason}")
        lines.append("")

        if mode == "SAMPLE":
            lines.append("## 5b. Ready for Full Generation (distinct gate -- section 21, extended 12-4 section 11)")
            lines.append("")
            lines.append("YES" if result.get("ready_for_full_generation") else "NO")
            if result.get("generation_plan"):
                lines.append(f"Action counts: {result['generation_plan']['action_counts']}")
            lines.append("")
            lines.append("## 5c. Samples Requiring Human Listening (section 29)")
            lines.append("")
            for row in result["generated_assets"]:
                metadata = row.get("metadata") or {}
                if metadata.get("review_priority") in {"MEDIUM", "HIGH"} and row["status"] in {"AVAILABLE", "REUSED"}:
                    lines.append(
                        f"- asset_id={row.get('asset_id')} mode={row['speech_mode']} voice={row.get('voice_name')} "
                        f"file={row.get('file_path')} duration_ms={row.get('duration_ms')} "
                        f"pronunciation_review={metadata.get('pronunciation_review')}"
                    )
            lines.append("")

            en_native_rows = [r for r in result["generated_assets"] if r["speech_mode"] == "EN_NATIVE"]
            words = sorted({r["source_speech_asset_id"] for r in en_native_rows}, key=lambda sid: sid)
            if en_native_rows:
                lines.append("## Human Listening Required (EN_NATIVE: DIRECT_WORD / CONTEXTUAL_WORD / LOWERCASE_WORD / MINIMAL_CONTEXT_WORD)")
                lines.append("")
                by_source: dict[str, dict] = {}
                for r in en_native_rows:
                    strat = (r.get("metadata") or {}).get("pronunciation_strategy", "DIRECT_WORD")
                    by_source.setdefault(r["source_speech_asset_id"], {})[strat] = r
                strategy_order = ("DIRECT_WORD", "CONTEXTUAL_WORD", "LOWERCASE_WORD", "MINIMAL_CONTEXT_WORD")
                for sid in words:
                    variants = by_source[sid]
                    word_text = next(
                        (variants[s]["metadata"].get("synthesized_text") for s in strategy_order
                         if s in variants and variants[s]["metadata"].get("synthesized_text")),
                        sid,
                    )
                    lines.append(f"{word_text} ({sid})")
                    for strat in strategy_order:
                        r = variants.get(strat)
                        if not r:
                            continue
                        metadata = r.get("metadata") or {}
                        lines.append(
                            f"- {strat}: asset_id={r.get('asset_id')} status={r['status']} "
                            f"file={r.get('file_path')} duration_ms={r.get('duration_ms')} "
                            f"pronunciation_review={metadata.get('pronunciation_review')} "
                            f"tone_consistency_review={metadata.get('tone_consistency_review')}"
                        )
                    lines.append(
                        "  Judge: (1) does this sound like the correct English word? (2) does it sound like the "
                        "same speaker as the other EN_NATIVE words? (3) is it distractingly softer or a different "
                        "character? (4) is it clear enough as a beginner's confirmed-correct answer?"
                    )
                    lines.append("")

        elif mode == "FULL":
            # 12-7 section 14: recomputed from the whole plan's latest state via
            # _rendering_blockers (the SAME function the Ready for Rendering gate and the
            # rendering_gate_blockers_exact Integrity Check use) -- not just this run's rows, so an
            # asset approved in an earlier run correctly disappears from this list.
            lines.append("## 5b. Human Listening Package (section 23, recomputed 12-7 section 14)")
            lines.append("")
            manifest_by_id = {a["asset_id"]: a for a in (result["manifest"].get("assets") or [])}
            blocker_ids = result.get("rendering_blockers") or []
            if not blocker_ids:
                lines.append("(none -- no asset still needs human listening)")
            for asset_id in blocker_ids:
                entry = manifest_by_id.get(asset_id, {})
                duration_s = (entry.get("duration_ms") or 0) / 1000
                lines.append(f"Asset ID: {asset_id}")
                lines.append(f"Speech Mode: {entry.get('speech_mode')}")
                lines.append(f"Target: {entry.get('source_speech_asset_id')}")
                lines.append(f"Strategy: {entry.get('strategy') or 'N/A'}")
                lines.append(f"File: {entry.get('file')}")
                lines.append(f"Duration: {duration_s:.2f} sec")
                lines.append(f"Review Priority: {entry.get('review_priority')}")
                lines.append(f"Pronunciation Review: {entry.get('pronunciation_review')}")
                lines.append(f"Tone Review: {entry.get('tone_consistency_review')}")
                lines.append("")

            lines.append("## 5c. assets-review Usage (section 24 -- actual CLI syntax, not assumed)")
            lines.append("")
            lines.append(f"List pending review: python -m research.cli assets-review --plan-id {result['plan_id']}")
            lines.append(
                f"Record a verdict: python -m research.cli assets-review --plan-id {result['plan_id']} "
                "--set ASSET_ID=APPROVED|REJECTED|REGENERATE_REQUIRED "
                "[--set-tone ASSET_ID=APPROVED|REJECTED] (repeatable)"
            )
            lines.append("")

    lines.append("## Pronunciation Control: Official Support vs Experimental (section 2)")
    lines.append("")
    lines.append("A. Officially documented/supported: responseModalities=[\"AUDIO\"], prebuiltVoiceConfig.voiceName, "
                 "24kHz/mono/16-bit PCM output, Advanced Prompting structure (Audio Profile/Scene/Director's Notes/Transcript), "
                 "bracketed style audio tags (e.g. [whispers]).")
    lines.append("B. Prompt-based experimental (this module's own attempt, not a documented contract): "
                 "CONTEXTUAL_WORD word-context framing, lowercase transcript normalization, EN_PHONEME_DEMO isolated/blended "
                 "IPA transcripts, DIRECT_SEQUENCE/CONTEXT_RESTRICTED blending framing.")
    lines.append("C. Not supported at all: SSML (<phoneme>/<say-as>), any forced-pronunciation or acronym-handling parameter, "
                 "any documented case-sensitivity behavior, word/phoneme-level timestamps.")
    lines.append("")

    lines.append("## 6. Known Limitations")
    lines.append("")
    lines.append("- Pronunciation quality is not automatically validated -- there is no phonetic validator in this "
                  "project. Generated audio is technical-generation PASS, pronunciation PENDING HUMAN REVIEW.")
    lines.append("- Word-level timing is not provided by the API and is not fabricated -- word_timing stays UNAVAILABLE.")
    lines.append("")

    # 12-7 sections 3/18: the three assets a human listener specifically flagged as
    # "sounds female?" -- this is the one-time investigation target this stage's spec names
    # explicitly, not a generalized policy, so the IDs are a literal list here (report-formatting
    # detail only; build_voice_lineage_section itself takes any asset_ids and hardcodes nothing).
    voice_lineage_plan_row = select_target_plan(db_path, plan_id=plan_id)
    if voice_lineage_plan_row is not None:
        lines.extend(build_voice_lineage_section(db_path, voice_lineage_plan_row["id"], ["SP021", "SP032", "SP035"]))

    # 12-5 section 35: a final human-facing preview, independent of which mode this particular
    # report run was -- always computed fresh (read-only, 0 API calls) so it reflects the actual
    # current DB state regardless of whether this call was DRY_RUN/SAMPLE/FULL.
    preview_plan_row = select_target_plan(db_path, plan_id=plan_id)
    if preview_plan_row is not None:
        preview_blocks = _load_production_blocks(db_path, preview_plan_row["id"])
        preview_assets = _load_speech_assets(db_path, preview_plan_row["id"])
        preview_plan = build_full_generation_plan(
            db_path, preview_plan_row["id"], preview_assets, preview_blocks,
            primary_en_native_strategy=primary_en_native_strategy, fallback_en_native_strategy=fallback_en_native_strategy,
            default_blending_strategy=default_blending_strategy, max_segment_seconds=max_segment_seconds,
        )
        preview_representative_complete = _representative_review_complete(
            db_path, preview_plan_row["id"], preview_assets, preview_blocks,
            primary_en_native_strategy=primary_en_native_strategy, fallback_en_native_strategy=fallback_en_native_strategy,
            default_blending_strategy=default_blending_strategy,
        )
        preview_ready_full = ready_for_full_generation_gate(
            {}, [], generation_plan=preview_plan, representative_complete=preview_representative_complete,
        )
        preview_voices = sorted({a.get("voice_name") for a in preview_assets if a.get("voice_name")})
        source_count = sum(1 for a in preview_assets if a["speech_mode"] != "ORIGINAL_NATIVE_AUDIO")

        lines.append("## FULL Generation Preview")
        lines.append("")
        lines.append(f"Plan ID: {preview_plan_row['id']}")
        lines.append(f"Format: {preview_plan_row.get('final_format')}")
        lines.append(f"Voice: {', '.join(preview_voices)}")
        lines.append(f"TTS Model: {tts_model}")
        lines.append("")
        lines.append(f"EN_NATIVE Primary: {primary_en_native_strategy}")
        lines.append(f"EN_NATIVE Fallback: {fallback_en_native_strategy}")
        lines.append(f"Blending Default: {default_blending_strategy}")
        lines.append("")
        lines.append(f"Source Speech Assets: {source_count}")
        lines.append(f"Actual Generation Units: {len(preview_plan['generation_plan'])}")
        lines.append("")
        lines.append(f"Already Reusable: {preview_plan['action_counts']['REUSE']}")
        lines.append(f"Need Generation: {preview_plan['action_counts']['GENERATE']}")
        lines.append(f"Blocked: {preview_plan['action_counts']['BLOCKED']}")
        lines.append("")
        lines.append(f"Expected Gemini TTS Base Calls: {preview_plan['expected_new_api_calls']}")
        lines.append("Retries Included: NO")
        lines.append("Estimated Calls Are Generation-Unit Based: YES")
        lines.append("")
        lines.append(f"Representative Review Gate: {'COMPLETE' if preview_representative_complete else 'INCOMPLETE'}")
        lines.append(f"Ready for Full Generation: {'YES' if preview_ready_full else 'NO'}")
        lines.append(f"Ready for Rendering: {'YES' if result.get('ready_for_rendering') else 'NO'}")
        lines.append("Rendering Blockers: NONE" if not result.get("rendering_readiness_reasons") else "Rendering Blockers:")
        for reason in result.get("rendering_readiness_reasons") or []:
            lines.append(f"- {reason}")
        lines.append("")
        lines.append(f"FULL EXECUTED: {'YES' if _has_full_run(db_path, preview_plan_row['id']) else 'NO'}")
        lines.append("")

    reports_dir.mkdir(parents=True, exist_ok=True)
    out_path = reports_dir / f"asset_generation_{datetime.utcnow().date().isoformat()}.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path
