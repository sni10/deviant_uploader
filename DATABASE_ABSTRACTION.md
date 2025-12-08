# Database Abstraction Layer

## Overview

This document describes the database abstraction layer implementation that enables easy switching between SQLite and PostgreSQL backends without changing application code.

## Architecture

The abstraction layer follows a **Protocol-based Adapter Pattern** with three main components:

### 1. DBConnection Protocol (`src/storage/base_repository.py`)

Defines the minimal interface that all database connections must implement:
- `execute(sql, parameters)` - Execute SQL statements
- `commit()` - Commit transactions
- `close()` - Close connections

All repositories depend on this protocol, not concrete implementations.

### 2. Database Adapters (`src/storage/adapters/`)

**Base Protocol** (`base.py`):
- `DatabaseAdapter` - Protocol defining adapter interface
  - `initialize()` - Create schema and run migrations
  - `get_connection()` - Return a DBConnection-compliant connection

**SQLite Adapter** (`sqlite_adapter.py`):
- `SQLiteConnection` - Wraps `sqlite3.Connection` to implement `DBConnection`
- `SQLiteAdapter` - Factory for SQLite connections
  - Uses existing schema from `database.py`
  - Runs existing migration logic
  - No external dependencies beyond Python stdlib

**SQLAlchemy Adapter** (`sqlalchemy_adapter.py`):
- `SQLAlchemyConnection` - Wraps SQLAlchemy `Session` to implement `DBConnection`
- `SQLAlchemyAdapter` - Factory for PostgreSQL connections via SQLAlchemy
  - Uses declarative models from `models.py`
  - Creates schema via `Base.metadata.create_all()`
  - Requires `sqlalchemy` and `psycopg2` packages

**SQLAlchemy Models** (`src/storage/models.py`):
- Declarative ORM models matching the SQLite schema
- Tables: users, oauth_tokens, galleries, deviations, deviation_stats, stats_snapshots, user_stats_snapshots, deviation_metadata

### 3. Factory Functions (`src/storage/database.py`)

**`get_database_adapter()`**:
- Reads `DATABASE_TYPE` from configuration
- Returns appropriate adapter (SQLiteAdapter or SQLAlchemyAdapter)
- Validates configuration (e.g., DATABASE_URL required for PostgreSQL)

**`get_connection()`**:
- Convenience function that creates adapter and returns connection
- Recommended entry point for all application code

**`init_database(db_path)`**:
- Legacy function kept for backward compatibility
- New code should use `get_connection()` instead

## Configuration

### Environment Variables

Add to your `.env` file:

```bash
# Database backend selection
DATABASE_TYPE=sqlite  # or 'postgresql'

# SQLite configuration (used when DATABASE_TYPE=sqlite)
DATABASE_PATH=data/deviant.db

# PostgreSQL configuration (required when DATABASE_TYPE=postgresql)
DATABASE_URL=postgresql://username:password@localhost:5432/deviant
```

### Switching Between Databases

**To use SQLite** (default):
```bash
DATABASE_TYPE=sqlite
DATABASE_PATH=data/deviant.db
```

**To use PostgreSQL**:
```bash
DATABASE_TYPE=postgresql
DATABASE_URL=postgresql://deviant_user:mypassword@localhost:5432/deviant
```

No code changes required - just update configuration and restart the application.

## Usage

### Application Code

All entry points have been updated to use the factory function:

```python
from src.storage import create_repositories

# Automatically uses configured database backend
user_repo, token_repo, gallery_repo, deviation_repo, stats_repo = create_repositories()

# Use repositories as normal
user = user_repo.get_user_by_userid('12345')

# Close when done (all repos share same connection)
token_repo.close()
```

### Direct Connection Access

For advanced use cases:

```python
from src.storage import get_connection, get_database_adapter

# Get a connection directly
conn = get_connection()
cursor = conn.execute("SELECT * FROM users")
conn.close()

# Or work with adapter
adapter = get_database_adapter()
adapter.initialize()  # Ensure schema exists
conn = adapter.get_connection()
```

## Implementation Details

### How Repositories Stay Unchanged

Repositories only use three methods from connections:
1. `execute(sql, parameters)` - Both SQLite and SQLAlchemy support this
2. `commit()` - Standard transaction commit
3. `close()` - Cleanup

Both `SQLiteConnection` and `SQLAlchemyConnection` implement these methods, wrapping their respective native connection/session objects.

### SQL Compatibility

The current implementation uses **raw SQL queries** in repositories, which works because:
- SQLite and PostgreSQL have similar SQL dialects for the operations we use
- Queries use `?` placeholders which both support (SQLAlchemy converts as needed)
- No database-specific features are used (e.g., no SQLite-only functions)

### Schema Management

**SQLite**:
- Schema defined as SQL string in `database.py`
- Migrations handled by `_migrate_database()` function
- Uses `PRAGMA table_info` to detect missing columns

**PostgreSQL**:
- Schema defined as SQLAlchemy models in `models.py`
- Migrations currently use `Base.metadata.create_all()` (creates all tables)
- Future: Should use Alembic for proper migration management

## Migration Path to Alembic

The current PostgreSQL adapter uses `create_all()` which only creates missing tables but doesn't handle schema changes. For production use, implement Alembic:

### Setup Steps (Future Work)

1. **Initialize Alembic**:
   ```bash
   alembic init alembic
   ```

2. **Configure `alembic.ini`**:
   - Set `sqlalchemy.url` to read from DATABASE_URL env var

3. **Create Initial Migration**:
   ```bash
   alembic revision --autogenerate -m "Initial schema"
   alembic upgrade head
   ```

4. **Update SQLAlchemyAdapter**:
   ```python
   def initialize(self):
       """Run Alembic migrations instead of create_all()."""
       from alembic.config import Config
       from alembic import command
       
       alembic_cfg = Config("alembic.ini")
       command.upgrade(alembic_cfg, "head")
   ```

5. **Future Schema Changes**:
   - Modify SQLAlchemy models
   - Generate migration: `alembic revision --autogenerate -m "description"`
   - Apply: `alembic upgrade head`

## Testing

Comprehensive tests ensure the abstraction works correctly:

**`tests/test_database_adapters.py`**:
- Protocol compliance tests for both adapters
- Schema initialization verification
- Factory function tests
- Database switching tests

Run tests:
```bash
python -m pytest tests/test_database_adapters.py -v
```

All existing tests pass, confirming no regression.

## Benefits

1. **Easy Switching**: Change database backend via configuration, no code changes
2. **Development/Production Parity**: Use SQLite for local dev, PostgreSQL for production
3. **No Repository Changes**: All repositories work with both backends transparently
4. **Backward Compatible**: Existing SQLite functionality preserved
5. **Future-Proof**: Easy to add more backends (MySQL, etc.) by implementing the adapter protocol
6. **Testable**: Can use in-memory SQLite for fast unit tests

## Files Changed

### New Files
- `src/storage/adapters/__init__.py` - Adapter module exports
- `src/storage/adapters/base.py` - DatabaseAdapter protocol
- `src/storage/adapters/sqlite_adapter.py` - SQLite implementation
- `src/storage/adapters/sqlalchemy_adapter.py` - PostgreSQL/SQLAlchemy implementation
- `src/storage/models.py` - SQLAlchemy declarative models
- `tests/test_database_adapters.py` - Abstraction layer tests
- `DATABASE_ABSTRACTION.md` - This documentation

### Modified Files
- `src/config/settings.py` - Added DATABASE_TYPE and DATABASE_URL config
- `src/storage/base_repository.py` - Added DBConnection protocol
- `src/storage/database.py` - Added factory functions
- `src/storage/__init__.py` - Updated create_repositories() to use factory
- `main.py` - Updated to use new create_repositories()
- `fetch_user.py` - Updated to use new create_repositories()
- `fetch_galleries.py` - Updated to use new create_repositories()
- `src/api/stats_api.py` - Updated to use new create_repositories()
- `.env.example` - Documented new configuration options

## Dependencies

**SQLite** (no additional dependencies):
- Python stdlib `sqlite3` module

**PostgreSQL** (requires additional packages):
```bash
pip install sqlalchemy psycopg2-binary
```

Add to `requirements.txt`:
```
sqlalchemy>=2.0.0
psycopg2-binary>=2.9.0
```

## Limitations and Future Work

1. **Alembic Integration**: Currently PostgreSQL uses `create_all()`. Should implement Alembic for proper migrations.

2. **Connection Pooling**: Current implementation creates connections on-demand. For high-concurrency applications, implement connection pooling.

3. **ORM Usage**: Repositories still use raw SQL. Could migrate to SQLAlchemy ORM queries for more type safety and database independence.

4. **Transaction Management**: Currently manual commit/close. Consider implementing context managers for automatic cleanup.

5. **Additional Backends**: Framework supports adding MySQL, MongoDB, etc. by implementing the adapter protocol.

## Conclusion

The database abstraction layer successfully decouples application code from specific database implementations, enabling easy switching between SQLite and PostgreSQL. The protocol-based design follows SOLID principles and maintains backward compatibility while providing a clear path for future enhancements.
