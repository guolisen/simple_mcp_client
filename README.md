# Simple MCP Client

A simple command-line MCP (Model Context Protocol) client for testing MCP servers using Python. It supports chatting with various LLM providers and connecting to multiple MCP servers.

## Features

- Connect to multiple MCP servers (SSE and stdio protocols)
- Integrate with different LLM providers (Ollama, DeepSeek, OpenAI, OpenRouter)
- Interactive command-line interface with auto-completion
- Command-based tool execution
- Chat mode with LLM-driven tool execution
- Configurable via JSON configuration files

## Installation

There are several ways to install the client:

### Using UV (recommended)

```bash
uv venv
source .venv/bin/activate
uv pip install -e .
```

### Using pip with requirements.txt

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

### Using pip directly

```bash
pip install -e .
```

### Using pip with pyproject.toml

```bash
pip install .
```

## Configuration

The client uses a configuration file to define LLM providers and MCP servers. By default, it looks for `config.json` in the current directory, or it creates one with default values.

Example configuration:

```json
{
  "llm": {
    "provider": "ollama",
    "model": "llama3",
    "api_url": "http://localhost:11434/api",
    "api_key": null,
    "other_params": {
      "temperature": 0.7,
      "max_tokens": 4096
    }
  },
  "mcpServers": {
    "k8s": {
      "type": "sse",
      "url": "http://192.168.182.128:8000/sse",
      "command": null,
      "args": [],
      "env": {}
    }
  },
  "default_server": "k8s"
}
```

## Usage

Start the client:

```bash
simple-mcp-client
```

Or run it directly:

```bash
python -m simple_mcp_client.main
```

## Available Commands

- `help`: Show help message
- `connect <server_name>`: Connect to an MCP server
- `disconnect <server_name>`: Disconnect from an MCP server
- `servers`: List available MCP servers
- `tools [server_name]`: List available tools, optionally from a specific server
- `resources [server_name]`: List available resources, optionally from a specific server
- `execute <server_name> <tool_name> [arg1=val1 ...]`: Execute a specific tool with arguments
- `chat`: Start a chat session with the configured LLM and active MCP tools
- `config show`: Show current configuration
- `config llm <provider> [model=<model>] [api_url=<url>] [api_key=<key>] [param=value ...]`: Configure LLM provider
- `reload`: Reload configuration from file
- `exit`: Exit the program

## Environment Variables

- `MCP_LOG_LEVEL`: Set logging level (default: INFO)
- `OPENAI_API_KEY`: OpenAI API key (for OpenAI provider)
- `DEEPSEEK_API_KEY`: DeepSeek API key (for DeepSeek provider)
- `OPENROUTER_API_KEY`: OpenRouter API key (for OpenRouter provider)

## LLM Providers

The client supports the following LLM providers:

- **Ollama**: Local LLM provider
- **OpenAI**: API-based LLM provider 
- **DeepSeek**: API-based LLM provider
- **OpenRouter**: API-based LLM provider that supports multiple LLM backends

## License

MIT
