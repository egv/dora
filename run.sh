#!/bin/bash

# Check if virtual environment exists, if not create it
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    uv venv
fi

# Activate virtual environment
source .venv/bin/activate

# Install dependencies if needed
if [ ! -d "dora.egg-info" ]; then
    echo "Installing dependencies..."
    uv pip install -e .
fi

# Run the application
python -m dora "$@"