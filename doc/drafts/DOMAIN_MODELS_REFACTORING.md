# Domain Models Refactoring - Future Work

## Issue Summary

**Status**: Deferred to future iteration  
**Priority**: Medium  
**Related**: architecture-issues.md point 4

## Problem Description

Currently, some domain models in `src/domain/models.py` contain raw dict/list fields that mirror DeviantArt's JSON API payloads. This creates coupling between the domain layer and external API formats, violating clean DDD principles.

### Affected Models

1. **DeviationMetadata** (lines 139-175)
   - `tags: list[dict]` - raw tag objects from API
   - `author: Optional[dict]` - raw author object
   - `submitted_with: Optional[dict]` - raw submission metadata
   - `stats: Optional[dict]` - raw stats object
   - `camera: Optional[dict]` - raw camera EXIF data
   - `collections: list[dict]` - raw collection objects
   - `galleries: list[dict]` - raw gallery objects

2. **Other models** may have similar issues with JSON serialization in repositories

## Why It's a Problem

1. **Domain Pollution**: Domain models are coupled to external API format
2. **Validation Gap**: No type-safe validation of nested structures
3. **Evolution Risk**: Changes to DeviantArt API format require domain changes
4. **Testing Difficulty**: Hard to mock and validate complex dict structures

## Ideal Solution

Replace raw dict/list fields with properly typed value objects:

```python
@dataclass
class Tag:
    """Value object for deviation tag."""
    tag_name: str
    sponsored: bool = False
    
@dataclass
class Author:
    """Value object for deviation author."""
    userid: str
    username: str
    usericon: str
    type: str

@dataclass
class DeviationMetadata:
    """Domain entity with typed fields."""
    deviationid: str
    title: str
    tags: list[Tag] = field(default_factory=list)  # Typed!
    author: Optional[Author] = None  # Typed!
    # ... other typed fields
```

Introduce DTO-to-Domain mappers in service layer:

```python
class DeviantArtMapper:
    """Maps DeviantArt API responses to domain models."""
    
    @staticmethod
    def map_metadata(api_response: dict) -> DeviationMetadata:
        """Convert API JSON to domain model."""
        return DeviationMetadata(
            deviationid=api_response['deviationid'],
            title=api_response['title'],
            tags=[Tag(**tag) for tag in api_response.get('tags', [])],
            author=Author(**api_response['author']) if 'author' in api_response else None,
            # ... map other fields
        )
```

## Why Deferred

1. **Requires Test Coverage**: Need comprehensive tests before refactoring
   - ✅ Repository tests now exist (added in this iteration)
   - ✅ API tests now exist (added in this iteration)
   
2. **Large Scope**: Affects multiple layers
   - Domain models
   - Repository serialization/deserialization
   - Service layer mapping
   - Potentially breaks existing data in database

3. **Lower Priority**: Current implementation works functionally
   - Not blocking features
   - No immediate bugs
   - More of an architectural improvement

## Recommended Approach

When addressing this in the future:

1. **Phase 1**: Add comprehensive tests for existing behavior
   - ✅ Already done in this iteration
   
2. **Phase 2**: Introduce value objects and mappers
   - Create typed value objects for nested structures
   - Build DTO-to-domain mappers in service layer
   - Keep existing dict-based storage as interim step

3. **Phase 3**: Update repositories
   - Modify serialization logic to handle typed objects
   - May need database schema changes or JSON column migration

4. **Phase 4**: Remove legacy dict-based code
   - Clean up temporary compatibility layers
   - Update all call sites

## Notes

- This is acknowledged technical debt, not a critical defect
- The issue was discussed in Russian in the original architecture review
- Decision: Fix points 6 and 7 first (logging and tests), defer point 4
- Having tests in place (from this iteration) provides safety for future refactoring

## Related Files

- `src/domain/models.py` - Domain models to refactor
- `src/service/stats_service.py` - Service that maps API to domain
- `src/storage/deviation_metadata_repository.py` - Handles JSON serialization
- `tests/test_deviation_metadata_repository.py` - Tests that provide safety net

## References

- Original issue: architecture-issues.md
- Guidelines: .junie/guidelines.md (DDD principles)
- Related PR: Points 6 and 7 completed in current iteration
