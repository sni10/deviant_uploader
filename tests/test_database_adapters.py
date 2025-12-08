"""Tests for database adapters and abstraction layer."""

import pytest
import tempfile
import os
from pathlib import Path

from src.storage.adapters import SQLiteAdapter, SQLiteConnection
from src.storage.adapters.base import DatabaseAdapter
from src.storage.base_repository import DBConnection
from src.storage.database import get_database_adapter, get_connection


class TestSQLiteConnection:
    """Test SQLiteConnection wrapper implements DBConnection protocol."""
    
    def test_sqlite_connection_implements_protocol(self):
        """Test that SQLiteConnection implements DBConnection protocol."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name
        
        try:
            adapter = SQLiteAdapter(db_path)
            adapter.initialize()
            conn = adapter.get_connection()
            
            # Verify it's recognized as DBConnection
            assert isinstance(conn, DBConnection)
            
            conn.close()
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)
    
    def test_sqlite_connection_execute(self):
        """Test SQLiteConnection execute method."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name
        
        try:
            adapter = SQLiteAdapter(db_path)
            adapter.initialize()
            conn = adapter.get_connection()
            
            # Test execute without parameters
            cursor = conn.execute("SELECT 1")
            result = cursor.fetchone()
            assert result[0] == 1
            
            # Test execute with parameters
            cursor = conn.execute("SELECT ? + ?", (2, 3))
            result = cursor.fetchone()
            assert result[0] == 5
            
            conn.close()
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)
    
    def test_sqlite_connection_commit(self):
        """Test SQLiteConnection commit method."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name
        
        try:
            adapter = SQLiteAdapter(db_path)
            adapter.initialize()
            conn = adapter.get_connection()
            
            # Insert data
            conn.execute("INSERT INTO users (userid, username, type) VALUES (?, ?, ?)",
                        ('test123', 'testuser', 'regular'))
            conn.commit()
            
            # Verify data was committed
            cursor = conn.execute("SELECT username FROM users WHERE userid = ?", ('test123',))
            result = cursor.fetchone()
            assert result[0] == 'testuser'
            
            conn.close()
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)


class TestSQLiteAdapter:
    """Test SQLiteAdapter implementation."""
    
    def test_sqlite_adapter_implements_protocol(self):
        """Test that SQLiteAdapter implements DatabaseAdapter protocol."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name
        
        try:
            adapter = SQLiteAdapter(db_path)
            # Verify it's recognized as DatabaseAdapter
            assert isinstance(adapter, DatabaseAdapter)
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)
    
    def test_sqlite_adapter_initialize(self):
        """Test SQLiteAdapter initialization creates schema."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name
        
        try:
            adapter = SQLiteAdapter(db_path)
            adapter.initialize()
            
            # Verify database file exists
            assert os.path.exists(db_path)
            
            # Verify tables were created
            conn = adapter.get_connection()
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            tables = [row[0] for row in cursor.fetchall()]
            
            # Check for key tables
            assert 'users' in tables
            assert 'oauth_tokens' in tables
            assert 'galleries' in tables
            assert 'deviations' in tables
            assert 'deviation_stats' in tables
            
            conn.close()
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)
    
    def test_sqlite_adapter_get_connection(self):
        """Test SQLiteAdapter get_connection returns valid connection."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name
        
        try:
            adapter = SQLiteAdapter(db_path)
            adapter.initialize()
            
            conn = adapter.get_connection()
            assert conn is not None
            assert isinstance(conn, DBConnection)
            
            # Test connection works
            cursor = conn.execute("SELECT 1")
            assert cursor.fetchone()[0] == 1
            
            conn.close()
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)


class TestDatabaseFactory:
    """Test database factory functions."""
    
    def test_get_database_adapter_sqlite(self, monkeypatch):
        """Test get_database_adapter returns SQLiteAdapter for sqlite type."""
        # Mock config to return sqlite type
        from src.config import Config
        
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name
        
        try:
            # Create a mock config
            def mock_get_config():
                config = Config()
                config.database_type = 'sqlite'
                config.database_path = Path(db_path)
                return config
            
            monkeypatch.setattr('src.config.get_config', mock_get_config)
            
            adapter = get_database_adapter()
            assert isinstance(adapter, SQLiteAdapter)
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)
    
    def test_get_database_adapter_unsupported_type(self, monkeypatch):
        """Test get_database_adapter raises error for unsupported type."""
        from src.config import Config
        
        def mock_get_config():
            config = Config()
            config.database_type = 'mongodb'  # Unsupported
            return config
        
        monkeypatch.setattr('src.config.get_config', mock_get_config)
        
        with pytest.raises(ValueError, match="Unsupported DATABASE_TYPE"):
            get_database_adapter()
    
    def test_get_connection_function(self, monkeypatch):
        """Test get_connection convenience function."""
        from src.config import Config
        
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name
        
        try:
            def mock_get_config():
                config = Config()
                config.database_type = 'sqlite'
                config.database_path = Path(db_path)
                return config
            
            monkeypatch.setattr('src.config.get_config', mock_get_config)
            
            conn = get_connection()
            assert isinstance(conn, DBConnection)
            
            # Verify connection works
            cursor = conn.execute("SELECT 1")
            assert cursor.fetchone()[0] == 1
            
            conn.close()
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)
