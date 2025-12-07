"""Domain models for the DeviantArt uploader."""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


@dataclass
class User:
    """Represents a DeviantArt user."""
    userid: str  # UUID from DeviantArt
    username: str
    usericon: str  # Avatar URL
    type: str  # "regular", "premium", etc.
    
    # Extended profile information (from /user/profile endpoint)
    is_watching: Optional[bool] = None
    profile_url: Optional[str] = None
    user_is_artist: Optional[bool] = None
    artist_level: Optional[str] = None  # "Hobbyist", "Professional", etc.
    artist_specialty: Optional[str] = None  # "Digital Art", "Traditional Art", etc.
    real_name: Optional[str] = None
    tagline: Optional[str] = None
    country_id: Optional[int] = None
    country: Optional[str] = None
    website: Optional[str] = None
    bio: Optional[str] = None
    
    # Statistics
    user_deviations: Optional[int] = None
    user_favourites: Optional[int] = None
    user_comments: Optional[int] = None
    profile_pageviews: Optional[int] = None
    profile_comments: Optional[int] = None
    
    # Database fields
    user_db_id: Optional[int] = None  # Internal DB identifier
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


@dataclass
class Gallery:
    """Represents a DeviantArt gallery folder."""
    folderid: str  # UUID from DeviantArt
    name: str
    parent: Optional[str] = None  # Parent folder UUID
    size: Optional[int] = None  # Number of deviations in folder
    
    # Database fields
    gallery_db_id: Optional[int] = None  # Internal DB identifier
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


class UploadStatus(str, Enum):
    """Status of a deviation upload."""
    NEW = "new"
    UPLOADING = "uploading"
    DONE = "done"
    FAILED = "failed"


@dataclass
class Deviation:
    """Represents a DeviantArt deviation (artwork submission)."""
    filename: str
    title: str
    is_mature: bool = False
    mature_level: Optional[str] = None  # "strict" or "moderate"
    mature_classification: list[str] = field(default_factory=list)  # nudity, sexual, gore, language, ideology
    feature: bool = True
    allow_comments: bool = True
    display_resolution: int = 0  # 0 = original
    tags: list[str] = field(default_factory=list)
    allow_free_download: bool = False
    add_watermark: bool = False
    is_ai_generated: bool = False
    noai: bool = False
    
    # Stash submit fields
    artist_comments: Optional[str] = None  # Additional information about the submission
    original_url: Optional[str] = None  # Link to original if posted elsewhere
    is_dirty: bool = False  # Flag to warn users that item is being edited
    stack: Optional[str] = None  # Stack name to place submission in
    stackid: Optional[int] = None  # Stack ID to place submission in
    
    # Runtime and database fields
    status: UploadStatus = UploadStatus.NEW
    file_path: Optional[str] = None
    itemid: Optional[int] = None  # Stash item ID (required for publish)
    gallery_id: Optional[int] = None  # Internal DB ID of gallery (references galleries table)
    deviationid: Optional[str] = None  # UUID returned after successful publish
    url: Optional[str] = None  # URL of published deviation
    error: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    uploaded_at: Optional[datetime] = None
    # Publication information returned by DeviantArt API (/deviation/{deviationid})
    # Stored as raw string from API (e.g. "2024-12-07T21:15:00Z") to avoid
    # assumptions about timezone handling at this layer.
    published_time: Optional[str] = None
    deviation_id: Optional[int] = None  # DB identifier


@dataclass
class DeviationStats:
    """Represents aggregated statistics for a deviation."""

    deviationid: str
    title: str
    is_mature: bool = False
    views: int = 0
    favourites: int = 0
    comments: int = 0
    thumb_url: Optional[str] = None
    gallery_folderid: Optional[str] = None

    # Database fields
    stats_id: Optional[int] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


@dataclass
class StatsSnapshot:
    """Represents a daily snapshot of deviation statistics."""

    deviationid: str
    snapshot_date: str  # YYYY-MM-DD
    views: int = 0
    favourites: int = 0
    comments: int = 0

    snapshot_id: Optional[int] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


@dataclass
class DeviationMetadata:
    """Represents extended metadata fetched from DeviantArt."""

    deviationid: str
    title: str
    description: Optional[str] = None
    license: Optional[str] = None
    allows_comments: Optional[bool] = None
    tags: list[dict] = field(default_factory=list)
    is_favourited: Optional[bool] = None
    is_watching: Optional[bool] = None
    is_mature: Optional[bool] = None
    mature_level: Optional[str] = None
    mature_classification: list[str] = field(default_factory=list)
    printid: Optional[str] = None
    author: Optional[dict] = None
    creation_time: Optional[str] = None
    category: Optional[str] = None
    file_size: Optional[str] = None
    resolution: Optional[str] = None
    submitted_with: Optional[dict] = None
    stats: Optional[dict] = None
    camera: Optional[dict] = None
    collections: list[dict] = field(default_factory=list)
    galleries: list[dict] = field(default_factory=list)
    can_post_comment: Optional[bool] = None
    stats_views_today: Optional[int] = None
    stats_downloads_today: Optional[int] = None
    stats_downloads: Optional[int] = None
    stats_views: Optional[int] = None
    stats_favourites: Optional[int] = None
    stats_comments: Optional[int] = None

    metadata_id: Optional[int] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
