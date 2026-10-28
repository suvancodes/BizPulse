import os

from flask import Flask

from backend.auth import register_auth_routes
from backend.config import get_flask_secret_key
from routes import register_routes


app = Flask(__name__)
app.config.update(
    SECRET_KEY=get_flask_secret_key(),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("VERCEL") == "1",
)
register_auth_routes(app)
register_routes(app)


if __name__ == "__main__":
    app.run(debug=True)
