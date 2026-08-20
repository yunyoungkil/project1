# Stage 13-4C-1 — Approved Visual Profile 승인 정합성 교정

현재 프로젝트는 다음 단계까지 진행되었다.

- Stage 13-1 Render Specification 완료
- Stage 13-2 Timeline Compiler 완료
- Stage 13-3 Scene/Layout Specification 완료
- Stage 13-3A answer_reveal_policy semantic debt 수정 완료
- Stage 13-4A Visual Design System 완료
- Stage 13-4B Visual Prototype 완료
- Stage 13-4B-R CLEAN_DARK_FOCUS Human Review 반영 Prototype Revision 진행
- Stage 13-4C Approved Visual Profile 구현 시도 완료

하지만 13-4C 완료 보고에서 Human Review 기록과 실제 대화 결정 사이에 정합성 문제가 발견되었다.

이번 단계의 목적은:

1. 잘못 승인된 Visual Candidate 기록을 교정하고
2. 부분 승인과 전체 Approved Profile을 명확히 분리하며
3. Renderer가 미확정 값을 승인된 값으로 오해하지 못하도록 Gate를 교정하는 것이다.

이번 작업은 새 디자인을 만드는 단계가 아니다.

새 Prototype을 만들지 않는다.
새 색상/폰트/px 값을 발명하지 않는다.
실제 MP4를 만들지 않는다.

이번 단계는 오직 “승인 상태와 Source of Truth 정합성”을 바로잡는다.

======================================================================
0. 발견된 정확한 문제
======================================================================

13-4C 완료 보고에는 다음과 같이 기록되었다.

Human Visual Review = APPROVED
승인 후보 = SOFT_LIGHT_EDUCATION

그리고 DB에:

visual_design_specs id=2
approval_status=APPROVED

가 기록되었다.

하지만 실제 Human Review 대화에서 사용자가 선호한 방향은:

CLEAN_DARK_FOCUS

였다.

사용자는 실제 Prototype을 보고:

“CLEAN_DARK_FOCUS_AFTER_REVEAL이 더 좋은 것 같아”

라고 선택했고,
이후 모든 세부 Human Review 결정도 CLEAN_DARK_FOCUS를 기준으로 진행되었다.

또한 13-4B-R 프롬프트 자체도:

CLEAN_DARK_FOCUS Human Review 반영

을 명시적으로 기준으로 삼았다.

따라서:

SOFT_LIGHT_EDUCATION = APPROVED

라는 기록은 현재 대화 기반 Human Review와 불일치한다.

이 승인 기록을 canonical truth로 유지하면 안 된다.

======================================================================
1. 두 번째 문제 — 부분 승인과 전체 승인 혼동
======================================================================

13-4C 완료 보고 기준 실제 확정된 카테고리는:

2 / 15

뿐이다.

확정된 항목:

1. color_palette
2. typography_scale

미확정 13개:

font_family
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

이 13개는 모두:

PENDING_VISUAL_REVIEW

상태다.

그런데 visual_design_specs id=2가:

approval_status = APPROVED

로 기록되어 있다.

이 상태는 downstream Renderer가:

“Visual Profile 전체가 승인됨”

으로 오해할 위험이 있다.

부분 승인 상태와 전체 승인 상태를 명확히 분리해야 한다.

======================================================================
2. 이번 단계의 최종 의미 모델
======================================================================

다음 세 가지 개념을 분리하라.

A. Candidate Selection

사용자가 어느 Visual Direction을 선호했는가?

현재 값:

selected_candidate = CLEAN_DARK_FOCUS

B. Category Approval

Visual Profile의 개별 카테고리 중 무엇이 실제로 승인되었는가?

현재:

approved_categories = 2 / 15

C. Full Profile Approval

Renderer가 아무 추가 Human Review 없이
전체 Visual Profile을 canonical하게 사용할 수 있는가?

현재 답:

NO

이 세 가지를 하나의 approval_status로 뭉뚱그리지 마라.

======================================================================
3. 현재 Human Review Source of Truth
======================================================================

현재 Human Review에서 실제로 확정된 Visual Direction:

CLEAN_DARK_FOCUS

이다.

SOFT_LIGHT_EDUCATION이 아니다.

CLEAN_DARK_FOCUS의 Human Review 기반 원칙:

- dark base
- white/gray default text
- semantic color only when meaningful
- target word is dominant
- explanation text is supporting
- Caption Layer separate
- minimal decoration
- learning motion only
- CB06 prompt → thinking → answer → mapping → blending → final word 흐름
- 기존 문제 word는 answer 공개 후 MUTED trace
- answer는 DOMINANT/SUCCESS
- sequential left-to-right mapping/blending
- CAP → cap은 visual transformation
- scaffold removal
- final natural word only

이 방향은 기존 13-4A semantic grammar 위에 적용된 Human Review 결과다.

======================================================================
4. 기존 visual_design_specs id=2 처리 원칙
======================================================================

잘못된 row를 조용히 삭제하거나 덮어쓰지 마라.

감사 이력을 보존하라.

먼저 현재 DB schema와 기존 project pattern을 조사하라.

가능한 처리 우선순위:

Option A.
기존 row를 명시적으로 INVALIDATED / SUPERSEDED / CORRECTED 상태로 전환하고
새 canonical correction row를 추가

Option B.
기존 schema가 상태 변경을 안전하게 지원하지 않는다면
기존 row를 immutable history로 남기고
새 correction row에:

supersedes_visual_design_spec_id
correction_reason
canonical=true

또는 동등한 명확한 lineage를 기록

Option C.
schema 확장이 과도하다면
metadata_json / approval_json 내에:

approval_valid=false
invalidated_reason
superseded_by

등으로 기록

무엇을 선택하든:

- 기존 history 삭제 금지
- 잘못된 approval을 canonical latest-approved로 반환하면 안 됨
- correction lineage가 추적 가능해야 함

완료 보고에서 선택한 방식과 이유를 설명하라.

======================================================================
5. Approval Status taxonomy 재검토
======================================================================

기존 approval_status 하나로 전체 상태를 표현하기 어렵다면
최소한 의미를 다음처럼 구분하라.

예시 taxonomy:

PENDING_HUMAN_REVIEW
CANDIDATE_SELECTED
PARTIALLY_APPROVED
FULLY_APPROVED
INVALIDATED
SUPERSEDED

정확한 이름은 기존 프로젝트 naming convention을 조사해 조정 가능하다.

중요:

현재 상태는:

CANDIDATE_SELECTED
또는
PARTIALLY_APPROVED

에 해당한다.

FULLY_APPROVED가 아니다.

approval_status = APPROVED

라는 단일 모호한 값은 downstream Gate에 그대로 사용하면 안 된다.

======================================================================
6. Category-level Approval 구조
======================================================================

15개 category 각각에 대해 상태가 명확해야 한다.

현재 category 목록:

color_palette
typography_scale
font_family
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

각 category 최소 상태:

APPROVED
PENDING_VISUAL_REVIEW
REJECTED
SUPERSEDED

또는 기존 구조에 맞는 동등한 taxonomy.

현재 실제 상태:

color_palette:
상태를 그대로 APPROVED로 유지하기 전에
후보 provenance를 반드시 확인하라.

typography_scale:
동일.

나머지 13개:
PENDING_VISUAL_REVIEW

중요:

13-4C 보고의 color_palette와 typography_scale이
SOFT_LIGHT_EDUCATION 후보에서 파생된 값이라면
그 값을 CLEAN_DARK_FOCUS 승인값으로 자동 승격하지 마라.

후보 provenance를 조사하라.

======================================================================
7. Color Palette provenance 조사
======================================================================

13-4C에 기록된 값:

DEFAULT #2b2b2b
PRIMARY_FOCUS #1d4ed8
RELATION #7c3aed
SUCCESS #15803d
SECONDARY #6b7280
MUTED #b3b3b3
EXCEPTION_CAUTION #b45309

이 Palette가:

SOFT_LIGHT_EDUCATION candidate에서 실제 preview된 값인지
CLEAN_DARK_FOCUS candidate에서 실제 preview된 값인지

반드시 조사하라.

근거:

- prototype generator
- candidate config
- generated HTML
- visual_design.py
- approved_visual_profile.json
- report
- tests

를 확인하라.

만약 이 Palette가 SOFT_LIGHT 전용이라면:

color_palette APPROVED

를 철회하고:

PENDING_VISUAL_REVIEW

로 되돌려라.

CLEAN_DARK_FOCUS에 맞는 새 HEX를 임의 생성하지 마라.

만약 실제 CLEAN_DARK_FOCUS prototype에도 동일 palette가 사용되었다면
그 사실을 증거와 함께 보고하라.

단 DEFAULT #2b2b2b가 dark background 위 기본 텍스트 역할이라면
contrast상 부적절할 가능성이 있으므로
실제 candidate context를 반드시 확인하라.

추측 금지.

======================================================================
8. Typography Scale provenance 조사
======================================================================

현재 값:

DOMINANT 64px / 800
PRIMARY 40px / 700
SUPPORTING 26px / 500
CAPTION 18px / 400
MICRO 14px / 400

이 값도:

- CLEAN_DARK_FOCUS Prototype에서 실제 사용되었는가?
- SOFT_LIGHT_EDUCATION에서만 사용되었는가?
- 두 candidate가 공유하는 preview-only 값인가?

를 조사하라.

Human Review가 실제로 이 scale 자체를 명시적으로 승인했는지도 구분하라.

사용자가:

“CLEAN_DARK_FOCUS가 더 좋다”

라고 한 것은
candidate direction 승인이지
64px/40px/26px/18px/14px 값을 숫자별로 명시 승인했다는 뜻은 아니다.

따라서:

“candidate direction 승인”
과
“exact numeric token 승인”

을 같은 것으로 취급하지 마라.

Human Review에서 정확한 px를 직접 비교/승인한 근거가 없다면
typography_scale도:

PENDING_VISUAL_REVIEW

로 되돌리는 것이 정직할 수 있다.

실제 근거를 조사 후 결정하라.

======================================================================
9. selected_candidate와 approved_profile 분리
======================================================================

최종 canonical correction row 또는 profile structure에는
최소 다음 의미가 분리되어야 한다.

selected_candidate:
CLEAN_DARK_FOCUS

candidate_selection_status:
APPROVED 또는 SELECTED

profile_approval_status:
PARTIAL / PENDING

category_approvals:
...

full_profile_approved:
false

ready_for_final_renderer_binding:
false

approved_category_count:
실제 근거 기반 값

total_category_count:
15

pending_categories:
[...]

중요:

selected_candidate=CLEAN_DARK_FOCUS
라고 해서
full_profile_approved=true
가 되면 안 된다.

======================================================================
10. Ready for Final Renderer Binding Gate
======================================================================

기존:

Ready for Final Renderer Binding = YES (부분)

같은 애매한 상태를 제거하라.

boolean Gate라면:

Ready for Final Renderer Binding = NO

가 현재 정답이다.

부분 사용 가능성을 표현해야 한다면 별도 필드로:

renderer_binding_scope

예:

{
  "ready": false,
  "approved_scope": [...],
  "pending_scope": [...]
}

처럼 분리할 수 있다.

하지만 downstream Renderer의 최상위 Gate는:

NO

여야 한다.

왜냐하면:

font_family
background
caption_style
focus_style
success_style
motion_style
output_profile

등 핵심 Renderer 값이 아직 미확정이기 때문이다.

부분 승인만으로 전체 Renderer 진입을 허용하지 마라.

======================================================================
11. Stage 13-4C 완료 상태 재정의
======================================================================

현재 13-4C를 “완료”로 취급하지 마라.

정확한 상태:

13-4A = COMPLETE

13-4B = COMPLETE

13-4B-R = Human-reviewed direction available

Visual Candidate Selection:
CLEAN_DARK_FOCUS = SELECTED

13-4C Full Approved Visual Profile:
NOT COMPLETE

현재는:

13-4C-PARTIAL

또는 기존 naming convention에 맞는
부분 승인 상태로 보는 것이 정확하다.

최종 13-4C 완료 조건은:

- selected candidate 명확
- 모든 mandatory Renderer category 승인
- exact canonical values 승인
- full profile validation pass
- full profile integrity pass
- ready_for_final_renderer_binding = YES

가 되어야 한다.

======================================================================
12. Mandatory Renderer Categories
======================================================================

Full Renderer Binding을 위해 실제로 필수인 category를 조사하라.

무조건 15개 전부 mandatory라고 가정하지 마라.

하지만 최소 다음은 Renderer에 필요할 가능성이 높다.

font_family
typography_scale
color_palette
background
caption_style
focus_style
success_style
motion_style
output_profile_16_9

9:16이 현재 최종 Renderer 대상이 아니라면
output_profile_9_16이 full long-form Renderer Gate에 mandatory인지
별도로 판단할 수 있다.

spacing/container/border/radius도
실제 Renderer contract에 필수인지 조사하라.

중요:

required vs optional category를 코드에서 명확히 구분하면
Gate 의미가 더 정직해질 수 있다.

임의 판단하지 말고 downstream consumer 요구를 조사하라.

======================================================================
13. Canonical Approved Visual Profile 파일 처리
======================================================================

현재:

assets/generated/plan_7/render/approved_visual_profile.json

이 존재한다.

이 파일이 현재:

SOFT_LIGHT_EDUCATION
approval_status=APPROVED
ready=true

등 잘못된 의미를 담고 있다면
그 상태로 downstream에서 사용되면 안 된다.

처리 원칙:

- history가 필요한 기존 파일은 보존 가능
- canonical 파일은 correction 결과로 업데이트 가능
- 또는 invalidated snapshot 별도 보존 후 canonical correction 파일 재생성 가능

하지만 최종 canonical file은 반드시:

selected_candidate = CLEAN_DARK_FOCUS

full_profile_approved = false

ready_for_final_renderer_binding = false

를 정확히 반영해야 한다.

미확정 category를 APPROVED로 표시하지 마라.

======================================================================
14. Human Review 감사 이력
======================================================================

승인 교정 이유를 명시적으로 기록하라.

예:

correction_reason:
"HUMAN_REVIEW_CANDIDATE_MISMATCH"

details:
"SOFT_LIGHT_EDUCATION was recorded as approved, but the actual human review selected CLEAN_DARK_FOCUS."

또한 부분 승인 문제:

"PARTIAL_CATEGORY_APPROVAL_WAS_MISREPRESENTED_AS_FULL_PROFILE_APPROVAL"

같은 명확한 reason을 사용할 수 있다.

정확한 naming은 기존 convention에 맞게 조정 가능.

======================================================================
15. CLI 동작 교정
======================================================================

현재:

approve-visual-design

CLI가 candidate 하나를 받으면
바로 approval_status=APPROVED를 쓰는 구조인지 조사하라.

만약 그렇다면 위험하다.

CLI 의미를 다음처럼 분리하는 것을 검토하라.

예:

candidate selection:
--select-candidate CLEAN_DARK_FOCUS

category approval:
--approve-category color_palette
--approve-category typography_scale

full profile finalize:
--finalize

단 CLI 확장을 무조건 하라는 뜻은 아니다.

기존 API를 최소 변경으로 안전하게 만들 수 있다면
그 방식을 우선한다.

중요:

candidate selection만으로
full approval이 되지 않게 만들어라.

======================================================================
16. Backward Compatibility
======================================================================

기존 13-4A/B:

run_visual_design

은 계속:

PENDING_HUMAN_REVIEW

를 반환해야 한다.

approve-visual-design의 기존 호출 signature를
불필요하게 깨지 마라.

다만 기존 semantics가 위험하다면
안전한 default로 변경할 수 있다.

예:

기존:
approve candidate → APPROVED

교정:
approve candidate → CANDIDATE_SELECTED / PARTIAL

full finalize는 별도 explicit action

이 더 안전하다.

변경 시 완료 보고에 migration impact를 명시하라.

======================================================================
17. Negative Cases 필수
======================================================================

다음 실패 케이스를 테스트하라.

CASE A
SOFT_LIGHT가 실제 Human Review와 불일치
→ canonical selected candidate로 반환되면 fail

CASE B
selected candidate만 존재
→ full_profile_approved=true면 fail

CASE C
13개 mandatory/pending category 존재
→ ready_for_final_renderer_binding=true면 fail

CASE D
invalidated approval row가 latest canonical approval로 선택됨
→ fail

CASE E
superseded row가 canonical latest로 선택됨
→ fail

CASE F
CLEAN_DARK selected
+ exact HEX provenance 없음
→ color palette를 자동 승인하면 fail

CASE G
exact typography px Human Review 근거 없음
→ numeric scale 자동 승인하면 fail

CASE H
category approval 2/15
→ full approval이면 fail

CASE I
full finalize without mandatory categories
→ fail

CASE J
PENDING category를 Renderer가 canonical resolved value처럼 사용
→ fail

CASE K
13-4A run path가 auto approval
→ fail

CASE L
correction history가 삭제됨
→ fail

======================================================================
18. Integrity Check
======================================================================

기존 Integrity Check 이름을 삭제/변경하지 마라.

13-4C-1 전용 Integrity Check를 추가하라.

예:

visual_approval_candidate_consistency_safe
visual_approval_history_preserved
visual_approval_invalidated_row_not_canonical
visual_approval_category_scope_safe
visual_approval_full_status_safe
visual_approval_renderer_gate_safe
visual_approval_palette_provenance_safe
visual_approval_typography_provenance_safe
visual_approval_pending_categories_safe
visual_approval_correction_lineage_safe
visual_approval_no_auto_finalize
visual_approval_complete

이름은 실제 구현에 맞게 조정 가능하다.

숫자 채우기용 meaningless check 금지.

======================================================================
19. 기존 데이터 보호
======================================================================

이번 단계에서 변경 금지:

Production Plan
Production Blocks
Speech Assets
Generated Assets
WAV
Human Pronunciation Review
Render Spec
Timeline
Scene Layout
PAUSE
viewer_action
active asset selection
TTS
audio checksum

13-4A/B의 기존 artifact history도 삭제하지 마라.

승인 관련 downstream artifact만 정합성 교정한다.

======================================================================
20. 외부 호출 금지
======================================================================

Gemini TTS 호출 0
YouTube API 호출 0
영상 생성 AI 호출 0
외부 이미지 생성 0
실제 MP4 생성 0

이번 단계는 승인 metadata/gate 교정이다.

======================================================================
21. Git
======================================================================

사용자가 명시적으로 요청하기 전에는:

git commit 금지
git push 금지

git status 확인은 허용.

======================================================================
22. 완료 후 기대 상태
======================================================================

정상적인 최종 상태 예:

selected_candidate:
CLEAN_DARK_FOCUS

candidate_selection_status:
SELECTED

full_profile_approved:
false

approval_status:
PARTIALLY_APPROVED
또는 동등한 안전 상태

approved_category_count:
실제 provenance 확인 결과

pending_category_count:
나머지

Ready for Final Renderer Binding:
NO

Approved Visual Profile:
NO 또는 PARTIAL

Human Visual Review:
CLEAN_DARK_FOCUS DIRECTION SELECTED

13-4C full completion:
NO

다음 단계:
남은 category를 Prototype/Human Review로 확정

======================================================================
23. 완료 보고에서 반드시 답할 것
======================================================================

작업 후 다음 항목을 번호로 상세 보고하라.

1. 수정/추가 파일
2. 기존 승인 오류의 정확한 원인
3. Human Review 실제 selected candidate
4. 잘못 기록된 candidate
5. 기존 visual_design_specs id=2 상태
6. id=2를 어떻게 보존/무효화/대체했는지
7. correction lineage 방식
8. 신규 canonical row id
9. 최종 selected_candidate
10. candidate_selection_status
11. full_profile_approved
12. 최종 approval_status
13. approved category 수
14. pending category 수
15. category별 최종 상태 전체 목록
16. color_palette provenance 조사 결과
17. color_palette exact 값 승인 유지/철회 여부
18. 철회했다면 이유
19. typography_scale provenance 조사 결과
20. typography_scale exact 값 승인 유지/철회 여부
21. 철회했다면 이유
22. CLEAN_DARK_FOCUS와 palette 정합성
23. CLEAN_DARK_FOCUS와 typography scale 정합성
24. mandatory Renderer category 목록
25. optional category 목록
26. Ready for Final Renderer Binding 최종 결과
27. Renderer Gate가 NO라면 정확한 blocker
28. approved_visual_profile.json 수정 결과
29. canonical profile 경로
30. history artifact 보존 여부
31. approve-visual-design CLI semantic 변경 여부
32. CLI 하위 호환 여부
33. candidate selection과 full finalize 분리 여부
34. auto approval 방지 결과
35. 신규 Integrity Check 목록
36. Integrity Check 전체 결과
37. 신규 테스트 수
38. 전체 테스트 수
39. 기존 테스트 회귀 여부
40. 13-4A/B 회귀 여부
41. Production Plan 불변 여부
42. Render Spec 불변 여부
43. Timeline 불변 여부
44. Scene Layout 불변 여부
45. WAV 불변 여부
46. Human Pronunciation Review 불변 여부
47. Gemini TTS 호출 수
48. YouTube API 호출 수
49. 영상 생성 AI 호출 수
50. 실제 MP4 생성 여부
51. git commit 여부
52. git push 여부
53. 남은 unresolved mandatory visual categories
54. 다음 Human Review에서 확정해야 할 정확한 항목
55. 13-4C full completion 여부
56. Ready for Stage 13-5 여부
57. 발견된 실제 bug/semantic debt
58. 발견된 제한사항
59. 성공 기준 전체 충족 여부

마지막에는 반드시 다음처럼 명시하라.

CANONICAL VISUAL CANDIDATE: CLEAN_DARK_FOCUS

FULL APPROVED VISUAL PROFILE: YES / NO

READY FOR FINAL RENDERER BINDING: YES / NO

READY FOR STAGE 13-5: YES / NO

현재 예상되는 정직한 결과는:

CANONICAL VISUAL CANDIDATE: CLEAN_DARK_FOCUS
FULL APPROVED VISUAL PROFILE: NO
READY FOR FINAL RENDERER BINDING: NO
READY FOR STAGE 13-5: NO

이다.

단 실제 코드/데이터 조사 결과가 다르면
있는 그대로 보고하라.

======================================================================
24. 성공 기준
======================================================================

다음을 모두 만족해야 이번 교정 완료다.

- 실제 Human Review selected candidate가 CLEAN_DARK_FOCUS로 정정
- SOFT_LIGHT 잘못된 canonical approval 제거
- history 삭제 없음
- correction lineage 존재
- candidate selection과 full approval 분리
- category-level approval 존재
- exact token provenance 재검증
- 근거 없는 HEX 승인 금지
- 근거 없는 px 승인 금지
- pending category를 APPROVED로 위장하지 않음
- full_profile_approved=false
- ready_for_final_renderer_binding=false
- invalidated/superseded row가 canonical latest로 선택되지 않음
- approved_visual_profile canonical artifact 정합성 회복
- 13-4A auto approval 없음
- 기존 상류 데이터 불변
- 외부 API 0
- MP4 0
- 신규 테스트 PASS
- 기존 테스트 회귀 없음
- git commit/push 없음

이번 작업의 핵심 질문은 하나다.

“사람이 실제로 승인한 것보다 더 많이 승인된 것으로
시스템이 착각하고 있지 않은가?”

조금이라도 그렇다면 Gate를 NO로 유지하라.