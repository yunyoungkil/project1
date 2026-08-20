"""CLI entry point: `python -m research.cli <command>` (also exposed via run_research.py)."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime

from research.analyze_pipeline import analyze_pending_videos, estimate_analyze_units
from research.analytics_client import run_oauth_flow
from research.asset_generator import (
    PRONUNCIATION_REVIEW_STATES,
    TONE_CONSISTENCY_REVIEW_STATES,
    _latest_generated_rows_for_plan,
    build_asset_generation_report,
    record_pronunciation_review,
    record_tone_consistency_review,
    select_target_plan,
)
from research.config import load_config
from research.content_pattern_analyzer import analyze_video
from research.db import connect, init_db
from research.gemini_client import GeminiClient
from research.keyword_pool import add_keyword, iter_keywords, load_pool, resolve_legacy_problem, sync_to_db
from research.my_channel import compute_topic_scores, sync_my_channel_stats
from research.outlier_detector import DEFAULT_GRADE_THRESHOLDS
from research.progress import (
    log_error,
    log_progress,
    log_stage_done,
    log_stage_start,
    log_warning,
    print_failure_summary,
    print_run_summary,
)
from research.click_analysis import build_click_analysis_report
from research.content_packages import build_content_packages_report
from research.production_blueprint import build_production_blueprint_report
from research.production_planner import build_production_plan_report
from research.render_spec import run_render_spec
from research.scene_layout import run_scene_layout
from research.script_writer import build_script_report
from research.timeline_compiler import run_timeline_compiler
from research.topic_candidates import build_topic_candidates_report
from research.tts_client import GeminiTTSClient
from research.video_director import build_video_direction_report
from research.visual_design import CANDIDATES, run_approve_visual_design, run_correct_visual_approval, run_font_family_review, run_visual_design
from research.weekly_report import build_weekly_report
from research.youtube_client import YouTubeClient
from research.youtube_search import estimate_search_units, run_category_search

# Windows consoles often default to a non-UTF-8 codepage, which mangles the Korean text
# throughout this project (titles, keyword pool, reports). Force UTF-8 output regardless of
# the host codepage.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("research.cli")


def _ensure_db(cfg):
    init_db(cfg.db_path)
    pool = load_pool(cfg.keyword_pool_path)
    sync_to_db(cfg.db_path, pool)


def _total_quota_used(db_path) -> int:
    with connect(db_path) as conn:
        row = conn.execute("SELECT COALESCE(SUM(cost_units), 0) AS total FROM api_call_log").fetchone()
    return row["total"]


def _require_youtube_client(cfg) -> YouTubeClient:
    if not cfg.youtube_api_key:
        print("YOUTUBE_API_KEY is not set in .env", file=sys.stderr)
        sys.exit(1)
    return YouTubeClient(cfg.youtube_api_key, cfg.db_path)


def _gemini_client(cfg) -> GeminiClient:
    return GeminiClient(
        cfg.gemini_api_key,
        model=cfg.get("gemini", "model", default="gemini-flash-latest"),
        timeout_seconds=cfg.get("gemini", "timeout_seconds", default=30),
    )


def _tts_client(cfg) -> GeminiTTSClient:
    return GeminiTTSClient(
        cfg.gemini_api_key,
        model=cfg.get("gemini", "tts_model", default="gemini-3.1-flash-tts-preview"),
        timeout_seconds=cfg.get("gemini", "timeout_seconds", default=30),
        max_retries=cfg.get("asset_generation", "max_retries", default=3),
    )


class _GeminiFailureCapture(logging.Handler):
    """Listens for gemini_client's own "falling back to rule-based logic" warnings so the
    PATTERNS loop can surface *which* item failed and why, without gemini_client.py needing to
    know anything about progress reporting. Purely observational."""

    def __init__(self):
        super().__init__()
        self.last_message: str | None = None

    def emit(self, record: logging.LogRecord) -> None:
        self.last_message = record.getMessage()


class _StageFailure(Exception):
    def __init__(self, stage: str, cause: Exception):
        super().__init__(str(cause))
        self.stage = stage
        self.cause = cause


def _run_stage(stage: str, fn, stage_results: dict[str, str]):
    try:
        result = fn()
        stage_results[stage] = "PASS"
        return result
    except Exception as e:  # noqa: BLE001 - re-raised as _StageFailure with stage context attached
        stage_results[stage] = "FAIL"
        log_error(f"{stage} 단계 실패", stage=stage, reason=str(e))
        raise _StageFailure(stage, e) from e


def cmd_auth(args, cfg):
    if not cfg.youtube_client_id or not cfg.youtube_client_secret:
        print("YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET must be set in .env", file=sys.stderr)
        sys.exit(1)
    print("Opening a browser to authorize YouTube Analytics access...")
    run_oauth_flow(cfg.youtube_client_id, cfg.youtube_client_secret, cfg.oauth_token_path)
    print(f"Token saved to {cfg.oauth_token_path}")


def cmd_keywords_list(args, cfg):
    pool = load_pool(cfg.keyword_pool_path)
    for kw in iter_keywords(pool):
        print(f"[{kw.category}/{kw.problem_id}] {kw.search_query}  (problem: {kw.problem_label})")


def cmd_keywords_add(args, cfg):
    using_legacy = args.problem is not None
    using_new = args.problem_id is not None or args.problem_label is not None

    if using_legacy and using_new:
        print("Use either --problem OR --problem-id/--problem-label, not both", file=sys.stderr)
        sys.exit(1)

    if using_legacy:
        # Backward-compat path: old scripts only ever passed a natural-language --problem.
        problem_id, problem_label = resolve_legacy_problem(cfg.keyword_pool_path, args.category, args.problem)
    elif args.problem_id and args.problem_label:
        problem_id, problem_label = args.problem_id, args.problem_label
    else:
        print("Provide --problem-id and --problem-label (or the legacy --problem)", file=sys.stderr)
        sys.exit(1)

    add_keyword(cfg.keyword_pool_path, args.category, problem_id, problem_label, args.query)
    print(f"Added '{args.query}' to category '{args.category}' / problem '{problem_id}'")


def cmd_search(args, cfg):
    log_stage_start("SEARCH", args.category)
    yt = _require_youtube_client(cfg)
    cache_ttl_hours = cfg.get("search", "cache_ttl_hours", default=168)
    estimated = estimate_search_units(
        cfg.db_path, cfg.keyword_pool_path, args.category,
        cache_ttl_hours=cache_ttl_hours, query_limit=args.query_limit,
    )
    print(f"[quota] estimated {estimated} unit(s) for this search")
    result = run_category_search(
        cfg.db_path,
        cfg.keyword_pool_path,
        yt,
        args.category,
        max_results_per_query=cfg.get("search", "max_results_per_query", default=15),
        cache_ttl_hours=cache_ttl_hours,
        region_code=cfg.get("search", "region_code", default="KR"),
        relevance_language=cfg.get("search", "relevance_language", default="ko"),
        query_limit=args.query_limit,
        short_max_seconds=cfg.get("content_type", "short_max_seconds", default=60),
        ambiguous_max_seconds=cfg.get("content_type", "ambiguous_max_seconds", default=180),
    )
    print(result)
    log_stage_done(
        "SEARCH",
        f"{result['category']}\n  queries: {result['keywords_total']}\n  cached: {result['queries_cached']}"
        f"\n  api calls: {result['queries_run']}\n  new videos: {result['new_video_count']}",
    )
    return result


def cmd_analyze(args, cfg):
    log_stage_start("ANALYZE")
    yt = _require_youtube_client(cfg)
    estimated = estimate_analyze_units(cfg.db_path, cache_ttl_hours=cfg.get("baseline", "cache_ttl_hours", default=168))
    print(f"[quota] estimated {estimated} unit(s) for this analyze run")
    result = analyze_pending_videos(
        cfg.db_path,
        yt,
        baseline_cfg=cfg.get("baseline", default={}),
        content_type_cfg=cfg.get("content_type", default={}),
        grade_thresholds=cfg.get("outlier", "thresholds", default=DEFAULT_GRADE_THRESHOLDS),
        score_weights=cfg.get("opportunity_score", "weights", default={}),
        score_caps=cfg.get("opportunity_score", "caps", default={}),
        neutral_score=cfg.get("opportunity_score", "neutral_score_when_missing", default=50),
        min_grade_to_store=cfg.get("outlier", "min_grade_to_store", default="notable"),
        on_progress=lambda i, total: log_progress("ANALYZE", i, total),
    )
    print(result)
    log_stage_done(
        "ANALYZE",
        f"total={result['total_candidates']} processed={result['processed']}"
        f" unknown_type={result['skipped_unknown_type']} no_baseline={result['skipped_no_baseline']}"
        f" below_threshold={result['skipped_below_threshold']}",
    )
    return result


TOP_VIDEO_QUERY = """
    SELECT v.title, v.video_id, v.thumbnail_url, c.title AS channel_title, v.published_at,
           v.view_count, c.subscriber_count, os.channel_median_views, os.subscriber_ratio,
           os.outlier_ratio, os.views_per_day, os.opportunity_score, os.outlier_grade,
           v.matched_keyword, v.problem_category
    FROM outlier_scores os
    JOIN videos v ON v.video_id = os.video_id
    LEFT JOIN channels c ON c.channel_id = v.channel_id
    WHERE os.outlier_grade IS NOT NULL AND os.outlier_grade != 'normal'
    ORDER BY os.opportunity_score DESC
    LIMIT ?
"""


def cmd_top(args, cfg):
    with connect(cfg.db_path) as conn:
        rows = conn.execute(TOP_VIDEO_QUERY, (args.limit,)).fetchall()
    for i, r in enumerate(rows, start=1):
        print(f"{i}. {r['title']}")
        print(f"   channel: {r['channel_title']}")
        print(f"   video_url: https://www.youtube.com/watch?v={r['video_id']}")
        print(f"   thumbnail: {r['thumbnail_url']}")
        print(f"   published_at: {r['published_at']}")
        print(f"   views: {r['view_count']}  subscriber_count: {r['subscriber_count']}")
        print(f"   channel_median_views: {_fmt1(r['channel_median_views'])}")
        print(f"   subscriber_ratio: {_fmt1(r['subscriber_ratio'])}  outlier_ratio: {_fmt1(r['outlier_ratio'])}X"
              f" ({r['outlier_grade']})  views_per_day: {_fmt1(r['views_per_day'])}")
        print(f"   opportunity_score: {_fmt1(r['opportunity_score'])}/100")
        print(f"   matched_keyword: {r['matched_keyword']}  problem_category: {r['problem_category']}")
        print()


def _fmt1(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)


def cmd_patterns(args, cfg):
    gemini = _gemini_client(cfg)
    with connect(cfg.db_path) as conn:
        rows = conn.execute(
            """
            SELECT v.video_id, v.title FROM outlier_scores os
            JOIN videos v ON v.video_id = os.video_id
            WHERE os.outlier_grade IS NOT NULL AND os.outlier_grade != 'normal'
            ORDER BY os.opportunity_score DESC
            LIMIT 50
            """
        ).fetchall()

    total = len(rows)
    log_stage_start("PATTERNS", f"{total}개 영상 제목 패턴 분석")

    # Listens for gemini_client's own logging output so a failed call can be reported as
    # "[WARN] ... (i/total)" without content_pattern_analyzer.py needing to know about progress.
    failure_capture = _GeminiFailureCapture()
    gemini_logger = logging.getLogger("research.gemini_client")
    gemini_logger.addHandler(failure_capture)

    gemini_success = 0
    fallback = 0
    try:
        for i, r in enumerate(rows, start=1):
            failure_capture.last_message = None
            pattern = analyze_video(
                r["video_id"], r["title"], gemini, max_output_tokens=cfg.get("gemini", "max_output_tokens", default=1024)
            )

            if gemini.available and failure_capture.last_message:
                fallback += 1
                log_warning(
                    f"Gemini 분석 실패 ({i}/{total})",
                    reason=failure_capture.last_message,
                    fallback="rule-based",
                    pipeline="continues",
                )
            elif pattern.source == "gemini":
                gemini_success += 1

            with connect(cfg.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO content_patterns (video_id, viewer_problem, title_pattern, hook, promise,
                        emotion, beginner_appeal, primary_archetype, secondary_archetype, is_question,
                        is_negative, is_reason, is_result, is_number, is_fear_avoidance, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(video_id) DO UPDATE SET
                        viewer_problem=excluded.viewer_problem, title_pattern=excluded.title_pattern,
                        hook=excluded.hook, promise=excluded.promise, emotion=excluded.emotion,
                        beginner_appeal=excluded.beginner_appeal, primary_archetype=excluded.primary_archetype,
                        secondary_archetype=excluded.secondary_archetype, is_question=excluded.is_question,
                        is_negative=excluded.is_negative, is_reason=excluded.is_reason,
                        is_result=excluded.is_result, is_number=excluded.is_number,
                        is_fear_avoidance=excluded.is_fear_avoidance, source=excluded.source,
                        computed_at=datetime('now')
                    """,
                    (
                        r["video_id"], pattern.viewer_problem, pattern.title_pattern, pattern.hook,
                        pattern.promise, pattern.emotion, pattern.beginner_appeal,
                        pattern.primary_archetype, pattern.secondary_archetype,
                        pattern.flags.is_question, pattern.flags.is_negative,
                        pattern.flags.is_reason, pattern.flags.is_result, pattern.flags.is_number,
                        pattern.flags.is_fear_avoidance, pattern.source,
                    ),
                )
            log_progress("PATTERNS", i, total)
    finally:
        gemini_logger.removeHandler(failure_capture)

    log_stage_done("PATTERNS", f"total={total} gemini_success={gemini_success} fallback={fallback}")

    log_stage_start("CHANNEL", "내 채널 Analytics 동기화")
    yt = _require_youtube_client(cfg)
    my_stats = sync_my_channel_stats(
        cfg.db_path, cfg.youtube_client_id, cfg.youtube_client_secret, cfg.oauth_token_path, yt,
        lookback_days=cfg.get("my_channel", "lookback_days", default=90),
        traffic_source_top_n=cfg.get("my_channel", "traffic_source_top_n", default=20),
    )
    print("my_channel_stats:", my_stats)
    log_stage_done("CHANNEL", str(my_stats))

    log_stage_start("TOPIC", "topic score 계산")
    topics = compute_topic_scores(
        cfg.db_path,
        cfg.keyword_pool_path,
        market_demand_top_n=cfg.get("topic_score", "market_demand_top_n", default=5),
        market_demand_weights=cfg.get("topic_score", "market_demand_weights", default=None),
        outlier_count_cap=cfg.get("topic_score", "outlier_count_cap", default=10),
        fit_neutral_score=cfg.get("topic_score", "fit_neutral_score", default=50),
        min_candidate_videos=cfg.get("topic_score", "min_candidate_videos", default=10),
    )
    for t in topics:
        print(t)
    log_stage_done("TOPIC", f"{len(topics)}개 카테고리")

    return {
        "patterns_total": total,
        "gemini_success": gemini_success,
        "fallback": fallback,
        "my_channel_stats": my_stats,
        "topics": topics,
    }


def cmd_report_weekly(args, cfg):
    log_stage_start("REPORT", "주간 리포트 생성")
    gemini = _gemini_client(cfg)
    path = build_weekly_report(
        cfg.db_path,
        cfg.reports_dir,
        gemini,
        cfg.get("channel", default={}),
        cfg.keyword_pool_path,
        max_output_tokens=cfg.get("gemini", "max_output_tokens", default=1024),
    )
    print(f"Report written to {path}")
    log_stage_done("REPORT", str(path))
    return path


def cmd_topics(args, cfg):
    log_stage_start("TOPICS", "viewer problem 기반 topic candidate 생성 (신규 API 호출 없음)")
    gemini = _gemini_client(cfg)
    path = build_topic_candidates_report(
        cfg.db_path,
        cfg.reports_dir,
        gemini,
        cfg.keyword_pool_path,
        top_n=args.top,
        fit_neutral_score=cfg.get("topic_score", "fit_neutral_score", default=50),
        max_output_tokens=cfg.get("gemini", "max_output_tokens", default=1024),
    )
    print(f"Topic candidates report written to {path}")
    log_stage_done("TOPICS", str(path))
    return path


def cmd_clicks(args, cfg):
    log_stage_start("CLICKS", "topic candidate의 대표 outlier 클릭 이유 분석 (신규 API 호출 없음)")
    gemini = _gemini_client(cfg)
    path = build_click_analysis_report(
        cfg.db_path,
        cfg.reports_dir,
        gemini,
        top_n=args.top,
        max_output_tokens=cfg.get("gemini", "max_output_tokens", default=1024),
    )
    print(f"Click analysis report written to {path}")
    log_stage_done("CLICKS", str(path))
    return path


def cmd_packages(args, cfg):
    log_stage_start("PACKAGES", "06 후보의 제목x썸네일 패키지 생성 (신규 API 호출 없음)")
    gemini = _gemini_client(cfg)
    path = build_content_packages_report(
        cfg.db_path,
        cfg.reports_dir,
        gemini,
        cfg.get("channel", default={}),
        top_n=args.top,
        max_output_tokens=cfg.get("gemini", "max_output_tokens_packages", default=3000),
    )
    print(f"Content packages report written to {path}")
    log_stage_done("PACKAGES", str(path))
    return path


def cmd_blueprint(args, cfg):
    log_stage_start("BLUEPRINT", "07 선정 Package의 영상 제작 설계 생성 (신규 API 호출 없음)")
    gemini = _gemini_client(cfg)
    path = build_production_blueprint_report(
        cfg.db_path,
        cfg.reports_dir,
        gemini,
        cfg.get("channel", default={}),
        package_id=args.package_id,
        max_output_tokens=cfg.get("gemini", "max_output_tokens_blueprint", default=6000),
    )
    print(f"Production blueprint report written to {path}")
    log_stage_done("BLUEPRINT", str(path))
    return path


def cmd_script(args, cfg):
    log_stage_start("SCRIPT", "08 Blueprint의 촬영용 대본 생성 (신규 API 호출 없음)")
    gemini = _gemini_client(cfg)
    path = build_script_report(
        cfg.db_path,
        cfg.reports_dir,
        gemini,
        cfg.get("channel", default={}),
        blueprint_id=args.blueprint_id,
        max_output_tokens=cfg.get("gemini", "max_output_tokens_script", default=8000),
    )
    print(f"Script report written to {path}")
    log_stage_done("SCRIPT", str(path))
    return path


def cmd_direction(args, cfg):
    log_stage_start("DIRECTION", "09 Content Script의 영상 포맷/연출 방향 결정 (신규 API 호출 없음)")
    gemini = _gemini_client(cfg)
    transcript_segments = None
    if args.transcript_json:
        with open(args.transcript_json, "r", encoding="utf-8") as f:
            transcript_segments = json.load(f)
    path = build_video_direction_report(
        cfg.db_path,
        cfg.reports_dir,
        gemini,
        cfg.get("channel", default={}),
        cfg.get("clip_score", default={}),
        script_id=args.script_id,
        transcript_segments=transcript_segments,
        max_output_tokens=cfg.get("gemini", "max_output_tokens_direction", default=6000),
    )
    print(f"Video direction report written to {path}")
    log_stage_done("DIRECTION", str(path))
    return path


def cmd_production_plan(args, cfg):
    log_stage_start("PRODUCTION-PLAN", "10 Video Direction의 제작 명세 컴파일 (신규 API 호출 없음)")
    path = build_production_plan_report(
        cfg.db_path,
        cfg.reports_dir,
        direction_id=args.direction_id,
        clip_config=cfg.get("clip_score", default={}),
        complexity_config=cfg.get("production_planner", "complexity_thresholds", default={}),
    )
    print(f"Production plan report written to {path}")
    log_stage_done("PRODUCTION-PLAN", str(path))
    return path


def cmd_assets(args, cfg):
    if args.dry_run:
        mode = "DRY_RUN"
    elif args.sample:
        mode = "SAMPLE"
    else:
        mode = "FULL"
    log_stage_start("ASSETS", f"11 Production Plan의 실제 TTS Asset 생성/검증 ({mode})")
    path = build_asset_generation_report(
        cfg.db_path, cfg.reports_dir, cfg.assets_dir, _tts_client(cfg),
        plan_id=args.plan_id, mode=mode,
        tts_model=cfg.get("gemini", "tts_model", default="gemini-3.1-flash-tts-preview"),
        max_segment_seconds=cfg.get("asset_generation", "max_segment_seconds", default=12),
        primary_en_native_strategy=cfg.get("asset_generation", "primary_en_native_strategy", default="DIRECT_WORD"),
        fallback_en_native_strategy=cfg.get("asset_generation", "fallback_en_native_strategy", default="CONTEXTUAL_WORD"),
        default_blending_strategy=cfg.get("asset_generation", "default_blending_strategy", default="DIRECT_SEQUENCE"),
    )
    print(f"Asset generation report written to {path}")
    log_stage_done("ASSETS", str(path))
    return path


def cmd_assets_review(args, cfg):
    # 12-1 section 24: every CLI command in this project runs non-interactively to completion --
    # none read from stdin. An [A]pprove/[R]eject prompt would be the first interactive command in
    # the project, so this stays a plain listing; approving/rejecting is a direct DB update against
    # generated_assets.metadata_json.pronunciation_review (documented below), not a new workflow.
    plan_row = select_target_plan(cfg.db_path, plan_id=args.plan_id)
    if plan_row is None:
        print("No production_plans row found.", file=sys.stderr)
        return
    rows = _latest_generated_rows_for_plan(cfg.db_path, plan_row["id"])
    priority_rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    pending = []
    for r in rows:
        try:
            metadata = json.loads(r.get("metadata_json") or "{}")
        except (TypeError, ValueError):
            metadata = {}
        if metadata.get("pronunciation_review") == "PENDING":
            pending.append((r, metadata))
    pending.sort(key=lambda item: priority_rank.get(item[1].get("review_priority"), 9))

    print(f"production_plans.id: {plan_row['id']}  PENDING review: {len(pending)}")
    for r, metadata in pending:
        print(
            f"[{metadata.get('review_priority')}] {r['asset_id']} mode={r['speech_mode']} "
            f"voice={r['voice_name']} file={r['file_path']} duration_ms={r['duration_ms']}"
        )
    print(
        "\nTo approve/reject, update generated_assets.metadata_json.pronunciation_review "
        "(\"APPROVED\" / \"REJECTED\" / \"REGENERATE_REQUIRED\") for the asset_id directly in the DB, "
        "or pass --set ASSET_ID=STATUS (repeatable) to this command."
    )

    # 12-2 section 16: non-interactive, scriptable recording of an already-made human verdict --
    # not an interactive [A]pprove/[R]eject prompt, consistent with section 24's CLI philosophy.
    for entry in getattr(args, "set", None) or []:
        if "=" not in entry:
            print(f"Skipping invalid --set entry (expected ASSET_ID=STATUS): {entry}", file=sys.stderr)
            continue
        asset_id, status = entry.split("=", 1)
        asset_id, status = asset_id.strip(), status.strip().upper()
        if status not in PRONUNCIATION_REVIEW_STATES:
            print(f"Skipping --set {entry}: invalid status (must be one of {sorted(PRONUNCIATION_REVIEW_STATES)})", file=sys.stderr)
            continue
        updated = record_pronunciation_review(cfg.db_path, plan_row["id"], asset_id, status)
        print(f"Recorded {asset_id} -> {status} ({updated} row(s) updated)")

    # 12-3 section 20: tone_consistency_review is a separate axis from pronunciation_review --
    # "pronunciation is correct but tone doesn't match" needs its own recordable verdict.
    for entry in getattr(args, "set_tone", None) or []:
        if "=" not in entry:
            print(f"Skipping invalid --set-tone entry (expected ASSET_ID=STATUS): {entry}", file=sys.stderr)
            continue
        asset_id, status = entry.split("=", 1)
        asset_id, status = asset_id.strip(), status.strip().upper()
        if status not in TONE_CONSISTENCY_REVIEW_STATES:
            print(f"Skipping --set-tone {entry}: invalid status (must be one of {sorted(TONE_CONSISTENCY_REVIEW_STATES)})", file=sys.stderr)
            continue
        updated = record_tone_consistency_review(cfg.db_path, plan_row["id"], asset_id, status)
        print(f"Recorded tone_consistency_review {asset_id} -> {status} ({updated} row(s) updated)")


def cmd_render_spec(args, cfg):
    log_stage_start("RENDER-SPEC", "12-9 canonical Ready for Rendering을 기준으로 Renderer-neutral Render Specification 컴파일 (신규 API 호출 없음)")
    result = run_render_spec(cfg.db_path, cfg.assets_dir, cfg.reports_dir, plan_id=args.plan_id)
    if result["blocked"]:
        print("Renderer Entry Gate: NO", file=sys.stderr)
        for reason in result["reasons"]:
            print(f"- {reason}", file=sys.stderr)
        print(f"Report written to {result['report_path']}")
        log_stage_done("RENDER-SPEC", "blocked -- see report")
        return result["report_path"]
    print(f"render_spec.json written to {result['json_path']}")
    print(f"Report written to {result['report_path']}")
    print(f"Ready for Timeline Compilation: {'YES' if result['ready_for_timeline_compilation'] else 'NO'}")
    log_stage_done("RENDER-SPEC", str(result["report_path"]))
    return result["report_path"]


def cmd_render_timeline(args, cfg):
    log_stage_start("RENDER-TIMELINE", "13-1 Render Specification을 결정론적 밀리초 Timeline으로 컴파일 (신규 API 호출 없음)")
    result = run_timeline_compiler(cfg.db_path, cfg.assets_dir, cfg.reports_dir, plan_id=args.plan_id)
    if not result["pass"]:
        print("Timeline Entry Gate: NO", file=sys.stderr)
        print(f"- {result['reason']}", file=sys.stderr)
        print(f"Report written to {result['report_path']}")
        log_stage_done("RENDER-TIMELINE", "blocked -- see report")
        return result["report_path"]
    print(f"timeline.json written to {result['json_path']}")
    print(f"Report written to {result['report_path']}")
    print(f"Ready for Scene/Layout: {'YES' if result['ready_for_scene_layout'] else 'NO'}")
    log_stage_done("RENDER-TIMELINE", str(result["report_path"]))
    return result["report_path"]


def cmd_render_layout(args, cfg):
    log_stage_start("RENDER-LAYOUT", "13-2 Timeline을 Renderer-neutral Scene/Layout Model로 컴파일 (신규 API 호출 없음)")
    result = run_scene_layout(cfg.db_path, cfg.assets_dir, cfg.reports_dir, plan_id=args.plan_id)
    if not result["pass"]:
        print("Scene/Layout Entry Gate: NO", file=sys.stderr)
        print(f"- {result['reason']}", file=sys.stderr)
        print(f"Report written to {result['report_path']}")
        log_stage_done("RENDER-LAYOUT", "blocked -- see report")
        return result["report_path"]
    print(f"scene_layout.json written to {result['json_path']}")
    print(f"Report written to {result['report_path']}")
    print(f"Ready for Visual Design: {'YES' if result['ready_for_visual_design'] else 'NO'}")
    log_stage_done("RENDER-LAYOUT", str(result["report_path"]))
    return result["report_path"]


def cmd_render_visual_design(args, cfg):
    log_stage_start("RENDER-VISUAL-DESIGN", "13-3 Scene Layout에 Renderer-neutral Visual Design System을 결합하고 Prototype을 생성 (신규 API 호출 없음)")
    result = run_visual_design(cfg.db_path, cfg.assets_dir, cfg.reports_dir, plan_id=args.plan_id)
    if not result["pass"]:
        print("Visual Design Entry Gate: NO", file=sys.stderr)
        print(f"- {result['reason']}", file=sys.stderr)
        print(f"Report written to {result['report_path']}")
        log_stage_done("RENDER-VISUAL-DESIGN", "blocked -- see report")
        return result["report_path"]
    print(f"visual_design.json written to {result['json_path']}")
    print(f"Prototypes written to {result['prototype_dir']} ({result['prototype_file_count']} files)")
    print(f"Report written to {result['report_path']}")
    print(f"Ready for Visual Prototype Review: {'YES' if result['ready_for_visual_prototype_review'] else 'NO'}")
    print(f"Human Visual Review: {result['human_visual_review_status']}")
    print(f"Approved Visual Profile: {'YES' if result['approved_visual_profile'] else 'NO'}")
    log_stage_done("RENDER-VISUAL-DESIGN", str(result["report_path"]))
    return result["report_path"]


def cmd_approve_visual_design(args, cfg):
    log_stage_start("APPROVE-VISUAL-DESIGN", "13-4B Prototype에 대한 Candidate Selection을 기록 (Full Profile 승인 아님, 신규 API 호출 없음)")
    result = run_approve_visual_design(cfg.db_path, cfg.assets_dir, cfg.reports_dir, plan_id=args.plan_id, candidate=args.candidate)
    if not result["pass"]:
        print("Approve Visual Design: NO", file=sys.stderr)
        print(f"- {result['reason']}", file=sys.stderr)
        log_stage_done("APPROVE-VISUAL-DESIGN", "blocked")
        return None
    print(f"approved_visual_profile.json written to {result['json_path']}")
    print(f"Report written to {result['report_path']}")
    print(f"Candidate selection status: {result['candidate_selection']['candidate_selection_status']}")
    print(f"Approved categories: {result['category_approvals']['approved_category_count']}/{result['category_approvals']['total_category_count']}")
    print(f"Ready for Final Renderer Binding: {'YES' if result['ready_for_final_renderer_binding'] else 'NO'}")
    log_stage_done("APPROVE-VISUAL-DESIGN", str(result["report_path"]))
    return result["report_path"]


def cmd_correct_visual_approval(args, cfg):
    log_stage_start("CORRECT-VISUAL-APPROVAL", "잘못 기록된 Visual Approval Source of Truth를 이력 보존하며 교정 (신규 API 호출 없음)")
    result = run_correct_visual_approval(
        cfg.db_path, cfg.assets_dir, cfg.reports_dir, plan_id=args.plan_id,
        selected_candidate=args.candidate, corrects_record_id=args.corrects_id,
    )
    if not result["pass"]:
        print("Correct Visual Approval: NO", file=sys.stderr)
        print(f"- {result['reason']}", file=sys.stderr)
        log_stage_done("CORRECT-VISUAL-APPROVAL", "blocked")
        return None
    print(f"approved_visual_profile.json written to {result['json_path']}")
    print(f"Report written to {result['report_path']}")
    print(f"Canonical candidate: {result['selected_candidate']} (corrects record id={result['corrects_record_id']}, history preserved)")
    print(f"Manifest revision corrected: {'YES' if result['manifest_corrected'] else 'NO'}")
    print(f"Unresolved mandatory categories: {result['unresolved_mandatory_categories'] or 'NONE'}")
    print(f"Ready for Final Renderer Binding: {'YES' if result['ready_for_final_renderer_binding'] else 'NO'}")
    log_stage_done("CORRECT-VISUAL-APPROVAL", str(result["report_path"]))
    return result["report_path"]


def cmd_review_font_family(args, cfg):
    log_stage_start("REVIEW-FONT-FAMILY", "CLEAN_DARK_FOCUS Font Family 비교 Prototype 생성 (신규 API 호출 없음, DB 미기록)")
    result = run_font_family_review(cfg.db_path, cfg.assets_dir, cfg.reports_dir, plan_id=args.plan_id)
    if not result["pass"]:
        print("Review Font Family: NO", file=sys.stderr)
        print(f"- {result['reason']}", file=sys.stderr)
        log_stage_done("REVIEW-FONT-FAMILY", "blocked")
        return None
    print(f"Font review files written to {result['review_dir']} ({result['file_count']} files)")
    print(f"Report written to {result['report_path']}")
    print(f"Review first: {result['review_dir'] / 'index.html'}")
    log_stage_done("REVIEW-FONT-FAMILY", str(result["report_path"]))
    return result["report_path"]


def cmd_run_scheduled(args, cfg):
    weekday = datetime.now().strftime("%A").lower()
    task = cfg.get("schedule", weekday)
    if not task:
        print(f"No scheduled task for {weekday}")
        return
    print(f"Running scheduled task for {weekday}: {task}")
    if task == "report":
        cmd_analyze(args, cfg)
        cmd_patterns(args, cfg)
        cmd_report_weekly(args, cfg)
    else:
        args.category = task
        args.query_limit = None
        cmd_search(args, cfg)


def cmd_run_all(args, cfg):
    log_stage_start("START", "전체 파이프라인 실행")
    stage_results: dict[str, str] = {}
    quota_start = _total_quota_used(cfg.db_path)
    report_path = None

    def _search_all():
        pool = load_pool(cfg.keyword_pool_path)
        for category in pool:
            args.category = category
            cmd_search(args, cfg)

    try:
        _run_stage("Search", _search_all, stage_results)
        _run_stage("Analyze", lambda: cmd_analyze(args, cfg), stage_results)
        patterns_result = _run_stage("Patterns", lambda: cmd_patterns(args, cfg), stage_results)
        # Channel sync + topic score run inside cmd_patterns (see [CHANNEL]/[TOPIC] stage logs
        # above) -- they succeeded if Patterns did, since any failure there would already have
        # raised out of cmd_patterns and been caught as a Patterns failure.
        stage_results["Channel Sync"] = "PASS"
        stage_results["Topic Score"] = "PASS"
        report_path = _run_stage("Report", lambda: cmd_report_weekly(args, cfg), stage_results)
    except _StageFailure as failure:
        print_failure_summary(failed_stage=failure.stage.upper(), reason=str(failure.cause), stage_results=stage_results)
        raise failure.cause from None

    fallback_count = (patterns_result or {}).get("fallback", 0)
    quota_used = _total_quota_used(cfg.db_path) - quota_start
    log_stage_done("DONE", "전체 파이프라인 완료")
    print_run_summary(
        stage_results=stage_results,
        report_path=report_path,
        quota_used=quota_used,
        warning_count=fallback_count,
        success=True,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="research")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("auth", help="One-time OAuth consent for YouTube Analytics").set_defaults(func=cmd_auth)

    kw = sub.add_parser("keywords", help="Manage the keyword pool")
    kw_sub = kw.add_subparsers(dest="keywords_command", required=True)
    kw_sub.add_parser("list").set_defaults(func=cmd_keywords_list)
    kw_add = kw_sub.add_parser("add")
    kw_add.add_argument("--category", required=True)
    kw_add.add_argument("--problem-id", default=None, help="Short stable id, e.g. 'word_stress'")
    kw_add.add_argument("--problem-label", default=None, help="Natural-language viewer problem")
    kw_add.add_argument("--problem", default=None, help="Deprecated alias for --problem-label; resolves/generates a problem_id automatically")
    kw_add.add_argument("--query", required=True)
    kw_add.set_defaults(func=cmd_keywords_add)

    search = sub.add_parser("search", help="Search a category and collect videos")
    search.add_argument("--category", required=True)
    search.add_argument("--query-limit", type=int, default=None, help="Limit number of queries run (for small test runs)")
    search.set_defaults(func=cmd_search)

    sub.add_parser("analyze", help="Compute baselines, outlier and opportunity scores").set_defaults(func=cmd_analyze)

    top = sub.add_parser("top", help="Show top outlier videos")
    top.add_argument("--limit", type=int, default=20)
    top.set_defaults(func=cmd_top)

    sub.add_parser("patterns", help="Analyze title patterns and compute topic scores").set_defaults(func=cmd_patterns)

    report = sub.add_parser("report", help="Generate a report")
    report_sub = report.add_subparsers(dest="report_command", required=True)
    report_sub.add_parser("weekly").set_defaults(func=cmd_report_weekly)

    topics = sub.add_parser("topics", help="Generate ranked topic candidates from viewer problems (no new API calls)")
    topics.add_argument("--top", type=int, default=20)
    topics.set_defaults(func=cmd_topics)

    clicks = sub.add_parser("clicks", help="Analyze why the shortlisted topics' outlier videos got clicked (no new API calls)")
    clicks.add_argument("--top", type=int, default=10)
    clicks.set_defaults(func=cmd_clicks)

    packages = sub.add_parser("packages", help="Generate title x thumbnail packages for the 06-selected topics (no new API calls)")
    packages.add_argument("--top", type=int, default=10)
    packages.set_defaults(func=cmd_packages)

    blueprint = sub.add_parser("blueprint", help="Generate a production blueprint for the 07-selected package (no new API calls)")
    blueprint.add_argument("--package-id", type=int, default=None, help="Use a specific content_packages id instead of the top selected_for_production package")
    blueprint.set_defaults(func=cmd_blueprint)

    script = sub.add_parser("script", help="Generate a shootable script for the 08-selected blueprint (no new API calls)")
    script.add_argument("--blueprint-id", type=int, default=None, help="Use a specific production_blueprints id instead of the latest ready_for_script blueprint")
    script.set_defaults(func=cmd_script)

    direction = sub.add_parser("direction", help="Decide the video format and per-block direction for the 09-selected Content Script (no new API calls)")
    direction.add_argument("--script-id", type=int, default=None, help="Use a specific video_scripts id instead of the latest ready_for_direction script")
    direction.add_argument("--transcript-json", type=str, default=None, help="Path to a JSON file of transcript segments ([{start,end,text,audio_quality?,source_ref?}, ...]) for the Source Clip Analyzer; omit if no source video is available")
    direction.set_defaults(func=cmd_direction)

    production_plan = sub.add_parser("production-plan", help="Compile the 10-selected Video Direction into a Production Plan (no new API calls)")
    production_plan.add_argument("--direction-id", type=int, default=None, help="Use a specific video_directions id instead of the latest ready_for_production_planning direction")
    production_plan.set_defaults(func=cmd_production_plan)

    assets = sub.add_parser("assets", help="Generate and validate real Gemini TTS audio assets for the 11-selected Production Plan")
    assets.add_argument("--plan-id", type=int, default=None, help="Use a specific production_plans id instead of the latest ready_for_asset_generation plan")
    assets.add_argument("--dry-run", action="store_true", help="Count planned assets and expected API calls without calling Gemini TTS")
    assets.add_argument("--sample", action="store_true", help="Generate the 12-1 Sample Matrix (KO_NARRATION short+segmented-long, EN_NATIVE across two words, isolated phonemes, both blending strategies) via real Gemini TTS calls")
    assets.set_defaults(func=cmd_assets)

    assets_review = sub.add_parser("assets-review", help="List generated assets pending human pronunciation review (non-interactive)")
    assets_review.add_argument("--plan-id", type=int, default=None, help="Use a specific production_plans id instead of the latest ready_for_asset_generation plan")
    assets_review.add_argument("--set", action="append", metavar="ASSET_ID=STATUS", help="Record an already-made human pronunciation review verdict (repeatable), e.g. --set SP007=APPROVED")
    assets_review.add_argument("--set-tone", action="append", metavar="ASSET_ID=STATUS", help="Record an already-made human tone_consistency review verdict (repeatable), e.g. --set-tone SP029::CONTEXTUAL_WORD=REJECTED")
    assets_review.set_defaults(func=cmd_assets_review)

    render_spec = sub.add_parser("render-spec", help="Compile the 12-ready Production Plan into a Renderer-neutral Render Specification (no new API calls)")
    render_spec.add_argument("--plan-id", type=int, default=None, help="Use a specific production_plans id instead of the latest ready plan")
    render_spec.set_defaults(func=cmd_render_spec)

    render_timeline = sub.add_parser("render-timeline", help="Compile a Render Specification into a deterministic millisecond Timeline (no new API calls)")
    render_timeline.add_argument("--plan-id", type=int, default=None, help="Use a specific production_plans id instead of the latest ready plan")
    render_timeline.set_defaults(func=cmd_render_timeline)

    render_layout = sub.add_parser("render-layout", help="Compile a Timeline into a Renderer-neutral Scene/Layout Model (no new API calls)")
    render_layout.add_argument("--plan-id", type=int, default=None, help="Use a specific production_plans id instead of the latest ready plan")
    render_layout.set_defaults(func=cmd_render_layout)

    render_visual_design = sub.add_parser("render-visual-design", help="Bind a Renderer-neutral Visual Design System onto a Scene Layout and generate a static HTML Prototype (no new API calls)")
    render_visual_design.add_argument("--plan-id", type=int, default=None, help="Use a specific production_plans id instead of the latest ready plan")
    render_visual_design.set_defaults(func=cmd_render_visual_design)

    approve_visual_design = sub.add_parser("approve-visual-design", help="Record a real Human Visual Review decision for a Prototype candidate (no new API calls)")
    approve_visual_design.add_argument("--plan-id", type=int, default=None, help="Use a specific production_plans id instead of the latest ready plan")
    approve_visual_design.add_argument("--candidate", required=True, choices=list(CANDIDATES), help="The Prototype candidate a human has actually reviewed and approved")
    approve_visual_design.set_defaults(func=cmd_approve_visual_design)

    correct_visual_approval = sub.add_parser("correct-visual-approval", help="Correct a misrecorded Visual Approval Source of Truth, preserving history (no new API calls)")
    correct_visual_approval.add_argument("--plan-id", type=int, default=None, help="Use a specific production_plans id instead of the latest ready plan")
    correct_visual_approval.add_argument("--candidate", default="CLEAN_DARK_FOCUS", choices=list(CANDIDATES), help="The candidate actually selected by Human Review")
    correct_visual_approval.add_argument("--corrects-id", type=int, default=2, dest="corrects_id", help="The visual_design_specs row id being superseded (preserved, never modified)")
    correct_visual_approval.set_defaults(func=cmd_correct_visual_approval)

    review_font_family = sub.add_parser("review-font-family", help="Generate a Font Family comparison Prototype for CLEAN_DARK_FOCUS (no new API calls, no DB writes)")
    review_font_family.add_argument("--plan-id", type=int, default=None, help="Use a specific production_plans id instead of the latest ready plan")
    review_font_family.set_defaults(func=cmd_review_font_family)

    sub.add_parser("run-scheduled", help="Run today's scheduled task from config").set_defaults(func=cmd_run_scheduled)

    run_all = sub.add_parser("run-all", help="Run the full pipeline for all categories")
    run_all.add_argument("--query-limit", type=int, default=None)
    run_all.set_defaults(func=cmd_run_all)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    cfg = load_config()
    _ensure_db(cfg)
    quota_before = _total_quota_used(cfg.db_path)
    args.func(args, cfg)
    quota_used = _total_quota_used(cfg.db_path) - quota_before
    print(f"[quota] this run used {quota_used} unit(s)")


if __name__ == "__main__":
    main()
