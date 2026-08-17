"""Generates the weekly markdown report: TOP20 outliers, recurring viewer problems, strong title
patterns, market x my-channel intersection, and a TOP3 next-content recommendation."""
from __future__ import annotations

import json
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from research.content_pattern_analyzer import analyze_video
from research.db import connect
from research.gemini_client import GeminiClient
from research.keyword_pool import load_pool

_TOP3_PROMPT_TEMPLATE = """너는 한국 YouTube 채널 "{channel_name}"의 콘텐츠 기획자다.

채널 정보:
- 핵심 시청자: {audience}
- 철학: {philosophy}
- 콘텐츠 영역: {focus_areas}

다음은 시장에서 검증된 시청자 고민과 근거다:
- 문제 카테고리: {category}
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


def _fallback_top3_content(problem_phrase: str) -> dict:
    return {
        "titles": [
            f"{problem_phrase}, 원리로 이해하면 쉬워집니다",
            f"{problem_phrase} - 진짜 이유부터 짚어드립니다",
            f"{problem_phrase}, 처음부터 다시 정리해드립니다",
        ],
        "thumbnail_phrases": ["이제 이해가 됩니다", "원리를 알면 쉬워요"],
        "shorts_ideas": [f"{problem_phrase}, 60초 핵심 요약"],
    }


def build_weekly_report(
    db_path: Path,
    reports_dir: Path,
    gemini: GeminiClient | None,
    channel_cfg: dict,
    keyword_pool_path: Path,
    *,
    top_n: int = 20,
    top3_n: int = 3,
    max_output_tokens: int = 1024,
) -> Path:
    end_date = date.today()
    start_date = end_date - timedelta(days=7)

    pool = load_pool(keyword_pool_path)
    # category slug ("reading") -> natural viewer-problem phrase ("영어 왕초보 어디서부터
    # 시작해야 하나") for display; falls back to the slug itself if a category has no problems.
    category_labels = {
        category: (body.get("problems") or [category])[0] for category, body in pool.items()
    }
    # category slug -> the *set* of all its problem phrases. Each video's problem_category is now
    # the single best-matching problem within its category (see youtube_search.best_matching_problem),
    # not always the category's first/"primary" problem -- so matching a topic back to its videos
    # has to check membership in the whole set, not equality against one label.
    category_problem_sets = {
        category: set(body.get("problems") or [category]) for category, body in pool.items()
    }

    with connect(db_path) as conn:
        top_rows = [
            dict(r)
            for r in conn.execute(
                """
                SELECT v.title, v.video_id, v.channel_id, c.title AS channel_title,
                       v.published_at, v.view_count, c.subscriber_count,
                       os.channel_median_views, os.subscriber_ratio, os.outlier_ratio,
                       os.views_per_day, os.opportunity_score, os.outlier_grade,
                       v.matched_keyword, v.problem_category
                FROM outlier_scores os
                JOIN videos v ON v.video_id = os.video_id
                LEFT JOIN channels c ON c.channel_id = v.channel_id
                WHERE os.outlier_grade IS NOT NULL AND os.outlier_grade != 'normal'
                ORDER BY os.opportunity_score DESC
                LIMIT ?
                """,
                (top_n,),
            ).fetchall()
        ]
        topic_rows = [
            dict(r)
            for r in conn.execute(
                """
                SELECT * FROM topic_opportunities
                WHERE id IN (SELECT MAX(id) FROM topic_opportunities GROUP BY problem_category)
                ORDER BY content_opportunity_score DESC
                """
            ).fetchall()
        ]

    problem_counter = Counter(r["problem_category"] for r in top_rows if r.get("problem_category"))

    patterns = []
    for r in top_rows[:10]:
        p = analyze_video(r["video_id"], r["title"], gemini, max_output_tokens=max_output_tokens)
        patterns.append(p)
    pattern_names = Counter(p.title_pattern for p in patterns if p.title_pattern)

    lines: list[str] = []
    lines.append("# Weekly YouTube Market Research")
    lines.append("")
    lines.append(f"기간: {start_date.isoformat()} ~ {end_date.isoformat()}")
    lines.append("")
    lines.append("## 1. 이번 주 시장 Outlier TOP {}".format(min(10, len(top_rows))))
    lines.append("")
    for i, (r, p) in enumerate(zip(top_rows[:10], patterns), start=1):
        lines.append(f"{i}. {r['title']}")
        lines.append(f"   - Channel: {r.get('channel_title') or r['channel_id']}")
        lines.append(f"   - Views: {r.get('view_count')}")
        lines.append(f"   - Channel baseline (median): {_fmt(r.get('channel_median_views'))}")
        lines.append(f"   - Outlier: {_fmt(r.get('outlier_ratio'))}X ({r.get('outlier_grade')})")
        lines.append(f"   - Opportunity: {_fmt(r.get('opportunity_score'))}/100")
        lines.append(f"   - Viewer problem: {r.get('problem_category') or '-'}")
        lines.append(f"   - Title pattern: {p.title_pattern or '(rule-based flags only)'}")
        if p.emotion:
            lines.append(f"   - Emotion: {p.emotion}")
        lines.append(f"   - Video: https://www.youtube.com/watch?v={r['video_id']}")
        lines.append("")

    lines.append("## 2. 반복적으로 나타나는 시청자 고민")
    lines.append("")
    for problem, count in problem_counter.most_common(10):
        lines.append(f"- {problem} ({count}건)")
    if not problem_counter:
        lines.append("- (데이터 부족)")
    lines.append("")

    lines.append("## 3. 이번 주 강한 제목 패턴")
    lines.append("")
    for pattern_name, count in pattern_names.most_common(10):
        lines.append(f"- {pattern_name} ({count}건)")
    if not pattern_names:
        lines.append("- (LLM 분석 없이 rule-based 플래그만 사용됨)")
    lines.append("")

    lines.append("## 4. 내 채널과의 교집합")
    lines.append("")
    for t in topic_rows:
        fit_note = "" if t["fit_data_available"] else " (내 채널 데이터 부족 - 중립값 사용)"
        phrase = category_labels.get(t["problem_category"], t["problem_category"])
        lines.append(
            f"- {phrase} [{t['problem_category']}]: 시장수요 {_fmt(t['market_demand_score'])}, "
            f"내채널적합도 {_fmt(t['my_channel_fit_score'])}{fit_note}, "
            f"종합 {_fmt(t['content_opportunity_score'])}"
        )
    if not topic_rows:
        lines.append("- (아직 topic score가 계산되지 않았습니다. `research patterns` 실행 필요)")
    lines.append("")

    lines.append("## 5. 다음 콘텐츠 추천 TOP{}".format(top3_n))
    lines.append("")
    for i, t in enumerate(topic_rows[:top3_n], start=1):
        evidence = json.loads(t["evidence_json"]) if t.get("evidence_json") else {}
        problem_phrase = category_labels.get(t["problem_category"], t["problem_category"])
        problem_set = category_problem_sets.get(t["problem_category"], {problem_phrase})
        matched_rows = [r for r in top_rows if r.get("problem_category") in problem_set]
        sample_titles = [r["title"] for r in matched_rows][:3]
        representative_outlier_ratios = [r["outlier_ratio"] for r in matched_rows if r.get("outlier_ratio") is not None]
        representative_outlier_ratio = max(representative_outlier_ratios) if representative_outlier_ratios else None

        content = None
        if gemini and gemini.available:
            prompt = _TOP3_PROMPT_TEMPLATE.format(
                channel_name=channel_cfg.get("name", ""),
                audience=channel_cfg.get("audience", ""),
                philosophy=channel_cfg.get("philosophy", ""),
                focus_areas=", ".join(channel_cfg.get("focus_areas", [])),
                category=problem_phrase,
                outlier_count=evidence.get("outlier_video_count", 0),
                avg_score=sum(evidence.get("top_opportunity_scores", [0])) / max(1, len(evidence.get("top_opportunity_scores", [0]))),
                sample_titles=", ".join(sample_titles) or "(없음)",
            )
            content = gemini.generate_json(prompt, max_output_tokens=max_output_tokens)
        if not content:
            content = _fallback_top3_content(problem_phrase)

        lines.append(f"### #{i}")
        lines.append(f"주제: {problem_phrase}")
        lines.append("")
        ratio_str = f"{_fmt(representative_outlier_ratio)}X" if representative_outlier_ratio is not None else "-"
        lines.append(
            f"시장 근거: outlier 영상 {evidence.get('outlier_video_count', 0)}개, "
            f"대표 Outlier Ratio {ratio_str}, "
            f"종합 opportunity {_fmt(t['content_opportunity_score'])}"
        )
        lines.append(f"내 채널 근거: fit score {_fmt(t['my_channel_fit_score'])}"
                      + ("" if t["fit_data_available"] else " (데이터 부족, 중립값)"))
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

    lines.append("## 6. 이번 주 최우선 제작 추천")
    lines.append("")
    if topic_rows:
        top = topic_rows[0]
        top_phrase = category_labels.get(top["problem_category"], top["problem_category"])
        lines.append(f"Long-form: {top_phrase} 관련 콘텐츠")
        lines.append(f"이유: content_opportunity_score {_fmt(top['content_opportunity_score'])}로 최고 순위")
    else:
        lines.append("(topic score 없음 - `research patterns` 먼저 실행)")
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


def _fmt(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)
