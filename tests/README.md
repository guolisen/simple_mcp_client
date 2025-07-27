# Test Suite for Simple MCP Client

This directory contains the test suite for the Simple MCP Client. The tests are written using pytest and pytest-asyncio for testing asynchronous code.

## Running Tests

To run the tests, use the following command:

```bash
python -m pytest
```

For verbose output:

```bash
python -m pytest -v
```

To run a specific test file:

```bash
python -m pytest tests/test_config.py -v
```

## Test Coverage

The test suite covers the following modules:

- Configuration management (`test_config.py`)
- Connection handling (`test_connection.py`)
- Server management (`test_server.py`, `test_server_manager.py`)
- LangChain adapter (`test_langchain_adapter.py`)
- ReAct agent (`test_react_agent.py`)
- Chat utilities (`test_chat_utils.py`)
- Integration tests (`test_integration.py`)

## Known Issues and Fixes

The test suite currently has several issues that need to be addressed:

### 1. Read-only Properties

Many tests attempt to set read-only properties directly, such as `is_connected` on `MCPServer` objects. This results in errors like:

```
AttributeError: property 'is_connected' of 'MCPServer' object has no setter
```

**Fix**: Instead of directly setting the property, modify the underlying attribute or use a different approach to mock the behavior. For example:

```python
# Instead of:
mock_mcp_server.is_connected = True

# Use:
mock_mcp_server._connected = True  # Access the underlying attribute
# Or:
type(mock_mcp_server).is_connected = property(lambda self: True)  # Mock the property
```

### 2. AsyncMock and Coroutines

Some tests have issues with AsyncMock objects and coroutines not being properly awaited. This results in errors like:

```
RuntimeWarning: coroutine 'AsyncMockMixin._execute_mock_call' was never awaited
```

**Fix**: Ensure that all AsyncMock objects are properly awaited when called, and that the return values are set correctly.

```python
# Instead of:
mock_function = AsyncMock(return_value="result")

# Use:
mock_function = AsyncMock()
mock_function.return_value = "result"
```

### 3. MagicMock Objects in LangGraph Tools

There are issues with using MagicMock objects as tools in LangGraph, resulting in errors like:

```
ValueError: The first argument must be a string or a callable with a __name__ for tool decorator. Got <class 'unittest.mock.MagicMock'>
```

**Fix**: Create proper mock functions with names instead of using MagicMock objects directly:

```python
# Instead of:
mock_tools = [MagicMock(), MagicMock()]

# Use:
def mock_tool1(param1: str) -> str:
    """Mock tool 1."""
    return "Tool 1 result"

def mock_tool2(param2: int) -> str:
    """Mock tool 2."""
    return "Tool 2 result"

mock_tools = [mock_tool1, mock_tool2]
```

### 4. Missing Module Attributes

Some tests attempt to patch attributes that don't exist in the modules, such as:

```
AttributeError: <module 'simple_mcp_client.console.chat_utils'> does not have the attribute 'default_formatter'
```

**Fix**: Check the actual module structure and update the tests to patch the correct attributes.

### 5. Assertion Mismatches

There are mismatches between expected and actual values in assertions:

```
AssertionError: assert 'Agent response' == 'Response content'
```

**Fix**: Update the expected values in the assertions to match the actual values, or modify the mock objects to return the expected values.

## Adding New Tests

When adding new tests:

1. Create a new test file in the `tests/` directory with the prefix `test_`.
2. Import the necessary modules and fixtures.
3. Use pytest fixtures for common setup and teardown.
4. Use `@pytest.mark.asyncio` for asynchronous tests.
5. Follow the existing test patterns for consistency.
