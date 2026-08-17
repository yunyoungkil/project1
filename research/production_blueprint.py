"""Turns one 07-selected Title x Thumbnail Package into a production-ready video design: what the
video must deliver on (Viewer Contract), the single question/answer it proves, its scope, a
graduated example ladder, a hook, a 5-8 section structure, retention/visual design, Shorts
extraction points, and a Content Integrity Check that gates ready_for_script. Full script writing
is the next stage's job. Gemini writes the design content in one call; every score and every
verifiable Integrity Check item is decided by code, not by Gemini.
"""
from __future__ import annotations

import json
import math
import re
from datetime import date
from pathlib import Path

from research.db import connect
from research.gemini_client import GeminiClient
from research.topic_candidates import _content_words

# ---------------------------------------------------------------------------
# Fixed taxonomies (sections 13, 16, 19, 8)
# ---------------------------------------------------------------------------

HOOK_TYPES = {
    "immediate_question", "misconception", "before_after", "quiz", "surprising_example",
    "demonstration", "result_preview", "problem_reenactment",
}

RETENTION_DEVICES = {
    "open_loop", "quiz", "prediction", "contrast", "new_example", "visual_change",
    "mini_success", "misconception_correction", "next_question",
}

VISUAL_TYPES = {
    "word_focus", "letter_highlight", "sound_build", "comparison", "quiz_card", "rule_card", "recap_card",
}

PREREQUISITE_LEVELS = {"none", "very_beginner", "beginner", "intermediate"}


def _log_normalize(value: float, cap: float) -> float:
    if value is None or value <= 0:
        return 0.0
    return max(0.0, min(100.0, 100 * math.log1p(value) / math.log1p(cap)))


# ---------------------------------------------------------------------------
# Section 2: target package selection
# ---------------------------------------------------------------------------

def select_target_package(db_path: Path, package_id: int | None = None) -> dict | None:
    with connect(db_path) as conn:
        if package_id is not None:
            row = conn.execute("SELECT * FROM content_packages WHERE id = ?", (package_id,)).fetchone()
        else:
            row = conn.execute(
                """
                SELECT * FROM content_packages
                WHERE selected_for_production = 1
                  AND generated_at = (SELECT MAX(generated_at) FROM content_packages WHERE selected_for_production = 1)
                ORDER BY package_score DESC
                LIMIT 1
                """
            ).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Gemini generation
# ---------------------------------------------------------------------------

_BLUEPRINT_PROMPT = """너는 한국 YouTube 채널 "{channel_name}"의 영상 설계자다.

채널 정보:
- 핵심 시청자: {audience}
- 철학: {philosophy}

다음 확정된 Title x Thumbnail Package를 실제 제작 가능한 영상 설계로 바꿔라.

Title: {title}
Thumbnail: {thumbnail_text}
Topic(시청자 문제): {topic_text}
핵심 예시 단어(썸네일에서 사용, 있으면 본문에서 반드시 다뤄야 함): {example_word}

중요 원칙:
- 영상의 출발점은 "가르치고 싶은 지식"이 아니라 Title/Thumbnail이 시청자에게 한 약속이다.
- 한 영상에 하나의 core_question과 하나의 core_answer만 만든다.
- learning_objectives는 1~3개로 제한한다.
- 예시는 쉬운 것 -> 원리 확인 -> 작은 응용 -> 새 단어 도전 순서(4레벨)로 설계한다.
- 정의부터 길게 설명하지 않는다. 사례를 먼저 보여주고 용어를 나중에 붙인다.
- 이 채널에서 실제로 촬영 가능한 단순 자막/텍스트 중심 설계를 우선한다 (복잡한 촬영/유명인 얼굴 불필요).
- 영상이 실제로 보장할 수 없는 결과를 viewer_contract에 넣지 않는다.

발음 정확성 원칙 (중요):
- 정확성의 기준은 항상 영어 음소(예: /g/, /k/, /b/, /p/, /d/, /t/)이며, 한국어 발음 표기는 왕초보
  이해를 돕는 보조 수단일 뿐 정확성의 기준이 아니다.
- 단어를 "단어(한글)" 또는 "단어 = 한글"처럼 하나의 한글 표기로 고정해서 소리를 완전히 대신하지
  마라. 특히 /g/-/k/, /b/-/p/, /d/-/t/처럼 헷갈리기 쉬운 종성 소리를 한글 표기가 지워버리게 하지
  마라. 예시(sound blending)를 설명할 때는 "B /b/ + A /æ/ + G /g/ → BAG"처럼 음소 조합을 먼저
  보여주고, 필요하면 "BAG의 끝소리는 /g/입니다"처럼 음소를 명시한 보조 설명만 덧붙인다.
- 같은 단어에 대해 서로 다른 한글 표기를 "/"로 동시에 제시하지 마라 (예: "BAT(배트/뱃)" 금지).
- 특정 글자의 소리를 설명할 때는 반드시 현재 예시 단어 "안에서만" 한정해서 말하라 (예: "CAP에서는
  C가 /k/ 소리를 냅니다"). "C의 소리는 'ㅋ'"처럼 모든 단어에 적용되는 일반 규칙처럼 말하지 마라.
- example_ladder의 exception_risk는 단어가 낯설다는 이유만으로 올리지 마라. 그 글자 조합이 이번에
  가르치는 규칙 안에서 실제로 예외를 포함하는 경우에만 medium/high로 표시한다.
- core_answer를 포함해 어디에서도 "각 글자가 내는 고유한 소리", "알파벳마다 정해진 소리가 있다"
  처럼 글자마다 하나의 고정된 소리가 있다고 암시하는 표현을 쓰지 마라. 대신 "이 단어에서 나타내는
  소리", "오늘 다루는 단어에서 글자가 나타내는 소리"처럼 지금 다루는 예시로 범위를 한정하라.

Promise 범위 원칙 (중요):
- viewer_contract의 video_promise/expected_transformation은 learning_objectives와 scope_in이
  다루는 범위를 넘어서는 약속을 하지 마라. 예를 들어 scope가 "단모음 A"로 한정되어 있으면 "모든
  단모음", "어떤 단어든", "완벽하게", "무조건" 같은 과잉 일반화 표현을 쓰지 마라.
{continuity_note}
hook_type은 반드시 다음 중에서: {hook_types}
retention_device는 반드시 다음 중에서 (section마다 최대 1개, 억지로 만들지 말 것): {retention_devices}
visual_type은 반드시 다음 중에서: {visual_types}
prerequisite_level은 반드시 다음 중에서: {prerequisite_levels}

아래 JSON 형식으로만 답하라:

{{
  "viewer_contract": {{
    "viewer_problem": "...", "click_expectation": "...", "video_promise": "...", "expected_transformation": "..."
  }},
  "core_question": "...",
  "core_answer": "...",
  "learning_objectives": ["...", "..."],
  "prerequisite_level": "...",
  "scope_in": ["...", "..."],
  "scope_out": ["...", "..."],
  "example_ladder": [
    {{"level": 1, "word": "...", "target_pattern": "...", "purpose": "...", "difficulty": "easy", "exception_risk": "low"}},
    {{"level": 2, "word": "...", "target_pattern": "...", "purpose": "...", "difficulty": "easy", "exception_risk": "low"}},
    {{"level": 3, "word": "...", "target_pattern": "...", "purpose": "...", "difficulty": "medium", "exception_risk": "low"}},
    {{"level": 4, "word": "...", "target_pattern": "...", "purpose": "...", "difficulty": "medium", "exception_risk": "medium"}}
  ],
  "hook": {{
    "primary_hook_type": "...", "secondary_hook_type": "... 또는 null",
    "opening_line": "0~5초 문제 재현 대사", "gap_line": "5~15초 예상과 실제 차이", "promise_line": "15~30초 오늘 얻을 결과"
  }},
  "sections": [
    {{"section_number": 1, "section_goal": "...", "viewer_question": "...", "key_point": "...", "example": "...",
      "estimated_duration": "약 30초", "retention_device": "...", "visual_type": "..."}}
  ],
  "mini_success": {{"description": "...", "prompt_word": "...", "think_seconds": 3}},
  "audio_visual": {{"overall_audio_dependency": "low|medium|high", "overall_visual_dependency": "low|medium|high",
    "notes": "..."}},
  "shorts_candidates": [
    {{"hook": "...", "question": "...", "example": "...", "payoff": "...", "source_section": 1, "estimated_duration": "약 30초"}}
  ],
  "natural_next_topics": ["...", "..."],
  "external_clip_needed": false,
  "clip_purpose": null,
  "promise_feasibility_self_assessment": "strong|acceptable|risky",
  "promise_risk_reason": "... 또는 null",
  "brand_design_fit_self_assessment": "high|medium|low",
  "brand_fit_reason": "...",
  "integrity_jargon_before_explained": "pass|warning|fail",
  "integrity_examples_match_rule": "pass|warning|fail"
}}

sections는 5~8개를 만들어라. 최소 5개 이상이어야 한다.
"""


def _fallback_blueprint(package: dict) -> dict:
    """Used only if Gemini is unavailable/fails -- a minimal but structurally valid blueprint so
    the pipeline never crashes. Content is generic and should be reviewed before scripting."""
    topic = package["topic_text"]
    title = package["title"]
    example_word = package.get("example_word") or "예시 단어"
    return {
        "viewer_contract": {
            "viewer_problem": topic,
            "click_expectation": f"{title} - 이 질문에 대한 답을 알고 싶다.",
            "video_promise": f"{topic}에 대한 원리를 이해하게 된다.",
            "expected_transformation": "영상 전: 막연함 / 영상 후: 원리를 이해하고 스스로 적용 가능",
        },
        "core_question": title,
        "core_answer": f"{topic}에 대한 핵심 원리를 단계별로 설명한다.",
        "learning_objectives": [f"{topic}의 핵심 원리를 설명할 수 있다."],
        "prerequisite_level": "very_beginner",
        "scope_in": [topic],
        "scope_out": ["심화 예외 사례"],
        "example_ladder": [
            {"level": i, "word": example_word, "target_pattern": "기본 패턴", "purpose": "원리 확인",
             "difficulty": "easy" if i <= 2 else "medium", "exception_risk": "low" if i <= 3 else "medium"}
            for i in range(1, 5)
        ],
        "hook": {
            "primary_hook_type": "problem_reenactment", "secondary_hook_type": None,
            "opening_line": f"{title}", "gap_line": "많은 분들이 놓치는 부분이 있습니다.",
            "promise_line": "오늘 그 이유를 알려드립니다.",
        },
        "sections": [
            {"section_number": i, "section_goal": f"단계 {i}", "viewer_question": topic,
             "key_point": "핵심 원리", "example": example_word, "estimated_duration": "약 1분",
             "retention_device": "open_loop" if i == 1 else "new_example", "visual_type": "word_focus"}
            for i in range(1, 6)
        ],
        "mini_success": {"description": "새 단어를 스스로 읽어보게 한다.", "prompt_word": example_word, "think_seconds": 3},
        "audio_visual": {"overall_audio_dependency": "medium", "overall_visual_dependency": "medium", "notes": "폴백 설계"},
        "shorts_candidates": [
            {"hook": title, "question": topic, "example": example_word, "payoff": "핵심 원리 30초 요약",
             "source_section": 1, "estimated_duration": "약 30초"}
        ],
        "natural_next_topics": [],
        "external_clip_needed": False,
        "clip_purpose": None,
        "promise_feasibility_self_assessment": "acceptable",
        "promise_risk_reason": "Gemini 미사용 - 최소 폴백 설계이므로 검토 필요",
        "brand_design_fit_self_assessment": "medium",
        "brand_fit_reason": "Gemini 미사용 - 최소 폴백 설계",
        "integrity_jargon_before_explained": "warning",
        "integrity_examples_match_rule": "warning",
    }


def generate_blueprint_content(
    package: dict,
    gemini: GeminiClient | None,
    channel_cfg: dict,
    max_output_tokens: int = 6000,
    previous_example_words: list[str] | None = None,
) -> dict:
    result = None
    if gemini and gemini.available:
        if previous_example_words:
            continuity_note = (
                "\n연속성 원칙 (중요):\n"
                f"- 이 Package는 이전에 이미 한 번 설계된 적이 있고, 그때 사용한 Example Ladder 단어는 "
                f"{' -> '.join(previous_example_words)} 였다. 특별한 교육적 이유가 없는 한 이 단어 구성과 "
                "순서를 그대로 유지하라. 단, 발음 설명 방식(음소 표기, 스코프 제한 등 위 원칙들)은 이번 "
                "지침에 맞게 반드시 새로 교정하라.\n"
            )
        else:
            continuity_note = ""
        prompt = _BLUEPRINT_PROMPT.format(
            channel_name=channel_cfg.get("name", ""),
            audience=channel_cfg.get("audience", ""),
            philosophy=channel_cfg.get("philosophy", ""),
            title=package["title"],
            thumbnail_text=package["thumbnail_text"],
            topic_text=package["topic_text"],
            example_word=package.get("example_word") or "(없음)",
            continuity_note=continuity_note,
            hook_types=", ".join(sorted(HOOK_TYPES)),
            retention_devices=", ".join(sorted(RETENTION_DEVICES)),
            visual_types=", ".join(sorted(VISUAL_TYPES)),
            prerequisite_levels=", ".join(sorted(PREREQUISITE_LEVELS)),
        )
        result = gemini.generate_json(prompt, max_output_tokens=max_output_tokens)

    if not isinstance(result, dict) or not result.get("core_question") or not result.get("sections"):
        result = _fallback_blueprint(package)

    return _sanitize_blueprint(result)


def _sanitize_blueprint(raw: dict) -> dict:
    """Enforces every fixed taxonomy and count limit -- Gemini's raw output never reaches the
    rest of the pipeline unvalidated."""
    hook = raw.get("hook") or {}
    if hook.get("primary_hook_type") not in HOOK_TYPES:
        hook["primary_hook_type"] = "problem_reenactment"
    if hook.get("secondary_hook_type") not in HOOK_TYPES:
        hook["secondary_hook_type"] = None
    raw["hook"] = hook

    sections = raw.get("sections") or []
    for s in sections:
        if s.get("retention_device") not in RETENTION_DEVICES:
            s["retention_device"] = None
        if s.get("visual_type") not in VISUAL_TYPES:
            s["visual_type"] = "word_focus"
    if len(sections) < 5:
        for i in range(len(sections) + 1, 6):
            sections.append(
                {"section_number": i, "section_goal": "추가 설명", "viewer_question": "",
                 "key_point": "", "example": "", "estimated_duration": "약 30초",
                 "retention_device": None, "visual_type": "word_focus"}
            )
    raw["sections"] = sections[:8]

    objectives = raw.get("learning_objectives") or []
    raw["learning_objectives"] = objectives[:3] or ["핵심 원리를 설명할 수 있다."]

    if raw.get("prerequisite_level") not in PREREQUISITE_LEVELS:
        raw["prerequisite_level"] = "very_beginner"

    shorts = raw.get("shorts_candidates") or []
    raw["shorts_candidates"] = shorts if shorts else [
        {"hook": raw.get("core_question", ""), "question": raw.get("core_question", ""), "example": "",
         "payoff": raw.get("core_answer", ""), "source_section": 1, "estimated_duration": "약 30초"}
    ]

    example_ladder = raw.get("example_ladder") or []
    raw["example_ladder"] = example_ladder

    if raw.get("promise_feasibility_self_assessment") not in {"strong", "acceptable", "risky"}:
        raw["promise_feasibility_self_assessment"] = "acceptable"
    if raw.get("brand_design_fit_self_assessment") not in {"high", "medium", "low"}:
        raw["brand_design_fit_self_assessment"] = "medium"
    for key in ("integrity_jargon_before_explained", "integrity_examples_match_rule"):
        if raw.get(key) not in {"pass", "warning", "fail"}:
            raw[key] = "warning"

    return raw


# ---------------------------------------------------------------------------
# Section 5: promise feasibility backstop
# ---------------------------------------------------------------------------

def verify_promise_feasibility(package: dict, blueprint: dict) -> tuple[str, str | None]:
    claimed = blueprint.get("promise_feasibility_self_assessment", "acceptable")
    reason = blueprint.get("promise_risk_reason")

    example_word = package.get("example_word")
    example_covered = True
    if example_word:
        ladder_text = " ".join(str(e.get("word", "")) for e in blueprint.get("example_ladder") or [])
        example_covered = example_word.lower() in ladder_text.lower()

    title_words = _content_words(package["title"]) | _content_words(blueprint.get("core_question", ""))
    answer_words = _content_words(blueprint.get("core_answer", ""))
    answer_addresses_title = bool(title_words & answer_words) if title_words and answer_words else False

    if not example_covered and not answer_addresses_title:
        return "risky", (reason or "") + " [자동 강등: 썸네일 예시 단어가 example ladder에 없고, core_answer가 제목/질문과 단어 겹침이 없음]"

    return claimed, reason


# ---------------------------------------------------------------------------
# 08-1: phoneme accuracy / scope-discipline backstops
#
# Korean transliteration is only an aid for beginners -- English phonemes (/g/, /k/, /b/, /p/,
# /d/, /t/, ...) are the accuracy standard. These checks catch the two concrete failure modes
# found in the first real run: (a) a single fixed Hangul syllable silently erasing a
# voiced/voiceless contrast (e.g. "BAG = 백" hides /g/ vs /k/), or two conflicting Hangul
# readings offered at once (e.g. "BAT(배트/뱃)"); (b) a single letter's sound stated as if it
# were a universal rule ("C의 소리는 'ㅋ'") instead of scoped to the current example.
# ---------------------------------------------------------------------------

_RISKY_FINAL_LETTER_PHONEMES = {"G": "g", "K": "k", "B": "b", "P": "p", "D": "d", "T": "t"}

_DUAL_READING_RE = re.compile(r"[A-Z]{2,}\([가-힣]+/[가-힣]+\)")
# A fixed Hangul<->word equivalence, in either order ("BAG(백)"/"BAG = 백" or "백(BAG)"/"백 = BAG").
# Hangul syllable blocks only (가-힣) -- deliberately excludes compatibility jamo (ㄱ-ㅎ/ㅏ-ㅣ)
# used in IPA-style notation like "(/ㄱ/)", which is exactly the safe form we want to allow.
_FIXED_EQUIVALENCE_RE = re.compile(
    r"([A-Z]{2,})\s*(?:\(([가-힣]+)\)|=\s*([가-힣]+))"
    r"|([가-힣]+)\s*(?:\(([A-Z]{2,})\)|=\s*([A-Z]{2,}))"
)
_LETTER_SOUND_CLAIM_RE = re.compile(r"[A-Za-z]\s*의\s*소리는")
# 09-1: the same generalization can also show up as "B는 단어 안에서 /b/ 소리를 냅니다" or
# "C는 /k/ 소리를 냅니다" -- a letter + particle followed (within a short gap) by an IPA slash and
# "소리", with no "~의 소리는" wording at all.
_LETTER_SOUND_IPA_CLAIM_RE = re.compile(r"\b[A-Za-z]\s*(?:는|은|가|이)\b[^./!?\n]{0,20}/[^/]+/\s*소리")
# A claim only counts as properly scoped if "에서" is anchored to an actual example word (or an
# explicit "이 단어"/"오늘 예시"/"오늘 배운" phrase) right before it -- not just any "에서" anywhere
# in the sentence. This is what "단어 안에서" (a generic, unscoped "에서") used to slip past.
_SCOPE_PREFIX = r"(?:[A-Z]{2,}(?:\s*[와과]\s*[A-Z]{2,})?|이\s*단어(?:\s*[A-Z]{2,})?|오늘\s*예시|오늘\s*배운|이\s*예시)"
# 09-3: "의" (possessive: "BAT의 끝소리는 /t/") is just as valid a scoping anchor as "에서" (in/at)
# -- both explicitly tie the claim to one named word rather than stating it as a bare rule. "은/는/
# 이/가/이다" are deliberately excluded: "CAP이다" only asserts an equality/conclusion, it doesn't
# scope the *sound claim itself* to CAP.
_SCOPED_CONTEXT_RE = re.compile(_SCOPE_PREFIX + r"\s*(?:에서|의)")

# 09-3: a softer variant of the same "letter = fixed sound" generalization, without naming any
# specific letter or IPA at all -- "각 글자가 내는 고유한 소리", "알파벳마다 정해진 소리가 있다".
# This implies every letter has one permanent sound, which the channel's Scope (a handful of CVC
# examples) never claims. Scoping here is looser than _SCOPED_CONTEXT_RE (spec's own GOOD example
# "오늘 다루는 단어에서" doesn't match the strict word+에서 anchor), so any explicit "this
# word/today/here/now" cue or a named example word is accepted.
_GENERIC_LETTER_SOUND_RE = re.compile(r"(글자|알파벳)[^.!?\n]{0,10}(고유한|정해진)\s*소리")
_SOFT_SCOPE_SIGNALS = ("이 단어", "오늘", "지금", "여기서")
_EXAMPLE_WORD_TOKEN_RE = re.compile(r"[A-Z]{2,}")

_OVERGENERALIZATION_KEYWORDS = ("모든", "항상", "어떤 단어든", "완벽하게", "무조건", "전부")


def _blueprint_text_items(blueprint: dict) -> list[str]:
    """Per-item text chunks (not one giant blob) so a nearby phoneme marker or scoping word is
    checked in the same sentence/entry it belongs to, not borrowed from somewhere else."""
    items: list[str] = []
    # 09-3: Core Answer was previously outside every check's scan range, which is exactly how
    # "각 글자가 내는 고유한 소리" (letter = fixed sound) slipped through undetected.
    core_answer = blueprint.get("core_answer")
    if core_answer:
        items.append(str(core_answer))
    for e in blueprint.get("example_ladder") or []:
        items.append(" ".join(str(e.get(k, "")) for k in ("word", "target_pattern", "purpose")))
    for s in blueprint.get("sections") or []:
        items.append(" ".join(str(s.get(k, "")) for k in ("section_goal", "viewer_question", "key_point", "example")))
    for sc in blueprint.get("shorts_candidates") or []:
        items.append(" ".join(str(sc.get(k, "")) for k in ("hook", "question", "example", "payoff")))
    hook = blueprint.get("hook") or {}
    items.append(" ".join(str(hook.get(k, "")) for k in ("opening_line", "gap_line", "promise_line")))
    mini = blueprint.get("mini_success") or {}
    items.append(str(mini.get("description", "")))
    return items


def _phoneme_safe_over_texts(texts: list[str]) -> str:
    """Low-level check reused by both the Blueprint (08) and Script (09) stages: same phoneme-
    accuracy principle, different text source."""
    status = "pass"
    for text in texts:
        if _DUAL_READING_RE.search(text):
            return "fail"
        for match in _FIXED_EQUIVALENCE_RE.finditer(text):
            word = match.group(1) or match.group(5) or match.group(6)
            if not word:
                continue
            last_letter = word[-1]
            phoneme = _RISKY_FINAL_LETTER_PHONEMES.get(last_letter)
            if phoneme and f"/{phoneme}/" not in text:
                status = "fail"
    return status


def _scope_safe_over_texts(texts: list[str]) -> str:
    """Low-level check reused by both the Blueprint (08) and Script (09/09-3) stages.

    The scoping requirement ("BAG에서"/"이 단어"/etc.) is checked against the whole item a
    sentence came from, not just that one sentence. 09-3's real output showed why: a natural
    explanation like "BAG에서 소리를 살펴봅니다. 이 단어에서 B는 /b/ 소리를 냅니다. 가운데 A는
    /æ/ 소리를 냅니다." establishes scope once and continues across several sentences within the
    same section -- requiring every single sentence to re-name the word would flag normal writing.
    Cross-item leakage (one section's scoping satisfying an unrelated section's claim) is what
    the per-item boundary here still prevents.
    """
    status = "pass"
    for text in texts:
        sentences = re.split(r"[.!?\n]", text)
        for sentence in sentences:
            triggered = _LETTER_SOUND_CLAIM_RE.search(sentence) or _LETTER_SOUND_IPA_CLAIM_RE.search(sentence)
            if triggered and not _SCOPED_CONTEXT_RE.search(text):
                return "fail"
            if _GENERIC_LETTER_SOUND_RE.search(sentence):
                scoped = any(sig in text for sig in _SOFT_SCOPE_SIGNALS) or bool(_EXAMPLE_WORD_TOKEN_RE.search(text))
                if not scoped:
                    return "fail"
    return status


def _scope_safe_over_text_blob(text_blob: str) -> str:
    """Back-compat wrapper -- treats the whole blob as a single item."""
    return _scope_safe_over_texts([text_blob])


def check_phoneme_explanation_safe(blueprint: dict) -> str:
    return _phoneme_safe_over_texts(_blueprint_text_items(blueprint))


def check_example_scope_safe(blueprint: dict) -> str:
    return _scope_safe_over_texts(_blueprint_text_items(blueprint))


def check_promise_matches_scope(blueprint: dict) -> str:
    contract = blueprint.get("viewer_contract") or {}
    promise_text = f"{contract.get('video_promise', '')} {contract.get('expected_transformation', '')}"
    if any(kw in promise_text for kw in _OVERGENERALIZATION_KEYWORDS):
        return "fail"
    scope_words = _content_words(" ".join(blueprint.get("scope_in") or [])) | _content_words(
        " ".join(blueprint.get("learning_objectives") or [])
    )
    promise_words = _content_words(promise_text)
    if scope_words and promise_words and not (scope_words & promise_words):
        return "warning"
    return "pass"


# ---------------------------------------------------------------------------
# Section 23: Content Integrity Check (deterministic where verifiable)
# ---------------------------------------------------------------------------

def run_integrity_check(package: dict, blueprint: dict) -> dict:
    checks = {}

    core_answer = blueprint.get("core_answer", "")
    title_words = _content_words(package["title"]) | _content_words(blueprint.get("core_question", ""))
    answer_words = _content_words(core_answer)
    checks["answers_title_question"] = "pass" if core_answer and (title_words & answer_words) else (
        "warning" if core_answer else "fail"
    )

    example_word = package.get("example_word")
    if example_word:
        ladder_text = " ".join(str(e.get("word", "")) for e in blueprint.get("example_ladder") or [])
        section_text = " ".join(str(s.get("example", "")) for s in blueprint.get("sections") or [])
        covered = example_word.lower() in (ladder_text + " " + section_text).lower()
        checks["thumbnail_example_covered"] = "pass" if covered else "fail"
    else:
        checks["thumbnail_example_covered"] = "pass"  # nothing promised, nothing to break

    checks["jargon_introduced_after_example"] = blueprint.get("integrity_jargon_before_explained", "warning")

    objectives = blueprint.get("learning_objectives") or []
    scope_in = blueprint.get("scope_in") or []
    checks["not_overloaded"] = "pass" if len(objectives) <= 3 and len(scope_in) <= 6 else "warning"

    checks["examples_match_rule"] = blueprint.get("integrity_examples_match_rule", "warning")

    early_levels = [e for e in (blueprint.get("example_ladder") or []) if e.get("level", 0) <= 3]
    high_risk_early = any(e.get("exception_risk") == "high" for e in early_levels)
    checks["no_exception_taught_as_rule"] = "fail" if high_risk_early else "pass"

    mini_success = blueprint.get("mini_success")
    checks["has_hands_on_moment"] = "pass" if mini_success and mini_success.get("description") else "fail"

    sections = blueprint.get("sections") or []
    last_section = sections[-1] if sections else {}
    recap_signal = any(
        kw in str(last_section.get("section_goal", "")) or kw in str(last_section.get("key_point", ""))
        for kw in ("정리", "복습", "요약", "recap")
    )
    checks["resolves_opening_question"] = "pass" if recap_signal or last_section.get("retention_device") == "next_question" else "warning"

    checks["phoneme_explanation_safe"] = check_phoneme_explanation_safe(blueprint)
    checks["example_scope_safe"] = check_example_scope_safe(blueprint)
    checks["promise_matches_scope"] = check_promise_matches_scope(blueprint)

    return checks


def ready_for_script(integrity_checks: dict) -> bool:
    return not any(status == "fail" for status in integrity_checks.values())


# ---------------------------------------------------------------------------
# Section 24: production complexity
# ---------------------------------------------------------------------------

def estimate_production_complexity(blueprint: dict) -> str:
    sections = blueprint.get("sections") or []
    example_cards = len(blueprint.get("example_ladder") or [])
    shorts = len(blueprint.get("shorts_candidates") or [])
    external_clip = bool(blueprint.get("external_clip_needed"))

    score = len(sections) + example_cards + shorts + (3 if external_clip else 0)
    if score <= 10:
        return "low"
    if score <= 16:
        return "medium"
    return "high"


# ---------------------------------------------------------------------------
# Section 26: Blueprint Score (pure function)
# ---------------------------------------------------------------------------

DEFAULT_BLUEPRINT_SCORE_WEIGHTS = {
    "viewer_contract": 0.25,
    "core_answer_clarity": 0.15,
    "example_ladder": 0.15,
    "mini_success": 0.10,
    "retention_structure": 0.10,
    "brand_fit": 0.10,
    "production_feasibility": 0.10,
    "shorts_expandability": 0.05,
}


def compute_blueprint_score(blueprint: dict, brand_design_fit: str, production_complexity: str, weights: dict = DEFAULT_BLUEPRINT_SCORE_WEIGHTS) -> float:
    contract = blueprint.get("viewer_contract") or {}
    contract_fields = ["viewer_problem", "click_expectation", "video_promise", "expected_transformation"]
    filled = sum(1 for f in contract_fields if contract.get(f))
    problem_words = _content_words(contract.get("viewer_problem", ""))
    promise_words = _content_words(contract.get("video_promise", ""))
    overlap_bonus = 20.0 if (problem_words & promise_words) else 0.0
    viewer_contract_score = min(100.0, (filled / len(contract_fields)) * 80 + overlap_bonus)

    core_answer = blueprint.get("core_answer", "")
    core_answer_score = 100.0 if len(_content_words(core_answer)) >= 4 else 50.0 if core_answer else 0.0

    ladder = blueprint.get("example_ladder") or []
    levels_present = len({e.get("level") for e in ladder if e.get("level")})
    low_risk_ratio = (
        sum(1 for e in ladder if e.get("exception_risk") == "low") / len(ladder) if ladder else 0.0
    )
    example_ladder_score = min(100.0, (levels_present / 4) * 70 + low_risk_ratio * 30)

    mini_success = blueprint.get("mini_success")
    mini_success_score = 100.0 if mini_success and mini_success.get("description") else 0.0

    sections = blueprint.get("sections") or []
    valid_devices = sum(1 for s in sections if s.get("retention_device") in RETENTION_DEVICES)
    retention_score = (valid_devices / len(sections)) * 100 if sections else 0.0

    brand_fit_score = {"high": 100.0, "medium": 60.0, "low": 20.0}.get(brand_design_fit, 60.0)
    feasibility_score = {"low": 100.0, "medium": 70.0, "high": 40.0}.get(production_complexity, 70.0)
    shorts_score = _log_normalize(len(blueprint.get("shorts_candidates") or []), cap=3)

    components = {
        "viewer_contract": viewer_contract_score,
        "core_answer_clarity": core_answer_score,
        "example_ladder": example_ladder_score,
        "mini_success": mini_success_score,
        "retention_structure": retention_score,
        "brand_fit": brand_fit_score,
        "production_feasibility": feasibility_score,
        "shorts_expandability": shorts_score,
    }
    score = sum(weights[k] * components[k] for k in weights)
    return max(0.0, min(100.0, score))


# ---------------------------------------------------------------------------
# Orchestration + report
# ---------------------------------------------------------------------------

def _fmt(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)


def _previous_example_words(db_path: Path, package_id: int | None) -> list[str] | None:
    """Words from the most recent prior blueprint for this same package, if any -- used to ask
    Gemini to keep the Example Ladder stable across a correction re-run instead of reshuffling it."""
    if package_id is None:
        return None
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT example_ladder_json FROM production_blueprints WHERE package_id = ? ORDER BY generated_at DESC LIMIT 1",
            (package_id,),
        ).fetchone()
    if not row or not row["example_ladder_json"]:
        return None
    try:
        ladder = json.loads(row["example_ladder_json"])
    except (TypeError, ValueError):
        return None
    words = [e.get("word") for e in ladder if e.get("word")]
    return words or None


def build_blueprint(db_path: Path, gemini: GeminiClient | None, channel_cfg: dict, *, package_id: int | None = None, max_output_tokens: int = 6000) -> dict:
    package = select_target_package(db_path, package_id=package_id)
    if package is None:
        raise ValueError("No content_packages row selected_for_production=1 (or no such package_id). Run `research packages` first.")

    previous_words = _previous_example_words(db_path, package.get("id"))
    blueprint = generate_blueprint_content(
        package, gemini, channel_cfg, max_output_tokens=max_output_tokens, previous_example_words=previous_words
    )
    feasibility, risk_reason = verify_promise_feasibility(package, blueprint)
    integrity = run_integrity_check(package, blueprint)
    complexity = estimate_production_complexity(blueprint)
    score = compute_blueprint_score(blueprint, blueprint["brand_design_fit_self_assessment"], complexity)

    return {
        "package": package,
        "blueprint": blueprint,
        "promise_feasibility": feasibility,
        "promise_risk_reason": risk_reason,
        "brand_design_fit": blueprint["brand_design_fit_self_assessment"],
        "brand_fit_reason": blueprint.get("brand_fit_reason"),
        "integrity_checks": integrity,
        "ready_for_script": ready_for_script(integrity),
        "production_complexity": complexity,
        "blueprint_score": score,
    }


def _persist(db_path: Path, result: dict, report_path: str) -> None:
    package = result["package"]
    blueprint = result["blueprint"]
    contract = blueprint.get("viewer_contract") or {}
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO production_blueprints (report_path, package_id, category, problem_id, title,
                thumbnail_text, viewer_problem, click_expectation, video_promise, expected_transformation,
                core_question, core_answer, learning_objectives_json, scope_in_json, scope_out_json,
                prerequisite_level, hook_json, sections_json, example_ladder_json, mini_success_json,
                audio_visual_json, shorts_candidates_json, natural_next_topics_json, external_clip_needed,
                clip_purpose, promise_feasibility, promise_risk_reason, brand_design_fit, brand_fit_reason,
                integrity_check_json, production_complexity, blueprint_score, ready_for_script)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report_path, package.get("id"), package["category"], package["problem_id"], package["title"],
                package["thumbnail_text"], contract.get("viewer_problem"), contract.get("click_expectation"),
                contract.get("video_promise"), contract.get("expected_transformation"),
                blueprint["core_question"], blueprint["core_answer"],
                json.dumps(blueprint["learning_objectives"], ensure_ascii=False),
                json.dumps(blueprint.get("scope_in") or [], ensure_ascii=False),
                json.dumps(blueprint.get("scope_out") or [], ensure_ascii=False),
                blueprint["prerequisite_level"],
                json.dumps(blueprint["hook"], ensure_ascii=False),
                json.dumps(blueprint["sections"], ensure_ascii=False),
                json.dumps(blueprint["example_ladder"], ensure_ascii=False),
                json.dumps(blueprint.get("mini_success"), ensure_ascii=False),
                json.dumps(blueprint.get("audio_visual"), ensure_ascii=False),
                json.dumps(blueprint["shorts_candidates"], ensure_ascii=False),
                json.dumps(blueprint.get("natural_next_topics") or [], ensure_ascii=False),
                1 if blueprint.get("external_clip_needed") else 0,
                blueprint.get("clip_purpose"),
                result["promise_feasibility"], result["promise_risk_reason"],
                result["brand_design_fit"], result["brand_fit_reason"],
                json.dumps(result["integrity_checks"], ensure_ascii=False),
                result["production_complexity"], result["blueprint_score"],
                1 if result["ready_for_script"] else 0,
            ),
        )


def build_production_blueprint_report(
    db_path: Path,
    reports_dir: Path,
    gemini: GeminiClient | None,
    channel_cfg: dict,
    *,
    package_id: int | None = None,
    max_output_tokens: int = 6000,
) -> Path:
    result = build_blueprint(db_path, gemini, channel_cfg, package_id=package_id, max_output_tokens=max_output_tokens)
    package = result["package"]
    blueprint = result["blueprint"]
    contract = blueprint.get("viewer_contract") or {}

    lines: list[str] = []
    lines.append("# YouTube Production Blueprint")
    lines.append("")
    lines.append(f"생성일: {date.today().isoformat()}")
    lines.append("")

    lines.append("## 1. 선택 Package")
    lines.append("")
    lines.append(f"Title: {package['title']}")
    lines.append(f"Thumbnail: {package['thumbnail_text']}")
    lines.append(f"Topic: {package['topic_text']}")
    lines.append(
        f"기존 점수 — Topic Candidate: {_fmt(package.get('topic_candidate_score'))} / "
        f"Click Evidence: {_fmt(package.get('click_evidence_score'))} / Package: {_fmt(package.get('package_score'))}"
    )
    lines.append("")

    lines.append("## 2. Viewer Contract")
    lines.append("")
    lines.append(f"Viewer Problem: {contract.get('viewer_problem')}")
    lines.append(f"Click Expectation: {contract.get('click_expectation')}")
    lines.append(f"Video Promise: {contract.get('video_promise')}")
    lines.append(f"Expected Transformation: {contract.get('expected_transformation')}")
    lines.append(f"Promise Feasibility: {result['promise_feasibility']}" + (f" ({result['promise_risk_reason']})" if result["promise_risk_reason"] else ""))
    lines.append("")

    lines.append("## 3. Core Question / Core Answer")
    lines.append("")
    lines.append(f"Core Question: {blueprint['core_question']}")
    lines.append(f"Core Answer: {blueprint['core_answer']}")
    lines.append("")

    lines.append("## 4. Learning Objectives")
    lines.append("")
    for i, obj in enumerate(blueprint["learning_objectives"], start=1):
        lines.append(f"{i}. {obj}")
    lines.append(f"Prerequisite Level: {blueprint['prerequisite_level']}")
    lines.append("")

    lines.append("## 5. Scope")
    lines.append("")
    lines.append("IN:")
    for item in blueprint.get("scope_in") or []:
        lines.append(f"- {item}")
    lines.append("OUT:")
    for item in blueprint.get("scope_out") or []:
        lines.append(f"- {item}")
    lines.append("")

    lines.append("## 6. Example Ladder")
    lines.append("")
    for e in blueprint["example_ladder"]:
        lines.append(
            f"Level {e.get('level')}: {e.get('word')} — {e.get('target_pattern')} "
            f"({e.get('purpose')}, difficulty={e.get('difficulty')}, exception_risk={e.get('exception_risk')})"
        )
    lines.append("")

    lines.append("## 7. Opening Hook")
    lines.append("")
    hook = blueprint["hook"]
    lines.append(f"Primary: {hook.get('primary_hook_type')} / Secondary: {hook.get('secondary_hook_type')}")
    lines.append(f"0~5초: {hook.get('opening_line')}")
    lines.append(f"5~15초: {hook.get('gap_line')}")
    lines.append(f"15~30초: {hook.get('promise_line')}")
    lines.append("(이것은 설계 예시이며 최종 대본은 아니다)")
    lines.append("")

    lines.append("## 8. Long-form Structure")
    lines.append("")
    for s in blueprint["sections"]:
        lines.append(f"### Section {s.get('section_number')}: {s.get('section_goal')}")
        lines.append(f"- 질문: {s.get('viewer_question')}")
        lines.append(f"- 핵심 내용: {s.get('key_point')}")
        lines.append(f"- 예시: {s.get('example')}")
        lines.append(f"- 예상 시간: {s.get('estimated_duration')}")
        lines.append(f"- Retention Device: {s.get('retention_device')}")
        lines.append(f"- Visual Type: {s.get('visual_type')}")
        lines.append("")

    lines.append("## 9. Mini Success Point")
    lines.append("")
    mini = blueprint.get("mini_success") or {}
    lines.append(f"{mini.get('description')} (예시: {mini.get('prompt_word')}, 생각 시간: {mini.get('think_seconds')}초)")
    lines.append("")

    lines.append("## 10. Audio-first / Visual Design")
    lines.append("")
    av = blueprint.get("audio_visual") or {}
    lines.append(f"Audio dependency: {av.get('overall_audio_dependency')} / Visual dependency: {av.get('overall_visual_dependency')}")
    lines.append(f"비고: {av.get('notes')}")
    lines.append("")

    lines.append("## 11. Shorts Candidates")
    lines.append("")
    for i, sc in enumerate(blueprint["shorts_candidates"], start=1):
        lines.append(f"### Shorts {i}")
        lines.append(f"- Hook: {sc.get('hook')}")
        lines.append(f"- Question: {sc.get('question')}")
        lines.append(f"- Example: {sc.get('example')}")
        lines.append(f"- Payoff: {sc.get('payoff')}")
        lines.append(f"- Source Section: {sc.get('source_section')} / 예상 시간: {sc.get('estimated_duration')}")
    lines.append("")

    lines.append("## 12. Natural Next Topics")
    lines.append("")
    for t in blueprint.get("natural_next_topics") or []:
        lines.append(f"- {t}")
    if not blueprint.get("natural_next_topics"):
        lines.append("- (없음)")
    lines.append("")

    lines.append("## 13. Content Integrity Check")
    lines.append("")
    for check, status in result["integrity_checks"].items():
        lines.append(f"- {check}: {status}")
    lines.append("")

    lines.append("## 14. Production Complexity")
    lines.append("")
    lines.append(result["production_complexity"])
    external = blueprint.get("external_clip_needed")
    if external:
        lines.append(f"external_clip_needed: true ({blueprint.get('clip_purpose')})")
    lines.append("")

    lines.append("## 15. Production Blueprint Score")
    lines.append("")
    lines.append(f"{_fmt(result['blueprint_score'])}/100 (참고용 — 이 점수만으로 제작 여부를 확정하지 않는다)")
    lines.append(f"Brand Design Fit: {result['brand_design_fit']}" + (f" ({result['brand_fit_reason']})" if result.get("brand_fit_reason") else ""))
    lines.append("")

    lines.append("## 16. Ready for Script")
    lines.append("")
    lines.append("YES" if result["ready_for_script"] else "NO")
    lines.append("")

    reports_dir.mkdir(parents=True, exist_ok=True)
    out_path = reports_dir / f"production_blueprint_{date.today().isoformat()}.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")

    _persist(db_path, result, str(out_path))

    return out_path
