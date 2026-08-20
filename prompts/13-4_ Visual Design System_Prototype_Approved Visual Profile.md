# Stage 13-4 — Visual Design System / Prototype / Approved Visual Profile

현재 프로젝트의 Stage 13-1(Render Specification), 13-2(Timeline Compiler),
13-3(Scene/Layout Specification)까지 완료되었다.

Production Plan 7 기준 현재 상태:

- Render Spec version: 13.1
- Timeline version: 13.2
- Layout version: 13.3
- Production Plan ID: 7
- Scene 수: 8
- Ready for Visual Design: YES
- video duration: 290120ms
- Source Speech Assets: 44 distinct
- Generation Units: 51 distinct
- CAP active asset: SP039::CONTEXTUAL_WORD
- BAG active asset: SP003
- MAP active asset: SP029
- BAT active asset: SP016
- failed/rejected variant 사용: 0
- experimental variant 사용: 0
- CB06 PAUSE: 3000ms
- CB06 answer reveal not-before: 243280ms
- CB06 answer audio start: 243280ms
- CB07 answer_reveal_policy: None
- CB07 Timeline barrier: 없음
- 13-3A semantic debt 수정 완료
- Ready for Visual Design: YES

Stage 13-4의 공식 입력은:

assets/generated/plan_<ID>/render/scene_layout.json

또는 scene_layouts 테이블의 해당 Plan 최신 row이다.

13-4는 Render Spec/Timeline/Production Plan을 다시 해석하여
새로운 의미나 timing을 만들어서는 안 된다.

Scene Layout 13.3을 공식 입력 계약으로 사용한다.

======================================================================
0. 이번 단계의 핵심 목표
======================================================================

13-4의 목적은 곧바로 최종 MP4를 만드는 것이 아니다.

이번 단계는 다음 3개 층으로 분리한다.

13-4A — Visual Design System
13-4B — Visual Prototype
Human Visual Review
13-4C — Approved Visual Profile

중요:

13-4A와 13-4B를 먼저 구현한다.

13-4B에서 실제 Plan 7의 대표 Scene 디자인 시안을 만든 뒤
사람이 실제 화면을 보고 승인하기 전에는
13-4C의 최종 디자인 값을 확정하지 않는다.

즉:

Design principles
    ↓
Visual Design System
    ↓
Prototype
    ↓
Human Visual Review
    ↓
Approved Visual Profile
    ↓
Renderer Implementation

순서다.

이번 단계에서 실제 MP4를 생성하지 마라.

Gemini TTS 호출 금지.
YouTube API 호출 금지.
영상 생성 AI 호출 금지.

기존 WAV 수정/재생성 금지.
Human Review 상태 수정 금지.
Production Plan 수정 금지.
Render Spec timing 수정 금지.
Timeline 수정 금지.
Scene Layout semantic 수정 금지.

======================================================================
1. Renderer-neutral 원칙
======================================================================

13-4A Visual Design System은 Renderer-neutral이어야 한다.

즉 다음 구현 기술에 직접 종속되어서는 안 된다.

- Remotion
- React
- HTML
- CSS
- JavaScript
- Canvas
- SVG renderer
- FFmpeg filter
- 특정 영상 생성 AI
- 특정 편집 프로그램

예:

금지:

css_class
html_tag
absoluteFill
flexbox
grid-template
remotion_sequence
canvas_context
ffmpeg_filter

허용:

semantic_role
visual_priority
typography_role
color_role
motion_role
background_role
container_role
media_role
responsive_behavior
visibility_state
emphasis_role

실제 Renderer binding은 이후 단계의 책임이다.

======================================================================
2. Visual Design의 최상위 철학
======================================================================

이 프로젝트의 영상은 “예쁜 영상”보다
“왕초보가 지금 무엇을 봐야 하는지 즉시 이해할 수 있는 영상”을 목표로 한다.

최우선 순위:

1. 학습 이해
2. 시선 유도
3. 정보 계층
4. 읽기 편의성
5. 학습 흐름
6. 디자인 일관성
7. 미적 장식

장식 때문에 학습 관계가 약해져서는 안 된다.

핵심 문장:

“영어가 주인공이고, 디자인은 영어를 이해하도록 돕는다.”

======================================================================
3. Long-form + Shorts 기본 전략
======================================================================

기본 제작 대상은 16:9 Long-form이다.

하지만 16:9만 고려하여
나중에 9:16 Shorts를 처음부터 다시 만들어야 하는 구조를 만들지 않는다.

동일한:

- Scene semantics
- learning elements
- semantic roles
- Timeline relationships
- visual hierarchy

를 유지하고 Output Profile에 따라 재배치할 수 있도록 설계한다.

16:9 → 9:16은 단순 center crop이 아니다.

Responsive Recomposition을 전제로 한다.

즉:

same Scene
+ same semantic elements
+ same learning relationship
→ different layout profile

구조다.

======================================================================
4. Core Safe Area
======================================================================

16:9 전체 공간은 자유롭게 활용할 수 있다.

그러나 핵심 학습 요소는 가능한 한
중앙 Core Safe Area를 중심으로 구성한다.

대표 핵심 요소:

- TARGET_WORD
- PHONEME
- BLEND_SEQUENCE
- QUESTION
- ANSWER
- PRIMARY_FOCUS

좌우 공간에는 필요할 경우:

- supporting explanation
- comparison
- external media
- examples
- contextual information

등을 배치할 수 있다.

하지만 16:9를 억지로 좁은 세로 영상처럼 만들지 마라.

동시에 핵심 학습 관계를 화면 양끝 위치에 과도하게 의존시키지 마라.

9:16에서는 같은 의미 구조를 상하 구조 등으로 재배치할 수 있어야 한다.

======================================================================
5. Visual Hierarchy
======================================================================

화면에는 항상 시각적 우선순위가 존재해야 한다.

모든 정보를 같은 강도로 보여주지 마라.

기본 개념:

DOMINANT
PRIMARY
SUPPORTING
CAPTION
MICRO

우선순위:

DOMINANT
↓
PRIMARY
↓
SUPPORTING
↓
CAPTION
↓
MICRO

DOMINANT는 정말 중요한 순간에만 사용한다.

예:

- 핵심 학습 단어
- 최종 정답
- Mini Success 결과

모든 요소를 크게 만드는 방식은 금지한다.

핵심:

“글자를 크게 만드는 것이 아니라,
중요한 것을 크게 보이게 한다.”

======================================================================
6. Typography 방향
======================================================================

현대적이고 읽기 쉬운 Typography를 기본으로 한다.

화려한 Typeface보다 글자 형태의 명확성을 우선한다.

특히 다음이 쉽게 구별되어야 한다.

b / d
p / q
I / l
O / 0

IPA/phoneme glyph:

/æ/
/ə/
/ɪ/
/ʊ/
/θ/
/ð/

등이 정확하고 명확하게 보여야 한다.

영어 학습 문자:
→ 글자 형태 명확성 최우선

한국어 설명:
→ 장시간 읽기 편해야 함

phoneme:
→ IPA glyph 지원 필수

강조를 위해 Typeface를 계속 바꾸지 않는다.

우선 사용:

- size
- weight
- semantic color
- contrast
- position
- motion

실제 font family/px/weight/line-height/letter-spacing은
Human Visual Review 전 최종값으로 고정하지 마라.

======================================================================
7. Uppercase / Lowercase
======================================================================

대문자와 소문자를 장식 목적으로 사용하지 않는다.

학습 목적에 따라 사용한다.

예:

초기 단어 인식:

BAT

글자 분석:

b   a   t

블렌딩:

b + a + t
→ bat

실제 읽기:

bat

The bat is ...

실제 읽기에 가까워질수록 자연스러운 표기를 우선한다.

대문자만 익혀 소문자를 낯설게 만드는 디자인을 피한다.

======================================================================
8. Semantic Color System
======================================================================

색은 장식이 아니라 의미 전달에 사용한다.

Semantic Color Role을 먼저 정의한다.

최소 후보:

DEFAULT
PRIMARY_FOCUS
RELATION
SUCCESS
SECONDARY
MUTED
EXCEPTION_CAUTION

같은 의미는 영상 전체에서 같은 Color Role을 가져야 한다.

예:

a ↔ /æ/

관계를 설명한다면 두 요소가 RELATION/F​​OCUS 체계에서
시각적으로 연결되어야 한다.

다음 학습 대상으로 이동하면
기존 강조는 MUTED될 수 있다.

실제 HEX/RGB 값은 아직 최종 확정하지 마라.

기존 프로젝트에서 사용한 색이 있더라도
자동으로 최종 Profile로 승격하지 마라.

Human Visual Review 후 결정한다.

======================================================================
9. Color Accessibility
======================================================================

강제 규칙:

NO SEMANTIC INFORMATION MAY DEPEND ON COLOR ALONE.

색은 의미를 강화할 수 있지만
색만으로 의미를 전달해서는 안 된다.

색과 함께 적절한 경우:

- position
- connector
- arrow
- typography weight
- typography scale
- contrast
- motion
- shape

등의 추가 cue를 사용한다.

예:

a
│
↓
/æ/

색을 제거해도 관계를 이해할 수 있어야 한다.

======================================================================
10. Whitespace
======================================================================

빈 공간을 채워야 할 공간으로 생각하지 않는다.

Whitespace 자체를 Visual System으로 취급한다.

역할:

- Primary Focus 강화
- 정보 그룹 분리
- Motion 공간 확보
- 학습 관계 표현
- 시선 휴식

예:

/b/              /æ/              /t/

→

/b/        /æ/        /t/

→

/b/ /æ/ /t/

→

bat

공간 자체가 “분리 → 접근 → 결합”을 설명할 수 있다.

화면이 허전하다는 이유로:

- icon
- character
- decorative line
- background object
- random graphic

을 추가하지 마라.

======================================================================
11. Progressive Disclosure
======================================================================

모든 정보를 처음부터 한 화면에 보여주지 않는다.

학습자가 현재 이해해야 하는 정보만 보여준다.

예:

BAT

↓

b   a   t

↓

b   a   t
    ↓
   /æ/

↓

/b/ /æ/ /t/

↓

/b-æ-t/

↓

bat

↓

필요할 경우 한국어 의미

정보 상태 개념을 정의하라.

예:

ACTIVE
PRIMARY
MUTED
REMOVED

필요한 정보는 등장하고,
현재 핵심은 강조하고,
역할이 끝난 정보는 약화하거나 제거한다.

max_simultaneous_elements를 근거 없이 숫자로 확정하지 마라.

======================================================================
12. Progressive Assistance
======================================================================

같은 학습 개념이 반복될수록 시각적 도움을 줄인다.

처음:
→ 자세한 설명

첫 반복:
→ 짧은 Reminder

추가 반복:
→ 최소 Hint

충분히 익숙한 단계:
→ 도움 없이 읽기

예:

첫 설명:

a
↓
/æ/

MAP에서 재사용:

m   a   p
    /æ/

더 뒤:

/m/ /æ/ /p/

최종적으로는 자연스러운 단어/문장 읽기로 이동한다.

======================================================================
13. Word Meaning
======================================================================

한국어 뜻을 항상 표시하지 않는다.

현재 학습 목표가 읽기라면
글자와 소리 관계를 먼저 보여준다.

예:

b   a   t
/b/ /æ/ /t/
↓
bat

필요한 시점에만:

bat
박쥐

처럼 의미를 SUPPORTING/MUTED 수준으로 표시한다.

한국어 의미가 영어 학습 대상보다 강하게 보여서는 안 된다.

핵심:

“먼저 읽고, 그다음 이해한다.”

======================================================================
14. Sentence Context
======================================================================

학습한 단어가 실제 문장에 등장할 경우
문장의 자연스러운 표기를 훼손하지 않는다.

예:

The bat is black.

처음에는 bat에 잠깐 Focus를 줄 수 있다.

그 후 Focus를 제거하여:

The bat is black.

그대로 읽도록 한다.

BAT처럼 문장 중간의 실제 표기를
학습 강조 때문에 부자연스럽게 변경하지 않는다.

강조는 임시 학습 scaffold다.

======================================================================
15. Character / Human Visual
======================================================================

기본 학습 화면에는 캐릭터를 상시 배치하지 않는다.

영상의 주인공은 영어와 학습 과정이다.

캐릭터/사람/일러스트는 다음처럼 실제 역할이 있을 때만 사용 가능하다.

- opening context
- real-world situation
- abstract explanation support
- short mood reset
- channel guidance

캐릭터가 없어도 핵심 학습 Scene이 완전히 성립해야 한다.

화면이 허전하다는 이유로 캐릭터를 추가하지 마라.

======================================================================
16. External Media
======================================================================

실제 영상/사진/외부 클립은 학습 목적에 따라 사용한다.

3단계 구조를 허용한다.

A. EXPERIENCE

실제 상황 자체를 먼저 경험
→ media 중심

B. ANALYSIS

실제 영상 + 학습 그래픽
→ 방금 들은 영어와 학습 원리 연결

C. PRINCIPLE

media 비중 감소/제거
→ 깨끗한 학습 화면으로 원리 정리

즉:

실제 영어를 보여준다
→ 분석한다
→ 학습 원리로 정리한다

외부 클립을 단순 볼거리나 화면 채우기 용도로 사용하지 마라.

======================================================================
17. Media Style Integration
======================================================================

사진, 영화 클립, 원어민 영상, 일러스트, AI 영상 등을
억지로 하나의 필터 스타일로 만들지 않는다.

원본 미디어의 특성은 가능한 유지한다.

대신 그 위에 적용하는:

- PRIMARY_FOCUS
- RELATION
- TARGET_WORD
- PHONEME
- highlight
- caption
- semantic color
- learning motion

등의 학습 Visual Grammar를 통일한다.

핵심:

“미디어의 스타일을 통일하는 것이 아니라,
미디어를 가르치는 방식을 통일한다.”

======================================================================
18. Background System
======================================================================

배경은 학습 대상을 돋보이게 하는 보조 시스템이다.

Semantic Background Role 후보:

LEARNING_BACKGROUND
CONTEXT_BACKGROUND
TRANSITION_BACKGROUND
MEDIA_BACKGROUND

LEARNING_BACKGROUND:
→ 가장 조용하고 깨끗

CONTEXT_BACKGROUND:
→ 상황/맥락 보조

TRANSITION_BACKGROUND:
→ 학습 단계 변화 인식 보조

MEDIA_BACKGROUND:
→ 실제 영상/사진 중심

모든 Scene에 같은 배경 이미지를 강제하지 마라.

특정 HEX/gradient/texture는 아직 최종 확정하지 마라.

======================================================================
19. Semantic Container
======================================================================

카드/박스/테두리를 장식 목적으로 사용하지 않는다.

정보의 의미적 경계를 구별할 필요가 있을 때만 사용한다.

예:

a → /æ/

에는 Container가 필요 없을 수 있다.

반면:

CAT        CAKE
/æ/        /eɪ/

비교라면 두 정보 그룹을 Container로 분리할 수 있다.

Semantic Container 후보:

COMPARE
KEY_POINT
EXAMPLE
SUPPORTING_INFO

실제 border/radius/shadow 값은 Human Review 전 최종 확정하지 마라.

======================================================================
20. Caption Layer
======================================================================

LEARNING_TEXT와 NARRATION_CAPTION을 분리한다.

LEARNING_TEXT:
→ 학습자가 반드시 봐야 하는 정보

NARRATION_CAPTION:
→ 음성 접근성 보조

자막이 핵심 영어/음소/정답과 경쟁해서는 안 된다.

구조적으로:

Visual Learning Layer
Caption Layer

를 분리한다.

나중에:

- burn-in caption
- platform caption
- caption on/off
- 16:9 caption placement
- 9:16 caption placement

정책을 독립적으로 적용할 수 있어야 한다.

실제 위치/크기/한 줄 글자 수는 아직 최종 확정하지 마라.

======================================================================
21. Scene Transition
======================================================================

학습 내용이 이어질 경우
화면 전체를 매번 교체하지 않는다.

예:

/b/        /æ/        /t/

↓

/b/    /æ/    /t/

↓

/b/ /æ/ /t/

↓

BAT

동일 요소의 연속성을 유지한다.

학습 단계가 실제로 바뀔 때만
짧고 차분한 Scene Transition을 사용할 수 있다.

금지 기본값:

- 과도한 zoom
- spin
- flash
- aggressive blur
- decorative camera movement

핵심:

“내용이 이어지면 화면도 이어지고,
내용이 바뀌면 조용히 전환한다.”

======================================================================
22. Motion Semantic Roles
======================================================================

모든 Motion에 같은 속도/성격을 적용하지 않는다.

Semantic Motion Role 후보:

LEARNING_MOTION
TRANSITION_MOTION
EMPHASIS_MOTION
REVEAL_MOTION
DECORATIVE_MOTION

LEARNING_MOTION:
→ 반드시 따라가야 하는 변화
→ 이해가 속도보다 중요

TRANSITION_MOTION:
→ Scene/학습 단계 전환
→ 짧고 자연스럽게

EMPHASIS_MOTION:
→ 현재 봐야 할 요소 안내
→ 짧고 분명하게

REVEAL_MOTION:
→ 정답/새 정보 공개
→ 분명하지만 과장 금지

DECORATIVE_MOTION:
→ 기본적으로 최소화
→ 학습 기능 없으면 사용하지 않는 것이 우선

13-4에서 모든 애니메이션을 500ms 같은 값으로 고정하지 마라.

Timeline AUDIO timing을 디자인 때문에 수정하지 마라.

CB06 PAUSE 3000ms를 절대 침범하지 마라.

Answer Reveal Barrier를 침범하지 마라.

======================================================================
23. Entrance Motion
======================================================================

모든 정보가 같은 방식으로 등장하지 않는다.

정보 중요도에 따라 등장 강도를 다르게 한다.

새로운 핵심 정보:
→ PRIMARY_ENTRANCE

보조 정보:
→ SUPPORTING_ENTRANCE

이미 알고 있는 정보:
→ REUSED_ELEMENT_ENTRANCE
→ 거의 움직이지 않거나 매우 약하게

정답:
→ ANSWER_REVEAL

중요:

새 핵심 정보 → 분명하게
보조 정보 → 조용하게
이미 아는 정보 → 최소한
정답 → 짧지만 확실하게

실제 easing/scale/opacity/duration 값은 아직 Renderer 구현값으로 확정하지 마라.

======================================================================
24. Mini Success
======================================================================

CB06은 매우 중요한 기준 Scene이다.

현재 canonical timing:

PAUSE:
240280 → 243280
duration = 3000ms

answer reveal not-before:
243280ms

answer audio:
SP039::CONTEXTUAL_WORD
start = 243280ms

Visual Design은 이 barrier를 절대 침범해서는 안 된다.

Prompt:
→ 생각하는 동안 유지 가능

Answer:
→ barrier 이전 숨김

정답 Reveal:
→ 243280ms 이전 금지

PAUSE를 디자인/애니메이션 때문에 줄이거나 덮어쓰지 마라.

viewer_action을 보존한다.

CB07 RECAP에는 Answer Reveal Barrier가 없다.

CB07에 Mini Success 규칙을 적용하지 마라.

======================================================================
25. Unified Visual Grammar
======================================================================

모든 Scene을 같은 화면으로 만들지 않는다.

반대로 Scene마다 완전히 다른 스타일을 만들지도 않는다.

공통 Visual Grammar:

- Typography System
- Semantic Color
- Motion Language
- Whitespace
- Core Safe Area
- Caption Layer
- Container System
- Accessibility
- Background System
- Progressive Disclosure

를 공유한다.

그 안에서 Scene Role/Layout Type별로 다른 구성을 허용한다.

현재 Scene:

CB01 OPENING
CB02 EXPLANATION
CB03 EXPLANATION
CB04 BLENDING
CB05 PRACTICE
CB06 MINI_SUCCESS
CB07 RECAP
CB08 RESOLUTION

각 Scene은 자신의 학습 목적에 맞는 디자인 구조를 가져야 한다.

핵심:

“같은 채널처럼 보이지만,
학습 목적이 다르면 화면도 다르게 행동한다.”

======================================================================
26. 13-3 Zone/Binding 존중
======================================================================

13-4가 Scene Layout을 새로 발명하지 마라.

13-3의:

zones
element_bindings
visibility_rules
layout_constraints
emphasis_bindings

을 공식 구조로 사용한다.

특히 CB06:

zones:
answer
caption
prompt

constraints:
ANSWER_HIDDEN_BEFORE_BARRIER
PROMPT_VISIBLE_DURING_ATTEMPT

을 보존한다.

CB07에 barrier constraint를 새로 만들지 마라.

13-4는 semantic design token/style role을 binding하는 단계이지
13-3의 semantic layout을 다시 판단하는 단계가 아니다.

======================================================================
27. Visual Review Gate
======================================================================

모든 Scene을 무조건 자동 승인하지 않는다.

기본:

AUTO_LAYOUT → PASS

자동 디자인 판단의 신뢰도가 낮으면:

VISUAL_REVIEW_REQUIRED

로 명시한다.

반드시 reason을 기록한다.

Reason taxonomy 후보:

TOO_MANY_COMPETING_ELEMENTS
VISUAL_HIERARCHY_AMBIGUOUS
MEDIA_LEARNING_CONTENT_CONFLICT
TEXT_DENSITY_HIGH
RESPONSIVE_RECOMPOSITION_RISK
CORE_SAFE_AREA_CONFLICT
CAPTION_COLLISION_RISK
ACCESSIBILITY_RISK

필요하면 실제 데이터에서 발견된 이유를 추가할 수 있으나
근거 없이 taxonomy를 확대하지 마라.

자동화가 모르는 것을 억지로 결정하지 않는다.

======================================================================
28. 13-4A — Visual Design System 산출물
======================================================================

신규 모듈을 설계하라.

권장 예:

research/visual_design.py

단 실제 프로젝트 구조를 먼저 조사하고
기존 naming/style과 맞지 않으면 적절히 조정하라.

Visual Design System에는 최소한 다음 semantic structure가 있어야 한다.

typography_roles
color_roles
motion_roles
background_roles
container_roles
media_roles
caption_roles
element_states
responsive_rules
scene_visual_rules
accessibility_rules
visual_review_rules

중요:

실제 px/HEX/font를 최종 승인값으로 넣지 않는다.

필요하면 candidate/UNRESOLVED 상태로 표현한다.

예:

{
  "typography_role": "DOMINANT",
  "resolved_style": null,
  "resolution_status": "PENDING_VISUAL_REVIEW"
}

형태가 가능하다.

단 정확한 schema는 기존 프로젝트 패턴을 조사한 뒤
가장 단순하고 명확한 구조를 선택하라.

======================================================================
29. 13-4B — Visual Prototype
======================================================================

Visual Design System을 실제 Plan 7 대표 Scene에 적용하여
사람이 볼 수 있는 Prototype을 생성한다.

최소 대표 Scene:

CB03 EXPLANATION
CB04 BLENDING
CB05 PRACTICE
CB06 MINI_SUCCESS
CB07 RECAP

가능하면 추가:

CB01 OPENING
CB08 RESOLUTION

Prototype의 목적은 영상 생성이 아니다.

정적인 이미지 또는 Renderer-neutral prototype representation 등
현재 프로젝트에서 가장 안전하고 검증 가능한 방식으로
“실제 화면을 사람이 판단할 수 있게” 만드는 것이다.

중요:

Prototype을 만들기 위해
영상 생성 AI를 호출하지 마라.

외부 API 호출하지 마라.

실제 MP4 생성하지 마라.

Prototype은 후보 디자인이다.

APPROVED 디자인으로 취급하지 마라.

======================================================================
30. Prototype Candidate Strategy
======================================================================

최종 Theme을 자동으로 하나 골라 확정하지 마라.

Visual Design System을 만족하는
소수의 명확한 후보 Profile을 만들 수 있다.

예시 이름:

CLEAN_DARK
SOFT_LIGHT
MODERN_EDUCATION

단 위 이름/개수를 그대로 강제하지 않는다.

실제 프로젝트의 기존 채널 디자인,
현재 데이터 구조,
가독성 요구를 조사한 뒤
최소한의 유의미한 후보만 생성하라.

각 후보는 같은 Scene/같은 내용으로 비교 가능해야 한다.

후보마다 학습 semantics를 바꾸면 안 된다.

바뀔 수 있는 것:

- palette candidate
- typography candidate
- background treatment
- container treatment
- spacing treatment
- focus treatment
- caption treatment

바뀌면 안 되는 것:

- learning meaning
- Timeline
- PAUSE
- answer barrier
- active asset
- text content
- scene role
- element lineage

======================================================================
31. 13-4C — Approved Visual Profile
======================================================================

13-4C는 Human Visual Review 이후에만 실행 가능해야 한다.

사람의 승인 없이 자동으로 APPROVED를 기록하지 마라.

승인 후에만 실제 값을 고정한다.

예:

Color Palette
Font Family
Font Weight
Typography Scale
Spacing Scale
Background
Container
Border
Radius
Caption Style
Focus Style
Success Style
Motion Style
16:9 Profile
9:16 Recomposition Profile

13-4A/13-4B 실행만으로
13-4C가 완료된 것처럼 표시하면 안 된다.

현재 작업에서 Human Review가 실제로 수행되지 않았다면:

Ready for Visual Prototype Review: YES

까지는 가능하지만

Approved Visual Profile: NO / PENDING

이어야 한다.

정직한 Gate를 구현하라.

======================================================================
32. Output Profile / Resolution
======================================================================

현재 상류 데이터의:

width
height
fps
orientation

이 미확정 상태라면
근거 없이 값을 canonical data에 박지 마라.

다만 Prototype을 사람이 보기 위해
preview canvas가 기술적으로 필요하다면
그 값은 반드시:

PREVIEW_ONLY

또는 동등한 의미로 표시하고
canonical Output Profile과 분리하라.

Preview resolution이
최종 16:9 output resolution으로 승격되어서는 안 된다.

9:16도 마찬가지다.

======================================================================
33. DB Persistence
======================================================================

05~13-3의 패턴을 조사하라.

구조화 산출물을 DB에 저장하는 기존 패턴이 일관되게 사용되고 있고
13-5 이후 단계가 재조회해야 한다면
Visual Design System용 테이블 추가를 검토하라.

예:

visual_design_specs

또는 기존 naming convention에 맞는 이름.

Prototype/Approved Profile을 별도 저장할 필요가 있다면
실제 consumer와 lifecycle을 먼저 확인하라.

불필요한 테이블을 무조건 만들지 마라.

DB schema version을 실제 필요 없이 도입하지 마라.

======================================================================
34. File Output
======================================================================

기존 패턴에 맞춰 최소한 다음 계열 산출물을 검토하라.

assets/generated/plan_<ID>/render/visual_design.json

reports/visual_design_<DATE>.md

Prototype이 파일로 생성된다면:

assets/generated/plan_<ID>/render/prototypes/

아래처럼 명확한 위치를 사용하라.

단 기존 프로젝트 convention을 먼저 조사한다.

======================================================================
35. Validation
======================================================================

최소 다음을 검증하라.

1. Entry Gate가 13-3 canonical readiness를 사용
2. Scene count lineage
3. Scene ID lineage
4. Layout type lineage
5. Zone lineage
6. Element binding lineage
7. visibility rule preservation
8. layout constraint preservation
9. emphasis binding preservation
10. CB06 answer barrier preservation
11. CB06 PAUSE semantics preservation
12. CB06 viewer action preservation
13. CB07 no false answer barrier
14. no failed/rejected asset introduction
15. no experimental variant introduction
16. renderer-neutral
17. no canonical pixel/resolution invention
18. semantic color not sole cue
19. typography role completeness
20. visual hierarchy completeness
21. progressive disclosure support
22. progressive assistance support
23. caption/learning text separation
24. responsive recomposition support
25. visual review reason completeness
26. prototype not falsely approved
27. deterministic output where applicable

실제 구현 구조에 맞춰 필요한 검증을 추가할 수 있으나
숫자를 채우기 위한 meaningless check는 만들지 마라.

======================================================================
36. Integrity Check
======================================================================

13-1/13-2/13-3 Integrity Check 이름을 변경하지 마라.

13-4 전용 Integrity Check를 별도로 만든다.

예:

visual_design_entry_gate_safe
visual_design_scene_lineage_safe
visual_design_layout_lineage_safe
visual_design_binding_lineage_safe
visual_design_visibility_safe
visual_design_constraint_safe
visual_design_emphasis_safe
visual_design_mini_success_safe
visual_design_recap_scope_safe
visual_design_renderer_neutral
visual_design_resolution_independent
visual_design_accessibility_safe
visual_design_typography_safe
visual_design_color_semantics_safe
visual_design_progressive_disclosure_safe
visual_design_progressive_assistance_safe
visual_design_caption_layer_safe
visual_design_responsive_safe
visual_design_review_gate_safe
visual_design_prototype_not_auto_approved
visual_design_deterministic
visual_design_complete

이 이름들은 예시다.

실제 코드 구조에 맞게 조정 가능하다.

기존 Integrity Check를 삭제/rename하지 마라.

======================================================================
37. Tests
======================================================================

충분한 신규 테스트를 추가하라.

반드시 포함할 case:

A. 정상 Plan 7 entry
B. Ready for Visual Design=NO → 차단
C. Scene lineage mismatch → 차단
D. zone/binding mismatch → 차단
E. CB06 answer가 barrier 이전 visible → 차단
F. CB07에 잘못된 answer barrier style 적용 → 차단
G. semantic meaning이 color만으로 전달 → 차단
H. renderer-specific field 오염 → 차단
I. canonical pixel/resolution 임의 확정 → 차단
J. caption과 learning text semantic 혼합 → 탐지
K. 9:16 단순 crop-only contract → 탐지
L. responsive recomposition contract → pass
M. failed/rejected asset 도입 → 탐지
N. experimental variant 도입 → 탐지
O. Prototype 자동 APPROVED → 차단
P. Visual Review Required reason 없음 → 차단
Q. 동일 입력 determinism
R. 기존 13-1/13-2/13-3 regression 없음

실제 구현에서 발견되는 버그에는 별도 회귀 테스트를 추가하라.

======================================================================
38. 반드시 보존할 현재 Plan 7 사실
======================================================================

다음을 변경하지 마라.

Production Plan ID = 7

Scene:
CB01 OPENING
CB02 EXPLANATION
CB03 EXPLANATION
CB04 BLENDING
CB05 PRACTICE
CB06 MINI_SUCCESS
CB07 RECAP
CB08 RESOLUTION

CAP:
SP039::CONTEXTUAL_WORD

BAG:
SP003

MAP:
SP029

BAT:
SP016

CB06 PAUSE:
3000ms

CB06 pause:
240280 → 243280

CB06 answer:
not before 243280

CB06 answer audio:
start 243280

CB07:
answer_reveal_policy = None
Timeline barrier = none
Scene Layout barrier constraint = none

video duration:
290120ms

failed/rejected active variant:
0

experimental active variant:
0

이 값은 Visual Design 단계가 수정할 권한이 없다.

======================================================================
39. 금지 사항
======================================================================

하지 마라:

- TTS 재생성
- WAV 수정
- Human Review 재기록
- Production Plan 수정
- Render Spec 의미 변경
- Timeline 재계산
- Scene timing 변경
- PAUSE 변경
- viewer_action 변경
- active asset 재선택
- CAP fallback 재선택
- width/height/fps를 canonical 값으로 임의 확정
- 최종 Font를 사람 검토 없이 APPROVED
- 최종 Color Palette를 사람 검토 없이 APPROVED
- 실제 MP4 생성
- 영상 생성 AI 호출
- YouTube API 호출
- 불필요한 외부 API 호출
- Remotion 구현을 Visual Design Spec 안에 삽입
- HTML/CSS 구현을 canonical Visual Design Spec으로 사용
- 단순 center crop을 9:16 전략으로 확정
- 모든 Scene을 같은 Template으로 강제
- Scene마다 Visual Grammar를 제각각 변경
- 장식 목적으로 Motion/Character/Card 추가
- 모든 정보를 동시에 표시
- 색상만으로 의미 전달
- Human Visual Review를 자동 PASS 처리

======================================================================
40. 실제 구현 전 조사
======================================================================

코드를 수정하기 전에 반드시 현재 repository를 조사하라.

확인:

- research/scene_layout.py
- research/render_spec.py
- research/timeline_compiler.py
- research/asset_generator.py
- research/db.py
- research/cli.py
- 관련 tests
- DB table pattern
- latest-ready lookup pattern
- JSON/report output convention
- integrity check convention
- CLI naming convention

기존 helper가 이미 같은 질문에 답하고 있다면 재사용하라.

같은 의미의 판정 로직을 새로 복제하지 마라.

상류 Source of Truth를 다시 계산하지 마라.

======================================================================
41. 구현 중 실제 버그를 발견하면
======================================================================

13-4 구현 중 상류 단계의 실제 semantic bug를 발견했다면
조용히 우회하지 마라.

먼저:

- 정확한 원인
- producer
- consumer
- 영향 범위
- canonical source
- 수정 필요 여부

를 분석하라.

13-4에서 안전하게 방어할 수 있더라도
상류 canonical data가 잘못된 경우 semantic debt로 보고해야 한다.

단 실제 근거 없이 상류 코드를 수정하지 마라.

======================================================================
42. 완료 판정
======================================================================

이번 실행의 정상적인 최종 상태는
Human Review가 아직 이루어지지 않았다면 다음이어야 한다.

Ready for Visual Design System: YES
Visual Design System Generated: YES
Visual Prototype Generated: YES
Ready for Visual Prototype Review: YES
Human Visual Review: PENDING
Approved Visual Profile: NO
Ready for Final Renderer Binding: NO

이것은 실패가 아니다.

의도한 Gate다.

사람이 Prototype을 승인한 이후 별도 13-4C 실행에서:

Human Visual Review: APPROVED
Approved Visual Profile: YES
Ready for Final Renderer Binding: YES

가 될 수 있다.

======================================================================
43. 완료 보고 형식
======================================================================

작업 완료 후 축약하지 말고 다음 항목을 번호로 상세 보고하라.

1. 수정/추가 파일
2. Architecture
3. 공식 입력 Scene Layout
4. Production Plan ID
5. Layout version
6. Visual Design version
7. Entry Gate 결과
8. Scene 수
9. Visual Design System schema
10. Typography Role taxonomy
11. Color Role taxonomy
12. Motion Role taxonomy
13. Background Role taxonomy
14. Container Role taxonomy
15. Caption Role taxonomy
16. Element State taxonomy
17. Responsive/Recomposition taxonomy
18. Scene별 visual rule
19. Core Safe Area 처리
20. Whitespace 처리
21. Progressive Disclosure 처리
22. Progressive Assistance 처리
23. Uppercase/Lowercase 처리
24. Word Meaning 처리
25. Sentence Context 처리
26. Character/Human 처리
27. External Media 처리
28. Media Style Integration 처리
29. Caption/LEARNING_TEXT 분리 결과
30. Semantic Color 결과
31. Color-alone accessibility 검증
32. Typography accessibility 검증
33. Scene Transition 정책
34. Motion Tempo 정책
35. Entrance Motion 정책
36. CB06 Mini Success 처리
37. CB06 PAUSE 보존
38. CB06 answer reveal barrier 보존
39. CB06 viewer_action 보존
40. CB07 RECAP 처리
41. CAP active asset 확인
42. BAG/MAP/BAT active asset 확인
43. failed/rejected variant 여부
44. experimental variant 여부
45. 16:9 전략
46. 9:16 recomposition 전략
47. crop-only 방지 검증
48. unresolved critical fields
49. unresolved non-critical fields
50. Visual Review Gate taxonomy
51. AUTO_LAYOUT Scene 수
52. VISUAL_REVIEW_REQUIRED Scene 수/이유
53. Prototype 대상 Scene
54. Prototype candidate 수/이름
55. Prototype 출력 형식/경로
56. Preview-only resolution 사용 여부
57. DB 저장 여부/id
58. JSON 경로
59. report 경로
60. 신규 Validation 목록
61. 신규 Integrity Check 목록
62. Integrity Check 전체 결과
63. 신규 테스트 수
64. 전체 테스트 수
65. 기존 테스트 회귀 여부
66. 13-1 회귀 여부
67. 13-2 회귀 여부
68. 13-3 회귀 여부
69. Production Plan/05~12 불변 여부
70. Render Spec 불변 여부
71. Timeline 불변 여부
72. Scene Layout 불변 여부
73. generated WAV 불변 여부
74. Human Review 불변 여부
75. Gemini TTS 호출 수
76. YouTube API 호출 수
77. 영상 생성 AI 호출 수
78. 실제 MP4 생성 여부
79. Ready for Visual Design System
80. Visual Design System Generated
81. Visual Prototype Generated
82. Ready for Visual Prototype Review
83. Human Visual Review 상태
84. Approved Visual Profile 상태
85. Ready for Final Renderer Binding
86. 구현 중 발견된 실제 버그/semantic debt
87. 발견된 제한사항
88. 13-4C가 승인 후 확정해야 할 값 목록
89. 다음 단계가 읽어야 할 정확한 입력 계약
90. 성공 기준 전체 충족 여부

마지막에는 반드시 다음과 같이 명시하라.

Human Review 전이라면:

READY FOR VISUAL PROTOTYPE REVIEW: YES/NO
READY FOR STAGE 13-4C: NO — HUMAN VISUAL REVIEW REQUIRED

사람이 실제로 승인한 이후에만:

READY FOR STAGE 13-4C: YES

라고 표시할 수 있다.

======================================================================
44. 최종 원칙
======================================================================

이 단계에서 가장 중요한 것은
“AI가 디자인을 알아서 예쁘게 만드는 것”이 아니다.

우리가 지금까지 결정한 학습 철학을
재현 가능한 Visual Grammar로 만드는 것이다.

따라서:

디자인 원칙은 자동화한다.
디자인 취향은 실제 화면을 보고 승인한다.

학습 의미는 상류 데이터가 결정한다.
Visual Design은 그 의미를 명확하게 보여준다.

Timeline은 시간을 결정한다.
Visual Design은 시간을 바꾸지 않는다.

Scene Layout은 구조를 결정한다.
Visual Design은 구조를 다시 발명하지 않는다.

Renderer는 구현한다.
Visual Design System은 Renderer를 지정하지 않는다.

16:9와 9:16은 같은 학습 의미를 공유한다.
9:16은 16:9의 단순 Crop이 아니다.

그리고 모든 판단에서 최우선 질문은 이것이다:

“왕초보 학습자가 지금 무엇을 봐야 하는지
즉시 알 수 있는가?”

이 기준을 만족시키는 방향으로 Stage 13-4A와 13-4B를 구현하라.