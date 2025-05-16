"""Integration tests for Dora application."""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dora.agents.event_classifier import EventClassifierAgent
from dora.agents.event_finder import EventFinderAgent
from dora.agents.language_selector import LanguageSelectorAgent
from dora.agents.orchestrator import OrchestratorAgent
from dora.agents.text_writer import TextWriterAgent
from dora.models.config import DoraConfig
from dora.models.messages import ProcessCityRequest, ProcessCityResponse


class TestIntegration(unittest.TestCase):
    """Integration tests for Dora."""

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test_openai_key", "PERPLEXITY_API_KEY": "test_perplexity_key"})
    @patch("openai_agents.Agent")
    @patch("openai_agents.Threads")
    def test_orchestrator_creation(self, mock_threads, mock_agent):
        """Test that the orchestrator can be created with all agents."""
        # Mock OpenAI responses
        mock_threads.return_value.create.return_value.id = "test_thread_id"
        mock_threads.return_value.run.return_value.id = "test_run_id"
        mock_threads.return_value.wait_for_run.return_value = {"status": "completed"}
        mock_threads.return_value.get_messages.return_value = [
            {"content": "[]"}
        ]
        
        # Create config
        config = DoraConfig()
        
        # Create agents
        event_finder = EventFinderAgent(config)
        event_classifier = EventClassifierAgent(config)
        language_selector = LanguageSelectorAgent(config)
        text_writer = TextWriterAgent(config)
        
        # Create orchestrator
        orchestrator = OrchestratorAgent(
            config=config,
            event_finder=event_finder,
            event_classifier=event_classifier,
            language_selector=language_selector,
            text_writer=text_writer,
        )
        
        # Assert orchestrator has all agents
        self.assertEqual(orchestrator.event_finder, event_finder)
        self.assertEqual(orchestrator.event_classifier, event_classifier)
        self.assertEqual(orchestrator.language_selector, language_selector)
        self.assertEqual(orchestrator.text_writer, text_writer)
        
        # Assert orchestrator has tools
        self.assertTrue(len(orchestrator.tools) > 0)
        self.assertTrue(any(tool.name == "find_events" for tool in orchestrator.tools))
        self.assertTrue(any(tool.name == "classify_event" for tool in orchestrator.tools))
        self.assertTrue(any(tool.name == "get_city_languages" for tool in orchestrator.tools))
        self.assertTrue(any(tool.name == "generate_notification" for tool in orchestrator.tools))


if __name__ == "__main__":
    unittest.main()