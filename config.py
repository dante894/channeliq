import os
from datetime import timedelta

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-production")

    # Base de datos
    _db_url = os.environ.get("DATABASE_URL", f"sqlite:///{os.path.join(basedir, 'app.db')}")
    if _db_url.startswith("postgres://"):
        _db_url = _db_url.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_DATABASE_URI = _db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Google OAuth
    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"

    # MercadoPago Argentina
    MP_ACCESS_TOKEN = os.environ.get("MP_ACCESS_TOKEN", "")
    MP_PUBLIC_KEY = os.environ.get("MP_PUBLIC_KEY", "")
    MP_PRO_PRICE_ARS = int(os.environ.get("MP_PRO_PRICE_ARS", "15000"))  # $15.000 ARS/mes
    MP_IS_TEST = os.environ.get("MP_IS_TEST", "true").lower() == "true"

    # Planes
    FREE_DAYS = 7
    PRO_DAYS = 28
    FREE_VIDEOS = 5
    PRO_VIDEOS = 50

    # Email (para reportes semanales)
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "noreply@channeliq.app")


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False
