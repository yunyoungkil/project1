# 12-2. EN_NATIVE 짧은 단어 발음 안정화 및 Blending 기본 전략 확정

## 0. 작업 목적

12-1 실제 Sample 청취 결과 다음이 확인되었다.

정상:
- SP007 /b/ → 좋음
- SP011 /g/ → 좋음
- SP013 DIRECT_SEQUENCE → 좋음
- SP013 CONTEXT_RESTRICTED → 좋음

Blending 사람 평가:
- DIRECT_SEQUENCE:
  "브, 애~, 그, 배~~~~그"처럼 들림.
  음가를 비교적 천천히 분리해서 들려준 뒤 blending하므로
  왕초보에게 처음 원리를 설명할 때 적합하다.
- CONTEXT_RESTRICTED:
  "브, 애, 그, 배~~그"처럼 들림.
  DIRECT_SEQUENCE보다 조금 빠르게 연결되는 느낌이며
  이것도 사용 가능한 품질이다.

문제:
- SP039 EN_NATIVE target = CAP
- 실제 청취 결과 "CAP"의 자연스러운 영어 단어 발음으로 안정적으로
  들리지 않았으며 사용자가 "배그"처럼 들린다고 판정했다.
- 따라서 pronunciation_review는 APPROVED가 될 수 없다.
- SP039는 REGENERATE_REQUIRED로 취급해야 한다.

이번 단계의 핵심 목적은:

1. EN_NATIVE 짧은 영어 단어를 Gemini TTS가 안정적으로 발음하도록 한다.
2. display/source text와 실제 TTS pronunciation context를 분리한다.
3. CAP 하나만 하드코딩해서 고치지 않는다.
4. BAG/MAP/CAP 등 짧은 CVC 단어에 일반화 가능한 방법인지 실제 TTS로 검증한다.
5. DIRECT_SEQUENCE를 초급 교육용 기본 Blending 전략으로 확정한다.
6. CONTEXT_RESTRICTED는 제거하지 않고 보조 전략으로 유지한다.
7. 기존 Production Plan / Speech Asset / Content Block 의미를 변경하지 않는다.
8. 사람이 승인하기 전 발음을 자동 APPROVED 처리하지 않는다.

중요:
이번 단계는 Renderer 단계가 아니다.
영상 렌더링, 자막 렌더링, FFmpeg 조립 등을 만들지 않는다.

---

# 1. 가장 중요한 원칙

이번 문제를 CAP 한 단어의 예외 처리로 해결하지 마라.

금지 예:

if source_text == "CAP":
    ...

CAP 전용 pronunciation dictionary를 하드코딩하는 것도 금지한다.

문제는 더 일반적이다.

현재 EN_NATIVE는 짧은 대문자 영어 토큰을 그대로 TTS Transcript에 전달한다.

예:

CAP

이 입력만으로 Gemini TTS가

- 영어 단어
- 약어
- 철자 이름
- 다른 문맥

중 무엇으로 해석할지 충분히 안정적이지 않을 수 있다.

따라서 이번 단계에서는

DISPLAY ORTHOGRAPHY

와

TTS PRONUNCIATION CONTEXT

를 개념적으로 분리한다.

예:

source_text / display:
CAP

TTS가 이해해야 할 의미:
"영어 단어 cap을 철자 이름이 아니라 하나의 자연스러운 단어로 발음"

단, source_text 자체를 다른 문자열로 덮어쓰지 않는다.

Production Plan의 원본 데이터도 수정하지 않는다.

---

# 2. Gemini TTS 공식 문서 재확인

구현 전에 현재 Gemini TTS 공식 문서를 다시 확인하라.

확인 대상:

- gemini-3.1-flash-tts-preview
- single-speaker TTS prompting
- Audio Profile
- Scene
- Director's Notes
- Transcript
- pronunciation 관련 공식 제어 방법
- IPA/phoneme pronunciation 강제 기능 존재 여부
- SSML 지원 여부
- spelling / acronym / word pronunciation 관련 공식 guidance
- responseModalities AUDIO
- prebuilt voice Charon

웹 검색 결과보다 Google 공식 문서를 우선한다.

보고서에 다음을 명확히 구분한다.

A. 공식 지원 기능
B. prompt를 이용한 비공식/실험적 제어
C. 공식적으로 지원되지 않는 기능

특히 IPA를 공식 forced-pronunciation 기능처럼 취급하지 마라.

공식 기능이 아니라면 명확히 그렇게 기록한다.

---

# 3. 기존 코드 먼저 조사

수정 전에 반드시 다음 흐름을 추적한다.

production_plan
→ speech_assets
→ asset_generator
→ build_tts_prompt
→ GeminiTTSClient
→ cache
→ generated_assets
→ pronunciation_review

특히 EN_NATIVE의 현재 prompt가 실제 REST 요청의 어느 부분에 들어가는지 확인한다.

다음도 확인한다.

- source_text
- delivery_instruction
- delivery_language
- delivery_role
- prompt version
- cache key
- metadata_json
- pronunciation_review

추측하지 말고 실제 코드 기준으로 보고한다.

---

# 4. EN_NATIVE pronunciation strategy 도입

EN_NATIVE에 명시적인 pronunciation strategy 개념을 추가한다.

최소한 다음 두 전략을 비교 가능하게 한다.

## Strategy A — DIRECT_WORD

현재 방식에 가까운 baseline.

예:

Transcript:
CAP

또는 현재 코드가 실제 사용하는 동일한 direct 입력.

이 전략은 비교 기준이며 무조건 삭제하지 않는다.

## Strategy B — CONTEXTUAL_WORD

TTS에게 이것이 영어 단어임을 문맥으로 명확하게 알려준다.

핵심 지시 의미:

- This is an English word.
- Pronounce it naturally as one word.
- Do not spell the letters.
- Do not say the letter names.
- Do not explain the word.
- Speak only the requested target word in the actual output.
- Use natural American English pronunciation.

중요:

이 설명을 실제 발화 Transcript에 섞어 Gemini가 설명문까지 읽어버리는
구조로 만들지 마라.

Gemini TTS의 공식 Advanced Prompting 구조에 맞춰
Audio Profile / Scene / Director's Notes / Transcript 역할을 분리한다.

Transcript에는 가능한 한 실제로 발화할 target만 남긴다.

예:

Director's Notes:
Pronounce the transcript as one natural English word.
Do not spell the letters.
Do not explain it.
Do not add any other spoken words.

Transcript:
cap

단, 이것은 예시다.
공식 문서와 현재 구현 구조를 확인한 후 가장 적절한 형태로 구현한다.

---

# 5. Case normalization 조사

EN_NATIVE source_text가 대문자로 저장되어 있더라도
TTS 전달용 transcript에서 lowercase가 더 안정적인지 실제 비교한다.

예:

source_text:
CAP

display/source 보존:
CAP

TTS transcript 후보:
cap

이 경우에도 원본 source_text는 절대 변경하지 않는다.

metadata에 실제 TTS transcript/strategy를 추적 가능하게 남긴다.

예:

{
  "source_text": "CAP",
  "tts_transcript": "cap",
  "pronunciation_strategy": "CONTEXTUAL_WORD"
}

필드명은 기존 코드 스타일에 맞게 결정한다.

---

# 6. IPA 강제 방식은 우선 사용하지 않는다

이번 EN_NATIVE 안정화의 첫 해결책으로 다음과 같이 하지 마라.

CAP → /kæp/

이유:

Gemini TTS에 공식 forced phoneme/IPA pronunciation 기능이 없다면
이것을 안정적인 API 계약으로 간주할 수 없다.

우선:

orthography + pronunciation context

방식으로 해결한다.

IPA는 이미 EN_PHONEME_DEMO라는 별도 speech_mode에서 사용 중이며
EN_NATIVE와 역할을 섞지 않는다.

---

# 7. 실제 Sample Matrix

CAP 하나만 성공시키고 종료하지 않는다.

최소 다음 실제 영어 단어로 일반화 검증한다.

BAG
MAP
CAP

가능하면 기존 Speech Asset을 재사용하여
source lineage를 유지한다.

각 단어에 대해 최소:

DIRECT_WORD
CONTEXTUAL_WORD

두 전략을 비교한다.

즉 최대 기본 비교:

BAG
  DIRECT_WORD
  CONTEXTUAL_WORD

MAP
  DIRECT_WORD
  CONTEXTUAL_WORD

CAP
  DIRECT_WORD
  CONTEXTUAL_WORD

단, 기존 cache에 DIRECT_WORD 결과가 있고
prompt/version/strategy가 정확히 일치한다면
불필요하게 API를 재호출하지 않는다.

새로운 CONTEXTUAL_WORD만 생성하면 되는 경우 그렇게 한다.

---

# 8. 실제 유료 API 호출 제한

무작정 반복 생성하지 않는다.

이번 단계의 신규 Gemini TTS 호출 목표:

3~6회

필요하면 최대 8회까지 허용하지만
왜 추가 호출이 필요했는지 보고서에 기록한다.

같은 입력을 이유 없이 반복 생성하지 않는다.

YouTube API는 호출하지 않는다.

---

# 9. 사람 청취가 최종 판정

기술적으로 WAV가 생성되었다고 pronunciation을 APPROVED 하지 않는다.

다음 상태를 그대로 유지한다.

NOT_REQUIRED
PENDING
APPROVED
REJECTED
REGENERATE_REQUIRED

신규 EN_NATIVE Sample은 기본:

PENDING

으로 생성한다.

사람이 실제로 듣고 승인해야 APPROVED가 된다.

SP039 기존 잘못된 CAP 결과는
가능하면 review workflow를 통해

REGENERATE_REQUIRED

로 기록한다.

단, 기존 asset row를 파괴적으로 덮어쓰지 않는다.

기존 파일/기록을 감사 가능하게 보존한다.

---

# 10. EN_NATIVE review priority

기존 정책을 검토한다.

현재:

EN_NATIVE = MEDIUM

EN_PHONEME_DEMO = HIGH

이 정책은 기본적으로 유지한다.

다만 이번처럼 왕초보에게 정답으로 직접 들려주는
Mini Success answer EN_NATIVE는 교육적으로 중요하다.

가능하면 context 기반으로 review priority를 승격할 수 있는지 검토한다.

예:

일반 EN_NATIVE:
MEDIUM

Mini Success 정답 EN_NATIVE:
HIGH

단, 이 변경이 지나치게 복잡하거나
Production Block lineage 없이는 안정적으로 판별할 수 없다면
억지로 추가하지 말고 제한사항으로 보고한다.

---

# 11. Blending 기본 전략 확정

12-1 사람 청취 결과를 정책에 반영한다.

초기 교육/설명용 기본:

DIRECT_SEQUENCE

이유:
각 음가를 비교적 천천히 분리한 후 blending하여
왕초보가 소리 결합 과정을 듣기 쉽다.

CONTEXT_RESTRICTED는 제거하지 않는다.

다음 용도로 보존한다.

- reinforcement
- review
- 이미 한 번 설명한 뒤 더 빠른 blending
- 향후 Director/Planner가 필요에 따라 선택할 수 있는 alternative

이번 단계에서 모든 Content Block에 복잡한 자동 선택기를 만들 필요는 없다.

최소한:

default_blending_strategy = DIRECT_SEQUENCE

를 config 또는 적절한 정책 위치에 두고
하드코딩 분산을 피한다.

---

# 12. Blending 발화 길이에 대한 오해 금지

DIRECT_SEQUENCE가 약 9초였다는 이유만으로
자동 실패시키지 않는다.

사람 청취 결과:

"브, 애~, 그, 배~~~~그"

처럼 천천히 교육적으로 들려주는 특성이 오히려 장점으로 평가되었다.

따라서 duration만 보고 품질을 판정하지 않는다.

대신 다음을 본다.

- 불필요한 설명 발화가 있는가
- target 외 단어를 말하는가
- 각 음가가 식별 가능한가
- 최종 blending이 있는가
- 사람이 교육용으로 승인했는가

CONTEXT_RESTRICTED 역시 약간 더 빠른 유효한 대안으로 보존한다.

---

# 13. Cache versioning

12-1에서 추가한 prompt_version 정책을 반드시 유지한다.

EN_NATIVE prompt/strategy가 바뀌므로
옛 CAP 오발음이 cache hit되어 다시 사용되는 일이 없어야 한다.

cache key에 최소 다음이 반영되는지 확인한다.

- model
- voice
- speech_mode
- source/tts text
- delivery_instruction
- prompt_version
- pronunciation_strategy

필요하다면:

TTS_PROMPT_VERSION = "12.2"

로 올린다.

하지만 12-1의 정상적인 EN_PHONEME_DEMO까지
불필요하게 cache invalidation하지 않는 방법이 있다면
mode-specific versioning을 검토한다.

과도한 설계는 하지 않는다.

핵심은:

새 EN_NATIVE 전략이 옛 잘못된 CAP cache를 재사용하면 안 된다.

---

# 14. 기존 APPROVED/PENDING 의미 보존

Cache hit가 발생했다고 review status를 자동 APPROVED로 바꾸지 않는다.

기존 metadata가:

PENDING

이면 재사용 후에도 PENDING.

기존 사람이 APPROVED한 동일 전략/동일 prompt version/동일 target의
정확히 같은 asset을 재사용할 경우에만 APPROVED 보존을 검토한다.

전략이나 prompt version이 바뀌면 신규 pronunciation artifact로 취급한다.

---

# 15. CLI

기존:

research assets
research assets-review

하위 호환을 깨지 않는다.

가능하면 기존 assets-review 흐름을 재사용한다.

이번 단계만을 위해 불필요한 별도 CLI를 만들지 않는다.

다만 실제 Sample 비교를 명확하게 수행하기 위해
기존 CLI에 작은 옵션이 필요한 경우 최소 확장할 수 있다.

기존 명령 시그니처/동작은 깨지면 안 된다.

---

# 16. assets-review 사용성 확인

사람이 다음과 같은 review를 실제 기록할 수 있어야 한다.

SP007 /b/
→ APPROVED

SP011 /g/
→ APPROVED

SP013 DIRECT_SEQUENCE
→ APPROVED

SP039 기존 CAP
→ REGENERATE_REQUIRED

신규 CAP CONTEXTUAL_WORD
→ PENDING

현재 assets-review가 전략별 variant를 구분하지 못한다면
최소 수정으로 구분 가능하게 한다.

특히:

SP013__DIRECT_SEQUENCE.wav
SP013__CONTEXT_RESTRICTED.wav

처럼 같은 source asset의 variant를
독립적으로 review할 수 있어야 한다.

---

# 17. 신규 Integrity Check

기존 21개 Integrity Check 이름/의미를 변경하지 않는다.

필요한 최소 신규 check를 추가한다.

권장:

en_native_pronunciation_strategy_safe

검증:
- EN_NATIVE에 허용된 strategy만 사용
- source_text 보존
- TTS transcript 추적 가능
- spelling instruction 금지/word pronunciation 지시 존재

en_native_source_preserved

검증:
- display/source text가 TTS normalization 때문에 변경되지 않았음

cache_pronunciation_strategy_safe

검증:
- strategy 변경이 cache key에 반영됨

human_pronunciation_gate_safe

검증:
- 신규 pronunciation sample이 자동 APPROVED되지 않음
- REJECTED/REGENERATE_REQUIRED asset이 Ready gate를 통과하지 않음

blending_default_strategy_safe

검증:
- default = DIRECT_SEQUENCE
- CONTEXT_RESTRICTED도 valid alternative로 유지

실제 구현에 맞게 이름은 조정 가능하지만
각 목적은 보고서에 명시한다.

---

# 18. Ready for Full Generation Gate

12-1의 Ready for Full Generation 개념을 유지한다.

다음 조건을 만족하기 전 FULL 44개를 생성하지 않는다.

최소:

1. 모든 Integrity Check critical 항목 pass
2. EN_PHONEME_DEMO HIGH sample 승인
3. 기본 Blending strategy 승인
4. EN_NATIVE 대표 Sample의 pronunciation 검증
5. REGENERATE_REQUIRED asset을 active output으로 사용하지 않음
6. CAP 같은 짧은 CVC target에서 신규 전략이 실제로 검증됨

이번 단계에서 사람 청취 전이라면:

Ready for Full Generation: NO

가 정상이다.

억지로 YES를 만들지 않는다.

---

# 19. Production Plan 불변성

12단계는 Asset Generation 단계다.

다음 upstream 데이터는 수정하지 않는다.

05 topic
06 click
07 package
08 blueprint
09 script
10 direction
11 production plan
production_blocks
speech_assets

필요한 asset-generation metadata와 generated_assets만 추가/갱신한다.

Production Plan을 다시 생성해서 문제를 숨기지 않는다.

---

# 20. 테스트

최소 다음을 테스트한다.

CASE A
EN_NATIVE source_text=CAP이 그대로 보존된다.

CASE B
CONTEXTUAL_WORD의 실제 TTS transcript는 필요 시 cap으로 normalization 가능하다.

CASE C
normalization이 source_text를 변경하지 않는다.

CASE D
EN_NATIVE prompt에 "spell the letters"를 요구하지 않는다.

CASE E
EN_NATIVE prompt가 explanation을 발화하도록 요구하지 않는다.

CASE F
DIRECT_WORD와 CONTEXTUAL_WORD cache key가 다르다.

CASE G
prompt version 변경 시 cache key가 달라진다.

CASE H
기존 잘못된 CAP cache가 신규 strategy에서 재사용되지 않는다.

CASE I
BAG/MAP/CAP에 동일한 일반화 로직이 적용된다.

CASE J
CAP 하드코딩 분기 없음.

CASE K
신규 Sample pronunciation_review 기본 PENDING.

CASE L
REGENERATE_REQUIRED가 자동 APPROVED되지 않는다.

CASE M
APPROVED 기존 asset의 review state 보존 조건이 정확하다.

CASE N
DIRECT_SEQUENCE가 default blending strategy다.

CASE O
CONTEXT_RESTRICTED가 valid alternative로 남아 있다.

CASE P
duration이 길다는 이유만으로 DIRECT_SEQUENCE를 자동 reject하지 않는다.

CASE Q
EN_PHONEME_DEMO 기존 동작 회귀 없음.

CASE R
KO_NARRATION 기존 동작 회귀 없음.

CASE S
PAUSE 3000ms 불변.

CASE T
viewer_action 불변.

CASE U
Production Plan row/content 불변.

CASE V
기존 assets CLI 하위 호환.

CASE W
assets-review가 strategy variant를 구분할 수 있다.

CASE X
전체 기존 테스트 회귀 없음.

---

# 21. 실제 Sample 생성

테스트만 통과시키고 끝내지 않는다.

실제 DB 기준으로 대표 Sample을 생성한다.

최소:

BAG
MAP
CAP

각각 신규 CONTEXTUAL_WORD 전략을 실제 Gemini TTS로 생성한다.

DIRECT_WORD가 정확히 동일한 기존 cache로 존재한다면 재사용한다.

각 파일의:

- asset id
- source_text
- strategy
- tts_transcript
- filename
- duration
- cache hit/miss
- pronunciation_review
- review_priority

를 보고한다.

신규 파일은 사람이 직접 비교할 수 있도록
경로를 명확히 적는다.

---

# 22. 실제 사람이 들을 최종 비교 세트

보고서 마지막에 반드시 별도 섹션:

## Human Listening Required

를 만든다.

최소 다음처럼 정리한다.

BAG
- DIRECT_WORD: ...
- CONTEXTUAL_WORD: ...

MAP
- DIRECT_WORD: ...
- CONTEXTUAL_WORD: ...

CAP
- 기존 DIRECT_WORD: ...
- 신규 CONTEXTUAL_WORD: ...

그리고 사용자가 어떤 파일을 먼저 들어야 하는지 명확하게 표시한다.

자동으로 어느 전략이 발음상 더 정확하다고 판정하지 않는다.

---

# 23. 이번 단계에서 하지 말 것

- FULL 44개 무조건 생성 금지
- Renderer 구현 금지
- FFmpeg 영상 생성 금지
- CAP 하드코딩 금지
- 자체 발음 사전 대규모 구축 금지
- IPA forced pronunciation을 공식 기능처럼 사용 금지
- STT를 붙여서 가짜 pronunciation verifier 만들지 말 것
- 사람 청취 없이 APPROVED 금지
- Production Plan 수정 금지
- upstream stage 재생성 금지
- YouTube API 호출 금지
- DIRECT_SEQUENCE 제거 금지
- CONTEXT_RESTRICTED 제거 금지

---

# 24. 완료 보고 형식

작업 후 한글로 다음 순서대로 보고한다.

1. 수정/추가한 파일
2. 기존 SP039 CAP 오발음 원인 분석
3. Gemini TTS 공식 문서에서 확인한 pronunciation 제어 범위
4. 공식 지원 vs prompt 기반 실험적 제어 구분
5. EN_NATIVE 기존 prompt 구조
6. EN_NATIVE 수정 prompt 구조
7. DIRECT_WORD 정의
8. CONTEXTUAL_WORD 정의
9. source_text와 tts_transcript 분리 방식
10. uppercase/lowercase 처리 방식
11. CAP 하드코딩 여부
12. IPA 강제 방식 사용 여부와 이유
13. prompt version 변경 내용
14. cache key 변경 내용
15. 기존 잘못된 CAP cache 재사용 방지 결과
16. BAG DIRECT/CONTEXTUAL 결과
17. MAP DIRECT/CONTEXTUAL 결과
18. CAP DIRECT/CONTEXTUAL 결과
19. 각 실제 Sample duration
20. 실제 신규 Gemini TTS 호출 횟수
21. cache hit 횟수
22. pronunciation_review 상태
23. SP007 /b/ 승인 상태
24. SP011 /g/ 승인 상태
25. DIRECT_SEQUENCE 승인/기본 전략 반영 결과
26. CONTEXT_RESTRICTED 보조 전략 보존 여부
27. assets-review variant 지원 결과
28. Mini Success EN_NATIVE review priority 처리
29. 신규 Integrity Check 목록
30. 전체 Integrity Check 결과
31. Ready for Full Generation 여부
32. Ready for Rendering 여부
33. PAUSE 3000ms 보존 여부
34. viewer_action 보존 여부
35. Production Plan 불변 여부
36. 추가한 테스트 수
37. 전체 테스트 결과
38. 05~12-1 회귀 여부
39. CLI 하위 호환 여부
40. Gemini TTS 실제 API 사용량
41. YouTube API 사용량
42. 사람이 지금 직접 들어야 할 파일 목록
43. 발견된 제한사항

---

# 25. 성공 기준

이번 단계의 성공은

"CAP 하나가 우연히 제대로 발음되었다"

가 아니다.

성공 기준은:

- EN_NATIVE short-word pronunciation 전략이 일반화 가능하다.
- BAG/MAP/CAP에서 동일 구조로 동작한다.
- source/display text는 원형 보존된다.
- TTS용 pronunciation context만 별도로 최적화된다.
- cache가 전략/version 차이를 안전하게 구분한다.
- 잘못된 기존 CAP asset은 승인되지 않는다.
- 신규 발음도 사람 승인 전에는 PENDING이다.
- DIRECT_SEQUENCE는 왕초보용 기본 Blending 전략으로 유지된다.
- CONTEXT_RESTRICTED도 유효한 보조 전략으로 남는다.
- upstream Production Plan은 변경되지 않는다.
- FULL Generation은 사람 검토 전 실행되지 않는다.

이 조건을 만족할 때 12-2 완료로 판정한다.