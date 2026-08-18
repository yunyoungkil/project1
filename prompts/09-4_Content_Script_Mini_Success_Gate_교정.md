# 09-4단계: Content Script Mini Success Gate 교정

현재 프로젝트의 05~09-3 전체 구조와
가장 최근 실제 Content Script Report를 먼저 읽고,
09단계의 기존 책임/Integrity Check/DB/CLI 구조를 충분히 이해한 뒤 수정하라.

이번 작업은 새로운 Stage를 추가하는 것이 아니다.

09단계 Content Script의
Mini Success 검증 및 Ending 해석 교정 작업이다.

목표:

1. 실제로 정상적인 Mini Success가 존재하는데
   mini_success_present가 fail되는 false negative를 제거한다.

2. Practice와 Mini Success가 같은 단어를 사용할 때
   교육적으로 정당한 반복인지 불필요한 중복인지 구분한다.

3. ending_resolves_opening warning이
   실제 콘텐츠 문제인지 검증기 한계인지 판별하고,
   검증 로직을 필요한 만큼만 교정한다.

4. 기존 09 Content Script의 교육 정확성/Scope/포맷 중립성은
   절대 약화시키지 않는다.


==================================================
0. 현재 실제 실패 사례
==================================================

최근 실제 Content Script는 다음 구조를 가진다.

Title:
"왕초보가 영어 단어장부터 외우면 3달 뒤 포기하는 이유 (하루 30분 로드맵)"

Core Question:
영어 왕초보는 단어장 암기 대신 첫 3개월 동안
매일 30분씩 무엇을 해야 할까?

Core Answer:
철자 암기가 아니라
단어 속 글자가 나타내는 소리를 연결해 읽는 연습부터
하루 30분씩 단계별로 훈련해야 한다.


현재 Content Script에는:

CB08
Learning Function: MINI_SUCCESS

Viewer Action:
정답 공개 전에 MAP 단어의 세 소리를 연결해
직접 소리 내어 읽어본다

Thinking Time:
3s

Base Narration:
화면에 나오는 MAP 단어를 보면서,
세 소리를 순서대로 합쳐 3초 안에 직접 소리 내어 읽어보세요.
네, /m/, /æ/, /p/가 이어져 /mæp/이 됩니다.
스스로 소리를 연결해 읽어내셨습니다.


별도 Mini Success section에도:

MAP 퀴즈
[PAUSE 3 SEC]
pause 후 /mæp/ 정답 확인

이 존재한다.


그런데 현재 Integrity Check:

mini_success_present: fail

이다.


이것은 실제 콘텐츠의 Mini Success 부재가 아니라
검증기가 현재 구조를 정확히 인식하지 못한
false negative일 가능성이 높다.


==================================================
1. 절대 원칙
==================================================

이번 작업에서:

Mini Success 요구를 삭제하지 마라.

mini_success_present를 무조건 pass시키지 마라.

Thinking Time 요구를 삭제하지 마라.

Viewer Action 요구를 삭제하지 마라.

Answer-before-pause 허용으로 완화하지 마라.

단순히 Learning Function == MINI_SUCCESS라는 이유만으로
pass시키지 마라.

실제 구조적 evidence가 있어야 한다.


==================================================
2. Mini Success의 정의
==================================================

09단계에서 Mini Success는 최소 다음 의미를 가져야 한다.

A. 학습자가 직접 수행해야 할 대상이 존재한다.

B. 정답/해답 공개 전에
   학습자에게 실제 시도 기회가 주어진다.

C. viewer_action 또는 이에 준하는 명시적 행동 유도가 있다.

D. 필요한 경우 thinking_time_seconds > 0이 존재한다.

E. 시도 이후 정답/확인이 존재한다.

F. 이 활동이 해당 Content Script의
   Learning Objective/Example Ladder/Scope 안에 있다.


즉 Mini Success는:

"문제를 하나 넣었다"

가 아니라

ATTEMPT
→ THINK
→ ANSWER
→ CONFIRM

의 작은 학습 성공 경험이다.


==================================================
3. Mini Success 구조적 판정
==================================================

mini_success_present는
가능하면 다음 구조적 신호를 함께 본다.


필수 신호:

1.
Content Block 중 learning_function == MINI_SUCCESS
또는 retention_intent.type == mini_success
또는 별도 mini_success_meta 존재


2.
viewer_action이 비어 있지 않음
또는 base_narration에 직접 수행 유도 존재


3.
정답/answer evidence 존재


4.
시도보다 정답이 먼저 나오지 않음


추가 강한 신호:

thinking_time_seconds > 0

[PAUSE N SEC] cue

answer/reveal narration

target example 존재


==================================================
4. mini_success_present 새 판정 제안
==================================================

다음처럼 하나의 문자열 검색이 아니라
구조 기반으로 판단하라.


예:

has_mini_success_block
AND
has_viewer_action
AND
has_answer_evidence
AND
answer_after_attempt
AND
scope_safe

이면 pass.


thinking_time은:

해당 Mini Success 설계가 thinking_time을 요구하는 경우
반드시 보존되어야 한다.


현재 실제 CB08은:

MINI_SUCCESS
+
Viewer Action
+
Thinking Time 3s
+
MAP target
+
pause
+
/mæp/ answer

가 모두 있으므로
정상적으로 pass되어야 한다.


==================================================
5. Mini Success Answer Evidence
==================================================

정답 evidence는 단순히 "정답"이라는 단어를 찾지 않는다.

다음도 정답 evidence로 인정할 수 있다.

EN target answer

IPA answer

expected_word

answer narration

예:

/m/
/æ/
/p/

/mæp/

MAP

같은 실제 학습 답.


현재 CB08에서는:

/m/, /æ/, /p/
→ /mæp/

가 명확한 answer evidence다.


==================================================
6. Attempt-before-answer 검증
==================================================

Mini Success가 존재해도:

정답이 viewer_action보다 먼저 노출되면
pass시키면 안 된다.


예:

BAD:

"MAP은 /mæp/입니다.
이제 직접 읽어보세요."

→ mini_success_present fail 또는 critical warning


GOOD:

"MAP을 직접 읽어보세요."

PAUSE 3s

"/m/ /æ/ /p/가 이어져 /mæp/입니다."

→ pass


기존 script beats / mini_success_meta / content_blocks / cues
중 실제 순서를 확인할 수 있는 가장 신뢰 가능한 구조를 사용하라.


==================================================
7. 실제 현재 CB08 Acceptance
==================================================

현재 실제 CB08 구조:

Learning Function:
MINI_SUCCESS

Viewer Action:
정답 공개 전에 MAP 단어의 세 소리를 연결해
직접 소리 내어 읽어본다

Thinking Time:
3s

Narration before answer:
"화면에 나오는 MAP 단어를 보면서,
세 소리를 순서대로 합쳐 3초 안에 직접 소리 내어 읽어보세요."

Cue:
[PAUSE 3 SEC]

Answer:
"네, /m/, /æ/, /p/가 이어져 /mæp/이 됩니다."

이 구조는 반드시:

mini_success_present = pass

가 되어야 한다.


==================================================
8. Practice vs Mini Success 중복 문제
==================================================

현재 실제 Content Script에는:

CB05
Learning Function: PRACTICE

Target:
MAP

그리고:

CB08
Learning Function: MINI_SUCCESS

Target:
MAP

이 존재한다.


같은 단어를 사용한다는 이유만으로
자동 중복 처리하면 안 된다.


==================================================
9. Practice와 Mini Success 역할 구분
==================================================

같은 example word를 써도
학습 기능이 다르면 정당한 반복일 수 있다.


예:

PRACTICE:

교사가 /m/ /æ/ /p/를 안내하면서
MAP을 읽는 방법을 준비시킴


MINI_SUCCESS:

정답을 숨기고
학습자가 스스로 MAP을 읽게 함


이 경우:

같은 target word라도

GUIDED PRACTICE
→ INDEPENDENT ATTEMPT

관계이므로 정당한 progression이다.


==================================================
10. 신규 검사
    practice_mini_success_progression_safe
==================================================

Practice와 Mini Success가 같은 example을 사용할 경우
최소 다음을 검사한다.


PASS 조건 예:

Practice:
- 더 많은 scaffold 제공
- phoneme 정보 또는 설명 제공
- 정답/원리 안내 가능


Mini Success:
- scaffold 감소
- viewer_action 존재
- 정답 지연
- thinking time 존재 가능
- independent attempt 성격


즉:

support decreases
AND
learner responsibility increases

이면 pass.


FAIL 조건 예:

CB05:
MAP 직접 읽기 3초 퀴즈

CB08:
MAP 직접 읽기 3초 퀴즈

처럼

같은 target
+
같은 viewer action
+
같은 thinking time
+
같은 answer sequence

가 사실상 반복되는 경우.


==================================================
11. 중복 검증 시 기존 09-3 로직 재사용
==================================================

기존:

content_block_uniqueness_safe
_is_duplicate_candidate
_merge_candidate_into

등의 구조를 먼저 조사하라.


새로운 별도 중복 시스템을 크게 만들지 말고,
현재 Practice↔Mini Success progression을
해석할 수 있도록 필요한 최소 확장만 하라.


==================================================
12. 현재 CB05/CB08에 대한 기대 판정
==================================================

현재 CB05:

PRACTICE
MAP
phoneme /m/ /æ/ /p/ 제공
viewer_action 없음
thinking_time 0


현재 CB08:

MINI_SUCCESS
MAP
viewer_action 있음
thinking_time 3초
정답 지연


따라서 현재 구조는:

GUIDED PRACTICE
→ INDEPENDENT MINI SUCCESS

로 판정하는 것이 타당하다.


즉:

practice_mini_success_progression_safe = pass


==================================================
13. ending_resolves_opening 현재 상태
==================================================

현재 Integrity Check:

ending_resolves_opening: warning


Opening에서는:

단어장부터 무작정 암기하는 문제

+
소리 읽기

+
하루 30분 3단계 로드맵

을 약속한다.


Core Question:

첫 3개월 동안
매일 30분씩 무엇을 해야 하는가?


Ending:

다음 영상에서는
단모음 o/u 및 끝소리 /g/ /k/ 차이 예고

+
구독/좋아요

+
감사 인사


현재 CB07 Recap에서는:

단어 암기보다 소리 조합 우선
+
하루 30분 로드맵
+
CAT/BAT/BAG/MAP

을 다시 정리한다.


따라서 opening promise 해결이
CB07에서 이미 이루어지고,
CB09는 sign-off/next topic 역할일 가능성이 있다.


==================================================
14. Ending Resolution의 정의 수정
==================================================

ending_resolves_opening을:

"마지막 Block 하나가 Opening 단어를 반복해야 한다"

로 판정하면 안 된다.


영상 전체의 closing region에서:

Opening Problem
Core Question
Video Promise

가 해결되었는지 판단해야 한다.


Closing region은 최소:

마지막 RECAP
+
RESOLUTION/ENDING
+
Mini Success가 뒤쪽에 있다면 해당 Block

을 포함할 수 있다.


==================================================
15. Ending Resolution 판정 구조
==================================================

다음 세 축을 본다.


A. Problem resolution

Opening에서 제기한 문제에
해결 원리가 실제로 제시되었는가?


B. Promise fulfillment

Video Promise의 핵심 결과가
closing region에서 다시 확인되는가?


C. Action closure

학습자가 다음에 무엇을 할지
행동 또는 정리 상태가 남는가?


이 세 가지 중 핵심 요소가 충족되면
ending_resolves_opening pass 가능.


==================================================
16. 현재 실제 Script Acceptance
==================================================

현재 실제 Script는:

CB07에서

- 단어 암기보다 소리 블렌딩 우선
- 하루 30분 실천
- CAT/BAT/BAG/MAP 복습

을 정리한다.


CB08에서:

실제 독립 적용 Mini Success를 수행한다.


CB09에서:

다음 주제 예고
+
마무리 인사

를 한다.


따라서 전체 closing region 기준으로:

Core Question과 Video Promise가 실제로 해결되는지
판정해야 한다.


만약 해결된다면:

ending_resolves_opening = pass


단:

단순히 마지막 Block에 "감사합니다"가 있다고
pass시키면 안 된다.


==================================================
17. 신규 helper 권장
==================================================

필요하면:

collect_closing_region()

또는 동등한 내부 helper를 만든다.


예:

closing blocks:

last RECAP
+
MINI_SUCCESS
+
final RECAP/RESOLUTION


이 구조 전체를 검사한다.


하지만 기존 데이터 구조를 대규모 변경하지 않는다.


==================================================
18. 기존 Integrity Check 보존
==================================================

현재 09-3의 기존 Integrity Check 이름/의미를
가능한 한 유지한다.


기존:

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
content_block_uniqueness_safe


를 삭제하지 않는다.


이번 수정에서는:

mini_success_present

ending_resolves_opening

의 false negative를 정확히 교정한다.


추가로:

practice_mini_success_progression_safe

를 신규 Check로 추가할 수 있다.


==================================================
19. Ready for Direction Gate
==================================================

ready_for_direction은
기존 critical Integrity Gate를 계속 우선한다.


mini_success_present가
실제로 정상 구조에서 pass되면
더 이상 false negative 때문에 Gate가 막히면 안 된다.


하지만 실제 Mini Success가 없으면:

ready_for_direction = NO

가 유지되어야 한다.


==================================================
20. Gemini 사용 원칙
==================================================

이번 수정은 가능하면 결정론적 검증 로직 교정으로 해결한다.


Mini Success 판정 때문에
Gemini를 새로 호출하지 마라.


Ending 의미 판정 역시
기존 데이터/구조로 충분히 결정할 수 있으면
결정론적으로 처리한다.


새 Gemini API 호출 추가 금지.


==================================================
21. 현재 실제 Script를 재작성하지 마라
==================================================

중요:

이번 작업의 1차 목적은
Script 내용 자체를 바꾸는 것이 아니다.


현재 Script의:

CAT
BAT
BAG
MAP

Example Ladder

하루 30분 3단계 로드맵

MAP Mini Success

를 그대로 보존한다.


검증기의 false negative를 고치는 것이 우선이다.


==================================================
22. 실제 Script에서 발견되는 별도 문제
==================================================

현재 Script에는:

CB01
"철자를 백 번 써서 외워도,
소리로 읽을 줄 모르면 3주만 지나도
머릿속에서 완전히 지워집니다."

같은 강한 단정 표현이 존재한다.


이번 09-4의 핵심 스코프는
Mini Success Gate/Ending Resolution이므로
이 문장을 임의 수정하지 마라.


단:

기존 no_false_guarantee가 pass한 이유가
명백한 검증 누락처럼 보인다면
보고서의 Known Limitations에 기록하라.


이번 스코프 밖의 대규모 수정은 하지 않는다.


==================================================
23. 테스트 CASE
==================================================

최소 다음 테스트를 추가한다.


CASE A

MINI_SUCCESS block 없음

→ mini_success_present fail


CASE B

MINI_SUCCESS block은 있으나 viewer_action 없음
+
attempt 유도도 없음

→ fail


CASE C

MINI_SUCCESS + viewer_action 존재
+
answer 없음

→ fail


CASE D

answer가 attempt보다 먼저 존재

→ fail


CASE E

MINI_SUCCESS
+
viewer_action
+
3초 thinking time
+
pause 후 answer

→ pass


CASE F

현재 실제 MAP CB08 구조

→ pass


CASE G

[PAUSE 3 SEC] cue를 실제 thinking time으로 인식


CASE H

thinking_time_seconds=3
+
cue=3 sec 일치

→ pass


CASE I

thinking_time_seconds=3
+
cue=0 또는 missing인데
구조상 pause 보존이 필요한 경우

→ warning/fail
기존 프로젝트 정책과 일관되게 결정


CASE J

Practice와 Mini Success가 다른 target

→ progression safe


CASE K

Practice와 Mini Success가 같은 target이지만

Practice:
scaffold high

Mini Success:
independent attempt

→ pass


CASE L

Practice와 Mini Success가
같은 target + 같은 action + 같은 timing + 같은 answer

→ duplication fail


CASE M

현재 CB05 MAP → CB08 MAP 구조

→ practice_mini_success_progression_safe pass


CASE N

Opening problem 해결이
마지막 RECAP에서 이루어짐
+
final sign-off는 짧음

→ ending_resolves_opening pass 가능


CASE O

마지막 Block에 opening 단어가 없다는 이유만으로
warning/fail하지 않음


CASE P

Closing region 전체에도
Core Question 해결이 없음

→ ending_resolves_opening warning/fail 유지


CASE Q

현재 실제 CB07+CB08+CB09 closing 구조

→ ending_resolves_opening pass 또는
명확한 근거가 있는 warning

단,
판정 이유를 테스트 fixture에서 검증


CASE R

기존 17개 Check 이름/의미 보존


CASE S

format_neutrality_safe 회귀 없음


CASE T

content_block_uniqueness_safe 회귀 없음


CASE U

example_ladder_preserved 회귀 없음


CASE V

phoneme_explanation_safe 회귀 없음


CASE W

no_scope_creep 회귀 없음


CASE X

기존 CLI:
research script [--blueprint-id ID]

시그니처 불변


CASE Y

05~08 데이터 불변


CASE Z

전체 기존 테스트 회귀 없음


==================================================
24. 실제 데이터 재실행
==================================================

이번 환경에는 실제 DB가 존재하므로
수정 후 반드시 실제 데이터로 재실행한다.


실행:

python -m research.cli script


필요하면 특정 blueprint id를 사용하되,
기존 CLI 규칙을 따른다.


기존 video_scripts row를 수정하지 않는다.


새 실행 = 새 row


원칙 유지.


==================================================
25. 실제 재생성 시 주의
==================================================

Gemini를 다시 호출하면
Script 문구가 달라질 수 있다.


이번 작업은 Gate 검증 로직 교정이 핵심이므로,
가능하면 기존 latest video_script row를
재검증하는 deterministic 경로가 있는지 먼저 조사하라.


만약 기존 구조상
script command가 항상 Gemini 재생성을 수행한다면:

1. 기존 row에 대해 integrity 재평가 helper를 추가할지 검토
2. 불필요한 architecture 확대는 피함
3. 실제 새 Script 생성 결과도 별도로 보고


기존 row를 직접 UPDATE하여
ready_for_direction만 1로 바꾸는 방식은 금지.


==================================================
26. 권장 재검증 기능
==================================================

현재 architecture에 자연스럽다면
내부적으로:

recheck_script_integrity(script_row)

같은 helper를 만들 수 있다.


목적:

기존 저장된 Script 내용을 바꾸지 않고
새 검증 로직으로 Integrity 결과를 다시 계산.


하지만 CLI를 새로 추가할 필요가 없으면
억지로 만들지 않는다.


==================================================
27. 실제 결과에서 반드시 확인
==================================================

수정 후 실제 최신 Script에서:


1.
mini_success_present


2.
practice_mini_success_progression_safe


3.
ending_resolves_opening


4.
Ready for Direction


5.
MAP Mini Success Viewer Action


6.
Thinking Time 3s


7.
[PAUSE 3 SEC]


8.
Answer 위치


9.
CAT/BAT/BAG/MAP 보존


10.
Scope 보존


11.
기존 발음 안전 Check


12.
Content Block uniqueness


를 직접 확인하라.


==================================================
28. 기대 결과
==================================================

현재 실제 Script 내용이 그대로 유지된다는 전제에서
기대 결과는:


mini_success_present:
pass


practice_mini_success_progression_safe:
pass


ending_resolves_opening:
pass
또는 실제 의미상 부족하면
근거 있는 warning


Ready for Direction:
YES


단:

다른 critical Integrity Check가 새 Script에서 fail하면
Ready for Direction을 강제로 YES로 만들지 않는다.


==================================================
29. Script Score
==================================================

이번 수정은 Script Score를 높이기 위한 작업이 아니다.


현재:

Total 93.1/100


점수 공식을 임의 변경하지 않는다.


Retention 점수를
mini_success_present를 통과시키기 위해
올려치지 않는다.


Integrity와 Score는 분리한다.


==================================================
30. API quota
==================================================

검증 로직 자체:

Gemini API 0
YouTube API 0


실제 script 재생성이 Gemini를 호출하는 기존 동작이라면
기존 동작으로 발생한 호출만 정직하게 보고한다.


새로운 API 호출을 09-4 때문에 추가하지 않는다.


==================================================
31. 완료 보고 형식
==================================================

완료 후 다음을 보고하라.


1. 수정한 파일

2. mini_success_present 기존 fail 원인

3. 기존 검증 로직이 놓친 구조

4. 새 Mini Success 판정 방식

5. Attempt-before-answer 판정 방식

6. Thinking Time 판정 방식

7. 현재 MAP Mini Success 판정 결과

8. CB05 Practice와 CB08 Mini Success의
   같은 MAP 사용을 어떻게 판정했는가

9. practice_mini_success_progression_safe 추가 여부

10. Practice→Mini Success progression 판정 방식

11. ending_resolves_opening 기존 warning 원인

12. Closing region 정의 방식

13. CB07+CB08+CB09 실제 closing 판정

14. mini_success_present 수정 전/후

15. ending_resolves_opening 수정 전/후

16. Ready for Direction 수정 전/후

17. Viewer Action 보존 여부

18. Thinking Time 3초 보존 여부

19. [PAUSE 3 SEC] 보존 여부

20. Answer 위치 보존 여부

21. CAT/BAT/BAG/MAP 보존 여부

22. Example Ladder 보존 여부

23. 기존 17개 Integrity Check 보존 여부

24. 신규 Integrity Check 목록

25. 전체 Integrity Check 결과

26. Script Score 전/후

27. 추가한 테스트 수

28. 전체 테스트 결과

29. 05~08 회귀 여부

30. 기존 CLI 하위 호환 여부

31. Gemini API 사용량

32. YouTube API quota 사용량

33. 실제 DB row 재검증 여부

34. 발견된 추가 제한사항


==================================================
32. 성공 조건
==================================================

성공 기준은:

mini_success_present를 억지로 pass시키는 것

이 아니다.


다음이 성립해야 한다.


실제 Mini Success 존재
→ pass


Mini Success 부재
→ fail


Answer 선공개
→ fail


정상 3초 thinking time
→ 보존


Practice와 Mini Success가
교육적으로 다른 역할
→ 허용


실질적으로 같은 Activity 반복
→ 탐지


Opening Promise가 Closing Region에서 해결
→ pass


해결되지 않음
→ warning/fail


그리고 현재 실제 Script가
다른 critical 오류 없이 정상이라면:

Ready for Direction:
YES


==================================================
33. 절대 금지
==================================================

mini_success_present를
learning_function == MINI_SUCCESS 하나로 pass시키지 마라.

viewer_action만 있다고 pass시키지 마라.

thinking_time만 있다고 pass시키지 마라.

정답이 먼저 나와도 pass시키지 마라.

현재 MAP Mini Success를 삭제하지 마라.

같은 MAP을 썼다는 이유만으로
Practice 또는 Mini Success를 제거하지 마라.

Ending warning을 없애기 위해
마지막 문장을 억지로 다시 쓰지 마라.

Script Score를 조작하지 마라.

Ready for Direction DB 값을 수동으로 1로 바꾸지 마라.

기존 video_scripts row를 임의 UPDATE하지 마라.

05~08 데이터를 변경하지 마라.

10~12단계를 수정하지 마라.

불필요한 대규모 리팩터링을 하지 마라.


==================================================
34. 최종 원칙
==================================================

09단계의 Integrity Gate는
콘텐츠를 막기 위한 장벽이 아니다.

정상적인 교육 구조는 통과시키고,
실제로 불완전한 구조만 막아야 한다.


이번 실제 사례처럼:

MINI_SUCCESS
+
Viewer Action
+
3초 Thinking Time
+
Pause
+
Answer

가 명백히 존재한다면
검증기가 그것을 정확히 이해해야 한다.


검증 로직이 실제 콘텐츠 구조보다 뒤처져
정상 Script를 막아서는 안 된다.


반대로 검증기를 통과시키기 위해
조건을 약화해서도 안 된다.


목표는:

"더 느슨한 Gate"

가 아니라

"더 정확한 Gate"

이다.