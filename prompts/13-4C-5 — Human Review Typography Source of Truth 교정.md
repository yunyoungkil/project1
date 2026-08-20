# Stage 13-4C-5 — Human Review Typography Source of Truth 교정
# PRIMARY 40px / 700 복구 + Font Review 재생성

======================================================================
0. 이번 단계의 목적
======================================================================

이번 단계는 새로운 디자인을 만드는 단계가 아니다.

새 Font Candidate를 만드는 단계도 아니다.

이번 단계의 목적은 단 하나다.

13-4C-4에서 잘못 판단된 Human Review Source of Truth를
실제 사용자 결정과 다시 일치시키고,
그 정확한 baseline으로 Font Family 비교 Prototype을 재생성한다.

핵심 교정:

CLEAN_DARK_FOCUS preview/code value:
PRIMARY = 42px / 700

하지만 이후 Human Review에서 사용자가 명시적으로 선택한 값:
PRIMARY = 40px / 700

따라서 Font Review의 최신 Human Review Source of Truth는:

PRIMARY = 40px / 700

이다.

이번 단계에서는 이를 적용한다.

======================================================================
1. 현재 프로젝트 상태
======================================================================

현재 보고된 상태:

Production Plan ID:
7

Visual Design Version:
13.4

Canonical Visual Candidate:
CLEAN_DARK_FOCUS

Font Review revision:
13-4C-3

전체 test baseline:
821 PASS

Font Family:
PENDING_VISUAL_REVIEW

Full Approved Visual Profile:
NO

Ready for Final Renderer Binding:
NO

Ready for Stage 13-5:
NO

13-4C-4에서는 코드 변경이 이루어지지 않았다.

따라서 현재 Font Review Prototype은 여전히:

PRIMARY = 42px / 700

을 사용하고 있다.

======================================================================
2. 13-4C-4 판단 교정
======================================================================

13-4C-4 완료 보고에서는 다음과 같이 판단했다.

"CLEAN_DARK_FOCUS의 실제 코드 값이 42px이므로
42px가 정답이다."

이 판단을 이번 단계에서는 Source-of-Truth로 사용하지 마라.

이유:

기존 candidate code / preview value와
그 이후의 Human Review Decision은 별개의 provenance다.

시간적/의미적 관계:

1. CLEAN_DARK_FOCUS Prototype에 42px 존재
2. 사람이 CLEAN_DARK_FOCUS 방향을 선택
3. 이후 Typography Human Review 진행
4. PRIMARY 크기 후보:
   36px / 40px / 44px
5. 사용자가 ②를 선택
6. 따라서 PRIMARY Size = 40px
7. 이어서 PRIMARY Font Weight 후보에서
   사용자가 ② = 700을 선택

따라서 최신 Human Review Decision:

PRIMARY = 40px / 700

이다.

기존 42px은:

PREVIOUS_PREVIEW_VALUE

로 취급한다.

======================================================================
3. 중요한 provenance 원칙
======================================================================

다음은 서로 다른 개념이다.

CANDIDATE PREVIEW VALUE
≠
HUMAN REVIEW DECISION
≠
CANONICAL PERSISTED APPROVAL

현재 PRIMARY의 provenance는:

Previous CLEAN_DARK preview:
42px / 700

Human Review decision:
40px / 700

Canonical DB persistence:
아직 별도 승인 persistence가 필요할 수 있음

따라서 Font Review comparison baseline은:

40px / 700

을 사용해야 한다.

하지만 이번 Prototype 교정만으로
DB category 전체를 자동 APPROVED로 만들지는 마라.

======================================================================
4. 이번 단계의 Human Review Source of Truth
======================================================================

Font Review에 사용할 fixed typography baseline:

DOMINANT
68px / 800

PRIMARY
40px / 700

SUPPORTING
26px / 500

CAPTION
18px / 400

MICRO
14px / 400

이번 단계에서 PRIMARY만:

42px
→
40px

로 실제 교정한다.

다른 typography value는 변경하지 마라.

======================================================================
5. Human Review Color / Background baseline
======================================================================

Font Review에서는 기존에 결정된 다음 값을 그대로 고정한다.

BACKGROUND

page_bg:
#111318

COLOR PALETTE

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
#555b66

EXCEPTION_CAUTION:
#f59e0b

이번 단계에서 색상을 다시 설계하거나 변경하지 마라.

======================================================================
6. 먼저 실제 코드 조사
======================================================================

수정 전 다음을 조사하라.

research/visual_design.py

CANDIDATES["CLEAN_DARK_FOCUS"]

font review token source

build_font_learning_prototype

build_font_hierarchy_test_prototype

build_font_glyph_test_prototype

font review manifest builder

font review index builder

관련 tests

현재 보고에 따르면:

CANDIDATES["CLEAN_DARK_FOCUS"]["roles"]["PRIMARY"]
=
"font-size:42px;font-weight:700;"

이 single source에서 Learning/Hierarchy Prototype이
파생되고 있다.

실제 코드가 현재도 그러한지 다시 확인하라.

======================================================================
7. 수정 범위 판단
======================================================================

주의:

CANDIDATES["CLEAN_DARK_FOCUS"] 자체가
기존 13-4B-R1 Prototype까지 공유하는 global candidate라면
무조건 global value를 42→40으로 바꾸지 마라.

먼저 consumer를 조사한다.

두 경우를 구분하라.

CASE A
CANDIDATES의 PRIMARY를 변경해도
기존 13-4B-R1 historical Prototype/canonical artifact 의미를
훼손하지 않는다.

→ single source를 40px로 교정 가능.

CASE B
CANDIDATES가 historical 13-4B-R1 preview definition이기도 해서
global 수정 시 과거 artifact semantics까지 바뀐다.

→ historical candidate definition은 보존하고
Font Review용 HUMAN_REVIEW_FIXED_TYPOGRAPHY 또는
동등한 review override/token source를 만든다.

중요:

어떤 방식을 선택하든
Font Review의 Source of Truth는 40px이어야 한다.

하지만 과거 history를 거짓으로 다시 쓰면 안 된다.

======================================================================
8. 권장 데이터 모델
======================================================================

가능하면 다음 의미를 분리한다.

preview_candidate_tokens

human_review_fixed_tokens

canonical_approved_tokens

현재 Font Review는:

human_review_fixed_tokens

를 우선 사용한다.

예:

human_review_fixed_tokens = {
    "DOMINANT": {"size_px": 68, "weight": 800},
    "PRIMARY": {"size_px": 40, "weight": 700},
    "SUPPORTING": {"size_px": 26, "weight": 500},
    "CAPTION": {"size_px": 18, "weight": 400},
    "MICRO": {"size_px": 14, "weight": 400},
}

단 기존 architecture에 이미 동등한 구조가 있다면 재사용한다.

불필요하게 새 abstraction을 만들지 마라.

======================================================================
9. Font Candidate는 그대로 유지
======================================================================

후보:

VERDANA_HUMANIST

ARIAL_NEUTRAL

SEGOE_MODERN

3개를 그대로 유지한다.

후보 추가 금지.

후보 삭제 금지.

후보 자동 ranking 금지.

후보 자동 승인 금지.

이번 비교에서 변경되는 것은:

42px → 40px baseline correction

뿐이다.

======================================================================
10. Font Review 재생성
======================================================================

경로:

assets/generated/plan_7/render/font_review/

현재 13-4C-3 Font Review 산출물을
정확한 Human Review baseline으로 재생성한다.

구조 유지:

Learning Prototype 3

Glyph Prototype 3

Hierarchy Prototype 3

index.html

manifest.json

총 9개 HTML + index + manifest

Font Candidate마다 Font Family만 달라야 한다.

======================================================================
11. Font Review Revision
======================================================================

재생성 후 Font Review revision:

13-4C-5

로 기록한다.

주의:

13-4C-4는 실제 artifact 변경이 없었으므로
Font Review artifact revision으로 사용할 필요가 없다.

Visual Design Version:

13.4

는 변경하지 마라.

Prototype lineage 예:

13-4C-3
→ 13-4C-4 NO-OP / investigation
→ 13-4C-5 corrected font review

로 보고한다.

======================================================================
12. Learning Prototype
======================================================================

모든 후보의 Learning Prototype에서:

DOMINANT = 68px / 800

PRIMARY = 40px / 700

SUPPORTING = 26px / 500

CAPTION = 18px / 400

MICRO = 14px / 400

을 사용한다.

특히 Prompt 등 PRIMARY role의 실제 CSS를 검사하여:

font-size: 40px
font-weight: 700

인지 확인한다.

42px이 남아 있으면 실패다.

======================================================================
13. Hierarchy Prototype
======================================================================

Hierarchy Prototype에는 실제 token에서 파생하여:

DOMINANT — 68px / 800

PRIMARY — 40px / 700

SUPPORTING — 26px / 500

CAPTION — 18px / 400

MICRO — 14px / 400

을 표시한다.

label과 CSS가 반드시 같아야 한다.

금지:

label만 40
CSS는 42

또는:

label 42
CSS 40

======================================================================
14. Glyph Prototype
======================================================================

Glyph test 내용은 그대로 유지한다.

I / l / 1

O / 0

b / d

p / q

u / v

c / e

rn / m

a / o

CAP → cap

BAT → bat

MAP → map

BAG → bag

Glyph test의 목적은 Font Family 비교다.

내용을 확장하거나 재설계하지 마라.

======================================================================
15. 후보 간 비교 변수
======================================================================

재생성된 세 후보를 비교했을 때:

Font Family

외에는 visual variable 차이가 없어야 한다.

동일해야 하는 항목:

text

layout

background

color

font-size

font-weight

spacing

container

role

sample content

responsive behavior

후보 간 PRIMARY size 차이가 있으면 실패다.

======================================================================
16. Historical Prototype 보호
======================================================================

다음 경로는 수정하지 마라.

assets/generated/plan_7/render/prototypes/

13-4B-R1 26개 Prototype

13-4B-R1 manifest

13-4B-R1 index

SOFT_LIGHT history

CLEAN_DARK historical Prototype

이번 단계에서 수정 가능한 렌더 artifact는:

assets/generated/plan_7/render/font_review/

뿐이다.

======================================================================
17. 42px provenance 보존
======================================================================

42px이 기존 CLEAN_DARK preview에서 사용됐다는 사실을
삭제하거나 숨기지 마라.

완료 보고에 명시한다.

예:

PREVIOUS CLEAN_DARK PREVIEW PRIMARY:
42px / 700

LATEST HUMAN REVIEW PRIMARY:
40px / 700

FONT REVIEW BASELINE:
40px / 700

이렇게 provenance를 구분한다.

======================================================================
18. Canonical DB Approval은 별도
======================================================================

이번 단계는 Font Family 선택 전 단계다.

따라서:

font_family = PENDING_VISUAL_REVIEW

유지.

또한 Font Review 재생성만으로:

full_profile_approved = true

금지.

ready_for_final_renderer_binding = true

금지.

Ready for Stage 13-5 = YES

금지.

======================================================================
19. Color/Typography canonical persistence
======================================================================

이번 단계에서 중요한 점:

현재 대화 Human Review에서는
Color/Background/Typography 값이 결정되었다.

하지만 13-4C-2 DB correction row에서는
15개 category가 모두 PENDING이었다.

따라서 실제 DB가 아직 그 상태라면:

HUMAN REVIEW DECISION:
EXISTS

CANONICAL PERSISTENCE:
PENDING

이라고 보고한다.

이번 13-4C-5에서
그 approval persistence까지 섞어 처리하지 마라.

Font Review baseline 교정만 수행한다.

후속 단계에서 정식 persistence를 처리한다.

======================================================================
20. Mandatory Tests
======================================================================

최소 다음을 테스트하라.

CASE A

Font Review PRIMARY size == 42
→ FAIL

CASE B

Font Review PRIMARY size != 40
→ FAIL

CASE C

PRIMARY weight != 700
→ FAIL

CASE D

Hierarchy label != 40px / 700
→ FAIL

CASE E

Hierarchy CSS != 40px / 700
→ FAIL

CASE F

Learning Prototype PRIMARY != 40px / 700
→ FAIL

CASE G

Candidate A/B/C PRIMARY 값 불일치
→ FAIL

CASE H

DOMINANT != 68 / 800
→ FAIL

CASE I

SUPPORTING != 26 / 500
→ FAIL

CASE J

CAPTION != 18 / 400
→ FAIL

CASE K

MICRO != 14 / 400
→ FAIL

CASE L

Background != #111318
→ FAIL

CASE M

Color Palette mismatch
→ FAIL

CASE N

Font Candidate 목록 변경
→ FAIL

CASE O

Font Family 외 candidate visual difference
→ FAIL

CASE P

기존 13-4B-R1 Prototype 변경
→ FAIL

CASE Q

13-4B-R1 manifest 변경
→ FAIL

CASE R

Font Review 생성으로 font_family APPROVED
→ FAIL

CASE S

Font Review 생성으로 full_profile_approved=True
→ FAIL

CASE T

Font Review 생성으로 renderer ready=True
→ FAIL

CASE U

Font Review manifest revision != 13-4C-5
→ FAIL

CASE V

Visual Design Version != 13.4
→ FAIL

CASE W

42px previous-preview provenance가
40px Human Review provenance로 거짓 덮어쓰기됨
→ FAIL

======================================================================
21. Test baseline
======================================================================

현재 보고된 baseline:

821 PASS

작업 시작 전 실제 전체 suite를 실행하여 확인한다.

수정 후 필요한 regression test를 추가한다.

전체 test suite PASS 필수.

기존 테스트가:

PRIMARY = 42

를 Font Review truth로 기대한다면
40으로 수정해야 한다.

단 기존 historical CLEAN_DARK preview 자체가
42였음을 검증하는 테스트라면
무조건 수정하지 마라.

둘의 의미를 구분한다.

======================================================================
22. DB row
======================================================================

이번 단계에서:

visual_design_specs

새 row 생성하지 않는 것을 기본으로 한다.

Font Family가 아직 선택되지 않았기 때문이다.

DB를 변경해야 할 기술적 이유가 없다면
0 writes가 맞다.

완료 보고에서 row count 전/후를 확인한다.

======================================================================
23. 상류 불변
======================================================================

다음은 절대 변경하지 마라.

Production Plan 7

production_blocks

speech_assets

generated_assets

Render Spec

Timeline

Scene Layout

WAV

Human Pronunciation Review

source_text

display_text

active asset

CB06 PAUSE

CB06 Answer Reveal Barrier

CB07 semantics

CAP = SP039::CONTEXTUAL_WORD

BAG = SP003

MAP = SP029

BAT = SP016

======================================================================
24. 외부 호출 금지
======================================================================

Font download = 0

External Font Network = 0

Google Fonts = 0

Gemini TTS = 0

YouTube API = 0

영상 생성 AI = 0

이미지 생성 AI = 0

MP4 = 0

WAV 생성 = 0

======================================================================
25. Git
======================================================================

사용자 요청 전:

git commit 금지

git push 금지

git status 확인 허용.

======================================================================
26. 이번 단계에서 하지 말 것
======================================================================

Font Family 선택 금지

Font Family 승인 금지

Verdana 자동 추천/승인 금지

Arial 자동 탈락 금지

Segoe UI 자동 승인 금지

새 Font 추가 금지

Color 변경 금지

Background 변경 금지

Typography hierarchy 재설계 금지

DOMINANT 변경 금지

SUPPORTING 변경 금지

CAPTION 변경 금지

MICRO 변경 금지

Spacing 결정 금지

Container 결정 금지

Border 결정 금지

Radius 결정 금지

Caption Style 결정 금지

Focus Style 결정 금지

Success Style 결정 금지

Motion 결정 금지

Output Profile 결정 금지

Stage 13-5 실행 금지

Final Renderer 실행 금지

MP4 생성 금지

======================================================================
27. 완료 후 기대 상태
======================================================================

PREVIOUS CLEAN_DARK PREVIEW PRIMARY:
42px / 700

LATEST HUMAN REVIEW PRIMARY:
40px / 700

FONT REVIEW PRIMARY:
40px / 700

FONT REVIEW REVISION:
13-4C-5

FONT CANDIDATES:

VERDANA_HUMANIST
ARIAL_NEUTRAL
SEGOE_MODERN

FONT FAMILY STATUS:
PENDING_VISUAL_REVIEW

CANONICAL VISUAL CANDIDATE:
CLEAN_DARK_FOCUS

FULL APPROVED VISUAL PROFILE:
NO

READY FOR FINAL RENDERER BINDING:
NO

READY FOR STAGE 13-5:
NO

HUMAN FONT REVIEW:
READY

======================================================================
28. 완료 보고
======================================================================

완료 후 다음을 번호로 보고하라.

1. 수정/추가 파일
2. 13-4C-5 Architecture
3. 실행 전 baseline test 수
4. 실행 후 전체 test 수
5. 신규 테스트 수
6. 수정한 기존 테스트 수
7. Production Plan ID
8. Visual Design version
9. 이전 Font Review revision
10. 새 Font Review revision
11. Canonical Visual Candidate
12. previous CLEAN_DARK PRIMARY
13. latest Human Review PRIMARY
14. 실제 Font Review PRIMARY
15. PRIMARY weight
16. 42px source 위치
17. 40px review source 구현 위치
18. global CANDIDATES 수정 여부
19. global 수정/별도 review override 선택 이유
20. historical 42px provenance 보존 여부
21. DOMINANT
22. SUPPORTING
23. CAPTION
24. MICRO
25. Background
26. Color Palette 전체
27. Font Candidate 수
28. Font Candidate 이름
29. Candidate 변경 여부
30. Font Family 외 candidate 차이 여부
31. Learning Prototype 재생성 수
32. Glyph Prototype 재생성 수
33. Hierarchy Prototype 재생성 수
34. 전체 Font Review HTML 수
35. Learning PRIMARY CSS
36. Hierarchy PRIMARY CSS
37. Hierarchy PRIMARY label
38. Candidate A PRIMARY
39. Candidate B PRIMARY
40. Candidate C PRIMARY
41. manifest revision
42. index 갱신 여부
43. manifest 갱신 여부
44. 기존 13-4B-R1 Prototype 불변 여부
45. 기존 13-4B-R1 manifest 불변 여부
46. Human Review Decision과 Preview Value 분리 결과
47. Human Review Decision과 Canonical Persistence 분리 결과
48. font_family status
49. full_profile_approved
50. ready_for_final_renderer_binding
51. Ready for Stage 13-5
52. visual_design_specs row 수 before/after
53. 신규 DB row 생성 여부
54. 신규 Validation
55. 신규 Integrity Check
56. Mandatory CASE A~W 결과
57. 전체 테스트 결과
58. 기존 821 tests 회귀 여부
59. 13-4A 회귀 여부
60. 13-4B 회귀 여부
61. 13-4B-R 회귀 여부
62. 13-4B-R1 회귀 여부
63. 13-4C-2 회귀 여부
64. 13-4C-3 회귀 여부
65. Production Plan 불변 여부
66. Render Spec 불변 여부
67. Timeline 불변 여부
68. Scene Layout 불변 여부
69. WAV 불변 여부
70. Human Pronunciation Review 불변 여부
71. CAP/BAG/MAP/BAT 불변 여부
72. source_text/display_text 불변 여부
73. Font download 수
74. External Font Network 수
75. Gemini TTS 호출 수
76. YouTube API 호출 수
77. 영상 생성 AI 호출 수
78. 이미지 생성 AI 호출 수
79. MP4 생성 여부
80. git commit 여부
81. git push 여부
82. 발견된 실제 bug/semantic debt
83. 발견된 제한사항
84. unresolved critical
85. unresolved non-critical
86. Human Font Review 준비 여부
87. 사용자가 가장 먼저 열 파일
88. 사용자가 비교해야 할 정확한 항목
89. 다음 단계
90. 성공 기준 전체 충족 여부

마지막에는 반드시 다음 형식으로 출력하라.

HUMAN REVIEW TYPOGRAPHY SOURCE OF TRUTH: RESTORED / NOT RESTORED

PREVIOUS CLEAN_DARK PRIMARY: 42px / 700

LATEST HUMAN REVIEW PRIMARY: 40px / 700

FONT REVIEW PRIMARY: 40px / 700

FONT REVIEW REVISION: 13-4C-5

FONT FAMILY HUMAN REVIEW: READY / NOT READY

FONT FAMILY STATUS: PENDING_VISUAL_REVIEW

CANONICAL VISUAL CANDIDATE: CLEAN_DARK_FOCUS

FULL APPROVED VISUAL PROFILE: NO

READY FOR FINAL RENDERER BINDING: NO

READY FOR STAGE 13-5: NO

FONT CANDIDATES:
VERDANA_HUMANIST
ARIAL_NEUTRAL
SEGOE_MODERN

REVIEW FIRST:
<정확한 파일>

======================================================================
29. 성공 기준
======================================================================

다음을 모두 만족해야 성공이다.

- 기존 CLEAN_DARK preview 42px provenance 보존
- 최신 Human Review 40px provenance 보존
- Font Review에서 PRIMARY 40px 실제 적용
- PRIMARY weight 700
- DOMINANT 68/800
- SUPPORTING 26/500
- CAPTION 18/400
- MICRO 14/400
- Background #111318
- 승인된 review Color Palette 유지
- Font 후보 3개 유지
- Font Family만 비교 변수
- Learning Prototype 40/700
- Hierarchy Prototype 40/700
- label/CSS 일치
- Font Review revision 13-4C-5
- 기존 13-4B-R1 Prototype 불변
- Font 자동 선택 없음
- Font 자동 승인 없음
- DB Full Approval 없음
- Renderer Gate NO
- Stage 13-5 NO
- 상류 데이터 불변
- 전체 테스트 PASS
- 외부 호출 0
- MP4 0
- commit/push 없음

이번 단계의 핵심 원칙:

"코드에 먼저 존재했다는 이유만으로
그 값이 이후 Human Review 결정보다 우선하지 않는다."

42px은 CLEAN_DARK_FOCUS의 이전 Preview 값이다.

40px / 700은 이후 Typography Human Review에서
사람이 선택한 값이다.

둘을 삭제하거나 섞지 말고 provenance를 보존하면서,
현재 Font Family 비교에는 최신 Human Review 값인
40px / 700을 사용하라.