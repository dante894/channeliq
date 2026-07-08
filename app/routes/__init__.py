import json
import io
from datetime import datetime, timedelta

import requests
import mercadopago
from flask import (Blueprint, redirect, url_for, session, current_app,
                   request, jsonify, render_template, send_file)
from flask_login import login_user, logout_user, login_required, current_user
from oauthlib.oauth2 import WebApplicationClient
 from flask import request as flask_request

from app.extensions import db
from app.models import User, YouTubeChannel, Subscription
from app.services import youtube as yt_service

# ── Auth ────────────────────────────────────────────────────────────────────

auth_bp = Blueprint("auth", __name__)


def _google_cfg():
    return requests.get(current_app.config["GOOGLE_DISCOVERY_URL"]).json()


@auth_bp.route("/login")
def login():
    cfg = _google_cfg()
    client = WebApplicationClient(current_app.config["GOOGLE_CLIENT_ID"])
    uri = client.prepare_request_uri(
        cfg["authorization_endpoint"],
        redirect_uri=url_for("auth.callback", _external=True),
        scope=["openid", "email", "profile"],
    )
    return redirect(uri)


@auth_bp.route("/login/callback")
def callback():
    code = request.args.get("code")
    cfg = _google_cfg()
    client = WebApplicationClient(current_app.config["GOOGLE_CLIENT_ID"])
    token_url, headers, body = client.prepare_token_request(
        cfg["token_endpoint"],
        authorization_response=request.url,
        redirect_url=url_for("auth.callback", _external=True),
        code=code,
    )
    token_resp = requests.post(
        token_url, headers=headers, data=body,
        auth=(current_app.config["GOOGLE_CLIENT_ID"], current_app.config["GOOGLE_CLIENT_SECRET"]),
    )
    client.parse_request_body_response(json.dumps(token_resp.json()))
    uri, headers, body = client.add_token(cfg["userinfo_endpoint"])
    userinfo = requests.get(uri, headers=headers).json()

    user = User.query.filter_by(google_id=userinfo["sub"]).first()
    if not user:
        user = User(google_id=userinfo["sub"], email=userinfo["email"],
                    name=userinfo.get("name"), avatar_url=userinfo.get("picture"))
        db.session.add(user)
    else:
        user.last_login_at = datetime.utcnow()
    db.session.commit()
    login_user(user)
    next_page = flask_request.args.get("next") or url_for("main.dashboard")
    return redirect(next_page)


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    session.clear()
    return redirect(url_for("main.index"))


# ── Main ────────────────────────────────────────────────────────────────────

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    return render_template("index.html")


@main_bp.route("/privacy")
def privacy():
    return render_template("privacy.html")


@main_bp.route("/dashboard")
@login_required
def dashboard():
    sub = current_user.get_subscription()
    return render_template("dashboard.html",
                           subscription=sub,
                           channel=current_user.channel,
                           mp_public_key=current_app.config["MP_PUBLIC_KEY"])


# ── YouTube OAuth ────────────────────────────────────────────────────────────

yt_bp = Blueprint("youtube", __name__, url_prefix="/youtube")


@yt_bp.route("/connect")
@login_required
def connect():
    url = yt_service.get_auth_url(
        current_app.config["GOOGLE_CLIENT_ID"],
        url_for("youtube.yt_callback", _external=True),
    )
    return redirect(url)


@yt_bp.route("/callback")
@login_required
def yt_callback():
    code = request.args.get("code")
    if not code:
        return redirect(url_for("main.dashboard") + "?error=access_denied")
    try:
        tokens = yt_service.exchange_code(
            code, current_app.config["GOOGLE_CLIENT_ID"],
            current_app.config["GOOGLE_CLIENT_SECRET"],
            url_for("youtube.yt_callback", _external=True),
        )
        access_token = tokens["access_token"]
        info = yt_service.fetch_channel_info(access_token)

        ch = current_user.channel or YouTubeChannel(user_id=current_user.id)
        ch.access_token = access_token
        ch.refresh_token = tokens.get("refresh_token")
        ch.token_expiry = datetime.utcnow() + timedelta(seconds=tokens.get("expires_in", 3600))
        ch.channel_id = info["channel_id"]
        ch.channel_name = info["channel_name"]
        ch.channel_thumbnail = info["channel_thumbnail"]
        ch.subscriber_count = info["subscriber_count"]
        ch.video_count = info["video_count"]
        ch.view_count = info["view_count"]
        ch.connected_at = datetime.utcnow()
        ch.last_synced_at = datetime.utcnow()
        if not current_user.channel:
            db.session.add(ch)
        db.session.commit()
    except yt_service.YouTubeAPIError as e:
        return redirect(url_for("main.dashboard") + f"?error={e}")
    return redirect(url_for("main.dashboard") + "?connected=1")


@yt_bp.route("/disconnect", methods=["POST"])
@login_required
def disconnect():
    if current_user.channel:
        db.session.delete(current_user.channel)
        db.session.commit()
    return jsonify({"ok": True})


# ── Analytics API ────────────────────────────────────────────────────────────

api_bp = Blueprint("api", __name__, url_prefix="/api")


def _get_token():
    ch = current_user.channel
    if not ch or not ch.channel_id:
        return None, jsonify({"error": "Canal no conectado"}), 400
    try:
        token = yt_service.get_valid_token(
            ch, current_app.config["GOOGLE_CLIENT_ID"],
            current_app.config["GOOGLE_CLIENT_SECRET"],
        )
        return token, None, None
    except yt_service.YouTubeAPIError as e:
        return None, jsonify({"error": str(e)}), 400


@api_bp.route("/overview")
@login_required
def overview():
    token, err, code = _get_token()
    if err:
        return err, code
    is_pro = current_user.is_pro
    days = current_app.config["PRO_DAYS"] if is_pro else current_app.config["FREE_DAYS"]
    max_videos = current_app.config["PRO_VIDEOS"] if is_pro else current_app.config["FREE_VIDEOS"]
    try:
        ch = current_user.channel
        analytics = yt_service.fetch_analytics(token, ch.channel_id, days)
        videos = yt_service.fetch_videos(token, ch.channel_id, max_videos)
        # Actualizar stats del canal
        info = yt_service.fetch_channel_info(token)
        ch.subscriber_count = info["subscriber_count"]
        ch.last_synced_at = datetime.utcnow()
        db.session.commit()
        return jsonify({"analytics": analytics, "videos": videos,
                        "channel": ch.to_dict(), "is_pro": is_pro})
    except yt_service.YouTubeAPIError as e:
        return jsonify({"error": str(e)}), 400


@api_bp.route("/export/excel")
@login_required
def export_excel():
    if not current_user.is_pro:
        return jsonify({"error": "Requiere plan Pro", "upgrade": True}), 403
    token, err, code = _get_token()
    if err:
        return err, code
    try:
        ch = current_user.channel
        info = yt_service.fetch_channel_info(token)
        analytics = yt_service.fetch_analytics(token, ch.channel_id, 28)
        videos = yt_service.fetch_videos(token, ch.channel_id, 50)
        excel = yt_service.build_excel(info, analytics, videos)
        fname = f"channeliq_{ch.channel_name}_{datetime.utcnow().strftime('%Y%m%d')}.xlsx"
        return send_file(io.BytesIO(excel),
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                         as_attachment=True, download_name=fname)
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# ── Pagos ────────────────────────────────────────────────────────────────────

pay_bp = Blueprint("payments", __name__, url_prefix="/payments")


def _mp():
    return mercadopago.SDK(current_app.config["MP_ACCESS_TOKEN"])


@pay_bp.route("/checkout-pro", methods=["POST"])
@login_required
def checkout_pro():
    sdk = _mp()
    precio_ars = current_app.config["MP_PRO_PRICE_ARS"]
    preference_data = {
        "items": [{
            "title": "ChannelIQ Pro — Suscripción mensual",
            "quantity": 1,
            "unit_price": precio_ars,
            "currency_id": "ARS",
        }],
        "back_urls": {
            "success": url_for("main.dashboard", _external=True) + "?pro=1",
            "failure": url_for("main.dashboard", _external=True) + "?pro=error",
            "pending": url_for("main.dashboard", _external=True) + "?pro=pending",
        },
        "auto_return": "approved",
        "notification_url": url_for("payments.webhook", _external=True),
        "external_reference": str(current_user.id),
        "payment_methods": {
            "excluded_payment_types": [
                {"id": "ticket"},
                {"id": "atm"},
                {"id": "digital_currency"},
            ],
            "installments": 1,
        },
    }
    result = sdk.preference().create(preference_data)
    if result["status"] != 201:
        return jsonify({"error": "No se pudo crear el pago."}), 400

    # En prueba usar sandbox_init_point, en producción usar init_point
    is_test = current_app.config.get("MP_IS_TEST", True)
    checkout_url = result["response"]["sandbox_init_point"] if is_test else result["response"]["init_point"]
    return jsonify({"checkout_url": checkout_url})


@pay_bp.route("/webhook", methods=["POST"])
def webhook():
    """MercadoPago notifica aquí cuando ocurre un pago."""
    topic = request.args.get("topic") or request.args.get("type")
    resource_id = request.args.get("id") or request.args.get("data.id")

    if not topic or not resource_id:
        data = request.get_json(silent=True) or {}
        topic = data.get("type")
        resource_id = data.get("data", {}).get("id")

    if topic in ("payment", "merchant_order"):
        sdk = _mp()
        try:
            if topic == "payment":
                payment = sdk.payment().get(resource_id)
                if payment["status"] == 200:
                    p = payment["response"]
                    if p.get("status") == "approved":
                        user_id = p.get("external_reference")
                        if user_id:
                            user = User.query.get(int(user_id))
                            if user:
                                sub = user.get_subscription()
                                sub.plan = "pro"
                                sub.current_period_end = datetime.utcnow() + timedelta(days=31)
                                sub.stripe_subscription_id = str(p.get("id"))
                                db.session.commit()
        except Exception as e:
            current_app.logger.error(f"Error webhook MP: {e}")

    return jsonify({"ok": True})


@pay_bp.route("/success")
@login_required
def payment_success():
    """MercadoPago redirige aquí tras pago exitoso."""
    payment_id = request.args.get("payment_id")
    status = request.args.get("status")
    external_ref = request.args.get("external_reference")

    if status == "approved" and external_ref:
        user = User.query.get(int(external_ref))
        if user and user.id == current_user.id:
            sub = user.get_subscription()
            sub.plan = "pro"
            sub.current_period_end = datetime.utcnow() + timedelta(days=31)
            if payment_id:
                sub.stripe_subscription_id = payment_id
            db.session.commit()

    return redirect(url_for("main.dashboard") + "?pro=1")

@api_bp.route("/pro-stats")
@login_required
def pro_stats_api():
    if not current_user.is_pro:
        return jsonify({"error": "Requiere plan Pro", "upgrade": True}), 403
    token, err, code = _get_token()
    if err:
        return err, code
    ch = current_user.channel
    try:
        from app.services import youtube_pro
        top_videos = youtube_pro.fetch_top_videos_by_views(token, ch.channel_id, 10)
        traffic = youtube_pro.fetch_traffic_sources(token, ch.channel_id, 28)
        comparison = youtube_pro.fetch_period_comparison(token, ch.channel_id, 28)
        retention = youtube_pro.fetch_video_retention(token, ch.channel_id, 5)
        return jsonify({"top_videos": top_videos, "traffic": traffic,
                        "comparison": comparison, "retention": retention})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@main_bp.route("/pro-stats")
@login_required
def pro_stats_page():
    if not current_user.is_pro:
        return redirect(url_for("main.dashboard"))
    sub = current_user.get_subscription()
    return render_template("pro_stats.html", subscription=sub)
