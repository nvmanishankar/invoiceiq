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
    SEND_EMAILS: bool = True  # false: alerts are stored as Drafted and nothing goes to Resend
    MIN_STAGE_MS: int = 400


settings = Settings()


# --- Rule constants (build guide section 9). Tune these with the test suite. ---

MAX_LLM_CALLS_PER_RUN = 2  # extraction + description similarity

# Stage 5: PO inference scoring. Weights add up to 100.
PO_WEIGHT_LINES = 50
PO_WEIGHT_AMOUNT = 30
PO_WEIGHT_DATE = 20
PO_DATE_WINDOW_DAYS = 60  # date score falls to 0 this many days after the PO date
# Each paired line earns: similarity * SIM share + qty ok * QTY share + price ok * PRICE share.
PO_LINE_SHARE_SIM = 0.5
PO_LINE_SHARE_QTY = 0.25
PO_LINE_SHARE_PRICE = 0.25
PO_DESC_MIN_SIM = 0.6  # below this a line pair doesn't count
PO_MATCH_MIN_SCORE = 70  # top score needed to auto-match
PO_MATCH_MIN_GAP = 20  # lead over the runner-up needed to auto-match

# Stage 3 and 8: printed arithmetic may be off by rounding, up to Rs 1.
MATHS_TOLERANCE_PAISE = 100

# Stage 7
NEAR_DUPLICATE_DAYS = 30

# Stage 9
DEFAULT_TERMS_DAYS = 30  # when no PO is matched
MSME_MAX_TERMS_DAYS = 45
STALE_INVOICE_DAYS = 180
