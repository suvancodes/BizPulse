import base64
import hashlib
import json
import secrets
from functools import wraps
from typing import Any, Callable
from urllib.parse import urlparse

import httpx
from cryptography.fernet import Fernet, InvalidToken
from flask import (
    Flask,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from supabase import create_client
from supabase_auth.errors import AuthApiError

from backend.config import get_supabase_config
from backend.config import get_flask_secret_key


AUTH_SESSION_KEY = "supabase_session"
CSRF_SESSION_KEY = "csrf_token"


def register_auth_routes(app: Flask) -> None:
    @app.context_processor
    def inject_auth_context() -> dict[str, Any]:
        return {
            "current_user": getattr(g, "current_user", None),
            "csrf_token": get_csrf_token(),
        }

    @app.before_request
    def restore_auth_session() -> None:
        g.current_user = None
        g.supabase_client = None
        stored_session = session.get(AUTH_SESSION_KEY)
        if not stored_session:
            return

        try:
            stored_session = unseal_session(stored_session)
            client = get_supabase_client()
            response = client.auth.set_session(
                stored_session["access_token"],
                stored_session["refresh_token"],
            )
            if response.session is None or response.user is None:
                session.pop(AUTH_SESSION_KEY, None)
                return

            session[AUTH_SESSION_KEY] = seal_session(
                session_to_dict(response.session)
            )
            g.current_user = response.user
        except (
            AuthApiError,
            AttributeError,
            InvalidToken,
            KeyError,
            TypeError,
            ValueError,
            httpx.RequestError,
        ):
            session.pop(AUTH_SESSION_KEY, None)

    @app.route("/auth/register", methods=["GET", "POST"])
    def auth_register():
        if g.current_user is not None:
            return redirect(url_for("dashboard_page"))

        if request.method == "POST":
            error = validate_csrf_token()
            if error:
                return render_template("register.html", error=error), 400

            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            confirm_password = request.form.get("confirm_password", "")

            if not email or not password:
                return render_template(
                    "register.html",
                    error="Email and password are required.",
                    email=email,
                ), 400
            if len(password) < 8:
                return render_template(
                    "register.html",
                    error="Password must be at least 8 characters.",
                    email=email,
                ), 400
            if password != confirm_password:
                return render_template(
                    "register.html",
                    error="Passwords do not match.",
                    email=email,
                ), 400

            try:
                response = get_supabase_client().auth.sign_up({
                    "email": email,
                    "password": password,
                })
            except (AuthApiError, httpx.RequestError) as exc:
                return render_template(
                    "register.html",
                    error=auth_error_message(exc),
                    email=email,
                ), 400

            if response.session is None:
                return render_template(
                    "login.html",
                    message=(
                        "Account created. You can now sign in with your "
                        "email and password."
                    ),
                )

            store_auth_session(response.session)
            return redirect(url_for("dashboard_page"))

        return render_template("register.html")

    @app.route("/auth/login", methods=["GET", "POST"])
    def auth_login():
        if g.current_user is not None:
            return redirect(url_for("dashboard_page"))

        if request.method == "POST":
            error = validate_csrf_token()
            if error:
                return render_template("login.html", error=error), 400

            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            if not email or not password:
                return render_template(
                    "login.html",
                    error="Email and password are required.",
                    email=email,
                ), 400

            try:
                response = get_supabase_client().auth.sign_in_with_password({
                    "email": email,
                    "password": password,
                })
            except (AuthApiError, httpx.RequestError) as exc:
                return render_template(
                    "login.html",
                    error=auth_error_message(exc),
                    email=email,
                ), 401

            if response.session is None:
                return render_template(
                    "login.html",
                    error="The login session could not be created.",
                    email=email,
                ), 401

            store_auth_session(response.session)
            return redirect(
                safe_next_url(
                    request.form.get("next") or request.args.get("next")
                )
            )

        return render_template(
            "login.html",
            next_url=safe_next_url(request.args.get("next")),
        )

    @app.route("/auth/logout", methods=["POST"])
    def auth_logout():
        error = validate_csrf_token()
        if error:
            flash(error, "error")
            return redirect(url_for("dashboard_page"))

        stored_session = session.get(AUTH_SESSION_KEY)
        if stored_session:
            try:
                stored_session = unseal_session(stored_session)
                client = get_supabase_client()
                client.auth.set_session(
                    stored_session["access_token"],
                    stored_session["refresh_token"],
                )
                client.auth.sign_out()
            except (
                AuthApiError,
                AttributeError,
                InvalidToken,
                KeyError,
                TypeError,
                ValueError,
                httpx.RequestError,
            ):
                flash(
                    "The Supabase session could not be revoked remotely. "
                    "The local session was cleared.",
                    "error",
                )

        session.clear()
        return redirect(url_for("auth_login"))

    @app.route("/auth/forgot-password", methods=["GET", "POST"])
    def auth_forgot_password():
        if request.method == "POST":
            error = validate_csrf_token()
            if error:
                return render_template("forgot_password.html", error=error), 400

            email = request.form.get("email", "").strip().lower()
            if not email:
                return render_template(
                    "forgot_password.html",
                    error="Email is required.",
                ), 400

            try:
                get_supabase_client().auth.reset_password_for_email(
                    email,
                    options={
                        "redirect_to": url_for(
                            "auth_reset_password",
                            _external=True,
                        ),
                    },
                )
            except (AuthApiError, httpx.RequestError) as exc:
                return render_template(
                    "forgot_password.html",
                    error=auth_error_message(exc),
                    email=email,
                ), 400

            return render_template(
                "forgot_password.html",
                message=(
                    "If an account exists for that email, a password reset "
                    "link has been sent."
                ),
            )

        return render_template("forgot_password.html")

    @app.route("/auth/reset-password")
    def auth_reset_password():
        return render_template(
            "reset_password.html",
            supabase_config=get_supabase_config(),
        )


def get_supabase_client():
    cached_client = getattr(g, "supabase_client", None)
    if cached_client is not None:
        return cached_client

    config = get_supabase_config()
    client = create_client(config.url, config.publishable_key)
    g.supabase_client = client
    return client


def login_required(view: Callable) -> Callable:
    @wraps(view)
    def wrapped_view(*args: Any, **kwargs: Any):
        if getattr(g, "current_user", None) is None:
            next_url = request.full_path.rstrip("?")
            return redirect(url_for("auth_login", next=next_url))
        return view(*args, **kwargs)

    return wrapped_view


def get_csrf_token() -> str:
    token = session.get(CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[CSRF_SESSION_KEY] = token
    return token


def validate_csrf_token() -> str | None:
    submitted = request.form.get("csrf_token", "")
    return validate_csrf_value(submitted)


def validate_csrf_request() -> str | None:
    submitted = (
        request.headers.get("X-CSRF-Token")
        or request.form.get("csrf_token", "")
    )
    return validate_csrf_value(submitted)


def validate_csrf_value(submitted: str) -> str | None:
    expected = session.get(CSRF_SESSION_KEY, "")
    if not expected or not secrets.compare_digest(submitted, expected):
        return "Your session expired. Please refresh the page and try again."
    return None


def store_auth_session(auth_session: Any) -> None:
    session[AUTH_SESSION_KEY] = seal_session(session_to_dict(auth_session))
    session.permanent = True


def session_to_dict(auth_session: Any) -> dict[str, str]:
    return {
        "access_token": auth_session.access_token,
        "refresh_token": auth_session.refresh_token,
    }


def session_cipher() -> Fernet:
    key = hashlib.sha256(
        get_flask_secret_key().encode("utf-8")
    ).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def seal_session(auth_session: dict[str, str]) -> str:
    return session_cipher().encrypt(
        json.dumps(auth_session, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")


def unseal_session(value: str) -> dict[str, str]:
    decrypted = session_cipher().decrypt(value.encode("ascii"))
    session_data = json.loads(decrypted.decode("utf-8"))
    if not isinstance(session_data, dict):
        raise ValueError("Invalid Supabase session payload.")
    return session_data


def auth_error_message(error: Exception) -> str:
    if isinstance(error, httpx.RequestError):
        return (
            "BizPulse could not connect to Supabase. Check your internet "
            "connection and SUPABASE_URL, then try again."
        )

    error_code = getattr(error, "code", None)
    error_message = str(error).strip().lower()
    if (
        error_code in {
            "over_email_send_rate_limit",
            "email_rate_limit_exceeded",
        }
        or "rate limit" in error_message
    ):
        return (
            "Supabase temporarily limited email sending. Wait a few minutes "
            "before trying again, or configure a custom SMTP provider in "
            "Supabase Auth."
        )
    if error_code == "invalid_credentials":
        return (
            "Email or password is incorrect. Please try again."
        )
    message = str(error).strip()
    return message or "Authentication failed. Please try again."


def safe_next_url(value: str | None) -> str:
    if not value:
        return url_for("dashboard_page")

    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc or not value.startswith("/"):
        return url_for("dashboard_page")
    return value
