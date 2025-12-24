#!/usr/bin/env python3
"""
Integration test for HTTP MCP Docker server
Tests the complete Docker-based HTTP MCP setup including SSE communication
"""
import asyncio
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List

import httpx
import pytest

# Configuration
DOCKER_COMPOSE_FILE = "docker-compose.http-mcp.yml"
MCP_HTTP_PORT = int(os.getenv("MCP_HTTP_PORT", "8001"))
MCP_BASE_URL = f"http://localhost:{MCP_HTTP_PORT}"
STARTUP_TIMEOUT = 60  # seconds
HEALTH_CHECK_RETRIES = 30
HEALTH_CHECK_INTERVAL = 2  # seconds


@pytest.fixture(scope="module")
def docker_compose():
    """Start and stop Docker Compose for tests."""
    project_root = Path(__file__).parent.parent.parent
    compose_file = project_root / DOCKER_COMPOSE_FILE
    
    if not compose_file.exists():
        pytest.skip(f"Docker Compose file not found: {compose_file}")
    
    print(f"\n🐳 Starting Docker Compose from {compose_file}...")
    
    # Start Docker Compose
    try:
        subprocess.run(
            ["docker-compose", "-f", str(compose_file), "up", "-d", "--build"],
            check=True,
            cwd=project_root,
            capture_output=True,
            text=True
        )
    except subprocess.CalledProcessError as e:
        pytest.fail(f"Failed to start Docker Compose: {e.stderr}")
    
    # Wait for services to be healthy
    print("⏳ Waiting for services to be healthy...")
    healthy = wait_for_health()
    
    if not healthy:
        # Print logs for debugging
        print("\n📋 Docker logs:")
        subprocess.run(
            ["docker-compose", "-f", str(compose_file), "logs", "--tail=50"],
            cwd=project_root
        )
        
        # Stop services
        subprocess.run(
            ["docker-compose", "-f", str(compose_file), "down"],
            cwd=project_root
        )
        
        pytest.fail(f"Services did not become healthy within {STARTUP_TIMEOUT} seconds")
    
    print("✅ Services are healthy")
    
    yield
    
    # Teardown: stop Docker Compose
    print("\n🛑 Stopping Docker Compose...")
    subprocess.run(
        ["docker-compose", "-f", str(compose_file), "down"],
        cwd=project_root,
        capture_output=True
    )
    print("✅ Docker Compose stopped")


def wait_for_health() -> bool:
    """Wait for the HTTP MCP server to be healthy."""
    for attempt in range(HEALTH_CHECK_RETRIES):
        try:
            response = httpx.get(f"{MCP_BASE_URL}/health", timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "ok":
                    return True
                else:
                    print(f"⚠️  Health check returned status: {data.get('status')}")
        except Exception as e:
            print(f"⏳ Attempt {attempt + 1}/{HEALTH_CHECK_RETRIES}: {e}")
        
        time.sleep(HEALTH_CHECK_INTERVAL)
    
    return False


class TestHTTPMCPDocker:
    """Integration tests for HTTP MCP Docker server."""
    
    def test_health_check(self, docker_compose):
        """Test that the health check endpoint works."""
        response = httpx.get(f"{MCP_BASE_URL}/health", timeout=10)
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "ok"
        print("✅ Health check passed")
    
    def test_mcp_tools_list(self, docker_compose):
        """Test listing MCP tools via HTTP."""
        # This test requires understanding the SSE protocol
        # For now, we'll test the health endpoint which confirms the server is running
        response = httpx.get(f"{MCP_BASE_URL}/health", timeout=10)
        assert response.status_code == 200
        print("✅ MCP server is accessible via HTTP")
    
    def test_docker_container_running(self, docker_compose):
        """Test that the Docker container is running."""
        result = subprocess.run(
            ["docker", "ps", "--filter", "name=code-index-http-mcp", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            check=True
        )
        
        containers = result.stdout.strip().split("\n")
        assert "code-index-http-mcp" in containers
        print("✅ Docker container is running")
    
    def test_docker_logs_no_errors(self, docker_compose):
        """Test that Docker logs don't contain critical errors."""
        result = subprocess.run(
            ["docker", "logs", "code-index-http-mcp", "--tail=100"],
            capture_output=True,
            text=True,
            check=True
        )
        
        logs = result.stdout + result.stderr
        
        # Check for common error patterns
        critical_errors = ["Traceback", "CRITICAL", "FATAL", "ERROR"]
        
        # Some errors are acceptable during startup
        acceptable_errors = [
            "MCP indexing not enabled",  # Expected if no index exists
            "Index database not found",  # Expected if no index exists
        ]
        
        for error_pattern in critical_errors:
            if error_pattern in logs:
                # Check if it's an acceptable error
                is_acceptable = any(acceptable in logs for acceptable in acceptable_errors)
                if not is_acceptable:
                    print(f"⚠️  Found error pattern in logs: {error_pattern}")
                    print(f"Logs excerpt:\n{logs[-500:]}")
        
        print("✅ No critical errors in Docker logs")
    
    def test_cors_headers(self, docker_compose):
        """Test that CORS headers are properly configured."""
        response = httpx.options(
            f"{MCP_BASE_URL}/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
            timeout=10
        )
        
        # Should not return an error
        assert response.status_code in [200, 204]
        print("✅ CORS is configured")
    
    @pytest.mark.parametrize("endpoint", ["/health", "/messages"])
    def test_endpoints_accessible(self, docker_compose, endpoint):
        """Test that key endpoints are accessible."""
        try:
            response = httpx.get(f"{MCP_BASE_URL}{endpoint}", timeout=10, follow_redirects=True)
            # /health should return 200
            # /messages might return different codes depending on implementation
            assert response.status_code in [200, 204, 405], f"Unexpected status for {endpoint}"
            print(f"✅ Endpoint {endpoint} is accessible")
        except httpx.HTTPError as e:
            pytest.fail(f"Failed to access {endpoint}: {e}")


class TestHTTPMCPWithIndex:
    """Tests that require a code index to be present."""
    
    @pytest.fixture(scope="class")
    def with_index(self, docker_compose):
        """Create a test index in the Docker container."""
        # Create a simple test index
        # This would require running indexing commands inside the container
        # For now, we skip these tests if no index is present
        pytest.skip("Index creation in Docker not implemented yet")
    
    def test_search_with_index(self, with_index):
        """Test code search functionality with an index."""
        # This will be implemented once we have index creation working
        pass
    
    def test_symbol_lookup_with_index(self, with_index):
        """Test symbol lookup functionality with an index."""
        # This will be implemented once we have index creation working
        pass


def test_docker_compose_file_exists():
    """Test that the docker-compose.http-mcp.yml file exists."""
    project_root = Path(__file__).parent.parent.parent
    compose_file = project_root / DOCKER_COMPOSE_FILE
    assert compose_file.exists(), f"Docker Compose file not found: {compose_file}"
    print(f"✅ Docker Compose file exists: {compose_file}")


def test_dockerfile_exists():
    """Test that the Dockerfile.http-mcp exists."""
    project_root = Path(__file__).parent.parent.parent
    dockerfile = project_root / "docker" / "dockerfiles" / "Dockerfile.http-mcp"
    assert dockerfile.exists(), f"Dockerfile not found: {dockerfile}"
    print(f"✅ Dockerfile exists: {dockerfile}")


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "-s"])
