"""Pytest configuration for Dora tests."""

import os
import pytest
from unittest.mock import patch

from dora.models.config import DoraConfig


@pytest.fixture(scope="session", autouse=True)
def mock_env_vars():
    """Mock environment variables for testing."""
    with patch.dict(os.environ, {
        "OPENAI_API_KEY": "test_openai_key",
        "PERPLEXITY_API_KEY": "test_perplexity_key",
    }):
        yield


@pytest.fixture
def dora_config():
    """Create a DoraConfig for testing."""
    return DoraConfig(
        openai_api_key="test_openai_key",
        perplexity_api_key="test_perplexity_key",
    )