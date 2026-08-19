# 12-4. EN_NATIVE 전략 확정 및 Full Generation Gate

## 0. 현재 상태와 이번 단계의 목적

현재 12~12-3까지 실제 Gemini TTS 호출과 사람 청취를 통해
다음 정책 후보가 검증되었다.

이미 사람 검토된 결과:

EN_PHONEME_DEMO
- SP007 /b/ → APPROVED
- SP011 /g/ → APPROVED

BLENDING
- SP013::DIRECT_SEQUENCE → APPROVED
- SP013::CONTEXT_RESTRICTED → 사용 가능하지만 기본은 아님

EN_NATIVE
- BAG DIRECT_WORD → 좋음
- MAP DIRECT_WORD → 좋음
- CAP DIRECT_WORD → 실패, REGENERATE_REQUIRED
- CAP CONTEXTUAL_WORD → 좋음, 빠르지 않고 명료함
- MAP CONTEXTUAL_WORD → 발음은 좋지만 DIRECT와 톤 차이가 느껴짐
- BAG CONTEXTUAL_WORD → 발음은 좋지만 DIRECT와 톤 차이가 느껴짐
- LOWERCASE_WORD / MINIMAL_CONTEXT_WORD → 실험상 사용 가능하지만
  현재 기본 전략으로 채택할 이유는 충분하지 않음

따라서 사람이 선택한 제작 정책은:

PRIMARY EN_NATIVE:
DIRECT_WORD

FALLBACK EN_NATIVE:
CONTEXTUAL_WORD

BLENDING DEFAULT:
DIRECT_SEQUENCE

BLENDING ALTERNATIVE:
CONTEXT_RESTRICTED

이다.

이번 단계의 목적은 새 TTS 실험이 아니다.

목적은:

1. 위 사람 결정을 코드 정책으로 확정한다.
2. APPROVED/REGENERATE_REQUIRED 이력을 실제 Full Generation에 반영한다.
3. EN_NATIVE asset별로 primary/fallback을 안전하게 선택한다.
4. 잘못된 DIRECT 결과를 다시 active asset으로 선택하지 않는다.
5. 사람 승인이 필요한 대표 발음 Gate를 충족시킨다.
6. Ready for Full Generation을 정확하게 계산한다.
7. FULL 생성 직전 manifest/generation plan을 확정한다.
8. 아직 44개 전체 FULL 생성은 하지 않는다.

이번 단계가 끝나면:

Ready for Full Generation:
YES

가 되어야 하며,

그 다음 실행에서만 실제 FULL Asset Generation으로 넘어간다.

---

# 1. 절대 원칙

이번 작업은 "전략 확정" 단계다.

새로운 pronunciation strategy를 추가하지 마라.

다음 기존 전략은 그대로 유지한다.

- DIRECT_WORD
- CONTEXTUAL_WORD
- LOWERCASE_WORD
- MINIMAL_CONTEXT_WORD
- DIRECT_SEQUENCE
- CONTEXT_RESTRICTED

새 voice를 도입하지 마라.

Charon 유지.

KO_NARRATION prompt 변경 금지.

EN_PHONEME_DEMO prompt 변경 금지.

Blending prompt 재설계 금지.

FULL 생성 금지.

Renderer 구현 금지.

Production Plan 수정 금지.

---

# 2. EN_NATIVE 최종 정책

최종 정책:

primary_en_native_strategy:
DIRECT_WORD

fallback_en_native_strategy:
CONTEXTUAL_WORD

의미:

1차로 DIRECT_WORD를 선호한다.

단:

해당 target의 DIRECT_WORD asset이
REJECTED 또는 REGENERATE_REQUIRED라면
active output으로 사용하지 않는다.

그 경우:

동일 target의 CONTEXTUAL_WORD 중
APPROVED된 asset이 있으면 그것을 fallback으로 사용한다.

예:

BAG:
DIRECT_WORD APPROVED
→ DIRECT_WORD 사용

MAP:
DIRECT_WORD APPROVED
→ DIRECT_WORD 사용

CAP:
DIRECT_WORD REGENERATE_REQUIRED
+
CONTEXTUAL_WORD APPROVED
→ CONTEXTUAL_WORD 사용

이 구조를 일반화한다.

CAP 하드코딩 금지.

---

# 3. Strategy Selection 함수

명시적인 함수 또는 동등 구조를 만든다.

예:

select_active_en_native_variant(
    source_speech_asset,
    generated_asset_history
)

반환:

{
  selected_strategy,
  selected_generated_asset_id,
  selection_reason
}

selection_reason 예:

PRIMARY_APPROVED

FALLBACK_AFTER_PRIMARY_FAILURE

PRIMARY_PENDING

NO_APPROVED_VARIANT

이유를 추적 가능하게 한다.

---

# 4. 승인 상태가 source of truth

EN_NATIVE 전략 선택 우선순위는
"최신 파일"이나 "가장 짧은 duration"이 아니다.

사람 review 상태가 우선이다.

허용:

APPROVED

금지:

REJECTED
REGENERATE_REQUIRED

PENDING:

Full Generation의 existing reusable active asset으로는
승인되지 않은 상태.

단 신규 생성 예정 asset일 수는 있다.

---

# 5. 현재 실제 Review 상태 반영

실제 DB에서 다음 상태를 확인하고
필요하면 assets-review 명령으로 정확히 기록한다.

반드시 실제 row/metadata를 확인하고
프롬프트의 ID를 맹목적으로 믿지 않는다.

기대 상태:

SP007 /b/
pronunciation_review = APPROVED

SP011 /g/
pronunciation_review = APPROVED

SP013::DIRECT_SEQUENCE
pronunciation_review = APPROVED

CAP DIRECT_WORD
pronunciation_review = REGENERATE_REQUIRED

CAP CONTEXTUAL_WORD
pronunciation_review = APPROVED
tone_consistency_review = APPROVED

BAG DIRECT_WORD
pronunciation_review = APPROVED

MAP DIRECT_WORD
pronunciation_review = APPROVED

현재 사람 청취 결과를 반영하되,
DB에 이미 기록되어 있으면 중복 mutation하지 않는다.

---

# 6. MAP/BAG CONTEXTUAL 처리

MAP CONTEXTUAL_WORD와 BAG CONTEXTUAL_WORD는
발음 자체는 좋았지만 사람 청취에서
기존 음성과 톤 차이가 느껴졌다.

따라서:

기본 active variant로 선택하지 않는다.

그렇다고 REJECTED 처리할 필요도 없다.

PENDING 또는 valid alternative 상태로 보존 가능.

핵심:

DIRECT_WORD가 APPROVED이면
CONTEXTUAL_WORD가 존재하더라도
fallback을 쓸 이유가 없다.

---

# 7. LOWERCASE / MINIMAL_CONTEXT 정책

LOWERCASE_WORD와 MINIMAL_CONTEXT_WORD는 삭제하지 않는다.

실험 결과/대체 후보로 보존.

그러나 현재 제작 정책 우선순위에는 넣지 않는다.

즉 default fallback chain:

DIRECT_WORD
→ CONTEXTUAL_WORD

까지만 사용한다.

LOWERCASE_WORD / MINIMAL_CONTEXT_WORD는
자동 선택 대상이 아니다.

향후 별도 사람이 명시적으로 정책을 바꾸기 전까지
experimental variants로 유지한다.

---

# 8. Blending 최종 정책

default_blending_strategy:

DIRECT_SEQUENCE

로 확정.

사용 이유:

왕초보에게:

/b/
→ /æ/
→ /g/
→ blending

과정을 상대적으로 천천히 들려줘
교육용 demonstration에 적합하다고 사람 청취에서 승인됨.

CONTEXT_RESTRICTED:

valid alternative

로 유지.

현재 Full Generation 기본 blending에는:

DIRECT_SEQUENCE

사용.

단 향후 reinforcement 역할에
CONTEXT_RESTRICTED를 선택할 수 있도록 삭제하지 않는다.

---

# 9. Review 상태와 Tone 상태 분리

기존:

pronunciation_review

tone_consistency_review

분리를 유지한다.

EN_NATIVE active variant가 Full Generation에 사용되려면
대표/critical asset에 대해 최소:

pronunciation_review = APPROVED

필요.

Mini Success answer처럼 HIGH priority인 경우:

pronunciation_review = APPROVED
AND
tone_consistency_review = APPROVED

를 요구한다.

일반 MEDIUM EN_NATIVE:

pronunciation APPROVED를 최소 필수로 하고,
tone review 정책은 현재 샘플 대표 검증을 활용할 수 있다.

정책을 과도하게 만들어
모든 단어를 사람이 하나씩 tone 승인해야 하는 구조는 만들지 마라.

---

# 10. Representative Review Gate

사람이 44개 전부를 FULL 전에 승인하는 것은
자동화 목적에 맞지 않는다.

따라서 대표 Gate를 사용한다.

현재 대표 승인 세트:

Isolated phoneme:
- /b/
- /g/

Blending:
- DIRECT_SEQUENCE

EN_NATIVE normal:
- BAG DIRECT_WORD
- MAP DIRECT_WORD

EN_NATIVE fallback critical:
- CAP CONTEXTUAL_WORD

이 세트가 정책별 대표 검증 역할을 한다.

향후 새로운 발음 패턴/새 전략이 나오면
대표 샘플 추가가 필요할 수 있다.

---

# 11. Ready for Full Generation 정의

신규/기존 함수를 정리하여
Ready for Full Generation을 결정론적으로 계산한다.

최소 조건:

A.
source Production Plan:
ready_for_asset_generation = YES

B.
TTS model/config valid

C.
primary/fallback strategy config valid

D.
phoneme representative review approved

E.
default blending strategy approved

F.
normal EN_NATIVE primary representative approved

G.
fallback EN_NATIVE representative approved

H.
REJECTED/REGENERATE_REQUIRED variant가
active selection에 포함되지 않음

I.
strategy cache isolation pass

J.
Production Plan unchanged

K.
all critical Integrity Checks pass

이 조건이 만족되면:

Ready for Full Generation:
YES

---

# 12. Ready for Full Generation과 Full Asset 완료 구분

중요:

Ready for Full Generation = YES

는:

"전체 asset이 이미 생성됨"

이라는 뜻이 아니다.

의미:

"정책/샘플/검증이 완료되어
전체 필요한 asset을 생성해도 안전함"

이다.

Ready for Rendering은 여전히:

NO

가 정상이다.

FULL generation이 아직 실행되지 않았기 때문.

---

# 13. Full Generation Plan 생성

이번 단계에서 실제 TTS를 생성하지 않고
FULL 생성 계획만 만든다.

예:

{
  "production_plan_id": ...,
  "ready_for_full_generation": true,
  "generation_plan": [
    {
      "source_speech_asset_id": "SP003",
      "speech_mode": "EN_NATIVE",
      "preferred_strategy": "DIRECT_WORD",
      "existing_approved_asset": true,
      "action": "REUSE"
    },
    {
      "source_speech_asset_id": "SP039",
      "speech_mode": "EN_NATIVE",
      "preferred_strategy": "CONTEXTUAL_WORD",
      "selection_reason": "FALLBACK_AFTER_PRIMARY_FAILURE",
      "action": "REUSE"
    },
    ...
  ]
}

action taxonomy 최소:

REUSE
GENERATE
SKIP
BLOCKED

이 계획으로 실제 FULL 실행 전
예상 API 호출 수를 알 수 있어야 한다.

---

# 14. EN_NATIVE generation planning

각 EN_NATIVE source asset에 대해:

1. DIRECT_WORD APPROVED 존재?
→ REUSE DIRECT

2. DIRECT_WORD REJECTED/REGENERATE_REQUIRED?
   CONTEXTUAL_WORD APPROVED 존재?
→ REUSE CONTEXTUAL

3. DIRECT approved 없음,
   CONTEXTUAL approved 없음?
→ GENERATE primary 또는
   정책에 따라 GENERATE+review required

현재 Full 자동화 목적상
새 단어 대부분은 아직 사람이 승인한 결과가 없을 수 있다.

따라서 FULL generation에서는:

DIRECT_WORD로 먼저 생성

하되,

신규 생성 asset은
pronunciation_review=PENDING

이 될 수 있다.

이 경우 Ready for Rendering을 막는 것은 정상.

Ready for Full Generation은
생성 시작 가능 여부만 판단한다.

---

# 15. Generated new EN_NATIVE review policy

FULL 실행으로 새 EN_NATIVE가 생성되면:

technical validation = PASS 가능

pronunciation_review = PENDING

자동 APPROVED 금지.

단 future optimization으로
대표 패턴 기반 자동 승인 정책을 만들지 않는다.

현재는 사람이 확인 필요.

다만 동일 source+same strategy+same prompt version의
APPROVED asset cache hit이면
APPROVED 상태를 재사용 가능.

---

# 16. EN_PHONEME_DEMO planning

현재 승인된 대표 isolated phoneme:

/b/
/g/

그러나 전체 phoneme assets에는:

/æ/
/t/
/m/
/p/
/k/

등도 존재할 수 있다.

이것들을 대표 /b/, /g/가 승인되었다는 이유만으로
자동 APPROVED하지 않는다.

실제 FULL 생성은 가능하지만:

새 phoneme:
pronunciation_review=PENDING

이어야 한다.

Ready for Rendering은
critical phoneme review가 완료될 때까지 NO.

즉:

Ready for Full Generation YES
≠
Ready for Rendering YES

원칙 유지.

---

# 17. Blended phoneme planning

기존 /b-æ-g/ DIRECT_SEQUENCE APPROVED는
전략 자체의 대표 승인.

향후:

/b-æ-t/
/m-æ-p/

등은 동일 DIRECT_SEQUENCE 전략으로 생성 가능.

하지만 개별 generated asset의
pronunciation_review는 기본 PENDING.

전략 승인과 asset 승인 구분.

---

# 18. Cache reuse 규칙

다음 조건이 완전히 동일할 때만
APPROVED status를 가진 cache를 신뢰:

- model
- voice
- speech_mode
- source/tts transcript
- strategy
- prompt version
- relevant delivery instruction

전략이 다르면 승인 상태 전이 금지.

예:

CAP CONTEXTUAL APPROVED

이라고 해서:

CAP LOWERCASE

를 APPROVED로 취급 금지.

---

# 19. 실패 variant 보존

CAP DIRECT_WORD 같은 실패 결과를 삭제하지 않는다.

metadata/history에 보존.

Full Generation Plan에서:

BLOCKED/IGNORED_FAILED_VARIANT

의 근거로 사용.

active selection에서는 제외.

감사 가능성 유지.

---

# 20. default 정책 config

config/research_config.yaml에
이미 적절한 정책 섹션이 있으면 확장.

예:

asset_generation:
  primary_en_native_strategy: DIRECT_WORD
  fallback_en_native_strategy: CONTEXTUAL_WORD
  default_blending_strategy: DIRECT_SEQUENCE

코드 상수와 config가 중복 source of truth가 되지 않도록 한다.

가능하면 config를 source of truth로 하고
코드는 config를 읽는다.

기존 DEFAULT_BLENDING_STRATEGY 상수가 있다면
하위 호환/기본값 역할로 제한하거나 정리.

대규모 refactor 금지.

---

# 21. assets-review 상태 기록

사람 결정이 DB에 아직 반영되지 않았다면
기존:

assets-review --set
assets-review --set-tone

기능을 사용하거나 내부 함수를 재사용하여
정확히 기록한다.

새 review system을 만들지 않는다.

최종 보고에 실제 반영된 상태를 출력.

---

# 22. Full Generation dry-run

이번 단계에서:

research assets --full-dry-run

같은 신규 명령을 꼭 만들 필요는 없다.

기존:

research assets --dry-run

이 Full Generation Plan을 출력하도록
안전하게 확장할 수 있는지 조사.

기존 dry-run 의미를 깨지 않는다.

최소 출력:

Production Plan ID

total source assets

REUSE count

GENERATE count

BLOCKED count

expected Gemini API calls

EN_NATIVE selected strategy breakdown

phoneme strategy breakdown

approved reuse count

pending-after-generation 예상 count

---

# 23. 실제 API 호출

이번 12-4의 목표는 정책 확정.

새 Gemini TTS 호출은 원칙적으로:

0

이어야 한다.

이미 사람 검토할 샘플은 충분히 있다.

불필요한 sample 생성 금지.

YouTube API:
0

---

# 24. Integrity Check 신규/강화

기존 30개 Check 이름/의미 유지.

최소 다음 목적을 추가/강화:

## en_native_primary_fallback_policy_safe

primary=DIRECT_WORD
fallback=CONTEXTUAL_WORD
정책 유효성.

## failed_variant_not_selected

REJECTED/REGENERATE_REQUIRED가
active generation/reuse selection에 포함되지 않음.

## approved_fallback_selection_safe

primary 실패 시 approved fallback을 선택함.

## representative_review_gate_safe

필수 대표 샘플의 사람 승인 상태 확인.

## full_generation_plan_complete

모든 required speech source가
REUSE/GENERATE/SKIP/BLOCKED 중 정확히 하나를 가짐.

## full_generation_api_estimate_safe

expected call count가 실제 계획과 일치.

Ready for Full Generation을 점수로 덮어쓰지 않는다.

---

# 25. 현재 실데이터 Acceptance

현재 실제 Production Plan 기준:

EN_NATIVE unique:
BAG
BAT
MAP
CAP

실제 DB를 source of truth로 사용.

기대:

BAG
→ approved DIRECT 있으면 REUSE DIRECT

MAP
→ approved DIRECT 있으면 REUSE DIRECT

CAP
→ DIRECT failed
→ approved CONTEXTUAL
→ REUSE CONTEXTUAL

BAT
→ approved DIRECT가 있는지 실제 DB 확인
→ 없으면 GENERATE DIRECT

CAP 때문에
DIRECT_WORD 전체 전략을 버리면 안 된다.

---

# 26. Human Review 결정 반영

이번 작업에서 다음 사람 판단을 정책 source로 반영:

- /b/ 승인
- /g/ 승인
- DIRECT_SEQUENCE 승인
- CAP CONTEXTUAL_WORD 승인
- MAP DIRECT_WORD 승인
- BAG DIRECT_WORD 승인

톤 측면:

CAP CONTEXTUAL:
승인 가능

MAP/BAG CONTEXTUAL:
primary로 선호하지 않음

LOWERCASE/MINIMAL:
기본 정책 미선택

사람 결정과 코드 정책이 일치해야 한다.

---

# 27. 테스트

최소 다음 CASE:

CASE A
primary strategy DIRECT_WORD

CASE B
fallback CONTEXTUAL_WORD

CASE C
default blend DIRECT_SEQUENCE

CASE D
DIRECT approved → DIRECT selected

CASE E
DIRECT REGENERATE_REQUIRED + CONTEXTUAL approved
→ CONTEXTUAL selected

CASE F
DIRECT REJECTED + CONTEXTUAL approved
→ CONTEXTUAL selected

CASE G
DIRECT pending + contextual approved의 우선순위 정책 명확

CASE H
DIRECT failed + contextual pending
→ approved fallback으로 간주 금지

CASE I
LOWERCASE approved여도 현재 fallback chain에서 자동 선택 안 함

CASE J
MINIMAL_CONTEXT 자동 선택 안 함

CASE K
REGENERATE_REQUIRED asset cache active selection 금지

CASE L
CAP 하드코딩 없음

CASE M
BAG/MAP/CAP 일반화 selection

CASE N
review state variant 간 전이 금지

CASE O
approved DIRECT cache reuse

CASE P
approved CONTEXTUAL fallback cache reuse

CASE Q
FULL plan 모든 required source 포함

CASE R
REUSE/GNERATE count 계산 정확
(오타 없이 실제 taxonomy 사용)

CASE S
expected API calls = GENERATE count 중 실제 TTS 대상

CASE T
Dry Run API 0

CASE U
Ready for Full Generation false when representative approval missing

CASE V
Ready for Full Generation true when representative approvals complete

CASE W
Ready for Rendering still false before FULL

CASE X
Production Plan unchanged

CASE Y
PAUSE 3000ms unchanged

CASE Z
viewer_action unchanged

CASE AA
existing review history preserved

CASE AB
previous 30 integrity checks regression 없음

CASE AC
existing CLI compatibility

CASE AD
전체 test regression 없음

---

# 28. 실제 DB 검증

구현 완료 후 실제 DB를 읽어
다음 상태를 출력:

- BAG active strategy
- BAT active/planned strategy
- MAP active strategy
- CAP active strategy
- CAP failed variant
- CAP fallback selected reason
- default blending strategy
- representative review statuses

실제 DB 상태와 다르면
보고서가 기대값을 가장하지 않는다.

---

# 29. Dry Run 실제 실행

테스트 완료 후:

python -m research.cli assets --dry-run

또는 실제 구현한 동일 목적 명령 실행.

Gemini API:
0

반드시 확인:

Ready for Full Generation

REUSE

GENERATE

expected API calls

strategy selection

---

# 30. 아직 FULL 실행하지 않는다

이번 작업 종료 시:

Ready for Full Generation:
YES

가 나와도

python -m research.cli assets

FULL 실행은 하지 않는다.

사람에게:

"FULL 생성 계획과 예상 API 호출 수"

를 먼저 보여준다.

사용자가 다음 단계에서 명시적으로 진행한 뒤
실제 생성.

---

# 31. 완료 보고 형식

반드시 한글로:

1. 수정/추가 파일
2. 최종 EN_NATIVE primary strategy
3. 최종 EN_NATIVE fallback strategy
4. 최종 blending default
5. CONTEXT_RESTRICTED 상태
6. LOWERCASE_WORD 상태
7. MINIMAL_CONTEXT_WORD 상태
8. Strategy selection algorithm
9. Review status 우선순위
10. failed variant 처리
11. CAP DIRECT 상태
12. CAP CONTEXTUAL 상태
13. CAP active strategy
14. BAG active strategy
15. MAP active strategy
16. BAT planned/active strategy
17. 사람 승인 상태 DB 반영 결과
18. pronunciation_review/tone review 정책
19. representative review gate
20. config source-of-truth 구조
21. cache reuse 정책
22. legacy cache 안전성
23. FULL generation plan 구조
24. REUSE count
25. GENERATE count
26. BLOCKED count
27. 예상 Gemini TTS API 호출 수
28. EN_NATIVE 전략별 planned count
29. phoneme generation 계획
30. blending generation 계획
31. 신규 Integrity Check
32. 전체 Integrity Check 결과
33. Ready for Full Generation YES/NO
34. Ready for Rendering YES/NO
35. PAUSE 3000ms 보존
36. viewer_action 보존
37. Production Plan 불변
38. 신규 테스트 수
39. 전체 테스트 수
40. 05~12-3 회귀 여부
41. CLI 하위 호환
42. 이번 단계 실제 Gemini API 호출 수
43. YouTube API 호출 수
44. Full Generation 실제 실행 여부
45. 다음 FULL 실행 시 예상 비용/호출 규모
46. 발견된 제한사항

---

# 32. 성공 기준

12-4 성공 기준:

- primary DIRECT_WORD 확정
- fallback CONTEXTUAL_WORD 확정
- default blending DIRECT_SEQUENCE 확정
- 사람 승인 결과가 DB에 반영
- 실패 DIRECT variant가 active selection에서 제외
- approved fallback이 정확히 선택
- experimental strategies가 자동 선택되지 않음
- representative review gate 충족
- Full Generation Plan 완전
- 예상 API 호출 수 계산 가능
- Ready for Full Generation = YES
- Ready for Rendering = NO
- 실제 FULL TTS 호출 = 0
- Production Plan 불변
- 전체 테스트 pass

이 조건이 충족되면 12-4 완료로 판정한다.

그 다음 단계에서만 실제 FULL Asset Generation을 실행한다.