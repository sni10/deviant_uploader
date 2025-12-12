"""SQLAlchemy Core table definitions for feed auto-fave functionality."""

from sqlalchemy import (
    MetaData,
    Table,
    Column,
    String,
    BigInteger,
    Integer,
    Text,
    DateTime,
    CheckConstraint,
    Index,
    func,
)

metadata = MetaData()

feed_state = Table(
    "feed_state",
    metadata,
    Column("key", String, primary_key=True),
    Column("value", Text, nullable=False),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
)

feed_deviations = Table(
    "feed_deviations",
    metadata,
    Column("deviationid", String, primary_key=True),
    Column("ts", BigInteger, nullable=False),
    Column("status", String, nullable=False, server_default="pending"),
    Column("attempts", Integer, nullable=False, server_default="0"),
    Column("last_error", Text),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    CheckConstraint("status IN ('pending','faved','failed')", name="chk_feed_deviations_status"),
)

Index("idx_feed_deviations_status_ts", feed_deviations.c.status, feed_deviations.c.ts.desc())
