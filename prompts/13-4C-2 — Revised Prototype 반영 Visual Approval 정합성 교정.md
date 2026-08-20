# Stage 13-4C-2 — Revised Prototype 반영 Visual Approval 정합성 교정

현재 프로젝트는 다음 상태다.

- Stage 13-1 완료
- Stage 13-2 완료
- Stage 13-3 완료
- Stage 13-3A 완료
- Stage 13-4A Visual Design System 완료
- Stage 13-4B Visual Prototype 완료
- Stage 13-4B-R Revised Prototype 완료
- Stage 13-4B-R1 CB06 Caption / Scaffold Visibility Correction 완료
- 전체 테스트 baseline: 788 PASS
- Production Plan ID: 7
- Visual Design version: 13.4

이번 단계는 기존 13-4C/13-4C-1 이후 발생한 Revised Prototype과
Human Visual Review 결과를 반영하여
Visual Approval 상태의 Source of Truth를 다시 정합하게 만드는 단계다.

중요:

이번 단계는 새 디자인 생성 단계가 아니다.
새 Prototype 생성 단계가 아니다.
Final Renderer 실행 단계도 아니다.

핵심 목적은:

1. 실제 Human Review에서 선택된 CLEAN_DARK_FOCUS를 canonical candidate로 기록
2. 과거 SOFT_LIGHT_EDUCATION 승인 오류를 canonical truth에서 제외
3. Candidate Selection과 Exact Token Approval을 분리
4. Partial Approval과 Full Profile Approval을 분리
5. 미확정 Visual 값이 Renderer로 넘어가는 것을 차단

하는 것이다.

======================================================================
1. Human Review Source of Truth
======================================================================

실제 Human Review에서 사용자가 선택한 Visual Direction은:

CLEAN_DARK_FOCUS

이다.

사용자는 Prototype을 보고:

"CLEAN_DARK_FOCUS_AFTER_REVEAL이 더 좋은 것 같아"

라고 선택했다.

이후 CB06 Human Review와 13-4B-R/R1 수정 역시
CLEAN_DARK_FOCUS를 기준으로 진행되었다.

따라서 canonical candidate는:

CLEAN_DARK_FOCUS

이어야 한다.

SOFT_LIGHT_EDUCATION을 현재 canonical approved candidate로
취급하면 안 된다.

======================================================================
2. Revised Prototype Human Review 결과
======================================================================

13-4B-R1에서 CB06 Caption/Scaffold bug를 수정했다.

현재 CB06 phase:

01 ATTEMPT_PROMPT
02 THINKING_PAUSE
03 ANSWER_CONFIRMATION
04 CASE_BRIDGE
05 SCAFFOLD_REMOVAL
06 NATURAL_WORD_FINAL

Human Review에서 결정한 Visual Grammar:

- 학습 대상이 화면의 주인공
- dark base
- white/gray 중심의 기본 정보
- Semantic Color 사용
- Target Word = DOMINANT
- Supporting instruction은 학습 대상보다 약하게
- Caption Layer와 Learning Layer 분리
- Caption이 필요하지 않은 phase에서는 숨김 가능
- ATTEMPT에서는 "직접 읽어보세요."만 사용
- THINKING에서는 countdown 없음
- Answer 공개 전 answer hidden
- Answer 공개 후 Answer = DOMINANT + SUCCESS
- 이전 문제 CAP = MUTED trace
- CAP → cap은 visual-only transformation
- Scaffold는 단계적으로 제거
- NATURAL_WORD_FINAL은 자연스러운 단어만 남김
- Celebration decoration 사용하지 않음

13-4B-R1 실측 결과:

01 ATTEMPT:
"직접 읽어보세요." + CAP
narration caption = 0

02 THINKING:
Prompt + CAP + THINKING_PROGRESS
narration caption = 0
answer = 0
PAUSE = 3000ms

03 ANSWER:
ANSWER(ACTIVE)
QUESTION(MUTED)
Answer = DOMINANT/SUCCESS
narration caption = 0
action prompt = 0

04 CASE_BRIDGE:
CAP → cap visual transformation
narration caption = 0

05 SCAFFOLD_REMOVAL:
ANSWER만 유지
Caption = 0
Question = 0

06 NATURAL_WORD_FINAL:
visible learning content == {"cap"}

즉 R1 수정 결과는 Human Review에서 의도했던
CB06 Visual Grammar와 정합한다.

======================================================================
3. 현재 DB History
======================================================================

현재 알려진 visual_design_specs history:

id=1
13-4A initial Visual Design
PENDING_HUMAN_REVIEW

id=2
과거 SOFT_LIGHT_EDUCATION 승인 기록
APPROVED

id=3
13-4B-R Revised Prototype
PENDING_HUMAN_REVIEW

id=4
13-4B-R1 Caption/Scaffold Correction
PENDING_HUMAN_REVIEW

실제 DB를 다시 조회하여 이 정보가 정확한지 확인하라.

id 숫자나 상태가 실제 DB와 다르면
실제 데이터를 Source of Truth로 사용하라.

중요:

기존 row를 삭제하지 마라.

======================================================================
4. id=2 승인 오류 처리
======================================================================

id=2의:

SOFT_LIGHT_EDUCATION = APPROVED

기록은 실제 Human Review Source of Truth와 불일치한다.

하지만 history를 삭제해서는 안 된다.

목표:

id=2는 historical record로 보존

BUT

현재 canonical approved/selected candidate query에서는 제외

되어야 한다.

기존 schema와 architecture를 조사하여
가장 작은 안전한 방식으로 구현하라.

가능한 방식:

SUPERSEDED
INVALIDATED
CORRECTED

또는 별도 correction lineage.

기존 row immutable 정책이 있다면
id=2 자체를 수정하지 않고 새 correction row에서:

supersedes_visual_design_spec_id

또는 동등한 lineage를 사용하라.

중요:

잘못된 기록을 삭제하거나 몰래 덮어쓰지 마라.

======================================================================
5. Candidate Selection과 Full Approval 분리
======================================================================

가장 중요한 semantic invariant:

SELECTED CANDIDATE
≠
FULL APPROVED VISUAL PROFILE

현재:

selected_candidate = CLEAN_DARK_FOCUS

는 확정할 수 있다.

하지만 이것은 다음 exact value가 승인되었다는 뜻이 아니다.

HEX
Font Family
Font Weight
Typography px
Spacing px
Border
Radius
Caption position
Motion duration
Easing
Output width
Output height
FPS

따라서 최소 다음 의미를 분리하라.

selected_candidate

candidate_selection_status

category_approvals

full_profile_approved

ready_for_final_renderer_binding

======================================================================
6. 현재 예상 Approval 상태
======================================================================

현재 예상되는 정직한 상태:

selected_candidate:
CLEAN_DARK_FOCUS

candidate_selection_status:
SELECTED

full_profile_approved:
false

ready_for_final_renderer_binding:
false

approved_visual_profile:
NO 또는 PARTIAL

단 실제 category provenance 조사 결과에 따라
일부 category는 APPROVED일 수 있다.

근거 없는 approval은 금지한다.

======================================================================
7. 15개 Visual Category
======================================================================

현재 Visual Profile category:

1. color_palette
2. typography_scale
3. font_family
4. font_weight
5. spacing_scale
6. background
7. container
8. border
9. radius
10. caption_style
11. focus_style
12. success_style
13. motion_style
14. output_profile_16_9
15. output_profile_9_16

각 category는 최소 다음 의미 중 하나를 가져야 한다.

APPROVED
PENDING_VISUAL_REVIEW
REJECTED
SUPERSEDED

또는 기존 project convention의 동등한 taxonomy.

======================================================================
8. 기존 color_palette 승인 재검증
======================================================================

과거 13-4C 시도에서 다음 값이 APPROVED로 기록되었다.

DEFAULT #2b2b2b
PRIMARY_FOCUS #1d4ed8
RELATION #7c3aed
SUCCESS #15803d
SECONDARY #6b7280
MUTED #b3b3b3
EXCEPTION_CAUTION #b45309

하지만 R1 CLEAN_DARK_FOCUS Prototype 보고에서는
Answer SUCCESS가:

#4ade80

으로 확인되었다.

따라서 과거 approved palette와
현재 CLEAN_DARK preview 사이에 불일치 가능성이 있다.

반드시 provenance를 조사하라.

조사 대상:

research/visual_design.py
candidate definitions
generated Prototype HTML
manifest.json
approved_visual_profile.json
visual_design_specs
reports
tests

확인할 것:

- 위 HEX는 어느 candidate에서 나온 값인가?
- SOFT_LIGHT 전용인가?
- CLEAN_DARK 전용인가?
- 공유 값인가?
- preview-only 값인가?
- 사용자가 exact HEX 자체를 승인했는가?

중요:

Prototype에서 사용됐다는 사실만으로
canonical APPROVED로 승격하지 마라.

Human Review에서 exact HEX 승인 근거가 없다면:

color_palette = PENDING_VISUAL_REVIEW

로 되돌려라.

새 CLEAN_DARK HEX를 임의로 만들지 마라.

======================================================================
9. 기존 typography_scale 승인 재검증
======================================================================

과거 승인 값:

DOMINANT = 64px / 800
PRIMARY = 40px / 700
SUPPORTING = 26px / 500
CAPTION = 18px / 400
MICRO = 14px / 400

반드시 provenance를 조사하라.

확인:

- CLEAN_DARK Prototype에서 실제 사용됐는가?
- SOFT_LIGHT에서만 사용됐는가?
- 두 candidate 공유 preview 값인가?
- preview-only CSS인가?
- 사용자가 exact px/weight를 직접 승인했는가?

사용자가:

"CLEAN_DARK_FOCUS가 더 좋다"

라고 선택한 것은
위 숫자 각각을 승인한 것이 아니다.

exact token Human Review 근거가 없으면:

typography_scale = PENDING_VISUAL_REVIEW

로 되돌려라.

======================================================================
10. Preview Value와 Canonical Value 분리
======================================================================

Prototype을 브라우저에서 보여주기 위해:

HEX
px
font-size
padding
margin

같은 preview value가 존재할 수 있다.

하지만:

PREVIEW VALUE
≠
CANONICAL APPROVED TOKEN

이다.

이 원칙을 코드/validation/test에서 보장하라.

Prototype CSS 값이 존재한다는 이유만으로
category approval이 발생하면 실패다.

======================================================================
11. Exact Token Approval provenance
======================================================================

각 APPROVED category에는
왜 승인됐는지 provenance가 있어야 한다.

가능한 provenance 예:

HUMAN_EXPLICIT_APPROVAL
HUMAN_PROTOTYPE_COMPARISON
CANONICAL_UPSTREAM_VALUE
SYSTEM_DEFAULT

단 SYSTEM_DEFAULT를 Human Approved와 혼동하면 안 된다.

Human approval이 필요한 category에서
SYSTEM_DEFAULT만 존재하면:

PENDING_VISUAL_REVIEW

이어야 한다.

정확한 taxonomy는 기존 architecture에 맞게 조정 가능하다.

======================================================================
12. Approval Status taxonomy
======================================================================

기존:

approval_status=APPROVED

하나로 모든 상태를 표현하지 마라.

가능한 상태:

PENDING_HUMAN_REVIEW
CANDIDATE_SELECTED
PARTIALLY_APPROVED
FULLY_APPROVED
SUPERSEDED
INVALIDATED

현재 예상 top-level 상태:

CANDIDATE_SELECTED

또는:

PARTIALLY_APPROVED

이다.

FULLY_APPROVED는 아니다.

======================================================================
13. Canonical Correction Row
======================================================================

이번 Human Review 결과를 기록하기 위해
필요하면 새 visual_design_specs row를 생성하라.

기존 row 삭제/overwrite보다
append-only history를 우선한다.

새 row는 최소 다음 의미를 표현해야 한다.

revision:
13-4C-2

selected_candidate:
CLEAN_DARK_FOCUS

candidate_selection_status:
SELECTED

full_profile_approved:
false

ready_for_final_renderer_binding:
false

category_approvals:
provenance 기반 결과

correction lineage:
과거 id=2 approval 오류와 연결

정확한 DB schema는 기존 구조를 조사 후 결정한다.

======================================================================
14. Canonical query semantics
======================================================================

매우 중요하다.

"가장 최근 APPROVED row"

같은 단순 query가
canonical profile을 결정해서는 안 된다.

왜냐하면 id=2 같은 과거 잘못된 approval history가 있기 때문이다.

canonical selection은 최소:

not invalidated
not superseded
current lineage
latest applicable correction

을 고려해야 한다.

기존 query path를 조사하고
id=2가 다시 canonical current approval로 선택되지 않는지 테스트하라.

======================================================================
15. approved_visual_profile.json
======================================================================

현재 파일:

assets/generated/plan_7/render/approved_visual_profile.json

을 조사하라.

과거 SOFT_LIGHT approval 또는
full APPROVED 의미가 남아 있다면
current canonical artifact로 사용해서는 안 된다.

history snapshot이 필요하면 보존하라.

하지만 current canonical state는 최소:

selected_candidate = CLEAN_DARK_FOCUS

candidate_selection_status = SELECTED

full_profile_approved = false

ready_for_final_renderer_binding = false

category_approvals = provenance 결과

pending_categories = [...]

correction lineage 존재

를 반영해야 한다.

======================================================================
16. 13-4B-R1 manifest lineage 정리
======================================================================

13-4B-R1 완료 보고에서:

코드상 revision identifier:
13-4B-R1

하지만:

manifest.json
revision = "13-4B-R"

로 남아 있었다.

이것은 artifact lineage mismatch다.

Prototype 내용 자체를 다시 설계하지 말고
manifest가 실제 artifact revision을 나타내도록:

revision = "13-4B-R1"

로 교정하라.

index가 revision을 표시한다면 함께 맞춰라.

단:

VISUAL_DESIGN_VERSION = 13.4

는 절대 변경하지 마라.

Prototype revision과 canonical schema version은 별개다.

======================================================================
17. Renderer Mandatory Category 조사
======================================================================

15개 category를 다음으로 분류하라.

MANDATORY
OPTIONAL
CONDITIONAL

실제 downstream Renderer contract를 조사해서 결정한다.

무조건 15개 모두 mandatory라고 가정하지 마라.

예상 mandatory 후보:

color_palette
typography_scale
font_family
background
caption_style
focus_style
success_style
motion_style
output_profile_16_9

하지만 이것도 실제 consumer를 조사해서 확정하라.

output_profile_9_16이 현재 long-form renderer에
필수인지도 조사하라.

======================================================================
18. Renderer Gate
======================================================================

최상위 Gate:

ready_for_final_renderer_binding

은 boolean이어야 한다.

"YES (부분)"

같은 모호한 표현은 사용하지 마라.

Mandatory category가 하나라도 unresolved면:

ready_for_final_renderer_binding = false

이어야 한다.

부분적으로 사용할 수 있는 category가 있으면
별도 scope로 표현할 수 있다.

예:

approved_scope
pending_scope

하지만 top-level ready=false를 우회할 수 없어야 한다.

======================================================================
19. approve-visual-design CLI semantics 조사
======================================================================

현재 CLI:

approve-visual-design

이 candidate 하나를 선택하는 것만으로:

APPROVED
full_profile_approved
renderer ready

까지 설정하는지 조사하라.

그렇다면 semantic bug다.

최소 다음 operation은 의미적으로 분리되어야 한다.

Candidate Selection

Category Approval

Full Finalization

구현 방식은 기존 architecture에 맞춰 최소 변경한다.

중요 invariant:

SELECT CANDIDATE
≠
FINALIZE PROFILE

======================================================================
20. Full Finalization Gate
======================================================================

Full Approved Visual Profile을 만드는 action은
명시적이어야 한다.

Full finalize 전에 최소:

selected candidate 존재

mandatory categories 전부 APPROVED

category provenance 존재

unresolved critical field 없음

validation PASS

integrity PASS

renderer gate conditions PASS

가 필요하다.

하나라도 실패하면 finalize를 거부하라.

이번 단계에서는 Full Finalize를 실행하지 마라.

======================================================================
21. Negative Tests
======================================================================

다음 CASE를 반드시 테스트하라.

CASE A

id=2 SOFT_LIGHT가
current canonical candidate로 반환
→ FAIL

CASE B

selected_candidate=CLEAN_DARK_FOCUS
+
exact token unresolved
+
full_profile_approved=true
→ FAIL

CASE C

pending mandatory category 존재
+
renderer ready=true
→ FAIL

CASE D

invalidated/superseded row가 canonical로 반환
→ FAIL

CASE E

Prototype CSS HEX 존재
→ color_palette 자동 APPROVED
→ FAIL

CASE F

Prototype font-size 존재
→ typography_scale 자동 APPROVED
→ FAIL

CASE G

candidate selection
→ 자동 full finalize
→ FAIL

CASE H

mandatory category unresolved 상태에서
full finalize 성공
→ FAIL

CASE I

id=2 history 삭제
→ FAIL

CASE J

id=4 history 삭제
→ FAIL

CASE K

13-4A 실행만으로 approval 발생
→ FAIL

CASE L

13-4B/R/R1 generation으로 approval 발생
→ FAIL

CASE M

canonical selected candidate != CLEAN_DARK_FOCUS
→ FAIL

CASE N

full_profile_approved=false
+
ready_for_final_renderer_binding=true
→ FAIL

CASE O

R1 Prototype인데 manifest revision이
13-4B-R로 남음
→ FAIL 또는 명시적 integrity warning

CASE P

Preview-only value를
Human Approved value로 분류
→ FAIL

======================================================================
22. Integrity Checks
======================================================================

기존 Integrity Check 이름을 삭제/변경하지 마라.

이번 단계에 필요한 실제 check만 추가하라.

예:

visual_approval_candidate_consistency_safe

visual_approval_history_preserved

visual_approval_superseded_record_not_canonical

visual_approval_category_scope_safe

visual_approval_exact_token_provenance_safe

visual_approval_preview_not_canonical_safe

visual_approval_full_status_safe

visual_approval_renderer_gate_safe

visual_approval_mandatory_categories_safe

visual_approval_correction_lineage_safe

visual_approval_no_auto_finalize

visual_approval_manifest_revision_safe

visual_approval_complete

숫자를 늘리기 위한 meaningless check는 만들지 마라.

======================================================================
23. Test baseline
======================================================================

현재 baseline 보고:

788 tests PASS

먼저 실제 test suite를 실행하여
baseline이 맞는지 확인하라.

그 후 수정한다.

신규 테스트 추가 후:

전체 test suite PASS

가 필수다.

기존 테스트를 삭제하여 숫자를 맞추지 마라.

기존 테스트를 수정해야 한다면
semantic 변경 이유를 완료 보고에 명시하라.

======================================================================
24. 상류 데이터 불변
======================================================================

이번 단계에서 변경 금지:

Production Plan ID 7

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

active asset selection

CB06 PAUSE

CB06 answer reveal barrier

CB07 no-barrier semantics

CAP = SP039::CONTEXTUAL_WORD

BAG = SP003

MAP = SP029

BAT = SP016

13-4C-2는 Approval Metadata/Gate 정합성 교정이다.

======================================================================
25. Prototype 변경 범위
======================================================================

13-4B-R1 Prototype의 학습 화면을
이번 단계에서 다시 디자인하지 마라.

허용되는 Prototype 관련 변경:

manifest revision correction

index lineage correction

approval/canonical metadata correction

금지:

CB06 visual layout 재설계

Caption policy 재설계

새 phase 생성

LETTER_SOUND_MAPPING 생성

SEQUENTIAL_BLENDING 생성

새 color 적용

새 typography 적용

======================================================================
26. 외부 호출 금지
======================================================================

Gemini TTS 호출 0

YouTube API 호출 0

영상 생성 AI 호출 0

이미지 생성 AI 호출 0

MP4 생성 0

WAV 생성 0

이번 단계에서 Final Renderer 실행 금지.

======================================================================
27. Git
======================================================================

사용자 명시 요청 전:

git commit 금지

git push 금지

git status 확인 허용.

======================================================================
28. 이번 단계에서 하지 말 것
======================================================================

새 Visual Candidate 생성 금지

새 Prototype Candidate 생성 금지

SOFT_LIGHT history 삭제 금지

CLEAN_DARK exact HEX 발명 금지

Font Family 임의 확정 금지

Typography px 임의 승인 금지

Spacing 임의 확정 금지

Border/Radius 임의 확정 금지

Caption 위치 임의 확정 금지

Focus Style 임의 확정 금지

Success Style 임의 확정 금지

Motion duration/easing 임의 확정 금지

16:9 width/height/fps 임의 확정 금지

9:16 width/height/fps 임의 확정 금지

Stage 13-5 실행 금지

Final Renderer 실행 금지

MP4 생성 금지

======================================================================
29. 이번 단계 완료 후 기대 상태
======================================================================

정상적인 예상 상태:

CANONICAL VISUAL CANDIDATE:
CLEAN_DARK_FOCUS

CANDIDATE SELECTION:
SELECTED

EXACT TOKEN APPROVAL:
실제 provenance 기반 PARTIAL 또는 PENDING

FULL APPROVED VISUAL PROFILE:
NO

READY FOR FINAL RENDERER BINDING:
NO

READY FOR STAGE 13-5:
NO

PROTOTYPE REVISION:
13-4B-R1

VISUAL DESIGN VERSION:
13.4

과거 SOFT_LIGHT approval:
HISTORY PRESERVED
BUT NOT CANONICAL

======================================================================
30. 다음 Human Visual Review 준비
======================================================================

이번 단계 완료 후
미확정 Visual category를 한꺼번에 모두 결정하지 마라.

다음 Human Review Round를 dependency 순서로 제안하라.

우선 예상 순서:

ROUND 1
Color Palette + Background

ROUND 2
Typography Scale + Font Family + Font Weight

ROUND 3
Caption Style + Focus Style + Success Style

ROUND 4
Spacing + Container + Border + Radius

ROUND 5
Motion Style

ROUND 6
16:9 Output Profile

ROUND 7
9:16 Recomposition Profile

실제 architecture dependency를 조사한 결과
더 좋은 순서가 있으면 조정 가능하다.

중요:

다음 Round에서 사람이 비교할 수 있도록
구체적으로 어떤 Prototype을 만들어야 하는지도 보고하라.

자동으로 그 Prototype을 생성하지는 마라.

======================================================================
31. 완료 보고
======================================================================

완료 후 다음을 번호로 상세 보고하라.

1. 수정/추가 파일
2. Stage 13-4C-2 Architecture
3. 실행 전 baseline test 수
4. 실행 후 전체 test 수
5. 신규 테스트 수
6. 수정된 기존 테스트 수
7. Production Plan ID
8. Visual Design version
9. Prototype revision
10. Human Review Source of Truth
11. canonical selected candidate
12. 기존 잘못된 candidate
13. visual_design_specs 전체 관련 row 상태
14. id=1 상태
15. id=2 상태
16. id=2 history 보존 여부
17. id=2 canonical 제외 방식
18. id=3 상태
19. id=4 상태
20. id=4 history 보존 여부
21. 신규 correction row 생성 여부/id
22. correction lineage
23. candidate_selection_status
24. full_profile_approved
25. top-level approval_status
26. ready_for_final_renderer_binding
27. color_palette provenance 조사 결과
28. 기존 HEX가 어느 candidate/value source에서 왔는지
29. color_palette exact approval 유지/철회
30. color_palette 최종 상태
31. typography_scale provenance 조사 결과
32. 기존 px/weight가 어느 source에서 왔는지
33. typography exact approval 유지/철회
34. typography_scale 최종 상태
35. font_family 상태
36. font_weight 상태
37. spacing_scale 상태
38. background 상태
39. container 상태
40. border 상태
41. radius 상태
42. caption_style 상태
43. focus_style 상태
44. success_style 상태
45. motion_style 상태
46. output_profile_16_9 상태
47. output_profile_9_16 상태
48. 15 category 전체 상태
49. approved category count
50. pending category count
51. rejected/superseded category count
52. Mandatory Renderer category
53. Optional Renderer category
54. Conditional Renderer category
55. unresolved mandatory category
56. Renderer Gate blocker
57. approved_visual_profile.json 기존 상태
58. approved_visual_profile.json 교정 결과
59. canonical profile 경로
60. history artifact 보존 여부
61. manifest revision 수정 전
62. manifest revision 수정 후
63. index/manifest 정합성
64. approve-visual-design CLI 기존 semantics
65. CLI 수정 여부
66. Candidate Selection과 Full Approval 분리 결과
67. explicit Full Finalization Gate 존재 여부
68. auto finalize 방지 결과
69. Preview HEX auto approval 방지 결과
70. Preview px auto approval 방지 결과
71. 신규 Validation 목록
72. 신규 Integrity Check 목록
73. Integrity Check 전체 결과
74. Negative test CASE A~P 결과
75. 기존 테스트 회귀 여부
76. 13-1 회귀 여부
77. 13-2 회귀 여부
78. 13-3 회귀 여부
79. 13-4A 회귀 여부
80. 13-4B 회귀 여부
81. 13-4B-R 회귀 여부
82. 13-4B-R1 회귀 여부
83. Production Plan/05~12 불변 여부
84. Render Spec 불변 여부
85. Timeline 불변 여부
86. Scene Layout 불변 여부
87. WAV 불변 여부
88. Human Pronunciation Review 불변 여부
89. CAP active asset
90. BAG/MAP/BAT active asset
91. source_text/display_text 불변 여부
92. Gemini TTS 호출 수
93. YouTube API 호출 수
94. 영상 생성 AI 호출 수
95. 이미지 생성 AI 호출 수
96. MP4 생성 여부
97. git commit 여부
98. git push 여부
99. 발견된 실제 bug/semantic debt
100. 발견된 제한사항
101. unresolved critical fields
102. unresolved non-critical fields
103. 다음 Human Visual Review Round
104. 다음 Round에서 비교해야 할 항목
105. 다음 Round용 Prototype 필요 여부
106. 다음 Round Prototype의 정확한 목적
107. 13-4C Full Completion 여부
108. Ready for Final Renderer Binding 여부
109. Ready for Stage 13-5 여부
110. 성공 기준 전체 충족 여부

마지막에는 반드시 다음 형식으로 출력하라.

CANONICAL VISUAL CANDIDATE: CLEAN_DARK_FOCUS

CANDIDATE SELECTION: SELECTED

FULL APPROVED VISUAL PROFILE: YES / NO

READY FOR FINAL RENDERER BINDING: YES / NO

READY FOR STAGE 13-5: YES / NO

NEXT HUMAN VISUAL REVIEW:
<다음 검토 Round>

NEXT PROTOTYPE PURPOSE:
<사람이 무엇을 비교하고 결정해야 하는지>

======================================================================
32. 성공 기준
======================================================================

다음을 모두 만족해야 Stage 13-4C-2 성공이다.

- CLEAN_DARK_FOCUS가 canonical selected candidate
- SOFT_LIGHT 과거 승인 history 보존
- SOFT_LIGHT가 current canonical truth에서는 제외
- id=1/2/3/4 history 삭제 없음
- correction lineage 추적 가능
- Candidate Selection과 Full Approval 분리
- category-level approval 상태 명확
- Preview CSS와 Canonical Token 분리
- exact HEX provenance 재검증
- exact typography provenance 재검증
- 근거 없는 HEX 승인 없음
- 근거 없는 px 승인 없음
- mandatory Renderer category 명확
- unresolved mandatory category가 있으면 renderer ready=false
- full_profile_approved=false
- Final Renderer 실행 없음
- approved_visual_profile canonical artifact 정합성 회복
- R1 manifest revision 정합성 회복
- 13-4A/B/R/R1 auto approval 없음
- 상류 Production/Audio/Timeline/Layout 데이터 불변
- 신규 테스트 PASS
- 기존 테스트 회귀 없음
- 외부 API 호출 0
- MP4 생성 0
- git commit/push 없음

이번 단계의 핵심 질문은 두 가지다.

첫째:

"사람이 실제로 선택한 Visual Direction은 무엇인가?"

답:
CLEAN_DARK_FOCUS

둘째:

"그 선택만으로 모든 Renderer 값을 승인했다고 볼 수 있는가?"

답:
NO

시스템은 이 두 사실을 정확히 동시에 표현해야 한다.

모르는 값은 PENDING으로 남겨라.
사람이 승인하지 않은 값을 시스템이 대신 승인하지 마라.