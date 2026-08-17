"""Compiles one 10-approved Video Direction into a Production Plan: exactly which speech assets
(as semantic TTS specs, not audio files), source clips, visuals, captions, and pauses are needed
and in what order -- for every Content Block. No TTS is called, no video is rendered, no clip is
downloaded or cut. 09/10 data (learning_function, required_content, viewer_action,
thinking_time_seconds, retention_intent, media_affinity, base_narration, delivery_mode,
clip_requirement) is read-only here and never redefined; this stage only decides HOW those already-
made decisions get compiled into a production-ready spec. Everything is deterministic -- no Gemini
call is made anywhere in this module.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from research.db import connect
from research.script_writer import (
    ENGLISH_WORDS_PER_MINUTE,
    KOREAN_CHARS_PER_SECOND,
    _FORMAT_LEAKAGE_PATTERNS,
    estimate_duration_and_words,
)
from research.topic_candidates import _content_words

# ---------------------------------------------------------------------------
# Fixed taxonomies
# ---------------------------------------------------------------------------

SPEECH_MODES = {"KO_NARRATION", "EN_NATIVE", "KO_PRONUNCIATION_GUIDE", "EN_PHONEME_DEMO", "ORIGINAL_NATIVE_AUDIO"}
PRODUCTION_VISUAL_TYPES = {"TARGET_WORD", "PHONEME_SEQUENCE", "KEY_CONCEPT", "COMPARISON", "QUESTION", "ANSWER_REVEAL", "RECAP"}
CAPTION_MODES = {"FULL_NARRATION", "KEY_PHRASE", "TARGET_ENGLISH", "BILINGUAL", "NONE"}
PAUSE_VISUAL_BEHAVIORS = {"HOLD_HIGHLIGHT", "FREEZE_WAVEFORM", "THINKING_DOTS", "CLEAN_HOLD", "NONE"}
TIMELINE_EVENT_TYPES = {"SPEECH", "SOURCE_CLIP", "VISUAL", "CAPTION", "PAUSE", "REPLAY", "BLOCK_TRANSITION"}
HIGHLIGHT_MODES = {"WORD", "PHRASE", "NONE"}
FORMATS = {"EDUCATION", "CLIP_ANALYSIS", "HYBRID", "PODCAST"}

# Fixed voice-casting policy (spec section 4) -- not something the planner "decides" per run.
NARRATOR_VOICE = "Charon"
PODCAST_VOICES = {"female": "Zephyr", "male": "Charon"}
# stage 10's podcast_direction speakers are ids (host_a/host_b) with no gender field; this project
# fixes host_a=female/host_b=male so the Zephyr/Charon policy above has something to key off of.
PODCAST_SPEAKER_GENDER = {"host_a": "female", "host_b": "male"}

READY_FOR_ASSET_GENERATION_SCORE_THRESHOLD = 0  # Integrity Gate decides; score is diagnostic only.

_DELIVERY_INSTRUCTIONS = {
    "KO_NARRATION": "Calm, clear Korean educational narration. Speak naturally and clearly for a beginner learner. Do not sound theatrical.",
    "EN_NATIVE": "Produce one natural native-like English pronunciation. Do not spell the word. Do not add explanation.",
    "EN_PHONEME_DEMO": "Produce only the target English sound for pronunciation demonstration. No letter name. No explanation.",
    "KO_PRONUNCIATION_GUIDE": "Read this Korean approximation naturally as a Korean pronunciation guide. It is a learner aid, not the authoritative English pronunciation.",
    "ORIGINAL_NATIVE_AUDIO": None,
}

_PRIMARY_VISUAL_TYPE_MAP = {
    "PROBLEM_RECOGNITION": "KEY_CONCEPT",
    "CORE_EXPLANATION": "PHONEME_SEQUENCE",
    "DEMONSTRATION": "PHONEME_SEQUENCE",
    "REINFORCEMENT": "COMPARISON",
    "CONTRAST": "COMPARISON",
    "TRANSFER": "PHONEME_SEQUENCE",
    "PRACTICE": "PHONEME_SEQUENCE",
    "MINI_SUCCESS": "QUESTION",
    "RECAP": "RECAP",
    "RESOLUTION": "RECAP",
    "OTHER": "KEY_CONCEPT",
}

_APPROXIMATION_SIGNAL_PHRASES = ("처럼 들릴", "라고 들릴", "근사 발음", "한글로 표기", "발음처럼")


# ---------------------------------------------------------------------------
# Source loading (read-only)
# ---------------------------------------------------------------------------

def select_target_direction(db_path: Path, direction_id: int | None = None) -> dict | None:
    with connect(db_path) as conn:
        if direction_id is not None:
            row = conn.execute("SELECT * FROM video_directions WHERE id = ?", (direction_id,)).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM video_directions WHERE ready_for_production_planning = 1 ORDER BY generated_at DESC LIMIT 1"
            ).fetchone()
    return dict(row) if row else None


def _load_direction_bundle(db_path: Path, direction_row: dict) -> dict:
    """Reads everything 11 is allowed to depend on -- all read-only, nothing here is mutated."""
    with connect(db_path) as conn:
        script_row = conn.execute("SELECT * FROM video_scripts WHERE id = ?", (direction_row["video_script_id"],)).fetchone()
        block_direction_rows = conn.execute(
            "SELECT * FROM block_directions WHERE video_direction_id = ?", (direction_row["id"],)
        ).fetchall()
        clip_rows = conn.execute(
            "SELECT * FROM source_clip_candidates WHERE video_direction_id = ?", (direction_row["id"],)
        ).fetchall()

    script_row = dict(script_row) if script_row else {}
    try:
        content_blocks = json.loads(script_row.get("content_blocks_json") or "[]")
    except (TypeError, ValueError):
        content_blocks = []

    block_directions = []
    for row in block_direction_rows:
        bd = dict(row)
        for key in ("viewer_interaction_json", "audio_requirement_json", "visual_requirement_json", "clip_requirement_json", "retention_role_json"):
            try:
                bd[key.replace("_json", "")] = json.loads(bd.get(key) or "null")
            except (TypeError, ValueError):
                bd[key.replace("_json", "")] = None
        block_directions.append(bd)

    clip_candidates_by_block: dict[str, list[dict]] = {}
    for row in clip_rows:
        c = dict(row)
        clip_candidates_by_block.setdefault(c["content_block_id"], []).append(c)

    podcast_direction = None
    raw_podcast = direction_row.get("podcast_direction_json")
    if raw_podcast:
        try:
            podcast_direction = json.loads(raw_podcast)
        except (TypeError, ValueError):
            podcast_direction = None

    return {
        "script_row": script_row,
        "content_blocks": content_blocks,
        "block_directions": block_directions,
        "clip_candidates_by_block": clip_candidates_by_block,
        "podcast_direction": podcast_direction,
    }


def _selected_clip_for_block(bundle: dict, content_block_id: str) -> dict | None:
    for candidate in bundle["clip_candidates_by_block"].get(content_block_id, []):
        if candidate.get("selected"):
            return candidate
    return None


# ---------------------------------------------------------------------------
# Narration segmentation (spec section 7): a mixed Korean/English/IPA sentence is never sent to
# TTS as one blob. Deterministic regex split -- same "no ML/embeddings" trade-off already accepted
# elsewhere in this project (e.g. topic_candidates._content_words): the Korean particle
# immediately after an extracted token can read slightly awkwardly in isolation, which is a known,
# documented limitation rather than an attempt at real NLU segmentation.
# ---------------------------------------------------------------------------

_PHONEME_TOKEN_RE = re.compile(r"/[^/\s]+/")
_ENGLISH_WORD_TOKEN_RE = re.compile(r"[A-Z]{2,}")
_SEGMENT_TOKEN_RE = re.compile(r"(/[^/\s]+/)|([A-Z]{2,})")


def segment_narration(text: str) -> list[dict]:
    tokens: list[dict] = []
    text = text or ""
    last_end = 0
    for m in _SEGMENT_TOKEN_RE.finditer(text):
        if m.start() > last_end:
            chunk = text[last_end:m.start()]
            if chunk.strip(" ,.!?\n"):
                tokens.append({"kind": "KOREAN", "text": chunk.strip()})
        if m.group(1):
            tokens.append({"kind": "PHONEME", "text": m.group(1)})
        else:
            tokens.append({"kind": "ENGLISH_WORD", "text": m.group(2)})
        last_end = m.end()
    if last_end < len(text):
        tail = text[last_end:]
        if tail.strip(" ,.!?\n"):
            tokens.append({"kind": "KOREAN", "text": tail.strip()})
    return tokens


def classify_speech_mode(kind: str, korean_text: str = "", has_native_audio_source: bool = False) -> str:
    """Spec section 6 priority order, coded exactly."""
    if has_native_audio_source:
        return "ORIGINAL_NATIVE_AUDIO"
    if kind == "ENGLISH_WORD":
        return "EN_NATIVE"
    if kind == "PHONEME":
        return "EN_PHONEME_DEMO"
    if kind == "KOREAN" and any(p in korean_text for p in _APPROXIMATION_SIGNAL_PHRASES):
        return "KO_PRONUNCIATION_GUIDE"
    return "KO_NARRATION"


# ---------------------------------------------------------------------------
# Speech Asset registry (dedup, spec section 32)
# ---------------------------------------------------------------------------

class SpeechAssetRegistry:
    """One registry per Production Plan. Assets are deduplicated by (speech_mode, voice_name,
    source_text, delivery_intent) so the same EN_NATIVE "BAG" spoken twice in a video reuses one
    asset instead of being planned as two separate TTS generations (spec section 32)."""

    def __init__(self):
        self._by_key: dict[tuple, str] = {}
        self._counter = 0
        self.assets: list[dict] = []

    def get_or_create(
        self, speech_mode: str, voice_name: str | None, source_text: str, delivery_intent: str = "natural",
        **extra,
    ) -> str:
        key = (speech_mode, voice_name, source_text, delivery_intent)
        if key in self._by_key:
            return self._by_key[key]
        self._counter += 1
        asset_id = f"SP{self._counter:03d}"
        asset = {
            "speech_asset_id": asset_id,
            "speech_mode": speech_mode,
            "voice_name": voice_name,
            "language_code": "en-US" if speech_mode in {"EN_NATIVE", "EN_PHONEME_DEMO"} else ("ko-KR" if speech_mode != "ORIGINAL_NATIVE_AUDIO" else None),
            "source_text": source_text,
            "tts_input_text": source_text,
            "display_text": source_text,
            "expected_pronunciation": source_text if speech_mode == "EN_PHONEME_DEMO" else None,
            "delivery_intent": delivery_intent,
            "delivery_instruction": _DELIVERY_INSTRUCTIONS.get(speech_mode),
            "approximation_only": speech_mode == "KO_PRONUNCIATION_GUIDE",
            "source_clip_candidate_id": extra.get("source_clip_candidate_id"),
            "pause_before_ms": 0,
            "pause_after_ms": 0,
            "replay_group": extra.get("replay_group"),
        }
        self._by_key[key] = asset_id
        self.assets.append(asset)
        return asset_id

    def by_id(self) -> dict[str, dict]:
        return {a["speech_asset_id"]: a for a in self.assets}


# ---------------------------------------------------------------------------
# Pause (first-class object, spec section 15)
# ---------------------------------------------------------------------------

def build_pause_event(content_block: dict) -> dict | None:
    thinking_time = content_block.get("thinking_time_seconds") or 0
    if content_block.get("viewer_action") and thinking_time > 0:
        return {"duration_ms": int(thinking_time * 1000), "pause_visual_behavior": "THINKING_DOTS"}
    return None


# ---------------------------------------------------------------------------
# Per-block speech plan: tokenize narration, resolve each token to a (deduplicated) speech asset,
# and -- for blocks with a viewer-attempt pause -- keep the spoken "answer" content (the target
# word's pronunciation and its phoneme breakdown) strictly after the pause. The word's first
# mention becomes a VISUAL prompt (text shown, not spoken) instead, matching spec section 36's
# worked example (VISUAL CAP before PAUSE, spoken EN_NATIVE CAP only after).
# ---------------------------------------------------------------------------

def build_block_speech_plan(content_block: dict, registry: SpeechAssetRegistry, has_native_audio_source: bool = False) -> dict:
    tokens = segment_narration(content_block.get("base_narration") or "")
    thinking_time = content_block.get("thinking_time_seconds") or 0
    has_pause = bool(content_block.get("viewer_action")) and thinking_time > 0

    def _resolve(tok: dict) -> dict:
        speech_mode = classify_speech_mode(
            tok["kind"], korean_text=tok["text"] if tok["kind"] == "KOREAN" else "",
            has_native_audio_source=has_native_audio_source and tok["kind"] in {"ENGLISH_WORD", "PHONEME"},
        )
        voice = None if speech_mode == "ORIGINAL_NATIVE_AUDIO" else NARRATOR_VOICE
        asset_id = registry.get_or_create(speech_mode, voice, tok["text"])
        return {"speech_asset_id": asset_id, "speech_mode": speech_mode, "text": tok["text"]}

    if not has_pause:
        return {
            "pre_pause": [_resolve(t) for t in tokens],
            "visual_word": None,
            "post_pause": [],
            "pause_event": None,
        }

    korean_tokens = [t for t in tokens if t["kind"] == "KOREAN"]
    practice_tokens = [t for t in tokens if t["kind"] in ("PHONEME", "ENGLISH_WORD")]

    visual_word = None
    remaining_practice = []
    for t in practice_tokens:
        if t["kind"] == "ENGLISH_WORD" and visual_word is None:
            visual_word = t["text"]
            continue
        remaining_practice.append(t)

    return {
        "pre_pause": [_resolve(t) for t in korean_tokens],
        "visual_word": visual_word,
        "post_pause": [_resolve(t) for t in remaining_practice],
        "pause_event": build_pause_event(content_block),
    }


# ---------------------------------------------------------------------------
# Timeline assembly (spec section 26)
# ---------------------------------------------------------------------------

def build_timeline(content_block: dict, speech_plan: dict, selected_clip: dict | None = None) -> list[dict]:
    events: list[dict] = []
    order = 1

    if selected_clip:
        events.append({
            "event_order": order, "type": "SOURCE_CLIP", "source_clip_candidate_id": selected_clip["id"],
            "focus_in": selected_clip["focus_in"], "focus_out": selected_clip["focus_out"],
            "context_in": selected_clip["context_in"], "context_out": selected_clip["context_out"],
        })
        order += 1

    for seg in speech_plan["pre_pause"]:
        events.append({"event_order": order, "type": "SPEECH", "speech_asset_id": seg["speech_asset_id"]})
        order += 1

    if speech_plan["visual_word"]:
        events.append({"event_order": order, "type": "VISUAL", "visual_role": "TARGET_WORD", "content": speech_plan["visual_word"]})
        order += 1

    if speech_plan["pause_event"]:
        events.append({"event_order": order, "type": "PAUSE", **speech_plan["pause_event"]})
        order += 1

    for seg in speech_plan["post_pause"]:
        events.append({"event_order": order, "type": "SPEECH", "speech_asset_id": seg["speech_asset_id"]})
        order += 1

    return events


# ---------------------------------------------------------------------------
# Visual / Caption spec (semantic only -- spec sections 23-24)
# ---------------------------------------------------------------------------

def build_visual_spec(content_block: dict) -> dict:
    learning_function = content_block.get("learning_function", "OTHER")
    primary = _PRIMARY_VISUAL_TYPE_MAP.get(learning_function, "KEY_CONCEPT")
    answer_hidden = bool(content_block.get("viewer_action")) and (content_block.get("thinking_time_seconds") or 0) > 0
    content_items = [
        tok["text"] for tok in segment_narration(content_block.get("base_narration") or "")
        if tok["kind"] in ("PHONEME", "ENGLISH_WORD")
    ]
    return {
        "primary_visual_type": primary,
        "content": content_items,
        "progressive_reveal": learning_function in {"CORE_EXPLANATION", "DEMONSTRATION", "TRANSFER"},
        "answer_hidden_until_attempt": answer_hidden,
    }


def build_caption_spec(content_block: dict, speech_plan: dict) -> dict:
    all_segments = speech_plan["pre_pause"] + speech_plan["post_pause"]
    has_approximation = any(seg["speech_mode"] == "KO_PRONUNCIATION_GUIDE" for seg in all_segments)
    learning_function = content_block.get("learning_function", "OTHER")
    if learning_function == "MINI_SUCCESS":
        caption_mode = "TARGET_ENGLISH"
    elif learning_function in {"CORE_EXPLANATION", "DEMONSTRATION", "REINFORCEMENT", "TRANSFER"}:
        caption_mode = "KEY_PHRASE"
    else:
        caption_mode = "FULL_NARRATION"
    highlight_mode = "WORD" if learning_function in {"CORE_EXPLANATION", "DEMONSTRATION", "MINI_SUCCESS"} else "NONE"
    return {
        "caption_mode": caption_mode,
        "highlight_mode": highlight_mode,
        "approximation_label_required": has_approximation,
    }


# ---------------------------------------------------------------------------
# required_content coverage (spec section 29)
# ---------------------------------------------------------------------------

_COVERAGE_PUNCTUATION_RE = re.compile(r"[\"'“”‘’.,!?()]")


def _coverage_words(text: str) -> set:
    """_content_words as-is, plus quote/period stripping local to this check only -- required_
    content bullets often quote a phrase ("'이해하면 쉬워진다'") while the actual narration writes
    it unquoted, and a leading/trailing quote character was enough to break an otherwise-exact
    word match. Not touched in the shared _content_words utility since other callers rely on its
    current behavior."""
    return _content_words(_COVERAGE_PUNCTUATION_RE.sub("", text))


def compute_required_content_coverage(content_block: dict, timeline_events: list[dict], speech_assets_by_id: dict) -> dict:
    coverage: dict[str, list[str]] = {}
    for item in content_block.get("required_content") or []:
        item_words = _coverage_words(str(item))
        matches = []
        for ev in timeline_events:
            if ev["type"] == "SPEECH":
                asset = speech_assets_by_id.get(ev["speech_asset_id"])
                text = asset["source_text"] if asset else ""
                if item_words and _coverage_words(text) & item_words:
                    matches.append(f"SPEECH:{ev['speech_asset_id']}")
            elif ev["type"] == "VISUAL":
                text = str(ev.get("content") or "")
                if item_words and _coverage_words(text) & item_words:
                    matches.append(f"VISUAL:{ev['event_order']}")
        coverage[str(item)] = matches
    return coverage


# ---------------------------------------------------------------------------
# Production Complexity (spec section 33)
# ---------------------------------------------------------------------------

def estimate_production_complexity(production_blocks: list[dict], complexity_config: dict | None = None) -> str:
    complexity_config = complexity_config or {}
    total_signals = 0
    for pb in production_blocks:
        total_signals += len(pb.get("speech_segments") or [])
        total_signals += 1 if pb.get("clip_spec") else 0
        total_signals += 1 if (pb.get("interaction_spec") or {}).get("has_pause") else 0
        total_signals += len((pb.get("visual_spec") or {}).get("content") or []) and 1 or 0

    high_at = complexity_config.get("high_at_total_signals", 22)
    medium_at = complexity_config.get("medium_at_total_signals", 12)
    if total_signals >= high_at:
        return "high"
    if total_signals >= medium_at:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Duration (reuses script_writer's estimator -- spec section 27 explicitly forbids a duplicate
# formula)
# ---------------------------------------------------------------------------

def estimate_block_duration(speech_plan: dict, selected_clip: dict | None = None) -> float:
    all_segments = speech_plan["pre_pause"] + speech_plan["post_pause"]
    combined_text = " ".join(seg["text"] for seg in all_segments)
    seconds, _ = estimate_duration_and_words(combined_text)
    if speech_plan["pause_event"]:
        seconds += speech_plan["pause_event"]["duration_ms"] / 1000.0
    if selected_clip:
        seconds += max(0.0, selected_clip["focus_out"] - selected_clip["focus_in"])
    return round(seconds, 1)


# ---------------------------------------------------------------------------
# PODCAST production blocks (isolated grammar -- spec section 21)
# ---------------------------------------------------------------------------

def build_podcast_production_blocks(bundle: dict, registry: SpeechAssetRegistry) -> list[dict]:
    podcast_direction = bundle.get("podcast_direction") or {"dialogue_beats": []}
    beats_by_block: dict[str, list[dict]] = {}
    for beat in podcast_direction.get("dialogue_beats") or []:
        beats_by_block.setdefault(beat.get("content_block_id"), []).append(beat)

    production_blocks = []
    for order, content_block_id in enumerate(beats_by_block.keys(), start=1):
        events = []
        segments = []
        for i, beat in enumerate(beats_by_block[content_block_id], start=1):
            speaker = beat.get("speaker", "host_a")
            gender = PODCAST_SPEAKER_GENDER.get(speaker, "male")
            voice = PODCAST_VOICES[gender]
            asset_id = registry.get_or_create("KO_NARRATION", voice, str(beat.get("text") or ""), delivery_intent=f"podcast:{speaker}")
            segments.append({"speech_asset_id": asset_id, "speech_mode": "KO_NARRATION", "text": beat.get("text")})
            events.append({"event_order": i, "type": "SPEECH", "speech_asset_id": asset_id})

        speech_plan = {"pre_pause": segments, "post_pause": [], "visual_word": None, "pause_event": None}
        production_blocks.append({
            "content_block_id": content_block_id,
            "block_order": order,
            "delivery_mode": "PODCAST",
            "production_intent": "podcast_dialogue",
            "timeline": events,
            "speech_plan": speech_plan,
            "visual_spec": {"primary_visual_type": "KEY_CONCEPT", "content": [], "progressive_reveal": False, "answer_hidden_until_attempt": False},
            "caption_spec": {"caption_mode": "FULL_NARRATION", "highlight_mode": "NONE", "approximation_label_required": False},
            "clip_spec": None,
            "interaction_spec": {"has_pause": False, "viewer_action": None, "thinking_time_seconds": 0},
            "required_content_coverage": {},
        })
    return production_blocks


# ---------------------------------------------------------------------------
# Integrity Check (19 items, spec section 34) + Ready Gate
# ---------------------------------------------------------------------------

def run_planner_integrity_check(
    content_blocks: list[dict], final_format: str, production_blocks: list[dict],
    speech_assets_by_id: dict, clip_candidates_by_block: dict, source_direction_unchanged: bool,
) -> dict:
    checks = {}

    checks["valid_final_format"] = "pass" if final_format in FORMATS else "fail"
    checks["source_direction_unchanged"] = "pass" if source_direction_unchanged else "fail"

    if final_format == "PODCAST":
        eligible_ids = {pb["content_block_id"] for pb in production_blocks}
    else:
        eligible_ids = {b["content_block_id"] for b in content_blocks if b.get("direction_eligible", True)}
    covered_ids = {pb["content_block_id"] for pb in production_blocks}
    checks["content_blocks_preserved"] = "pass" if eligible_ids.issubset(covered_ids) else "fail"

    orders = [pb["block_order"] for pb in production_blocks]
    checks["block_order_preserved"] = "pass" if orders == sorted(orders) and len(orders) == len(set(orders)) else "fail"

    missing_coverage = any(
        any(not matches for matches in pb.get("required_content_coverage", {}).values())
        for pb in production_blocks
    )
    checks["required_content_covered"] = "fail" if missing_coverage else "pass"

    block_by_id = {b["content_block_id"]: b for b in content_blocks}
    lost_viewer_action = any(
        block_by_id.get(pb["content_block_id"], {}).get("viewer_action")
        and not (pb.get("interaction_spec") or {}).get("viewer_action")
        for pb in production_blocks if pb["content_block_id"] in block_by_id
    )
    checks["viewer_action_preserved"] = "fail" if lost_viewer_action else "pass"

    lost_thinking_time = any(
        (block_by_id.get(pb["content_block_id"], {}).get("thinking_time_seconds") or 0) > 0
        and not any(ev["type"] == "PAUSE" and ev.get("duration_ms") == int(block_by_id[pb["content_block_id"]]["thinking_time_seconds"] * 1000) for ev in pb.get("timeline") or [])
        for pb in production_blocks if pb["content_block_id"] in block_by_id
    )
    checks["thinking_time_preserved"] = "fail" if lost_thinking_time else "pass"

    revealed_early = False
    for pb in production_blocks:
        timeline = pb.get("timeline") or []
        pause_index = next((i for i, ev in enumerate(timeline) if ev["type"] == "PAUSE"), None)
        if pause_index is None:
            continue
        for ev in timeline[:pause_index]:
            if ev["type"] == "SPEECH":
                asset = speech_assets_by_id.get(ev["speech_asset_id"])
                if asset and asset["speech_mode"] in {"EN_NATIVE", "EN_PHONEME_DEMO"}:
                    revealed_early = True
    checks["answer_not_revealed_before_attempt"] = "fail" if revealed_early else "pass"

    checks["speech_mode_valid"] = "pass" if all(a["speech_mode"] in SPEECH_MODES for a in speech_assets_by_id.values()) else "fail"

    voice_ok = True
    for asset in speech_assets_by_id.values():
        if asset["speech_mode"] == "ORIGINAL_NATIVE_AUDIO":
            continue
        if final_format == "PODCAST":
            if asset["voice_name"] not in PODCAST_VOICES.values():
                voice_ok = False
        elif asset["voice_name"] != NARRATOR_VOICE:
            voice_ok = False
    checks["voice_casting_valid"] = "pass" if voice_ok else "fail"

    native_audio_ok = True
    for asset in speech_assets_by_id.values():
        if asset["speech_mode"] == "ORIGINAL_NATIVE_AUDIO":
            candidate_ids = {c["id"] for candidates in clip_candidates_by_block.values() for c in candidates}
            if asset.get("source_clip_candidate_id") not in candidate_ids:
                native_audio_ok = False
    checks["native_audio_source_valid"] = "pass" if native_audio_ok else "fail"

    approx_ok = all(
        asset["approximation_only"] for asset in speech_assets_by_id.values() if asset["speech_mode"] == "KO_PRONUNCIATION_GUIDE"
    )
    checks["korean_approximation_labeled"] = "pass" if approx_ok else "fail"

    phoneme_ok = all(
        asset["source_text"].startswith("/") and asset["source_text"].endswith("/")
        for asset in speech_assets_by_id.values() if asset["speech_mode"] == "EN_PHONEME_DEMO"
    )
    checks["phoneme_source_of_truth_preserved"] = "pass" if phoneme_ok else "fail"

    clip_boundary_ok = True
    for pb in production_blocks:
        for ev in pb.get("timeline") or []:
            if ev["type"] != "SOURCE_CLIP":
                continue
            candidates = clip_candidates_by_block.get(pb["content_block_id"], [])
            source = next((c for c in candidates if c["id"] == ev.get("source_clip_candidate_id")), None)
            if not source or source["focus_in"] != ev["focus_in"] or source["focus_out"] != ev["focus_out"] \
                    or source["context_in"] != ev["context_in"] or source["context_out"] != ev["context_out"]:
                clip_boundary_ok = False
    checks["clip_boundary_preserved"] = "pass" if clip_boundary_ok else "fail"

    if final_format == "PODCAST":
        # Charon alone can't distinguish an EDUCATION narrator from the podcast's own male host --
        # both legitimately use Charon. delivery_intent ("podcast:host_a"/"podcast:host_b") is the
        # signal that actually marks an asset as belonging to the podcast dialogue grammar.
        isolation_ok = all(
            a["speech_mode"] == "ORIGINAL_NATIVE_AUDIO" or str(a.get("delivery_intent", "")).startswith("podcast:")
            for a in speech_assets_by_id.values()
        )
    else:
        isolation_ok = not any(a["voice_name"] == PODCAST_VOICES["female"] for a in speech_assets_by_id.values())
    checks["podcast_voice_isolation_safe"] = "pass" if isolation_ok else "fail"

    pause_ok = True
    for pb in production_blocks:
        for ev in pb.get("timeline") or []:
            if ev["type"] == "PAUSE" and ev.get("pause_visual_behavior") not in PAUSE_VISUAL_BEHAVIORS:
                pause_ok = False
    checks["pause_visualization_valid"] = "pass" if pause_ok else "fail"

    timeline_order_ok = True
    for pb in production_blocks:
        orders_in_block = [ev["event_order"] for ev in pb.get("timeline") or []]
        if orders_in_block != list(range(1, len(orders_in_block) + 1)):
            timeline_order_ok = False
    checks["timeline_order_valid"] = "pass" if timeline_order_ok else "fail"

    asset_refs_ok = True
    for pb in production_blocks:
        for ev in pb.get("timeline") or []:
            if ev["type"] == "SPEECH" and ev.get("speech_asset_id") not in speech_assets_by_id:
                asset_refs_ok = False
            if ev["type"] == "SOURCE_CLIP":
                candidates = clip_candidates_by_block.get(pb["content_block_id"], [])
                if not any(c["id"] == ev.get("source_clip_candidate_id") for c in candidates):
                    asset_refs_ok = False
    checks["asset_references_valid"] = "pass" if asset_refs_ok else "fail"

    text_blob_parts = [str(a.get("source_text") or "") for a in speech_assets_by_id.values()]
    text_blob_parts.extend(str(pb.get("production_intent") or "") for pb in production_blocks)
    blob = " ".join(text_blob_parts)
    checks["no_renderer_specific_instruction"] = "fail" if any(p in blob for p in _FORMAT_LEAKAGE_PATTERNS) else "pass"

    return checks


def ready_for_asset_generation_gate(checks: dict) -> bool:
    return not any(status == "fail" for status in checks.values())


# ---------------------------------------------------------------------------
# Planner Score (diagnostic only -- never overrides the Integrity Gate)
# ---------------------------------------------------------------------------

def compute_planner_score(production_blocks: list[dict], checks: dict, speech_assets_by_id: dict) -> float:
    total_required = 0
    covered_required = 0
    for pb in production_blocks:
        for matches in pb.get("required_content_coverage", {}).values():
            total_required += 1
            if matches:
                covered_required += 1
    coverage_score = 100.0 * covered_required / total_required if total_required else 100.0

    fail_count = sum(1 for v in checks.values() if v == "fail")
    pronunciation_checks = ("speech_mode_valid", "voice_casting_valid", "korean_approximation_labeled", "phoneme_source_of_truth_preserved")
    pronunciation_score = 100.0 if all(checks.get(c) == "pass" for c in pronunciation_checks) else 40.0
    interaction_score = 100.0 if checks.get("viewer_action_preserved") == "pass" and checks.get("thinking_time_preserved") == "pass" and checks.get("answer_not_revealed_before_attempt") == "pass" else 30.0
    timeline_score = 100.0 if checks.get("timeline_order_valid") == "pass" and checks.get("asset_references_valid") == "pass" else 30.0

    unique_assets = len(speech_assets_by_id)
    total_occurrences = sum(len(pb.get("speech_plan", {}).get("pre_pause", [])) + len(pb.get("speech_plan", {}).get("post_pause", [])) for pb in production_blocks)
    reusability_score = 100.0 * (1 - (unique_assets / total_occurrences)) if total_occurrences and unique_assets <= total_occurrences else 50.0
    reusability_score = max(0.0, min(100.0, reusability_score + 50.0))  # baseline credit even with no reuse opportunity

    speech_planning_score = 100.0 if fail_count == 0 else max(0.0, 100.0 - fail_count * 15.0)

    return round(
        coverage_score * 0.25 + speech_planning_score * 0.20 + pronunciation_score * 0.20
        + interaction_score * 0.15 + timeline_score * 0.10 + reusability_score * 0.10,
        1,
    )


# ---------------------------------------------------------------------------
# Orchestration + persistence + report
# ---------------------------------------------------------------------------

def build_production_plan(
    db_path: Path, *, direction_id: int | None = None,
    clip_config: dict | None = None, complexity_config: dict | None = None,
) -> dict:
    direction_row = select_target_direction(db_path, direction_id=direction_id)
    if direction_row is None:
        raise ValueError("No video_directions row with ready_for_production_planning=1 (or no such direction_id). Run `research direction` first.")

    bundle = _load_direction_bundle(db_path, direction_row)
    content_blocks = bundle["content_blocks"]
    final_format = direction_row["final_format"]

    registry = SpeechAssetRegistry()
    production_blocks: list[dict] = []

    if final_format == "PODCAST":
        production_blocks = build_podcast_production_blocks(bundle, registry)
    else:
        block_direction_by_id = {bd["content_block_id"]: bd for bd in bundle["block_directions"]}
        eligible_blocks = [b for b in content_blocks if b.get("direction_eligible", True)]
        for order, block in enumerate(eligible_blocks, start=1):
            block_id = block["content_block_id"]
            bd = block_direction_by_id.get(block_id, {})
            selected_clip = _selected_clip_for_block(bundle, block_id)
            has_native_audio = bd.get("delivery_mode") == "CLIP_ANALYSIS" and selected_clip is not None

            speech_plan = build_block_speech_plan(block, registry, has_native_audio_source=has_native_audio)
            timeline = build_timeline(block, speech_plan, selected_clip=selected_clip)
            visual_spec = build_visual_spec(block)
            caption_spec = build_caption_spec(block, speech_plan)
            coverage = compute_required_content_coverage(block, timeline, registry.by_id())

            clip_spec = None
            if selected_clip:
                clip_spec = {
                    "source_clip_candidate_id": selected_clip["id"], "clip_role": selected_clip["clip_role"],
                    "clip_grade": selected_clip["clip_grade"], "focus_in": selected_clip["focus_in"],
                    "focus_out": selected_clip["focus_out"], "context_in": selected_clip["context_in"],
                    "context_out": selected_clip["context_out"],
                }

            production_blocks.append({
                "content_block_id": block_id,
                "block_order": order,
                "delivery_mode": bd.get("delivery_mode", "EDUCATION"),
                "production_intent": bd.get("production_intent"),
                "timeline": timeline,
                "speech_plan": speech_plan,
                "speech_segments": speech_plan["pre_pause"] + speech_plan["post_pause"],
                "visual_spec": visual_spec,
                "caption_spec": caption_spec,
                "clip_spec": clip_spec,
                "interaction_spec": {
                    "has_pause": bool(speech_plan["pause_event"]),
                    "viewer_action": block.get("viewer_action"),
                    "thinking_time_seconds": block.get("thinking_time_seconds", 0),
                },
                "required_content_coverage": coverage,
            })

    with connect(db_path) as conn:
        after_direction = conn.execute(
            "SELECT preferred_format, final_format, integrity_json FROM video_directions WHERE id = ?", (direction_row["id"],)
        ).fetchone()
        after_block_directions = conn.execute(
            "SELECT content_block_id, delivery_mode FROM block_directions WHERE video_direction_id = ? ORDER BY id", (direction_row["id"],)
        ).fetchall()
    source_unchanged = (
        after_direction is not None
        and after_direction["preferred_format"] == direction_row["preferred_format"]
        and after_direction["final_format"] == direction_row["final_format"]
        and after_direction["integrity_json"] == direction_row["integrity_json"]
    )

    speech_assets_by_id = registry.by_id()
    checks = run_planner_integrity_check(
        content_blocks, final_format, production_blocks, speech_assets_by_id,
        bundle["clip_candidates_by_block"], source_unchanged,
    )
    ready = ready_for_asset_generation_gate(checks)

    complexity = estimate_production_complexity(production_blocks, complexity_config)
    total_duration = sum(
        estimate_block_duration(pb["speech_plan"], selected_clip=_selected_clip_for_block(bundle, pb["content_block_id"]))
        for pb in production_blocks if "speech_plan" in pb
    )
    planner_score = compute_planner_score(production_blocks, checks, speech_assets_by_id)

    return {
        "direction_row": direction_row,
        "script_row": bundle["script_row"],
        "content_blocks": content_blocks,
        "final_format": final_format,
        "production_blocks": production_blocks,
        "speech_assets": registry.assets,
        "estimated_duration_seconds": round(total_duration, 1),
        "production_complexity": complexity,
        "generation_method": "deterministic",
        "integrity_checks": checks,
        "ready_for_asset_generation": ready,
        "planner_score": planner_score,
    }


def _persist(db_path: Path, result: dict, report_path: str) -> int:
    direction_row = result["direction_row"]
    plan_json = {
        "final_format": result["final_format"],
        "production_blocks": [
            {k: v for k, v in pb.items() if k != "speech_plan"} for pb in result["production_blocks"]
        ],
    }

    with connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO production_plans (report_path, video_direction_id, video_script_id, final_format,
                plan_json, estimated_duration_seconds, production_complexity, generation_method,
                integrity_check_json, planner_score, ready_for_asset_generation)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report_path, direction_row["id"], direction_row["video_script_id"], result["final_format"],
                json.dumps(plan_json, ensure_ascii=False), result["estimated_duration_seconds"],
                result["production_complexity"], result["generation_method"],
                json.dumps(result["integrity_checks"], ensure_ascii=False), result["planner_score"],
                1 if result["ready_for_asset_generation"] else 0,
            ),
        )
        plan_id = cur.lastrowid

        for pb in result["production_blocks"]:
            conn.execute(
                """
                INSERT INTO production_blocks (production_plan_id, content_block_id, block_order,
                    delivery_mode, production_intent, timeline_spec_json, speech_segments_json,
                    visual_spec_json, caption_spec_json, clip_spec_json, interaction_spec_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plan_id, pb["content_block_id"], pb["block_order"], pb["delivery_mode"], pb["production_intent"],
                    json.dumps(pb["timeline"], ensure_ascii=False),
                    json.dumps(pb.get("speech_segments") or (pb["speech_plan"]["pre_pause"] + pb["speech_plan"]["post_pause"]), ensure_ascii=False),
                    json.dumps(pb["visual_spec"], ensure_ascii=False), json.dumps(pb["caption_spec"], ensure_ascii=False),
                    json.dumps(pb["clip_spec"], ensure_ascii=False) if pb.get("clip_spec") else None,
                    json.dumps(pb["interaction_spec"], ensure_ascii=False),
                ),
            )

        for asset in result["speech_assets"]:
            conn.execute(
                """
                INSERT INTO speech_assets (production_plan_id, content_block_id, speech_asset_id, speech_mode,
                    voice_name, language_code, source_text, tts_input_text, display_text,
                    expected_pronunciation, approximation_only, source_clip_candidate_id,
                    pause_before_ms, pause_after_ms, replay_group)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plan_id, "", asset["speech_asset_id"], asset["speech_mode"], asset["voice_name"],
                    asset["language_code"], asset["source_text"], asset["tts_input_text"], asset["display_text"],
                    asset["expected_pronunciation"], 1 if asset["approximation_only"] else 0,
                    asset.get("source_clip_candidate_id"), asset["pause_before_ms"], asset["pause_after_ms"],
                    asset.get("replay_group"),
                ),
            )

    return plan_id


def _fmt(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)


def build_production_plan_report(
    db_path: Path, reports_dir: Path, *, direction_id: int | None = None,
    clip_config: dict | None = None, complexity_config: dict | None = None,
) -> Path:
    result = build_production_plan(db_path, direction_id=direction_id, clip_config=clip_config, complexity_config=complexity_config)
    direction_row = result["direction_row"]

    speech_mode_counts: dict[str, int] = {}
    voice_counts: dict[str, int] = {}
    for asset in result["speech_assets"]:
        speech_mode_counts[asset["speech_mode"]] = speech_mode_counts.get(asset["speech_mode"], 0) + 1
        if asset["voice_name"]:
            voice_counts[asset["voice_name"]] = voice_counts.get(asset["voice_name"], 0) + 1

    lines: list[str] = []
    lines.append("# Production Plan Report")
    lines.append("")
    lines.append(f"생성일: {date.today().isoformat()}")
    lines.append(f"Generation Method: {result['generation_method']}")
    lines.append("")

    lines.append("## 1. Source Video Direction")
    lines.append("")
    lines.append(f"video_directions.id: {direction_row['id']}")
    lines.append(f"final_format: {result['final_format']}")
    lines.append("")

    lines.append("## 2. Production Blocks")
    lines.append("")
    lines.append(f"총 {len(result['production_blocks'])}개")
    lines.append("")

    lines.append("## 3. Speech Assets")
    lines.append("")
    lines.append(f"총 {len(result['speech_assets'])}개 (중복 제거됨)")
    lines.append(f"Speech Mode별: {speech_mode_counts}")
    lines.append(f"Voice별: {voice_counts}")
    lines.append("")

    lines.append("## 4. Block별 Speech 구조")
    lines.append("")
    for pb in result["production_blocks"]:
        lines.append(f"### {pb['content_block_id']} (order={pb['block_order']}, delivery_mode={pb['delivery_mode']})")
        for ev in pb["timeline"]:
            if ev["type"] == "SPEECH":
                asset = next((a for a in result["speech_assets"] if a["speech_asset_id"] == ev["speech_asset_id"]), None)
                lines.append(f"- SPEECH [{asset['speech_mode']}] {asset['voice_name']}: \"{asset['source_text']}\"")
            elif ev["type"] == "PAUSE":
                lines.append(f"- PAUSE {ev['duration_ms']}ms ({ev.get('pause_visual_behavior')})")
            elif ev["type"] == "VISUAL":
                lines.append(f"- VISUAL [{ev.get('visual_role')}] {ev.get('content')}")
            elif ev["type"] == "SOURCE_CLIP":
                lines.append(f"- SOURCE_CLIP focus=({_fmt(ev['focus_in'])}, {_fmt(ev['focus_out'])})")
        lines.append("")

    lines.append("## 5. Required Content Coverage")
    lines.append("")
    for pb in result["production_blocks"]:
        for item, matches in pb.get("required_content_coverage", {}).items():
            lines.append(f"- [{pb['content_block_id']}] \"{item}\": {matches if matches else 'UNCOVERED'}")
    lines.append("")

    lines.append("## 6. Production Complexity")
    lines.append("")
    lines.append(result["production_complexity"])
    lines.append(f"Estimated Duration: {_fmt(result['estimated_duration_seconds'])}초 (추정값, 실측 TTS 아님)")
    lines.append("")

    lines.append("## 7. Integrity Check")
    lines.append("")
    for check, status in result["integrity_checks"].items():
        lines.append(f"- {check}: {status}")
    lines.append("")

    lines.append("## 8. Ready for Asset Generation")
    lines.append("")
    lines.append("YES" if result["ready_for_asset_generation"] else "NO")
    lines.append(f"Planner Score (참고용): {_fmt(result['planner_score'])}")
    lines.append("")

    lines.append("## 9. Known Limitations")
    lines.append("")
    lines.append("- Speech Segmentation은 정규식 기반 결정론적 분리이며 실제 NLU가 아니다 -- 추출된 영어/음소 "
                  "토큰 바로 뒤에 남는 한국어 조사가 다소 어색하게 이어질 수 있다.")
    lines.append("- 실제 TTS는 호출하지 않았다. Speech Asset은 12단계 Asset Generator가 사용할 semantic "
                  "direction일 뿐이며, estimated_duration_seconds는 실측이 아닌 추정값이다.")
    lines.append("")

    reports_dir.mkdir(parents=True, exist_ok=True)
    out_path = reports_dir / f"production_plan_{date.today().isoformat()}.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")

    _persist(db_path, result, str(out_path))

    return out_path
