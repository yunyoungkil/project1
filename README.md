# 한국 영어교육 YouTube 시장 리서치 자동화

채널 "이해하면 쉬운 영어"를 위해 한국 영어교육 YouTube 시장을 자동 조사하여, 작은/중간 채널의
비정상적 성과 영상(outlier)을 탐지하고 내 채널 성과와 결합해 매주 콘텐츠 제작 후보 TOP3를
추천하는 시스템입니다.

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

```bash
python -m research.cli auth                       # 1회 OAuth 동의 (로컬 브라우저 필요)
python -m research.cli keywords list               # keyword pool 조회
python -m research.cli keywords add --category reading --query "영어 발음 규칙"
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
- `my_channel_fit_score` = 내 채널의 해당 카테고리 평균 retention/CTR 대 채널 전체 평균 비율.
  내 채널 데이터가 없으면 중립값 50 + `fit_data_available=false`
- `content_opportunity_score = market_demand_score × (my_channel_fit_score / 100)`

모든 가중치/캡/임계값은 `config/research_config.yaml`에서 조정 가능합니다.

## Quota 절약

- `search.list`(100 unit)는 카테고리 검색에만 사용, 동일 검색어는 `search_cache`로 7일(config) 내
  재호출 방지
- 채널 baseline은 `search.list` 대신 `channels.list`(1) + `playlistItems.list`(1)로 채널당 2 unit만
  사용 (search 대비 50배 절약)
- `videos.list`/`channels.list`는 최대 50개 id를 배치로 조회
- 모든 호출은 `api_call_log` 테이블에 기록되어 실행당 실제 quota 사용량을 추적 가능

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

## 테스트

```bash
pytest tests/
```

핵심 계산 로직(median/mean baseline, outlier_ratio, subscriber_ratio, views_per_day,
opportunity_score, content_type 분류, 결측치/0-division 처리)에 대한 mock 기반 unit test 36개가
포함되어 있으며 실제 API를 호출하지 않습니다.

## 알려진 한계

- `problem_category`는 카테고리의 대표 고민(`problems[0]`)으로 기록됩니다. `data/keyword_pool.yaml`의
  `problems`와 `search_queries`가 1:1로 매핑되어 있지 않기 때문에, 영상별로 더 구체적인 고민을
  구분하려면 (예: 의미 기반 매칭) 추가 작업이 필요합니다.
- Gemini 호출이 실패(키에 Generative Language API 미활성 등)하면 제목 패턴 분석은 rule-based
  플래그(질문형/부정형/이유형/결과형/숫자형/공포회피형)만 사용하고, TOP3 추천 문구는 템플릿으로
  대체됩니다.
- `my_channel_fit_score`는 내 영상 제목과 keyword pool 용어의 단어 매칭으로 카테고리를 추정합니다
  (임베딩 기반 의미 매칭이 아님).
- YouTube 공식 API는 Shorts 여부를 직접 제공하지 않아 duration 기반 추정에 의존합니다.
