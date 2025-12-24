# Service Layer Refactoring Plan

**Date**: 2025-12-24
**Status**: Planning
**Objective**: Eliminate duplicated code in service layer through abstraction and inheritance

---

## Executive Summary

Analysis of 13 service files revealed **~600-900 lines of duplicated code** across the service layer. This refactoring plan establishes a proper inheritance hierarchy with `BaseService` and enhanced `BaseWorkerService` to eliminate duplication and improve maintainability.

**Expected outcome**: Reduction of 300-600 lines of duplicated code while maintaining all existing functionality.

---

## Analysis Results

### Service Classification

#### **Worker Services** (inherit from BaseWorkerService):
- `comment_poster_service.py`
- `profile_message_service.py`
- `mass_fave_service.py`

#### **Non-Worker Services with Threading**:
- `stats_service.py` (implements own worker pattern - **needs refactoring**)

#### **Standard Services** (no threading):
- `auth_service.py`
- `comment_collector_service.py`
- `gallery_service.py`
- `user_service.py`
- `uploader.py`

#### **Utility Modules**:
- `http_client.py`
- `message_randomizer.py`

---

## Duplicated Code Patterns Identified

### 1. Common Initialization Pattern (DUPLICATED)

**Pattern**: Logger + HTTP Client Initialization

**Found in**: 8 services
**Lines duplicated**: ~64-120 lines total

**Services affected**:
- `CommentCollectorService` (lines 27-42)
- `CommentPosterService` (lines 41-58)
- `ProfileMessageService` (lines 28-48)
- `MassFaveService` (lines 22-34)
- `StatsService` (lines 26-47)
- `GalleryService` (lines 32-52)
- `UserService` (lines 32-51)
- `UploaderService` (lines 30-60)

**Example**:
```python
def __init__(
    self,
    # ... repositories ...
    logger: Logger,
    token_repo=None,
    http_client: Optional[DeviantArtHttpClient] = None,
):
    self.logger = logger
    self.http_client = http_client or DeviantArtHttpClient(
        logger=logger, token_repo=token_repo
    )
```

---

### 2. Lazy Config Loading (DUPLICATED)

**Found in**: 2 worker services
**Lines duplicated**: ~12 lines total

**Services affected**:
- `CommentPosterService` (lines 60-65)
- `ProfileMessageService` (lines 55-60)

**Example**:
```python
@property
def config(self):
    """Lazy-load config if not provided during initialization."""
    if self._config is None:
        self._config = get_config()
    return self._config
```

---

### 3. Worker Status Tracking (DUPLICATED)

**Found in**: 4 services
**Lines duplicated**: ~60-120 lines total

**Services affected**:
- `CommentPosterService` (lines 110-126)
- `ProfileMessageService` (lines 335-364)
- `MassFaveService` (lines 148-164)
- `StatsService` (lines 793-808)

**Example**:
```python
def get_worker_status(self) -> dict:
    """Get worker and queue status."""
    running = self._is_worker_alive()
    if not running:
        self._worker_running = False

    with self._stats_lock:
        return {
            "running": running,
            "processed": self._worker_stats["processed"],
            "errors": self._worker_stats["errors"],
            # ...
        }
```

---

### 4. HTTP Error Handling (DUPLICATED)

**Found in**: `MassFaveService` (lines 219-282)
**Lines duplicated**: ~30 lines

**Note**: `BaseWorkerService._format_http_error()` already exists but not used by `MassFaveService`.

---

### 5. Rate Limiting Delays (DUPLICATED)

**Found in**: 7 services
**Lines duplicated**: ~30-50 lines total

**Services affected**:
- `CommentCollectorService` (lines 185-191)
- `GalleryService` (lines 110-116)
- `StatsService` (lines 142-145, 209-212, 261-264)
- `UploaderService` (lines 823-829, 916-921, 1037-1043)

**Example**:
```python
delay = self.http_client.get_recommended_delay()
self.logger.debug("Waiting %s seconds before next request", delay)
time.sleep(delay)
```

---

### 6. API Pagination Pattern (DUPLICATED)

**Found in**: 4 services
**Lines duplicated**: ~160-320 lines total

**Services affected**:
- `CommentCollectorService._collect` (lines 84-204)
- `ProfileMessageService._fetch_watchers_from_api` (lines 64-170)
- `MassFaveService.collect_from_feed` (lines 38-132)
- `GalleryService.fetch_galleries` (lines 54-125)

**Pattern structure**:
```python
offset = 0
pages = 0
has_more = True

while pages < max_pages (or has_more):
    params = {
        "access_token": access_token,
        "limit": limit,
        "offset": offset,
    }

    response = self.http_client.get(url, params=params, timeout=30)
    data = response.json() or {}

    results = data.get("results", [])
    for item in results:
        # Process item

    pages += 1
    has_more = bool(data.get("has_more"))
    next_offset = data.get("next_offset")

    if next_offset is not None:
        offset = int(next_offset)

    if not has_more:
        break

    delay = self.http_client.get_recommended_delay()
    time.sleep(delay)
```

---

### 7. Broadcast Delay Generation (DUPLICATED)

**Found in**: 2 services
**Lines duplicated**: ~30 lines total

**Services affected**:
- `CommentPosterService` (lines 194-209)
- `ProfileMessageService` (lines 294-309)

**Example**:
```python
def _get_broadcast_delay(self) -> int:
    """Generate random delay for broadcasting (in seconds)."""
    min_delay = self.config.broadcast_min_delay_seconds
    max_delay = self.config.broadcast_max_delay_seconds
    delay = random.randint(min_delay, max_delay)
    self.logger.debug(
        "Generated broadcast delay: %d seconds (range: %d-%d)",
        delay, min_delay, max_delay,
    )
    return delay
```

---

### 8. StatsService Custom Worker Implementation

**Service**: `StatsService` (lines 49-61, 738-889)
**Lines of custom worker code**: ~200 lines

**Duplicates**:
- Threading infrastructure already in `BaseWorkerService`
- `start_worker()`, `stop_worker()`, `get_worker_status()` methods
- Worker stats tracking

**Solution**: Refactor to inherit from `BaseWorkerService`

---

## Refactoring Plan

### Stage 1: Create BaseService (New Abstraction)

**Objective**: Unify common initialization logic for all services

**File**: `src/service/base_service.py` (new)

**Implementation**:
```python
"""Base service with common initialization logic for all services."""
from __future__ import annotations

from abc import ABC
from logging import Logger
from typing import Optional

from src.config import get_config
from src.service.http_client import DeviantArtHttpClient


class BaseService(ABC):
    """Base class for all services with common initialization logic.

    Provides:
    - Logger initialization
    - HTTP client initialization (optional, with token_repo)
    - Config lazy loading property
    - Repository dependency injection pattern
    """

    def __init__(
        self,
        logger: Logger,
        token_repo=None,
        http_client: Optional[DeviantArtHttpClient] = None,
    ):
        """Initialize base service.

        Args:
            logger: Logger instance for this service
            token_repo: Optional OAuth token repository
            http_client: Optional HTTP client (auto-created if token_repo provided)
        """
        self.logger = logger
        self._token_repo = token_repo
        self.http_client = http_client or (
            DeviantArtHttpClient(logger=logger, token_repo=token_repo)
            if token_repo is not None
            else None
        )
        self._config = None

    @property
    def config(self):
        """Lazy-load config if not provided during initialization.

        Returns:
            Application configuration instance
        """
        if self._config is None:
            self._config = get_config()
        return self._config
```

**Impact**:
- **Lines removed**: 64-120 lines of duplicated code
- **Files affected**: `src/service/base_service.py` (create new)

**Tests**:
- Create `tests/test_base_service.py`
- Validate logger initialization
- Validate http_client auto-creation
- Validate config lazy loading

---

### Stage 2: Refactor BaseWorkerService to Inherit from BaseService

**Objective**: Make `BaseWorkerService` inherit from `BaseService`

**File**: `src/service/base_worker_service.py`

**Changes**:
```python
from src.service.base_service import BaseService

class BaseWorkerService(BaseService, ABC):
    """Base class for worker services with common threading logic."""

    def __init__(
        self,
        logger: Logger,
        token_repo=None,
        http_client: Optional[DeviantArtHttpClient] = None,
    ):
        # Call BaseService constructor
        super().__init__(logger, token_repo, http_client)

        # Thread management (existing code)
        self._worker_thread: threading.Thread | None = None
        self._stop_flag = threading.Event()
        self._worker_running = False

        # Statistics tracking (existing code)
        self._stats_lock = threading.Lock()
        self._worker_stats: dict[str, Any] = {
            "processed": 0,
            "errors": 0,
            "last_error": None,
            "consecutive_failures": 0,
        }
```

**Impact**:
- **Files affected**: `src/service/base_worker_service.py` (modify)

**Tests**:
- Update `tests/test_base_worker_service.py` (if exists)
- Verify BaseService functionality is accessible

---

### Stage 3: Add Standardized get_worker_status() to BaseWorkerService

**Objective**: Unify `get_worker_status()` across all worker services

**File**: `src/service/base_worker_service.py`

**Add method**:
```python
def get_worker_status(self) -> dict:
    """Get standardized worker and queue status.

    Subclasses can override to add service-specific stats.

    Returns:
        Dictionary with worker status:
        - running: bool - worker thread status
        - processed: int - total items processed
        - errors: int - total errors encountered
        - last_error: str | None - last error message
        - consecutive_failures: int - consecutive failures counter
    """
    # Sync running flag with actual thread state
    running = self._is_worker_alive()
    if not running:
        self._worker_running = False

    with self._stats_lock:
        return {
            "running": running,
            "processed": self._worker_stats["processed"],
            "errors": self._worker_stats["errors"],
            "last_error": self._worker_stats["last_error"],
            "consecutive_failures": self._worker_stats["consecutive_failures"],
        }
```

**Impact**:
- **Lines removed**: 60-120 lines of duplicated code
- **Files affected**:
  - `src/service/base_worker_service.py` (add method)
  - `src/service/comment_poster_service.py` (simplify, override to add queue_size)
  - `src/service/profile_message_service.py` (simplify, override to add queue_size)
  - `src/service/mass_fave_service.py` (simplify, override for specific stats)

**Tests**:
- Update worker service tests to verify standard status format

---

### Stage 4: Add _get_broadcast_delay() to BaseWorkerService

**Objective**: Remove duplicated broadcast delay logic

**File**: `src/service/base_worker_service.py`

**Add method**:
```python
def _get_broadcast_delay(
    self,
    min_delay: int | None = None,
    max_delay: int | None = None
) -> int:
    """Generate random delay for broadcasting (in seconds).

    Args:
        min_delay: Minimum delay in seconds (uses config if None)
        max_delay: Maximum delay in seconds (uses config if None)

    Returns:
        Random delay in seconds between min and max configured values
    """
    import random

    min_val = (
        min_delay if min_delay is not None
        else self.config.broadcast_min_delay_seconds
    )
    max_val = (
        max_delay if max_delay is not None
        else self.config.broadcast_max_delay_seconds
    )
    delay = random.randint(min_val, max_val)
    self.logger.debug(
        "Generated broadcast delay: %d seconds (range: %d-%d)",
        delay,
        min_val,
        max_val,
    )
    return delay
```

**Impact**:
- **Lines removed**: ~30 lines of duplicated code
- **Files affected**:
  - `src/service/base_worker_service.py` (add method)
  - `src/service/comment_poster_service.py` (remove method, use base)
  - `src/service/profile_message_service.py` (remove method, use base)

**Tests**:
- Add test for `_get_broadcast_delay()` in BaseWorkerService

---

### Stage 5: Create API Pagination Helper Utility

**Objective**: Eliminate 160-320 lines of duplicated pagination code

**File**: `src/service/api_pagination_helper.py` (new)

**Implementation**:
```python
"""Helper utility for DeviantArt API offset-based pagination."""
from __future__ import annotations

import time
from logging import Logger
from typing import Any, Callable, Generator

from src.service.http_client import DeviantArtHttpClient


class APIPaginationHelper:
    """Helper for DeviantArt API offset-based pagination.

    Provides a reusable pattern for paginating through API results
    with proper rate limiting and error handling.
    """

    def __init__(
        self,
        http_client: DeviantArtHttpClient,
        logger: Logger,
    ):
        """Initialize pagination helper.

        Args:
            http_client: DeviantArt HTTP client for API requests
            logger: Logger instance
        """
        self.http_client = http_client
        self.logger = logger

    def paginate(
        self,
        url: str,
        access_token: str,
        limit: int = 50,
        max_pages: int | None = None,
        additional_params: dict | None = None,
        process_item: Callable[[dict], Any] | None = None,
    ) -> Generator[dict, None, None]:
        """Paginate through DeviantArt API endpoint.

        Args:
            url: API endpoint URL
            access_token: OAuth access token
            limit: Items per page (default: 50)
            max_pages: Maximum pages to fetch (None = unlimited)
            additional_params: Additional query parameters
            process_item: Optional callback to process each item before yielding

        Yields:
            Individual items from API results

        Example:
            ```python
            pagination = APIPaginationHelper(http_client, logger)
            for item in pagination.paginate(
                url="https://www.deviantart.com/api/v1/oauth2/browse/home",
                access_token=token,
                limit=50,
                max_pages=10,
            ):
                # Process item
                process_deviation(item)
            ```
        """
        offset = 0
        pages = 0
        has_more = True

        while (max_pages is None or pages < max_pages) and has_more:
            params = {
                "access_token": access_token,
                "limit": limit,
                "offset": offset,
            }
            if additional_params:
                params.update(additional_params)

            self.logger.debug(
                "Fetching page %d (offset=%d, limit=%d)",
                pages + 1,
                offset,
                limit,
            )

            response = self.http_client.get(url, params=params, timeout=30)
            data = response.json() or {}

            # Yield results
            results = data.get("results", [])
            for item in results:
                if process_item:
                    processed = process_item(item)
                    if processed is not None:
                        yield processed
                else:
                    yield item

            pages += 1
            has_more = bool(data.get("has_more"))
            next_offset = data.get("next_offset")

            if next_offset is not None:
                offset = int(next_offset)

            if not has_more:
                self.logger.debug("No more pages available")
                break

            # Rate limiting delay
            delay = self.http_client.get_recommended_delay()
            self.logger.debug("Waiting %s seconds before next page", delay)
            time.sleep(delay)

        self.logger.info(
            "Pagination complete: %d pages fetched, final offset=%d",
            pages,
            offset,
        )
```

**Usage example in services**:
```python
# Before: ~80 lines of duplicated pagination code

# After:
from src.service.api_pagination_helper import APIPaginationHelper

pagination = APIPaginationHelper(self.http_client, self.logger)
for item in pagination.paginate(
    url=url,
    access_token=access_token,
    limit=50,
    max_pages=max_pages,
):
    # Process item
    self._process_item(item)
```

**Impact**:
- **Lines removed**: 160-320 lines of duplicated code
- **Files affected**:
  - `src/service/api_pagination_helper.py` (create new)
  - `src/service/comment_collector_service.py` (refactor `_collect`)
  - `src/service/profile_message_service.py` (refactor `_fetch_watchers_from_api`)
  - `src/service/mass_fave_service.py` (refactor `collect_from_feed`)
  - `src/service/gallery_service.py` (refactor `fetch_galleries`)

**Tests**:
- Create `tests/test_api_pagination_helper.py`
- Mock http_client responses
- Verify pagination logic, rate limiting, has_more handling

---

### Stage 6: Refactor Existing Worker Services

**Objective**: Simplify existing workers using new base classes

#### 6.1. CommentPosterService

**File**: `src/service/comment_poster_service.py`

**Changes**:
1. Remove duplicated initialization (uses BaseService via BaseWorkerService)
2. Remove `_get_broadcast_delay()` (use from BaseWorkerService)
3. Override `get_worker_status()` to add queue_size

**Before**: ~700 lines
**After**: ~650 lines (-50 lines)

#### 6.2. ProfileMessageService

**File**: `src/service/profile_message_service.py`

**Changes**:
1. Remove duplicated initialization
2. Remove `_get_broadcast_delay()`
3. Use `APIPaginationHelper` in `_fetch_watchers_from_api`
4. Override `get_worker_status()` to add queue_size

**Before**: ~1000 lines
**After**: ~900 lines (-100 lines)

#### 6.3. MassFaveService

**File**: `src/service/mass_fave_service.py`

**Changes**:
1. Remove duplicated initialization
2. Use `APIPaginationHelper` in `collect_from_feed`
3. Use `BaseWorkerService._format_http_error()` instead of duplicated logic (lines 219-282)
4. Consider using `_is_critical_error()`

**Before**: ~400 lines
**After**: ~320 lines (-80 lines)

---

### Stage 7: Refactor StatsService to Inherit from BaseWorkerService

**Objective**: Eliminate ~200 lines of custom worker logic

**File**: `src/service/stats_service.py`

**Before**:
```python
class StatsService:
    def __init__(self, ...):
        # Duplicated initialization
        self._worker_thread = None
        self._worker_running = False
        self._stop_flag = threading.Event()
        self._stats_lock = threading.Lock()
        self._worker_stats = {...}

    def start_worker(self):
        # Duplicated logic

    def stop_worker(self):
        # Duplicated logic

    def get_worker_status(self):
        # Duplicated logic

    def _worker_loop(self):
        # Main gallery processing logic
```

**After**:
```python
class StatsService(BaseWorkerService):
    def __init__(
        self,
        deviation_stats_repo,
        stats_snapshot_repo,
        user_stats_snapshot_repo,
        deviation_metadata_repo,
        deviation_repo,
        gallery_repo,
        logger: Logger,
        token_repo=None,
        http_client: Optional[DeviantArtHttpClient] = None,
    ):
        # Call BaseWorkerService constructor
        super().__init__(logger, token_repo, http_client)

        # Service-specific repositories
        self.deviation_stats_repo = deviation_stats_repo
        self.stats_snapshot_repo = stats_snapshot_repo
        self.user_stats_snapshot_repo = user_stats_snapshot_repo
        self.deviation_metadata_repo = deviation_metadata_repo
        self.deviation_repo = deviation_repo
        self.gallery_repo = gallery_repo

    def _validate_worker_start(self) -> dict[str, object]:
        """Validate conditions before starting worker."""
        # StatsService doesn't require validation
        return {"valid": True}

    def _worker_loop(self, access_token: str, user_id: str) -> None:
        """Main worker loop - process galleries."""
        # Existing logic remains unchanged (lines 810-889)
        pass

    # start_worker(), stop_worker(), get_worker_status()
    # inherited from BaseWorkerService - NO NEED TO DUPLICATE
```

**Remove methods** (inherited from BaseWorkerService):
- `start_worker()` (lines 738-773)
- `stop_worker()` (lines 775-791)
- `get_worker_status()` (lines 793-808)

**Remove fields** (inherited from BaseWorkerService):
- `self._worker_thread` (line 50)
- `self._worker_running` (line 51)
- `self._stop_flag` (line 52)
- `self._stats_lock` (line 53)
- `self._worker_stats` (lines 54-60)

**Impact**:
- **Before**: ~900 lines
- **After**: ~700 lines (-200 lines)

**Tests**:
- Update `tests/test_stats_service.py`
- Verify worker starts/stops correctly
- Verify `get_worker_status()` returns correct format

---

### Stage 8: Refactor Non-Worker Services to Inherit from BaseService

**Objective**: Simplify initialization in services without workers

#### 8.1. CommentCollectorService

**File**: `src/service/comment_collector_service.py`

**Changes**:
```python
class CommentCollectorService(BaseService):
    def __init__(
        self,
        deviation_comment_queue_repo,
        deviation_comment_message_repo,
        logger: Logger,
        token_repo=None,
        http_client: Optional[DeviantArtHttpClient] = None,
    ):
        super().__init__(logger, token_repo, http_client)
        self.deviation_comment_queue_repo = deviation_comment_queue_repo
        self.deviation_comment_message_repo = deviation_comment_message_repo
        # Remove duplicated logger, http_client initialization
```

**Use APIPaginationHelper** in `_collect`:
```python
def _collect(self, ...):
    pagination = APIPaginationHelper(self.http_client, self.logger)
    for item in pagination.paginate(
        url=url,
        access_token=access_token,
        limit=limit,
        max_pages=max_pages,
    ):
        # Process item
```

**Before**: ~220 lines
**After**: ~170 lines (-50 lines)

#### 8.2. GalleryService

**File**: `src/service/gallery_service.py`

**Changes**:
1. Inherit from `BaseService`
2. Remove duplicated initialization
3. Use `APIPaginationHelper` in `fetch_galleries`

**Before**: ~150 lines
**After**: ~100 lines (-50 lines)

#### 8.3. UserService

**File**: `src/service/user_service.py`

**Changes**:
1. Inherit from `BaseService`
2. Remove duplicated initialization

**Before**: ~100 lines
**After**: ~70 lines (-30 lines)

#### 8.4. UploaderService

**File**: `src/service/uploader.py`

**Changes**:
1. Inherit from `BaseService`
2. Remove duplicated initialization
3. Consider extracting rate limiting delay pattern to base method

**Before**: ~1100 lines
**After**: ~1050 lines (-50 lines)

---

### Stage 9: Update Imports in All API Endpoints and Entry Points

**Objective**: Ensure all services initialize correctly

**Files to review**:
- `src/api/stats_api.py`
- `src/api/upload_admin_api.py`
- `src/api/stats_routes/*.py`
- `main.py`
- `run_stats.py`
- `fetch_user.py`
- `fetch_galleries.py`

**Verify**:
- All imports are updated
- Service initialization is correct
- Parameters are passed correctly

---

### Stage 10: Update and Expand Tests

**New test files**:
1. `tests/test_base_service.py` - BaseService tests
2. `tests/test_api_pagination_helper.py` - Pagination helper tests

**Update existing tests**:
1. `tests/test_base_worker_service.py` (if exists)
2. `tests/test_stats_service.py` - adapt to new inheritance
3. `tests/test_comment_poster_service.py` - verify new get_worker_status
4. `tests/test_profile_message_service.py` - verify new get_worker_status
5. All other service tests

---

## Final Results

### Code Reduction Summary

| Stage | Component | Lines Removed |
|-------|-----------|---------------|
| 1 | BaseService creation | 64-120 |
| 3 | get_worker_status() standardization | 60-120 |
| 4 | _get_broadcast_delay() | 30 |
| 5 | APIPaginationHelper | 160-320 |
| 7 | StatsService refactoring | 200 |
| 6,8 | Other services | 260 |
| **TOTAL** | | **~774-1050 lines** |

### New Files

1. `src/service/base_service.py` (~80 lines)
2. `src/service/api_pagination_helper.py` (~120 lines)
3. `tests/test_base_service.py` (~100 lines)
4. `tests/test_api_pagination_helper.py` (~150 lines)

**Net reduction**: ~300-600 lines of code

---

## Final Class Hierarchy

```
BaseService (NEW)
├── logger
├── http_client (optional)
├── config property
└── Common initialization

BaseWorkerService (REFACTORED - extends BaseService)
├── All from BaseService
├── Threading management
├── Worker stats
├── get_worker_status() (standardized)
├── _get_broadcast_delay()
├── _format_http_error()
├── _is_critical_error()
└── start_worker() / stop_worker()

Worker Services (extends BaseWorkerService):
├── CommentPosterService
├── ProfileMessageService
├── MassFaveService
└── StatsService (REFACTORED)

Standard Services (extends BaseService):
├── CommentCollectorService
├── GalleryService
├── UserService
├── UploaderService
└── AuthService

Utilities (no inheritance):
├── APIPaginationHelper (NEW)
├── MessageRandomizer
└── DeviantArtHttpClient
```

---

## Recommended Execution Order

1. **Stage 1**: BaseService → minimal risk, maximum benefit
2. **Stage 2**: BaseWorkerService inheritance → affects workers
3. **Stage 3-4**: Standardize get_worker_status + broadcast_delay → improves workers
4. **Stage 5**: APIPaginationHelper → independent utility
5. **Stage 6**: Refactor existing workers → uses stages 1-4
6. **Stage 7**: StatsService → largest refactoring
7. **Stage 8**: Other services → simple changes
8. **Stage 9-10**: Imports and tests → finalization

**Each stage** should:
- Pass all tests (`pytest`)
- Maintain functionality
- Be committed separately for easy rollback

---

## Success Criteria

- [ ] All tests pass
- [ ] No functional regressions
- [ ] Code duplication reduced by 300-600 lines
- [ ] All services follow consistent initialization pattern
- [ ] Worker services standardized with common status format
- [ ] Documentation updated (this file, README, CLAUDE.md)

---

## Notes

- This refactoring follows **SOLID principles** (especially Single Responsibility and DRY)
- Maintains **backward compatibility** with existing API interfaces
- **No changes to business logic** - only structural improvements
- All changes are **testable and reversible**
