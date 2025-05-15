# Dora the Explora

An autonomous AI agent system that discovers events in cities and generates targeted push notifications for users.

## Features

- City-based event discovery for the upcoming two weeks
- Event classification by size, importance, and target audiences
- Multi-language push notification generation
- Modular agent-based architecture
- Structured communication between agents

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/dora.git
cd dora

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
PERPLEXITY_API_KEY=your_perplexity_api_key
```

## Usage

```bash
python -m dora --city "New York"
```

## Development

```bash
# Install development dependencies
uv pip install -e ".[dev]"

# Run tests
pytest
```

## License

MIT