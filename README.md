# Dora the Explora

An autonomous AI agent system that discovers events in cities and generates targeted push notifications for users.

## Features

- City-based event discovery for the upcoming two weeks
- Event classification by size, importance, and target audiences
- Multi-language push notification generation
- Modular agent-based architecture using OpenAI Agents framework
- Structured communication between agents

## Architecture

Dora consists of several specialized agents working together:

1. **Orchestration Agent**: Coordinates the overall process
2. **Event Finder Agent**: Discovers events in a given city using Perplexity API
3. **Event Classifier Agent**: Analyzes events by size, importance, and target audiences
4. **Language Selector Agent**: Determines languages spoken in the city
5. **Text Writer Agent**: Creates personalized push notifications in multiple languages

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/dora.git
cd dora

# Use the run script (automatically sets up venv and dependencies)
./run.sh --city "New York"
```

Or manually:

```bash
# Set up virtual environment
uv venv

# Activate virtual environment
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
uv pip install -e .
```

## Configuration

Create a `.env` file in the root directory with the following variables:

```
OPENAI_API_KEY=your_openai_api_key
PERPLEXITY_API_KEY=your_perplexity_api_key  # Optional but recommended
```

## Usage

```bash
# Using the convenience script
./run.sh --city "New York"

# Or directly
python -m dora --city "New York"

# Output as JSON
python -m dora --city "Tokyo" --output json

# Specify number of days to look ahead
python -m dora --city "Paris" --days 7
```

## Docker

```bash
# Build and run with Docker
docker build -t dora .
docker run -it --env-file .env dora --city "Berlin"

# Or using docker-compose
docker-compose run --rm dora --city "London" --output json
```

## Development

```bash
# Install development dependencies
uv pip install -e ".[dev]"

# Run tests
pytest

# Run a specific test
pytest tests/test_integration.py
```

## License

MIT