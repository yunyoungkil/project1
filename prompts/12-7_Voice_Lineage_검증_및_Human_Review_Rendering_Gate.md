# 12-7. Voice Lineage 검증 및 Human Review Rendering Gate

## 0. 이번 작업의 목적

12-6까지 FULL Asset Generation이 완료되었다.

현재 상태:

- Production Plan ID: 7
- Source Speech Assets: 44
- Generation Units: 51
- FULL Generation: 완료
- 최종 REUSE: 51
- 남은 GENERATE: 0
- BLOCKED: 0
- Manifest: complete
- Technical Validation: pass
- Ready for Full Generation: YES
- Ready for Rendering: NO

Ready for Rendering이 NO인 이유는
Human Pronunciation/Tone Review PENDING asset이 남아 있기 때문이다.

현재 사람이 직접 청취한 결과:

SP016 BAT: 좋음
SP024 BAT blend: 좋음
SP037 MAP blend: 좋음
SP003 BAG tone: 좋음
SP029 MAP tone: 좋음
SP009 /æ/: 좋음

하지만 다음 3개 isolated phoneme은
사람 청취상 "여자 목소리처럼 들리는 것 같다"는 의문이 발생했다.

SP021 /t/
SP032 /m/
SP035 /p/

현재 시스템 정책상 EN_PHONEME_DEMO는
Charon으로 생성되어야 한다.

따라서 이번 단계에서는
사람의 음색 인상만으로 승인/반려하지 않고
실제 Voice Lineage를 코드/DB/API metadata 기준으로 추적한다.

핵심 질문:

"SP021 /t/, SP032 /m/, SP035 /p/가 실제 API 요청에서 Charon으로 생성되었는가?"

이번 단계의 목적:

1. 해당 3개 asset의 실제 voice_name lineage 검증
2. 실제 Gemini TTS request payload가 Charon을 사용했는지 검증
3. generated_assets metadata와 실제 요청 정책 일치 여부 확인
4. voice mismatch가 있으면 원인 수정
5. 실제 Charon이었다면 isolated phoneme 특성으로 음색이 다르게 들릴 수 있음을 구조적으로 기록
6. 이미 사람이 승인한 Human Review 결과를 DB에 반영
7. 남은 PENDING blocker를 정확히 정리
8. Ready for Rendering Gate를 다시 계산

새로운 TTS 실험이나 FULL 재생성은 기본적으로 하지 않는다.

---

## 1. 절대 원칙

이번 단계에서 하지 말 것:

- Production Plan 수정
- Speech Asset source_text 수정
- 새로운 EN_NATIVE 전략 추가
- Blending 전략 변경
- Charon → Zephyr 자동 변경
- /t/, /m/, /p/를 여자 목소리로 재생성
- FULL 전체 재생성
- Renderer 구현
- FFmpeg 영상 생성
- 기존 APPROVED review 상태 초기화
- 사람 청취 없이 pronunciation/tone 자동 APPROVED
- voice metadata만 보고 발음 품질 자동 승인
- YouTube API 호출

이번 단계는:

Voice Lineage 검증
+
Human Review 반영
+
Rendering Gate 재계산

이다.

---

## 2. 현재 Voice 정책

현재 확정 Voice 정책:

KO_NARRATION
→ Charon

EN_NATIVE
→ Charon

EN_PHONEME_DEMO
→ Charon

KO_PRONUNCIATION_GUIDE
→ Charon

PODCAST female
→ Zephyr

PODCAST male
→ Charon

현재 EDUCATION Plan에는 Zephyr가 사용되면 안 된다.

즉 SP021/SP032/SP035가 실제 Zephyr로 생성됐다면
명백한 voice-casting bug다.

---

## 3. 검증 대상 3개

필수 검증:

SP021
speech_mode = EN_PHONEME_DEMO
target = /t/

SP032
speech_mode = EN_PHONEME_DEMO
target = /m/

SP035
speech_mode = EN_PHONEME_DEMO
target = /p/

각각 다음을 추적한다.

1. speech_assets.voice
2. generated_assets.voice_name
3. generated_assets.metadata_json
4. generation_method
5. cache_key
6. prompt metadata
7. 실제 Gemini request payload를 구성한 함수
8. voiceName을 결정하는 코드 경로
9. asset_generation_run
10. 실제 생성 파일

---

## 4. Voice Lineage 정의

Voice Lineage는 다음 흐름으로 추적 가능해야 한다.

Production Planner Speech Asset
↓
speech_mode
↓
voice policy
↓
build_tts_prompt / synthesize_asset
↓
GeminiTTSClient.synthesize
↓
REST request payload
↓
speechConfig.voiceConfig.prebuiltVoiceConfig.voiceName
↓
generated_assets.voice_name
↓
WAV file

모든 단계가 Charon을 가리켜야 한다.

---

## 5. 실제 REST payload 확인

현재 tts_client.py에서 실제 Gemini REST request payload를 만드는 코드를 추적한다.

최소 다음 구조가 실제 요청에 들어가는지 확인:

speechConfig:
  voiceConfig:
    prebuiltVoiceConfig:
      voiceName: "Charon"

주의:

코드상 default가 Charon이라고 적혀 있는 것만 확인하고 끝내지 않는다.

SP021/SP032/SP035 실제 생성 시 사용된 voice metadata와
현재 request builder가 실제로 Charon을 넣는지 둘 다 확인한다.

가능하면 API key를 노출하지 않는 범위에서
request payload의 safe subset을 report에 출력한다.

예:

{
  "model": "gemini-3.1-flash-tts-preview",
  "voiceName": "Charon",
  "speechMode": "EN_PHONEME_DEMO",
  "assetId": "SP021"
}

API key / Authorization header 출력 금지.

---

## 6. generated_assets 검증

SP021/SP032/SP035의 최신 generated_assets row를 조회한다.

각각 최소 확인:

asset_id
source_speech_asset_id
speech_mode
voice_name
generation_method
status
file_path
duration_ms
metadata_json
validation_json

기대:

voice_name = Charon

speech_mode = EN_PHONEME_DEMO

status = AVAILABLE 또는 REUSED

technical validation = pass

---

## 7. Cache 재사용 lineage 확인

혹시 SP021/SP032/SP035가
기존 다른 voice asset을 잘못 cache hit한 것은 아닌지 확인한다.

cache key에 voice가 포함되는지 검증한다.

반드시:

Charon asset
≠
Zephyr asset

서로 다른 cache key를 가져야 한다.

테스트로 확인:

same text /t/
same speech mode
voice=Charon

vs

same text /t/
voice=Zephyr

→ cache key different

이 조건이 없다면 즉시 수정한다.

---

## 8. Voice mismatch 판정

다음 중 하나라도 발생하면 voice mismatch로 판정:

- speech_assets 기대 voice = Charon인데 generated_assets.voice_name = Zephyr
- request payload voiceName = Zephyr
- cache가 다른 voice asset을 재사용
- metadata voice와 실제 request voice가 불일치
- EN_PHONEME_DEMO에 Zephyr가 선택되는 branch 존재

이 경우:

1. 원인 수정
2. 해당 3개 asset만 REGENERATE_REQUIRED
3. 전체 FULL 재생성 금지
4. 정확히 필요한 3개만 Charon으로 재생성
5. 재생성 후 다시 PENDING Human Review

단, 실제 mismatch가 있을 때만 재생성한다.

---

## 9. 실제 Charon이었다면

만약 SP021/SP032/SP035 모두:

voice_name = Charon
request payload = Charon
cache identity = Charon
voice policy = Charon

으로 확인되면
voice-casting bug는 아니다.

이 경우 다음 사실을 기록한다.

isolated phoneme은:

- duration이 매우 짧고
- 일반 문장과 발성 방식이 다르며
- Gemini가 목표 음가를 강조하면서
  pitch/timbre/attack이 달라질 수 있어

같은 Charon이라도 일반 narration/word pronunciation보다
다른 음색처럼 들릴 수 있다.

단:

이 설명만으로 발음 자산을 자동 APPROVED하지 않는다.

사람이 "교육용으로 좋음"이라고 직접 판단한 결과가 별도로 필요하다.

---

## 10. 현재 Human Review 결과 반영

다음 사람 청취 결과를 실제 DB에 반영한다.

SP016 BAT
pronunciation_review = APPROVED

SP021 /t/
현재 보류
voice lineage 검증 후 결정

SP032 /m/
현재 보류
voice lineage 검증 후 결정

SP035 /p/
현재 보류
voice lineage 검증 후 결정

SP024::DIRECT_SEQUENCE
pronunciation_review = APPROVED

SP037::DIRECT_SEQUENCE
pronunciation_review = APPROVED

SP003 BAG
tone_consistency_review = APPROVED

SP029 MAP
tone_consistency_review = APPROVED

SP009 /æ/
pronunciation_review = APPROVED

이미 APPROVED라면 중복 mutation하지 않는다.

---

## 11. BAT tone review

SP016 BAT에 대해 사용자가:

"좋음"

이라고 평가했다.

현재 SP016이 EN_NATIVE이고
tone_consistency_review가 PENDING이면
이 "좋음"이 발음과 tone 모두에 대한 승인으로 충분한지
현재 review 정책을 확인한다.

이번 대화에서 사용자가 BAT을 별도 문제 없이 좋다고 평가했으므로
일반 EN_NATIVE review workflow가 pronunciation + tone을 별도 요구한다면:

pronunciation_review = APPROVED
tone_consistency_review = APPROVED

로 반영하는 것이 합리적이다.

단 현재 Gate가 일반 EN_NATIVE에 tone approval을 필수로 하지 않는다면
불필요한 정책 변경은 하지 않는다.

실제 기존 정책을 확인한 뒤 최소 변경한다.

---

## 12. /t/, /m/, /p/ 승인 정책

Voice Lineage가 Charon으로 정상 확인되면
사용자의 기존 청취 평가는:

SP021 /t/: 좋음
SP032 /m/: 좋음
SP035 /p/: 좋음

이었다.

그러나 이후 사용자가:

"여자 음성 같은데?"

라고 의문을 제기했다.

따라서 이 3개는 이번 단계에서 자동 APPROVED하지 말고
voice lineage 결과를 먼저 보고한다.

voice lineage가 정상 Charon이면:

Human Review Status:
PENDING_CONFIRMATION

또는 기존 taxonomy에 가장 가까운 PENDING 유지.

그 다음 사용자에게:

"실제로 Charon으로 생성된 것이 확인되었습니다.
현재 파일을 그대로 교육용으로 승인할지,
Charon으로 새로 한 번 재생성 비교할지"

결정하게 한다.

새 review state를 만들 필요가 없다면 PENDING 유지.

---

## 13. 불필요한 재생성 금지

voice lineage가 정상이라면
SP021/SP032/SP035를 단순히 여자처럼 들린다는 인상만으로
자동 재생성하지 않는다.

이유:

Gemini TTS는 생성형 모델이라
같은 Charon으로 재생성해도 다른 timbre/intonation이 나올 수 있고,
재생성이 반드시 더 "남성적"인 결과를 보장하지 않는다.

재생성은 사람 선택 후에만 수행.

---

## 14. Human Review Package 재계산

Voice Lineage 검증과 review 반영 후
Human Listening Required 목록을 다시 계산한다.

이미 승인 완료된 asset은 목록에서 제외.

예상:

SP003 → tone 승인 후 제외
SP009 → 승인 후 제외
SP016 → 승인 후 제외
SP024 → 승인 후 제외
SP029 → tone 승인 후 제외
SP037 → 승인 후 제외

남을 가능성이 있는 항목:

SP021
SP032
SP035

단 실제 DB source of truth를 사용한다.

---

## 15. Ready for Rendering Gate

review 반영 후 Gate를 다시 계산한다.

다음 조건이 모두 충족되면:

Ready for Rendering = YES

- 51 Generation Units materialized
- technical validation pass
- manifest complete
- failed active asset 없음
- required pronunciation review complete
- required tone review complete
- active strategy plan 일치
- Production Plan integrity 유지

하지만 SP021/SP032/SP035가 PENDING이면:

Ready for Rendering = NO

가 정상이다.

Blocker를 정확히 3개 asset으로 보고한다.

---

## 16. 신규 Integrity Check

기존 51개 Check 이름/의미를 변경하지 않는다.

필요하면 최소 다음을 추가한다.

### voice_lineage_safe

speech asset → generated asset → request policy의 voice가 일치하는지 확인.

### phoneme_voice_policy_safe

EN_PHONEME_DEMO가 EDUCATION Plan에서 Charon인지 확인.

### voice_cache_isolation_safe

동일 text라도 voice가 다르면 cache key가 다름.

### human_review_application_safe

사람 승인 결과가 정확한 variant에만 적용되고
다른 asset으로 전이되지 않음.

### rendering_gate_blockers_exact

Ready for Rendering=NO일 때
실제 PENDING required review 목록과 blocker 목록이 일치.

이미 동등 check가 있으면 재사용하고 중복 구현하지 않는다.

---

## 17. 테스트

최소 다음 테스트를 추가한다.

CASE A
EN_PHONEME_DEMO voice policy = Charon

CASE B
KO_NARRATION voice policy = Charon

CASE C
EN_NATIVE voice policy = Charon

CASE D
Podcast female = Zephyr

CASE E
Charon /t/ cache key != Zephyr /t/ cache key

CASE F
SP021 metadata voice=Charon → pass

CASE G
voice metadata mismatch → fail

CASE H
request payload voice mismatch → fail

CASE I
generated asset voice mismatch → fail

CASE J
voice lineage 정상인데 사람 review PENDING → 자동 APPROVED 금지

CASE K
SP016 approval이 올바른 variant에만 반영

CASE L
SP024 DIRECT_SEQUENCE approval 보존

CASE M
SP037 DIRECT_SEQUENCE approval 보존

CASE N
SP009 /æ/ approval 보존

CASE O
SP003 tone approval 보존

CASE P
SP029 tone approval 보존

CASE Q
remaining review list는 실제 PENDING asset만 포함

CASE R
Ready for Rendering blocker count 정확

CASE S
Production Plan 불변

CASE T
PAUSE 3000ms 불변

CASE U
viewer_action 불변

CASE V
기존 51 Integrity Check 회귀 없음

CASE W
전체 기존 테스트 회귀 없음

---

## 18. 실제 DB 검증

실제 DB에서 SP021/SP032/SP035를 조회한다.

보고서에 각 asset별로 다음 표를 만든다.

Asset:
SP021

Target:
/t/

Speech Mode:
EN_PHONEME_DEMO

Expected Voice:
Charon

speech_assets voice:
...

generated_assets voice_name:
...

request policy voice:
...

cache key includes voice:
YES/NO

Voice Lineage:
PASS/FAIL

Pronunciation Review:
PENDING/APPROVED/...

같은 형식으로 SP032, SP035도 보고.

---

## 19. 실제 API 호출 정책

Voice Lineage 확인만으로 충분하다면:

Gemini TTS API 신규 호출 = 0

이어야 한다.

voice mismatch가 실제 발견될 경우에만
해당 asset을 재생성할 수 있다.

하지만 자동 재생성하지 말고
먼저 mismatch 결과를 보고하고 멈춘다.

즉 기본 목표:

Gemini TTS API = 0

YouTube API = 0

---

## 20. CLI

기존 assets-review --set / --set-tone 기능을 재사용한다.

새 review CLI를 만들지 않는다.

Voice Lineage 출력용 별도 명령이 꼭 필요한지 먼저 검토한다.

필요 없다면 report/debug 함수로 충분.

불필요한 CLI 확장 금지.

---

## 21. 12-6 Git 상태

12-6 변경사항이 아직 commit되지 않은 상태라고 보고되었다.

이번 작업 시작 전:

git status

를 확인한다.

12-6 변경사항을 잃지 않는다.

12-7 수정은 12-6 위에 이어서 진행 가능하지만
완료 후 어떤 파일이 12-6/12-7에서 변경되었는지 보고한다.

자동 commit/push는 사용자 요청 없이 하지 않는다.

---

## 22. 완료 보고 형식

반드시 한글로 다음 순서대로 보고한다.

1. 수정/추가한 파일
2. SP021 /t/ expected voice
3. SP021 speech_assets voice
4. SP021 generated_assets voice
5. SP021 request policy voice
6. SP021 Voice Lineage 결과
7. SP032 /m/ expected voice
8. SP032 speech_assets voice
9. SP032 generated_assets voice
10. SP032 request policy voice
11. SP032 Voice Lineage 결과
12. SP035 /p/ expected voice
13. SP035 speech_assets voice
14. SP035 generated_assets voice
15. SP035 request policy voice
16. SP035 Voice Lineage 결과
17. 세 asset 중 Zephyr 실제 사용 여부
18. cache key에 voice 포함 여부
19. Charon/Zephyr cache isolation 결과
20. voice mismatch 버그 존재 여부
21. mismatch가 있었다면 원인
22. mismatch가 없었다면 왜 다른 음색처럼 들릴 수 있는지
23. 이번 단계 실제 Gemini TTS 신규 호출 수
24. SP016 BAT review 반영 결과
25. SP024 BAT blend review 반영 결과
26. SP037 MAP blend review 반영 결과
27. SP003 BAG tone review 반영 결과
28. SP029 MAP tone review 반영 결과
29. SP009 /æ/ review 반영 결과
30. SP021 review 상태
31. SP032 review 상태
32. SP035 review 상태
33. Human Listening Required 수정 전/후
34. 남은 review blocker 목록
35. Ready for Rendering 결과
36. Ready for Rendering이 NO라면 정확한 blocker
37. 신규 Integrity Check
38. 전체 Integrity Check 결과
39. 신규 테스트 수
40. 전체 테스트 수
41. 기존 테스트 회귀 여부
42. PAUSE 3000ms 보존 여부
43. viewer_action 보존 여부
44. Production Plan 불변 여부
45. 05~11 DB 불변 여부
46. YouTube API 호출 수
47. 실제 TTS 재생성 여부
48. 다음 사용자 결정이 필요한 항목
49. 발견된 제한사항

---

## 23. 성공 기준

이번 단계 성공 조건:

- SP021/SP032/SP035의 실제 Voice Lineage를 끝까지 추적
- expected voice = Charon 확인
- generated asset voice 확인
- request voice 확인
- cache voice isolation 확인
- Zephyr 오사용 여부 판정
- voice mismatch가 없으면 불필요한 재생성 안 함
- 이미 승인된 Human Review 결과 DB 반영
- remaining PENDING 목록 정확히 계산
- Ready for Rendering을 정직하게 재계산
- 사람 승인 없이 /t/, /m/, /p/ 자동 APPROVED 금지
- Gemini TTS 신규 호출 기본 0
- YouTube API 0
- Production Plan 불변
- PAUSE/viewer_action 불변
- 기존 테스트 회귀 없음

이번 단계의 핵심은:

"여자처럼 들린다"는 인상만으로 voice를 추측하는 것이 아니라,
실제 생성 lineage에서 어떤 voice가 사용됐는지 확인하는 것이다.

Voice Lineage가 Charon으로 정상이라면
그 사실과 Human Listening 판단을 분리한다.

그 다음 사용자가 해당 /t/, /m/, /p/ 자산을 그대로 승인할지
재생성 비교할지를 결정하게 한다.