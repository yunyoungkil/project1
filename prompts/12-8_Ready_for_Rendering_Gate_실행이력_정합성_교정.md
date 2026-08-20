# 12-8. Ready for Rendering Gate 실행이력 정합성 교정

## 0. 현재 실제 상태

12-7까지 완료되었고, 실제 최신 DRY_RUN report에서 다음이 확인된다.

Production Plan ID: 7

Source Speech Assets: 44
Actual Generation Units: 51

Already Reusable: 51
Need Generation: 0
Blocked: 0

Expected Gemini TTS Base Calls: 0

Representative Review Gate: COMPLETE
Ready for Full Generation: YES
FULL EXECUTED: YES

SP021 /t/:
Voice Lineage PASS
Pronunciation Review APPROVED

SP032 /m/:
Voice Lineage PASS
Pronunciation Review APPROVED

SP035 /p/:
Voice Lineage PASS
Pronunciation Review APPROVED

그런데:

Ready for Rendering: NO

로 남아 있다.

현재 report에는 active Rendering blocker가 하나도 표시되지 않는다.

따라서 이번 작업의 목적은:

"Ready for Rendering이 실제 현재 Production Plan의 materialized asset/review/full execution 상태를 기준으로 계산되는지 추적하고, 현재 DRY_RUN mode 자체 때문에 NO가 되는 stale gate가 있다면 교정하는 것"

이다.

새 TTS 생성 단계가 아니다.

Gemini TTS 호출 금지.
YouTube API 호출 금지.


## 1. 핵심 원칙

Ready for Rendering은 현재 CLI 실행 mode가:

DRY_RUN
SAMPLE
FULL

중 무엇인가에 의해 결정되어서는 안 된다.

Ready for Rendering은 Production Plan 단위의 persistent state를 봐야 한다.

즉 다음 질문에 답해야 한다.

1. 과거 FULL generation이 실제 완료됐는가?
2. 현재 required Generation Unit 전부 materialized됐는가?
3. 현재 active Generation Unit 전부 technical validation을 통과했는가?
4. active strategy가 Full Generation Plan과 일치하는가?
5. 현재 active asset에 review blocker가 남아 있는가?
6. manifest가 완전한가?

현재 실행이 DRY_RUN이라는 이유만으로 NO가 되면 안 된다.


## 2. 현재 모순 재현

실제 DB/report에서 반드시 다음 상태를 먼저 재현한다.

Generation Units = 51
REUSE = 51
GENERATE = 0
BLOCKED = 0

Representative Review Gate = COMPLETE
FULL EXECUTED = YES

Rendering blocker active list = 0

Ready for Rendering = NO

이 모순이 실제 코드의 어느 조건에서 발생하는지 lineage를 추적한다.


## 3. ready_for_rendering 계산 함수 추적

research/asset_generator.py에서 다음을 찾는다.

- Ready for Rendering을 계산하는 함수
- rendering blockers 함수
- FULL execution status 함수
- run mode 검사
- manifest completeness 검사
- materialization 검사
- review gate 검사

최종 boolean expression을 정확하게 보고한다.

예:

ready_for_rendering = (
    mode == "FULL"
    and ...
)

같은 조건이 있다면 왜 존재하는지 추적한다.

이번 문제를 추측으로 수정하지 않는다.


## 4. 현재 run과 persistent plan state 분리

중요.

다음 두 개념을 구분한다.

CURRENT RUN

예:
DRY_RUN
api_calls=0
generated_count=0
reused_count=0

PERSISTENT PLAN STATE

예:
과거 FULL 실행 완료
51 Generation Units 모두 materialized
active reviews complete
manifest complete

Ready for Rendering은 반드시:

PERSISTENT PLAN STATE

를 기반으로 계산한다.

현재 DRY_RUN의:

generated_count=0
reused_count=0

같은 run-local 통계를 Ready for Rendering 조건으로 사용하면 안 된다.


## 5. FULL EXECUTED 판정

현재 report:

FULL EXECUTED: YES

가 실제 DB의 asset_generation_runs 이력을 기반으로 계산되는 것으로 보고되었다.

Ready for Rendering도 동일한 authoritative FULL execution state를 사용해야 한다.

예:

has_successful_full_run(production_plan_id)

또는 기존 동등 함수를 재사용한다.

FULL run의 존재만으로 pass하는 것도 안 된다.

FULL 실행 이후 모든 generation unit materialization이 완료돼 있어야 한다.


## 6. Materialization Gate

현재:

Generation Units = 51
REUSE = 51
GENERATE = 0
BLOCKED = 0

이므로 모든 required Generation Unit이 materialized된 상태다.

Ready for Rendering에서 이 상태를 확인할 때:

현재 DRY_RUN 결과의 generated_assets 배열만 보면 안 된다.

DB + current Full Generation Plan을 기준으로:

모든 required generation_unit_id에
AVAILABLE 또는 valid REUSED asset이 존재하는지 검사한다.


## 7. Active Review Gate

12-7에서 _rendering_blockers를 수정하여
과거 실험 variant가 blocker로 들어오지 않게 했다.

현재 active blocker 예상:

0

다음을 blocker로 다시 포함시키면 안 된다.

- SP039::LOWERCASE_WORD
- SP039::MINIMAL_CONTEXT_WORD
- SP013::CONTEXT_RESTRICTED
- SP003::CONTEXTUAL_WORD
- SP029::CONTEXTUAL_WORD
- SP029::LOWERCASE_WORD
- SP029::MINIMAL_CONTEXT_WORD

active Full Generation Plan이 선택한 asset만 review gate 대상으로 본다.


## 8. 현재 active review 상태 검증

최소 다음을 실제 DB에서 다시 확인한다.

BAG DIRECT_WORD:
pronunciation APPROVED
tone APPROVED

MAP DIRECT_WORD:
pronunciation APPROVED
tone APPROVED

CAP CONTEXTUAL_WORD:
pronunciation APPROVED
tone APPROVED

BAT DIRECT_WORD:
pronunciation APPROVED
tone APPROVED

/æ/:
APPROVED

/t/:
APPROVED

/m/:
APPROVED

/p/:
APPROVED

/b/:
/g/:
기존 APPROVED

BAT DIRECT_SEQUENCE:
APPROVED

MAP DIRECT_SEQUENCE:
APPROVED

BAG DIRECT_SEQUENCE:
APPROVED

실제 DB 값이 다르면 그대로 보고한다.


## 9. Ready for Rendering 정의

Ready for Rendering은 최소 다음 조건의 conjunction으로 정의한다.

A.
successful FULL execution history exists

B.
current Full Generation Plan complete

C.
all required Generation Units materialized

D.
GENERATE = 0

E.
BLOCKED = 0

F.
all active generated audio technical validation pass

G.
all required active pronunciation reviews complete

H.
required active tone reviews complete

I.
active strategy matches Full Generation Plan

J.
manifest complete

K.
Production Plan unchanged

현재 CLI mode는 조건에 넣지 않는다.


## 10. DRY_RUN에서도 YES가 가능해야 함

중요.

FULL이 과거에 성공적으로 완료된 상태에서:

python -m research.cli assets --dry-run --plan-id 7

을 실행하면:

Ready for Rendering: YES

가 나올 수 있어야 한다.

DRY_RUN이라는 의미는:

"이번 실행에서 TTS를 생성하지 않는다"

이지:

"이 Plan이 rendering ready가 아니다"

가 아니다.


## 11. SAMPLE run도 persistent gate를 왜곡하지 않는다

마찬가지로 이미 Rendering Ready인 Plan에서
향후 sample/report 명령을 실행했다고 해서:

Ready for Rendering YES → NO

로 바뀌어서는 안 된다.

run mode와 plan readiness를 분리한다.


## 12. 실패 상태에서는 여전히 NO

Gate를 느슨하게 만들지 않는다.

다음은 반드시 NO.

CASE:

FULL 실행 이력 없음
→ NO

required Generation Unit missing
→ NO

GENERATE > 0
→ NO

BLOCKED > 0
→ NO

active pronunciation PENDING
→ NO

active tone review required + PENDING
→ NO

technical validation fail
→ NO

manifest incomplete
→ NO

failed/rejected active asset selected
→ NO


## 13. Report에 blocker 이유 명시

Ready for Rendering이 NO면
반드시 이유를 보고서에 출력한다.

예:

Rendering Blockers:
- SP021: pronunciation_review=PENDING

또는:

- FULL generation has not completed.

현재처럼:

Ready for Rendering: NO

만 있고 blocker가 하나도 표시되지 않는 상태를 금지한다.

YES면:

Rendering Blockers: NONE

출력 권장.


## 14. 신규 Integrity Check

기존 56개 Integrity Check를 보존한다.

필요한 최소 신규 check:

ready_for_rendering_persistent_state_safe

- current run mode에 무관하게 persistent state 기준인지 검증

rendering_gate_reason_complete

- NO이면 blocker reason 최소 1개 존재
- YES이면 blocker 0

dry_run_does_not_reset_rendering_readiness

- 완료 Plan을 DRY_RUN해도 readiness가 NO로 떨어지지 않음

full_execution_history_consistent

- report의 FULL EXECUTED와 rendering gate가 같은 persistent source 사용

all_active_reviews_complete

- Full Plan active asset의 review 상태만 검사

동등 검사가 이미 있으면 재사용한다.


## 15. 테스트

최소 다음 CASE를 추가한다.

CASE A
과거 FULL 완료 + all materialized + all reviews approved + current DRY_RUN
→ Ready for Rendering YES

CASE B
동일 상태 + current SAMPLE
→ Ready for Rendering YES

CASE C
동일 상태 + current FULL
→ Ready for Rendering YES

CASE D
FULL history 없음
→ NO

CASE E
1 Generation Unit missing
→ NO

CASE F
GENERATE=1
→ NO

CASE G
BLOCKED=1
→ NO

CASE H
active pronunciation PENDING
→ NO + exact blocker

CASE I
inactive experimental variant PENDING
→ rendering readiness 영향 없음

CASE J
CAP failed DIRECT_WORD REGENERATE_REQUIRED
하지만 active CONTEXTUAL APPROVED
→ YES 가능

CASE K
active CONTEXTUAL CAP PENDING
→ NO

CASE L
technical validation fail
→ NO

CASE M
manifest incomplete
→ NO

CASE N
NO인데 blocker list가 빈 경우 Integrity fail

CASE O
YES이면 blocker list=0

CASE P
current run generated_count=0인 DRY_RUN이어도 과거 FULL 완료 상태 보존

CASE Q
current run reused_count=0이어도 persistent DB에서 51 materialized면 pass

CASE R
FULL EXECUTED report 값과 gate가 동일 source 사용

CASE S
Production Plan 불변

CASE T
PAUSE 3000ms 불변

CASE U
viewer_action 불변

CASE V
기존 56 Integrity Check 회귀 없음

CASE W
전체 기존 테스트 회귀 없음


## 16. 실제 API 호출 금지

이번 작업은 Gate 계산 교정이다.

Gemini TTS 신규 호출:

0

YouTube API:

0

새 audio asset 생성:

0

기존 파일 수정:

0


## 17. 실제 DB 재검증

수정 후 실제 DB에 대해:

python -m research.cli assets --dry-run --plan-id 7

실행한다.

기대:

Source Speech Assets: 44
Actual Generation Units: 51

Already Reusable: 51
Need Generation: 0
Blocked: 0

Expected Gemini TTS Base Calls: 0

Representative Review Gate: COMPLETE
FULL EXECUTED: YES

Rendering Blockers: NONE

Ready for Full Generation: YES
Ready for Rendering: YES

실제 DB 상태가 이 조건을 만족하지 않는다면
억지로 YES로 만들지 않고 blocker를 정확히 보고한다.


## 18. 05~12 데이터 불변

이번 수정은 readiness evaluation/reporting이다.

다음은 수정하지 않는다.

- video_scripts
- video_directions
- block_directions
- production_plans
- production_blocks
- speech_assets
- generated WAV
- review status

필요한 코드/테스트만 변경한다.


## 19. 완료 보고 형식

한글로 다음 순서대로 보고한다.

1. 수정한 파일
2. Ready for Rendering이 NO였던 정확한 원인
3. 기존 Ready for Rendering boolean expression
4. 현재 run state가 잘못 사용된 지점
5. persistent Plan state 정의
6. FULL execution history source
7. Generation Unit materialization source
8. active review blocker source
9. manifest completeness source
10. 수정 후 Ready for Rendering 조건
11. current DRY_RUN mode가 Gate에서 제거되었는지
12. SAMPLE mode 영향 여부
13. FULL mode 영향 여부
14. inactive experimental variants 영향 여부
15. active blocker 계산 결과
16. 실제 active pronunciation review 결과
17. 실제 active tone review 결과
18. all Generation Units materialized 결과
19. GENERATE 수
20. BLOCKED 수
21. FULL EXECUTED 결과
22. manifest complete 결과
23. 신규 Integrity Check
24. 전체 Integrity Check 결과
25. 수정 전 Ready for Rendering
26. 수정 후 Ready for Rendering
27. Rendering Blocker 수정 전/후
28. 신규 테스트 수
29. 전체 테스트 수
30. 기존 테스트 회귀 여부
31. 실제 Gemini TTS 호출 수
32. YouTube API 호출 수
33. PAUSE 3000ms 보존
34. viewer_action 보존
35. Production Plan 불변
36. generated WAV 불변
37. Human Review 상태 불변
38. 발견된 제한사항


## 20. 성공 기준

현재 실제 Plan 7의 상태가:

51 Generation Units 전부 materialized
GENERATE=0
BLOCKED=0
FULL EXECUTED=YES
Representative Review Gate=COMPLETE
active Human Review blocker=0
technical validation pass
manifest complete

라면:

Ready for Rendering = YES

가 되어야 한다.

그리고 이 결과는:

DRY_RUN
SAMPLE
FULL

중 현재 어떤 명령으로 report를 생성했는지와 무관해야 한다.

이번 작업의 핵심은:

"현재 실행(run)의 상태"와
"Production Plan의 누적 준비 상태(readiness)"를
명확하게 분리하는 것이다.