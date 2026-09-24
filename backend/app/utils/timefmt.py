"""Timestamps for the API: always ISO with an explicit UTC offset.

SQLite hands DateTime(timezone=True) columns back naive; every value we store is UTC, so naive means UTC.
The frontend turns the offset into the viewer's local time.
"""

from datetime import date, datetime, timezone


def as_utc(v: datetime) -> datetime:
    return v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v.astimezone(timezone.utc)


def iso(v: datetime | date | None) -> str | None:
    """datetime → '2026-09-24T08:15:00+00:00'; a plain date stays '2026-09-24'."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return as_utc(v).isoformat()
    return v.isoformat()
