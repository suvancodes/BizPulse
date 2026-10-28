import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv(".env")
load_dotenv(".env.local", override=False)


class ConfigurationError(RuntimeError):
    """Raised when required application configuration is missing."""


@dataclass(frozen=True)
class SupabaseConfig:
    url: str
    publishable_key: str


def get_flask_secret_key() -> str:
    secret_key = os.environ.get("FLASK_SECRET_KEY", "").strip()
    if len(secret_key) < 32:
        raise ConfigurationError(
            "FLASK_SECRET_KEY must be configured with at least 32 characters."
        )
    return secret_key


def get_supabase_config() -> SupabaseConfig:
    url = os.environ.get("SUPABASE_URL", "").strip()
    publishable_key = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "").strip()

    missing = []
    if not url:
        missing.append("SUPABASE_URL")
    if not publishable_key:
        missing.append("SUPABASE_PUBLISHABLE_KEY")

    if missing:
        raise ConfigurationError(
            "Missing required environment variable(s): "
            + ", ".join(missing)
            + ". Configure them locally or in the Vercel project settings."
        )

    if not url.startswith(("https://", "http://")):
        raise ConfigurationError("SUPABASE_URL must be an HTTP(S) URL.")

    return SupabaseConfig(
        url=url.rstrip("/"),
        publishable_key=publishable_key,
    )
