# 13-4C-7. Color Palette + Background Human Review
# CLEAN_DARK_FOCUS — Human Review Prototype / Approval Preparation

======================================================================
0. 이번 단계의 목적
======================================================================

이번 단계는 Color Palette와 Background의 exact value를
자동 승인하는 단계가 아니다.

목적은:

CLEAN_DARK_FOCUS를 기준으로
Color Palette + Background를 사람이 실제 화면에서 검토하고
승인/수정 여부를 판단할 수 있도록
Human Review Prototype을 준비하는 것이다.

이번 단계에서는:

- 기존 canonical 상태를 먼저 읽는다.
- 기존 CLEAN_DARK_FOCUS preview 값을 조사한다.
- preview value와 approved value를 구분한다.
- 실제 학습 화면에서 색상 semantic을 검토할 수 있게 한다.
- 필요한 비교 Prototype을 생성한다.
- Human Review 전에는 APPROVED로 기록하지 않는다.

핵심 원칙:

PREVIEW VALUE
≠
HUMAN REVIEW DECISION
≠
CANONICAL APPROVED VALUE

이 세 가지를 절대 혼동하지 마라.


======================================================================
1. 현재 Source of Truth를 먼저 읽어라
======================================================================

프롬프트의 과거 상태 설명을 무조건 사실로 가정하지 마라.

작업 시작 시 반드시 현재 프로젝트에서 다음을 조사한다.

1. visual_design_specs의 latest canonical record
2. assets/generated/plan_7/render/approved_visual_profile.json
3. assets/generated/plan_7/render/visual_design.json
4. research/visual_design.py의 candidate definitions
5. assets/generated/plan_7/render/prototypes/
6. assets/generated/plan_7/render/font_review/
7. 관련 report
8. 관련 tests

현재 실제 DB/artifact/code가
이번 프롬프트의 예상 상태와 다르면:

임의로 맞추지 말고 차이를 보고한다.

Human Review가 필요한 값은
과거 대화가 있었다고 추정하지 마라.


======================================================================
2. 예상 현재 상태 — 반드시 실제 데이터로 재검증
======================================================================

이전 단계 보고 기준 예상 상태:

Production Plan ID:
7

Visual Design Version:
13.4

Canonical Visual Candidate:
CLEAN_DARK_FOCUS

Font Family:
APPROVED

Approved Font Family Candidate:
VERDANA_HUMANIST

Expected actual font stack:
Verdana, Geneva, 'Malgun Gothic', sans-serif

Approved category count:
1

Pending category count:
14

full_profile_approved:
False

ready_for_final_renderer_binding:
False

Ready for Stage 13-5:
NO

Latest canonical record는 이전 보고 기준 id=6이지만
id를 하드코딩하지 마라.

record_status / lineage를 사용하여
실제 canonical record를 찾는다.


======================================================================
3. 이번 Human Review 대상
======================================================================

이번 단계에서 검토할 category는 정확히 두 개다.

1. color_palette
2. background

다른 category는 Human Review 대상으로 확장하지 마라.

특히 다음은 이번 단계에서 결정하지 않는다.

typography_scale
font_weight
spacing_scale
container
border
radius
caption_style
focus_style
success_style
motion_style
output_profile_16_9
output_profile_9_16

Font Family는 이미 승인 상태라면 그대로 보존한다.


======================================================================
4. CLEAN_DARK_FOCUS Preview 값 조사
======================================================================

현재 CLEAN_DARK_FOCUS가 실제로 사용하는
preview Color/Background 값을 코드에서 조사하라.

이전 Prototype에서 관측된 예상 값은 다음과 같다.

page_bg:
#111318

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

하지만 이것들을:

APPROVED VALUE

라고 가정하지 마라.

먼저 실제 코드와 Prototype을 조사하여
현재 값이 정확히 무엇인지 확인한다.

값이 다르면 실제 값을 사용하고
차이를 완료 보고에 기록한다.


======================================================================
5. Preview Value의 의미
======================================================================

이번 단계에서 CLEAN_DARK_FOCUS에 이미 존재하는 HEX는:

PREVIEW CANDIDATE VALUE

이다.

Human Review 전에는:

CANONICAL APPROVED VALUE

가 아니다.

따라서 Prototype 생성 과정에서:

color_palette = APPROVED

background = APPROVED

로 변경하면 안 된다.

Human Review 이후 별도의 Approval Persistence 단계에서
승인 기록을 만든다.


======================================================================
6. Font Family 고정
======================================================================

현재 canonical font_family가 실제로 APPROVED라면
이번 Color Review Prototype에서 반드시 그 Font를 사용한다.

예상:

VERDANA_HUMANIST

Verdana, Geneva, 'Malgun Gothic', sans-serif

그러나 실제 canonical record를 먼저 확인한다.

Font Family를 이번 단계에서 변경하지 마라.

Arial/Segoe UI 비교를 다시 만들지 마라.

Font Review를 다시 열지 마라.


======================================================================
7. Typography 고정 — 승인으로 간주하지 마라
======================================================================

이번 Color/Background 비교에서는
Typography를 비교 변수로 만들면 안 된다.

현재 CLEAN_DARK_FOCUS review baseline에서 사용 중인
실제 Typography 값을 조사하여 그대로 사용한다.

이전 Font Review 기준 예상:

DOMINANT:
68px / 800

PRIMARY:
42px / 700

SUPPORTING:
26px / 500

CAPTION:
18px / 400

MICRO:
14px / 400

하지만 typography_scale category가 canonical에서
PENDING_VISUAL_REVIEW라면:

그 상태는 그대로 유지한다.

즉:

Typography value를 비교 화면의 fixed condition으로 사용

≠

Typography category를 APPROVED 처리

이다.


======================================================================
8. Human Review Prototype의 핵심 질문
======================================================================

사람이 이번 화면에서 판단할 질문은 다음뿐이다.

Q1.
#111318 계열 Background가
장시간 영어 학습 영상에 적절한가?

Q2.
DEFAULT text가 Background에서 충분히 읽히는가?

Q3.
PRIMARY_FOCUS가
"지금 봐야 할 핵심"을 명확히 전달하는가?

Q4.
RELATION이
글자/소리/결합 관계를 보여줄 때
PRIMARY_FOCUS와 구별되는가?

Q5.
SUCCESS가
정답 공개를 명확히 전달하는가?

Q6.
SECONDARY와 MUTED가
학습 핵심과 경쟁하지 않는가?

Q7.
EXCEPTION_CAUTION이
예외/주의를 나타낼 때
SUCCESS와 혼동되지 않는가?

Q8.
색상을 제거해도
정보 구조가 이해되는가?

마지막 Q8은 accessibility 때문에 중요하다.


======================================================================
9. 새 Review Artifact 경로
======================================================================

기존 Prototype을 수정하지 마라.

새 경로를 사용한다.

권장:

assets/generated/plan_7/render/color_background_review/

생성 예:

index.html
01_FULL_LEARNING_SAMPLE.html
02_SEMANTIC_COLOR_ROLES.html
03_ANSWER_REVEAL_SAMPLE.html
04_RELATION_SAMPLE.html
05_MUTED_SECONDARY_SAMPLE.html
06_EXCEPTION_CAUTION_SAMPLE.html
07_GRAYSCALE_ACCESSIBILITY_SAMPLE.html
manifest.json

필요한 화면만 생성하라.

숫자를 채우기 위해 의미 없는 Prototype을 추가하지 마라.


======================================================================
10. Prototype 01 — Full Learning Sample
======================================================================

실제 CLEAN_DARK_FOCUS 학습 화면과 가까운
통합 샘플을 만든다.

가능하면 기존 Plan 7 콘텐츠를 재사용한다.

예:

직접 읽어보세요.

CAP

CAP
→
cap

또는 기존 CB06/CB07에서
실제 학습 semantic을 대표하는 내용을 사용한다.

중요:

새로운 학습 내용을 발명하지 마라.

기존 Production/Visual data를 읽어
실제 텍스트를 사용한다.

이 화면에서 확인할 것:

- page background
- DEFAULT
- PRIMARY_FOCUS
- RELATION
- SUCCESS
- SECONDARY
- MUTED
- approved font_family
- 현재 fixed typography hierarchy


======================================================================
11. Prototype 02 — Semantic Color Roles
======================================================================

모든 color role을 한 화면에서 비교할 수 있게 한다.

반드시 표시:

DEFAULT

PRIMARY_FOCUS

RELATION

SUCCESS

SECONDARY

MUTED

EXCEPTION_CAUTION

각 role에:

role name
preview HEX
실제 sample

을 표시할 수 있다.

단 이것은 개발자용 색상표만 되어서는 안 된다.

가능하면 학습 semantic 예시를 함께 보여준다.

예:

PRIMARY_FOCUS
→ 현재 읽을 단어

RELATION
→ 글자와 소리의 연결

SUCCESS
→ 정답

MUTED
→ 이미 지나간 정보

EXCEPTION_CAUTION
→ 예외/주의


======================================================================
12. Prototype 03 — Answer Reveal
======================================================================

정답 공개 상황을 실제로 검토할 수 있어야 한다.

기존 CB06 semantics를 우선 재사용한다.

예:

Before:
CAP

After:
cap 또는 실제 ANSWER semantic

SUCCESS role이:

- 너무 형광처럼 튀지 않는지
- 정답임을 즉시 알 수 있는지
- PRIMARY_FOCUS와 혼동되지 않는지
- 장시간 봐도 부담스럽지 않은지

판단할 수 있어야 한다.

CB06의 실제 answer reveal barrier/timing을 변경하지 마라.

이것은 정적 visual review다.


======================================================================
13. Prototype 04 — Relation
======================================================================

RELATION role의 목적을 확인한다.

기존 데이터에 실제 relation semantic이 있다면 재사용한다.

새 phoneme 교육 구조를 발명하지 마라.

RELATION color가:

PRIMARY_FOCUS와 충분히 다르고

SUCCESS와도 충분히 다르며

학습 관계를 보조하지만
핵심 단어보다 더 강하게 보이지 않는지

판단할 수 있어야 한다.


======================================================================
14. Prototype 05 — Secondary / Muted
======================================================================

SECONDARY와 MUTED를 비교한다.

확인 목적:

SECONDARY:
보조 정보이지만 읽을 수 있어야 함

MUTED:
이미 지나간 정보 또는 약화된 정보

둘이 너무 비슷해
역할 차이가 사라지지 않는지 확인한다.

반대로 MUTED가 너무 어두워
필요한 trace 자체가 안 보이는지도 확인한다.


======================================================================
15. Prototype 06 — Exception / Caution
======================================================================

EXCEPTION_CAUTION은 현재 Plan 7에서
실사용 0일 가능성이 있다.

먼저 실제 데이터를 확인한다.

실사용이 없다면:

"실제 Plan 7 사용 예"

라고 거짓으로 만들지 마라.

대신 명확히:

SEMANTIC ROLE PREVIEW ONLY
NOT USED IN CURRENT PLAN 7

라고 표시한 별도 review sample을 만들 수 있다.

이 역할의 목적은:

예외
주의
규칙에서 벗어나는 정보

이다.

SUCCESS와 혼동되지 않는지 확인한다.


======================================================================
16. Prototype 07 — Accessibility / Grayscale
======================================================================

Color-alone communication 방지 검토용 화면을 만든다.

기존 color review sample을
grayscale 또는 equivalent non-color review로 보여준다.

목적:

색이 없어도 다음을 구별할 수 있는가?

- 핵심
- 관계
- 정답
- 보조
- 약화
- 예외/주의

중요:

canonical Visual Design의 color를
실제로 grayscale로 변경하지 마라.

이 파일은 Review-only accessibility simulation이다.

manifest에:

preview_only = true

또는 동등한 의미를 기록한다.


======================================================================
17. Contrast 검증
======================================================================

이번 단계에서는 사람이 보기 전에
기계적으로 계산 가능한 contrast를 계산해도 된다.

가능하면 WCAG contrast ratio를 계산한다.

최소 다음 조합:

DEFAULT vs page_bg
PRIMARY_FOCUS vs page_bg
RELATION vs page_bg
SUCCESS vs page_bg
SECONDARY vs page_bg
MUTED vs page_bg
EXCEPTION_CAUTION vs page_bg

단:

contrast 계산 결과만으로
색을 자동 승인하거나 자동 변경하지 마라.

결과는 Human Review 참고 자료다.

자동으로 HEX를 밝게/어둡게 조정하지 마라.


======================================================================
18. Contrast 결과의 의미
======================================================================

각 role에 대해 가능하면 다음을 표시한다.

HEX

contrast ratio

normal text reference

large text reference

하지만 WCAG PASS/FAIL을
이 채널의 최종 디자인 승인과 동일시하지 마라.

예:

MUTED는 의도적으로 낮은 prominence를 가질 수 있다.

그러나 실제로 읽어야 하는 정보라면
접근성 문제가 될 수 있다.

따라서 기계 계산 + Human Review를 함께 사용한다.


======================================================================
19. Color-alone 검증
======================================================================

기존 13-4A 원칙:

color_not_sole_cue

를 유지한다.

이번 Prototype에서도:

색상만 바뀌고
다른 cue가 전혀 없는 구조를 새로 만들지 마라.

가능한 non-color cue:

position
typography hierarchy
label
shape
state
opacity
layout
textual marker

기존 Visual Design semantic을 우선한다.


======================================================================
20. Background Review
======================================================================

Background category는 단순히:

#111318

하나만 승인하는 문제인지 조사하라.

기존 schema에서 background가:

background role
actual page background
gradient
texture
media background
scene background

등으로 나뉘는지 확인한다.

현재 Human Review에서 실제로 검토 가능한 것이
page background 하나뿐이라면:

background category 전체를 승인할 수 있다고
미리 가정하지 마라.

Human Review가 정확히 무엇을 승인할 수 있는지
scope를 보고한다.

필요하다면:

background.page_bg

만 검토 대상으로 명시하고,

background 전체 category approval 가능 여부는
후속 persistence 단계에서 판단한다.


======================================================================
21. Color Palette Review 범위
======================================================================

Color Palette도 마찬가지다.

현재 실제 role:

DEFAULT
PRIMARY_FOCUS
RELATION
SUCCESS
SECONDARY
MUTED
EXCEPTION_CAUTION

전체를 한 번에 사람이 검토할 수 있게 한다.

하지만 어떤 role이 Plan 7에서 미사용이라면
그 사실을 명시한다.

미사용 role도 미래 taxonomy용으로
exact HEX를 승인할지 여부는 사람이 판단할 수 있어야 한다.


======================================================================
22. Human Review 선택 방식
======================================================================

이번 단계에서는 자동으로:

APPROVE

하지 않는다.

Prototype 생성 후 완료 보고에서
사람에게 다음 선택을 요청한다.

COLOR PALETTE:

1. 현재 CLEAN_DARK_FOCUS palette 그대로 승인
2. 일부 색상 수정 필요
3. 전체 palette 재검토 필요

BACKGROUND:

1. 현재 Background 그대로 승인
2. Background 수정 필요

단 실제 scope가 background 전체 category가 아니라
page_bg 하나뿐이면 그 사실을 함께 설명한다.


======================================================================
23. 이번 단계에서 DB Approval 금지
======================================================================

이번 단계는 REVIEW PREPARATION이다.

따라서:

visual_design_specs에
Color/Background APPROVED row를 만들지 마라.

기존 canonical row를 수정하지 마라.

새 approval row를 만들지 마라.

DB write가 필요 없는 것이 정상이다.

Font Family APPROVED 상태는 그대로 유지한다.


======================================================================
24. approved_visual_profile.json
======================================================================

이번 단계에서는
approved_visual_profile.json의 approval state를
변경하지 마라.

Review Prototype을 만들었다는 이유로:

color_palette = APPROVED

background = APPROVED

로 바꾸면 실패다.

Font Family 승인 기록도 변경하지 마라.


======================================================================
25. Review Manifest
======================================================================

새 manifest:

assets/generated/plan_7/render/color_background_review/manifest.json

권장 metadata:

revision:
13-4C-7

review_type:
COLOR_PALETTE_BACKGROUND

canonical_visual_candidate:
CLEAN_DARK_FOCUS

human_review_required:
true

approval_written:
false

color_palette_status:
PENDING_VISUAL_REVIEW

background_status:
PENDING_VISUAL_REVIEW

font_family_status:
APPROVED

font_family:
VERDANA_HUMANIST

preview_values:
현재 실제 코드에서 읽은 값

contrast_results:
계산 결과

prototype_files:
[...]

중요:

approved_color_palette

approved_background

필드는 Human Review 전에는 만들지 마라.


======================================================================
26. index.html
======================================================================

Human Review가 쉽게 되도록 index.html을 만든다.

권장 순서:

1. Full Learning Sample
2. Semantic Color Roles
3. Answer Reveal
4. Relation
5. Secondary / Muted
6. Exception / Caution
7. Accessibility / Grayscale

각 링크 옆에:

"무엇을 확인해야 하는지"

짧게 설명해도 된다.


======================================================================
27. 기존 Font Review 불변
======================================================================

다음 경로 변경 금지:

assets/generated/plan_7/render/font_review/

revision:
13-4C-3

Font Candidate files
manifest.json
index.html

Font Review는 종료됐다.

재생성하지 마라.


======================================================================
28. 기존 Visual Prototype 불변
======================================================================

다음 경로 변경 금지:

assets/generated/plan_7/render/prototypes/

13-4B-R1
26 Prototype HTML
manifest.json
index.html

CB06 phase 구조도 변경하지 마라.


======================================================================
29. Production / Audio / Layout 불변
======================================================================

절대 변경하지 마라.

Production Plan
production_blocks
speech_assets
generated_assets
Render Spec
Timeline
Scene Layout
WAV
Human Pronunciation Review
active assets
source_text
display_text

이 단계는 Visual Review artifact 생성만 담당한다.


======================================================================
30. 테스트 Baseline
======================================================================

현재 이전 보고 기준:

835 PASS

작업 전 실제 전체 테스트를 실행하여 baseline을 확인한다.

코드 변경 후 신규 테스트를 추가한다.

전체 suite PASS 필수.

835라는 숫자를 맹목적으로 하드코딩하지 마라.
실제 baseline을 보고한다.


======================================================================
31. Mandatory Tests
======================================================================

최소 다음을 검증한다.

CASE A

canonical visual candidate != CLEAN_DARK_FOCUS
→ FAIL

CASE B

font_family가 기존 APPROVED 상태에서 변경됨
→ FAIL

CASE C

Font Review artifact 변경
→ FAIL

CASE D

13-4B-R1 Prototype 변경
→ FAIL

CASE E

Color Review Prototype이 실제 CLEAN_DARK preview 값과 불일치
→ FAIL

CASE F

Background Review 값이 실제 preview 값과 불일치
→ FAIL

CASE G

Typography가 후보별/화면별 임의 변경
→ FAIL

CASE H

PRIMARY가 현재 fixed review baseline과 불일치
→ FAIL

CASE I

Color Review 생성으로 color_palette APPROVED
→ FAIL

CASE J

Color Review 생성으로 background APPROVED
→ FAIL

CASE K

Color Review 생성으로 full_profile_approved=True
→ FAIL

CASE L

Color Review 생성으로 renderer ready=True
→ FAIL

CASE M

Color Review 생성으로 Stage 13-5 ready=True
→ FAIL

CASE N

contrast 계산이 HEX 값을 자동 수정
→ FAIL

CASE O

grayscale preview가 canonical palette를 변경
→ FAIL

CASE P

EXCEPTION_CAUTION 미사용인데
Plan 7 실제 사용 예라고 허위 표시
→ FAIL

CASE Q

DB canonical row 변경
→ FAIL

CASE R

새 approval DB row 생성
→ FAIL

CASE S

approved_visual_profile.json approval state 변경
→ FAIL


======================================================================
32. Contrast Tests
======================================================================

contrast calculation helper를 구현한다면
독립적으로 테스트한다.

검증:

#RRGGBB parsing

relative luminance

contrast ratio

foreground/background order independence

invalid HEX rejection

단 테스트를 늘리기 위해
불필요한 utility를 만들지 마라.


======================================================================
33. Determinism
======================================================================

동일 입력으로 Color Review Prototype을 두 번 생성하면
semantic output과 manifest가 동일해야 한다.

timestamp 때문에 artifact 전체가 달라지는 구조라면
deterministic content와 metadata를 분리하라.

불필요한 random 값 금지.


======================================================================
34. 외부 호출 금지
======================================================================

Gemini TTS = 0

YouTube API = 0

영상 생성 AI = 0

이미지 생성 AI = 0

Font download = 0

External Font Network = 0

Google Fonts = 0

MP4 생성 = 0

WAV 생성 = 0


======================================================================
35. Git
======================================================================

사용자 명시 요청 전:

git commit 금지

git push 금지

git status 확인 허용.


======================================================================
36. 이번 단계에서 하지 말 것
======================================================================

Color 자동 승인 금지

Background 자동 승인 금지

HEX 자동 수정 금지

Font Family 변경 금지

Typography 승인 금지

Typography 값 재설계 금지

Spacing 승인 금지

Container 승인 금지

Border 승인 금지

Radius 승인 금지

Caption Style 승인 금지

Focus Style 승인 금지

Success Style 승인 금지

Motion 승인 금지

Output Profile 승인 금지

Stage 13-5 실행 금지

Final Renderer 실행 금지

MP4 생성 금지

Production data 변경 금지


======================================================================
37. 완료 보고 형식
======================================================================

완료 후 다음을 번호로 정확히 보고하라.

1. 수정/추가 파일
2. 13-4C-7 Architecture
3. 실행 전 테스트 baseline
4. 실행 후 전체 테스트 수
5. 신규 테스트 수
6. 수정한 기존 테스트 수
7. Production Plan ID
8. Visual Design version
9. Review revision
10. Canonical Visual Candidate
11. latest canonical record id
12. 기존 Approved category 수
13. 기존 Pending category 수
14. font_family status
15. Approved Font Family
16. 실제 Font Stack
17. color_palette 현재 canonical status
18. background 현재 canonical status
19. CLEAN_DARK 실제 page_bg preview 값
20. CLEAN_DARK 실제 DEFAULT 값
21. CLEAN_DARK 실제 PRIMARY_FOCUS 값
22. CLEAN_DARK 실제 RELATION 값
23. CLEAN_DARK 실제 SUCCESS 값
24. CLEAN_DARK 실제 SECONDARY 값
25. CLEAN_DARK 실제 MUTED 값
26. CLEAN_DARK 실제 EXCEPTION_CAUTION 값
27. 프롬프트 예상 HEX와 실제 코드 HEX 일치 여부
28. 현재 fixed typography 값
29. typography_scale canonical status
30. Full Learning Sample 생성 여부
31. Semantic Color Roles 생성 여부
32. Answer Reveal Sample 생성 여부
33. Relation Sample 생성 여부
34. Secondary/Muted Sample 생성 여부
35. Exception/Caution Sample 생성 여부
36. Grayscale Accessibility Sample 생성 여부
37. 총 Review HTML 수
38. index.html 경로
39. manifest.json 경로
40. Review artifact 경로
41. DEFAULT/background contrast ratio
42. PRIMARY_FOCUS/background contrast ratio
43. RELATION/background contrast ratio
44. SUCCESS/background contrast ratio
45. SECONDARY/background contrast ratio
46. MUTED/background contrast ratio
47. EXCEPTION_CAUTION/background contrast ratio
48. contrast 자동 수정 여부
49. color-alone accessibility review 결과
50. EXCEPTION_CAUTION Plan 7 실제 사용 여부
51. Background category 실제 scope 조사 결과
52. Color Palette category 실제 scope 조사 결과
53. color_palette approval 변경 여부
54. background approval 변경 여부
55. font_family approval 변경 여부
56. full_profile_approved
57. ready_for_final_renderer_binding
58. Ready for Stage 13-5
59. visual_design_specs row before/after
60. 신규 DB row 생성 여부
61. approved_visual_profile.json 변경 여부
62. Font Review Prototype 불변 여부
63. 13-4B-R1 Prototype 불변 여부
64. Production Plan 불변 여부
65. Render Spec 불변 여부
66. Timeline 불변 여부
67. Scene Layout 불변 여부
68. WAV 불변 여부
69. Human Pronunciation Review 불변 여부
70. CAP/BAG/MAP/BAT 불변 여부
71. source_text/display_text 불변 여부
72. 신규 Validation
73. 신규 Integrity Check
74. Mandatory CASE A~S 결과
75. 전체 테스트 결과
76. 기존 테스트 회귀 여부
77. Gemini TTS 호출 수
78. YouTube API 호출 수
79. 영상 생성 AI 호출 수
80. 이미지 생성 AI 호출 수
81. Font Network 호출 수
82. MP4 생성 여부
83. git commit 여부
84. git push 여부
85. 발견된 실제 bug/semantic debt
86. 발견된 제한사항
87. unresolved critical
88. unresolved non-critical
89. Human Color/Background Review 준비 여부
90. 사용자가 가장 먼저 열 파일
91. 사용자가 확인해야 할 순서
92. Human Review에서 답해야 할 정확한 선택지
93. 다음 단계
94. 성공 기준 전체 충족 여부


======================================================================
38. 완료 보고 마지막 상태
======================================================================

마지막에는 반드시:

COLOR + BACKGROUND HUMAN REVIEW:
READY / NOT READY

COLOR PALETTE STATUS:
PENDING_VISUAL_REVIEW

BACKGROUND STATUS:
PENDING_VISUAL_REVIEW

FONT FAMILY STATUS:
APPROVED

APPROVED FONT FAMILY:
<실제 canonical 값>

CANONICAL VISUAL CANDIDATE:
CLEAN_DARK_FOCUS

FULL APPROVED VISUAL PROFILE:
NO

READY FOR FINAL RENDERER BINDING:
NO

READY FOR STAGE 13-5:
NO

REVIEW FIRST:
<정확한 HTML 파일>

HUMAN REVIEW QUESTIONS:

COLOR PALETTE
1 = 현재 Palette 그대로 승인
2 = 일부 색상 수정 필요
3 = 전체 Palette 재검토 필요

BACKGROUND
1 = 현재 Background 그대로 승인
2 = Background 수정 필요

라고 출력하라.


======================================================================
39. 성공 기준
======================================================================

다음을 모두 만족해야 성공이다.

- 실제 canonical state 먼저 조사
- CLEAN_DARK_FOCUS 유지
- 승인된 Font Family 유지
- Color Palette는 Human Review 전 PENDING
- Background는 Human Review 전 PENDING
- Preview HEX와 Approval 의미 분리
- 실제 코드 HEX 사용
- fixed typography 조건 유지
- typography_scale 자동 승인 없음
- 실제 학습 semantic 기반 Prototype
- Color role 전체 비교 가능
- Answer Reveal 검토 가능
- Relation 검토 가능
- Secondary/Muted 검토 가능
- Exception/Caution 미사용 여부 정직하게 표시
- grayscale/accessibility 검토 가능
- contrast ratio 계산 가능
- contrast 결과로 HEX 자동 변경 없음
- color-alone communication 방지
- DB approval write 없음
- approved_visual_profile approval 변경 없음
- Font Review artifact 불변
- 13-4B-R1 Prototype 불변
- Production/Audio/Layout 불변
- 전체 테스트 PASS
- 외부 API 호출 0
- MP4 생성 0
- commit/push 없음

이번 단계의 핵심 질문은:

"현재 CLEAN_DARK_FOCUS의 색과 배경이
왕초보가 영어 학습의 핵심/관계/정답/보조/예외를
빠르고 편안하게 구별하는 데 적절한가?"

이다.

코드가 답을 대신 결정하지 마라.

사람이 실제 화면을 보고 결정할 수 있게 만들어라.