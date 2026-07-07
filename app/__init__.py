import os
from flask import Flask
from app.extensions import db, migrate, login_manager, mail


def create_app(config="config.DevelopmentConfig"):
    app = Flask(__name__)
    app.config.from_object(config)

    if app.config.get("DEBUG"):
        os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    mail.init_app(app)

    from app.models import User

    @login_manager.user_loader
    def load_user(uid):
        return User.query.get(int(uid))

    from app.routes import auth_bp, main_bp, yt_bp, api_bp, pay_bp
    for bp in (auth_bp, main_bp, yt_bp, api_bp, pay_bp):
        app.register_blueprint(bp)

    return app
from app.routes.admin import admin_bp
    app.register_blueprint(admin_bp)
    app.config["ADMIN_EMAILS"] = [
        os.environ.get("ADMIN_EMAIL", "trabajon.dante@gmail.com")
    ]
