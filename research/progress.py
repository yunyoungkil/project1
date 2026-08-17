"""Terminal progress/status logging for the CLI. Purely observational -- these helpers never
influence analysis logic, they only report on it (see prompts/04). Color is applied only when
stdout is an interactive terminal; the [TAG] prefix always carries the meaning on its own so
output stays readable when colors aren't supported (or output is piped/redirected).
"""
from __future__ import annotations

import sys

_USE_COLOR = sys.stdout.isatty()

_COLOR_CODES = {
    "WARN": "\033[33m",
    "ERROR": "\033[31m",
    "DONE": "\033[32m",
}
_RESET = "\033[0m"


def _colorize(tag: str, text: str) -> str:
    code = _COLOR_CODES.get(tag)
    if not _USE_COLOR or not code:
        return text
    return f"{code}{text}{_RESET}"


def log_stage_start(stage: str, detail: str = "") -> None:
    msg = f"[{stage}] 시작" + (f" - {detail}" if detail else "")
    print(msg)


def log_stage_done(stage: str, detail: str = "") -> None:
    msg = f"[{stage} DONE]" + (f" {detail}" if detail else "")
    print(_colorize("DONE", msg))


def log_progress(stage: str, current: int, total: int) -> None:
    """Prints at most ~10 lines regardless of total size (every 10% or every 10 items,
    whichever is coarser), plus always the final item."""
    if total <= 0:
        return
    step = max(10, total // 10)
    if current != total and current % step != 0:
        return
    print(f"[{stage}] {current}/{total}")


def log_warning(message: str, **context: object) -> None:
    lines = [f"[WARN] {message}"]
    for key, value in context.items():
        lines.append(f"       {key}: {value}")
    print(_colorize("WARN", "\n".join(lines)))


def log_error(message: str, **context: object) -> None:
    lines = [f"[ERROR] {message}"]
    for key, value in context.items():
        lines.append(f"        {key}={value}")
    print(_colorize("ERROR", "\n".join(lines)), file=sys.stderr)


def print_run_summary(
    *, stage_results: dict[str, str], report_path: object, quota_used: int, warning_count: int, success: bool
) -> None:
    lines = [
        "=" * 40,
        "YouTube Market Research 완료" if success else "YouTube Market Research 실패",
        "=" * 40,
        "",
    ]
    for stage, status in stage_results.items():
        lines.append(f"{stage}: {status}")
    lines.append("")
    lines.append("Report:")
    lines.append(str(report_path) if report_path is not None else "NOT CREATED")
    lines.append("")
    lines.append("Quota used:")
    lines.append(f"{quota_used} units")
    lines.append("")
    lines.append("Warnings:")
    lines.append(f"Gemini fallback {warning_count}건")
    lines.append("")
    lines.append("Result:")
    lines.append("SUCCESS" if success else "FAILED")
    lines.append("=" * 40)
    print("\n".join(lines))


def print_failure_summary(*, failed_stage: str, reason: str, stage_results: dict[str, str]) -> None:
    lines = [
        "=" * 40,
        "YouTube Market Research 실패",
        "=" * 40,
        "",
        "Failed stage:",
        failed_stage,
        "",
        "Reason:",
        str(reason),
        "",
        "Completed stages:",
    ]
    for stage, status in stage_results.items():
        lines.append(f"{stage} {status}")
    lines.append("")
    lines.append("Report:")
    lines.append("NOT CREATED")
    lines.append("")
    lines.append("Result:")
    lines.append("FAILED")
    lines.append("=" * 40)
    print(_colorize("ERROR", "\n".join(lines)), file=sys.stderr)
