"""Configuration models for the application."""

import os
from typing import Dict, Optional
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class AgentConfig(BaseModel):
    """Configuration for an individual agent."""

    model: str = "gpt-4o"
    temperature: float = 0.2
    system_prompt: Optional[str] = None
    tools: Optional[Dict] = None


class APIConfig(BaseModel):
    """API Configuration."""

    openai_api_key: str
    perplexity_api_key: str


class DoraConfig(BaseSettings):
    """Main configuration for the Dora application."""

    # API Keys
    openai_api_key: str = Field(default="", env="OPENAI_API_KEY")
    perplexity_api_key: str = Field(default="", env="PERPLEXITY_API_KEY")
    telegram_api_key: str = Field(default="", env="TELEGRAM_API_KEY")
    
    # Agent Configurations
    orchestrator_config: AgentConfig = Field(
        default_factory=lambda: AgentConfig(
            model="gpt-4o",
            temperature=0.1,
            system_prompt="You are an orchestration agent that coordinates other agents to find and classify events in cities, determine languages spoken, and generate notifications."
        )
    )
    
    event_finder_config: AgentConfig = Field(
        default_factory=lambda: AgentConfig(
            model="gpt-4o",
            temperature=0.7,
            system_prompt="You are an event finder agent that finds events in a specified city using Perplexity API."
        )
    )
    
    event_classifier_config: AgentConfig = Field(
        default_factory=lambda: AgentConfig(
            model="gpt-4o",
            temperature=0.2,
            system_prompt="You are an event classifier agent that estimates event size, importance, and identifies target audiences."
        )
    )
    
    language_selector_config: AgentConfig = Field(
        default_factory=lambda: AgentConfig(
            model="gpt-4o",
            temperature=0.2,
            system_prompt="You are a language selector agent that determines languages commonly spoken in a specified city."
        )
    )
    
    text_writer_config: AgentConfig = Field(
        default_factory=lambda: AgentConfig(
            model="gpt-4o",
            temperature=0.7,
            system_prompt="You are a text writer agent that creates engaging push notifications in different languages for specific target audiences."
        )
    )
    
    class Config:
        """Pydantic config."""
        
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
    
    def get_api_config(self) -> APIConfig:
        """Get API configuration."""
        return APIConfig(
            openai_api_key=self.openai_api_key,
            perplexity_api_key=self.perplexity_api_key,
        )