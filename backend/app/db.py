"""Engine, session and Base. Same code for SQLite (local) and Postgres (Neon)."""

from collections.abc import Iterator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        eng = create_engine(url, connect_args={"check_same_thread": False})

        @event.listens_for(eng, "connect")
        def _pragmas(dbapi_conn, _):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            # WAL: the SSE reader and the pipeline writer don't block each other.
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()

        return eng
    return create_engine(url, pool_pre_ping=True)


engine = make_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db(bind: Engine | None = None) -> None:
    from app import models  # noqa: F401  (registers tables on Base.metadata)

    bind = bind or engine
    Base.metadata.create_all(bind)
    _add_missing_columns(bind)


def _add_missing_columns(bind: Engine) -> None:
    """create_all makes new tables but never new columns. A nullable column added to a model since the database was
    created is added here, so an existing database (Neon) keeps working without a migration tool."""
    have = inspect(bind)
    with bind.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not have.has_table(table.name):
                continue
            existing = {c["name"] for c in have.get_columns(table.name)}
            for col in table.columns:
                if col.name not in existing and col.nullable and col.server_default is None:
                    kind = col.type.compile(dialect=bind.dialect)
                    conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN "{col.name}" {kind}'))


def get_db() -> Iterator[Session]:
    with SessionLocal() as db:
        yield db
