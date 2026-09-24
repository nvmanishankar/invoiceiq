import os
import sys
from pathlib import Path

import pytest

# Point the app at a throwaway SQLite file before anything imports app.config.
_TMP_DB = Path(__file__).resolve().parent / ".test_app.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB}"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import Session  # noqa: E402

from app.db import make_engine  # noqa: E402
from app.seed import reset  # noqa: E402


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """Tests never reach Gemini: no key, and both model calls fail loudly if reached anyway."""
    from app import llm
    from app.config import settings

    def boom(*a, **k):
        raise AssertionError("network call attempted")

    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
    monkeypatch.setattr(llm, "_call_model", boom)
    monkeypatch.setattr(llm, "_call_similarity_model", boom)


@pytest.fixture(autouse=True)
def emails(monkeypatch):
    """Tests never reach Resend. Every email that would have gone out is recorded here instead."""
    from app import alerts
    from app.config import settings

    sent: list[dict] = []

    def record(subject: str, body: str) -> str:
        sent.append({"subject": subject, "body": body})
        return f"test-{len(sent)}"

    monkeypatch.setattr(settings, "RESEND_API_KEY", "")
    monkeypatch.setattr(settings, "SEND_EMAILS", True)
    monkeypatch.setattr(settings, "VENDOR_AUTO_SEND", True)
    monkeypatch.setattr(alerts, "_send_email", record)
    return sent


@pytest.fixture
def engine():
    eng = make_engine("sqlite://")  # fresh in-memory DB per test
    reset(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine):
    with Session(engine) as s:
        yield s


def pytest_sessionfinish(session, exitstatus):
    for suffix in ("", "-wal", "-shm"):
        Path(f"{_TMP_DB}{suffix}").unlink(missing_ok=True)
