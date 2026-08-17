"""OAuth + YouTube Analytics API v2 wrapper for the channel owner's own performance data.

`run_oauth_flow` must be run interactively on the user's machine (it opens a local browser) --
it cannot run inside an unattended/background session. Everything else degrades gracefully to
"no data" when no token file exists yet, so the rest of the pipeline keeps working without it.
"""
from __future__ import annotations

import logging
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/youtube.readonly",
]


def run_oauth_flow(client_id: str, client_secret: str, token_path: Path) -> None:
    """Runs the one-time interactive OAuth consent flow and stores a refresh token.
    Must be invoked from an interactive local session (opens a browser)."""
    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }
    flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
    creds = flow.run_local_server(port=0)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json(), encoding="utf-8")


def load_credentials(client_id: str, client_secret: str, token_path: Path) -> Credentials | None:
    if not token_path.exists():
        return None
    creds = Credentials.from_authorized_user_file(str(token_path), scopes=SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json(), encoding="utf-8")
    return creds


class AnalyticsClient:
    def __init__(self, credentials: Credentials):
        self._analytics = build("youtubeAnalytics", "v2", credentials=credentials, cache_discovery=False)
        self._youtube = build("youtube", "v3", credentials=credentials, cache_discovery=False)

    def get_my_channel_id(self) -> str | None:
        try:
            resp = self._youtube.channels().list(part="id", mine=True).execute()
        except HttpError as e:
            logger.warning("channels.list(mine=True) failed: %s", e)
            return None
        items = resp.get("items", [])
        return items[0]["id"] if items else None

    def get_video_performance(self, channel_id: str, start_date: str, end_date: str) -> list[dict]:
        """Fetches per-video retention/watch-time/subscriber-gain for the period.

        Note: `impressions` and `impressionsClickThroughRate` (CTR) are NOT available through the
        public YouTube Analytics API with the `video` dimension -- they're exposed only in the
        YouTube Studio UI. CTR/impressions therefore stay None throughout this project; that's an
        API limitation, not a bug.
        """
        try:
            resp = self._analytics.reports().query(
                ids=f"channel=={channel_id}",
                startDate=start_date,
                endDate=end_date,
                metrics=(
                    "views,averageViewDuration,averageViewPercentage,estimatedMinutesWatched,"
                    "subscribersGained"
                ),
                dimensions="video",
                sort="-views",
                maxResults=200,
            ).execute()
        except HttpError as e:
            logger.warning("youtubeAnalytics.reports.query failed: %s", e)
            return []

        headers = [h["name"] for h in resp.get("columnHeaders", [])]
        rows = resp.get("rows", []) or []
        results = []
        for row in rows:
            record = dict(zip(headers, row))
            results.append(
                {
                    "video_id": record.get("video"),
                    "views": record.get("views"),
                    "average_view_duration": record.get("averageViewDuration"),
                    "average_percentage_viewed": record.get("averageViewPercentage"),
                    "watch_time_minutes": record.get("estimatedMinutesWatched"),
                    "subscriber_gain": record.get("subscribersGained"),
                    "impressions": record.get("impressions"),
                    "ctr": record.get("impressionsClickThroughRate"),
                }
            )
        return results

    def get_top_traffic_source(self, channel_id: str, video_id: str, start_date: str, end_date: str) -> str | None:
        try:
            resp = self._analytics.reports().query(
                ids=f"channel=={channel_id}",
                startDate=start_date,
                endDate=end_date,
                metrics="views",
                dimensions="insightTrafficSourceType",
                filters=f"video=={video_id}",
                sort="-views",
                maxResults=1,
            ).execute()
        except HttpError as e:
            logger.warning("traffic source query failed for video=%s: %s", video_id, e)
            return None
        rows = resp.get("rows") or []
        return rows[0][0] if rows else None
