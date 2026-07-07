"""
Funciones adicionales de YouTube Analytics para el plan Pro.
Complementa app/services/youtube.py con métricas avanzadas.
"""
from datetime import datetime, timedelta
import requests


def fetch_top_videos_by_views(access_token, channel_id, max_results=10):
    """Top videos ordenados por vistas (ranking)."""
    search = requests.get(
        "https://www.googleapis.com/youtube/v3/search",
        params={
            "part": "snippet",
            "channelId": channel_id,
            "type": "video",
            "order": "viewCount",
            "maxResults": max_results,
        },
        headers={"Authorization": f"Bearer {access_token}"},
    ).json()

    ids = [i["id"]["videoId"] for i in search.get("items", [])]
    if not ids:
        return []

    vdata = requests.get(
        "https://www.googleapis.com/youtube/v3/videos",
        params={"part": "snippet,statistics,contentDetails", "id": ",".join(ids)},
        headers={"Authorization": f"Bearer {access_token}"},
    ).json()

    result = []
    for rank, item in enumerate(vdata.get("items", []), 1):
        s = item.get("statistics", {})
        duration = item.get("contentDetails", {}).get("duration", "PT0S")
        result.append({
            "rank": rank,
            "id": item["id"],
            "title": item["snippet"]["title"],
            "published_at": item["snippet"]["publishedAt"][:10],
            "thumbnail": item["snippet"]["thumbnails"].get("medium", {}).get("url", ""),
            "views": int(s.get("viewCount", 0)),
            "likes": int(s.get("likeCount", 0)),
            "comments": int(s.get("commentCount", 0)),
            "duration": _parse_duration(duration),
        })
    return result


def fetch_traffic_sources(access_token, channel_id, days=28):
    """Fuentes de tráfico del canal."""
    end = datetime.utcnow().date()
    start = end - timedelta(days=days)

    resp = requests.get(
        "https://youtubeanalytics.googleapis.com/v2/reports",
        params={
            "ids": f"channel=={channel_id}",
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "metrics": "views",
            "dimensions": "insightTrafficSourceType",
            "sort": "-views",
        },
        headers={"Authorization": f"Bearer {access_token}"},
    ).json()

    if "error" in resp:
        return []

    headers = [h["name"] for h in resp.get("columnHeaders", [])]
    rows = resp.get("rows", [])
    total = sum(r[1] for r in rows) if rows else 1

    SOURCE_LABELS = {
        "YT_SEARCH": "Búsqueda de YouTube",
        "SUGGESTED_VIDEO": "Videos sugeridos",
        "EXTERNAL": "Fuentes externas",
        "BROWSE_FEATURES": "Página de inicio / tendencias",
        "CHANNEL": "Página del canal",
        "NO_LINK_OTHER": "Otros",
        "NOTIFICATION": "Notificaciones",
        "PLAYLIST": "Listas de reproducción",
        "YT_CHANNEL": "Canal de YouTube",
        "SUBSCRIBER": "Suscriptores",
    }

    result = []
    for row in rows:
        entry = dict(zip(headers, row))
        source = entry.get("insightTrafficSourceType", "OTHER")
        views = int(entry.get("views", 0))
        result.append({
            "source": source,
            "label": SOURCE_LABELS.get(source, source),
            "views": views,
            "percentage": round((views / total) * 100, 1),
        })
    return result


def fetch_period_comparison(access_token, channel_id, days=28):
    """Compara el período actual vs el período anterior."""
    end = datetime.utcnow().date()
    start_current = end - timedelta(days=days)
    start_previous = start_current - timedelta(days=days)

    def _fetch(start, end_date):
        resp = requests.get(
            "https://youtubeanalytics.googleapis.com/v2/reports",
            params={
                "ids": f"channel=={channel_id}",
                "startDate": start.isoformat(),
                "endDate": end_date.isoformat(),
                "metrics": "views,estimatedMinutesWatched,subscribersGained,subscribersLost",
            },
            headers={"Authorization": f"Bearer {access_token}"},
        ).json()
        if "error" in resp or not resp.get("rows"):
            return {"views": 0, "minutes": 0, "subs_gained": 0, "subs_lost": 0}
        row = resp["rows"][0]
        return {
            "views": int(row[0]),
            "minutes": int(row[1]),
            "subs_gained": int(row[2]),
            "subs_lost": int(row[3]),
        }

    current = _fetch(start_current, end)
    previous = _fetch(start_previous, start_current)

    def _change(curr, prev):
        if prev == 0:
            return 100 if curr > 0 else 0
        return round(((curr - prev) / prev) * 100, 1)

    return {
        "current": current,
        "previous": previous,
        "changes": {
            "views": _change(current["views"], previous["views"]),
            "minutes": _change(current["minutes"], previous["minutes"]),
            "subs_gained": _change(current["subs_gained"], previous["subs_gained"]),
        },
        "days": days,
    }


def fetch_video_retention(access_token, channel_id, max_videos=5):
    """Retención promedio (avg view duration) de los videos más recientes."""
    search = requests.get(
        "https://www.googleapis.com/youtube/v3/search",
        params={
            "part": "snippet",
            "channelId": channel_id,
            "type": "video",
            "order": "date",
            "maxResults": max_videos,
        },
        headers={"Authorization": f"Bearer {access_token}"},
    ).json()

    ids = [i["id"]["videoId"] for i in search.get("items", [])]
    if not ids:
        return []

    end = datetime.utcnow().date()
    start = end - timedelta(days=90)

    resp = requests.get(
        "https://youtubeanalytics.googleapis.com/v2/reports",
        params={
            "ids": f"channel=={channel_id}",
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "metrics": "views,averageViewDuration,averageViewPercentage",
            "dimensions": "video",
            "filters": f"video=={','.join(ids)}",
            "sort": "-views",
        },
        headers={"Authorization": f"Bearer {access_token}"},
    ).json()

    if "error" in resp:
        return []

    # Obtener títulos
    vdata = requests.get(
        "https://www.googleapis.com/youtube/v3/videos",
        params={"part": "snippet,contentDetails", "id": ",".join(ids)},
        headers={"Authorization": f"Bearer {access_token}"},
    ).json()
    titles = {v["id"]: v["snippet"]["title"] for v in vdata.get("items", [])}
    durations = {v["id"]: _parse_duration(v["contentDetails"]["duration"]) for v in vdata.get("items", [])}

    headers_list = [h["name"] for h in resp.get("columnHeaders", [])]
    result = []
    for row in resp.get("rows", []):
        entry = dict(zip(headers_list, row))
        vid_id = entry.get("video", "")
        result.append({
            "id": vid_id,
            "title": titles.get(vid_id, vid_id),
            "views": int(entry.get("views", 0)),
            "avg_duration_seconds": int(entry.get("averageViewDuration", 0)),
            "avg_percentage": round(float(entry.get("averageViewPercentage", 0)), 1),
            "total_duration_seconds": durations.get(vid_id, 0),
        })
    return result


def _parse_duration(iso_duration):
    """Convierte ISO 8601 duration (PT4M13S) a segundos."""
    import re
    match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', iso_duration)
    if not match:
        return 0
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    return hours * 3600 + minutes * 60 + seconds


def fmt_seconds(seconds):
    """Formatea segundos como mm:ss."""
    m = seconds // 60
    s = seconds % 60
    return f"{m}:{s:02d}"
