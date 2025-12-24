# HTTP MCP Docker Guide

## Overview

The HTTP MCP Docker setup provides MCP (Model Context Protocol) over HTTP using Server-Sent Events (SSE), allowing Claude Code and other MCP clients to connect via HTTP instead of STDIO.

This is particularly useful for:
- Remote MCP server access
- Cloud deployments
- Multi-user scenarios
- Container orchestration (Kubernetes, Docker Swarm)
- Situations where STDIO is not suitable

## Architecture

```
┌─────────────────┐      HTTP/SSE      ┌──────────────────┐
│  Claude Code /  │◄──────────────────►│  HTTP MCP Server │
│   MCP Client    │                    │   (Port 8001)    │
└─────────────────┘                    └──────────────────┘
                                                 │
                                                 ▼
                                       ┌──────────────────┐
                                       │   Dispatcher     │
                                       │   & Plugins      │
                                       └──────────────────┘
                                                 │
                                                 ▼
                                       ┌──────────────────┐
                                       │  SQLite Index    │
                                       └──────────────────┘
```

## Quick Start

### 1. Basic Setup (No API Keys Required)

```bash
# Start the HTTP MCP server
docker-compose -f docker-compose.http-mcp.yml up -d

# Check the server is running
curl http://localhost:8001/health

# Expected response:
# {"status":"ok"}
```

### 2. With Semantic Search (Requires Voyage AI API Key)

```bash
# Set your API key
export VOYAGE_AI_API_KEY=your-api-key-here
export SEMANTIC_SEARCH_ENABLED=true

# Start with semantic search support
docker-compose -f docker-compose.http-mcp.yml up -d

# Verify semantic search is enabled
curl http://localhost:8001/health
```

### 3. With All Optional Services

```bash
# Start with Redis cache and Qdrant vector database
docker-compose -f docker-compose.http-mcp.yml \
  --profile with-cache \
  --profile with-semantic \
  up -d
```

## Configuration

### Environment Variables

Create a `.env` file or export these variables:

```bash
# Required
MCP_WORKSPACE=/path/to/your/code  # Code directory to index

# Optional - Server Configuration
MCP_HTTP_PORT=8001                # HTTP server port (default: 8001)
LOG_LEVEL=INFO                    # Logging level (DEBUG, INFO, WARNING, ERROR)
MCP_USE_SIMPLE_DISPATCHER=false   # Use simple dispatcher (BM25 only)
MCP_ENABLE_MULTI_PATH=true        # Enable multi-path index discovery

# Optional - Semantic Search
VOYAGE_AI_API_KEY=your-key        # Voyage AI API key for semantic search
SEMANTIC_SEARCH_ENABLED=false     # Enable semantic search
SEMANTIC_EMBEDDING_MODEL=voyage-code-3  # Embedding model to use

# Optional - Security
CORS_ORIGINS=*                    # CORS allowed origins (comma-separated)
JWT_SECRET_KEY=your-secret        # JWT secret for authentication
ACCESS_TOKEN_EXPIRE_MINUTES=30    # Token expiration time
```

### Docker Compose Profiles

The HTTP MCP setup includes optional profiles for additional services:

- **Default**: HTTP MCP server only
- **with-cache**: Adds Redis caching layer
- **with-semantic**: Adds Qdrant vector database
- **with-proxy**: Adds Nginx reverse proxy

```bash
# Example: Start with all optional services
docker-compose -f docker-compose.http-mcp.yml \
  --profile with-cache \
  --profile with-semantic \
  --profile with-proxy \
  up -d
```

## Client Configuration

### Claude Code (.mcp.json)

```json
{
  "mcpServers": {
    "code-index-http": {
      "url": "http://localhost:8001",
      "transport": "sse",
      "sse_endpoint": "/messages"
    }
  }
}
```

### Custom MCP Client

```python
import httpx
from mcp.client import ClientSession
from mcp.client.sse import sse_client

async def connect_to_http_mcp():
    async with httpx.AsyncClient() as client:
        async with sse_client(
            url="http://localhost:8001/sse"
        ) as (read, write):
            async with ClientSession(read, write) as session:
                # Initialize the session
                await session.initialize()
                
                # List available tools
                tools = await session.list_tools()
                print(f"Available tools: {tools}")
                
                # Call a tool
                result = await session.call_tool(
                    "search_code",
                    {"query": "def main", "limit": 10}
                )
                print(f"Search results: {result}")

# Run the client
import asyncio
asyncio.run(connect_to_http_mcp())
```

## Available MCP Tools

The HTTP MCP server provides the following tools:

### 1. symbol_lookup

Look up a symbol definition in the codebase.

```json
{
  "name": "symbol_lookup",
  "arguments": {
    "symbol": "MyClass",
    "file_path": "/path/to/file.py"  // optional
  }
}
```

### 2. search_code

Search for code patterns across the codebase.

```json
{
  "name": "search_code",
  "arguments": {
    "query": "async def.*handle",
    "limit": 10,
    "semantic": false,
    "file_extensions": [".py", ".js"]  // optional
  }
}
```

### 3. get_status

Get the status of the code index server.

```json
{
  "name": "get_status",
  "arguments": {}
}
```

### 4. list_plugins

List all available language plugins.

```json
{
  "name": "list_plugins",
  "arguments": {}
}
```

## Testing

### Run Integration Tests

```bash
# Install test dependencies
pip install pytest httpx

# Run the integration tests
pytest tests/integration/test_http_mcp_docker.py -v

# Run with Docker Compose logs visible
pytest tests/integration/test_http_mcp_docker.py -v -s
```

### Manual Testing

```bash
# 1. Start the server
docker-compose -f docker-compose.http-mcp.yml up -d

# 2. Check health
curl http://localhost:8001/health

# 3. Check Docker logs
docker logs code-index-http-mcp

# 4. Test SSE endpoint (requires SSE client)
curl -N -H "Accept: text/event-stream" http://localhost:8001/messages

# 5. Stop the server
docker-compose -f docker-compose.http-mcp.yml down
```

## Troubleshooting

### Server Won't Start

```bash
# Check Docker logs
docker logs code-index-http-mcp

# Common issues:
# - Missing index: Create index with `mcp-index rebuild`
# - Port conflict: Change MCP_HTTP_PORT in .env
# - Permission issues: Check file permissions on mounted volumes
```

### Health Check Fails

```bash
# Check if the container is running
docker ps | grep code-index-http-mcp

# Check network connectivity
docker network ls
docker network inspect code-index-mcp_mcp-network

# Restart the container
docker-compose -f docker-compose.http-mcp.yml restart
```

### Connection Refused from Client

```bash
# Verify server is listening
netstat -tuln | grep 8001

# Check firewall rules
sudo ufw status

# Test with curl
curl -v http://localhost:8001/health
```

### Semantic Search Not Working

```bash
# Verify API key is set
docker exec code-index-http-mcp env | grep VOYAGE

# Check Qdrant is running (if using with-semantic profile)
docker ps | grep qdrant
curl http://localhost:6333/health

# Check server logs for semantic search initialization
docker logs code-index-http-mcp | grep -i semantic
```

## Production Deployment

### Using Nginx Reverse Proxy

```nginx
# /etc/nginx/sites-available/mcp-server
server {
    listen 80;
    server_name mcp.example.com;

    location / {
        proxy_pass http://localhost:8001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # SSE-specific settings
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 86400s;
    }
}
```

### Using with Kubernetes

See `k8s/http-mcp-deployment.yaml` for a complete Kubernetes deployment example.

### Security Considerations

1. **Enable JWT authentication**:
   ```bash
   export JWT_SECRET_KEY=$(openssl rand -base64 32)
   ```

2. **Restrict CORS origins**:
   ```bash
   export CORS_ORIGINS=https://app.example.com,https://admin.example.com
   ```

3. **Use HTTPS in production**:
   - Deploy behind a reverse proxy with SSL termination
   - Use Let's Encrypt for free SSL certificates

4. **Limit resource usage**:
   ```yaml
   # In docker-compose.http-mcp.yml
   services:
     http-mcp-server:
       deploy:
         resources:
           limits:
             cpus: '2.0'
             memory: 4G
           reservations:
             cpus: '0.5'
             memory: 1G
   ```

## Performance Tuning

### For Large Codebases

```bash
# Use simple dispatcher for better performance
export MCP_USE_SIMPLE_DISPATCHER=true

# Increase worker processes
# Edit docker-compose.http-mcp.yml:
command: ["uvicorn", "mcp_server.http_mcp_server:http_mcp_app", "--host", "0.0.0.0", "--port", "8001", "--workers", "4"]
```

### Enable Caching

```bash
# Start with Redis cache
docker-compose -f docker-compose.http-mcp.yml --profile with-cache up -d

# Configure cache settings in .env
export CACHE_DEFAULT_TTL=3600
export CACHE_MAX_ENTRIES=10000
```

## Monitoring

### Health Checks

```bash
# Basic health check
curl http://localhost:8001/health

# Detailed status (requires authentication in production)
curl http://localhost:8001/status
```

### Prometheus Metrics

If you deployed with the monitoring profile:

```bash
# Access Prometheus
open http://localhost:9090

# Access Grafana (default password: admin)
open http://localhost:3000
```

## Migration from STDIO MCP

If you're currently using the STDIO-based MCP server, here's how to migrate:

1. **Keep your existing setup** - Both can coexist
2. **Update .mcp.json** to use HTTP transport:
   ```json
   {
     "mcpServers": {
       "code-index-stdio": {
         "command": "python",
         "args": ["scripts/cli/mcp_server_cli.py"]
       },
       "code-index-http": {
         "url": "http://localhost:8001",
         "transport": "sse"
       }
     }
   }
   ```
3. **Test both configurations** to ensure compatibility
4. **Switch to HTTP** when ready by using the `code-index-http` server

## Support

- **Issues**: [GitHub Issues](https://github.com/netbrah/Code-Index-MCP/issues)
- **Discussions**: [GitHub Discussions](https://github.com/netbrah/Code-Index-MCP/discussions)
- **Documentation**: [Project README](../README.md)
