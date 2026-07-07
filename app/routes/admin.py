"""
Panel de administración — solo accesible para el email del administrador.
Muestra usuarios, planes, canales conectados e ingresos.
"""
from functools import wraps
from datetime import datetime, timedelta
from flask import Blueprint, render_template, jsonify, redirect, url_for, current_app
from flask_login import login_required, current_user
from app.extensions import db
from app.models import User, Subscription, YouTubeChannel

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

ADMIN_EMAILS = []  # se llena desde config en create_app


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
    # Totales
    total_users = User.query.count()
    total_pro = Subscription.query.filter_by(plan="pro").count()
    total_channels = YouTubeChannel.query.filter(YouTubeChannel.channel_id.isnot(None)).count()

    # Ingresos estimados (usuarios pro * precio)
    mp_price = current_app.config.get("MP_PRO_PRICE_ARS", 15000)
    estimated_mrr = total_pro * mp_price

    # Usuarios recientes
    recent_users = (
        User.query
        .outerjoin(Subscription)
        .outerjoin(YouTubeChannel)
        .order_by(User.created_at.desc())
        .limit(50)
        .all()
    )

    # Usuarios nuevos últimos 7 días
    week_ago = datetime.utcnow() - timedelta(days=7)
    new_this_week = User.query.filter(User.created_at >= week_ago).count()

    return render_template("admin.html",
        total_users=total_users,
        total_pro=total_pro,
        total_channels=total_channels,
        estimated_mrr=estimated_mrr,
        new_this_week=new_this_week,
        recent_users=recent_users,
        mp_price=mp_price,
    )


@admin_bp.route("/api/stats")
@login_required
@admin_required
def api_stats():
    """API JSON para el admin — últimos 30 días de registros."""
    days = []
    for i in range(29, -1, -1):
        day = datetime.utcnow().date() - timedelta(days=i)
        count = User.query.filter(
            db.func.date(User.created_at) == day
        ).count()
        days.append({"date": day.isoformat(), "count": count})
    return jsonify({"daily_signups": days})
