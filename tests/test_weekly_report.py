from pathlib import Path

from research.db import connect, init_db
from research.weekly_report import _fetch_category_top_rows, _fetch_top_rows, problem_frequency


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
