"""Turns one 08/08-1-approved Production Blueprint into a format-neutral Content Script: what
must be taught, in what order, with what required content, viewer actions, retention intent, and
media-affinity signals -- never a specific video format (EDUCATION/CLIP ANALYSIS/HYBRID/PODCAST)
or production/camera/editing instruction. That format decision belongs to the not-yet-built 10
(Video Director) stage. Topic, Title, Thumbnail, Viewer Contract, Core Q&A, Scope, and Example
Ladder are the Blueprint's source of truth and are never re-decided here -- Gemini only writes
natural base narration and educational metadata around them. Every score and every verifiable
Integrity Check item is decided by code, not by Gemini. The legacy beats/script_json/script_text/
ready_for_production fields (09/09-1) are preserved unchanged for backward compatibility; Content
Blocks (09-2) are a read-only derived layer built on top of them.
"""
from __future__ import annotations

import json
import math
import re
from datetime import date
from pathlib import Path

from research.db import connect
from research.gemini_client import GeminiClient
from research.production_blueprint import (
    _OVERGENERALIZATION_KEYWORDS,
    _phoneme_safe_over_texts,
    _RISKY_FINAL_LETTER_PHONEMES,
    _scope_safe_over_texts,
    check_promise_matches_scope,
    RETENTION_DEVICES,
)
from research.topic_candidates import _content_words

READY_FOR_PRODUCTION_SCORE_THRESHOLD = 70

# Rough, documented estimates -- not a measured TTS rate. Korean educational narration for
# absolute beginners is read slower and more deliberately than conversational speech.
KOREAN_CHARS_PER_SECOND = 4.3
ENGLISH_WORDS_PER_MINUTE = 130

_GENERIC_GREETING_PHRASES = ("안녕하세요", "오늘은 영어 공부를", "여러분 안녕")
_JARGON_TERMS = ("onset", "nucleus", "coda", "phonemic blending", "음소론", "형태론")
_VISUAL_DEPENDENT_PHRASES = ("이것", "여기", "보시는 것처럼", "보시면", "이렇게 보시면")
_PAUSE_CUE_RE = re.compile(r"\[PAUSE\s*(\d+)\s*SEC\]|생각\s*시간|(\d+)\s*초")
_RECAP_SIGNAL_KEYWORDS = ("정리", "복습", "요약", "recap")
_IPA_TOKEN_RE = re.compile(r"/[^/\s]+/")
_MEMORIZATION_NEAR_IPA_RE = re.compile(r"(외우|암기)[^./!?\n]{0,20}/[^/]+/|/[^/]+/[^./!?\n]{0,20}(외우|암기)")

# 09-1: narration-level (not just Video Promise-level) scope-overreach phrases -- these already
# include the "읽" verb where needed so a bare "완벽하게"/"무조건" in an unrelated sentence doesn't
# false-positive (that broader ban stays at _OVERGENERALIZATION_KEYWORDS/no_false_guarantee).
_NARRATION_SCOPE_OVERREACH_PHRASES = (
    "어떤 단어도", "어떤 단어든", "모든 단어", "어떤 영어 단어든",
    "다 읽을 수", "전부 읽을 수", "무조건 읽", "완벽하게 읽",
)
# 09-2: "모든"/"어떤" can also be separated from "단어" by a short modifier ("모든 3글자 영어
# 단어를 읽을 수 있습니다") -- a small allowed gap catches that without matching across sentences.
_NARRATION_SCOPE_OVERREACH_RE = re.compile(r"(모든|어떤)[^.!?\n]{0,12}단어[^.!?\n]{0,6}읽")

# 09-1: "guaranteed/automatic outcome" phrasing -- learning requires practice, not "저절로"/
# "자동으로" success. Kept separate from the shared 08-level _OVERGENERALIZATION_KEYWORDS so this
# stays scoped to script narration instead of widening what Blueprint promise-text bans.
_LEARNING_OUTCOME_EXAGGERATION_PHRASES = (
    "저절로", "자동으로 됩니다", "자동으로 읽", "한 번에 다 됩니다", "한 번에 됩니다",
    "이것만 알면 됩니다", "이것만 알면 다", "무조건 됩니다", "완벽하게 됩니다",
)

# 09-1: genuine participatory retention devices (prediction / challenge / open loop), used both
# to enrich the prompt's guidance and to recognize real engagement in scoring -- not just "?".
_PARTICIPATORY_PHRASES = (
    "어떻게 될까요", "떠올려보세요", "생각해보세요", "여러분 차례", "직접 읽어", "직접 소리 내",
    "한번 읽어보세요", "예측해", "먼저 읽지 않겠습니다",
)

# 09-2: fixed taxonomy for what a Content Block is *for* educationally -- 09 answers "what must
# this teach", never "how should this be shot", so this stays a closed set like every other
# taxonomy in the pipeline (HOOK_TYPES, RETENTION_DEVICES, ...).
LEARNING_FUNCTIONS = {
    "PROBLEM_RECOGNITION", "CORE_EXPLANATION", "DEMONSTRATION", "REINFORCEMENT", "CONTRAST",
    "TRANSFER", "PRACTICE", "MINI_SUCCESS", "RECAP", "RESOLUTION", "OTHER",
}
_MEDIA_AFFINITY_KEYS = (
    "visualization", "real_world_clip", "dialogue", "audio_demonstration", "replay",
    "comparison", "interaction", "storytelling",
)
_MEDIA_AFFINITY_LEVELS = {"low", "medium", "high"}
_IMPORTANCE_LEVELS = {"required", "supporting"}

# 09-2: format_neutrality_safe -- 09 must describe WHAT to teach, never HOW to shoot/edit/host it.
# Phrases are full-ish (e.g. "화면을 확대" not bare "확대") so an unrelated benign sentence doesn't
# false-positive; literal speaker-name tokens are banned outright since the spec's own leakage
# example names them (Mia/Leo/Host/Guest).
_FORMAT_LEAKAGE_PATTERNS = (
    "화면 왼쪽", "화면 오른쪽", "화면 중앙", "중앙 배치", "화면을 확대", "카메라", "Zoom", "zoom",
    "B-roll", "b-roll", "브롤", "waveform", "웨이브폼", "ripple", "karaoke", "가라오케",
    "자막 색", "자막색", "폰트", "font", "애니메이션을 표시", "speaker avatar", "캐릭터가 움직",
    "클립을 재생", "영화 클립", "장면을 삽입", "재생 속도", "슬로우 모션", "slow motion",
    "split screen", "화면을 정지", "Mia", "Leo", "Host:", "Guest:",
    "recommended_format", "selected_format", "video_format", "production_format",
    "EDUCATION 포맷", "CLIP ANALYSIS 포맷", "HYBRID 포맷", "PODCAST 포맷",
)


# ---------------------------------------------------------------------------
# Target blueprint selection
# ---------------------------------------------------------------------------

def select_target_blueprint(db_path: Path, blueprint_id: int | None = None) -> dict | None:
    with connect(db_path) as conn:
        if blueprint_id is not None:
            row = conn.execute("SELECT * FROM production_blueprints WHERE id = ?", (blueprint_id,)).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM production_blueprints WHERE ready_for_script = 1 ORDER BY generated_at DESC LIMIT 1"
            ).fetchone()
    return dict(row) if row else None


def _load_blueprint(row: dict) -> dict:
    """Reconstructs the same blueprint-shaped dict the 08 stage checks expect, from the DB row's
    *_json columns. This is read-only reconstruction -- nothing here is re-decided."""
    def _j(key):
        raw = row.get(key)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return None

    return {
        "viewer_contract": {
            "viewer_problem": row.get("viewer_problem"),
            "click_expectation": row.get("click_expectation"),
            "video_promise": row.get("video_promise"),
            "expected_transformation": row.get("expected_transformation"),
        },
        "core_question": row.get("core_question"),
        "core_answer": row.get("core_answer"),
        "learning_objectives": _j("learning_objectives_json") or [],
        "prerequisite_level": row.get("prerequisite_level"),
        "scope_in": _j("scope_in_json") or [],
        "scope_out": _j("scope_out_json") or [],
        "example_ladder": _j("example_ladder_json") or [],
        "hook": _j("hook_json") or {},
        "sections": _j("sections_json") or [],
        "mini_success": _j("mini_success_json") or {},
        "audio_visual": _j("audio_visual_json") or {},
        "natural_next_topics": _j("natural_next_topics_json") or [],
    }


def _topic_candidate_id_for_package(db_path: Path, category: str | None, problem_id: str | None) -> int | None:
    if not category or not problem_id:
        return None
    with connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT id FROM topic_candidates WHERE category = ? AND problem_id = ?
            ORDER BY generated_at DESC LIMIT 1
            """,
            (category, problem_id),
        ).fetchone()
    return row["id"] if row else None


# ---------------------------------------------------------------------------
# Gemini narration generation
# ---------------------------------------------------------------------------

_SCRIPT_PROMPT = """You are writing a format-neutral educational Content Script, not a final
production script. 너는 한국 YouTube 채널 "{channel_name}"의 Content Script 작가다.

채널 정보:
- 핵심 시청자: {audience}
- 철학: {philosophy}
- 톤: 차분함, 성인 왕초보에게 설명, 과장하지 않음, 가르치려 드는 권위적 어조 최소화, 함께 확인하는 느낌
- 금지 표현: "이것도 모르셨나요?", "초등학생도 압니다", "이걸 모르면 영어 못합니다"

아래는 이미 확정된 Production Blueprint다. Title/Thumbnail/Viewer Contract/Core Question/
Core Answer/Learning Objectives/Scope/Example Ladder는 이미 결정되어 있으므로 절대 다시 정의하거나
바꾸지 마라. 너의 역할은 이 설계를 "무엇을 가르쳐야 하는가"를 담은 자연스러운 한국어 base
narration과 그 옆에 붙는 교육 메타데이터로 옮기는 것뿐이다.

이 단계에서 절대 하지 말 것 (10단계 Video Director의 몫):
- EDUCATION / CLIP ANALYSIS / HYBRID / PODCAST 중 하나를 선택하지 마라.
- 카메라 지시, 화면 레이아웃, 자막 스타일, 애니메이션, B-roll 지시를 만들지 마라.
- 실제 클립 검색 요구사항(예: "~라고 말하는 영화 장면 검색")을 만들지 마라.
- 팟캐스트 화자/역할(Mia, Leo, Host, Guest 등)이나 대사를 만들지 마라.
- 편집 지시(Zoom, Cut, Transition, waveform, karaoke highlight 등)를 만들지 마라.
대신 다음만 정의하라: 무엇을 가르쳐야 하는가, 이 Block이 왜 존재하는가, 필수 교육 내용,
시청자 행동, 생각 시간, retention 의도, base narration, media affinity 신호.

Title: {title}
Thumbnail: {thumbnail_text}
Viewer Problem: {viewer_problem}
Video Promise: {video_promise}
Expected Transformation: {expected_transformation}
Core Question: {core_question}
Core Answer: {core_answer}
Scope IN: {scope_in}
Scope OUT (본론으로 확장 금지, 대본 마지막 Natural Next Topic에서 짧게만 언급 가능): {scope_out}
Example Ladder (이 순서와 단어를 그대로 사용하라): {example_ladder}
Opening Hook 설계: {hook}
Long-form Section 설계 (이 순서와 개수를 그대로 사용하라, 새 규칙을 추가하거나 순서를 바꾸지 마라): {sections}
Mini Success 설계: {mini_success}
Audio-first / Visual 설계: {audio_visual}
Natural Next Topics: {natural_next_topics}

절대 금지:
- Blueprint에 없는 영어 규칙을 새로 추가하지 마라.
- 새로운 예외 규칙을 만들지 마라.
- 예시 단어를 임의로 교체하지 마라.
- 제목/썸네일을 다시 쓰지 마라 (script_json에 제목/썸네일 필드를 만들지 마라).
- Scope OUT을 본론으로 확장하지 마라.
- required_content는 제작 지시가 아니라 교육 내용이다. "BAG를 화면 중앙에 크게 표시"가 아니라
  "BAG를 예시로 사용", "/b/ /æ/ /g/ 음소를 제시" 처럼 적어라.

발음 정확성 원칙 (중요, 08-1과 동일):
- 정확성의 기준은 항상 영어 음소(/g/, /k/, /b/, /p/, /d/, /t/ 등)이며, 한국어 표기는 보조 수단이다.
- "단어(한글)" 또는 "단어=한글"처럼 하나의 한글 표기로 고정해서 소리를 완전히 대신하지 마라. 특히
  /g/-/k/, /b/-/p/, /d/-/t/ 차이를 한글 표기가 지워버리게 하지 마라.
- 같은 단어에 서로 다른 한글 표기를 "/"로 동시 제시하지 마라.
- 글자 소리는 반드시 현재 예시 단어 "안에서만" 한정해서 말하라 (예: "CAP에서는 C가 /k/ 소리를
  냅니다", "BAG와 BAT에서는 B가 /b/ 소리를 냅니다"). "C는 /k/ 소리입니다", "B는 단어 안에서 /b/
  소리를 냅니다"처럼 특정 예시 단어를 명시하지 않고 모든 단어에 적용되는 일반 규칙처럼 말하지 마라
  ("단어 안에서"는 범위 한정이 아니다 -- 반드시 실제 예시 단어 이름이나 "이 단어"/"오늘 예시"를 붙여라).
- core_answer를 포함해 어디에서도 "각 글자가 내는 고유한 소리", "알파벳마다 정해진 소리가 있다"
  처럼 글자마다 하나의 고정된 소리가 있다고 암시하는 표현을 쓰지 마라 -- "이 단어에서" 같은 범위
  한정을 붙여도 "고유한"/"정해진"이라는 단어 선택 자체가 위험하다. 대신 "이 단어에서 나타내는
  소리", "오늘 다루는 단어에서 글자가 나타내는 소리"처럼 지금 다루는 예시로 범위를 한정하라.
- IPA는 정확성 도구일 뿐 시청자의 암기 과제가 아니다. "/æ/를 외우세요" 같은 표현을 쓰지 마라.
  필요하면 "이 기호를 외울 필요는 없습니다, 지금 나는 소리에만 집중하세요" 정도로 안내하라.

Scope 범위 원칙 (중요, 본문 narration에도 적용):
- 이 영상은 단모음 a가 들어간 기초 3글자 CVC 단어만 다룬다. 본문 어디에서도 이보다 넓은 범위를
  약속하지 마라.
- 금지 표현: "어떤 단어도", "모든 단어", "어떤 영어 단어든", "이제 다 읽을 수 있다", "이것만 알면
  다 읽힌다", "항상", "무조건", "완벽하게".
- 단, 문맥상 명확하게 현재 Scope로 한정되어 있다면 허용한다.
  BAD: "이 방법이면 어떤 단어도 읽을 수 있습니다."
  GOOD: "이런 기초 3글자 단어는 같은 방식으로 읽어볼 수 있습니다."
  GOOD: "오늘 다룬 단모음 a가 들어간 CVC 단어에서는 같은 원리를 적용해볼 수 있습니다."

학습 효과 표현 원칙 (중요):
- 학습 결과를 자동적·즉각적·보장된 결과처럼 말하지 마라. Sound Blending은 이해만으로 자동화되지
  않고 실제 연습이 필요한 과정이다.
- 금지 표현: "저절로 됩니다", "바로 됩니다" (단, "바로 다음 단어를 보겠습니다"처럼 순서를 뜻하는
  "바로"는 허용), "한 번에 됩니다", "이것만 알면 됩니다", "자동으로 됩니다", "무조건 됩니다",
  "완벽하게 됩니다".
- 대신 학습 행동 중심으로 말하라.
  BAD: "외우지 않아도 소리가 저절로 연결됩니다."
  GOOD: "글자 이름을 읊는 대신 각 글자의 소리를 하나씩 연결하는 연습을 해보세요."
  GOOD: "처음에는 천천히 소리를 나눠 말한 뒤 조금씩 이어 붙여보세요."

Hook 원칙:
- 첫 문장부터 Viewer Problem으로 들어간다. "안녕하세요", "오늘은 영어 공부를 해보겠습니다" 같은
  일반적인 인사로 시작하지 않는다.
- 0~5초 Viewer Problem 즉시 재현 / 5~15초 잘못 알고 있던 지점 제시 / 15~30초 오늘 얻을 결과 약속.

Audio-first 원칙:
- 화면을 보지 않아도 핵심 흐름을 이해할 수 있어야 한다. "여기 보시면 이렇게 됩니다" 같은 시각
  의존 표현을 과도하게 쓰지 마라.

Mini Success 원칙 (중요):
- CAP 등 Mini Success 단어의 정답을 즉시 말하지 않는다. `viewer_action`에 "정답 공개 전에 CAP을
  직접 읽어본다"처럼 시청자 행동을 적고, `thinking_time_seconds`에 생각 시간(초)을 숫자로 적어라.
  이 시간을 화면에서 "어떻게" 표현할지(정지 화면, 카운트다운 애니메이션 등)는 정하지 마라 -- 그건
  10단계의 몫이다. narration에는 "[PAUSE 3 SEC]"처럼 짧게 시간 경과를 알리는 표시 정도만 남긴다.
- mini_success_beats에서 "[PAUSE N SEC]" cue 이전 narration에는 음소 표기(/k/, /æ/, /p/ 같은
  IPA)나 전체 발음을 절대 넣지 마라. 시청자가 아직 시도하지 않은 상태에서 정답 소리를 먼저 들려주면
  더 이상 스스로 소리를 떠올리는 것이 아니라 주어진 답을 따라 읽는 것이 된다. pause 이전에는 대상
  단어의 철자(예: "CAP")와 "직접 읽어보세요" 같은 행동 유도만 적고, IPA 음소 breakdown과 자연스러운
  발음 확인은 반드시 "[PAUSE N SEC]" 다음 narration에서만 등장해야 한다.
  BAD (pause 전): "오늘 배운 C의 /k/, A의 /æ/, P의 /p/ 소리를 합쳐 CAP을 읽어보세요."
  GOOD (pause 전): "화면의 단어를 보고, 오늘 배운 방법대로 직접 소리 내어 읽어보세요."
  GOOD (pause 후): "C의 /k/, A의 /æ/, P의 /p/ 소리를 이어 CAP이 됩니다."

Retention 원칙 (중요, retention_intent로 구조화):
- 각 Content Block에 `retention_intent: {{"type": "...", "purpose": "..."}}`를 채워라. type은
  Blueprint Section의 retention_device 값(예: open_loop, quiz, prediction, contrast, new_example,
  visual_change, mini_success, misconception_correction, next_question)을 그대로 쓰거나 가장
  가까운 것을 골라라. 모든 Block에 억지로 질문을 넣지 말고, 다음 목적에 해당할 때만 base_narration에
  짧은 참여 장치를 실제로 반영하라: (1) 다음 예시를 예측하게 한다, (2) 앞에서 배운 원리를 다시
  사용하게 한다, (3) 정답 공개 전에 짧게 생각하게 한다, (4) 다음 Block으로 넘어갈 이유를 만든다.
  예: BAG 완료 후 "그럼 끝 글자만 바꾸면 어떻게 될까요?" / BAT 완료 후 "이번에는 앞 글자까지
  바꿔보겠습니다. 그래도 같은 방법일까요?" / MAP 진입 "제가 읽기 전에 세 소리를 한번 떠올려보세요."
  / CAP 진입 "이제 마지막은 여러분 차례입니다."
- 의미 없는 질문형 문장을 반복해서 넣어 분량만 늘리지 마라.

Content Block 메타데이터 (각 opening/section/mini_success/ending에 채워라):
- `learning_function`: 다음 중 하나만 사용 -- {learning_functions}
- `required_content`: 이 Block이 반드시 전달해야 하는 교육 내용 리스트 (제작 지시 아님). 예:
  "BAG를 예시로 사용", "/b/ /æ/ /g/ 음소를 제시", "세 소리를 연결하는 원리를 설명".
- `importance`: "required" 또는 "supporting".
- `viewer_action`: 시청자가 해야 할 행동 (없으면 null).
- `thinking_time_seconds`: 생각 시간(초), 없으면 0.
- `media_affinity`: 다음 8개 신호를 각각 low/medium/high로 -- visualization, real_world_clip,
  dialogue, audio_demonstration, replay, comparison, interaction, storytelling. 이것은 "추천
  포맷"이 아니라 신호일 뿐이다. real_world_clip이 high라고 CLIP ANALYSIS 포맷을 선택하라는
  뜻이 아니고, dialogue가 high라고 화자를 만들라는 뜻도 아니다.

CTA는 선택이며, 사용한다면 영상 끝에 짧고 자연스럽게만 넣는다.

아래 JSON 형식으로만 답하라 (각 opening/section/mini_success/ending에 위 메타데이터 필드를
모두 포함하라):

{{
  "opening": {{"beats": [{{"type": "narration", "text": "..."}}],
    "learning_function": "PROBLEM_RECOGNITION", "required_content": ["..."], "importance": "required",
    "viewer_action": null, "thinking_time_seconds": 0,
    "retention_intent": {{"type": "open_loop", "purpose": "..."}},
    "media_affinity": {{"visualization": "medium", "real_world_clip": "low", "dialogue": "low",
      "audio_demonstration": "medium", "replay": "low", "comparison": "low", "interaction": "low",
      "storytelling": "low"}}}},
  "sections": [
    {{"section_number": 1, "purpose": "...", "estimated_seconds": 40,
      "beats": [{{"type": "narration", "text": "..."}}],
      "learning_function": "CORE_EXPLANATION", "required_content": ["..."], "importance": "required",
      "viewer_action": null, "thinking_time_seconds": 0,
      "retention_intent": {{"type": "new_example", "purpose": "..."}},
      "media_affinity": {{"visualization": "medium", "real_world_clip": "low", "dialogue": "low",
        "audio_demonstration": "high", "replay": "low", "comparison": "medium", "interaction": "low",
        "storytelling": "low"}}}}
  ],
  "mini_success_beats": [{{"type": "narration", "text": "..."}}, {{"type": "cue", "text": "[PAUSE 3 SEC]"}}],
  "mini_success_meta": {{"learning_function": "MINI_SUCCESS", "required_content": ["..."],
    "importance": "required", "viewer_action": "...", "thinking_time_seconds": 3,
    "retention_intent": {{"type": "mini_success", "purpose": "..."}},
    "media_affinity": {{"visualization": "medium", "real_world_clip": "low", "dialogue": "low",
      "audio_demonstration": "high", "replay": "low", "comparison": "low", "interaction": "high",
      "storytelling": "low"}}}},
  "ending": {{"beats": [{{"type": "narration", "text": "..."}}],
    "learning_function": "RECAP", "required_content": ["..."], "importance": "required",
    "viewer_action": null, "thinking_time_seconds": 0,
    "retention_intent": {{"type": "next_question", "purpose": "..."}},
    "media_affinity": {{"visualization": "low", "real_world_clip": "low", "dialogue": "low",
      "audio_demonstration": "low", "replay": "low", "comparison": "low", "interaction": "low",
      "storytelling": "low"}}}},
  "no_unverified_rule_self_check": "pass|warning|fail",
  "ipa_not_memorization_self_check": "pass|warning|fail"
}}

sections 배열은 Blueprint의 Section 개수와 순서를 정확히 그대로 사용하라.
"""


def _default_media_affinity() -> dict:
    return {key: "medium" for key in _MEDIA_AFFINITY_KEYS}


def _default_block_meta(learning_function: str, retention_type: str) -> dict:
    """Safe, format-neutral defaults for any block missing metadata (fallback path or a
    Gemini response that omits fields) -- never invents production/format decisions."""
    return {
        "learning_function": learning_function if learning_function in LEARNING_FUNCTIONS else "OTHER",
        "required_content": [],
        "importance": "required",
        "viewer_action": None,
        "thinking_time_seconds": 0,
        "retention_intent": {"type": retention_type, "purpose": ""},
        "media_affinity": _default_media_affinity(),
    }


def _fallback_script(blueprint: dict) -> dict:
    """Used only if Gemini is unavailable/fails. Deliberately minimal -- no hook framing, no
    mini-success pause cue -- so the downstream Integrity Check honestly catches the quality gap
    instead of a fabricated pass. generation_method is recorded separately as 'fallback'."""
    sections = blueprint.get("sections") or []
    script = {
        "opening": {
            "beats": [{"type": "narration", "text": str(blueprint.get("core_question") or "")}],
            **_default_block_meta("PROBLEM_RECOGNITION", "open_loop"),
        },
        "sections": [
            {
                "section_number": s.get("section_number", i + 1),
                "purpose": s.get("section_goal", ""),
                "estimated_seconds": 30,
                "beats": [{"type": "narration", "text": str(s.get("key_point") or "")}],
                **_default_block_meta("CORE_EXPLANATION", s.get("retention_device") or "open_loop"),
            }
            for i, s in enumerate(sections)
        ],
        "mini_success_beats": [],
        "mini_success_meta": _default_block_meta("MINI_SUCCESS", "mini_success"),
        "ending": {
            "beats": [{"type": "narration", "text": str(blueprint.get("core_answer") or "")}],
            **_default_block_meta("RECAP", "next_question"),
        },
        "no_unverified_rule_self_check": "warning",
        "ipa_not_memorization_self_check": "warning",
    }
    return script


def generate_script_content(
    blueprint: dict, gemini: GeminiClient | None, channel_cfg: dict, max_output_tokens: int = 8000
) -> tuple[dict, str]:
    """Returns (script_dict, generation_method)."""
    result = None
    if gemini and gemini.available:
        contract = blueprint.get("viewer_contract") or {}
        prompt = _SCRIPT_PROMPT.format(
            channel_name=channel_cfg.get("name", ""),
            audience=channel_cfg.get("audience", ""),
            philosophy=channel_cfg.get("philosophy", ""),
            title=blueprint.get("title", ""),
            thumbnail_text=blueprint.get("thumbnail_text", ""),
            viewer_problem=contract.get("viewer_problem", ""),
            video_promise=contract.get("video_promise", ""),
            expected_transformation=contract.get("expected_transformation", ""),
            core_question=blueprint.get("core_question", ""),
            core_answer=blueprint.get("core_answer", ""),
            scope_in=json.dumps(blueprint.get("scope_in") or [], ensure_ascii=False),
            scope_out=json.dumps(blueprint.get("scope_out") or [], ensure_ascii=False),
            example_ladder=json.dumps(blueprint.get("example_ladder") or [], ensure_ascii=False),
            hook=json.dumps(blueprint.get("hook") or {}, ensure_ascii=False),
            sections=json.dumps(blueprint.get("sections") or [], ensure_ascii=False),
            mini_success=json.dumps(blueprint.get("mini_success") or {}, ensure_ascii=False),
            audio_visual=json.dumps(blueprint.get("audio_visual") or {}, ensure_ascii=False),
            natural_next_topics=json.dumps(blueprint.get("natural_next_topics") or [], ensure_ascii=False),
            learning_functions=", ".join(sorted(LEARNING_FUNCTIONS)),
        )
        result = gemini.generate_json(prompt, max_output_tokens=max_output_tokens)

    if not isinstance(result, dict) or not result.get("sections"):
        return _fallback_script(blueprint), "fallback"

    return _sanitize_script(result, blueprint), "gemini"


def _sanitize_script(raw: dict, blueprint: dict) -> dict:
    """Forces the script's section list to match the Blueprint's section count/order exactly --
    Gemini's raw output never gets to silently reorder, merge, or invent sections."""
    blueprint_sections = blueprint.get("sections") or []
    by_number = {s.get("section_number"): s for s in (raw.get("sections") or []) if isinstance(s, dict)}

    fixed_sections = []
    for bs in blueprint_sections:
        number = bs.get("section_number")
        candidate = by_number.get(number) or {}
        fallback_retention = bs.get("retention_device") or "open_loop"
        if candidate.get("beats"):
            fixed_sections.append(
                {
                    "section_number": number,
                    "purpose": candidate.get("purpose") or bs.get("section_goal", ""),
                    "estimated_seconds": candidate.get("estimated_seconds") or 30,
                    "beats": candidate.get("beats") or [],
                    **_sanitize_block_meta(candidate, "CORE_EXPLANATION", fallback_retention),
                }
            )
        else:
            fixed_sections.append(
                {
                    "section_number": number,
                    "purpose": bs.get("section_goal", ""),
                    "estimated_seconds": 30,
                    "beats": [{"type": "narration", "text": str(bs.get("key_point") or "")}],
                    **_default_block_meta("CORE_EXPLANATION", fallback_retention),
                }
            )

    raw["sections"] = fixed_sections
    opening = raw.get("opening") or {}
    raw["opening"] = {"beats": opening.get("beats") or [], **_sanitize_block_meta(opening, "PROBLEM_RECOGNITION", "open_loop")}
    raw.setdefault("mini_success_beats", [])
    mini_meta = raw.get("mini_success_meta") or {}
    raw["mini_success_meta"] = _sanitize_block_meta(mini_meta, "MINI_SUCCESS", "mini_success")
    ending = raw.get("ending") or {}
    raw["ending"] = {"beats": ending.get("beats") or [], **_sanitize_block_meta(ending, "RECAP", "next_question")}
    if raw.get("no_unverified_rule_self_check") not in {"pass", "warning", "fail"}:
        raw["no_unverified_rule_self_check"] = "warning"
    if raw.get("ipa_not_memorization_self_check") not in {"pass", "warning", "fail"}:
        raw["ipa_not_memorization_self_check"] = "warning"
    return raw


def _sanitize_block_meta(block: dict, fallback_learning_function: str, fallback_retention_type: str) -> dict:
    """Validates a Content Block's educational metadata against its fixed taxonomies -- a Gemini
    response with a missing/invalid value never crashes the pipeline or silently becomes a
    production decision; it falls back to a safe, format-neutral default (09-2 spec section 4)."""
    learning_function = block.get("learning_function")
    if learning_function not in LEARNING_FUNCTIONS:
        learning_function = fallback_learning_function if fallback_learning_function in LEARNING_FUNCTIONS else "OTHER"

    required_content = block.get("required_content")
    if not isinstance(required_content, list):
        required_content = []

    importance = block.get("importance")
    if importance not in _IMPORTANCE_LEVELS:
        importance = "required"

    viewer_action = block.get("viewer_action")
    if not isinstance(viewer_action, str) or not viewer_action.strip():
        viewer_action = None

    thinking_time = block.get("thinking_time_seconds")
    if not isinstance(thinking_time, (int, float)) or thinking_time < 0:
        thinking_time = 0

    retention_intent = block.get("retention_intent") or {}
    r_type = retention_intent.get("type") if isinstance(retention_intent, dict) else None
    if r_type not in RETENTION_DEVICES:
        r_type = fallback_retention_type if fallback_retention_type in RETENTION_DEVICES else "open_loop"
    r_purpose = retention_intent.get("purpose", "") if isinstance(retention_intent, dict) else ""

    raw_affinity = block.get("media_affinity") or {}
    media_affinity = {}
    for key in _MEDIA_AFFINITY_KEYS:
        value = raw_affinity.get(key) if isinstance(raw_affinity, dict) else None
        media_affinity[key] = value if value in _MEDIA_AFFINITY_LEVELS else "medium"

    return {
        "learning_function": learning_function,
        "required_content": required_content,
        "importance": importance,
        "viewer_action": viewer_action,
        "thinking_time_seconds": thinking_time,
        "retention_intent": {"type": r_type, "purpose": r_purpose},
        "media_affinity": media_affinity,
    }


# ---------------------------------------------------------------------------
# script_text synthesis
# ---------------------------------------------------------------------------

_BEAT_LABELS = {"narration": "[NARRATION]", "on_screen": "[ON SCREEN]", "cue": "[CUE]"}


def _render_beats(beats: list[dict]) -> list[str]:
    lines = []
    for beat in beats or []:
        label = _BEAT_LABELS.get(beat.get("type"), "[NARRATION]")
        text = str(beat.get("text") or "")
        if text:
            lines.append(f"{label}\n{text}")
    return lines


def render_script_text(script: dict) -> str:
    parts = ["## Opening Hook"]
    parts.extend(_render_beats((script.get("opening") or {}).get("beats")))

    for s in script.get("sections") or []:
        parts.append(f"\n## Section {s.get('section_number')}: {s.get('purpose', '')}")
        parts.extend(_render_beats(s.get("beats")))

    parts.append("\n## Mini Success")
    parts.extend(_render_beats(script.get("mini_success_beats")))

    parts.append("\n## Ending")
    parts.extend(_render_beats((script.get("ending") or {}).get("beats")))

    return "\n\n".join(parts)


def _narration_texts(script: dict, include_ending: bool = True) -> list[str]:
    """One text chunk per narration beat, opening through ending (or excluding ending)."""
    texts = []
    for beat in (script.get("opening") or {}).get("beats") or []:
        if beat.get("type") == "narration":
            texts.append(str(beat.get("text") or ""))
    for s in script.get("sections") or []:
        for beat in s.get("beats") or []:
            if beat.get("type") == "narration":
                texts.append(str(beat.get("text") or ""))
    for beat in script.get("mini_success_beats") or []:
        if beat.get("type") == "narration":
            texts.append(str(beat.get("text") or ""))
    if include_ending:
        for beat in (script.get("ending") or {}).get("beats") or []:
            if beat.get("type") == "narration":
                texts.append(str(beat.get("text") or ""))
    return texts


def _block_narration(beats: list[dict]) -> str:
    return " ".join(str(b.get("text") or "") for b in (beats or []) if b.get("type") == "narration")


# ---------------------------------------------------------------------------
# 09-2: format-neutral Content Block structure
#
# A Content Block answers "what must this teach", never "how should this be shot" -- it's built
# purely by reading the already-generated beats/metadata, so it never touches the existing
# scoring/Integrity Check pipeline that already operates on `script`.
# ---------------------------------------------------------------------------

_DUPLICATE_BLOCK_JACCARD_THRESHOLD = 0.5
# No \b boundaries: Korean particles routinely attach directly to an English word with no space
# ("CAP이", "BAT가"), and Python's \b treats Hangul as a word character, so "\bCAP\b" would fail
# to match "CAP" in "CAP이" -- the same reason production_blueprint.py's equivalent patterns
# (_EXAMPLE_WORD_TOKEN_RE, _SCOPE_PREFIX's [A-Z]{2,}) don't use \b either.
_UPPERCASE_TOKEN_RE = re.compile(r"[A-Z]{2,}")


def _candidate_words(candidate: dict) -> set:
    text = str(candidate.get("base_narration") or "") + " " + " ".join(str(x) for x in candidate.get("required_content") or [])
    return _content_words(text)


def _is_duplicate_candidate(candidate: dict, existing: dict) -> bool:
    """09-3: two blocks represent the same educational event if they share a learning_function
    and their content overlaps heavily -- same function alone isn't enough (a BAG DEMONSTRATION
    and a BAT REINFORCEMENT block both talk about sound blending but teach different things).
    Checks three signals in order of reliability (spec section 2/11):

    1. base_narration word overlap -- the actual spoken content, so two blocks narrating the same
       scene almost verbatim are the clearest signal ("같은 CAP 퀴즈 장면을 두 번 제작할 위험").
    2. same explicit example word (e.g. both mention "CAP") plus a matching viewer_action or
       thinking_time_seconds -- catches the case where Gemini rewords the narration enough each
       time that word-overlap alone dips under threshold, but it's still visibly the same
       in-video event (same word, same "make the viewer read it before revealing the answer" beat).
    3. combined base_narration + required_content bag-of-words, as a looser fallback.
    """
    if candidate.get("learning_function") != existing.get("learning_function"):
        return False

    narration_a_text = str(candidate.get("base_narration") or "")
    narration_b_text = str(existing.get("base_narration") or "")
    narration_a = _content_words(narration_a_text)
    narration_b = _content_words(narration_b_text)
    if narration_a and narration_b:
        narration_overlap = len(narration_a & narration_b) / len(narration_a | narration_b)
        if narration_overlap >= _DUPLICATE_BLOCK_JACCARD_THRESHOLD:
            return True

    shared_example_words = set(_UPPERCASE_TOKEN_RE.findall(narration_a_text)) & set(_UPPERCASE_TOKEN_RE.findall(narration_b_text))
    if shared_example_words:
        viewer_action_a, viewer_action_b = candidate.get("viewer_action"), existing.get("viewer_action")
        same_viewer_action = bool(viewer_action_a and viewer_action_b and (
            _content_words(viewer_action_a) & _content_words(viewer_action_b)
        ))
        thinking_a, thinking_b = candidate.get("thinking_time_seconds"), existing.get("thinking_time_seconds")
        same_thinking_time = bool(thinking_a and thinking_b and thinking_a == thinking_b)
        if same_viewer_action or same_thinking_time:
            return True

    words_a, words_b = _candidate_words(candidate), _candidate_words(existing)
    if not words_a or not words_b:
        return False
    overlap = len(words_a & words_b) / len(words_a | words_b)
    return overlap >= _DUPLICATE_BLOCK_JACCARD_THRESHOLD


def _merge_candidate_into(target: dict, candidate: dict) -> None:
    """Folds a duplicate candidate's useful fields into the canonical block instead of discarding
    it outright -- a later-generated duplicate (e.g. mini_success_meta) sometimes carries a
    viewer_action/thinking_time the earlier section block left empty."""
    if not target.get("viewer_action") and candidate.get("viewer_action"):
        target["viewer_action"] = candidate["viewer_action"]
    if not target.get("thinking_time_seconds") and candidate.get("thinking_time_seconds"):
        target["thinking_time_seconds"] = candidate["thinking_time_seconds"]
    existing_required = target.get("required_content") or []
    for item in candidate.get("required_content") or []:
        if item not in existing_required:
            existing_required.append(item)
    target["required_content"] = existing_required


def _extract_block_meta(source: dict) -> dict:
    return {
        "learning_function": source.get("learning_function", "OTHER"),
        "required_content": list(source.get("required_content") or []),
        "importance": source.get("importance", "required"),
        "viewer_action": source.get("viewer_action"),
        "thinking_time_seconds": source.get("thinking_time_seconds", 0),
        "retention_intent": source.get("retention_intent") or {"type": "open_loop", "purpose": ""},
        "media_affinity": source.get("media_affinity") or _default_media_affinity(),
    }


def build_content_blocks(blueprint: dict, script: dict) -> list[dict]:
    """Builds Content Blocks in educational-flow order, then avoids emitting a second block for
    an educational event that's already fully represented by the previous one (09-3 spec section
    4: "가능하면 Content Block을 생성할 때 중복 자체를 만들지 않는 방식을 우선한다") -- e.g. a
    section already tagged MINI_SUCCESS that duplicates the separate mini_success_meta block, or a
    final Section already doing RECAP that duplicates the Ending block."""
    candidates: list[dict] = []

    opening = script.get("opening") or {}
    candidates.append({
        "section_number": None, "purpose": "Viewer Problem 즉시 제시",
        **_extract_block_meta(opening), "base_narration": _block_narration(opening.get("beats")),
    })

    for s in script.get("sections") or []:
        candidates.append({
            "section_number": s.get("section_number"), "purpose": s.get("purpose", ""),
            **_extract_block_meta(s), "base_narration": _block_narration(s.get("beats")),
        })

    mini_meta = script.get("mini_success_meta") or {}
    mini_candidate = {
        "section_number": None, "purpose": mini_meta.get("purpose") or "학습자가 스스로 적용해보는 성공 경험",
        **_extract_block_meta(mini_meta), "base_narration": _block_narration(script.get("mini_success_beats")),
    }
    # Compare against every existing candidate, not just the immediately preceding one -- the
    # section this duplicates (e.g. the CAP section already tagged MINI_SUCCESS) is very often
    # not the last one built, since later sections (or Ending) may sit between them.
    duplicate_of = next((c for c in candidates if _is_duplicate_candidate(mini_candidate, c)), None)
    if duplicate_of is not None:
        _merge_candidate_into(duplicate_of, mini_candidate)
    else:
        candidates.append(mini_candidate)

    ending = script.get("ending") or {}
    ending_candidate = {
        "section_number": None, "purpose": ending.get("purpose") or "핵심 원리 정리 및 다음 주제 예고",
        **_extract_block_meta(ending), "base_narration": _block_narration(ending.get("beats")),
    }
    duplicate_of = next((c for c in candidates if _is_duplicate_candidate(ending_candidate, c)), None)
    if duplicate_of is not None:
        _merge_candidate_into(duplicate_of, ending_candidate)
    else:
        candidates.append(ending_candidate)

    blocks: list[dict] = []
    prior_id: str | None = None
    for i, c in enumerate(candidates, start=1):
        block_id = f"CB{i:02d}"
        blocks.append({
            "content_block_id": block_id,
            "section_number": c.get("section_number"),
            "learning_function": c["learning_function"],
            "purpose": c["purpose"],
            "required_content": c["required_content"],
            "importance": c["importance"],
            "prerequisite_blocks": [prior_id] if prior_id else [],
            "viewer_action": c["viewer_action"],
            "thinking_time_seconds": c["thinking_time_seconds"],
            "retention_intent": c["retention_intent"],
            "media_affinity": c["media_affinity"],
            "base_narration": c["base_narration"],
            "format_neutral": True,
            "direction_eligible": True,
        })
        prior_id = block_id

    return blocks


# ---------------------------------------------------------------------------
# Duration / word count estimate (documented estimate, not measured TTS)
# ---------------------------------------------------------------------------

_PAUSE_SECONDS_RE = re.compile(r"\[PAUSE\s*(\d+)\s*SEC\]")
_KOREAN_CHAR_RE = re.compile(r"[가-힣]")
_ENGLISH_WORD_RE = re.compile(r"[A-Za-z]+")
_KOREAN_WORD_RE = re.compile(r"[가-힣]+")


def estimate_duration_and_words(script_text: str) -> tuple[float, int]:
    """Deterministic rough estimate only -- not a measured CapCut TTS speaking rate. Korean
    syllables and English words are counted separately since this channel's narration mixes
    both, and a single English-WPM formula would badly misestimate the Korean portion."""
    korean_char_count = len(_KOREAN_CHAR_RE.findall(script_text))
    english_word_count = len(_ENGLISH_WORD_RE.findall(script_text))
    korean_word_count = len(_KOREAN_WORD_RE.findall(script_text))

    pause_seconds = sum(int(n) for n in _PAUSE_SECONDS_RE.findall(script_text))

    seconds = korean_char_count / KOREAN_CHARS_PER_SECOND
    seconds += english_word_count / (ENGLISH_WORDS_PER_MINUTE / 60)
    seconds += pause_seconds

    word_count = korean_word_count + english_word_count
    return round(seconds, 1), word_count


def _content_block_check_text(content_blocks: list[dict]) -> str:
    """All text a format-neutrality violation could hide in: required_content (should be content
    facts, not production instructions) plus base_narration."""
    parts = []
    for block in content_blocks:
        parts.extend(str(item) for item in block.get("required_content") or [])
        parts.append(block.get("base_narration") or "")
    return " ".join(parts)


def check_format_neutrality_safe(content_blocks: list[dict]) -> str:
    """Deterministic backstop -- 09 must describe WHAT to teach, never HOW to shoot/edit/host it.
    Does not rely on Gemini's own self-report; scans required_content/base_narration directly."""
    text = _content_block_check_text(content_blocks)
    return "fail" if any(p in text for p in _FORMAT_LEAKAGE_PATTERNS) else "pass"


# ---------------------------------------------------------------------------
# 09-4: mini_success_present structural re-judgment (spec sections 2-7). The old check required
# blueprint.mini_success.prompt_word (e.g. "M /m/ + A /æ/ + P /p/ = ?") to appear as a literal
# substring in the narration -- Gemini almost never echoes that exact equation text back verbatim,
# so a real, structurally complete Mini Success (viewer_action + pause + IPA answer, all present
# and correctly ordered) still failed. This replaces the substring match with the structural
# signals from spec section 3: a real Mini Success block, an explicit attempt cue, answer evidence
# (IPA is the concrete "the answer was actually given" signal -- a bare target word alone is not,
# since showing the word to read is the legitimate prompt), and attempt-before-answer ordering.
# ---------------------------------------------------------------------------

def _is_mini_success_block(cb: dict) -> bool:
    learning_function = cb.get("learning_function")
    if learning_function == "MINI_SUCCESS":
        return True
    if learning_function and learning_function != "OTHER":
        # An explicit, different learning_function taxonomy value takes precedence over a
        # retention_intent label that only describes *why* the block exists -- e.g. a PRACTICE
        # block whose retention purpose is "priming for the upcoming mini success" can legitimately
        # carry retention_intent.type == "mini_success" without itself being the Mini Success.
        return False
    return (cb.get("retention_intent") or {}).get("type") == "mini_success"


def _has_answer_evidence(text: str, blueprint: dict) -> bool:
    """IPA is the concrete "the sound answer was actually given" signal. A bare target word
    (e.g. "MAP") is not counted here on its own -- that's the legitimate pre-pause prompt ("read
    MAP"), not evidence that an answer/confirmation exists; only the Blueprint's own prompt_word
    (spec section 5's "expected_word") counts as an explicit non-IPA answer signal."""
    if _IPA_TOKEN_RE.search(text):
        return True
    prompt_word = (blueprint.get("mini_success") or {}).get("prompt_word") or ""
    return bool(prompt_word) and prompt_word.lower() in text.lower()


def _answer_revealed_before_attempt(beats: list[dict]) -> bool:
    """IPA is the concrete "sound answer" signal -- the bare target word (e.g. "MAP을 직접
    읽어보세요.") is the legitimate pre-pause prompt, not a reveal, so only IPA tokens count here."""
    pause_index = next(
        (i for i, b in enumerate(beats) if b.get("type") == "cue" and _PAUSE_CUE_RE.search(str(b.get("text") or ""))), None,
    )
    if pause_index is not None:
        pre_text = " ".join(str(b.get("text") or "") for b in beats[:pause_index] if b.get("type") == "narration")
        return bool(_IPA_TOKEN_RE.search(pre_text))
    narration_beats = [b for b in beats if b.get("type") == "narration"]
    if not narration_beats:
        return False
    return bool(_IPA_TOKEN_RE.search(str(narration_beats[0].get("text") or "")))


def _mini_success_candidates(script: dict, content_blocks: list[dict]) -> list[dict]:
    """Signal #1's third alternative (spec section 3): the dedicated mini_success_meta/beats
    structure counts as Mini Success evidence on its own, even when a content block wasn't (or
    couldn't be) tagged learning_function == MINI_SUCCESS -- e.g. a bare script dict built without
    going through _sanitize_block_meta's fallback tagging."""
    raw_beats = script.get("mini_success_beats") or []
    candidates = [cb for cb in content_blocks if _is_mini_success_block(cb)]
    if raw_beats:
        mini_meta = script.get("mini_success_meta") or {}
        candidates.append({"base_narration": _block_narration(raw_beats), "viewer_action": mini_meta.get("viewer_action")})
    return candidates


def _candidate_beats(cb: dict, raw_beats: list[dict]) -> list[dict]:
    """Prefer the raw mini_success_beats (retains the [PAUSE N SEC] cue for order-checking) when
    they're the actual source of this block's narration; otherwise fall back to a synthetic single
    narration beat built from the block's own text, which still preserves before/after ordering
    even without the cue itself."""
    narration = cb.get("base_narration") or ""
    if raw_beats and _block_narration(raw_beats) == narration:
        return raw_beats
    return [{"type": "narration", "text": narration}]


def check_mini_success_present(blueprint: dict, script: dict, content_blocks: list[dict]) -> str:
    candidates = _mini_success_candidates(script, content_blocks)
    if not candidates:
        return "fail"

    raw_beats = script.get("mini_success_beats") or []
    for cb in candidates:
        narration = cb.get("base_narration") or ""
        has_action_signal = bool(cb.get("viewer_action")) or any(p in narration for p in _PARTICIPATORY_PHRASES)
        if not has_action_signal:
            continue

        beats = _candidate_beats(cb, raw_beats)
        beat_text = " ".join(str(b.get("text") or "") for b in beats if b.get("type") == "narration")

        if not _has_answer_evidence(beat_text, blueprint):
            continue
        if _answer_revealed_before_attempt(beats):
            continue
        return "pass"
    return "fail"


# ---------------------------------------------------------------------------
# 09-5 section 9-12: mini_success_answer_barrier_safe. Distinct from mini_success_present's
# structural check -- this specifically re-verifies, for every recognized Mini Success candidate,
# that no answer-pronunciation evidence (IPA phonemes/full pronunciation) precedes the attempt.
# TARGET ORTHOGRAPHY (the bare word shown as the prompt) is not answer information and is allowed
# freely before the pause; only IPA counts as a reveal (see _answer_revealed_before_attempt).
#
# Known limitation: at 09's plain-text stage there is no structural way to distinguish "CAP shown
# as the prompt spelling" from "CAP spoken aloud as the natural-pronunciation answer" (spec
# section 11's third reveal example) -- both are just the substring "CAP" in narration text. That
# distinction only becomes checkable once speech_mode exists (11's answer_not_revealed_before_
# attempt, which classifies EN_NATIVE/EN_PHONEME_DEMO speech events against the timeline).
# ---------------------------------------------------------------------------

def check_mini_success_answer_barrier_safe(script: dict, content_blocks: list[dict]) -> str:
    candidates = _mini_success_candidates(script, content_blocks)
    if not candidates:
        return "warning"  # mini_success_present already owns "no Mini Success at all"

    raw_beats = script.get("mini_success_beats") or []
    for cb in candidates:
        beats = _candidate_beats(cb, raw_beats)
        if _answer_revealed_before_attempt(beats):
            return "fail"
    return "pass"


# ---------------------------------------------------------------------------
# 09-4: practice_mini_success_progression_safe (spec sections 8-12). Reusing the same target word
# in a PRACTICE block and a MINI_SUCCESS block is a legitimate GUIDED PRACTICE -> INDEPENDENT
# ATTEMPT progression, not automatic duplication -- it only becomes real repetition when scaffold
# does NOT decrease (Practice already required an independent attempt too) or the two blocks share
# the same viewer_action AND thinking_time (spec section 10's FAIL example).
# ---------------------------------------------------------------------------

def check_practice_mini_success_progression_safe(content_blocks: list[dict]) -> str:
    practice_blocks = [cb for cb in content_blocks if cb.get("learning_function") == "PRACTICE"]
    mini_blocks = [cb for cb in content_blocks if _is_mini_success_block(cb)]

    for practice in practice_blocks:
        practice_words = set(_UPPERCASE_TOKEN_RE.findall(str(practice.get("base_narration") or "")))
        for mini in mini_blocks:
            mini_words = set(_UPPERCASE_TOKEN_RE.findall(str(mini.get("base_narration") or "")))
            if not (practice_words & mini_words):
                continue  # different target example -- not the same activity at all

            practice_has_scaffold = bool(_IPA_TOKEN_RE.search(str(practice.get("base_narration") or ""))) and not practice.get("viewer_action")
            mini_is_independent = bool(mini.get("viewer_action"))

            same_viewer_action = bool(
                practice.get("viewer_action") and mini.get("viewer_action")
                and _content_words(practice["viewer_action"]) == _content_words(mini["viewer_action"])
            )
            same_thinking_time = bool(
                practice.get("thinking_time_seconds") and mini.get("thinking_time_seconds")
                and practice["thinking_time_seconds"] == mini["thinking_time_seconds"]
            )

            if practice_has_scaffold and mini_is_independent and not (same_viewer_action and same_thinking_time):
                continue  # legitimate GUIDED PRACTICE -> INDEPENDENT MINI SUCCESS progression
            return "fail"
    return "pass"


# ---------------------------------------------------------------------------
# 09-4: ending_resolves_opening closing-region widening (spec sections 13-17). The old check only
# looked at the single `ending` Block's narration -- a short final sign-off (next-topic preview +
# thanks) that never re-mentions the Core Question. The actual resolution (a RECAP restating the
# core principle) can sit in an earlier Block that's still part of the closing region.
# ---------------------------------------------------------------------------

_CLOSING_REGION_FUNCTIONS = {"RECAP", "RESOLUTION", "MINI_SUCCESS"}


def collect_closing_region(content_blocks: list[dict]) -> list[dict]:
    closing: list[dict] = []
    for cb in reversed(content_blocks):
        if cb.get("learning_function") in _CLOSING_REGION_FUNCTIONS:
            closing.append(cb)
        else:
            break
    closing.reverse()
    return closing or (content_blocks[-1:] if content_blocks else [])


def check_ending_resolves_opening(blueprint: dict, content_blocks: list[dict]) -> str:
    closing_blocks = collect_closing_region(content_blocks)
    closing_text = " ".join(cb.get("base_narration") or "" for cb in closing_blocks)
    core_question_words = _content_words(blueprint.get("core_question", ""))
    recap_signal = any(kw in closing_text for kw in _RECAP_SIGNAL_KEYWORDS) or bool(
        core_question_words & _content_words(closing_text)
    )
    return "pass" if recap_signal else "warning"


def check_content_block_uniqueness_safe(content_blocks: list[dict]) -> str:
    """09-3: independent re-verification that no two direction-eligible blocks represent the same
    educational event -- doesn't rely on build_content_blocks having already deduplicated (a block
    list built or edited some other way is still checked), and respects an explicit
    direction_eligible=False marker (spec section 7) if one is present."""
    eligible = [b for b in content_blocks if b.get("direction_eligible", True)]
    for i in range(len(eligible)):
        for j in range(i + 1, len(eligible)):
            if _is_duplicate_candidate(eligible[i], eligible[j]):
                return "fail"
    return "pass"


# ---------------------------------------------------------------------------
# Script Integrity Check (14 items from the 09 spec, plus 09-1's narration_scope_safe, plus
# 09-2's format_neutrality_safe, plus 09-3's content_block_uniqueness_safe)
# ---------------------------------------------------------------------------

def run_script_integrity_check(
    blueprint: dict, title: str, thumbnail_text: str, script: dict, script_text: str,
    content_blocks: list[dict] | None = None,
) -> dict:
    checks = {}
    if content_blocks is None:
        content_blocks = build_content_blocks(blueprint, script)

    # 1 & 2: structurally guaranteed -- title/thumbnail are copied verbatim from the Blueprint
    # row and never exposed to Gemini as writable fields, so there's no path for them to drift.
    checks["title_preserved"] = "pass"
    checks["thumbnail_preserved"] = "pass"

    core_answer_words = _content_words(blueprint.get("core_answer", ""))
    narration_words = _content_words(" ".join(_narration_texts(script)))
    checks["answers_core_question"] = "pass" if core_answer_words and (core_answer_words & narration_words) else "warning"

    checks["promise_matches_scope"] = check_promise_matches_scope(blueprint)

    ladder_words = [e.get("word") for e in (blueprint.get("example_ladder") or []) if e.get("word")]
    if ladder_words:
        indices = []
        search_from = 0
        preserved = True
        for word in ladder_words:
            idx = script_text.lower().find(word.lower(), search_from)
            if idx == -1:
                preserved = False
                break
            indices.append(idx)
            search_from = idx + 1
        checks["example_ladder_preserved"] = "pass" if preserved and indices == sorted(indices) else "fail"
    else:
        checks["example_ladder_preserved"] = "warning"

    section_texts = []
    for s in script.get("sections") or []:
        section_texts.append(" ".join(str(b.get("text") or "") for b in s.get("beats") or []))
    checks["phoneme_explanation_safe"] = _phoneme_safe_over_texts(section_texts or [script_text])

    # 09-3: check per-block (same granularity as phoneme_explanation_safe above), not one giant
    # joined blob -- scope established once in a section's opening sentence ("BAG에서 소리를
    # 살펴봅니다. 이 단어에서 B는 /b/...") must cover that section's later sentences too, but must
    # not leak across sections. Core Answer is included as its own item -- it previously sat
    # outside every check's range, which is how "각 글자가 내는 고유한 소리" slipped past undetected.
    scope_safe_items = [
        _block_narration((script.get("opening") or {}).get("beats")),
        *section_texts,
        _block_narration(script.get("mini_success_beats")),
        _block_narration((script.get("ending") or {}).get("beats")),
        str(blueprint.get("core_answer") or ""),
    ]
    checks["example_scope_safe"] = _scope_safe_over_texts(scope_safe_items)

    body_text = " ".join(_narration_texts(script, include_ending=False))
    scope_creep = False
    for out_item in blueprint.get("scope_out") or []:
        out_words = _content_words(str(out_item))
        if out_words and out_words.issubset(_content_words(body_text)):
            scope_creep = True
            break
    checks["no_scope_creep"] = "fail" if scope_creep else "pass"

    checks["mini_success_present"] = check_mini_success_present(blueprint, script, content_blocks)
    checks["mini_success_answer_barrier_safe"] = check_mini_success_answer_barrier_safe(script, content_blocks)

    all_narration = " ".join(_narration_texts(script))
    sentences = [s for s in re.split(r"[.!?\n]", all_narration) if s.strip()]
    visual_dependent_count = sum(1 for s in sentences if any(p in s for p in _VISUAL_DEPENDENT_PHRASES))
    visual_ratio = (visual_dependent_count / len(sentences)) if sentences else 0.0
    checks["audio_first_usable"] = "pass" if visual_ratio <= 0.2 else "warning" if visual_ratio <= 0.4 else "fail"

    checks["no_false_guarantee"] = "fail" if any(
        kw in all_narration for kw in (*_OVERGENERALIZATION_KEYWORDS, *_LEARNING_OUTCOME_EXAGGERATION_PHRASES)
    ) else "pass"

    # 09-1/09-2: narration_scope_safe -- catches scope-overreach phrasing ("어떤 단어도 읽을 수
    # 있습니다", "모든 3글자 영어 단어를 읽을 수 있습니다") anywhere in the narration, including at
    # the very end where an over-broad send-off is just as misleading as one mid-body.
    checks["narration_scope_safe"] = "fail" if (
        any(p in all_narration for p in _NARRATION_SCOPE_OVERREACH_PHRASES)
        or _NARRATION_SCOPE_OVERREACH_RE.search(all_narration)
    ) else "pass"

    checks["no_unverified_rule"] = script.get("no_unverified_rule_self_check", "warning")

    ipa_status = script.get("ipa_not_memorization_self_check", "warning")
    if _MEMORIZATION_NEAR_IPA_RE.search(all_narration):
        ipa_status = "fail"
    checks["ipa_not_taught_as_memorization"] = ipa_status

    checks["ending_resolves_opening"] = check_ending_resolves_opening(blueprint, content_blocks)

    # 09-2: format_neutrality_safe -- 09 must not smuggle in production/format decisions.
    checks["format_neutrality_safe"] = check_format_neutrality_safe(content_blocks)

    # 09-3: content_block_uniqueness_safe -- a critical check, so a duplicate slipping through
    # (however it got there) blocks ready_for_direction just like any other fail.
    checks["content_block_uniqueness_safe"] = check_content_block_uniqueness_safe(content_blocks)

    # 09-4: practice_mini_success_progression_safe -- same target word in PRACTICE and
    # MINI_SUCCESS is a legitimate GUIDED -> INDEPENDENT progression, not automatic duplication;
    # this only fails when scaffold doesn't actually decrease (spec sections 8-12).
    checks["practice_mini_success_progression_safe"] = check_practice_mini_success_progression_safe(content_blocks)

    return checks


def ready_for_production_gate(checks: dict, script_score: float) -> bool:
    no_fail = not any(status == "fail" for status in checks.values())
    return no_fail and script_score >= READY_FOR_PRODUCTION_SCORE_THRESHOLD


# 09-2: same gate, new name -- "ready_for_direction" is the real source of truth going forward
# (spec section 19); ready_for_production_gate is kept and still populates the legacy field.
ready_for_direction_gate = ready_for_production_gate


# ---------------------------------------------------------------------------
# Scores (6 components + weighted total, spec section 30 weights)
# ---------------------------------------------------------------------------

DEFAULT_SCRIPT_SCORE_WEIGHTS = {
    "hook": 0.15,
    "clarity": 0.20,
    "scope_alignment": 0.20,
    "example_alignment": 0.20,
    "audio_first": 0.10,
    "retention": 0.15,
}


def compute_hook_score(blueprint: dict, script: dict) -> float:
    opening_text = " ".join(
        str(b.get("text") or "") for b in (script.get("opening") or {}).get("beats") or []
    )
    if not opening_text:
        return 0.0

    score = 0.0
    contract = blueprint.get("viewer_contract") or {}
    problem_words = _content_words(contract.get("viewer_problem", ""))
    opening_words = _content_words(opening_text)
    if problem_words and (problem_words & opening_words):
        score += 35.0

    title_words = _content_words(blueprint.get("title", ""))
    if title_words and (title_words & opening_words):
        score += 20.0

    if not any(p in opening_text for p in _GENERIC_GREETING_PHRASES):
        score += 25.0

    promise_words = _content_words(contract.get("video_promise", ""))
    if promise_words and (promise_words & opening_words):
        score += 20.0

    return min(100.0, score)


def compute_clarity_score(script: dict) -> float:
    narration = " ".join(_narration_texts(script))
    sentences = [s.strip() for s in re.split(r"[.!?\n]", narration) if s.strip()]
    if not sentences:
        return 0.0

    avg_len = sum(len(s) for s in sentences) / len(sentences)
    length_score = 100.0 if avg_len <= 40 else 70.0 if avg_len <= 70 else 40.0

    jargon_hits = sum(1 for term in _JARGON_TERMS if term.lower() in narration.lower())
    jargon_score = 100.0 if jargon_hits == 0 else max(0.0, 100.0 - jargon_hits * 40.0)

    return round((length_score + jargon_score) / 2, 1)


def compute_scope_alignment_score(blueprint: dict, checks: dict) -> float:
    mapping = {"pass": 100.0, "warning": 60.0, "fail": 20.0}
    promise_score = mapping.get(checks.get("promise_matches_scope"), 60.0)
    scope_creep_score = mapping.get("fail" if checks.get("no_scope_creep") == "fail" else "pass", 100.0)
    narration_scope_score = mapping.get(checks.get("narration_scope_safe"), 100.0)
    return round((promise_score + scope_creep_score + narration_scope_score) / 3, 1)


def compute_example_alignment_score(blueprint: dict, checks: dict) -> float:
    ladder = blueprint.get("example_ladder") or []
    if not ladder:
        return 0.0
    base = 100.0 if checks.get("example_ladder_preserved") == "pass" else 30.0
    return base


def compute_audio_first_score(checks: dict) -> float:
    mapping = {"pass": 100.0, "warning": 60.0, "fail": 20.0}
    return mapping.get(checks.get("audio_first_usable"), 60.0)


def _section_has_retention_engagement(text: str) -> bool:
    """09-1: a section counts as retention-active if it has a real participatory device
    (prediction/challenge/open-loop phrasing), not only a bare '?'. This recognizes engagement
    that doesn't happen to end in a question mark (e.g. "이제 마지막은 여러분 차례입니다.")."""
    return "?" in text or any(p in text for p in _PARTICIPATORY_PHRASES)


def compute_retention_score(script: dict) -> float:
    sections = script.get("sections") or []
    if not sections:
        return 0.0
    active_sections = 0
    for s in sections:
        text = " ".join(str(b.get("text") or "") for b in s.get("beats") or [])
        if _section_has_retention_engagement(text):
            active_sections += 1
    ratio = active_sections / len(sections)
    # Log-normalize the raw active-section count too, so more sections with engagement doesn't
    # linearly dominate the score just because there are more of them -- and repeating the same
    # trivial "?" many times still only grows this sub-linearly, not proportionally.
    count_bonus = min(20.0, 20 * math.log1p(active_sections) / math.log1p(len(sections) or 1))
    return round(min(100.0, ratio * 80.0 + count_bonus), 1)


def compute_script_score(component_scores: dict, weights: dict = DEFAULT_SCRIPT_SCORE_WEIGHTS) -> float:
    total = sum(weights[k] * component_scores[k] for k in weights)
    return round(max(0.0, min(100.0, total)), 1)


# ---------------------------------------------------------------------------
# Orchestration + report
# ---------------------------------------------------------------------------

def _fmt(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)


def build_script(
    db_path: Path, gemini: GeminiClient | None, channel_cfg: dict, *, blueprint_id: int | None = None, max_output_tokens: int = 8000
) -> dict:
    row = select_target_blueprint(db_path, blueprint_id=blueprint_id)
    if row is None:
        raise ValueError("No production_blueprints row with ready_for_script=1 (or no such blueprint_id). Run `research blueprint` first.")

    blueprint = _load_blueprint(row)
    blueprint["title"] = row["title"]
    blueprint["thumbnail_text"] = row["thumbnail_text"]

    script, generation_method = generate_script_content(blueprint, gemini, channel_cfg, max_output_tokens=max_output_tokens)
    script_text = render_script_text(script)
    content_blocks = build_content_blocks(blueprint, script)

    checks = run_script_integrity_check(blueprint, row["title"], row["thumbnail_text"], script, script_text, content_blocks)

    hook_score = compute_hook_score(blueprint, script)
    clarity_score = compute_clarity_score(script)
    scope_alignment_score = compute_scope_alignment_score(blueprint, checks)
    example_alignment_score = compute_example_alignment_score(blueprint, checks)
    audio_first_score = compute_audio_first_score(checks)
    retention_score = compute_retention_score(script)

    script_score = compute_script_score(
        {
            "hook": hook_score,
            "clarity": clarity_score,
            "scope_alignment": scope_alignment_score,
            "example_alignment": example_alignment_score,
            "audio_first": audio_first_score,
            "retention": retention_score,
        }
    )

    ready = ready_for_production_gate(checks, script_score)
    if generation_method == "fallback":
        ready = False
    # 09-2: ready_for_direction is the real source of truth going forward; ready_for_production
    # is kept identical for backward compatibility (spec section 19).
    ready_for_direction = ready

    duration_seconds, word_count = estimate_duration_and_words(script_text)

    return {
        "blueprint_row": row,
        "blueprint": blueprint,
        "script": script,
        "script_text": script_text,
        "content_blocks": content_blocks,
        "generation_method": generation_method,
        "estimated_duration_seconds": duration_seconds,
        "estimated_word_count": word_count,
        "hook_score": hook_score,
        "clarity_score": clarity_score,
        "scope_alignment_score": scope_alignment_score,
        "example_alignment_score": example_alignment_score,
        "audio_first_score": audio_first_score,
        "retention_score": retention_score,
        "script_score": script_score,
        "integrity_checks": checks,
        "ready_for_production": ready,
        "ready_for_direction": ready_for_direction,
    }


# ---------------------------------------------------------------------------
# 09-4 section 25-26: re-evaluates an already-persisted video_scripts row against the current
# validation logic -- read-only, no Gemini call, no DB write -- so a Gate-logic fix can be verified
# against real, previously-generated content without risking a fresh Gemini call rewording the
# narration (which would defeat verifying that the fix judges *this* content correctly).
# ---------------------------------------------------------------------------

def recheck_script_integrity(db_path: Path, script_row: dict) -> dict:
    with connect(db_path) as conn:
        blueprint_row = conn.execute(
            "SELECT * FROM production_blueprints WHERE id = ?", (script_row["blueprint_id"],)
        ).fetchone()
    blueprint = _load_blueprint(dict(blueprint_row))
    blueprint["title"] = script_row["title"]
    blueprint["thumbnail_text"] = script_row["thumbnail_text"]

    script = json.loads(script_row["script_json"])
    script_text = script_row["script_text"]
    content_blocks = json.loads(script_row["content_blocks_json"])

    checks = run_script_integrity_check(blueprint, script_row["title"], script_row["thumbnail_text"], script, script_text, content_blocks)

    hook_score = compute_hook_score(blueprint, script)
    clarity_score = compute_clarity_score(script)
    scope_alignment_score = compute_scope_alignment_score(blueprint, checks)
    example_alignment_score = compute_example_alignment_score(blueprint, checks)
    audio_first_score = compute_audio_first_score(checks)
    retention_score = compute_retention_score(script)
    script_score = compute_script_score({
        "hook": hook_score, "clarity": clarity_score, "scope_alignment": scope_alignment_score,
        "example_alignment": example_alignment_score, "audio_first": audio_first_score, "retention": retention_score,
    })

    ready = ready_for_production_gate(checks, script_score)
    if script_row.get("generation_method") == "fallback":
        ready = False

    return {
        "integrity_checks": checks,
        "hook_score": hook_score,
        "clarity_score": clarity_score,
        "scope_alignment_score": scope_alignment_score,
        "example_alignment_score": example_alignment_score,
        "audio_first_score": audio_first_score,
        "retention_score": retention_score,
        "script_score": script_score,
        "ready_for_production": ready,
        "ready_for_direction": ready,
    }


def _persist(db_path: Path, result: dict, report_path: str) -> None:
    row = result["blueprint_row"]
    blueprint = result["blueprint"]
    contract = blueprint.get("viewer_contract") or {}
    topic_candidate_id = _topic_candidate_id_for_package(
        db_path, row.get("category"), row.get("problem_id")
    )
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO video_scripts (report_path, blueprint_id, package_id, topic_candidate_id,
                title, thumbnail_text, viewer_problem, video_promise, expected_transformation,
                core_question, core_answer, script_json, script_text, estimated_duration_seconds,
                estimated_word_count, hook_score, clarity_score, scope_alignment_score,
                example_alignment_score, audio_first_score, retention_score, script_score,
                integrity_json, ready_for_production, generation_method, content_blocks_json,
                ready_for_direction)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report_path, row["id"], row.get("package_id"), topic_candidate_id,
                row["title"], row["thumbnail_text"], contract.get("viewer_problem"),
                contract.get("video_promise"), contract.get("expected_transformation"),
                blueprint.get("core_question"), blueprint.get("core_answer"),
                json.dumps(result["script"], ensure_ascii=False), result["script_text"],
                result["estimated_duration_seconds"], result["estimated_word_count"],
                result["hook_score"], result["clarity_score"], result["scope_alignment_score"],
                result["example_alignment_score"], result["audio_first_score"], result["retention_score"],
                result["script_score"], json.dumps(result["integrity_checks"], ensure_ascii=False),
                1 if result["ready_for_production"] else 0, result["generation_method"],
                json.dumps(result["content_blocks"], ensure_ascii=False),
                1 if result["ready_for_direction"] else 0,
            ),
        )


def build_script_report(
    db_path: Path,
    reports_dir: Path,
    gemini: GeminiClient | None,
    channel_cfg: dict,
    *,
    blueprint_id: int | None = None,
    max_output_tokens: int = 8000,
) -> Path:
    result = build_script(db_path, gemini, channel_cfg, blueprint_id=blueprint_id, max_output_tokens=max_output_tokens)
    row = result["blueprint_row"]
    blueprint = result["blueprint"]
    contract = blueprint.get("viewer_contract") or {}
    content_blocks = result["content_blocks"]

    lines: list[str] = []
    lines.append("# Content Script")
    lines.append("")
    lines.append(f"생성일: {date.today().isoformat()}")
    lines.append(f"Generation Method: {result['generation_method']}")
    lines.append("")

    lines.append("## Viewer Contract")
    lines.append("")
    lines.append(f"Title: {row['title']}")
    lines.append(f"Thumbnail: {row['thumbnail_text']}")
    lines.append(f"Viewer Problem: {contract.get('viewer_problem')}")
    lines.append(f"Click Expectation: {contract.get('click_expectation')}")
    lines.append(f"Video Promise: {contract.get('video_promise')}")
    lines.append(f"Expected Transformation: {contract.get('expected_transformation')}")
    lines.append("")

    lines.append("## Core Question")
    lines.append("")
    lines.append(str(blueprint.get("core_question")))
    lines.append("")

    lines.append("## Core Answer")
    lines.append("")
    lines.append(str(blueprint.get("core_answer")))
    lines.append("")

    lines.append("## Learning Objectives")
    lines.append("")
    for obj in blueprint.get("learning_objectives") or []:
        lines.append(f"- {obj}")
    lines.append("")

    lines.append("## Scope")
    lines.append("")
    lines.append(f"IN: {blueprint.get('scope_in')}")
    lines.append(f"OUT: {blueprint.get('scope_out')}")
    lines.append(f"Estimated Duration: {_fmt(result['estimated_duration_seconds'])}초 (추정값, 실측 TTS 아님)")
    lines.append(f"Estimated Word Count: {result['estimated_word_count']}")
    lines.append("")

    lines.append("## Content Blocks")
    lines.append("")
    lines.append(
        "각 Block은 '무엇을 가르쳐야 하는가'만 정의한다. 포맷/연출 결정(EDUCATION/CLIP "
        "ANALYSIS/HYBRID/PODCAST 및 카메라/편집 지시)은 이 단계에서 하지 않는다."
    )
    lines.append("")
    for block in content_blocks:
        lines.append(f"### {block['content_block_id']} (Section {block.get('section_number')})")
        lines.append("")
        lines.append(f"Learning Function: {block['learning_function']}")
        lines.append(f"Purpose: {block['purpose']}")
        lines.append(f"Required Content: {block['required_content']}")
        lines.append(f"Importance: {block['importance']}")
        lines.append(f"Prerequisite Blocks: {block['prerequisite_blocks']}")
        lines.append(f"Viewer Action: {block['viewer_action']}")
        lines.append(f"Thinking Time: {block['thinking_time_seconds']}s")
        lines.append(f"Retention Intent: {block['retention_intent']}")
        lines.append(f"Media Affinity: {block['media_affinity']}")
        lines.append(f"Base Narration: {block['base_narration']}")
        lines.append("")

    lines.append("## Example Ladder")
    lines.append("")
    for e in blueprint.get("example_ladder") or []:
        lines.append(
            f"Level {e.get('level')}: {e.get('word')} — {e.get('target_pattern')} "
            f"({e.get('purpose')}, difficulty={e.get('difficulty')}, exception_risk={e.get('exception_risk')})"
        )
    lines.append("")

    lines.append("## Mini Success")
    lines.append("")
    mini = blueprint.get("mini_success") or {}
    lines.append(f"{mini.get('description')} (단어: {mini.get('prompt_word')}, 생각 시간: {mini.get('think_seconds')}초)")
    for b in result["script"].get("mini_success_beats") or []:
        lines.append(f"[{b.get('type')}] {b.get('text')}")
    lines.append("")

    lines.append("## Educational Integrity Check")
    lines.append("")
    for check, status in result["integrity_checks"].items():
        if check in ("format_neutrality_safe", "content_block_uniqueness_safe"):
            continue
        lines.append(f"- {check}: {status}")
    lines.append("")

    lines.append("## Format Neutrality Check")
    lines.append("")
    lines.append(f"- format_neutrality_safe: {result['integrity_checks'].get('format_neutrality_safe')}")
    lines.append(f"- content_block_uniqueness_safe: {result['integrity_checks'].get('content_block_uniqueness_safe')}")
    lines.append("")

    lines.append("## Script/Content Score")
    lines.append("")
    lines.append(f"Hook: {_fmt(result['hook_score'])} / Clarity: {_fmt(result['clarity_score'])} / "
                  f"Scope Alignment: {_fmt(result['scope_alignment_score'])} / "
                  f"Example Alignment: {_fmt(result['example_alignment_score'])} / "
                  f"Audio-first: {_fmt(result['audio_first_score'])} / Retention: {_fmt(result['retention_score'])}")
    lines.append(f"Total: {_fmt(result['script_score'])}/100")
    lines.append("")

    lines.append("## Ready for Direction")
    lines.append("")
    lines.append("YES" if result["ready_for_direction"] else "NO")
    lines.append(f"(하위 호환: ready_for_production = {'YES' if result['ready_for_production'] else 'NO'})")
    lines.append("")

    reports_dir.mkdir(parents=True, exist_ok=True)
    out_path = reports_dir / f"script_{date.today().isoformat()}.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")

    _persist(db_path, result, str(out_path))

    return out_path
