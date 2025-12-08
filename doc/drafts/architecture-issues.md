# Architecture Issues (src)

- **Severity: Critical – Storage stack diverges from required PostgreSQL/SQLAlchemy**  
  Paths: `src/storage/database.py`, `src/config/settings.py` (default `database_path`).  
  Guideline: repositories must use PostgreSQL via SQLAlchemy ORM; no SQLite or raw SQL.  
  Impact: schema and migrations are manual, platform-specific, and incompatible with the mandated stack; harder to test/scale and violates the authoritative storage standard.  
  Recommendation: replace `sqlite3` usage with SQLAlchemy models bound to PostgreSQL, move DDL into migrations, and let repositories operate on ORM sessions.

- **Severity: High – Single shared SQLite connection reused across app and Flask server**  
  Paths: `src/storage/__init__.py:create_repositories`, `src/storage/database.py` (single `sqlite3.connect(..., check_same_thread=False)`).  
  Guideline: repositories should rely on proper connection management/pooling; services should not share one connection across threads.  
  Impact: hidden global state, thread-safety risks under Flask, no unit-of-work boundaries, and difficult test isolation.  
  Recommendation: provide per-request/session scoped connections (via SQLAlchemy sessionmaker/engine pool); inject sessions through factories or context managers instead of a module-level singleton.

- **Severity: High – StatsRepository aggregates multiple entities**  
  Paths: `src/storage/stats_repository.py`.  
  Guideline: one repository per entity (UserRepository, OAuthTokenRepository, GalleryRepository, DeviationRepository); SRP per repository.  
  Impact: a single class handles deviation stats, daily snapshots, user watcher history, and metadata, making responsibilities tangled and violating the repository-per-entity rule.  
  Recommendation: split into dedicated repositories (e.g., DeviationStatsRepository, StatsSnapshotRepository, UserStatsSnapshotRepository, DeviationMetadataRepository) and wire them individually from the factory.

- **Severity: Medium – Domain models mirror external API payloads without abstraction**  
  Paths: `src/domain/models.py` (DeviationMetadata, StatsSnapshot, DeviationStats), `src/service/stats_service.py`.  
  Guideline: domain layer should stay pure and decoupled from external API shapes.  
  Impact: domain objects carry raw dict/list structures from DeviantArt, tying domain to HTTP response formats and leaking JSON directly into storage, which hampers validation and evolution.  
  Recommendation: define domain value objects with typed fields, map API responses to them inside the service, and persist structured fields instead of opaque JSON blobs.

- **Severity: Medium – API layer instantiates global state at import time**  
  Paths: `src/api/stats_api.py` (module-level config, repositories, services, Flask app).  
  Guideline: prefer explicit dependency injection; avoid hidden singletons for better testability and SOLID (DIP).  
  Impact: importing the module triggers I/O (env load, DB connect) and binds a shared connection to Flask, making tests/mocking hard and coupling runtime to module import order.  
  Recommendation: adopt an app-factory (`create_app(config, repo_factory)`) that wires dependencies per invocation, and construct repositories per request or via scoped sessions.

- **Severity: Low – Console prints inside storage/migration code**  
  Paths: `src/storage/database.py` (`print` in `_migrate_database`).  
  Guideline: logging must be centralized in `src/log/logger.py`; avoid `print` in library code.  
  Impact: bypasses log configuration and makes observability inconsistent.  
  Recommendation: replace `print` with the shared logger or propagate events up to a caller-owned logger.

- **Severity: Medium – Testing gap for new stats/storage layers**  
  Paths: `src/api/stats_api.py`, `src/storage/stats_repository.py`, `src/storage/database.py` migrations.  
  Guideline: TDD with coverage >=85% and tests for new/changed logic.  
  Impact: stats repositories, migrations, and API endpoints lack coverage; only rate-limit behavior is tested, so regressions in persistence and HTTP contracts may go unnoticed.  
  Recommendation: add unit tests for each repository method (upserts, JSON (de)serialization, snapshot diffs), integration tests for `/api/stats` and `/api/stats/sync`, and migration tests to assert new columns/tables are created.
