# 12-3. EN_NATIVE 발음 및 톤 일관성 최적화

## 0. 작업 목적

12-2 실제 사람 청취 결과 EN_NATIVE 짧은 단어의 발음 안정화에는 성공했다.

실제 청취 결과:

1. SP039__CONTEXTUAL_WORD.wav
   target = CAP
   결과 = 좋음
   기존 SP039 DIRECT_WORD에서 "배그"처럼 잘못 들리던 문제가 해결됨.

2. SP029.wav
   target = MAP
   strategy = DIRECT_WORD
   결과 = 좋음.

3. SP029__CONTEXTUAL_WORD.wav
   target = MAP
   결과 = 좋음.
   DIRECT_WORD보다 조금 더 부드럽게 들림.
   다만 다른 음성과 비교하면 톤이 다른 것처럼 느껴짐.

4. SP003__CONTEXTUAL_WORD.wav
   target = BAG
   결과 = 좋음.
   역시 조금 더 부드럽지만 다른 음성과 톤 차이가 느껴짐.

따라서 현재 상태는:

- EN_NATIVE pronunciation 안정화: 성공
- CONTEXTUAL_WORD pronunciation: 사용 가능
- CAP 문제: 해결 가능성이 실제 샘플로 확인됨
- 하지만 CONTEXTUAL_WORD가 기존 Charon 음성과 톤/발화 성격을
  다르게 만드는 문제가 있음
- FULL Generation은 아직 실행하지 않는다

이번 단계의 핵심 질문은 하나다.

"CAP 발음이 좋아진 이유가 lowercase normalization 때문인가,
contextual pronunciation instruction 때문인가?"

그리고 최종 목표는:

"짧은 영어 단어를 정확히 발음시키면서도
영상 전체에서 Charon의 화자 톤을 최대한 일관되게 유지하는 것"

이다.

이번 단계는 원인 분리 A/B 테스트 + 최소 교정 단계다.

Renderer를 만들지 않는다.
FULL asset generation을 실행하지 않는다.

---

# 1. 가장 중요한 원칙

12-2 CONTEXTUAL_WORD는 동시에 두 변수를 변경했다.

기존 DIRECT_WORD:

source_text:
CAP

TTS transcript:
CAP

기존 voice/profile + 기존 prompt

12-2 CONTEXTUAL_WORD:

source_text:
CAP

TTS transcript:
cap

그리고 Director's Notes에 추가적인 pronunciation context를 넣음.

즉:

변수 A = uppercase → lowercase
변수 B = contextual pronunciation instruction

두 변수가 동시에 바뀌었다.

따라서 CAP이 정확해진 이유를 현재 데이터만으로는 알 수 없다.

이번 단계에서는 반드시 두 변수를 분리한다.

추측으로 어느 하나를 원인이라고 확정하지 않는다.

---

# 2. 이번 단계의 실험 전략

최소 다음 3개 전략을 명확히 구분한다.

## Strategy 1 — DIRECT_WORD

12-2 baseline 그대로.

예:

source_text:
CAP

tts_transcript:
CAP

기존 EN_NATIVE prompt/profile 사용.

기존 결과를 재사용할 수 있으면 API를 다시 호출하지 않는다.

---

## Strategy 2 — LOWERCASE_WORD

이번 단계의 핵심 신규 전략.

source_text:
CAP

tts_transcript:
cap

그러나:

Audio Profile
Scene
Director's Notes
delivery style

은 DIRECT_WORD와 가능한 한 동일하게 유지한다.

즉 CONTEXTUAL_WORD의 추가 pronunciation framing을 넣지 않는다.

목적:

"CAP → cap 소문자화만으로 단어 발음 문제가 해결되는가?"

를 확인한다.

중요:

source_text는 CAP 그대로 보존한다.

DB의 Speech Asset 원본을 변경하지 않는다.

---

## Strategy 3 — MINIMAL_CONTEXT_WORD

LOWERCASE_WORD와 동일하게:

source_text:
CAP
tts_transcript:
cap

을 사용한다.

단, pronunciation instruction만 최소한 추가한다.

의미:

"Pronounce the transcript as one English word.
Do not spell it."

정도의 최소 지시만 사용한다.

불필요한 style adjective를 넣지 않는다.

예를 들어 다음처럼 발화 성격을 바꿀 가능성이 있는 지시는
이번 전략에서 제거한다.

- warm
- friendly
- expressive
- conversational
- gentle
- smooth
- enthusiastic
- natural American English style
- teacher-like
- narrator-like

단, 기존 공통 Charon profile에 이미 존재하는 표현을
무조건 삭제하라는 뜻은 아니다.

핵심은 세 전략 사이에서 pronunciation 이외의 변수를
최대한 통제하는 것이다.

---

# 3. 기존 CONTEXTUAL_WORD 처리

12-2의 CONTEXTUAL_WORD를 삭제하지 않는다.

기존 generated asset과 metadata도 삭제하지 않는다.

감사 가능한 과거 실험 결과로 보존한다.

다만 이번 실험의 신규 비교에서는:

DIRECT_WORD
LOWERCASE_WORD
MINIMAL_CONTEXT_WORD

세 전략을 핵심 비교 대상으로 한다.

기존 CONTEXTUAL_WORD는 reference sample로만 사용할 수 있다.

---

# 4. Voice Identity와 Pronunciation Instruction 분리

현재 Voice는 Charon으로 유지한다.

Charon을 다른 voice로 변경하지 않는다.

목표 구조:

VOICE IDENTITY
        │
        └── Charon 공통 성격

LANGUAGE / SPEECH ROLE
        │
        ├── KO_NARRATION
        ├── EN_NATIVE
        └── EN_PHONEME_DEMO

PRONUNCIATION STRATEGY
        │
        ├── DIRECT_WORD
        ├── LOWERCASE_WORD
        └── MINIMAL_CONTEXT_WORD

이 세 개념을 가능한 한 코드상 분리한다.

특히:

"발음을 정확하게 만들기 위한 지시"

가

"화자의 성격/톤"

까지 불필요하게 변경하지 않도록 한다.

---

# 5. 공통 EN_NATIVE Audio Profile

세 전략을 비교할 때 Voice/Profile 조건이 달라지면
실험 의미가 없어진다.

따라서 EN_NATIVE에 공통으로 사용하는:

- voice
- audio profile
- scene
- delivery role
- 기본 tone instruction

을 하나의 공통 기반으로 사용한다.

전략별 차이는 가능한 한:

1. tts_transcript normalization
2. 최소 pronunciation instruction

두 부분에만 존재하도록 한다.

DIRECT_WORD와 LOWERCASE_WORD 사이에서는
가능하면 transcript case만 달라야 한다.

이 조건을 Integrity Check 또는 테스트로 검증한다.

---

# 6. Gemini TTS의 비결정성 인정

중요:

같은 Charon,
같은 prompt,
같은 transcript를 사용해도
생성형 TTS 결과가 매번 완전히 동일한 음색/억양을
보장한다고 가정하지 않는다.

따라서 이번 단계의 목표는:

"모든 파일의 음색을 waveform 수준으로 동일하게 만든다"

가 아니다.

목표는:

"prompt 구조 때문에 의도치 않게 체계적인 톤 차이가 발생하는 것을
최소화한다"

이다.

사람이 듣기에:

"같은 선생님이 같은 수업 안에서 말하는 것 같다"

정도의 perceptual consistency를 목표로 한다.

자동으로 tone consistency PASS를 만들어내지 않는다.

---

# 7. Tone 자동 판정 금지

다음과 같은 가짜 자동 판정기를 만들지 않는다.

- pitch만 비교해서 같은 목소리 판정
- duration만 비교해서 tone consistency 판정
- RMS만 비교해서 같은 화자 판정
- waveform similarity만으로 사람 청취를 대체
- STT 결과가 맞다고 tone까지 APPROVED

기술 메타데이터는 참고용으로 기록할 수 있지만
최종 tone consistency는 사람 청취가 필요하다.

---

# 8. 실제 Sample Matrix

이번 실험은 CAP을 최우선으로 한다.

이유:

CAP은 DIRECT_WORD에서 실제 실패했고
CONTEXTUAL_WORD에서 실제 성공했기 때문에
원인 분리 실험에 가장 가치가 높다.

최소 실제 생성:

CAP LOWERCASE_WORD
CAP MINIMAL_CONTEXT_WORD

기존:

CAP DIRECT_WORD
CAP CONTEXTUAL_WORD

는 reference로 재사용한다.

따라서 CAP 비교 세트:

A. DIRECT_WORD
   기존 실패 reference

B. LOWERCASE_WORD
   신규

C. MINIMAL_CONTEXT_WORD
   신규

D. CONTEXTUAL_WORD
   기존 성공 reference

---

# 9. 일반화 검증

CAP 결과만 보고 정책을 확정하지 않는다.

CAP에서 LOWERCASE_WORD 또는 MINIMAL_CONTEXT_WORD가
좋은 결과를 내면 BAG 또는 MAP 중 최소 하나를 추가 검증한다.

권장:

MAP

이유:

DIRECT_WORD와 CONTEXTUAL_WORD가 모두 이미 좋은 결과였으므로
톤 차이를 비교하기 좋은 reference가 존재한다.

최소 추가 생성 후보:

MAP LOWERCASE_WORD
MAP MINIMAL_CONTEXT_WORD

단, CAP 결과가 둘 다 명백히 실패한다면
무작정 MAP까지 생성하지 말고 원인을 먼저 보고한다.

API 비용을 아끼기 위해 단계적으로 실행해도 된다.

---

# 10. API 호출 예산

이번 단계의 신규 Gemini TTS 호출 목표:

2~4회

정상적인 경우:

CAP LOWERCASE_WORD
CAP MINIMAL_CONTEXT_WORD
MAP LOWERCASE_WORD
MAP MINIMAL_CONTEXT_WORD

= 최대 4회

필요한 경우 최대 6회까지 허용한다.

6회를 넘기지 않는다.

추가 호출이 발생했다면 이유를 보고한다.

YouTube API:
0회

---

# 11. LOWERCASE_WORD 구현

일반화 가능한 함수로 구현한다.

예:

compute_tts_transcript(
    source_text="CAP",
    strategy="LOWERCASE_WORD"
)

결과:

cap

하지만:

speech_assets.source_text == "CAP"

은 그대로 유지되어야 한다.

다음 같은 하드코딩 금지:

if source_text == "CAP":
    return "cap"

BAG/MAP/CAP 및 향후 다른 EN_NATIVE 단어에도
동일 규칙이 적용되어야 한다.

---

# 12. MINIMAL_CONTEXT_WORD 구현

tts_transcript:

cap

Director's Notes pronunciation delta:

Pronounce the transcript as one English word.
Do not spell it.

정도의 최소 지시를 사용한다.

실제 문구는 현재 prompt compiler와
Gemini TTS Advanced Prompting 구조에 맞게 조정 가능하다.

하지만 중요한 제약:

- 설명을 발화하지 않음
- 철자명을 읽지 않음
- target 외의 단어를 발화하지 않음
- pronunciation 외의 style 변경을 최소화
- 기존 Charon 공통 voice identity 유지

---

# 13. Prompt Delta 추적

각 전략이 실제로 무엇을 변경했는지 metadata에 남긴다.

최소:

pronunciation_strategy
source_text
tts_transcript
tts_prompt_version

가능하면:

pronunciation_instruction_delta

또는 이에 준하는 추적 가능한 metadata를 남긴다.

목적:

나중에 "왜 이 파일의 톤이 달랐는가?"를 추적할 수 있어야 한다.

---

# 14. Cache Key

신규 전략은 기존 cache와 절대 충돌하면 안 된다.

cache key에:

- model
- voice
- speech_mode
- source/tts text
- delivery_instruction
- prompt version
- pronunciation_strategy

가 반영되는 기존 12-2 원칙을 유지한다.

LOWERCASE_WORD와 MINIMAL_CONTEXT_WORD는
서로 다른 cache key를 가져야 한다.

DIRECT_WORD
CONTEXTUAL_WORD
LOWERCASE_WORD
MINIMAL_CONTEXT_WORD

모두 전략 차원에서 구분되어야 한다.

---

# 15. Legacy Cache Safety

12-2에서 실제 발견한 버그를 재발시키지 않는다.

legacy cache fallback은 신규 pronunciation strategy를
모르는 옛 cache를 신규 전략 결과처럼 반환하면 안 된다.

신규:

LOWERCASE_WORD
MINIMAL_CONTEXT_WORD

에는 legacy fallback을 적용하지 않는다.

REJECTED 또는 REGENERATE_REQUIRED asset 역시
어떤 cache path에서도 active result로 서빙하면 안 된다.

---

# 16. 기존 Review 상태 보존

현재 사람 검토 결과:

SP007 /b/
→ APPROVED

SP011 /g/
→ APPROVED

SP013::DIRECT_SEQUENCE
→ APPROVED

SP039 기존 DIRECT_WORD CAP
→ REGENERATE_REQUIRED

이 상태를 절대 초기화하지 않는다.

기존 CONTEXTUAL_WORD 결과도 삭제하지 않는다.

신규 전략 Sample은:

PENDING

으로 시작한다.

자동 APPROVED 금지.

---

# 17. Blending 정책은 이번 단계에서 변경하지 않는다

이미 사람 평가를 통해:

DIRECT_SEQUENCE

가 왕초보 설명용 기본 전략으로 적합하다고 판단했다.

따라서:

default_blending_strategy = DIRECT_SEQUENCE

유지.

CONTEXT_RESTRICTED도 valid alternative로 유지.

이번 12-3은 Blending 재설계 단계가 아니다.

EN_PHONEME_DEMO prompt도 불필요하게 수정하지 않는다.

---

# 18. KO_NARRATION도 변경하지 않는다

이번 문제는 EN_NATIVE word pronunciation/tone consistency다.

KO_NARRATION prompt를 변경하지 않는다.

Zephyr를 도입하지 않는다.

Voice는 기존 정책대로 Charon을 유지한다.

---

# 19. Mini Success

CAP은 Mini Success 정답 asset이므로
review_priority=HIGH 정책을 유지한다.

신규:

CAP LOWERCASE_WORD
CAP MINIMAL_CONTEXT_WORD

도 동일 lineage에서 Mini Success answer라면
HIGH가 되어야 한다.

MAP 등의 일반 EN_NATIVE는 기존 정책대로
MEDIUM을 유지할 수 있다.

하드코딩하지 말고 기존 12-2의
is_mini_success_answer_asset() 로직을 재사용한다.

---

# 20. Tone Consistency Review metadata

pronunciation_review와 tone review를 개념적으로 구분할 필요가 있는지 검토한다.

현재 pronunciation_review 하나에 모든 판단을 억지로 넣으면:

"발음은 맞지만 톤이 다름"

이라는 현재 상황을 표현하기 어렵다.

가능하면 metadata_json 수준에서 최소한:

pronunciation_review
tone_consistency_review

를 분리하는 방안을 검토한다.

예:

pronunciation_review:
PENDING / APPROVED / REJECTED / REGENERATE_REQUIRED

tone_consistency_review:
NOT_REQUIRED / PENDING / APPROVED / REJECTED

단:

DB schema를 불필요하게 크게 변경하지 않는다.
metadata_json으로 충분하면 그것을 우선한다.

기존 pronunciation_review 하위 호환은 유지한다.

---

# 21. Ready for Full Generation Gate 강화

EN_NATIVE를 대량 생성하기 전에:

발음 정확성

뿐 아니라

대표 Sample tone consistency

도 확인해야 한다.

단, 모든 44개를 사람이 먼저 들으라는 뜻이 아니다.

대표 Sample Gate다.

최소:

CAP selected strategy
MAP selected strategy

에서:

pronunciation = APPROVED
tone_consistency = APPROVED

가 되어야 EN_NATIVE 기본 전략을 확정할 수 있도록 한다.

사람 청취 전:

Ready for Full Generation = NO

가 정상이다.

---

# 22. 전략 자동 선택 금지

이번 실행 직후 코드가 자동으로:

LOWERCASE_WORD가 최고다

또는

MINIMAL_CONTEXT_WORD가 최고다

라고 결정하지 않는다.

기술적 생성 성공과
사람이 듣는 품질은 다르다.

실제 파일을 생성한 뒤:

Human Listening Required

로 종료한다.

사용자의 청취 평가를 받은 뒤
최종 default_en_native_strategy를 결정한다.

---

# 23. 신규 Integrity Check

기존 26개 Integrity Check 이름/의미를 변경하지 않는다.

필요한 최소 신규 Check를 추가한다.

권장:

## en_native_experiment_isolation_safe

DIRECT_WORD vs LOWERCASE_WORD 비교에서
pronunciation strategy 외 불필요한 prompt 차이가 없는지 확인.

특히 DIRECT vs LOWERCASE는 가능한 한
transcript case만 달라야 한다.

## tone_review_gate_safe

tone_consistency_review가 필요한 신규 Sample이
사람 검토 없이 자동 APPROVED되지 않는지 확인.

## pronunciation_variant_cache_safe

DIRECT_WORD
CONTEXTUAL_WORD
LOWERCASE_WORD
MINIMAL_CONTEXT_WORD

cache key가 전략별로 분리되는지 확인.

## mini_success_en_native_review_safe

CAP 신규 variant가 HIGH review priority를 유지하는지 확인.

실제 구현에 맞게 이름은 조정 가능하다.

---

# 24. 테스트

최소 다음을 검증한다.

CASE A
DIRECT_WORD CAP → tts_transcript "CAP"

CASE B
LOWERCASE_WORD CAP → tts_transcript "cap"

CASE C
MINIMAL_CONTEXT_WORD CAP → tts_transcript "cap"

CASE D
CONTEXTUAL_WORD 기존 동작 회귀 없음

CASE E
LOWERCASE_WORD는 contextual pronunciation instruction을 추가하지 않음

CASE F
MINIMAL_CONTEXT_WORD만 최소 pronunciation instruction 추가

CASE G
DIRECT_WORD와 LOWERCASE_WORD의 공통 Audio Profile 동일

CASE H
LOWERCASE_WORD와 MINIMAL_CONTEXT_WORD의 voice 동일

CASE I
source_text CAP 불변

CASE J
BAG/MAP/CAP 동일 일반화 로직 사용

CASE K
CAP 하드코딩 없음

CASE L
4개 pronunciation strategy cache key 서로 안전하게 구분

CASE M
LOWERCASE_WORD legacy fallback 금지

CASE N
MINIMAL_CONTEXT_WORD legacy fallback 금지

CASE O
REGENERATE_REQUIRED cache serving 금지

CASE P
신규 Sample pronunciation_review=PENDING

CASE Q
신규 Sample tone_consistency_review=PENDING

CASE R
tone review 자동 APPROVED 금지

CASE S
CAP 신규 variants review_priority=HIGH

CASE T
MAP 일반 variant=MEDIUM

CASE U
DIRECT_SEQUENCE default 불변

CASE V
CONTEXT_RESTRICTED 보존

CASE W
PAUSE 3000ms 불변

CASE X
viewer_action 불변

CASE Y
Production Plan 불변

CASE Z
KO_NARRATION 회귀 없음

CASE AA
EN_PHONEME_DEMO 회귀 없음

CASE AB
기존 assets CLI 하위 호환

CASE AC
assets-review 기존 동작 하위 호환

CASE AD
전체 기존 테스트 회귀 없음

---

# 25. 실제 실행 순서

테스트 통과 후 실제 DB에서 다음 순서로 실행한다.

STEP 1

CAP LOWERCASE_WORD 생성

STEP 2

CAP MINIMAL_CONTEXT_WORD 생성

STEP 3

두 파일이 기술적으로 정상인지 확인.

- WAV decode
- duration > 0
- AVAILABLE
- target 외 설명문 발화 여부는 자동 승인하지 않음
- review=PENDING

STEP 4

가능하면 MAP:

MAP LOWERCASE_WORD
MAP MINIMAL_CONTEXT_WORD

생성.

단 CAP 두 신규 전략이 모두 기술적으로 실패하면
MAP 추가 호출을 중단하고 보고한다.

---

# 26. 사람이 최종적으로 들어야 할 CAP 비교

보고서 마지막에 정확한 파일 경로를 제시한다.

CAP:

1. DIRECT_WORD
   기존 실패 reference
   SP039.wav

2. CONTEXTUAL_WORD
   기존 성공 reference
   SP039__CONTEXTUAL_WORD.wav

3. LOWERCASE_WORD
   신규

4. MINIMAL_CONTEXT_WORD
   신규

사람에게 다음을 평가하도록 한다.

- CAP으로 정확히 들리는가?
- 다른 EN_NATIVE 단어와 같은 화자처럼 들리는가?
- 지나치게 부드럽거나 별도 캐릭터처럼 들리는가?
- 왕초보 정답 발음으로 충분히 또렷한가?

---

# 27. 사람이 최종적으로 들어야 할 MAP 비교

가능하면:

1. MAP DIRECT_WORD
2. MAP CONTEXTUAL_WORD
3. MAP LOWERCASE_WORD
4. MAP MINIMAL_CONTEXT_WORD

를 제시한다.

평가:

- 발음 정확성
- 또렷함
- 부드러움
- 기존 EN_NATIVE와의 톤 일관성
- 같은 선생님이 같은 수업에서 말하는 느낌인지

---

# 28. 최종 전략 결정은 보류

이번 코드 실행만으로:

default_en_native_strategy

를 신규 전략으로 확정하지 않는다.

현재 default가 존재한다면 안전한 기존 상태를 유지하거나
명시적인 UNRESOLVED 상태로 둔다.

사람 청취 후 다음 중 하나를 선택한다.

A. DIRECT_WORD
B. LOWERCASE_WORD
C. MINIMAL_CONTEXT_WORD
D. CONTEXTUAL_WORD

선택 후에만 FULL Generation 정책에 반영한다.

---

# 29. Production Plan 불변

다음은 절대 수정하지 않는다.

05 Topic
06 Click Analysis
07 Content Package
08 Blueprint
09 Script
10 Direction
11 Production Plan
production_blocks
speech_assets

12-3은 generated asset/prompt/review 정책 단계다.

upstream을 재생성하지 않는다.

---

# 30. 이번 단계에서 하지 말 것

- FULL 44개 생성 금지
- Renderer 구현 금지
- FFmpeg 작업 금지
- CAP 전용 하드코딩 금지
- 새 pronunciation dictionary 구축 금지
- IPA forced pronunciation 추가 금지
- SSML 비공식 기능을 만들어내지 말 것
- Voice를 Charon에서 변경 금지
- Zephyr 실험 금지
- KO_NARRATION prompt 변경 금지
- EN_PHONEME_DEMO 재설계 금지
- DIRECT_SEQUENCE 재설계 금지
- CONTEXT_RESTRICTED 삭제 금지
- tone 자동 승인 금지
- 사람 청취 없이 default strategy 확정 금지
- upstream stage 재실행 금지
- YouTube API 호출 금지

---

# 31. 완료 보고 형식

작업 후 한글로 다음 순서대로 보고한다.

1. 수정/추가한 파일
2. 12-2에서 남은 문제 정의
3. DIRECT_WORD 구조
4. CONTEXTUAL_WORD 구조
5. LOWERCASE_WORD 구조
6. MINIMAL_CONTEXT_WORD 구조
7. 실험 변수 분리 방식
8. 공통 Charon Audio Profile 처리 방식
9. source_text 보존 방식
10. tts_transcript 처리 방식
11. pronunciation instruction delta
12. CAP 하드코딩 여부
13. cache key 처리
14. legacy fallback 처리
15. 기존 review 상태 보존 결과
16. tone_consistency_review 구현 여부/방식
17. CAP DIRECT 기존 결과
18. CAP CONTEXTUAL 기존 결과
19. CAP LOWERCASE 실제 결과
20. CAP MINIMAL_CONTEXT 실제 결과
21. MAP DIRECT 기존 결과
22. MAP CONTEXTUAL 기존 결과
23. MAP LOWERCASE 실제 결과
24. MAP MINIMAL_CONTEXT 실제 결과
25. 각 신규 Sample duration
26. 실제 Gemini TTS 신규 호출 횟수
27. cache hit 횟수
28. pronunciation_review 상태
29. tone_consistency_review 상태
30. CAP 신규 variant review_priority
31. Blending 기본 전략 보존 여부
32. CONTEXT_RESTRICTED 보존 여부
33. 신규 Integrity Check 목록
34. 전체 Integrity Check 결과
35. Ready for Full Generation 여부
36. Ready for Rendering 여부
37. PAUSE 3000ms 보존 여부
38. viewer_action 보존 여부
39. Production Plan 불변 여부
40. 추가한 테스트 수
41. 전체 테스트 결과
42. 05~12-2 회귀 여부
43. CLI 하위 호환 여부
44. Gemini TTS 실제 신규 API 호출 수
45. YouTube API 사용량
46. Human Listening Required 파일 목록
47. 각 파일에서 사람이 판단해야 할 항목
48. 발견된 제한사항

---

# 32. 성공 기준

12-3 성공 기준은 단순히 새로운 WAV 파일이 생성되는 것이 아니다.

다음을 만족해야 한다.

1. CAP 발음 개선 원인을 분리해서 비교할 수 있다.
2. lowercase만 적용한 전략을 독립적으로 검증할 수 있다.
3. minimal context만 추가한 전략을 독립적으로 비교할 수 있다.
4. source_text는 변하지 않는다.
5. Charon voice identity는 유지된다.
6. pronunciation instruction이 tone instruction과 분리된다.
7. 전략별 cache가 섞이지 않는다.
8. 기존 REGENERATE_REQUIRED asset이 다시 active cache로 사용되지 않는다.
9. 신규 Sample은 사람 승인 전 PENDING이다.
10. pronunciation과 tone consistency를 구분해 평가할 수 있다.
11. CAP에서 실제 Sample이 생성된다.
12. 가능하면 MAP에서도 일반화 검증된다.
13. DIRECT_SEQUENCE 기본 Blending 정책은 그대로 유지된다.
14. Production Plan은 불변이다.
15. FULL Generation은 아직 실행하지 않는다.
16. 최종 EN_NATIVE 기본 전략은 사람 청취 후 결정한다.

이 조건을 만족하면 12-3 코드/실험 단계 완료로 판정한다.

최종 정책 확정은 Human Listening 결과를 받은 뒤 별도로 수행한다.