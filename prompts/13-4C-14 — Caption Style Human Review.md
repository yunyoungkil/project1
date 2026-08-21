# 13-4C-14 — Caption Style Human Review

## 0. 작업 성격

이번 단계는 `caption_style`의 Human Visual Review를 위한 후보 생성 단계다.

중요:

- 이번 단계에서는 caption_style을 승인하지 않는다.
- Human Decision을 추정하지 않는다.
- DB에 새로운 승인 row를 기록하지 않는다.
- `approved_visual_profile.json`을 변경하지 않는다.
- Stage 13-5를 시작하지 않는다.
- Renderer를 구현하지 않는다.
- MP4를 생성하지 않는다.
- 기존 승인 category를 재승인하지 않는다.

목표는 오직:

1. 현재 canonical visual state를 정확히 읽는다.
2. caption_style 후보를 만든다.
3. 실제 학습 화면과 유사한 Prototype을 생성한다.
4. 사람이 브라우저에서 비교할 수 있게 한다.
5. Human Decision은 `NONE` 상태로 끝낸다.


# 1. 가장 먼저 해야 할 일 — PROJECT_STATE 확인

다른 작업보다 먼저 프로젝트 루트의:

`PROJECT_STATE.md`

를 읽어라.

단, PROJECT_STATE.md는 orientation/resume 문서이지 최종 canonical source of truth가 아니다.

반드시 다음 우선순위를 따른다.

SOURCE OF TRUTH PRECEDENCE:

1. canonical DB state
2. canonical machine-readable artifacts
3. current code
4. PROJECT_STATE.md
5. reports / README / historical prompts

PROJECT_STATE와 canonical DB/artifact가 충돌하면 canonical source를 우선하고 충돌 사실을 보고하라.


# 2. Historical Evidence Policy — 매우 중요

과거 prompt/report에 적힌:

- "사용자가 선택했다"
- "Human Review에서 결정했다"
- "이번 대화에서 사용자가 말했다"

같은 문장을 실제 Human Decision의 독립적인 증거로 사용하지 마라.

특히 과거 prompt가 현재 대화의 발언을 인용한다고 주장하더라도 그것을 사실로 자동 인정하지 마라.

현재 canonical state에 이미 APPROVED로 기록된 category는 canonical state로 받아들일 수 있다.

하지만 이번 `caption_style`에 대해서는:

HUMAN DECISION = NONE

으로 시작해야 한다.

이번 단계에서 사용자의 선택을 요구하거나 AskUserQuestion으로 승인받으려고 하지 마라.

이번 단계는 Review Artifact 생성까지만 수행한다.

사람의 선택은 다음 별도 Approval 단계에서 처리한다.


# 3. 현재 예상 canonical state

아래 값은 직전 완료 보고에 따른 expected state일 뿐이다.

반드시 실제 DB/artifact/code를 읽어 검증하라.

EXPECTED:

Production Plan ID:
7

Visual Design Version:
13.4

Current Major Stage:
13-4C Human Visual Review

Previous completed sub-stage:
13-4C-13 Font Weight Human Approval

Canonical Visual Candidate:
CLEAN_DARK_FOCUS

Expected canonical visual_design_spec id:
10

Expected Approved Category Count:
5

Expected Pending Category Count:
10


# 4. 현재 APPROVED로 예상되는 category

다음을 실제 canonical source에서 검증한다.

## font_family

status:
APPROVED

candidate:
VERDANA_HUMANIST

stack:

Verdana, Geneva, 'Malgun Gothic', sans-serif


## background

status:
APPROVED

value:

#111318


## color_palette

status:
APPROVED

exact roles:

DEFAULT:
#e6e6e6

PRIMARY_FOCUS:
#60a5fa

RELATION:
#c4b5fd

SUCCESS:
#4ade80

SECONDARY:
#9ca3af

MUTED:
#757b87

EXCEPTION_CAUTION:
#fbbf24


## typography_scale

status:
APPROVED

DOMINANT:
72px

PRIMARY:
46px

SUPPORTING:
28px

CAPTION:
20px

MICRO:
15px


## font_weight

status:
APPROVED

DOMINANT:
800

PRIMARY:
700

SUPPORTING:
500

CAPTION:
400

MICRO:
400

Font face provenance를 반드시 보존한다.

VERDANA_HUMANIST native weights:

[400, 700]

따라서:

DOMINANT 800:
synthetic

PRIMARY 700:
native

SUPPORTING 500:
synthetic

CAPTION 400:
native

MICRO 400:
native

Human approval은 synthetic weight가 native face라는 의미가 아니다.


# 5. 현재 PENDING으로 예상되는 category

다음을 실제 canonical source에서 검증한다.

caption_style
focus_style
success_style
motion_style
output_profile_16_9

spacing_scale
container
border
radius
output_profile_9_16

총 10개가 예상된다.

이번 단계에서 변경 대상은:

caption_style

하나뿐이다.

나머지 9개는 절대 승인하거나 수정하지 않는다.


# 6. Caption Style의 역할부터 조사하라

후보를 임의로 만들기 전에 현재 프로젝트 전체에서 caption/subtitle 관련 의미와 consumer를 조사하라.

최소 조사 대상:

- `research/visual_design.py`
- render 관련 코드
- scene layout 관련 코드
- render spec
- render timeline
- production blocks
- 기존 visual prototype
- typography review artifacts
- font weight review artifacts
- caption scaffold 관련 과거 구현
- CB06 관련 caption correction/review 코드
- tests
- reports
- PROJECT_STATE.md

검색 키워드 예:

caption
subtitle
caption_style
CAPTION
supporting
display_text
source_text
scaffold
visibility
safe area
question
answer
trace
reading
pronunciation

목표:

현재 프로젝트에서 caption이 실제로 무엇을 의미하는지 먼저 파악한다.

일반적인 영상 자막 디자인을 외부 지식으로 가정하지 마라.

이 프로젝트의 기존 semantic contract를 우선한다.


# 7. Caption Style과 Typography를 혼동하지 마라

이미 다음은 승인되었다.

font_family
font_weight
typography_scale
color_palette
background

따라서 Caption Style 후보를 비교하면서:

- font size 변경 금지
- font weight 변경 금지
- font family 변경 금지
- background 변경 금지
- palette role 값 변경 금지

Caption Style은 승인된 typography 위에서 동작해야 한다.

이번 review의 variable은 `caption_style`뿐이어야 한다.


# 8. Caption Style 후보 설계 원칙

현재 코드와 기존 artifacts를 조사한 뒤 최소 3개 후보를 만든다.

단, 후보 이름과 exact values는 코드/현재 semantic contract를 조사한 결과에 근거해서 결정한다.

무근거로 기존 프로젝트에 없는 디자인 시스템을 끼워 넣지 않는다.

후보는 최소 다음 차이를 사람이 실제로 판단할 수 있어야 한다.

- caption의 시각적 분리 정도
- 학습 본문과 caption의 hierarchy
- 한글 caption 가독성
- 영어 caption 가독성
- 짧은 caption
- 긴 caption
- 1줄/2줄 상황
- focus/answer 등 다른 semantic role과 충돌 여부
- dark background에서의 인지성

가능하다면 후보는 다음 철학적 축을 갖도록 설계한다.

A:
최소 개입 / 텍스트 중심

B:
균형형 / 현재 CLEAN_DARK_FOCUS와 자연스럽게 통합

C:
초보자 가독성 강화

단, 이것은 방향성일 뿐 exact implementation은 실제 프로젝트 구조를 조사한 뒤 결정한다.


# 9. 반드시 피해야 할 잘못된 후보 비교

다음처럼 여러 변수를 동시에 바꾸지 마라.

BAD:

A = 16px + white + no background
B = 22px + yellow + box
C = 28px + bold + shadow

이렇게 하면 caption_style이 아니라 typography/color/font_weight까지 동시에 비교하게 된다.

이미 승인된 category는 고정한다.

후보 간 차이는 caption_style 자체의 표현 속성으로 제한한다.


# 10. Palette semantic role 재사용

새로운 색을 임의로 추가하지 않는다.

반드시 승인된 palette role 안에서 해결한다.

사용 가능한 role:

DEFAULT
PRIMARY_FOCUS
RELATION
SUCCESS
SECONDARY
MUTED
EXCEPTION_CAUTION

caption에 어떤 role을 사용하는지는 기존 semantic contract를 조사해서 결정한다.

MUTED `#757b87` 사용 시 주의:

contrast:
4.37:1

normal AA:
FAIL

large AA:
PASS

MUTED는 이미 Human Review에서:

DE-EMPHASIZED TRACE / ALREADY-SEEN INFORMATION

용도로 승인된 값이다.

따라서 일반적인 핵심 caption body text에 MUTED를 무비판적으로 사용하지 마라.

caption의 실제 semantic importance에 따라 DEFAULT/SECONDARY/MUTED 등의 기존 role을 적절히 재사용하라.


# 11. Prototype은 실제 학습 화면을 대표해야 한다

단순히:

"Caption Sample"

한 줄만 보여주는 Prototype은 충분하지 않다.

최소 6개의 실제 context prototype을 만들어라.

권장 context:

01_FULL_LEARNING

승인된 visual hierarchy 안에서:

instruction
word
relation
answer
caption

이 함께 있는 전체 학습 화면.


02_SHORT_CAPTION

짧은 한글 caption.

예:

직접 읽어보세요.


03_LONG_CAPTION

실제 영상에서 발생할 수 있는 긴 caption.

한 줄 또는 wrapping이 발생할 수 있는 길이로 만든다.


04_KOREAN_ENGLISH

한글 + 영어가 함께 있는 caption.

Verdana + Malgun Gothic fallback 상황을 사람이 확인할 수 있어야 한다.


05_QUESTION_ANSWER

QUESTION → ANSWER reveal 문맥.

caption이 DOMINANT/PRIMARY/answer hierarchy를 방해하는지 확인한다.


06_DENSE_LEARNING

여러 학습 정보가 동시에 존재하는 상황.

caption이 다른 role과 섞이거나 지나치게 눈에 띄는지 확인한다.


# 12. 가능하면 추가 Context

현재 실제 code/artifact 조사 결과 유효하다면 다음도 추가할 수 있다.

07_TWO_LINE_CAPTION

08_LONG_ENGLISH_CAPTION

09_TRACE_WITH_CAPTION

10_EXCEPTION_CAUTION_WITH_CAPTION

하지만 불필요한 Prototype 수 증가를 목표로 하지 마라.

Human Review에 필요한 최소 충분 집합을 우선한다.


# 13. Side-by-Side 비교 화면

반드시 생성:

`00_CAPTION_STYLE_SIDE_BY_SIDE.html`

목적:

동일한 content를 후보 A/B/C로 한 화면에서 비교한다.

중요:

세 후보의:

- content
- font family
- font size
- font weight
- base background
- semantic meaning

은 동일해야 한다.

오직 caption_style 표현만 달라야 한다.


# 14. Review Artifact 경로

다음 계열을 사용한다.

`assets/generated/plan_7/render/caption_style_review/`

최소 생성:

index.html
manifest.json
00_CAPTION_STYLE_SIDE_BY_SIDE.html

그리고 context × candidate HTML.


# 15. index.html

사람이 가장 먼저 열 파일:

`assets/generated/plan_7/render/caption_style_review/index.html`

index에는 최소 다음을 표시한다.

CAPTION STYLE HUMAN REVIEW

STATUS:
PENDING_VISUAL_REVIEW

HUMAN DECISION:
NONE

FIXED APPROVED CONDITIONS:

Font Family:
VERDANA_HUMANIST

Background:
#111318

Typography Scale:
72 / 46 / 28 / 20 / 15

Font Weight:
800 / 700 / 500 / 400 / 400

Color Palette:
approved 7 roles

그리고:

Candidate A
Candidate B
Candidate C

각 후보의:

- 이름
- 디자인 의도
- exact style properties
- 사용 semantic role
- 장점
- trade-off

를 표시한다.

각 context prototype으로 이동할 링크도 제공한다.


# 16. Preview 상단 경고

모든 Review HTML에 명확히 표시한다.

예:

PREVIEW ONLY — Caption Style Human Review.
caption_style is NOT APPROVED.
Font Family / Background / Color Palette / Typography Scale / Font Weight are already Human Review APPROVED and are fixed conditions here.

Human decision:
NONE

문구는 실제 상태에 맞게 작성한다.


# 17. Candidate Label과 실제 CSS는 Single Source여야 한다

이전 단계에서 만든 `_parse_role_style` 또는 기존 helper 구조를 최대한 재사용한다.

후보 설명 label에는:

"padding 8px"

라고 써놓고 실제 CSS는 12px인 식의 drift가 발생하면 안 된다.

candidate data structure → HTML label + CSS

가 같은 source에서 생성되도록 한다.

필요하면 순수함수 helper를 추가한다.

하지만 이미 존재하는 helper로 해결 가능하면 재사용한다.


# 18. Caption 후보 Validation

실제 invariant를 검사하는 validation 함수를 만든다.

예:

`validate_caption_style_candidates`

검증 가능한 항목만 검증한다.

최소:

- 후보 수
- candidate id uniqueness
- 필요한 style property 존재
- 허용 palette role만 사용
- 승인 typography 변경 없음
- 승인 font weight 변경 없음
- 승인 font family 변경 없음
- invalid CSS 값 방지
- deterministic output
- Human Decision 없음

실제 browser layout을 측정하지 않았다면:

"browser clipping validation PASS"

라고 주장하지 마라.


# 19. Wrapping / Overflow에 대한 정직한 검증

Caption Style에서는 wrapping이 중요하다.

가능하다면 현재 코드에 safe-area/container width가 canonical하게 존재하는지 조사한다.

존재한다면 그 값을 사용해 구조적 검증을 한다.

존재하지 않는다면 임의의 canonical safe-area를 발명하지 마라.

그 경우 보고서에:

- browser pixel measurement not performed
- visual human inspection required

라고 명시한다.

실제 브라우저 자동 측정 환경이 이미 프로젝트에 존재한다면 재사용할 수 있다.

새 외부 browser dependency를 함부로 추가하지 않는다.


# 20. Existing Caption Scaffold와 충돌 검사

특히 과거 작업 중:

CB06 Caption Scaffold Visibility Correction

관련 코드/artifact가 존재하므로 반드시 조사한다.

이번 caption_style 후보가 기존 scaffold semantics를 덮어쓰거나 파괴하면 안 된다.

다음을 구분한다.

Caption content semantics
vs
Caption visual style

이번 단계는 visual style review다.

source_text/display_text 또는 production semantic content를 변경하지 않는다.


# 21. Production Data 불변

이번 작업 전후 다음 row/count/state를 기록한다.

최소:

production_blocks
speech_assets
generated_assets
render_specs
render_timelines
scene_layouts
visual_design_specs

직전 예상:

production_blocks:
56

speech_assets:
330

generated_assets:
506

render_specs:
3

render_timelines:
2

scene_layouts:
2

visual_design_specs:
10

하지만 예상값을 그대로 믿지 말고 실제 실행 전 DB에서 확인한다.

Caption Review Artifact 생성 때문에 canonical production data가 변하면 안 된다.


# 22. Canonical Visual DB — ZERO WRITE

이번 단계에서:

visual_design_specs

새 row 생성 금지.

expected:

before canonical id = 10
after canonical id = 10

expected visual_design_specs row count:

before = 10
after = 10

실제 값을 확인해서 보고한다.

다르면 원인을 조사하고 임의로 수정하지 않는다.


# 23. approved_visual_profile.json — ZERO CHANGE

이번 단계는 approval 단계가 아니다.

따라서 canonical:

`approved_visual_profile.json`

은 변경하면 안 된다.

가능하면 작업 전후 byte/hash 비교를 수행한다.

변경되었다면 작업을 성공으로 보고하지 말고 원인을 조사한다.


# 24. 기존 Review Artifact 불변

다음을 수정하지 않는다.

font review
background review
color palette review
muted color review
typography scale review
font weight review
기존 prototypes

가능하면 manifest/hash/revision 등 기존 프로젝트에서 사용한 방식으로 불변 여부를 확인한다.


# 25. Audio / Production / Layout 불변

다음을 변경하지 않는다.

Production Plan
production blocks
speech assets
WAV
Human Pronunciation Review
active generated assets
render specs
render timelines
scene layouts
source_text
display_text

이번 단계에서 필요한 것은 Caption Style Review Artifact뿐이다.


# 26. 외부 호출 금지

이번 단계에서 외부 API 호출은 필요 없다.

Gemini:
0

YouTube:
0

Video AI:
0

Image AI:
0

Font Network:
0

새 WAV:
0

새 MP4:
0


# 27. Tests

작업 전 반드시 전체 test baseline을 실제로 실행한다.

직전 예상:

969 passed

하지만 숫자를 복사하지 말고 실제 실행 결과를 baseline으로 기록한다.

구현 후:

- 신규 unit tests
- candidate validation tests
- zero DB write test
- canonical artifact unchanged test
- approved category preservation test
- candidate isolation test
- deterministic generation test
- palette-role constraint test
- no human decision test
- previous artifact preservation test

등 실제 의미 있는 테스트를 추가한다.

기존 테스트를 억지로 수정해서 통과시키지 않는다.

가능하면:

MODIFIED EXISTING TESTS = 0

을 유지한다.


# 28. Negative Tests

최소 다음 실패 조건을 검증한다.

CASE A:
caption candidate가 승인되지 않은 새 color hex를 직접 사용

→ FAIL

CASE B:
caption candidate가 approved typography size를 변경

→ FAIL

CASE C:
caption candidate가 approved font weight를 변경

→ FAIL

CASE D:
caption candidate가 approved font family를 변경

→ FAIL

CASE E:
caption candidate id 중복

→ FAIL

CASE F:
필수 style property 누락

→ FAIL

CASE G:
잘못된 CSS 값

→ FAIL

CASE H:
caption_style을 자동 APPROVED로 기록하려 함

→ FAIL

CASE I:
Human Decision을 임의로 candidate로 설정

→ FAIL

CASE J:
visual_design_specs에 row 추가

→ FAIL

CASE K:
approved_visual_profile.json 변경

→ FAIL

CASE L:
production/source_text/display_text 변경

→ FAIL

필요하면 실제 architecture에 맞게 추가한다.


# 29. Determinism

동일 canonical input으로 두 번 실행했을 때:

- candidate definitions
- manifest semantic content
- generated HTML semantic content

가 deterministic해야 한다.

timestamp처럼 의도된 비결정 필드가 있다면 구분해서 보고한다.

가능하면 review artifact 자체도 deterministic하게 만든다.


# 30. README

필요하다면 CLI 명령 한 줄 정도만 추가한다.

예:

`review-caption-style`

하지만 README에 아직 승인되지 않은 caption_style을 APPROVED라고 쓰지 않는다.

상태 문구를 과도하게 변경하지 않는다.


# 31. PROJECT_STATE.md 업데이트

이번 작업이 성공하면 PROJECT_STATE.md를 업데이트한다.

Current Major Stage:

13-4C Human Visual Review

Current Sub-stage:

13-4C-14 Caption Style Human Review
(Prototype generated, Human decision pending)

Canonical id:

실제 canonical id 그대로 유지

Expected:
10

Approved category count:

5

Pending category count:

10

caption_style:

PENDING_VISUAL_REVIEW

그리고 생성된 Review Artifact 경로와 후보 이름을 기록한다.

NEXT STEP:

Human reviews caption_style_review/index.html and selects a candidate.

아직 선택하지 않았다고 명확히 기록한다.


# 32. Human Decision 금지

이번 단계의 최종 상태는 반드시:

CAPTION STYLE STATUS:
PENDING_VISUAL_REVIEW

HUMAN DECISION:
NONE

이어야 한다.

사용자가 과거에 특정 스타일을 좋아했다고 추론해서 선택하지 않는다.

과거 YouTube 디자인 취향도 이번 Human Review 선택의 증거로 사용하지 않는다.


# 33. 다음 Approval 단계는 아직 만들지 않는다

이번 작업 완료 후 사용자가 실제 Prototype을 보고 후보를 선택한다.

그 후 별도:

13-4C-15 Caption Style Human Approval

단계에서 DB에 append-only로 persist한다.

13-4C-14에서 13-4C-15를 자동 실행하지 않는다.


# 34. Git

git commit:
NO

git push:
NO

사용자가 명시적으로 요청하기 전까지 수행하지 않는다.

현재 누적된 미커밋 변경을:

- revert
- reset
- checkout
- clean
- stash

하지 않는다.

이번 작업과 무관한 기존 변경은 그대로 둔다.


# 35. 구현 방식

기존 architecture를 최대한 재사용한다.

예상 구조:

`build_caption_style_candidates(...)`

`validate_caption_style_candidates(...)`

`run_caption_style_human_review(...)`

단, 실제 기존 코드 구조를 조사한 후 가장 자연스러운 방식으로 구현한다.

새로운 추상화가 필요하지 않다면 억지로 만들지 않는다.

Review generation은 canonical DB write와 분리한다.


# 36. 성공 기준

다음이 모두 만족되어야 성공이다.

1. PROJECT_STATE를 먼저 읽음
2. canonical source 검증
3. 기존 승인 5 category 정확히 보존
4. caption_style만 review variable
5. 후보 최소 3개 생성
6. 실제 학습 context Prototype 최소 6종
7. Side-by-Side 생성
8. index.html 생성
9. manifest.json 생성
10. Human Decision NONE
11. caption_style PENDING 유지
12. visual_design_specs zero write
13. canonical id 불변
14. approved_visual_profile.json 불변
15. production/audio/layout 불변
16. 기존 Review artifact 불변
17. 외부 API 0
18. WAV 0
19. MP4 0
20. tests 전체 PASS
21. regression 없음
22. PROJECT_STATE 업데이트
23. Stage 13-5 시작 안 함
24. Renderer 시작 안 함
25. git commit/push 없음


# 37. 완료 보고 형식

작업 완료 후 추상적인 요약만 하지 말고 다음을 실제 값으로 보고하라.

1. 수정/추가 파일
2. Architecture
3. 실행 전 test baseline
4. 실행 후 test count
5. 신규 test 수
6. 수정한 기존 test 수
7. Production Plan ID
8. Visual Design Version
9. Review Stage
10. Canonical Visual Candidate
11. canonical record id before/after
12. visual_design_specs row count before/after
13. Approved/Pending count before/after
14. 기존 승인 5 category 보존 여부
15. caption_style before/after status
16. Human Decision 존재 여부
17. Caption Style 후보 이름
18. 각 후보 exact properties
19. 각 후보 설계 근거
20. 사용 palette role
21. 승인 typography 고정 여부
22. 승인 font weight 고정 여부
23. 승인 font family 고정 여부
24. Prototype context 종류
25. 후보당 Prototype 수
26. 총 HTML 수
27. Side-by-Side 생성 여부
28. index.html 경로
29. manifest.json 경로
30. 한글/영어 혼합 검증 여부
31. short/long/two-line caption 검토 여부
32. wrapping/overflow 검증 방법
33. browser pixel measurement 수행 여부
34. CB06 caption scaffold와 충돌 여부
35. 신규 Validation
36. Negative CASE 결과
37. Determinism 결과
38. approved_visual_profile.json 변경 여부
39. 이전 Review artifact 불변 여부
40. Production/Render/Timeline/Layout 불변 여부
41. source_text/display_text 불변 여부
42. 전체 테스트 결과
43. regression 여부
44. 외부 호출 수
45. WAV 생성 여부
46. MP4 생성 여부
47. README 수정 여부/이유
48. PROJECT_STATE 수정 여부/내용
49. git commit 여부
50. git push 여부
51. 발견된 bug
52. semantic debt
53. limitations
54. unresolved critical
55. unresolved non-critical
56. Caption Style Human Review 준비 여부
57. 가장 먼저 열 파일
58. Human Review 선택지
59. 다음 단계
60. 성공 기준 전체 충족 여부


# 38. 최종 출력

마지막에 반드시 사람이 바로 이해할 수 있게 아래 형태로 출력한다.

CAPTION STYLE HUMAN REVIEW: READY

CAPTION STYLE STATUS:
PENDING_VISUAL_REVIEW

HUMAN DECISION:
NONE

CANONICAL VISUAL CANDIDATE:
CLEAN_DARK_FOCUS

FIXED APPROVED FONT FAMILY:
VERDANA_HUMANIST
Verdana, Geneva, 'Malgun Gothic', sans-serif

FIXED APPROVED BACKGROUND:
#111318

FIXED APPROVED TYPOGRAPHY SCALE:
DOMINANT 72px
PRIMARY 46px
SUPPORTING 28px
CAPTION 20px
MICRO 15px

FIXED APPROVED FONT WEIGHT:
DOMINANT 800
PRIMARY 700
SUPPORTING 500
CAPTION 400
MICRO 400

FONT FACE PROVENANCE:
Verdana native weights = 400, 700
800/500 remain browser-synthesized where applicable.

FIXED APPROVED COLOR PALETTE:
DEFAULT #e6e6e6
PRIMARY_FOCUS #60a5fa
RELATION #c4b5fd
SUCCESS #4ade80
SECONDARY #9ca3af
MUTED #757b87
EXCEPTION_CAUTION #fbbf24

CAPTION STYLE CANDIDATES:

1 = <actual candidate A>
    <actual exact properties>

2 = <actual candidate B>
    <actual exact properties>

3 = <actual candidate C>
    <actual exact properties>

4 = 세 후보 모두 부적절 — 새 후보 필요

APPROVED CATEGORY COUNT:
5

PENDING CATEGORY COUNT:
10

FULL APPROVED VISUAL PROFILE:
NO

READY FOR FINAL RENDERER BINDING:
NO

READY FOR STAGE 13-5:
NO

RENDERER:
NOT_STARTED

REVIEW FIRST:
assets/generated/plan_7/render/caption_style_review/index.html

NEXT:
Human reviews Caption Style candidates.
Do not persist Caption Style approval before the Human decision.
Do not start Stage 13-5.