# Stage 13-4C-3 — Font Family 비교 Prototype 생성
# CLEAN_DARK_FOCUS / Typography Human Review

======================================================================
0. 목적
======================================================================

이번 단계는 새로운 Visual Design을 만드는 단계가 아니다.

목적은 오직:

CLEAN_DARK_FOCUS에서 사용할
canonical Font Family를 사람이 비교·선택할 수 있도록
Font Family 비교 Prototype을 생성하는 것이다.

현재까지 Human Review에서 결정된 Visual Direction,
Color Palette, Background, Typography Scale은 그대로 고정한다.

이번 Prototype에서 바꿔도 되는 변수는:

FONT FAMILY

하나뿐이다.

다른 Visual 변수는 비교 조건을 동일하게 유지한다.

======================================================================
1. 현재 프로젝트 상태
======================================================================

Production Plan ID:
7

Visual Design Version:
13.4

Prototype Revision:
13-4B-R1

Stage 13-4C-2:
COMPLETE

전체 테스트 baseline:
803 PASS

Canonical Visual Candidate:
CLEAN_DARK_FOCUS

Candidate Selection:
SELECTED

Full Approved Visual Profile:
NO

Ready for Final Renderer Binding:
NO

Ready for Stage 13-5:
NO

현재 Visual category 15개는 13-4C-2 기준
전부 PENDING_VISUAL_REVIEW 상태에서 시작했다.

이후 Human Review에서 Color Palette / Background와
Typography Scale에 대해 아래 결정을 내렸다.

======================================================================
2. Human Review에서 확정된 Color / Background
======================================================================

다음 값은 이번 세션에서 Human Review로 결정되었다.

BACKGROUND / page_bg
#111318

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

이 값들은 이번 Font Family Prototype에서
변경하지 마라.

후보 Font에 따라 색을 조정하지 마라.

======================================================================
3. Human Review에서 확정된 Typography Scale
======================================================================

현재 확정 Typography hierarchy:

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

이번 Font Family 비교에서
이 size/weight hierarchy를 변경하지 마라.

Font Family에 따라:

font-size 변경 금지
font-weight 변경 금지
line-height 임의 보정 금지
letter-spacing 임의 보정 금지

후보별 조건은 가능한 한 동일해야 한다.

======================================================================
4. Font Family 선정 목적
======================================================================

이 채널은 영어 왕초보 학습자를 대상으로 한다.

따라서 Font Family 선정 기준은
"예쁜 폰트"가 아니다.

최우선 기준:

1. 영어 대문자/소문자 형태가 명확한가
2. 초보자가 비슷한 글자를 구별하기 쉬운가
3. 단어 자체를 빠르게 인식할 수 있는가
4. 큰 학습 단어에서 글자 형태가 무너지지 않는가
5. 작은 Caption에서도 가독성이 유지되는가
6. 숫자와 알파벳을 혼동하기 어렵게 설계되어 있는가
7. 실제 영상 Renderer에서 안정적으로 사용할 수 있는가

특히 다음 glyph를 중요하게 평가한다.

I / l

O / 0

b / d

p / q

u / v

rn / m

c / e

a / o

1 / I / l

======================================================================
5. Font 후보 선정
======================================================================

Font 후보는 3개를 넘기지 마라.

2~3개만 비교한다.

후보는 다음 조건을 만족해야 한다.

- 영어 학습용으로 높은 가독성
- 대문자/소문자 형태 명확
- DOMINANT 800 수준 지원 가능
- PRIMARY 700 지원 가능
- SUPPORTING 500 지원 가능
- CAPTION/MICRO 400 지원 가능
- 일반적인 Renderer 환경에서 사용 가능
- 라이선스상 영상 제작/배포에 문제없는 방향
- 지나치게 decorative하지 않음
- condensed/display-only font 금지

우선 현재 프로젝트 환경에서 실제 사용 가능한
font family를 조사하라.

이미 프로젝트에 font dependency,
CSS font stack,
local font configuration,
Renderer font configuration 등이 있다면
먼저 그것을 확인한다.

존재하지 않는 Font를
설치되어 있다고 가정하지 마라.

새 Font 파일 다운로드 금지.

외부 Font API 호출 금지.

Google Fonts 네트워크 로딩 금지.

Prototype은 외부 리소스 없이 열려야 한다.

======================================================================
6. 후보 선정 원칙
======================================================================

후보는 서로 실제로 비교 가치가 있어야 한다.

예:

Candidate A
Neutral / highly readable sans-serif

Candidate B
Humanist sans-serif

Candidate C
Education/readability-oriented sans-serif

같은 의미의 후보 구성이 가능하다.

하지만 정확한 Font Family 이름은
현재 환경을 조사해서 결정하라.

3개 후보가 사실상 같은 fallback font로
렌더링되는 구조를 만들면 안 된다.

실제 사용할 수 있는 Font가 2개뿐이면
억지로 3개를 만들지 마라.

======================================================================
7. Font Availability 검증
======================================================================

각 후보마다 다음을 확인하라.

font family name

local availability

400 지원 여부

500 지원 여부

700 지원 여부

800 지원 여부

fallback 발생 여부

glyph support

I/l/O/0 구별 가능성

b/d/p/q 형태

가능하면 Browser Prototype에서
실제로 해당 Font가 적용됐는지 검증할 수 있는
metadata를 표시하거나 검사하라.

단 Font 파일 자체를 복사하거나
artifact로 포함하지 마라.

======================================================================
8. 비교 Prototype 구조
======================================================================

새 Prototype은 Font Family 비교 전용이다.

기존 26개 Prototype을 수정하지 마라.

별도 디렉터리를 사용하라.

권장 경로:

assets/generated/plan_7/render/font_review/

예:

index.html

FONT_A_learning.html
FONT_B_learning.html
FONT_C_learning.html

FONT_A_glyph_test.html
FONT_B_glyph_test.html
FONT_C_glyph_test.html

manifest.json

실제 이름에는 가능한 경우
Font Family를 식별할 수 있는 slug를 사용한다.

======================================================================
9. Prototype A — 실제 학습 화면
======================================================================

각 Font Candidate마다
동일한 CLEAN_DARK_FOCUS 학습 화면을 생성한다.

내용 예:

직접 읽어보세요.

CAP

cap

BAT

bat

MAP

map

BAG

bag

레이아웃은 기존 CLEAN_DARK_FOCUS Visual Grammar를 따른다.

특히:

Target Word = DOMINANT

Prompt = PRIMARY 또는 기존 semantic role

Supporting information은 기존 hierarchy 유지

Background = #111318

Color semantics = 승인된 palette 사용

모든 Font Candidate에서:

텍스트
위치
크기
굵기
색
spacing
container
layout

을 동일하게 유지한다.

Font Family만 변경한다.

======================================================================
10. Prototype B — Glyph Disambiguation Test
======================================================================

각 Font Candidate마다
별도의 glyph comparison 화면을 만든다.

반드시 다음을 포함한다.

I   l

1   I   l

O   0

b   d

p   q

u   v

c   e

rn   m

a   o

그리고 실제 단어 예시:

ILL

ill

little

look

book

good

bad

dad

pig

dig

map

cap

BAT

bat

CAP

cap

가능하면 동일 line에서
비슷한 glyph를 나란히 보여준다.

목적은 디자인 감상이 아니라:

"영어 왕초보가 글자를 잘못 읽을 가능성이 적은가?"

를 판단하는 것이다.

======================================================================
11. Uppercase / Lowercase 확인
======================================================================

반드시 다음 변환을 크게 보여준다.

CAP
↓
cap

BAT
↓
bat

MAP
↓
map

BAG
↓
bag

특히:

uppercase와 lowercase가
서로 충분히 다른 형태이면서도
같은 단어라는 것을 인식하기 쉬운지

확인할 수 있어야 한다.

======================================================================
12. Typography Hierarchy Test
======================================================================

각 후보에 다음을 한 화면에서 보여주는
Typography hierarchy sample을 추가해도 된다.

DOMINANT — 68 / 800
CAP

PRIMARY — 40 / 700
직접 읽어보세요.

SUPPORTING — 26 / 500
CAP → cap

CAPTION — 18 / 400
학습 보조 자막 예시

MICRO — 14 / 400
metadata sample

중요:

후보마다 정확히 같은 문자열을 사용한다.

======================================================================
13. Korean Caption 고려
======================================================================

현재 Font Family가 영어뿐 아니라
한국어 Caption에도 사용될 가능성이 있는지
기존 architecture를 조사하라.

만약 하나의 Font Family가
영어와 한국어 모두를 담당하는 구조라면:

한글 glyph 지원 여부도 검증해야 한다.

테스트 문자열:

직접 읽어보세요.

정답을 확인해 보세요.

글자의 소리를 연결해 보세요.

단:

영문 학습 Font와
한글 Caption Font를 별도로 둘 수 있는 architecture라면
이를 억지로 하나의 Font로 합치지 마라.

그 경우 완료 보고에서:

ENGLISH_LEARNING_FONT

KOREAN_CAPTION_FONT

분리가 필요한지 명시한다.

이번 단계에서 사람이 요청하지 않은
두 번째 Font를 자동 승인하지 마라.

======================================================================
14. Responsive 확인
======================================================================

Font Candidate가 16:9에서만 좋아 보이고
9:16에서 무너지는지 확인할 필요가 있다.

하지만 이번 단계에서
새 responsive layout system을 설계하지 마라.

기존 responsive rule을 사용해
가능하면 최소 preview만 확인한다.

특히:

DOMINANT CAP

Prompt

Caption

이 overflow되는지 확인한다.

Font 후보 때문에 layout 구조 자체를 변경하지 마라.

======================================================================
15. 평가 기준
======================================================================

각 후보에 대해 다음 항목을 평가할 수 있게 한다.

A. LETTER CLARITY

I/l
O/0
b/d
p/q

B. BEGINNER READABILITY

처음 보는 단어를
글자 단위로 보기 쉬운가

C. UPPER/LOWER CASE CLARITY

CAP → cap 같은 변환이 명확한가

D. DOMINANT WORD QUALITY

68px / 800에서
글자 형태가 지나치게 뭉개지지 않는가

E. SMALL TEXT READABILITY

18px / 14px에서
Caption/Micro가 읽히는가

F. VISUAL FIT

CLEAN_DARK_FOCUS와 어울리는가

G. RENDERER PRACTICALITY

실제 Renderer에서 안정적으로 사용할 수 있는가

======================================================================
16. 자동 점수로 최종 Font를 선택하지 마라
======================================================================

중요:

코드는 Font Candidate를 비교할 수 있게 만들 수 있다.

하지만:

BEST_FONT = ...

를 자동 결정하지 마라.

최종 Font Family 선택은:

HUMAN VISUAL REVIEW

이다.

가독성 검사를 코드로 수행하더라도
그 결과는 참고 정보다.

자동 승인 금지.

======================================================================
17. Canonical Profile 변경 금지
======================================================================

이번 단계에서는 Font Family를 아직 승인하지 않는다.

따라서:

approved_visual_profile.json

의 canonical Font Family를
Prototype 생성만으로 변경하지 마라.

category 상태:

font_family = PENDING_VISUAL_REVIEW

를 유지한다.

이번 단계 완료 후 사용자가
후보 하나를 선택했을 때만
후속 Approval 단계에서 기록한다.

======================================================================
18. 이미 승인된 값 보호
======================================================================

이번 Font Prototype을 생성하면서
이미 Human Review에서 결정한 다음 값을
다시 PENDING으로 돌리지 마라.

Background:
#111318

Color Palette:

DEFAULT #e6e6e6
PRIMARY_FOCUS #60a5fa
RELATION #c4b5fd
SUCCESS #4ade80
SECONDARY #9ca3af
MUTED #555b66
EXCEPTION_CAUTION #f59e0b

Typography:

DOMINANT 68 / 800
PRIMARY 40 / 700
SUPPORTING 26 / 500
CAPTION 18 / 400
MICRO 14 / 400

단:

현재 DB/canonical artifact에는
이 Human Review 결정이 아직 기록되지 않았을 수 있다.

그 경우 임의로 과거 승인처럼 위조하지 마라.

이번 단계의 review context로 명시하고,
필요한 canonical persistence는 후속 Approval 단계에서
정합하게 처리할 수 있도록 보고한다.

======================================================================
19. Canonical vs Review Decision 차이 보고
======================================================================

반드시 확인하라.

현재 conversation-level Human Review에서는
Color/Background/Typography 값이 결정되었다.

하지만 DB/canonical profile이 아직
13-4C-2의:

15 categories PENDING

상태일 가능성이 있다.

그렇다면:

HUMAN REVIEW DECISION EXISTS
BUT
CANONICAL PERSISTENCE PENDING

이라고 정확히 보고하라.

이 차이를 몰래 자동 동기화하지 마라.

이번 단계 목적은 Font 비교 Prototype 생성이다.

======================================================================
20. 기존 Prototype 보호
======================================================================

다음은 수정하지 마라.

assets/generated/plan_7/render/prototypes/

기존 26개 Prototype

CB06 6-phase

SOFT_LIGHT history

CLEAN_DARK existing Prototype

13-4B-R1 manifest

기존 Prototype을 overwrite하지 말고
Font Review 전용 artifact를 별도로 생성한다.

======================================================================
21. Production 데이터 불변
======================================================================

절대 변경 금지:

Production Plan

production_blocks

speech_assets

generated_assets

Render Spec

Timeline

Scene Layout

WAV

Human Pronunciation Review

active asset

source_text

display_text

CB06 PAUSE

CB06 Answer Barrier

CB07 semantics

CAP = SP039::CONTEXTUAL_WORD

BAG = SP003

MAP = SP029

BAT = SP016

======================================================================
22. 외부 호출 금지
======================================================================

Gemini TTS = 0

YouTube API = 0

영상 생성 AI = 0

이미지 생성 AI = 0

MP4 생성 = 0

WAV 생성 = 0

Font download = 0

External Font CDN = 0

Google Fonts network request = 0

======================================================================
23. Test baseline
======================================================================

현재 보고된 baseline:

803 tests PASS

작업 전에 실제 전체 test suite를 실행하여
baseline을 확인하라.

그 후 구현한다.

신규 테스트를 추가한다.

완료 후 전체 test suite PASS가 필수다.

======================================================================
24. Mandatory Tests
======================================================================

최소 다음을 검증한다.

CASE A

Font Candidate가 3개 초과
→ FAIL

CASE B

Font Candidate 0개
→ FAIL

CASE C

모든 후보가 동일 fallback으로 렌더링
→ FAIL

CASE D

후보마다 font-size가 다름
→ FAIL

CASE E

후보마다 font-weight가 다름
→ FAIL

CASE F

후보마다 Color Palette가 다름
→ FAIL

CASE G

후보마다 layout이 다름
→ FAIL

CASE H

I/l test 없음
→ FAIL

CASE I

O/0 test 없음
→ FAIL

CASE J

b/d/p/q test 없음
→ FAIL

CASE K

CAP → cap test 없음
→ FAIL

CASE L

DOMINANT 68/800이 보존되지 않음
→ FAIL

CASE M

PRIMARY 40/700이 보존되지 않음
→ FAIL

CASE N

SUPPORTING 26/500이 보존되지 않음
→ FAIL

CASE O

CAPTION 18/400이 보존되지 않음
→ FAIL

CASE P

MICRO 14/400이 보존되지 않음
→ FAIL

CASE Q

Background != #111318
→ FAIL

CASE R

승인된 Color Palette와 불일치
→ FAIL

CASE S

Prototype 생성으로
font_family가 자동 APPROVED
→ FAIL

CASE T

Prototype 생성으로
full_profile_approved=True
→ FAIL

CASE U

Prototype 생성으로
renderer ready=True
→ FAIL

CASE V

외부 Font URL 포함
→ FAIL

CASE W

기존 26개 Prototype overwrite
→ FAIL

======================================================================
25. Prototype Manifest
======================================================================

Font Review용 manifest를 별도로 만든다.

예:

revision:
13-4C-3

review_type:
FONT_FAMILY

canonical_candidate:
CLEAN_DARK_FOCUS

human_review_required:
true

font_family_status:
PENDING_VISUAL_REVIEW

fixed_review_values:
background
color_palette
typography_scale

candidates:
[...]

files:
[...]

manifest에:

selected_font

approved_font

같은 값을 자동으로 넣지 마라.

======================================================================
26. index.html
======================================================================

Font Review 전용 index.html을 만든다.

사람이 브라우저에서 쉽게 비교할 수 있도록:

Candidate 이름

Learning Sample

Glyph Test

Typography Hierarchy

링크를 후보별로 정리한다.

가능하다면 다음 순서:

Candidate A
- Learning Screen
- Glyph Test
- Hierarchy Test

Candidate B
- Learning Screen
- Glyph Test
- Hierarchy Test

Candidate C
- Learning Screen
- Glyph Test
- Hierarchy Test

자동으로 "추천 1위"를 표시하지 마라.

======================================================================
27. Human Review 방법도 출력
======================================================================

완료 보고에서 사용자가
무엇을 봐야 하는지 간단히 설명하라.

우선순위:

1.
I / l / 1

2.
O / 0

3.
b / d / p / q

4.
CAP → cap

5.
68px/800 CAP의 형태

6.
18px Caption 가독성

7.
전체 CLEAN_DARK_FOCUS와의 조화

사용자는 최종적으로:

Candidate A / B / C

중 하나를 선택할 수 있어야 한다.

======================================================================
28. Git
======================================================================

사용자 요청 전:

git commit 금지
git push 금지

git status 확인은 허용.

======================================================================
29. 이번 단계에서 하지 말 것
======================================================================

Font 자동 승인 금지

Color 재설계 금지

Background 재설계 금지

Typography Scale 재설계 금지

Spacing 확정 금지

Container 확정 금지

Border 확정 금지

Radius 확정 금지

Caption Style 확정 금지

Focus Style 확정 금지

Success Style 확정 금지

Motion Style 확정 금지

Output Profile 확정 금지

Stage 13-5 실행 금지

Final Renderer 실행 금지

MP4 생성 금지

======================================================================
30. 완료 보고
======================================================================

완료 후 다음을 번호로 보고하라.

1. 수정/추가 파일
2. Stage 13-4C-3 Architecture
3. 실행 전 test baseline
4. 실행 후 전체 test 수
5. 신규 테스트 수
6. Production Plan ID
7. Visual Design version
8. Font Review revision
9. Canonical Visual Candidate
10. Font Family 기존 canonical 상태
11. Human Review Color 결정 인식 여부
12. Human Review Background 결정
13. Human Review Typography 결정
14. DB/canonical persistence와 conversation decision 차이
15. Font 후보 수
16. Font 후보 이름
17. 각 후보 선정 이유
18. 각 후보 실제 local availability
19. 각 후보 400 지원 여부
20. 각 후보 500 지원 여부
21. 각 후보 700 지원 여부
22. 각 후보 800 지원 여부
23. fallback 여부
24. 영문 glyph 지원 결과
25. 한글 glyph 지원 결과
26. English/Korean Font 분리 필요 여부
27. I/l/1 비교 포함 여부
28. O/0 비교 포함 여부
29. b/d/p/q 비교 포함 여부
30. CAP→cap 비교 포함 여부
31. DOMINANT 68/800 보존
32. PRIMARY 40/700 보존
33. SUPPORTING 26/500 보존
34. CAPTION 18/400 보존
35. MICRO 14/400 보존
36. Background #111318 보존
37. Color Palette 전체 보존
38. Candidate 간 Font 외 차이 존재 여부
39. Learning Prototype 수
40. Glyph Prototype 수
41. Hierarchy Prototype 수
42. 전체 Font Review HTML 수
43. index.html 경로
44. manifest.json 경로
45. Font Review artifact 경로
46. 기존 26개 Prototype 불변 여부
47. 13-4B-R1 manifest 불변 여부
48. font_family approval 상태
49. full_profile_approved
50. ready_for_final_renderer_binding
51. Ready for Stage 13-5
52. 신규 Validation
53. 신규 Integrity Check
54. 신규 테스트 결과
55. 전체 테스트 결과
56. 기존 803 tests 회귀 여부
57. Production Plan 불변 여부
58. Render Spec 불변 여부
59. Timeline 불변 여부
60. Scene Layout 불변 여부
61. WAV 불변 여부
62. Human Pronunciation Review 불변 여부
63. CAP/BAG/MAP/BAT active asset 불변 여부
64. source_text/display_text 불변 여부
65. 외부 Font 다운로드 수
66. External Font Network 호출 수
67. Gemini TTS 호출 수
68. YouTube API 호출 수
69. 영상 생성 AI 호출 수
70. 이미지 생성 AI 호출 수
71. MP4 생성 여부
72. git commit 여부
73. git push 여부
74. 발견된 bug/semantic debt
75. 발견된 제한사항
76. unresolved critical
77. unresolved non-critical
78. Human Font Review 준비 여부
79. 사용자가 확인해야 할 파일
80. 다음 단계

마지막에는 반드시:

FONT FAMILY HUMAN REVIEW: READY / NOT READY

FONT FAMILY STATUS: PENDING_VISUAL_REVIEW

CANONICAL VISUAL CANDIDATE: CLEAN_DARK_FOCUS

FULL APPROVED VISUAL PROFILE: NO

READY FOR FINAL RENDERER BINDING: NO

READY FOR STAGE 13-5: NO

FONT CANDIDATES:
<후보 이름>

REVIEW FIRST:
<가장 먼저 열 파일>

라고 출력하라.

======================================================================
31. 성공 기준
======================================================================

이번 단계 성공 조건:

- Font Family만 비교 변수
- 후보 최대 3개
- 실제 환경에서 사용 가능한 후보
- 외부 Font 다운로드 없음
- 후보별 동일 Color
- 후보별 동일 Background
- 후보별 동일 Typography Scale
- 후보별 동일 layout
- I/l/1 비교 가능
- O/0 비교 가능
- b/d/p/q 비교 가능
- CAP→cap 비교 가능
- 실제 학습 화면 비교 가능
- Caption 크기 비교 가능
- Font 자동 승인 없음
- Canonical Font Family 여전히 PENDING
- Full Profile 승인 없음
- Renderer Gate NO
- 기존 Prototype 불변
- 상류 Production 데이터 불변
- 전체 테스트 PASS
- 외부 API 호출 0
- MP4 생성 0
- commit/push 없음

이번 단계의 핵심 질문은 하나다.

"왕초보가 영어 글자를 가장 명확하게 구별하면서
CLEAN_DARK_FOCUS 학습 화면에도 자연스럽게 어울리는
Font Family는 무엇인가?"

시스템이 답을 대신 결정하지 마라.

사람이 실제 Prototype을 보고 선택할 수 있게 만들어라.