# 12-6. FULL Asset Generation 및 검증

## 0. 이번 작업의 목적

12-5까지 Verified Asset Generator의 구조 교정과 FULL Generation Plan 검증이 완료되었다.

현재 확인된 상태:

- Production Plan ID: 7
- Source Speech Asset 수: 44
- Generation Unit 수: 51
- REUSE: 10
- GENERATE: 41
- BLOCKED: 0
- expected_base_api_calls: 41
- retries_included: false
- Ready for Full Generation: YES
- Ready for Rendering: NO
- FULL EXECUTED: NO

이번 12-6의 목적은 새로운 설계 변경이 아니다.

**12-5에서 확정된 Full Generation Plan을 그대로 실제 실행하여 필요한 TTS Asset을 생성하고, 생성 결과의 기술적 무결성·cache·lineage·manifest·human pronunciation review 상태를 검증하는 것**이 목적이다.

이번 단계에서는 실제 Gemini TTS API 호출을 허용한다.

단, API 호출 수를 불필요하게 늘리지 말고 기존 승인/생성된 asset은 반드시 cache/reuse한다.

---

# 1. 절대 원칙

이번 작업에서 다음을 반드시 지킨다.

1. 05~11 Production Pipeline의 데이터/로직을 수정하지 않는다.
2. Production Plan의 내용을 수정하지 않는다.
3. Production Block을 수정하지 않는다.
4. Speech Asset의 source_text를 수정하지 않는다.
5. PAUSE 3000ms를 수정하지 않는다.
6. viewer_action을 수정하지 않는다.
7. 이미 APPROVED된 pronunciation review를 임의로 변경하지 않는다.
8. REGENERATE_REQUIRED asset을 정상 asset처럼 재사용하지 않는다.
9. LOWERCASE_WORD / MINIMAL_CONTEXT_WORD를 자동 선택하지 않는다.
10. CONTEXT_RESTRICTED를 기본 blending 전략으로 사용하지 않는다.
11. 발음 품질을 자동 APPROVED 처리하지 않는다.
12. 파일이 생성됐다는 이유만으로 Ready for Rendering=YES로 만들지 않는다.
13. API 호출 수를 맞추기 위해 cache/reuse 판단을 왜곡하지 않는다.
14. 실패를 숨기거나 자동으로 성공 처리하지 않는다.
15. FULL 실행 전에 반드시 다시 DRY_RUN을 수행한다.

---

# 2. 현재 확정 정책

현재 정책을 변경하지 않는다.

## EN_NATIVE

Primary:

DIRECT_WORD

Fallback:

CONTEXTUAL_WORD

현재 알려진 선택:

BAG
- DIRECT_WORD
- PRIMARY_APPROVED
- REUSE

MAP
- DIRECT_WORD
- PRIMARY_APPROVED
- REUSE

CAP
- DIRECT_WORD = REGENERATE_REQUIRED
- CONTEXTUAL_WORD = APPROVED pronunciation
- CONTEXTUAL_WORD = APPROVED tone
- active strategy = CONTEXTUAL_WORD
- FALLBACK_AFTER_PRIMARY_FAILURE
- REUSE

BAT
- 기존 생성 이력 없음
- planned strategy = DIRECT_WORD
- action = GENERATE

CAP의 실패한 DIRECT_WORD를 다시 생성하지 않는다.

CAP은 승인된 CONTEXTUAL_WORD를 재사용해야 한다.

---

# 3. Blending 정책

Default:

DIRECT_SEQUENCE

현재 승인 상태:

SP013::DIRECT_SEQUENCE = APPROVED

CONTEXT_RESTRICTED는 실험적 옵션으로만 보존한다.

자동 선택하지 않는다.

현재 계획:

BAG blended
- DIRECT_SEQUENCE
- REUSE

BAT blended
- DIRECT_SEQUENCE
- GENERATE

MAP blended
- DIRECT_SEQUENCE
- GENERATE

---

# 4. FULL 실행 전 Preflight

실제 Gemini TTS를 호출하기 전에 반드시 다음을 확인한다.

실행:

python -m research.cli assets --dry-run --plan-id 7

다음을 보고한다.

- Source Speech Asset count
- Generation Unit count
- REUSE
- GENERATE
- BLOCKED
- expected_base_api_calls
- Representative Review Gate
- Ready for Full Generation

예상 기준:

Source Speech Assets = 44

Generation Units = 51

REUSE = 10

GENERATE = 41

BLOCKED = 0

expected_base_api_calls = 41

Ready for Full Generation = YES

숫자가 달라졌다면 즉시 FULL을 실행하지 않는다.

먼저 왜 달라졌는지 조사한다.

단, 기존 cache 상태가 추가되어 GENERATE가 감소한 경우는 정상일 수 있다.

이 경우 어떤 asset이 새롭게 REUSE로 전환됐는지 명확히 보고한다.

---

# 5. Generation Unit을 authoritative 단위로 사용

FULL 실행의 최소 단위는 Source Speech Asset이 아니라 Generation Unit이다.

예:

SP001

이 하나의 Source Speech Asset이

SP001-1
SP001-2
SP001-3
SP001-4

처럼 여러 Generation Unit으로 나뉠 수 있다.

FULL 실행에서도 반드시 12-5의

build_generation_units()

결과를 사용한다.

SAMPLE과 FULL이 서로 다른 segmentation 계산을 해서는 안 된다.

---

# 6. KO_NARRATION FULL Segmentation

KO_NARRATION은 12-1에서 확정한 sentence-boundary segmentation을 그대로 사용한다.

새 segmentation 알고리즘을 만들지 않는다.

설정:

max_segment_seconds = 12

현재 실데이터 기준:

KO_NARRATION Source Assets = 31

KO_NARRATION Generation Units = 38

현재 예상:

REUSE = 3

GENERATE = 35

기존 SAMPLE에서 생성된 segment가 있다면 재사용한다.

특히 기존에 확인된:

SP001-1
SP001-2

는 cache identity가 일치하면 REUSE되어야 한다.

SP001-3
SP001-4

등 아직 생성되지 않은 unit만 GENERATE한다.

---

# 7. Segment Lineage

모든 segmented asset은 metadata_json에 최소 다음 정보를 보존한다.

- segment_index
- segment_count
- source_block_ids
- source_speech_asset_id
- tts_prompt_version
- delivery_language
- delivery_role
- review_priority

source_text lineage가 끊기면 안 된다.

---

# 8. 실제 FULL Generation 실행

Preflight가 정상일 때만 실제 FULL을 실행한다.

프로젝트의 현재 CLI가 요구하는 정확한 FULL 실행 명령을 먼저 코드에서 확인한다.

임의로 CLI 옵션을 추측하지 않는다.

예를 들어 현재 구현이 다음 형태라면:

python -m research.cli assets --full --plan-id 7

그 명령을 사용한다.

실제 cli.py parser를 확인하여 정확한 명령만 실행한다.

---

# 9. API 호출 정책

이번 단계에서는 실제 Gemini TTS API 호출을 허용한다.

현재 예상 기본 호출:

41회

단:

expected_base_api_calls에는 retry가 포함되지 않는다.

따라서 실제 API 호출은 일시적인 5xx/timeout/empty response가 발생하면 41회를 초과할 수 있다.

반드시 다음을 구분해서 기록한다.

- base generation calls
- retry calls
- total Gemini TTS calls
- cache reuse count
- failed calls

호출 횟수를 41에 억지로 맞추지 않는다.

---

# 10. Retry 정책

기존 retry 정책을 그대로 사용한다.

새 retry 로직을 만들지 않는다.

retry 대상은 기존 정책에 정의된 일시적 실패만 허용한다.

예:

- 5xx
- timeout
- empty response

발음이 마음에 들지 않는다는 이유로 자동 retry하지 않는다.

발음 품질 문제는 Human Review 영역이다.

---

# 11. 생성 즉시 Technical Validation

각 실제 생성 WAV에 대해 최소 다음을 검증한다.

- 파일 존재
- file size > 0
- WAV decode 가능
- duration > 0
- sample rate 확인
- channel count 확인
- checksum 기록
- DB status 정상
- manifest 연결 정상

기술 검증 실패 asset은 AVAILABLE로 처리하지 않는다.

---

# 12. EN_NATIVE 생성 검증

이번 FULL에서 새로 생성될 가능성이 높은 EN_NATIVE:

BAT

BAT은 primary strategy:

DIRECT_WORD

로 생성한다.

BAT에 문제가 생겼다는 증거가 없는 상태에서 CONTEXTUAL_WORD로 자동 fallback하지 않는다.

DIRECT_WORD 생성 성공 후:

pronunciation_review = PENDING

으로 남긴다.

자동 APPROVED 금지.

---

# 13. EN_PHONEME_DEMO 생성 검증

현재 예상 신규 isolated phoneme:

/t/
/m/
/p/

현재 예상 신규 blended:

BAT blend
MAP blend

기본 blending strategy:

DIRECT_SEQUENCE

모두 생성 후:

pronunciation_review = PENDING

으로 둔다.

기존 승인 asset:

/b/
/g/
/æ/
BAG DIRECT_SEQUENCE

는 불필요하게 재생성하지 않는다.

---

# 14. Human Review Priority

기존 정책을 그대로 적용한다.

특히 교육 정확성에 직접 영향을 주는 asset은 HIGH priority로 유지한다.

신규 생성 후 사람이 실제로 들어야 하는 asset을 별도 목록으로 만든다.

최소 다음 그룹으로 나눈다.

## A. EN_NATIVE

예:

BAT

검토:

- 단어로 정확히 들리는가?
- 철자를 읽는 것처럼 들리지 않는가?
- BAG/MAP/CAP과 화자 톤이 크게 다르지 않은가?
- 왕초보 학습자가 듣기에 명료한가?

## B. Isolated Phoneme

예:

/t/
/m/
/p/

검토:

- letter name이 아니라 실제 target sound인가?
- 불필요한 모음이 과도하게 붙지 않는가?
- 왕초보 설명용으로 충분히 명료한가?

## C. Blending

예:

/b-æ-t/
/m-æ-p/

검토:

- 각 음소가 들리는가?
- 마지막에 자연스럽게 blend되는가?
- 너무 빠르지 않은가?
- 초보 학습자가 결합 과정을 따라갈 수 있는가?

---

# 15. KO_NARRATION Review

KO_NARRATION은 기존 정책상 pronunciation review 자동 승인 대상이 아니다.

하지만 다음 technical/content sanity check는 한다.

- segment가 문장 중간에서 비정상적으로 잘리지 않았는가?
- punctuation-only segment가 없는가?
- 빈 segment가 없는가?
- 동일 문장이 중복 생성되지 않았는가?
- source lineage가 올바른가?
- segment 순서가 유지되는가?

임의로 narration 문장을 고치지 않는다.

문장 자체 문제를 발견하면 생성 단계에서 수정하지 말고 보고만 한다.

---

# 16. Cache 검증

FULL 완료 후 다음을 검증한다.

같은 Generation Unit + 같은:

- model
- voice
- speech_mode
- source/segment text
- delivery instruction
- prompt version
- pronunciation strategy
- phoneme strategy

조합은 동일 cache identity를 가져야 한다.

REGENERATE_REQUIRED / REJECTED asset은 cache에서 정상 reusable asset으로 선택되면 안 된다.

---

# 17. CAP Regression Check

이번 FULL에서 반드시 확인한다.

CAP:

SP039 DIRECT_WORD

상태:

REGENERATE_REQUIRED

이 asset을 재생성하거나 active asset으로 선택하면 실패다.

반드시 기존 승인된:

SP039::CONTEXTUAL_WORD

를 재사용해야 한다.

selection_reason:

FALLBACK_AFTER_PRIMARY_FAILURE

가 유지되어야 한다.

---

# 18. Experimental Strategy Regression Check

다음 전략은 FULL에서 자동 선택되면 안 된다.

- LOWERCASE_WORD
- MINIMAL_CONTEXT_WORD
- CONTEXT_RESTRICTED

실험 이력은 DB에 남겨도 된다.

하지만 production active strategy가 되어서는 안 된다.

---

# 19. Manifest 완성

FULL 완료 후 manifest가 모든 required Generation Unit을 표현하는지 검증한다.

각 unit에 최소 다음 정보가 추적 가능해야 한다.

- source_speech_asset_id
- generated asset id
- content block
- speech mode
- voice
- strategy
- status
- file path
- duration
- checksum
- review status
- lineage

누락 unit이 있으면 Ready for Rendering=NO.

---

# 20. FULL Completion 정의

FULL Generation이 성공했다는 것은:

모든 required Generation Unit이

AVAILABLE 또는 REUSED

상태라는 뜻이다.

단 이것은 Rendering Ready와 다르다.

FULL asset generation 완료와 Human Pronunciation Approval을 분리한다.

---

# 21. Ready for Rendering Gate

Ready for Rendering은 다음을 모두 만족해야 한다.

1. 모든 required Generation Unit 존재
2. technical validation pass
3. BLOCKED = 0
4. FAILED = 0
5. required HIGH-priority pronunciation review 완료
6. required EN_NATIVE pronunciation review 완료
7. Mini Success EN_NATIVE는 필요한 tone review까지 완료
8. required blending review 완료
9. manifest complete
10. Production Plan integrity 유지

사람이 아직 듣지 않은 신규 발음 asset이 있다면:

Ready for Rendering = NO

가 정상이다.

절대 자동 YES 처리하지 않는다.

---

# 22. FULL 직후 기대 상태

이번 FULL 실행 직후에는 신규 EN_NATIVE/phoneme/blending asset이 PENDING일 가능성이 높다.

따라서 정상적인 예상 상태는:

FULL Generation = completed

하지만:

Ready for Rendering = NO

일 가능성이 높다.

이것을 실패로 간주하지 않는다.

그 다음 사람이 실제 sample을 듣고 승인하는 단계가 필요하다.

---

# 23. Human Listening Package

FULL 완료 후 사람이 검토해야 하는 신규 asset만 추려서 명확하게 출력한다.

형식:

Asset ID
Speech Mode
Target
Strategy
File
Duration
Review Priority
Pronunciation Review
Tone Review

예:

SPxxx
EN_NATIVE
BAT
DIRECT_WORD
assets/generated/plan_7/audio/...
1.xx sec
MEDIUM/HIGH
PENDING
PENDING 또는 NOT_REQUIRED

각 파일의 실제 경로를 반드시 표시한다.

---

# 24. assets-review 사용 안내

Human Review 대상과 함께 현재 프로젝트에서 실제 지원되는 assets-review 명령을 출력한다.

cli.py를 확인하고 정확한 syntax만 사용한다.

예:

python -m research.cli assets-review --plan-id 7

승인 syntax 역시 현재 구현을 확인한 뒤 실제 명령을 출력한다.

추측하지 않는다.

---

# 25. Integrity Check 확장

기존 43개 Integrity Check 이름을 삭제하거나 약화하지 않는다.

이번 단계에서 실제 FULL 결과 검증에 필요한 check를 추가한다.

최소 다음 개념을 검증한다.

### full_generation_executed_safe

FULL run이 실제 존재하고 completed 상태인지 확인.

### all_generation_units_materialized

모든 required Generation Unit이 AVAILABLE/REUSED인지 확인.

### generated_audio_technical_validation_safe

모든 실제 생성 WAV가 technical validation을 통과했는지 확인.

### full_manifest_complete

모든 required Generation Unit이 manifest에 존재하는지 확인.

### full_review_state_honest

사람이 검토하지 않은 pronunciation asset이 자동 APPROVED되지 않았는지 확인.

### failed_or_rejected_asset_not_reused

REJECTED/REGENERATE_REQUIRED asset이 production asset으로 재사용되지 않았는지 확인.

### active_strategy_matches_full_plan

실제 생성/재사용된 EN_NATIVE 및 blending 전략이 Full Generation Plan과 일치하는지 확인.

### full_api_call_accounting_safe

base/retry/total API call accounting이 실제 실행과 일치하는지 확인.

기존 구조에 이미 동등한 check가 있으면 중복 구현하지 말고 재사용한다.

---

# 26. 테스트

실제 Gemini API를 호출하는 테스트를 만들지 않는다.

pytest는 mock/fake client를 사용한다.

최소 다음을 검증한다.

CASE A
FULL에서 KO_NARRATION이 Generation Unit 단위로 실행된다.

CASE B
기존 segment cache가 있으면 재사용한다.

CASE C
없는 segment만 실제 synthesize 대상으로 간다.

CASE D
CAP은 CONTEXTUAL_WORD 승인 variant를 재사용한다.

CASE E
CAP DIRECT_WORD REGENERATE_REQUIRED는 호출하지 않는다.

CASE F
BAG/MAP은 승인된 DIRECT_WORD를 재사용한다.

CASE G
BAT은 DIRECT_WORD로 신규 생성된다.

CASE H
LOWERCASE_WORD 자동 선택 없음.

CASE I
MINIMAL_CONTEXT_WORD 자동 선택 없음.

CASE J
CONTEXT_RESTRICTED 자동 선택 없음.

CASE K
DIRECT_SEQUENCE가 blending default다.

CASE L
신규 phoneme은 자동 APPROVED되지 않는다.

CASE M
신규 EN_NATIVE도 자동 APPROVED되지 않는다.

CASE N
technical validation 실패 asset은 AVAILABLE 처리되지 않는다.

CASE O
FULL manifest에 모든 generation unit이 포함된다.

CASE P
retry가 발생하면 base와 retry가 분리 집계된다.

CASE Q
FULL 완료 후 review pending이면 Ready for Rendering=NO.

CASE R
필수 review 승인 후에만 Ready for Rendering 조건이 충족된다.

CASE S
Production Plan은 변경되지 않는다.

CASE T
PAUSE 3000ms 유지.

CASE U
viewer_action 유지.

필요한 회귀 테스트를 추가한다.

---

# 27. 실제 실행 후 두 번째 실행 검증

첫 FULL이 기술적으로 완료된 뒤, 비용을 발생시키지 않는 범위에서 cache/reuse plan을 다시 계산한다.

가능하면:

python -m research.cli assets --dry-run --plan-id 7

을 다시 실행한다.

이때 이미 생성된 모든 정상 asset이 cache/reuse 대상으로 인식되는지 확인한다.

중요:

Human Review PENDING 때문에 asset 파일 자체를 다시 생성해서는 안 된다.

PENDING은 "다시 TTS 생성"이 아니라 "사람이 들어야 함"을 의미한다.

따라서 FULL 직후 두 번째 DRY_RUN에서 기술적으로 정상 생성된 asset을 또 GENERATE 대상으로 잡는다면 cache/gate 설계를 조사한다.

---

# 28. API 비용 안전장치

FULL 실행 도중 예상보다 API 호출이 급격히 증가하면 무작정 계속하지 않는다.

특히 다음 상황을 감시한다.

- 동일 Generation Unit 반복 호출
- cache miss 반복
- 같은 asset retry 무한 반복
- segmentation unit 중복
- failed primary와 approved fallback 동시 생성
- experimental strategy까지 자동 생성

이 중 하나라도 발견되면 중단하고 원인을 조사한다.

---

# 29. 기존 데이터 불변성

작업 전후 다음 row count와 핵심 값을 비교한다.

최소:

- video_scripts
- video_directions
- block_directions
- production_plans
- production_blocks
- speech_assets

Asset generation 관련 테이블의 신규 row 증가는 정상이다.

하지만 05~11 산출물은 수정되면 안 된다.

---

# 30. 실제 생성 파일 위치

FULL 완료 후 실제 생성된 asset root를 보고한다.

예:

assets/generated/plan_7/audio/

manifest:

assets/generated/plan_7/manifest/manifest.json

실제 코드가 다른 경로를 사용하면 실제 경로를 보고한다.

추측하지 않는다.

---

# 31. 이번 단계에서 하지 말 것

다음은 하지 않는다.

- Renderer 구현
- FFmpeg 영상 합성
- Caption rendering
- Motion graphic 생성
- Thumbnail 생성
- YouTube upload
- 새로운 Script 생성
- 새로운 Production Plan 생성
- Gemini text generation
- YouTube API 호출
- TTS voice 변경
- Charon 변경
- Zephyr 실험
- 새로운 EN_NATIVE 전략 개발
- 새로운 blending 전략 개발
- pronunciation 자동 판정 모델 개발

이번 단계는 오직:

**FULL Asset Generation + Technical Validation + Human Review 준비**

까지다.

---

# 32. 성공 기준

다음을 만족해야 12-6 구현 완료로 본다.

- FULL 실행 전 DRY_RUN 정상
- Ready for Full Generation = YES 확인
- Full Generation Plan 실제 소비
- Generation Unit 기준 FULL 실행
- KO_NARRATION segmentation 실제 적용
- 기존 segment cache 재사용
- BAG/MAP DIRECT_WORD 재사용
- CAP CONTEXTUAL_WORD 재사용
- CAP 실패 DIRECT_WORD 재생성 없음
- BAT DIRECT_WORD 신규 생성
- DIRECT_SEQUENCE blending 유지
- experimental strategy 자동 선택 없음
- 신규 WAV technical validation
- segment lineage 보존
- manifest complete
- API call accounting 정확
- 신규 발음 asset 자동 APPROVED 없음
- Human Listening Required 목록 생성
- FULL Generation 완료 여부 명확
- Ready for Rendering을 정직하게 판정
- PAUSE 3000ms 불변
- viewer_action 불변
- Production Plan 불변
- 기존 테스트 회귀 없음
- 신규 테스트 pass

---

# 33. 최종 보고 형식

작업 완료 후 반드시 한글로 아래 순서대로 보고한다.

1. 수정/추가한 파일
2. FULL 실행 전 DRY_RUN 결과
3. 선택된 Production Plan ID
4. Source Speech Asset 수
5. Generation Unit 수
6. FULL 시작 시 REUSE 수
7. FULL 시작 시 GENERATE 수
8. FULL 시작 시 BLOCKED 수
9. expected_base_api_calls
10. 실제 base Gemini TTS 호출 수
11. 실제 retry 호출 수
12. 실제 총 Gemini TTS 호출 수
13. 생성 성공 수
14. cache reuse 수
15. 실패 수
16. KO_NARRATION Source Asset 수
17. KO_NARRATION Generation Unit 수
18. KO_NARRATION 실제 신규 생성 수
19. 기존 SAMPLE segment 재사용 결과
20. EN_NATIVE 생성/재사용 결과
21. BAG active strategy/result
22. MAP active strategy/result
23. CAP active strategy/result
24. BAT active strategy/result
25. CAP DIRECT_WORD가 재생성되지 않았는지
26. 신규 isolated phoneme 결과
27. 신규 blending 결과
28. blending default 확인
29. experimental strategy 자동 선택 여부
30. WAV technical validation 결과
31. segment lineage 결과
32. manifest 경로 및 completeness
33. pronunciation_review 상태 요약
34. tone_consistency_review 상태 요약
35. Human Listening Required 파일 전체 목록
36. 각 Human Review 파일의 실제 경로
37. FULL Generation 완료 여부
38. Ready for Rendering 여부
39. Ready for Rendering이 NO라면 정확한 blocker
40. FULL 후 재-DRY_RUN 결과
41. 남은 GENERATE 수
42. 남은 review PENDING 수
43. 신규 Integrity Check 목록
44. 전체 Integrity Check 결과
45. 신규 테스트 수
46. 전체 테스트 수
47. 기존 테스트 회귀 여부
48. PAUSE 3000ms 보존 여부
49. viewer_action 보존 여부
50. Production Plan 불변 여부
51. 05~11 DB row 불변 여부
52. YouTube API 호출 수
53. 실제 생성 asset root
54. manifest 실제 경로
55. 발견된 제한사항

API 호출 수와 실패/retry는 실제 결과 그대로 보고한다.

숫자를 예상값에 맞추지 않는다.

---

# 34. 가장 중요한 최종 원칙

이번 단계의 목표는

"모든 파일을 만들었으니 성공"

이 아니다.

목표는:

Production Plan
→ Generation Unit
→ Full Generation Plan
→ Gemini TTS
→ Technical Validation
→ Cache
→ Manifest
→ Human Pronunciation Review

이 lineage를 끊지 않고 실제 asset을 생성하는 것이다.

특히:

**생성 성공과 발음 승인은 서로 다른 상태다.**

Gemini TTS가 정상 WAV를 반환해도 발음이 교육용으로 적합하다는 뜻은 아니다.

신규 EN_NATIVE / EN_PHONEME_DEMO / Blending asset은 사람이 실제로 듣기 전까지 필요한 경우 PENDING으로 유지한다.

따라서 FULL Generation 직후:

Ready for Rendering = NO

가 나와도 정상일 수 있다.

사람이 필요한 신규 asset을 청취하고 승인한 뒤에만 Rendering Gate를 열도록 한다.