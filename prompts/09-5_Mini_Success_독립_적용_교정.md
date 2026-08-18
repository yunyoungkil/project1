# 09-5단계: Mini Success 독립 적용 교정

현재 프로젝트의 05~09-4 전체 구조와
가장 최근 실제 Content Script Report를 먼저 읽고,
Mini Success가 어느 단계에서 최초로 결정되는지 추적한 뒤 수정하라.

이번 작업에서 가장 중요한 원칙:

"09에서 보이는 오류라고 해서 무조건 09를 수정하지 않는다."

먼저 Mini Success target / example / prompt_word / thinking_time이

08 Production Blueprint에서 이미 잘못 결정된 것인지,
아니면 08은 정상인데 09 Script Writer가 잘못 변형한 것인지

데이터 lineage를 추적하라.

최초 오류 발생 Stage만 수정하는 것을 기본 원칙으로 한다.


==================================================
0. 현재 실제 실패 사례
==================================================

현재 실제 Content Script:

Viewer Contract:
"왕초보가 영어 단어장부터 외우면 3달 뒤 포기하는 이유
(하루 30분 로드맵)"

Example Ladder:

CAT
→ BAT
→ BAG
→ MAP


현재 CB05:

Learning Function:
PRACTICE

Target:
MAP

Viewer Action:
화면의 M, A, P 소리를 떠올리며
스스로 MAP을 소리 내어 읽어본다

Thinking Time:
0

Narration에는 이미:

M → /m/
A → /æ/
P → /p/

가 모두 제시된다.


현재 CB08:

Learning Function:
MINI_SUCCESS

Target:
MAP

Viewer Action:
정답 공개 전에 MAP을 직접 소리 내어 읽어본다

Thinking Time:
3초

그러나 PAUSE 이전 narration에서 이미:

M → /m/
A → /æ/
P → /p/

를 다시 전부 제시한다.


현재 Integrity:

mini_success_present:
fail

practice_mini_success_progression_safe:
fail

Ready for Direction:
NO


==================================================
1. 이번 수정의 목적
==================================================

Mini Success를 다음 구조로 만든다.

GUIDED LEARNING
→ GUIDED PRACTICE
→ NEW INDEPENDENT ATTEMPT
→ THINKING TIME
→ ANSWER
→ SUCCESS CONFIRMATION


Mini Success는 단순 복습이 아니다.

시청자가 이미 배운 원리를
"새로운 예시"에 도움 없이 적용해보는
첫 독립 성공 경험이어야 한다.


==================================================
2. 가장 먼저 해야 할 원인 추적
==================================================

코드를 수정하기 전에 반드시 다음 lineage를 조사하라.


07 Content Package
↓
08 Production Blueprint
↓
Example Ladder
↓
mini_success
↓
09 Script Writer
↓
mini_success_meta
↓
Content Blocks
↓
CB05 Practice
↓
CB08 Mini Success


특히 다음을 확인하라.


A.

production_blueprints의 현재 row에서
mini_success target이 무엇인가?


B.

08의 Example Ladder 마지막 단어가 무엇인가?


C.

08 mini_success.prompt_word / example_word /
target_word 등에 MAP이 이미 들어 있는가?


D.

08에서는 CAP 등 다른 단어인데
09에서 MAP으로 변경되는가?


E.

09의 build_content_blocks /
mini_success generation 과정에서
Example Ladder 마지막 단어를 자동 재사용하는가?


==================================================
3. 발원 단계 수정 원칙
==================================================

CASE A:

08 Blueprint에서 이미:

Practice = MAP
Mini Success = MAP

이라면

→ 최초 오류는 08이다.

08 Production Blueprint 생성 원칙을 수정하라.

09가 임의로 CAP으로 교체하도록 하지 않는다.


CASE B:

08:

Practice = MAP
Mini Success = CAP

인데

09에서:

Mini Success = MAP

으로 바뀐다면

→ 최초 오류는 09다.

09 Script Writer만 수정한다.


CASE C:

08의 mini_success target 자체가 없고
09가 자동으로 마지막 Example Ladder 단어를 선택한다면

→ 해당 selection 책임이 실제로 어느 Stage에 속해야 하는지
기존 설계를 조사한 뒤 최소 수정한다.


원인을 확인하지 않고
08과 09를 둘 다 동시에 수정하지 마라.


==================================================
4. Independent Mini Success 정의
==================================================

Mini Success target은 다음 조건을 만족해야 한다.


1.

현재 Scope 안의 단어


2.

학습자가 Mini Success 이전까지 배운
phoneme/rule만으로 해결 가능


3.

Practice에서 이미 정답까지 풀어본
동일 단어를 기본적으로 재사용하지 않음


4.

새로운 규칙을 요구하지 않음


5.

예외 단어가 아님


6.

난이도가 지나치게 상승하지 않음


7.

answer reveal 전까지
정답 핵심 정보가 노출되지 않음


8.

3초 thinking time 안에서
초보자가 현실적으로 시도 가능


==================================================
5. 현재 실데이터의 권장 Mini Success
==================================================

현재까지 학습된 소리:

C → /k/   (CAT에서)
A → /æ/
T → /t/

B → /b/
G → /g/

M → /m/
P → /p/


따라서 현재 Mini Success 후보로:

CAP

을 우선 검토하라.


CAP:

C /k/
A /æ/
P /p/


모든 필요한 소리는 이미 앞 Block에서 학습했다.


하지만 CAP이라는 단어 조합 자체는
현재 Example Ladder:

CAT
BAT
BAG
MAP

에서 독립 연습하지 않았다.


따라서:

MAP = Guided Practice

CAP = Independent Mini Success

구조가 교육적으로 자연스럽다.


==================================================
6. 중요한 원칙 — CAP 하드코딩 금지
==================================================

CAP을 모든 콘텐츠에 하드코딩하지 마라.


이번 실제 BAG/CAT 계열 콘텐츠에서는
CAP이 좋은 acceptance candidate일 뿐이다.


일반 로직은:

"이미 학습한 소리만 사용하면서,
Practice에서 사용하지 않은,
Scope 안의 새로운 안전한 example"

을 선택해야 한다.


즉:

select_independent_mini_success_candidate(...)

또는 동등한 역할의 로직을 설계할 수 있다.


그러나 unnecessary general-purpose word generator를
대규모로 만들지 마라.


현재 Blueprint가 이미 후보/example metadata를
제공할 수 있다면 그것을 우선 사용한다.


==================================================
7. Mini Success Candidate 안전 조건
==================================================

후보 단어를 선택할 때 최소 다음을 확인한다.


candidate != practice_target

candidate not in already_fully_practiced_targets

candidate uses only learned phoneme inventory

candidate within Scope IN

candidate not dependent on Scope OUT

candidate exception_risk == low
또는 실제 규칙 예외가 없는 것으로 기존 데이터에서 확인

candidate difficulty <= 적절한 Mini Success 난이도


새로운 phonics rule을 Mini Success에서
몰래 도입하면 안 된다.


==================================================
8. 같은 단어 재사용이 항상 금지되는 것은 아니다
==================================================

같은 target 재사용을 절대 금지하지 않는다.


예외적으로 동일 단어를 다시 써도 되는 경우:

Practice에서는 정답을 보여주지 않았고
Mini Success에서 최초 독립 시도가 일어나는 경우

또는

Practice의 목적이 완전히 다른 경우


하지만 현재 실제 MAP은:

CB05에서 이미

/m/
/æ/
/p/

를 모두 제공하며
직접 읽기를 요구한다.


따라서 CB08에서 다시 MAP으로
독립 성공을 만들기에는 scaffold 감소가 충분하지 않다.


현재 MAP 재사용은 부적합으로 판정해야 한다.


==================================================
9. Mini Success Pre-answer Information Barrier
==================================================

가장 중요한 신규 원칙이다.


Mini Success의 attempt 이전에는
정답을 구성하는 핵심 phoneme answer를
직접 제공하지 않는다.


BAD:

"MAP을 읽어보세요.
M은 /m/, A는 /æ/, P는 /p/입니다."

PAUSE 3 SEC


이 경우 학습자는
소리를 스스로 recall하는 것이 아니라
주어진 정답을 이어 붙이기만 한다.


GOOD:

"이번에는 아무 도움 없이 직접 읽어보겠습니다.
화면에 나온 단어를 보고
앞에서 배운 방법대로 세 소리를 떠올려보세요."

VISUAL:
CAP

PAUSE 3 SEC

ANSWER:
CAP

그리고:

C /k/
A /æ/
P /p/

확인


==================================================
10. 신규 Integrity Check
    mini_success_answer_barrier_safe
==================================================

Mini Success의 attempt 영역을 구분하고
PAUSE/reveal 이전에 answer evidence가 있는지 검사한다.


answer evidence 최소:

target에 대응되는 IPA phoneme

전체 pronunciation IPA

정답 발음을 직접 알려주는 narration

explicit answer wording


예:

CAP Mini Success에서 pause 이전에:

/k/
/æ/
/p/

가 모두 등장한다면 fail.


단:

화면에 "CAP" 철자 자체가 보이는 것은 정상이다.

문제를 풀려면 target word는 보여줘야 한다.


따라서:

TARGET ORTHOGRAPHY != ANSWER PRONUNCIATION


으로 구분한다.


==================================================
11. target word와 answer의 구분
==================================================

중요:


CAP

이라는 철자를 보여주는 것은 문제 제시다.


/k/ /æ/ /p/

/kæp/

자연 발음 CAP

은 answer/reveal 정보다.


검증기에서 둘을 같은 것으로 취급하지 마라.


현재 09-4에서
"MAP 문자열 자체는 answer evidence로 인정하지 않는다"
는 원칙을 유지한다.


==================================================
12. Mini Success 구조
==================================================

최종 Mini Success는 논리적으로:


PROMPT

"이번에는 여러분 차례입니다."


TARGET PRESENTATION

CAP


ATTEMPT INSTRUCTION

"앞에서 배운 방법대로
세 소리를 머릿속으로 연결해 직접 읽어보세요."


THINKING TIME

[PAUSE 3 SEC]


ANSWER

CAP natural pronunciation


ANSWER BREAKDOWN

C /k/
A /æ/
P /p/


CONFIRMATION

"앞에서 배운 소리만으로
새 단어도 직접 읽어냈습니다."


순서여야 한다.


정확한 문구를 하드코딩할 필요는 없다.

의미 구조가 중요하다.


==================================================
13. Practice 구조도 분명히 한다
==================================================

Guided Practice는 Mini Success와 다르다.


현재 MAP Practice는 다음 역할을 가진다.


TARGET:
MAP


SCAFFOLD:

M → /m/
A → /æ/
P → /p/


ACTION:

세 소리를 연결해 본다.


즉:

teacher-assisted transfer


로 유지할 수 있다.


Mini Success에서는 이 scaffold가 사라져야 한다.


==================================================
14. practice_mini_success_progression_safe 강화
==================================================

기존 09-4 check를 삭제하지 않는다.


다음 신호를 더 명확히 반영한다.


Practice:

scaffold_score


Mini Success:

scaffold_score


Mini Success의 scaffold가
Practice보다 실질적으로 낮아야 한다.


그리고:

learner_responsibility

는 높아야 한다.


개념적으로:

Practice:
scaffold HIGH
learner responsibility MEDIUM

Mini Success:
scaffold LOW
learner responsibility HIGH


이어야 한다.


==================================================
15. Scaffold 신호
==================================================

결정론적 신호 예:


phoneme answer before attempt
→ scaffold 증가


word pronunciation before attempt
→ scaffold 증가


letter-sound mapping explicitly supplied
→ scaffold 증가


viewer_action only
→ learner responsibility 증가


thinking_time > 0
→ independent attempt signal


answer delayed
→ independent attempt signal


새로운 target
→ transfer signal


이를 점수로 만들 수도 있지만
불필요하면 boolean rule로 유지한다.


==================================================
16. Example Ladder와 Mini Success 관계
==================================================

Mini Success target을
Example Ladder에 반드시 새 Level로 추가해야 하는지는
기존 08 구조를 조사한 뒤 결정하라.


두 가능한 구조가 있다.


A.

Example Ladder:
CAT → BAT → BAG → MAP

Mini Success:
CAP


즉 Mini Success는 Ladder 외
transfer challenge.


이 구조는 허용 가능하다.


B.

Example Ladder:
CAT → BAT → BAG → MAP → CAP

Mini Success:
CAP


현재 Blueprint schema가
Mini Success를 Ladder에 포함하도록 설계돼 있다면
이 구조를 사용할 수 있다.


기존 architecture를 우선한다.


억지로 Ladder schema를 바꾸지 마라.


==================================================
17. Phoneme inventory 추적
==================================================

Mini Success 후보가
"이미 배운 소리만 사용한다"는 것을
검증할 수 있어야 한다.


현재 예:

learned phonemes:

/k/
/æ/
/t/
/b/
/g/
/m/
/p/


CAP required:

/k/
/æ/
/p/


subset이므로 안전.


필요하다면 Example Ladder의
기존 IPA metadata를 재사용해
결정론적으로 비교한다.


새 발음 사전을 이번 단계에서 만들지 마라.


==================================================
18. 발음 정확성 보존
==================================================

기존:

phoneme_explanation_safe

example_scope_safe

no_unverified_rule

ipa_not_taught_as_memorization


를 그대로 유지한다.


Mini Success candidate를 바꾼다고 해서:

"C는 항상 /k/"

같은 일반화를 만들지 않는다.


정답 설명:

"이 단어 CAP에서 C는 /k/..."

처럼 scope 한정 원칙을 유지한다.


==================================================
19. 현재 실데이터의 별도 교육 표현 문제
==================================================

현재 CB03 narration:

"각 글자가 이 단어 안에서 내는 고유한 소리"

라는 표현이 존재한다.


이 표현은 과거 단계에서
위험 표현으로 교정한 적이 있다.


이번 작업의 핵심은 Mini Success이지만,
현재 실제 Script에서 다시 나타났으므로
원인을 반드시 조사하라.


중요:

09-5가 이를 임의로 문장 교정해서 덮지 마라.


먼저:

08 Blueprint source에 이미 존재하는지

09 Gemini generation에서 새로 생기는지

확인하라.


만약 이미 구현된
educational wording guard가 이를 놓친 명백한 회귀라면
최소 수정으로 함께 방지하고 보고한다.


하지만 Mini Success 작업을 핑계로
대본 전반을 대규모 리라이트하지 마라.


==================================================
20. 강한 단정 표현은 별도 기록
==================================================

현재 CB01:

"3주만 지나도 머릿속에서 완전히 지워집니다."

같은 표현이 존재한다.


이 역시 현재 no_false_guarantee가 통과시킨다.


이번 Mini Success 수정과 직접 관련 없으므로
무조건 수정하지 않는다.


단:

Known Limitation에 유지한다.


향후 별도 Content Claim Safety 교정이
필요할 수 있음을 보고한다.


==================================================
21. 08 수정이 필요한 경우
==================================================

원인 추적 결과 08에서
Mini Success target이 잘못 설계된 경우:


research/production_blueprint.py

의 Mini Success 생성 프롬프트/후처리/검증만
최소 수정한다.


목표:

Practice target과 독립 Mini Success target의
역할 차이를 명시.


예:

"Mini Success should preferably use a new,
scope-safe example that can be solved using
only sounds/rules already taught before it."


그리고:

"Do not reveal the answer phonemes
before the learner attempt."


를 추가.


==================================================
22. 08 신규/강화 검증
==================================================

08이 원인이라면
가능하면 다음 결정론적 백스톱을 추가한다.


mini_success_target_novel_safe

검증:

Mini Success target이
Practice에서 이미 완전 풀이된 target과
무분별하게 동일하지 않은가?


mini_success_uses_learned_material_safe

검증:

Mini Success가 새 규칙을 요구하지 않는가?


기존 integrity check를 삭제하지 않는다.


==================================================
23. 09 수정이 필요한 경우
==================================================

08이 정상이고 09가
Mini Success target을 바꾸거나
answer phoneme를 pause 전에 삽입했다면:


research/script_writer.py

만 수정한다.


원칙:

08 Mini Success target 보존


09가 임의로 Example Ladder 마지막 단어로
교체 금지


Mini Success pre-answer narration에
answer phoneme 삽입 금지


Viewer Action과 Thinking Time 보존


==================================================
24. 09 신규/강화 검증
==================================================

현재 09-4의:

mini_success_present

practice_mini_success_progression_safe

를 유지한다.


추가:

mini_success_answer_barrier_safe


최종 09 Gate는 최소:


mini_success_present
=
pass


practice_mini_success_progression_safe
=
pass


mini_success_answer_barrier_safe
=
pass


여야 한다.


==================================================
25. 기존 Mini Success metadata 보존
==================================================

다음을 유지한다.


viewer_action

thinking_time_seconds

retention_intent

purpose

scope

required_content


target만 올바른 독립 적용 대상으로
상위 설계에 따라 바뀔 수 있다.


==================================================
26. Acceptance Case — 현재 실데이터
==================================================

현재 콘텐츠 기준 기대 구조:


Guided examples:

CAT
BAT
BAG


Practice:

MAP


Mini Success:

CAP


Mini Success pre-answer:

CAP 철자 노출:
YES


/k/:
/æ/:
/p/:

NO


/kæp/:

NO


natural spoken answer:

NO


Thinking Time:

3 seconds


Pause 후:

CAP natural answer


그 뒤:

/k/
/æ/
/p/

확인


==================================================
27. Acceptance 결과
==================================================

현재 실데이터가 정상 교정됐다면:


mini_success_present:
pass


practice_mini_success_progression_safe:
pass


mini_success_answer_barrier_safe:
pass


ending_resolves_opening:
pass


phoneme_explanation_safe:
pass


example_scope_safe:
pass


no_scope_creep:
pass


content_block_uniqueness_safe:
pass


Ready for Direction:
YES


가 되어야 한다.


단:

다른 critical 오류가 실제로 있으면
강제로 YES 만들지 않는다.


==================================================
28. 테스트 CASE — 원인 추적
==================================================

최소 다음을 추가한다.


CASE A

08 Practice=MAP
08 MiniSuccess=CAP

09 MiniSuccess=CAP

→ 정상 보존


CASE B

08 Practice=MAP
08 MiniSuccess=CAP

09가 MAP으로 변경

→ fail


CASE C

08 자체가 Practice=MAP
MiniSuccess=MAP

→ upstream design issue 탐지


==================================================
29. 테스트 CASE — Novel Transfer
==================================================

CASE D

Practice MAP
Mini Success CAP
CAP phoneme가 learned inventory subset

→ pass


CASE E

Practice MAP
Mini Success에 새 phoneme/rule 필요

→ fail


CASE F

Practice와 Mini Success 같은 MAP
+
Practice에서 이미 phoneme 모두 공개
+
Mini Success도 같은 구조

→ fail


CASE G

같은 target이지만 Practice에서는
완전 풀이하지 않았고 Mini Success가 최초 독립 시도

→ 무조건 fail하지 않음


==================================================
30. 테스트 CASE — Answer Barrier
==================================================

CASE H

CAP pause 전:

CAP 철자만 존재

→ pass


CASE I

CAP pause 전:

/k/ /æ/ /p/

→ fail


CASE J

CAP pause 전:

/kæp/

→ fail


CASE K

CAP 자연 발음을 pause 전에 재생

→ fail


CASE L

pause 후 /k/ /æ/ /p/

→ pass


CASE M

pause 후 natural CAP

→ pass


==================================================
31. 테스트 CASE — Thinking Time
==================================================

CASE N

Thinking Time 3초 보존


CASE O

Viewer Action 보존


CASE P

[PAUSE 3 SEC] 보존


CASE Q

answer가 pause 뒤에 위치


==================================================
32. 테스트 CASE — Progression
==================================================

CASE R

CAT → BAT → BAG → MAP guided → CAP independent

→ progression pass


CASE S

MAP guided → MAP same guided repetition

→ fail


CASE T

Mini Success scaffold < Practice scaffold

→ pass


CASE U

Mini Success scaffold >= Practice scaffold
AND same target

→ fail


==================================================
33. 기존 회귀 테스트
==================================================

반드시 확인:


title_preserved

thumbnail_preserved

answers_core_question

promise_matches_scope

example_ladder_preserved

phoneme_explanation_safe

example_scope_safe

no_scope_creep

audio_first_usable

no_false_guarantee

narration_scope_safe

no_unverified_rule

ipa_not_taught_as_memorization

ending_resolves_opening

format_neutrality_safe

content_block_uniqueness_safe


전부 회귀 없음.


==================================================
34. 11단계와의 관계
==================================================

이번 수정 후 09가:

Ready for Direction = YES

가 된 뒤에만 10/11로 진행한다.


11-1 Production Plan 교정 코드는
이번 작업에서 수정하지 않는다.


09가 안정화되면:

python -m research.cli direction

그 다음:

python -m research.cli production-plan

을 실행한다.


==================================================
35. 실제 데이터 재생성 전략
==================================================

원인 Stage를 수정한 뒤
그 Stage 이후 데이터만 새 row로 재생성한다.


예:

08 수정 필요:

blueprint
→ script
→ direction
→ production-plan


09만 수정 필요:

script
→ direction
→ production-plan


기존 DB row를 DELETE/UPDATE하여
결과를 맞추지 않는다.


기존 immutable history를 유지한다.


==================================================
36. Gemini 재실행 주의
==================================================

08/09 재생성에는 Gemini 호출이 발생할 수 있다.


새 실행 결과가 이전 문구와
완전히 같을 필요는 없다.


Acceptance는 정확한 문장 일치가 아니라
교육 구조와 Integrity 기준으로 판단한다.


특히:

MAP Practice

CAP 또는 동등한 독립 new target Mini Success

answer barrier

3초 thinking time

을 본다.


==================================================
37. 실데이터 직접 확인
==================================================

재생성 후 리포트에서 반드시 직접 확인:


1. Example Ladder

2. Practice target

3. Mini Success target

4. Mini Success Viewer Action

5. Thinking Time

6. Pause 이전 narration

7. Pause 이전 IPA 존재 여부

8. Pause 이후 answer

9. mini_success_present

10. practice_mini_success_progression_safe

11. mini_success_answer_barrier_safe

12. Ready for Direction


==================================================
38. Score
==================================================

Script Score를 올리기 위해
점수 공식을 변경하지 않는다.


현재 90.1이라는 점수 자체가
이번 작업의 목표가 아니다.


Integrity 구조가 정상이라면
점수는 실제 계산 결과를 그대로 보고한다.


==================================================
39. API quota
==================================================

코드 검증/테스트에서는
새 API 호출 0을 유지한다.


실데이터 재생성으로 발생한 Gemini 호출은
정직하게 보고한다.


YouTube API는 이번 작업에서
새로 사용할 이유가 없다.


==================================================
40. 완료 보고 형식
==================================================

완료 후 반드시 다음을 보고하라.


1. 수정한 파일


2. Mini Success 오류 최초 발생 Stage


3. 08 Blueprint의 기존 Practice target


4. 08 Blueprint의 기존 Mini Success target


5. 09에서 target 변형 여부


6. 실제 root cause


7. 수정한 Stage와 이유


8. Mini Success target 선정 원칙


9. CAP 사용 여부
   (CAP을 사용했다면 왜 안전한지)


10. learned phoneme inventory 검증 방식


11. Practice target 수정 전/후


12. Mini Success target 수정 전/후


13. Practice scaffold 구조


14. Mini Success scaffold 구조


15. pause 전 answer 정보


16. pause 후 answer 정보


17. mini_success_answer_barrier_safe 구현 방식


18. mini_success_present 결과


19. practice_mini_success_progression_safe 결과


20. mini_success_answer_barrier_safe 결과


21. Thinking Time 3초 보존 여부


22. Viewer Action 보존 여부


23. [PAUSE 3 SEC] 보존 여부


24. Example Ladder 변화 여부


25. phoneme_explanation_safe 결과


26. example_scope_safe 결과


27. content_block_uniqueness_safe 결과


28. ending_resolves_opening 결과


29. 전체 Integrity Check 결과


30. Script Score 전/후


31. Ready for Direction 여부


32. 추가한 테스트 수


33. 전체 테스트 결과


34. 05~07 또는 05~08 기존 데이터 불변 여부
    (수정 Stage에 따라 정확히 보고)


35. 기존 CLI 하위 호환 여부


36. Gemini API 사용량


37. YouTube API 사용량


38. "고유한 소리" 표현 조사 결과


39. "3주만 지나도 완전히 지워집니다" 등
    claim safety 제한사항


40. 발견된 추가 제한사항


==================================================
41. 성공 조건
==================================================

성공은:

MAP을 CAP으로 바꾸는 것 자체

가 아니다.


진짜 성공 조건은:


Guided Practice와 Mini Success가
교육적으로 다른 역할을 가진다.


Mini Success는 이미 배운 material만 사용한다.


Mini Success는 새로운 독립 적용이다.


Pause 전에는 정답 핵심 phoneme이 없다.


Target 철자는 보여준다.


Thinking Time 3초를 보존한다.


Pause 후 정답을 확인한다.


Mini Success Gate 3개가 모두 pass한다.


다른 Integrity Check를 약화시키지 않는다.


Ready for Direction = YES


이다.


==================================================
42. 절대 금지
==================================================

검증기를 느슨하게 만들어 MAP 반복을 통과시키지 마라.

CAP을 모든 영상에 하드코딩하지 마라.

새 Mini Success에 아직 안 배운 규칙을 넣지 마라.

Pause 전에 answer phoneme을 넣지 마라.

Thinking Time을 제거하지 마라.

Viewer Action을 제거하지 마라.

09가 08 target을 이유 없이 바꾸지 마라.

08이 원인인데 09에서만 땜질하지 마라.

09가 원인인데 08까지 불필요하게 변경하지 마라.

DB의 ready_for_direction 값을 수동 UPDATE하지 마라.

기존 row를 삭제해서 결과를 맞추지 마라.

Script Score를 조작하지 마라.

Mini Success 때문에 전체 Script를 대규모 재작성하지 마라.

11/12 코드를 수정하지 마라.


==================================================
43. 최종 원칙
==================================================

Mini Success는:

"방금 알려준 답을 따라 하는 구간"

이 아니다.


Mini Success는:

"방금 배운 원리를
새로운 쉬운 문제에
스스로 적용해 성공하는 구간"

이다.


따라서:

GUIDED EXAMPLE
→ GUIDED PRACTICE
→ INDEPENDENT TRANSFER

라는 학습 progression이
실제 Content Script 안에서 보여야 한다.


이번 수정의 목적은
Gate를 통과시키는 것이 아니라

그 progression을 실제로 만들고,
Gate가 그것을 정확히 검증하게 하는 것이다.