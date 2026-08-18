# 12-1단계: TTS 발음 · Blending · Speech Asset 분할 교정

## 0. 작업 목적

현재 프로젝트의 12단계 Verified Asset Generator는 실제 Gemini TTS를 사용해
KO_NARRATION / EN_NATIVE / EN_PHONEME_DEMO 음성을 생성하는 데 성공했다.

현재 실제 Sample:

- SP001.wav
  - speech_mode: KO_NARRATION
  - voice: Charon
  - duration: 약 32.6초

- SP003.wav
  - speech_mode: EN_NATIVE
  - source: BAG
  - voice: Charon
  - duration: 약 1.16초

- SP009.wav
  - speech_mode: EN_PHONEME_DEMO
  - source: /æ/
  - voice: Charon
  - duration: 약 1.6초

현재 모델:
gemini-3.1-flash-tts-preview

현재 기본 Voice 정책:
- EDUCATION: Charon
- 영어 원어민 발음: Charon
- 한국어 나레이션: Charon
- PODCAST female: Zephyr
- PODCAST male: Charon

12단계의 구조적 생성 파이프라인은 정상 작동한다.

그러나 FULL 44개 음성 자산을 생성하기 전에 다음 문제를 검증/교정해야 한다.

1. 단독 phoneme가 실제 교육용 목표 음가로 생성되는가
2. phoneme blending을 어떻게 TTS에 지시해야 가장 안정적인가
3. EN_NATIVE와 EN_PHONEME_DEMO가 역할상 확실히 분리되는가
4. 한국어 설명과 영어 원어민 발음이 같은 Charon을 사용해도 각각 적절한 발음 모드로 전환되는가
5. 너무 긴 KO_NARRATION Asset이 향후 자막/강조/화면 동기화를 방해하지 않는가
6. FULL 생성 전에 어떤 음성 자산에 사람 검토가 반드시 필요한가

이번 단계는 새로운 영상 제작 단계가 아니다.

목표는:

"12단계가 생성할 Speech Asset을 영어교육 영상에서 실제 사용할 수 있는 수준으로 검증하고,
잘못된 발음 자산의 대량 생성을 사전에 차단하는 것"

이다.


# 1. 매우 중요한 작업 원칙

## 1-1. 기존 단계 보존

05~11-2 및 12단계의 기존 책임을 변경하지 마라.

특히 다음을 임의 변경하지 마라.

- Content Script
- Video Direction
- Production Plan
- Production Block
- viewer_action
- thinking_time
- PAUSE
- caption plan
- source clip plan
- final_format
- speech_mode taxonomy

12-1은 Speech Asset 생성 품질과 검증만 교정한다.


## 1-2. FULL 생성 금지

이번 작업에서 전체 44개 Speech Asset을 실제 API로 생성하지 마라.

반드시 소규모 Sample/Test Set만 생성한다.

API 호출이 필요하면 호출 이유와 개수를 먼저 최소화하고,
동일 결과를 cache로 확인할 수 있으면 재호출하지 않는다.


## 1-3. 실제 TTS 능력과 추측을 구분

Gemini TTS가 제공하지 않는 기능을 있다고 가정하지 마라.

예:

- word-level timestamp
- phoneme-level timestamp
- forced alignment
- pronunciation confidence
- phoneme accuracy score

API가 제공하지 않는 정보는 만들어내지 않는다.

UNAVAILABLE / HUMAN_REVIEW_REQUIRED 등의 상태로 정직하게 기록한다.


# 2. 먼저 현재 구현을 조사하라

다음 파일을 읽고 현재 구조를 정확히 파악하라.

- research/asset_generator.py
- research/tts_client.py
- research/production_planner.py
- research/video_director.py
- research/db.py
- research/config.py
- config/research_config.yaml
- tests/test_asset_generator.py

기존 12단계의 다음 구조를 우선 재사용하라.

- build_tts_prompt()
- synthesize_asset()
- compute_cache_key()
- pronunciation_review
- speech_mode
- delivery_instruction
- expected_pronunciation
- generated_assets
- manifest

기존 함수를 무시하고 별도 시스템을 중복 구현하지 마라.


# 3. 실제 Gemini TTS 공식 문서 재확인

현재 시점의 Gemini TTS 공식 문서를 웹에서 확인하라.

우선순위:

1. Google AI / Gemini API 공식 문서
2. Google 공식 API reference
3. 필요할 경우 공식 cookbook/example

블로그/커뮤니티 글을 공식 계약보다 우선하지 마라.

다음을 확인하라.

- gemini-3.1-flash-tts-preview의 현재 사용 방식
- prompt/director instruction 권장 방식
- voice configuration
- Charon 특성
- Zephyr 특성
- multi-language 처리
- pronunciation control 관련 공식 지원 범위
- style/tone instruction
- audio output format
- 알려진 TTS prompt 작성 권장사항

현재 코드가 공식 계약과 다르면 최소 범위에서 교정한다.

단, google-genai SDK 설치를 이번 작업의 필수 조건으로 만들지 마라.
현재 requests 기반 REST 구현이 공식 계약과 일치하면 유지 가능하다.


# 4. Speech Mode 역할을 명확하게 고정

다음 네 역할을 절대로 혼동하지 않게 한다.


## A. KO_NARRATION

목적:
한국인 학습자에게 설명하는 한국어 나레이션.

Voice:
Charon

원칙:
- 자연스러운 한국어
- 차분함
- 설명형
- 지나치게 연기하지 않음
- 영어 단어가 문장 안에 섞여 있으면 가능하면 별도 EN_NATIVE Asset으로 분리
- IPA 목표 음가는 별도 EN_PHONEME_DEMO로 분리

KO_NARRATION에서 영어 단어의 원어민 발음을 대신 처리하지 않는 것을 기본값으로 한다.


## B. EN_NATIVE

목적:
학습자에게 "실제 영어 단어가 어떻게 들리는지" 들려주는 정답/원어민 모델.

Voice:
Charon

예:

BAG
BAT
MAP
CAP

원칙:

- word pronunciation only
- spelling 금지
- letter name 금지
- 한국어 설명 금지
- IPA 설명 금지
- 불필요한 앞뒤 문장 금지

예:

BAD:
"B-A-G, bag."

BAD:
"The word is bag."

GOOD:
"BAG"의 자연스러운 원어민 발음만.


## C. EN_PHONEME_DEMO

목적:
단어 전체가 아니라 목표 음가를 들려주는 교육용 음성.

예:

/b/
/æ/
/g/
/t/
/m/
/p/
/k/

원칙:

- letter name을 말하지 않는다.
- IPA symbol 이름을 읽지 않는다.
- "the sound is..." 같은 설명을 하지 않는다.
- 가능한 경우 목표 음가만 생성한다.
- 결과가 교육적으로 불안정하면 자동 PASS하지 않는다.


## D. KO_PRONUNCIATION_GUIDE

목적:
한국 학습자를 위한 근사 발음 가이드.

이것은 원어민 발음이 아니다.

반드시 approximation_only=true 의미를 유지한다.

EN_NATIVE 또는 EN_PHONEME_DEMO를 대체하지 않는다.


# 5. Language Delivery Mode 명시

같은 Charon을 사용하더라도 prompt가 언어 역할을 분명하게 알려주도록 한다.

필요하다면 TTS Prompt 내부에 다음과 같은 명시적 개념을 추가하라.

delivery_language:
- ko-KR
- en-US

delivery_role:
- korean_educational_narrator
- native_english_model
- isolated_english_phoneme
- korean_pronunciation_approximation

단, Gemini API에 존재하지 않는 필드를 REST payload에 임의 추가하지 마라.

이 값들은 내부 metadata/prompt compiler용으로 사용할 수 있다.


# 6. Phoneme Test Set

FULL 생성 전에 최소 phoneme 검증 세트를 만든다.

현재 실제 콘텐츠에서 필요한 음가를 우선 사용한다.

최소:

/b/
/æ/
/g/
/t/
/m/
/p/
/k/

각 phoneme에 대해:

- source_text
- expected_pronunciation
- generated file
- duration
- mime type
- voice
- prompt version
- pronunciation_review

를 추적 가능하게 한다.


# 7. Blending Test 설계

이번 단계의 핵심이다.

BAG을 기준으로 최소 다음 교육 흐름을 검증한다.

/b/
→ /æ/
→ /g/
→ blending
→ BAG

단순히 문자열 "/b-æ-g/"를 Gemini에 던지는 것을 정답이라고 가정하지 마라.

최소 몇 가지 prompt strategy를 비교할 수 있는 구조를 만든다.

예:

Strategy A
phoneme sequence를 직접 제시

Strategy B
"blend these sounds smoothly..." 같은 delivery instruction 사용

Strategy C
target word를 내부 context로 제공하되 출력은 blending pronunciation만 요구

중요:

TTS에 전달하는 context와 실제로 발화해야 하는 transcript를 구분하라.

BAG이라는 정답 단어를 context로 줬다는 이유로
TTS가 "BAG"만 바로 읽어버리면 blending demonstration 실패다.


# 8. Blending Asset 역할 분리 검토

필요하다면 기존 EN_PHONEME_DEMO 안에 metadata를 추가하여 다음을 구분할 수 있다.

phoneme_demo_type:

- ISOLATED
- BLENDED_SEQUENCE

새 speech_mode를 만드는 것은 우선 피한다.

기존 taxonomy로 표현 가능하면 metadata 수준에서 해결한다.

예:

EN_PHONEME_DEMO
demo_type=ISOLATED
source=/æ/

EN_PHONEME_DEMO
demo_type=BLENDED_SEQUENCE
source=/b/ + /æ/ + /g/

단, 실제 생성 결과가 불안정하면 BLENDED_SEQUENCE를 자동 승인하지 않는다.


# 9. Pronunciation Review 상태 정의

현재 pronunciation_review=PENDING 구조를 확장할 필요가 있는지 검토한다.

최소 다음 상태를 표현할 수 있어야 한다.

NOT_REQUIRED
PENDING
APPROVED
REJECTED

필요하다면:

REGENERATE_REQUIRED

를 추가할 수 있다.

하지만 기존 DB와 하위 호환을 깨뜨리지 마라.


# 10. 자동 발음 PASS 금지

매우 중요하다.

현재 시스템에는 실제 음향 기반 phoneme recognition/forced alignment가 없다.

따라서 다음을 금지한다.

"Gemini가 성공 응답을 줬으므로 발음 정확"

"파일이 정상 WAV이므로 pronunciation pass"

"duration이 정상 범위이므로 발음 pass"

파일 기술 검증과 발음 검증을 분리한다.

예:

technical_validation = PASS
pronunciation_review = PENDING

은 정상적인 상태다.


# 11. Human Review 대상 최소화

모든 한국어 나레이션을 사람이 하나씩 검수해야 하는 구조로 만들 필요는 없다.

다음처럼 위험도 기반 검토를 설계하라.

LOW:
일반 KO_NARRATION

MEDIUM:
EN_NATIVE

HIGH:
EN_PHONEME_DEMO isolated

HIGH:
EN_PHONEME_DEMO blended

KO_PRONUNCIATION_GUIDE도 교육 정확성 때문에 검토 대상으로 고려한다.

실제 최종 정책은 코드 구조를 보고 결정하되 이유를 보고하라.


# 12. Speech Asset 길이 문제

SP001 KO_NARRATION이 약 32.6초였다.

이것이 향후 Renderer에서 다음 문제를 만들 수 있는지 검토하라.

- caption timing
- visual emphasis
- keyword highlighting
- scene transition
- retry 비용
- 일부 문장만 재생성하기 어려움

단순히 "32초니까 길다"라고 하드코딩하지 마라.

문장 경계/의미 단위/렌더링 제어 가능성을 기준으로 segmentation 정책을 설계하라.


# 13. KO_NARRATION segmentation 정책

필요하면 다음 원칙으로 segmentation을 개선한다.

우선순위:

1. 문장 완결성
2. 의미 단위
3. 교육적 강조 단위
4. 지나치게 긴 duration 방지

절대로 이전 11-1에서 해결한 orphan fragment 문제를 재발시키지 마라.

금지:

"-"
"에서"
"가 있습니다."
"그리고,"
같은 깨진 Speech Asset.

영어 단어/IPA 분리 때문에 한국어 문장 자체가 문법적으로 깨져서도 안 된다.


# 14. Hard Duration Cut 금지

문자 수 N자마다 자르기 같은 방식만으로 해결하지 마라.

문장 경계를 우선한다.

긴 한 문장은 의미 clause 단위로만 보조 분할한다.

분할 전후 narration을 이어 읽었을 때 원문의 의미와 문법이 보존되어야 한다.


# 15. Segment Lineage 보존

Speech Asset을 분할하더라도 원래 어느 Production Block / narration에서 나왔는지 추적 가능해야 한다.

필요하면 metadata로 다음을 관리한다.

source_block_id
source_narration_index
segment_index
segment_count

기존 schema를 무리하게 변경하지 않고 JSON metadata로 해결 가능하면 그 방법을 우선 검토한다.


# 16. Cache Key 검토

Prompt 전략이나 segmentation 방식이 바뀌었는데 이전 TTS 파일이 잘못 재사용되어서는 안 된다.

현재 cache key:

model
voice
speech_mode
text
delivery_instruction

을 검토하라.

TTS 결과에 영향을 주는 다음 요소가 실제로 있다면 cache key에 포함해야 한다.

- prompt version
- delivery language
- phoneme demo type
- pronunciation strategy
- relevant audio profile

불필요한 값까지 넣어 cache hit를 파괴하지 마라.


# 17. Prompt Versioning

TTS prompt가 바뀌면 어떤 prompt로 생성된 음성인지 추적 가능해야 한다.

예:

tts_prompt_version = "12.1"

또는 이에 준하는 구조.

Manifest/report에서 확인 가능하게 한다.


# 18. Sample Matrix

FULL 생성 전에 작은 검증 Matrix를 만든다.

최소:

A. KO_NARRATION
- 짧은 한국어 문장 1개
- 기존 SP001 계열의 긴 narration을 새 segmentation 정책으로 나눈 예시

B. EN_NATIVE
- BAG
- CAP

C. ISOLATED PHONEME
- /b/
- /æ/
- /g/

D. BLENDING
- BAG에 해당하는 blending sequence 최소 1개

가능하면 총 실제 API 호출을 최소화한다.

기존 SP003 BAG / SP009 /æ/가 cache 또는 기존 sample로 재사용 가능하면 재생성하지 않는다.


# 19. Sample 생성 후 자동으로 할 수 있는 검증

다음은 자동 검증 가능하다.

- 파일 존재
- WAV decode
- sample rate
- channels
- duration > 0
- empty response 여부
- cache integrity
- manifest consistency
- lineage consistency
- prompt version 존재
- correct voice
- correct speech_mode

하지만 pronunciation accuracy는 자동 PASS하지 않는다.


# 20. Ready for Full Generation Gate

새 Gate를 정의하라.

예:

Ready for Full Generation = YES

가 되려면 최소:

- TTS API contract safe
- prompt compiler safe
- segmentation safe
- no orphan narration fragments
- EN_NATIVE mode safe
- isolated phoneme strategy structurally safe
- blending strategy selected
- sample technical validation pass
- required pronunciation samples human-approved

가 필요하다.

사람 검토가 필요한 sample이 PENDING이면:

Ready for Full Generation = NO

가 정상이다.


# 21. Ready for Rendering과 혼동 금지

12-1의:

Ready for Full Generation

과 기존 12의:

Ready for Rendering

을 구분한다.

흐름:

Production Plan
→ Sample Generation
→ 12-1 Verification
→ Ready for Full Generation
→ FULL Asset Generation
→ pronunciation review
→ Ready for Rendering
→ Renderer

이 구조를 유지한다.


# 22. Integrity Check

기존 12단계 Integrity Check를 삭제/이름변경하지 마라.

12-1에서 필요한 신규 check를 최소 추가한다.

후보:

tts_prompt_version_safe
language_delivery_mode_safe
phoneme_demo_strategy_safe
blending_strategy_safe
speech_segmentation_safe
speech_lineage_safe
cache_prompt_consistency_safe
sample_pronunciation_review_safe

최종 항목 수는 실제 구현에 맞게 결정한다.


# 23. CLI

기존:

python -m research.cli assets

동작을 깨뜨리지 마라.

12-1용 명령이 필요하다면 기존 스타일과 일관되게 추가한다.

예:

python -m research.cli assets-review

또는

python -m research.cli assets --review

현재 CLI 구조를 먼저 읽고 더 자연스러운 쪽을 선택하라.

기존 명령의 의미를 바꾸지 마라.


# 24. Human Review CLI

가능하면 매우 단순한 review workflow를 제공하라.

예:

python -m research.cli assets-review --plan-id 7

출력 예:

SP003
Mode: EN_NATIVE
Text: BAG
File: ...
Review: PENDING

[A] Approve
[R] Reject
[S] Skip

하지만 기존 프로젝트 CLI 철학과 맞지 않거나 과도한 구현이라면
이번 단계에서 억지로 만들지 말고 DB/status 인터페이스까지만 준비한다.

판단 근거를 보고하라.


# 25. 테스트

최소 다음 CASE를 검증한다.

CASE A
KO_NARRATION과 EN_NATIVE prompt 역할이 다르다.

CASE B
EN_NATIVE BAG에 spelling instruction이 들어가지 않는다.

CASE C
EN_PHONEME_DEMO /æ/가 phoneme-only 역할로 컴파일된다.

CASE D
KO_PRONUNCIATION_GUIDE가 native pronunciation으로 오인되지 않는다.

CASE E
delivery_language가 speech mode에 맞다.

CASE F
ISOLATED와 BLENDED_SEQUENCE가 구분된다.

CASE G
blending prompt가 target word를 설명 문장으로 발화하도록 요구하지 않는다.

CASE H
technical validation PASS가 pronunciation APPROVED를 자동 생성하지 않는다.

CASE I
PENDING pronunciation sample이 있으면 Ready for Full Generation=NO.

CASE J
required sample APPROVED 후 Gate가 열릴 수 있다.

CASE K
punctuation-only narration segment가 생성되지 않는다.

CASE L
orphan Korean fragment가 생성되지 않는다.

CASE M
긴 narration이 문장 경계를 우선해 분할된다.

CASE N
분할 후 원문 의미 순서가 유지된다.

CASE O
source block lineage가 유지된다.

CASE P
prompt version 변경 시 stale cache를 재사용하지 않는다.

CASE Q
동일 prompt/config이면 cache hit가 유지된다.

CASE R
word timing을 가짜 생성하지 않는다.

CASE S
기존 PAUSE 3000ms가 변경되지 않는다.

CASE T
기존 viewer_action이 변경되지 않는다.

CASE U
기존 Production Plan이 변경되지 않는다.

CASE V
기존 12 Integrity Check가 보존된다.

CASE W
DRY_RUN은 API 0회.

CASE X
Sample generation만 선택적으로 실행 가능하다.

CASE Y
FULL generation을 이번 교정 작업에서 자동 실행하지 않는다.

CASE Z
기존 CLI 하위 호환 유지.


# 26. 실제 데이터 검증

현재 최신 ready production plan을 사용한다.

현재 보고된 기준은:

Production Plan id=7
Format=EDUCATION
Blocks=8
Speech Assets=44
Charon=44

단, DB에서 실제 최신 상태를 다시 읽고 다르면 DB를 source of truth로 사용한다.

기존 Sample 파일이 존재하면 재사용 가능한지 cache key와 manifest를 먼저 확인한다.

무조건 다시 생성하지 마라.


# 27. API 비용 보호

실제 TTS 호출 전:

1. cache 확인
2. 기존 sample 확인
3. 필요한 sample만 선택
4. 호출 예상 개수 출력

순서로 처리한다.

FULL 44개 생성 금지.

YouTube API는 이번 단계에서 사용할 이유가 없다.


# 28. 절대 하지 말 것

- 05~11 데이터를 수정하지 마라.
- Content Script를 다시 생성하지 마라.
- Blueprint를 다시 생성하지 마라.
- Direction을 다시 생성하지 마라.
- Production Plan 내용을 임의 수정하지 마라.
- FULL 44개 TTS를 생성하지 마라.
- 발음 정확도를 자동으로 꾸며내지 마라.
- word/phoneme timestamp를 가짜 생성하지 마라.
- CAP/BAG 등을 하드코딩한 비즈니스 로직으로 만들지 마라.
- 새 발음 사전을 대규모로 만들지 마라.
- 기존 speech_mode taxonomy를 이유 없이 늘리지 마라.


# 29. 완료 후 실제 Sample 청취가 필요한 파일

작업 완료 후 사람이 직접 들어야 할 파일을 명확하게 출력하라.

최소 다음 역할이 포함되어야 한다.

1. KO_NARRATION
2. EN_NATIVE
3. ISOLATED PHONEME
4. BLENDED PHONEME

각각:

- asset id
- source text
- file path
- speech mode
- voice
- duration
- pronunciation_review

를 보고한다.


# 30. 완료 보고 형식

반드시 한글로 아래 순서대로 보고하라.

1. 수정/추가한 파일
2. 기존 12단계에서 발견한 문제
3. Gemini TTS 공식 문서 확인 결과
4. TTS Prompt 구조 수정 여부
5. Prompt Version
6. KO_NARRATION 최종 정책
7. EN_NATIVE 최종 정책
8. EN_PHONEME_DEMO 최종 정책
9. KO_PRONUNCIATION_GUIDE 최종 정책
10. Charon 언어별 사용 방식
11. delivery_language 처리 방식
12. isolated phoneme 생성 전략
13. blending 생성 전략
14. 비교한 blending 전략
15. 최종 선택한 blending 전략과 이유
16. Speech Asset segmentation 정책
17. 기존 SP001 같은 긴 narration 처리 결과
18. orphan fragment 방지 결과
19. lineage 보존 방식
20. cache key 변경 여부와 이유
21. 기존 cache 하위 호환 처리
22. pronunciation_review 상태 구조
23. Human Review 대상 정책
24. 실제 Sample Matrix
25. 실제 신규 Gemini TTS 호출 횟수
26. cache hit 횟수
27. 각 Sample 실제 duration
28. 각 Sample technical validation 결과
29. 각 Sample pronunciation_review 상태
30. BAG blending 실제 생성 여부
31. CAP 등 다른 단어에 일반화 가능한 구조인지
32. word timing 처리 상태
33. PAUSE 3000ms 보존 여부
34. viewer_action 보존 여부
35. 기존 Production Plan 불변 여부
36. 신규 Integrity Check 목록
37. 전체 Integrity Check 결과
38. Ready for Full Generation YES/NO
39. Ready for Rendering 상태와 구분
40. 추가한 테스트 수
41. 전체 테스트 결과
42. 기존 05~12 회귀 여부
43. CLI 하위 호환 여부
44. Gemini TTS API 실제 사용량
45. YouTube API 사용량
46. 사람이 지금 직접 들어야 할 Sample 파일 목록
47. 발견된 제한사항


# 31. 최종 성공 기준

이번 단계의 성공은

"모든 음성을 생성했다"

가 아니다.

성공 기준은:

"FULL 생성 전에 어떤 방식으로 한국어 설명, 원어민 단어,
개별 phoneme, blending phoneme를 생성해야 하는지 검증 가능한 구조가 생겼고,
잘못된 발음이 대량 생성되는 것을 Gate가 막을 수 있다."

이다.

사람의 실제 청취 검토가 끝나지 않았다면

Ready for Full Generation: NO

라고 정직하게 보고하라.

그것은 실패가 아니라 이번 단계의 정상적인 안전 동작이다.