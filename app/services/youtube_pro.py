"""Consultas avanzadas a YouTube Analytics API para la sección Stats Pro."""
from datetime import datetime, timedelta

import requests

from app.services.youtube import YouTubeAPIError

ANALYTICS_URL = "https://youtubeanalytics.googleapis.com/v2/reports"
DATA_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"

TRAFFIC_SOURCE_LABELS = {
    "ADVERTISING": "Publicidad",
    "ANNOTATION": "Anotaciones",
    "CAMPAIGN_CARD": "Tarjetas de campaña",
    "END_SCREEN": "Pantalla final",
    "EXT_URL": "Enlaces externos",
    "NO_LINK_EMBEDDED": "Insertado (sin enlace)",
    "NO_LINK_OTHER": "Otro (sin enlace)",
    "NOTIFICATION": "Notificaciones",
    "PLAYLIST": "Listas de reproducción",
    "PROMOTED": "Promocionado",
    "RELATED_VIDEO": "Videos relacionados",
    "SUBSCRIBER": "Suscriptores",
    "YT_CHANNEL": "Página del canal",
    "YT_OTHER_PAGE": "Otra página de YouTube",
    "YT_SEARCH": "Búsqueda de YouTube",
    "SHORTS": "YouTube Shorts",
    "SOUND_PAGE": "Página de sonido",
    "HASHTAGS": "Hashtags",
    "LIVE_REDIRECT": "Redirección en vivo",
}


def _get(access_token, params):
    resp = requests.get(
        ANALYTICS_URL, params=params,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    data = resp.json()
    if "error" in data:
        raise YouTubeAPIError(data["error"].get("message", "Error Analytics API"))
    return data


def fetch_top_videos_by_views(access_token, channel_id, max_results=10, days=28):
    """Videos con más vistas en el período, enriquecidos con título/miniatura."""
    end = datetime.utcnow().date()
    start = end - timedelta(days=days)
    data = _get(access_token, {
        "ids": f"channel=={channel_id}",
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "metrics": "views,likes,comments,estimatedMinutesWatched,averageViewPercentage",
        "dimensions": "video",
        "sort": "-views",
        "maxResults": max_results,
    })
    headers = [h["name"] for h in data.get("columnHeaders", [])]
    rows = data.get("rows", [])

    entries, ids = [], []
    for row in rows:
        e = dict(zip(headers, row))
        vid = e.get("video")
        ids.append(vid)
        entries.append({
            "id": vid,
            "views": int(e.get("views", 0)),
            "likes": int(e.get("likes", 0)),
            "comments": int(e.get("comments", 0)),
            "minutes_watched": int(e.get("estimatedMinutesWatched", 0)),
            "avg_view_pct": round(float(e.get("averageViewPercentage", 0)), 1),
        })

    meta = {}
    if ids:
        vdata = requests.get(
            DATA_VIDEOS_URL, params={"part": "snippet", "id": ",".join(ids)},
            headers={"Authorization": f"Bearer {access_token}"},
        ).json()
        for item in vdata.get("items", []):
            meta[item["id"]] = {
                "title": item["snippet"]["title"],
                "thumbnail": item["snippet"]["thumbnails"].get("medium", {}).get("url", ""),
                "published_at": item["snippet"]["publishedAt"][:10],
            }

    for e in entries:
        m = meta.get(e["id"], {})
        e["title"] = m.get("title", "(video eliminado o privado)")
        e["thumbnail"] = m.get("thumbnail", "")
        e["published_at"] = m.get("published_at", "")
    return entries


def fetch_traffic_sources(access_token, channel_id, days=28):
    """Distribución de vistas por fuente de tráfico."""
    end = datetime.utcnow().date()
    start = end - timedelta(days=days)
    data = _get(access_token, {
        "ids": f"channel=={channel_id}",
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "metrics": "views",
        "dimensions": "insightTrafficSourceType",
        "sort": "-views",
    })
    rows = data.get("rows", [])
    total = sum(int(r[1]) for r in rows) or 1

    sources = []
    for r in rows:
        key, views = r[0], int(r[1])
        sources.append({
            "source": TRAFFIC_SOURCE_LABELS.get(key, key.title()),
            "views": views,
            "pct": round(views / total * 100, 1),
        })
    return sources


def fetch_period_comparison(access_token, channel_id, days=28):
    """Compara el período actual contra el período inmediatamente anterior."""
    end = datetime.utcnow().date()
    cur_start = end - timedelta(days=days)
    prev_end = cur_start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=days - 1)

    def totals(start, until):
        data = _get(access_token, {
            "ids": f"channel=={channel_id}",
            "startDate": start.isoformat(),
            "endDate": until.isoformat(),
            "metrics": "views,estimatedMinutesWatched,subscribersGained,subscribersLost,likes,comments,shares",
        })
        rows = data.get("rows", [])
        if not rows:
            return {"views": 0, "minutes_watched": 0, "subs_gained": 0,
                    "subs_lost": 0, "likes": 0, "comments": 0, "shares": 0}
        headers = [h["name"] for h in data.get("columnHeaders", [])]
        e = dict(zip(headers, rows[0]))
        return {
            "views": int(e.get("views", 0)),
            "minutes_watched": int(e.get("estimatedMinutesWatched", 0)),
            "subs_gained": int(e.get("subscribersGained", 0)),
            "subs_lost": int(e.get("subscribersLost", 0)),
            "likes": int(e.get("likes", 0)),
            "comments": int(e.get("comments", 0)),
            "shares": int(e.get("shares", 0)),
        }

    current = totals(cur_start, end)
    previous = totals(prev_start, prev_end)

    def pct_change(cur, prev):
        if prev == 0:
            return 100.0 if cur > 0 else 0.0
        return round((cur - prev) / prev * 100, 1)

    changes = {k: pct_change(current[k], previous[k]) for k in current}
    return {"current": current, "previous": previous, "changes": changes, "days": days}


def fetch_video_retention(access_token, channel_id, max_videos=5):
    """Curva de retención de audiencia para los videos más vistos."""
    top = fetch_top_videos_by_views(access_token, channel_id, max_results=max_videos)

    results = []
    for v in top:
        curve = []
        try:
            data = _get(access_token, {
                "ids": f"channel=={channel_id}",
                "startDate": "2020-01-01",
                "endDate": datetime.utcnow().date().isoformat(),
                "metrics": "audienceWatchRatio",
                "dimensions": "elapsedVideoTimeRatio",
                "filters": f"video=={v['id']}",
                "sort": "elapsedVideoTimeRatio",
            })
            curve = [
                {"t": round(float(r[0]) * 100, 1), "retention": round(float(r[1]) * 100, 1)}
                for r in data.get("rows", [])
            ]
        except YouTubeAPIError:
            curve = []
        results.append({
            "id": v["id"],
            "title": v["title"],
            "thumbnail": v["thumbnail"],
            "views": v["views"],
            "curve": curve,
        })
    return results
