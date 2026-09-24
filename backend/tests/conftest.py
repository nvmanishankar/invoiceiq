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
    _TMP_DB.unlink(missing_ok=True)
