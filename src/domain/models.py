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
    deviation_id: Optional[int] = None  # DB identifier
