#!/bin/bash
# Quick start script for HTTP MCP Docker server

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 Code Index HTTP MCP Docker Quick Start${NC}"
echo ""

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker is not installed${NC}"
    echo "Please install Docker from: https://docs.docker.com/get-docker/"
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}❌ Docker Compose is not installed${NC}"
    echo "Please install Docker Compose from: https://docs.docker.com/compose/install/"
    exit 1
fi

echo -e "${GREEN}✅ Docker and Docker Compose are installed${NC}"
echo ""

# Check if docker-compose.http-mcp.yml exists
if [ ! -f "docker-compose.http-mcp.yml" ]; then
    echo -e "${RED}❌ docker-compose.http-mcp.yml not found${NC}"
    echo "Please run this script from the Code-Index-MCP root directory"
    exit 1
fi

# Ask user for configuration
echo -e "${YELLOW}Configuration:${NC}"
echo ""

# Ask about semantic search
read -p "Enable semantic search? (requires Voyage AI API key) [y/N]: " enable_semantic
if [[ "$enable_semantic" =~ ^[Yy]$ ]]; then
    read -p "Enter your Voyage AI API key: " voyage_key
    if [ -z "$voyage_key" ]; then
        echo -e "${RED}❌ API key is required for semantic search${NC}"
        exit 1
    fi
    export VOYAGE_AI_API_KEY="$voyage_key"
    export SEMANTIC_SEARCH_ENABLED=true
    PROFILES="--profile with-semantic"
    echo -e "${GREEN}✅ Semantic search enabled${NC}"
else
    export SEMANTIC_SEARCH_ENABLED=false
    PROFILES=""
    echo -e "${YELLOW}ℹ️  Semantic search disabled (using BM25 only)${NC}"
fi

echo ""

# Ask about optional services
read -p "Enable Redis caching? [Y/n]: " enable_cache
if [[ ! "$enable_cache" =~ ^[Nn]$ ]]; then
    PROFILES="$PROFILES --profile with-cache"
    echo -e "${GREEN}✅ Redis caching enabled${NC}"
fi

echo ""

# Set workspace
export MCP_WORKSPACE=${MCP_WORKSPACE:-$(pwd)}
echo -e "${YELLOW}Workspace: $MCP_WORKSPACE${NC}"
echo ""

# Create .env file
cat > .env.http-mcp << EOF
# HTTP MCP Server Configuration
MCP_WORKSPACE=$MCP_WORKSPACE
MCP_HTTP_PORT=8001
LOG_LEVEL=INFO
SEMANTIC_SEARCH_ENABLED=$SEMANTIC_SEARCH_ENABLED
EOF

if [ ! -z "$VOYAGE_AI_API_KEY" ]; then
    echo "VOYAGE_AI_API_KEY=$VOYAGE_AI_API_KEY" >> .env.http-mcp
fi

echo -e "${GREEN}✅ Configuration saved to .env.http-mcp${NC}"
echo ""

# Build and start the server
echo -e "${YELLOW}🏗️  Building and starting HTTP MCP server...${NC}"
docker-compose -f docker-compose.http-mcp.yml --env-file .env.http-mcp $PROFILES up -d --build

# Wait for server to be ready
echo ""
echo -e "${YELLOW}⏳ Waiting for server to be ready...${NC}"
MAX_RETRIES=30
RETRY_COUNT=0
until curl -sf http://localhost:8001/health > /dev/null 2>&1; do
    RETRY_COUNT=$((RETRY_COUNT + 1))
    if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
        echo -e "${RED}❌ Server failed to start${NC}"
        echo ""
        echo "View logs with:"
        echo "  docker logs code-index-http-mcp"
        exit 1
    fi
    echo -n "."
    sleep 2
done

echo ""
echo ""
echo -e "${GREEN}✅ HTTP MCP server is running!${NC}"
echo ""
echo -e "${YELLOW}📋 Server Information:${NC}"
echo "  - URL: http://localhost:8001"
echo "  - Health Check: http://localhost:8001/health"
echo "  - SSE Endpoint: http://localhost:8001/sse"
echo ""
echo -e "${YELLOW}🔧 Useful Commands:${NC}"
echo "  - View logs:    docker logs -f code-index-http-mcp"
echo "  - Stop server:  docker-compose -f docker-compose.http-mcp.yml down"
echo "  - Restart:      docker-compose -f docker-compose.http-mcp.yml restart"
echo ""
echo -e "${YELLOW}📖 Documentation:${NC}"
echo "  - Full Guide: docs/HTTP_MCP_DOCKER_GUIDE.md"
echo "  - README: README.md"
echo ""

# Test the server
echo -e "${YELLOW}🧪 Testing server...${NC}"
HEALTH_CHECK=$(curl -s http://localhost:8001/health)
echo "Health check response: $HEALTH_CHECK"
echo ""

if echo "$HEALTH_CHECK" | grep -q '"status":"ok"'; then
    echo -e "${GREEN}✅ Server is healthy and ready to use!${NC}"
else
    echo -e "${YELLOW}⚠️  Server is running but may not be fully initialized${NC}"
    echo "Check logs for details: docker logs code-index-http-mcp"
fi

echo ""
echo -e "${GREEN}🎉 Setup complete!${NC}"
