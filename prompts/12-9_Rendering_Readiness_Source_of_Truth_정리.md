# 12-9. Rendering Readiness Source of Truth 정리

## 목적

12-8에서 Ready for Rendering이 실제 실행 이력과 무관하게 현재 CLI 실행 mode(DRY_RUN/SAMPLE/FULL)에 종속되던 문제를 수정하여, Production Plan의 persistent state를 기준으로 Ready for Rendering: YES가 정상 계산되도록 교정했다.

하지만 12-8 완료 과정에서 아직 하나의 구조적 모호성이 남아 있다.

현재 시스템에는 서로 의미가 다른 두 값이 같은 ready_for_rendering이라는 이름을 사용할 수 있다.

1. manifest의 ready_for_rendering
   - 현재 run 기준의 local/technical readiness
   - 기존 ready_for_rendering_gate()가 계산
   - 현재 실행 mode의 영향을 받는 기존 의미

2. summary/report의 Ready for Rendering
   - Production Plan 전체의 persistent rendering readiness
   - compute_persistent_rendering_readiness()가 계산
   - FULL 실행 이력, Generation Unit materialization, active review, manifest completeness 등 persistent state를 기준으로 판단
   - 12-8 이후 실제 Renderer 진입 여부를 의미

13 Renderer를 만들기 전에 이 의미 충돌을 제거한다.

이번 단계의 핵심 목표는:

"Renderer가 사용할 Ready for Rendering의 Source of Truth를 하나로 확정하고, run-local readiness와 persistent Plan readiness를 명시적으로 다른 개념과 다른 필드명으로 분리한다."

이번 단계에서는 Renderer 자체를 구현하지 않는다.


## 1. 절대 원칙

다음 원칙을 반드시 지켜라.

1. 12-8에서 구현한 compute_persistent_rendering_readiness()를 Renderer 진입 Gate의 유일한 Source of Truth로 사용한다.
2. 현재 CLI 실행 mode(DRY_RUN/SAMPLE/FULL)는 Renderer 진입 가능 여부를 결정해서는 안 된다.
3. run-local readiness와 persistent Plan readiness를 같은 필드명으로 사용하지 않는다.
4. 기존 의미를 조용히 바꾸지 말고 migration/하위 호환 정책을 명확히 한다.
5. 12-8에서 이미 Ready for Rendering: YES가 된 실제 Plan 7 상태를 깨뜨리지 않는다.
6. Production Plan, Production Blocks, Speech Assets, generated WAV, Human Review 상태를 변경하지 않는다.
7. Gemini TTS를 호출하지 않는다.
8. YouTube API를 호출하지 않는다.
9. asset을 재생성하지 않는다.
10. 13 Renderer는 아직 구현하지 않는다.
11. 새로운 추상화가 필요하지 않다면 파일을 추가하지 않는다.
12. 테스트를 통과시키기 위해 readiness 조건을 약화하지 않는다.


## 2. 먼저 현재 구조를 조사하라

코드를 수정하기 전에 다음을 전부 조사해서 보고하라.

검색 대상:

- ready_for_rendering
- ready_for_rendering_gate
- compute_persistent_rendering_readiness
- manifest["ready_for_rendering"]
- result.get("ready_for_rendering")
- summary["ready_for_rendering"]
- report renderer
- asset manifest builder
- FULL/SAMPLE/DRY_RUN 반환 구조
- 테스트에서 ready_for_rendering을 직접 참조하는 모든 위치

다음 질문에 답하라.

Q1.
현재 ready_for_rendering이라는 이름이 몇 가지 의미로 사용되고 있는가?

각 위치를 다음 형식으로 분류하라.

- 위치
- producer
- consumer
- 의미
- persistent / run-local 여부

Q2.
13 Renderer가 현재 manifest만 읽는다고 가정하면 어떤 잘못된 판단이 발생할 수 있는가?

Q3.
ready_for_rendering_gate()를 아직 유지해야 하는 실제 하위 호환 이유는 무엇인가?

Q4.
manifest의 기존 ready_for_rendering을 제거할 수 있는가?

제거 가능/불가능을 코드와 테스트를 조사한 뒤 결정하라.

추측하지 마라.


## 3. Readiness 의미를 명시적으로 분리하라

최종적으로 최소 다음 두 개념이 명확히 존재해야 한다.

### A. Run-local readiness

의미:

"이번 asset generation run 자체의 기술적 결과가 rendering-ready 조건을 충족했는가?"

권장 명칭:

run_local_ready_for_rendering

또는 코드 스타일에 맞는 더 명확한 이름을 사용해도 된다.

이 값은 historical/persistent Renderer Gate가 아니다.


### B. Persistent Plan Rendering Readiness

의미:

"현재 Production Plan의 누적 asset 상태를 기준으로 Renderer가 안전하게 시작 가능한가?"

Source of Truth:

compute_persistent_rendering_readiness(...)

이 값만 실제 Renderer 진입 Gate로 사용한다.

권장 명칭:

ready_for_rendering

또는

persistent_ready_for_rendering

단, 외부 사용자에게 노출되는 최종 의미는 반드시 하나여야 한다.

보고서의:

Ready for Rendering: YES/NO

는 반드시 persistent Plan readiness를 의미해야 한다.


## 4. Source of Truth를 명문화하라

코드에서 다음 관계가 명확해야 한다.

Production Plan persistent state
    ↓
compute_persistent_rendering_readiness()
    ↓
persistent Ready for Rendering
    ↓
13 Renderer entry gate

반대로 다음 구조는 금지한다.

current CLI mode
    ↓
ready_for_rendering_gate()
    ↓
Renderer entry gate

또한 다음도 금지한다.

manifest의 오래된 run-local ready_for_rendering
    ↓
Renderer entry gate


## 5. Persistent readiness 결과 구조를 점검하라

compute_persistent_rendering_readiness()가 단순 boolean만 반환하는지 또는 상세 결과를 반환하는지 확인하라.

가능하다면 Renderer가 향후 다음 정보를 안정적으로 사용할 수 있도록 구조를 명확히 한다.

예:

{
    "ready_for_rendering": true,
    "full_executed": true,
    "generation_units_total": 51,
    "generation_units_materialized": 51,
    "generate_remaining": 0,
    "blocked_remaining": 0,
    "technical_validation_passed": true,
    "manifest_complete": true,
    "active_review_blockers": [],
    "reasons": []
}

기존 구조가 이미 동일 정보를 제공한다면 불필요하게 새 구조를 만들지 마라.

중요:

reasons 또는 blockers가 있다면 Ready for Rendering: NO의 원인을 기계적으로 설명할 수 있어야 한다.


## 6. Manifest 의미 충돌을 제거하라

현재 manifest에:

manifest["ready_for_rendering"]

이 존재하면서 run-local 의미를 가진다면 반드시 정리한다.

다음 중 실제 코드에 가장 안전한 방법을 선택하라.

Option A — 명시적 rename

예:

manifest["run_local_ready_for_rendering"]

persistent 값은:

manifest["ready_for_rendering"]

또는 별도 persistent section에서 제공한다.


Option B — compatibility alias

기존 consumer가 존재한다면:

manifest["run_local_ready_for_rendering"]
manifest["ready_for_rendering"]

를 일정 기간 함께 제공하되 각 의미를 명확히 정의한다.


Option C — deprecated field

기존 필드를 유지해야 한다면 deprecated임을 코드/리포트에서 명확히 표시하고 Renderer가 절대 읽지 않도록 한다.

어떤 방식을 선택했는지 보고서에 이유를 설명하라.

필드 이름만 바꾸고 consumer를 조사하지 않는 방식은 금지한다.


## 7. Manifest JSON 자체의 정합성도 확인하라

실제:

assets/generated/plan_7/manifest/manifest.json

의 현재 구조를 확인하라.

단, 파일을 재생성하거나 수정해야 하는지는 코드 정책을 먼저 조사한 뒤 결정한다.

이번 단계의 목적은 asset 데이터 변경이 아니라 readiness metadata 의미 정리다.

기존 manifest를 갱신해야만 새 schema가 적용되는 구조라면:

- Gemini 호출 없이
- WAV 변경 없이
- DB review 변경 없이

metadata/manifest만 안전하게 재빌드할 수 있는지 확인한다.

가능하지 않다면 억지로 수정하지 말고 제한사항으로 보고한다.


## 8. Renderer Entry Contract를 정의하라

13 Renderer 구현 전에 사용할 최소 계약을 코드 또는 명확한 helper 수준으로 정의한다.

예:

def get_renderer_entry_readiness(...):
    ...

하지만 이미:

compute_persistent_rendering_readiness(...)

가 그 역할을 충분히 수행한다면 새 함수를 만들지 마라.

Renderer가 앞으로 확인해야 하는 것은 최소 다음과 같다.

Ready for Rendering == YES
FULL execution history == YES
Generation Units materialized == total
GENERATE == 0
BLOCKED == 0
technical validation == PASS
manifest complete == YES
active human review blockers == 0

이 계약을 13단계에서 그대로 소비할 수 있어야 한다.


## 9. Run mode 독립성을 회귀 테스트하라

동일한 persistent Plan state에 대해 다음 세 상황을 테스트한다.

DRY_RUN
SAMPLE
FULL

persistent readiness는 모두 동일해야 한다.

예:

DRY_RUN -> persistent Ready for Rendering = YES
SAMPLE  -> persistent Ready for Rendering = YES
FULL    -> persistent Ready for Rendering = YES

현재 run의 local result는 서로 달라도 된다.

핵심은:

"persistent Renderer Gate는 run mode 때문에 바뀌면 안 된다."


## 10. Negative Gate 테스트를 반드시 추가하라

Ready for Rendering: YES만 테스트하지 마라.

최소 다음 failure case를 검증한다.

CASE A — FULL history 없음

Ready for Rendering = NO
reason = FULL_NOT_EXECUTED


CASE B — Generation Unit 하나 missing

Ready for Rendering = NO


CASE C — GENERATE remaining > 0

Ready for Rendering = NO


CASE D — BLOCKED > 0

Ready for Rendering = NO


CASE E — active pronunciation review PENDING

Ready for Rendering = NO


CASE F — active tone review PENDING

Ready for Rendering = NO


CASE G — inactive experimental variant PENDING

예:

LOWERCASE_WORD
MINIMAL_CONTEXT_WORD
CONTEXT_RESTRICTED

이들만 PENDING이라면 Ready for Rendering에 영향을 주면 안 된다.


CASE H — technical validation fail

Ready for Rendering = NO


CASE I — manifest incomplete

Ready for Rendering = NO


## 11. Active strategy selection은 절대 변경하지 마라

현재 확정된 정책:

EN_NATIVE primary = DIRECT_WORD
EN_NATIVE fallback = CONTEXTUAL_WORD
Blending default = DIRECT_SEQUENCE

실제 active 결과:

BAG = DIRECT_WORD
MAP = DIRECT_WORD
CAP = CONTEXTUAL_WORD
BAT = DIRECT_WORD

그대로 유지한다.

다음 experimental variant는 자동 선택하지 않는다.

LOWERCASE_WORD
MINIMAL_CONTEXT_WORD
CONTEXT_RESTRICTED


## 12. Human Review 상태를 변경하지 마라

현재 active asset review가 완료된 상태를 그대로 사용한다.

이번 단계에서는:

assets-review --set
assets-review --set-tone

을 실행하지 않는다.

어떤 review 상태도 새로 APPROVED/REJECTED 처리하지 않는다.

Readiness 계산만 검증한다.


## 13. 새로운 Integrity Check

기존 Integrity Check 이름은 삭제하거나 약화하지 마라.

최소 다음 검사를 추가한다.

rendering_readiness_single_source_of_truth
manifest_readiness_semantics_safe
renderer_entry_contract_safe
persistent_readiness_mode_independent
run_local_readiness_not_used_as_renderer_gate
rendering_readiness_negative_cases_safe

필요하면 이름은 프로젝트 naming convention에 맞춰 조정 가능하다.

각 check는 실제 의미 있는 조건을 검증해야 한다.

단순 return pass 금지.


## 14. 실제 Plan 7 검증

코드 수정 후 실제 DB를 사용해 다음을 다시 확인한다.

Production Plan ID: 7
Source Speech Assets: 44
Generation Units: 51
Reusable: 51
Need Generation: 0
Blocked: 0
FULL EXECUTED: YES
Representative Review Gate: COMPLETE
Active Rendering Blockers: 0
Manifest Complete: YES
Ready for Rendering: YES

숫자가 다르면 억지로 기대값에 맞추지 말고 원인을 조사한다.


## 15. DRY_RUN 실제 검증

다음을 실행한다.

python -m research.cli assets --dry-run --plan-id 7

Gemini TTS 호출은 반드시:

0

이어야 한다.

리포트에서 최소 다음이 명확히 보여야 한다.

Ready for Full Generation: YES
Ready for Rendering: YES
Rendering Blockers: NONE
FULL EXECUTED: YES

그리고 run-local readiness와 persistent readiness가 둘 다 표시된다면 반드시 이름이 달라야 한다.


## 16. Manifest 검사

실제 manifest를 확인해서 다음을 보고하라.

- manifest schema/version
- run-local readiness field
- persistent readiness field
- deprecated compatibility field 존재 여부
- Renderer가 읽어야 하는 canonical field

manifest에 schema version 개념이 현재 없다면 이번 단계만을 위해 과도한 versioning 시스템을 만들지 마라.

필요성이 실제로 확인될 때만 추가한다.


## 17. 기존 데이터 불변성

작업 전후 다음 row 수 및 핵심 데이터를 비교한다.

최소:

production_plans
production_blocks
speech_assets
video_scripts
video_directions
block_directions

그리고:

PAUSE 3000ms
viewer_action / production_intent
Human Review 상태
generated WAV checksum 또는 파일 변경 여부

를 확인한다.

이번 단계에서 WAV 파일 내용은 변경되면 안 된다.


## 18. API 사용 제한

이번 단계에서:

Gemini TTS API = 0
YouTube API = 0

이어야 한다.

새로운 asset 생성 금지.


## 19. 테스트

기존 전체 테스트를 먼저 실행하고 변경 후 다시 실행한다.

최소 다음 범주를 테스트한다.

- persistent readiness
- run-local readiness
- manifest field semantics
- DRY_RUN mode independence
- SAMPLE mode independence
- FULL mode independence
- FULL history missing
- Generation Unit missing
- GENERATE remaining
- BLOCKED remaining
- pronunciation blocker
- tone blocker
- inactive experimental variant ignored
- technical validation failure
- manifest incomplete
- Renderer entry contract
- Plan 7 positive case
- legacy compatibility

기존 테스트를 단순히 삭제하거나 assertion을 약화해 통과시키지 마라.

Integrity Check 총개수 변경으로 기존 count assertion을 수정해야 한다면 이유를 보고서에 명시한다.


## 20. 13단계와의 경계

이번 단계에서는 다음을 구현하지 않는다.

timeline renderer
video composition
caption renderer
highlight animation
audio mixing
FFmpeg composition
Remotion
MP4 export
thumbnail
visual asset generation

12-9의 책임은 오직:

"13 Renderer가 어떤 readiness 값을 신뢰해야 하는가?"

를 완전히 확정하는 것이다.


## 21. 성공 기준

다음을 모두 만족해야 12-9 완료다.

[ ] run-local readiness와 persistent readiness 의미가 분리됨
[ ] Renderer Gate Source of Truth가 하나로 확정됨
[ ] compute_persistent_rendering_readiness가 canonical source임
[ ] current CLI mode가 Renderer Gate에 영향 없음
[ ] manifest의 ready_for_rendering 의미 충돌 제거
[ ] 기존 consumer/테스트 조사 완료
[ ] Renderer entry contract 명확
[ ] negative gate cases 검증
[ ] inactive experimental variant가 blocker가 아님
[ ] active Human Review 상태 변경 없음
[ ] 51 Generation Units 유지
[ ] GENERATE=0
[ ] BLOCKED=0
[ ] FULL EXECUTED=YES
[ ] Manifest Complete=YES
[ ] Rendering Blockers=0
[ ] Ready for Rendering=YES
[ ] DRY_RUN에서도 Ready for Rendering=YES
[ ] Gemini TTS 신규 호출=0
[ ] YouTube API 호출=0
[ ] WAV 변경 없음
[ ] Production Plan/PAUSE/viewer_action 불변
[ ] 기존 테스트 회귀 없음
[ ] 신규 테스트 전부 pass


## 22. 완료 보고 형식

완료 후 반드시 다음 번호 형식으로 보고하라.

1. 수정한 파일
2. 기존 ready_for_rendering 사용 위치 전체
3. 기존에 존재하던 readiness 의미 종류
4. run-local readiness의 최종 명칭
5. persistent readiness의 최종 명칭
6. Renderer Gate의 canonical Source of Truth
7. ready_for_rendering_gate()의 최종 역할
8. compute_persistent_rendering_readiness()의 최종 역할
9. manifest 기존 필드의 문제
10. manifest 최종 필드 구조
11. compatibility/deprecation 처리 방식
12. Renderer가 13단계에서 읽어야 하는 정확한 필드/helper
13. DRY_RUN/SAMPLE/FULL mode independence 검증 결과
14. FULL history 검증 결과
15. Generation Unit materialization 결과
16. GENERATE 수
17. BLOCKED 수
18. technical validation 결과
19. manifest completeness 결과
20. active pronunciation review 결과
21. active tone review 결과
22. inactive experimental variant 영향 여부
23. Rendering Blocker 수 및 목록
24. 수정 전 Ready for Rendering
25. 수정 후 Ready for Rendering
26. 실제 Plan 7 DRY_RUN 결과
27. 신규 Integrity Check 목록
28. 전체 Integrity Check 결과
29. negative gate 테스트 결과
30. 신규 테스트 수
31. 전체 테스트 수
32. 기존 테스트 회귀 여부
33. Gemini TTS 신규 호출 수
34. YouTube API 호출 수
35. PAUSE 3000ms 보존 여부
36. viewer_action 보존 여부
37. Production Plan/05~11 DB 불변 여부
38. Human Review 상태 불변 여부
39. generated WAV 불변 여부
40. 발견된 제한사항
41. 13 Renderer 진입 계약 최종 요약
42. 성공 기준 전체 충족 여부

중요:

이번 단계가 완료되면 마지막에 반드시 다음 중 하나를 명확히 출력하라.

READY FOR STAGE 13: YES

또는

READY FOR STAGE 13: NO

NO라면 정확한 blocker를 함께 출력하라.