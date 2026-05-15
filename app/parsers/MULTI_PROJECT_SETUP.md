# Smart MCP Dynamic Multi-Project Setup

## Example Claude Desktop Config

```json
{
  "mcpServers": {
    "smart-mcp": {
      "command": "C:/Users/burha/AppData/Local/Programs/Python/Python311/python.exe",
      "args": [
        "C:/Work/smart-mcp/app/mcp/server.py",
        "C:/Work/NatFirstAPI",
        "C:/Work/cosmetics_api"
      ]
    }
  }
}
```

## Features Added

- Multiple repository support
- Dynamic repo detection
- REPO_PATH environment variable support
- Better logging
- Independent indexing per repository
- Failure isolation per repository
