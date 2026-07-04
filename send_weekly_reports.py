"""
Script de reporte semanal — se ejecuta como Cron Job en Render cada lunes.
Envía un resumen de los últimos 7 días a todos los usuarios Pro con canal conectado.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.extensions import db
from app.models import User, Subscription
from app.services import youtube as yt_service
from app.services.email import send_weekly_report

app = create_app(os.environ.get("FLASK_CONFIG", "config.ProductionConfig"))

with app.app_context():
    # Obtener todos los usuarios Pro con canal conectado
    pro_users = (
        db.session.query(User)
        .join(Subscription)
        .filter(Subscription.plan == "pro")
        .all()
    )

    sent = 0
    failed = 0

    for user in pro_users:
        if not user.channel or not user.channel.channel_id:
            continue
        try:
            token = yt_service.get_valid_token(
                user.channel,
                app.config["GOOGLE_CLIENT_ID"],
                app.config["GOOGLE_CLIENT_SECRET"],
            )
            channel_info = yt_service.fetch_channel_info(token)
            analytics = yt_service.fetch_analytics(token, user.channel.channel_id, days=7)
            success = send_weekly_report(user, channel_info, analytics["totals"])
            if success:
                sent += 1
                print(f"✓ Reporte enviado a {user.email}")
            else:
                failed += 1
                print(f"✗ Error enviando a {user.email}")
        except Exception as e:
            failed += 1
            print(f"✗ Error con {user.email}: {e}")

    print(f"\nResumen: {sent} enviados, {failed} fallidos de {len(pro_users)} usuarios Pro")
