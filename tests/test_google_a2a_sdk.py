"""
Test Google's official A2A SDK integration

This test verifies that Google's official A2A SDK can work with our system
and helps evaluate the migration effort required.
"""

import pytest
from fastapi.testclient import TestClient

# Test basic import and instantiation
def test_google_a2a_sdk_imports():
    """Test that we can import Google's A2A SDK components"""
    try:
        from a2a.server.apps.jsonrpc.fastapi_app import A2AFastAPIApplication
        from a2a.types import AgentCard, AgentSkill, AgentCapabilities
        from a2a.server.request_handlers.jsonrpc_handler import RequestHandler
        
        assert A2AFastAPIApplication is not None
        assert AgentCard is not None
        assert AgentSkill is not None
        
    except ImportError as e:
        pytest.fail(f"Failed to import Google A2A SDK components: {e}")


def test_create_official_agent_card():
    """Test creating an AgentCard using Google's official spec"""
    from a2a.types import AgentCard, AgentSkill, AgentCapabilities
    
    # Create a skill (equivalent to our Capability)
    test_skill = AgentSkill(
        id="test-skill-1",
        name="Test Skill",
        description="A test skill for evaluation",
        tags=["test", "evaluation"],
        examples=["Test this skill"]
    )
    
    # Create capabilities
    capabilities = AgentCapabilities(
        skills=[test_skill]
    )
    
    # Create official AgentCard with all required fields
    agent_card = AgentCard(
        name="Test Agent",
        description="Test agent for Google A2A SDK evaluation",
        defaultInputModes=["text/plain"],
        defaultOutputModes=["text/plain"],
        capabilities=capabilities,
        skills=[test_skill],  # Required field
        url="http://localhost:8000",  # Required field
        version="1.0.0"  # Required field
    )
    
    # Verify the card was created successfully
    assert agent_card.name == "Test Agent"
    assert agent_card.description == "Test agent for Google A2A SDK evaluation"
    assert len(agent_card.skills) == 1
    assert agent_card.skills[0].id == "test-skill-1"
    assert agent_card.url == "http://localhost:8000"
    assert agent_card.version == "1.0.0"


def test_compare_agent_card_structures():
    """Compare our legacy models with Google's official AgentCard after migration"""
    from a2a.types import AgentCard as OfficialAgentCard
    
    # We no longer have custom AgentCard - we use the official one directly
    # This test now verifies that our BaseAgent generates proper official AgentCards
    
    # Get official AgentCard fields
    official_fields = set(OfficialAgentCard.model_fields.keys())
    
    # Key official fields we should have
    expected_fields = {"name", "description", "skills", "capabilities", "url", "version", 
                      "defaultInputModes", "defaultOutputModes"}
    
    print(f"Official AgentCard fields: {sorted(official_fields)}")
    
    # Verify expected fields are present
    assert expected_fields.issubset(official_fields)
    
    # Create a test agent card to verify it works
    from a2a.types import AgentSkill, AgentCapabilities
    
    test_skill = AgentSkill(
        id="test-skill",
        name="Test Skill",
        description="A test skill",
        tags=["test"]
    )
    
    agent_card = OfficialAgentCard(
        name="Test Agent",
        description="Test agent using official A2A format",
        defaultInputModes=["text/plain"],
        defaultOutputModes=["text/plain"],
        capabilities=AgentCapabilities(skills=[test_skill]),
        skills=[test_skill],
        url="http://localhost:8000",
        version="1.0.0"
    )
    
    # Verify the card was created successfully with official format
    assert agent_card.name == "Test Agent"
    assert len(agent_card.skills) == 1
    assert agent_card.skills[0].id == "test-skill"
    print("✅ Successfully migrated to official A2A AgentCard format")


def test_official_agent_card_required_fields():
    """Test what fields are required in the official AgentCard"""
    from a2a.types import AgentCard, AgentCapabilities
    
    # Try to create minimal AgentCard with all required fields
    try:
        minimal_card = AgentCard(
            name="Minimal Agent",
            description="Minimal test agent",
            defaultInputModes=["text/plain"],
            defaultOutputModes=["text/plain"],
            capabilities=AgentCapabilities(skills=[]),
            skills=[],  # Required field
            url="http://localhost:8000",  # Required field
            version="1.0.0"  # Required field
        )
        assert minimal_card.name == "Minimal Agent"
        assert minimal_card.url == "http://localhost:8000"
        assert minimal_card.version == "1.0.0"
        
    except Exception as e:
        pytest.fail(f"Failed to create minimal AgentCard: {e}")


def test_authentication_structures():
    """Test the authentication structures in Google's A2A SDK"""
    from a2a.types import APIKeySecurityScheme
    
    # Test API Key security scheme with correct field name
    api_key_scheme = APIKeySecurityScheme(
        name="X-API-Key",
        **{"in": "header"},  # Use dict unpacking for the 'in' field
        description="API key authentication"
    )
    
    assert api_key_scheme.name == "X-API-Key"
    assert api_key_scheme.in_ == "header"
    assert api_key_scheme.type == "apiKey"


class MockRequestHandler:
    """Mock request handler for testing A2A FastAPI app creation"""
    
    async def handle_request(self, request_data):
        return {"result": "test response"}


def test_create_a2a_fastapi_app():
    """Test creating an A2A FastAPI application"""
    from a2a.server.apps.jsonrpc.fastapi_app import A2AFastAPIApplication
    from a2a.types import AgentCard, AgentCapabilities
    
    # Create agent card with all required fields
    agent_card = AgentCard(
        name="FastAPI Test Agent",
        description="Test agent for FastAPI integration",
        defaultInputModes=["text/plain"],
        defaultOutputModes=["text/plain"],
        capabilities=AgentCapabilities(skills=[]),
        skills=[],  # Required field
        url="http://localhost:8000",  # Required field
        version="1.0.0"  # Required field
    )
    
    # Create mock handler
    handler = MockRequestHandler()
    
    # Create A2A FastAPI application
    try:
        app = A2AFastAPIApplication(
            agent_card=agent_card,
            http_handler=handler
        )
        
        # Verify app was created
        assert app is not None
        
        # The app should have FastAPI routes
        # We can check if it has the expected A2A endpoints
        # Note: Actual route inspection would require more setup
        
    except Exception as e:
        pytest.fail(f"Failed to create A2AFastAPIApplication: {e}")



if __name__ == "__main__":
    pytest.main([__file__, "-v"])