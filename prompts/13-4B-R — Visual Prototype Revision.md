# Stage 13-4B-R — Visual Prototype Revision
# CLEAN_DARK_FOCUS Human Review 반영

현재 프로젝트는 다음 단계까지 완료되어 있다.

- Stage 13-1 Render Specification 완료
- Stage 13-2 Timeline Compiler 완료
- Stage 13-3 Scene/Layout Specification 완료
- Stage 13-3A answer_reveal_policy semantic debt 수정 완료
- Stage 13-4A Visual Design System 완료
- Stage 13-4B Visual Prototype 1차 생성 완료
- Human Visual Review 진행 중
- Approved Visual Profile은 아직 없음
- Stage 13-4C는 아직 시작하면 안 됨

현재 Production Plan:

Production Plan ID = 7

현재 canonical versions:

Render Spec = 13.1
Timeline = 13.2
Scene Layout = 13.3
Visual Design = 13.4

현재 테스트 상태:

761 tests PASS

현재 Visual Design Integrity Check:

22/22 PASS

현재 Human Review 상태:

PENDING

현재 Approved Visual Profile:

NO

현재 Ready for Final Renderer Binding:

NO

======================================================================
0. 이번 작업의 정확한 목적
======================================================================

이번 작업은 새로운 Stage 13-4A를 만드는 것이 아니다.

13-4B에서 생성된 Prototype을 사람이 실제로 검토한 결과를 반영하여
Visual Prototype을 교정하는 작업이다.

작업명:

Stage 13-4B-R
Visual Prototype Revision

이번 작업의 핵심 후보는:

CLEAN_DARK_FOCUS

이다.

Human Review 결과 CLEAN_DARK_FOCUS 방향을 우선 후보로 선택했다.

그러나 이것은 아직:

APPROVED_VISUAL_PROFILE

을 의미하지 않는다.

이번 작업 후에도:

Human Visual Review = PENDING
Approved Visual Profile = NO
Ready for Final Renderer Binding = NO

상태를 유지해야 한다.

수정된 Prototype을 사람이 다시 본 뒤에만
13-4C 진행 여부를 결정한다.

======================================================================
1. 절대 변경하면 안 되는 상류 계약
======================================================================

이번 작업은 Visual Prototype Revision이다.

다음을 수정하지 마라.

Production Plan
Production Blocks
Speech Assets
Generated Audio Assets
Human Review
Render Spec semantics
Timeline
Scene timing
Scene Layout semantics
active asset selection
viewer_action
PAUSE
Answer Reveal Barrier

특히 현재 canonical 사실:

Production Plan ID = 7

video duration = 290120ms

CB06 PAUSE:
240280 → 243280
duration = 3000ms

CB06 answer reveal not-before:
243280ms

CB06 answer audio:
SP039::CONTEXTUAL_WORD
start = 243280ms

CB07:
answer_reveal_policy = None
Timeline Answer Reveal Barrier = 없음
Scene Layout Answer Reveal Barrier constraint = 없음

Active Assets:

CAP = SP039::CONTEXTUAL_WORD
BAG = SP003
MAP = SP029
BAT = SP016

failed/rejected active variant = 0
experimental active variant = 0

이 값들은 이번 단계가 변경할 권한이 없다.

======================================================================
2. 공식 입력
======================================================================

13-4B-R의 공식 Visual Design 입력:

assets/generated/plan_7/render/visual_design.json

또는:

visual_design_specs 테이블의 Plan 7 최신 design_json

Visual Design version:

13.4

Scene/Layout 공식 입력은 계속:

assets/generated/plan_7/render/scene_layout.json

이다.

단 13-4B-R은 Scene Layout을 다시 해석하여
새로운 semantic structure를 발명하면 안 된다.

13-4A의 semantic role을 사용하여
Prototype presentation을 개선하는 단계다.

기존 Prototype:

assets/generated/plan_7/render/prototypes/

을 조사하라.

======================================================================
3. Human Review에서 확정된 최상위 방향
======================================================================

우선 Visual Candidate:

CLEAN_DARK_FOCUS

를 기준으로 Revision한다.

SOFT_LIGHT_EDUCATION을 삭제할 필요는 없다.

하지만 이번 Revision의 주 대상은:

CLEAN_DARK_FOCUS

이다.

CLEAN_DARK_FOCUS의 기본 철학:

- 어두운 배경
- 핵심 학습 대상이 강하게 보임
- 기본 텍스트는 white/gray 계열
- 색은 장식이 아니라 semantic meaning이 있을 때만 사용
- 영어가 화면의 주인공
- 설명 텍스트가 영어보다 강해지지 않음
- 장식 최소화
- Motion은 학습 기능이 있을 때만 사용

중요:

Human Review에서 CLEAN_DARK_FOCUS 방향을 선호했다고 해서
현재 preview의 HEX/font/px 값을 최종 승인값으로 승격하지 마라.

이번에도 candidate/preview 값일 뿐이다.

======================================================================
4. 공통 Visual Grammar
======================================================================

Human Review 결정:

CLEAN_DARK_FOCUS의 공통 Visual Grammar는 유지하되
모든 Scene을 같은 Template으로 만들지 않는다.

Scene의 학습 목적에 따라:

structure
visual hierarchy
progressive disclosure
learning motion
emphasis

가 달라져야 한다.

현재 Scene:

CB01 OPENING
CB02 EXPLANATION
CB03 EXPLANATION
CB04 BLENDING
CB05 PRACTICE
CB06 MINI_SUCCESS
CB07 RECAP
CB08 RESOLUTION

특히:

EXPLANATION
BLENDING
PRACTICE
MINI_SUCCESS
RECAP

은 같은 채널처럼 보여야 하지만
서로 다른 학습 행동을 가져야 한다.

핵심 원칙:

“같은 채널처럼 보이지만,
학습 목적이 다르면 화면도 다르게 행동한다.”

======================================================================
5. Semantic Color — Human Review 결정
======================================================================

Human Review에서 다음을 확정했다.

기본 화면:

white / gray 중심

색은 semantic meaning이 있을 때만 사용한다.

예:

DEFAULT
→ white/gray candidate

PRIMARY_FOCUS
→ 현재 집중해야 하는 학습 대상

RELATION
→ 글자↔소리 등의 관계

SUCCESS
→ 정답 확인

MUTED
→ 이전 단계/기억 흔적

색을 화면을 예쁘게 만들기 위해 사용하지 마라.

모든 색에는 semantic reason이 있어야 한다.

그리고 기존 13-4A 규칙:

NO SEMANTIC INFORMATION MAY DEPEND ON COLOR ALONE

을 반드시 유지한다.

예:

C → /k/

관계를 색으로만 표현하면 안 된다.

position
arrow
connector
weight
scale
motion

등의 non-color cue를 함께 사용한다.

실제 HEX는 아직 APPROVED 값이 아니다.

======================================================================
6. Typography — Human Review 결정
======================================================================

Human Review 방향:

학습 대상:
→ 크고 명확

영어 글자:
→ letterform 명확성 우선

IPA:
→ glyph 정확성과 가독성 우선

행동 안내:
→ 작고 간결

나레이션 Caption:
→ 편안하게 읽을 수 있으나 학습 대상보다 약함

Typography hierarchy:

DOMINANT
PRIMARY
SUPPORTING
CAPTION
MICRO

를 유지한다.

실제 Font Family
Font Weight
px
line-height
letter-spacing

은 이번 단계에서도 최종 승인하지 마라.

Preview candidate로 사용하는 것은 허용한다.

Canonical Visual Design 값으로 승격하지 마라.

======================================================================
7. Caption Layer — Human Review 결정
======================================================================

나레이션 자막과 학습 화면을 분리한다.

화면 구조:

Visual Learning Layer

+

Independent Caption Layer

로 취급한다.

예:

              CAP
        /k/ /æ/ /p/


--------------------------------
       narration caption
--------------------------------

Caption Layer가:

TARGET_WORD
PHONEME
BLEND_SEQUENCE
PROMPT
ANSWER

와 경쟁해서는 안 된다.

16:9 → 9:16 Recomposition에서도
Caption Layer는 독립적으로 재배치 가능해야 한다.

중요:

CB06의 “직접 읽어보세요.”는
NARRATION_CAPTION이 아니라
학습자 행동을 안내하는 SUPPORTING PROMPT다.

======================================================================
8. CB06 MINI_SUCCESS — 핵심 Revision
======================================================================

CB06은 이번 Human Review에서 가장 구체적으로 결정된 Scene이다.

기존 Prototype의 단순:

BEFORE_REVEAL
AFTER_REVEAL

두 상태만으로 끝내지 마라.

CB06은 학습적으로 다음 sequence를 표현할 수 있어야 한다.

PHASE 1
ATTEMPT_PROMPT

↓

PHASE 2
THINKING_PAUSE

↓

PHASE 3
ANSWER_CONFIRMATION

↓

PHASE 4
LETTER_SOUND_MAPPING

↓

PHASE 5
SEQUENTIAL_BLENDING

↓

PHASE 6
CASE_BRIDGE

↓

PHASE 7
SCAFFOLD_REMOVAL

↓

PHASE 8
NATURAL_WORD_FINAL

이 sequence는 Prototype용 visual phase다.

새로운 canonical Timeline을 발명하는 것이 아니다.

상류에 timing 근거가 없는 phase에
임의 millisecond 값을 만들지 마라.

======================================================================
9. CB06 PHASE 1 — ATTEMPT_PROMPT
======================================================================

기존 긴 설명:

“이제 여러분 차례입니다.
화면에 나온 단어를 보고,
앞에서 연습한 소리를 떠올리며 직접 읽어보세요.”

를 화면의 주 학습 텍스트로 그대로 강하게 보여주지 않는다.

화면 행동 안내는 짧게:

“직접 읽어보세요.”

수준으로 축약한다.

중요:

원본 narration/script text를 수정하는 것이 아니다.

Prototype의 visual prompt representation만 간결하게 만드는 것이다.

구조:

          직접 읽어보세요.

                CAP

CAP이 DOMINANT.

행동 안내는 SUPPORTING.

CAP은 Core Safe Area 중심.

행동 안내는 CAP 위쪽에 작고 조용하게 위치한다.

기존 Prototype처럼
긴 설명과 CAP이 비슷한 시각적 강도로 경쟁하지 않게 한다.

======================================================================
10. CB06 PHASE 2 — THINKING_PAUSE
======================================================================

CB06의 canonical PAUSE:

240280 → 243280
3000ms

를 그대로 보존한다.

이 3초 동안:

CAP

이 화면의 주인공이다.

숫자:

3
2
1

카운트다운은 사용하지 않는다.

대신 아주 약한:

THINKING_PROGRESS

visual cue를 허용한다.

예:

          직접 읽어보세요.

                CAP

             ━━━━━━━

이 progress는:

MICRO 또는 SUPPORTING 수준

이어야 한다.

CAP보다 눈에 띄면 안 된다.

중요:

THINKING_PROGRESS가 새로운 타이머를 만드는 것이 아니다.

canonical PAUSE를 시각적으로 표현하는 것뿐이다.

Answer는 243280ms 이전에 절대 나타나면 안 된다.

======================================================================
11. CB06 PHASE 3 — ANSWER_CONFIRMATION
======================================================================

Human Review 결정:

정답 공개 후
기존 문제 CAP을 완전히 제거하지 않는다.

기존 문제는:

MUTED

상태로 작고 흐리게 남긴다.

새 정답 CAP은:

DOMINANT
SUCCESS

상태로 크게 보여준다.

개념:

          CAP
     [ANSWER / SUCCESS]


          cap 또는 CAP
     [MUTED TRACE]

단:

두 CAP이 동일한 강도로 보이면 안 된다.

기존 Prototype처럼:

큰 초록 CAP
+
아래쪽 강한 파란 CAP

이 동시에 경쟁하는 구조를 만들지 마라.

정답이 명백한 주인공이어야 한다.

기존 문제는
“내가 방금 읽어본 문제”라는 기억 흔적 수준이어야 한다.

======================================================================
12. Answer Confirmation과 Explanation 분리
======================================================================

Human Review 결정:

정답 공개 순간에
발음 해설을 한꺼번에 모두 표시하지 않는다.

먼저:

ANSWER_CONFIRMATION

을 한다.

즉:

CAP

정답을 먼저 확인한다.

그 후 별도 visual phase에서:

LETTER_SOUND_MAPPING

으로 이동한다.

핵심:

“내가 읽어본다
→ 맞았는지 확인한다
→ 왜 그렇게 읽는지 본다”

순서를 유지한다.

ANSWER_REVEAL과
PHONEME_EXPLANATION을
같은 순간으로 취급하지 마라.

======================================================================
13. CB06 PHASE 4 — LETTER_SOUND_MAPPING
======================================================================

CAP의 글자와 소리를
한꺼번에 모두 표시하지 않는다.

읽는 방향:

LEFT → RIGHT

에 맞춰 단계적으로 연결한다.

STEP 1:

 C       A       P
 ↓
/k/

STEP 2:

 C       A       P
 ↓       ↓
/k/     /æ/

STEP 3:

 C       A       P
 ↓       ↓       ↓
/k/     /æ/     /p/

중요:

C → /k/
A → /æ/
P → /p/

관계는 색만으로 표현하지 않는다.

반드시:

vertical alignment
arrow/connector
position

등의 non-color cue를 함께 사용한다.

Human Review에서 선택한 원칙:

글자와 소리는 실제 읽는 방향인
왼쪽 → 오른쪽으로 하나씩 연결한다.

======================================================================
14. Audio ↔ Visual Synchronization 원칙
======================================================================

Human Review 결정:

가능하다면 음성과 해당 시각 변화를
같은 순간에 맞춘다.

예:

audio /k/
→ visual C → /k/

audio /æ/
→ visual A → /æ/

audio /p/
→ visual P → /p/

하지만 매우 중요한 제한:

13-4B-R이 새로운 audio timing을 발명하면 안 된다.

상류 Timeline에 정확한 동기화 근거가 있는 경우에만
audio-synchronized visual cue로 표현한다.

근거가 없다면:

“synchronization intent”

만 semantic하게 기록하고
임의:

500ms
700ms
1초

같은 timing을 만들지 마라.

Timeline이 시간을 결정한다.
Visual Design은 시간을 바꾸지 않는다.

======================================================================
15. CB06 PHASE 5 — SEQUENTIAL_BLENDING
======================================================================

Human Review 결정:

세 phoneme을 한꺼번에 가운데로 모으지 않는다.

실제 읽는 방향대로:

LEFT → RIGHT

순차 결합한다.

예:

/k/        /æ/        /p/

↓

/k-æ/                 /p/

↓

/k-æ-p/

이것을:

SEQUENTIAL_BLENDING

visual behavior로 정의한다.

Motion semantic role:

LEARNING_MOTION

이다.

Motion은 장식이 아니라:

분리된 소리
→ 앞에서부터 연결
→ 하나의 발음

이라는 학습 원리를 설명해야 한다.

실제 duration/easing은 아직 승인하지 않는다.

======================================================================
16. Blending 중 C A P 처리
======================================================================

Human Review 결정:

블렌딩이 시작될 때
C A P를 완전히 없애지 않는다.

대신:

PRIMARY → MUTED

로 전환한다.

예:

      C     A     P
      [MUTED]

 /k/       /æ/       /p/
      [PRIMARY]

↓

 /k-æ/              /p/

↓

 /k-æ-p/

즉 학습의 주인공이:

letters
→ letter/sound relation
→ sounds
→ blending
→ word

순서로 이동한다.

이것은 Progressive Disclosure와
Progressive Assistance의 실제 표현이다.

======================================================================
17. CB06 PHASE 6 — CASE_BRIDGE
======================================================================

Human Review 결정:

문제/학습 과정에서 사용한:

CAP

을 마지막 실제 읽기 단계에서:

cap

으로 연결한다.

예:

CAP
 ↓
cap

중요:

상류 source_text/display_text를 수정하지 마라.

CAP → cap은:

VISUAL_TRANSFORMATION

또는 동등한 명확한 semantic representation으로만 표현한다.

원본 lineage는 반드시 유지한다.

목적:

대문자 학습 형태
→ 실제 자연스러운 소문자 단어

사이의 연결을 보여주는 것이다.

13-4B-R이 원본 데이터를 lowercase로 덮어쓰면 안 된다.

======================================================================
18. CB06 PHASE 7 — SCAFFOLD_REMOVAL
======================================================================

Human Review 결정:

학습이 완료되면
분석용 scaffold를 계속 화면에 남겨두지 않는다.

다음 요소:

C A P
arrows
/k/ /æ/ /p/
/k-æ-p/
설명
progress
prompt

등을 조용히:

MUTED
→ REMOVED

방향으로 전환할 수 있어야 한다.

목적:

도움을 받아 읽기
→ 도움 없이 읽기

로 이동하는 것이다.

======================================================================
19. CB06 PHASE 8 — NATURAL_WORD_FINAL
======================================================================

CB06 마지막에는:

cap

만 화면에 남긴다.

예:

                cap

추가:

“정답입니다!”
“성공!”
“축하합니다!”

같은 문구를 기본적으로 추가하지 않는다.

별도의 confetti
badge
celebration icon
character

등도 추가하지 않는다.

완성된 단어 자체가
학습 성공의 결과가 되어야 한다.

핵심:

분석 → 결합 → 실제 읽기

를 끝내고
영어 단어 자체로 돌아간다.

======================================================================
20. 핵심 단어 강조 방식
======================================================================

Human Review 결정:

TARGET_WORD / ANSWER 등
핵심 학습 단어는:

1. 큰 Typography
2. Semantic Point Color
3. 아주 약한 Entrance/Emphasis Motion

을 함께 사용할 수 있다.

Motion은:

“여기를 보세요”

수준이어야 한다.

금지:

bounce 과다
flash
spin
aggressive zoom
decorative pulse 반복
glow 남용

Motion semantic role:

EMPHASIS_MOTION

또는 적절한 기존 role을 사용한다.

======================================================================
21. Progressive Disclosure — Prototype에서 실제로 보여라
======================================================================

기존 13-4A에 Progressive Disclosure가 semantic state로 존재하는 것만으로
이번 Revision을 완료했다고 하지 마라.

Prototype에서 실제로 사람이:

“정보가 단계적으로 나타나고
이전 정보가 약해지고
마지막에는 scaffold가 제거되는 과정”

을 확인할 수 있어야 한다.

특히 CB06에서:

ATTEMPT
THINKING
ANSWER
LETTER_SOUND
BLENDING
CASE_BRIDGE
FINAL

의 대표 상태를 HTML로 직접 볼 수 있게 하라.

======================================================================
22. Prototype 파일 전략
======================================================================

현재 정적 HTML 방식을 유지한다.

외부 resource 없이 열 수 있어야 한다.

Prototype은 preview artifact다.

Canonical Visual Design Spec이 아니다.

CB06에 대해서는 기존:

BEFORE_REVEAL
AFTER_REVEAL

만으로는 Human Review가 충분하지 않으므로
필요한 대표 phase별 HTML을 추가하라.

예시:

CB06_CLEAN_DARK_FOCUS_01_ATTEMPT.html
CB06_CLEAN_DARK_FOCUS_02_THINKING.html
CB06_CLEAN_DARK_FOCUS_03_ANSWER.html
CB06_CLEAN_DARK_FOCUS_04_LETTER_SOUND_1.html
CB06_CLEAN_DARK_FOCUS_05_LETTER_SOUND_2.html
CB06_CLEAN_DARK_FOCUS_06_LETTER_SOUND_3.html
CB06_CLEAN_DARK_FOCUS_07_BLEND_1.html
CB06_CLEAN_DARK_FOCUS_08_BLEND_2.html
CB06_CLEAN_DARK_FOCUS_09_CASE_BRIDGE.html
CB06_CLEAN_DARK_FOCUS_10_FINAL.html

정확한 파일 개수/이름은
기존 prototype generator 구조를 조사한 뒤
중복 없이 가장 명확하게 정하라.

중요:

Human Review가 실제 progression을
브라우저에서 순서대로 확인할 수 있어야 한다.

가능하다면 index/manifest HTML을 제공하여
PREVIOUS / NEXT 또는 링크 목록으로
순서대로 열어볼 수 있게 하는 것도 허용한다.

단 이것은 preview navigation일 뿐
canonical renderer UI가 아니다.

======================================================================
23. 다른 Scene에 적용할 원칙
======================================================================

CB06에서 결정한 화면을
CB03/CB04/CB05/CB07에 그대로 복사하지 마라.

공통 Visual Grammar만 공유한다.

CB03 EXPLANATION:

목적:
관계 이해

따라서:

letter
sound
relation
explanation

의 hierarchy가 명확해야 한다.

CB04 BLENDING:

목적:
소리 결합

따라서:

separation
approach
sequential combination
target word

의 학습 Motion이 중요하다.

CB05 PRACTICE:

목적:
학습자가 직접 시도

따라서:

설명 감소
target 강화
도움 최소화

가 중요하다.

CB06 MINI_SUCCESS:

목적:
직접 읽기
→ 생각
→ 정답 확인
→ 원리 확인
→ 도움 없이 읽기

CB07 RECAP:

목적:
이미 배운 내용을 빠르게 재확인

따라서:

새 설명을 처음부터 반복하지 않는다.

Progressive Assistance 원칙에 따라
도움을 줄인다.

BAG
BAT
MAP
CAP

등의 recap 대상이
같은 Visual Grammar 안에서 빠르게 확인되어야 한다.

CB07에는 Mini Success Answer Barrier를 만들지 마라.

======================================================================
24. 16:9 / 9:16
======================================================================

기존 원칙 유지:

16:9가 기본 Long-form.

9:16은 단순 Crop이 아니다.

동일:

semantic elements
learning relationships
visual hierarchy

를 유지하고
layout만 Responsive Recomposition한다.

CB06의 핵심:

TARGET_WORD
LETTER_SOUND_MAPPING
BLEND_SEQUENCE
ANSWER

는 9:16에서도 Core Safe Area 중심 관계를 유지해야 한다.

Caption Layer는 독립적으로 재배치한다.

단 이번 Revision에서
canonical width/height/fps를 확정하지 마라.

필요한 HTML preview 값은
PREVIEW_ONLY로 취급한다.

======================================================================
25. 13-4A 수정 범위
======================================================================

기존 13-4A Visual Design System을 무조건 재작성하지 마라.

먼저 조사하라.

Human Review에서 새로 확정된 개념 중
기존 semantic schema로 충분히 표현 가능한 것은
기존 구조를 재사용한다.

예:

element_state
entrance_style
motion_role
typography_role
color_role

로 표현 가능하면 새 taxonomy를 만들지 않는다.

반면 다음처럼 실제로 새로운 reusable semantic 개념이 필요한 경우:

THINKING_PROGRESS
SEQUENTIAL_BLENDING
VISUAL_TRANSFORMATION
SCAFFOLD_REMOVAL
AUDIO_VISUAL_SYNC_INTENT

등은 기존 schema로 표현 가능한지 먼저 조사한다.

표현 불가능할 때만
최소한의 semantic extension을 추가하라.

새 필드를 추가한다면:

왜 기존 schema로 표현할 수 없는지
완료 보고에서 설명하라.

======================================================================
26. 중요한 Source-of-Truth 원칙
======================================================================

13-4B-R은 presentation을 수정하는 단계다.

다음 질문의 답을 새로 만들면 안 된다.

무엇을 가르치는가?
→ 상류 Content/Production data

어떤 Speech Asset을 쓰는가?
→ 상류 Render Spec

언제 소리가 재생되는가?
→ Timeline

어떤 Scene 구조인가?
→ Scene Layout

어떤 semantic visual role인가?
→ Visual Design System

13-4B-R이 결정하는 것은:

“Human Review에서 정한 Visual Grammar를
Prototype에서 어떻게 눈으로 검증 가능하게 보여줄 것인가?”

이다.

======================================================================
27. Validation
======================================================================

기존 13-4 Validation을 보존한다.

추가/강화가 필요하다면 최소 다음을 검증하라.

1. CLEAN_DARK_FOCUS revision 존재
2. CB06 ATTEMPT state 존재
3. CB06 THINKING state 존재
4. CB06 ANSWER state 존재
5. Answer가 PAUSE barrier 이전 Prototype state에 노출되지 않음
6. THINKING_PROGRESS가 answer를 암시하지 않음
7. Answer와 기존 prompt word가 동일 visual priority로 경쟁하지 않음
8. Answer = DOMINANT/SUCCESS
9. previous prompt trace = MUTED
10. LETTER_SOUND mapping이 left-to-right progression 지원
11. C→/k/, A→/æ/, P→/p/ relation이 color-only가 아님
12. SEQUENTIAL_BLENDING progression 지원
13. letters가 blending 중 MUTED 가능
14. CAP→cap transformation이 upstream text mutation이 아님
15. scaffold removal 지원
16. final natural word state 존재
17. final state에 불필요한 celebration decoration 없음
18. Caption Layer 독립
19. Learning Text와 Caption 경쟁 방지
20. canonical timing 발명 없음
21. audio sync는 upstream evidence 없으면 timing 발명 없음
22. CB07 no Mini Success contamination
23. 16:9→9:16 crop-only 아님
24. Prototype candidate가 APPROVED로 자동 승격되지 않음
25. renderer-neutral canonical spec 유지
26. deterministic output where applicable
27. 기존 13-4A 계약 회귀 없음

숫자를 채우기 위한 meaningless validation은 만들지 마라.

======================================================================
28. Tests
======================================================================

기존 761 tests를 모두 보존한다.

새 동작에는 회귀 테스트를 추가하라.

최소 case:

A.
CB06 ATTEMPT에서 Answer 미노출

B.
CB06 THINKING에서 Answer 미노출

C.
CB06 Answer state에서 Answer DOMINANT/SUCCESS

D.
기존 Prompt word trace는 MUTED

E.
LETTER_SOUND step 1:
C→/k/만 활성

F.
LETTER_SOUND step 2:
C→/k/, A→/æ/

G.
LETTER_SOUND step 3:
C→/k/, A→/æ/, P→/p/

H.
relation이 color-only가 아님

I.
Sequential Blend:
/k/ + /æ/ → /k-æ/

J.
Sequential Blend:
/k-æ/ + /p/ → /k-æ-p/

K.
Blending 중 C A P는 MUTED

L.
CAP→cap이 visual transformation이며 source text mutation 없음

M.
Final state는 cap 중심

N.
Final state에 celebration decoration 없음

O.
CB06 barrier 243280 이전 Answer 금지

P.
CB06 PAUSE 3000ms 불변

Q.
CB07 barrier 생성 안 됨

R.
Caption Layer 독립

S.
canonical px/HEX/font approval 없음

T.
Prototype auto approval 없음

U.
기존 13-4A/B regression 없음

V.
전체 기존 test regression 없음

실제 구현 중 발견되는 bug에는
별도 regression test를 추가하라.

======================================================================
29. 이번 단계에서 금지
======================================================================

금지:

TTS 호출
Gemini TTS 호출
YouTube API 호출
영상 생성 AI 호출
실제 MP4 생성
WAV 수정
Speech Asset 수정
Human Review 상태 변경
Production Plan 수정
Render Spec timing 수정
Timeline 수정
Scene Layout 수정
CB06 PAUSE 수정
CB06 Answer Barrier 수정
CB07 barrier 생성
active asset 재선택
CAP fallback 재선택
source_text 수정
display_text 수정
CAP을 canonical data에서 cap으로 덮어쓰기
canonical width/height/fps 임의 확정
최종 HEX 승인
최종 Font 승인
최종 px 승인
최종 Motion duration 승인
CLEAN_DARK_FOCUS 자동 APPROVED 처리
13-4C 자동 실행
git commit
git push

사용자가 명시적으로 요청하기 전에는
commit/push하지 마라.

======================================================================
30. 이번 단계의 정상 완료 상태
======================================================================

정상 완료 후:

13-4A Visual Design System:
VALID / 필요한 최소 semantic extension만 반영

13-4B Original Prototype:
보존 가능

13-4B-R Revised CLEAN_DARK_FOCUS Prototype:
GENERATED

Human Visual Review:
PENDING

Approved Visual Profile:
NO

Ready for 13-4C:
NO

Ready for Final Renderer Binding:
NO

이어야 한다.

이것은 실패가 아니다.

수정된 Prototype을 사람이 실제로 다시 봐야 하기 때문이다.

======================================================================
31. 완료 보고
======================================================================

완료 후 다음 항목을 번호로 상세 보고하라.

1. 수정/추가 파일
2. 13-4B-R Architecture
3. 공식 입력 Visual Design
4. Production Plan ID
5. 기존 Visual Design version
6. Revision version/identifier
7. Entry Gate 결과
8. 기존 761 tests baseline 확인
9. CLEAN_DARK_FOCUS Revision 적용 여부
10. SOFT_LIGHT_EDUCATION 보존 여부
11. 기존 13-4A schema 변경 여부
12. schema를 변경했다면 정확한 이유
13. 새 semantic role/field 목록
14. Human Review 결정 반영 목록
15. Semantic Color 반영
16. Typography hierarchy 반영
17. Caption Layer 반영
18. Core Safe Area 반영
19. CB06 phase taxonomy
20. ATTEMPT 화면 결과
21. 행동 안내 문구 처리
22. CAP DOMINANT 처리
23. THINKING 화면 결과
24. 3000ms PAUSE 보존
25. THINKING_PROGRESS 처리
26. Countdown 미사용 확인
27. ANSWER_CONFIRMATION 결과
28. Answer DOMINANT/SUCCESS 결과
29. 기존 Prompt trace MUTED 결과
30. 기존 Prototype의 CAP 중복 경쟁 문제 해결 여부
31. Answer와 Explanation 분리 결과
32. LETTER_SOUND_MAPPING 결과
33. C→/k/ mapping
34. A→/æ/ mapping
35. P→/p/ mapping
36. left-to-right progression 결과
37. color-only relation 여부
38. Audio↔Visual sync 처리 방식
39. 새 timing 발명 여부
40. SEQUENTIAL_BLENDING 결과
41. /k/→/k-æ/→/k-æ-p/ progression
42. Blending 중 C A P MUTED 결과
43. CASE_BRIDGE 결과
44. CAP→cap visual transformation 결과
45. source_text/display_text 불변 확인
46. SCAFFOLD_REMOVAL 결과
47. NATURAL_WORD_FINAL 결과
48. 최종 cap 단독 상태 결과
49. Celebration decoration 미사용 여부
50. CB03 적용 방식
51. CB04 적용 방식
52. CB05 적용 방식
53. CB06 적용 방식
54. CB07 적용 방식
55. CB07 Mini Success contamination 여부
56. 16:9 처리
57. 9:16 Recomposition 처리
58. Caption Layer responsive 처리
59. Prototype HTML 파일 수
60. CB06 Prototype 파일 목록
61. Prototype index/manifest 결과
62. Preview-only style 사용 여부
63. canonical HEX 확정 여부
64. canonical Font 확정 여부
65. canonical px 확정 여부
66. canonical Motion duration 확정 여부
67. 신규 Validation 목록
68. 신규 Integrity Check 목록
69. Integrity Check 전체 결과
70. 신규 테스트 수
71. 전체 테스트 수
72. 기존 761 tests 회귀 여부
73. 13-1 회귀 여부
74. 13-2 회귀 여부
75. 13-3 회귀 여부
76. 13-4A 회귀 여부
77. Production Plan/05~12 불변 여부
78. Render Spec 불변 여부
79. Timeline 불변 여부
80. Scene Layout 불변 여부
81. generated WAV 불변 여부
82. Human Review 데이터 불변 여부
83. CAP active asset
84. BAG/MAP/BAT active assets
85. failed/rejected variant 사용 여부
86. experimental variant 사용 여부
87. Gemini TTS 호출 수
88. YouTube API 호출 수
89. 영상 생성 AI 호출 수
90. 실제 MP4 생성 여부
91. DB 저장/수정 여부
92. Revised Prototype 경로
93. report 경로
94. 구현 중 발견한 실제 bug/semantic debt
95. 남은 unresolved critical fields
96. 남은 unresolved non-critical fields
97. Human Visual Review 상태
98. Approved Visual Profile 상태
99. Ready for Stage 13-4C
100. 다음 Human Review에서 사람이 확인해야 할 정확한 항목

마지막에는 반드시:

READY FOR REVISED VISUAL PROTOTYPE REVIEW: YES/NO

READY FOR STAGE 13-4C: NO — HUMAN VISUAL REVIEW REQUIRED

라고 출력하라.

사람이 실제 Revised Prototype을 승인하기 전에는
절대로:

READY FOR STAGE 13-4C: YES

라고 출력하지 마라.

======================================================================
32. 최종 성공 기준
======================================================================

이번 작업의 성공은
“더 예쁜 HTML을 만들었다”가 아니다.

다음이 실제 Prototype에서 눈으로 확인 가능해야 한다.

CB06:

직접 읽어보세요.
        ↓
CAP
        ↓
3초 Thinking
        ↓
정답 CAP
        ↓
기존 문제 흔적 MUTED
        ↓
C → /k/
A → /æ/
P → /p/
        ↓
/k/ + /æ/
        ↓
/k-æ/ + /p/
        ↓
/k-æ-p/
        ↓
CAP → cap
        ↓
scaffold 제거
        ↓
cap

그리고 이 전체 과정에서:

- 학습 대상이 항상 주인공이어야 한다.
- 긴 설명이 학습 대상과 경쟁하면 안 된다.
- 색은 의미가 있을 때만 사용한다.
- 색만으로 관계를 설명하면 안 된다.
- Motion은 학습 기능이 있어야 한다.
- Caption은 별도 Layer다.
- Timeline을 바꾸면 안 된다.
- 새로운 timing을 발명하면 안 된다.
- 16:9와 9:16은 같은 학습 의미를 공유한다.
- 9:16은 단순 Crop이 아니다.
- CLEAN_DARK_FOCUS는 아직 Candidate다.
- Human Review 없이 Approved Profile을 만들면 안 된다.

가장 중요한 판단 기준:

“왕초보 학습자가 설명을 읽느라 고민하지 않고,
화면을 보는 것만으로
지금 무엇을 보고,
무엇을 읽고,
어떻게 소리를 연결해야 하는지
따라갈 수 있는가?”

이 기준으로 Stage 13-4B-R을 구현하라.