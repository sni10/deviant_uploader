"""SQLAlchemy ORM models for PostgreSQL backend."""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey, Index, Boolean
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


class User(Base):
    """User model representing DeviantArt users."""
    
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    userid = Column(String, nullable=False, unique=True, index=True)
    username = Column(String, nullable=False, index=True)
    usericon = Column(String)
    type = Column(String, nullable=False)
    
    # Extended profile information
    is_watching = Column(Integer)
    profile_url = Column(String)
    user_is_artist = Column(Integer)
    artist_level = Column(String)
    artist_specialty = Column(String)
    real_name = Column(String)
    tagline = Column(String)
    country_id = Column(Integer)
    country = Column(String)
    website = Column(String)
    bio = Column(Text)
    
    # Statistics
    user_deviations = Column(Integer)
    user_favourites = Column(Integer)
    user_comments = Column(Integer)
    profile_pageviews = Column(Integer)
    profile_comments = Column(Integer)
    
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class OAuthToken(Base):
    """OAuth token model for storing access and refresh tokens."""
    
    __tablename__ = 'oauth_tokens'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), index=True)
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text, nullable=False)
    token_type = Column(String, nullable=False, default='Bearer')
    expires_at = Column(DateTime, nullable=False)
    scope = Column(String)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class Gallery(Base):
    """Gallery model representing DeviantArt gallery folders."""
    
    __tablename__ = 'galleries'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), index=True)
    folderid = Column(String, nullable=False, unique=True, index=True)
    name = Column(String, nullable=False)
    parent = Column(String)
    size = Column(Integer)
    sync_enabled = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class Deviation(Base):
    """Deviation model tracking uploaded deviations."""
    
    __tablename__ = 'deviations'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), index=True)
    filename = Column(String, nullable=False, unique=True, index=True)
    title = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    status = Column(String, nullable=False, default='new', index=True)
    
    # DeviantArt submission parameters
    is_mature = Column(Integer, nullable=False, default=0)
    mature_level = Column(String)
    mature_classification = Column(Text)  # JSON array
    feature = Column(Integer, default=1)
    allow_comments = Column(Integer, default=1)
    display_resolution = Column(Integer, default=0)
    tags = Column(Text)  # JSON array
    allow_free_download = Column(Integer, default=0)
    add_watermark = Column(Integer, default=0)
    is_ai_generated = Column(Integer, default=0)
    noai = Column(Integer, default=0)
    
    # Stash submit parameters
    artist_comments = Column(Text)
    original_url = Column(String)
    is_dirty = Column(Integer, default=0)
    stack = Column(String)
    stackid = Column(Integer)
    
    # Upload results
    itemid = Column(Integer)
    gallery_id = Column(Integer)
    deviationid = Column(String)
    url = Column(String)
    error = Column(Text)
    
    created_at = Column(DateTime, default=func.now())
    uploaded_at = Column(DateTime)
    published_time = Column(String)


class DeviationStats(Base):
    """Current deviation statistics."""
    
    __tablename__ = 'deviation_stats'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    deviationid = Column(String, nullable=False, unique=True, index=True)
    title = Column(String, nullable=False)
    thumb_url = Column(String)
    is_mature = Column(Integer, nullable=False, default=0)
    views = Column(Integer, default=0)
    favourites = Column(Integer, default=0)
    comments = Column(Integer, default=0)
    gallery_folderid = Column(String)
    url = Column(String)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class StatsSnapshot(Base):
    """Daily snapshots of deviation statistics."""
    
    __tablename__ = 'stats_snapshots'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    deviationid = Column(String, nullable=False, index=True)
    snapshot_date = Column(String, nullable=False, index=True)
    views = Column(Integer, default=0)
    favourites = Column(Integer, default=0)
    comments = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        Index('idx_stats_snapshots_deviationid_date', 'deviationid', 'snapshot_date', unique=True),
    )


class UserStatsSnapshot(Base):
    """Daily snapshots of user watcher statistics."""
    
    __tablename__ = 'user_stats_snapshots'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer)
    username = Column(String, nullable=False)
    snapshot_date = Column(String, nullable=False)
    watchers = Column(Integer, default=0)
    friends = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        Index('idx_user_stats_snapshots_username_date', 'username', 'snapshot_date', unique=True),
    )


class DeviationMetadata(Base):
    """Extended deviation metadata from DeviantArt."""
    
    __tablename__ = 'deviation_metadata'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    deviationid = Column(String, nullable=False, unique=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text)
    license = Column(String)
    allows_comments = Column(Integer)
    tags = Column(Text)
    is_favourited = Column(Integer)
    is_watching = Column(Integer)
    is_mature = Column(Integer)
    mature_level = Column(String)
    mature_classification = Column(String)
    printid = Column(String)
    author = Column(String)
    creation_time = Column(String)
    category = Column(String)
    file_size = Column(String)
    resolution = Column(String)
    submitted_with = Column(String)
    stats_json = Column(Text)
    camera = Column(String)
    collections = Column(Text)
    galleries = Column(Text)
    can_post_comment = Column(Integer)
    stats_views_today = Column(Integer)
    stats_downloads_today = Column(Integer)
    stats_downloads = Column(Integer)
    stats_views = Column(Integer)
    stats_favourites = Column(Integer)
    stats_comments = Column(Integer)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class UploadPreset(Base):
    """Upload preset configuration for batch deviation uploads."""
    
    __tablename__ = 'upload_presets'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True, index=True)
    description = Column(Text)
    
    # Title generation parameters
    base_title = Column(String, nullable=False)
    title_increment_start = Column(Integer, default=1)
    last_used_increment = Column(Integer, default=1)
    
    # Stash parameters
    artist_comments = Column(Text)
    tags = Column(Text)  # JSON array
    is_ai_generated = Column(Integer, default=1)
    noai = Column(Integer, default=0)
    is_dirty = Column(Integer, default=0)
    
    # Publish parameters
    is_mature = Column(Integer, default=0)
    mature_level = Column(String)
    mature_classification = Column(Text)  # JSON array
    feature = Column(Integer, default=1)
    allow_comments = Column(Integer, default=1)
    display_resolution = Column(Integer, default=0)
    allow_free_download = Column(Integer, default=0)
    add_watermark = Column(Integer, default=0)
    
    # Gallery selection
    gallery_folderid = Column(String)
    
    # Metadata
    is_default = Column(Integer, default=0, index=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class FeedState(Base):
    """Key-value store for feed cursor and other state."""

    __tablename__ = 'feed_state'

    key = Column(String, primary_key=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class FeedDeviation(Base):
    """Queue of deviations from feed for auto-faving."""

    __tablename__ = 'feed_deviations'

    deviationid = Column(String, primary_key=True)
    ts = Column(Integer, nullable=False)
    status = Column(String, nullable=False, default='pending', index=True)
    attempts = Column(Integer, default=0)
    last_error = Column(Text)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index('idx_feed_deviations_status_ts', 'status', 'ts'),
    )
