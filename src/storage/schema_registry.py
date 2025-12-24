"""Schema registry for SQLAlchemy metadata collections."""

from __future__ import annotations

from typing import Iterable

from .deviation_comment_tables import metadata as deviation_comment_metadata
from .feed_tables import metadata as feed_metadata
from .models import Base
from .profile_message_tables import metadata as profile_message_metadata

CORE_METADATA = (
    feed_metadata,
    profile_message_metadata,
    deviation_comment_metadata,
)

ORM_METADATA = Base.metadata


def iter_metadata() -> Iterable[object]:
    """Yield ORM and Core metadata in creation order."""

    yield ORM_METADATA
    for metadata in CORE_METADATA:
        yield metadata
