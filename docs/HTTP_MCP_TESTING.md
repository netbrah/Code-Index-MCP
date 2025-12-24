# HTTP MCP Docker Testing Guide

This guide covers testing the HTTP MCP Docker implementation.

## Quick Test

```bash
# 1. Start the server
docker-compose -f docker-compose.http-mcp.yml up -d

# 2. Wait for it to be ready
sleep 10

# 3. Test health endpoint
curl http://localhost:8001/health

# 4. Run example client
python3 examples/http_mcp_client_example.py

# 5. Run full MCP client test (requires mcp package)
pip install mcp httpx
python3 examples/full_mcp_client_test.py

# 6. Stop the server
docker-compose -f docker-compose.http-mcp.yml down
```

## Automated Integration Tests

```bash
# Run all integration tests
pytest tests/integration/test_http_mcp_docker.py -v

# Run specific test
pytest tests/integration/test_http_mcp_docker.py::TestHTTPMCPDocker::test_health_check -v

# Run with Docker Compose (requires Docker daemon)
pytest tests/integration/test_http_mcp_docker.py::TestHTTPMCPDocker -v -s
```

## Manual Testing Scenarios

### Scenario 1: Basic HTTP MCP Server

**Setup:**
```bash
docker-compose -f docker-compose.http-mcp.yml up -d
```

**Tests:**
1. Health check: `curl http://localhost:8001/health`
2. SSE endpoint: `curl -N http://localhost:8001/messages`
3. Container status: `docker ps | grep code-index-http-mcp`
4. Container logs: `docker logs code-index-http-mcp`

**Expected Results:**
- Health endpoint returns `{"status":"ok"}`
- Container is running
- No critical errors in logs

### Scenario 2: With Semantic Search

**Setup:**
```bash
export VOYAGE_AI_API_KEY=your-key
export SEMANTIC_SEARCH_ENABLED=true
docker-compose -f docker-compose.http-mcp.yml --profile with-semantic up -d
```

**Tests:**
1. Verify Qdrant is running: `docker ps | grep qdrant`
2. Check Qdrant health: `curl http://localhost:6333/health`
3. Check server recognizes semantic search: `docker logs code-index-http-mcp | grep -i semantic`

**Expected Results:**
- Qdrant container is running
- Server logs show "semantic search enabled"

### Scenario 3: With Caching

**Setup:**
```bash
docker-compose -f docker-compose.http-mcp.yml --profile with-cache up -d
```

**Tests:**
1. Verify Redis is running: `docker ps | grep redis`
2. Check Redis connection: `docker exec code-index-redis redis-cli ping`
3. Monitor cache usage: `docker exec code-index-redis redis-cli INFO stats`

**Expected Results:**
- Redis container is running
- Redis responds to PING with PONG

### Scenario 4: Full Stack (All Services)

**Setup:**
```bash
export VOYAGE_AI_API_KEY=your-key
docker-compose -f docker-compose.http-mcp.yml \
  --profile with-cache \
  --profile with-semantic \
  up -d
```

**Tests:**
1. Verify all containers: `docker-compose -f docker-compose.http-mcp.yml ps`
2. Check inter-service connectivity
3. Run full MCP client test: `python3 examples/full_mcp_client_test.py`

**Expected Results:**
- All 3 containers running (mcp-server, redis, qdrant)
- All health checks passing
- MCP client can connect and invoke tools

## Performance Testing

### Load Testing with Apache Bench

```bash
# Test health endpoint
ab -n 1000 -c 10 http://localhost:8001/health

# Expected results:
# - No failed requests
# - Response time < 100ms (p95)
```

### SSE Connection Stress Test

```bash
# Test multiple concurrent SSE connections
for i in {1..10}; do
  curl -N http://localhost:8001/messages &
done
sleep 5
killall curl

# Check server logs for any errors
docker logs code-index-http-mcp | tail -20
```

## Debugging Failed Tests

### Server Won't Start

```bash
# Check Docker logs
docker logs code-index-http-mcp

# Common issues:
# 1. Missing index database
#    Solution: Create index or disable index requirement
# 2. Port already in use
#    Solution: Change MCP_HTTP_PORT or kill conflicting process
# 3. Permission issues
#    Solution: Check volume mount permissions
```

### Health Check Fails

```bash
# Check if container is running
docker ps -a | grep code-index-http-mcp

# Check container status
docker inspect code-index-http-mcp

# Try to access from inside container
docker exec code-index-http-mcp curl http://localhost:8001/health
```

### SSE Connection Issues

```bash
# Test SSE endpoint with verbose output
curl -v -N -H "Accept: text/event-stream" http://localhost:8001/messages

# Check server logs for SSE-related errors
docker logs code-index-http-mcp | grep -i sse

# Verify CORS headers
curl -v -H "Origin: http://localhost:3000" http://localhost:8001/health
```

### MCP Client Connection Fails

```bash
# Verify server is accessible
curl http://localhost:8001/health

# Check network connectivity
docker network inspect code-index-mcp_mcp-network

# Test with telnet
telnet localhost 8001
```

## Test Coverage

The integration tests cover:

✅ File existence (Dockerfile, docker-compose.yml)
✅ Docker container startup
✅ Health check endpoint
✅ CORS configuration
✅ Container logging (no critical errors)
✅ Basic endpoint accessibility

Not yet covered (requires manual testing):
- [ ] SSE connection establishment
- [ ] MCP protocol handshake
- [ ] Tool invocation through SSE
- [ ] Multi-client scenarios
- [ ] Long-running connections
- [ ] Error recovery

## Continuous Integration

For CI/CD pipelines, use this test sequence:

```bash
#!/bin/bash
set -e

# 1. Start services
docker-compose -f docker-compose.http-mcp.yml up -d

# 2. Wait for health
timeout 60 bash -c 'until curl -sf http://localhost:8001/health; do sleep 2; done'

# 3. Run tests
pytest tests/integration/test_http_mcp_docker.py -v

# 4. Cleanup
docker-compose -f docker-compose.http-mcp.yml down -v
```

## Security Testing

### Test CORS Configuration

```bash
# Test allowed origin
curl -v -H "Origin: http://localhost:3000" \
  -H "Access-Control-Request-Method: GET" \
  -X OPTIONS http://localhost:8001/health

# Test disallowed origin (if CORS is restricted)
curl -v -H "Origin: http://malicious-site.com" \
  http://localhost:8001/health
```

### Test Authentication (if enabled)

```bash
# Test without auth (should fail if auth is enabled)
curl http://localhost:8001/health

# Test with auth token
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8001/health
```

## Reporting Issues

When reporting issues, include:

1. **Environment:**
   - OS and version
   - Docker version: `docker --version`
   - Docker Compose version: `docker-compose --version`

2. **Configuration:**
   - Contents of `.env.http-mcp` (redact sensitive values)
   - Compose profiles used

3. **Logs:**
   ```bash
   docker logs code-index-http-mcp > server.log
   docker-compose -f docker-compose.http-mcp.yml logs > compose.log
   ```

4. **Steps to reproduce**

5. **Expected vs actual behavior**
