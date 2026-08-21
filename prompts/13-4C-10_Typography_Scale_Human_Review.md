# 13-4C-10. Typography Scale Human Review
# Typography Scale Comparison Prototype Preparation
# Human Review Before Approval Persistence

======================================================================
0. 이번 단계의 목적
======================================================================

현재 Visual Approval은 다음까지 완료되었다.

APPROVED:
- font_family
- background
- color_palette

PENDING:
- typography_scale
- font_weight
- spacing_scale
- container
- border
- radius
- caption_style
- focus_style
- success_style
- motion_style
- output_profile_16_9
- output_profile_9_16

현재 Canonical Visual Candidate:

CLEAN_DARK_FOCUS

현재 승인된 Font Family:

VERDANA_HUMANIST
Verdana, Geneva, 'Malgun Gothic', sans-serif

현재 승인된 Background:

#111318

현재 승인된 Color Palette:

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


이번 단계의 목적은:

Typography Scale을 자동 승인하는 것이 아니다.

실제 왕초보 영어 학습 영상에서
다음 5단계 Typography hierarchy를 사람이 비교할 수 있는
Human Review Prototype을 만드는 것이다.

DOMINANT
PRIMARY
SUPPORTING
CAPTION
MICRO


현재 CLEAN_DARK_FOCUS preview baseline:

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


중요:

위 값은 현재 preview baseline이다.

아직 Human Approved Typography Scale이 아니다.

이번 단계에서는:

PENDING_VISUAL_REVIEW

상태를 유지한다.


======================================================================
1. 가장 중요한 원칙
======================================================================

이번 Review에서 비교할 핵심 variable은:

TYPOGRAPHY SCALE

이다.

이미 승인된 다음 값은 고정한다.

Font Family
Background
Color Palette

이 세 category는 비교 변수가 아니다.


절대 하지 말 것:

- Font Family 재검토
- Background 변경
- Color Palette 변경
- MUTED 변경
- Typography 자동 승인
- font_weight 자동 승인
- 다른 category 자동 승인
- Renderer 시작
- MP4 생성


======================================================================
2. 실행 전 Source of Truth 조사
======================================================================

구현 전에 실제 프로젝트를 조사한다.

반드시 확인:

1. latest canonical visual_design_specs record
2. approved_visual_profile.json
3. category approval 전체 상태
4. current typography preview source
5. CANDIDATES["CLEAN_DARK_FOCUS"]
6. typography 관련 consumer
7. font review artifact
8. color/background review artifact
9. muted review artifact
10. 13-4B-R1 prototype
11. README 현재 상태
12. 관련 CLI
13. 관련 tests
14. 전체 test baseline


이전 완료 보고 예상:

latest canonical record:
id=8

approved:
3

pending:
12

test baseline:
902 PASS


하지만:

id=8
902

등을 하드코딩하지 마라.

반드시 실제 프로젝트 상태를 재조회한다.


======================================================================
3. Human Review Source of Truth
======================================================================

이번 단계에서 확정된 Human Decision은:

"Typography Scale을 지금 승인한다."

가 아니다.


확정된 것은 오직:

Typography Scale Human Review를 진행한다.

이다.


따라서:

DOMINANT 68
PRIMARY 42
SUPPORTING 26
CAPTION 18
MICRO 14

를 이미 사람이 승인했다고 기록하면 실패다.


======================================================================
4. 현재 Preview Baseline 검증
======================================================================

실제 코드에서 CLEAN_DARK_FOCUS typography를 읽는다.

예상:

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


실제 값이 다르면:

실제 값을 사용한다.

프롬프트 예상값으로 코드를 덮어쓰지 마라.


======================================================================
5. 42px / 40px 문제 재발 방지
======================================================================

매우 중요.

이 프로젝트에서는 과거:

PRIMARY 42px

과

PRIMARY 40px

사이에 provenance 혼동이 있었다.

현재 CLEAN_DARK_FOCUS preview baseline이 실제 코드에서:

42px

라면 그것을 baseline으로 사용한다.


40px가 과거 SOFT_LIGHT_EDUCATION 또는 다른 후보에서 나온 값이라면
Human Review 승인값인 것처럼 가져오지 마라.


이번 단계에서는 오히려 필요하면:

42px baseline

과 사람이 비교할 수 있는 alternative를
명시적으로 Prototype으로 보여준다.


======================================================================
6. Font Weight와 Typography Scale 분리
======================================================================

현재 taxonomy에서:

typography_scale

과

font_weight

가 별도 category라면
둘을 섞어 승인하지 않는다.


하지만 Typography Scale Prototype을 실제로 렌더링하려면
현재 preview weight가 필요할 수 있다.

그 경우 기존 preview weight:

DOMINANT 800
PRIMARY 700
SUPPORTING 500
CAPTION 400
MICRO 400

을 고정 reference 값으로 사용한다.


이것은:

font_weight APPROVAL

이 아니다.


보고서에 반드시:

"Font weights are fixed preview/reference values for typography-scale comparison only."

라고 의미를 남긴다.


======================================================================
7. Verdana 800 제한 재확인
======================================================================

13-4C-3에서 확인된 기존 제한:

VERDANA_HUMANIST는 native 800 지원이 보장되지 않으며
브라우저가 synthetic bold 또는 근사 weight를 사용할 수 있다.

실제 현재 코드/보고서를 다시 확인한다.


이 제한이 여전히 존재한다면:

DOMINANT 800을
"native Verdana 800 verified"

라고 보고하면 안 된다.


이번 단계에서 font_weight 자체를 해결하려 하지 마라.

Typography Scale과 Font Weight Review를 분리한다.


======================================================================
8. Review Candidate 설계 원칙
======================================================================

후보를 너무 많이 만들지 마라.

권장:

3개

최대:

3개


목표는:

작음 / 현재 baseline / 큼

또는

compact / balanced / spacious

처럼 사람이 실제 차이를 판단할 수 있게 만드는 것이다.


단 임의 숫자를 바로 확정하지 마라.

먼저 현재 baseline의 hierarchy ratio를 분석하고
왕초보 영어 학습 화면의 실제 사용 context를 조사한다.


======================================================================
9. 권장 Candidate 구조
======================================================================

실제 조사 결과 특별한 이유가 없다면
다음 3개 방향을 우선 검토한다.


CANDIDATE A
COMPACT_LEARNING

현재 baseline보다 약간 작은 hierarchy.


CANDIDATE B
CURRENT_BALANCED

현재 CLEAN_DARK_FOCUS preview baseline 그대로.


CANDIDATE C
LARGE_BEGINNER

왕초보 가독성을 위해
핵심 학습 text를 조금 더 크게 만든 hierarchy.


중요:

후보 이름은 semantic label이다.

실제 px 값은 코드에서 현재 baseline을 읽은 후
결정론적으로 생성한다.


======================================================================
10. Candidate B
======================================================================

Candidate B는 반드시:

CURRENT_BALANCED

현재 CLEAN_DARK_FOCUS baseline 그대로여야 한다.


예상:

DOMINANT 68
PRIMARY 42
SUPPORTING 26
CAPTION 18
MICRO 14


실제 baseline이 다르면 실제 값을 사용한다.


======================================================================
11. Candidate A / C 생성 방식
======================================================================

Candidate A/C는
무작위 숫자를 하드코딩하지 않는다.

현재 baseline을 기준으로
명시적인 deterministic transformation을 사용한다.


예:

A:
DOMINANT -4
PRIMARY -4
SUPPORTING -2
CAPTION -2
MICRO 유지 또는 -1

C:
DOMINANT +4
PRIMARY +4
SUPPORTING +2
CAPTION +2
MICRO 유지 또는 +1


하지만 위 숫자를 무조건 사용하지 마라.

실제 layout/safe area를 조사해서
overflow 위험이 없는 범위에서 결정한다.


선택한 transformation rule을 report에 기록한다.


======================================================================
12. Typography hierarchy 유지
======================================================================

모든 후보에서 반드시:

DOMINANT > PRIMARY > SUPPORTING > CAPTION > MICRO

가 유지되어야 한다.


같은 크기가 되어 hierarchy가 무너지면 실패.


======================================================================
13. Core Safe Area
======================================================================

기존 Scene Layout / Core Safe Area를 조사한다.

Typography 후보 때문에:

- text clipping
- frame overflow
- caption collision
- answer overlap
- safe-area violation

이 발생하면 안 된다.


특히 Candidate C는 큰 글씨이므로
실제 16:9 frame에서 검증한다.


======================================================================
14. Review Prototype 목적
======================================================================

단순히:

68px
42px
26px

숫자만 나열하는 페이지를 만들지 마라.


실제 학습 화면에서:

"어느 크기가 더 읽기 좋은가?"

를 판단할 수 있어야 한다.


따라서 최소 다음 종류의 Prototype을 만든다.


======================================================================
15. Prototype 01 — Full Learning Context
======================================================================

실제 영어 학습 화면과 유사한 구성.

예:

CAP

직접 읽어보세요.

CAP → cap

또는 실제 Plan 7에서 이미 사용된
대표 학습 구조를 재사용한다.


각 후보에서 동일 content를 사용한다.

변수는 Typography Scale뿐.


======================================================================
16. Prototype 02 — Hierarchy Overview
======================================================================

5개 level을 한 화면에서 비교한다.

DOMINANT
PRIMARY
SUPPORTING
CAPTION
MICRO


각 level 옆에:

실제 px
reference weight

를 표시한다.


단 숫자 라벨 자체가
비교 대상 Typography를 왜곡하지 않도록
review metadata 영역은 별도 UI로 분리한다.


======================================================================
17. Prototype 03 — Beginner Reading
======================================================================

왕초보 영어 학습자가 실제로 읽는 상황을 만든다.

예:

CAP
BAG
MAP
BAT

또는 현재 Plan 7에서 실제 사용되는 학습 단어.


큰 핵심 단어
보조 설명
caption

을 함께 보여준다.


목적:

DOMINANT/PRIMARY의 크기가
왕초보에게 충분한지 판단.


======================================================================
18. Prototype 04 — Answer Reveal
======================================================================

CB06 semantic을 참고하여:

QUESTION
→
ANSWER

전환 이후 화면을 정적으로 재현한다.


현재 ANSWER:
SUCCESS

previous prompt trace:
MUTED #757b87


Color는 이미 승인됐으므로 그대로 사용한다.

Typography만 후보별로 달라야 한다.


======================================================================
19. Prototype 05 — Dense Learning Context
======================================================================

조금 더 많은 정보가 있는 화면을 만든다.

목적:

Candidate C처럼 큰 Typography가
실제 화면에서 너무 답답하거나
정보 공간을 과도하게 소비하지 않는지 확인.


포함 가능:

PRIMARY heading
SUPPORTING explanation
CAPTION
MICRO metadata


단 실제 채널에 존재하지 않는
복잡한 UI를 발명하지 마라.


======================================================================
20. Prototype 06 — Caption / Small Text Check
======================================================================

CAPTION
MICRO

두 작은 hierarchy level을 집중 비교한다.


목적:

- 너무 작지 않은지
- Verdana에서 읽히는지
- Korean fallback에서 깨지지 않는지
- approved background/color에서 충분한지


단 caption_style 자체를 승인하는 단계는 아니다.


======================================================================
21. 한글 Caption
======================================================================

Font stack:

Verdana, Geneva, 'Malgun Gothic', sans-serif

이므로 한글은 Malgun Gothic fallback 가능성이 높다.


Prototype에 최소 한 줄의 한글 caption을 포함한다.


예:

직접 읽어보세요.
정답을 확인해 보세요.


목적은:

영문 Verdana와 한글 fallback이
같은 scale에서 어색하지 않은지
사람이 볼 수 있게 하는 것.


하지만:

Korean Caption Font를 별도 승인하지 마라.


======================================================================
22. Candidate별 고정값
======================================================================

모든 후보에서 반드시 동일:

Font Family:
VERDANA_HUMANIST

Font Stack:
Verdana, Geneva, 'Malgun Gothic', sans-serif

Background:
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
#757b87

EXCEPTION_CAUTION:
#fbbf24


다른 visual variable 변경 금지.


======================================================================
23. Output Profile
======================================================================

현재 output_profile_16_9가 아직 PENDING이라면
이번 단계에서 그것을 승인하지 않는다.


다만 기존 Prototype/Scene Layout에서 사용하던
현재 preview canvas를 reference로 사용할 수 있다.


예:

16:9 preview


이것은:

output_profile_16_9 approval

이 아니다.


======================================================================
24. 9:16
======================================================================

이번 Typography Scale Review에서
9:16까지 확장하지 마라.


이유:

output_profile_9_16은 별도 CONDITIONAL category이며
recomposition 문제까지 섞이면
Typography Scale 하나만 비교할 수 없게 된다.


이번 Review는 기존 primary 16:9 context에 집중한다.


======================================================================
25. Prototype 산출물 경로
======================================================================

권장:

assets/generated/plan_7/render/typography_scale_review/


최소:

index.html
manifest.json


후보별 Prototype HTML을 생성한다.


예:

01_FULL_LEARNING_COMPACT_LEARNING.html
01_FULL_LEARNING_CURRENT_BALANCED.html
01_FULL_LEARNING_LARGE_BEGINNER.html

02_HIERARCHY_COMPACT_LEARNING.html
...

파일명은 기존 프로젝트 naming convention을 조사하여
그 convention에 맞춘다.


======================================================================
26. 예상 파일 수
======================================================================

Prototype type:

6

Candidate:

3


가능하면:

18 HTML

+ index.html
+ manifest.json


하지만 기존 architecture가
candidate switching을 한 HTML 안에서 처리하는 구조라면
억지로 18개로 만들지 마라.


중요한 것은 파일 개수가 아니라
Human Review 가능성이다.


======================================================================
27. manifest.json
======================================================================

최소 의미:

review_stage:
13-4C-10

review_type:
TYPOGRAPHY_SCALE_HUMAN_REVIEW_PREPARATION

canonical_visual_candidate:
CLEAN_DARK_FOCUS

typography_status:
PENDING_VISUAL_REVIEW

font_family_status:
APPROVED

background_status:
APPROVED

color_palette_status:
APPROVED

candidates:
A/B/C

각 candidate의:

DOMINANT
PRIMARY
SUPPORTING
CAPTION
MICRO

size 값.


reference weights도 명확히 구분해서 기록한다.


======================================================================
28. Preview Value와 Approved Value 구분
======================================================================

manifest/report에서 반드시:

CURRENT PREVIEW BASELINE

과

HUMAN APPROVED TYPOGRAPHY

를 분리한다.


이번 단계 종료 시:

HUMAN APPROVED TYPOGRAPHY:
NONE

이어야 한다.


======================================================================
29. DB Write 금지
======================================================================

이번 단계는:

Review Preparation

이다.


따라서:

visual_design_specs INSERT 금지.

기존 canonical row UPDATE 금지.


실행 전/후 row count가 동일해야 한다.


======================================================================
30. approved_visual_profile.json
======================================================================

변경 금지.


Typography Scale은 아직 승인되지 않았다.


따라서 approved_visual_profile.json의:

typography_scale:
PENDING_VISUAL_REVIEW

상태를 그대로 유지한다.


======================================================================
31. 기존 승인 보존
======================================================================

반드시 그대로:

font_family:
APPROVED

background:
APPROVED

color_palette:
APPROVED


어떤 Prototype generation도
이 승인 metadata를 변경하면 안 된다.


======================================================================
32. Historical Artifact 불변
======================================================================

다음 기존 Review artifact를 수정하지 마라.

assets/generated/plan_7/render/font_review/

assets/generated/plan_7/render/color_background_review/

assets/generated/plan_7/render/muted_color_review/

assets/generated/plan_7/render/prototypes/


특히:

13-4C-7
13-4C-8
13-4B-R1

historical evidence 불변.


======================================================================
33. Production 데이터 불변
======================================================================

변경 금지:

Production Plan
production_blocks
speech_assets
generated_assets
Render Spec
Render Timeline
Scene Layout
WAV
Human Pronunciation Review
active assets
source_text
display_text


이번 단계는 Review-only artifact generation이다.


======================================================================
34. Typography Candidate Source
======================================================================

후보값은 한 곳에서 생성한다.

예:

build_typography_scale_candidates(...)


Prototype별로:

68
42
26

등을 따로 하드코딩하지 마라.


모든 Prototype은 동일 candidate structure를 소비한다.


======================================================================
35. Single Source of Truth
======================================================================

특히 과거 발생했던:

label = 40px
CSS = 42px

같은 문제를 다시 만들지 마라.


화면에 표시하는:

"PRIMARY — 42px"

같은 label도
실제 candidate data에서 파생한다.


CSS도 동일 candidate data에서 파생한다.


======================================================================
36. Candidate Determinism
======================================================================

동일 canonical input으로 실행하면:

동일 후보
동일 px
동일 manifest
동일 Prototype semantics

가 생성되어야 한다.


timestamp 같은 불가피한 metadata가 있다면
determinism 검증 범위에서 제외 이유를 명시한다.


======================================================================
37. Overflow 검사
======================================================================

가능한 범위에서 programmatic check를 한다.


최소:

- hierarchy ordering
- positive size
- minimum size sanity
- candidate C excessive growth 방지
- known safe-area width에 대한 예상 overflow


정적 HTML만으로 실제 browser layout measurement가 불가능하다면
그 한계를 정직하게 보고한다.


"브라우저에서 clipping 없음 검증 완료"

라고 거짓 보고하지 마라.


======================================================================
38. Human Review 질문
======================================================================

index.html 마지막에 명확하게 보여준다.


TYPOGRAPHY SCALE HUMAN REVIEW

1 = COMPACT_LEARNING
2 = CURRENT_BALANCED
3 = LARGE_BEGINNER
4 = 세 후보 모두 부적절 — 새 후보 필요


단 실제 candidate 이름이 조사 후 달라졌다면
실제 이름을 사용한다.


======================================================================
39. Review 판단 기준
======================================================================

사람이 다음을 판단할 수 있게 한다.

1. 핵심 영어 단어가 충분히 크게 보이는가?
2. PRIMARY가 DOMINANT와 명확히 구분되는가?
3. SUPPORTING이 너무 크거나 작지 않은가?
4. CAPTION이 편하게 읽히는가?
5. MICRO가 실제 필요한 경우 읽을 수 있는가?
6. 화면이 너무 답답하지 않은가?
7. 왕초보 학습자가 핵심을 즉시 찾을 수 있는가?
8. Answer Reveal에서 현재 정답이 가장 먼저 보이는가?
9. MUTED trace가 핵심보다 앞서지 않는가?
10. 한글 fallback 크기가 어색하지 않은가?


======================================================================
40. 이번 단계에서 Approval CLI 만들지 마라
======================================================================

이번 단계는 Preparation이다.


approve-typography-scale

같은 persistence CLI를
미리 만들지 마라.


Human Review가 끝난 뒤
별도 단계에서 만든다.


예:

13-4C-11
Typography Scale Human Approval


순서를 지킨다.


======================================================================
41. README
======================================================================

이번 단계는 승인 상태를 바꾸지 않는다.


따라서 README의:

Approved:
font_family
background
color_palette

Pending:
12

상태는 그대로다.


단 새로운 Review Preparation CLI가
사용자-facing CLI 목록에 포함되어야 하는 구조라면
명령만 최소 추가할 수 있다.


승인 category count는 변경하지 마라.


======================================================================
42. CLI
======================================================================

기존 naming convention을 조사한다.


예상 후보:

review-typography-scale


하지만 기존 CLI convention이 다르면
실제 convention을 따른다.


이 CLI는:

Prototype generation
report generation

만 수행한다.


DB write:
0


======================================================================
43. Report
======================================================================

권장:

reports/typography_scale_review_<actual-date>.md


프로젝트의 기존 date convention을 따른다.


UTC/local date semantic debt가 기존에 있다면
이번 단계에서 별도 요청 없이 전역 수정하지 마라.


======================================================================
44. Mandatory Negative Test A
======================================================================

Review generation 후:

typography_scale = APPROVED

→ FAIL


======================================================================
45. Mandatory Negative Test B
======================================================================

Review generation 후:

font_weight = APPROVED

→ FAIL


======================================================================
46. Mandatory Negative Test C
======================================================================

font_family 변경

→ FAIL


======================================================================
47. Mandatory Negative Test D
======================================================================

background 변경

→ FAIL


======================================================================
48. Mandatory Negative Test E
======================================================================

color_palette 변경

→ FAIL


======================================================================
49. Mandatory Negative Test F
======================================================================

MUTED #757b87이
#555b66 또는 #8a919d로 변경

→ FAIL


======================================================================
50. Mandatory Negative Test G
======================================================================

CURRENT_BALANCED candidate가
실제 current baseline과 다름

→ FAIL


======================================================================
51. Mandatory Negative Test H
======================================================================

Prototype label의 px와
실제 CSS px가 다름

→ FAIL


======================================================================
52. Mandatory Negative Test I
======================================================================

후보 간 font-family가 다름

→ FAIL


======================================================================
53. Mandatory Negative Test J
======================================================================

후보 간 Color Palette가 다름

→ FAIL


======================================================================
54. Mandatory Negative Test K
======================================================================

후보 간 content가 달라
Typography 외 변수까지 달라짐

→ FAIL


======================================================================
55. Mandatory Negative Test L
======================================================================

DOMINANT <= PRIMARY

또는

PRIMARY <= SUPPORTING

등 hierarchy collapse

→ FAIL


======================================================================
56. Mandatory Negative Test M
======================================================================

Review Preparation 과정에서
visual_design_specs 새 row INSERT

→ FAIL


======================================================================
57. Mandatory Negative Test N
======================================================================

approved_visual_profile.json 변경

→ FAIL


======================================================================
58. Mandatory Negative Test O
======================================================================

full_profile_approved=True

→ FAIL


======================================================================
59. Mandatory Negative Test P
======================================================================

ready_for_final_renderer_binding=True

→ FAIL


======================================================================
60. Mandatory Negative Test Q
======================================================================

Ready for Stage 13-5=YES

→ FAIL


======================================================================
61. Mandatory Negative Test R
======================================================================

Production/Audio/Layout 데이터 변경

→ FAIL


======================================================================
62. Mandatory Negative Test S
======================================================================

Font Weight Preview를 사용했다는 이유로:

font_weight Human Approved

라고 기록

→ FAIL


======================================================================
63. Mandatory Negative Test T
======================================================================

Verdana 800을 실제 native 800이라고
검증 없이 단정

→ FAIL


======================================================================
64. Test Baseline
======================================================================

이전 보고 예상:

902 PASS


작업 전에 실제 전체 suite 실행.

baseline 기록.


작업 후 전체 suite 실행.


신규 테스트 수를 목표로 삼지 마라.

필요한 invariant만 테스트한다.


======================================================================
65. Regression
======================================================================

최소 기존 다음 흐름에 회귀 없어야 한다.

13-1
13-2
13-3
13-4A
13-4B
13-4B-R
13-4B-R1
13-4C-1
13-4C-2
13-4C-3
13-4C-6
13-4C-7
13-4C-8
13-4C-9


실제 테스트 suite 기준으로 검증한다.


======================================================================
66. 외부 호출
======================================================================

Gemini:
0

YouTube:
0

영상 생성 AI:
0

이미지 생성 AI:
0

Google Fonts:
0

Font download:
0

WAV 생성:
0

MP4 생성:
0


======================================================================
67. Git
======================================================================

commit 금지.

push 금지.

사용자가 명시적으로 요청하기 전까지 하지 마라.


======================================================================
68. 완료 보고
======================================================================

완료 후 번호를 붙여 정확히 보고한다.

1. 수정/추가 파일
2. Architecture
3. 실행 전 test baseline
4. 실행 후 test count
5. 신규 test 수
6. 수정한 기존 test 수
7. Production Plan ID
8. Visual Design version
9. Review revision
10. Canonical Visual Candidate
11. latest canonical record id
12. Approved category count
13. Pending category count
14. font_family status/value
15. background status/value
16. color_palette status
17. MUTED canonical value
18. typography_scale status before
19. typography_scale status after
20. font_weight status
21. current preview DOMINANT
22. current preview PRIMARY
23. current preview SUPPORTING
24. current preview CAPTION
25. current preview MICRO
26. Candidate A 이름
27. Candidate A 5개 size
28. Candidate B 이름
29. Candidate B 5개 size
30. Candidate C 이름
31. Candidate C 5개 size
32. Candidate transformation rule
33. Candidate B가 실제 baseline과 동일한지
34. reference weight 5개
35. Verdana 800 native support 검증 여부
36. Font Weight가 승인되지 않았음을 확인
37. Prototype 종류 수
38. Candidate 수
39. 총 Review HTML 수
40. index.html 경로
41. manifest.json 경로
42. Review artifact 경로
43. Full Learning Prototype 생성 여부
44. Hierarchy Prototype 생성 여부
45. Beginner Reading Prototype 생성 여부
46. Answer Reveal Prototype 생성 여부
47. Dense Context Prototype 생성 여부
48. Caption/Small Text Prototype 생성 여부
49. 한글 fallback sample 포함 여부
50. 모든 후보 font-family 동일 여부
51. 모든 후보 background 동일 여부
52. 모든 후보 palette 동일 여부
53. 모든 후보 content 동일 여부
54. hierarchy ordering 검증
55. overflow/safe-area 검증 방법
56. browser actual layout 검증 가능 여부
57. typography_scale 자동 승인 여부
58. font_weight 자동 승인 여부
59. visual_design_specs row before/after
60. 신규 DB row 생성 여부
61. approved_visual_profile.json 변경 여부
62. 기존 Font Review artifact 불변 여부
63. 13-4C-7 artifact 불변 여부
64. 13-4C-8 artifact 불변 여부
65. 13-4B-R1 artifact 불변 여부
66. Production Plan 불변 여부
67. production_blocks 불변 여부
68. speech_assets 불변 여부
69. generated_assets 불변 여부
70. Render Spec 불변 여부
71. Timeline 불변 여부
72. Scene Layout 불변 여부
73. WAV 불변 여부
74. Human Pronunciation Review 불변 여부
75. active assets 불변 여부
76. source_text/display_text 불변 여부
77. 신규 Validation/Integrity Check
78. Negative CASE A~T 결과
79. Determinism 결과
80. 전체 테스트 결과
81. 회귀 여부
82. Gemini 호출 수
83. YouTube 호출 수
84. 영상 생성 AI 호출 수
85. 이미지 생성 AI 호출 수
86. Font network 호출 수
87. WAV 생성 여부
88. MP4 생성 여부
89. README 수정 여부
90. git commit/push 여부
91. 발견된 bug/semantic debt
92. 발견된 제한사항
93. unresolved critical
94. unresolved non-critical
95. Typography Human Review 준비 여부
96. 가장 먼저 열 파일
97. Human Review 선택지
98. 다음 단계
99. 성공 기준 전체 충족 여부


======================================================================
69. 성공 기준
======================================================================

성공 조건:

- 실제 canonical state 재조회
- 기존 3개 Approved category 보존
- Typography Scale은 PENDING 유지
- Font Weight도 PENDING 유지
- 현재 CLEAN_DARK baseline 실제 코드에서 추출
- 40px/42px provenance 혼동 없음
- Typography 후보 최대 3개
- Candidate B = current baseline
- Candidate A/C deterministic
- 5-level hierarchy 유지
- Font Family 고정
- Background 고정
- approved Color Palette 고정
- MUTED #757b87 고정
- Font Weight는 reference only
- 실제 학습 context Prototype 생성
- 한글 fallback 확인 가능
- label/CSS single source
- DB write 0
- approved_visual_profile 변경 0
- historical artifact 변경 0
- Production/Audio/Layout 변경 0
- full_profile_approved=False
- renderer binding=False
- Stage 13-5=NO
- 전체 테스트 PASS
- 외부 API 0
- WAV 0
- MP4 0
- commit/push 0


======================================================================
70. 완료 후 최종 출력
======================================================================

실제 결과로 다음 형식을 출력한다.

TYPOGRAPHY SCALE HUMAN REVIEW:
READY

TYPOGRAPHY SCALE STATUS:
PENDING_VISUAL_REVIEW

FONT WEIGHT STATUS:
PENDING_VISUAL_REVIEW

CANONICAL VISUAL CANDIDATE:
CLEAN_DARK_FOCUS

APPROVED FONT FAMILY:
VERDANA_HUMANIST
Verdana, Geneva, 'Malgun Gothic', sans-serif

APPROVED BACKGROUND:
#111318

APPROVED COLOR PALETTE:
DEFAULT #e6e6e6
PRIMARY_FOCUS #60a5fa
RELATION #c4b5fd
SUCCESS #4ade80
SECONDARY #9ca3af
MUTED #757b87
EXCEPTION_CAUTION #fbbf24

CURRENT TYPOGRAPHY BASELINE:
DOMINANT <actual>
PRIMARY <actual>
SUPPORTING <actual>
CAPTION <actual>
MICRO <actual>

TYPOGRAPHY CANDIDATES:

1 = <Candidate A>
<actual sizes>

2 = <Candidate B>
<actual sizes>

3 = <Candidate C>
<actual sizes>

4 = 세 후보 모두 부적절 — 새 후보 필요

FULL APPROVED VISUAL PROFILE:
NO

READY FOR FINAL RENDERER BINDING:
NO

READY FOR STAGE 13-5:
NO

REVIEW FIRST:
assets/generated/plan_7/render/typography_scale_review/index.html

NEXT:
Human reviews Typography Scale candidates.
Do not persist Typography approval before the Human decision.