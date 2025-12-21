#!/usr/bin/env python3
"""Apply migrations to PostgreSQL database."""

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from src.storage.adapters.sqlalchemy_adapter import SQLAlchemyAdapter


def main():
    """Apply all migrations to PostgreSQL."""
    # PostgreSQL connection URL from docker-compose
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/deviant"
    )

    print(f"Connecting to PostgreSQL: {database_url}")

    # Create adapter
    adapter = SQLAlchemyAdapter(database_url)

    print("\nApplying migrations...")
    print("  - Creating tables from models.py (Base.metadata)")
    print("  - Creating tables from feed_tables.py")
    print("  - Creating tables from profile_message_tables.py")

    # This will create all tables defined in:
    # - Base.metadata (models.py)
    # - feed_metadata (feed_tables.py)
    # - profile_message_metadata (profile_message_tables.py)
    adapter.initialize()

    print("\n✓ Migrations applied successfully!")

    # Verify tables were created
    print("\nVerifying tables in PostgreSQL...")
    conn = adapter.get_connection()

    result = conn.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name
    """)

    tables = [row[0] for row in result.fetchall()]

    print(f"\nCreated {len(tables)} tables:")
    for table_name in tables:
        print(f"  ✓ {table_name}")

    conn.close()

    print("\n🎉 PostgreSQL database is ready!")


if __name__ == "__main__":
    main()
