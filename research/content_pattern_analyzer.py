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


@dataclass
class ContentPattern:
    video_id: str
    flags: RulePatternFlags
    viewer_problem: str | None = None
    title_pattern: str | None = None
    hook: str | None = None
    promise: str | None = None
    source: str = "rule"


_GEMINI_PROMPT_TEMPLATE = """다음은 한국 영어교육 YouTube 영상의 제목이다: "{title}"

이 제목을 분석해서 아래 JSON 형식으로만 답하라. 제목을 그대로 베끼지 말고 패턴만 추출하라.

{{
  "viewer_problem": "이 영상이 다루는 시청자의 실제 고민 (한 문장)",
  "title_pattern": "제목의 구조 패턴 (예: 문제+이유, 질문형, 결과형 등)",
  "hook": "제목이 만드는 호기심/궁금증 포인트 (한 문장)",
  "promise": "시청자에게 약속하는 결과 (한 문장)"
}}
"""


def analyze_video(video_id: str, title: str, gemini: GeminiClient | None, max_output_tokens: int = 1024) -> ContentPattern:
    flags = analyze_title_rules(title)
    pattern = ContentPattern(video_id=video_id, flags=flags)

    if gemini and gemini.available:
        result = gemini.generate_json(_GEMINI_PROMPT_TEMPLATE.format(title=title), max_output_tokens=max_output_tokens)
        if result:
            pattern.viewer_problem = result.get("viewer_problem")
            pattern.title_pattern = result.get("title_pattern")
            pattern.hook = result.get("hook")
            pattern.promise = result.get("promise")
            pattern.source = "gemini"

    return pattern
