from flask import current_app, render_template_string
from flask_mail import Message
from app.extensions import mail


WEEKLY_REPORT_TEMPLATE = """
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family:Inter,sans-serif;background:#0E1116;color:#E6E9EF;padding:2rem;max-width:600px;margin:0 auto;">
  <div style="border-bottom:1px solid #2A313C;padding-bottom:1rem;margin-bottom:1.5rem;">
    <h1 style="font-size:1.4rem;margin:0;color:#5EEAD4;">ChannelIQ</h1>
    <p style="margin:0.25rem 0 0;color:#8A93A3;font-size:0.85rem;">Reporte semanal de tu canal</p>
  </div>

  <h2 style="font-size:1.1rem;">Hola {{ name }},</h2>
  <p style="color:#8A93A3;">Aquí está el resumen de tu canal <strong style="color:#E6E9EF;">{{ channel_name }}</strong> de los últimos 7 días:</p>

  <div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin:1.5rem 0;">
    <div style="background:#161B22;border:1px solid #2A313C;padding:1rem;border-radius:3px;text-align:center;">
      <div style="font-size:1.8rem;font-weight:700;color:#5EEAD4;">{{ views }}</div>
      <div style="font-size:0.8rem;color:#8A93A3;margin-top:0.25rem;">Vistas</div>
    </div>
    <div style="background:#161B22;border:1px solid #2A313C;padding:1rem;border-radius:3px;text-align:center;">
      <div style="font-size:1.8rem;font-weight:700;color:#5EEAD4;">{{ minutes }}</div>
      <div style="font-size:0.8rem;color:#8A93A3;margin-top:0.25rem;">Minutos vistos</div>
    </div>
    <div style="background:#161B22;border:1px solid #2A313C;padding:1rem;border-radius:3px;text-align:center;">
      <div style="font-size:1.8rem;font-weight:700;color:{{ '+' if subs_net >= 0 else '' }}{{ '#5EEAD4' if subs_net >= 0 else '#F87171' }};">{{ '+' if subs_net >= 0 else '' }}{{ subs_net }}</div>
      <div style="font-size:0.8rem;color:#8A93A3;margin-top:0.25rem;">Subs netos</div>
    </div>
    <div style="background:#161B22;border:1px solid #2A313C;padding:1rem;border-radius:3px;text-align:center;">
      <div style="font-size:1.8rem;font-weight:700;color:#5EEAD4;">{{ subscribers }}</div>
      <div style="font-size:0.8rem;color:#8A93A3;margin-top:0.25rem;">Suscriptores totales</div>
    </div>
  </div>

  <a href="https://channeliq.app/dashboard" style="display:inline-block;background:#5EEAD4;color:#06201C;padding:0.75rem 1.5rem;text-decoration:none;font-weight:700;border-radius:3px;margin-top:0.5rem;">
    Ver análisis completo →
  </a>

  <p style="margin-top:2rem;color:#8A93A3;font-size:0.78rem;">
    Recibes este email porque tienes el plan Pro de ChannelIQ.<br>
    <a href="https://channeliq.app/dashboard" style="color:#5EEAD4;">Gestionar suscripción</a>
  </p>
</body>
</html>
"""


def send_weekly_report(user, channel_info, analytics_totals):
    """Envía el reporte semanal por email al usuario Pro."""
    try:
        subs_net = analytics_totals.get("subs_gained", 0) - analytics_totals.get("subs_lost", 0)

        def fmt(n):
            if n >= 1_000_000: return f"{n/1_000_000:.1f}M"
            if n >= 1_000: return f"{n/1_000:.1f}K"
            return str(n)

        html = render_template_string(
            WEEKLY_REPORT_TEMPLATE,
            name=user.name,
            channel_name=channel_info["channel_name"],
            views=fmt(analytics_totals.get("views", 0)),
            minutes=fmt(analytics_totals.get("minutes_watched", 0)),
            subs_net=subs_net,
            subscribers=fmt(channel_info.get("subscriber_count", 0)),
        )

        msg = Message(
            subject=f"📊 Reporte semanal — {channel_info['channel_name']}",
            recipients=[user.email],
            html=html,
        )
        mail.send(msg)
        return True
    except Exception as e:
        current_app.logger.error(f"Error enviando reporte a {user.email}: {e}")
        return False
