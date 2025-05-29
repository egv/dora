"""Configuration models for the application."""

import os
from typing import Dict, Optional, List
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
    perplexity_api_key: Optional[str] = None  # Deprecated - using WebSearchTool instead


class DoraConfig(BaseSettings):
    """Main configuration for the Dora application."""

    # API Keys
    openai_api_key: str = Field(default="", env="OPENAI_API_KEY")
    perplexity_api_key: Optional[str] = Field(default=None, env="PERPLEXITY_API_KEY")  # Deprecated - using WebSearchTool
    telegram_api_key: str = Field(default="", env="TELEGRAM_API_KEY")
    
    # Memory cache configuration
    memory_cache_enabled: bool = Field(default=True, env="MEMORY_CACHE_ENABLED")
    memory_cache_path: str = Field(default="./cache/dora_memory.db", env="MEMORY_CACHE_PATH")
    memory_cache_ttl_days: int = Field(default=7, env="MEMORY_CACHE_TTL_DAYS")
    memory_cache_max_size_mb: int = Field(default=100, env="MEMORY_CACHE_MAX_SIZE_MB")
    
    # HTTP Server configuration
    http_enabled: bool = Field(default=True, env="HTTP_ENABLED")
    http_host: str = Field(default="0.0.0.0", env="HTTP_HOST")
    http_port: int = Field(default=8000, env="HTTP_PORT")
    http_api_keys: List[str] = Field(default_factory=list, env="HTTP_API_KEYS", description="Comma-separated list of API keys")
    http_rate_limit: int = Field(default=100, env="HTTP_RATE_LIMIT", description="Requests per minute")
    
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
            system_prompt="You are an event finder agent that finds events in a specified city using web search."
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
            perplexity_api_key=self.perplexity_api_key,  # Deprecated but kept for compatibility
        )