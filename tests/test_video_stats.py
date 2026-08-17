from research.db import connect, init_db
from research.video_stats import (
    classify_content_type,
    normalize_channel,
    normalize_video,
    parse_iso8601_duration,
    upsert_videos,
)


def test_parse_iso8601_duration_minutes_seconds():
    assert parse_iso8601_duration("PT1M30S") == 90


def test_parse_iso8601_duration_hours():
    assert parse_iso8601_duration("PT1H2M3S") == 3723


def test_parse_iso8601_duration_seconds_only():
    assert parse_iso8601_duration("PT45S") == 45


def test_parse_iso8601_duration_missing_returns_none():
    assert parse_iso8601_duration(None) is None
    assert parse_iso8601_duration("") is None


def test_classify_content_type_boundaries():
    assert classify_content_type(60, short_max=60, ambiguous_max=180) == "short"
    assert classify_content_type(61, short_max=60, ambiguous_max=180) == "unknown"
    assert classify_content_type(180, short_max=60, ambiguous_max=180) == "unknown"
    assert classify_content_type(181, short_max=60, ambiguous_max=180) == "longform"
    assert classify_content_type(None, short_max=60, ambiguous_max=180) == "unknown"


def test_normalize_video_hidden_stats():
    item = {
        "id": "v1",
        "snippet": {
            "channelId": "c1",
            "title": "t",
            "description": "d",
            "publishedAt": "2026-01-01T00:00:00Z",
            "thumbnails": {"high": {"url": "http://x/high.jpg"}},
        },
        "statistics": {"viewCount": "1000"},  # no likeCount/commentCount => hidden/disabled
        "contentDetails": {"duration": "PT2M"},
    }
    result = normalize_video(item, short_max=60, ambiguous_max=180)
    assert result["view_count"] == 1000
    assert result["like_count"] is None
    assert result["likes_hidden"] == 1
    assert result["comment_count"] is None
    assert result["comments_disabled"] == 1
    assert result["content_type"] == "unknown"  # 120s is in the ambiguous zone


def test_normalize_video_live_detected():
    item = {
        "id": "v1",
        "snippet": {"channelId": "c1", "title": "t", "liveBroadcastContent": "live", "thumbnails": {}},
        "statistics": {},
        "contentDetails": {},
    }
    result = normalize_video(item, short_max=60, ambiguous_max=180)
    assert result["is_live"] == 1


def test_normalize_channel_hidden_subscribers():
    item = {
        "id": "c1",
        "snippet": {"title": "Channel"},
        "statistics": {"hiddenSubscriberCount": True, "videoCount": "10", "viewCount": "1000"},
        "contentDetails": {"relatedPlaylists": {"uploads": "UUxxx"}},
    }
    result = normalize_channel(item)
    assert result["subscriber_count"] is None
    assert result["subscriber_hidden"] == 1
    assert result["uploads_playlist_id"] == "UUxxx"


def test_normalize_channel_visible_subscribers():
    item = {
        "id": "c1",
        "snippet": {"title": "Channel"},
        "statistics": {"subscriberCount": "500", "videoCount": "10", "viewCount": "1000"},
        "contentDetails": {"relatedPlaylists": {"uploads": "UUxxx"}},
    }
    result = normalize_channel(item)
    assert result["subscriber_count"] == 500
    assert result["subscriber_hidden"] == 0


def test_upsert_videos_records_a_metrics_snapshot(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)

    item = {
        "id": "v1",
        "snippet": {"channelId": "c1", "title": "t", "thumbnails": {}},
        "statistics": {"viewCount": "1000", "likeCount": "10", "commentCount": "2"},
        "contentDetails": {"duration": "PT5M"},
    }
    normalized = normalize_video(item, short_max=60, ambiguous_max=180)
    upsert_videos(db_path, [normalized])

    with connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM video_metrics_snapshots WHERE video_id = 'v1'").fetchall()
    assert len(rows) == 1
    assert rows[0]["view_count"] == 1000
    assert rows[0]["like_count"] == 10


def test_upsert_videos_appends_a_new_snapshot_on_each_call(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)

    def _item(views):
        return {
            "id": "v1",
            "snippet": {"channelId": "c1", "title": "t", "thumbnails": {}},
            "statistics": {"viewCount": str(views)},
            "contentDetails": {"duration": "PT5M"},
        }

    upsert_videos(db_path, [normalize_video(_item(1000), short_max=60, ambiguous_max=180)])
    upsert_videos(db_path, [normalize_video(_item(2000), short_max=60, ambiguous_max=180)])

    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT view_count FROM video_metrics_snapshots WHERE video_id = 'v1' ORDER BY id"
        ).fetchall()
    assert [r["view_count"] for r in rows] == [1000, 2000]
