"""SQLAlchemy Core table definitions for profile message broadcasting."""

from sqlalchemy import (
    MetaData,
    Table,
    Column,
    String,
    Integer,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
    CheckConstraint,
    Index,
    func,
)

metadata = MetaData()

watchers = Table(
    "watchers",
    metadata,
    Column("watcher_id", Integer, primary_key=True, autoincrement=True),
    Column("username", String(100), nullable=False, unique=True),
    Column("userid", String(100), nullable=False),
    Column("fetched_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
)

profile_messages = Table(
    "profile_messages",
    metadata,
    Column("message_id", Integer, primary_key=True, autoincrement=True),
    Column("title", String(200), nullable=False),
    Column("body", Text, nullable=False),
    Column("is_active", Boolean, nullable=False, server_default="1"),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False),
)

profile_message_logs = Table(
    "profile_message_logs",
    metadata,
    Column("log_id", Integer, primary_key=True, autoincrement=True),
    Column("message_id", Integer, ForeignKey("profile_messages.message_id"), nullable=False),
    Column("recipient_username", String(100), nullable=False),
    Column("recipient_userid", String(100), nullable=False),
    Column("commentid", String(100)),  # DeviantArt comment UUID
    Column("status", String(20), nullable=False),
    Column("error_message", Text),
    Column("sent_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    CheckConstraint("status IN ('sent','failed')", name="chk_profile_message_logs_status"),
)

# Indexes for efficient queries
Index("idx_watchers_username", watchers.c.username)
Index("idx_profile_message_logs_message_id", profile_message_logs.c.message_id)
Index("idx_profile_message_logs_status", profile_message_logs.c.status)
Index("idx_profile_message_logs_recipient", profile_message_logs.c.recipient_username)
