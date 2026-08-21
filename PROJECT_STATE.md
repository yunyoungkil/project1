# PROJECT STATE

> Derived current-state summary. Machine-generated document, not authored as raw truth.
> Canonical Source of Truth: DB + canonical machine-readable artifacts + current code.
> Last Verified Against Canonical State: 2026-08-21 (13-4C-15 완료 직후, 실제 DB/코드 재조회로 검증됨)
> Document Type: DERIVED CURRENT-STATE SUMMARY
>
> **Important**: This document is NOT the canonical database. If this file conflicts with
> canonical state (DB / `approved_visual_profile.json` / code), verify the canonical state first —
> do not trust this file, and do not use this file to "correct" the DB.

## 1. Project Goal

한국 영어교육 YouTube 채널 "이해하면 쉬운 영어"(알파벳-소리 대응이 안 되는 성인 완전 초보자 대상)를
위한, 시장 리서치 → 콘텐츠 기획 → 실제 음성 에셋 생성 → 렌더링 준비까지 이어지는 production
pipeline입니다(단순 리서치 도구가 아님). 상세 정의는 `README.md` 1~17행 참고.

## 2. Current Position

- Current Major Stage: **13-4C Human Visual Review** (Visual Approval category-by-category 승인)
- Current Sub-stage: **13-4C-18 Success Style Human Review — Prototype 생성 완료, Human 결정 대기
  (NONE)** (`success_style` category는 여전히 PENDING, canonical id는 13-4C-17과 동일하게 **12**로
  불변 — 이 단계는 zero DB write)
- Next Planned Stage: 사람이 `success_style_review/index.html`을 보고 후보(COLOR_ONLY/
  BALANCED_SUCCESS/STRONG_SUCCESS) 선택 → 별도 단계에서 persist. 그 다음은 남은 mandatory
  category(`motion_style` 등) Human Review 준비
- Next Major Gate: Final Renderer Binding (아직 도달 못함)
- Renderer (Stage 14+): **NOT_STARTED** (코드베이스에 `research/render_spec.py`까지만 존재, 실제
  픽셀/MP4 렌더러 모듈 없음)

## 3. Pipeline Status

| Pipeline | Status | Evidence |
|---|---|---|
| Research (시장 조사) | COMPLETED | `research/youtube_search.py` 등, `data/research.db` |
| Content Planning (Topic~Production Plan) | COMPLETED | `production_plans` 테이블 (Plan 7) |
| Asset Generation (Gemini TTS) | COMPLETED | `generated_assets` 506건 |
| Human Pronunciation Review | **IN_PROGRESS** | `generated_assets.metadata_json.pronunciation_review`: APPROVED 152 / PENDING 31 / REGENERATE_REQUIRED 11 / NOT_REQUIRED 312 |
| Render Spec (13-1) | COMPLETED | `render_specs` 3건 |
| Render Timeline (13-2) | COMPLETED | `render_timelines` 2건 |
| Scene Layout (13-3) | COMPLETED | `scene_layouts` 2건 |
| Visual Design System (13-4A/B) | COMPLETED | `visual_design_specs`, `prototypes/`(rev 13-4B-R1) |
| Human Visual Review (13-4C) | **IN_PROGRESS** | 아래 5절/6절 참고 — 7/15 category APPROVED |
| Final Renderer Binding | BLOCKED | mandatory category 9개 중 3개 미승인 |
| Renderer (실제 픽셀/MP4 생성) | NOT_STARTED | 코드 없음 |
| MP4 | NOT_STARTED | — |

## 4. Canonical IDs and Versions

- Production Plan ID: **7**
- Visual Design Version: **13.4**
- Latest Canonical Visual Record ID: **12** (`visual_design_specs`, `record_status=CANONICAL_CORRECTION`,
  `corrects_record_id=11`)
- Prototype revision (13-4B): **13-4B-R1**
- Font Review revision (13-4C-3): **13-4C-3**
- Color/Background Review revision (13-4C-7): **13-4C-7**
- MUTED Review revision (13-4C-8): **13-4C-8**
- Typography Scale Review revision (13-4C-10): **13-4C-10**
- Font Weight Review revision (13-4C-12): **13-4C-12**
- Caption Style Review revision (13-4C-14): **13-4C-14**
- Caption Style Human Approval revision (13-4C-15): **13-4C-15**
- Focus Style Review revision (13-4C-16): **13-4C-16**
- Focus Style Human Approval revision (13-4C-17): **13-4C-17**
- Success Style Review revision (13-4C-18): **13-4C-18**

## 5. Human Approved Decisions

실제 canonical record(id=12)의 `category_approvals`에서 `resolution_status == APPROVED`인 것만.

### Visual Design (Canonical Candidate: CLEAN_DARK_FOCUS)

- **Font Family**: APPROVED — `VERDANA_HUMANIST`, `Verdana, Geneva, 'Malgun Gothic', sans-serif`
  (provenance: 13-4C-6)
- **Background**: APPROVED — `#111318` (provenance: 13-4C-8)
- **Color Palette**: APPROVED — 7 role 전체 (provenance: 13-4C-9)
  - DEFAULT `#e6e6e6`, PRIMARY_FOCUS `#60a5fa`, RELATION `#c4b5fd`, SUCCESS `#4ade80`,
    SECONDARY `#9ca3af`, EXCEPTION_CAUTION `#fbbf24` — 전부 13-4C-7 Human Review에서 KEEP
  - **MUTED `#757b87`** — 13-4C-8의 MODERATE 후보가 13-4C-9에서 선택됨. Contrast 4.37:1 (normal AA
    **FAIL**, large AA PASS). Usage guidance: DE-EMPHASIZED TRACE / ALREADY-SEEN INFORMATION —
    NOT PRIMARY BODY TEXT. Human Review usage guidance일 뿐, Renderer가 아직 없어 강제되는 제약은
    아님.
- **Typography Scale**: APPROVED — `LARGE_BEGINNER` 후보 (provenance: 13-4C-11)
  - DOMINANT `72px`, PRIMARY `46px`, SUPPORTING `28px`, CAPTION `20px`, MICRO `15px`
- **Font Weight**: APPROVED — `BALANCED_HIERARCHY` 후보 (provenance: 13-4C-13)
  - DOMINANT `800`(synthetic), PRIMARY `700`(native), SUPPORTING `500`(synthetic),
    CAPTION `400`(native), MICRO `400`(native)
  - VERDANA_HUMANIST native weights는 `[400, 700]`뿐 — 800/500은 승인됐어도 여전히
    browser-synthesized. 승인은 "synthetic이 없다"는 뜻이 아니라 Human이 실제 렌더링을 보고 이
    trade-off를 감수하고 선택했다는 뜻(13-4C-13 provenance).
- **Caption Style**: APPROVED — `BALANCED_INTEGRATED` 후보 (provenance: 13-4C-15)
  - text_color_role `DEFAULT`(승인된 palette role 재사용, 새 HEX 없음), background `box`,
    background_opacity `0.55`, padding `8px 16px`, line_height `1.5`
  - caption_style은 하단 NARRATION_CAPTION zone에만 적용됨(`CAPTION_ROLES`/`_caption_role_for_zone`) —
    LEARNING_TEXT는 별도 스타일 불필요
- **Focus Style**: APPROVED — `COLOR_ONLY` 후보 (provenance: 13-4C-17)
  - color_role `PRIMARY_FOCUS`(resolved `#60a5fa`, 승인된 palette role 재사용, 새 색 없음),
    highlight_box `False`, box_opacity `0.0`, padding `0`, underline `False`
  - focus_style은 승인된 PRIMARY_FOCUS 색만 사용하고 추가 표현(박스/밑줄) 없음. 이미
    `element_state=MUTED`인 이전 focus 대상(BAG/BAT/MAP)에는 애초에 focus_style 자체가 적용되지
    않음(실제 CB07 데이터 근거, 13-4C-16 provenance) — ACTIVE/MUTED semantic 자체는 이 승인으로
    변경되지 않음

### Pronunciation / Assets

이 category는 Visual Approval과 별개 트랙이며 부분적으로만 완료됨 — 6절 참고.

## 6. Pending Human Decisions

실제 canonical record(id=12) 기준, `PENDING_VISUAL_REVIEW`인 category. `MANDATORY`/`OPTIONAL`/
`CONDITIONAL` 분류는 `research/visual_design.py`의 `MANDATORY_VISUAL_CATEGORIES` 등에서 조회했으며,
코드 주석 자체가 **PROVISIONAL**(아직 실제 Renderer 소비자가 없어 최선의 판단일 뿐)이라고 명시함.

| Category | Classification |
|---|---|
| success_style | MANDATORY (PROVISIONAL) — 13-4C-18 Prototype 완료, Human 결정 대기(NONE). 3후보(COLOR_ONLY/BALANCED_SUCCESS/STRONG_SUCCESS) 전부 승인된 SUCCESS palette role만 재사용, typography/weight/family/background/caption_style/focus_style 불변. 실제 Plan 7에서 SUCCESS는 CB06 1곳에서만 쓰임 |
| motion_style | MANDATORY (PROVISIONAL) |
| output_profile_16_9 | MANDATORY (PROVISIONAL) |
| spacing_scale | OPTIONAL (PROVISIONAL) |
| container | OPTIONAL (PROVISIONAL) |
| border | OPTIONAL (PROVISIONAL) |
| radius | OPTIONAL (PROVISIONAL) |
| output_profile_9_16 | CONDITIONAL (9:16 Shorts 파생 시에만 필요) |

**별도 트랙 — Pronunciation Review**: `generated_assets` 중 PENDING 31건, REGENERATE_REQUIRED 11건
(둘 다 실제 사람 검토 필요, `research assets-review` CLI로 처리).

## 7. Current Preview / Review Baselines

**PENDING — NOT HUMAN APPROVED.** typography_scale은 13-4C-11에서 이미 승인되어 5절로 이동함(아래는
코드 `CANDIDATES`에 남아있는 preview 값 — 승인된 canonical 값과 다르니 혼동 금지, 9절 참고).

Typography Scale Preview (`CANDIDATES["CLEAN_DARK_FOCUS"]["roles"]`, 여전히 코드에 남아있는 옛 baseline):
DOMINANT 68px/800, PRIMARY 42px/700, SUPPORTING 26px/500, CAPTION 18px/400, MICRO 14px/400 — 이
값은 실제 승인된 LARGE_BEGINNER(72/46/28/20/15)가 아니다.

font_weight은 13-4C-13에서 이미 승인되어 5절로 이동함(`BALANCED_HIERARCHY` 800/700/500/400/400).
13-4C-12의 나머지 두 후보(LIGHTER_HIERARCHY 700/600/400/400/400, STRONG_BEGINNER
900/800/500/400/400)는 `font_weight_review/`에 review evidence로 그대로 남아있음 — 정상(9절 참고).

caption_style은 13-4C-15에서 이미 승인되어 5절로 이동함(`BALANCED_INTEGRATED`). 13-4C-14의 나머지 두
후보(MINIMAL_TEXT, BEGINNER_EMPHASIS)는 `caption_style_review/`에 review evidence로 그대로
남아있음 — 정상(9절 참고).

focus_style은 13-4C-17에서 이미 승인되어 5절로 이동함(`COLOR_ONLY`). 13-4C-16의 나머지 두 후보
(BALANCED_FOCUS, STRONG_FOCUS)는 `focus_style_review/`에 review evidence로 그대로 남아있음 —
정상(9절 참고).

Success Style Preview 후보 3개(결정론적, Human 미선택, 13-4C-18): COLOR_ONLY(박스 없음, 승인된
SUCCESS 색만), BALANCED_SUCCESS(SUCCESS 색 tint 박스 opacity 0.15), STRONG_SUCCESS(opacity 0.28 +
underline) — 셋 다 `color_role=SUCCESS`(이미 승인된 palette role, 새 색 추가 없음), focus_style
(13-4C-16/17)과 동일한 `_hex_to_rgb(SUCCESS hex)` rgba(...) 오버레이 기법 재사용. 실제 Plan 7에서
SUCCESS는 CB06(MINI_SUCCESS_LAYOUT) 1곳에서만 쓰임(`_color_role_usage_counts` 실측).

현재 아직 Human Review Prototype 자체가 없는 category(예: `motion_style`)는 이 절에 추가할 preview
값이 아직 없음.

## 8. Protected Decisions / Invariants

- Historical Human Review artifact(`font_review/`, `color_background_review/`, `muted_color_review/`,
  `prototypes/`)는 소급 수정하지 않는다.
- Canonical `visual_design_specs` correction은 append-only — 기존 row UPDATE 금지.
- Human Review 없이 PENDING category를 APPROVED로 바꾸지 않는다.
- Renderer Gate(`ready_for_final_renderer_binding`)를 자동으로 True로 만들지 않는다.
- Production/Audio/Layout 데이터(Production Plan, speech_assets, Render Spec, Timeline, Scene
  Layout, WAV, active assets)는 Visual Approval 작업에서 절대 변경하지 않는다.
- Preview value(`CANDIDATES[...]`)와 Human Approved value(canonical `resolved_style`)를 구분한다 —
  이미 승인된 category(`font_family`/`background`/`color_palette`)는 이후 모든 소비자가 canonical
  값을 읽어야 하며, `CANDIDATES`를 다시 읽으면 안 된다(13-4C-9/13-4C-10에서 확립).

## 9. Historical Evidence Policy

과거 Review artifact가 현재 canonical 값과 달라도 정상이다 — 목적이 다르기 때문이다.

- `color_background_review/`(13-4C-7)에는 여전히 MUTED `#555b66`이 보인다 — 당시 preview 값,
  정상.
- `muted_color_review/`(13-4C-8)에는 A `#555b66` / B `#757b87` / C `#8a919d` 3후보가 그대로 남아
  있다 — 정상.
- `CANDIDATES["CLEAN_DARK_FOCUS"]["colors"]["MUTED"]`는 코드에서 여전히 `#555b66`이다(의도적 보존,
  13-4C-9에서 CANDIDATES를 수정하지 않기로 결정 — 10절 참고). 실제 승인된 MUTED는 canonical
  `category_approvals["color_palette"]["resolved_style"]["MUTED"]` = `#757b87`.
- 마찬가지로 `CANDIDATES["CLEAN_DARK_FOCUS"]["roles"]`는 여전히 68/42/26/18/14(옛 baseline)이다 —
  실제 승인된 typography_scale은 canonical `category_approvals["typography_scale"]["resolved_style"]`
  = 72/46/28/20/15(LARGE_BEGINNER). `typography_scale_review/`(13-4C-10)에는 3후보(COMPACT_LEARNING/
  CURRENT_BALANCED/LARGE_BEGINNER) 전부 그대로 남아있다 — 정상.
- `font_weight_review/`(13-4C-12)에는 3후보(LIGHTER_HIERARCHY/BALANCED_HIERARCHY/STRONG_BEGINNER)
  전부 그대로 남아있다 — 정상. 실제 승인된 font_weight는 canonical
  `category_approvals["font_weight"]["resolved_style"]` = 800/700/500/400/400(BALANCED_HIERARCHY).
- `caption_style_review/`(13-4C-14)에는 3후보(MINIMAL_TEXT/BALANCED_INTEGRATED/BEGINNER_EMPHASIS)
  전부 그대로 남아있다 — 정상. 실제 승인된 caption_style은 canonical
  `category_approvals["caption_style"]["resolved_style"]` = BALANCED_INTEGRATED
  (text_color_role=DEFAULT, background=box, opacity=0.55, padding=8px 16px, line_height=1.5).
- `focus_style_review/`(13-4C-16)에는 3후보(COLOR_ONLY/BALANCED_FOCUS/STRONG_FOCUS) 전부 그대로
  남아있다 — 정상. 실제 승인된 focus_style은 canonical
  `category_approvals["focus_style"]["resolved_style"]` = COLOR_ONLY(color_role=PRIMARY_FOCUS,
  highlight_box=False, box_opacity=0.0, padding=0, underline=False).
- `success_style_review/`(13-4C-18)에는 3후보(COLOR_ONLY/BALANCED_SUCCESS/STRONG_SUCCESS) 전부
  그대로 남아있다 — 정상, success_style은 아직 PENDING이라 승인된 canonical 값 자체가 없음.

과거 artifact를 최신 값으로 소급 수정하지 않는다.

## 10. Database and Artifact Snapshot

(2026-08-21 실제 조회값 — snapshot only, 다음 단계 전 재확인 필요)

| Table | Count |
|---|---|
| production_plans | 7 |
| production_blocks | 56 |
| speech_assets | 330 |
| generated_assets | 506 |
| render_specs | 3 |
| render_timelines | 2 |
| scene_layouts | 2 |
| visual_design_specs | 12 |

주요 canonical artifact:
- `assets/generated/plan_7/render/approved_visual_profile.json` — canonical 승인 snapshot
- `assets/generated/plan_7/render/visual_design.json` — 13-4A Visual Design 원본
- `assets/generated/plan_7/render/{prototypes,font_review,color_background_review,
  muted_color_review,typography_scale_review,font_weight_review,caption_style_review,
  focus_style_review,success_style_review}/manifest.json` — 단계별 Review evidence

## 11. Test State

Total tests: **1056** / Passed: **1056** / Failed: **0**
Last verified: 2026-08-21 (`pytest -q` 실제 실행, 13-4C-18 코드/테스트 추가 반영)

**Snapshot only — verify before each stage.** 다음 코드 변경 후에는 이 숫자가 stale됨.

## 12. Known Issues / Semantic Debt

- MUTED `#757b87`이 WCAG AA normal text 기준(4.5:1) 미달(4.37:1) — Human Review에서 semantic
  hierarchy를 우선한 의도된 선택으로 기록됨(13-4C-9 provenance).
- VERDANA_HUMANIST의 native 800 weight 지원 불확실 — 브라우저가 synthetic bold를 쓸 가능성
  있음(`FONT_CANDIDATES["VERDANA_HUMANIST"]["weight_800_behavior"]`).
- `background` category의 실제 구현 scope가 `page_bg` 단일 값으로 제한됨(gradient/texture/media
  background 없음, 13-4C-7에서 확인).
- Renderer(실제 픽셀/MP4 생성 엔진, Stage 14+)가 아직 구현되지 않음.
- `output_profile_16_9`/`output_profile_9_16` 등 다수 output profile category가 아직 미승인.
- 리포트 파일명이 `datetime.utcnow().date()` 기준이라 로컬 날짜(KST)보다 하루 이를 수 있음(기존
  전역 관례, 이번 문서 작업에서 별도로 고치지 않음).
- Pronunciation Review 31건 PENDING + 11건 REGENERATE_REQUIRED — Visual Approval과 별개로 남아있는
  실제 미해결 항목.
- Typography Scale overflow/clipping을 실제 브라우저에서 검증할 수단이 이 코드베이스에 없음(정적
  HTML 구조 검증까지만 가능, 13-4C-10에서 확인).

## 13. Resolved Pitfalls / Do Not Repeat

1. **스펙이 "Human Review가 있었다"고 주장해도 실제 대화/DB persistence를 먼저 확인한다.**
   13-4C-1/4/5/6/8/9/11/13에서 반복적으로 스펙이 존재하지 않는 Human Review 대화를 주장했음(13-4C-13은
   심지어 "이번엔 가짜 주장이 아니다"라고까지 적었지만 역시 근거 없었음) — 매번 AskUserQuestion으로
   확인 후 진행.
2. SOFT_LIGHT_EDUCATION과 CLEAN_DARK_FOCUS의 provenance(특히 PRIMARY px 값)를 섞지 않는다 —
   SOFT_LIGHT_EDUCATION의 PRIMARY는 40px, CLEAN_DARK_FOCUS는 42px로 서로 다른 후보의 값이다.
3. Preview exact token을 Human Approved token으로 자동 승격하지 않는다 — 후보 방향 선택과 exact
   HEX/px 승인은 별개 행위(13-4C-2에서 확립).
4. Historical prototype을 현재 canonical 값으로 소급 수정하지 않는다(9절).
5. Candidate selection(어느 방향을 쓸지)과 full profile approval(모든 category 승인)을 구분한다.
6. 이미 승인된 category는 이후 모든 소비자가 `CANDIDATES`가 아니라 canonical `resolved_style`을
   읽어야 한다(8절 마지막 항목) — 안 그러면 폐기된 preview 값이 되살아난다.

## 14. Current Gate

- Full Approved Visual Profile: **NO**
- Ready for Final Renderer Binding: **NO**
- Ready for Stage 13-5: **NO**

이유: mandatory visual category 9개 중 3개(success_style, motion_style,
output_profile_16_9)가 아직 Human Review 대상.

## 15. Next Step

**NEXT**: 사람이 `success_style_review/index.html`을 보고 3후보(COLOR_ONLY/BALANCED_SUCCESS/
STRONG_SUCCESS) 중 실제로 선택 — 아직 결정 없음(HUMAN DECISION: NONE).

**AFTER THAT**: 그 결정을 별도 Human Approval 단계에서 append-only로 canonical에 기록. 그 다음은
남은 mandatory category(`motion_style` 등)에 대한 Human Review Prototype 준비.

## 16. Do Not Start Yet

- Final Renderer Binding
- Stage 13-5
- Renderer 구현 (실제 픽셀/MP4 생성 엔진)
- MP4 generation

## 17. Resume Instructions

1. 이 문서(PROJECT_STATE.md)를 읽는다.
2. 이 문서를 Source of Truth로 믿지 않는다.
3. `select_canonical_visual_approval(db_path, 7)`로 latest canonical DB state를 조회한다.
4. `approved_visual_profile.json`과 비교한다.
5. 현재 stage(13-4C-10 이후라면 다음 단계) artifact/manifest를 확인한다.
6. 전체 `pytest -q` 또는 필요한 entry gate를 실행한다.
7. 이 문서와 실제 상태가 다르면 실제 상태를 우선한다.
8. 차이를 이 문서에 반영한다(9~12절).
9. 그 다음 15절 Next Step을 수행한다.

## 18. Update Policy

다음 경우 이 문서를 갱신한다:
- Human Approval persistence 완료 (category가 새로 APPROVED됨)
- major pipeline stage 완료
- canonical record 변경
- Renderer Gate 변경
- 새로운 unresolved critical issue 발견
- 다음 작업 stage 변경

다음 경우는 갱신 불필요(단, Current Stage/Next Step 자체가 바뀌면 갱신):
- 단순 Prototype 생성
- 테스트 몇 개 증가
- 사소한 내부 refactor
