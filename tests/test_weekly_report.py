from pathlib import Path

from research.db import connect, init_db
from research.weekly_report import (
    _fetch_category_top_rows,
    _fetch_top_rows,
    _write_outlier_block,
    get_video_matches,
    problem_frequency,
)


def _seed_video(conn, video_id, channel_id, title, view_count=1000):
    conn.execute("INSERT OR IGNORE INTO channels (channel_id, title) VALUES (?, ?)", (channel_id, f"Channel {channel_id}"))
    conn.execute(
        "INSERT INTO videos (video_id, channel_id, title, content_type, is_search_result, view_count) "
        "VALUES (?, ?, ?, 'longform', 1, ?)",
        (video_id, channel_id, title, view_count),
    )


def _seed_outlier(conn, video_id, score, grade="strong", ratio=8.0):
    conn.execute(
        "INSERT INTO outlier_scores (video_id, outlier_ratio, outlier_grade, opportunity_score) VALUES (?, ?, ?, ?)",
        (video_id, ratio, grade, score),
    )


def _seed_match(conn, video_id, category, search_query, problem_id, problem_label):
    conn.execute(
        """
        INSERT INTO video_keyword_matches (video_id, category, search_query, problem_id, problem_label)
        VALUES (?, ?, ?, ?, ?)
        """,
        (video_id, category, search_query, problem_id, problem_label),
    )


def _set_first_seen_at(conn, video_id, date_str):
    conn.execute("UPDATE videos SET first_seen_at = ? WHERE video_id = ?", (f"{date_str} 00:00:00", video_id))


def test_category_top_is_independent_of_global_top(tmp_path):
    """A category's TOP videos must show up even if the category is entirely outside the global
    TOP-N -- otherwise one dominant category silently hides every other category's results."""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        # "reading" dominates the global top with a very high score.
        _seed_video(conn, "r1", "c1", "reading video")
        _seed_outlier(conn, "r1", score=99.0)
        _seed_match(conn, "r1", "reading", "q1", "p1", "reading problem")

        # "listening" has a much weaker video that would never make a global TOP-1.
        _seed_video(conn, "l1", "c2", "listening video")
        _seed_outlier(conn, "l1", score=10.0)
        _seed_match(conn, "l1", "listening", "q2", "p2", "listening problem")

    global_top = _fetch_top_rows(db_path, limit=1)
    assert [r["video_id"] for r in global_top] == ["r1"]

    listening_top = _fetch_category_top_rows(db_path, "listening", limit=5)
    assert [r["video_id"] for r in listening_top] == ["l1"]


def test_this_week_filter_excludes_old_discoveries(tmp_path):
    """The 'this week' section must reflect when a video was first discovered, not just be the
    all-time TOP relabeled."""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_video(conn, "old1", "c1", "old evergreen video")
        _seed_outlier(conn, "old1", score=90.0)
        _set_first_seen_at(conn, "old1", "2020-01-01")

        _seed_video(conn, "new1", "c1", "freshly discovered video")
        _seed_outlier(conn, "new1", score=50.0)
        _set_first_seen_at(conn, "new1", "2026-08-15")

    this_week = _fetch_top_rows(db_path, limit=10, since="2026-08-10", until="2026-08-17")
    assert [r["video_id"] for r in this_week] == ["new1"]

    evergreen = _fetch_top_rows(db_path, limit=10)
    assert {r["video_id"] for r in evergreen} == {"old1", "new1"}


def test_problem_frequency_counts_unique_video_once_per_problem(tmp_path):
    """A video matched by two different search queries under the *same* problem must only count
    once for that problem -- otherwise repeat-matches inflate the 'recurring problem' ranking."""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_video(conn, "v1", "c1", "video 1")
        _seed_match(conn, "v1", "reading", "query a", "p1", "shared problem")
        _seed_match(conn, "v1", "reading", "query b", "p1", "shared problem")  # same problem, different query

        _seed_video(conn, "v2", "c1", "video 2")
        _seed_match(conn, "v2", "reading", "query c", "p1", "shared problem")

    counter = problem_frequency(db_path)
    assert counter["shared problem"] == 2  # v1 and v2, not 3 (v1 matched twice)


def test_problem_frequency_video_can_have_multiple_problems(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_video(conn, "v1", "c1", "video 1")
        _seed_match(conn, "v1", "reading", "query a", "p1", "problem A")
        _seed_match(conn, "v1", "reading", "query b", "p2", "problem B")

    counter = problem_frequency(db_path)
    assert counter["problem A"] == 1
    assert counter["problem B"] == 1


def test_get_video_matches_returns_all_distinct_problems(tmp_path):
    """A video matched to two different problems must show both -- videos.problem_category only
    ever holds the first match, so the report display can't rely on it alone."""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_video(conn, "v1", "c1", "video 1")
        _seed_match(conn, "v1", "reading", "영어 단어 읽는 법", "cannot_read_words", "알파벳은 아는데 영어 단어를 못 읽는다")
        _seed_match(conn, "v1", "reading", "영어 강세", "word_stress", "영어 강세 위치를 어떻게 아는가")

    matches = get_video_matches(db_path, "v1")
    labels = {p["problem_label"] for p in matches["problems"]}
    assert labels == {"알파벳은 아는데 영어 단어를 못 읽는다", "영어 강세 위치를 어떻게 아는가"}
    assert len(matches["problems"]) == 2


def test_get_video_matches_dedups_same_problem_from_multiple_queries(tmp_path):
    """Two search queries under the same problem must not produce two problem entries."""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_video(conn, "v1", "c1", "video 1")
        _seed_match(conn, "v1", "reading", "영어 강세", "word_stress", "영어 강세 위치를 어떻게 아는가")
        _seed_match(conn, "v1", "reading", "강세 규칙", "word_stress", "영어 강세 위치를 어떻게 아는가")

    matches = get_video_matches(db_path, "v1")
    assert len(matches["problems"]) == 1
    assert matches["problems"][0]["problem_label"] == "영어 강세 위치를 어떻게 아는가"
    # but both search queries are still both shown
    assert set(matches["search_queries"]) == {"영어 강세", "강세 규칙"}


def test_get_video_matches_search_queries_are_distinct(tmp_path):
    # video_keyword_matches has a UNIQUE(video_id, category, search_query) constraint, so exact
    # duplicate rows can't exist -- this confirms the query still returns each distinct query
    # exactly once when several *different* queries are recorded.
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_video(conn, "v1", "c1", "video 1")
        _seed_match(conn, "v1", "reading", "영어 강세", "word_stress", "label")
        _seed_match(conn, "v1", "reading", "강세 규칙", "word_stress", "label")

    matches = get_video_matches(db_path, "v1")
    assert sorted(matches["search_queries"]) == sorted(["영어 강세", "강세 규칙"])
    assert len(matches["search_queries"]) == len(set(matches["search_queries"]))


def test_get_video_matches_single_match_still_works(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_video(conn, "v1", "c1", "video 1")
        _seed_match(conn, "v1", "reading", "영어 단어 읽는 법", "cannot_read_words", "알파벳은 아는데 영어 단어를 못 읽는다")

    matches = get_video_matches(db_path, "v1")
    assert len(matches["problems"]) == 1
    assert matches["search_queries"] == ["영어 단어 읽는 법"]


def test_get_video_matches_no_match_returns_empty_lists(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_video(conn, "v1", "c1", "video 1")

    matches = get_video_matches(db_path, "v1")
    assert matches["problems"] == []
    assert matches["search_queries"] == []


def test_outlier_block_shows_multiple_matches_in_evergreen_and_category_sections(tmp_path):
    """The same multi-match video must render identically (all problems/queries listed) whether
    it's pulled via the global/evergreen query or the per-category query."""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_video(conn, "v1", "c1", "multi-match video")
        _seed_outlier(conn, "v1", score=80.0)
        _seed_match(conn, "v1", "reading", "영어 단어 읽는 법", "cannot_read_words", "알파벳은 아는데 영어 단어를 못 읽는다")
        _seed_match(conn, "v1", "reading", "영어 강세", "word_stress", "영어 강세 위치를 어떻게 아는가")

    evergreen_rows = _fetch_top_rows(db_path, limit=10)
    category_rows = _fetch_category_top_rows(db_path, "reading", limit=5)

    evergreen_lines: list[str] = []
    _write_outlier_block(db_path, evergreen_lines, evergreen_rows)
    category_lines: list[str] = []
    _write_outlier_block(db_path, category_lines, category_rows)

    for lines in (evergreen_lines, category_lines):
        text = "\n".join(lines)
        assert "알파벳은 아는데 영어 단어를 못 읽는다" in text
        assert "영어 강세 위치를 어떻게 아는가" in text
        assert "영어 단어 읽는 법" in text
        assert "영어 강세" in text
