"""Turns each 06-selected Topic into several distinct Title x Thumbnail packages -- Topic is the
viewer's problem, Title is the click-worthy expression of it, and this stage must never just copy
the Topic sentence into the Title. Package Score is independent from Topic Candidate Score and
Click Evidence Score (never blended into a single number for the final decision). No new YouTube
API calls; Gemini writes titles/thumbnail text, every score is deterministic code.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import date
from pathlib import Path

from research.click_analysis import CLICK_DRIVERS, _BRAND_ALIGNED_DRIVERS, _BRAND_CONFLICTING_DRIVERS
from research.db import connect
from research.gemini_client import GeminiClient
from research.topic_candidates import _content_words

# ---------------------------------------------------------------------------
# Section 5: fixed Packaging Angle taxonomy
# ---------------------------------------------------------------------------

PACKAGING_ANGLES: dict[str, str] = {
    "problem": "시청자의 문제를 직접 보여줌",
    "curiosity": "이유/반전/의문을 이용",
    "result": "시청 후 얻을 결과를 강조",
    "example": "구체적인 영어 단어/문장 사례",
    "beginner_identity": "왕초보/성인 초보 등의 자기 인식",
    "mistake": "흔한 실수 또는 잘못된 접근",
    "contrast": "전/후 또는 예상/실제 대비",
    "simplicity": "복잡한 것을 쉽게 이해한다는 약속",
}

RELATIONSHIP_TYPES = {
    "complementary", "curiosity_plus_answer", "problem_plus_solution", "setup_plus_payoff",
    "contrast", "duplicate", "unclear",
}

# ---------------------------------------------------------------------------
# Section 8: exaggeration phrases -- competitor patterns we don't copy uncritically
# ---------------------------------------------------------------------------

_EXAGGERATION_PATTERNS = [
    re.compile(p) for p in [
        r"무조건", r"100%", r"완벽", r"평생", r"이것만\s?알면\s?끝", r"99%가\s?모르는",
        r"충격", r"기적", r"1초\s?만에", r"무조건\s?됩니다",
    ]
]

_CURIOSITY_RESULT_PATTERNS = re.compile(r"왜|이유|궁금|반전|완성|끝|해결|비법|원리")
_SPECIFICITY_HINT_PATTERNS = re.compile(r"[A-Za-z]{2,}|\d+")


def detect_exaggeration(text: str) -> float:
    """Returns a 0~20 penalty -- one flagged phrase is a mild penalty, several stack up (capped)."""
    hits = sum(1 for p in _EXAGGERATION_PATTERNS if p.search(text or ""))
    return min(20.0, hits * 10.0)


def is_duplicate_relationship(title: str, thumbnail_text: str, threshold: float = 0.7) -> bool:
    """Deterministic backstop: if title and thumbnail restate almost the same words, it's a
    duplicate regardless of what Gemini classified it as.

    This is word-overlap (via _content_words' particle-stripping), not conjugation-aware --
    "읽히지 않을까" and "안 읽힐까" share the same verb stem but score near-zero overlap because
    only trailing particles are stripped, not verb endings. It reliably catches near-verbatim
    repeats (the common real case) but can miss a duplicate phrased with different verb forms.
    """
    title_words = _content_words(title)
    thumb_words = _content_words(thumbnail_text)
    if not title_words or not thumb_words:
        return False
    overlap = len(title_words & thumb_words) / len(title_words | thumb_words)
    return overlap >= threshold


def compute_copy_risk(title: str, existing_titles: list[str]) -> tuple[str, float]:
    """Compares a generated title against real outlier titles already in the DB. Returns
    (risk_level, max_overlap_ratio)."""
    title_words = _content_words(title)
    if not title_words or not existing_titles:
        return "low", 0.0
    max_overlap = 0.0
    for existing in existing_titles:
        existing_words = _content_words(existing)
        if not existing_words:
            continue
        overlap = len(title_words & existing_words) / len(title_words | existing_words)
        max_overlap = max(max_overlap, overlap)
    if max_overlap >= 0.7:
        return "high", max_overlap
    if max_overlap >= 0.5:
        return "medium", max_overlap
    return "low", max_overlap


# ---------------------------------------------------------------------------
# Section 7/10/12: Gemini package generation (title, thumbnail, angle, driver, relationship)
# ---------------------------------------------------------------------------

_ANGLE_LIST = "\n".join(f"- {key}: {label}" for key, label in PACKAGING_ANGLES.items())
_DRIVER_LIST = "\n".join(f"- {key}: {label}" for key, label in CLICK_DRIVERS.items())
_RELATIONSHIP_LIST = ", ".join(sorted(RELATIONSHIP_TYPES))

_PACKAGE_PROMPT = """너는 한국 YouTube 채널 "{channel_name}"의 제목/썸네일 기획자다.

채널 정보:
- 핵심 시청자: {audience}
- 철학: {philosophy}

다음 Topic(시청자 문제)에 대한 Title x Thumbnail 패키지 5개를 만들어라: "{topic_text}"

이 Topic에서 실제로 반복 확인된 Click Driver(참고용, 최대한 활용): {repeated_drivers}

규칙:
1. Title은 Topic 문장을 그대로 베끼지 않는다. Topic은 문제, Title은 그 문제를 클릭하게 만드는 표현이다.
2. 5개 패키지는 서로 다른 packaging angle을 하나씩 사용해야 한다 (아래 목록에서 최소 4개 이상 angle을 겹치지 않게 사용):
{angle_list}
3. primary_click_driver는 반드시 아래 목록의 id 중에서만 골라라:
{driver_list}
4. thumbnail_text는 짧고(2~6단어, 2줄 이내), 제목을 반복하지 않는다. 초보자가 한눈에 읽을 수 있는 짧은 영어 단어(예: KNIFE, CAKE)만 쓰고 긴 영어 문장은 쓰지 않는다.
5. title_thumbnail_relationship은 다음 중 하나: {relationship_list}
6. 과장 표현(무조건/100%/완벽/평생/이것만 알면 끝/99%가 모르는/충격/기적/1초 만에)은 실제로 그 약속을 지킬 수 있는 경우가 아니면 피한다.
7. 실제 촬영/유명인 없이 텍스트 중심으로 제작 가능한 visual_focus/layout만 제안한다.

아래 JSON 배열 형식으로만 답하라 (정확히 5개 항목):
[
  {{
    "title": "제목",
    "thumbnail_text": "썸네일 문구",
    "visual_focus": "썸네일에서 강조할 대상",
    "layout": "배치 설명",
    "example_word": "핵심 영어 예시 단어 (없으면 null)",
    "highlight_element": "강조 요소 설명",
    "primary_angle": "위 angle 목록의 id",
    "secondary_angle": "위 angle 목록의 id 또는 null",
    "primary_click_driver": "위 driver 목록의 id",
    "title_thumbnail_relationship": "위 관계 목록 중 하나"
  }},
  ...
]
"""


def _fallback_packages(topic_text: str, problem_label: str) -> list[dict]:
    """Used only if Gemini is unavailable/fails -- template variations, never the raw Topic
    sentence, still angle-tagged so scoring/report code has something structurally valid."""
    templates = [
        (f"{problem_label}, 원리로 이해하면 쉬워집니다", "problem", "problem_recognition"),
        (f"왜 {problem_label.rstrip('?')}? 진짜 이유", "curiosity", "curiosity_gap"),
        (f"{problem_label}, 처음부터 다시 정리해드립니다", "result", "result_promise"),
        (f"왕초보를 위한 {problem_label} 완전 정복", "beginner_identity", "beginner_identity"),
        (f"{problem_label} - 3가지 핵심 원리", "simplicity", "specificity"),
    ]
    return [
        {
            "title": title, "thumbnail_text": "이제 이해됩니다", "visual_focus": None, "layout": None,
            "example_word": None, "highlight_element": None, "primary_angle": angle, "secondary_angle": None,
            "primary_click_driver": driver, "title_thumbnail_relationship": "unclear",
        }
        for title, angle, driver in templates
    ]


def generate_packages_for_topic(
    topic: dict, gemini: GeminiClient | None, channel_cfg: dict, max_output_tokens: int = 1536
) -> list[dict]:
    repeated_drivers = topic.get("repeated_drivers") or []
    packages = None
    if gemini and gemini.available:
        prompt = _PACKAGE_PROMPT.format(
            channel_name=channel_cfg.get("name", ""),
            audience=channel_cfg.get("audience", ""),
            philosophy=channel_cfg.get("philosophy", ""),
            topic_text=topic["topic_text"],
            repeated_drivers=", ".join(repeated_drivers) or "(데이터 부족)",
            angle_list=_ANGLE_LIST,
            driver_list=_DRIVER_LIST,
            relationship_list=_RELATIONSHIP_LIST,
        )
        result = gemini.generate_json(prompt, max_output_tokens=max_output_tokens)
        if isinstance(result, list) and result:
            packages = result

    if not packages:
        packages = _fallback_packages(topic["topic_text"], topic["problem_label"])

    cleaned = []
    for p in packages:
        angle = p.get("primary_angle")
        secondary_angle = p.get("secondary_angle")
        driver = p.get("primary_click_driver")
        relationship = p.get("title_thumbnail_relationship")
        cleaned.append(
            {
                "title": p.get("title") or topic["problem_label"],
                "thumbnail_text": p.get("thumbnail_text") or "핵심 정리",
                "visual_focus": p.get("visual_focus"),
                "layout": p.get("layout"),
                "example_word": p.get("example_word"),
                "highlight_element": p.get("highlight_element"),
                "primary_angle": angle if angle in PACKAGING_ANGLES else "problem",
                "secondary_angle": secondary_angle if secondary_angle in PACKAGING_ANGLES else None,
                "primary_click_driver": driver if driver in CLICK_DRIVERS else "problem_recognition",
                "title_thumbnail_relationship": relationship if relationship in RELATIONSHIP_TYPES else "unclear",
            }
        )
    return cleaned


# ---------------------------------------------------------------------------
# Section 14: Package Score (pure function, deterministic)
# ---------------------------------------------------------------------------

DEFAULT_PACKAGE_SCORE_WEIGHTS = {
    "viewer_problem_clarity": 0.20,
    "click_driver_match": 0.20,
    "curiosity_result_strength": 0.15,
    "title_thumbnail_role": 0.15,
    "brand_fit": 0.15,
    "specificity": 0.10,
    "originality": 0.05,
}

_RELATIONSHIP_SCORES = {
    "complementary": 100.0, "curiosity_plus_answer": 100.0, "problem_plus_solution": 100.0,
    "setup_plus_payoff": 100.0, "contrast": 90.0, "unclear": 50.0, "duplicate": 0.0,
}


def compute_package_score(
    *,
    title: str,
    problem_label: str,
    primary_click_driver: str,
    repeated_drivers: list[str],
    title_thumbnail_relationship: str,
    example_word: str | None,
    copy_overlap: float,
    weights: dict = DEFAULT_PACKAGE_SCORE_WEIGHTS,
) -> dict:
    title_words = _content_words(title)
    problem_words = _content_words(problem_label)
    viewer_problem_clarity = (
        100 * len(title_words & problem_words) / len(problem_words) if problem_words else 50.0
    )
    viewer_problem_clarity = min(100.0, viewer_problem_clarity)

    if primary_click_driver in repeated_drivers:
        click_driver_match = 100.0
    elif primary_click_driver in CLICK_DRIVERS:
        click_driver_match = 50.0
    else:
        click_driver_match = 20.0

    curiosity_result_strength = 100.0 if _CURIOSITY_RESULT_PATTERNS.search(title or "") else 40.0

    title_thumbnail_role = _RELATIONSHIP_SCORES.get(title_thumbnail_relationship, 50.0)

    if primary_click_driver in _BRAND_ALIGNED_DRIVERS:
        brand_fit_score = 100.0
    elif primary_click_driver in _BRAND_CONFLICTING_DRIVERS:
        brand_fit_score = 30.0
    else:
        brand_fit_score = 65.0

    specificity = 100.0 if example_word or _SPECIFICITY_HINT_PATTERNS.search(title or "") else 50.0

    originality = max(0.0, 100.0 - copy_overlap * 100.0)

    components = {
        "viewer_problem_clarity": viewer_problem_clarity,
        "click_driver_match": click_driver_match,
        "curiosity_result_strength": curiosity_result_strength,
        "title_thumbnail_role": title_thumbnail_role,
        "brand_fit": brand_fit_score,
        "specificity": specificity,
        "originality": originality,
    }
    base_score = sum(weights[k] * components[k] for k in weights)
    return {"base_score": max(0.0, min(100.0, base_score)), "components": components}


def classify_package_brand_fit(primary_click_driver: str) -> str:
    if primary_click_driver in _BRAND_ALIGNED_DRIVERS:
        return "high"
    if primary_click_driver in _BRAND_CONFLICTING_DRIVERS:
        return "low"
    return "medium"


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def _fmt(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)


def _latest_click_analysis_topics(db_path: Path) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM click_analysis_topics WHERE generated_at = (SELECT MAX(generated_at) FROM click_analysis_topics)"
        ).fetchall()
    return [dict(r) for r in rows]


def _existing_titles_for(db_path: Path, category: str, problem_id: str) -> list[str]:
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT v.title FROM video_keyword_matches vkm
            JOIN videos v ON v.video_id = vkm.video_id
            WHERE vkm.category = ? AND vkm.problem_id = ?
            """,
            (category, problem_id),
        ).fetchall()
    return [r["title"] for r in rows if r["title"]]


def select_target_topics(db_path: Path) -> list[dict]:
    """05/06 source of truth: the latest selected_for_next_stage=1 topics, plus a Listening
    comparison candidate (best click_evidence_score in that category) even if it wasn't
    auto-selected -- so a strong Listening package isn't excluded just for missing 06's cut."""
    all_topics = _latest_click_analysis_topics(db_path)
    main = [t for t in all_topics if t["selected_for_next_stage"]]
    for t in main:
        t["is_comparison_candidate"] = False

    main_keys = {(t["category"], t["problem_id"]) for t in main}
    listening_topics = sorted(
        (t for t in all_topics if t["category"] == "listening"),
        key=lambda t: t["click_evidence_score"],
        reverse=True,
    )
    comparison = None
    if listening_topics and (listening_topics[0]["category"], listening_topics[0]["problem_id"]) not in main_keys:
        comparison = dict(listening_topics[0])
        comparison["is_comparison_candidate"] = True

    result = main + ([comparison] if comparison else [])
    for t in result:
        try:
            t["repeated_drivers"] = list(json.loads(t["repeated_click_drivers_json"] or "{}").get("driver_counts", {}).keys())
        except (TypeError, json.JSONDecodeError):
            t["repeated_drivers"] = []
        with connect(db_path) as conn:
            problem_row = conn.execute(
                "SELECT problem_label FROM video_keyword_matches WHERE category = ? AND problem_id = ? LIMIT 1",
                (t["category"], t["problem_id"]),
            ).fetchone()
        t["problem_label"] = problem_row["problem_label"] if problem_row else t["topic_text"]
    return result


def build_all_packages(db_path: Path, gemini: GeminiClient | None, channel_cfg: dict, max_output_tokens: int = 1536) -> list[dict]:
    topics = select_target_topics(db_path)
    all_packages = []
    for topic in topics:
        existing_titles = _existing_titles_for(db_path, topic["category"], topic["problem_id"])
        raw_packages = generate_packages_for_topic(topic, gemini, channel_cfg, max_output_tokens=max_output_tokens)

        for p in raw_packages:
            if is_duplicate_relationship(p["title"], p["thumbnail_text"]):
                p["title_thumbnail_relationship"] = "duplicate"

            copy_risk, copy_overlap = compute_copy_risk(p["title"], existing_titles)
            exaggeration_penalty = detect_exaggeration(p["title"]) + detect_exaggeration(p["thumbnail_text"])
            duplicate_penalty = 10.0 if p["title_thumbnail_relationship"] == "duplicate" else 0.0

            scored = compute_package_score(
                title=p["title"], problem_label=topic["problem_label"],
                primary_click_driver=p["primary_click_driver"], repeated_drivers=topic["repeated_drivers"],
                title_thumbnail_relationship=p["title_thumbnail_relationship"], example_word=p["example_word"],
                copy_overlap=copy_overlap,
            )
            package_score = max(0.0, scored["base_score"] - exaggeration_penalty - duplicate_penalty)
            excluded_reason = "copy_risk=high (기존 outlier 제목과 지나치게 유사)" if copy_risk == "high" else None

            all_packages.append(
                {
                    **p,
                    "category": topic["category"],
                    "problem_id": topic["problem_id"],
                    "topic_text": topic["topic_text"],
                    "is_comparison_candidate": topic["is_comparison_candidate"],
                    "brand_fit": classify_package_brand_fit(p["primary_click_driver"]),
                    "copy_risk": copy_risk,
                    "copy_overlap": copy_overlap,
                    "exaggeration_penalty": exaggeration_penalty + duplicate_penalty,
                    "package_score": package_score,
                    "topic_candidate_score": topic.get("topic_candidate_score"),
                    "click_evidence_score": topic.get("click_evidence_score"),
                    "excluded_reason": excluded_reason,
                }
            )
    return all_packages


def select_topic_top3(packages: list[dict]) -> dict[tuple, list[dict]]:
    by_topic: dict[tuple, list[dict]] = {}
    for p in packages:
        if p["excluded_reason"]:
            continue
        key = (p["category"], p["problem_id"])
        by_topic.setdefault(key, []).append(p)
    for key, items in by_topic.items():
        items.sort(key=lambda p: p["package_score"], reverse=True)
        by_topic[key] = items[:3]
    return by_topic


def select_overall_top10(packages: list[dict], max_n: int = 10, max_per_topic: int = 2) -> list[dict]:
    eligible = sorted((p for p in packages if not p["excluded_reason"]), key=lambda p: p["package_score"], reverse=True)
    result = []
    per_topic_count: Counter = Counter()
    for p in eligible:
        key = (p["category"], p["problem_id"])
        if per_topic_count[key] >= max_per_topic:
            continue
        result.append(p)
        per_topic_count[key] += 1
        if len(result) >= max_n:
            break
    return result


def select_production_candidates(packages: list[dict], min_n: int = 3, max_n: int = 3) -> list[dict]:
    """Doesn't just take Package Score #1-3 -- filters to reasonable brand fit first, then
    balances topic diversity, click evidence, and package score."""
    eligible = [p for p in packages if not p["excluded_reason"] and p["brand_fit"] != "low"]
    eligible.sort(
        key=lambda p: (p["package_score"] + (p["click_evidence_score"] or 0) + (p["topic_candidate_score"] or 0)) / 3,
        reverse=True,
    )
    selected: list[dict] = []
    seen_topics: set[tuple] = set()
    for p in eligible:
        key = (p["category"], p["problem_id"])
        if key in seen_topics:
            continue  # prefer topic diversity in the final 3
        selected.append(p)
        seen_topics.add(key)
        if len(selected) >= max_n:
            break
    for p in selected:
        reasons = []
        if p["package_score"] >= 75:
            reasons.append("Package Score 강함")
        if (p["click_evidence_score"] or 0) >= 70:
            reasons.append("Click Evidence 충분")
        if (p["topic_candidate_score"] or 0) >= 70:
            reasons.append("시장 반응 강함")
        if p["brand_fit"] == "high":
            reasons.append("Channel Brand Fit 높음")
        reasons.append("Topic 다양성 확보")
        p["production_reason"] = ", ".join(reasons)
    return selected


def _persist(db_path: Path, packages: list[dict], report_path: str) -> None:
    with connect(db_path) as conn:
        for p in packages:
            conn.execute(
                """
                INSERT INTO content_packages (report_path, category, problem_id, topic_text,
                    is_comparison_candidate, title, thumbnail_text, visual_focus, layout, example_word,
                    highlight_element, primary_angle, secondary_angle, primary_click_driver,
                    title_thumbnail_relationship, brand_fit, copy_risk, exaggeration_penalty,
                    package_score, topic_candidate_score, click_evidence_score, excluded_reason,
                    selected_for_production, production_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report_path, p["category"], p["problem_id"], p["topic_text"],
                    1 if p["is_comparison_candidate"] else 0, p["title"], p["thumbnail_text"],
                    p["visual_focus"], p["layout"], p["example_word"], p["highlight_element"],
                    p["primary_angle"], p["secondary_angle"], p["primary_click_driver"],
                    p["title_thumbnail_relationship"], p["brand_fit"], p["copy_risk"],
                    p["exaggeration_penalty"], p["package_score"], p["topic_candidate_score"],
                    p["click_evidence_score"], p["excluded_reason"],
                    1 if p.get("selected_for_production") else 0, p.get("production_reason"),
                ),
            )


_REVIEW_QUESTIONS = [
    "이 제목을 보고 시청자가 무엇을 기대하는가?",
    "썸네일을 1초 봤을 때 무엇이 궁금해지는가?",
    "영상이 실제로 이 약속을 지킬 수 있는가?",
    "우리 채널에서 자연스럽게 느껴지는가?",
]


def build_content_packages_report(
    db_path: Path,
    reports_dir: Path,
    gemini: GeminiClient | None,
    channel_cfg: dict,
    *,
    top_n: int = 10,
    max_output_tokens: int = 1536,
) -> Path:
    packages = build_all_packages(db_path, gemini, channel_cfg, max_output_tokens=max_output_tokens)
    topic_top3 = select_topic_top3(packages)
    overall_top10 = select_overall_top10(packages, max_n=top_n)
    production = select_production_candidates(packages)
    production_keys = {(p["category"], p["problem_id"], p["title"]) for p in production}
    for p in packages:
        p["selected_for_production"] = (p["category"], p["problem_id"], p["title"]) in production_keys

    topics_seen = []
    for p in packages:
        key = (p["category"], p["problem_id"])
        if key not in [t[0] for t in topics_seen]:
            topics_seen.append((key, p["topic_text"], p["is_comparison_candidate"]))

    lines: list[str] = []
    lines.append("# YouTube Title & Thumbnail Strategy")
    lines.append("")
    lines.append(f"생성일: {date.today().isoformat()}")
    lines.append("")

    lines.append("## 1. 분석 대상")
    lines.append("")
    for (category, problem_id), topic_text, is_comparison in topics_seen:
        tag = " (Listening 비교군)" if is_comparison else ""
        lines.append(f"- [{category}] {topic_text}{tag}")
    lines.append("")

    lines.append("## 2. Topic별 Click Driver")
    lines.append("")
    for (key, topic_text, _is_cmp) in topics_seen:
        drivers = {p["primary_click_driver"] for p in packages if (p["category"], p["problem_id"]) == key}
        lines.append(f"- {topic_text}: {', '.join(sorted(drivers))}")
    lines.append("")

    lines.append("## 3. Topic별 Packaging Angle")
    lines.append("")
    for (key, topic_text, _is_cmp) in topics_seen:
        angles = [p["primary_angle"] for p in packages if (p["category"], p["problem_id"]) == key]
        lines.append(f"- {topic_text}: {', '.join(sorted(set(angles)))} ({len(set(angles))}종)")
    lines.append("")

    lines.append("## 4. 전체 제목 후보")
    lines.append("")
    for p in packages:
        flag = f" [copy_risk={p['copy_risk']}]" if p["copy_risk"] != "low" else ""
        lines.append(f"- ({p['primary_angle']}/{p['primary_click_driver']}) {p['title']}{flag}")
    lines.append("")

    lines.append("## 5. Topic별 TOP3 Package")
    lines.append("")
    for (key, topic_text, _is_cmp) in topics_seen:
        lines.append(f"### {topic_text}")
        for p in topic_top3.get(key, []):
            lines.append(f"- **{p['title']}** (score {_fmt(p['package_score'])})")
            lines.append(f"  - 썸네일: {p['thumbnail_text']}")
            lines.append(f"  - Angle: {p['primary_angle']} / Driver: {p['primary_click_driver']} / 관계: {p['title_thumbnail_relationship']}")
        lines.append("")

    lines.append("## 6. 전체 Package TOP10")
    lines.append("")
    for i, p in enumerate(overall_top10, start=1):
        lines.append(f"{i}. [{p['category']}] {p['title']} (score {_fmt(p['package_score'])}) — 썸네일: {p['thumbnail_text']}")
    lines.append("")

    lines.append("## 7. Listening 비교군")
    lines.append("")
    comparison_packages = [p for p in packages if p["is_comparison_candidate"]]
    if comparison_packages:
        topic_text = comparison_packages[0]["topic_text"]
        best = max(comparison_packages, key=lambda p: p["package_score"])
        lines.append(f"Topic: {topic_text}")
        lines.append(
            f"최고 Package Score: {_fmt(best['package_score'])} (Topic {_fmt(best['topic_candidate_score'])}, "
            f"Click {_fmt(best['click_evidence_score'])}, Brand Fit {best['brand_fit']})"
        )
        strong = best["package_score"] >= 70 and (best["click_evidence_score"] or 0) >= 60 and best["brand_fit"] != "low"
        lines.append(
            "판정: Reading 중심 후보에 뒤지지 않는 강한 Package가 나옴" if strong
            else "판정: 상대적으로 약함 — 자동 제외 사유가 있는 것으로 보이며 정직하게 탈락"
        )
    else:
        lines.append("- (Listening 비교군 없음 — 06 결과에 listening 카테고리 topic이 없음)")
    lines.append("")

    lines.append("## 8. 과장/Copy Risk 제외 항목")
    lines.append("")
    excluded = [p for p in packages if p["excluded_reason"]]
    for p in excluded:
        lines.append(f"- {p['title']} — {p['excluded_reason']}")
    penalized = [p for p in packages if p["exaggeration_penalty"] > 0 and not p["excluded_reason"]]
    for p in penalized:
        lines.append(f"- {p['title']} — 감점만 적용 (penalty {_fmt(p['exaggeration_penalty'])}, 최종 제외 아님)")
    if not excluded and not penalized:
        lines.append("- (해당 없음)")
    lines.append("")

    lines.append("## 9. 실제 제작 검토 후보 TOP3")
    lines.append("")
    for i, p in enumerate(production, start=1):
        lines.append(f"### #{i}: {p['title']}")
        lines.append(f"Topic: {p['topic_text']}")
        lines.append(f"썸네일: {p['thumbnail_text']}")
        lines.append(
            f"Topic Candidate: {_fmt(p['topic_candidate_score'])} / Click Evidence: {_fmt(p['click_evidence_score'])} "
            f"/ Package: {_fmt(p['package_score'])} / Brand Fit: {p['brand_fit']}"
        )
        lines.append(f"선정 이유: {p['production_reason']}")
        lines.append("")
        for q in _REVIEW_QUESTIONS:
            lines.append(f"- {q}")
        lines.append("")
    if not production:
        lines.append("- (brand_fit='low'가 아닌 후보가 없어 선정된 항목 없음)")
        lines.append("")

    lines.append("## 10. 다음 단계")
    lines.append("")
    lines.append("이번 단계에서는 대본/촬영/최종 제작을 확정하지 않았습니다. 위 TOP3 중 하나를 확정하면")
    lines.append("실제 대본과 촬영 구성으로 넘어갈 수 있습니다 (다음 프롬프트 단계에서 진행).")
    lines.append("")

    reports_dir.mkdir(parents=True, exist_ok=True)
    out_path = reports_dir / f"content_packages_{date.today().isoformat()}.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")

    _persist(db_path, packages, str(out_path))

    return out_path
