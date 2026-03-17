"""
MCP Server Configuration.

Reads from environment variables with sensible defaults.
"""

import os


# Memory API server URL
BASE_URL = os.environ.get("MEMORY_BASE_URL", "http://localhost:19876")

# Default project path
PROJECT_PATH = os.environ.get("MEMORY_PROJECT_PATH", os.getcwd())

# Default agent identity
DEFAULT_AGENT = os.environ.get("MEMORY_AGENT_NAME", "mcp-agent")
DEFAULT_MODEL = os.environ.get("MEMORY_MODEL_NAME", "unknown")
DEFAULT_PROVIDER = os.environ.get("MEMORY_PROVIDER", "mcp")
CLI_NAME = os.environ.get("MEMORY_CLI_NAME", "mcp-memory-server")
