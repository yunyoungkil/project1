"""Extracts title/content patterns for TOP videos. Rule-based flags always run (cheap, no
network); Gemini is used only to enrich with a short interpretive read (viewer_problem/hook/
promise/title_pattern) when available, and is skipped gracefully otherwise. We never copy
competitor titles -- only patterns are extracted."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from research.gemini_client import GeminiClient

_QUESTION_RE = re.compile(r"[?？]|왜|어떻게|무엇|어디서|언제")
_NEGATIVE_RE = re.compile(r"안\s?되|못\s?하|안\s?들|안\s?들리|말\s?못|실수|안\s?읽|못\s?읽|못\s?들")
_REASON_RE = re.compile(r"이유|때문|원인|왜")
_RESULT_RE = re.compile(r"방법|하는\s?법|공부법|팁|비법|끝|정리")
_NUMBER_RE = re.compile(r"\d+")
_FEAR_RE = re.compile(r"실수|틀릴까|망신|망함|하지\s?마|절대")

# Fixed taxonomy for title_pattern aggregation -- a free-form Gemini description makes almost
# every video its own unique "pattern", which makes the weekly report's frequency count useless.
ARCHETYPES: dict[str, str] = {
    "problem_reason": "문제 + 이유",
    "beginner_target": "왕초보/연령/특정 수준 타깃",
    "one_solution": "이것 하나면 끝 / 핵심 하나",
    "result_promise": "원하는 결과 약속",
    "roadmap": "단계/순서/로드맵",
    "time_saving": "시간 절약/빠른 결과",
    "contrarian": "기존 상식 반박/하지 마세요",
    "number_list": "숫자/몇 가지 방법",
    "curiosity_gap": "왜 그런지 궁금증 유발",
    "social_proof": "조회수/성공 사례/다른 사람의 검증",
    "other": "위 항목에 해당하지 않음",
}


@dataclass
class RulePatternFlags:
    is_question: bool
    is_negative: bool
    is_reason: bool
    is_result: bool
    is_number: bool
    is_fear_avoidance: bool


def analyze_title_rules(title: str) -> RulePatternFlags:
    title = title or ""
    return RulePatternFlags(
        is_question=bool(_QUESTION_RE.search(title)),
        is_negative=bool(_NEGATIVE_RE.search(title)),
        is_reason=bool(_REASON_RE.search(title)),
        is_result=bool(_RESULT_RE.search(title)),
        is_number=bool(_NUMBER_RE.search(title)),
        is_fear_avoidance=bool(_FEAR_RE.search(title)),
    )


def fallback_archetype(flags: RulePatternFlags) -> str:
    """A deterministic archetype guess from the cheap rule flags alone, used whenever Gemini is
    unavailable so archetype aggregation never goes empty."""
    if flags.is_number:
        return "number_list"
    if flags.is_fear_avoidance:
        return "contrarian"
    if flags.is_reason and flags.is_negative:
        return "problem_reason"
    if flags.is_question:
        return "curiosity_gap"
    if flags.is_result:
        return "one_solution"
    return "other"


@dataclass
class ContentPattern:
    video_id: str
    flags: RulePatternFlags
    viewer_problem: str | None = None
    title_pattern: str | None = None
    hook: str | None = None
    promise: str | None = None
    emotion: str | None = None
    beginner_appeal: str | None = None
    primary_archetype: str | None = None
    secondary_archetype: str | None = None
    source: str = "rule"


_ARCHETYPE_LIST = "\n".join(f'- {key}: {label}' for key, label in ARCHETYPES.items())

_GEMINI_PROMPT_TEMPLATE = """다음은 한국 영어교육 YouTube 영상의 제목이다: "{title}"

이 제목을 분석해서 아래 JSON 형식으로만 답하라. 제목을 그대로 베끼지 말고 패턴만 추출하라.

primary_archetype과 secondary_archetype은 반드시 아래 목록의 id 중에서만 골라라 (해당 없으면 "other"):
{archetype_list}

{{
  "viewer_problem": "이 영상이 다루는 시청자의 실제 고민 (한 문장)",
  "title_pattern": "제목의 구조 패턴을 자유롭게 서술 (예: 문제+이유, 질문형, 결과형 등)",
  "hook": "제목이 만드는 호기심/궁금증 포인트 (한 문장)",
  "promise": "시청자에게 약속하는 결과 (한 문장)",
  "emotion": "제목이 건드리는 시청자의 감정 (예: 답답함, 불안, 안도감 등, 한 단어~구)",
  "beginner_appeal": "이 제목이 왕초보 시청자에게 매력적인 이유 (한 문장)",
  "primary_archetype": "위 목록의 id 중 하나",
  "secondary_archetype": "위 목록의 id 중 하나 또는 null (해당 없으면 null)"
}}
"""


def analyze_video(video_id: str, title: str, gemini: GeminiClient | None, max_output_tokens: int = 1024) -> ContentPattern:
    flags = analyze_title_rules(title)
    pattern = ContentPattern(video_id=video_id, flags=flags)

    if gemini and gemini.available:
        prompt = _GEMINI_PROMPT_TEMPLATE.format(title=title, archetype_list=_ARCHETYPE_LIST)
        result = gemini.generate_json(prompt, max_output_tokens=max_output_tokens)
        if result:
            pattern.viewer_problem = result.get("viewer_problem")
            pattern.title_pattern = result.get("title_pattern")
            pattern.hook = result.get("hook")
            pattern.promise = result.get("promise")
            pattern.emotion = result.get("emotion")
            pattern.beginner_appeal = result.get("beginner_appeal")
            primary = result.get("primary_archetype")
            secondary = result.get("secondary_archetype")
            pattern.primary_archetype = primary if primary in ARCHETYPES else None
            pattern.secondary_archetype = secondary if secondary in ARCHETYPES else None
            pattern.source = "gemini"

    if pattern.primary_archetype is None:
        pattern.primary_archetype = fallback_archetype(flags)

    return pattern
