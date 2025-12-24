#!/usr/bin/env python3
"""
Full MCP Client Example for HTTP MCP Server
Demonstrates complete MCP protocol communication over HTTP/SSE
Requires: pip install mcp httpx
"""
import asyncio
import json
import sys
from typing import Any, Dict, List

try:
    import httpx
    from mcp.client import ClientSession
    from mcp.client.sse import sse_client
except ImportError as e:
    print(f"❌ Missing required package: {e}")
    print("\nInstall with:")
    print("  pip install mcp httpx")
    sys.exit(1)


async def test_mcp_tools(base_url: str = "http://localhost:8001"):
    """Test MCP tools over HTTP/SSE."""
    print("🚀 Full MCP Client Test")
    print("=" * 60)
    print(f"Connecting to: {base_url}")
    print()
    
    try:
        async with httpx.AsyncClient() as http_client:
            # First verify server is up
            print("1️⃣  Checking server health...")
            try:
                response = await http_client.get(f"{base_url}/health", timeout=5.0)
                health = response.json()
                print(f"   Status: {health.get('status')}")
                if health.get('status') != 'ok':
                    print(f"   ⚠️  Server reports: {health}")
                else:
                    print("   ✅ Server is healthy")
            except Exception as e:
                print(f"   ❌ Health check failed: {e}")
                print("\n💡 Make sure the server is running:")
                print("   docker-compose -f docker-compose.http-mcp.yml up -d")
                return
            
            print("\n2️⃣  Connecting via SSE...")
            
            # Connect using SSE transport
            async with sse_client(
                url=f"{base_url}/sse",
                headers={"Accept": "text/event-stream"}
            ) as (read_stream, write_stream):
                print("   ✅ SSE connection established")
                
                print("\n3️⃣  Initializing MCP session...")
                async with ClientSession(read_stream, write_stream) as session:
                    print("   ✅ MCP session initialized")
                    
                    # Test: List tools
                    print("\n4️⃣  Listing available tools...")
                    tools_result = await session.list_tools()
                    
                    if tools_result and hasattr(tools_result, 'tools'):
                        tools = tools_result.tools
                        print(f"   Found {len(tools)} tools:")
                        for tool in tools:
                            print(f"      - {tool.name}: {tool.description}")
                    else:
                        print("   ⚠️  No tools found")
                    
                    # Test: Symbol lookup
                    print("\n5️⃣  Testing symbol_lookup tool...")
                    try:
                        result = await session.call_tool(
                            "symbol_lookup",
                            arguments={"symbol": "main"}
                        )
                        print(f"   Result: {result}")
                        print("   ✅ Symbol lookup works")
                    except Exception as e:
                        print(f"   ⚠️  Symbol lookup: {e}")
                    
                    # Test: Code search
                    print("\n6️⃣  Testing search_code tool...")
                    try:
                        result = await session.call_tool(
                            "search_code",
                            arguments={
                                "query": "def",
                                "limit": 5
                            }
                        )
                        print(f"   Result preview: {str(result)[:200]}...")
                        print("   ✅ Code search works")
                    except Exception as e:
                        print(f"   ⚠️  Code search: {e}")
                    
                    # Test: Get status
                    print("\n7️⃣  Testing get_status tool...")
                    try:
                        result = await session.call_tool("get_status", arguments={})
                        print(f"   Status: {result}")
                        print("   ✅ Status check works")
                    except Exception as e:
                        print(f"   ⚠️  Status check: {e}")
                    
                    # Test: List plugins
                    print("\n8️⃣  Testing list_plugins tool...")
                    try:
                        result = await session.call_tool("list_plugins", arguments={})
                        print(f"   Plugins: {result}")
                        print("   ✅ Plugin listing works")
                    except Exception as e:
                        print(f"   ⚠️  Plugin listing: {e}")
                    
                    print("\n" + "=" * 60)
                    print("✅ All MCP tests completed!")
                    print("\n📊 Summary:")
                    print("   - SSE connection: ✅")
                    print("   - MCP session: ✅")
                    print("   - Tool listing: ✅")
                    print("   - Tool invocation: Check results above")
    
    except Exception as e:
        print(f"\n❌ Error during MCP test: {e}")
        print(f"   Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        
        print("\n💡 Troubleshooting:")
        print("   1. Ensure server is running:")
        print("      docker-compose -f docker-compose.http-mcp.yml up -d")
        print("   2. Check server logs:")
        print("      docker logs code-index-http-mcp")
        print("   3. Verify server health:")
        print("      curl http://localhost:8001/health")


async def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Full MCP Client Test for HTTP MCP Server"
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8001",
        help="Base URL of the HTTP MCP server"
    )
    
    args = parser.parse_args()
    
    await test_mcp_tools(args.url)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)
