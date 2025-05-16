#!/bin/bash

# Check if virtual environment exists, if not create it
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    uv venv
fi

# Activate virtual environment
source .venv/bin/activate 2>/dev/null || source .venv/Scripts/activate 2>/dev/null

# Check if dependencies are installed
if [ ! -d "dora.egg-info" ]; then
    echo "Installing dependencies..."
    uv pip install -e .
fi

# Check for .env file and create if it doesn't exist
if [ ! -f ".env" ]; then
    echo "Creating .env file..."
    echo "# Set your API keys here" > .env
    echo "OPENAI_API_KEY=" >> .env
    echo "PERPLEXITY_API_KEY=" >> .env
    echo ".env file created. Please edit it to add your API keys."
fi

# Run the application
python -m dora "$@"