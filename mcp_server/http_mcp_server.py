#!/usr/bin/env python3
"""
HTTP MCP Server - Provides MCP protocol over HTTP using Server-Sent Events (SSE)
This allows Claude Code and other MCP clients to connect via HTTP instead of STDIO.
"""
import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import mcp.types as types
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from mcp.server import Server
from mcp.server.sse import SseServerTransport

from .core.logging import setup_logging
from .dispatcher.dispatcher_enhanced import EnhancedDispatcher
from .dispatcher.simple_dispatcher import SimpleDispatcher
from .plugin_system import PluginManager
from .storage.sqlite_store import SQLiteStore
from .utils.index_discovery import IndexDiscovery

# Set up logging
setup_logging(log_level="INFO")
logger = logging.getLogger(__name__)

# Initialize the MCP server
mcp_server = Server("code-index-mcp-http")

# Global instances
dispatcher: EnhancedDispatcher | SimpleDispatcher | None = None
plugin_manager: PluginManager | None = None
sqlite_store: SQLiteStore | None = None
initialization_error: str | None = None

# Configuration from environment
USE_SIMPLE_DISPATCHER = os.getenv("MCP_USE_SIMPLE_DISPATCHER", "false").lower() == "true"


async def initialize_services():
    """Initialize all services needed for the MCP server."""
    global dispatcher, plugin_manager, sqlite_store, initialization_error
    
    try:
        # Use multi-path discovery to find index
        current_dir = Path.cwd()
        enable_multi_path = os.getenv("MCP_ENABLE_MULTI_PATH", "true").lower() == "true"
        
        logger.info("Searching for index using multi-path discovery...")
        discovery = IndexDiscovery(current_dir, enable_multi_path=enable_multi_path)
        
        # Get information about index discovery
        index_info = discovery.get_index_info()
        
        if not index_info["enabled"]:
            logger.error("MCP indexing is not enabled for this repository")
            raise RuntimeError("MCP indexing not enabled. Create .mcp-index.json to enable.")
        
        # Discover index path
        index_path = discovery.discover_index()
        
        if not index_path:
            logger.error("Could not find index database")
            raise RuntimeError("Index database not found. Run 'mcp-index rebuild' to create index.")
        
        logger.info(f"Found index at: {index_path}")
        
        # Initialize SQLite store
        sqlite_store = SQLiteStore(str(index_path))
        logger.info("SQLite store initialized successfully")
        
        # Initialize dispatcher based on configuration
        if USE_SIMPLE_DISPATCHER:
            logger.info("Using Simple Dispatcher (BM25-only, no plugin loading)")
            dispatcher = SimpleDispatcher(sqlite_store)
        else:
            logger.info("Using Enhanced Dispatcher with plugin support")
            semantic_enabled = os.getenv("SEMANTIC_SEARCH_ENABLED", "false").lower() == "true"
            dispatcher = EnhancedDispatcher(
                sqlite_store=sqlite_store,
                semantic_search_enabled=semantic_enabled,
                lazy_load=True,
            )
        
        logger.info("HTTP MCP server initialized successfully")
        
    except Exception as e:
        error_msg = f"Failed to initialize HTTP MCP server: {e}"
        logger.error(error_msg, exc_info=True)
        initialization_error = error_msg
        raise


# MCP Tool Handlers
@mcp_server.list_tools()
async def list_tools() -> List[types.Tool]:
    """List available MCP tools."""
    return [
        types.Tool(
            name="symbol_lookup",
            description="Look up a symbol definition in the codebase",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "The symbol name to look up (class, function, variable, etc.)",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Optional: specific file to search in",
                    },
                },
                "required": ["symbol"],
            },
        ),
        types.Tool(
            name="search_code",
            description="Search for code patterns across the codebase",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (supports regex patterns)",
                    },
                    "file_extensions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional: filter by file extensions (e.g., ['.py', '.js'])",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default: 10)",
                        "default": 10,
                    },
                    "semantic": {
                        "type": "boolean",
                        "description": "Use semantic search if available (default: false)",
                        "default": False,
                    },
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="get_status",
            description="Get the status of the code index server",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        types.Tool(
            name="list_plugins",
            description="List all available language plugins",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
    ]


@mcp_server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[types.TextContent]:
    """Handle tool calls from MCP clients."""
    if initialization_error:
        return [
            types.TextContent(
                type="text",
                text=f"Error: Server not properly initialized - {initialization_error}",
            )
        ]
    
    if not dispatcher:
        return [
            types.TextContent(
                type="text",
                text="Error: Dispatcher not initialized",
            )
        ]
    
    try:
        if name == "symbol_lookup":
            symbol = arguments.get("symbol")
            file_path = arguments.get("file_path")
            
            if not symbol:
                return [types.TextContent(type="text", text="Error: 'symbol' parameter is required")]
            
            # Use dispatcher to look up symbol
            result = dispatcher.getDefinition(symbol, {"file_path": file_path} if file_path else {})
            
            if result:
                return [
                    types.TextContent(
                        type="text",
                        text=json.dumps(result, indent=2),
                    )
                ]
            else:
                return [
                    types.TextContent(
                        type="text",
                        text=f"Symbol '{symbol}' not found",
                    )
                ]
        
        elif name == "search_code":
            query = arguments.get("query")
            limit = arguments.get("limit", 10)
            semantic = arguments.get("semantic", False)
            
            if not query:
                return [types.TextContent(type="text", text="Error: 'query' parameter is required")]
            
            # Use dispatcher to search
            results = list(dispatcher.search(query, semantic=semantic, limit=limit))
            
            if results:
                return [
                    types.TextContent(
                        type="text",
                        text=json.dumps([r.__dict__ if hasattr(r, '__dict__') else r for r in results], indent=2, default=str),
                    )
                ]
            else:
                return [
                    types.TextContent(
                        type="text",
                        text=f"No results found for query: {query}",
                    )
                ]
        
        elif name == "get_status":
            status = {
                "status": "online",
                "dispatcher_type": "simple" if USE_SIMPLE_DISPATCHER else "enhanced",
                "semantic_search": dispatcher.semantic_search_enabled if hasattr(dispatcher, 'semantic_search_enabled') else False,
                "index_path": str(sqlite_store.db_path) if sqlite_store else None,
            }
            return [
                types.TextContent(
                    type="text",
                    text=json.dumps(status, indent=2),
                )
            ]
        
        elif name == "list_plugins":
            # List available plugins
            if hasattr(dispatcher, 'plugins'):
                plugins = list(dispatcher.plugins.keys())
            else:
                plugins = []
            
            return [
                types.TextContent(
                    type="text",
                    text=json.dumps({"plugins": plugins}, indent=2),
                )
            ]
        
        else:
            return [
                types.TextContent(
                    type="text",
                    text=f"Unknown tool: {name}",
                )
            ]
    
    except Exception as e:
        logger.error(f"Error handling tool call '{name}': {e}", exc_info=True)
        return [
            types.TextContent(
                type="text",
                text=f"Error: {str(e)}",
            )
        ]


# Create FastAPI app for HTTP MCP
http_mcp_app = FastAPI(
    title="HTTP MCP Server",
    description="Code Index MCP Server over HTTP using SSE",
    version="1.0.0"
)

# Configure CORS
http_mcp_app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@http_mcp_app.on_event("startup")
async def startup():
    """Initialize services on startup."""
    await initialize_services()


@http_mcp_app.get("/health")
async def health_check():
    """Health check endpoint."""
    if initialization_error:
        return {"status": "error", "error": initialization_error}
    return {"status": "ok"}


@http_mcp_app.post("/sse")
async def handle_sse(request: Request):
    """Handle SSE connections for MCP protocol."""
    try:
        # Create SSE transport
        async with SseServerTransport("/messages") as transport:
            # Run the MCP server with this transport
            await mcp_server.run(
                transport.read_stream,
                transport.write_stream,
                mcp_server.create_initialization_options()
            )
    except Exception as e:
        logger.error(f"Error in SSE handler: {e}", exc_info=True)
        raise


@http_mcp_app.get("/messages")
async def handle_messages():
    """SSE endpoint for receiving messages from client."""
    async def event_generator():
        """Generate SSE events."""
        try:
            # This will be handled by the SSE transport
            # Just keep the connection alive
            while True:
                await asyncio.sleep(1)
                yield {"data": json.dumps({"type": "ping"})}
        except asyncio.CancelledError:
            logger.info("SSE connection closed")
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


# For running as standalone application
if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("MCP_HTTP_PORT", "8001"))
    host = os.getenv("MCP_HTTP_HOST", "0.0.0.0")
    
    logger.info(f"Starting HTTP MCP server on {host}:{port}")
    uvicorn.run(http_mcp_app, host=host, port=port)
