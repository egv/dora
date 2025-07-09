"""
Basic infrastructure tests to verify project setup
"""

import pytest
from pathlib import Path


def test_project_structure():
    """Test that all required directories exist"""
    base_dir = Path(__file__).parent.parent
    
    required_dirs = [
        "agents",
        "mcp_tools", 
        "models",
        "api",
        "tests",
        "docs"
    ]
    
    for dir_name in required_dirs:
        assert (base_dir / dir_name).exists(), f"Directory {dir_name} should exist"


def test_imports():
    """Test that basic imports work"""
    import agents
    import models
    import mcp_tools
    import api
    
    # Test version attributes
    assert hasattr(agents, '__version__')
    assert hasattr(models, '__version__')
    assert hasattr(mcp_tools, '__version__')
    assert hasattr(api, '__version__')


def test_dependencies():
    """Test that key dependencies can be imported"""
    try:
        import pydantic_ai
        import fastapi
        import redis
        import psycopg2
        import structlog
        # A2A SDK imports
        from a2a.types import AgentCard
        from a2a.server.apps.jsonrpc.fastapi_app import A2AFastAPIApplication
    except ImportError as e:
        pytest.fail(f"Failed to import required dependency: {e}")


def test_environment_template():
    """Test that .env.example exists and has required keys"""
    base_dir = Path(__file__).parent.parent
    env_example = base_dir / ".env.example"
    
    assert env_example.exists(), ".env.example should exist"
    
    content = env_example.read_text()
    required_keys = [
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY", 
        "PERPLEXITY_API_KEY",
        "DATABASE_URL",
        "REDIS_URL"
    ]
    
    for key in required_keys:
        assert key in content, f"Required environment variable {key} should be in .env.example"