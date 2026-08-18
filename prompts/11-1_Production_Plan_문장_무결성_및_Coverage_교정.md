# 11-1단계: Production Plan 문장 무결성 및 Coverage 교정

현재 프로젝트의 05~11단계 전체 구조와
가장 최근 Production Plan Report를 먼저 읽고,
11단계 Production Planner의 책임과 기존 테스트를 충분히 이해한 뒤 수정하라.

이번 작업은 새로운 Stage를 추가하는 것이 아니다.

11단계 Production Planner의 교정 작업이다.

목표는:

"11단계가 생성한 Production Plan을 실제 TTS/Asset Generator에
안전하게 전달할 수 있는 상태로 만드는 것"

이다.


==================================================
0. 현재 상태
==================================================

현재 최신 Production Plan:

final_format:
EDUCATION

Production Blocks:
8개

Speech Assets:
55개

Speech Mode:

KO_NARRATION 43
EN_NATIVE 4
EN_PHONEME_DEMO 8

Voice:

Charon 55


현재 Integrity Check:

19개 중 18개 pass

required_content_covered:
fail

Ready for Asset Generation:
NO


Planner Score:
95.1


현재 전체 테스트:

378 passed


이번 수정 후에도:

05~10 기존 데이터
09 Content Script
10 Video Direction

을 변경하지 않는다.


==================================================
1. 이번 수정의 핵심 원칙
==================================================

11단계의 역할은:

교육 내용을 다시 쓰는 것

이 아니다.


11단계의 역할은:

09 Content Script
+
10 Video Direction

을 실제 제작 가능한 Production Plan으로
compile하는 것이다.


따라서:

Content meaning
Educational scope
Pronunciation meaning
Teaching claims

을 11단계가 임의로 다시 작성하면 안 된다.


허용:

문장을 TTS 단위로 분리
영어 target을 별도 Speech Asset으로 분리
IPA를 별도 Speech Asset으로 분리
pause 삽입
visual instruction 연결
answer reveal 순서 조정
production metadata 생성


금지:

교육 의미 재작성
새 규칙 추가
기존 scope 확대
발음 설명 변경
상위 단계에서 제거한 잘못된 표현 복원


==================================================
2. 실제 발견 문제 A
   "고유한 소리" 표현 재등장
==================================================

현재 CB02에 다음 표현이 존재한다.

"각 글자가 이 단어에서 내는 고유한 소리를
하나씩 찾아내야 합니다."


이 표현은 이전 단계에서 이미 교정한
교육 표현 원칙과 충돌한다.


문제:

초보 학습자가

letter = one fixed unique sound

로 오해할 수 있다.


11단계는 상위 단계에서 안전하게 정리된
교육 표현을 다시 위험한 표현으로 바꾸면 안 된다.


==================================================
3. Educational Wording Preservation
==================================================

새 원칙:

Production Planner는 Content Script의
교육적 의미를 보존해야 한다.


특히 다음 계열 표현을 새로 만들어내지 않는다.

"고유한 소리"
"정해진 소리"
"항상 이 소리"
"글자는 원래 이 소리"
"무조건 이 소리"


상위 단계에서 이미 범위가 한정된 경우:

"BAG에서 B는 /b/ 소리를 나타냅니다."

처럼 그대로 보존한다.


필요하면 기존 08/09의:

example_scope_safe

또는 해당 저수준 검사 함수를
재사용한다.


새로운 별도 의미 규칙을 중복 구현하지 않는다.


==================================================
4. Production Planner의 narration 처리 원칙
==================================================

11단계는 narration을 새로 창작하기보다:

PRESERVE
SPLIT
RECONNECT

하는 compiler처럼 동작해야 한다.


즉:

원문

"BAG에서 B는 /b/ 소리를 냅니다."

를

KO_NARRATION:
"BAG에서 B는"

EN_PHONEME_DEMO:
/b/

KO_NARRATION:
"소리를 냅니다."

처럼 분리하는 것은 허용된다.


하지만:

"각 글자에는 고유한 소리가 있습니다."

처럼 의미를 다시 쓰는 것은 금지한다.


==================================================
5. 실제 발견 문제 B
   standalone punctuation Speech Asset
==================================================

현재 실제 Production Plan에서:

CB03:

EN_PHONEME_DEMO /b/
KO_NARRATION "-"
EN_PHONEME_DEMO /æ/


CB05:

EN_PHONEME_DEMO /m/
KO_NARRATION "-"
EN_PHONEME_DEMO /æ/
KO_NARRATION "-"
EN_PHONEME_DEMO /p/


형태가 생성되었다.


이것은 실제 TTS로 보내면 안 된다.


"-"

는 한국어 narration이 아니다.


==================================================
6. Speech Fragment Integrity
==================================================

신규 결정론적 Integrity Check:

speech_fragment_integrity_safe


모든 SPEECH Asset의 source_text를 검사한다.


다음처럼 punctuation/symbol만 존재하는
Speech Asset은 fail이다.


예:

"-"
"--"
"."
","
":"
";"
"|"
"/"
"+"
"→"
"="
"·"
"…"


whitespace + punctuation만 있는 경우도 fail.


예:

" - "
" , "
"..."



단:

실제 linguistic target인 IPA:

/b/
/æ/
/g/

는 EN_PHONEME_DEMO이므로 허용한다.


즉 단순 punctuation 검사 때문에
IPA를 제거하면 안 된다.


==================================================
7. punctuation 처리
==================================================

연결 기호는 Speech Asset으로 만들지 않는다.


예:

/b/ - /æ/ - /g/


의 "-"는 실제 음성이 아니다.


필요하다면:

visual connector

또는

timing relation

또는

metadata

로 표현한다.


11단계에서 별도 구조가 필요하지 않다면
그냥 Speech Asset 생성 대상에서 제외해도 된다.


핵심은:

Charon에게 "-"

를 읽으라고 요청하는 Asset을
만들지 않는 것이다.


==================================================
8. Fragmented Korean 검사
==================================================

punctuation-only뿐 아니라
영어/IPA token 제거 후 남은 한국어 조각이
독립적으로 TTS 가능한 문장인지도 확인해야 한다.


예:

BAD:

"가 있습니다."

"에서 첫 글자 C는"

"소리를 냅니다. 가운데 A는"

", 끝 글자 P는"

"소리입니다."


이런 조각들이 각각 독립 Speech Asset으로
생성되면 실제 TTS에서 문장이 깨진다.


==================================================
9. 신규 검사
   narration_fragment_safe
==================================================

결정론적 백스톱을 추가한다.


최소 다음 위험 패턴을 탐지한다.


Speech Asset 시작이:

"가 있습니다"
"이 있습니다"
"에서 "
"의 "
"를 "
"을 "
"은 "
"는 "
"이 "
"가 "
","
"."
"-"


처럼 앞 Asset의 누락된 명사/target에
문법적으로 의존하는 경우.


그러나 한국어 전체 문법을 정규식으로
판정하려 하지 않는다.


이번 실제 회귀 형태를 안정적으로 잡는
conservative backstop으로 구현한다.


1차 방어선은 segmentation algorithm이다.


==================================================
10. 실제 발견 문제 C
    CAP Answer Hiding
==================================================

현재 CB06은 정답 선공개 방지를 위해
CAP과 음소를 narration에서 제거했지만,

그 결과:

"모자를 뜻하는 단어"
"가 있습니다."
"에서 첫 글자 C는"
"소리를 냅니다. 가운데 A는"
", 끝 글자 P는"
"소리입니다."

같은 깨진 narration이 생성됐다.


answer_not_revealed_before_attempt 자체는 pass지만,

시청자에게 들려줄 narration 품질은 실패다.


==================================================
11. Answer Hiding 원칙
==================================================

정답을 숨길 때:

token deletion

방식으로 문장을 훼손하지 않는다.


BAD:

원문:

"CAP에서 C는 /k/ 소리를 냅니다."

↓

CAP과 /k/ 삭제

↓

"에서 C는 소리를 냅니다."


금지.


정답 은닉은:

semantic reconstruction

또는

safe template

방식으로 처리한다.


==================================================
12. Mini Success Safe Template
==================================================

viewer_action + thinking_time이 있는
MINI_SUCCESS Block에서는

정답을 숨겨야 할 경우
안전한 결정론적 narration template을
사용할 수 있다.


예:

"이제 마지막 단어는 여러분 차례입니다.
화면에 나온 세 글자를 보세요.
앞에서 연습한 방법대로 각 소리를 떠올린 뒤,
직접 이어서 읽어보세요."


그 후:

VISUAL:
CAP

PAUSE:
3000ms

EN_NATIVE:
CAP


그리고 정답 공개 후:

KO_NARRATION:
"이번에는 소리를 하나씩 확인해보겠습니다."

EN_PHONEME_DEMO:
/k/

EN_PHONEME_DEMO:
/æ/

EN_PHONEME_DEMO:
/p/


이 구조는 허용한다.


==================================================
13. 중요한 Mini Success 보존 원칙
==================================================

현재 09/10/11에서 이미 확정된:

viewer_action
thinking_time_seconds
answer_not_revealed_before_attempt

를 변경하지 않는다.


현재 CAP:

thinking_time:
3000ms

반드시 보존.


정답 EN_NATIVE "CAP"은
PAUSE 이후에만 존재해야 한다.


/k/
/æ/
/p/

정답 음소 역시
attempt 이전 narration에서
정답으로 노출되면 안 된다.


==================================================
14. Answer Hiding과 required_content
==================================================

중요:

required_content에는:

"CAP에서 C는 /k/, A는 /æ/, P는 /p/"

가 필요하다.


하지만 이것이 반드시
PAUSE 이전에 있어야 한다는 뜻은 아니다.


required_content coverage는
Block 전체에서 만족하면 된다.


따라서:

PAUSE 후

CAP
/k/
/æ/
/p/

가 존재하면

교육 내용은 보존된 것이다.


coverage를 만족시키기 위해
정답을 pause 전에 다시 넣지 않는다.


==================================================
15. 실제 발견 문제 D
    STYLE_INTENT Coverage
==================================================

현재 CB08 required_content:

"자연스럽고 부담 없는 마무리 인사"


실제 narration:

"오늘 영상이 도움이 되셨다면 함께 연습을 이어가 보세요.
시청해 주셔서 감사합니다."


의미상 마무리 인사가 존재한다.


하지만 lexical overlap이 없어:

required_content_covered = fail

이 되었다.


이것은 콘텐츠 누락과
스타일/톤 요구를 같은 방식으로 검사해서 생긴 문제다.


==================================================
16. Required Content 종류 구분
==================================================

required_content를 검증할 때 최소:

FACTUAL_CONTENT
STYLE_INTENT

를 구분한다.


가능하면 기존 Content Block 구조를
대규모 변경하지 말고
11단계 내부 coverage classifier로 처리한다.


FACTUAL_CONTENT 예:

"BAG 예시 사용"

"BAG에서 B는 /b/"

"3초 생각 시간 후 CAP 정답 확인"

"다음 모음 o, e 연결"


이것들은 실제 Asset/내용 존재 여부를
결정론적으로 검증한다.


STYLE_INTENT 예:

"자연스럽고 부담 없는 마무리 인사"

"부담 없이 도전하도록 유도"

"친근하게 안내"

"차분하게 마무리"


이것들은 동일 lexical overlap 기준을
적용하면 안 된다.


==================================================
17. STYLE_INTENT 판정
==================================================

STYLE_INTENT를 무조건 pass시키지 않는다.


최소한 structural evidence가 있어야 한다.


예:

"자연스럽고 부담 없는 마무리 인사"


검증 신호:

Block learning_function == RESOLUTION

또는 Ending block


AND


실제 KO_NARRATION 존재


AND


ending/greeting/thanks/continuation 성격의
문장 신호 존재


예:

"감사합니다"
"다음 시간"
"함께"
"이어가"
"도움이 되셨다면"


등.


이 조건을 만족하면:

covered_with_style_evidence


로 판정 가능.


단순히 STYLE_INTENT라는 이유만으로
자동 pass 금지.


==================================================
18. Coverage 결과 구조
==================================================

가능하면 coverage 결과에:

coverage_type

을 남긴다.


예:

{
  "required_content": "자연스럽고 부담 없는 마무리 인사",
  "type": "STYLE_INTENT",
  "status": "covered",
  "evidence": ["SP055"],
  "method": "structural_style_evidence"
}


FACTUAL_CONTENT:

{
  "required_content": "BAG 예시 사용",
  "type": "FACTUAL_CONTENT",
  "status": "covered",
  "evidence": ["SP003"],
  "method": "content_match"
}


==================================================
19. 기존 required_content_covered 의미 보존
==================================================

기존 Integrity Check:

required_content_covered

를 삭제하거나 이름을 변경하지 않는다.


다만 내부 판정 방식을:

FACTUAL_CONTENT
+
STYLE_INTENT

를 올바르게 처리하도록 개선한다.


즉 validation을 약화시키는 것이 아니다.


false negative를 줄이는 것이다.


==================================================
20. Speech Segmentation 개선
==================================================

현재 regex 기반 segmentation 자체를
대규모 NLU 시스템으로 교체하지 않는다.


이번 수정의 목표는:

"실제 TTS에 넘길 수 없는 조각을 만들지 않는 것"


이다.


Segmentation 후 반드시 normalization 단계를 둔다.


예:

segment_speech()
↓
normalize_fragments()
↓
validate_fragments()
↓
create_speech_assets()


==================================================
21. normalize_fragments
==================================================

최소 다음 작업을 수행한다.


1.

punctuation-only fragment 제거


2.

빈 문자열 제거


3.

앞/뒤 whitespace 정리


4.

target 추출 후 남은 조사-only fragment가
앞 문장과 결합 가능하면 결합


5.

Mini Success answer hiding으로
문장이 파괴된 경우 safe template 사용


6.

의미 있는 narration은 보존


==================================================
22. 합치기 원칙
==================================================

무조건 짧은 Speech Asset을 앞뒤와 합치지 않는다.


예:

"와"

"에서"

등이 모든 상황에서 잘못된 것은 아니다.


특히:

KO_NARRATION
"/b/와"

처럼 IPA가 별도 Asset으로 빠졌을 경우

KO_NARRATION:
"와"

가 자연스럽게 이어질 수도 있다.


따라서 단순 글자 수 기준:

len(text) < N → merge

같은 규칙 금지.


문맥과 실제 segmentation origin을 이용한다.


==================================================
23. TTS Continuity Metadata
==================================================

필요하다면 Speech Asset 또는 Production Block metadata에:

continuation_from_previous
continuation_to_next

같은 힌트를 추가할 수 있다.


그러나 12단계가 반드시 이 필드를 필요로 하지 않는다면
억지로 DB 스키마를 늘리지 않는다.


핵심은 최종 Speech sequence가
실제로 자연스럽게 재생 가능해야 한다는 것이다.


==================================================
24. Speech Asset Deduplication 보존
==================================================

현재 장점:

EN_NATIVE BAG/BAT/MAP/CAP 재사용

EN_PHONEME_DEMO /æ/ 등 재사용


이 구조는 반드시 보존한다.


이번 narration fragment 수정 때문에
deduplication을 제거하지 않는다.


동일:

speech_mode
voice
source_text
delivery_intent

조합 재사용 원칙 유지.


==================================================
25. EN_NATIVE 보존
==================================================

현재:

BAG
BAT
MAP
CAP

4개 EN_NATIVE asset

구조를 보존한다.


delivery_instruction:

natural pronunciation
no spelling
no explanation

의 의미도 보존한다.


==================================================
26. EN_PHONEME_DEMO 보존
==================================================

현재:

/b/
/æ/
/g/
/t/
/m/
/p/
/k/

등의 phoneme asset 구조를 보존한다.


source_text:

IPA 원문


expected_pronunciation:

IPA 원문


원칙 유지.


IPA를 한글 근사 발음으로 교체하지 않는다.


==================================================
27. 현재 실제 BAG Production Plan에서
    기대하는 수정 결과
==================================================

수정 후 최소 다음이 성립해야 한다.


CB03:

"-" 단독 KO_NARRATION Asset = 0


CB05:

"-" 단독 KO_NARRATION Asset = 0


CB06:

"가 있습니다."

"에서 첫 글자 C는"

같은 깨진 독립 narration = 0


CB06:

VISUAL CAP
→ PAUSE 3000ms
→ EN_NATIVE CAP

순서 보존


CB06:

/k/
/æ/
/p/

정답 음소는 attempt 이후 확인 단계에서 제시


CB08:

"자연스럽고 부담 없는 마무리 인사"

STYLE_INTENT coverage = covered


==================================================
28. 새 Integrity Check
==================================================

기존 19개를 삭제하거나 의미 변경하지 않는다.


신규 최소:

speech_fragment_integrity_safe
narration_fragment_safe
educational_wording_preserved


총 최소 22개.


A.

speech_fragment_integrity_safe

punctuation-only Speech Asset 금지.


B.

narration_fragment_safe

segmentation 또는 answer hiding으로 인해
독립 재생 불가능한 명백한 한국어 fragment 금지.


C.

educational_wording_preserved

11단계가 상위 단계의 교육 의미를
위험하게 재작성하지 않았는지 검사.


가능하면 08/09의 기존
scope/phoneme 관련 저수준 함수를 재사용한다.


==================================================
29. Ready for Asset Generation Gate
==================================================

다음 critical 항목이 모두 pass여야 한다.


required_content_covered

speech_fragment_integrity_safe

narration_fragment_safe

educational_wording_preserved

answer_not_revealed_before_attempt

thinking_time_preserved

phoneme_source_of_truth_preserved

speech_mode_valid

voice_casting_valid

asset_references_valid

timeline_order_valid


하나라도 critical fail이면:

ready_for_asset_generation = NO


Planner Score가 높아도 덮어쓰지 않는다.


==================================================
30. Planner Score
==================================================

기존 점수 공식을 가능하면 변경하지 않는다.


이번 11-1은:

점수를 높이는 작업

이 아니라

Production Plan을 실제 실행 가능한 상태로
교정하는 작업이다.


신규 Integrity Check는 Gate 중심으로 사용한다.


==================================================
31. 테스트 — 실제 회귀 CASE
==================================================

최소 다음 테스트를 추가한다.


CASE A

KO_NARRATION source_text="-"

→ speech_fragment_integrity_safe fail


CASE B

KO_NARRATION source_text=" , "

→ fail


CASE C

EN_PHONEME_DEMO source_text="/æ/"

→ punctuation으로 오인하지 않고 pass


CASE D

빈 Speech fragment

→ 생성 금지


CASE E

CB03의:

/b/ - /æ/

분절

→ "-" Speech Asset 생성되지 않음


CASE F

CB05:

/m/ - /æ/ - /p/

→ "-" Speech Asset 0개


CASE G

Mini Success answer hiding 후:

"가 있습니다."

같은 orphan fragment

→ narration_fragment_safe fail


CASE H

"에서 첫 글자 C는"

같은 orphan fragment

→ fail


CASE I

정상 narration:

"이번에는 소리를 하나씩 확인해보겠습니다."

→ pass


CASE J

CAP safe reconstruction 생성 후
문장 자연성 구조 검증


CASE K

CAP VISUAL이 PAUSE 전에 존재


CASE L

CAP EN_NATIVE answer는
PAUSE 이후에만 존재


CASE M

CAP /k/ /æ/ /p/ answer phoneme도
attempt 이후에 존재


CASE N

CAP 3000ms 보존


CASE O

"자연스럽고 부담 없는 마무리 인사"

STYLE_INTENT로 분류


CASE P

CB08 실제 ending narration 존재 시
STYLE_INTENT covered


CASE Q

STYLE_INTENT라는 이유만으로
narration 없는 Block을 자동 pass하지 않음


CASE R

FACTUAL_CONTENT 기존 coverage 방식 보존


CASE S

"BAG 예시 사용"이 없으면
required_content_covered fail 유지


CASE T

"고유한 소리" 위험 표현이
11단계에서 새로 생성되면
educational_wording_preserved fail


CASE U

안전한:

"이 단어에서 나타내는 소리"

→ pass


CASE V

EN_NATIVE BAG/BAT/MAP/CAP 보존


CASE W

EN_PHONEME_DEMO source of truth 보존


CASE X

Speech Asset deduplication 회귀 없음


CASE Y

55개라는 기존 Asset 개수를
강제로 유지하지 않음

이유:
잘못 생성된 punctuation/orphan asset 제거로
개수가 줄어드는 것이 정상일 수 있음.


CASE Z

Production Block 8개 보존


CASE AA

05~10 source 데이터 불변


CASE AB

기존 11단계 테스트 회귀 없음


CASE AC

기존 CLI:

research production-plan [--direction-id ID]

시그니처 불변


CASE AD

전체 기존 테스트 통과


==================================================
32. 매우 중요한 테스트 원칙
==================================================

현재 Speech Asset 수:

55개


수정 후에도 반드시 55개여야 한다고
테스트하지 않는다.


현재 55개 안에는:

"-"

같은 잘못된 Asset이 포함되어 있다.


따라서 올바른 결과가:

53
51
49

등으로 줄어들 수도 있다.


중요한 것은 숫자가 아니라:

필요한 교육 Speech가 모두 존재하고
불필요한/깨진 Speech가 없는 것

이다.


==================================================
33. 실데이터 재생성
==================================================

수정 후 최신 Video Direction을 기준으로
11 Production Plan을 새 row로 재생성한다.


기존 production_plans row를
수정하거나 삭제하지 않는다.


Stage 원칙:

기존 산출물 immutable
새 실행 = 새 row


를 유지한다.


==================================================
34. 재생성 후 직접 검사
==================================================

새 Production Plan에서 반드시 직접 확인:


1.

Production Block 수


2.

Speech Asset 총수


3.

KO_NARRATION 수


4.

EN_NATIVE 수


5.

EN_PHONEME_DEMO 수


6.

"-" 단독 Speech Asset 수


7.

punctuation-only Speech Asset 수


8.

orphan Korean fragment 수


9.

"고유한 소리" 표현 존재 여부


10.

CAP pre-answer narration


11.

CAP VISUAL 위치


12.

CAP PAUSE 위치


13.

CAP EN_NATIVE 위치


14.

CAP phoneme answer 위치


15.

CB08 coverage


==================================================
35. 기대하는 CAP 구조
==================================================

정확한 문구를 강제하지는 않는다.


하지만 의미 구조는 최소:


KO_NARRATION:

시청자 차례임을 안내


KO_NARRATION:

화면의 단어를 직접 읽도록 요청


VISUAL:

CAP


PAUSE:

3000ms


EN_NATIVE:

CAP


KO_NARRATION:

정답의 소리를 확인한다는 transition
(필요한 경우)


EN_PHONEME_DEMO:

/k/


EN_PHONEME_DEMO:

/æ/


EN_PHONEME_DEMO:

/p/


순서여야 한다.


==================================================
36. CB08 기대 결과
==================================================

현재 실제 narration:

"영어 단어는 외우려고 할수록 복잡해지지만,
소리가 이어지는 원리를 이해하면 훨씬 쉬워집니다.
오늘 영상이 도움이 되셨다면 함께 연습을 이어가 보세요.
시청해 주셔서 감사합니다."


이 narration 자체를
coverage 점수를 위해 불필요하게 다시 쓰지 않는다.


"자연스럽고 부담 없는 마무리 인사"

required_content는:

STYLE_INTENT

로 분류하고

Ending/Resolution 구조 +
실제 마무리 narration evidence

로 검증한다.


==================================================
37. 12단계와의 책임 경계
==================================================

이번 작업에서 Gemini TTS를 호출하지 않는다.


이번 작업에서:

WAV 생성 금지

실제 음성 생성 금지

실제 duration 측정 금지

Asset cache 구현 금지

Source Clip 추출 금지


이것들은 12단계 책임이다.


11-1은 오직:

"12단계가 믿고 실행할 수 있는
Production Specification"

을 만든다.


==================================================
38. API quota
==================================================

11단계는 기존처럼 결정론적이어야 한다.


Gemini API:
0

YouTube API:
0


새 API 호출을 추가하지 않는다.


==================================================
39. 보고서
==================================================

완료 후 다음을 보고한다.


1. 수정한 파일

2. Production Planner에서 수정한 핵심 로직

3. "고유한 소리" 재등장 원인

4. educational_wording_preserved 구현 방식

5. punctuation-only Speech 처리 방식

6. speech_fragment_integrity_safe 구현 방식

7. orphan Korean fragment 원인

8. narration_fragment_safe 구현 방식

9. CAP answer hiding 기존 문제 원인

10. CAP safe reconstruction 방식

11. 재생성된 CAP pre-answer narration

12. CAP VISUAL → PAUSE → ANSWER 실제 순서

13. CAP 3000ms 보존 여부

14. CB03 "-" Asset 제거 결과

15. CB05 "-" Asset 제거 결과

16. 전체 punctuation-only Speech Asset 수

17. 전체 orphan narration 수

18. STYLE_INTENT / FACTUAL_CONTENT 구분 방식

19. CB08 "자연스럽고 부담 없는 마무리 인사"
    coverage 결과

20. required_content_covered 최종 결과

21. 기존 19개 Integrity Check 보존 여부

22. 신규 Integrity Check 목록

23. 전체 Integrity Check 결과

24. 수정 전 Speech Asset 수: 55

25. 수정 후 Speech Asset 수

26. Speech Mode별 개수

27. Voice별 개수

28. EN_NATIVE BAG/BAT/MAP/CAP 보존 여부

29. EN_PHONEME_DEMO 보존 여부

30. Speech deduplication 보존 여부

31. Production Block 8개 보존 여부

32. Planner Score 전/후

33. Ready for Asset Generation 여부

34. 추가한 테스트 수

35. 전체 테스트 결과

36. 05~10 회귀 여부

37. 기존 CLI 하위 호환 여부

38. Gemini API 사용량

39. YouTube API quota 사용량

40. 발견된 제한사항


==================================================
40. 성공 조건
==================================================

이번 수정의 성공은:

Planner Score 100

이 아니다.


다음이 모두 성립하는 것이다.


required_content_covered:
pass


speech_fragment_integrity_safe:
pass


narration_fragment_safe:
pass


educational_wording_preserved:
pass


CAP 3초:
preserved


answer_not_revealed_before_attempt:
pass


punctuation-only Speech:
0


명백한 orphan Korean Speech:
0


EN_NATIVE:
preserved


EN_PHONEME_DEMO:
preserved


Ready for Asset Generation:
YES


==================================================
41. 절대 금지
==================================================

required_content_covered를 통과시키기 위해
검사를 삭제하지 마라.

STYLE_INTENT를 전부 자동 pass시키지 마라.

Speech Asset 개수 55를 억지로 유지하지 마라.

"-"를 TTS용 Speech로 남겨두지 마라.

CAP 정답을 문장 자연성을 고친다는 이유로
PAUSE 전에 노출하지 마라.

CAP 3초를 줄이거나 삭제하지 마라.

IPA를 한글 발음으로 대체하지 마라.

EN_NATIVE를 KO_NARRATION에 합치지 마라.

상위 단계의 교육 의미를 다시 쓰지 마라.

Gemini를 호출해 문장을 고치지 마라.

기존 production_plan row를 수정/삭제하지 마라.

12단계 Asset Generator를 구현하지 마라.

최종 Renderer를 구현하지 마라.


==================================================
42. 최종 원칙
==================================================

11 Production Planner는 작가가 아니다.

11 Production Planner는:

검증된 Content Script와
Video Direction을

실제 제작 가능한
Production Specification으로 변환하는 compiler다.


따라서 가장 중요한 것은:

"내용을 더 잘 써주는 것"

이 아니라

"상위 단계의 의미를 손상시키지 않고
실제 TTS/Asset Generator가 그대로 실행할 수 있게 만드는 것"

이다.


이번 수정 후:

09
Content meaning

↓

10
Direction

↓

11
Clean Production Specification

↓

12
Verified Asset Generation


이 경계가 명확하게 유지되어야 한다.