# 한국 영어교육 YouTube 콘텐츠 제작 자동화

채널 "이해하면 쉬운 영어"(영어 알파벳-소리 대응이 안 되는 성인 완전 초보자 대상)를 위한
시장 리서치 → 토픽/스크립트/프로덕션 기획 → 실제 음성 에셋 생성 → 렌더링 준비 파이프라인입니다.

1. **시장 리서치**: 한국 영어교육 YouTube 시장을 자동 조사하여 작은/중간 채널의 비정상적 성과
   영상(outlier)을 탐지하고 내 채널 성과와 결합해 매주 콘텐츠 제작 후보 TOP3를 추천
2. **콘텐츠 기획**: 리서치에서 나온 Viewer Problem을 Topic → Title/Thumbnail Package →
   Production Blueprint → Content Script → Video Direction → Production Plan 순서로 구체화
3. **에셋 생성**: Production Plan의 Speech Asset을 실제 Gemini TTS로 음성 파일 생성 + 검증
4. **렌더링 준비**: 검증된 Production Plan을 Renderer-neutral Render Spec → Timeline → Scene
   Layout → Visual Design(색/타이포/폰트) 순서로 컴파일하고 Human Review 승인을 기록 (실제 영상
   렌더링 엔진은 아직 구현되지 않음 — 13단계는 렌더링 "직전"까지)

각 단계는 이전 단계의 DB 데이터를 read-only로 소비하고, 사람이 검토/승인해야 하는 지점은 별도
CLI 명령과 append-only DB row로 명시적으로 분리되어 있습니다 (자동으로 다음 단계까지 승인되는
경우가 없습니다).

> 현재 진행 상태(어느 category가 승인됐는지, 다음 할 일이 무엇인지)는 이 README가 아니라
> [`PROJECT_STATE.md`](PROJECT_STATE.md)에서 확인하세요 — 다음 단계를 시작하기 전에 먼저 읽고,
> 반드시 실제 DB/canonical artifact로 재검증한 뒤 진행하세요.

## 설치

```bash
pip install -r requirements.txt
cp .env.example .env   # 값 채우기 (이미 .env가 있다면 생략)
```

`.env`에 필요한 값:

- `YOUTUBE_API_KEY` — YouTube Data API v3 키 (검색/영상/채널 조회 및 기본 Gemini 키로도 재사용)
- `YOUTUBE_CLIENT_ID` / `YOUTUBE_CLIENT_SECRET` — YouTube Analytics API OAuth 클라이언트 (`research auth`용)
- `GEMINI_API_KEY` (선택) — 별도 Gemini 키. 미설정 시 `YOUTUBE_API_KEY`를 재사용합니다. 이 키에
  [Generative Language API](https://console.cloud.google.com/apis/library/generativelanguage.googleapis.com)가
  활성화돼 있어야 Gemini 호출이 성공합니다. 비활성 상태여도 시스템은 죽지 않고 rule-based 분석으로
  자동 전환됩니다.

## CLI 명령

### 1) 시장 리서치

```bash
python -m research.cli auth                       # 1회 OAuth 동의 (로컬 브라우저 필요)
python -m research.cli keywords list               # keyword pool 조회
python -m research.cli keywords add --category reading --problem-id word_stress \
  --problem-label "영어 강세 위치를 어떻게 아는가" --query "영어 강세"
python -m research.cli search --category reading   # 카테고리 검색 + 수집 (캐시 적용)
python -m research.cli analyze                     # baseline + outlier + opportunity score 계산
python -m research.cli top --limit 20               # TOP N 출력
python -m research.cli patterns                     # 제목 패턴 분석 + 내 채널 결합 + topic score
python -m research.cli report weekly                 # 주간 리포트 생성 (reports/weekly_YYYY-MM-DD.md)
python -m research.cli run-scheduled                 # config/research_config.yaml의 요일별 스케줄 실행
python -m research.cli run-all                       # 전체 카테고리 파이프라인 (quota 소모 큼, 주의)
```

`--query-limit N` 옵션으로 `search`/`run-all` 실행 시 카테고리당 검색어 수를 제한할 수 있습니다
(테스트/quota 절약용).

### 2) 콘텐츠 기획 (신규 API 호출 없음 — DB 데이터로만 계산/Gemini 텍스트 생성)

```bash
python -m research.cli topics --top 20              # Viewer Problem -> Topic Candidate 랭킹
python -m research.cli clicks --top 10               # 선택된 Topic의 outlier 영상이 왜 클릭됐는지 분석
python -m research.cli packages --top 10             # Topic -> Title x Thumbnail Package 생성
python -m research.cli blueprint                     # 선택된 Package -> Production Blueprint 생성
python -m research.cli script                        # 승인된 Blueprint -> 포맷-중립 Content Script 생성
python -m research.cli direction                     # Content Script -> 영상 포맷 + 블록별 연출(Video Direction) 결정
python -m research.cli production-plan               # Video Direction -> Production Plan(정확한 speech/visual/pause 순서) 컴파일
```

각 명령은 `--*-id`(예: `--package-id`, `--blueprint-id`, `--script-id`)로 특정 row를 지정하지
않으면 이전 단계에서 "이 단계로 넘길 준비가 됐다"고 표시된 가장 최근 row를 자동으로 사용합니다.

### 3) 에셋 생성 (실제 Gemini TTS API 호출)

```bash
python -m research.cli assets --dry-run              # 실제 호출 없이 생성될 에셋 수/예상 API 호출 수만 확인
python -m research.cli assets --sample                # Sample Matrix 생성 (전략 검증용 소량 실제 TTS 호출)
python -m research.cli assets                         # 승인된 Production Plan의 전체 Speech Asset을 실제 Gemini TTS로 생성 + 검증
python -m research.cli assets-review                  # 사람 발음 검토 대기 목록 조회
python -m research.cli assets-review --set SP007=APPROVED --set-tone SP029::CONTEXTUAL_WORD=REJECTED
```

### 4) 렌더링 준비 (신규 API 호출 없음, 실제 렌더러는 아직 없음)

```bash
python -m research.cli render-spec                    # Production Plan -> Renderer-neutral Render Specification
python -m research.cli render-timeline                 # Render Spec -> 밀리초 단위 결정론적 Timeline
python -m research.cli render-layout                   # Timeline -> Scene/Layout Model(Zone 구조)
python -m research.cli render-visual-design             # Scene Layout -> Visual Design System + 정적 HTML Prototype
python -m research.cli approve-visual-design --candidate CLEAN_DARK_FOCUS   # Prototype에 대한 실제 Human Review Candidate 선택 기록
python -m research.cli correct-visual-approval --candidate CLEAN_DARK_FOCUS --corrects-id 2  # 잘못 기록된 승인을 이력 보존하며 교정
python -m research.cli review-font-family               # Font Family 비교 Prototype 생성 (DB 미기록)
python -m research.cli approve-font-family               # Font Family Human Review 승인 기록 (font_family category만)
python -m research.cli review-color-background           # Color Palette + Background 비교 Prototype 생성 (DB 미기록)
python -m research.cli review-muted-color                 # Background Human Approval 기록 + MUTED 후보 비교 Prototype 생성
python -m research.cli approve-color-palette              # Color Palette Human Review 승인 기록 (7 role 전체)
python -m research.cli review-typography-scale             # Typography Scale 비교 Prototype 생성 (DB 미기록)
python -m research.cli approve-typography-scale             # Typography Scale Human Review 승인 기록 (typography_scale category만)
python -m research.cli review-font-weight                    # Font Weight 비교 Prototype 생성 (DB 미기록)
python -m research.cli approve-font-weight                    # Font Weight Human Review 승인 기록 (font_weight category만)
python -m research.cli review-caption-style                    # Caption Style 비교 Prototype 생성 (DB 미기록)
python -m research.cli approve-caption-style                   # Caption Style Human Review 승인 기록 (caption_style category만)
python -m research.cli review-focus-style                      # Focus Style 비교 Prototype 생성 (DB 미기록)
python -m research.cli approve-focus-style                     # Focus Style Human Review 승인 기록 (focus_style category만)
python -m research.cli review-success-style                    # Success Style 비교 Prototype 생성 (DB 미기록)
python -m research.cli approve-success-style                   # Success Style Human Review 승인 기록 (success_style category만)
```

모든 승인 명령(`approve-*`, `correct-*`)은 append-only입니다 — 기존 row를 수정하지 않고 새 row를
추가하며, 승인 category 하나가 전체 Visual Profile을 자동으로 승인하지 않습니다
(`ready_for_final_renderer_binding`은 필수 category가 모두 APPROVED여야 True).

## 아키텍처

```
research/
  config.py                 .env + config/research_config.yaml 로딩
  db.py                      SQLite 스키마
  youtube_client.py          YouTube Data API v3 래퍼 + quota 로깅
  analytics_client.py        YouTube Analytics API v2 + OAuth
  gemini_client.py           Gemini REST 호출 (실패 시 None -> rule-based 폴백)
  keyword_pool.py            data/keyword_pool.yaml 로드/추가
  youtube_search.py          카테고리별 검색 + 캐시 + dedup
  video_stats.py             video/channel 정규화, content_type 분류
  channel_baseline.py        채널 최근 영상 median/mean baseline
  outlier_detector.py        outlier_ratio/subscriber_ratio/views_per_day/grade (순수 함수)
  opportunity_score.py       영상 단위 opportunity_score (순수 함수)
  analyze_pipeline.py         위 모듈들을 묶어 outlier_scores 테이블에 저장
  content_pattern_analyzer.py 제목 패턴: rule-based + Gemini 보강
  my_channel.py                내 채널 Analytics + market_demand/my_fit/content_opportunity
  weekly_report.py             주간 마크다운 리포트 생성
  progress.py                  터미널 진행 상태 로깅 (분석 로직에 영향 없음, 관찰 전용)

  topic_candidates.py          Viewer Problem -> Topic Candidate (시장 근거 기반, 결정론적 점수)
  click_analysis.py            선택된 Topic의 outlier 영상이 왜 클릭됐는지 (Click Evidence Score)
  content_packages.py          Topic -> Title x Thumbnail Package (Package Score, Topic/Click과 독립)
  production_blueprint.py      Package -> Production Blueprint (Viewer Contract, 섹션 구조, Integrity Check)
  script_writer.py             Blueprint -> 포맷-중립 Content Script (영상 포맷은 아직 결정 안 함)
  video_director.py             Content Script -> Video Direction (포맷 + 블록별 연출 결정)
  production_planner.py         Video Direction -> Production Plan (speech/visual/pause 정확한 순서, TTS 미호출)
  asset_generator.py            Production Plan -> 실제 Gemini TTS 호출 + WAV 생성 + 검증
  tts_client.py                  Gemini TTS REST 래퍼 (실패 시 None, google-genai SDK 미사용)

  render_spec.py                13-1: Production Plan -> Renderer-neutral Render Specification
  timeline_compiler.py          13-2: Render Spec -> 밀리초 단위 결정론적 Timeline
  scene_layout.py                13-3: Timeline -> Scene/Layout Model (Zone 구조, 픽셀 좌표 아님)
  visual_design.py               13-4: Scene Layout -> Visual Design System + HTML Prototype +
                                  Human Review 승인 기록 (append-only, category별 개별 승인)
  cli.py                       위 전체를 묶는 CLI
```

데이터는 `data/research.db` (SQLite)에 저장됩니다. 스키마는 `research/db.py` 참고.

## 핵심 계산식

- `subscriber_ratio = view_count / subscriber_count` — 구독자 수 hidden/0/None이면 `null`
- `outlier_ratio = view_count / channel_median_views` — 동일 content_type 채널 baseline 대비
- `views_per_day = view_count / max(1, age_days)`
- Outlier 등급: `<2x normal / 2-5x notable / 5-10x strong / 10-20x very_strong / ≥20x exceptional`
  (`config/research_config.yaml`의 `outlier.thresholds`)
- `opportunity_score` (0~100) = `outlier_strength(40%) + views_velocity(20%) + subscriber_ratio(10%)
  + engagement(10%) + relevance(20%)`, 각 구성요소는 `100 * ln(1+x) / ln(1+cap)` 로그 정규화로
  극단값을 완충 (`opportunity_score.py`). 결측 지표는 중립값(기본 50)으로 처리해 0으로 깎이지 않음.
- `market_demand_score` = 카테고리 내 top-N 영상 opportunity_score 평균(70%) + outlier 영상 개수(30%, capped)
- `my_channel_fit_score` = 내 채널의 해당 카테고리 평균 retention(`average_percentage_viewed`) 대 채널
  전체 평균 비율. CTR/impressions는 YouTube Analytics API가 애초에 제공하지 않아(Studio 전용) retention만
  사용합니다. 내 채널 데이터가 없으면 중립값 50 + `fit_data_available=false`
- `content_opportunity_score = market_demand_score × (my_channel_fit_score / 100)`. 카테고리의
  후보 영상 수가 `topic_score.min_candidate_videos`(기본 10) 미만이면 `market_demand_score`/
  `content_opportunity_score`는 **0이 아니라 `null`**이고 `market_evidence_status =
  "insufficient_data"`로 표시됩니다 — "시장 조사가 부족함"과 "시장 수요가 확인상 0임"은 다른
  주장이라서 구분합니다.

모든 가중치/캡/임계값은 `config/research_config.yaml`에서 조정 가능합니다.

## Keyword Pool 구조와 Viewer Problem 매칭

`data/keyword_pool.yaml`은 `category -> problems[] -> {id, label, search_queries[]}` 구조입니다.
검색어 하나는 정확히 하나의 problem에 귀속되므로, 어떤 영상이 어떤 시청자 고민에서 발견됐는지는
추측이 아니라 결정론적 조회입니다 (`research/keyword_pool.py`). `video_keyword_matches` 테이블이
영상-검색어-problem 매치를 전부 보존하므로, 영상 하나가 여러 problem에 걸릴 수 있고
(`videos.problem_category`는 그중 "처음 매치된 것" 하나만 보여주는 하위 호환용 요약 필드입니다),
빈도 집계(`weekly_report.problem_frequency`)는 항상 `DISTINCT video_id, problem_label` 기준이라
같은 영상이 여러 검색어에 걸려도 중복 집계되지 않습니다.

## Quota 절약

- `search.list`(100 unit)는 카테고리 검색에만 사용, 동일 검색어는 `search_cache`로 7일(config) 내
  재호출 방지
- 채널 baseline은 `search.list` 대신 `channels.list`(1) + `playlistItems.list`(1)로 채널당 2 unit만
  사용 (search 대비 50배 절약)
- **baseline 자체도 재사용**: 이미 계산한 채널의 baseline이 `baseline.cache_ttl_hours`(기본 7일) 이내면
  API를 다시 호출하지 않고 저장된 값을 그대로 씁니다. `research analyze`를 반복 실행해도 새 영상이 없는
  채널은 quota를 추가로 쓰지 않습니다.
- `outlier.min_grade_to_store`(기본 `notable`, 2배 미만) 미만인 영상은 `outlier_scores`에 저장하지
  않습니다 — 이미 저장돼 있다가 재계산으로 등급이 떨어진 영상은 삭제됩니다.
- `videos.list`/`channels.list`는 최대 50개 id를 배치로 조회
- 모든 호출은 `api_call_log` 테이블에 기록되어 실행당 **실제** quota 사용량을 추적 가능
- `search`/`analyze` 실행 전에는 캐시를 감안한 **예상 quota**도 미리 출력합니다
  (`[quota] estimated N unit(s) ...`)

## Content type 분류의 한계

- `duration ≤ 60초` → `short` (고신뢰)
- `60초 < duration ≤ 180초` → `unknown` (Shorts 3분 확장 정책으로 판별 불확실, baseline 계산에서 제외됨)
- `duration > 180초` → `longform`

## `research auth` (내 채널 Analytics 연동)

이 명령은 로컬 브라우저에서 Google 계정 동의가 필요합니다. 자동화 환경에서는 실행할 수 없으므로,
**사용자가 로컬 터미널에서 직접 1회 실행**해야 합니다:

```bash
python -m research.cli auth
```

성공하면 `config/youtube_token.json`에 refresh token이 저장됩니다(코드에 하드코딩되지 않음, git에
커밋하지 마세요). 이 파일이 없어도 나머지 기능(시장 조사, outlier 탐지, TOP20)은 정상 동작하며,
내 채널 적합도만 중립값(50)으로 표시됩니다.

## Weekly Report 구조

`reports/weekly_YYYY-MM-DD.md`는 9개 섹션입니다:

1. 조사 상태 (카테고리별 query/후보/outlier 수, evidence status, confidence)
2. 이번 주 발견 Outlier TOP10 — `videos.first_seen_at`(최초 발견 시점)이 이번 리포트 기간
   안인 것만. 오래된 영상이라도 이번 주에 처음 발견됐다면 여기 포함됩니다.
3. Evergreen Benchmark TOP10 — 발견 시점 무관, DB 전체 기준 TOP (2와 다른 근거)
4. 카테고리별 Outlier TOP5 — 카테고리마다 독립적으로 계산되어, 특정 카테고리가 강해도 다른
   카테고리의 결과가 가려지지 않습니다
5. 반복적으로 나타나는 Viewer Problems — unique video × problem 기준 (같은 영상이 여러 검색어에
   걸려도 중복 집계 안 됨)
6. 강한 제목 Archetype — 고정 taxonomy(`content_pattern_analyzer.ARCHETYPES`) 기준 집계
7. 시장 기회 — evidence 부족 카테고리는 "데이터 부족 (후보 N개)"로 표시, 점수 0 아님
8. 다음 콘텐츠 후보 TOP5 — evidence가 `sufficient`인 카테고리만 대상
9. 이번 주 제작 우선순위

## 데이터 스냅샷

`video_metrics_snapshots` 테이블에 영상을 조회할 때마다(검색/baseline 수집 등) view/like/comment
count를 시점 기록으로 남깁니다. 같은 영상을 여러 번 조사하면 조회수 변화 추이를 나중에 재구성할 수
있습니다.

## 매주 자동 실행 (Windows 작업 스케줄러)

`research run-scheduled`는 `config/research_config.yaml`의 `schedule`(월~토 6개 핵심 카테고리를
하나씩, 일요일은 `report`)을 읽어 오늘 할 일을 실행합니다. 이 자체를 매일 자동으로 트리거하려면 Windows 작업
스케줄러에 등록해야 합니다 (아래는 예시 명령이며, 프로젝트 경로/Python 경로는 환경에 맞게 바꿔야
합니다 — 이 명령은 시스템에 영구적인 예약 작업을 만드므로 직접 실행 전에 검토해주세요):

```powershell
schtasks /Create /TN "YouTube Research Daily" /SC DAILY /ST 09:00 ^
  /TR "python -m research.cli run-scheduled" ^
  /RU "%USERNAME%"
```

- 작업 디렉터리는 스케줄러가 기본으로 잡지 않으므로, 위 `/TR`을 배치 파일(예: `run_scheduled.bat`)로
  감싸서 `cd /d C:\Users\yunyo\Downloads\project1` 후 명령을 실행하게 만드는 것을 권장합니다.
- 등록 확인: `schtasks /Query /TN "YouTube Research Daily"`
- 삭제: `schtasks /Delete /TN "YouTube Research Daily" /F`

## 테스트

```bash
pytest tests/
```

실제 API를 호출하지 않는 mock/fake 기반 unit test 835개가 포함되어 있습니다. 리서치 핵심 계산
로직(median/mean baseline, outlier_ratio, subscriber_ratio, views_per_day, opportunity_score,
content_type 분류, 결측치/0-division 처리, min_grade 필터링, keyword pool problem 매칭, "이번 주"
필터, viewer problem 빈도 집계, archetype 고정 taxonomy)뿐 아니라, 콘텐츠 기획 파이프라인 각
단계의 read-only 상류 데이터 보존, 에셋 생성의 실패/재시도 처리, 렌더링 준비 단계의 append-only
Human Review 승인(잘못된 category 자동 승인 금지, 기존 row 불변 등)까지 포함합니다.

## 알려진 한계

- Gemini 호출이 실패(키에 Generative Language API 미활성 등)하면 제목 패턴 분석은 rule-based
  플래그(질문형/부정형/이유형/결과형/숫자형/공포회피형)와 `fallback_archetype()`(플래그 기반 간이
  추정)만 사용하고, TOP5 추천 문구는 템플릿으로 대체됩니다. `emotion`/`beginner_appeal`/
  `secondary_archetype` 필드도 Gemini 없이는 채워지지 않습니다.
- Gemini가 고정 taxonomy 밖의 archetype id를 만들어내면(할루시네이션) 무시하고 rule-based 폴백으로
  대체합니다 — 집계가 깨지지 않도록 하기 위함이며, 이 경우도 여전히 rule-based 추정치일 뿐입니다.
- `my_channel_fit_score`는 내 영상 제목과 keyword pool 용어의 단어 매칭으로 카테고리를 추정합니다
  (임베딩 기반 의미 매칭이 아님).
- `topic_score.min_candidate_videos` 임계값은 통계적 유의성 검정이 아니라 단순 카운트 기준입니다.
  경계값 근처(예: 후보 9개 vs 11개)에서 sufficient/insufficient 판정이 급격히 바뀔 수 있습니다.
- YouTube 공식 API는 Shorts 여부를 직접 제공하지 않아 duration 기반 추정에 의존합니다.
- `research run-scheduled`를 실제로 매일 자동 실행하려면 위 작업 스케줄러 등록을 사용자가 직접
  해야 합니다 (코드가 스스로 등록하지 않음).
- 실제 영상을 픽셀로 그리는 Renderer(14+)는 아직 구현되지 않았습니다. 13단계는 Render Spec/
  Timeline/Scene Layout/Visual Design까지만 컴파일하며, 이 JSON들을 실제로 읽어 MP4를 만드는
  엔진은 별도 단계입니다.
- Visual Profile의 15개 category 중 `font_family`(`VERDANA_HUMANIST`)/`background`(`#111318`)/
  `color_palette`(7 role 전체 확정, `MUTED`는 3개 후보 중 Human Review로 `#757b87` 선택)/
  `typography_scale`(3개 후보 중 Human Review로 `LARGE_BEGINNER` 72/46/28/20/15px 선택)/
  `font_weight`(3개 후보 중 Human Review로 `BALANCED_HIERARCHY` 800/700/500/400/400 선택, DOMINANT·
  SUPPORTING은 Verdana native가 아닌 synthetic weight)/`caption_style`(3개 후보 중 Human Review로
  `BALANCED_INTEGRATED` 선택: text_color_role=DEFAULT, background=box, opacity=0.55,
  padding=8px 16px, line_height=1.5)/`focus_style`(3개 후보 중 Human Review로 `COLOR_ONLY` 선택:
  color_role=PRIMARY_FOCUS(#60a5fa), highlight_box 없음, underline 없음 — 승인된 색만 사용하고 추가
  표현 없음) 7개만 현재 Human Review 승인 완료 상태이며, 나머지 8개는 아직 `PENDING_VISUAL_REVIEW`라
  `ready_for_final_renderer_binding`은 여전히 `False`입니다.
