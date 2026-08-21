# 13-4C-13. Font Weight Human Approval

## 0. 작업 목적

13-4C-12에서 생성한 Font Weight Human Review Prototype을
사용자가 실제로 검토했다.

이번 대화에서 사용자는 명시적으로:

"2번 선택"

이라고 결정했다.

따라서 이번 단계의 Human-selected Font Weight candidate는:

BALANCED_HIERARCHY

이다.

이번 단계의 목적은 새로운 Font Weight 후보를 만들거나
Prototype을 다시 생성하는 것이 아니다.

목적은 오직:

1. 실제 Human Review 결정을 provenance와 함께 기록하고
2. font_weight category를 APPROVED로 전환하고
3. canonical visual_design_specs record를 append-only 방식으로 추가하고
4. approved_visual_profile.json을 갱신하고
5. PROJECT_STATE.md를 현재 실제 상태와 일치시키는 것

이다.

중요:

이번 Human Decision은 추론하거나 이전 스펙에서 가정한 것이 아니다.

실제 대화 기록:

User:
"2번 선택 다음 프롬프트 만들어줘"

여기서 "2번"은 바로 직전 13-4C-12 Font Weight Human Review의 선택지:

2 = BALANCED_HIERARCHY

를 의미한다.

따라서 별도의 Human Decision 재질문을 하지 말 것.


==================================================
1. 반드시 먼저 읽을 것
==================================================

작업 시작 전에 반드시:

PROJECT_STATE.md

를 먼저 읽어라.

그 후 실제 canonical source를 검증하라.

최소 확인 대상:

- DB
- approved_visual_profile.json
- research/visual_design.py
- research/cli.py
- tests/test_visual_design.py
- 13-4C-12 Font Weight Review manifest/report
- font_weight_review artifacts

PROJECT_STATE.md는 orientation용 derived summary다.

충돌 시 Source-of-Truth precedence는 기존 PROJECT_STATE.md에 정의된 규칙을 따른다.

PROJECT_STATE.md의 숫자나 상태를 무조건 신뢰하지 말고
실제 DB/canonical artifact/current code와 대조할 것.


==================================================
2. 현재 기대 상태 — 반드시 실제 값 검증
==================================================

기대값:

Production Plan ID:
7

Visual Design Version:
13.4

Canonical Visual Candidate:
CLEAN_DARK_FOCUS

현재 canonical visual_design_specs record:
id = 9

현재 Approved category count:
4

현재 Pending category count:
11

현재 APPROVED:

- font_family
- background
- color_palette
- typography_scale

현재 font_weight:

PENDING_VISUAL_REVIEW

현재 Typography Scale APPROVED:

DOMINANT: 72px
PRIMARY: 46px
SUPPORTING: 28px
CAPTION: 20px
MICRO: 15px

현재 Font Family APPROVED:

VERDANA_HUMANIST

Verdana, Geneva, 'Malgun Gothic', sans-serif

현재 Background APPROVED:

#111318

현재 Color Palette APPROVED:

DEFAULT: #e6e6e6
PRIMARY_FOCUS: #60a5fa
RELATION: #c4b5fd
SUCCESS: #4ade80
SECONDARY: #9ca3af
MUTED: #757b87
EXCEPTION_CAUTION: #fbbf24

위 값 중 실제 repository/DB와 다른 것이 발견되면
조용히 덮어쓰지 말고 작업을 중단하고 inconsistency를 보고할 것.


==================================================
3. Human Decision
==================================================

실제 Human-selected candidate:

BALANCED_HIERARCHY

13-4C-12에서 정의된 exact candidate values:

DOMINANT: 800
PRIMARY: 700
SUPPORTING: 500
CAPTION: 400
MICRO: 400

이 값을 임의로 변경하지 말 것.

다른 후보로 치환하지 말 것.

후보 이름을 새로 만들지 말 것.

반드시 13-4C-12의 기존:

build_font_weight_candidates

또는 해당 candidate source를 재사용하여
BALANCED_HIERARCHY가 실제로 위 값인지 검증할 것.

Human Approval 단계에서 별도의 숫자를 하드코딩해
review candidate와 approval candidate가 서로 갈라지는 구조를 만들지 말 것.


==================================================
4. Native / Synthetic provenance 보존
==================================================

Verdana Human Review 당시 확인된 native weights:

400
700

따라서 BALANCED_HIERARCHY의 provenance는:

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

이다.

중요:

CSS font-weight 값이 존재한다고 해서
native font face가 존재한다고 주장하지 말 것.

특히:

800 = native

라고 기록하면 안 된다.

500 = native

라고 기록하면 안 된다.

BALANCED_HIERARCHY를 승인한다는 것은
synthetic weight가 존재하지 않는다는 뜻이 아니다.

Human은 실제 browser rendering 결과를 보고
그 trade-off를 포함한 상태에서 BALANCED_HIERARCHY를 선택한 것이다.

이 provenance를 approval record/report에 보존할 것.


==================================================
5. Approval Persistence Architecture
==================================================

기존 Human Approval 단계의 append-only 패턴을 재사용하라.

참고할 기존 구현:

- Font Family Human Approval
- Background Human Approval
- Color Palette Human Approval
- Typography Scale Human Approval

새로운 독립 architecture를 만들지 말 것.

예상 orchestration 함수 이름:

run_font_weight_human_approval

단, repository naming convention과 충돌한다면
기존 패턴에 맞추되 보고서에 실제 함수명을 명시할 것.


==================================================
6. 구조적 Human-selected candidate guard
==================================================

Human-selected candidate는:

BALANCED_HIERARCHY

로 고정한다.

예:

HUMAN_SELECTED_FONT_WEIGHT_CANDIDATE = "BALANCED_HIERARCHY"

또는 기존 Human Approval 단계와 동일한 방어 패턴.

목적:

- LIGHTER_HIERARCHY accidental approval 방지
- STRONG_BEGINNER accidental approval 방지
- 임의 candidate injection 방지
- review artifact와 approval provenance 분리 방지

다른 candidate가 전달되면 fail-fast 해야 한다.


==================================================
7. 상태 전환
==================================================

font_weight:

PENDING_VISUAL_REVIEW
→
APPROVED

정확한 approved values:

DOMINANT: 800
PRIMARY: 700
SUPPORTING: 500
CAPTION: 400
MICRO: 400

기존 승인 category는 절대 변경하지 말 것:

font_family
background
color_palette
typography_scale


==================================================
8. Canonical Record — append-only
==================================================

현재 canonical record가 실제로 id=9인지 먼저 확인한다.

맞다면 새로운 visual_design_specs row를 append한다.

예상:

previous canonical id:
9

new canonical id:
10

단:

id=10을 하드코딩하지 말 것.

DB가 실제로 생성한 id를 사용한다.

기존 id=9 row는 절대 UPDATE하지 말 것.

검증:

- 이전 canonical row byte/logical equivalent 유지
- row count +1
- 신규 row가 canonical
- font_weight만 PENDING → APPROVED
- 기존 approved categories exact preservation
- 나머지 pending categories exact preservation


==================================================
9. Approved / Pending Category Count
==================================================

현재 실제 상태가 기대값과 일치한다면:

Before:

Approved = 4
Pending = 11

After:

Approved = 5
Pending = 10

APPROVED:

1. font_family
2. background
3. color_palette
4. typography_scale
5. font_weight

나머지는 계속 PENDING_VISUAL_REVIEW.

예상 pending:

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

실제 canonical category 목록을 기준으로 검증할 것.


==================================================
10. approved_visual_profile.json
==================================================

새 canonical approval에 맞게 갱신한다.

반드시 포함/검증:

Font Family:
VERDANA_HUMANIST

Background:
#111318

Color Palette:
기존 승인 7 role exact preservation

Typography Scale:
72 / 46 / 28 / 20 / 15

Font Weight:
800 / 700 / 500 / 400 / 400

Font Weight candidate:
BALANCED_HIERARCHY

가능하면 provenance에:

native/synthetic status

도 기존 schema가 허용하는 범위에서 보존한다.

중요:

기존 schema를 불필요하게 깨뜨리면서까지
새 필드를 억지로 추가하지 말 것.

기존 provenance 구조가 있다면 그것을 재사용한다.


==================================================
11. Full Profile / Renderer Gate
==================================================

Font Weight 하나가 승인됐다고 해서:

full_profile_approved=True

로 만들면 안 된다.

아직 pending category가 존재한다.

따라서 예상:

FULL APPROVED VISUAL PROFILE:
NO

READY FOR FINAL RENDERER BINDING:
NO

READY FOR STAGE 13-5:
NO

RENDERER:
NOT_STARTED

현재 실제 gate 계산 로직을 사용해 검증할 것.

위 값을 단순 하드코딩하지 말 것.


==================================================
12. Prototype
==================================================

새 Font Weight Prototype을 만들지 말 것.

13-4C-12의 기존 review artifact를 그대로 provenance source로 사용한다.

기존:

assets/generated/plan_7/render/font_weight_review/

artifact를 수정하지 말 것.

특히 기존:

index.html
manifest.json
00_FONT_WEIGHT_SIDE_BY_SIDE.html
01~06 candidate HTML

을 approval 과정에서 재생성하거나 덮어쓰지 말 것.


==================================================
13. Production Pipeline 불변성
==================================================

이번 작업은 Visual Approval Persistence 단계다.

다음 영역을 수정하면 안 된다:

production_blocks
speech_assets
generated_assets
render_specs
render_timelines
scene_layouts

또한:

source_text
display_text
pronunciation decisions
human pronunciation review
active generated assets

를 변경하지 말 것.

현재 알려진 row count는 참고값일 뿐이며
실제 DB에서 다시 확인한다.

이전 상태 기준:

production_blocks = 56
speech_assets = 330
generated_assets = 506
render_specs = 3
render_timelines = 2
scene_layouts = 2

visual_design_specs는 approval 때문에 정확히 +1만 증가해야 한다.


==================================================
14. External Calls 금지
==================================================

이번 단계에서 외부 호출은 필요 없다.

금지:

Gemini API
YouTube API
Video AI
Image AI
Font Network
기타 외부 생성 API

Expected:

Gemini calls = 0
YouTube calls = 0
Video AI calls = 0
Image AI calls = 0
Font Network calls = 0


==================================================
15. Media 생성 금지
==================================================

이번 단계에서는:

WAV 생성 금지
MP4 생성 금지

Renderer 구현 시작 금지.

Stage 13-5 시작 금지.


==================================================
16. Tests
==================================================

작업 전에 현재 test baseline을 실제 실행하여 기록한다.

이전 보고값:

956 passed

하지만 이를 그대로 믿지 말고 현재 repository에서 다시 확인한다.

신규 테스트는 최소한 다음을 검증해야 한다:

A. BALANCED_HIERARCHY만 승인 가능

B. LIGHTER_HIERARCHY 승인 시도 거부

C. STRONG_BEGINNER 승인 시도 거부

D. unknown candidate 거부

E. candidate exact values 검증

F. DOMINANT = 800

G. PRIMARY = 700

H. SUPPORTING = 500

I. CAPTION = 400

J. MICRO = 400

K. native/synthetic provenance 정확성

L. font_weight PENDING → APPROVED

M. 기존 font_family preservation

N. 기존 background preservation

O. 기존 color_palette preservation

P. 기존 typography_scale preservation

Q. previous canonical row mutation 없음

R. append-only new canonical row 생성

S. approved_visual_profile.json 갱신

T. Approved count 4 → 5

U. Pending count 11 → 10

V. full_profile_approved=False

W. ready_for_final_renderer_binding=False

X. Stage 13-5 gate closed

Y. Production/Audio/Layout tables 불변

Z. 기존 Font Weight Review artifacts 불변

AA. determinism / integrity

필요하다면 기존 test helper를 재사용할 것.

기존 테스트를 approval 구현에 맞추기 위해
불필요하게 수정하지 말 것.

가능하면 신규 테스트 추가 방식으로 처리한다.


==================================================
17. PROJECT_STATE.md 갱신
==================================================

성공적으로 approval persistence가 완료된 뒤에만
PROJECT_STATE.md를 갱신한다.

예상 변경:

Current Major Stage:
13-4C Human Visual Review

Current Sub-stage:
13-4C-13 Font Weight Human Approval — APPROVED

Approved categories:
5

Pending categories:
10

Font Weight:
APPROVED BALANCED_HIERARCHY

Exact weights:
800 / 700 / 500 / 400 / 400

Native/synthetic note:
800 synthetic
700 native
500 synthetic
400 native
400 native

Canonical record:
새 실제 DB id

Full Profile:
NO

Renderer Binding:
NO

Stage 13-5:
NO

Next Step:
remaining Human Visual Review

가능하면 다음 MANDATORY Human Review 대상으로
caption_style을 우선 검토한다.

단, PROJECT_STATE.md가 canonical source가 아니라
derived current-state summary라는 원칙은 유지한다.


==================================================
18. README
==================================================

필요한 경우에만 최소 수정한다.

예:

Font Weight approval CLI가 새로 추가되었다면
CLI 목록 한 줄 추가.

또는 stale approval count/status가 명시돼 있다면
실제 상태로 갱신.

README 전체를 재작성하지 말 것.


==================================================
19. Report
==================================================

새 보고서 생성:

reports/font_weight_human_approval_2026-08-21.md

보고서에는 최소한 다음을 기록한다:

- Human Decision source
- selected candidate
- exact weights
- native/synthetic provenance
- previous canonical id
- new canonical id
- append-only 여부
- previous row mutation 여부
- category status before/after
- approved/pending count before/after
- existing approval preservation
- approved_visual_profile update 여부
- production/audio/layout invariance
- tests baseline/final
- new/modified test count
- external calls
- WAV/MP4
- bugs
- semantic debt
- limitations
- unresolved critical/non-critical
- next Human Review target


==================================================
20. Human Decision provenance 문구
==================================================

이번에는 과거 단계에서 반복되었던
"실제 대화에 없는 Human 선택을 스펙이 주장하는 문제"가 없어야 한다.

실제 대화 근거가 존재한다.

정확한 provenance:

User:
"2번 선택 다음 프롬프트 만들어줘"

Context:
13-4C-12 Font Weight Human Review choices

2 = BALANCED_HIERARCHY

따라서:

Human Decision:
BALANCED_HIERARCHY

Decision status:
CONFIRMED

별도의 AskUserQuestion을 다시 수행하지 말 것.

이 provenance를 왜곡하거나
"사용자가 BALANCED_HIERARCHY라는 문자열을 직접 입력했다"고
과장하지 말 것.

사용자는 "2번"이라고 선택했고,
그 선택지가 BALANCED_HIERARCHY에 매핑된 것이다.


==================================================
21. Git
==================================================

git commit 하지 말 것.
git push 하지 말 것.

기존 누적 미커밋 변경을 임의로 정리하지 말 것.

다른 단계의 파일을 revert하지 말 것.

작업 종료 후 git status를 보고한다.


==================================================
22. 성공 조건
==================================================

다음이 모두 만족되어야 SUCCESS다:

- 실제 Human Decision provenance 존재
- BALANCED_HIERARCHY 승인
- exact weights 보존
- native/synthetic provenance 보존
- font_weight APPROVED
- append-only canonical persistence
- previous canonical row mutation 없음
- 기존 승인 4 category exact preservation
- Approved 5 / Pending 10
- approved_visual_profile.json 갱신
- review artifacts 불변
- Production/Audio/Layout 불변
- Full Profile NO
- Renderer Binding NO
- Stage 13-5 NO
- 외부 API 0
- WAV 0
- MP4 0
- 전체 tests PASS
- PROJECT_STATE.md 실제 상태 반영
- git commit/push 없음


==================================================
23. 최종 출력 형식
==================================================

작업 완료 후 반드시 아래 형식으로 실제 값을 출력한다.

FONT WEIGHT HUMAN REVIEW: APPROVED

HUMAN DECISION SOURCE:
User selected option 2 in the actual conversation.

HUMAN SELECTED CANDIDATE:
BALANCED_HIERARCHY

APPROVED FONT WEIGHT:
DOMINANT: 800
PRIMARY: 700
SUPPORTING: 500
CAPTION: 400
MICRO: 400

FONT FACE PROVENANCE:
DOMINANT 800: synthetic
PRIMARY 700: native
SUPPORTING 500: synthetic
CAPTION 400: native
MICRO 400: native

TYPOGRAPHY SCALE:
DOMINANT: 72px
PRIMARY: 46px
SUPPORTING: 28px
CAPTION: 20px
MICRO: 15px

FONT FAMILY:
APPROVED VERDANA_HUMANIST
Verdana, Geneva, 'Malgun Gothic', sans-serif

BACKGROUND:
APPROVED #111318

COLOR PALETTE:
APPROVED
DEFAULT #e6e6e6
PRIMARY_FOCUS #60a5fa
RELATION #c4b5fd
SUCCESS #4ade80
SECONDARY #9ca3af
MUTED #757b87
EXCEPTION_CAUTION #fbbf24

PREVIOUS CANONICAL RECORD:
<actual previous id>

NEW CANONICAL RECORD:
<actual new id>

APPEND-ONLY:
YES/NO

PREVIOUS ROW MUTATION:
YES/NO

APPROVED CATEGORY COUNT:
<actual>

PENDING CATEGORY COUNT:
<actual>

FULL APPROVED VISUAL PROFILE:
YES/NO

READY FOR FINAL RENDERER BINDING:
YES/NO

READY FOR STAGE 13-5:
YES/NO

PROJECT_STATE:
UPDATED/NOT UPDATED

TEST BASELINE:
<actual>

TESTS:
<actual passed>, <actual failed>

NEW TESTS:
<actual>

MODIFIED EXISTING TESTS:
<actual>

EXTERNAL API CALLS:
Gemini <actual>
YouTube <actual>
Video AI <actual>
Image AI <actual>
Font Network <actual>

WAV GENERATED:
YES/NO

MP4 GENERATED:
YES/NO

GIT COMMIT:
YES/NO

GIT PUSH:
YES/NO

UNRESOLVED CRITICAL:
<actual>

UNRESOLVED NON-CRITICAL:
<actual>

NEXT HUMAN VISUAL REVIEW:
<actual target>

NEXT:
Continue remaining Human Visual Review.
Do not start Stage 13-5.