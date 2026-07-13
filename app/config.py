"""Application configuration.

All runtime configuration is read from environment variables (optionally
via a local .env file) so the same image can move from dev -> staging ->
prod with no code change — see .env.example for the supported keys.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed, validated application settings.

    Field names are lower_snake_case; pydantic-settings matches them to
    the upper-case environment variables of the same name (e.g.
    ``database_url`` <- ``DATABASE_URL``) case-insensitively.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Identity ---
    app_name: str = "TradeEdge AI Backend"
    app_version: str = "7.0.0"

    # --- Environment ---
    app_env: str = "dev"  # dev | staging | prod
    log_level: str = "INFO"

    # --- Security ---
    secret_key: str = "dev-only-change-me"

    # --- Database (wired up in Step 2 — accepted here so config is stable) ---
    database_url: str = "sqlite+aiosqlite:///./data/tradeedge.db"

    # --- CORS ---
    cors_origins: list[str] = ["*"]
    # Audit finding: the app was pairing allow_origins=["*"] with
    # allow_credentials=True in app/main.py. That combination is a
    # well-known CORS misconfiguration — browsers forbid wildcard
    # origins alongside credentialed requests, so CORSMiddleware
    # quietly echoes back whatever Origin header the request sent
    # instead, which defeats the purpose of an origin allowlist. This
    # app authenticates via a plain header (X-User-Id, see app/deps.py),
    # not cookies, so it never actually needed allow_credentials=True.
    # Defaults to False; only turn this on together with a real,
    # non-wildcard cors_origins list.
    cors_allow_credentials: bool = False

    # --- ML dataset exports ---
    export_dir: str = "./data/exports"

    # --- Sprint 7: trained model artifacts (joblib) ---
    models_dir: str = "./data/models"

    # --- Sprint 10: Chart Analysis Engine — vision AI (optional) ---
    # When unset, the chart screenshot-reading path automatically falls
    # back to PlaceholderVisionProvider (app/chart/vision_provider.py).
    # Set this (e.g. as a Render env var) to switch on real Claude
    # vision analysis with zero code changes.
    anthropic_api_key: str | None = None

    # --- Sprint 12: Market Context Filters — news/economic calendar (optional) ---
    # When unset, the news filter automatically falls back to
    # PlaceholderCalendarProvider (app/news/calendar_provider.py). Set
    # this (e.g. as a Render env var) to switch on real economic
    # calendar data via Finnhub's free tier with zero code changes.
    # Get a free key at https://finnhub.io/register.
    finnhub_api_key: str | None = None

    @property
    def is_dev(self) -> bool:
        return self.app_env.lower() == "dev"


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton — env vars are read once per process."""
    return Settings()
