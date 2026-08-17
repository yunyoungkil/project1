# 09-2단계: 포맷 중립 Content Script 교정

현재 프로젝트의 09단계 대본 작성 시스템을 수정한다.

이번 작업의 목적은 09단계에서 특정 영상 포맷과 제작 연출을 결정하지 않고,
교육적으로 검증된 "무엇을 전달해야 하는가"를 Content Script 형태로 생성하도록
책임을 재정의하는 것이다.

중요:
이번 작업은 09단계를 새로 만드는 작업이 아니다.
현재 09 및 09-1에서 완성된 교육 정확성, Scope 보호, 발음 보호,
Example Ladder, Mini Success, Retention 개선을 모두 보존한 상태에서
"Content와 Production Direction의 책임 분리"만 수행한다.

최종 구조는 다음을 목표로 한다.

08 Production Blueprint
        ↓
09 Content Script
   "무엇을 전달할 것인가?"
        ↓
10 Video Director
   "어떻게 보여주고 들려줄 것인가?"
        ↓
 ┌─────────────┬───────────────┬──────────┬──────────┐
 │ EDUCATION   │ CLIP ANALYSIS │ HYBRID   │ PODCAST  │
 └─────────────┴───────────────┴──────────┴──────────┘
        ↓
Production Script / Scene Spec
        ↓
실제 제작 엔진


==================================================
0. 먼저 현재 구현을 조사하라
==================================================

코드를 수정하기 전에 반드시 다음을 확인한다.

- research/script_writer.py
- research/production_blueprint.py
- research/db.py
- research/cli.py
- config/research_config.yaml
- tests/test_script_writer.py
- tests/test_production_blueprint.py

그리고 현재 video_scripts 테이블 구조,
09단계 JSON 구조,
Integrity Check,
Script Score,
ready_for_production 판정,
Gemini prompt,
fallback,
report 생성 방식을 먼저 파악한다.

기존 동작을 추측해서 수정하지 않는다.

특히 현재 09-1에서 통과한 261개 테스트를 기준선으로 삼는다.

기존 기능을 불필요하게 리팩터링하지 않는다.


==================================================
1. 09단계의 책임을 재정의한다
==================================================

기존 09의 개념:

Production Blueprint
→ 완성된 영상 나레이션
→ Ready for Production

수정 후:

Production Blueprint
→ Format-neutral Content Script
→ Ready for Direction

09단계가 답해야 하는 질문은 오직:

"What must this video teach/say?"

이다.

09단계가 다음 질문에는 답하지 않아야 한다.

"How should this be visually/audio produced?"

다음 제작 결정은 10단계의 책임이다.

- EDUCATION
- CLIP ANALYSIS
- HYBRID
- PODCAST

09에서는 위 4개 중 어떤 것도 선택하지 않는다.


==================================================
2. 기존 핵심 구조는 반드시 보존한다
==================================================

다음 항목은 삭제하거나 약화하지 않는다.

- Viewer Problem
- Viewer Contract
- Core Question
- Core Answer
- Video Promise
- Expected Transformation
- Learning Objectives
- Scope IN
- Scope OUT
- Opening Hook의 문제 제기 목적
- Example Ladder
- BAG → BAT → MAP → CAP 순서
- Mini Success
- thinking time
- 발음 정확성
- IPA 기반 음소 설명
- 고정 한글 등가 표기 금지
- 같은 단어의 복수 한글 발음 표기 금지
- example scope 제한
- 과잉 일반화 방지
- false guarantee 방지
- Retention intent
- Ending에서 Core Question 해결

현재 09-1의 Integrity Check도 의미를 약화시키지 않는다.


==================================================
3. Content Block 구조를 추가한다
==================================================

현재 Section 구조를 완전히 삭제하지 않는다.

Section을 기반으로 Content Block을 생성하도록 확장한다.

각 Content Block은 최소 다음 정보를 가져야 한다.

{
  "content_block_id": "CB01",
  "section_number": 1,
  "learning_function": "...",
  "purpose": "...",

  "required_content": [],

  "importance": "required|supporting",

  "prerequisite_blocks": [],

  "viewer_action": null,

  "thinking_time_seconds": 0,

  "retention_intent": {
      "type": "...",
      "purpose": "..."
  },

  "media_affinity": {
      "visualization": "low|medium|high",
      "real_world_clip": "low|medium|high",
      "dialogue": "low|medium|high",
      "audio_demonstration": "low|medium|high",
      "replay": "low|medium|high",
      "comparison": "low|medium|high",
      "interaction": "low|medium|high",
      "storytelling": "low|medium|high"
  },

  "base_narration": "...",

  "format_neutral": true
}

필드명은 현재 코드 구조와 충돌한다면 최소 조정 가능하지만,
의미는 보존해야 한다.


==================================================
4. learning_function taxonomy
==================================================

learning_function은 무제한 자유 텍스트로 만들지 말고
고정 taxonomy를 사용한다.

최소 다음을 지원한다.

- PROBLEM_RECOGNITION
- CORE_EXPLANATION
- DEMONSTRATION
- REINFORCEMENT
- CONTRAST
- TRANSFER
- PRACTICE
- MINI_SUCCESS
- RECAP
- RESOLUTION

필요하다면 OTHER를 추가할 수 있다.

Gemini가 taxonomy 밖의 값을 반환하면
OTHER 또는 결정론적 fallback으로 처리한다.

파이프라인을 중단시키지 않는다.


==================================================
5. required_content
==================================================

각 Block에는 해당 Block에서 반드시 전달되어야 할
교육 내용이 명시되어야 한다.

예:

BAG Block

required_content:
- BAG
- B /b/
- A /æ/
- G /g/
- 알파벳 이름과 단어에서 사용하는 소리는 다를 수 있음
- 단어 읽기에서는 각 소리를 이어 붙임

중요:

required_content는 제작 지시가 아니다.

Bad:
- BAG를 화면 중앙에 크게 표시
- B를 빨간색으로 Highlight
- waveform 재생

Good:
- BAG를 예시로 사용
- /b/ /æ/ /g/ 음소를 제시
- 세 소리를 연결하는 원리를 설명


==================================================
6. viewer_action / thinking_time 분리
==================================================

교육적으로 필요한 시청자 행동은 09에 남긴다.

예:

viewer_action:
"정답 공개 전에 CAP을 직접 읽어본다"

thinking_time_seconds:
3

하지만 다음과 같은 Production 표현은 09에서 만들지 않는다.

- 화면을 3초 정지한다
- 점 3개 animation을 표시한다
- waveform을 멈춘다
- karaoke highlight를 정지한다

09는 "3초 생각 시간이 필요하다"까지만 정의한다.

실제로 그 3초를 어떻게 시각/음향적으로 표현할지는
10 이후 단계에서 결정한다.


==================================================
7. Retention 문장과 Retention Intent를 분리한다
==================================================

현재 09-1의 Retention 개선을 보존한다.

다만 실제 문장과 목적을 분리한다.

예:

retention_intent:
{
  "type": "prediction",
  "purpose": "다음 예시에서도 같은 원리가 유지되는지 예상하게 한다"
}

base_narration:
"그럼 끝 글자만 바꾸면 어떻게 될까요?"

또 다른 예:

retention_intent:
{
  "type": "challenge",
  "purpose": "시청자가 CAP을 정답 공개 전에 직접 읽도록 한다"
}

이 구조를 사용한다.

질문형 문장을 억지로 모든 Block에 넣지 않는다.

Retention은 질문 개수가 아니라
학습 참여와 다음 내용에 대한 기대를 만드는 것이 목적이다.


==================================================
8. media_affinity를 추가한다
==================================================

각 Content Block은 다음 신호를 가질 수 있다.

visualization
real_world_clip
dialogue
audio_demonstration
replay
comparison
interaction
storytelling

값:

low
medium
high

중요:

media_affinity는 "추천 포맷"이 아니다.

예:

real_world_clip = high

라고 해서

format = CLIP_ANALYSIS

라고 결정해서는 안 된다.

09는 Evidence/Signal만 생성한다.

10 Video Director가 전체 Content Script와
실제 사용 가능한 자료를 보고 포맷을 결정한다.


==================================================
9. 09에서 금지되는 포맷 결정
==================================================

09 출력에 다음과 같은 필드를 만들지 않는다.

recommended_format
selected_format
video_format
production_format

또는 동일 의미의 필드.

또한 Gemini prompt에서도

"EDUCATION/CLIP ANALYSIS/HYBRID/PODCAST 중 선택하라"

라고 지시하지 않는다.

이 결정은 10단계의 책임이다.


==================================================
10. Clip Requirement도 09에서 만들지 않는다
==================================================

09에서 실제 외부 클립 검색 요구사항을 만들지 않는다.

예:

Bad:

clip_requirement:
"미드에서 What are you doing?이라고 말하는 장면 검색"

Bad:

required_clip:
"원어민이 빠르게 What are you를 말하는 영상"

09에서 허용되는 것은:

real_world_clip: high
audio_demonstration: high
replay: high

정도이다.

실제 Clip Requirement 생성은
10단계가 CLIP ANALYSIS 또는 HYBRID를 선택한 뒤 수행한다.


==================================================
11. Podcast 대사도 09에서 만들지 않는다
==================================================

09는 Mia / Leo 같은 화자를 생성하지 않는다.

다음과 같은 출력 금지:

Mia:
Leo:
Host:
Guest:

09는 대화형 표현 가능성만

dialogue: high

처럼 전달한다.

PODCAST가 선택될 경우
10단계에서 Content Block을 실제 화자 대화로 변환한다.


==================================================
12. Production-specific visual instruction 금지
==================================================

09 Content Script에서 다음 종류의 지시를 제거하거나 생성하지 않는다.

- 화면 왼쪽/오른쪽
- 중앙 배치
- Zoom
- Camera
- Cut
- Transition
- B-roll
- waveform
- ripple
- karaoke highlight
- subtitle position
- font
- color
- animation
- speaker avatar
- character movement
- clip playback
- replay speed
- slow motion
- split screen

단, 교육적으로 필요한 "예시를 제시한다",
"비교한다", "다시 들려줄 가치가 높다" 등의 의미는 허용한다.


==================================================
13. base_narration은 유지한다
==================================================

현재 09가 만드는 좋은 나레이션을 폐기하지 않는다.

각 Content Block에 base_narration을 저장한다.

base_narration의 의미:

"교육적으로 검증된 기본 설명 표현"

이지

"최종 영상에서 반드시 그대로 읽어야 하는 Production Script"

가 아니다.

10단계는 필요에 따라 이를:

EDUCATION narration
CLIP ANALYSIS commentary
HYBRID narration
PODCAST dialogue

등으로 변환할 수 있어야 한다.

단, 변환 시 required_content와 Scope/Integrity를 잃어서는 안 된다.


==================================================
14. Format Neutrality Integrity Check 추가
==================================================

기존 Integrity Check를 삭제하지 말고 신규 체크:

format_neutrality_safe

를 추가한다.

목적:

09 Content Script가 특정 제작 형식을 강제로 전제하는지 검사한다.

예:

FAIL 후보:

"화면 왼쪽에 BAG를 보여줍니다."
"여기서 영화 클립을 재생합니다."
"Mia가 질문합니다."
"카메라를 확대합니다."
"자막을 노란색으로 바꿉니다."
"waveform을 멈춥니다."
"B-roll을 삽입합니다."

PASS:

"BAG를 예시로 제시한다."
"CAP을 직접 읽어보도록 한다."
"정답 공개 전에 3초 생각 시간을 제공한다."
"실제 발화 사례가 있으면 이해에 도움이 되는 내용이다."
"소리 비교가 중요한 Block이다."

가능하면 결정론적 keyword/pattern 검사를
백스톱으로 구현한다.

Gemini 자가평가만 신뢰하지 않는다.

단, 지나치게 넓은 단어 하나만으로 fail시키지 말고
production-specific context를 탐지하도록 한다.


==================================================
15. Existing Integrity Checks 보존
==================================================

현재 09-1에서 존재하는 15개 Integrity Check의 의미와
동작을 유지한다.

현재 체크:

- title_preserved
- thumbnail_preserved
- answers_core_question
- promise_matches_scope
- example_ladder_preserved
- phoneme_explanation_safe
- example_scope_safe
- no_scope_creep
- narration_scope_safe
- mini_success_present
- audio_first_usable
- no_false_guarantee
- no_unverified_rule
- ipa_not_taught_as_memorization
- ending_resolves_opening

여기에:

- format_neutrality_safe

를 추가한다.

총 16개가 되는 것이 예상되지만,
실제 코드에 현재 체크 수/이름이 다르면
현재 구현을 source of truth로 확인 후 보고한다.


==================================================
16. Audio-first 의미를 잘못 제거하지 않는다
==================================================

audio_first_usable은 유지한다.

하지만 이것이 영상 포맷 선택이라고 해석해서는 안 된다.

Audio-first는 우리 채널의 콘텐츠 접근성/교육 전달 원칙이다.

즉:

화면을 보지 않아도 핵심 설명을 이해할 수 있는가?

를 검사한다.

이는 EDUCATION / CLIP ANALYSIS / HYBRID / PODCAST
어느 포맷에도 적용될 수 있다.


==================================================
17. BAG/BAT/MAP/CAP 회귀 금지
==================================================

현재 실제 Blueprint/Script의 Example Ladder:

BAG
→ BAT
→ MAP
→ CAP

순서를 그대로 보존한다.

특히:

BAG
B /b/ + A /æ/ + G /g/

BAT
B /b/ + A /æ/ + T /t/

MAP
M /m/ + A /æ/ + P /p/

CAP
C /k/ + A /æ/ + P /p/

방식의 음소 중심 설명을 유지한다.

고정 한글 등가 발음으로 되돌아가면 안 된다.

"이 단어 CAP에서는 C가 /k/ 소리를 냅니다"

처럼 예시 범위를 제한하는 원칙도 유지한다.


==================================================
18. Video Promise Scope 유지
==================================================

현재 교정된 Promise의 범위를 유지한다.

예:

"단모음 a가 들어간 3글자 단어(CVC)를
소리 조합으로 읽는 기본 원리를 이해한다"

수준이어야 한다.

다음과 같은 표현으로 확대하지 않는다.

- 모든 영어 단어
- 어떤 단어든
- 이제 영어를 다 읽는다
- 무조건 읽을 수 있다
- 완벽하게 읽는다

Content Block으로 구조를 바꾸면서
Scope 보호가 약해져서는 안 된다.


==================================================
19. 상태를 Ready for Direction으로 변경한다
==================================================

09의 최종 성공 상태 개념을:

Ready for Production

에서

Ready for Direction

으로 변경한다.

의미:

Content Script가 교육적으로 완성되어
10 Video Director가 포맷 및 제작 방식을 결정할 준비가 됨.

가능하면 DB에 명시적:

ready_for_direction

필드를 추가한다.

기존 ready_for_production 필드는
하위 호환성/기존 데이터 때문에 즉시 삭제하지 않는다.

기존 CLI/테스트/데이터를 깨뜨리지 않는 방향을 우선한다.

09 신규 실행에서는 ready_for_direction이
실질적인 source of truth가 되도록 한다.

ready_for_production의 최종 판정은
향후 10단계 이후의 책임으로 넘길 수 있도록 구조를 준비한다.

단, 아직 10단계를 구현하지 않는다.


==================================================
20. DB 변경
==================================================

현재 video_scripts 테이블을 조사한 뒤
최소 변경으로 필요한 데이터를 저장한다.

가능한 방법:

A.
video_scripts에 content_blocks_json,
ready_for_direction 등의 컬럼 추가

또는

B.
별도 content_script_blocks 테이블 추가

둘 중 현재 프로젝트 구조에 더 안전하고 단순한 방식을 선택한다.

불필요한 대규모 migration을 하지 않는다.

기존 DB가 그대로 열려야 한다.

기존 video_scripts 데이터도 깨지면 안 된다.


==================================================
21. CLI 하위 호환
==================================================

현재:

python -m research.cli script

관련 명령의 기존 사용법을 깨지 않는다.

새로운 필수 인자를 추가하지 않는다.

기존:

python -m research.cli script --blueprint-id ID

가 있다면 그대로 동작해야 한다.

09-2 실행 결과가 Content Script 구조로 저장/리포트되도록 내부 동작만 확장한다.


==================================================
22. Gemini Prompt 수정
==================================================

Gemini에게 명시적으로 다음 원칙을 준다.

"You are writing a format-neutral educational Content Script,
not a final production script."

그리고:

Do NOT choose:
- EDUCATION
- CLIP ANALYSIS
- HYBRID
- PODCAST

Do NOT create:
- camera directions
- visual layout
- subtitle styling
- animation instructions
- B-roll instructions
- actual clip requirements
- podcast speakers/dialogue roles
- editing instructions

Instead define:

- what must be taught
- why the block exists
- required educational content
- viewer action
- thinking time
- retention intent
- base narration
- media affinity signals

또한 기존 09-1의:

- pronunciation accuracy
- phoneme-first explanation
- scope protection
- no false guarantee
- no overgeneralization
- example-specific sound claims

프롬프트를 그대로 보존한다.


==================================================
23. Gemini JSON 실패 fallback
==================================================

Gemini JSON 파싱 실패가 발생해도
파이프라인을 중단하지 않는다.

기존 fallback 정책을 유지한다.

단 fallback도 Content Block 구조를 반환해야 한다.

fallback이 교육적으로 충분하지 않다면
ready_for_direction=NO로 정직하게 판정한다.

Gemini 실패를 숨기거나
임의로 high-quality 결과로 처리하지 않는다.


==================================================
24. Score
==================================================

기존 Script Score:

Hook
Clarity
Scope Alignment
Example Alignment
Audio-first
Retention
Total

을 불필요하게 폐기하지 않는다.

이번 단계에서 점수 공식 전체를 새로 설계하지 않는다.

다만 필요하다면 Format Neutrality를
Integrity Gate로만 추가한다.

즉:

format_neutrality_safe = fail

이면

ready_for_direction = NO

가 되도록 한다.

점수를 억지로 조정해서 PASS시키지 않는다.


==================================================
25. Report 수정
==================================================

09 리포트에서 최소 다음을 확인할 수 있어야 한다.

# Content Script

## Viewer Contract

## Core Question

## Core Answer

## Learning Objectives

## Scope

## Content Blocks

각 Block에:

- Block ID
- Learning Function
- Purpose
- Required Content
- Viewer Action
- Thinking Time
- Retention Intent
- Media Affinity
- Base Narration

## Example Ladder

## Mini Success

## Educational Integrity Check

## Format Neutrality Check

## Script/Content Score

## Ready for Direction

기존 정보 중 중요한 내용을 삭제하지 않는다.


==================================================
26. 실제 BAG Content Script 기대 예
==================================================

예를 들어 CAP Block은 개념적으로 다음과 같아야 한다.

CB05

Learning Function:
PRACTICE / MINI_SUCCESS

Purpose:
앞에서 배운 sound blending 원리를
새 단어에 직접 적용하게 한다.

Required Content:
- CAP
- C /k/
- A /æ/
- P /p/
- 이 단어 CAP에서는 C가 /k/ 소리를 냄
- /k/ + /æ/ + /p/를 연결

Viewer Action:
정답 공개 전에 CAP을 직접 읽어본다.

Thinking Time:
3 seconds

Retention Intent:
challenge

Media Affinity:
visualization: high
real_world_clip: low
dialogue: medium
audio_demonstration: high
replay: medium
comparison: medium
interaction: high
storytelling: low

Base Narration:
현재 09-1에서 검증된 범위 안전한 설명.

Format Neutral:
true

중요:
이것은 예시 구조이지 문자열을 그대로 하드코딩하라는 뜻이 아니다.


==================================================
27. 10단계와의 인터페이스 준비
==================================================

아직 10 Video Director는 구현하지 않는다.

하지만 10이 다음 정보를 읽을 수 있도록
09 출력 구조를 명확하게 만든다.

10이 사용할 핵심 입력:

- Viewer Contract
- Core Question
- Core Answer
- Scope
- Content Blocks
- required_content
- viewer_action
- thinking_time_seconds
- retention_intent
- media_affinity
- base_narration
- Example Ladder
- Integrity results

10은 이를 기반으로 이후:

EDUCATION
CLIP ANALYSIS
HYBRID
PODCAST

중 하나를 결정하게 될 것이다.

따라서 09 출력은 특정 포맷에 종속되어서는 안 된다.


==================================================
28. 테스트
==================================================

기존 전체 테스트를 먼저 실행하고
수정 후 다시 실행한다.

최소 다음 신규 테스트를 추가한다.


CASE A — Format Neutral Education

입력:
"BAG를 예시로 /b/ /æ/ /g/를 설명한다."

기대:
format_neutrality_safe = pass


CASE B — Visual Direction Leakage

입력:
"화면 왼쪽에 BAG를 크게 표시한다."

기대:
format_neutrality_safe = fail


CASE C — Clip Direction Leakage

입력:
"여기서 영화 클립을 재생한다."

기대:
format_neutrality_safe = fail


CASE D — Podcast Leakage

입력:
"Mia가 질문하고 Leo가 설명한다."

기대:
format_neutrality_safe = fail


CASE E — Editing Direction Leakage

입력:
"CAP에서 화면을 확대하고 자막 색을 바꾼다."

기대:
format_neutrality_safe = fail


CASE F — Thinking Time

입력:
viewer_action = CAP 직접 읽기
thinking_time_seconds = 3

기대:
format neutral
교육 요구사항으로 정상 저장


CASE G — Media Affinity Is Not Format Selection

입력:
real_world_clip = high

기대:
selected_format/recommended_format 생성 안 됨
format_neutrality_safe = pass


CASE H — Dialogue Affinity Is Not Podcast

입력:
dialogue = high

기대:
Mia/Leo/Host 등 화자 생성 안 됨
PODCAST 자동 선택 안 됨


CASE I — Example Ladder Regression

BAG → BAT → MAP → CAP

순서와 음소 설명 그대로 보존.


CASE J — Pronunciation Regression

"BAG(백)"
"BAT(배트/뱃)"

등 기존 금지 패턴이 다시 나오면 fail.


CASE K — Scope Regression

"이제 모든 3글자 영어 단어를 읽을 수 있습니다."

기대:
narration_scope_safe 또는 관련 기존 체크 fail.


CASE L — Existing Integrity Checks

기존 15개 Integrity Check가 모두 유지되는지 확인.


CASE M — New Integrity Count

format_neutrality_safe가 전체 Integrity 결과에 포함되는지 확인.


CASE N — Ready for Direction

모든 critical check pass:
ready_for_direction = YES

format_neutrality_safe fail:
ready_for_direction = NO


CASE O — Gemini Fallback

Gemini unavailable/JSON parse fail 시:
Content Block fallback 생성
파이프라인은 중단되지 않음
품질 부족 시 ready_for_direction=NO


CASE P — DB Backward Compatibility

기존 video_scripts row가 있는 DB에서
schema initialization 및 신규 실행 정상.


CASE Q — CLI Backward Compatibility

기존 research script 명령 시그니처 정상.


CASE R — Previous Stage Immutable

05/06/07/08 데이터가 09-2 실행 전후 변경되지 않음.


==================================================
29. 절대 하지 말 것
==================================================

이번 작업에서 다음을 하지 않는다.

- 10 Video Director 구현
- 편집 도구 선택
- Remotion 구현
- CapCut 구현
- FFmpeg 구현
- TTS 엔진 선택
- 실제 YouTube/영화/TikTok/Instagram 클립 검색
- 외부 클립 다운로드
- 저작권 판단 시스템 구현
- EDUCATION 제작 문법 구현
- CLIP ANALYSIS 제작 문법 구현
- HYBRID 제작 문법 구현
- PODCAST 제작 문법 구현
- 썸네일 제작
- 실제 영상 렌더링

이번 작업은 오직:

"09를 Format-neutral Content Script 계층으로 교정"

하는 작업이다.


==================================================
30. YouTube API
==================================================

이번 단계에서 새 YouTube API 호출은 필요 없다.

08 및 기존 DB 산출물을 재사용한다.

불필요한 search/list 호출을 절대 추가하지 않는다.

실행 후 API quota 사용 여부를 보고한다.


==================================================
31. 완료 후 실제 재생성
==================================================

테스트만 통과시키고 끝내지 않는다.

현재 최신 ready Blueprint를 대상으로
09 Content Script를 실제로 1회 재생성한다.

현재 BAG/BAT/MAP/CAP Blueprint가 선택되는지 확인한다.

실제 생성 결과에서 다음을 육안 검증한다.

- BAG/BAT/MAP/CAP 보존
- 음소 설명 보존
- Scope 보존
- Mini Success 보존
- thinking time 3초 보존
- Retention Intent 생성
- Content Block 생성
- media_affinity 생성
- base_narration 생성
- 특정 포맷 선택 없음
- 제작 지시 없음
- format_neutrality_safe pass
- ready_for_direction YES


==================================================
32. 완료 보고 형식
==================================================

작업 완료 후 아래 형식으로 보고하라.

1. 수정/추가한 파일

2. 09단계 책임이 어떻게 변경되었는가

3. Content Block 구조

4. 생성된 Content Block 수

5. 각 Block의 learning_function

6. required_content가 어떻게 저장되는가

7. viewer_action / thinking_time 처리 방식

8. Retention Intent 처리 방식

9. media_affinity 구조와 실제 결과

10. EDUCATION/CLIP ANALYSIS/HYBRID/PODCAST를
    09가 선택하지 않는다는 것을 어떻게 보장했는가

11. Clip Requirement가 생성되지 않는지 확인

12. Podcast 화자/대사가 생성되지 않는지 확인

13. Production-specific visual/editing instruction이
    생성되지 않는지 확인

14. base_narration 보존 방식

15. format_neutrality_safe 구현 방식과 실제 결과

16. 기존 Integrity Check 보존 결과

17. 전체 Integrity Check 결과

18. BAG/BAT/MAP/CAP 보존 결과

19. 발음 정확성 회귀 여부

20. Scope/Promise 회귀 여부

21. 수정 전/후 Script 또는 Content Score
    (공식이 변경되지 않았다면 그대로 명시)

22. Ready for Direction 여부

23. 기존 ready_for_production 하위 호환 처리 방식

24. 추가한 테스트 수

25. 전체 테스트 결과
    PASS / FAIL / SKIP

26. Gemini fallback 발생 여부

27. 새 YouTube API quota 사용 여부

28. 05~08 기존 데이터 불변 여부

29. 발견된 제한사항

30. 10 Video Director 단계 진행 가능 여부


==================================================
33. 최종 원칙
==================================================

09의 목표는 좋은 "영상"을 만드는 것이 아니다.

09의 목표는:

"어떤 영상 포맷으로 변환하더라도
교육적 핵심과 Viewer Promise가 무너지지 않는
검증된 Content Script를 만드는 것"

이다.

09는 WHAT을 책임진다.

10은 HOW를 책임진다.

따라서 09가 특정 포맷이나 연출을 먼저 결정하면
이번 수정은 실패한 것이다.

반대로 Format Neutral을 만든다는 이유로
현재 09-1에서 확보한 교육 정확성,
좋은 base narration,
Retention,
Mini Success,
발음 안전성,
Scope 안전성을 잃어도 실패다.

두 조건을 동시에 만족시켜라.