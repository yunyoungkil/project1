# 11-2단계: Required Content Coverage 의미 유형 교정

현재 프로젝트의 05~11-1 전체 구조와
가장 최근 실제 Production Plan Report를 먼저 읽고,
11단계 Production Planner의
required_content coverage 로직을 충분히 이해한 뒤 수정하라.

이번 작업은 새로운 Stage를 추가하는 것이 아니다.

11단계 Production Planner의
Required Content Coverage 판정 정확도를 높이는 교정 작업이다.

목표:

"required_content를 모두 narration 텍스트 겹침으로 검증하지 말고,
그 요구가 어떤 종류인지에 따라
실제 Production Plan 안의 올바른 evidence source를 사용해 검증한다."

중요:

검증을 약화하지 마라.
UNCOVERED를 억지로 covered로 바꾸지 마라.
STYLE_INTENT를 자동 pass시키지 마라.
STRUCTURAL requirement를 narration 어휘로 찾지 마라.


==================================================
0. 현재 실제 실패 사례
==================================================

현재 최신 Production Plan:

final_format:
EDUCATION

Production Blocks:
8개

Speech Assets:
44개

Speech Modes:
KO_NARRATION 31
EN_NATIVE 4
EN_PHONEME_DEMO 9

Voice:
Charon 44

Integrity Check:
22개 중 required_content_covered 하나만 fail

Ready for Asset Generation:
NO


실제 UNCOVERED 2건:

CB06:
"정답 공개 전 3초 생각 시간 부여"

CB08:
"차분하고 권위적이지 않은 마무리 멘트"


하지만 실제 Production Plan에는:

CB06:

VISUAL [TARGET_WORD] CAP
PAUSE 3000ms (THINKING_DOTS)
EN_NATIVE CAP

순서가 존재한다.

즉 3초 생각 시간은 실제로 구현되어 있다.


CB08:

KO_NARRATION:
"가운데 모음이 a가 아니라 o나 e로 바뀌면...
다음 시간에도 함께 확인해 보겠습니다."

라는 실제 closing narration이 존재한다.


따라서 현재 false negative의 원인은:

required_content의 성격과 무관하게
lexical/content overlap 중심으로 coverage를 판정하는 방식에 있다.


==================================================
1. 이번 수정의 핵심 철학
==================================================

Required Content는 모두 같은 종류가 아니다.

예:

"BAG 예시 사용"
→ 콘텐츠 사실

"3초 생각 시간 제공"
→ 구조/타임라인 요구

"정답 공개 전에 직접 읽어보기"
→ 상호작용/순서 요구

"차분하고 권위적이지 않은 마무리"
→ 스타일/톤 요구


이들을 동일한 lexical matching으로 검증하면 안 된다.


따라서 최소 다음 4개 의미 유형으로 분류한다.


FACTUAL_CONTENT

STRUCTURAL_REQUIREMENT

INTERACTION_REQUIREMENT

STYLE_INTENT


필요하면 기존 11-1의
FACTUAL_CONTENT / STYLE_INTENT 분류를
하위 호환 형태로 확장하라.


==================================================
2. Type 정의
==================================================

A. FACTUAL_CONTENT

실제로 영상에 들어가야 하는
학습 내용/예시/정답/개념.

예:

"BAG 예시 단어 사용"

"B의 /b/, A의 /æ/, G의 /g/ 음소 제시"

"단모음 a 기초 3글자 단어 범위 정리"

이 유형은 기존처럼:

speech
visual
phoneme
clip

등의 콘텐츠 evidence로 검증한다.


B. STRUCTURAL_REQUIREMENT

콘텐츠가 아니라
시간/순서/배치/구조가 요구사항인 경우.

예:

"3초 생각 시간 제공"

"정답 공개 전에 pause"

"답 공개 후 phoneme 확인"

"원본 clip replay"

이 유형은:

timeline event
pause duration
event order
replay relation

등으로 검증한다.


C. INTERACTION_REQUIREMENT

학습자가 실제로 해야 하는 행동이나
attempt/reveal 관계가 요구사항인 경우.

예:

"시청자가 직접 읽어보게 한다"

"정답 공개 전에 스스로 소리 조합"

"첫 읽기 성공 경험 제공"

이 유형은:

viewer_action
thinking_time
attempt event
answer reveal order
mini_success block
confirmation narration

등으로 검증한다.


D. STYLE_INTENT

말투/분위기/마무리 방식/친근함 등
내용이 아닌 표현 의도.

예:

"차분하고 권위적이지 않은 마무리"

"자연스럽고 부담 없는 안내"

"간결한 마무리 인사"

"격려하는 톤"

이 유형은:

block role
narration 존재
closing/ending 구조
tone metadata
금지 tone 신호 부재

등으로 검증한다.


==================================================
3. 기존 classify_required_content_type 확장
==================================================

현재 11-1에서 만든:

classify_required_content_type()

또는 동등 함수가 있다면 삭제하지 말고 확장하라.

현재:

FACTUAL_CONTENT
STYLE_INTENT

만 지원한다면 최소:

FACTUAL_CONTENT
STRUCTURAL_REQUIREMENT
INTERACTION_REQUIREMENT
STYLE_INTENT

를 지원하게 한다.


기존 반환 형식/DB 호환성을 깨지 마라.


==================================================
4. Type 판정 우선순위
==================================================

단순 style 단어 하나만 보고 판정하지 않는다.


권장 우선순위:


Priority 1:
STRUCTURAL_REQUIREMENT

명확한 시간/순서/재생 구조 신호가 있는가?

예:

초
분
생각 시간
pause
정답 공개 전
공개 후
재생
replay
순서
먼저
뒤에


Priority 2:
INTERACTION_REQUIREMENT

viewer action / attempt / success / challenge 신호가 있는가?

예:

직접
시도
읽어보
소리 내어
생각해
도전
성공 경험
격려
확인해보


Priority 3:
FACTUAL_CONTENT

단어/IPA/예시/규칙/숫자 factual teaching content가 있는가?


Priority 4:
STYLE_INTENT

차분한
자연스러운
부담 없는
간결한
친근한
권위적이지 않은
격려하는
부드러운

등.


단:

"3초 생각 시간 제공"은
숫자가 있다는 이유로 FACTUAL_CONTENT로 분류하면 안 된다.

숫자가 시간 구조와 결합되어 있으므로
STRUCTURAL_REQUIREMENT가 우선이다.


==================================================
5. STRUCTURAL_REQUIREMENT Coverage
==================================================

신규 helper를 권장:

check_structural_requirement_coverage(...)

또는 동등 역할.


텍스트가 아니라 실제 timeline을 본다.


예:

required_content:
"정답 공개 전 3초 생각 시간 부여"


검증:

해당 Block에 PAUSE event 존재

duration_ms == 3000
또는 thinking_time_seconds == 3과 일치

그리고

answer event가 PAUSE 뒤에 존재


위 조건이 만족되면 covered.


Evidence 예:

["PAUSE:event_3", "SPEECH:SP039"]


method:

"structural_timeline_evidence"


==================================================
6. 시간 표현 파싱
==================================================

다음 패턴을 최소 지원:

"3초"
"3 초"
"3초간"
"3초의 생각 시간"
"3초 생각 시간"

필요하면 regex로 정규화한다.


seconds_expected = 3


실제 timeline:

duration_ms = 3000


를 비교한다.


허용 오차를 둘 필요가 없다면 정확 비교.


향후 2500ms 등 다른 값이 있다면
요구값과 불일치로 fail.


==================================================
7. 정답 공개 전 구조 검증
==================================================

"정답 공개 전 3초 생각 시간"은
단순 PAUSE 3000ms만 있다고 covered가 아니다.


반드시:

TARGET PRESENTATION
→ PAUSE
→ ANSWER

순서가 존재해야 한다.


현재 CB06:

VISUAL CAP
→ PAUSE 3000ms
→ EN_NATIVE CAP

이므로 pass.


만약:

EN_NATIVE CAP
→ PAUSE 3000ms

이면 fail.


기존:

answer_not_revealed_before_attempt
timeline_order_valid

로직을 재사용할 수 있으면 재사용하라.


중복 검증 시스템을 만들지 마라.


==================================================
8. INTERACTION_REQUIREMENT Coverage
==================================================

신규 helper 권장:

check_interaction_requirement_coverage(...)


예:

"시청자 스스로 소리 조합 시도 안내"


검증 evidence:

viewer_action 존재
또는 interaction_spec 존재
또는 pre-answer narration에 직접 행동 유도


예:

"직접 읽어보세요"
"소리를 떠올려보세요"


이런 경우 covered.


==================================================
9. Mini Success / 성공 경험 Coverage
==================================================

예:

"시청자의 첫 읽기 성공 경험 격려"


이것을 Ending STYLE_INTENT로만 보지 않는다.


이 요구는:

INTERACTION_REQUIREMENT
+
STYLE 성격

이 섞여 있다.


Primary type은:

INTERACTION_REQUIREMENT

로 두는 것을 권장한다.


검증:

learning_function == MINI_SUCCESS
또는 production_intent == viewer_must_attempt_before_answer

AND

viewer_action 존재

AND

thinking time / delayed answer 구조 존재

AND

answer/confirmation narration 존재


그리고 "격려" 요소가 필요하다면:

confirmation narration에:

성공
잘
맞습니다
읽어냈
해냈
좋습니다
직접 연결
첫 연습

등의 evidence가 존재하는지 확인.


자동 pass 금지.


==================================================
10. Mixed requirement 처리
==================================================

한 required_content에:

구조 + 스타일
상호작용 + 스타일

이 섞일 수 있다.


예:

"3초 생각 시간을 주고 부담 없이 직접 읽어보게 한다"


한 타입만으로 정확히 표현하기 어렵다.


가능하면 internal classification에:

primary_type
secondary_types

를 지원할 수 있다.


예:

primary:
STRUCTURAL_REQUIREMENT

secondary:
INTERACTION_REQUIREMENT
STYLE_INTENT


하지만 기존 구조를 크게 바꾸고 싶지 않다면:

coverage evaluator가
여러 evidence source를 조합해서 판정해도 된다.


중요한 것은:

하나의 lexical overlap으로 끝내지 않는 것.


==================================================
11. STYLE_INTENT Coverage
==================================================

STYLE_INTENT를 자동 pass하지 않는다.


현재 CB08:

"차분하고 권위적이지 않은 마무리 멘트"


검증할 구조:


A.
Block이 final/closing 역할인가?


B.
KO_NARRATION이 실제 존재하는가?


C.
마무리/다음 주제/감사/함께하기 등
closing intent가 존재하는가?


D.
명백한 공격적/과장/권위적 tone signal이 없는가?


이 네 축을 본다.


==================================================
12. Ending Block 판정 확장
==================================================

현재 11-1의 is_ending_block이
RESOLUTION만 보는 구조라면
너무 좁을 수 있다.


실제 CB08은:

delivery_mode = EDUCATION

learning/purpose 상 final closing 역할


일 수 있다.


다음 신호를 함께 고려하라:

마지막 production block

content_block이 source script의 마지막 block

retention_role next_question/open_loop

closing narration

"다음 영상"
"다음 시간"
"감사합니다"
"함께"
"이어가"

등.


즉:

last_block

이면 강한 ending 후보.


==================================================
13. STYLE_INTENT — "차분하고"
==================================================

"차분하고 권위적이지 않은"은
내용 단어가 아니라 tone constraint다.


가능하면 Production Plan에
delivery_instruction / tone metadata가 있다면
그것을 evidence로 우선 사용한다.


없다면:

KO_NARRATION text +
block role +
금지 표현 absence

를 conservative하게 사용.


예:

PASS 가능:

"다음 시간에도 함께 확인해 보겠습니다."

같은 자연스러운 closing


FAIL 예:

"반드시 제 말을 따라야 합니다."

"이것만 하면 무조건 됩니다."

"지금 당장 외우세요."

같은 authoritative/aggressive 신호.


==================================================
14. STYLE_INTENT — "권위적이지 않은"
==================================================

negative style requirement를
positive keyword만으로 판정하지 않는다.


권장 방식:

forbidden tone signals가 없는지 검사.


초기 보수적 blacklist 예:

"무조건 하세요"
"반드시 해야 합니다"
"제대로 하려면"
"이것만 따라하세요"
"틀리면 안 됩니다"
"외우세요"
"당장"


기존 no_false_guarantee /
scope safety / tone guard가 있다면 재사용.


새 blacklist를 여러 곳에 중복 정의하지 마라.


==================================================
15. STYLE_INTENT — "간결한"
==================================================

향후 같은 문제가 재발할 수 있으므로
"간결한"도 STYLE_INTENT 신호어에 추가한다.


하지만 "간결한"이라는 단어가 있다고
covered가 되는 것은 아니다.


최종 narration이 지나치게 길지 않은지
구조적 보조 evidence를 사용할 수 있다.


예:

final block narration sentence count <= 적절한 값


단:

magic number를 남발하지 마라.


현재 스펙상 엄격한 길이 기준이 없다면
closing narration 존재 + 불필요 반복 없음 정도로 제한.


==================================================
16. Coverage 결과 구조
==================================================

가능하면 각 required_content마다 다음을 보고한다.


{
  "required_content": "정답 공개 전 3초 생각 시간 부여",
  "type": "STRUCTURAL_REQUIREMENT",
  "status": "covered",
  "evidence": [
    "VISUAL:3",
    "PAUSE:3000ms",
    "SPEECH:SP039"
  ],
  "method": "timeline_order_and_duration"
}


STYLE:

{
  "required_content": "차분하고 권위적이지 않은 마무리 멘트",
  "type": "STYLE_INTENT",
  "status": "covered",
  "evidence": [
    "BLOCK:CB08",
    "SPEECH:SP044"
  ],
  "method": "closing_structure_and_tone_evidence"
}


==================================================
17. 기존 compute_required_content_coverage 호환
==================================================

기존 Report/테스트가 기대하는:

required_content_coverage

구조를 가능하면 깨지 않는다.


현재 report에서:

- [CB06] "...": UNCOVERED

또는:

['SPEECH:...']


형태가 있다면
기존 human-readable 출력은 유지할 수 있다.


내부 상세 metadata만 확장해도 된다.


==================================================
18. FACTUAL_CONTENT 기존 동작 보존
==================================================

현재 잘 작동하는 항목:

BAG 예시

B /b/, A /æ/, G /g/

BAT

MAP

CAP

등은 기존 lexical/content coverage 로직으로
잘 커버되고 있다.


이 부분을 새 분류 시스템 때문에 깨뜨리지 마라.


기존 결과는 그대로 유지되어야 한다.


==================================================
19. 실제 CB06 Acceptance
==================================================

현재 required_content:

"정답 공개 전 3초 생각 시간 부여"


실제 events:

VISUAL [TARGET_WORD] CAP

PAUSE 3000ms (THINKING_DOTS)

EN_NATIVE CAP


따라서:


type:
STRUCTURAL_REQUIREMENT


status:
covered


method:
timeline_order_and_duration


이어야 한다.


==================================================
20. 실제 CB08 Acceptance
==================================================

현재 required_content:

"차분하고 권위적이지 않은 마무리 멘트"


실제 narration:

"가운데 모음이 a가 아니라 o나 e로 바뀌면
소리는 또 어떻게 달라질까요?
다음 영상에서는 다른 모음이 들어간 3글자 단어의
소리 연결도 함께 알아보겠습니다.
외우지 않고 소리로 이해하는 영어,
다음 시간에도 함께 확인해 보겠습니다."


현재 Block은 마지막 Production Block.


따라서 최소:


type:
STYLE_INTENT


closing structure:
present


KO_NARRATION:
present


authoritative violation:
absent


natural continuation:
present


이면 covered.


==================================================
21. False Positive 방지
==================================================

다음은 covered로 처리하면 안 된다.


CASE:

required:
"3초 생각 시간"

실제:
PAUSE 1000ms

→ fail


CASE:

PAUSE 3000ms는 있지만
answer가 pause 전에 나옴

→ fail


CASE:

"차분한 마무리"

final block narration 없음

→ fail


CASE:

마무리 narration은 있지만
"무조건 따라하세요. 반드시 해야 합니다."

→ STYLE_INTENT fail


CASE:

"직접 읽기 성공 경험"

viewer_action 없음

→ fail


==================================================
22. Integrity Check
==================================================

기존:

required_content_covered

이름을 삭제/변경하지 않는다.


이번 수정은 이 Check의
내부 판정 정확도를 높이는 작업이다.


기존 다른 21개 Check는
이름/의미 변경 없이 보존.


==================================================
23. 신규 optional diagnostics
==================================================

필요하면 별도 diagnostics:

required_content_type_valid
required_content_evidence_source_valid

등을 추가할 수 있다.


하지만 꼭 필요하지 않으면
Integrity Check 개수를 억지로 늘리지 마라.


핵심은 기존 required_content_covered가
정확해지는 것이다.


==================================================
24. Ready for Asset Generation Gate
==================================================

현재 유일 blocker:

required_content_covered


수정 후 실제 모든 required content가
정상 evidence를 갖는다면:

required_content_covered:
pass


그리고 다른 critical check도 전부 pass라면:

Ready for Asset Generation:
YES


가 되어야 한다.


Score로 Gate를 덮어쓰지 않는다.


==================================================
25. Planner Score
==================================================

현재:

93.8


이번 작업 때문에 점수 공식을
임의 변경하지 않는다.


coverage가 실제로 개선되어
기존 공식에 따라 점수가 변한다면
그 결과만 그대로 보고.


==================================================
26. 실제 Production Block 수 보존
==================================================

현재:

8개


이번 coverage 검증 수정 때문에
Production Block을 새로 만들거나 삭제하지 않는다.


Speech Asset:

44개


역시 coverage를 맞추기 위해
억지로 추가/삭제하지 않는다.


이번 작업은 검증 로직 교정이지
Production Plan content 재작성 작업이 아니다.


==================================================
27. Speech/Timeline 내용 불변
==================================================

현재 정상인:

BAG
BAT
MAP
CAP

EN_NATIVE

EN_PHONEME_DEMO

Charon

CAP:

VISUAL
→ PAUSE 3000
→ EN_NATIVE

구조를 변경하지 않는다.


==================================================
28. 테스트 CASE — Type Classification
==================================================

최소 다음을 추가한다.


CASE A

"BAG 예시 단어 사용"

→ FACTUAL_CONTENT


CASE B

"정답 공개 전 3초 생각 시간 부여"

→ STRUCTURAL_REQUIREMENT


CASE C

"시청자가 직접 읽어본다"

→ INTERACTION_REQUIREMENT


CASE D

"차분하고 권위적이지 않은 마무리 멘트"

→ STYLE_INTENT


CASE E

"간결한 마무리 인사"

→ STYLE_INTENT


CASE F

"3초 생각 시간 + 직접 읽기"

→ structural/interation 혼합을
정상 처리


==================================================
29. 테스트 CASE — Structural Coverage
==================================================

CASE G

PAUSE 3000ms
+
answer after pause

→ 3초 thinking requirement covered


CASE H

PAUSE 1000ms

→ fail


CASE I

PAUSE 3000ms
하지만 answer before pause

→ fail


CASE J

VISUAL target
→ PAUSE 3000
→ answer

→ pass


CASE K

thinking_time=3 metadata만 있고
timeline PAUSE 없음

→ 기존 planner 정책에 따라
warning 또는 fail

실제 renderer용 구조가 필요하므로
가능하면 fail을 권장


==================================================
30. 테스트 CASE — Interaction Coverage
==================================================

CASE L

viewer_action 존재
+
attempt narration

→ covered


CASE M

viewer_action 없음
+
직접 행동 유도도 없음

→ fail


CASE N

MINI_SUCCESS
+
viewer_action
+
answer after pause
+
success confirmation

→ "첫 읽기 성공 경험" covered


CASE O

MINI_SUCCESS label만 있고
실제 attempt 없음

→ fail


==================================================
31. 테스트 CASE — Style Coverage
==================================================

CASE P

final block
+
KO_NARRATION
+
자연스러운 closing
+
authoritative blacklist 없음

→ "차분하고 권위적이지 않은 마무리" covered


CASE Q

final block narration 없음

→ fail


CASE R

final narration:
"무조건 따라하세요."

→ non-authoritative style requirement fail


CASE S

"간결한 마무리 인사"
+
짧은 closing narration

→ covered


CASE T

STYLE_INTENT라는 이유만으로
자동 covered 금지


==================================================
32. 테스트 CASE — Existing Factual Coverage
==================================================

CASE U

BAG example coverage 기존 pass 유지


CASE V

B /b/, A /æ/, G /g/ coverage 유지


CASE W

CAP target coverage 유지


CASE X

required factual target 실제 누락

→ fail 유지


==================================================
33. 테스트 CASE — Current Real Regression
==================================================

CASE Y

현재 CB06:

VISUAL CAP
PAUSE 3000
EN_NATIVE CAP

→ "정답 공개 전 3초 생각 시간 부여" covered


CASE Z

현재 CB08 final narration fixture

→ "차분하고 권위적이지 않은 마무리 멘트" covered


CASE AA

두 항목 모두 covered되면
required_content_covered pass


CASE AB

다른 21개 Integrity Check 회귀 없음


CASE AC

Ready for Asset Generation YES


==================================================
34. 기존 11-1 기능 회귀 방지
==================================================

반드시 확인:


speech_fragment_integrity_safe:
pass


narration_fragment_safe:
pass


educational_wording_preserved:
pass


punctuation-only Speech:
0


orphan narration:
0


CAP answer order:
보존


==================================================
35. 기존 09/10 데이터 불변
==================================================

이번 작업은 11단계 coverage 검증 수정.


다음을 변경하지 않는다:


video_scripts

video_directions

block_directions


기존 row UPDATE 금지.


새 production-plan 실행은
새 Production Plan row를 생성할 수 있다.


==================================================
36. 실데이터 재실행
==================================================

수정 후 반드시 실제 DB를 대상으로:

python -m research.cli production-plan

실행.


기존 row를 수정하지 않고
새 row 생성 원칙 유지.


==================================================
37. 실제 재생성 후 확인
==================================================

Report에서 반드시 확인:


1.
Production Block 수


2.
Speech Asset 수


3.
CB06 3초 requirement coverage


4.
CB08 style requirement coverage


5.
required_content_covered


6.
thinking_time_preserved


7.
answer_not_revealed_before_attempt


8.
speech_fragment_integrity_safe


9.
narration_fragment_safe


10.
educational_wording_preserved


11.
Ready for Asset Generation


==================================================
38. 기대 실데이터 결과
==================================================

현재 Production Plan 내용이
변하지 않는다는 전제에서:


CB06:

"정답 공개 전 3초 생각 시간 부여"
→ covered


CB08:

"차분하고 권위적이지 않은 마무리 멘트"
→ covered


required_content_covered:
pass


다른 21개:
pass


Ready for Asset Generation:
YES


Planner Score:
실제 공식 결과 그대로


==================================================
39. API Usage
==================================================

이번 작업은 완전 결정론적이어야 한다.


Gemini API:
0


YouTube API:
0


새 외부 API 호출 금지.


==================================================
40. 보고서 완료 형식
==================================================

완료 후 다음을 보고하라.


1. 수정한 파일

2. 기존 required_content_covered false negative 원인

3. 기존 FACTUAL/STYLE 2분류의 한계

4. 새 의미 유형 taxonomy

5. classify_required_content_type 수정 방식

6. STRUCTURAL_REQUIREMENT 판정 방식

7. INTERACTION_REQUIREMENT 판정 방식

8. STYLE_INTENT 판정 방식

9. FACTUAL_CONTENT 기존 로직 보존 여부

10. Mixed requirement 처리 방식

11. CB06 "3초 생각 시간" 분류 결과

12. CB06 coverage evidence

13. CB06 answer-after-pause 검증 결과

14. CB08 "차분하고 권위적이지 않은 마무리" 분류 결과

15. CB08 coverage evidence

16. 권위적 tone false positive/negative 방지 방식

17. "간결한" STYLE_INTENT 지원 여부

18. "격려" INTERACTION/STYLE 처리 방식

19. required_content_covered 수정 전/후

20. Production Block 수 전/후

21. Speech Asset 수 전/후

22. 기존 22개 Integrity Check 보존 여부

23. 전체 Integrity Check 결과

24. Planner Score 전/후

25. Ready for Asset Generation 수정 전/후

26. 추가한 테스트 수

27. 전체 테스트 결과

28. 09/10 데이터 불변 여부

29. 기존 CLI 하위 호환 여부

30. Gemini API 사용량

31. YouTube API 사용량

32. 실제 DB 재생성 여부

33. 발견된 제한사항


==================================================
41. 성공 조건
==================================================

성공은:

UNCOVERED 두 줄을
강제로 covered로 바꾸는 것

이 아니다.


성공 조건:


FACTUAL content
→ content evidence로 검증


STRUCTURAL requirement
→ timeline evidence로 검증


INTERACTION requirement
→ viewer/action/reveal evidence로 검증


STYLE intent
→ role/tone/closing evidence로 검증


그리고 실제 요구가 없으면
정직하게 fail.


현재 실데이터에서는:


PAUSE 3000ms가 실제 존재하므로
3초 thinking requirement covered


자연스러운 final narration이 존재하고
권위적 tone 위반이 없으므로
closing style requirement covered


required_content_covered pass


Ready for Asset Generation YES


가 되어야 한다.


==================================================
42. 절대 금지
==================================================

STYLE_INTENT를 무조건 pass시키지 마라.

STRUCTURAL requirement를 narration text로 찾지 마라.

3초 요구를 숫자 keyword 하나로 covered 처리하지 마라.

PAUSE 순서를 무시하지 마라.

answer-before-pause인데 covered 처리하지 마라.

final block이라는 이유만으로 style pass시키지 마라.

FACTUAL_CONTENT 기존 검증을 약화시키지 마라.

required_content_covered check를 삭제하지 마라.

Production Plan 내용을 coverage 때문에 다시 쓰지 마라.

Speech Asset을 coverage 맞추기 위해 추가하지 마라.

CAP timing을 바꾸지 마라.

기존 09/10 데이터를 수정하지 마라.

Gemini를 호출하지 마라.

12단계 Asset Generator를 구현하지 마라.

Renderer를 구현하지 마라.


==================================================
43. 최종 원칙
==================================================

Required Content Coverage는:

"문장에 비슷한 단어가 있는가?"

를 보는 기능이 아니다.


진짜 목적은:

"상위 단계에서 요구한 교육적/구조적/상호작용적/스타일적 의도가
Production Plan 안에 실제로 구현되어 있는가?"

를 검증하는 것이다.


따라서 evidence source는
requirement type에 맞아야 한다.


TEXT requirement
→ TEXT evidence


TIMING requirement
→ TIMELINE evidence


INTERACTION requirement
→ ACTION evidence


STYLE requirement
→ ROLE/TONE evidence


이 원칙으로 11단계의
required_content_covered를 교정하라.