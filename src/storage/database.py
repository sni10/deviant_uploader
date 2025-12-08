"""Database schema and initialization."""
import sqlite3
from pathlib import Path


DATABASE_SCHEMA = """
-- Users table: stores DeviantArt user information
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    userid TEXT NOT NULL UNIQUE,
    username TEXT NOT NULL,
    usericon TEXT,
    type TEXT NOT NULL,
    
    -- Extended profile information
    is_watching INTEGER,
    profile_url TEXT,
    user_is_artist INTEGER,
    artist_level TEXT,
    artist_specialty TEXT,
    real_name TEXT,
    tagline TEXT,
    country_id INTEGER,
    country TEXT,
    website TEXT,
    bio TEXT,
    
    -- Statistics
    user_deviations INTEGER,
    user_favourites INTEGER,
    user_comments INTEGER,
    profile_pageviews INTEGER,
    profile_comments INTEGER,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for faster user lookups by userid
CREATE INDEX IF NOT EXISTS idx_users_userid ON users(userid);

-- Index for faster user lookups by username
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

-- OAuth tokens table: stores access and refresh tokens
CREATE TABLE IF NOT EXISTS oauth_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    access_token TEXT NOT NULL,
    refresh_token TEXT NOT NULL,
    token_type TEXT NOT NULL DEFAULT 'Bearer',
    expires_at TIMESTAMP NOT NULL,
    scope TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Index for faster token lookups by user_id
CREATE INDEX IF NOT EXISTS idx_oauth_tokens_user_id ON oauth_tokens(user_id);

-- Galleries table: stores DeviantArt gallery folders
CREATE TABLE IF NOT EXISTS galleries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    folderid TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    parent TEXT,
    size INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Index for faster gallery lookups by folderid
CREATE INDEX IF NOT EXISTS idx_galleries_folderid ON galleries(folderid);

-- Index for faster gallery lookups by user_id
CREATE INDEX IF NOT EXISTS idx_galleries_user_id ON galleries(user_id);

-- Deviations table: tracks uploaded deviations
CREATE TABLE IF NOT EXISTS deviations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    filename TEXT NOT NULL,
    title TEXT NOT NULL,
    file_path TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new',
    
    -- DeviantArt submission parameters
    is_mature INTEGER NOT NULL DEFAULT 0,
    mature_level TEXT,
    mature_classification TEXT,  -- JSON array
    feature INTEGER DEFAULT 1,
    allow_comments INTEGER DEFAULT 1,
    display_resolution INTEGER DEFAULT 0,
    tags TEXT,  -- JSON array
    allow_free_download INTEGER DEFAULT 0,
    add_watermark INTEGER DEFAULT 0,
    is_ai_generated INTEGER DEFAULT 0,
    noai INTEGER DEFAULT 0,
    
    -- Stash submit parameters
    artist_comments TEXT,  -- Additional information about the submission
    original_url TEXT,  -- Link to original if posted elsewhere
    is_dirty INTEGER DEFAULT 0,  -- Flag to warn users that item is being edited
    stack TEXT,  -- Stack name to place submission in
    stackid INTEGER,  -- Stack ID to place submission in
    
    -- Upload results
    itemid INTEGER,  -- Stash item ID
    gallery_id INTEGER,  -- Internal DB ID of gallery (references galleries table)
    deviationid TEXT,  -- UUID from DeviantArt
    url TEXT,  -- Published deviation URL
    error TEXT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    uploaded_at TIMESTAMP,
    published_time TEXT,
    
    UNIQUE(filename),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Current deviation statistics
CREATE TABLE IF NOT EXISTS deviation_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    deviationid TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    thumb_url TEXT,
    is_mature INTEGER NOT NULL DEFAULT 0,
    views INTEGER DEFAULT 0,
    favourites INTEGER DEFAULT 0,
    comments INTEGER DEFAULT 0,
    gallery_folderid TEXT,
    url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_deviation_stats_deviationid ON deviation_stats(deviationid);

    -- Daily snapshots of deviation statistics
    CREATE TABLE IF NOT EXISTS stats_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    deviationid TEXT NOT NULL,
    snapshot_date TEXT NOT NULL,
    views INTEGER DEFAULT 0,
    favourites INTEGER DEFAULT 0,
    comments INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(deviationid, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_stats_snapshots_date ON stats_snapshots(snapshot_date);
CREATE INDEX IF NOT EXISTS idx_stats_snapshots_deviationid ON stats_snapshots(deviationid);

-- Daily snapshots of user watcher statistics
CREATE TABLE IF NOT EXISTS user_stats_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    username TEXT NOT NULL,
    snapshot_date TEXT NOT NULL,
    watchers INTEGER DEFAULT 0,
    friends INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(username, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_user_stats_snapshots_username_date
    ON user_stats_snapshots(username, snapshot_date);

-- Extended deviation metadata (latest snapshot from DeviantArt)
CREATE TABLE IF NOT EXISTS deviation_metadata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    deviationid TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    description TEXT,
    license TEXT,
    allows_comments INTEGER,
    tags TEXT,
    is_favourited INTEGER,
    is_watching INTEGER,
    is_mature INTEGER,
    mature_level TEXT,
    mature_classification TEXT,
    printid TEXT,
    author TEXT,
    creation_time TEXT,
    category TEXT,
    file_size TEXT,
    resolution TEXT,
    submitted_with TEXT,
    stats_json TEXT,
    camera TEXT,
    collections TEXT,
    galleries TEXT,
    can_post_comment INTEGER,
    stats_views_today INTEGER,
    stats_downloads_today INTEGER,
    stats_downloads INTEGER,
    stats_views INTEGER,
    stats_favourites INTEGER,
    stats_comments INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_deviation_metadata_deviationid ON deviation_metadata(deviationid);

-- Index for faster status queries
CREATE INDEX IF NOT EXISTS idx_deviations_status ON deviations(status);

-- Index for faster filename lookups
CREATE INDEX IF NOT EXISTS idx_deviations_filename ON deviations(filename);

-- Index for faster deviation lookups by user_id
CREATE INDEX IF NOT EXISTS idx_deviations_user_id ON deviations(user_id);
"""


def _migrate_database(conn: sqlite3.Connection) -> None:
    """Migrate existing database to add missing columns.
    
    This function checks for missing columns in tables and adds them
    if they don't exist. This ensures backward compatibility with
    databases created before new fields were added.
    
    Args:
        conn: Database connection
    """
    # Migration 1: Add Stash submit fields and publication time to deviations table
    cursor = conn.execute("PRAGMA table_info(deviations)")
    deviation_columns = {row[1] for row in cursor.fetchall()}
    
    stash_columns = {
        'artist_comments': 'TEXT',
        'original_url': 'TEXT',
        'is_dirty': 'INTEGER DEFAULT 0',
        'stack': 'TEXT',
        'stackid': 'INTEGER',
    }
    for column_name, column_type in stash_columns.items():
        if column_name not in deviation_columns:
            try:
                conn.execute(f"ALTER TABLE deviations ADD COLUMN {column_name} {column_type}")
                conn.commit()
                print(f"✓ Migration: Added column deviations.{column_name}")
            except sqlite3.OperationalError as e:
                print(f"Warning: Could not add column deviations.{column_name}: {e}")

    # Add published_time column for remote deviation publication datetime
    if 'published_time' not in deviation_columns:
        try:
            conn.execute("ALTER TABLE deviations ADD COLUMN published_time TEXT")
            conn.commit()
            print("✓ Migration: Added column deviations.published_time")
        except sqlite3.OperationalError as e:
            print(f"Warning: Could not add column deviations.published_time: {e}")
    
    # Migration 2: Add user_id foreign keys to existing tables
    # Check and add user_id to oauth_tokens
    cursor = conn.execute("PRAGMA table_info(oauth_tokens)")
    token_columns = {row[1] for row in cursor.fetchall()}
    if 'user_id' not in token_columns:
        try:
            conn.execute("ALTER TABLE oauth_tokens ADD COLUMN user_id INTEGER")
            conn.commit()
            print(f"✓ Migration: Added column oauth_tokens.user_id")
        except sqlite3.OperationalError as e:
            print(f"Warning: Could not add column oauth_tokens.user_id: {e}")
    
    # Check and add user_id to galleries
    cursor = conn.execute("PRAGMA table_info(galleries)")
    gallery_columns = {row[1] for row in cursor.fetchall()}
    if 'user_id' not in gallery_columns:
        try:
            conn.execute("ALTER TABLE galleries ADD COLUMN user_id INTEGER")
            conn.commit()
            print(f"✓ Migration: Added column galleries.user_id")
        except sqlite3.OperationalError as e:
            print(f"Warning: Could not add column galleries.user_id: {e}")
    
    # Check and add user_id to deviations (refresh column list first)
    cursor = conn.execute("PRAGMA table_info(deviations)")
    deviation_columns = {row[1] for row in cursor.fetchall()}
    if 'user_id' not in deviation_columns:
        try:
            conn.execute("ALTER TABLE deviations ADD COLUMN user_id INTEGER")
            conn.commit()
            print(f"✓ Migration: Added column deviations.user_id")
        except sqlite3.OperationalError as e:
            print(f"Warning: Could not add column deviations.user_id: {e}")

    # Migration 3: Add is_mature to deviation_stats
    cursor = conn.execute("PRAGMA table_info(deviation_stats)")
    deviation_stats_columns = {row[1] for row in cursor.fetchall()}
    if 'is_mature' not in deviation_stats_columns:
        try:
            conn.execute("ALTER TABLE deviation_stats ADD COLUMN is_mature INTEGER NOT NULL DEFAULT 0")
            conn.commit()
            print("✓ Migration: Added column deviation_stats.is_mature")
        except sqlite3.OperationalError as e:
            print(f"Warning: Could not add column deviation_stats.is_mature: {e}")

    # Migration 4: Add url to deviation_stats
    if 'url' not in deviation_stats_columns:
        try:
            conn.execute("ALTER TABLE deviation_stats ADD COLUMN url TEXT")
            conn.commit()
            print("✓ Migration: Added column deviation_stats.url")
        except sqlite3.OperationalError as e:
            print(f"Warning: Could not add column deviation_stats.url: {e}")


def init_database(db_path: str | Path) -> sqlite3.Connection:
    """
    Initialize database with schema (legacy function for backward compatibility).
    
    This function is kept for backward compatibility with existing code.
    New code should use get_database_adapter() and get_connection() instead.
    
    Args:
        db_path: Path to SQLite database file
        
    Returns:
        Database connection
    """
    db_path = Path(db_path)
    
    # Ensure data directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Connect and enable foreign keys
    # check_same_thread=False is required because the Flask dev server can
    # handle requests in a different thread than the one that created the
    # connection. This preserves the single shared connection while avoiding
    # sqlite3.ProgrammingError about cross-thread usage.
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    
    # Initialize schema
    conn.executescript(DATABASE_SCHEMA)
    conn.commit()
    
    # Migrate existing database (add missing columns if needed)
    _migrate_database(conn)
    
    return conn


def get_database_adapter():
    """
    Factory function to create the appropriate database adapter based on configuration.
    
    This function reads the DATABASE_TYPE from configuration and returns:
    - SQLiteAdapter for 'sqlite' (default)
    - SQLAlchemyAdapter for 'postgresql'
    
    The adapter provides a consistent interface for database operations
    regardless of the underlying backend.
    
    Returns:
        DatabaseAdapter instance (SQLiteAdapter or SQLAlchemyAdapter)
        
    Raises:
        ValueError: If DATABASE_TYPE is not supported
        
    Example:
        >>> from src.config import get_config
        >>> adapter = get_database_adapter()
        >>> adapter.initialize()
        >>> conn = adapter.get_connection()
    """
    from .adapters import SQLiteAdapter, SQLAlchemyAdapter
    from ..config import get_config
    
    config = get_config()
    db_type = config.database_type
    
    if db_type == 'sqlite':
        return SQLiteAdapter(config.database_path)
    elif db_type == 'postgresql':
        if not config.database_url:
            raise ValueError(
                "DATABASE_URL is required when DATABASE_TYPE is 'postgresql'. "
                "Example: postgresql://user:password@localhost:5432/deviant"
            )
        return SQLAlchemyAdapter(config.database_url)
    else:
        raise ValueError(
            f"Unsupported DATABASE_TYPE: '{db_type}'. "
            f"Supported types: 'sqlite', 'postgresql'"
        )


def get_connection():
    """
    Convenience function to get a database connection using the configured adapter.
    
    This is the recommended way to obtain database connections in application code.
    It automatically selects the correct backend based on configuration and
    returns a connection implementing the DBConnection protocol.
    
    Returns:
        DBConnection instance compatible with all repositories
        
    Example:
        >>> from src.storage.database import get_connection
        >>> from src.storage.user_repository import UserRepository
        >>> 
        >>> conn = get_connection()
        >>> user_repo = UserRepository(conn)
        >>> # ... use repository
        >>> conn.close()
    """
    adapter = get_database_adapter()
    adapter.initialize()
    return adapter.get_connection()
