"""Time helpers for the legacy-naive UTC database schema.

The schema currently stores UTC timestamps in ``TIMESTAMP WITHOUT TIME ZONE``.
Python 3.12 deprecates ``datetime.utcnow()``, so this helper produces the same
naive-UTC representation from a timezone-aware source without changing the
stored data contract during a maintenance release.
"""
from datetime import datetime, timezone


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)
