# 13-4C-6. Font Family Human Approval

## 0. 이번 단계의 목적

13-4C-3에서 생성한 Font Family 비교 Prototype을 사람이 실제로 검토했고,
이번 Human Review에서 Font Family 후보를 최종 선택했다.

이번 단계의 목적은 오직 이 Human Review 결과를
Approved Visual Profile의 `font_family` category에 정식으로 기록하는 것이다.

이번 단계는 새로운 Font Prototype을 만드는 단계가 아니다.
Typography Scale을 다시 결정하는 단계도 아니다.
전체 Visual Profile을 승인하는 단계도 아니다.

오직:

font_family = VERDANA_HUMANIST

하나만 Human Approved 상태로 반영한다.

다른 category를 추론하거나 자동 승인하지 마라.


---

# 1. Human Review Source of Truth

사용자가 실제 Font Review Prototype을 확인했다.

검토한 후보:

1. VERDANA_HUMANIST
2. ARIAL_NEUTRAL
3. SEGOE_MODERN

검토 화면에는 다음 항목이 포함되어 있었다.

- I / l / 1
- O / 0
- b / d
- p / q
- u / v
- c / e
- rn / m
- a / o
- ILL / ill / little
- look / book / good
- bad / dad
- pig / dig
- map / cap
- BAT / bat
- CAP / cap
- CAP → cap
- BAT → bat
- MAP → map
- BAG → bag
- Typography hierarchy sample
- Korean caption fallback sample

Human Review 결과:

APPROVED FONT FAMILY:

VERDANA_HUMANIST

사용자는 이 추천에 대해:

"ok"

라고 명시적으로 동의했다.

따라서 이번 단계에서 신뢰할 수 있는 Human Review 결정은:

font_family = VERDANA_HUMANIST

이다.


---

# 2. 중요한 Typography Source of Truth

이전 13-4C-4 / 13-4C-5에서 확인한 결과를 그대로 유지한다.

CLEAN_DARK_FOCUS의 현재 실제 Typography Preview 값:

DOMINANT = 68px / 800
PRIMARY = 42px / 700
SUPPORTING = 26px / 500
CAPTION = 18px / 400
MICRO = 14px / 400

특히:

PRIMARY = 42px / 700

을 유지한다.

40px로 변경하지 마라.

이번 Font Family 승인 때문에 Typography Scale을 변경하지 마라.

이번 단계에서 typography_scale을 APPROVED로 바꾸지도 마라.

Font Family 승인과 Typography Scale 승인을 혼동하지 마라.


---

# 3. 승인할 정확한 Font Stack

13-4C-3 Prototype에서 사용한 VERDANA_HUMANIST의 실제 stack을
single source에서 읽어 확인하라.

예상 값:

Verdana, Geneva, 'Malgun Gothic', sans-serif

그러나 위 문자열을 무조건 하드코딩하지 마라.

반드시 현재 코드의 Font Review candidate 정의에서
VERDANA_HUMANIST의 실제 font-family 값을 읽어 확인하라.

코드 값과 이 프롬프트가 다르면:

STOP

하고 실제 차이를 보고하라.

임의로 수정하거나 추정하지 마라.


---

# 4. 승인 범위

이번 Human Approval에서 APPROVED로 바꿀 수 있는 category는 정확히 하나다.

font_family

그 외 category는 이번 단계에서 승인 금지.

특히 다음 category는 기존 상태를 그대로 유지해야 한다.

color_palette
typography_scale
font_weight
spacing_scale
background
container
border
radius
caption_style
focus_style
success_style
motion_style
output_profile_16_9
output_profile_9_16

현재 canonical record에서 이들이 PENDING_VISUAL_REVIEW라면
그대로 PENDING_VISUAL_REVIEW로 유지하라.

이번 Font Family 선택을 근거로
다른 category의 exact value를 승인하지 마라.


---

# 5. Canonical Visual Candidate

Canonical Visual Candidate는 계속:

CLEAN_DARK_FOCUS

이다.

변경 금지:

SOFT_LIGHT_EDUCATION으로 되돌리지 마라.

Font Family 후보 이름과 Visual Candidate 이름을 혼동하지 마라.

즉:

Visual Candidate:
CLEAN_DARK_FOCUS

Font Family:
VERDANA_HUMANIST

두 개는 서로 다른 차원의 결정이다.


---

# 6. Canonical Approval Record 조회

기존 visual_design_specs를 먼저 조사하라.

현재 canonical correction record를
record_status 기반으로 정확히 찾는다.

이전 보고 기준 예상 canonical correction:

id=5
record_status=CANONICAL_CORRECTION
candidate_selection_status=SELECTED
canonical candidate=CLEAN_DARK_FOCUS

하지만 id=5를 하드코딩하지 마라.

실제 DB를 조회해서 canonical record를 결정하라.

과거 row는 수정하거나 삭제하지 마라.


---

# 7. Append-only Approval 원칙

이번 승인도 append-only로 처리한다.

기존 canonical correction row를 UPDATE하지 마라.

새 visual_design_specs row를 추가하여
이번 Font Family Human Approval을 기록하라.

새 row는 이전 canonical record를 lineage로 참조해야 한다.

필요하다면 다음과 같은 의미를 표현하라.

record_status = CANONICAL_CORRECTION
corrects_record_id = <previous canonical record id>

또는 현재 코드의 canonical lineage 구조가 이미 있다면
그 구조를 재사용하라.

새로운 schema를 불필요하게 발명하지 마라.


---

# 8. Category Approval 상태

새 canonical record의 category approval 결과는 정확히 다음 의미여야 한다.

font_family:
status = APPROVED
value = VERDANA_HUMANIST의 실제 font stack
provenance = HUMAN_VISUAL_REVIEW

나머지 category:

기존 canonical 상태 보존

특히 아직 PENDING인 category는 PENDING 유지.


---

# 9. Human Review Provenance 기록

font_family 승인에는 최소한 다음 provenance를 남겨라.

review_stage:
13-4C-6

review_type:
HUMAN_VISUAL_REVIEW

review_source:
13-4C-3 Font Family Prototype

selected_candidate:
VERDANA_HUMANIST

visual_candidate:
CLEAN_DARK_FOCUS

human_decision:
APPROVED

가능하면 실제 Prototype revision도 참조:

13-4C-3

단, 기존 schema로 표현할 수 있다면 기존 필드를 재사용하고
단지 이 정보를 넣기 위해 과도한 schema를 새로 만들지 마라.


---

# 10. Full Profile Approval 금지

이번 단계가 끝나도:

full_profile_approved = False

이어야 한다.

Ready for Final Renderer Binding도
mandatory category가 모두 승인되지 않았다면:

False

여야 한다.

Ready for Stage 13-5 역시:

NO

여야 한다.

Font Family 하나 승인됐다고
전체 Visual Profile을 승인하지 마라.


---

# 11. Renderer Gate 재계산

기존 ready_for_final_renderer_binding 로직을 재사용하라.

13-4C-2에서 정의한 mandatory category 기준을
현재 코드에서 다시 확인하라.

예상 mandatory categories:

color_palette
typography_scale
font_family
background
caption_style
focus_style
success_style
motion_style
output_profile_16_9

하지만 이 목록도 가능하면 현재 구현을 source of truth로 사용하라.

이번 단계 후 font_family 하나가 APPROVED되어도
나머지 mandatory category가 PENDING이면:

ready_for_final_renderer_binding = False

가 되어야 한다.


---

# 12. Font Review Prototype 보존

다음 경로의 Font Review 산출물을 변경하지 마라.

assets/generated/plan_7/render/font_review/

기존:

9 HTML
manifest.json
index.html

을 재생성하지 마라.

Font Family는 이미 Human Review가 끝났다.

이번 단계는 approval persistence 단계다.


---

# 13. 기존 Visual Prototype 보존

다음도 변경 금지:

assets/generated/plan_7/render/prototypes/

13-4B-R1 Prototype 26개
manifest.json
index.html

CB06 phase Prototype을 재생성하지 마라.


---

# 14. Approved Visual Profile 파일

현재:

assets/generated/plan_7/render/approved_visual_profile.json

의 의미를 조사하라.

현재 canonical correction record와
일치하도록 갱신해야 한다면 갱신하라.

단:

font_family만 새롭게 APPROVED

되어야 한다.

다른 PENDING category를 APPROVED로 만들지 마라.

파일에는 최소한 다음 상태가 명확해야 한다.

canonical_visual_candidate:
CLEAN_DARK_FOCUS

font_family:
APPROVED
VERDANA_HUMANIST

full_profile_approved:
false

ready_for_final_renderer_binding:
false


---

# 15. Validation

최소한 다음을 검증하라.

A.
canonical visual candidate가 CLEAN_DARK_FOCUS인가

B.
font_family가 VERDANA_HUMANIST인가

C.
font_family status가 APPROVED인가

D.
font_family approval provenance가 Human Review를 가리키는가

E.
PRIMARY가 여전히 42px / 700인가

F.
Typography Scale이 이번 단계에서 변경되지 않았는가

G.
typography_scale category가 자동 APPROVED되지 않았는가

H.
다른 PENDING category가 자동 승인되지 않았는가

I.
full_profile_approved가 False인가

J.
ready_for_final_renderer_binding이 False인가

K.
기존 canonical row가 수정되지 않았는가

L.
새 approval row가 append-only로 생성됐는가

M.
Font Review Prototype이 변경되지 않았는가

N.
13-4B-R1 Prototype이 변경되지 않았는가

O.
Production Plan / Render Spec / Timeline / Scene Layout이 불변인가

P.
WAV / Human Pronunciation Review / active asset이 불변인가


---

# 16. Negative Tests

반드시 다음 실패 케이스를 테스트하라.

CASE A
존재하지 않는 Font candidate를 승인하려 하면 실패

CASE B
ARIAL_NEUTRAL을 Human Review 결정 없이 승인하려 하면 실패

CASE C
SEGOE_MODERN을 Human Review 결정 없이 승인하려 하면 실패

CASE D
Font approval이 typography_scale까지 APPROVED로 바꾸면 실패

CASE E
Font approval이 PRIMARY 42px를 다른 값으로 바꾸면 실패

CASE F
Font approval이 full_profile_approved=True로 만들면 실패

CASE G
Font approval이 ready_for_final_renderer_binding=True로 만들면 실패

CASE H
Font approval이 기존 canonical DB row를 overwrite하면 실패

CASE I
Font approval이 CLEAN_DARK_FOCUS를 다른 visual candidate로 바꾸면 실패


---

# 17. Regression

전체 테스트를 실행하라.

현재 baseline:

821 PASS

코드/테스트가 추가된다면
기존 821개가 모두 그대로 통과해야 한다.

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

회귀가 없어야 한다.


---

# 18. 불변성

다음은 절대 변경하지 마라.

Production Plan 7
production_blocks
speech_assets
generated_assets
Render Spec
Timeline
Scene Layout
generated WAV
Human Pronunciation Review
CAP active asset
BAG active asset
MAP active asset
BAT active asset
source_text
display_text

특히:

CAP = SP039::CONTEXTUAL_WORD
BAG = SP003
MAP = SP029
BAT = SP016

기존 값이 실제 DB와 다르면
프롬프트 값을 억지로 맞추지 말고 차이를 보고하라.


---

# 19. 외부 호출 금지

이번 단계에서:

Gemini TTS 호출 금지
YouTube API 호출 금지
영상 생성 AI 호출 금지
이미지 생성 AI 호출 금지
Font 다운로드 금지
Google Fonts 호출 금지
외부 네트워크 Font 요청 금지
MP4 생성 금지


---

# 20. Git

commit 금지
push 금지

사용자가 명시적으로 요청하기 전까지
git commit / git push를 실행하지 마라.


---

# 21. 보고서

필요하다면 다음 보고서를 생성하라.

reports/font_family_human_approval_2026-08-21.md

보고서에는 최소한 다음을 기록한다.

- Human Review 대상
- 비교한 3개 Font 후보
- 선택된 Font
- 실제 Font Stack
- Human Review provenance
- PRIMARY 42px / 700 불변
- Typography Scale 미승인 상태
- Font Family APPROVED
- 나머지 category 상태
- Approved category count
- Pending category count
- Renderer blocker
- DB append-only 결과
- 테스트 결과
- 회귀 결과
- 불변성 결과
- 외부 호출 0
- MP4 생성 0


---

# 22. 완료 보고 형식

최종 보고에서 번호를 붙여 다음을 정확히 보고하라.

1. 수정/추가 파일
2. Architecture
3. 실행 전 테스트 수
4. 실행 후 테스트 수
5. 신규 테스트 수
6. Plan ID
7. Visual Design version
8. Font Review revision
9. Canonical Visual Candidate
10. Human Review Font 후보
11. Approved Font Family
12. 실제 Font Stack
13. font_family status
14. font_family provenance
15. PRIMARY typography
16. PRIMARY 변경 여부
17. typography_scale status
18. 다른 category 자동 승인 여부
19. Approved category 수
20. Pending category 수
21. full_profile_approved
22. ready_for_final_renderer_binding
23. Ready for Stage 13-5
24. 이전 canonical record id
25. 신규 canonical record id
26. append-only 여부
27. 기존 row 변경 여부
28. approved_visual_profile.json 갱신 여부
29. Font Review Prototype 변경 여부
30. 기존 13-4B-R1 Prototype 변경 여부
31. Production Plan 불변 여부
32. Render Spec 불변 여부
33. Timeline 불변 여부
34. Scene Layout 불변 여부
35. WAV 불변 여부
36. Human Pronunciation Review 불변 여부
37. CAP/BAG/MAP/BAT 불변 여부
38. 신규 Validation/Integrity Check
39. Negative Test 결과
40. 전체 테스트 결과
41. 회귀 여부
42. Gemini 호출 수
43. YouTube 호출 수
44. 영상 생성 AI 호출 수
45. 이미지 생성 AI 호출 수
46. Font network/download 호출 수
47. MP4 생성 여부
48. git commit/push 여부
49. 발견된 bug/semantic debt
50. 제한사항
51. unresolved critical
52. unresolved non-critical
53. 다음 Human Review 대상


---

# 23. 성공 기준

이번 단계 성공 조건:

- CLEAN_DARK_FOCUS 유지
- VERDANA_HUMANIST만 Font Family로 승인
- 실제 코드의 Font Stack을 provenance와 함께 저장
- PRIMARY 42px / 700 불변
- Typography Scale 자동 승인 없음
- 다른 category 자동 승인 없음
- Full Profile 자동 승인 없음
- Renderer Gate 자동 통과 없음
- append-only DB 기록
- 기존 Prototype 불변
- Production 데이터 불변
- 전체 테스트 PASS
- 외부 API 0
- Font network/download 0
- MP4 0
- commit/push 0


---

FONT FAMILY HUMAN DECISION:
APPROVED

APPROVED FONT FAMILY:
VERDANA_HUMANIST

CANONICAL VISUAL CANDIDATE:
CLEAN_DARK_FOCUS

PRIMARY TYPOGRAPHY:
42px / 700 — UNCHANGED

TYPOGRAPHY SCALE APPROVAL:
PENDING_VISUAL_REVIEW

FULL APPROVED VISUAL PROFILE:
NO

READY FOR FINAL RENDERER BINDING:
NO

READY FOR STAGE 13-5:
NO

NEXT:
Persist this Font Family Human Approval only.
Do not approve any other visual category.