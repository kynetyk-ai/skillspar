"""Utility functions for date formatting and validation."""

from datetime import datetime, timezone


def format_iso(dt: datetime) -> str:
    """Format a datetime as an ISO 8601 string in UTC."""
    utc_dt = dt.astimezone(timezone.utc)
    return utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s: str) -> datetime:
    """Parse an ISO 8601 string into a timezone-aware datetime."""
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def days_between(start: datetime, end: datetime) -> int:
    """Return the number of whole days between two datetimes."""
    delta = end - start
    return abs(delta.days)
