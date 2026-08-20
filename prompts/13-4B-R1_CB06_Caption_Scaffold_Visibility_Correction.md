# Stage 13-4B-R1 — CB06 Caption / Scaffold Visibility Correction
# CLEAN_DARK_FOCUS Revised Prototype 교정

현재 프로젝트는 다음 상태다.

- Stage 13-1 완료
- Stage 13-2 완료
- Stage 13-3 완료
- Stage 13-4A 완료
- Stage 13-4B 완료
- Stage 13-4B-R Revised Prototype 생성 완료
- 전체 테스트 779개 PASS
- Human Visual Review 진행 중
- Stage 13-4C Full Approval은 아직 금지
- Stage 13-5 진입 금지

이번 작업은 새로운 Visual Design 단계가 아니다.

13-4B-R에서 실제 생성된 CB06 Prototype을 사람이 확인하는 과정에서 발견된
Caption / Scaffold visibility 문제만 최소 범위로 교정한다.

작업명:

Stage 13-4B-R1
CB06 Caption / Scaffold Visibility Correction

======================================================================
0. 실제 Prototype에서 확인된 문제
======================================================================

현재 CB06 CLEAN_DARK_FOCUS Prototype 6개를 사람이 직접 확인했다.

파일:

CB06_CLEAN_DARK_FOCUS_01_ATTEMPT_PROMPT.html
CB06_CLEAN_DARK_FOCUS_02_THINKING_PAUSE.html
CB06_CLEAN_DARK_FOCUS_03_ANSWER_CONFIRMATION.html
CB06_CLEAN_DARK_FOCUS_04_CASE_BRIDGE.html
CB06_CLEAN_DARK_FOCUS_05_SCAFFOLD_REMOVAL.html
CB06_CLEAN_DARK_FOCUS_06_NATURAL_WORD_FINAL.html

실제 생성 결과에서 다음 문제가 확인되었다.

ATTEMPT_PROMPT에는 새 visual action prompt:

"직접 읽어보세요."

가 존재하지만 동시에 기존 narration caption:

"이제 여러분 차례입니다."

"화면에 나온 단어를 보고, 앞에서 연습한 소리를 떠올리며 직접 읽어보세요."

도 화면에 그대로 출력된다.

THINKING_PAUSE에서도 동일한 긴 narration caption이 계속 출력된다.

ANSWER_CONFIRMATION에서도 이전 narration caption이 계속 출력된다.

CASE_BRIDGE에서도 이전 narration caption이 계속 출력된다.

SCAFFOLD_REMOVAL에서도 caption이 실제 DOM에 남아 화면에 출력된다.

NATURAL_WORD_FINAL에서도:

cap

외에 기존 caption 두 개가 그대로 출력된다.

따라서 현재 구현은:

SCAFFOLD_REMOVAL
NATURAL_WORD_FINAL

이라는 phase 이름과 실제 화면 결과가 일치하지 않는다.

======================================================================
1. 이번 교정의 핵심 원칙
======================================================================

중요:

Narration source 자체를 삭제하거나 수정하는 작업이 아니다.

다음을 수정하지 마라.

source_text
display_text
speech_assets
narration
audio
Timeline
Scene Layout
Visual Design canonical semantics

이번 문제는:

DATA REMOVAL

문제가 아니라:

PROTOTYPE VISIBILITY

문제다.

즉 narration caption 데이터는 upstream에 그대로 존재해야 한다.

다만 CB06의 특정 learning phase에서
화면에 노출하지 않는 것이다.

반드시:

SOURCE PRESERVATION
≠
VISUAL VISIBILITY

를 구분하라.

======================================================================
2. 왜 Caption을 숨기는가
======================================================================

CB06 MINI_SUCCESS의 학습 목적은:

설명을 읽는 것

이 아니라:

학습자가 직접 CAP을 읽어보는 것

이다.

따라서 ATTEMPT에서 화면에 필요한 행동 지시는:

"직접 읽어보세요."

정도면 충분하다.

긴 narration caption을 동시에 표시하면:

"직접 읽어보세요."

와

"화면에 나온 단어를 보고, 앞에서 연습한 소리를 떠올리며 직접 읽어보세요."

가 같은 의미를 중복 전달한다.

또한 CAP과 Caption이 시각적으로 경쟁한다.

Human Review에서 확정한 원칙:

영어 학습 대상이 화면의 주인공이다.

Caption은 학습 대상과 경쟁해서는 안 된다.

를 적용하라.

======================================================================
3. CB06 Phase별 정확한 Visibility Contract
======================================================================

다음 Visibility Contract를 구현하라.

--------------------------------------------------
PHASE 01 — ATTEMPT_PROMPT
--------------------------------------------------

화면에 표시:

SUPPORTING ACTION PROMPT:
"직접 읽어보세요."

TARGET WORD:
CAP

표시하지 않음:

기존 narration caption
"이제 여러분 차례입니다."

기존 narration caption
"화면에 나온 단어를 보고, 앞에서 연습한 소리를 떠올리며 직접 읽어보세요."

의도:

          직접 읽어보세요.

                 CAP

CAP = DOMINANT
action prompt = SUPPORTING

Narration source는 삭제하지 않는다.

Prototype phase에서만 visually hidden/not rendered 처리한다.

--------------------------------------------------
PHASE 02 — THINKING_PAUSE
--------------------------------------------------

화면에 표시:

"직접 읽어보세요."

CAP

THINKING_PROGRESS

표시하지 않음:

기존 narration caption 전체

의도:

          직접 읽어보세요.

                 CAP

              ━━━━━━━

중요:

canonical PAUSE:

240280 → 243280
duration = 3000ms

불변.

Countdown:

3
2
1

추가 금지.

THINKING_PROGRESS는 CAP보다 약해야 한다.

--------------------------------------------------
PHASE 03 — ANSWER_CONFIRMATION
--------------------------------------------------

화면에 표시:

ANSWER CAP
→ DOMINANT
→ SUCCESS

이전 문제 CAP trace
→ MUTED

필요한 경우 아주 최소한의 기존 phase semantic만 사용.

표시하지 않음:

이전 narration caption
ATTEMPT용 긴 설명
"직접 읽어보세요." action prompt

즉 ATTEMPT가 끝났으므로
행동 지시도 제거한다.

의도:

              CAP
        [ANSWER / SUCCESS]


              CAP
          [MUTED TRACE]

두 CAP은 동일한 강도로 경쟁하면 안 된다.

--------------------------------------------------
PHASE 04 — CASE_BRIDGE
--------------------------------------------------

화면의 핵심:

CAP → cap

또는 기존 13-4B-R에서 구현한
동등한 visual transformation.

표시하지 않음:

narration caption
ATTEMPT action prompt
THINKING_PROGRESS

이 phase의 목적은 오직:

학습용 대문자 형태
→ 자연스러운 소문자 형태

연결이다.

source_text/display_text를 lowercase로 변경하지 마라.

CAP → cap은 visual-only transformation이다.

--------------------------------------------------
PHASE 05 — SCAFFOLD_REMOVAL
--------------------------------------------------

이 phase는 이름 그대로
학습 보조물을 제거하는 상태여야 한다.

반드시 제거/비노출:

QUESTION
ATTEMPT action prompt
Narration Caption
THINKING_PROGRESS
이전 Prompt trace
기타 설명성 scaffold

최종적으로 남길 핵심:

cap

단, 이 phase는 "제거 과정"을 검토하기 위한 Prototype이므로
구현 구조상 필요한 경우 제거 대상의 상태를:

MUTED
REMOVED
HIDDEN

등으로 metadata에 표현하는 것은 허용한다.

그러나 사람이 브라우저로 보았을 때
긴 설명 Caption이 그대로 보이면 실패다.

--------------------------------------------------
PHASE 06 — NATURAL_WORD_FINAL
--------------------------------------------------

이 phase는 가장 엄격하다.

실제 학습 콘텐츠로 화면에 보여야 하는 것은:

cap

하나뿐이다.

의도:

                 cap

금지:

"직접 읽어보세요."

"이제 여러분 차례입니다."

"화면에 나온 단어를 보고..."

정답입니다
성공
축하합니다
badge
confetti
icon
arrow
progress
prompt
caption
explanation
muted CAP trace
기타 scaffold

즉:

NATURAL_WORD_FINAL
= NATURAL WORD ONLY

이다.

======================================================================
4. Preview Metadata와 학습 콘텐츠를 구분하라
======================================================================

현재 HTML 상단에는:

PREVIEW ONLY -- not the canonical Visual Design Spec...

같은 개발/검토용 metadata가 있다.

이것은 Prototype reviewer를 위한 metadata이므로
학습 콘텐츠 Caption과 동일하게 취급하지 않아도 된다.

하지만 가능하면:

preview metadata

와

actual frame preview

를 구조적으로 분리하라.

예:

<header data-preview-metadata>
...
</header>

<main data-frame-preview>
...
</main>

처럼 구분할 수 있다.

NATURAL_WORD_FINAL의:

"cap만 남음"

이라는 의미는 actual frame preview 안에서
cap만 남는다는 뜻이다.

Preview metadata까지 무조건 삭제하라는 뜻은 아니다.

단 실제 영상 frame처럼 보는 영역이 명확해야 한다.

======================================================================
5. Caption Layer 원칙을 잘못 해석하지 마라
======================================================================

기존 Human Review에서:

Narration Caption은 Independent Caption Layer

라고 결정했다.

이것은:

"모든 phase에서 Caption을 항상 화면에 표시하라"

는 뜻이 아니다.

Independent Caption Layer의 정확한 의미:

Caption이 필요한 phase에서는
학습 요소와 독립된 Layer로 배치한다.

그리고:

phase의 학습 목적상 Caption이 방해되면
그 phase에서는 숨길 수 있어야 한다.

따라서:

Caption Layer exists
≠
Caption always visible

이다.

이 차이를 코드와 테스트에서 명확히 보장하라.

======================================================================
6. Audio와 Caption을 혼동하지 마라
======================================================================

Caption을 숨긴다고 해서:

narration audio

를 삭제하거나 mute하면 안 된다.

Audio Timeline은 그대로다.

이번 단계는 오직 visual prototype visibility다.

즉:

Narration audio may exist
+
Caption visually hidden

상태가 가능하다.

이것을 정상 상태로 취급하라.

======================================================================
7. Canonical Visual Design Schema
======================================================================

이번 수정 때문에:

visual_design.json

schema를 변경하지 마라.

우선 기존 Prototype phase override / renderer logic에서 해결하라.

현재 13-4B-R이:

CB06_PHASES
phase override
prototype rendering

내부에서 처리되고 있으므로
동일한 범위에서 visibility를 교정하는 것을 우선한다.

새 canonical taxonomy를 추가하지 마라.

정말 기존 구조로 표현 불가능한 경우에만
최소 semantic extension을 검토하되,
그 전에 왜 필요한지 증명하라.

현재 예상으로는 schema 변경이 필요하지 않다.

======================================================================
8. 다른 Scene에 적용 금지
======================================================================

이번 패치를:

CB01
CB02
CB03
CB04
CB05
CB07
CB08

전체에 무조건 적용하지 마라.

이번에 사람이 확인한 실제 문제는:

CB06 MINI_SUCCESS

의 phase-specific Caption visibility 문제다.

다른 Scene의 Caption은 각각의 학습 목적이 다르다.

따라서:

CB06 전용 correction

으로 제한한다.

공통 generator를 수정해야 한다면
다른 Scene 출력이 변하지 않는지 반드시 regression test하라.

======================================================================
9. SOFT_LIGHT_EDUCATION 처리
======================================================================

현재 13-4B-R은:

CLEAN_DARK_FOCUS
SOFT_LIGHT_EDUCATION

두 후보 모두 CB06 6-phase Prototype을 생성한다.

이번 visibility bug가 candidate-independent한
CB06 phase semantic bug라면
두 후보 모두 동일하게 수정하는 것이 맞다.

즉:

NATURAL_WORD_FINAL에서 Caption이 남는 문제는
dark/light palette 문제가 아니다.

CB06 phase contract 문제다.

따라서 두 후보 모두 같은 visibility contract를 적용하라.

하지만 Visual Style 자체를 변경하지 마라.

======================================================================
10. 기존 6-phase 구조 보존
======================================================================

현재 13-4B-R에서 상류 데이터 부족으로:

LETTER_SOUND_MAPPING
SEQUENTIAL_BLENDING

을 생략하고 6-phase로 생성했다.

현재 실제 6-phase:

01 ATTEMPT_PROMPT
02 THINKING_PAUSE
03 ANSWER_CONFIRMATION
04 CASE_BRIDGE
05 SCAFFOLD_REMOVAL
06 NATURAL_WORD_FINAL

을 유지하라.

이번 작업에서:

LETTER_SOUND_MAPPING
SEQUENTIAL_BLENDING

을 다시 발명하지 마라.

상류에 EN_PHONEME_DEMO 데이터가 없다면
계속 생략한다.

이번 패치는 Caption/Scaffold visibility만 수정한다.

======================================================================
11. 상류 불변 계약
======================================================================

다음을 변경하지 마라.

Production Plan ID = 7

Render Spec = 13.1
Timeline = 13.2
Scene Layout = 13.3
Visual Design = 13.4

CB06 PAUSE:
240280 → 243280
3000ms

CB06 answer reveal:
not-before = 243280ms

CB06 answer audio:
SP039::CONTEXTUAL_WORD
start = 243280ms

CB07:
Answer Reveal Barrier 없음

Active assets:

CAP = SP039::CONTEXTUAL_WORD
BAG = SP003
MAP = SP029
BAT = SP016

source_text 불변
display_text 불변

WAV 불변
Human Pronunciation Review 불변

======================================================================
12. Prototype 결과 요구사항
======================================================================

수정 후 최소 다음 파일을 다시 생성하라.

CB06_CLEAN_DARK_FOCUS_01_ATTEMPT_PROMPT.html
CB06_CLEAN_DARK_FOCUS_02_THINKING_PAUSE.html
CB06_CLEAN_DARK_FOCUS_03_ANSWER_CONFIRMATION.html
CB06_CLEAN_DARK_FOCUS_04_CASE_BRIDGE.html
CB06_CLEAN_DARK_FOCUS_05_SCAFFOLD_REMOVAL.html
CB06_CLEAN_DARK_FOCUS_06_NATURAL_WORD_FINAL.html

그리고 SOFT_LIGHT 후보도 동일 phase contract를 사용하는 경우
동일하게 재생성한다.

manifest/index도 실제 파일과 일치하도록 갱신한다.

Revision identifier는 기존 13-4B-R과 구분할 필요가 있다면:

13-4B-R1

을 사용할 수 있다.

단 canonical Visual Design version 13.4는 변경하지 마라.

======================================================================
13. 필수 Validation
======================================================================

최소 다음을 검증하라.

1.
ATTEMPT_PROMPT actual frame에
"직접 읽어보세요." 존재

2.
ATTEMPT_PROMPT actual frame에
긴 narration caption 미노출

3.
ATTEMPT_PROMPT에서 CAP DOMINANT

4.
THINKING_PAUSE에 action prompt 존재

5.
THINKING_PAUSE에 CAP 존재

6.
THINKING_PAUSE에 THINKING_PROGRESS 존재

7.
THINKING_PAUSE에 긴 narration caption 미노출

8.
THINKING_PAUSE에서 answer 미노출

9.
ANSWER_CONFIRMATION에 answer CAP 존재

10.
ANSWER_CONFIRMATION answer = DOMINANT/SUCCESS

11.
ANSWER_CONFIRMATION에 previous CAP trace = MUTED

12.
ANSWER_CONFIRMATION에 narration caption 미노출

13.
ANSWER_CONFIRMATION에 ATTEMPT action prompt 미노출

14.
CASE_BRIDGE에서 CAP→cap visual transformation 유지

15.
CASE_BRIDGE에 narration caption 미노출

16.
CASE_BRIDGE에 action prompt 미노출

17.
SCAFFOLD_REMOVAL actual frame에 narration caption 미노출

18.
SCAFFOLD_REMOVAL actual frame에 QUESTION 미노출

19.
SCAFFOLD_REMOVAL actual frame에 THINKING_PROGRESS 미노출

20.
NATURAL_WORD_FINAL actual frame에는 natural word cap만 존재

21.
NATURAL_WORD_FINAL에 Caption 0

22.
NATURAL_WORD_FINAL에 Prompt 0

23.
NATURAL_WORD_FINAL에 Question trace 0

24.
NATURAL_WORD_FINAL에 Progress 0

25.
NATURAL_WORD_FINAL에 Celebration decoration 0

26.
source_text/display_text 불변

27.
canonical visual_design.json 불변

28.
PAUSE 3000ms 불변

29.
Answer Barrier 243280ms 불변

30.
CB07 no barrier 불변

31.
다른 Scene Prototype regression 없음

32.
SOFT_LIGHT/CLEAN_DARK semantic phase parity 유지

======================================================================
14. 테스트 — 반드시 실제 rendered HTML을 검사하라
======================================================================

중요:

이번 버그는 semantic metadata가 맞는데
실제 HTML에 Caption이 남아 있었던 문제다.

따라서 Python object만 검사하는 테스트로 끝내지 마라.

최종 생성된 HTML 문자열 또는 DOM을 직접 검사하는
render-output regression test를 추가하라.

필수 CASE:

CASE A
01 ATTEMPT:
"직접 읽어보세요." 있음

CASE B
01 ATTEMPT:
긴 narration caption 없음

CASE C
02 THINKING:
긴 narration caption 없음

CASE D
02 THINKING:
THINKING_PROGRESS 있음

CASE E
02 THINKING:
Answer 없음

CASE F
03 ANSWER:
Answer CAP 있음

CASE G
03 ANSWER:
긴 narration caption 없음

CASE H
03 ANSWER:
"직접 읽어보세요." 없음

CASE I
04 CASE_BRIDGE:
lowercase cap visual transformation 있음

CASE J
04 CASE_BRIDGE:
긴 narration caption 없음

CASE K
05 SCAFFOLD_REMOVAL:
data-zone-id="caption"의 visible learning content 없음

CASE L
05:
QUESTION visible content 없음

CASE M
06 NATURAL_WORD_FINAL:
actual frame learning content = cap only

CASE N
06:
CAPTION visible count = 0

CASE O
06:
QUESTION visible count = 0

CASE P
06:
thinking progress count = 0

CASE Q
06:
celebration text/icon count = 0

CASE R
source_text/display_text mutation 없음

CASE S
canonical visual_design.json 변경 없음

CASE T
CB06 PAUSE/barrier 불변

CASE U
CB07 barrier 없음

CASE V
다른 7 Scene × candidate 일반 Prototype 회귀 없음

CASE W
CLEAN_DARK와 SOFT_LIGHT가 동일 CB06 visibility semantics를 가짐

테스트는 단순 문자열 오탐을 피하라.

Preview metadata/comment 안에 단어가 존재하는 것과
actual frame에서 visible한 것을 구분해야 한다.

======================================================================
15. 중요한 구현 주의점
======================================================================

단순 CSS:

opacity:0

만 적용하고 DOM에 visible semantics로 남겨두는 식으로
테스트를 통과시키지 마라.

phase에서 필요 없는 learning Caption이라면
Prototype actual frame에서는:

not rendered

또는 명시적:

hidden / REMOVED

상태로 처리하는 것을 우선한다.

접근성 tree에서도 불필요한 Caption이 읽히는 문제가 생기지 않도록
실제 renderer contract를 고려하라.

단 이것을 이유로 canonical source data를 삭제하면 안 된다.

======================================================================
16. 이번 작업에서 하지 말 것
======================================================================

금지:

13-4C 실행
13-4C-1 승인 교정 실행
Visual Candidate 승인
SOFT_LIGHT 승인/거절 변경
CLEAN_DARK 승인 상태 변경
새 HEX 확정
새 Font 확정
새 px 확정
새 Motion duration 확정
새 Output Profile 확정
TTS 호출
Gemini 호출
YouTube API 호출
영상 생성 AI 호출
MP4 생성
WAV 변경
Timeline 변경
Scene Layout 변경
Visual Design canonical schema 변경
CAP asset 변경
BAG/MAP/BAT asset 변경
source_text 변경
display_text 변경
새 phoneme 데이터 발명
LETTER_SOUND_MAPPING 재도입
SEQUENTIAL_BLENDING 재도입
git commit
git push

======================================================================
17. DB 처리
======================================================================

이번 작업은 Prototype correction이다.

승인 상태를 변경하지 마라.

현재 잘못된 과거 승인 row id=2 문제는
별도의 13-4C-1 승인 정합성 교정 책임이다.

이번 패치에서 id=2를 고치지 마라.

현재 최신 Prototype review 상태는 계속:

PENDING_HUMAN_REVIEW

이어야 한다.

필요하다면 새로운 Prototype revision row를 저장할 수 있으나
approval_status는:

PENDING_HUMAN_REVIEW

이어야 한다.

기존 row 삭제/덮어쓰기 금지.

======================================================================
18. 완료 후 기대 상태
======================================================================

정상 완료 후:

13-4A:
COMPLETE / UNCHANGED

13-4B:
HISTORY PRESERVED

13-4B-R:
HISTORY PRESERVED

13-4B-R1:
CB06 CAPTION/SCAFFOLD CORRECTED

Human Visual Review:
PENDING

Approved Visual Profile:
NO

Ready for 13-4C:
NO

Ready for Final Renderer Binding:
NO

Ready for 13-5:
NO

이어야 한다.

======================================================================
19. 완료 보고
======================================================================

완료 후 다음 항목을 번호로 상세 보고하라.

1. 수정/추가 파일
2. bug의 정확한 원인
3. 왜 기존 테스트가 이 bug를 잡지 못했는지
4. 수정 범위
5. canonical visual_design.json 변경 여부
6. Visual Design version
7. Prototype revision identifier
8. baseline test 수
9. CB06 phase 수
10. ATTEMPT_PROMPT 표시 요소
11. ATTEMPT narration caption 미노출 확인
12. ATTEMPT CAP hierarchy
13. THINKING_PAUSE 표시 요소
14. THINKING narration caption 미노출 확인
15. THINKING_PROGRESS 결과
16. Countdown 미사용 확인
17. PAUSE 3000ms 불변 확인
18. Answer barrier 243280ms 불변 확인
19. ANSWER_CONFIRMATION 표시 요소
20. Answer DOMINANT/SUCCESS 확인
21. previous CAP MUTED trace 확인
22. ANSWER narration caption 미노출 확인
23. ANSWER action prompt 미노출 확인
24. CASE_BRIDGE 결과
25. CAP→cap visual transformation 보존
26. CASE_BRIDGE narration caption 미노출
27. source_text/display_text 불변
28. SCAFFOLD_REMOVAL 표시 요소
29. SCAFFOLD_REMOVAL Caption 제거 확인
30. SCAFFOLD_REMOVAL Question 제거 확인
31. NATURAL_WORD_FINAL 실제 표시 요소
32. NATURAL_WORD_FINAL Caption count
33. NATURAL_WORD_FINAL Prompt count
34. NATURAL_WORD_FINAL Question trace count
35. NATURAL_WORD_FINAL Progress count
36. NATURAL_WORD_FINAL celebration count
37. final actual frame이 cap only인지
38. Preview metadata와 actual frame 분리 여부
39. CLEAN_DARK_FOCUS 결과
40. SOFT_LIGHT_EDUCATION 결과
41. 두 candidate visibility semantic parity
42. 다른 Scene Prototype 변경 여부
43. CB07 barrier 불변 여부
44. LETTER_SOUND_MAPPING 미생성 확인
45. SEQUENTIAL_BLENDING 미생성 확인
46. 신규 Validation 목록
47. 신규 Integrity Check 목록
48. HTML/DOM 직접 검사 테스트 목록
49. 신규 테스트 수
50. 전체 테스트 수
51. 기존 테스트 회귀 여부
52. 13-1 회귀 여부
53. 13-2 회귀 여부
54. 13-3 회귀 여부
55. 13-4A 회귀 여부
56. Production Plan 불변 여부
57. Render Spec 불변 여부
58. Timeline 불변 여부
59. Scene Layout 불변 여부
60. WAV 불변 여부
61. Human Pronunciation Review 불변 여부
62. active asset 불변 여부
63. Gemini TTS 호출 수
64. YouTube API 호출 수
65. 영상 생성 AI 호출 수
66. MP4 생성 여부
67. DB row 추가 여부/id
68. approval_status
69. Revised Prototype 경로
70. manifest/index 갱신 여부
71. 발견된 추가 bug/semantic debt
72. unresolved critical issue
73. unresolved non-critical issue
74. Human Visual Review 상태
75. Approved Visual Profile 상태
76. Ready for 13-4C
77. Ready for 13-5
78. git commit 여부
79. git push 여부
80. 성공 기준 전체 충족 여부

마지막에는 반드시:

READY FOR CB06 RE-REVIEW: YES / NO

HUMAN VISUAL REVIEW: PENDING

APPROVED VISUAL PROFILE: NO

READY FOR STAGE 13-4C: NO — CB06 HUMAN RE-REVIEW REQUIRED

READY FOR STAGE 13-5: NO

라고 출력하라.

======================================================================
20. 최종 성공 기준
======================================================================

사람이 수정된 6개 Prototype을 브라우저에서 봤을 때:

01 ATTEMPT

        직접 읽어보세요.

              CAP

02 THINKING

        직접 읽어보세요.

              CAP

           ━━━━━━━

03 ANSWER

              CAP
          [SUCCESS]

              CAP
           [MUTED]

04 CASE BRIDGE

              CAP
               ↓
              cap

05 SCAFFOLD REMOVAL

              cap

06 NATURAL WORD FINAL

              cap

이라는 학습 흐름이 명확해야 한다.

특히 06의 actual frame에는:

cap

외의 학습 콘텐츠가 하나도 남아 있으면 안 된다.

가장 중요한 회귀 테스트:

NATURAL_WORD_FINAL
→ visible learning content == {"cap"}

이다.

그리고 이 결과를 만들기 위해
upstream narration/source/display text를 삭제하거나 변경해서는 안 된다.

이번 수정의 핵심은:

"데이터를 없애는 것"이 아니라
"학습 단계가 끝났을 때 화면에서 도움을 제거하는 것"

이다.