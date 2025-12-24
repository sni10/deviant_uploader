"""Tests for BaseService class."""
import pytest
from unittest.mock import Mock, MagicMock, patch
from logging import Logger

from src.service.base_service import BaseService
from src.service.http_client import DeviantArtHttpClient


class ConcreteService(BaseService):
    """Concrete implementation of BaseService for testing."""

    pass


class TestBaseService:
    """Test BaseService initialization and properties."""

    def test_initialization_with_logger_only(self):
        """Test creating service with only logger."""
        logger = Mock(spec=Logger)

        service = ConcreteService(logger=logger)

        assert service.logger is logger
        assert service._token_repo is None
        assert service.http_client is None
        assert service._config is None

    def test_initialization_with_token_repo_creates_http_client(self):
        """Test that http_client is auto-created when token_repo provided."""
        logger = Mock(spec=Logger)
        token_repo = Mock()

        with patch(
            "src.service.base_service.DeviantArtHttpClient"
        ) as mock_http_client_class:
            mock_http_client = Mock(spec=DeviantArtHttpClient)
            mock_http_client_class.return_value = mock_http_client

            service = ConcreteService(logger=logger, token_repo=token_repo)

            assert service.logger is logger
            assert service._token_repo is token_repo
            assert service.http_client is mock_http_client
            mock_http_client_class.assert_called_once_with(
                logger=logger, token_repo=token_repo
            )

    def test_initialization_with_provided_http_client(self):
        """Test that provided http_client is used instead of auto-creation."""
        logger = Mock(spec=Logger)
        token_repo = Mock()
        custom_http_client = Mock(spec=DeviantArtHttpClient)

        service = ConcreteService(
            logger=logger, token_repo=token_repo, http_client=custom_http_client
        )

        assert service.logger is logger
        assert service._token_repo is token_repo
        assert service.http_client is custom_http_client

    def test_initialization_with_http_client_but_no_token_repo(self):
        """Test initialization with http_client but no token_repo."""
        logger = Mock(spec=Logger)
        custom_http_client = Mock(spec=DeviantArtHttpClient)

        service = ConcreteService(logger=logger, http_client=custom_http_client)

        assert service.logger is logger
        assert service._token_repo is None
        assert service.http_client is custom_http_client

    def test_config_property_lazy_loading(self):
        """Test that config property lazy-loads configuration."""
        logger = Mock(spec=Logger)

        with patch("src.service.base_service.get_config") as mock_get_config:
            mock_config = Mock()
            mock_get_config.return_value = mock_config

            service = ConcreteService(logger=logger)

            # Config not loaded yet
            assert service._config is None

            # First access triggers loading
            config1 = service.config
            assert config1 is mock_config
            mock_get_config.assert_called_once()

            # Second access returns cached value
            config2 = service.config
            assert config2 is mock_config
            mock_get_config.assert_called_once()  # Still only called once

    def test_config_property_caches_value(self):
        """Test that config property caches the loaded configuration."""
        logger = Mock(spec=Logger)

        with patch("src.service.base_service.get_config") as mock_get_config:
            mock_config = Mock()
            mock_get_config.return_value = mock_config

            service = ConcreteService(logger=logger)

            # Access config multiple times
            for _ in range(5):
                config = service.config
                assert config is mock_config

            # get_config should only be called once due to caching
            mock_get_config.assert_called_once()
