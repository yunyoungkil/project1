"""Turns Viewer Problems with real market evidence into comparable Topic Candidates.

Every number here is computed deterministically from data already in the DB (video_keyword_matches,
outlier_scores, videos, topic_opportunities) -- no new YouTube API calls. Gemini is used only to
reword a Viewer Problem into a specific, answerable topic question; it never decides a score.
topic_candidate_score is a separate metric from content_opportunity_score (my_channel.py) and does
not change it.
"""
from __future__ import annotations

import json
import math
import statistics
from collections import Counter
from datetime import date
from pathlib import Path

from research.db import connect
from research.gemini_client import GeminiClient
from research.keyword_pool import load_pool

# ---------------------------------------------------------------------------
# Word-overlap helpers (local to this module -- a topic-candidate-specific use
# distinct from the deterministic query->problem mapping in keyword_pool.py).
# ---------------------------------------------------------------------------

_PARTICLES = (
    "에서부터", "으로부터", "부터", "까지", "에서", "으로", "이나", "라도", "에게", "한테",
    "은", "는", "이", "가", "을", "를", "의", "에", "로", "와", "과", "도", "만",
)


def _stem(word: str) -> str:
    for particle in sorted(_PARTICLES, key=len, reverse=True):
        if word.endswith(particle) and len(word) - len(particle) >= 2:
            return word[: -len(particle)]
    return word


def _content_words(text: str) -> set[str]:
    if not text:
        return set()
    return {_stem(w) for w in text.lower().split() if len(w) > 1}


def _log_normalize(value: float, cap: float) -> float:
    if value is None or value <= 0:
        return 0.0
    return max(0.0, min(100.0, 100 * math.log1p(value) / math.log1p(cap)))


# ---------------------------------------------------------------------------
# Section 4: evidence quality
# ---------------------------------------------------------------------------

def classify_evidence_quality(title: str, problem_label: str, search_query: str) -> str:
    """direct: title clearly reflects the matched problem/query. adjacent: some overlap.
    weak: the video only matched on the search string, not on what it's actually about."""
    title_words = _content_words(title)
    if not title_words:
        return "weak"
    if search_query and search_query.lower() in (title or "").lower():
        return "direct"
    problem_words = _content_words(problem_label)
    if not problem_words:
        return "weak"
    overlap = len(title_words & problem_words)
    ratio = overlap / len(problem_words)
    if ratio >= 0.5:
        return "direct"
    if overlap >= 1:
        return "adjacent"
    return "weak"


_EVIDENCE_QUALITY_SCORES = {"direct": 100.0, "adjacent": 60.0, "weak": 20.0}


# ---------------------------------------------------------------------------
# Section 6: granularity
# ---------------------------------------------------------------------------

def check_granularity(problem_label: str, matched_video_count: int, outlier_video_count: int) -> str:
    if len(_content_words(problem_label)) < 3:
        return "too_broad"
    if outlier_video_count == 0 or matched_video_count <= 2:
        return "too_narrow"
    return "appropriate"


# ---------------------------------------------------------------------------
# Section 8: Long-form / Shorts / Both
# ---------------------------------------------------------------------------

def classify_format(content_types: list[str]) -> str:
    counts = Counter(ct for ct in content_types if ct in ("longform", "short"))
    if not counts:
        return "Both"
    longform, short = counts.get("longform", 0), counts.get("short", 0)
    total = longform + short
    if longform / total >= 0.8:
        return "Long-form"
    if short / total >= 0.8:
        return "Shorts"
    return "Both"


# ---------------------------------------------------------------------------
# Section 10: Topic Candidate Score (pure function, fully deterministic)
# ---------------------------------------------------------------------------

DEFAULT_SCORE_WEIGHTS = {
    "repetition": 0.15,
    "outlier_intensity": 0.20,
    "outlier_count": 0.15,
    "market_demand": 0.20,
    "channel_fit": 0.15,
    "evidence_quality": 0.10,
    "granularity": 0.03,
    "format_breadth": 0.02,
}

DEFAULT_SCORE_CAPS = {
    "matched_video_count_cap": 20,
    "outlier_ratio_cap": 50,
    "outlier_video_count_cap": 15,
}


def compute_topic_candidate_score(
    *,
    matched_video_count: int,
    median_outlier_ratio: float | None,
    outlier_video_count: int,
    market_demand_score: float,
    my_channel_fit_score: float,
    evidence_quality_scores: list[float],
    granularity: str,
    recommended_format: str,
    weights: dict = DEFAULT_SCORE_WEIGHTS,
    caps: dict = DEFAULT_SCORE_CAPS,
) -> float:
    repetition = _log_normalize(matched_video_count, caps["matched_video_count_cap"])
    outlier_intensity = _log_normalize(median_outlier_ratio or 0, caps["outlier_ratio_cap"])
    outlier_count = _log_normalize(outlier_video_count, caps["outlier_video_count_cap"])
    evidence_quality = sum(evidence_quality_scores) / len(evidence_quality_scores) if evidence_quality_scores else 20.0
    granularity_score = 100.0 if granularity == "appropriate" else 70.0
    format_score = 100.0 if recommended_format == "Both" else 75.0

    score = (
        weights["repetition"] * repetition
        + weights["outlier_intensity"] * outlier_intensity
        + weights["outlier_count"] * outlier_count
        + weights["market_demand"] * market_demand_score
        + weights["channel_fit"] * my_channel_fit_score
        + weights["evidence_quality"] * evidence_quality
        + weights["granularity"] * granularity_score
        + weights["format_breadth"] * format_score
    )
    return max(0.0, min(100.0, score))


# ---------------------------------------------------------------------------
# Section 3: Viewer Problem aggregation
# ---------------------------------------------------------------------------

def _latest_topic_opportunities(db_path: Path) -> dict[str, dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM topic_opportunities WHERE id IN (SELECT MAX(id) FROM topic_opportunities GROUP BY problem_category)"
        ).fetchall()
    return {r["problem_category"]: dict(r) for r in rows}


def _problem_outlier_videos(db_path: Path, category: str, problem_id: str) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT v.video_id, v.title, v.content_type, os.outlier_ratio, os.opportunity_score, vkm.search_query
            FROM video_keyword_matches vkm
            JOIN outlier_scores os ON os.video_id = vkm.video_id
            JOIN videos v ON v.video_id = vkm.video_id
            WHERE vkm.category = ? AND vkm.problem_id = ?
              AND os.outlier_grade IS NOT NULL AND os.outlier_grade != 'normal'
            """,
            (category, problem_id),
        ).fetchall()
    by_video: dict[str, dict] = {}
    for r in rows:
        by_video.setdefault(r["video_id"], dict(r))
    return list(by_video.values())


def aggregate_viewer_problems(db_path: Path, *, min_candidate_videos_status: str = "sufficient") -> list[dict]:
    """One row per (category, problem_id) with every field section 3 asks for. Only categories
    whose market_evidence_status is 'sufficient' are included -- an insufficient-data category
    has nothing reliable to promote into a topic candidate yet."""
    topic_by_category = _latest_topic_opportunities(db_path)

    with connect(db_path) as conn:
        problem_rows = conn.execute(
            """
            SELECT category, problem_id, problem_label, COUNT(DISTINCT video_id) AS matched_video_count
            FROM video_keyword_matches
            WHERE problem_label IS NOT NULL
            GROUP BY category, problem_id, problem_label
            """
        ).fetchall()
        query_rows = conn.execute(
            "SELECT DISTINCT category, problem_id, search_query FROM video_keyword_matches WHERE problem_label IS NOT NULL"
        ).fetchall()

    queries_by_problem: dict[tuple[str, str], list[str]] = {}
    for r in query_rows:
        queries_by_problem.setdefault((r["category"], r["problem_id"]), []).append(r["search_query"])

    results = []
    for row in problem_rows:
        category, problem_id, problem_label = row["category"], row["problem_id"], row["problem_label"]
        topic = topic_by_category.get(category)
        if not topic or topic["market_evidence_status"] != min_candidate_videos_status:
            continue

        outlier_videos = _problem_outlier_videos(db_path, category, problem_id)
        outlier_ratios = [v["outlier_ratio"] for v in outlier_videos if v["outlier_ratio"] is not None]
        representative = max(outlier_videos, key=lambda v: v["opportunity_score"] or 0) if outlier_videos else None

        results.append(
            {
                "category": category,
                "problem_id": problem_id,
                "problem_label": problem_label,
                "matched_video_count": row["matched_video_count"],
                "outlier_video_count": len(outlier_videos),
                "outlier_videos": outlier_videos,
                "median_outlier_ratio": statistics.median(outlier_ratios) if outlier_ratios else None,
                "representative_video_id": representative["video_id"] if representative else None,
                "representative_title": representative["title"] if representative else None,
                "representative_outlier_ratio": representative["outlier_ratio"] if representative else None,
                "representative_opportunity_score": representative["opportunity_score"] if representative else None,
                "search_queries": sorted(set(queries_by_problem.get((category, problem_id), []))),
                "market_demand_score": topic["market_demand_score"],
                "my_channel_fit_score": topic["my_channel_fit_score"],
                "market_evidence_status": topic["market_evidence_status"],
                "evidence_confidence": topic["evidence_confidence"],
            }
        )
    return results


# ---------------------------------------------------------------------------
# Section 5: problem -> topic text (Gemini, with a safe non-numeric fallback)
# ---------------------------------------------------------------------------

_TOPIC_TEXT_PROMPT = """다음은 한국 영어교육 YouTube 채널 시청자의 고민이다: "{problem_label}"

이 고민을 "한 편의 영상에서 답할 수 있는 구체적인 질문/주제" 하나로 바꿔라.
너무 넓으면 안 된다 (예: "영어 잘하는 법", "영어 공부법" 금지).
너무 좁아서 한 단어 설명 수준이어도 안 된다.
아래 JSON 형식으로만 답하라:

{{"topic": "구체적인 질문 형태의 주제 1개"}}
"""


def generate_topic_text(problem_label: str, gemini: GeminiClient | None, max_output_tokens: int = 512) -> str:
    if gemini and gemini.available:
        result = gemini.generate_json(_TOPIC_TEXT_PROMPT.format(problem_label=problem_label), max_output_tokens=max_output_tokens)
        if result and result.get("topic"):
            return result["topic"]
    return problem_label


# ---------------------------------------------------------------------------
# Section 7 / 13: clustering (duplicate merge + diversity)
# ---------------------------------------------------------------------------

def cluster_candidates(candidates: list[dict], threshold: float = 0.5) -> list[dict]:
    """Groups candidates whose topic_text word-overlap (Jaccard) is >= threshold. Within a
    cluster, the highest-scoring candidate becomes the representative; the rest are kept but
    marked as non-representative so the report can demote them instead of dropping the signal.

    This is lexical, not semantic: "영어 강세 위치를 어떻게 찾을까" and "영어 강세 위치는 어떻게
    아는가" merge because they share most content words, but true synonyms phrased with
    different words (e.g. "원어민이 빠르게 말한다" vs "듣기 속도를 못 따라간다") won't merge
    without an embedding model, which this project deliberately avoids.
    """
    clusters: list[list[dict]] = []
    for cand in candidates:
        words = _content_words(cand["topic_text"])
        placed = False
        for cluster in clusters:
            rep_words = _content_words(cluster[0]["topic_text"])
            if not words or not rep_words:
                continue
            overlap = len(words & rep_words) / len(words | rep_words)
            if overlap >= threshold:
                cluster.append(cand)
                placed = True
                break
        if not placed:
            clusters.append([cand])

    result = []
    for cluster_id, cluster in enumerate(clusters, start=1):
        cluster.sort(key=lambda c: c["topic_candidate_score"], reverse=True)
        for i, cand in enumerate(cluster):
            cand["cluster_id"] = cluster_id
            cand["is_cluster_representative"] = i == 0
            result.append(cand)
    return result


# ---------------------------------------------------------------------------
# Section 17: shortlist for the next stage (06_클릭_이유_분석)
# ---------------------------------------------------------------------------

def select_shortlist(candidates: list[dict], max_n: int = 10) -> list[dict]:
    representatives = sorted(
        (c for c in candidates if c["is_cluster_representative"]),
        key=lambda c: c["topic_candidate_score"],
        reverse=True,
    )
    shortlist = representatives[:max_n]
    for c in shortlist:
        reasons = []
        if c["topic_candidate_score"] >= 70:
            reasons.append("시장 반응 강함")
        if (c.get("my_channel_fit_score") or 0) >= 60:
            reasons.append("채널 적합도 높음")
        if c["matched_video_count"] >= 5:
            reasons.append("반복 Viewer Problem")
        if c["outlier_video_count"] >= 3:
            reasons.append("여러 Outlier에서 검증")
        if c["recommended_format"] == "Both":
            reasons.append("Long-form + Shorts 확장 가능")
        c["shortlisted"] = True
        c["shortlist_reason"] = ", ".join(reasons) if reasons else "종합 점수 상위"
    return shortlist


# ---------------------------------------------------------------------------
# Section 14: comparison with the Weekly Report's own TOP5
# ---------------------------------------------------------------------------

def compare_with_weekly_top5(db_path: Path, candidates: list[dict], top_n: int = 20) -> list[str]:
    topic_by_category = _latest_topic_opportunities(db_path)
    sufficient = [
        t for t in topic_by_category.values()
        if t["market_evidence_status"] == "sufficient" and t["content_opportunity_score"] is not None
    ]
    sufficient.sort(key=lambda t: t["content_opportunity_score"], reverse=True)
    weekly_top5 = sufficient[:5]
    weekly_top5_categories = {t["problem_category"] for t in weekly_top5}

    reps = [c for c in candidates if c["is_cluster_representative"]][:top_n]
    top20_categories = {c["category"] for c in reps}

    still_top = weekly_top5_categories & top20_categories
    high_demand_low_fit = [
        c for c in reps
        if (c["market_demand_score"] or 0) >= 70 and (c.get("my_channel_fit_score") or 0) < 40
    ]
    high_demand_high_fit = [
        c for c in reps
        if (c["market_demand_score"] or 0) >= 70 and (c.get("my_channel_fit_score") or 0) >= 60
    ]
    strong_outlier_weak_evidence = [
        c for c in reps
        if (c["median_outlier_ratio"] or 0) >= 20 and c["evidence_quality_avg"] < 60
    ]

    lines = []
    lines.append(f"- 기존 TOP5가 여전히 상위 후보인가: 카테고리 기준 {len(still_top)}/5 유지 ({', '.join(sorted(still_top)) or '없음'})")
    lines.append(f"- 더 구체적인 주제로 분해할 필요가 있는가: TOP5는 카테고리당 1개였지만, 이번 분석은 카테고리당 problem 단위로 세분화됨 (예: reading 1개 → {sum(1 for c in reps if c['category']=='reading')}개 후보)")
    lines.append(
        "- 시장수요는 높지만 채널과 거리가 먼 후보: "
        + (", ".join(c["topic_text"] for c in high_demand_low_fit[:3]) or "없음")
    )
    lines.append(
        "- 시장수요와 채널 적합도가 동시에 높은 후보: "
        + (", ".join(c["topic_text"] for c in high_demand_high_fit[:3]) or "없음")
    )
    lines.append(
        "- Outlier는 강하지만 evidence quality가 낮은 후보: "
        + (", ".join(c["topic_text"] for c in strong_outlier_weak_evidence[:3]) or "없음")
    )
    return lines


# ---------------------------------------------------------------------------
# Orchestration + report generation
# ---------------------------------------------------------------------------

def _fmt(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)


def build_candidates(
    db_path: Path,
    gemini: GeminiClient | None,
    *,
    score_weights: dict = DEFAULT_SCORE_WEIGHTS,
    score_caps: dict = DEFAULT_SCORE_CAPS,
    fit_neutral_score: float = 50.0,
    max_output_tokens: int = 512,
) -> list[dict]:
    problems = aggregate_viewer_problems(db_path)
    candidates = []

    for p in problems:
        granularity = check_granularity(p["problem_label"], p["matched_video_count"], p["outlier_video_count"])
        if granularity == "too_broad" or p["outlier_video_count"] == 0:
            continue

        quality_scores = []
        for v in p["outlier_videos"]:
            quality = classify_evidence_quality(v["title"], p["problem_label"], v["search_query"])
            quality_scores.append(_EVIDENCE_QUALITY_SCORES[quality])
        evidence_quality_avg = sum(quality_scores) / len(quality_scores) if quality_scores else 20.0
        evidence_quality_label = (
            "direct" if evidence_quality_avg >= 80 else "adjacent" if evidence_quality_avg >= 40 else "weak"
        )

        recommended_format = classify_format([v["content_type"] for v in p["outlier_videos"]])
        my_channel_fit_score = p["my_channel_fit_score"] if p["my_channel_fit_score"] is not None else fit_neutral_score

        score = compute_topic_candidate_score(
            matched_video_count=p["matched_video_count"],
            median_outlier_ratio=p["median_outlier_ratio"],
            outlier_video_count=p["outlier_video_count"],
            market_demand_score=p["market_demand_score"] or 0.0,
            my_channel_fit_score=my_channel_fit_score,
            evidence_quality_scores=quality_scores,
            granularity=granularity,
            recommended_format=recommended_format,
            weights=score_weights,
            caps=score_caps,
        )

        topic_text = generate_topic_text(p["problem_label"], gemini, max_output_tokens=max_output_tokens)

        candidates.append(
            {
                **p,
                "topic_text": topic_text,
                "granularity": granularity,
                "evidence_quality": evidence_quality_label,
                "evidence_quality_avg": evidence_quality_avg,
                "recommended_format": recommended_format,
                "my_channel_fit_score": my_channel_fit_score,
                "topic_candidate_score": score,
            }
        )

    candidates = cluster_candidates(candidates)
    candidates.sort(key=lambda c: (c["is_cluster_representative"], c["topic_candidate_score"]), reverse=True)
    return candidates


def _persist_candidates(db_path: Path, candidates: list[dict], report_path: str) -> None:
    with connect(db_path) as conn:
        for c in candidates:
            conn.execute(
                """
                INSERT INTO topic_candidates (report_path, category, problem_id, problem_label, topic_text,
                    cluster_id, is_cluster_representative, recommended_format, evidence_quality,
                    topic_candidate_score, market_demand_score, my_channel_fit_score, matched_video_count,
                    outlier_video_count, representative_video_id, representative_outlier_ratio,
                    shortlisted, shortlist_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report_path, c["category"], c["problem_id"], c["problem_label"], c["topic_text"],
                    c["cluster_id"], 1 if c["is_cluster_representative"] else 0, c["recommended_format"],
                    c["evidence_quality"], c["topic_candidate_score"], c["market_demand_score"],
                    c["my_channel_fit_score"], c["matched_video_count"], c["outlier_video_count"],
                    c["representative_video_id"], c["representative_outlier_ratio"],
                    1 if c.get("shortlisted") else 0, c.get("shortlist_reason"),
                ),
            )


def build_topic_candidates_report(
    db_path: Path,
    reports_dir: Path,
    gemini: GeminiClient | None,
    keyword_pool_path: Path,
    *,
    top_n: int = 20,
    score_weights: dict = DEFAULT_SCORE_WEIGHTS,
    score_caps: dict = DEFAULT_SCORE_CAPS,
    fit_neutral_score: float = 50.0,
    max_output_tokens: int = 512,
) -> Path:
    pool = load_pool(keyword_pool_path)
    categories = list(pool.keys())
    topic_by_category = _latest_topic_opportunities(db_path)

    candidates = build_candidates(
        db_path, gemini,
        score_weights=score_weights, score_caps=score_caps,
        fit_neutral_score=fit_neutral_score, max_output_tokens=max_output_tokens,
    )
    reps = [c for c in candidates if c["is_cluster_representative"]]
    top20 = reps[:top_n]
    shortlist = select_shortlist(candidates, max_n=10)
    shortlisted_ids = {(c["category"], c["problem_id"]) for c in shortlist}
    for c in candidates:
        if (c["category"], c["problem_id"]) in shortlisted_ids:
            match = next(s for s in shortlist if s["category"] == c["category"] and s["problem_id"] == c["problem_id"])
            c["shortlisted"] = True
            c["shortlist_reason"] = match["shortlist_reason"]

    lines: list[str] = []
    lines.append("# YouTube Topic Candidates")
    lines.append("")
    lines.append(f"생성일: {date.today().isoformat()}")
    lines.append("")

    lines.append("## 1. 데이터 상태")
    lines.append("")
    for category in categories:
        t = topic_by_category.get(category)
        status = t["market_evidence_status"] if t else "미조사"
        n_candidates = sum(1 for c in candidates if c["category"] == category)
        lines.append(f"- {category}: evidence {status}, 생성된 topic candidate {n_candidates}개")
    lines.append("")

    lines.append("## 2. Viewer Problem 전체 순위")
    lines.append("")
    all_problems = sorted(candidates, key=lambda c: c["outlier_video_count"], reverse=True)
    for c in all_problems:
        lines.append(
            f"- [{c['category']}] {c['problem_label']} — matched {c['matched_video_count']}, "
            f"outlier {c['outlier_video_count']}, median {_fmt(c['median_outlier_ratio'])}X"
        )
    if not all_problems:
        lines.append("- (충분한 evidence를 가진 problem 없음)")
    lines.append("")

    lines.append("## 3. Topic Cluster")
    lines.append("")
    cluster_ids = sorted({c["cluster_id"] for c in candidates})
    for cid in cluster_ids:
        members = [c for c in candidates if c["cluster_id"] == cid]
        rep = next(m for m in members if m["is_cluster_representative"])
        lines.append(f"### Cluster {cid}: {rep['topic_text']}")
        for m in members:
            tag = "대표" if m["is_cluster_representative"] else "하위"
            lines.append(f"  - ({tag}) {m['topic_text']} [{m['category']}] score={_fmt(m['topic_candidate_score'])}")
        lines.append("")

    lines.append(f"## 4. Topic Candidate TOP{top_n}")
    lines.append("")
    for i, c in enumerate(top20, start=1):
        lines.append(f"### #{i}")
        lines.append(f"Topic: {c['topic_text']}")
        lines.append(f"Viewer Problem: {c['problem_label']}")
        lines.append(f"Category: {c['category']}")
        lines.append(f"Recommended format: {c['recommended_format']}")
        lines.append("")
        lines.append("시장 근거:")
        lines.append(f"- matched videos: {c['matched_video_count']}")
        lines.append(f"- outlier videos: {c['outlier_video_count']}")
        lines.append(f"- 대표 Outlier: {c.get('representative_title') or '-'}")
        lines.append(f"- 대표 Outlier 배수: {_fmt(c['representative_outlier_ratio'])}X")
        lines.append(f"- 관련 search queries: {', '.join(c['search_queries']) or '-'}")
        lines.append("")
        lines.append(f"시장 점수: {_fmt(c['market_demand_score'])}")
        lines.append(f"채널 적합도: {_fmt(c['my_channel_fit_score'])}")
        lines.append(f"Evidence Quality: {c['evidence_quality']}")
        lines.append(f"Topic Candidate Score: {_fmt(c['topic_candidate_score'])}")
        lines.append("")
        lines.append(
            f"왜 후보인가: {c['category']} 카테고리에서 '{c['problem_label']}' 고민으로 "
            f"{c['outlier_video_count']}개의 outlier 영상이 발견됐고(대표 {_fmt(c['representative_outlier_ratio'])}X), "
            f"evidence quality는 {c['evidence_quality']}입니다."
        )
        lines.append("")

    lines.append("## 5. Long-form 후보")
    lines.append("")
    for c in [c for c in top20 if c["recommended_format"] in ("Long-form", "Both")]:
        lines.append(f"- {c['topic_text']} (score {_fmt(c['topic_candidate_score'])})")
    if not any(c["recommended_format"] in ("Long-form", "Both") for c in top20):
        lines.append("- (없음)")
    lines.append("")

    lines.append("## 6. Shorts 후보")
    lines.append("")
    for c in [c for c in top20 if c["recommended_format"] in ("Shorts", "Both")]:
        lines.append(f"- {c['topic_text']} (score {_fmt(c['topic_candidate_score'])})")
    if not any(c["recommended_format"] in ("Shorts", "Both") for c in top20):
        lines.append("- (없음)")
    lines.append("")

    section_num = 7
    highlighted = {"reading", "listening", "pronunciation"}
    for category in [c for c in categories if c in highlighted] + ["__OTHER__"]:
        if category == "__OTHER__":
            others = [c for c in candidates if c["category"] not in highlighted]
            lines.append(f"## {section_num}. 기타 카테고리 후보")
            lines.append("")
            for c in others:
                lines.append(f"- [{c['category']}] {c['topic_text']} (score {_fmt(c['topic_candidate_score'])})")
            if not others:
                lines.append("- (없음)")
        else:
            cat_candidates = [c for c in candidates if c["category"] == category]
            lines.append(f"## {section_num}. {category.capitalize()} 후보")
            lines.append("")
            for c in cat_candidates:
                lines.append(f"- {c['topic_text']} (score {_fmt(c['topic_candidate_score'])})")
            if not cat_candidates:
                lines.append("- (없음)")
        lines.append("")
        section_num += 1

    lines.append(f"## {section_num}. Weekly Report TOP5와 비교")
    lines.append("")
    lines.extend(compare_with_weekly_top5(db_path, candidates, top_n=top_n))
    lines.append("")
    section_num += 1

    lines.append(f"## {section_num}. 다음 단계로 넘길 후보")
    lines.append("")
    lines.append("(06_클릭_이유_분석 단계의 조사 대상일 뿐, 최종 제작 결정이 아닙니다)")
    lines.append("")
    for i, c in enumerate(shortlist, start=1):
        lines.append(f"{i}. {c['topic_text']} [{c['category']}] — {c['shortlist_reason']}")
    if not shortlist:
        lines.append("- (근거가 충분한 후보 없음)")
    lines.append("")

    reports_dir.mkdir(parents=True, exist_ok=True)
    out_path = reports_dir / f"topic_candidates_{date.today().isoformat()}.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")

    _persist_candidates(db_path, candidates, str(out_path))

    return out_path
