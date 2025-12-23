#!/usr/bin/env python3
"""Apply migrations to PostgreSQL main schema."""

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import create_engine, text
from src.storage.models import Base
from src.storage.feed_tables import metadata as feed_metadata
from src.storage.profile_message_tables import metadata as profile_message_metadata


def main():
    """Apply all migrations to PostgreSQL main schema."""
    # PostgreSQL connection URL
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/deviant"
    )

    print(f"Connecting to PostgreSQL: {database_url}")

    # Create engine with schema configuration
    engine = create_engine(database_url, echo=False)

    # Set search_path to main schema
    with engine.connect() as conn:
        conn.execute(text("SET search_path TO main"))
        conn.commit()

    print("\nApplying migrations to schema 'main'...")

    # Set schema for all metadata objects
    Base.metadata.schema = 'main'
    feed_metadata.schema = 'main'
    profile_message_metadata.schema = 'main'

    print("  - Creating tables from models.py (Base.metadata)")
    Base.metadata.create_all(engine)

    print("  - Creating tables from feed_tables.py")
    feed_metadata.create_all(engine)

    print("  - Creating tables from profile_message_tables.py")
    profile_message_metadata.create_all(engine)

    print("\n✓ Migrations applied successfully!")

    # Verify tables were created in main schema
    print("\nVerifying tables in schema 'main'...")
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'main'
            ORDER BY table_name
        """))

        tables = [row[0] for row in result.fetchall()]

    print(f"\nCreated {len(tables)} tables in schema 'main':")
    for table_name in tables:
        print(f"  ✓ {table_name}")

    print("\n🎉 PostgreSQL database (schema: main) is ready!")


if __name__ == "__main__":
    main()
