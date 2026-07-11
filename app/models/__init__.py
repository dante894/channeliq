from datetime import datetime
from flask_login import UserMixin
from app.extensions import db


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    google_id = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    name = db.Column(db.String(255))
    avatar_url = db.Column(db.String(512))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login_at = db.Column(db.DateTime, default=datetime.utcnow)

    channel = db.relationship("YouTubeChannel", backref="user", uselist=False, cascade="all, delete-orphan")
    subscription = db.relationship("Subscription", backref="user", uselist=False, cascade="all, delete-orphan")

    def get_subscription(self):
        if not self.subscription:
            sub = Subscription(user_id=self.id)
            db.session.add(sub)
            db.session.commit()
            return sub
        return self.subscription

    @property
    def is_pro(self):
        sub = self.subscription
        if not sub:
            return False
        return sub.is_pro


class YouTubeChannel(db.Model):
    __tablename__ = "youtube_channels"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)

    access_token = db.Column(db.Text)
    refresh_token = db.Column(db.Text)
    token_expiry = db.Column(db.DateTime)

    channel_id = db.Column(db.String(64))
    channel_name = db.Column(db.String(255))
    channel_thumbnail = db.Column(db.String(512))
    subscriber_count = db.Column(db.Integer, default=0)
    video_count = db.Column(db.Integer, default=0)
    view_count = db.Column(db.Integer, default=0)

    connected_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_synced_at = db.Column(db.DateTime)

    def is_token_expired(self):
        if not self.token_expiry:
            return True
        return datetime.utcnow() >= self.token_expiry

    def to_dict(self):
        return {
            "channel_id": self.channel_id,
            "channel_name": self.channel_name,
            "channel_thumbnail": self.channel_thumbnail,
            "subscriber_count": self.subscriber_count,
            "video_count": self.video_count,
            "view_count": self.view_count,
            "connected": bool(self.channel_id),
            "last_synced_at": self.last_synced_at.isoformat() if self.last_synced_at else None,
        }


class PageView(db.Model):
    __tablename__ = "page_views"
    id = db.Column(db.Integer, primary_key=True)
    path = db.Column(db.String(255), nullable=False, index=True)
    referrer = db.Column(db.String(512))
    referrer_host = db.Column(db.String(255), index=True)
    user_agent = db.Column(db.String(512))
    device = db.Column(db.String(16))  # mobile | tablet | desktop | bot
    ip_address = db.Column(db.String(45))  # IPv4/IPv6 con el último octeto/segmento enmascarado
    visitor_key = db.Column(db.String(64), index=True)  # hash diario para contar únicos sin guardar IP completa
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    user = db.relationship("User")


class Subscription(db.Model):
    __tablename__ = "subscriptions"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)

    plan = db.Column(db.String(16), default="free", nullable=False)
    stripe_subscription_id = db.Column(db.String(255))
    stripe_customer_id = db.Column(db.String(255))
    current_period_end = db.Column(db.DateTime)
    cancel_at_period_end = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def is_pro(self):
        if self.plan != "pro":
            return False
        if self.current_period_end and self.current_period_end < datetime.utcnow():
            return False
        return True

    def to_dict(self):
        return {
            "plan": self.plan,
            "is_pro": self.is_pro,
            "current_period_end": self.current_period_end.isoformat() if self.current_period_end else None,
            "cancel_at_period_end": self.cancel_at_period_end,
        }
