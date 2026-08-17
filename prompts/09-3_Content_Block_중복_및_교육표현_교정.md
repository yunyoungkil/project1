# 09-3단계 — Content Block 중복 및 교육 표현 교정

## 0. 이번 작업의 목적

09-2단계에서 Content Script를 포맷 중립 구조로 변경했다.

현재 전체 구조와 방향은 정상이며 다음 사항도 이미 만족한다.

- Content Script는 "무엇을 가르칠 것인가"만 정의한다.
- EDUCATION / CLIP ANALYSIS / HYBRID / PODCAST를 선택하지 않는다.
- 카메라/편집/자막/화면 구성 등 제작 지시를 하지 않는다.
- Content Block 구조가 존재한다.
- ready_for_direction이 존재한다.
- 기존 Educational Integrity Check 15개가 유지된다.
- format_neutrality_safe가 존재한다.
- BAG → BAT → MAP → CAP Example Ladder가 유지된다.
- 발음 정확성 및 Scope 보호가 적용되어 있다.
- 10단계 Video Director가 읽을 수 있는 media_affinity가 존재한다.

따라서 이번 09-3은 09-2를 다시 설계하는 작업이 아니다.

이번 작업의 목적은 딱 두 가지다.

1. Content Block의 의미적 중복 제거 또는 명시적 관계 처리
2. 영어 글자에 하나의 고정된 "고유한 소리"가 있는 것처럼 오해할 수 있는 교육 표현 교정

불필요한 리팩터링은 하지 않는다.

---

# 1. 현재 실제 산출물에서 확인된 문제

현재 `script_2026-08-17.md` 기준으로 다음 중복이 존재한다.

## 문제 A — Mini Success 중복

CB06:

- learning_function: MINI_SUCCESS
- CAP 사용
- Viewer Action: CAP 직접 읽기
- Thinking Time: 3초
- CAP에서 C=/k/ 안내
- 정답 확인

CB08:

- learning_function: MINI_SUCCESS
- CAP 사용
- Viewer Action: CAP 직접 읽기
- Thinking Time: 3초
- CAP에서 C=/k/ 안내
- 정답 확인

두 Block의 교육 목적과 내용이 사실상 동일하다.

10단계 Video Director가 Content Blocks를 그대로 Scene 후보로 해석할 경우,
같은 CAP 퀴즈/도전 장면을 두 번 제작할 위험이 있다.

---

## 문제 B — RECAP 중복

CB07:

- BAG/BAT/MAP/CAP 복습
- 소리 조합 원리 정리
- 다음 모음 학습 예고

CB09:

- BAG/BAT/MAP/CAP 복습
- 소리 조합 원리 정리
- 다음 학습 주제 예고

base_narration도 사실상 동일하다.

따라서 10단계에서 동일한 Ending/Recap Scene이 중복 생성될 위험이 있다.

---

# 2. 중복 해결의 핵심 원칙

중복 해결을 단순 문자열 비교 문제로 만들지 않는다.

Content Block의 의미를 기준으로 판단해야 한다.

다음 요소를 함께 사용한다.

- learning_function
- purpose
- required_content
- viewer_action
- thinking_time_seconds
- prerequisite_blocks
- base_narration

단, Gemini에게만 중복 판정을 맡기지 않는다.

가능한 부분은 결정론적 코드로 보호한다.

---

# 3. 가장 중요한 구조 원칙

같은 교육 이벤트를 나타내는 Content Block은
10단계에 독립적인 두 개의 제작 단위로 전달되어서는 안 된다.

특히 다음과 같은 경우 하나의 canonical block으로 처리해야 한다.

예:

Section 내부:

MINI_SUCCESS
CAP 직접 읽기
3초 생각
정답 공개

그리고 별도 Mini Success:

MINI_SUCCESS
CAP 직접 읽기
3초 생각
정답 공개

이 두 개가 동일한 학습 이벤트라면
두 개의 독립 Block으로 취급하지 않는다.

---

# 4. 권장 구현 방식

가능하면 Content Block을 생성할 때 중복 자체를 만들지 않는 방식을 우선한다.

즉:

Opening
Section 1
Section 2
...
Section N
Mini Success
Ending

을 기계적으로 모두 별도 Block으로 추가하기 전에,

Mini Success가 이미 Section 안에 포함되어 있는지 확인한다.

이미 해당 Section이 동일한 Mini Success를 구현하고 있다면
별도 Mini Success Block을 추가하지 않는다.

Ending도 마찬가지다.

마지막 Section이 이미 RECAP + NEXT QUESTION 역할을 완전히 수행하고 있다면
동일한 narration을 가진 별도 Ending Block을 추가하지 않는다.

---

# 5. 기존 Block을 삭제하는 방식에 대한 주의

기존 데이터베이스 row나 과거 script 데이터를 직접 파괴하지 않는다.

새 Content Script 생성 시
정상화된 Content Block 구조가 생성되도록 한다.

과거 `video_scripts` row는 그대로 두어도 된다.

필요하다면 신규 생성 결과에만 적용한다.

---

# 6. duplicate_of 방식이 필요한 경우

구조상 Block을 반드시 보존해야 하는 경우에는 다음 필드를 추가할 수 있다.

예:

{
  "content_block_id": "CB08",
  "duplicate_of": "CB06",
  "direction_eligible": false
}

canonical block:

{
  "content_block_id": "CB06",
  "duplicate_of": null,
  "direction_eligible": true
}

그러나 이 방식은 **중복 Block 자체를 제거할 수 없는 경우에만 사용한다.**

우선순위는:

1. 생성 단계에서 중복 Block을 만들지 않기
2. 불가피한 경우 duplicate_of 관계 명시

이다.

10단계가 같은 교육 이벤트를 두 번 제작하지 않는 것이 최종 목적이다.

---

# 7. direction_eligible

필요하다면 Content Block에 다음 필드를 추가한다.

`direction_eligible: true | false`

의미:

true
→ 10단계 Video Director가 독립적인 연출/Scene 단위로 사용할 수 있음

false
→ 다른 canonical block의 파생/중복 정보이므로 독립 Scene으로 만들면 안 됨

단, 중복 Block 자체를 생성하지 않는 구조라면 이 필드를 억지로 추가할 필요는 없다.

불필요한 스키마 확장은 피한다.

---

# 8. 교육 표현 문제 — "고유한 소리"

현재 Core Answer:

> 영어 단어는 알파벳 '이름'이 아니라 각 글자가 내는 고유한 '소리'를 순서대로 이어 붙여 읽기 때문입니다.

이 표현은 초보자가 다음처럼 오해할 수 있다.

> 알파벳 하나에는 언제나 하나의 고정된 소리가 있다.

하지만 현재 영상의 Scope는:

- 단모음 a
- 기초 CVC
- BAG / BAT / MAP / CAP

이다.

따라서 글자의 소리를 전체 영어에 일반화하지 않는다.

---

# 9. Core Answer 교정 원칙

다음과 같은 방향으로 표현한다.

BAD:

"각 글자가 내는 고유한 소리"

BAD:

"알파벳마다 정해진 소리가 있다"

BAD:

"B는 /b/ 소리다"

BAD:

"C는 /k/ 소리다"

GOOD:

"각 글자가 이 단어에서 나타내는 소리"

GOOD:

"오늘 다루는 단어에서 글자가 나타내는 소리"

GOOD:

"BAG에서 B는 /b/ 소리를 냅니다."

GOOD:

"이 단어 CAP에서는 C가 /k/ 소리를 냅니다."

핵심은:

letter = fixed sound

라는 등가 관계를 만들지 않는 것이다.

---

# 10. 기존 example_scope_safe와 연결

08-1/09-1에서 이미 `example_scope_safe`가 존재한다.

이번 작업에서 같은 목적의 새로운 체크를 중복해서 만들지 않는다.

가능하면 기존:

- example_scope_safe
- phoneme_explanation_safe
- narration_scope_safe

를 재사용 또는 최소 확장한다.

단, 현재 `Core Answer`가 기존 체크 범위 밖이라면
Core Answer도 검사 대상 텍스트에 포함하도록 확장할 수 있다.

기존 체크의 의미를 깨지 않는다.

---

# 11. 신규 결정론적 체크 권장

필요하다면 다음 Integrity Check를 추가한다.

`content_block_uniqueness_safe`

목적:

10단계로 전달되는 direction-eligible Content Block 사이에
명백하게 동일한 교육 이벤트가 중복되지 않았는지 확인한다.

판정 대상 예:

- 동일 learning_function
- 동일 example word
- 동일 viewer_action
- 동일 thinking_time
- required_content의 높은 중복
- base_narration의 높은 중복

단순히 learning_function이 같다고 중복 처리하면 안 된다.

예:

BAG demonstration
BAT reinforcement

은 둘 다 비슷한 소리 조합을 다루지만
교육 역할이 다르므로 중복이 아니다.

---

# 12. RECAP 중복 판정 주의

RECAP도 무조건 하나만 허용하는 것은 아니다.

중간 recap과 final recap은 존재할 수 있다.

그러나 다음이 동시에 거의 동일하면 중복으로 판단할 수 있다.

- 같은 example set
- 같은 핵심 원리
- 같은 next topic
- base_narration 거의 동일
- viewer_action 없음
- 바로 인접하거나 별도 Ending으로 반복

현재 CB07/CB09 사례는 이 문제에 해당한다.

---

# 13. Content Block ID

중복 제거 후 Content Block ID는 가능하면 다시 연속적으로 생성한다.

예:

CB01
CB02
CB03
...
CB07

중간 번호가 빠져도 기능적으로 문제는 없지만
사람이 리포트를 읽기 쉽게 연속 번호를 권장한다.

단, DB의 과거 Content Block ID와 호환성을 위해
재번호화가 위험하다면 기존 ID 유지도 허용한다.

안전성을 우선한다.

---

# 14. Prerequisite Blocks 무결성

중복 Block을 제거하면 prerequisite_blocks가 깨질 수 있다.

예:

CB09 prerequisite = CB08

인데 CB08이 제거된다면
그대로 두면 안 된다.

중복 제거 후 반드시:

- 존재하지 않는 Block ID 참조 없음
- 자기 자신 참조 없음
- 순환 참조 없음

을 확인한다.

필요하면 canonical block으로 dependency를 재연결한다.

---

# 15. Content Block 순서

최종 Content Blocks는 교육 흐름을 그대로 유지해야 한다.

현재 학습 흐름:

Problem Recognition
↓
Core Explanation
↓
BAG Demonstration
↓
BAT Reinforcement
↓
MAP Transfer
↓
CAP Mini Success
↓
Recap / Next Question

이 흐름은 유지한다.

중복 제거 때문에 교육 순서를 변경하지 않는다.

---

# 16. BAG / BAT / MAP / CAP 보존

이번 수정에서 Example Ladder를 변경하지 않는다.

반드시:

BAG
→ BAT
→ MAP
→ CAP

순서를 유지한다.

음소:

BAG
B /b/ + A /æ/ + G /g/

BAT
B /b/ + A /æ/ + T /t/

MAP
M /m/ + A /æ/ + P /p/

CAP
C /k/ + A /æ/ + P /p/

기존 08-1/09/09-1 정확성 원칙을 그대로 유지한다.

---

# 17. Mini Success 보존

중복을 제거한다고 CAP Mini Success 자체를 제거하면 안 된다.

반드시 한 번은 존재해야 한다.

필수 요소:

- CAP
- Viewer 직접 읽기
- 정답 선공개 금지
- Thinking Time 3초
- C /k/
- A /æ/
- P /p/
- 이후 정답 확인

즉:

"두 번 → 한 번"

으로 만드는 것이 목적이지

"두 번 → 없음"

으로 만드는 것이 아니다.

---

# 18. Retention Intent 보존

중복 제거 후에도 각 주요 교육 단계의 retention intent를 유지한다.

특히:

BAG → demonstration/visual change
BAT → contrast
MAP → new example / prediction
CAP → mini success / challenge
Ending → next question

구조가 사라지지 않아야 한다.

---

# 19. Media Affinity 보존

09-2의 media_affinity 구조를 변경하지 않는다.

8개 신호:

- visualization
- real_world_clip
- dialogue
- audio_demonstration
- replay
- comparison
- interaction
- storytelling

를 그대로 유지한다.

이번 단계에서 이 값을 이용해 포맷을 선택하지 않는다.

특히:

EDUCATION
CLIP ANALYSIS
HYBRID
PODCAST

중 어느 것도 선택하지 않는다.

그 판단은 10단계 Video Director의 책임이다.

---

# 20. Format Neutrality 유지

09-3에서도 다음을 절대 생성하지 않는다.

- selected_format
- recommended_format
- production_format
- EDUCATION 선택
- CLIP ANALYSIS 선택
- HYBRID 선택
- PODCAST 선택
- 카메라 지시
- 화면 배치
- 자막 디자인
- 색상
- Zoom
- B-roll
- 실제 클립 검색 요구
- Mia / Leo 등 Podcast 화자
- 편집 프로그램 지시

09는 여전히 WHAT 단계다.

10이 HOW 단계다.

---

# 21. 기존 Integrity Check 보존

09-2 기준 기존 16개 체크의 이름과 의미를 삭제하거나 변경하지 않는다.

현재:

title_preserved
thumbnail_preserved
answers_core_question
promise_matches_scope
example_ladder_preserved
phoneme_explanation_safe
example_scope_safe
no_scope_creep
mini_success_present
audio_first_usable
no_false_guarantee
narration_scope_safe
no_unverified_rule
ipa_not_taught_as_memorization
ending_resolves_opening
format_neutrality_safe

전부 유지한다.

필요하다면:

content_block_uniqueness_safe

를 추가한다.

총 17개가 될 수 있다.

---

# 22. Ready for Direction Gate

중복 Content Block이 실제로 10단계에서 이중 제작을 일으킬 수준이면
ready_for_direction=NO가 되어야 한다.

권장 critical check:

- format_neutrality_safe
- content_block_uniqueness_safe
- 기존 교육 정확성 critical checks

즉,

10단계가 안전하게 해석할 수 없는 Content Script를
YES로 넘기지 않는다.

---

# 23. Script/Content Score

이번 작업 때문에 기존 점수 공식을 임의로 바꾸지 않는다.

현재 실제 점수:

Hook 100
Clarity 100
Scope Alignment 100
Example Alignment 100
Audio-first 100
Retention 69.9
Total 95.5

중복 제거만으로 점수를 억지로 올리거나 내리지 않는다.

필요하다면 uniqueness는 점수가 아니라 Integrity Gate로 처리한다.

---

# 24. 테스트 — CASE A

입력:

CB06 = CAP Mini Success
CB08 = 동일 CAP Mini Success

기대:

독립 direction block은 1개만 존재

PASS

---

# 25. 테스트 — CASE B

입력:

CB07 = BAG/BAT/MAP/CAP recap
CB09 = 사실상 동일 recap

기대:

독립 recap block은 1개만 존재

PASS

---

# 26. 테스트 — CASE C

입력:

BAG demonstration
BAT reinforcement

둘 다 sound blending 관련

기대:

서로 다른 교육 기능이므로 중복으로 제거하지 않음

PASS

---

# 27. 테스트 — CASE D

입력:

중간 recap
final recap

내용과 목적이 실제로 다름

기대:

둘 다 유지 가능

PASS

---

# 28. 테스트 — CASE E

중복 Block 제거 후 prerequisite_blocks 검사

기대:

존재하지 않는 block reference 0개

PASS

---

# 29. 테스트 — CASE F

Core Answer:

"각 글자가 내는 고유한 소리"

기대:

안전하지 않은 표현으로 탐지 또는 재생성

FAIL → 교정

---

# 30. 테스트 — CASE G

Core Answer:

"각 글자가 이 단어에서 나타내는 소리를 순서대로 이어 붙여 읽습니다."

기대:

PASS

---

# 31. 테스트 — CASE H

Narration:

"B는 /b/ 소리입니다."

기대:

범위 없는 일반화이므로 FAIL

---

# 32. 테스트 — CASE I

Narration:

"BAG에서 B는 /b/ 소리를 냅니다."

기대:

PASS

---

# 33. 테스트 — CASE J

Narration:

"이 단어 CAP에서는 C가 /k/ 소리를 냅니다."

기대:

PASS

---

# 34. 테스트 — CASE K

중복 제거 후 Example Ladder

BAG → BAT → MAP → CAP

기대:

순서와 단어 모두 그대로

PASS

---

# 35. 테스트 — CASE L

CAP Mini Success 중복 제거

기대:

mini_success_present = pass

Thinking Time = 3초 유지

PASS

---

# 36. 테스트 — CASE M

Content Block에 다음이 들어감:

selected_format = "EDUCATION"

기대:

format_neutrality_safe = fail

기존 동작 유지

---

# 37. 테스트 — CASE N

media_affinity.real_world_clip = high

기대:

포맷 선택 없이 그대로 저장

PASS

---

# 38. 테스트 — CASE O

Content Block 중복이 존재하지만
direction_eligible=true인 상태로 두 Block 모두 전달

기대:

content_block_uniqueness_safe = fail

ready_for_direction = NO

---

# 39. 테스트 — CASE P

동일 Block이 duplicate_of 관계로 남아 있고

canonical:
direction_eligible=true

duplicate:
direction_eligible=false

기대:

10단계 독립 제작 대상은 canonical 1개

PASS

단, 구현이 중복 Block 자체를 제거하는 방식이면
이 테스트는 해당 구조에 맞게 대체 가능하다.

---

# 40. 테스트 — CASE Q

기존 16개 Integrity Check 확인

기대:

이름/의미 변경 없음

PASS

---

# 41. 테스트 — CASE R

05~08 데이터 불변

기대:

topic_candidates
click_analysis_topics
content_packages
production_blueprints

이번 작업으로 변경되지 않음

PASS

---

# 42. 테스트 — CASE S

기존 CLI 명령

auth
keywords
search
analyze
top
patterns
report
run-scheduled
run-all
topics
clicks
packages
blueprint
script

기대:

기존 시그니처 불변

PASS

---

# 43. 테스트 — CASE T

새 YouTube API 호출

기대:

0 units

이번 단계는 기존 09 산출물과 DB만 사용한다.

YouTube Search API를 새로 호출하지 않는다.

---

# 44. 실제 재생성 후 기대 구조

현재 9개 Content Block이 중복 제거 방식이라면
예를 들어 다음과 같이 정리될 수 있다.

CB01 — PROBLEM_RECOGNITION
CB02 — CORE_EXPLANATION
CB03 — DEMONSTRATION / BAG
CB04 — REINFORCEMENT / BAT
CB05 — TRANSFER / MAP
CB06 — MINI_SUCCESS / CAP
CB07 — RECAP / NEXT QUESTION

정확히 7개여야 한다는 뜻은 아니다.

중요한 것은:

같은 교육 이벤트를 나타내는 독립 Block이
두 번 존재하지 않는 것이다.

Block 개수를 맞추기 위해 억지로 삭제하지 않는다.

---

# 45. 이번 단계에서 하지 말 것

이번 단계에서는 절대 다음 작업으로 넘어가지 않는다.

- 4개 영상 포맷 선택 로직 구현
- Video Director 구현
- Scene 설계
- Shot 설계
- Clip 검색
- Clip availability 판정
- Asset 확보
- Podcast 대화문 생성
- TTS 화자 선택
- 말토막(Pause) 시각화 구현
- 편집 도구 선택
- Remotion/CapCut 구현
- 최종 Production Script 생성

이것들은 10단계 이후의 책임이다.

---

# 46. 완료 후 반드시 보고할 내용

작업 완료 후 다음 형식으로 보고한다.

1. 수정한 파일
2. Content Block 중복의 실제 원인
3. CB06/CB08을 어떻게 처리했는가
4. CB07/CB09를 어떻게 처리했는가
5. 중복 제거 후 Content Block 수
6. 최종 Content Block 목록과 learning_function
7. duplicate_of / direction_eligible을 사용했는지 여부
8. prerequisite_blocks 무결성 결과
9. "고유한 소리" 표현을 어떻게 수정했는가
10. Core Answer 수정 전/후
11. example_scope_safe를 어떻게 재사용/확장했는가
12. content_block_uniqueness_safe 추가 여부와 판정 방식
13. BAG/BAT/MAP/CAP 보존 여부
14. CAP Mini Success 3초 보존 여부
15. media_affinity 보존 여부
16. 기존 16개 Integrity Check 보존 여부
17. 전체 Integrity Check 결과
18. Script/Content Score 수정 전/후
19. Ready for Direction 여부
20. 추가한 테스트 수
21. 전체 테스트 결과
22. 기존 CLI 하위 호환 여부
23. 새 YouTube API quota 사용 여부
24. 05~08 기존 데이터 불변 여부
25. 발견된 제한사항
26. 10단계 Video Director 진행 가능 여부

---

# 47. 완료 기준

이번 단계의 최종 성공 조건은 다음과 같다.

Content Script가:

무엇을 가르칠지 정의하고
↓
교육 흐름을 중복 없이 구조화하고
↓
각 Block의 교육 목적을 명확히 가지고
↓
글자=고정 음가라는 잘못된 일반화를 만들지 않고
↓
BAG → BAT → MAP → CAP 흐름을 보존하고
↓
CAP Mini Success를 정확히 한 번 수행하고
↓
media_affinity를 유지하고
↓
어떤 영상 포맷도 아직 선택하지 않고
↓
10단계 Video Director가 안전하게 해석할 수 있어야 한다.

최종 목표:

Content Research
→ Topic
→ Click Analysis
→ Content Package
→ Production Blueprint
→ Content Script
→ [09-3 중복/교육표현 정규화]
→ ready_for_direction
→ 10 Video Director

이번 단계에서는 마지막 화살표를 넘어가지 않는다.