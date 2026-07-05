import json
import io
from datetime import datetime, timedelta

import requests
import stripe
from flask import (Blueprint, redirect, url_for, session, current_app,
                   request, jsonify, render_template, send_file)
from flask_login import login_user, logout_user, login_required, current_user
from oauthlib.oauth2 import WebApplicationClient

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
    return redirect(url_for("main.dashboard"))


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
                           stripe_public_key=current_app.config["STRIPE_PUBLIC_KEY"])


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


def _stripe():
    stripe.api_key = current_app.config["STRIPE_SECRET_KEY"]


@pay_bp.route("/checkout-pro", methods=["POST"])
@login_required
def checkout_pro():
    _stripe()
    try:
        session_obj = stripe.checkout.Session.create(
            payment_method_types=["card"],
            payment_method_options={
                "card": {"request_three_d_secure": "automatic"}
            },
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": "ChannelIQ Pro — Suscripción mensual"},
                    "unit_amount": current_app.config["STRIPE_PRO_PRICE_CENTS"],
                    "recurring": {"interval": "month"},
                },
                "quantity": 1,
            }],
            mode="subscription",
            success_url=url_for("main.dashboard", _external=True) + "?pro=1",
            cancel_url=url_for("main.dashboard", _external=True),
            metadata={"user_id": current_user.id},
        )
    except stripe.error.StripeError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"checkout_url": session_obj.url})


@pay_bp.route("/webhook", methods=["POST"])
def webhook():
    _stripe()
    payload = request.data
    sig = request.headers.get("Stripe-Signature")
    try:
        event = stripe.Webhook.construct_event(
            payload, sig, current_app.config["STRIPE_WEBHOOK_SECRET"])
    except Exception:
        return jsonify({"error": "Invalid signature"}), 400

    if event["type"] in ("checkout.session.completed", "invoice.paid"):
        obj = event["data"]["object"]
        user_id = obj.get("metadata", {}).get("user_id")
        if user_id:
            user = User.query.get(int(user_id))
            if user:
                sub = user.get_subscription()
                sub.plan = "pro"
                sub.stripe_subscription_id = obj.get("subscription")
                sub.stripe_customer_id = obj.get("customer")
                sub.current_period_end = datetime.utcnow() + timedelta(days=31)
                db.session.commit()

    elif event["type"] == "customer.subscription.deleted":
        obj = event["data"]["object"]
        sub = Subscription.query.filter_by(
            stripe_subscription_id=obj["id"]).first()
        if sub:
            sub.plan = "free"
            sub.current_period_end = None
            db.session.commit()

    return jsonify({"ok": True})
