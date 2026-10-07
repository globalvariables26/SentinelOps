"""Time utilities for SentinelOps.
Always use utcnow() to ensure timezone-naive UTC timestamps across SQLite and Postgres.
"""
from datetime import datetime, timezone


def utcnow() -> datetime:
    """Return timezone-naive UTC timestamp."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
