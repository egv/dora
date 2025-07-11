"""Perplexity proxy server - drop-in replacement for http_server.py with Perplexity proxy functionality."""

import time
import uuid
from typing import Dict, List, Optional, Union, Any, Type
from datetime import datetime
import httpx
import os
from dotenv import load_dotenv

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, create_model, Field as PydanticField
import logging
import json as json_module
from agents import Agent, ModelSettings, Runner, set_default_openai_key

from dora.models.config import DoraConfig
from dora.models.event import EventNotification
from dora.message_parser import MessageParser, ParsedQuery
from dora.__main__ import process_city

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


# Request/Response Models for OpenAI Compatibility

class Message(BaseModel):
    """OpenAI message format."""
    role: str = Field(..., description="Role of the message sender (system, user, assistant)")
    content: str = Field(..., description="Content of the message")
    name: Optional[str] = Field(None, description="Optional name of the sender")


class ResponseFormat(BaseModel):
    """Response format specification."""
    type: str = Field("text", description="Response format type (text, json_object, or json_schema)")
    json_schema: Optional[Dict[str, Any]] = Field(None, description="JSON schema for structured output")


class ChatCompletionRequest(BaseModel):
    """OpenAI-compatible chat completion request."""
    model: str = Field(..., description="Model to use for completion")
    messages: List[Message] = Field(..., description="List of messages in the conversation")
    response_format: Optional[ResponseFormat] = Field(None, description="Response format specification")
    temperature: Optional[float] = Field(0.7, ge=0, le=2, description="Sampling temperature")
    max_tokens: Optional[int] = Field(None, description="Maximum tokens to generate")
    stream: Optional[bool] = Field(False, description="Whether to stream the response")
    n: Optional[int] = Field(1, ge=1, description="Number of completions to generate")
    stop: Optional[Union[str, List[str]]] = Field(None, description="Stop sequences")
    presence_penalty: Optional[float] = Field(0, ge=-2, le=2, description="Presence penalty")
    frequency_penalty: Optional[float] = Field(0, ge=-2, le=2, description="Frequency penalty")
    user: Optional[str] = Field(None, description="Unique identifier for end-user")


class Choice(BaseModel):
    """Response choice."""
    index: int = Field(..., description="Index of the choice")
    message: Message = Field(..., description="Generated message")
    finish_reason: str = Field(..., description="Reason for stopping")
    logprobs: Optional[Any] = Field(None, description="Log probabilities")


class Usage(BaseModel):
    """Token usage information."""
    prompt_tokens: int = Field(..., description="Number of tokens in the prompt")
    completion_tokens: int = Field(..., description="Number of tokens in the completion")
    total_tokens: int = Field(..., description="Total number of tokens")


class ChatCompletionResponse(BaseModel):
    """OpenAI-compatible chat completion response."""
    id: str = Field(..., description="Unique completion ID")
    object: str = Field("chat.completion", description="Object type")
    created: int = Field(..., description="Unix timestamp of creation")
    model: str = Field(..., description="Model used")
    choices: List[Choice] = Field(..., description="List of completion choices")
    usage: Usage = Field(..., description="Token usage information")
    system_fingerprint: Optional[str] = Field(None, description="System fingerprint")


class ErrorResponse(BaseModel):
    """Error response format."""
    error: Dict[str, Union[str, int, None]] = Field(
        ...,
        description="Error details",
        examples=[{
            "message": "Invalid API key",
            "type": "invalid_request_error",
            "param": None,
            "code": "invalid_api_key"
        }]
    )


# Create FastAPI app (without lifespan for now)
app = FastAPI(
    title="Perplexity Proxy Server",
    description="OpenAI-compatible proxy server that forwards all requests to Perplexity API",
    version="1.0.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def estimate_tokens(text: str) -> int:
    """Estimate token count for a text string."""
    # Simple estimation: ~4 characters per token
    return len(text) // 4


def create_error_response(message: str, error_type: str = "invalid_request_error", 
                         param: Optional[str] = None, code: Optional[str] = None) -> ErrorResponse:
    """Create a standardized error response."""
    return ErrorResponse(
        error={
            "message": message,
            "type": error_type,
            "param": param,
            "code": code
        }
    )


# Perplexity proxy configuration
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")
PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"


async def proxy_to_perplexity(request_body: Dict[str, Any], headers: Dict[str, str]) -> JSONResponse:
    """Proxy request to Perplexity API."""
    if not PERPLEXITY_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="Perplexity API key not configured"
        )
    
    # Prepare headers for Perplexity
    perplexity_headers = {
        "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # Copy over any additional headers that might be useful
    for header, value in headers.items():
        if header.lower() in ["accept", "accept-encoding", "user-agent"]:
            perplexity_headers[header] = value
    
    async with httpx.AsyncClient() as client:
        try:
            # Forward the request to Perplexity
            response = await client.post(
                PERPLEXITY_API_URL,
                json=request_body,
                headers=perplexity_headers,
                timeout=60.0  # 60 second timeout
            )
            
            # Return the response from Perplexity
            return JSONResponse(
                content=response.json(),
                status_code=response.status_code,
                headers={
                    "Content-Type": "application/json",
                    "X-Proxied-From": "perplexity"
                }
            )
            
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=504,
                detail="Request to Perplexity API timed out"
            )
        except httpx.RequestError as e:
            logger.error(f"Error proxying to Perplexity: {e}")
            raise HTTPException(
                status_code=502,
                detail=f"Error communicating with Perplexity API: {str(e)}"
            )
        except Exception as e:
            logger.error(f"Unexpected error in Perplexity proxy: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Internal server error: {str(e)}"
            )




# ================ ORIGINAL HTTP SERVER CODE BELOW ================

@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Perplexity Proxy Server",
        "version": "1.0.0",
        "endpoints": {
            "chat_completions": "/v1/chat/completions (proxies to Perplexity)",
            "models": "/v1/models"
        }
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


@app.get("/v1/models")
async def list_models():
    """List available models (Perplexity models)."""
    models = [
        {
            "id": "llama-3.1-sonar-small-128k-online",
            "object": "model",
            "created": 1700000000,
            "owned_by": "perplexity",
            "permission": [],
            "root": "llama-3.1-sonar-small-128k-online",
            "parent": None,
        },
        {
            "id": "llama-3.1-sonar-large-128k-online",
            "object": "model",
            "created": 1700000000,
            "owned_by": "perplexity",
            "permission": [],
            "root": "llama-3.1-sonar-large-128k-online",
            "parent": None,
        },
        {
            "id": "llama-3.1-sonar-small-128k-chat",
            "object": "model",
            "created": 1700000000,
            "owned_by": "perplexity",
            "permission": [],
            "root": "llama-3.1-sonar-small-128k-chat",
            "parent": None,
        },
        {
            "id": "llama-3.1-sonar-large-128k-chat",
            "object": "model",
            "created": 1700000000,
            "owned_by": "perplexity",
            "permission": [],
            "root": "llama-3.1-sonar-large-128k-chat",
            "parent": None,
        }
    ]
    
    return {
        "object": "list",
        "data": models
    }


class ChatCompletionHandler:
    """Handler for chat completion requests."""
    
    def __init__(self, config: DoraConfig):
        """Initialize the handler."""
        self.config = config
        self._message_parser = MessageParser(config.openai_api_key)
        set_default_openai_key(config.openai_api_key)
    
    def _format_events_as_text(self, events: List[EventNotification]) -> str:
        """Format events as natural language text."""
        if not events:
            return "I couldn't find any events matching your request."
        
        lines = [f"I found {len(events)} upcoming events:\n"]
        
        for i, notification in enumerate(events, 1):
            event = notification.event
            lines.append(f"{i}. **{event.name}**")
            lines.append(f"   📍 {event.location}")
            lines.append(f"   📅 {event.start_date}")
            if event.description:
                # Truncate long descriptions
                desc = event.description[:150] + "..." if len(event.description) > 150 else event.description
                lines.append(f"   📝 {desc}")
            if event.url and event.url != "https://example.com":
                lines.append(f"   🔗 {event.url}")
            lines.append("")
        
        return "\n".join(lines)
    
    def _create_pydantic_model_from_schema(self, schema: Dict[str, Any], model_name: str = "ResponseModel") -> Type[BaseModel]:
        """Create a Pydantic model from JSON schema."""
        if schema.get("type") != "object" or "properties" not in schema:
            raise ValueError("Schema must be an object with properties")
        
        fields = {}
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        
        for field_name, field_schema in properties.items():
            field_type = Any  # Default type
            field_default = ... if field_name in required else None
            
            # Map JSON schema types to Python types
            if field_schema.get("type") == "string":
                field_type = str
            elif field_schema.get("type") == "number":
                field_type = float
            elif field_schema.get("type") == "integer":
                field_type = int
            elif field_schema.get("type") == "boolean":
                field_type = bool
            elif field_schema.get("type") == "array":
                items_schema = field_schema.get("items", {})
                if items_schema.get("type") == "object" and "properties" in items_schema:
                    # Create nested model for array items
                    item_model = self._create_pydantic_model_from_schema(
                        items_schema, 
                        model_name=f"{model_name}_{field_name}_Item"
                    )
                    field_type = List[item_model]
                elif items_schema.get("type") == "string":
                    field_type = List[str]
                elif items_schema.get("type") == "integer":
                    field_type = List[int]
                else:
                    field_type = List[Any]
            elif field_schema.get("type") == "object":
                if "properties" in field_schema:
                    # Create nested model
                    nested_model = self._create_pydantic_model_from_schema(
                        field_schema,
                        model_name=f"{model_name}_{field_name}"
                    )
                    field_type = nested_model
                else:
                    field_type = Dict[str, Any]
            
            description = field_schema.get("description", "")
            fields[field_name] = (field_type, PydanticField(default=field_default, description=description))
        
        return create_model(model_name, **fields)
    
    async def _format_with_agent(self, events: List[EventNotification], schema: Dict[str, Any]) -> str:
        """Format events using an agent with the provided schema."""
        # Create Pydantic model from schema
        output_model = self._create_pydantic_model_from_schema(schema)
        
        # Create formatting agent
        agent = Agent(
            name="EventFormatter",
            instructions="""You are a JSON formatter that converts event data into the requested format.
            Take the provided event notifications and format them according to the output schema.
            Ensure all required fields are populated and the output is valid JSON.""",
            model="gpt-4o-mini",
            model_settings=ModelSettings(temperature=0),
            output_type=output_model
        )
        
        # Prepare input data - convert all models to JSON-serializable format
        events_data = []
        for notification in events:
            # Use model_dump with mode='json' to ensure all nested objects are serializable
            notification_data = notification.model_dump(mode='json')
            events_data.append(notification_data)
        
        # Run the agent
        result = await Runner.run(agent, json_module.dumps({"events": events_data}))
        
        # Return the formatted JSON
        return json_module.dumps(result.final_output.model_dump())
    
    def _format_events_as_json(self, events: List[EventNotification]) -> str:
        """Format events as JSON with full notification data."""
        # Convert all Pydantic models to dictionaries first
        notifications_data = []
        
        for notification in events:
            # Use model_dump to convert the entire notification to a dictionary
            notif_dict = notification.model_dump(mode='json')
            notifications_data.append(notif_dict)
        
        import json
        return json.dumps({"notifications": notifications_data}, indent=2)
    
    async def process_request(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        """Process a chat completion request."""
        try:
            # Parse the messages to extract query parameters
            messages_dict = [{"role": msg.role, "content": msg.content} for msg in request.messages]
            parsed_query = await self._message_parser.parse(messages_dict)
            
            if not parsed_query or not parsed_query.city:
                logger.warning(f"Failed to parse city from messages: {messages_dict}")
                raise HTTPException(
                    status_code=400, 
                    detail="Could not determine which city to search for events. Please specify a city name."
                )
            
            logger.info(f"Parsed query: city={parsed_query.city}, events={parsed_query.events_count}, days={parsed_query.days_ahead}")
            
            # Map model to events count if needed
            events_count = parsed_query.events_count
            if request.model == "dora-events-fast":
                events_count = min(events_count, 5)  # Limit for fast model
            
            # Call Dora's process_city function
            results = await process_city(
                city=parsed_query.city,
                days_ahead=parsed_query.days_ahead,
                events_count=events_count,
                config=self.config
            )
            
            # Format the response based on response_format
            if request.response_format:
                logger.info(f"Response format type: {request.response_format.type}")
                if request.response_format.type == "json_schema":
                    schema = request.response_format.json_schema.get("schema", {})
                    if schema and "properties" in schema:
                        # Use agent-based formatting with a valid schema
                        response_content = await self._format_with_agent(results, schema)
                    else:
                        # Invalid or empty schema, return default JSON format
                        response_content = self._format_events_as_json(results)
                elif request.response_format.type == "json_object":
                    # Return default JSON format for json_object type
                    logger.info("Using JSON format for json_object type")
                    response_content = self._format_events_as_json(results)
                else:
                    response_content = self._format_events_as_text(results)
            else:
                response_content = self._format_events_as_text(results)
            
            # Generate completion ID
            completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
            
            # Calculate token usage
            prompt_tokens = sum(estimate_tokens(msg.content) for msg in request.messages)
            completion_tokens = estimate_tokens(response_content)
            
            return ChatCompletionResponse(
                id=completion_id,
                created=int(time.time()),
                model=request.model,
                choices=[
                    Choice(
                        index=0,
                        message=Message(role="assistant", content=response_content),
                        finish_reason="stop"
                    )
                ],
                usage=Usage(
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=prompt_tokens + completion_tokens
                )
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error processing request: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


# Global handler instance
completion_handler: Optional[ChatCompletionHandler] = None


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    """Application lifespan manager."""
    # Startup
    global completion_handler
    config = DoraConfig()
    completion_handler = ChatCompletionHandler(config)
    logger.info("Dora HTTP server started")
    yield
    # Shutdown
    logger.info("Dora HTTP server shutting down")


# Update app with lifespan
app.router.lifespan_context = lifespan


@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def create_chat_completion(
    request: ChatCompletionRequest,
    authorization: Optional[str] = Header(None)
) -> ChatCompletionResponse:
    """Create a chat completion - proxies all requests to Perplexity."""
    # Log the incoming request
    logger.info(f"Received chat completion request - Original Model: {request.model}")
    for i, msg in enumerate(request.messages):
        logger.info(f"Message {i+1} ({msg.role}): {msg.content}")
    
    # Convert request to dict for proxying
    request_dict = request.model_dump()
    
    # Force all requests to use sonar model
    request_dict["model"] = "sonar"
    logger.info(f"Substituted model to: sonar")
    
    # Proxy ALL requests to Perplexity
    headers = {"authorization": authorization} if authorization else {}
    response = await proxy_to_perplexity(request_dict, headers)
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    """Handle HTTP exceptions with OpenAI-compatible error format."""
    from fastapi.responses import JSONResponse
    
    error_response = ErrorResponse(
        error={
            "message": exc.detail,
            "type": "invalid_request_error",
            "param": None,
            "code": str(exc.status_code)
        }
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response.model_dump()
    )