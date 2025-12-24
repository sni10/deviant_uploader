"""Base service with common initialization logic for all services.

This module provides a base class that unifies common initialization patterns
across all services in the application, including logger setup, HTTP client
initialization, and configuration management.
"""
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

    This class eliminates duplicated initialization code across services
    by providing a single source of truth for common dependencies.
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
            token_repo: Optional OAuth token repository for HTTP client
            http_client: Optional HTTP client (auto-created if token_repo
                provided and http_client is None)
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
            Application configuration instance from get_config()
        """
        if self._config is None:
            self._config = get_config()
        return self._config
