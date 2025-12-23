"""SQLAlchemy Core table definitions for deviation auto-commenting."""

from sqlalchemy import (
    MetaData,
    Table,
    Column,
    String,
    Integer,
    BigInteger,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
    CheckConstraint,
    Index,
    func,
)

metadata = MetaData()

deviation_comment_messages = Table(
    "deviation_comment_messages",
    metadata,
    Column("message_id", Integer, primary_key=True, autoincrement=True),
    Column("title", String(200), nullable=False),
    Column("body", Text, nullable=False),
    Column("is_active", Boolean, nullable=False, server_default="1"),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column(
        "updated_at",
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    ),
)

deviation_comment_queue = Table(
    "deviation_comment_queue",
    metadata,
    Column("deviationid", String(100), primary_key=True),
    Column("deviation_url", Text),
    Column("title", String(200)),
    Column("author_username", String(100)),
    Column("author_userid", String(100)),
    Column("source", String(50), nullable=False),
    Column("ts", BigInteger, nullable=False),
    Column("status", String(20), nullable=False, server_default="pending"),
    Column("attempts", Integer, nullable=False, server_default="0"),
    Column("last_error", Text),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column(
        "updated_at",
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    ),
    CheckConstraint(
        "status IN ('pending','commented','failed')",
        name="chk_deviation_comment_queue_status",
    ),
)

deviation_comment_logs = Table(
    "deviation_comment_logs",
    metadata,
    Column("log_id", Integer, primary_key=True, autoincrement=True),
    Column(
        "message_id",
        Integer,
        ForeignKey("deviation_comment_messages.message_id"),
        nullable=False,
    ),
    Column("deviationid", String(100), nullable=False),
    Column("deviation_url", Text),
    Column("author_username", String(100)),
    Column("commentid", String(100)),
    Column("comment_text", Text),
    Column("status", String(20), nullable=False),
    Column("error_message", Text),
    Column("sent_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    CheckConstraint(
        "status IN ('sent','failed')",
        name="chk_deviation_comment_logs_status",
    ),
)

deviation_comment_state = Table(
    "deviation_comment_state",
    metadata,
    Column("key", String, primary_key=True),
    Column("value", Text, nullable=False),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
)

Index("idx_deviation_comment_queue_status", deviation_comment_queue.c.status)
Index("idx_deviation_comment_queue_ts", deviation_comment_queue.c.ts.desc())
Index("idx_deviation_comment_queue_deviationid", deviation_comment_queue.c.deviationid)
Index("idx_deviation_comment_queue_source", deviation_comment_queue.c.source)
Index("idx_deviation_comment_logs_deviationid", deviation_comment_logs.c.deviationid)
Index("idx_deviation_comment_logs_status", deviation_comment_logs.c.status)
Index("idx_deviation_comment_logs_message_id", deviation_comment_logs.c.message_id)
