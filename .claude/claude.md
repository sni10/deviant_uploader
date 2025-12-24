# DeviantArt Uploader - Project Guidelines for Junie

This document contains important information for developing and maintaining the DeviantArt image uploader project.

---

## Project Overview

**Type**: Python 3.10+ application  
**Purpose**: Upload images to DeviantArt via OAuth2 API  
**Architecture**: Domain-Driven Design (DDD) following SOLID, OOP, DRY, and KISS principles  
**Dependencies**: requests, python-dotenv, pytest

---

## Engineering Standard (Authoritative)

В этом разделе — строгие правила, которые важнее любых мягких рекомендаций в документе. Кратко и однозначно.

- Runtime
    - Python: 3.10.x only (use `typing` features available in 3.10; avoid 3.11+ specifics like `Self`, `typing.Any | None` without `from __future__ import annotations` if not supported).
    - Dependencies: runtime (requests, python-dotenv); dev-only (pytest, pytest-cov, black, isort, flake8).

- Architecture & Design (DDD, SOLID, OOP, DRY, KISS) — CRITICAL
    - Bounded Context: photomanager (this uploader). Declare context explicitly in PR descriptions.
    - Domain Layer: pure dataclasses `User`, `Gallery`, `Deviation`, and enum `UploadStatus`. No I/O, no DB, no HTTP.
    - Repository Layer: one repository per entity (`UserRepository`, `OAuthTokenRepository`, `GalleryRepository`, `DeviationRepository`, `DeviationStatsRepository`, `StatsSnapshotRepository`, `UserStatsSnapshotRepository`, `DeviationMetadataRepository`, `FeedDeviationRepository`, `PresetRepository`). No HTTP calls. Database access via adapter pattern: **SQLite (default) or PostgreSQL**. All queries written using **SQLAlchemy Core** (preferred method). Shared utility in `BaseRepository` only.
    - Service Layer: `AuthService`, `UserService`, `GalleryService`, `UploaderService`, `StatsService`. Orchestrates repositories and external API calls; no raw SQL. `StatsService` is responsible for DeviantArt statistics fetching, daily snapshots, and watcher history, and is exposed read‑only via a Flask stats API.
    - Config: `src/config/settings.py` is a Singleton provider. No direct `os.getenv` in services or repositories.
    - Logging: centralized in `src/log/logger.py` only. Do not reconfigure loggers elsewhere.
    - Layer rules (non-negotiable):
        - Domain ↔ Storage: Domain must not import storage or service.
        - Storage must not call external APIs.
        - Service must not embed SQL strings outside repositories.
    - HTTP Client Policy (mandatory):
        - **Single Requester Pattern**: All external HTTP requests (DeviantArt API, etc.) MUST go through a single, centralized requester/client instance.
        - **Retry-After Compliance**: Requester MUST respect server `Retry-After` headers for all HTTP requests (429 Too Many Requests, 503 Service Unavailable).
        - No direct `requests.get/post` calls in services; use shared HTTP client with built-in rate limiting and retry logic.
        - Shared requester ensures consistent error handling, logging, and backoff behavior across all API calls.

- Code Style (PEP 8/257 + tooling)
    - Format: black (line length 88) OR stricter project limit 79 for code, 72 for docstrings/comments. Prefer wrapping over inline ignores.
    - Imports: isort with default profile compatible with black.
    - Lint: flake8 with no unused imports, no wildcard imports, no bare `except`, no print in library code.
    - Typing: full type hints for all public functions/methods; avoid `Any` where feasible.
    - Docstrings: PEP 257. One-line summary, imperative mood; multiline: summary, blank line, details; document params/returns/raises and side effects.
    - Whitespace: no extra spaces inside brackets/braces; `spam(ham[1], {eggs: 2})` is correct.
    - Mutables: use `field(default_factory=...)` for lists/dicts in dataclasses.

- Testing (TDD) — mandatory
    - Write the failing test first. Use pytest.
    - Coverage threshold: >= 85% lines via `pytest --cov=src --cov-report=term-missing` (pytest-cov).
    - Unit tests focus: domain entities, repositories (with PostgreSQL test DB or in-memory), services (HTTP mocked).
- PRs without tests for new/changed logic are rejected.

- Git Workflow (GitHub)
    - Branch model: `main` (production; direct commits PROHIBITED), `dev` (integration), `feature/<task>`, `bugfix/<task>` from `dev`, `hotfix/<task>` from `main`.
    - All changes to `dev`/`main` go via PR; require at least one reviewer; CI must pass (lint, tests, coverage gate).
    - PR checklist: link the issue/task, summarize behavior change, list commands run (tests/lint), and attach relevant output (logs/screenshots) for flows you touched.

- Conventional Commits — required
    - Types: feat, fix, build, chore, ci, docs, style, refactor, perf, test.
    - Breaking change: add `!` after type/scope, e.g., `refactor(auth)!: drop legacy token schema`.
    - Example: `feat(uploader): publish deviations to selected gallery`.

- Code Quality Tools (manual usage)
    - Tools: black (formatter), isort (import sorter), flake8 (linter)
    - Run manually before commits: `black src/`, `isort src/`, `flake8 src/`
    - CI/CD on GitHub validates all PRs (lint, tests, coverage gate)

- Security & Secrets
    - Never commit `.env` or tokens. Access configuration only via `get_config()`; no raw secrets in code or logs.

- Operational Protocol (for tasks)
    1) Declare bounded context; 2) write failing test (TDD); 3) minimal implementation; 4) refactor to meet style/architecture; 5) verify tests and coverage >=85%.

## Project Structure

```
deviant/
├── src/                          # Source code
│   ├── config/                   # Configuration management
│   │   └── settings.py           # Singleton pattern for app config
│   ├── domain/                   # Domain layer (business entities)
│   │   └── models.py             # User, Gallery, Deviation, UploadStatus
│   ├── api/                      # HTTP APIs (read‑only stats dashboard)
│   │   ├── __init__.py
│   │   └── stats_api.py          # Flask API and entrypoint for stats dashboard
│   ├── storage/                  # Data persistence layer (SQLite/PostgreSQL)
│   │   ├── adapters/             # Database abstraction adapters
│   │   │   ├── __init__.py
│   │   │   ├── base.py           # DBConnection and DatabaseAdapter protocols
│   │   │   ├── sqlite_adapter.py # SQLite adapter implementation
│   │   │   └── sqlalchemy_adapter.py # PostgreSQL/SQLAlchemy adapter
│   │   ├── database.py           # Schema, migrations, factory functions
│   │   ├── models.py             # SQLAlchemy ORM models for PostgreSQL
│   │   ├── base_repository.py    # Base repository class
│   │   ├── user_repository.py    # User data access
│   │   ├── oauth_token_repository.py  # OAuth token management
│   │   ├── gallery_repository.py       # Gallery data access
│   │   ├── deviation_repository.py     # Deviation data access (incl. published_time)
│   │   ├── deviation_stats_repository.py  # Current deviation statistics
│   │   ├── stats_snapshot_repository.py   # Daily deviation snapshots
│   │   ├── user_stats_snapshot_repository.py  # User watcher history
│   │   └── deviation_metadata_repository.py   # Extended deviation metadata
│   ├── service/                  # Service layer (business logic)
│   │   ├── auth_service.py       # OAuth2 authentication flow
│   │   ├── user_service.py       # User management
│   │   ├── gallery_service.py    # Gallery synchronization
│   │   ├── uploader.py           # Upload orchestration
│   │   └── stats_service.py      # DeviantArt stats fetching & aggregation
│   ├── log/                      # Logging configuration
│   │   └── logger.py             # Centralized logger setup
│   └── fs/                       # File system utilities
│       └── utils.py              # File operations
├── tests/                        # Test suite
│   ├── __init__.py
│   ├── test_domain_models.py     # Domain model tests
│   └── test_stats_service.py     # StatsService tests (rate‑limit handling)
├── logs/                         # Application logs (auto-created)
├── static/                       # Static assets for stats dashboard
│   └── stats.html                # Single-page stats dashboard UI
├── upload/                       # Source images directory
│   └── done/                     # Successfully uploaded images
├── main.py                       # Main application entry point (uploader)
├── run_stats.py                  # Entry point for Flask-based stats dashboard
├── fetch_user.py                 # User synchronization script
├── fetch_galleries.py            # Gallery synchronization script
├── requirements.txt              # Python dependencies
├── .env                          # Environment configuration (in .gitignore)
└── upload_template.json          # Upload settings template (in .gitignore)
```

### Key Architectural Principles

- **Domain Layer**: Pure business logic, no external dependencies
- **Storage Layer**: Each entity has its own repository (UserRepository, OAuthTokenRepository, GalleryRepository, DeviationRepository)
- **Service Layer**: Orchestrates domain and storage layers, handles external API calls
- **Separation of Concerns**: Clear boundaries between layers
- **Dependency Injection**: Services receive dependencies via constructors

---

## Build & Configuration Instructions

### 1. Environment Setup

**Prerequisites:**
- Python 3.10 or higher
- pip package manager
- DeviantArt Developer account with registered application

**Initial Setup:**

```powershell
# Create virtual environment
python -m venv .venv

# Activate virtual environment (Windows)
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration

**Step 1: Create environment file**

Copy `.env.example` to `.env`:
```powershell
Copy-Item .env.example .env
```

**Step 2: Configure DeviantArt credentials**

Edit `.env` and set the following **required** variables:
- `DA_CLIENT_ID` - Your DeviantArt application client ID
- `DA_CLIENT_SECRET` - Your DeviantArt application client secret

**Optional variables** (have defaults):
- `DA_REDIRECT_URI` (default: `http://localhost:8080/callback`)
- `DA_SCOPES` (default: `browse stash publish`)
- `DATABASE_URL` (default: assembled from `DB_*` variables below)
- `DB_DATABASE` (default: `deviant`)
- `DB_HOST` (default: `localhost`)
- `DB_PORT` (default: `5432`)
- `DB_USERNAME` (default: `postgres`)
- `DB_PASSWORD` (default: `postgres`)
- `UPLOAD_DIR` (default: `upload`)
- `DONE_DIR` (default: `upload/done`)
- `LOG_DIR` (default: `logs`)
- `LOG_LEVEL` (default: `INFO`)

**Step 3: Create upload template**

Copy `upload_template.json.example` to `upload_template.json`:
```powershell
Copy-Item upload_template.json.example upload_template.json
```

Edit `upload_template.json` to configure default upload settings.

**Step 4: Start PostgreSQL**

The application requires PostgreSQL. Use Docker Compose:
```powershell
# Start PostgreSQL (and Redis) containers
docker-compose up -d postgres

# Verify PostgreSQL is running
docker-compose ps
```

Alternatively, use an external PostgreSQL instance and configure `DATABASE_URL` in `.env`.

### 3. First Run

```powershell
# Run main application
python main.py
```

Helper scripts:
- `python fetch_user.py` — refresh authenticated user profile into PostgreSQL.
- `python fetch_galleries.py` — sync DeviantArt galleries.

On first run:
1. Browser opens for DeviantArt OAuth authorization
2. User authenticates and authorizes the application
3. Token is saved to PostgreSQL database
4. Application processes images from `upload/` directory

### 4. No Build Step Required

This is a pure Python application - no compilation or build step is necessary. The PostgreSQL database schema and required directories are created automatically on first run.

---

## Testing

### Test Framework

The project uses **pytest** for testing. Tests are located in the `tests/` directory.
Target coverage: gate is 85%+, aim to maintain the 100% shown in CI badge.

### Running Tests

**Run all tests:**
```powershell
python -m pytest
```

**Run with verbose output:**
```powershell
python -m pytest -v
```

**Run specific test file:**
```powershell
python -m pytest tests\test_domain_models.py -v
```

**Run specific test class or method:**
```powershell
python -m pytest tests\test_domain_models.py::TestDeviation -v
python -m pytest tests\test_domain_models.py::TestDeviation::test_deviation_creation_minimal -v
```

### Test Structure

Tests are organized by layer:
- `test_domain_models.py` - Domain entity tests (User, Gallery, Deviation, UploadStatus)
- `test_stats_service.py` - Service-layer tests for `StatsService` (rate-limit handling, HTTP mocked)
- Future: `test_repositories.py` - Repository layer tests
- Future: `test_services.py` - Additional service layer tests

### Example Test Output

```
============================= test session starts =============================
platform win32 -- Python 3.10.11, pytest-9.0.1, pluggy-1.6.0
collected 12 items

tests/test_domain_models.py::TestUploadStatus::test_enum_values PASSED   [  8%]
tests/test_domain_models.py::TestUploadStatus::test_enum_comparison PASSED [ 16%]
tests/test_domain_models.py::TestUser::test_user_creation_minimal PASSED [ 25%]
tests/test_domain_models.py::TestUser::test_user_creation_with_profile PASSED [ 33%]
tests/test_domain_models.py::TestGallery::test_gallery_creation_minimal PASSED [ 41%]
tests/test_domain_models.py::TestGallery::test_gallery_creation_with_parent PASSED [ 50%]
tests/test_domain_models.py::TestDeviation::test_deviation_creation_minimal PASSED [ 58%]
tests/test_domain_models.py::TestDeviation::test_deviation_creation_with_tags PASSED [ 66%]
tests/test_domain_models.py::TestDeviation::test_deviation_mature_content PASSED [ 75%]
tests/test_domain_models.py::TestDeviation::test_deviation_ai_generated PASSED [ 83%]
tests/test_domain_models.py::TestDeviation::test_deviation_with_stash_fields PASSED [ 91%]
tests/test_domain_models.py::TestDeviation::test_deviation_status_workflow PASSED [100%]

============================= 12 passed in 0.07s ==============================
```

### Writing New Tests

**Guidelines for adding tests:**

1. **Create test file** in `tests/` directory with `test_` prefix
2. **Import pytest** and the module under test
3. **Organize tests in classes** with descriptive names
4. **Use descriptive test method names** starting with `test_`
5. **Add docstrings** explaining what each test validates

**Example test structure:**

```python
"""Tests for [module name]."""
import pytest
from src.domain.models import Deviation, UploadStatus


class TestDeviation:
    """Test Deviation model."""
    
    def test_deviation_creation_minimal(self):
        """Test creating a deviation with minimal required fields."""
        deviation = Deviation(
            filename="artwork.png",
            title="My Artwork"
        )
        
        assert deviation.filename == "artwork.png"
        assert deviation.title == "My Artwork"
        assert deviation.status == UploadStatus.NEW
```

**Test naming conventions:**
- Test files: `test_<module_name>.py`
- Test classes: `Test<ClassName>`
- Test methods: `test_<what_is_being_tested>`

---

## Code Style & Development Guidelines

### Python Style

- **PEP 8**: Follow Python PEP 8 style guide
- **Type hints**: Use type hints for all function parameters and return values
- **Docstrings**: All modules, classes, and public methods must have docstrings
- **Line length**: Maximum 120 characters (not strict 79)

### Domain Models

**Use dataclasses for domain entities:**
```python
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class Deviation:
    """Domain entity representing a DeviantArt deviation."""
    filename: str
    title: str
    tags: list[str] = field(default_factory=list)
    status: UploadStatus = UploadStatus.NEW
```

**Key principles:**
- Immutable where possible
- Default values via `field(default_factory=...)` for mutable types
- Optional fields with `Optional[T]` type hint
- Prefer deterministic tests: mock DeviantArt HTTP calls and file system side effects; avoid real network I/O.

### Repository Pattern

**Each entity has its own repository:**
- `UserRepository` - User data access
- `OAuthTokenRepository` - OAuth token management
- `GalleryRepository` - Gallery data access
- `DeviationRepository` - Deviation data access
- `DeviationStatsRepository` - Current deviation statistics (views, favourites, comments)
- `StatsSnapshotRepository` - Daily deviation statistics snapshots
- `UserStatsSnapshotRepository` - User watcher and friends snapshots
- `DeviationMetadataRepository` - Extended deviation metadata (tags, description, camera, etc.)

**Base repository** (`BaseRepository`) provides common functionality:
- Database connection management
- Transaction support via `close()` method

**Repository methods:**
- `save()` - Create or update entity
- `get_by_id()` - Retrieve by primary key
- `get_all()` - Retrieve all entities
- Custom query methods as needed

### Service Layer

**Services orchestrate business logic:**
- `AuthService` - OAuth2 flow, token validation/refresh
- `UserService` - User synchronization with DeviantArt
- `GalleryService` - Gallery synchronization
- `UploaderService` - Upload orchestration
- `StatsService` - DeviantArt stats synchronization, daily snapshots, and watcher history (used by Flask stats API)

**Service principles:**
- Services receive dependencies via constructor (Dependency Injection)
- Services use repositories for data access
- Services handle external API calls
- Services implement error handling and logging

**Example service structure:**
```python
class UploaderService:
    """Service for uploading deviations to DeviantArt."""
    
    def __init__(
        self,
        deviation_repo: DeviationRepository,
        gallery_repo: GalleryRepository,
        auth_service: AuthService,
        logger
    ):
        self.deviation_repo = deviation_repo
        self.gallery_repo = gallery_repo
        self.auth_service = auth_service
        self.logger = logger
    
    def upload_single(self, filename: str, title: str, **kwargs):
        """Upload a single image to DeviantArt."""
        # Implementation
```

### Configuration Management

**Config class (`src/config/settings.py`) - Singleton pattern:**
- Single source of truth for all app configuration
- Loads variables from `.env` via `python-dotenv`
- Access config anywhere via `get_config()`
- Never use `os.getenv()` directly in services or repositories

```python
from src.config import get_config

config = get_config()
database_path = config.database_path
client_id = config.da_client_id
```

**Configuration storage strategy:**
- **`.env` file**: Static config (credentials, paths, log levels) - never committed to git
- **JSON templates**: Dynamic parameters that change during project work (e.g., `upload_template.json` for upload settings)
- JSON templates used to populate entity fields or modify behavior without changing .env
- Example: `upload_template.json` contains gallery_id, tags, maturity settings for uploads

### Logging

**Centralized logger setup:**
```python
from src.log.logger import setup_logger

logger = setup_logger()
logger.info("Operation completed")
logger.error("Operation failed", exc_info=True)
```

**Logging levels:**
- `DEBUG` - Detailed diagnostic information
- `INFO` - General informational messages (default)
- `WARNING` - Warning messages for non-critical issues
- `ERROR` - Error messages for failures
- `CRITICAL` - Critical failures requiring immediate attention

**Log file rotation:**
- Location: `logs/app.log`
- Max size: 10MB per file
- Backups: 10 files retained

### Error Handling

**Handle errors at appropriate levels:**
- **Domain layer**: Raise domain-specific exceptions
- **Repository layer**: Handle database errors, convert to domain exceptions
- **Service layer**: Handle API errors, log and re-raise or return error status
- **Main application**: Catch all exceptions, log, and provide user feedback

**Always log exceptions with context:**
```python
try:
    result = api_call()
except requests.RequestException as e:
    self.logger.error(f"API call failed: {e}", exc_info=True)
    raise
```

### Database Abstraction Layer

**Architecture**: The project implements a **protocol-based adapter pattern** that allows seamless switching between SQLite and PostgreSQL backends without code changes.

**Current Status**:
- **Default**: SQLite (used in development and production)
- **Supported**: PostgreSQL (fully tested and available)
- **Query Method**: **SQLAlchemy Core is the primary and preferred way to write all database queries**

**Key Components**:

1. **DBConnection Protocol** (`src/storage/base_repository.py`):
    - Defines minimal interface: `execute()`, `commit()`, `close()`
    - All repositories depend on this protocol, not concrete implementations
    - Enables dependency inversion (SOLID principle)

2. **Database Adapters** (`src/storage/adapters/`):
    - **SQLiteAdapter**: Wraps `sqlite3.Connection`, used by default
    - **SQLAlchemyAdapter**: Wraps SQLAlchemy Session for PostgreSQL support
    - Both implement `DatabaseAdapter` protocol with `initialize()` and `get_connection()`

3. **Factory Functions** (`src/storage/database.py`):
    - `get_database_adapter()`: Returns appropriate adapter based on `DATABASE_TYPE` config (defaults to `sqlite`)
    - `get_connection()`: Convenience function returning ready-to-use connection
    - `create_repositories()`: Creates all repositories with shared connection

**Configuration**:

Add to `.env`:
```env
# Database backend selection
DATABASE_TYPE=sqlite          # or 'postgresql'

# SQLite configuration (when DATABASE_TYPE=sqlite)
DATABASE_PATH=data/deviant.db

# PostgreSQL configuration (required when DATABASE_TYPE=postgresql)
DATABASE_URL=postgresql://username:password@localhost:5432/deviant
```

**Usage Pattern**:

```python
from src.storage import create_repositories

# Automatically uses configured database backend
user_repo, token_repo, gallery_repo, deviation_repo, stats_repo = create_repositories()

# All repositories work transparently with both backends
user = user_repo.get_user_by_userid('12345')

# Close when done (all repos share same connection)
token_repo.close()
```

**Benefits**:
- ✅ Zero code changes required to switch databases
- ✅ All repositories remain unchanged
- ✅ Protocol-based design follows SOLID principles
- ✅ Easy to add new backends (MySQL, etc.)
- ✅ **SQLite is default** for simplicity and portability
- ✅ **SQLAlchemy Core** provides consistent query interface across backends

**Technical Details**: See `doc/drafts/DATABASE_ABSTRACTION.md` for implementation details, SQLAlchemy models, and migration path.

### Database Operations

**Database support**: **SQLite (default)** or PostgreSQL via adapter pattern (see Database Abstraction Layer above).

**Query Writing Standard**:
- **PRIMARY METHOD**: Use **SQLAlchemy Core** for all queries (SELECT, INSERT, UPDATE, DELETE)
- SQLAlchemy Core provides consistent interface for both SQLite and PostgreSQL
- Raw SQL strings are discouraged; use SQLAlchemy constructs instead
- Example: `select(table).where(table.c.id == value)` instead of `"SELECT * FROM table WHERE id = ?"`

**Schema management**:
- SQLite: Schema defined via SQLAlchemy Table objects in `src/storage/*_tables.py`, auto-created on first run
- PostgreSQL: Schema defined as SQLAlchemy models in `models.py`, created via `Base.metadata.create_all()`
- Both: Schema auto-created on first run

**Tables**: `users`, `oauth_tokens`, `galleries`, `deviations`, `deviation_stats`, `stats_snapshots`, `user_stats_snapshots`, `deviation_metadata`, `feed_deviations`, `presets`

**Repository pattern isolates database logic**:
- Never write raw SQL in services or domain layer
- **Always use SQLAlchemy Core constructs** in repositories
- Use repositories for all data access
- Repositories use protocol-based DBConnection interface

**Always close connections after use**:
```python
from src.storage import create_repositories

# All repos share same connection
user_repo, token_repo, gallery_repo, deviation_repo, stats_repo = create_repositories()

try:
    token = token_repo.get_token()
    # ... use repositories
finally:
    token_repo.close()  # Closes shared connection
```

### File Operations

**Use `src/fs/utils.py` for file operations:**
- `ensure_directory(path)` - Create directory if it doesn't exist
- `move_file(source, dest)` - Move file with error handling

**Important paths (Windows-style):**
- Use backslashes `\` for path separators
- Use `pathlib.Path` or `os.path.join()` for cross-platform compatibility

---

## Debugging Tips

### Common Issues

**1. OAuth authentication fails:**
- Verify `DA_CLIENT_ID` and `DA_CLIENT_SECRET` in `.env`
- Check redirect URI matches DeviantArt app settings
- Ensure port 8080 is available

**2. Database errors:**
- Verify PostgreSQL is running: `docker-compose ps`
- Check DATABASE_URL or DB_* variables in `.env`
- Ensure PostgreSQL is accessible on configured host/port
- Check logs in `logs/app.log` for SQL errors

**3. Upload fails:**
- Verify token is valid (check database or re-authenticate)
- Check image file format (JPG, PNG, GIF, BMP supported)
- Review DeviantArt API response in logs
- Ensure `upload_template.json` has valid gallery_id

**4. Import errors:**
- Ensure virtual environment is activated
- Verify all dependencies installed: `pip install -r requirements.txt`
- Check Python version: `python --version` (must be 3.10+)

### Useful Commands

**Check token status:**
```python
from src.storage import create_repositories

user_repo, token_repo, gallery_repo, deviation_repo, stats_repo = create_repositories()
try:
    token = token_repo.get_token()
    if token:
        print(f"Token expires: {token.expires_at}")
    else:
        print("No token found")
finally:
    token_repo.close()
```

**Query database directly:**
```powershell
# Connect to PostgreSQL via psql
docker-compose exec postgres psql -U postgres -d deviant

# Or using local psql client
psql -h localhost -U postgres -d deviant

# Example queries
\dt                    # List tables
SELECT * FROM deviations;
\q                     # Quit
```

**View logs:**
```powershell
Get-Content logs\app.log -Tail 50
```

---

## Development Workflow

### Adding New Features

1. **Domain layer first**: Define entities in `src/domain/models.py`
2. **Storage layer**: Add repository methods in appropriate repository
3. **Service layer**: Implement business logic in service class
4. **Entry point**: Add CLI script or update `main.py`
5. **Tests**: Write tests for new functionality
6. **Documentation**: Update README.md if user-facing

### Making Changes

1. **Understand the architecture**: Review layer responsibilities
2. **Locate the right layer**: Domain, Storage, or Service
3. **Follow existing patterns**: Maintain consistency
4. **Test changes**: Run relevant tests
5. **Update documentation**: Keep README.md current

---

## Important Notes for Junie

### Before Making Changes

1. **Review existing code structure** before adding new files
2. **Follow the established patterns** (Repository, Service, DDD)
3. **Check if functionality exists** before duplicating code
4. **Respect layer boundaries** - no database access in services, no API calls in repositories

### When Adding Tests

1. **Tests must pass** before committing changes
2. **Run full test suite**: `python -m pytest -v`
3. **Add tests for new features** in appropriate test file
4. **Keep tests isolated** - no external dependencies (mock API calls)

### When Debugging Issues

1. **Check logs first**: `logs/app.log` contains detailed information
2. **Run with DEBUG logging**: Set `LOG_LEVEL=DEBUG` in `.env`
3. **Verify configuration**: Ensure `.env` has all required variables
4. **Test incrementally**: Isolate the failing component

### Repository Separation

**Critical**: Each entity has its own repository - never combine them into a single repository class. This maintains Single Responsibility Principle and clean architecture:
- ✅ Good: Separate `UserRepository`, `OAuthTokenRepository`, `GalleryRepository`, `DeviationRepository`
- ❌ Bad: Single monolithic `Repository` class handling all entities

---

## Testing Status

✅ **Domain model tests** - Fully implemented and passing (12 tests)
- UploadStatus enum validation
- User model creation and fields
- Gallery model creation and relationships
- Deviation model with all fields and status workflow

⚠️ **Repository tests** - Not yet implemented (future work)
⚠️ **Service tests** - Not yet implemented (future work)
⚠️ **Integration tests** - Not yet implemented (future work)
