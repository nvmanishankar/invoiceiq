"""Environment settings (build guide section 4)."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    # Later files win: backend/.env overrides the repo-root .env.
    model_config = SettingsConfigDict(
        env_file=(REPO_DIR / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str = "sqlite:///./invoiceiq.db"

    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = ""
    GEMINI_MODEL_FALLBACK: str = ""

    RESEND_API_KEY: str = ""
    EMAIL_FROM: str = "InvoiceIQ <onboarding@resend.dev>"
    OWNER_EMAIL: str = "nvmanishankar@gmail.com"

    BASE_URL: str = "http://localhost:8000"
    MAX_RUNS_PER_DAY: int = 60
    VENDOR_AUTO_SEND: bool = True
    MIN_STAGE_MS: int = 400


settings = Settings()
