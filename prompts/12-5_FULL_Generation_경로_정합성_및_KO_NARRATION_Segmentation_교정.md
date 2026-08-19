# 12-5. FULL Generation 경로 정합성 및 KO_NARRATION Segmentation 교정

## 0. 이번 작업의 목적

12-4까지 다음 정책은 확정되었다.

- TTS Model: gemini-3.1-flash-tts-preview
- EDUCATION Voice: Charon
- EN_NATIVE Primary: DIRECT_WORD
- EN_NATIVE Fallback: CONTEXTUAL_WORD
- Blending Default: DIRECT_SEQUENCE
- LOWERCASE_WORD: 실험 전용
- MINIMAL_CONTEXT_WORD: 실험 전용
- CONTEXT_RESTRICTED: 실험/보조 전략
- Mini Success EN_NATIVE:
  - pronunciation review 필수
  - tone consistency review 필수
- CAP:
  - DIRECT_WORD = REGENERATE_REQUIRED
  - CONTEXTUAL_WORD = APPROVED / APPROVED
  - active variant = CONTEXTUAL_WORD
- BAG:
  - DIRECT_WORD = APPROVED
- MAP:
  - DIRECT_WORD = APPROVED
- /b/, /g/, BAG DIRECT_SEQUENCE:
  - APPROVED
- Representative Review Gate:
  - 완료
- Ready for Full Generation:
  - YES
- Ready for Rendering:
  - NO
- 실제 FULL Generation:
  - 아직 실행하지 않음

그러나 12-4 완료 보고에서 중요한 구조적 gap이 발견되었다.

12-1에서 구현한:

synthesize_ko_narration_segments()

및 KO_NARRATION 문장 경계 segmentation 로직이 SAMPLE 경로에는 연결되어 있지만,
FULL Generation 경로에는 연결되어 있지 않다.

현재 FULL 경로에서는 KO_NARRATION이 여전히 하나의 긴 Speech Asset 단위로
synthesize_asset()에 전달될 수 있다.

이 때문에:

1. SAMPLE과 FULL의 실제 생성 단위가 다르다.
2. Full Generation Plan의 예상 API 호출 수와 실제 호출 수가 달라질 수 있다.
3. segment별 cache/reuse가 FULL에서 제대로 활용되지 않을 수 있다.
4. segment lineage가 SAMPLE과 FULL에서 달라질 수 있다.
5. Renderer가 기대하는 세분화된 narration asset 구조와 실제 FULL 결과가 달라질 수 있다.
6. Dry Run의 API 예상치가 실제 FULL 비용 예측치로 신뢰하기 어렵다.

이번 12-5의 목적은 새로운 TTS 품질 실험이 아니다.

목적은 오직:

"SAMPLE / FULL / DRY_RUN이 동일한 Generation Unit 모델과 동일한 segmentation 정책을 사용하도록 생성 경로를 정합화하고, 실제 FULL 실행 전에 정확한 생성 계획과 API 호출 수를 계산할 수 있도록 만드는 것."

이다.


## 1. 절대 원칙

이번 단계에서는 기존에 확정된 발음/Voice/전략 정책을 변경하지 않는다.

특히 다음을 임의 수정하지 말 것.

- Gemini TTS model
- Charon
- Zephyr 정책
- DIRECT_WORD
- CONTEXTUAL_WORD
- LOWERCASE_WORD
- MINIMAL_CONTEXT_WORD
- DIRECT_SEQUENCE
- CONTEXT_RESTRICTED
- pronunciation_review 정책
- tone_consistency_review 정책
- review_priority 정책
- Mini Success HIGH priority 정책
- CAP fallback 결정
- BAG/MAP 승인 상태
- cache version 정책
- legacy cache fallback 정책
- TTS_PROMPT_VERSION
- Production Plan
- Production Blocks
- Speech Assets
- PAUSE 3000ms
- viewer_action
- 05~11 단계 데이터

이번 작업은 execution-path correction이다.

새로운 발음 전략 실험이 아니다.


## 2. 실제 Gemini TTS 호출 금지

이번 단계에서는 실제 Gemini TTS FULL 생성을 실행하지 않는다.

허용:

- DRY_RUN
- deterministic planning
- DB read
- cache inspection
- manifest planning
- Integrity Check
- pytest
- mock TTS tests

금지:

- 실제 FULL Gemini TTS 호출
- 새로운 SAMPLE TTS 호출
- 발음 비교용 실험 호출

이번 단계의 실제 Gemini TTS 신규 호출 수는 반드시:

0

이어야 한다.

YouTube API 역시:

0

이어야 한다.


## 3. 현재 구조 먼저 추적

코드를 수정하기 전에 반드시 현재 실제 호출 흐름을 추적해서 보고할 것.

최소한 다음 함수/경로를 확인한다.

- run_asset_generation
- build_asset_generation_report
- build_full_generation_plan
- synthesize_asset
- synthesize_ko_narration_segments
- SAMPLE path
- FULL path
- DRY_RUN path
- cache lookup path
- generated_assets persistence
- manifest generation

먼저 다음 질문에 답할 것.

Q1.
왜 SAMPLE에서는 KO_NARRATION segmentation이 적용되고 FULL에서는 적용되지 않는가?

Q2.
현재 FULL의 GENERATE count는 무엇을 세고 있는가?

- source speech asset?
- actual TTS request?
- generated asset row?
- renderer generation unit?

Q3.
현재 expected_api_calls=35는 실제 Gemini request 수와 동일한가?

동일하지 않다면 정확히 왜 다른지 lineage를 추적할 것.

추측하지 말고 코드로 확인한다.


## 4. Generation Unit 개념 도입

이번 단계에서 핵심 개념을 명확히 한다.

Speech Asset과 실제 TTS Generation Unit을 구분한다.

예:

SP001

원본 Speech Asset 하나가 있다고 하더라도 segmentation 결과가:

SP001-1
SP001-2
SP001-3

이라면 실제 TTS request 관점에서는:

3 Generation Units

이다.

따라서 다음 개념을 구분한다.

### Source Speech Asset

Production Planner가 만든 논리적 speech unit.

예:

SP001

### Generation Unit

실제 TTS API 호출/cache/reuse의 최소 단위.

예:

SP001::SEG01
SP001::SEG02
SP001::SEG03

실제 naming은 기존 코드와 하위 호환되는 방식을 우선 사용한다.

불필요하게 기존 asset ID 체계를 전면 변경하지 말 것.


## 5. 공통 Generation Unit Compiler

가능하면 SAMPLE/FULL 각각에서 segmentation을 따로 구현하지 말고,
공통 deterministic compiler를 만든다.

예시 개념:

build_generation_units(...)

또는 기존 구조에 더 자연스러운 이름을 사용해도 된다.

입력:

- Speech Asset
- speech_mode
- source_text
- Production Block lineage
- strategy
- config
- review/cache state

출력 개념:

[
    {
        "source_speech_asset_id": "SP001",
        "generation_unit_id": "SP001::SEG01",
        "segment_index": 1,
        "segment_count": 3,
        "speech_mode": "KO_NARRATION",
        "text": "...",
        "preferred_strategy": null,
        "source_block_ids": ["CB01"]
    }
]

EN_NATIVE처럼 segmentation이 필요 없는 asset은:

Speech Asset 1개 = Generation Unit 1개

가 되어야 한다.


## 6. KO_NARRATION segmentation 정책 보존

12-1에서 이미 구현하고 검증한 segmentation 정책을 재사용한다.

새로운 segmentation 알고리즘을 만들지 않는다.

현재 정책:

- 문장 경계 우선
- punctuation/whitespace-only fragment 제거
- 기존 duration estimation 재사용
- max_segment_seconds config 사용
- segment lineage 기록

현재 config:

asset_generation.max_segment_seconds: 12

를 그대로 사용한다.

12초는 Google 공식 품질 한계라는 의미가 아니다.

Renderer 제어성:

- caption sync
- keyword highlight
- partial regeneration
- asset granularity

을 위한 프로젝트 내부 정책이다.

이 의미를 유지한다.


## 7. SAMPLE/FULL 동일 segmentation

수정 후 다음이 성립해야 한다.

동일한 Production Plan + 동일 config + 동일 Speech Asset이면:

SAMPLE에서 생성되는 KO_NARRATION segmentation과
FULL에서 계획되는 KO_NARRATION segmentation이 동일해야 한다.

즉:

- segment_count
- segment_index
- segment text
- source_block_ids

가 mode에 따라 달라지면 안 된다.

SAMPLE은 전체 Generation Unit 중 일부만 실제 생성 대상으로 선택할 수 있지만,
Generation Unit 자체의 정의는 FULL과 동일해야 한다.


## 8. DRY_RUN도 동일 Generation Unit 모델 사용

DRY_RUN도 source Speech Asset 기준의 단순 cache miss 계산을 버리고,
실제 FULL이 사용할 Generation Unit 기준으로 계산해야 한다.

현재 12-4에서:

- naive cache misses expected = 38
- Full Generation Plan GENERATE = 35

처럼 서로 다른 숫자가 나왔다.

이번 단계 이후에는 사용자에게 보여주는 FULL 예상치는
반드시 실제 Generation Unit Plan을 기준으로 해야 한다.

구식 source-level 추정치를 유지해야 한다면:

legacy_source_level_estimate

처럼 명확히 참고값으로만 표시하고,

절대:

expected_api_calls

의 authoritative source로 사용하지 말 것.

가능하면 혼동되는 구식 표시 자체를 제거한다.

단, 기존 CLI 출력 하위 호환을 깨뜨릴 필요가 있다면
기존 필드를 유지하되 새 authoritative 필드를 별도로 둔다.


## 9. 정확한 API Call Estimate

다음 FULL 실행 시 예상 Gemini TTS 호출 수는:

action == GENERATE

인 Generation Unit 개수로 계산한다.

단 다음을 고려한다.

- approved cache REUSE → 0 call
- usable cache REUSE → 0 call
- GENERATE → 기본 1 call
- failed/rejected cache → reuse 금지
- EN_NATIVE fallback approved → failed primary 재생성하지 않고 fallback REUSE
- segmentation → segment마다 독립 call
- retry는 예상 기본 호출 수에 포함하지 않는다.

따라서 report에는 최소한:

- expected_base_api_calls
- retry_not_included

를 명시한다.

숫자는 실제 계산 결과를 사용하고 예시 숫자를 하드코딩하지 말 것.


## 10. Cache Key와 Segment Identity

KO_NARRATION segment cache는 서로 충돌하면 안 된다.

cache key가 최소한 다음 차원을 안전하게 반영하는지 확인한다.

- model
- voice
- speech_mode
- actual segment text
- delivery instruction
- prompt version
- relevant pronunciation strategy if applicable

segment_index 자체를 반드시 key에 넣어야 하는지는 기존 cache 철학에 따라 판단한다.

중요한 것은:

동일 텍스트 + 동일 TTS 조건이면 재사용 가능하고,
다른 segment text가 잘못 재사용되면 안 된다는 것이다.

불필요하게 segment index만 달라졌다고 동일 음성을 재생성하는 것도 피한다.


## 11. Segment Lineage 보존

12-1에서 기록하던:

- segment_index
- segment_count
- source_block_ids

를 FULL에서도 동일하게 유지한다.

추가로 가능하면:

- source_speech_asset_id
- generation_unit_id

관계를 manifest/report에서 명확히 볼 수 있도록 한다.

Production Plan 원본을 수정해서는 안 된다.

lineage는 Generated Asset / metadata / manifest 계층에서 관리한다.


## 12. Existing Generated Asset 호환성

기존 SAMPLE에서 생성된 segment asset이 있다.

예:

SP001의 일부 segment.

이것을 FULL에서 무조건 새로 생성하면 안 된다.

동일한:

- prompt version
- model
- voice
- text
- mode
- delivery instruction
- strategy

조건을 만족하는 기존 segment cache가 있다면 REUSE해야 한다.

기존 sample/full이라는 실행 mode 차이만으로 cache를 무효화하지 않는다.

TTS 결과가 동일해야 한다면 mode는 cache identity가 아니다.


## 13. EN_NATIVE 정책 절대 보존

12-4에서 확정된 다음 selection algorithm을 변경하지 않는다.

Primary:

DIRECT_WORD

Fallback:

CONTEXTUAL_WORD

규칙:

1. primary approved → primary
2. primary REJECTED/REGENERATE_REQUIRED + fallback approved → fallback
3. primary PENDING → fallback 자동 선택 금지
4. primary failure + fallback 미승인 → no approved variant / generation plan
5. LOWERCASE_WORD 자동 선택 금지
6. MINIMAL_CONTEXT_WORD 자동 선택 금지

특히 CAP:

DIRECT_WORD = REGENERATE_REQUIRED

CONTEXTUAL_WORD = APPROVED / APPROVED

이므로 FULL plan에서:

SP039::CONTEXTUAL_WORD

를 REUSE해야 한다.

실패한 SP039 DIRECT_WORD를 다시 생성하면 회귀다.


## 14. BAT 정책

BAT는 현재 EN_NATIVE 이력이 없다고 보고되었다.

따라서:

Primary = DIRECT_WORD

Generation Plan:

GENERATE

가 맞다.

CAP 한 단어에서 DIRECT_WORD가 실패했다고 해서
BAT까지 CONTEXTUAL_WORD로 바꾸지 않는다.

이 기존 12-4 정책을 보존한다.


## 15. Blending 정책 보존

Default:

DIRECT_SEQUENCE

보조:

CONTEXT_RESTRICTED

CONTEXT_RESTRICTED는 자동 fallback으로 사용하지 않는다.

LOWERCASE/MINIMAL_CONTEXT와 마찬가지로
실험 variant가 production default chain에 침투하면 안 된다.

BAG DIRECT_SEQUENCE approved cache가 있다면 REUSE.

BAT/MAP blending이 미생성이면 DIRECT_SEQUENCE로 GENERATE.


## 16. Review Gate와 Generation Gate 구분

Full Generation을 실행할 수 있다는 것과
생성된 모든 asset이 사람 승인되었다는 것은 다르다.

따라서 상태를 혼합하지 않는다.

### Ready for Full Generation

대표 샘플 검토가 완료되어
production strategy를 확정했고
나머지 asset을 생성해도 되는 상태.

### Ready for Rendering

FULL generation 완료 +
필수 review gate 충족 +
필수 asset available.

12-5에서는 실제 FULL을 실행하지 않으므로:

Ready for Rendering = NO

가 정상이다.

반면 구조가 정상이고 representative gate가 유지된다면:

Ready for Full Generation = YES

가 유지되어야 한다.


## 17. Full Generation Plan 확장

기존 build_full_generation_plan()을
실제 Generation Unit 기준으로 확장한다.

최소 출력 정보:

- source_speech_asset_id
- generation_unit_id
- speech_mode
- segment_index
- segment_count
- preferred_strategy
- selected_asset_id
- selection_reason
- action
- cache_status
- review_status
- source_block_ids
- estimated_api_calls

모든 field가 모든 mode에서 반드시 필요한 것은 아니며
해당되지 않는 값은 null/NOT_APPLICABLE 등 명확한 값으로 처리한다.


## 18. Plan Summary

리포트에는 다음 summary를 추가한다.

Source Speech Assets: N
Generation Units: M

REUSE: X
GENERATE: Y
BLOCKED: Z

Expected Gemini TTS Base Calls: Y
Retries Included: NO

그리고 speech_mode별:

KO_NARRATION
  source assets:
  generation units:
  reuse:
  generate:

EN_NATIVE
  source assets:
  generation units:
  reuse:
  generate:

EN_PHONEME_DEMO
  source assets:
  generation units:
  reuse:
  generate:

를 보여준다.


## 19. KO_NARRATION 상세 Summary

KO_NARRATION에 대해서는 별도 표 또는 섹션을 출력한다.

예:

SP001
  source duration estimate:
  segment count:
  segments:
    SEG01: ...
    SEG02: ...
    SEG03: ...
  REUSE:
  GENERATE:

모든 narration 전문을 리포트에 길게 출력할 필요는 없다.

segment text preview 정도로 제한해도 된다.


## 20. Integrity Check 추가

기존 36개 Integrity Check 이름과 의미를 변경하지 않는다.

다음 신규 check를 추가한다.

### 20-1. generation_unit_model_safe

모든 TTS 대상 Speech Asset이
최소 1개 이상의 Generation Unit으로 변환되는지 확인.

### 20-2. ko_segmentation_mode_consistent

동일 KO_NARRATION source에 대해
SAMPLE/FULL/DRY_RUN의 segmentation definition이 동일한지 확인.

### 20-3. generation_unit_lineage_safe

모든 segment가:

- source_speech_asset_id
- segment_index
- segment_count
- source_block_ids

를 잃지 않는지 확인.

### 20-4. full_api_estimate_generation_unit_based

expected API call count가 source asset count가 아니라
GENERATE Generation Unit count와 일치하는지 확인.

### 20-5. segment_cache_identity_safe

다른 segment text가 동일 cache identity로 잘못 충돌하지 않는지 확인.

### 20-6. full_reuses_existing_segments

기존 SAMPLE segment가 동일 조건이면
FULL에서 REUSE되는지 확인.

### 20-7. full_generation_path_uses_plan

FULL 실제 실행 루프가 독자적으로 전략/segmentation을 다시 결정하지 않고
Full Generation Plan의 Generation Unit/strategy/action을 실제 소비하는지 확인.

이 check가 중요하다.

12-4에서 EN_NATIVE fallback plan은 맞았지만
FULL 실행 루프가 별도로 DIRECT_WORD를 선택하던 실제 버그가 발견된 전례가 있다.

같은 구조적 문제가 KO_NARRATION에서 재발하면 안 된다.


## 21. Single Source of Truth

이번 교정 후 다음 구조를 목표로 한다.

Production Plan
      ↓
Generation Unit Compiler
      ↓
Full Generation Plan
      ↓
DRY_RUN / SAMPLE / FULL

DRY_RUN/SAMPLE/FULL이 각각:

- segmentation
- pronunciation strategy
- cache decision
- lineage

를 다시 독립적으로 계산하는 구조를 피한다.

모든 mode가 동일 plan/compiler를 소비하게 한다.

단, 프로젝트 기존 architecture를 과도하게 갈아엎지 말 것.

최소 수정으로 이 원칙을 달성한다.


## 22. SAMPLE Selection

SAMPLE은 전체 Generation Unit Plan 중
대표 asset만 선택해 생성하는 mode로 정의한다.

즉 SAMPLE 자체가 segmentation을 결정하면 안 된다.

먼저 공통 Generation Units가 만들어지고,
그중 sample matrix가 일부를 선택해야 한다.

기존 sample matrix의 의미와 대표성은 보존한다.


## 23. FULL Execution 준비 검증

이번 단계에서는 FULL을 실제 실행하지 않는다.

대신 mock client를 이용해:

mode=FULL

일 때 실제 실행 루프가 Full Generation Plan을 정확히 소비하는지 검증한다.

검증할 것:

- REUSE unit → TTS client 호출 없음
- GENERATE unit → TTS client 1회
- BLOCKED unit → TTS client 호출 없음
- CAP approved fallback → DIRECT_WORD 호출 없음
- segmented KO_NARRATION → segment별 호출
- 이미 존재하는 segment cache → 호출 없음


## 24. Retry Estimate

API estimate에는 retry를 포함하지 않는다.

이유:

실제 retry 수는 사전 예측 불가능하다.

따라서:

expected_base_api_calls

만 계산한다.

그리고 report에:

Actual calls may be higher if retryable Gemini TTS failures occur.

라는 의미를 명시한다.


## 25. DB 불변성

이번 작업 전후 다음 row count 및 기존 content를 확인한다.

- production_plans
- production_blocks
- speech_assets
- video_scripts
- video_directions
- block_directions

이번 단계에서 Production Plan 계층을 수정하면 안 된다.

generated_assets / asset_generation_runs는
DRY_RUN 기록 정책에 따라 변할 수 있으나
실제 TTS 생성 row를 새로 만들면 안 된다.

DRY_RUN이 기존 설계상 run row를 생성한다면 그것은 허용하되
Gemini TTS 호출은 0이어야 한다.


## 26. PAUSE / Viewer Action 회귀 방지

반드시 다시 확인한다.

CAP Mini Success:

PAUSE 3000ms

보존.

정답 발음은 pause 이후.

viewer_action 보존.

Production Planner가 만든 timeline을
Asset Generator가 수정하면 안 된다.


## 27. 기존 승인 상태 불변

다음 review 상태를 임의 변경하지 않는다.

최소한 현재 알려진:

- SP007 = APPROVED
- SP011 = APPROVED
- SP013::DIRECT_SEQUENCE = APPROVED
- SP003 = APPROVED
- SP029 = APPROVED
- SP039 DIRECT_WORD = REGENERATE_REQUIRED
- SP039::CONTEXTUAL_WORD pronunciation = APPROVED
- SP039::CONTEXTUAL_WORD tone = APPROVED

를 재기록하거나 덮어쓰지 않는다.

실제 DB 값이 다르면 보고하고 멋대로 수정하지 말 것.


## 28. 실제 DB Dry Run

코드/pytest 완료 후 실제 DB를 대상으로:

python -m research.cli assets --dry-run --plan-id 7

또는 현재 CLI의 정확한 syntax가 다르면
기존 syntax를 그대로 사용한다.

실행한다.

실제 TTS API 호출은 없어야 한다.

여기서 다음을 확인한다.

- Ready for Full Generation
- Ready for Rendering
- Source Speech Asset count
- Generation Unit count
- REUSE count
- GENERATE count
- BLOCKED count
- expected_base_api_calls
- KO_NARRATION source count
- KO_NARRATION segment count
- EN_NATIVE strategy distribution
- EN_PHONEME_DEMO strategy distribution
- Integrity Check 전체 결과


## 29. Ready for Full Generation 조건

다음이 모두 충족되어야 YES.

- representative review gate complete
- generation unit plan complete
- no unresolved BLOCKED required asset
- failed EN_NATIVE variant selected 없음
- CAP fallback 정확 선택
- experimental EN_NATIVE strategy 자동 선택 없음
- default blending strategy 적용
- segmentation integrity safe
- cache identity safe
- expected API calls 계산 가능
- Production Plan unchanged

실제 FULL generation 완료 여부는 이 Gate의 조건이 아니다.


## 30. Ready for Rendering

이번 단계에서는 반드시:

NO

가 정상이다.

FULL을 실행하지 않았기 때문이다.

코드를 억지로 YES로 만들지 않는다.


## 31. 테스트 요구사항

기존 전체 테스트를 모두 유지한다.

신규 테스트는 최소 다음 CASE를 포함한다.

CASE A
짧은 KO_NARRATION → Generation Unit 1개.

CASE B
긴 KO_NARRATION → 기존 12-1 정책에 따라 N개 segment.

CASE C
SAMPLE/FULL 동일 source → 동일 segmentation.

CASE D
DRY_RUN/FULL 동일 source → 동일 segmentation.

CASE E
segment_index 1..N 연속.

CASE F
segment_count 모든 segment에 동일.

CASE G
source_block_ids 보존.

CASE H
punctuation-only segment 없음.

CASE I
동일 segment cache 존재 → REUSE.

CASE J
다른 segment text → 잘못된 cache reuse 없음.

CASE K
FULL mock 실행 시 GENERATE segment마다 정확히 1회 호출.

CASE L
REUSE segment는 TTS 호출 0.

CASE M
expected_base_api_calls == GENERATE generation units.

CASE N
retry는 estimate에 포함되지 않음.

CASE O
CAP DIRECT_WORD REGENERATE_REQUIRED → 선택 금지.

CASE P
CAP CONTEXTUAL_WORD approved → fallback REUSE.

CASE Q
BAG DIRECT_WORD approved → primary REUSE.

CASE R
MAP DIRECT_WORD approved → primary REUSE.

CASE S
BAT history 없음 → DIRECT_WORD GENERATE.

CASE T
LOWERCASE_WORD 자동 선택 금지.

CASE U
MINIMAL_CONTEXT_WORD 자동 선택 금지.

CASE V
CONTEXT_RESTRICTED 자동 blending default 금지.

CASE W
DIRECT_SEQUENCE default 유지.

CASE X
FULL 실행 path가 plan의 preferred_strategy를 실제 사용.

CASE Y
FULL 실행 path가 plan의 generation units를 실제 사용.

CASE Z
SAMPLE path가 독자 segmentation을 하지 않음.

CASE AA
PAUSE 3000ms 불변.

CASE AB
viewer_action 불변.

CASE AC
Production Plan row/content 불변.

CASE AD
기존 review 상태 불변.

CASE AE
Dry Run Gemini TTS 호출 0.

CASE AF
기존 CLI 하위 호환.

필요하면 추가 테스트를 작성한다.


## 32. 기존 587개 테스트 회귀 금지

12-4 완료 시:

587 passed

였다.

이번 단계에서는:

기존 587개 전부 통과 + 신규 테스트 전부 통과

해야 한다.

기존 테스트를 삭제하거나 단순히 assertion을 약화시켜
통과시키지 말 것.

기존 테스트 수정이 정말 필요한 경우:

- 왜 기존 기대값이 구조적으로 잘못됐는지
- 어떤 의미 변화 때문인지

완료 보고에서 설명할 것.


## 33. 실제 FULL 실행 금지

매우 중요.

이번 작업 완료 후:

python -m research.cli assets --full ...

을 실행하지 않는다.

Ready for Full Generation이 YES가 되어도
실제 FULL 생성은 사용자 확인 후 별도 실행한다.

이번 단계는 FULL을 실행하기 위한 마지막 구조 검증 단계다.


## 34. 예상 호출 수 재계산

12-4에서는 약:

35 calls

로 추정했다.

그러나 이것은 KO_NARRATION segmentation이 FULL plan에 완전히 반영되기 전 수치다.

따라서 12-5에서는 이 숫자를 정답으로 가정하지 않는다.

실제 Generation Unit Plan을 만든 후 처음부터 다시 계산한다.

결과가:

- 35보다 많아도 정상일 수 있다.
- 35와 같아도 정상일 수 있다.
- 35보다 적다면 cache reuse 근거를 확인해야 한다.

숫자를 맞추기 위해 로직을 조정하지 말 것.


## 35. 실제 FULL 전 최종 사용자 확인용 Summary

리포트 마지막에 다음 섹션을 추가한다.

## FULL Generation Preview

Plan ID:
Format:
Voice:
TTS Model:

EN_NATIVE Primary:
EN_NATIVE Fallback:
Blending Default:

Source Speech Assets:
Actual Generation Units:

Already Reusable:
Need Generation:
Blocked:

Expected Gemini TTS Base Calls:
Retries Included:
Estimated Calls Are Generation-Unit Based: YES/NO

Representative Review Gate:
Ready for Full Generation:
Ready for Rendering:

FULL EXECUTED:

이번 단계에서는:

FULL EXECUTED: NO

여야 한다.


## 36. 수정 범위

가능하면 기존 파일을 확장한다.

우선:

- research/asset_generator.py
- research/cli.py
- config/research_config.yaml (정말 필요할 경우만)
- tests/test_asset_generator.py

새 파일은 꼭 필요한 경우에만 만든다.

12단계 이후 asset architecture가 이미
asset_generator.py 중심이므로
불필요하게 stage를 여러 파일로 쪼개지 않는다.


## 37. 완료 보고 형식

작업 완료 후 아래 번호를 그대로 사용해 한글로 보고한다.

1. 수정/추가한 파일
2. 기존 SAMPLE/FULL segmentation 경로 차이의 정확한 원인
3. 기존 expected API call 계산 방식
4. 왜 기존 35회가 authoritative하지 않았는지
5. Generation Unit 정의
6. 공통 Generation Unit Compiler 구조
7. SAMPLE 경로 변경 내용
8. FULL 경로 변경 내용
9. DRY_RUN 경로 변경 내용
10. KO_NARRATION segmentation 알고리즘 보존 여부
11. max_segment_seconds 값
12. Source Speech Asset 수
13. 실제 Generation Unit 수
14. KO_NARRATION Source Asset 수
15. KO_NARRATION Generation Unit 수
16. KO_NARRATION REUSE 수
17. KO_NARRATION GENERATE 수
18. EN_NATIVE Generation Unit 수
19. EN_NATIVE REUSE/GENERATE/BLOCKED 수
20. EN_PHONEME_DEMO Generation Unit 수
21. EN_PHONEME_DEMO REUSE/GENERATE/BLOCKED 수
22. 전체 REUSE 수
23. 전체 GENERATE 수
24. 전체 BLOCKED 수
25. 정확한 expected_base_api_calls
26. retry 포함 여부
27. 기존 SAMPLE segment cache 재사용 결과
28. segment cache identity 방식
29. segment lineage 보존 결과
30. CAP active strategy
31. BAG active strategy
32. MAP active strategy
33. BAT planned strategy
34. Blending default
35. 실험 전략 자동 선택 여부
36. 기존 review 상태 보존 여부
37. Representative Review Gate 결과
38. 신규 Integrity Check 목록
39. 전체 Integrity Check 결과
40. Ready for Full Generation
41. Ready for Rendering
42. FULL EXECUTED 여부
43. PAUSE 3000ms 보존 여부
44. viewer_action 보존 여부
45. Production Plan 불변 여부
46. 신규 테스트 수
47. 전체 테스트 수
48. 기존 587개 회귀 여부
49. CLI 하위 호환 여부
50. 실제 Gemini TTS 신규 호출 수
51. YouTube API 호출 수
52. 다음 FULL 실행 시 예상 기본 API 호출 수
53. 발견된 제한사항


## 38. 성공 기준

다음이 모두 충족되어야 12-5 완료다.

- SAMPLE/FULL/DRY_RUN이 공통 Generation Unit 모델 사용
- KO_NARRATION segmentation이 FULL에도 적용
- 기존 12-1 segmentation 정책 재사용
- source asset와 generation unit 구분
- FULL API estimate가 generation-unit 기준
- 기존 SAMPLE segment cache FULL에서 재사용 가능
- segment lineage 보존
- FULL execution이 Full Generation Plan을 실제 소비
- CAP approved fallback 재사용
- failed DIRECT CAP 재생성 금지
- BAG/MAP primary 유지
- BAT primary DIRECT_WORD 계획 유지
- 실험 EN_NATIVE 전략 자동 선택 없음
- DIRECT_SEQUENCE default 유지
- 기존 review 상태 불변
- Representative Review Gate 유지
- Ready for Full Generation = YES
- Ready for Rendering = NO
- FULL EXECUTED = NO
- 실제 Gemini TTS 신규 호출 = 0
- YouTube API 호출 = 0
- PAUSE/viewer_action 불변
- Production Plan 불변
- 기존 587개 테스트 회귀 없음
- 신규 테스트 전부 pass
- 다음 FULL 실행 예상 API 호출 수를 정확하게 산출 가능


## 39. 최종 원칙

이번 단계의 핵심은:

"FULL을 실행하는 것"이 아니라
"FULL을 실행하기 전에 실제 FULL이 무엇을 몇 번 생성할지를 정확하게 아는 것"

이다.

API 호출 수를 줄이기 위해 기능을 생략하지 말고,
반대로 기존 cache가 있는데 불필요하게 재생성하지도 말 것.

12-5 완료 후 결과를 사용자에게 보고하고 멈춘다.

실제 FULL Generation은 사용자 승인 후 다음 단계에서 실행한다.