"""Analyzes *why* the representative outlier videos behind each shortlisted Topic Candidate got
clicked -- as opposed to topic_candidates.py, which scores whether the topic is worth pursuing at
all. Click Evidence Score is a separate, independently-stored metric; it never modifies
topic_candidate_score. No new YouTube API calls: everything comes from videos/outlier_scores/
video_keyword_matches already in the DB. Thumbnail image analysis and first-30-seconds hook
analysis have no existing infrastructure in this project (no OCR, no transcripts) and are
deliberately left `unavailable` rather than building new capabilities for them.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import date
from pathlib import Path

from research.db import connect
from research.gemini_client import GeminiClient
from research.topic_candidates import (
    _EVIDENCE_QUALITY_SCORES,
    _content_words,
    _log_normalize,
    classify_evidence_quality,
)

# ---------------------------------------------------------------------------
# Section 4-F: rule-based click "device" flags (same regex style as
# content_pattern_analyzer.py, extended with the devices this spec lists).
# ---------------------------------------------------------------------------

_DEVICE_PATTERNS = {
    "why": re.compile(r"왜"),
    "reason": re.compile(r"이유|때문|원인"),
    "one_thing_only": re.compile(r"이것만|하나면|딱\s?하나"),
    "ending": re.compile(r"끝|종결"),
    "beginner": re.compile(r"왕초보|초보"),
    "real": re.compile(r"진짜|실제"),
    "native_speaker": re.compile(r"원어민"),
    "first_time_seeing": re.compile(r"처음\s?보는"),
    "dont_do_this": re.compile(r"하지\s?마세요|절대\s?하지"),
    "few_reasons": re.compile(r"몇\s?가지|여러\s?가지"),
    "number": re.compile(r"\d+"),
    "time_saving": re.compile(r"시간\s?절약|빠르게|순식간"),
    "loss_avoidance": re.compile(r"손해|낭비|놓치"),
    "mistake_avoidance": re.compile(r"실수|틀리"),
    "twist": re.compile(r"반전|사실은|알고보니"),
    "result_promise": re.compile(r"됩니다|끝냅니다|해결|완성"),
}


def classify_click_devices(title: str) -> dict[str, bool]:
    title = title or ""
    return {name: bool(pattern.search(title)) for name, pattern in _DEVICE_PATTERNS.items()}


# ---------------------------------------------------------------------------
# Section 8: fixed Click Driver taxonomy
# ---------------------------------------------------------------------------

CLICK_DRIVERS: dict[str, str] = {
    "problem_recognition": "내가 겪는 문제다",
    "curiosity_gap": "왜 그런지 궁금하다",
    "result_promise": "이걸 보면 해결된다",
    "one_solution": "이것 하나면 된다",
    "beginner_identity": "왕초보인 나를 위한 영상이다",
    "loss_avoidance": "잘못 공부하면 시간 낭비한다",
    "speed_convenience": "빠르게/쉽게 해결",
    "specificity": "구체적인 단어/문장/상황",
    "surprise": "상식과 다른 결과",
    "social_proof": "조회수/성공 사례/권위/실제 사례",
    "fear_or_failure": "못 알아듣음/틀림/실패 회피",
    "transformation": "전에는 못함 → 이제 가능",
}

_BRAND_ALIGNED_DRIVERS = {"problem_recognition", "curiosity_gap", "transformation", "specificity", "beginner_identity"}
_BRAND_CONFLICTING_DRIVERS = {"fear_or_failure", "surprise", "social_proof"}


def fallback_click_driver(devices: dict[str, bool]) -> str:
    """Deterministic guess from the cheap device flags alone, used whenever Gemini is
    unavailable so every video still gets a driver from the fixed taxonomy."""
    if devices.get("loss_avoidance") or devices.get("mistake_avoidance"):
        return "loss_avoidance" if devices.get("loss_avoidance") else "fear_or_failure"
    if devices.get("one_thing_only") or devices.get("ending"):
        return "one_solution"
    if devices.get("beginner"):
        return "beginner_identity"
    if devices.get("number") or devices.get("few_reasons"):
        return "specificity"
    if devices.get("time_saving"):
        return "speed_convenience"
    if devices.get("twist"):
        return "surprise"
    if devices.get("why") or devices.get("reason"):
        return "curiosity_gap"
    if devices.get("result_promise"):
        return "result_promise"
    return "problem_recognition"


# ---------------------------------------------------------------------------
# Section 3: representative outlier selection
# ---------------------------------------------------------------------------

_QUALITY_RANK = {"direct": 3, "adjacent": 2, "weak": 1}


def _fetch_problem_outlier_videos(db_path: Path, category: str, problem_id: str) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT v.video_id, v.title, v.content_type, v.channel_id, c.title AS channel_title,
                   os.outlier_ratio, os.opportunity_score, vkm.search_query
            FROM video_keyword_matches vkm
            JOIN outlier_scores os ON os.video_id = vkm.video_id
            JOIN videos v ON v.video_id = vkm.video_id
            LEFT JOIN channels c ON c.channel_id = v.channel_id
            WHERE vkm.category = ? AND vkm.problem_id = ?
              AND os.outlier_grade IS NOT NULL AND os.outlier_grade != 'normal'
            """,
            (category, problem_id),
        ).fetchall()
    by_video: dict[str, dict] = {}
    for r in rows:
        by_video.setdefault(r["video_id"], dict(r))
    return list(by_video.values())


def select_representative_videos(
    db_path: Path, category: str, problem_id: str, problem_label: str, max_n: int = 5
) -> list[dict]:
    """Picks up to max_n outlier videos for a topic: direct evidence first, then adjacent, then
    weak, each bucket sorted by opportunity_score, preferring channels not already picked so one
    channel (or one viral meme/entertainment Short) can't represent the whole topic alone."""
    videos = _fetch_problem_outlier_videos(db_path, category, problem_id)
    for v in videos:
        v["evidence_quality"] = classify_evidence_quality(v["title"], problem_label, v["search_query"])

    videos.sort(key=lambda v: (_QUALITY_RANK[v["evidence_quality"]], v["opportunity_score"] or 0), reverse=True)

    selected: list[dict] = []
    seen_channels: set[str] = set()
    for v in videos:
        if len(selected) >= max_n:
            break
        if v["channel_id"] in seen_channels and len(selected) < max_n - 1:
            continue  # prefer a fresh channel while there's still room to be picky
        selected.append(v)
        seen_channels.add(v["channel_id"])

    if len(selected) < min(max_n, len(videos)):
        for v in videos:
            if len(selected) >= max_n or v in selected:
                continue
            selected.append(v)

    return selected[:max_n]


# ---------------------------------------------------------------------------
# Section 4: per-video click-reason analysis (Gemini for qualitative fields,
# rule-based devices/driver always computed and used as the fallback)
# ---------------------------------------------------------------------------

_CLICK_DRIVER_LIST = "\n".join(f"- {key}: {label}" for key, label in CLICK_DRIVERS.items())

_CLICK_ANALYSIS_PROMPT = """다음은 한국 영어교육 YouTube 영상의 제목이다: "{title}"
이 영상이 답하려는 시청자 고민(참고용): "{problem_label}"

이 제목이 왜 클릭됐을지 분석해서 아래 JSON 형식으로만 답하라.

primary_click_driver와 secondary_click_driver는 반드시 아래 목록의 id 중에서만 골라라
(해당 없으면 secondary는 null):
{driver_list}

{{
  "viewer_problem_at_click": "클릭 직전 시청자가 느끼고 있었을 문제 (한 문장)",
  "title_hook": "제목이 문제를 건드리는 표현 방식 (한 문장)",
  "title_promise": "제목이 약속하는 결과 (한 문장)",
  "has_curiosity_gap": true 또는 false,
  "specificity": "specific 또는 broad",
  "emotion": "제목의 핵심 감정 (예: 답답함, 불안, 호기심, 안도감, 기대, 놀람, 자신감 등 한 단어~구)",
  "primary_click_driver": "위 목록의 id 중 하나",
  "secondary_click_driver": "위 목록의 id 중 하나 또는 null"
}}
"""


def analyze_video_click_reasons(video: dict, problem_label: str, gemini: GeminiClient | None, max_output_tokens: int = 512) -> dict:
    title = video["title"]
    devices = classify_click_devices(title)
    result = {
        "video_id": video["video_id"],
        "content_type": video.get("content_type"),
        "evidence_quality": video["evidence_quality"],
        "devices": devices,
        "viewer_problem_at_click": None,
        "title_hook": None,
        "title_promise": None,
        "has_curiosity_gap": bool(_content_words(title) & _content_words("왜 어떻게")) or devices["why"],
        "specificity": "specific" if (devices["number"] or devices["first_time_seeing"] or devices["native_speaker"]) else "broad",
        "emotion": None,
        "primary_click_driver": fallback_click_driver(devices),
        "secondary_click_driver": None,
        "source": "rule",
    }

    if gemini and gemini.available:
        prompt = _CLICK_ANALYSIS_PROMPT.format(title=title, problem_label=problem_label, driver_list=_CLICK_DRIVER_LIST)
        gemini_result = gemini.generate_json(prompt, max_output_tokens=max_output_tokens)
        if gemini_result:
            result["viewer_problem_at_click"] = gemini_result.get("viewer_problem_at_click")
            result["title_hook"] = gemini_result.get("title_hook")
            result["title_promise"] = gemini_result.get("title_promise")
            if isinstance(gemini_result.get("has_curiosity_gap"), bool):
                result["has_curiosity_gap"] = gemini_result["has_curiosity_gap"]
            if gemini_result.get("specificity") in ("specific", "broad"):
                result["specificity"] = gemini_result["specificity"]
            result["emotion"] = gemini_result.get("emotion")

            primary = gemini_result.get("primary_click_driver")
            secondary = gemini_result.get("secondary_click_driver")
            result["primary_click_driver"] = primary if primary in CLICK_DRIVERS else fallback_click_driver(devices)
            result["secondary_click_driver"] = secondary if secondary in CLICK_DRIVERS else None
            result["source"] = "gemini"

    return result


# ---------------------------------------------------------------------------
# Section 9: repeated click patterns within a topic
# ---------------------------------------------------------------------------

def summarize_repeated_patterns(video_analyses: list[dict]) -> dict:
    total = len(video_analyses)
    if total == 0:
        return {"total": 0, "driver_counts": {}, "device_counts": {}}
    driver_counts = Counter(v["primary_click_driver"] for v in video_analyses)
    device_counts: Counter = Counter()
    for v in video_analyses:
        for device, present in v["devices"].items():
            if present:
                device_counts[device] += 1
    return {"total": total, "driver_counts": dict(driver_counts), "device_counts": dict(device_counts)}


# ---------------------------------------------------------------------------
# Section 10: Click Evidence Score (pure function, deterministic)
# ---------------------------------------------------------------------------

DEFAULT_CLICK_SCORE_WEIGHTS = {
    "repeated_driver": 0.30,
    "representative_count": 0.20,
    "evidence_quality": 0.20,
    "title_thumbnail_clarity": 0.15,
    "viewer_problem_match": 0.15,
}


def compute_click_evidence_score(
    *,
    video_analyses: list[dict],
    thumbnail_data_available: bool = False,
    weights: dict = DEFAULT_CLICK_SCORE_WEIGHTS,
    representative_count_cap: int = 5,
) -> float:
    total = len(video_analyses)
    if total == 0:
        return 0.0

    driver_counts = Counter(v["primary_click_driver"] for v in video_analyses)
    repeated_driver_score = (driver_counts.most_common(1)[0][1] / total) * 100

    representative_count_score = _log_normalize(total, representative_count_cap)

    evidence_quality_score = sum(_EVIDENCE_QUALITY_SCORES[v["evidence_quality"]] for v in video_analyses) / total

    non_weak = sum(1 for v in video_analyses if v["evidence_quality"] != "weak")
    viewer_problem_match_score = (non_weak / total) * 100

    components = {
        "repeated_driver": repeated_driver_score,
        "representative_count": representative_count_score,
        "evidence_quality": evidence_quality_score,
        "viewer_problem_match": viewer_problem_match_score,
    }
    active_weights = {k: v for k, v in weights.items() if k in components}
    if thumbnail_data_available:
        components["title_thumbnail_clarity"] = 50.0  # not implemented; neutral placeholder if ever enabled
        active_weights["title_thumbnail_clarity"] = weights["title_thumbnail_clarity"]

    # Renormalize so unavailable evidence (thumbnail data, here always missing) doesn't get
    # silently scored as 0 -- the remaining weights are scaled up to still sum to 1.0.
    weight_sum = sum(active_weights.values())
    score = sum(active_weights[k] / weight_sum * components[k] for k in active_weights)
    return max(0.0, min(100.0, score))


# ---------------------------------------------------------------------------
# Section 13: Channel Brand Fit
# ---------------------------------------------------------------------------

def classify_brand_fit(video_analyses: list[dict]) -> str:
    total = len(video_analyses)
    if total == 0:
        return "medium"
    aligned = sum(1 for v in video_analyses if v["primary_click_driver"] in _BRAND_ALIGNED_DRIVERS)
    conflicting = sum(1 for v in video_analyses if v["primary_click_driver"] in _BRAND_CONFLICTING_DRIVERS)
    aligned_ratio = aligned / total
    conflicting_ratio = conflicting / total
    if aligned_ratio >= 0.6 and conflicting_ratio < 0.4:
        return "high"
    if conflicting_ratio >= 0.6:
        return "low"
    return "medium"


# ---------------------------------------------------------------------------
# Section 16: candidates to hand off to 07_제목_썸네일_전략
# ---------------------------------------------------------------------------

def select_next_stage_candidates(topics: list[dict], min_n: int = 3, max_n: int = 5) -> list[dict]:
    eligible = [t for t in topics if t["brand_fit"] != "low"]
    eligible.sort(key=lambda t: t["click_evidence_score"], reverse=True)
    selected = eligible[:max_n]
    for t in selected:
        reasons = []
        if t["click_evidence_score"] >= 70:
            reasons.append("Click Evidence 강함")
        if t["brand_fit"] == "high":
            reasons.append("Channel Brand Fit 높음")
        if (t["topic_candidate_score"] or 0) >= 70:
            reasons.append("시장 반응 강함")
        if t["representative_video_count"] >= 4:
            reasons.append("Evidence Quality 충분")
        t["selection_reason"] = ", ".join(reasons) if reasons else "종합 순위 상위"
    if len(selected) < min_n:
        # honest reporting: don't pad with brand_fit='low' topics just to hit the minimum
        pass
    return selected


# ---------------------------------------------------------------------------
# Orchestration + report
# ---------------------------------------------------------------------------

def _fmt(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)


def _latest_shortlist(db_path: Path, top_n: int) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM topic_candidates
            WHERE shortlisted = 1
              AND generated_at = (SELECT MAX(generated_at) FROM topic_candidates)
            ORDER BY topic_candidate_score DESC
            LIMIT ?
            """,
            (top_n,),
        ).fetchall()
    return [dict(r) for r in rows]


def build_click_analysis(db_path: Path, gemini: GeminiClient | None, *, top_n: int = 10, max_output_tokens: int = 512) -> list[dict]:
    shortlist = _latest_shortlist(db_path, top_n)
    topics = []
    for topic in shortlist:
        representatives = select_representative_videos(
            db_path, topic["category"], topic["problem_id"], topic["problem_label"], max_n=5
        )
        video_analyses = [
            analyze_video_click_reasons(v, topic["problem_label"], gemini, max_output_tokens=max_output_tokens)
            for v in representatives
        ]
        patterns = summarize_repeated_patterns(video_analyses)
        click_score = compute_click_evidence_score(video_analyses=video_analyses)
        brand_fit = classify_brand_fit(video_analyses)
        combined_signal = (
            ((topic["topic_candidate_score"] or 0) + click_score) / 2 if topic["topic_candidate_score"] is not None else None
        )

        topics.append(
            {
                "category": topic["category"],
                "problem_id": topic["problem_id"],
                "problem_label": topic["problem_label"],
                "topic_text": topic["topic_text"],
                "topic_candidate_score": topic["topic_candidate_score"],
                "click_evidence_score": click_score,
                "combined_signal": combined_signal,
                "brand_fit": brand_fit,
                "representative_video_count": len(representatives),
                "representative_videos": representatives,
                "video_analyses": video_analyses,
                "repeated_patterns": patterns,
                "thumbnail_data_status": "unavailable",
                "hook_data_status": "unavailable",
            }
        )
    return topics


def _persist(db_path: Path, topics: list[dict], report_path: str) -> None:
    with connect(db_path) as conn:
        for t in topics:
            conn.execute(
                """
                INSERT INTO click_analysis_topics (report_path, category, problem_id, topic_text,
                    topic_candidate_score, click_evidence_score, combined_signal, brand_fit,
                    representative_video_count, repeated_click_drivers_json, thumbnail_data_status,
                    hook_data_status, selected_for_next_stage, selection_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report_path, t["category"], t["problem_id"], t["topic_text"],
                    t["topic_candidate_score"], t["click_evidence_score"], t["combined_signal"], t["brand_fit"],
                    t["representative_video_count"], json.dumps(t["repeated_patterns"], ensure_ascii=False),
                    t["thumbnail_data_status"], t["hook_data_status"],
                    1 if t.get("selected_for_next_stage") else 0, t.get("selection_reason"),
                ),
            )
            for v in t["video_analyses"]:
                conn.execute(
                    """
                    INSERT INTO click_analysis_videos (report_path, category, problem_id, video_id,
                        content_type, evidence_quality, viewer_problem_at_click, title_hook, title_promise,
                        has_curiosity_gap, specificity, emotion, devices_json, primary_click_driver,
                        secondary_click_driver, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        report_path, t["category"], t["problem_id"], v["video_id"], v["content_type"],
                        v["evidence_quality"], v["viewer_problem_at_click"], v["title_hook"], v["title_promise"],
                        1 if v["has_curiosity_gap"] else 0, v["specificity"], v["emotion"],
                        json.dumps(v["devices"], ensure_ascii=False), v["primary_click_driver"],
                        v["secondary_click_driver"], v["source"],
                    ),
                )


def build_click_analysis_report(
    db_path: Path,
    reports_dir: Path,
    gemini: GeminiClient | None,
    *,
    top_n: int = 10,
    max_output_tokens: int = 512,
) -> Path:
    topics = build_click_analysis(db_path, gemini, top_n=top_n, max_output_tokens=max_output_tokens)
    next_stage = select_next_stage_candidates(topics)
    next_stage_ids = {(t["category"], t["problem_id"]) for t in next_stage}
    for t in topics:
        t["selected_for_next_stage"] = (t["category"], t["problem_id"]) in next_stage_ids

    lines: list[str] = []
    lines.append("# YouTube Click Analysis")
    lines.append("")
    lines.append(f"생성일: {date.today().isoformat()}")
    lines.append("")

    lines.append("## 1. 분석 데이터 상태")
    lines.append("")
    lines.append(f"- 분석 대상 Topic: {len(topics)}개 (05단계 shortlist 기준)")
    lines.append("- 썸네일 이미지 분석: unavailable (이 프로젝트에 이미지 분석 인프라 없음)")
    lines.append("- 첫 30초 Hook 분석: unavailable (transcript 데이터 없음)")
    lines.append("- 신규 YouTube API 호출: 0건")
    lines.append("")

    lines.append("## 2. 분석 대상 Topic 10개")
    lines.append("")
    for i, t in enumerate(topics, start=1):
        lines.append(f"{i}. [{t['category']}] {t['topic_text']}")
    lines.append("")

    lines.append("## 3. Topic별 대표 Outlier")
    lines.append("")
    for t in topics:
        lines.append(f"### {t['topic_text']}")
        for v in t["representative_videos"]:
            lines.append(
                f"- ({v['evidence_quality']}) {v['title']} — {v['channel_title'] or v['channel_id']}, "
                f"{_fmt(v['outlier_ratio'])}X, https://www.youtube.com/watch?v={v['video_id']}"
            )
        lines.append("")

    lines.append("## 4. Click Driver 전체 빈도")
    lines.append("")
    all_drivers = Counter()
    for t in topics:
        all_drivers.update(t["repeated_patterns"]["driver_counts"])
    for driver, count in all_drivers.most_common():
        lines.append(f"- {driver} ({CLICK_DRIVERS.get(driver, '')}): {count}건")
    if not all_drivers:
        lines.append("- (데이터 없음)")
    lines.append("")

    lines.append("## 5. Topic별 반복 Click Pattern")
    lines.append("")
    for t in topics:
        p = t["repeated_patterns"]
        lines.append(f"### {t['topic_text']}")
        for driver, count in Counter(p["driver_counts"]).most_common():
            lines.append(f"- {count}/{p['total']}: {driver} ({CLICK_DRIVERS.get(driver, '')})")
        for device, count in Counter(p["device_counts"]).most_common(5):
            lines.append(f"- {count}/{p['total']}: device={device}")
        lines.append("")

    lines.append("## 6. 제목 패턴 분석")
    lines.append("")
    for t in topics:
        hooks = [v["title_hook"] for v in t["video_analyses"] if v["title_hook"]]
        promises = [v["title_promise"] for v in t["video_analyses"] if v["title_promise"]]
        lines.append(f"- {t['topic_text']}")
        lines.append(f"  - hook 예시: {hooks[0] if hooks else '(Gemini 미사용 - rule-based만)'}")
        lines.append(f"  - promise 예시: {promises[0] if promises else '(Gemini 미사용 - rule-based만)'}")
    lines.append("")

    lines.append("## 7. 썸네일 패턴 분석")
    lines.append("")
    lines.append("thumbnail_data_status: unavailable — 이 프로젝트에 이미지 분석 기능이 없어 새로 만들지 않고 생략함. "
                 "thumbnail_url은 DB에 저장돼 있으나 내용 분석은 불가.")
    lines.append("")

    lines.append("## 8. 제목 × 썸네일 역할 관계")
    lines.append("")
    lines.append("title_thumbnail_relationship: unclear (전 항목 — 썸네일 분석 불가로 판정 불가)")
    lines.append("")

    lines.append("## 9. 첫 30초 Hook 분석 (데이터가 있는 경우)")
    lines.append("")
    lines.append("hook_data_status: unavailable — transcript/첫 30초 데이터가 프로젝트에 없어 전 Topic 공통으로 분석 불가.")
    lines.append("")

    lines.append("## 10. Topic Candidate Score vs Click Evidence Score")
    lines.append("")
    lines.append("| Topic | Category | Topic Score | Click Score | Brand Fit |")
    lines.append("|---|---|---:|---:|---|")
    for t in topics:
        lines.append(
            f"| {t['topic_text']} | {t['category']} | {_fmt(t['topic_candidate_score'])} | "
            f"{_fmt(t['click_evidence_score'])} | {t['brand_fit']} |"
        )
    lines.append("")
    lines.append("(Combined Signal은 참고용이며 최종 제작 결정 점수로 사용하지 않습니다.)")
    lines.append("")

    lines.append("## 11. Channel Brand Fit")
    lines.append("")
    for t in topics:
        lines.append(f"- {t['topic_text']}: {t['brand_fit']}")
    lines.append("")

    lines.append("## 12. Shorts vs Long-form 차이")
    lines.append("")
    for t in topics:
        shorts = [v for v in t["representative_videos"] if v["content_type"] == "short"]
        longform = [v for v in t["representative_videos"] if v["content_type"] == "longform"]
        lines.append(f"### {t['topic_text']}")
        lines.append(f"- Long-form 대표 영상: {len(longform)}개")
        lines.append(f"- Shorts 대표 영상: {len(shorts)}개")
    lines.append("")

    lines.append("## 13. 07 단계로 넘길 후보 3~5개")
    lines.append("")
    if next_stage:
        for i, t in enumerate(next_stage, start=1):
            lines.append(
                f"{i}. [{t['category']}] {t['topic_text']} — Topic {_fmt(t['topic_candidate_score'])}, "
                f"Click {_fmt(t['click_evidence_score'])}, Brand Fit {t['brand_fit']}"
            )
            lines.append(f"   선정 이유: {t['selection_reason']}")
    else:
        lines.append("- (brand_fit='low'가 아닌 후보가 없어 선정된 항목 없음 — 임의로 채우지 않음)")
    lines.append("")

    reports_dir.mkdir(parents=True, exist_ok=True)
    out_path = reports_dir / f"click_analysis_{date.today().isoformat()}.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")

    _persist(db_path, topics, str(out_path))

    return out_path
