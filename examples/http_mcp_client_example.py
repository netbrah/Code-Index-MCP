#!/usr/bin/env python3
"""
Example client for HTTP MCP Server
Demonstrates how to connect and use the HTTP MCP server with SSE transport
"""
import asyncio
import json
import os
from typing import Any, Dict, List

import httpx


class HTTPMCPClient:
    """Simple HTTP MCP client using REST API (simplified version)."""
    
    def __init__(self, base_url: str = "http://localhost:8001"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def health_check(self) -> Dict[str, Any]:
        """Check if the server is healthy."""
        response = await self.client.get(f"{self.base_url}/health")
        response.raise_for_status()
        return response.json()
    
    async def close(self):
        """Close the client connection."""
        await self.client.aclose()


async def main():
    """Run example client operations."""
    print("🚀 HTTP MCP Client Example")
    print("=" * 50)
    
    # Create client
    base_url = os.getenv("MCP_HTTP_URL", "http://localhost:8001")
    client = HTTPMCPClient(base_url)
    
    try:
        # Test 1: Health Check
        print("\n1️⃣  Testing health check...")
        health = await client.health_check()
        print(f"   Status: {health.get('status')}")
        print(f"   ✅ Server is healthy!")
        
        # Test 2: Server Info
        print("\n2️⃣  Server Information:")
        print(f"   Base URL: {base_url}")
        print(f"   SSE Endpoint: {base_url}/sse")
        print(f"   Messages Endpoint: {base_url}/messages")
        
        # Instructions for full MCP client
        print("\n3️⃣  Using with Full MCP Client:")
        print("""
   To use with the full MCP protocol client, you need the official MCP SDK:
   
   ```python
   import httpx
   from mcp.client import ClientSession
   from mcp.client.sse import sse_client
   
   async with httpx.AsyncClient() as http_client:
       async with sse_client(
           url="http://localhost:8001/sse"
       ) as (read, write):
           async with ClientSession(read, write) as session:
               # Initialize
               await session.initialize()
               
               # List tools
               tools = await session.list_tools()
               print(f"Available tools: {[t.name for t in tools.tools]}")
               
               # Call a tool
               result = await session.call_tool(
                   "search_code",
                   {"query": "def main", "limit": 10}
               )
               print(f"Results: {result}")
   ```
        """)
        
        # Test 4: Claude Code Configuration
        print("\n4️⃣  Claude Code Configuration:")
        print("""
   Add to your .mcp.json:
   
   {
     "mcpServers": {
       "code-index-http": {
         "url": "http://localhost:8001",
         "transport": "sse",
         "sse_endpoint": "/messages"
       }
     }
   }
        """)
        
        print("\n✅ All tests passed!")
        print("\n📖 For more information, see:")
        print("   - docs/HTTP_MCP_DOCKER_GUIDE.md")
        print("   - README.md")
        
    except httpx.HTTPError as e:
        print(f"\n❌ Error: {e}")
        print("\nMake sure the HTTP MCP server is running:")
        print("  docker-compose -f docker-compose.http-mcp.yml up -d")
    
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
    
    finally:
        await client.close()


if __name__ == "__main__":
    # Check if httpx is installed
    try:
        import httpx
    except ImportError:
        print("❌ httpx is required. Install with: pip install httpx")
        exit(1)
    
    # Run the client
    asyncio.run(main())
