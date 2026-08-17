from pathlib import Path

from research.analyze_pipeline import analyze_pending_videos
from research.db import connect, init_db


def _video_item(video_id, view_count, duration="PT5M", published_at="2026-01-01T00:00:00Z"):
    return {
        "id": video_id,
        "snippet": {"channelId": "c1", "title": f"video {video_id}", "publishedAt": published_at, "thumbnails": {}},
        "statistics": {"viewCount": str(view_count), "likeCount": "10", "commentCount": "1"},
        "contentDetails": {"duration": duration},
    }


class _FakeYouTubeClient:
    def __init__(self, baseline_views):
        self._baseline_videos = [_video_item(f"b{i}", v) for i, v in enumerate(baseline_views)]

    def get_channels(self, channel_ids):
        return [
            {
                "id": "c1",
                "snippet": {"title": "Test Channel"},
                "statistics": {"subscriberCount": "1000"},
                "contentDetails": {"relatedPlaylists": {"uploads": "UUxxx"}},
            }
        ]

    def get_playlist_video_ids(self, playlist_id, max_items=30):
        return [v["id"] for v in self._baseline_videos][:max_items]

    def get_videos(self, video_ids):
        return [v for v in self._baseline_videos if v["id"] in video_ids]


def _seed_pending_video(conn, video_id, view_count=100000):
    conn.execute(
        """
        INSERT INTO videos (video_id, channel_id, title, content_type, view_count, like_count,
            comment_count, published_at, is_search_result)
        VALUES (?, 'c1', ?, 'longform', ?, 10, 1, '2026-01-05T00:00:00Z', 1)
        """,
        (video_id, f"title {video_id}", view_count),
    )


def _analyze_kwargs(yt):
    return dict(
        baseline_cfg={"sample_size": 30, "min_sample_size": 1},
        content_type_cfg={"short_max_seconds": 60, "ambiguous_max_seconds": 180},
        grade_thresholds={"notable": 2, "strong": 5, "very_strong": 10, "exceptional": 20},
        score_weights={"outlier_strength": 0.4, "views_velocity": 0.2, "subscriber_ratio": 0.1, "engagement": 0.1, "relevance": 0.2},
        score_caps={"outlier_ratio_cap": 50, "views_per_day_cap": 5000, "subscriber_ratio_cap": 5, "like_rate_cap": 0.08, "comment_rate_cap": 0.01},
        min_grade_to_store="notable",
    )


def test_on_progress_called_once_per_video_in_order(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        for i in range(5):
            _seed_pending_video(conn, f"v{i}", view_count=100000)

    yt = _FakeYouTubeClient(baseline_views=[100] * 10)
    calls = []
    analyze_pending_videos(db_path, yt, on_progress=lambda i, total: calls.append((i, total)), **_analyze_kwargs(yt))

    assert calls == [(1, 5), (2, 5), (3, 5), (4, 5), (5, 5)]


def test_on_progress_is_optional_and_defaults_to_none(tmp_path):
    """analyze_pending_videos must keep working unmodified when no on_progress is passed --
    existing callers/tests must not break."""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        _seed_pending_video(conn, "v1", view_count=100000)

    yt = _FakeYouTubeClient(baseline_views=[100] * 10)
    result = analyze_pending_videos(db_path, yt, **_analyze_kwargs(yt))
    assert result["total_candidates"] == 1


def test_on_progress_fires_even_for_skipped_unknown_type_videos(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO videos (video_id, channel_id, title, content_type, view_count, is_search_result)
            VALUES ('u1', 'c1', 'unknown type video', 'unknown', 1000, 1)
            """
        )
        _seed_pending_video(conn, "v1", view_count=100000)

    yt = _FakeYouTubeClient(baseline_views=[100] * 10)
    calls = []
    analyze_pending_videos(db_path, yt, on_progress=lambda i, total: calls.append((i, total)), **_analyze_kwargs(yt))

    assert len(calls) == 2  # both videos counted, even the one skipped for unknown content_type
