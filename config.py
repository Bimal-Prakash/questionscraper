"""Application settings.

Everything is environment-driven so the same checkout runs locally against
SQLite and in production against Neon Postgres with no code change.
See `.env.example` for the full list.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit, urlunsplit

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# pydantic-settings JSON-decodes env values for list-typed fields *before* any
# validator runs, so CORS_ORIGINS=https://a.com,https://b.com would raise
# SettingsError rather than reaching `_split_csv`. NoDecode hands the validator
# the raw string instead. Comma-separated is the only form a hosting
# dashboard's single-line env var field can reasonably express.
CsvList = Annotated[list[str], NoDecode]

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"


def _as_list(value: object) -> list[str]:
    """Accept a real list, a comma-separated env string, or a JSON array."""
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("[") and text.endswith("]"):
            try:
                return _as_list(json.loads(text))
            except json.JSONDecodeError:
                pass
        return [item.strip() for item in text.split(",") if item.strip()]
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _normalize_database_url(url: str) -> str:
    """Make a provider-issued Postgres URL usable by SQLAlchemy + psycopg.

    Hosting dashboards hand out a libpq URL (`postgres://…?sslmode=require`).
    Pasting that verbatim is the most common deploy failure, so rewrite the
    scheme here rather than making every environment get it right. The query
    parameters are left alone on purpose: psycopg is libpq-based and accepts
    `sslmode` and `channel_binding` as given.
    """
    if not url.startswith(("postgres://", "postgresql://")):
        return url
    parts = urlsplit(url)
    return urlunsplit(parts._replace(scheme="postgresql+psycopg"))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---------------------------------------------------------------- app
    app_name: str = "Coding Question Extractor API"
    environment: str = "development"
    log_level: str = "INFO"

    # ----------------------------------------------------------- database
    # SQLite locally; every deployed environment sets DATABASE_URL to Neon,
    # because a free host wipes its disk on each deploy.
    database_url: str = f"sqlite:///{(DATA_DIR / 'questions.db').as_posix()}"

    # ---------------------------------------------------------------- api
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    # When set, the mutating endpoints (extractor start/stop, fetch, delete)
    # require header `X-Admin-Token: <value>`. Empty disables the check, which
    # is what you want locally and never what you want in production.
    admin_token: str = ""
    cors_origins: CsvList = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]
    # Escape hatch for frontends whose hostname is not fixed - preview deploys
    # get a fresh subdomain per branch, which no static list can cover.
    cors_origin_regex: str = ""
    default_page_size: int = 50
    max_page_size: int = 200

    # ---------------------------------------------------------- extractor
    # Polite delay between problem fetches.
    extract_delay_seconds: float = 0.8
    # Start pulling as soon as the API boots. Off on Render free: the instance
    # sleeps after 15 idle minutes, so a background loop there is a stuttering
    # scraper. GitHub Actions runs the real harvest.
    extract_on_startup: bool = False

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> list[str]:
        return _as_list(value)

    @field_validator("database_url", mode="before")
    @classmethod
    def _fix_database_url(cls, value: object) -> object:
        return _normalize_database_url(value) if isinstance(value, str) else value

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgresql")

    @property
    def is_pooled_postgres(self) -> bool:
        """True for a PgBouncer endpoint (Neon and Supabase both mark it '-pooler')."""
        return self.is_postgres and "-pooler." in self.database_url

    @property
    def db_connect_args(self) -> dict:
        if self.is_sqlite:
            # The extractor thread and the request threadpool share the engine.
            return {"timeout": 30, "check_same_thread": False}
        return {}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return Settings()


settings = get_settings()
