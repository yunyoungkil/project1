# Stage 13-4C-4 — Font Review Typography Baseline 정합성 교정
# PRIMARY 42px → 40px Human Review Source-of-Truth 반영

현재 프로젝트는 다음 상태다.

- Stage 13-1 완료
- Stage 13-2 완료
- Stage 13-3 완료
- Stage 13-4A 완료
- Stage 13-4B 완료
- Stage 13-4B-R 완료
- Stage 13-4B-R1 완료
- Stage 13-4C-2 승인 정합성 교정 완료
- Stage 13-4C-3 Font Family 비교 Prototype 생성 완료
- 전체 테스트 baseline: 821 PASS
- Production Plan ID: 7
- Visual Design version: 13.4
- Canonical Visual Candidate: CLEAN_DARK_FOCUS
- Font Family: PENDING_VISUAL_REVIEW
- Full Approved Visual Profile: NO
- Ready for Final Renderer Binding: NO
- Ready for Stage 13-5: NO

이번 단계는 새로운 Font 후보를 만드는 단계가 아니다.

이번 단계는 Font Review Prototype의 Typography baseline이
실제 Human Review Source of Truth와 일치하도록 교정하는
작은 정합성 수정 단계다.

핵심 문제:

13-4C-3에서 Font hierarchy Prototype을 생성할 때
CANDIDATES["CLEAN_DARK_FOCUS"]["roles"]["PRIMARY"]의 기존 코드 값인:

PRIMARY = 42px / 700

을 사용했다.

하지만 실제 Human Review에서는 이미:

PRIMARY = 40px / 700

으로 명시적으로 결정되었다.

따라서 현재 Font Review Prototype은
폰트 비교 조건 중 PRIMARY size 하나가
Human Review baseline과 불일치한다.

이번 단계에서는 이 한 가지 정합성 문제를 바로잡고
동일한 Font Family 비교 Prototype을 재생성한다.

======================================================================
1. Human Review Source of Truth
======================================================================

다음 값은 현재 대화에서 실제로 Human Review로 결정되었다.

--------------------------------------------------
BACKGROUND
--------------------------------------------------

page_bg
#111318

--------------------------------------------------
COLOR PALETTE
--------------------------------------------------

DEFAULT
#e6e6e6

PRIMARY_FOCUS
#60a5fa

RELATION
#c4b5fd

SUCCESS
#4ade80

SECONDARY
#9ca3af

MUTED
#555b66

EXCEPTION_CAUTION
#f59e0b

--------------------------------------------------
TYPOGRAPHY SCALE
--------------------------------------------------

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

이번 단계에서 위 값을 Human Review baseline으로 사용한다.

중요:

이 단계는 이 값을 새로 결정하는 단계가 아니다.

이미 결정된 Human Review 결과를
Font Review Prototype에 정확히 반영하는 단계다.

======================================================================
2. 현재 확인된 불일치
======================================================================

13-4C-3 완료 보고에 따르면:

실제 코드:

CANDIDATES["CLEAN_DARK_FOCUS"]["roles"]["PRIMARY"]

값이:

42px / 700

이었다.

Font Review hierarchy Prototype도
실제 코드 값에서 label을 파생하도록 수정되어:

PRIMARY — 42px / 700

으로 표시되었다.

코드와 HTML은 서로 일치한다.

하지만 둘 다 Human Review Source of Truth:

PRIMARY = 40px / 700

과 불일치한다.

따라서 이번 문제는:

"label bug"

가 아니다.

정확한 문제는:

"Font Review baseline candidate token이
Human Review에서 이미 결정된 typography token과 불일치"

이다.

======================================================================
3. 이번 수정의 정확한 목표
======================================================================

CLEAN_DARK_FOCUS Font Review baseline에서:

PRIMARY size

42px
→
40px

로 교정한다.

PRIMARY weight:

700

은 변경하지 않는다.

나머지 Typography:

DOMINANT 68 / 800
SUPPORTING 26 / 500
CAPTION 18 / 400
MICRO 14 / 400

은 변경하지 않는다.

Color Palette도 변경하지 않는다.

Background도 변경하지 않는다.

Font 후보도 변경하지 않는다.

======================================================================
4. 수정 전 반드시 조사
======================================================================

다음 위치를 조사하라.

research/visual_design.py

특히:

CANDIDATES["CLEAN_DARK_FOCUS"]

roles

typography-related candidate values

font review generator

build_font_hierarchy_test_prototype

build_font_learning_prototype

manifest generator

관련 tests

확인할 것:

PRIMARY = 42가 어디에서 정의되는가?

42가 다른 Prototype/Visual Design path에서도 사용되는가?

13-4A canonical semantic role인가?

단순 Preview candidate 값인가?

다른 Scene Prototype이 이 값을 참조하는가?

이번 Human Review decision을 반영하려면
어느 single source를 수정해야 가장 정합적인가?

중복 하드코딩을 만들지 마라.

======================================================================
5. Source-of-Truth 원칙
======================================================================

이번 단계 이후 Font Review가 사용하는 Typography 값은
가능한 한 한 곳에서 파생되어야 한다.

다음처럼 서로 다른 값이 생기면 안 된다.

Candidate config:
40px

Learning Prototype:
42px

Hierarchy Prototype:
40px

Manifest:
42px

Test expected:
40px

이런 구조를 금지한다.

모든 Font Review artifact가
같은 Review Typography baseline에서 파생되어야 한다.

======================================================================
6. Canonical Visual Design과 Review Baseline 구분
======================================================================

중요:

13-4C-2에서 canonical DB category 상태는
15개 전부 PENDING_VISUAL_REVIEW로 정리되었다.

이후 대화에서 사람은 실제로:

Color Palette
Background
Typography Scale

값을 하나씩 결정했다.

따라서 현재 상태는 의미적으로:

HUMAN REVIEW DECISION EXISTS

BUT

CANONICAL APPROVAL PERSISTENCE MAY STILL BE PENDING

일 수 있다.

이번 13-4C-4는:

font review baseline correction

단계다.

이번 단계에서 DB category approval을
자동 기록하지 마라.

즉:

Human Review baseline을 Prototype에 반영

≠

canonical approved_visual_profile에 자동 APPROVED 기록

이다.

후속 Approval Persistence 단계에서
정식 기록할 수 있도록 완료 보고에 차이를 명시하라.

======================================================================
7. Font 후보 불변
======================================================================

현재 후보:

VERDANA_HUMANIST

font stack:
Verdana, Geneva, 'Malgun Gothic', sans-serif

ARIAL_NEUTRAL

font stack:
Arial, Helvetica, 'Malgun Gothic', sans-serif

SEGOE_MODERN

font stack:
'Segoe UI', Tahoma, Geneva, 'Malgun Gothic', sans-serif

를 유지한다.

후보 추가 금지.

후보 삭제 금지.

후보 순서 변경은 특별한 이유 없으면 하지 마라.

이번 단계의 비교 변수는 계속:

FONT FAMILY ONLY

여야 한다.

======================================================================
8. Font Review Prototype 고정 조건
======================================================================

후보 3개 모두 정확히 같은 값을 사용해야 한다.

Background:
#111318

Color:

DEFAULT #e6e6e6
PRIMARY_FOCUS #60a5fa
RELATION #c4b5fd
SUCCESS #4ade80
SECONDARY #9ca3af
MUTED #555b66
EXCEPTION_CAUTION #f59e0b

Typography:

DOMINANT 68px / 800
PRIMARY 40px / 700
SUPPORTING 26px / 500
CAPTION 18px / 400
MICRO 14px / 400

Font Family만 후보마다 다르게 한다.

======================================================================
9. 기존 13-4C-3 Font Review 산출물
======================================================================

현재 경로:

assets/generated/plan_7/render/font_review/

현재 구성:

Learning Prototype 3
Glyph Prototype 3
Hierarchy Prototype 3
index.html
manifest.json

총 9개 HTML + index + manifest

이 구조를 유지할 수 있다.

이번 단계에서는 동일 경로를 재생성해도 되지만
기존 artifact lineage를 명확히 해야 한다.

manifest revision은:

13-4C-4

또는 동등한 revision identifier로 갱신하는 것을 우선한다.

Visual Design version:

13.4

는 변경하지 않는다.

======================================================================
10. Prototype Revision
======================================================================

Font Review manifest에:

revision = "13-4C-4"

review_type = "FONT_FAMILY"

를 기록하라.

기존:

13-4C-3

artifact가 history로 git/worktree에만 남는 구조라면
그 사실을 보고하라.

별도 history directory를 억지로 만들 필요는 없다.

단 현재 manifest가 어떤 revision인지
사람이 알 수 있어야 한다.

======================================================================
11. Hierarchy Prototype 요구사항
======================================================================

Hierarchy Prototype에는 실제 값에서 파생된:

DOMINANT — 68px / 800

PRIMARY — 40px / 700

SUPPORTING — 26px / 500

CAPTION — 18px / 400

MICRO — 14px / 400

가 표시되어야 한다.

label을 다시 하드코딩하지 마라.

실제 적용 style/token에서 파생하라.

그렇다고 CSS 문자열을 brittle하게 parsing하는 구조가
불필요하게 복잡하다면
shared token object에서:

display label
CSS value

둘 다 생성하는 구조를 우선한다.

가장 단순하고 안정적인 single source를 사용하라.

======================================================================
12. Learning Prototype 요구사항
======================================================================

Learning Prototype에서도 PRIMARY role이 등장한다면:

40px / 700

이 실제 적용되어야 한다.

DOMINANT:
68 / 800

SUPPORTING:
26 / 500

CAPTION:
18 / 400

MICRO:
14 / 400

도 기존과 동일해야 한다.

Font 후보 간 차이는:

font-family

하나뿐이어야 한다.

======================================================================
13. Glyph Prototype
======================================================================

Glyph Prototype의 목적은 Font 자체 비교이므로
PRIMARY 42→40 수정과 무관한 부분을 변경하지 마라.

기존 comparison set 유지:

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

필요 없는 문자열 추가 금지.

======================================================================
14. 실제 Font Weight 한계 보존
======================================================================

13-4C-3에서 확인된 제한:

세 후보 모두 native 800 weight 미지원 가능성
→ Browser가 synthetic bold로 근사

이 사실을 숨기지 마라.

이번 단계에서:

새 Font를 다운로드하여
native 800 문제를 해결하려 하지 마라.

현재 Font Review는:

이 제한을 가진 상태에서 사람이
실제 글자 형태를 비교하는 단계다.

======================================================================
15. Human Review Typography 결정 기록
======================================================================

이번 단계 report/manifest에
다음 context를 명시할 수 있다.

review_fixed_values:

background
color_palette
typography_scale

그리고 typography_scale:

DOMINANT 68/800
PRIMARY 40/700
SUPPORTING 26/500
CAPTION 18/400
MICRO 14/400

단 status를:

CANONICAL_APPROVED

라고 자동 기록하지 마라.

더 정확한 의미:

HUMAN_REVIEW_FIXED_FOR_COMPARISON

또는 동등한 non-canonical review metadata를 사용하라.

정확한 이름은 기존 architecture에 맞춘다.

======================================================================
16. Color/Background 값도 정확히 유지
======================================================================

이번 단계에서 다음 값이 바뀌면 안 된다.

#111318

#e6e6e6

#60a5fa

#c4b5fd

#4ade80

#9ca3af

#555b66

#f59e0b

Font 후보별 색상 차이 금지.

======================================================================
17. Font Review의 목적 재확인
======================================================================

이번 교정 후 사람은 오직 Font Family를 비교해야 한다.

다음 질문이 화면에 섞이면 안 된다.

"PRIMARY 크기는 40이 좋은가 42가 좋은가?"

이 질문은 이미 끝났다.

Font Review에서는:

40px

을 고정한다.

사람이 판단할 질문은:

Verdana 계열
Arial 계열
Segoe UI 계열

중 어떤 Font Family가
왕초보 영어 학습에 가장 적절한가?

하나다.

======================================================================
18. Mandatory Regression Tests
======================================================================

최소 다음을 테스트하라.

CASE A

CLEAN_DARK_FOCUS PRIMARY size != 40
→ FAIL

CASE B

CLEAN_DARK_FOCUS PRIMARY weight != 700
→ FAIL

CASE C

Hierarchy label PRIMARY != 40px / 700
→ FAIL

CASE D

Hierarchy 실제 CSS PRIMARY != 40px / 700
→ FAIL

CASE E

Learning Prototype PRIMARY != 40px / 700
→ FAIL

CASE F

Candidate A PRIMARY != Candidate B PRIMARY
→ FAIL

CASE G

Candidate B PRIMARY != Candidate C PRIMARY
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

Font 후보 목록 변경
→ FAIL

CASE O

font-family 외 Candidate visual difference 존재
→ FAIL

CASE P

Font Review 생성으로 font_family APPROVED
→ FAIL

CASE Q

Font Review 생성으로 full_profile_approved=True
→ FAIL

CASE R

Font Review 생성으로 ready_for_final_renderer_binding=True
→ FAIL

CASE S

manifest revision != 13-4C-4
→ FAIL

CASE T

Visual Design version != 13.4
→ FAIL

======================================================================
19. Human Review Source-of-Truth Regression
======================================================================

다음도 테스트 또는 validation으로 보장하라.

Human Review comparison baseline:

PRIMARY = 40

이어야 한다.

다시는:

CANDIDATES 코드 값이 42니까
42가 truth

라고 간주하면 안 된다.

이번 단계에서 명시된 Human Review decision이
Font Review comparison의 Source of Truth다.

단 canonical DB approval 상태와는 구분한다.

======================================================================
20. 기존 테스트
======================================================================

현재 baseline:

821 tests PASS

작업 시작 전 실제로 baseline을 확인하라.

변경 후 신규 테스트를 추가한다.

전체 suite PASS 필수.

기존 test를 42px 기대값에서
40px 기대값으로 수정해야 한다면
그 이유를 명확히 기록하라.

이것은 arbitrary test update가 아니라
Human Review Source-of-Truth correction이다.

======================================================================
21. 기존 Prototype 보호
======================================================================

다음 경로는 수정하지 마라.

assets/generated/plan_7/render/prototypes/

기존 13-4B/R/R1 Prototype

CB06 6-phase

CLEAN_DARK/ SOFT_LIGHT visual prototype

이번 단계는:

font_review/

만 수정한다.

======================================================================
22. DB 변경 금지
======================================================================

이번 단계에서는:

visual_design_specs

새 row를 추가하지 않는 것을 기본으로 한다.

이유:

Font Family는 아직 선택되지 않았다.

현재는 비교 Prototype baseline만 교정하는 단계다.

DB category approval 수정 금지.

font_family:
PENDING_VISUAL_REVIEW

유지.

Full Profile:
NO

Renderer Gate:
NO

Stage 13-5:
NO

======================================================================
23. 상류 불변
======================================================================

변경 금지:

Production Plan

Render Spec

Timeline

Scene Layout

WAV

Human Pronunciation Review

active assets

source_text

display_text

CB06 PAUSE

CB06 Barrier

CB07 semantics

CAP = SP039::CONTEXTUAL_WORD

BAG = SP003

MAP = SP029

BAT = SP016

======================================================================
24. 외부 호출 금지
======================================================================

Font download = 0

External font network = 0

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

사용자가 명시적으로 요청하지 않았다.

git commit 금지

git push 금지

git status 확인 허용.

======================================================================
26. 이번 단계에서 하지 말 것
======================================================================

Font Family 자동 선택 금지

Font Family 자동 승인 금지

Verdana를 자동 우승자로 지정 금지

Arial 자동 탈락 금지

Segoe UI 자동 우승 금지

새 Font 후보 추가 금지

Open-source Font 다운로드 금지

Color 재설계 금지

Background 재설계 금지

Typography hierarchy 재설계 금지

40px를 다시 질문하는 Prototype 생성 금지

Spacing 확정 금지

Caption Style 확정 금지

Motion Style 확정 금지

Output Profile 확정 금지

Stage 13-5 실행 금지

Final Renderer 실행 금지

======================================================================
27. 완료 후 기대 상태
======================================================================

Font Review Revision:
13-4C-4

Canonical Visual Candidate:
CLEAN_DARK_FOCUS

Font candidates:

VERDANA_HUMANIST
ARIAL_NEUTRAL
SEGOE_MODERN

Review Typography Baseline:

DOMINANT 68/800
PRIMARY 40/700
SUPPORTING 26/500
CAPTION 18/400
MICRO 14/400

Font Family:
PENDING_VISUAL_REVIEW

Full Approved Visual Profile:
NO

Ready for Final Renderer Binding:
NO

Ready for Stage 13-5:
NO

Human Font Review:
READY

======================================================================
28. 완료 보고
======================================================================

완료 후 다음을 번호로 보고하라.

1. 수정/추가 파일
2. 13-4C-4 Architecture
3. 실행 전 baseline test 수
4. 실행 후 전체 test 수
5. 신규 테스트 수
6. 수정한 기존 테스트 수
7. Production Plan ID
8. Visual Design version
9. Font Review revision
10. Canonical Visual Candidate
11. 발견된 42px Source 위치
12. 42px가 사용되던 consumer 목록
13. 수정한 single source
14. PRIMARY 수정 전 값
15. PRIMARY 수정 후 값
16. PRIMARY weight 불변 여부
17. DOMINANT 값
18. SUPPORTING 값
19. CAPTION 값
20. MICRO 값
21. Background 값
22. Color Palette 전체 값
23. Human Review baseline과 code 값 정합성
24. Human Review baseline과 manifest 정합성
25. Human Review baseline과 Learning Prototype 정합성
26. Human Review baseline과 Hierarchy Prototype 정합성
27. Glyph Prototype 변경 여부
28. Font Candidate 수
29. Font Candidate 이름
30. Candidate 목록 변경 여부
31. Candidate 간 font-family 외 차이 여부
32. Learning Prototype 재생성 수
33. Glyph Prototype 재생성 수
34. Hierarchy Prototype 재생성 수
35. 총 Font Review HTML 수
36. index.html 갱신 여부
37. manifest.json 갱신 여부
38. manifest revision
39. review_fixed_values 기록 여부
40. Human Review decision과 Canonical DB 상태 구분 결과
41. font_family status
42. full_profile_approved
43. ready_for_final_renderer_binding
44. Ready for Stage 13-5
45. visual_design_specs row 추가 여부
46. 기존 26개 Prototype 불변 여부
47. 13-4B-R1 manifest 불변 여부
48. Production Plan 불변 여부
49. Render Spec 불변 여부
50. Timeline 불변 여부
51. Scene Layout 불변 여부
52. WAV 불변 여부
53. Human Pronunciation Review 불변 여부
54. active assets 불변 여부
55. source_text/display_text 불변 여부
56. Font download 수
57. External Font network 수
58. Gemini TTS 호출 수
59. YouTube API 호출 수
60. 영상 생성 AI 호출 수
61. 이미지 생성 AI 호출 수
62. MP4 생성 여부
63. 신규 Validation
64. 신규 Integrity Check
65. 신규 테스트 결과
66. 전체 테스트 결과
67. 기존 821 tests 회귀 여부
68. git commit 여부
69. git push 여부
70. 발견된 추가 bug/semantic debt
71. 발견된 제한사항
72. unresolved critical
73. unresolved non-critical
74. Human Font Review 준비 여부
75. 사용자가 가장 먼저 열 파일
76. 다음 Human Review에서 판단할 정확한 질문
77. 성공 기준 전체 충족 여부

마지막에는 반드시:

FONT REVIEW BASELINE: CORRECTED / NOT CORRECTED

PRIMARY TYPOGRAPHY: 40px / 700

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

라고 출력하라.

======================================================================
29. 성공 기준
======================================================================

이번 단계 성공 조건:

- PRIMARY 42px → 40px 교정
- PRIMARY weight 700 유지
- DOMINANT 68/800 유지
- SUPPORTING 26/500 유지
- CAPTION 18/400 유지
- MICRO 14/400 유지
- Human Review Color Palette 유지
- Background #111318 유지
- 후보 3개 유지
- Font Family만 비교 변수
- Learning Prototype 40px baseline 사용
- Hierarchy Prototype 40px baseline 사용
- hierarchy label과 실제 CSS 일치
- Manifest 13-4C-4 lineage
- Font 자동 선택 없음
- Font 자동 승인 없음
- DB approval 변경 없음
- 기존 Visual Prototype 불변
- 상류 Production/Timeline/Audio 불변
- 전체 테스트 PASS
- 외부 Font 다운로드 0
- 외부 API 0
- MP4 0
- git commit/push 없음

이번 단계의 핵심은 매우 단순하다.

"폰트를 비교하기 전에
비교 기준부터 사람이 이미 결정한 값과 정확히 맞춘다."

Font Family를 고르는 실험에서
Font Size까지 같이 바뀌면
무엇이 더 좋은지 정확히 판단할 수 없다.

따라서 모든 후보에서:

PRIMARY = 40px / 700

을 고정한 뒤
Font Family만 비교할 수 있게 만들어라.