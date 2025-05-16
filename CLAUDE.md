
## General info

- this IS NOT Solana project
- ALWAYS use `uv` to do ALL python related tasks. uv is already installed in the system
- all dependencies MUST be managed through pyproject.toml
- you should use local venv
- all api keys etc. should be stored in .env file
- use openai agents framework for creating AI agents
- types for python are done using Pydantic

## Examples

- running python

`source .venv/bin/activate && uv run python`

- add dependency

`source .venv/bin/activate && uv add <dependency name>`

- install dependencies

`source .venv/bin/activate && uv sync`




## Docs section

- MCP docs: https://github.com/modelcontextprotocol/python-sdk
- MCP examples: https://github.com/modelcontextprotocol/python-sdk/tree/main/examples
- A2A docs: https://google.github.io/A2A/
- A2A examples: https://github.com/google/A2A/blob/main/samples/python
- OpenAI-agents docs: https://github.com/openai/openai-agents-python
- Openai-agents examples: https://github.com/openai/openai-agents-python/tree/main/examples

## Basic rules

- please always refer to docs and examples before writing code
- you should thoroughly explain what and why you are doing
- you should write tests first, and then make them pass
- always prefer modular approach to architectural tasks
- use docker for distribution
- always use typing everywhere it is possible to do so
