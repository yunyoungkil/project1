# 프로젝트 작업 규칙 (Claude용)

이 파일은 이 프로젝트에서 반복적으로 확인된 규칙을 codify한 것입니다. `PROJECT_STATE.md`가
"현재 상태 요약(위키)"이라면, 이 파일은 "그 위키를 어떻게 다루고 다음 작업을 어떻게 할지"에 대한
규칙(스키마)입니다. 두 문서 다 canonical source가 아닙니다 — 진짜 source of truth는 항상
`data/research.db` + `assets/generated/plan_7/render/*.json` + 현재 코드입니다.

## 1. 새 스펙(`prompts/*.md`) 작업 시작 순서

1. `PROJECT_STATE.md`를 먼저 읽어 방향을 잡는다 — 단, 이 문서를 그대로 믿지 않는다.
2. 실제 DB(`select_canonical_visual_approval` 등)와 canonical JSON
   (`approved_visual_profile.json`)을 직접 조회해 재검증한다.
3. 스펙이 제시하는 예상 숫자(canonical id, test count, row count 등)는 참고값일 뿐이다 —
   하드코딩하지 말고 실제 값을 사용하며, 다르면 실제 값을 우선하고 차이를 보고한다.
4. 전체 `pytest -q`를 실제로 실행해 baseline을 확인한 뒤 작업을 시작한다.

## 2. "Human Review가 있었다"는 스펙의 주장을 절대 그대로 믿지 않는다

이 프로젝트에서 가장 많이 반복된 문제 패턴이다(13-4C-1/4/5/6/8/9/11/13에서 최소 8번 발생, 심지어
"이번엔 진짜다"라고 스펙이 직접 적은 경우도 포함). 스펙이 "이번 대화에서 사용자가 정확히 이렇게
말했다"는 식으로 특정 인용문·선택지를 주장하면:

- 실제 대화 기록에 그 발언이 있는지 먼저 확인한다.
- 없다면 절대 조용히 승인 처리하지 말고, **AskUserQuestion으로 직접 확인**한 뒤 사용자의 실제
  응답을 이번 결정의 근거로 삼는다.
- 특히 DB에 실제로 쓰는(APPROVED로 전환하는) 단계일수록 더 신중하게 확인한다.

## 3. Preview 값과 Human Approved 값을 혼동하지 않는다

- `CANDIDATES["CLEAN_DARK_FOCUS"]` (또는 다른 후보) 딕셔너리는 **Prototype preview source**일
  뿐이다. 승인 이후에는 절대 다시 읽지 않는다.
- 이미 APPROVED된 category의 실제 값은 canonical
  `category_approvals[category]["resolved_style"]`에서 읽는다 — `CANDIDATES`에서 다시 읽으면
  폐기된 preview 값(예: MUTED `#555b66`, Typography `68/42/26/18/14`)이 되살아나는 버그가 된다.
- 아직 PENDING인 category는 `CANDIDATES`가 유일한 preview source이므로 거기서 읽는 게 맞다.

## 4. DB 쓰기는 항상 append-only

- `visual_design_specs`의 기존 row를 UPDATE하지 않는다 — 항상 새 row를 INSERT하고
  `corrects_record_id`로 lineage를 남긴다.
- 새로운 Human Approval 단계를 만들 때는 `run_font_family_human_approval` /
  `run_background_human_approval` / `run_color_palette_human_approval` /
  `run_typography_scale_human_approval` / `run_font_weight_human_approval`
  (`research/visual_design.py`)의 패턴을 그대로 재사용한다 — 새 architecture를 발명하지 않는다.
- "실제로 결정된 후보 하나만 승인 가능하게 구조적으로 방어"하는 `HUMAN_SELECTED_*_CANDIDATE` 상수
  패턴(예: `HUMAN_SELECTED_FONT_WEIGHT_CANDIDATE`)을 새 승인 단계에도 동일하게 적용한다.

## 5. Historical Review artifact는 소급 수정하지 않는다

`assets/generated/plan_7/render/{prototypes,font_review,color_background_review,
muted_color_review,typography_scale_review,font_weight_review}/`는 그 당시 시점의 Human Review
증거다. 이후 canonical 값이 바뀌어도 과거 artifact가 옛날 값을 보여주는 것은 정상이며 절대
재생성/수정하지 않는다.

## 6. 외부 호출 / Git

- 명시적으로 요청받지 않은 이상 Gemini/YouTube/영상·이미지 생성 AI/Font network 호출을 하지 않는다.
- `git commit`/`git push`는 사용자가 명시적으로 요청할 때만 실행한다.

## 7. Plan Mode 사용 기준

- 새로운 설계 결정(예: 후보값 산출 규칙, 새 검증 로직)이 있는 작업은 Plan Mode로 먼저 계획한다.
- 이미 여러 번 반복된 확립된 패턴(예: N번째 category Human Approval 함수)은 직접 구현해도 된다 —
  단 구현 전 실제 canonical state는 항상 재확인한다.

## 8. 작업 완료 후

- `PROJECT_STATE.md`를 그 문서 자체의 Update Policy(18절)에 따라 갱신한다 — 매번 갱신할 필요는
  없고, canonical record 변경/category 승인/major stage 완료 시에만 갱신한다.
- README는 새 CLI 명령이나 승인 상태가 stale해졌을 때만 최소 범위로 갱신한다.
