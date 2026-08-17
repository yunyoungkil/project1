"""Generates the weekly markdown report: investigation status, this-week vs evergreen outliers,
independent per-category breakdowns, deduped viewer-problem frequency, fixed-archetype title
patterns, market opportunity (explicit about insufficient data instead of a fake zero), and a
TOP5 next-content recommendation with its evidence front and center."""
from __future__ import annotations

import json
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from research.content_pattern_analyzer import ARCHETYPES, analyze_video
from research.db import connect
from research.gemini_client import GeminiClient
from research.keyword_pool import load_pool, problem_labels_for_category

_TOP_RECOMMENDATION_PROMPT = """너는 한국 YouTube 채널 "{channel_name}"의 콘텐츠 기획자다.

채널 정보:
- 핵심 시청자: {audience}
- 철학: {philosophy}
- 콘텐츠 영역: {focus_areas}

다음은 시장에서 검증된 시청자 고민과 근거다:
- 시청자 고민: {viewer_problem}
- 시장 근거: 관련 outlier 영상 {outlier_count}개, 평균 opportunity_score {avg_score:.0f}/100
- 참고 영상 제목들: {sample_titles}

이 주제로 우리 채널에 맞는 새 콘텐츠를 기획하라. 경쟁 영상 제목을 복제하지 말고 새로 작성하라.
아래 JSON 형식으로만 답하라:

{{
  "titles": ["롱폼 제목 후보 1", "롱폼 제목 후보 2", "롱폼 제목 후보 3"],
  "thumbnail_phrases": ["썸네일 문구 1", "썸네일 문구 2"],
  "shorts_ideas": ["Shorts 아이디어 1"]
}}
"""


def _fallback_recommendation_content(viewer_problem: str) -> dict:
    return {
        "titles": [
            f"{viewer_problem}, 원리로 이해하면 쉬워집니다",
            f"{viewer_problem} - 진짜 이유부터 짚어드립니다",
            f"{viewer_problem}, 처음부터 다시 정리해드립니다",
        ],
        "thumbnail_phrases": ["이제 이해가 됩니다", "원리를 알면 쉬워요"],
        "shorts_ideas": [f"{viewer_problem}, 60초 핵심 요약"],
    }


def _fmt(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)


_OUTLIER_ROW_COLUMNS = """
    v.title, v.video_id, v.channel_id, c.title AS channel_title, v.published_at, v.view_count,
    c.subscriber_count, os.channel_median_views, os.subscriber_ratio, os.outlier_ratio,
    os.views_per_day, os.opportunity_score, os.outlier_grade, v.matched_keyword,
    v.problem_category, v.first_seen_at
"""


def _fetch_top_rows(db_path: Path, limit: int, since: str | None = None, until: str | None = None) -> list[dict]:
    query = f"""
        SELECT {_OUTLIER_ROW_COLUMNS}
        FROM outlier_scores os
        JOIN videos v ON v.video_id = os.video_id
        LEFT JOIN channels c ON c.channel_id = v.channel_id
        WHERE os.outlier_grade IS NOT NULL AND os.outlier_grade != 'normal'
    """
    params: list = []
    if since is not None and until is not None:
        query += " AND date(v.first_seen_at) >= ? AND date(v.first_seen_at) <= ?"
        params.extend([since, until])
    query += " ORDER BY os.opportunity_score DESC LIMIT ?"
    params.append(limit)
    with connect(db_path) as conn:
        return [dict(r) for r in conn.execute(query, params).fetchall()]


def problem_frequency(db_path: Path) -> Counter:
    """Counts each (video, problem) pair once, so a video matched by several search queries under
    the same problem doesn't inflate that problem's frequency."""
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT DISTINCT video_id, problem_label FROM video_keyword_matches WHERE problem_label IS NOT NULL"
        ).fetchall()
    return Counter(r["problem_label"] for r in rows)


def _fetch_category_top_rows(db_path: Path, category: str, limit: int) -> list[dict]:
    query = f"""
        SELECT DISTINCT {_OUTLIER_ROW_COLUMNS}
        FROM outlier_scores os
        JOIN videos v ON v.video_id = os.video_id
        JOIN video_keyword_matches vkm ON vkm.video_id = v.video_id AND vkm.category = ?
        LEFT JOIN channels c ON c.channel_id = v.channel_id
        WHERE os.outlier_grade IS NOT NULL AND os.outlier_grade != 'normal'
        ORDER BY os.opportunity_score DESC
        LIMIT ?
    """
    with connect(db_path) as conn:
        return [dict(r) for r in conn.execute(query, (category, limit)).fetchall()]


def _write_outlier_block(lines: list[str], rows: list[dict], patterns: dict[str, "object"] | None = None) -> None:
    for i, r in enumerate(rows, start=1):
        lines.append(f"{i}. {r['title']}")
        lines.append(f"   - Channel: {r.get('channel_title') or r['channel_id']}")
        lines.append(f"   - Views: {r.get('view_count')}")
        lines.append(f"   - Channel baseline (median): {_fmt(r.get('channel_median_views'))}")
        lines.append(f"   - Outlier: {_fmt(r.get('outlier_ratio'))}X ({r.get('outlier_grade')})")
        lines.append(f"   - Opportunity: {_fmt(r.get('opportunity_score'))}/100")
        lines.append(f"   - Viewer problem: {r.get('problem_category') or '-'}")
        lines.append(f"   - Matched search query: {r.get('matched_keyword') or '-'}")
        if patterns and r["video_id"] in patterns:
            p = patterns[r["video_id"]]
            lines.append(f"   - Title archetype: {ARCHETYPES.get(p.primary_archetype, p.primary_archetype)}")
        lines.append(f"   - Video: https://www.youtube.com/watch?v={r['video_id']}")
        lines.append("")


def build_weekly_report(
    db_path: Path,
    reports_dir: Path,
    gemini: GeminiClient | None,
    channel_cfg: dict,
    keyword_pool_path: Path,
    *,
    top_n: int = 10,
    category_top_n: int = 5,
    recommend_n: int = 5,
    pattern_sample_size: int = 20,
    max_output_tokens: int = 1024,
) -> Path:
    end_date = date.today()
    start_date = end_date - timedelta(days=7)
    pool = load_pool(keyword_pool_path)
    categories = list(pool.keys())

    with connect(db_path) as conn:
        topic_rows = [
            dict(r)
            for r in conn.execute(
                """
                SELECT * FROM topic_opportunities
                WHERE id IN (SELECT MAX(id) FROM topic_opportunities GROUP BY problem_category)
                """
            ).fetchall()
        ]
    topic_by_category = {t["problem_category"]: t for t in topic_rows}

    this_week_rows = _fetch_top_rows(db_path, top_n, since=start_date.isoformat(), until=end_date.isoformat())
    evergreen_rows = _fetch_top_rows(db_path, top_n)

    # Title pattern archetypes are computed once over the evergreen set (the broadest, most
    # stable sample) and reused for both the per-video display and the frequency aggregation.
    pattern_source_rows = evergreen_rows[:pattern_sample_size] or this_week_rows[:pattern_sample_size]
    patterns = {}
    for r in pattern_source_rows:
        patterns[r["video_id"]] = analyze_video(r["video_id"], r["title"], gemini, max_output_tokens=max_output_tokens)
    archetype_counter = Counter(p.primary_archetype for p in patterns.values() if p.primary_archetype)
    archetype_examples: dict[str, str] = {}
    for r in pattern_source_rows:
        p = patterns.get(r["video_id"])
        if p and p.primary_archetype and p.primary_archetype not in archetype_examples:
            archetype_examples[p.primary_archetype] = r["title"]

    problem_counter = problem_frequency(db_path)

    lines: list[str] = []
    lines.append("# Weekly YouTube Market Research")
    lines.append("")
    lines.append(f"기간: {start_date.isoformat()} ~ {end_date.isoformat()}")
    lines.append("")

    lines.append("## 1. 조사 상태")
    lines.append("")
    for category in categories:
        t = topic_by_category.get(category)
        query_count = sum(len((p.get("search_queries") or [])) for p in (pool.get(category) or {}).get("problems") or [])
        if t:
            lines.append(
                f"- {category}: query {query_count}개, 후보 {t['candidate_video_count']}개, "
                f"outlier {t['outlier_video_count']}개, evidence {t['market_evidence_status']}, "
                f"confidence {t['evidence_confidence']}"
            )
        else:
            lines.append(f"- {category}: query {query_count}개, (아직 조사 안 됨)")
    lines.append("")

    lines.append(f"## 2. 이번 주 발견 Outlier TOP{min(top_n, len(this_week_rows))}")
    lines.append("")
    if this_week_rows:
        _write_outlier_block(lines, this_week_rows, patterns)
    else:
        lines.append("- 이번 주 새로 발견된 영상이 없습니다.")
        lines.append("")

    lines.append(f"## 3. Evergreen Benchmark TOP{min(top_n, len(evergreen_rows))}")
    lines.append("")
    lines.append("(발견 시점과 무관하게 DB 전체에서 여전히 참고 가치가 높은 outlier)")
    lines.append("")
    _write_outlier_block(lines, evergreen_rows, patterns)

    lines.append("## 4. 카테고리별 Outlier")
    lines.append("")
    for category in categories:
        cat_rows = _fetch_category_top_rows(db_path, category, category_top_n)
        if cat_rows:
            lines.append(f"### {category} TOP{min(category_top_n, len(cat_rows))}")
            lines.append("")
            _write_outlier_block(lines, cat_rows)
        else:
            lines.append(f"### {category}")
            lines.append("")
            lines.append("- (해당 카테고리 outlier 없음)")
            lines.append("")

    lines.append("## 5. 반복적으로 나타나는 Viewer Problems")
    lines.append("")
    for problem, count in problem_counter.most_common(10):
        lines.append(f"- {problem} — {count}개 영상")
    if not problem_counter:
        lines.append("- (데이터 부족)")
    lines.append("")

    lines.append("## 6. 강한 제목 Archetype")
    lines.append("")
    for archetype, count in archetype_counter.most_common(10):
        label = ARCHETYPES.get(archetype, archetype)
        example = archetype_examples.get(archetype, "")
        lines.append(f"- {archetype} ({label}): {count}건 — 예: {example}")
    if not archetype_counter:
        lines.append("- (데이터 부족)")
    lines.append("")

    lines.append("## 7. 시장 기회")
    lines.append("")
    for category in categories:
        t = topic_by_category.get(category)
        if not t:
            lines.append(f"- {category}: 아직 조사되지 않음")
            continue
        if t["market_evidence_status"] == "insufficient_data":
            lines.append(
                f"- {category}: 데이터 부족 (후보 {t['candidate_video_count']}개, "
                f"confidence {t['evidence_confidence']}), 내채널적합도 {_fmt(t['my_channel_fit_score'])}"
                + ("" if t["fit_data_available"] else " (중립값)")
            )
        else:
            lines.append(
                f"- {category}: 시장수요 {_fmt(t['market_demand_score'])} (confidence {t['evidence_confidence']}), "
                f"내채널적합도 {_fmt(t['my_channel_fit_score'])}"
                + ("" if t["fit_data_available"] else " (중립값)")
                + f", 종합 {_fmt(t['content_opportunity_score'])}"
            )
    lines.append("")

    lines.append(f"## 8. 다음 콘텐츠 후보 TOP{recommend_n}")
    lines.append("")
    sufficient_topics = [
        t for t in topic_rows
        if t["market_evidence_status"] == "sufficient" and t["content_opportunity_score"] is not None
    ]
    sufficient_topics.sort(key=lambda t: t["content_opportunity_score"], reverse=True)

    for i, t in enumerate(sufficient_topics[:recommend_n], start=1):
        category = t["problem_category"]
        evidence = json.loads(t["evidence_json"]) if t.get("evidence_json") else {}
        cat_rows = _fetch_category_top_rows(db_path, category, category_top_n)

        with connect(db_path) as conn:
            problem_freq_rows = conn.execute(
                """
                SELECT problem_label, COUNT(DISTINCT video_id) AS n
                FROM video_keyword_matches vkm
                WHERE category = ? AND video_id IN (SELECT video_id FROM outlier_scores WHERE outlier_grade IS NOT NULL AND outlier_grade != 'normal')
                GROUP BY problem_label ORDER BY n DESC LIMIT 1
                """,
                (category,),
            ).fetchall()
        if problem_freq_rows:
            viewer_problem = problem_freq_rows[0]["problem_label"]
        else:
            labels = problem_labels_for_category(pool, category)
            viewer_problem = labels[0] if labels else category

        representative = cat_rows[0] if cat_rows else None
        cat_archetypes = Counter(
            patterns[r["video_id"]].primary_archetype
            for r in cat_rows
            if r["video_id"] in patterns and patterns[r["video_id"]].primary_archetype
        )
        repeated_archetype = cat_archetypes.most_common(1)[0][0] if cat_archetypes else None

        sample_titles = [r["title"] for r in cat_rows][:3]
        content = None
        if gemini and gemini.available:
            prompt = _TOP_RECOMMENDATION_PROMPT.format(
                channel_name=channel_cfg.get("name", ""),
                audience=channel_cfg.get("audience", ""),
                philosophy=channel_cfg.get("philosophy", ""),
                focus_areas=", ".join(channel_cfg.get("focus_areas", [])),
                viewer_problem=viewer_problem,
                outlier_count=evidence.get("outlier_video_count", 0),
                avg_score=sum(evidence.get("top_opportunity_scores", [0])) / max(1, len(evidence.get("top_opportunity_scores", [0]))),
                sample_titles=", ".join(sample_titles) or "(없음)",
            )
            content = gemini.generate_json(prompt, max_output_tokens=max_output_tokens)
        if not content:
            content = _fallback_recommendation_content(viewer_problem)

        lines.append(f"### #{i}")
        lines.append(f"Viewer problem: {viewer_problem}")
        lines.append(f"Category: {category}")
        lines.append("")
        lines.append(
            f"시장 근거: outlier 영상 {evidence.get('outlier_video_count', 0)}개 "
            f"(후보 {evidence.get('candidate_video_count', 0)}개 중), confidence {t['evidence_confidence']}"
        )
        if representative:
            lines.append(
                f"대표 outlier 영상: {representative['title']} "
                f"({_fmt(representative.get('outlier_ratio'))}X, https://www.youtube.com/watch?v={representative['video_id']})"
            )
        if repeated_archetype:
            lines.append(f"반복되는 title archetype: {repeated_archetype} ({ARCHETYPES.get(repeated_archetype, '')})")
        lines.append(
            f"내 채널 근거: fit score {_fmt(t['my_channel_fit_score'])}"
            + ("" if t["fit_data_available"] else " (데이터 부족, 중립값)")
        )
        lines.append(f"Content Opportunity Score: {_fmt(t['content_opportunity_score'])}")
        lines.append("")
        lines.append("추천 제목:")
        for j, title in enumerate(content.get("titles", []), start=1):
            lines.append(f"{j}. {title}")
        lines.append("")
        lines.append("썸네일:")
        for j, phrase in enumerate(content.get("thumbnail_phrases", []), start=1):
            lines.append(f"{j}. {phrase}")
        lines.append("")
        lines.append("Shorts:")
        for j, idea in enumerate(content.get("shorts_ideas", []), start=1):
            lines.append(f"{j}. {idea}")
        lines.append("")

    if not sufficient_topics:
        lines.append("- 아직 시장 근거가 충분한(evidence sufficient) 카테고리가 없습니다. 검색을 더 진행하세요.")
        lines.append("")

    lines.append("## 9. 이번 주 제작 우선순위")
    lines.append("")
    if sufficient_topics:
        for i, t in enumerate(sufficient_topics[:3], start=1):
            lines.append(
                f"{i}순위: {t['problem_category']} "
                f"(content_opportunity_score {_fmt(t['content_opportunity_score'])}, "
                f"confidence {t['evidence_confidence']})"
            )
    else:
        lines.append("(시장 근거가 충분한 카테고리가 아직 없어 우선순위를 정할 수 없습니다)")
    lines.append("")

    reports_dir.mkdir(parents=True, exist_ok=True)
    out_path = reports_dir / f"weekly_{end_date.isoformat()}.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")

    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO weekly_reports (period_start, period_end, file_path) VALUES (?, ?, ?)",
            (start_date.isoformat(), end_date.isoformat(), str(out_path)),
        )

    return out_path
