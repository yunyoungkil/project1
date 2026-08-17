from research.progress import (
    log_error,
    log_progress,
    log_stage_done,
    log_stage_start,
    log_warning,
    print_failure_summary,
    print_run_summary,
)


def test_log_stage_start_and_done_output(capsys):
    log_stage_start("SEARCH", "reading")
    log_stage_done("SEARCH", "queries: 13")
    out = capsys.readouterr().out
    assert "[SEARCH] 시작 - reading" in out
    assert "[SEARCH DONE] queries: 13" in out


def test_log_progress_prints_at_step_intervals(capsys):
    total = 50
    for i in range(1, total + 1):
        log_progress("PATTERNS", i, total)
    out = capsys.readouterr().out
    lines = [l for l in out.splitlines() if l.startswith("[PATTERNS]")]
    # step = max(10, 50//10) = 10 -> prints at 10,20,30,40,50
    assert lines == [f"[PATTERNS] {n}/50" for n in (10, 20, 30, 40, 50)]


def test_log_progress_always_prints_final_item_even_off_step(capsys):
    total = 23
    for i in range(1, total + 1):
        log_progress("ANALYZE", i, total)
    out = capsys.readouterr().out
    lines = [l for l in out.splitlines() if l.startswith("[ANALYZE]")]
    assert lines[-1] == "[ANALYZE] 23/23"


def test_log_progress_zero_total_does_not_crash(capsys):
    log_progress("ANALYZE", 0, 0)
    out = capsys.readouterr().out
    assert out == ""


def test_log_warning_includes_context_fields(capsys):
    log_warning("Gemini 분석 실패 (12/50)", reason="Unterminated string", fallback="rule-based", pipeline="continues")
    out = capsys.readouterr().out
    assert "[WARN] Gemini 분석 실패 (12/50)" in out
    assert "reason: Unterminated string" in out
    assert "fallback: rule-based" in out
    assert "pipeline: continues" in out


def test_log_error_goes_to_stderr(capsys):
    log_error("YouTube API 호출 실패", stage="analyze", channel_id="abc123", reason="quota exceeded")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "[ERROR] YouTube API 호출 실패" in captured.err
    assert "stage=analyze" in captured.err
    assert "channel_id=abc123" in captured.err


def test_print_run_summary_success(capsys):
    print_run_summary(
        stage_results={"Search": "PASS", "Analyze": "PASS", "Report": "PASS"},
        report_path="reports/weekly_2026-08-17.md",
        quota_used=677,
        warning_count=3,
        success=True,
    )
    out = capsys.readouterr().out
    assert "YouTube Market Research 완료" in out
    assert "Search: PASS" in out
    assert "reports/weekly_2026-08-17.md" in out
    assert "677 units" in out
    assert "Gemini fallback 3건" in out
    assert "Result:" in out and "SUCCESS" in out


def test_print_failure_summary(capsys):
    print_failure_summary(
        failed_stage="PATTERNS",
        reason="Gemini API key invalid",
        stage_results={"Search": "PASS", "Analyze": "PASS"},
    )
    captured = capsys.readouterr()
    assert captured.out == ""  # failure summary goes to stderr, not stdout
    err = captured.err
    assert "YouTube Market Research 실패" in err
    assert "Failed stage:" in err
    assert "PATTERNS" in err
    assert "Gemini API key invalid" in err
    assert "Search PASS" in err
    assert "Analyze PASS" in err
    assert "NOT CREATED" in err
    assert "FAILED" in err
