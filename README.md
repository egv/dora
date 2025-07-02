# Multi-Agent Event Notification System

A distributed multi-agent system that builds comprehensive hyperlocal calendars combining events, weather, holidays, and cultural data to power intelligent marketing outreach. The system employs four specialized agents communicating via Pydantic AI's A2A protocol to deliver highly contextual, culturally-aware marketing opportunities with targeted notifications and visual content.

## 🏗️ Architecture

The system consists of four main agents working together through A2A protocol:

```
┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│                     │     │                     │     │                     │
│   Local Calendar    │────▶│ Message Generation  │────▶│ Audience Analysis   │
│ Intelligence Agent  │ A2A │      Agent          │ A2A │      Agent          │
│                     │◀────│                     │◀────│                     │
└─────────────────────┘     └─────────────────────┘     └─────────────────────┘
         │                           │                           │
         │                           ▼                           │
         │                  ┌─────────────────────┐             │
         │                  │                     │             │
         │                  │ Image Generation    │◀────────────┘
         │                  │      Agent          │         A2A
         │                  │                     │
         │                  └─────────────────────┘
         │                           │
         ▼                           ▼
    ┌─────────┐               ┌─────────┐
    │Calendar │               │Image Gen│
    │   MCP   │               │   MCP   │
    └─────────┘               └─────────┘
```

### Agent Details

1. **Local Calendar Intelligence Agent**: Multi-source data collection, verification, and calendar building
2. **Message Generation Agent**: Context-aware message creation with iterative refinement
3. **Audience Analysis Agent**: Behavior prediction and marketing optimization
4. **Image Generation Agent**: Visual content creation with verification

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- PostgreSQL 15+
- Redis 7+

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/dora.git
cd dora

# Set up Python environment using uv
uv sync

# Activate virtual environment
source .venv/bin/activate

# Copy environment template
cp .env.example .env
```

### Configuration

Edit `.env` file with your API keys:

```env
# Required API Keys
ANTHROPIC_API_KEY="sk-ant-api03-..."
OPENAI_API_KEY="sk-proj-..."
PERPLEXITY_API_KEY="pplx-..."

# Database Configuration
DATABASE_URL="postgresql://user:password@localhost:5432/dora_db"
REDIS_URL="redis://localhost:6379/0"

# Application Configuration
ENVIRONMENT="development"
LOG_LEVEL="INFO"
API_HOST="0.0.0.0"
API_PORT="8000"
```

### Database Setup

```bash
# Start PostgreSQL and Redis (using Docker)
docker run -d --name postgres -e POSTGRES_PASSWORD=password -p 5432:5432 postgres:15
docker run -d --name redis -p 6379:6379 redis:7

# Run database migrations (once implemented)
uv run python -m dora.database migrate
```

### Running the System

```bash
# Start the API server
uv run python -m api.main

# Or using uvicorn directly
uv run uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

## 🧪 Development

### Project Structure

```
dora/
├── agents/                 # Agent implementations
│   ├── calendar/          # Local Calendar Intelligence Agent
│   ├── message/           # Message Generation Agent
│   ├── audience/          # Audience Analysis Agent
│   └── image/             # Image Generation Agent
├── mcp_tools/             # MCP tool implementations
│   ├── calendar_cache/    # Redis-based calendar cache
│   └── image_gen/         # Image generation interface
├── models/                # Pydantic data models
├── api/                   # FastAPI application
├── tests/                 # Test suite
└── docs/                  # Documentation
```

### Development Commands

```bash
# Install development dependencies
uv sync --all-extras

# Run linting and formatting
uv run ruff check .
uv run ruff format .
uv run black .

# Type checking
uv run mypy .

# Run tests
uv run pytest tests/ -v

# Run tests with coverage
uv run pytest tests/ --cov=. --cov-report=html

# Install pre-commit hooks
uv run pre-commit install

# Run pre-commit manually
uv run pre-commit run --all-files
```

### Testing

```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_agents.py

# Run with coverage
uv run pytest --cov=dora --cov-report=html

# Run integration tests (requires database)
uv run pytest tests/integration/ -v
```

## 🐳 Docker Deployment

### Development

```bash
# Build development image
docker build -t dora:dev .

# Run with docker-compose
docker-compose -f docker-compose.dev.yml up
```

### Production

```bash
# Build production image
docker build -t dora:latest .

# Run with production compose
docker-compose up -d
```

## 📊 Monitoring

The system includes comprehensive monitoring and observability:

- **Metrics**: Prometheus metrics for all agents
- **Tracing**: Distributed tracing for A2A communication
- **Logging**: Structured logging with correlation IDs
- **Health Checks**: Built-in health endpoints

Access monitoring at:
- API Documentation: http://localhost:8000/docs
- Health Check: http://localhost:8000/health
- Metrics: http://localhost:8000/metrics

## 🔧 TaskMaster Integration

This project uses TaskMaster for project management:

```bash
# View current tasks
task-master list

# Get next task to work on
task-master next

# Mark task as complete
task-master set-status --id=1 --status=done

# Expand task into subtasks
task-master expand --id=2 --research
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Make your changes following the coding standards
4. Run tests: `uv run pytest`
5. Commit your changes: `git commit -m 'Add amazing feature'`
6. Push to the branch: `git push origin feature/amazing-feature`
7. Open a Pull Request

### Code Standards

- Use `uv` for all dependency management
- Follow Black code formatting (100 character line length)
- Use type hints with Pydantic models
- Write tests for all new functionality
- Document all public APIs

## 📝 API Documentation

Once running, interactive API documentation is available at:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 🔒 Security

- All agent communication is encrypted via A2A protocol
- API authentication using JWT tokens
- Environment variable management for secrets
- Regular security audits with bandit

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details

## 🎯 Roadmap

See the TaskMaster project for detailed development roadmap:
- [x] Project Infrastructure Setup
- [ ] A2A Protocol Framework Implementation
- [ ] Local Calendar Intelligence Agent
- [ ] Message Generation Agent
- [ ] Audience Analysis Agent
- [ ] Image Generation Agent
- [ ] API Gateway and Monitoring

## 🆘 Support

For issues and support:
1. Check the [TaskMaster tasks](/.taskmaster/tasks/) for known issues
2. Create an issue on GitHub
3. Review the API documentation at `/docs`

---

Built with ❤️ using Python, FastAPI, Pydantic AI, and uv.