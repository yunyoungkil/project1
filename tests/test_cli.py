import logging

import pytest
import yaml

import research.cli as cli
from research.cli import build_parser, cmd_keywords_add, cmd_patterns, cmd_run_all
from research.db import connect, init_db
from research.keyword_pool import load_pool


class _FakeConfig:
    def __init__(self, keyword_pool_path):
        self.keyword_pool_path = keyword_pool_path


def _write_pool(tmp_path):
    pool = {
        "reading": {
            "problems": [
                {"id": "word_stress", "label": "영어 강세 위치를 어떻게 아는가", "search_queries": ["영어 강세"]},
            ]
        }
    }
    path = tmp_path / "keyword_pool.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(pool, f, allow_unicode=True, sort_keys=False)
    return path


def test_new_style_args_parse_correctly():
    parser = build_parser()
    args = parser.parse_args([
        "keywords", "add", "--category", "reading",
        "--problem-id", "word_stress", "--problem-label", "영어 강세 위치를 어떻게 아는가",
        "--query", "영어 강세",
    ])
    assert args.problem_id == "word_stress"
    assert args.problem_label == "영어 강세 위치를 어떻게 아는가"
    assert args.problem is None


def test_legacy_style_args_parse_correctly():
    parser = build_parser()
    args = parser.parse_args([
        "keywords", "add", "--category", "reading",
        "--problem", "영어 강세 위치를 어떻게 아는가", "--query", "영어 강세",
    ])
    assert args.problem == "영어 강세 위치를 어떻게 아는가"
    assert args.problem_id is None
    assert args.problem_label is None


def test_cmd_keywords_add_new_style_end_to_end(tmp_path):
    pool_path = _write_pool(tmp_path)
    parser = build_parser()
    args = parser.parse_args([
        "keywords", "add", "--category", "reading",
        "--problem-id", "cannot_read_words", "--problem-label", "알파벳은 아는데 영어 단어를 못 읽는다",
        "--query", "영어 단어 읽는 법",
    ])
    cmd_keywords_add(args, _FakeConfig(pool_path))

    pool = load_pool(pool_path)
    problem = next(p for p in pool["reading"]["problems"] if p["id"] == "cannot_read_words")
    assert "영어 단어 읽는 법" in problem["search_queries"]


def test_cmd_keywords_add_legacy_style_end_to_end(tmp_path):
    """Old scripts that only ever passed --problem must keep working unmodified."""
    pool_path = _write_pool(tmp_path)
    parser = build_parser()
    args = parser.parse_args([
        "keywords", "add", "--category", "reading",
        "--problem", "영어 강세 위치를 어떻게 아는가", "--query", "강세 규칙",
    ])
    cmd_keywords_add(args, _FakeConfig(pool_path))

    pool = load_pool(pool_path)
    # reuses the existing word_stress problem instead of creating a duplicate
    assert len(pool["reading"]["problems"]) == 1
    problem = pool["reading"]["problems"][0]
    assert problem["id"] == "word_stress"
    assert "강세 규칙" in problem["search_queries"]


def test_cmd_keywords_add_rejects_both_legacy_and_new(tmp_path):
    pool_path = _write_pool(tmp_path)
    parser = build_parser()
    args = parser.parse_args([
        "keywords", "add", "--category", "reading",
        "--problem", "x", "--problem-id", "y", "--problem-label", "z", "--query", "q",
    ])
    with pytest.raises(SystemExit):
        cmd_keywords_add(args, _FakeConfig(pool_path))


def test_cmd_keywords_add_rejects_neither_legacy_nor_new(tmp_path):
    pool_path = _write_pool(tmp_path)
    parser = build_parser()
    args = parser.parse_args(["keywords", "add", "--category", "reading", "--query", "q"])
    with pytest.raises(SystemExit):
        cmd_keywords_add(args, _FakeConfig(pool_path))


class _RichFakeConfig:
    """Stands in for research.config.Config in CLI tests, without needing a real .env/YAML file."""

    def __init__(self, tmp_path, pool_path):
        self.db_path = tmp_path / "test.db"
        self.keyword_pool_path = pool_path
        self.reports_dir = tmp_path / "reports"
        self.oauth_token_path = tmp_path / "token.json"
        self.youtube_api_key = "fake-youtube-key"
        self.youtube_client_id = None
        self.youtube_client_secret = None
        self.gemini_api_key = "fake-gemini-key"
        self._raw: dict = {}

    def get(self, *keys, default=None):
        node = self._raw
        for k in keys:
            if not isinstance(node, dict) or k not in node:
                return default
            node = node[k]
        return node


class _FailingGemini:
    """Mimics exactly what the real GeminiClient logs on failure, without any network call."""

    available = True

    def generate_json(self, prompt, max_output_tokens=1024):
        logging.getLogger("research.gemini_client").warning(
            "Gemini call failed, falling back to rule-based logic: fake timeout"
        )
        return None


def _seed_two_outlier_videos(db_path):
    init_db(db_path)
    with connect(db_path) as conn:
        conn.execute("INSERT INTO channels (channel_id, title) VALUES ('c1', 'Ch1')")
        for vid in ("v1", "v2"):
            conn.execute(
                "INSERT INTO videos (video_id, channel_id, title, content_type, is_search_result) "
                "VALUES (?, 'c1', ?, 'longform', 1)",
                (vid, f"title {vid}"),
            )
            conn.execute(
                "INSERT INTO outlier_scores (video_id, outlier_ratio, outlier_grade, opportunity_score) "
                "VALUES (?, 8.0, 'strong', 80.0)",
                (vid,),
            )


def test_cmd_patterns_warns_on_gemini_failure_with_index_and_reason(tmp_path, monkeypatch, capsys):
    pool_path = _write_pool(tmp_path)
    cfg = _RichFakeConfig(tmp_path, pool_path)
    _seed_two_outlier_videos(cfg.db_path)

    monkeypatch.setattr(cli, "_gemini_client", lambda cfg: _FailingGemini())
    monkeypatch.setattr(cli, "_require_youtube_client", lambda cfg: object())
    monkeypatch.setattr(cli, "sync_my_channel_stats", lambda *a, **kw: {"available": False, "reason": "test"})
    monkeypatch.setattr(cli, "compute_topic_scores", lambda *a, **kw: [])

    result = cmd_patterns(None, cfg)
    out = capsys.readouterr().out

    assert "[WARN] Gemini 분석 실패 (1/2)" in out
    assert "[WARN] Gemini 분석 실패 (2/2)" in out
    assert "reason: Gemini call failed, falling back to rule-based logic: fake timeout" in out
    assert "fallback: rule-based" in out
    assert "pipeline: continues" in out
    assert result["fallback"] == 2
    assert result["gemini_success"] == 0


class _NoGemini:
    available = False


def test_cmd_patterns_progress_output(tmp_path, monkeypatch, capsys):
    pool_path = _write_pool(tmp_path)
    cfg = _RichFakeConfig(tmp_path, pool_path)
    _seed_two_outlier_videos(cfg.db_path)

    monkeypatch.setattr(cli, "_gemini_client", lambda cfg: _NoGemini())
    monkeypatch.setattr(cli, "_require_youtube_client", lambda cfg: object())
    monkeypatch.setattr(cli, "sync_my_channel_stats", lambda *a, **kw: {"available": False, "reason": "test"})
    monkeypatch.setattr(cli, "compute_topic_scores", lambda *a, **kw: [])

    cmd_patterns(None, cfg)
    out = capsys.readouterr().out
    assert "[PATTERNS] 시작" in out
    assert "[PATTERNS] 2/2" in out
    assert "[PATTERNS DONE]" in out


def test_cmd_run_all_success_prints_summary(tmp_path, monkeypatch, capsys):
    cfg = _RichFakeConfig(tmp_path, tmp_path / "keyword_pool.yaml")
    init_db(cfg.db_path)

    monkeypatch.setattr(cli, "load_pool", lambda path: {"reading": {}})
    monkeypatch.setattr(cli, "cmd_search", lambda args, cfg: {"category": "reading"})
    monkeypatch.setattr(cli, "cmd_analyze", lambda args, cfg: {"processed": 5})
    monkeypatch.setattr(cli, "cmd_patterns", lambda args, cfg: {"fallback": 2, "gemini_success": 3})
    monkeypatch.setattr(cli, "cmd_report_weekly", lambda args, cfg: "reports/weekly_test.md")

    class _Args:
        query_limit = None

    cmd_run_all(_Args(), cfg)
    out = capsys.readouterr().out

    assert "[START] 시작" in out
    assert "[DONE DONE]" in out
    assert "YouTube Market Research 완료" in out
    assert "Search: PASS" in out
    assert "Analyze: PASS" in out
    assert "Patterns: PASS" in out
    assert "Report: PASS" in out
    assert "reports/weekly_test.md" in out
    assert "Gemini fallback 2건" in out
    assert "SUCCESS" in out


def test_cmd_run_all_failure_prints_failure_summary_and_reraises(tmp_path, monkeypatch, capsys):
    cfg = _RichFakeConfig(tmp_path, tmp_path / "keyword_pool.yaml")
    init_db(cfg.db_path)

    monkeypatch.setattr(cli, "load_pool", lambda path: {"reading": {}})
    monkeypatch.setattr(cli, "cmd_search", lambda args, cfg: {"category": "reading"})

    def _boom(args, cfg):
        raise RuntimeError("simulated YouTube API outage")

    monkeypatch.setattr(cli, "cmd_analyze", _boom)

    class _Args:
        query_limit = None

    with pytest.raises(RuntimeError, match="simulated YouTube API outage"):
        cmd_run_all(_Args(), cfg)

    captured = capsys.readouterr()
    assert "[ERROR]" in captured.err
    assert "Analyze" in captured.err
    assert "YouTube Market Research 실패" in captured.err
    assert "Failed stage:" in captured.err
    assert "ANALYZE" in captured.err
    assert "simulated YouTube API outage" in captured.err
    assert "Search PASS" in captured.err
    assert "NOT CREATED" in captured.err
    assert "FAILED" in captured.err
    # success summary must NOT have been printed
    assert "완료" not in captured.out
