"""Tracking liviano de visitas al sitio (no confundir con analytics de YouTube).

Diseño pensado para no pesar en cada request y para no acumular datos
personales más de lo necesario:
- La IP se guarda con el último octeto/segmento enmascarado (no identifica
  a la persona exacta, sirve para ver origen aproximado / detectar abuso).
- Para contar "visitantes únicos" usamos un hash diario (IP completa + user
  agent + salt + día), nunca se guarda la IP completa.
"""
import hashlib
import re
from datetime import datetime
from urllib.parse import urlparse

from flask import request
from flask_login import current_user

from app.extensions import db
from app.models import PageView

# Rutas que no queremos contar como "visita" (assets, polling, la propia
# sección de admin para no auto-contaminar las métricas, health checks, etc.)
_SKIP_PREFIXES = ("/static", "/admin", "/api/", "/favicon", "/healthz", "/robots.txt", "/sitemap.xml")

_BOT_RE = re.compile(r"bot|spider|crawl|slurp|facebookexternalhit|preview|monitor", re.I)
_MOBILE_RE = re.compile(r"iphone|android.*mobile|mobile safari|windows phone", re.I)
_TABLET_RE = re.compile(r"ipad|android(?!.*mobile)|tablet", re.I)


def _classify_device(ua):
    if not ua:
        return "desktop"
    if _BOT_RE.search(ua):
        return "bot"
    if _TABLET_RE.search(ua):
        return "tablet"
    if _MOBILE_RE.search(ua):
        return "mobile"
    return "desktop"


def _mask_ip(ip):
    if not ip:
        return None
    if ":" in ip:  # IPv6 — enmascaramos los últimos 2 segmentos
        parts = ip.split(":")
        return ":".join(parts[:-2] + ["0", "0"]) if len(parts) > 2 else ip
    parts = ip.split(".")  # IPv4 — enmascaramos el último octeto
    if len(parts) == 4:
        parts[-1] = "0"
        return ".".join(parts)
    return ip


def _client_ip():
    fwd = request.headers.get("X-Forwarded-For", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.remote_addr or ""


def _visitor_key(ip, ua, secret):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    raw = f"{ip}|{ua}|{today}|{secret}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def should_track(path):
    return not path.startswith(_SKIP_PREFIXES)


def track_page_view(secret_key):
    """Registra una visita. Se llama desde un before_request; nunca debe
    romper el request si algo falla."""
    try:
        if request.method != "GET" or not should_track(request.path):
            return
        ip = _client_ip()
        ua = request.headers.get("User-Agent", "")
        device = _classify_device(ua)
        if device == "bot":
            return  # no ensuciamos las métricas con crawlers conocidos

        referrer = request.referrer or ""
        referrer_host = urlparse(referrer).netloc if referrer else None
        own_host = request.host
        if referrer_host == own_host:
            referrer_host = None  # navegación interna, no es una fuente de tráfico

        pv = PageView(
            path=request.path[:255],
            referrer=referrer[:512] if referrer else None,
            referrer_host=referrer_host[:255] if referrer_host else None,
            user_agent=ua[:512],
            device=device,
            ip_address=_mask_ip(ip),
            visitor_key=_visitor_key(ip, ua, secret_key),
            user_id=current_user.id if current_user.is_authenticated else None,
        )
        db.session.add(pv)
        db.session.commit()
    except Exception:
        db.session.rollback()
