from pathlib import Path

from research.channel_baseline import compute_channel_baseline
from research.db import connect, init_db


def _video_item(video_id, view_count, duration="PT5M", published_at="2026-01-01T00:00:00Z", live=False):
    item = {
        "id": video_id,
        "snippet": {
            "channelId": "channel1",
            "title": f"video {video_id}",
            "publishedAt": published_at,
            "thumbnails": {},
        },
        "statistics": {"viewCount": str(view_count), "likeCount": "10", "commentCount": "1"},
        "contentDetails": {"duration": duration},
    }
    if live:
        item["snippet"]["liveBroadcastContent"] = "live"
    return item


class FakeYouTubeClient:
    def __init__(self, videos, uploads_playlist_id="UUxxx"):
        self._videos = videos
        self._uploads_playlist_id = uploads_playlist_id
        self.playlist_calls = 0

    def get_channels(self, channel_ids):
        return [
            {
                "id": "channel1",
                "snippet": {"title": "Test Channel"},
                "statistics": {"subscriberCount": "1000", "videoCount": "50", "viewCount": "500000"},
                "contentDetails": {"relatedPlaylists": {"uploads": self._uploads_playlist_id}},
            }
        ]

    def get_playlist_video_ids(self, playlist_id, max_items=30):
        self.playlist_calls += 1
        return [v["id"] for v in self._videos][:max_items]

    def get_videos(self, video_ids):
        return [v for v in self._videos if v["id"] in video_ids]


def _setup_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "test.db"
    init_db(db_path)
    return db_path


def test_median_and_mean_baseline(tmp_path):
    db_path = _setup_db(tmp_path)
    videos = [_video_item(f"v{i}", view_count) for i, view_count in enumerate([100, 200, 300, 400, 500])]
    yt = FakeYouTubeClient(videos)

    baseline = compute_channel_baseline(
        db_path, yt, "channel1", "longform", exclude_video_id="target", min_sample_size=1
    )

    assert baseline["sample_size"] == 5
    assert baseline["median_views"] == 300
    assert baseline["mean_views"] == 300


def test_excludes_target_video_itself(tmp_path):
    db_path = _setup_db(tmp_path)
    videos = [_video_item(f"v{i}", 100) for i in range(3)] + [_video_item("target", 999999)]
    yt = FakeYouTubeClient(videos)

    baseline = compute_channel_baseline(
        db_path, yt, "channel1", "longform", exclude_video_id="target", min_sample_size=1
    )

    assert baseline["sample_size"] == 3
    assert baseline["median_views"] == 100


def test_content_type_separation(tmp_path):
    db_path = _setup_db(tmp_path)
    longform = [_video_item(f"lf{i}", 1000, duration="PT5M") for i in range(3)]
    shorts = [_video_item(f"sh{i}", 50, duration="PT30S") for i in range(3)]
    yt = FakeYouTubeClient(longform + shorts)

    baseline = compute_channel_baseline(
        db_path, yt, "channel1", "short", exclude_video_id="target", min_sample_size=1
    )

    assert baseline["sample_size"] == 3
    assert baseline["median_views"] == 50


def test_excludes_live_videos(tmp_path):
    db_path = _setup_db(tmp_path)
    videos = [_video_item(f"v{i}", 100) for i in range(3)] + [
        _video_item("live1", 999999, live=True)
    ]
    yt = FakeYouTubeClient(videos)

    baseline = compute_channel_baseline(
        db_path, yt, "channel1", "longform", exclude_video_id="target", exclude_live=True, min_sample_size=1
    )

    assert baseline["sample_size"] == 3
    assert baseline["median_views"] == 100


def test_low_sample_size_confidence(tmp_path):
    db_path = _setup_db(tmp_path)
    videos = [_video_item("v1", 100)]
    yt = FakeYouTubeClient(videos)

    baseline = compute_channel_baseline(
        db_path, yt, "channel1", "longform", exclude_video_id="target", min_sample_size=5
    )

    assert baseline["sample_size"] == 1
    assert baseline["confidence"] == "low"


def test_no_candidates_returns_none_baseline(tmp_path):
    db_path = _setup_db(tmp_path)
    yt = FakeYouTubeClient([])

    baseline = compute_channel_baseline(
        db_path, yt, "channel1", "longform", exclude_video_id="target", min_sample_size=5
    )

    assert baseline["sample_size"] == 0
    assert baseline["median_views"] is None
    assert baseline["confidence"] == "none"


def test_unknown_content_type_skipped(tmp_path):
    db_path = _setup_db(tmp_path)
    yt = FakeYouTubeClient([_video_item("v1", 100)])

    baseline = compute_channel_baseline(db_path, yt, "channel1", "unknown", exclude_video_id="target")

    assert baseline is None


def test_baseline_is_reused_within_cache_ttl(tmp_path):
    db_path = _setup_db(tmp_path)
    videos = [_video_item(f"v{i}", 100) for i in range(5)]
    yt = FakeYouTubeClient(videos)

    first = compute_channel_baseline(
        db_path, yt, "channel1", "longform", exclude_video_id="target", min_sample_size=1, cache_ttl_hours=168
    )
    second = compute_channel_baseline(
        db_path, yt, "channel1", "longform", exclude_video_id="target", min_sample_size=1, cache_ttl_hours=168
    )

    assert yt.playlist_calls == 1  # second call reused the stored baseline, no new API call
    assert first["median_views"] == second["median_views"]


def test_baseline_recomputes_after_cache_expires(tmp_path):
    db_path = _setup_db(tmp_path)
    videos = [_video_item(f"v{i}", 100) for i in range(5)]
    yt = FakeYouTubeClient(videos)

    compute_channel_baseline(
        db_path, yt, "channel1", "longform", exclude_video_id="target", min_sample_size=1, cache_ttl_hours=168
    )
    # Backdate the stored baseline so it looks older than any TTL.
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE channel_baselines SET computed_at = datetime('now', '-1000 hours') "
            "WHERE channel_id = 'channel1' AND content_type = 'longform'"
        )

    compute_channel_baseline(
        db_path, yt, "channel1", "longform", exclude_video_id="target", min_sample_size=1, cache_ttl_hours=168
    )

    assert yt.playlist_calls == 2  # cache had expired, so it fetched again
