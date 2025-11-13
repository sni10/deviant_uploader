"""Filesystem utility functions."""
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any


# Windows reserved names
WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"
}


def slugify(title: str, max_length: int = 150) -> str:
    """
    Convert title to a safe filesystem slug.
    
    - Removes invalid characters for Windows: <>:"/\\|?*
    - Removes control characters
    - Trims length
    - Handles Windows reserved names
    - Removes trailing dots and spaces
    
    Args:
        title: Original title string
        max_length: Maximum length of slug
        
    Returns:
        Safe filesystem slug
    """
    if not title or not title.strip():
        return "untitled"
    
    # Replace newlines with spaces
    slug = title.strip().replace("\n", " ").replace("\r", " ")
    
    # Remove invalid Windows characters
    slug = re.sub(r'[<>:"/\\|?*]', " ", slug)
    
    # Remove control characters
    slug = re.sub(r'[\x00-\x1f\x7f]', "", slug)
    
    # Collapse multiple spaces
    slug = re.sub(r'\s+', " ", slug).strip()
    
    # Limit length
    slug = slug[:max_length]
    
    # Check for Windows reserved names
    if slug.upper() in WINDOWS_RESERVED:
        slug = f"_{slug}"
    
    # Remove trailing dots and spaces (Windows requirement)
    slug = slug.rstrip(" .")
    
    # Final check if empty
    if not slug:
        return "untitled"
    
    return slug


def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename to be safe for Windows filesystem.
    
    Args:
        filename: Original filename
        
    Returns:
        Sanitized filename
    """
    if not filename:
        return "unnamed"
    
    # Keep extension separate
    path = Path(filename)
    name = path.stem
    ext = path.suffix
    
    # Sanitize the name part
    name = slugify(name, max_length=200)
    
    # Reconstruct with extension
    return f"{name}{ext}"


def atomic_write_jsonl(path: str | Path, rows: list[dict[str, Any]]) -> None:
    """
    Atomically write JSONL file.
    
    Writes to a temporary file first, then replaces the target file.
    This ensures the file is never corrupted even if the process crashes.
    
    Args:
        path: Target file path
        rows: List of dictionaries to write as JSONL
    """
    path = Path(path)
    
    # Ensure directory exists
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write to temporary file in the same directory
    with tempfile.NamedTemporaryFile(
        mode="w",
        delete=False,
        dir=path.parent,
        encoding="utf-8",
        newline="\n",
        suffix=".tmp"
    ) as tf:
        for row in rows:
            tf.write(json.dumps(row, ensure_ascii=False) + "\n")
        tmp_path = tf.name
    
    # Atomic replace
    os.replace(tmp_path, path)


def ensure_directory(path: str | Path) -> Path:
    """
    Ensure directory exists with proper permissions.
    
    Args:
        path: Directory path
        
    Returns:
        Path object of the created/existing directory
    """
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path
