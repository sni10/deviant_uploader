"""Fix watchers table sequence synchronization issue.

This script resets the watchers_watcher_id_seq sequence to the correct value
based on the maximum existing watcher_id in the table.

Run this script once to fix the sequence after data migration or manual inserts.
"""

from src.config import get_config
from src.storage.adapters.sqlalchemy_adapter import SQLAlchemyAdapter
from src.log.logger import setup_logger

logger = setup_logger()


def fix_watcher_sequence():
    """Reset watchers sequence to max(watcher_id) + 1."""
    config = get_config()
    
    # Only works with PostgreSQL
    if not config.database_url or not config.database_url.startswith('postgresql'):
        logger.error("This script only works with PostgreSQL database")
        return
    
    adapter = SQLAlchemyAdapter(config.database_url)
    adapter.initialize()
    conn = adapter.get_connection()
    
    try:
        # Get the maximum watcher_id
        result = conn.execute(
            "SELECT COALESCE(MAX(watcher_id), 0) FROM watchers"
        )
        max_id = result.scalar()
        
        logger.info(f"Current maximum watcher_id: {max_id}")
        
        # Reset the sequence to max_id + 1
        conn.execute(
            f"SELECT setval('watchers_watcher_id_seq', {max_id + 1}, false)"
        )
        conn.commit()
        
        logger.info(f"Sequence reset to {max_id + 1}")
        logger.info("Watcher sequence synchronization completed successfully")
        
    except Exception as e:
        logger.error(f"Failed to fix watcher sequence: {e}", exc_info=True)
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    fix_watcher_sequence()
