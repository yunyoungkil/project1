"""Thin wrapper around YouTube Data API v3 with quota logging and batching helpers."""
from __future__ import annotations

import logging
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from research.db import connect

logger = logging.getLogger(__name__)

SEARCH_LIST_COST = 100
LIST_ENDPOINT_COST = 1
BATCH_SIZE = 50


class YouTubeClient:
    def __init__(self, api_key: str, db_path: Path):
        self._youtube = build("youtube", "v3", developerKey=api_key, cache_discovery=False)
        self._db_path = db_path

    def _log_call(self, endpoint: str, cost_units: int, context: str = "") -> None:
        with connect(self._db_path) as conn:
            conn.execute(
                "INSERT INTO api_call_log (endpoint, cost_units, context) VALUES (?, ?, ?)",
                (endpoint, cost_units, context),
            )

    def search_videos(
        self,
        query: str,
        max_results: int = 15,
        region_code: str = "KR",
        relevance_language: str = "ko",
    ) -> list[str]:
        """Returns a list of video_ids matching the query. Costs 100 quota units."""
        try:
            resp = (
                self._youtube.search()
                .list(
                    q=query,
                    part="id",
                    type="video",
                    maxResults=max_results,
                    regionCode=region_code,
                    relevanceLanguage=relevance_language,
                    order="relevance",
                )
                .execute()
            )
        except HttpError as e:
            logger.warning("search.list failed for query=%r: %s", query, e)
            self._log_call("search.list", SEARCH_LIST_COST, context=f"query={query} (failed)")
            return []
        self._log_call("search.list", SEARCH_LIST_COST, context=f"query={query}")
        video_ids = []
        for item in resp.get("items", []):
            vid = item.get("id", {}).get("videoId")
            if vid:
                video_ids.append(vid)
        return video_ids

    def get_videos(self, video_ids: list[str]) -> list[dict]:
        """Batch-fetches video snippet/statistics/contentDetails. 1 unit per call regardless of batch size."""
        results: list[dict] = []
        for i in range(0, len(video_ids), BATCH_SIZE):
            chunk = video_ids[i : i + BATCH_SIZE]
            if not chunk:
                continue
            try:
                resp = (
                    self._youtube.videos()
                    .list(part="snippet,statistics,contentDetails,liveStreamingDetails", id=",".join(chunk))
                    .execute()
                )
            except HttpError as e:
                logger.warning("videos.list failed for chunk of %d ids: %s", len(chunk), e)
                self._log_call("videos.list", LIST_ENDPOINT_COST, context="failed")
                continue
            self._log_call("videos.list", LIST_ENDPOINT_COST, context=f"{len(chunk)} ids")
            results.extend(resp.get("items", []))
        return results

    def get_channels(self, channel_ids: list[str]) -> list[dict]:
        """Batch-fetches channel snippet/statistics/contentDetails (for uploads playlist id)."""
        results: list[dict] = []
        unique_ids = list(dict.fromkeys(channel_ids))
        for i in range(0, len(unique_ids), BATCH_SIZE):
            chunk = unique_ids[i : i + BATCH_SIZE]
            try:
                resp = (
                    self._youtube.channels()
                    .list(part="snippet,statistics,contentDetails", id=",".join(chunk))
                    .execute()
                )
            except HttpError as e:
                logger.warning("channels.list failed for chunk of %d ids: %s", len(chunk), e)
                self._log_call("channels.list", LIST_ENDPOINT_COST, context="failed")
                continue
            self._log_call("channels.list", LIST_ENDPOINT_COST, context=f"{len(chunk)} ids")
            results.extend(resp.get("items", []))
        return results

    def get_playlist_video_ids(self, playlist_id: str, max_items: int = 30) -> list[str]:
        """Fetches the most recent video ids from an uploads playlist. 1 unit per page."""
        video_ids: list[str] = []
        page_token = None
        try:
            while len(video_ids) < max_items:
                resp = (
                    self._youtube.playlistItems()
                    .list(
                        part="contentDetails",
                        playlistId=playlist_id,
                        maxResults=min(50, max_items - len(video_ids)),
                        pageToken=page_token,
                    )
                    .execute()
                )
                self._log_call("playlistItems.list", LIST_ENDPOINT_COST, context=playlist_id)
                for item in resp.get("items", []):
                    vid = item.get("contentDetails", {}).get("videoId")
                    if vid:
                        video_ids.append(vid)
                page_token = resp.get("nextPageToken")
                if not page_token:
                    break
        except HttpError as e:
            logger.warning("playlistItems.list failed for playlist=%s: %s", playlist_id, e)
        return video_ids[:max_items]
