from datetime import datetime, timedelta
import requests

YOUTUBE_TOKEN_URL = "https://oauth2.googleapis.com/token"
YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


class YouTubeAPIError(Exception):
    pass


def get_auth_url(client_id, redirect_uri):
    import urllib.parse
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(YOUTUBE_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
    }
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)


def exchange_code(code, client_id, client_secret, redirect_uri):
    resp = requests.post(YOUTUBE_TOKEN_URL, data={
        "code": code, "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    })
    data = resp.json()
    if "error" in data:
        raise YouTubeAPIError(data.get("error_description", data["error"]))
    return data


def refresh_token(refresh_tok, client_id, client_secret):
    resp = requests.post(YOUTUBE_TOKEN_URL, data={
        "refresh_token": refresh_tok, "client_id": client_id,
        "client_secret": client_secret, "grant_type": "refresh_token",
    })
    data = resp.json()
    if "error" in data:
        raise YouTubeAPIError(data.get("error_description", data["error"]))
    return data


def get_valid_token(channel, client_id, client_secret):
    from app.extensions import db
    if channel.is_token_expired():
        data = refresh_token(channel.refresh_token, client_id, client_secret)
        channel.access_token = data["access_token"]
        channel.token_expiry = datetime.utcnow() + timedelta(seconds=data.get("expires_in", 3600))
        db.session.commit()
    return channel.access_token


def fetch_channel_info(access_token):
    resp = requests.get(
        "https://www.googleapis.com/youtube/v3/channels",
        params={"part": "snippet,statistics", "mine": "true"},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    data = resp.json()
    if "error" in data:
        raise YouTubeAPIError(data["error"].get("message", "Error de API"))
    items = data.get("items", [])
    if not items:
        raise YouTubeAPIError("No se encontró ningún canal.")
    item = items[0]
    stats = item["statistics"]
    return {
        "channel_id": item["id"],
        "channel_name": item["snippet"]["title"],
        "channel_thumbnail": item["snippet"]["thumbnails"].get("default", {}).get("url", ""),
        "subscriber_count": int(stats.get("subscriberCount", 0)),
        "video_count": int(stats.get("videoCount", 0)),
        "view_count": int(stats.get("viewCount", 0)),
    }


def fetch_analytics(access_token, channel_id, days=7):
    end = datetime.utcnow().date()
    start = end - timedelta(days=days)
    resp = requests.get(
        "https://youtubeanalytics.googleapis.com/v2/reports",
        params={
            "ids": f"channel=={channel_id}",
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "metrics": "views,estimatedMinutesWatched,averageViewDuration,subscribersGained,subscribersLost",
            "dimensions": "day",
            "sort": "day",
        },
        headers={"Authorization": f"Bearer {access_token}"},
    )
    data = resp.json()
    if "error" in data:
        raise YouTubeAPIError(data["error"].get("message", "Error Analytics API"))

    headers = [h["name"] for h in data.get("columnHeaders", [])]
    rows = data.get("rows", [])
    daily, totals = [], {"views": 0, "minutes_watched": 0, "subs_gained": 0, "subs_lost": 0}

    for row in rows:
        e = dict(zip(headers, row))
        daily.append({
            "date": e.get("day"),
            "views": int(e.get("views", 0)),
            "minutes_watched": int(e.get("estimatedMinutesWatched", 0)),
            "avg_duration": int(e.get("averageViewDuration", 0)),
            "subs_gained": int(e.get("subscribersGained", 0)),
            "subs_lost": int(e.get("subscribersLost", 0)),
        })
        totals["views"] += int(e.get("views", 0))
        totals["minutes_watched"] += int(e.get("estimatedMinutesWatched", 0))
        totals["subs_gained"] += int(e.get("subscribersGained", 0))
        totals["subs_lost"] += int(e.get("subscribersLost", 0))

    return {"daily": daily, "totals": totals, "days": days}


def fetch_videos(access_token, channel_id, max_results=10):
    search = requests.get(
        "https://www.googleapis.com/youtube/v3/search",
        params={"part": "snippet", "channelId": channel_id, "type": "video",
                "order": "date", "maxResults": max_results},
        headers={"Authorization": f"Bearer {access_token}"},
    ).json()
    if "error" in search:
        return []
    ids = [i["id"]["videoId"] for i in search.get("items", [])]
    if not ids:
        return []
    vdata = requests.get(
        "https://www.googleapis.com/youtube/v3/videos",
        params={"part": "snippet,statistics", "id": ",".join(ids)},
        headers={"Authorization": f"Bearer {access_token}"},
    ).json()
    result = []
    for item in vdata.get("items", []):
        s = item.get("statistics", {})
        result.append({
            "id": item["id"],
            "title": item["snippet"]["title"],
            "published_at": item["snippet"]["publishedAt"][:10],
            "thumbnail": item["snippet"]["thumbnails"].get("medium", {}).get("url", ""),
            "views": int(s.get("viewCount", 0)),
            "likes": int(s.get("likeCount", 0)),
            "comments": int(s.get("commentCount", 0)),
        })
    return result


def build_excel(channel_info, analytics, videos):
    import io
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.chart import LineChart, Reference

    wb = openpyxl.Workbook()
    hfont = Font(bold=True, color="FFFFFF")
    hfill = PatternFill("solid", fgColor="1A1A2E")

    # Hoja 1: Resumen
    ws1 = wb.active
    ws1.title = "Resumen"
    ws1.column_dimensions["A"].width = 30
    ws1.column_dimensions["B"].width = 25
    ws1["A1"] = "ChannelIQ — Reporte de Canal"
    ws1["A1"].font = Font(bold=True, size=14)
    ws1["A2"] = f"Generado: {datetime.utcnow().strftime('%d/%m/%Y %H:%M')} UTC"
    ws1["A4"] = "Canal"; ws1["B4"] = channel_info["channel_name"]
    ws1["A5"] = "Suscriptores"; ws1["B5"] = channel_info["subscriber_count"]
    ws1["A6"] = "Total videos"; ws1["B6"] = channel_info["video_count"]
    ws1["A7"] = "Vistas históricas"; ws1["B7"] = channel_info["view_count"]
    t = analytics["totals"]
    ws1["A9"] = f"Últimos {analytics['days']} días"; ws1["A9"].font = Font(bold=True)
    ws1["A10"] = "Vistas"; ws1["B10"] = t["views"]
    ws1["A11"] = "Minutos vistos"; ws1["B11"] = t["minutes_watched"]
    ws1["A12"] = "Subs ganados"; ws1["B12"] = t["subs_gained"]
    ws1["A13"] = "Subs perdidos"; ws1["B13"] = t["subs_lost"]
    ws1["A14"] = "Subs netos"; ws1["B14"] = t["subs_gained"] - t["subs_lost"]

    # Hoja 2: Datos diarios + gráfica
    ws2 = wb.create_sheet("Analytics diarios")
    cols = ["Fecha", "Vistas", "Minutos vistos", "Duración prom (seg)", "Subs ganados", "Subs perdidos"]
    for ci, h in enumerate(cols, 1):
        c = ws2.cell(1, ci, h); c.font = hfont; c.fill = hfill
        ws2.column_dimensions[c.column_letter].width = 20
    for ri, d in enumerate(analytics["daily"], 2):
        ws2.cell(ri, 1, d["date"]); ws2.cell(ri, 2, d["views"])
        ws2.cell(ri, 3, d["minutes_watched"]); ws2.cell(ri, 4, d["avg_duration"])
        ws2.cell(ri, 5, d["subs_gained"]); ws2.cell(ri, 6, d["subs_lost"])
    if len(analytics["daily"]) > 1:
        chart = LineChart()
        chart.title = "Vistas diarias"; chart.style = 10
        chart.height = 10; chart.width = 20
        chart.add_data(Reference(ws2, min_col=2, min_row=1, max_row=len(analytics["daily"]) + 1), titles_from_data=True)
        chart.set_categories(Reference(ws2, min_col=1, min_row=2, max_row=len(analytics["daily"]) + 1))
        ws2.add_chart(chart, "H2")

    # Hoja 3: Videos
    ws3 = wb.create_sheet("Videos")
    vh = ["Título", "Fecha", "Vistas", "Likes", "Comentarios"]
    for ci, h in enumerate(vh, 1):
        c = ws3.cell(1, ci, h); c.font = hfont; c.fill = hfill
    ws3.column_dimensions["A"].width = 50
    for ri, v in enumerate(videos, 2):
        ws3.cell(ri, 1, v["title"]); ws3.cell(ri, 2, v["published_at"])
        ws3.cell(ri, 3, v["views"]); ws3.cell(ri, 4, v["likes"]); ws3.cell(ri, 5, v["comments"])

    out = io.BytesIO()
    wb.save(out); out.seek(0)
    return out.read()
