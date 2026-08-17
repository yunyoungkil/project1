"""Turns one 09-3 format-neutral Content Script into a Video Direction: which of the four
allowed formats (EDUCATION / CLIP_ANALYSIS / HYBRID / PODCAST) best delivers it, why, and how each
Content Block should be presented. 09's Content Script is a READ-ONLY source here -- nothing about
it (learning_function, required_content, viewer_action, thinking_time_seconds, retention_intent,
media_affinity, base_narration) is redefined. Choosing a rendering engine, camera work, subtitle
style, or any other production-specific instruction is out of scope; that belongs to the
not-yet-built stage 11+. Gemini is used only for the qualitative judgments explicitly called out
below (podcast/clip/explanation necessity, podcast dialogue text); every taxonomy value, score, and
Integrity Check result is decided by code.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from research.db import connect
from research.gemini_client import GeminiClient
from research.script_writer import _FORMAT_LEAKAGE_PATTERNS
from research.topic_candidates import _content_words

# ---------------------------------------------------------------------------
# Fixed taxonomies
# ---------------------------------------------------------------------------

FORMATS = {"EDUCATION", "CLIP_ANALYSIS", "HYBRID", "PODCAST"}
FORMAT_CONFIDENCE_LEVELS = {"low", "medium", "high"}
CLIP_DEPENDENCY_LEVELS = {"none", "optional", "required"}
CLIP_ROLES = {"HOOK", "EVIDENCE", "ANALYSIS_TARGET", "EXAMPLE", "PRACTICE", "REPLAY"}
CLIP_GRADES = {"STRONG", "GOOD", "USABLE", "WEAK"}

READY_FOR_PRODUCTION_PLANNING_SCORE_THRESHOLD = 0  # Integrity Gate decides; score is diagnostic only.

DEFAULT_CLIP_SCORE_WEIGHTS = {
    "learning_match": 0.30,
    "phenomenon_clarity": 0.25,
    "replay_value": 0.20,
    "context_independence": 0.15,
    "audio_usability": 0.10,
}
DEFAULT_CLIP_GRADE_THRESHOLDS = {"strong": 85, "good": 70, "usable": 55}
_GRADE_RANK = {"STRONG": 3, "GOOD": 2, "USABLE": 1, "WEAK": 0}

_AFFINITY_SCORE = {"low": 20.0, "medium": 50.0, "high": 85.0}

_PRODUCTION_INTENT_MAP = {
    "PROBLEM_RECOGNITION": "establish_viewer_problem",
    "CORE_EXPLANATION": "explain_core_principle",
    "DEMONSTRATION": "demonstrate_principle_in_action",
    "REINFORCEMENT": "reinforce_principle_with_variation",
    "CONTRAST": "highlight_name_vs_sound_contrast",
    "TRANSFER": "transfer_principle_to_new_example",
    "PRACTICE": "guided_practice",
    "MINI_SUCCESS": "viewer_must_attempt_before_answer",
    "RECAP": "summarize_key_principle",
    "RESOLUTION": "resolve_opening_question",
    "OTHER": "support_learning_flow",
}

_CLIP_ROLE_MAP = {
    "PROBLEM_RECOGNITION": "HOOK",
    "CONTRAST": "EVIDENCE",
    "CORE_EXPLANATION": "ANALYSIS_TARGET",
    "DEMONSTRATION": "ANALYSIS_TARGET",
    "REINFORCEMENT": "EXAMPLE",
    "TRANSFER": "EXAMPLE",
    "PRACTICE": "PRACTICE",
    "MINI_SUCCESS": "PRACTICE",
    "RECAP": "REPLAY",
    "RESOLUTION": "REPLAY",
    "OTHER": "EXAMPLE",
}


def production_intent_for(learning_function: str) -> str:
    return _PRODUCTION_INTENT_MAP.get(learning_function, _PRODUCTION_INTENT_MAP["OTHER"])


def classify_clip_role(learning_function: str) -> str:
    return _CLIP_ROLE_MAP.get(learning_function, "EXAMPLE")


# ---------------------------------------------------------------------------
# Source loading (read-only)
# ---------------------------------------------------------------------------

def select_target_script(db_path: Path, script_id: int | None = None) -> dict | None:
    with connect(db_path) as conn:
        if script_id is not None:
            row = conn.execute("SELECT * FROM video_scripts WHERE id = ?", (script_id,)).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM video_scripts WHERE ready_for_direction = 1 ORDER BY generated_at DESC LIMIT 1"
            ).fetchone()
    return dict(row) if row else None


def _load_content_blocks(row: dict) -> list[dict]:
    try:
        return json.loads(row.get("content_blocks_json") or "[]")
    except (TypeError, ValueError):
        return []


# ---------------------------------------------------------------------------
# 10A: Format Director
# ---------------------------------------------------------------------------

_FORMAT_GATE_PROMPT = """너는 YouTube 채널 "{channel_name}"의 Video Director다.

아래 Content Script는 "무엇을 가르칠지"가 이미 확정되어 있다. 너의 역할은 포맷 이름을 직접 고르는
것이 아니라, 아래 3가지 질문에 예/아니오와 근거만 답하는 것이다. 최종 포맷 결정은 코드가 한다.

Title: {title}
Viewer Problem: {viewer_problem}
Core Question: {core_question}

Content Block 요약 (learning_function / media_affinity):
{block_summary}

질문 1 (Podcast Necessity): 이 콘텐츠의 핵심 가치가 설명/시연보다 두 사람의 자연스러운 대화를
따라가며 경험·조언·사례·공감·발견을 얻는 데 있는가? 단순히 대화형 표현이 가능하다는 이유만으로
yes라고 하지 마라 -- 습관/학습 여정/공감 같은 성격의 콘텐츠에서만 강하게 yes다.

질문 2 (Authentic Evidence Necessity): 실제 원어민/영화/실제 발화 Clip을 경험하지 않으면 Viewer
Problem의 핵심을 제대로 체감하기 어려운가? 예: "왜 Did you가 디쥬처럼 들릴까" 같은 실제 발화 자체가
학습 증거인 경우만 강하게 yes다. 원리/규칙을 예시 단어로 설명하는 콘텐츠는 보통 no다.

질문 3 (Explanation Necessity): 질문 2가 yes라면, Clip 경험과 별개로 체계적인 원리 설명/시각화도
똑같이 중요한가? (yes면 Clip과 설명이 함께 필요, no면 Clip 분석 자체가 중심)

아래 JSON 형식으로만 답하라:
{{
  "podcast_necessity": true|false,
  "podcast_reason": "...",
  "clip_necessity": true|false,
  "clip_reason": "...",
  "explanation_necessity": true|false,
  "explanation_reason": "..."
}}
"""


def _block_summary_for_prompt(content_blocks: list[dict]) -> str:
    lines = []
    for b in content_blocks:
        affinity = b.get("media_affinity") or {}
        signals = ", ".join(f"{k}={v}" for k, v in affinity.items())
        lines.append(f"- {b.get('content_block_id')} [{b.get('learning_function')}]: {signals}")
    return "\n".join(lines)


def _fallback_format_gates(content_blocks: list[dict]) -> dict:
    """Deterministic fallback used only when Gemini is unavailable/fails. media_affinity averages
    are explicitly NOT the primary decision method (spec section 4) -- this is a conservative
    secondary path that leans toward EDUCATION whenever the signal isn't clearly strong."""
    def _avg(key: str) -> float:
        values = [_AFFINITY_SCORE.get((b.get("media_affinity") or {}).get(key), 50.0) for b in content_blocks]
        return sum(values) / len(values) if values else 50.0

    dialogue_signal = (_avg("dialogue") + _avg("storytelling")) / 2
    clip_signal = (_avg("real_world_clip") + _avg("replay")) / 2
    education_signal = (_avg("visualization") + _avg("comparison") + _avg("interaction") + _avg("audio_demonstration")) / 4

    return {
        "podcast_necessity": dialogue_signal >= 70 and dialogue_signal > clip_signal and dialogue_signal > education_signal,
        "podcast_reason": f"fallback: dialogue/storytelling 평균 {dialogue_signal:.0f}",
        "clip_necessity": clip_signal >= 60,
        "clip_reason": f"fallback: real_world_clip/replay 평균 {clip_signal:.0f}",
        "explanation_necessity": education_signal >= 50,
        "explanation_reason": f"fallback: education 신호 평균 {education_signal:.0f}",
    }


def decide_format(
    content_blocks: list[dict], script_row: dict, gemini: GeminiClient | None, channel_cfg: dict,
    max_output_tokens: int = 6000,
) -> dict:
    gates = None
    generation_method = "fallback"
    if gemini and gemini.available:
        prompt = _FORMAT_GATE_PROMPT.format(
            channel_name=channel_cfg.get("name", ""),
            title=script_row.get("title", ""),
            viewer_problem=script_row.get("viewer_problem", ""),
            core_question=script_row.get("core_question", ""),
            block_summary=_block_summary_for_prompt(content_blocks),
        )
        result = gemini.generate_json(prompt, max_output_tokens=max_output_tokens)
        if isinstance(result, dict) and "podcast_necessity" in result and "clip_necessity" in result:
            gates = result
            generation_method = "gemini"

    if gates is None:
        gates = _fallback_format_gates(content_blocks)

    reasons = []
    if gates.get("podcast_necessity"):
        preferred = "PODCAST"
        clip_dependency = "none"
        confidence = "high" if generation_method == "gemini" else "low"
        reasons.append({"gate": "podcast_necessity", "signal": True, "reasoning": str(gates.get("podcast_reason") or "")})
    elif gates.get("clip_necessity"):
        reasons.append({"gate": "clip_necessity", "signal": True, "reasoning": str(gates.get("clip_reason") or "")})
        if gates.get("explanation_necessity"):
            preferred = "HYBRID"
            reasons.append({"gate": "explanation_necessity", "signal": True, "reasoning": str(gates.get("explanation_reason") or "")})
        else:
            preferred = "CLIP_ANALYSIS"
            reasons.append({"gate": "explanation_necessity", "signal": False, "reasoning": str(gates.get("explanation_reason") or "")})
        clip_dependency = "required"
        confidence = "high" if generation_method == "gemini" else "low"
    else:
        preferred = "EDUCATION"
        clip_dependency = "none"
        confidence = "high" if generation_method == "gemini" else "medium"
        reasons.append({"gate": "podcast_necessity", "signal": False, "reasoning": str(gates.get("podcast_reason") or "")})
        reasons.append({"gate": "clip_necessity", "signal": False, "reasoning": str(gates.get("clip_reason") or "")})
        reasons.append({"gate": "default", "signal": True, "reasoning": "Podcast/Clip 필요성이 강하지 않아 EDUCATION을 기본값으로 적용"})

    if preferred not in FORMATS:
        preferred = "EDUCATION"
    if confidence not in FORMAT_CONFIDENCE_LEVELS:
        confidence = "low"
    if clip_dependency not in CLIP_DEPENDENCY_LEVELS:
        clip_dependency = "none"

    return {
        "preferred_format": preferred,
        "format_confidence": confidence,
        "format_reason": reasons,
        "clip_dependency": clip_dependency,
        "generation_method": generation_method,
    }


# ---------------------------------------------------------------------------
# 10B: Source Clip Analyzer
#
# No ASR/transcript-extraction infrastructure exists in this project, and this stage does not
# build one ("없는 인프라를 가짜로 구현하지 않는다"). transcript_segments is an INPUT INTERFACE --
# a list of {"start": float, "end": float, "text": str, "audio_quality": float | None, "source_ref":
# str | None} dicts assumed to already exist (e.g. produced by a future ASR/asset-prep stage, or
# supplied via `research direction --transcript-json PATH`). Everything downstream of that input
# (candidate generation, scoring, boundary math, role classification) is fully implemented.
# ---------------------------------------------------------------------------

def _block_match_words(content_block: dict) -> set:
    text = str(content_block.get("base_narration") or "")
    return _content_words(text)


def _required_content_words(content_block: dict) -> set:
    text = " ".join(str(x) for x in content_block.get("required_content") or [])
    return _content_words(text)


def _segment_is_valid(segment: dict) -> bool:
    start, end = segment.get("start"), segment.get("end")
    return isinstance(start, (int, float)) and isinstance(end, (int, float)) and start >= 0 and end > start


def _replay_value_score(duration: float, ideal_range: list) -> float:
    lo, hi = ideal_range[0], ideal_range[1]
    if duration <= 0:
        return 0.0
    if lo <= duration <= hi:
        return 100.0
    if duration < lo:
        return max(0.0, 100.0 * (duration / lo))
    overflow = duration - hi
    return max(20.0, 100.0 - overflow * 8.0)


_DANGLING_STARTS = ("그래서", "그리고", "근데", "이거", "그거", "저거", "이게", "그게")


def _context_independence_score(text: str) -> float:
    text = text.strip()
    if not text:
        return 0.0
    score = 100.0
    if text.startswith(_DANGLING_STARTS):
        score -= 40.0
    if not text.endswith((".", "!", "?", '"', "”")):
        score -= 20.0
    return max(0.0, score)


def compute_clip_score(sub_scores: dict, weights: dict = DEFAULT_CLIP_SCORE_WEIGHTS) -> float:
    total = sum(weights[k] * sub_scores[k] for k in weights)
    return round(max(0.0, min(100.0, total)), 1)


def grade_for_score(score: float, thresholds: dict = DEFAULT_CLIP_GRADE_THRESHOLDS) -> str:
    if score >= thresholds["strong"]:
        return "STRONG"
    if score >= thresholds["good"]:
        return "GOOD"
    if score >= thresholds["usable"]:
        return "USABLE"
    return "WEAK"


def compute_clip_boundary(segment: dict, padding_seconds: float, source_duration: float | None = None) -> dict:
    focus_in, focus_out = float(segment["start"]), float(segment["end"])
    if source_duration is not None:
        focus_out = min(focus_out, source_duration)
    context_in = max(0.0, focus_in - padding_seconds)
    context_out = focus_out + padding_seconds
    if source_duration is not None:
        context_out = min(context_out, source_duration)
    # Boundary math must never let focus escape context, regardless of clamping above.
    context_in = min(context_in, focus_in)
    context_out = max(context_out, focus_out)
    return {"focus_in": focus_in, "focus_out": focus_out, "context_in": context_in, "context_out": context_out}


def generate_clip_candidates(content_block: dict, transcript_segments: list[dict], clip_config: dict) -> list[dict]:
    weights = clip_config.get("weights", DEFAULT_CLIP_SCORE_WEIGHTS)
    thresholds = clip_config.get("grade_thresholds", DEFAULT_CLIP_GRADE_THRESHOLDS)
    min_learning_match = clip_config.get("min_learning_match_to_keep", 10)
    replay_ideal = clip_config.get("replay_ideal_seconds", [2, 6])
    neutral_audio = clip_config.get("neutral_audio_quality", 65)
    padding = clip_config.get("context_padding_seconds", 2.0)

    block_words = _block_match_words(content_block)
    required_words = _required_content_words(content_block)
    role = classify_clip_role(content_block.get("learning_function", "OTHER"))

    candidates = []
    for segment in transcript_segments or []:
        if not _segment_is_valid(segment):
            continue  # hard fail: invalid/negative timestamp

        text = str(segment.get("text") or "")
        segment_words = _content_words(text)
        learning_match = (
            100 * len(block_words & segment_words) / len(block_words | segment_words)
            if (block_words and segment_words) else 0.0
        )
        if learning_match < min_learning_match:
            continue  # hard fail: can't identify the target utterance for this block

        phenomenon_clarity = (
            100 * len(required_words & segment_words) / len(required_words | segment_words)
            if (required_words and segment_words) else 50.0
        )
        duration = float(segment["end"]) - float(segment["start"])
        replay_value = _replay_value_score(duration, replay_ideal)
        context_independence = _context_independence_score(text)
        audio_usability = segment.get("audio_quality")
        if not isinstance(audio_usability, (int, float)):
            audio_usability = neutral_audio

        sub_scores = {
            "learning_match": learning_match,
            "phenomenon_clarity": phenomenon_clarity,
            "replay_value": replay_value,
            "context_independence": context_independence,
            "audio_usability": audio_usability,
        }
        score = compute_clip_score(sub_scores, weights)
        boundary = compute_clip_boundary(segment, padding, segment.get("source_duration"))

        candidates.append({
            "source_ref": segment.get("source_ref"),
            "transcript": text,
            **boundary,
            **sub_scores,
            "clip_score": score,
            "clip_grade": grade_for_score(score, thresholds),
            "clip_role": role,
            "confidence": "medium",
            "selected": False,
        })
    return candidates


def select_best_clip(candidates: list[dict]) -> dict | None:
    if not candidates:
        return None
    best = max(candidates, key=lambda c: (_GRADE_RANK.get(c["clip_grade"], 0), c["clip_score"]))
    best["selected"] = True
    return best


def analyze_clips_for_blocks(content_blocks: list[dict], transcript_segments: list[dict], clip_config: dict) -> dict:
    results = {}
    for block in content_blocks:
        if not block.get("direction_eligible", True):
            continue
        candidates = generate_clip_candidates(block, transcript_segments, clip_config)
        results[block["content_block_id"]] = {"candidates": candidates, "selected": select_best_clip(candidates)}
    return results


# ---------------------------------------------------------------------------
# 10C: Final Director (spec section 13, Case A-E, pure function)
# ---------------------------------------------------------------------------

_USABLE_GRADES = {"STRONG", "GOOD", "USABLE"}
_STRONG_OR_GOOD = {"STRONG", "GOOD"}


def decide_final_format(preferred_format: str, clip_dependency: str, block_clip_results: dict, transcript_provided: bool) -> dict:
    if preferred_format not in {"CLIP_ANALYSIS", "HYBRID"}:
        return {
            "final_format": preferred_format,
            "fallback_format": None,
            "final_format_status": "resolved",
            "per_block_delivery_mode": {},
        }

    if clip_dependency == "required" and not transcript_provided:
        return {
            "final_format": "EDUCATION",
            "fallback_format": preferred_format,
            "final_format_status": "pending_source_analysis",
            "per_block_delivery_mode": {},
        }

    selected_grades = {
        block_id: (result.get("selected") or {}).get("clip_grade")
        for block_id, result in (block_clip_results or {}).items()
    }
    usable = {bid for bid, grade in selected_grades.items() if grade in _USABLE_GRADES}
    strong_or_good = {bid for bid, grade in selected_grades.items() if grade in _STRONG_OR_GOOD}

    if preferred_format == "CLIP_ANALYSIS":
        if strong_or_good:
            per_block = {bid: ("CLIP_ANALYSIS" if bid in usable else "EDUCATION") for bid in selected_grades}
            return {"final_format": "CLIP_ANALYSIS", "fallback_format": None, "final_format_status": "resolved", "per_block_delivery_mode": per_block}
        if usable:
            # Only USABLE-grade clips exist -- don't force CLIP_ANALYSIS (spec Case C), re-judge toward HYBRID.
            per_block = {bid: ("CLIP_ANALYSIS" if bid in usable else "EDUCATION") for bid in selected_grades}
            return {"final_format": "HYBRID", "fallback_format": "EDUCATION", "final_format_status": "resolved", "per_block_delivery_mode": per_block}
        return {"final_format": "EDUCATION", "fallback_format": "CLIP_ANALYSIS", "final_format_status": "resolved", "per_block_delivery_mode": {}}

    # HYBRID
    if usable:
        per_block = {bid: ("CLIP_ANALYSIS" if bid in usable else "EDUCATION") for bid in selected_grades}
        return {"final_format": "HYBRID", "fallback_format": None, "final_format_status": "resolved", "per_block_delivery_mode": per_block}
    return {"final_format": "EDUCATION", "fallback_format": "HYBRID", "final_format_status": "resolved", "per_block_delivery_mode": {}}


# ---------------------------------------------------------------------------
# 10D: Block Director
# ---------------------------------------------------------------------------

def _viewer_interaction(block: dict) -> dict:
    action = block.get("viewer_action")
    return {
        "type": "READ_BEFORE_REVEAL" if action else "NONE",
        "viewer_action": action,
        "thinking_time_seconds": block.get("thinking_time_seconds", 0),
        "reveal_before_attempt": False if action else None,
    }


def _audio_requirement(block: dict) -> dict:
    level = (block.get("media_affinity") or {}).get("audio_demonstration", "medium")
    return {"audio_demonstration_level": level, "target_pronunciation_required": level in {"medium", "high"}}


_VISUAL_PHONEME_FUNCTIONS = {"CORE_EXPLANATION", "DEMONSTRATION", "REINFORCEMENT", "TRANSFER", "MINI_SUCCESS"}


def _visual_requirement(block: dict) -> dict:
    level = (block.get("media_affinity") or {}).get("visualization", "medium")
    phoneme_required = level in {"medium", "high"} and block.get("learning_function") in _VISUAL_PHONEME_FUNCTIONS
    return {"visualization_level": level, "phoneme_sequence_required": phoneme_required}


def build_block_direction(block: dict, delivery_mode: str, clip_result: dict | None = None) -> dict:
    clip_requirement = {"needed": False}
    if delivery_mode == "CLIP_ANALYSIS" and clip_result and clip_result.get("selected"):
        selected = clip_result["selected"]
        clip_requirement = {
            "needed": True,
            "clip_role": selected["clip_role"],
            "clip_grade": selected["clip_grade"],
            "focus_in": selected["focus_in"],
            "focus_out": selected["focus_out"],
            "context_in": selected["context_in"],
            "context_out": selected["context_out"],
        }
    return {
        "content_block_id": block["content_block_id"],
        "delivery_mode": delivery_mode,
        "production_intent": production_intent_for(block.get("learning_function", "OTHER")),
        "required_content": list(block.get("required_content") or []),
        "viewer_interaction": _viewer_interaction(block),
        "audio_requirement": _audio_requirement(block),
        "visual_requirement": _visual_requirement(block),
        "clip_requirement": clip_requirement,
        "retention_role": block.get("retention_intent") or {"type": "open_loop", "purpose": ""},
    }


def build_all_block_directions(content_blocks: list[dict], final_format: str, per_block_delivery_mode: dict, block_clip_results: dict) -> list[dict]:
    directions = []
    for block in content_blocks:
        if not block.get("direction_eligible", True):
            continue
        block_id = block["content_block_id"]
        if final_format in {"CLIP_ANALYSIS", "HYBRID"} and block_id in per_block_delivery_mode:
            delivery_mode = per_block_delivery_mode[block_id]
        else:
            delivery_mode = "EDUCATION"
        clip_result = (block_clip_results or {}).get(block_id)
        directions.append(build_block_direction(block, delivery_mode, clip_result))
    return directions


# ---------------------------------------------------------------------------
# PODCAST Direction (isolated production grammar -- spec section 20)
# ---------------------------------------------------------------------------

_PODCAST_PROMPT = """너는 한국 팟캐스트 "{channel_name}"의 Dialogue Director다.

아래 Content Block들은 이미 확정된 교육 내용이다. 절대 새로 만들거나 바꾸지 마라. 너의 역할은 이
내용을 두 진행자의 자연스러운 대화(Dialogue Beat)로 옮기는 것뿐이다.

Host A: 학습자 시점, 궁금해하는 역할
Host B: 설명하는 역할, 경험 많음

카메라 지시, 화면 배치, 편집 지시, 색상, 애니메이션은 절대 만들지 마라 -- 오직 대화 텍스트만
만들어라. 각 Content Block마다 최소 1개의 Dialogue Beat를 만들어라.

Content Blocks:
{blocks_json}

아래 JSON 형식으로만 답하라:
{{
  "speakers": [{{"id": "host_a", "role": "learner-facing"}}, {{"id": "host_b", "role": "explanatory"}}],
  "dialogue_beats": [
    {{"content_block_id": "CB01", "speaker": "host_a", "text": "..."}}
  ]
}}
"""

_DEFAULT_SPEAKERS = [{"id": "host_a", "role": "learner-facing"}, {"id": "host_b", "role": "explanatory"}]


def _fallback_podcast_direction(content_blocks: list[dict]) -> dict:
    beats = []
    for i, block in enumerate(content_blocks):
        if not block.get("direction_eligible", True):
            continue
        speaker = "host_a" if i % 2 == 0 else "host_b"
        beats.append({
            "content_block_id": block["content_block_id"], "speaker": speaker,
            "text": str(block.get("base_narration") or ""),
        })
    return {"speakers": list(_DEFAULT_SPEAKERS), "dialogue_beats": beats}


def _sanitize_podcast_direction(raw: dict) -> dict:
    speakers = raw.get("speakers") or list(_DEFAULT_SPEAKERS)
    beats = [b for b in (raw.get("dialogue_beats") or []) if isinstance(b, dict) and b.get("text")]
    return {"speakers": speakers, "dialogue_beats": beats}


def build_podcast_direction(content_blocks: list[dict], channel_cfg: dict, gemini: GeminiClient | None, max_output_tokens: int = 6000) -> dict:
    result = None
    generation_method = "fallback"
    if gemini and gemini.available:
        blocks_json = json.dumps(
            [
                {
                    "content_block_id": b["content_block_id"], "learning_function": b.get("learning_function"),
                    "purpose": b.get("purpose"), "base_narration": b.get("base_narration"),
                }
                for b in content_blocks if b.get("direction_eligible", True)
            ],
            ensure_ascii=False,
        )
        prompt = _PODCAST_PROMPT.format(channel_name=channel_cfg.get("name", ""), blocks_json=blocks_json)
        raw = gemini.generate_json(prompt, max_output_tokens=max_output_tokens)
        if isinstance(raw, dict) and raw.get("dialogue_beats"):
            result = raw
            generation_method = "gemini"

    if result is None:
        result = _fallback_podcast_direction(content_blocks)

    sanitized = _sanitize_podcast_direction(result)
    sanitized["generation_method"] = generation_method
    return sanitized


def check_podcast_isolation_safe(final_format: str, podcast_direction: dict | None, block_directions: list[dict]) -> str:
    if final_format == "PODCAST":
        return "fail" if block_directions else "pass"
    return "fail" if podcast_direction else "pass"


# ---------------------------------------------------------------------------
# Integrity Check (13 items, spec section 28) + Ready Gate
# ---------------------------------------------------------------------------

def check_no_renderer_instruction(block_directions: list[dict], podcast_direction: dict | None) -> str:
    texts = [str(bd.get("production_intent") or "") for bd in block_directions]
    if podcast_direction:
        texts.extend(str(beat.get("text") or "") for beat in podcast_direction.get("dialogue_beats") or [])
    blob = " ".join(texts)
    return "fail" if any(p in blob for p in _FORMAT_LEAKAGE_PATTERNS) else "pass"


def run_direction_integrity_check(
    content_blocks: list[dict], format_result: dict, final_result: dict,
    block_directions: list[dict], podcast_direction: dict | None, block_clip_results: dict,
    source_script_unchanged: bool,
) -> dict:
    checks = {}

    checks["valid_format"] = "pass" if (
        format_result["preferred_format"] in FORMATS
        and final_result["final_format"] in FORMATS
        and format_result["format_confidence"] in FORMAT_CONFIDENCE_LEVELS
        and format_result["clip_dependency"] in CLIP_DEPENDENCY_LEVELS
    ) else "fail"

    eligible_ids = {b["content_block_id"] for b in content_blocks if b.get("direction_eligible", True)}
    if final_result["final_format"] == "PODCAST":
        covered_ids = {beat.get("content_block_id") for beat in (podcast_direction or {}).get("dialogue_beats") or [] if beat.get("content_block_id")}
    else:
        covered_ids = {bd["content_block_id"] for bd in block_directions}
    checks["content_blocks_preserved"] = "pass" if eligible_ids.issubset(covered_ids) else "fail"

    block_by_id = {b["content_block_id"]: b for b in content_blocks}

    lost_required_content = any(
        block_by_id[bd["content_block_id"]].get("required_content") and not bd.get("required_content")
        for bd in block_directions if bd["content_block_id"] in block_by_id
    )
    checks["required_content_preserved"] = "fail" if lost_required_content else "pass"

    lost_viewer_action = any(
        block_by_id[bd["content_block_id"]].get("viewer_action") and not bd["viewer_interaction"].get("viewer_action")
        for bd in block_directions if bd["content_block_id"] in block_by_id
    )
    checks["viewer_action_preserved"] = "fail" if lost_viewer_action else "pass"

    lost_thinking_time = any(
        (block_by_id[bd["content_block_id"]].get("thinking_time_seconds") or 0) > 0
        and bd["viewer_interaction"].get("thinking_time_seconds") != block_by_id[bd["content_block_id"]].get("thinking_time_seconds")
        for bd in block_directions if bd["content_block_id"] in block_by_id
    )
    checks["thinking_time_preserved"] = "fail" if lost_thinking_time else "pass"

    lost_retention = any(
        block_by_id[bd["content_block_id"]].get("retention_intent") != bd.get("retention_role")
        for bd in block_directions if bd["content_block_id"] in block_by_id
    )
    checks["retention_intent_preserved"] = "fail" if lost_retention else "pass"

    final_format = final_result["final_format"]
    clip_dependency = format_result["clip_dependency"]
    if final_format == "EDUCATION" and clip_dependency == "required" and final_result.get("final_format_status") != "pending_source_analysis":
        clip_consistent = False
    elif final_format == "CLIP_ANALYSIS" and clip_dependency == "none":
        clip_consistent = False
    else:
        clip_consistent = True
    checks["clip_dependency_consistent"] = "pass" if clip_consistent else "fail"

    boundary_ok = True
    for result in (block_clip_results or {}).values():
        for c in result.get("candidates") or []:
            if not (c["context_in"] <= c["focus_in"] <= c["focus_out"] <= c["context_out"]):
                boundary_ok = False
            if c["focus_in"] < 0 or c["context_in"] < 0:
                boundary_ok = False
    checks["clip_boundary_safe"] = "pass" if boundary_ok else "fail"

    forced_weak = False
    if final_format in {"CLIP_ANALYSIS", "HYBRID"}:
        for block_id, mode in (final_result.get("per_block_delivery_mode") or {}).items():
            if mode == "CLIP_ANALYSIS":
                selected = ((block_clip_results or {}).get(block_id) or {}).get("selected")
                if not selected or selected.get("clip_grade") == "WEAK":
                    forced_weak = True
    checks["weak_clip_not_forced"] = "fail" if forced_weak else "pass"

    # A Clip fallback (WEAK/absent Clip -> EDUCATION) must never drop the block itself -- already
    # verified by content_blocks_preserved, re-checked here specifically for fallback scenarios.
    checks["fallback_preserves_learning"] = checks["content_blocks_preserved"]

    checks["podcast_isolation_safe"] = check_podcast_isolation_safe(final_format, podcast_direction, block_directions)
    checks["no_renderer_instruction"] = check_no_renderer_instruction(block_directions, podcast_direction)
    checks["source_script_unchanged"] = "pass" if source_script_unchanged else "fail"

    return checks


def ready_for_production_planning_gate(checks: dict) -> bool:
    return not any(status == "fail" for status in checks.values())


# ---------------------------------------------------------------------------
# Director Score (diagnostic only -- never overrides the Integrity Gate)
# ---------------------------------------------------------------------------

_CONFIDENCE_SCORE = {"high": 100.0, "medium": 60.0, "low": 30.0}


def compute_director_score(format_result: dict, block_directions: list[dict], block_clip_results: dict) -> float:
    confidence_score = _CONFIDENCE_SCORE.get(format_result["format_confidence"], 50.0)
    coverage_score = 100.0 if block_directions or format_result["preferred_format"] == "PODCAST" else 0.0
    clip_scores = [
        (result.get("selected") or {}).get("clip_score")
        for result in (block_clip_results or {}).values() if result.get("selected")
    ]
    clip_quality_score = sum(clip_scores) / len(clip_scores) if clip_scores else 100.0
    return round(confidence_score * 0.4 + coverage_score * 0.3 + clip_quality_score * 0.3, 1)


# ---------------------------------------------------------------------------
# Orchestration + persistence + report
# ---------------------------------------------------------------------------

def build_direction(
    db_path: Path, gemini: GeminiClient | None, channel_cfg: dict, clip_config: dict, *,
    script_id: int | None = None, transcript_segments: list[dict] | None = None,
    max_output_tokens: int = 6000,
) -> dict:
    row = select_target_script(db_path, script_id=script_id)
    if row is None:
        raise ValueError("No video_scripts row with ready_for_direction=1 (or no such script_id). Run `research script` first.")

    content_blocks = _load_content_blocks(row)

    format_result = decide_format(content_blocks, row, gemini, channel_cfg, max_output_tokens=max_output_tokens)

    transcript_provided = transcript_segments is not None
    block_clip_results: dict = {}
    if format_result["preferred_format"] in {"CLIP_ANALYSIS", "HYBRID"} and transcript_provided:
        block_clip_results = analyze_clips_for_blocks(content_blocks, transcript_segments, clip_config)

    final_result = decide_final_format(format_result["preferred_format"], format_result["clip_dependency"], block_clip_results, transcript_provided)

    podcast_direction = None
    block_directions: list[dict] = []
    generation_method = format_result["generation_method"]
    if final_result["final_format"] == "PODCAST":
        podcast_direction = build_podcast_direction(content_blocks, channel_cfg, gemini, max_output_tokens=max_output_tokens)
        if podcast_direction.get("generation_method") == "fallback":
            generation_method = "fallback"
    else:
        block_directions = build_all_block_directions(content_blocks, final_result["final_format"], final_result["per_block_delivery_mode"], block_clip_results)

    with connect(db_path) as conn:
        after_row = conn.execute(
            "SELECT content_blocks_json, script_json FROM video_scripts WHERE id = ?", (row["id"],)
        ).fetchone()
    source_unchanged = (
        after_row is not None
        and after_row["content_blocks_json"] == row.get("content_blocks_json")
        and after_row["script_json"] == row.get("script_json")
    )

    checks = run_direction_integrity_check(
        content_blocks, format_result, final_result, block_directions, podcast_direction,
        block_clip_results, source_unchanged,
    )
    ready = ready_for_production_planning_gate(checks)

    director_score = compute_director_score(format_result, block_directions, block_clip_results)

    return {
        "script_row": row,
        "content_blocks": content_blocks,
        "format_result": format_result,
        "final_result": final_result,
        "block_clip_results": block_clip_results,
        "block_directions": block_directions,
        "podcast_direction": podcast_direction,
        "integrity_checks": checks,
        "ready_for_production_planning": ready,
        "director_score": director_score,
        "generation_method": generation_method,
        "transcript_provided": transcript_provided,
    }


def _persist(db_path: Path, result: dict, report_path: str) -> int:
    row = result["script_row"]
    format_result = result["format_result"]
    final_result = result["final_result"]

    with connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO video_directions (report_path, video_script_id, preferred_format, final_format,
                format_confidence, format_reason_json, clip_dependency, fallback_format,
                final_format_status, director_score, integrity_json, ready_for_production_planning,
                generation_method, podcast_direction_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report_path, row["id"], format_result["preferred_format"], final_result["final_format"],
                format_result["format_confidence"], json.dumps(format_result["format_reason"], ensure_ascii=False),
                format_result["clip_dependency"], final_result.get("fallback_format"),
                final_result["final_format_status"], result["director_score"],
                json.dumps(result["integrity_checks"], ensure_ascii=False),
                1 if result["ready_for_production_planning"] else 0, result["generation_method"],
                json.dumps(result["podcast_direction"], ensure_ascii=False) if result["podcast_direction"] else None,
            ),
        )
        video_direction_id = cur.lastrowid

        for bd in result["block_directions"]:
            conn.execute(
                """
                INSERT INTO block_directions (video_direction_id, content_block_id, delivery_mode,
                    production_intent, viewer_interaction_json, audio_requirement_json,
                    visual_requirement_json, clip_requirement_json, retention_role_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    video_direction_id, bd["content_block_id"], bd["delivery_mode"], bd["production_intent"],
                    json.dumps(bd["viewer_interaction"], ensure_ascii=False),
                    json.dumps(bd["audio_requirement"], ensure_ascii=False),
                    json.dumps(bd["visual_requirement"], ensure_ascii=False),
                    json.dumps(bd["clip_requirement"], ensure_ascii=False),
                    json.dumps(bd["retention_role"], ensure_ascii=False),
                ),
            )

        for block_id, clip_result in (result["block_clip_results"] or {}).items():
            for candidate in clip_result.get("candidates") or []:
                conn.execute(
                    """
                    INSERT INTO source_clip_candidates (video_direction_id, content_block_id, source_ref,
                        transcript, focus_in, focus_out, context_in, context_out, learning_match,
                        phenomenon_clarity, replay_value, context_independence, audio_usability,
                        clip_score, clip_grade, clip_role, confidence, selected)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        video_direction_id, block_id, candidate.get("source_ref"), candidate.get("transcript"),
                        candidate["focus_in"], candidate["focus_out"], candidate["context_in"], candidate["context_out"],
                        candidate["learning_match"], candidate["phenomenon_clarity"], candidate["replay_value"],
                        candidate["context_independence"], candidate["audio_usability"], candidate["clip_score"],
                        candidate["clip_grade"], candidate["clip_role"], candidate.get("confidence"),
                        1 if candidate.get("selected") else 0,
                    ),
                )

    return video_direction_id


def _fmt(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)


def build_video_direction_report(
    db_path: Path, reports_dir: Path, gemini: GeminiClient | None, channel_cfg: dict, clip_config: dict, *,
    script_id: int | None = None, transcript_segments: list[dict] | None = None, max_output_tokens: int = 6000,
) -> Path:
    result = build_direction(
        db_path, gemini, channel_cfg, clip_config, script_id=script_id,
        transcript_segments=transcript_segments, max_output_tokens=max_output_tokens,
    )
    row = result["script_row"]
    format_result = result["format_result"]
    final_result = result["final_result"]

    lines: list[str] = []
    lines.append("# Video Director Report")
    lines.append("")
    lines.append(f"생성일: {date.today().isoformat()}")
    lines.append(f"Generation Method: {result['generation_method']}")
    lines.append("")

    lines.append("## 1. Source Content Script")
    lines.append("")
    lines.append(f"video_scripts.id: {row['id']}")
    lines.append(f"Title: {row.get('title')}")
    lines.append(f"Viewer Problem: {row.get('viewer_problem')}")
    lines.append(f"Core Question: {row.get('core_question')}")
    lines.append("")

    lines.append("## 2. Format Decision")
    lines.append("")
    lines.append(f"Preferred Format: {format_result['preferred_format']}")
    lines.append(f"Final Format: {final_result['final_format']}")
    lines.append(f"Format Confidence: {format_result['format_confidence']}")
    lines.append("")

    lines.append("## 3. Format Reason")
    lines.append("")
    for reason in format_result["format_reason"]:
        lines.append(f"- [{reason['gate']}] signal={reason['signal']}: {reason['reasoning']}")
    lines.append("")

    lines.append("## 4. Clip Dependency")
    lines.append("")
    lines.append(format_result["clip_dependency"])
    lines.append("")

    lines.append("## 5. Fallback Format")
    lines.append("")
    lines.append(_fmt(final_result.get("fallback_format")))
    lines.append(f"final_format_status: {final_result['final_format_status']}")
    lines.append("")

    lines.append("## 6. Content Block Direction Table")
    lines.append("")
    if final_result["final_format"] == "PODCAST":
        lines.append("(PODCAST 포맷 -- Content Block Direction 대신 12. Podcast Direction 참고)")
    else:
        for bd in result["block_directions"]:
            lines.append(f"### {bd['content_block_id']}")
            lines.append(f"- delivery_mode: {bd['delivery_mode']}")
            lines.append(f"- production_intent: {bd['production_intent']}")
            lines.append(f"- clip_requirement: {bd['clip_requirement']}")
    lines.append("")

    lines.append("## 7. Viewer Interaction Plan")
    lines.append("")
    for bd in result["block_directions"]:
        vi = bd["viewer_interaction"]
        if vi.get("type") != "NONE":
            lines.append(f"- {bd['content_block_id']}: {vi['type']}, thinking_time={vi['thinking_time_seconds']}s, action=\"{vi['viewer_action']}\"")
    lines.append("")

    lines.append("## 8. Retention Translation")
    lines.append("")
    for bd in result["block_directions"]:
        lines.append(f"- {bd['content_block_id']}: {bd['retention_role']}")
    lines.append("")

    lines.append("## 9. Clip Analysis Result")
    lines.append("")
    if result["block_clip_results"]:
        for block_id, clip_result in result["block_clip_results"].items():
            selected = clip_result.get("selected")
            lines.append(f"- {block_id}: {len(clip_result.get('candidates') or [])}개 후보, selected={selected['clip_grade'] if selected else 'none'}")
    else:
        lines.append("(Clip 분석 미수행 -- transcript 입력 없음 또는 Clip이 필요 없는 포맷)")
    lines.append("")

    lines.append("## 10. Clip Candidates")
    lines.append("")
    for block_id, clip_result in (result["block_clip_results"] or {}).items():
        for c in clip_result.get("candidates") or []:
            marker = " (selected)" if c.get("selected") else ""
            lines.append(f"- {block_id}: [{c['clip_grade']}] score={_fmt(c['clip_score'])} focus=({_fmt(c['focus_in'])}, {_fmt(c['focus_out'])}){marker}")
    lines.append("")

    lines.append("## 11. Fallback Decisions")
    lines.append("")
    lines.append(f"preferred={format_result['preferred_format']} -> final={final_result['final_format']}"
                  + (f" (fallback_format={final_result['fallback_format']})" if final_result.get("fallback_format") else ""))
    lines.append("")

    lines.append("## 12. Podcast Direction")
    lines.append("")
    if result["podcast_direction"]:
        pd = result["podcast_direction"]
        lines.append(f"Speakers: {pd['speakers']}")
        for beat in pd["dialogue_beats"]:
            lines.append(f"- [{beat['content_block_id']}] {beat['speaker']}: {beat['text']}")
    else:
        lines.append("(해당 없음)")
    lines.append("")

    lines.append("## 13. Integrity Check")
    lines.append("")
    for check, status in result["integrity_checks"].items():
        lines.append(f"- {check}: {status}")
    lines.append("")

    lines.append("## 14. Ready for Production Planning")
    lines.append("")
    lines.append("YES" if result["ready_for_production_planning"] else "NO")
    lines.append(f"Director Score (참고용): {_fmt(result['director_score'])}")
    lines.append("")

    lines.append("## 15. Known Limitations")
    lines.append("")
    lines.append("- Source Clip Analyzer는 입력 인터페이스 + scoring + boundary 로직만 구현되어 있다. "
                  "실제 ASR/transcript 추출 인프라는 이 프로젝트에 없으며, `--transcript-json`으로 "
                  "이미 추출된 transcript segment를 공급받는다는 전제로 동작한다.")
    lines.append("- audio_usability는 세그먼트에 audio_quality가 없으면 중립값을 사용한다 -- 실제 "
                  "오디오 품질 분석은 미구현이다.")
    lines.append("")

    reports_dir.mkdir(parents=True, exist_ok=True)
    out_path = reports_dir / f"video_direction_{date.today().isoformat()}.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")

    _persist(db_path, result, str(out_path))

    return out_path
