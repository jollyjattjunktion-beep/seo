"""Small, quota-conscious wrapper for the public YouTube Data API v3."""
from __future__ import annotations

from datetime import datetime
from typing import Any
import requests

BASE_URL = "https://www.googleapis.com/youtube/v3"


class YouTubeAPIError(RuntimeError):
    pass


def _get(api_key: str, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
    params = {**params, "key": api_key}
    try:
        response = requests.get(f"{BASE_URL}/{endpoint}", params=params, timeout=25)
    except requests.RequestException as exc:
        raise YouTubeAPIError(f"Could not connect to YouTube: {exc}") from exc
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if not response.ok:
        error = payload.get("error", {}) if isinstance(payload, dict) else {}
        message = error.get("message") or f"YouTube API returned HTTP {response.status_code}."
        reasons = error.get("errors", [])
        if reasons and isinstance(reasons, list):
            reason = reasons[0].get("reason")
            if reason:
                message += f" (reason: {reason})"
        if response.status_code in (401, 403) and "quota" in message.casefold():
            message += " Check the project's YouTube Data API quota in Google Cloud Console."
        raise YouTubeAPIError(message)
    return payload if isinstance(payload, dict) else {}


def search_videos(api_key: str, query: str, max_results: int = 50, order: str = "viewCount",
                  region_code: str = "IN", published_after: str | None = None) -> list[dict[str, Any]]:
    """Search up to 50 public videos, then enrich them with public stats/tags."""
    api_key = (api_key or "").strip()
    query = (query or "").strip()
    if not api_key:
        raise YouTubeAPIError("Add a YouTube Data API key in the sidebar or set YOUTUBE_API_KEY.")
    if not query:
        raise YouTubeAPIError("Enter a search query first.")
    max_results = max(1, min(int(max_results), 50))
    params: dict[str, Any] = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "maxResults": max_results,
        "order": order if order in {"relevance", "date", "viewCount", "rating", "title"} else "viewCount",
    }
    if region_code and region_code != "ALL":
        params["regionCode"] = region_code
    if published_after:
        params["publishedAfter"] = published_after
    search_payload = _get(api_key, "search", params)
    items = search_payload.get("items", [])
    ids: list[str] = []
    base: dict[str, dict[str, Any]] = {}
    for item in items:
        video_id = (item.get("id") or {}).get("videoId")
        snippet = item.get("snippet") or {}
        if video_id:
            ids.append(video_id)
            base[video_id] = {
                "video_id": video_id,
                "title": snippet.get("title", ""),
                "description": snippet.get("description", ""),
                "channel_title": snippet.get("channelTitle", ""),
                "channel_id": snippet.get("channelId", ""),
                "published_at": snippet.get("publishedAt", ""),
                "thumbnail_url": ((snippet.get("thumbnails") or {}).get("medium") or {}).get("url", ""),
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "views": None,
                "likes": None,
                "comments": None,
                "tags": [],
            }
    if not ids:
        return []

    # videos.list accepts up to 50 IDs and costs far less quota than another search request.
    detail_payload = _get(api_key, "videos", {
        "part": "snippet,statistics",
        "id": ",".join(ids),
        "maxResults": len(ids),
    })
    for item in detail_payload.get("items", []):
        video_id = item.get("id")
        if video_id not in base:
            continue
        snippet = item.get("snippet") or {}
        stats = item.get("statistics") or {}
        base[video_id].update({
            "title": snippet.get("title", base[video_id]["title"]),
            "description": snippet.get("description", base[video_id]["description"]),
            "channel_title": snippet.get("channelTitle", base[video_id]["channel_title"]),
            "published_at": snippet.get("publishedAt", base[video_id]["published_at"]),
            "tags": snippet.get("tags", []) or [],
            "views": _as_int(stats.get("viewCount")),
            "likes": _as_int(stats.get("likeCount")),
            "comments": _as_int(stats.get("commentCount")),
        })
    # Preserve YouTube search order.
    return [base[video_id] for video_id in ids if video_id in base]


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def compact_number(value: Any) -> str:
    if value is None:
        return "Not public"
    value = int(value)
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}B"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return f"{value:,}"


def format_published_date(value: str) -> str:
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return stamp.strftime("%Y-%m-%d")
    except (ValueError, TypeError, AttributeError):
        return "Unknown"
