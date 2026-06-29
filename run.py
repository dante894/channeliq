import os
from app import create_app
from app.extensions import db

config = os.environ.get("FLASK_CONFIG", "config.DevelopmentConfig")
app = create_app(config)

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
