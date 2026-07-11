from functools import wraps
from datetime import datetime, timedelta
from flask import Blueprint, render_template, jsonify, redirect, url_for, current_app, request
from flask_login import login_required, current_user
from app.extensions import db
from app.models import User, Subscription, YouTubeChannel, PageView

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        admin_emails = current_app.config.get("ADMIN_EMAILS", [])
        if not current_user.is_authenticated or current_user.email not in admin_emails:
            return redirect(url_for("main.index"))
        return f(*args, **kwargs)
    return decorated


@admin_bp.route("/")
@login_required
@admin_required
def dashboard():
    total_users = User.query.count()
    total_pro = Subscription.query.filter_by(plan="pro").count()
    total_channels = YouTubeChannel.query.filter(YouTubeChannel.channel_id.isnot(None)).count()
    mp_price = current_app.config.get("MP_PRO_PRICE_ARS", 15000)
    estimated_mrr = total_pro * mp_price
    recent_users = (
        User.query
        .outerjoin(Subscription)
        .outerjoin(YouTubeChannel)
        .order_by(User.created_at.desc())
        .limit(50)
        .all()
    )
    week_ago = datetime.utcnow() - timedelta(days=7)
    new_this_week = User.query.filter(User.created_at >= week_ago).count()

    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    visits_today = PageView.query.filter(PageView.created_at >= today_start).count()

    return render_template("admin.html",
        total_users=total_users,
        total_pro=total_pro,
        total_channels=total_channels,
        estimated_mrr=estimated_mrr,
        new_this_week=new_this_week,
        recent_users=recent_users,
        mp_price=mp_price,
        visits_today=visits_today,
    )


@admin_bp.route("/api/stats")
@login_required
@admin_required
def api_stats():
    days = []
    for i in range(29, -1, -1):
        day = datetime.utcnow().date() - timedelta(days=i)
        count = User.query.filter(
            db.func.date(User.created_at) == day
        ).count()
        days.append({"date": day.isoformat(), "count": count})
    return jsonify({"daily_signups": days})


@admin_bp.route("/visitors")
@login_required
@admin_required
def visitors_page():
    return render_template("admin_visitors.html")


@admin_bp.route("/api/visitors-stats")
@login_required
@admin_required
def api_visitors_stats():
    range_days = request.args.get("days", default=30, type=int)
    range_days = max(1, min(range_days, 90))
    since = datetime.utcnow() - timedelta(days=range_days)

    base = PageView.query.filter(PageView.created_at >= since)

    total_views = base.count()
    unique_visitors = base.with_entities(PageView.visitor_key).distinct().count()

    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    views_today = PageView.query.filter(PageView.created_at >= today_start).count()

    # Serie diaria (vistas + únicos)
    daily_rows = (
        db.session.query(
            db.func.date(PageView.created_at).label("day"),
            db.func.count(PageView.id).label("views"),
            db.func.count(db.func.distinct(PageView.visitor_key)).label("uniques"),
        )
        .filter(PageView.created_at >= since)
        .group_by("day")
        .order_by("day")
        .all()
    )
    daily_map = {str(r.day): {"views": r.views, "uniques": r.uniques} for r in daily_rows}
    timeline = []
    for i in range(range_days - 1, -1, -1):
        day = (datetime.utcnow() - timedelta(days=i)).date()
        entry = daily_map.get(str(day), {"views": 0, "uniques": 0})
        timeline.append({"date": day.isoformat(), **entry})

    # Top páginas
    top_pages = (
        base.with_entities(PageView.path, db.func.count(PageView.id).label("n"))
        .group_by(PageView.path)
        .order_by(db.func.count(PageView.id).desc())
        .limit(12)
        .all()
    )

    # Top fuentes de tráfico (referrer host), agrupando "sin referrer" como directo
    ref_rows = (
        base.with_entities(PageView.referrer_host, db.func.count(PageView.id).label("n"))
        .group_by(PageView.referrer_host)
        .order_by(db.func.count(PageView.id).desc())
        .limit(10)
        .all()
    )
    top_referrers = [{"source": r.referrer_host or "Directo / desconocido", "n": r.n} for r in ref_rows]

    # Dispositivos
    device_rows = (
        base.with_entities(PageView.device, db.func.count(PageView.id).label("n"))
        .group_by(PageView.device)
        .all()
    )
    devices = [{"device": r.device or "desconocido", "n": r.n} for r in device_rows]

    # Últimas visitas (log crudo)
    recent = (
        PageView.query.filter(PageView.created_at >= since)
        .order_by(PageView.created_at.desc())
        .limit(100)
        .all()
    )
    recent_list = [{
        "path": v.path,
        "referrer_host": v.referrer_host,
        "device": v.device,
        "ip_address": v.ip_address,
        "user_email": v.user.email if v.user else None,
        "created_at": v.created_at.isoformat() + "Z",
    } for v in recent]

    return jsonify({
        "range_days": range_days,
        "total_views": total_views,
        "unique_visitors": unique_visitors,
        "views_today": views_today,
        "timeline": timeline,
        "top_pages": [{"path": p.path, "n": p.n} for p in top_pages],
        "top_referrers": top_referrers,
        "devices": devices,
        "recent": recent_list,
    })
