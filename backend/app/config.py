from functools import lru_cache
from typing import Literal
from urllib.parse import urlparse

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_JWT_SECRET = "change-me-in-production"
MIN_JWT_SECRET_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["development", "production"] = "development"
    # "json" writes one JSON object per log line for log aggregation; "text" is for humans.
    log_format: Literal["text", "json"] = "text"
    sentry_dsn: str | None = None

    database_url: str = "sqlite:///./lime_events.db"

    jwt_secret: str = DEFAULT_JWT_SECRET
    jwt_expire_minutes: int = 8 * 60

    ticketmaster_api_key: str | None = None
    predicthq_token: str | None = None

    # Cron expression in Europe/Berlin time; default is daily at 03:00.
    ingest_cron: str = "0 3 * * *"
    ingest_days_ahead: int = 90
    # Run the scheduler inside the API process. Production runs it in the separate
    # worker service instead (python -m app.cli scheduler) and sets this to false.
    scheduler_enabled: bool = True
    # /api/health/ingest reports unhealthy when the last successful sync is older than this.
    ingest_max_age_hours: int = 36
    # Events that ended longer ago than this are deleted by the nightly job.
    event_retention_days: int = 365
    # Slack-compatible incoming webhook; receives a message when a sync fails or finds nothing.
    alert_webhook_url: str | None = None

    # First admin, created by `init-db` (which runs on every container start) only while
    # the database has no users at all. Lets `docker compose up` produce a usable app in one go.
    admin_email: str | None = None
    admin_password: str | None = None

    timezone: str = "Europe/Berlin"
    city_lat: float = 48.7758
    city_lng: float = 9.1829
    city_radius_km: int = 25

    # Share of event attendees expected to want a scooter trip.
    scooter_share: float = 0.005
    max_scooters_per_spot: int = 150
    # 600 m groups MHPArena, Porsche-Arena and Schleyerhalle into one NeckarPark hotspot.
    hotspot_radius_m: int = 600

    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:8080"]

    # AI assistant. Any OpenAI-compatible Chat Completions endpoint works: Groq (default,
    # free tier), Google Gemini, Hugging Face, or a local Ollama. See .env.example.
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_model: str = "openai/gpt-oss-120b"
    llm_api_key: str | None = None
    # Upper bound on tool-call round trips per question, so a confused model can't loop.
    llm_max_tool_rounds: int = 6
    llm_timeout_seconds: float = 60

    @property
    def llm_is_local(self) -> bool:
        host = urlparse(self.llm_base_url).hostname or ""
        return host in ("localhost", "127.0.0.1", "::1") or host.endswith(".localhost")

    @property
    def llm_enabled(self) -> bool:
        """Local servers (Ollama) need no key; hosted providers do."""
        return bool(self.llm_api_key) or self.llm_is_local

    @property
    def llm_provider(self) -> str:
        host = urlparse(self.llm_base_url).hostname or ""
        for marker, name in (("groq", "Groq"), ("googleapis", "Google Gemini"),
                             ("huggingface", "Hugging Face"), ("openai.com", "OpenAI")):
            if marker in host:
                return name
        return "Ollama (local)" if self.llm_is_local else host

    def production_problems(self) -> list[str]:
        """Config that is acceptable for development but must not reach production."""
        problems = []
        if self.jwt_secret == DEFAULT_JWT_SECRET or len(self.jwt_secret) < MIN_JWT_SECRET_LENGTH:
            problems.append(f"JWT_SECRET must be a random string of at least {MIN_JWT_SECRET_LENGTH} characters")
        if self.database_url.startswith("sqlite"):
            problems.append("DATABASE_URL must point to PostgreSQL, not SQLite")
        return problems

    def check_production(self) -> None:
        """Raise on unsafe config when ENVIRONMENT=production. Called at startup by the API and the worker."""
        if self.environment == "production" and (problems := self.production_problems()):
            raise RuntimeError("Refusing to start with unsafe production config: " + "; ".join(problems))


@lru_cache
def get_settings() -> Settings:
    return Settings()
