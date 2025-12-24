"""
Integration test for the impact analysis endpoint.
"""

import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from mcp_server.storage.sqlite_store import SQLiteStore
from mcp_server.storage.relationship_tracker import RelationshipTracker


class TestImpactAnalysisEndpoint:
    """Test the /api/v1/impact-analysis endpoint."""
    
    def test_impact_analysis_endpoint_basic(self, sqlite_store, temp_db_path):
        """Test that the impact analysis endpoint returns correct data."""
        # Setup: Create test data
        repo_id = sqlite_store.create_repository("/test/repo", "test-repo")
        file_id = sqlite_store.store_file(
            repo_id, "/test/repo/main.py", "main.py", language="python"
        )
        
        # Create a chain: A -> B -> C
        a_id = sqlite_store.store_symbol(file_id, "A", "function", 1, 10)
        b_id = sqlite_store.store_symbol(file_id, "B", "function", 12, 20)
        c_id = sqlite_store.store_symbol(file_id, "C", "function", 22, 30)
        
        # Add relationships
        tracker = RelationshipTracker(str(temp_db_path))
        tracker.add_relationship(
            b_id, a_id, "calls", "B", "A",
            source_file="/test/repo/main.py",
            target_file="/test/repo/main.py"
        )
        tracker.add_relationship(
            c_id, b_id, "calls", "C", "B",
            source_file="/test/repo/main.py",
            target_file="/test/repo/main.py"
        )
        
        # Test direct impact analysis (without HTTP call)
        impact = tracker.get_symbol_impact(a_id, max_depth=2)
        
        assert impact.symbol_id == a_id
        assert len(impact.direct_dependents) == 1
        assert impact.direct_dependents[0]["source_name"] == "B"
        assert len(impact.indirect_dependents) == 1
        assert impact.indirect_dependents[0]["source_name"] == "C"
        assert impact.total_impact == 2
        assert len(impact.affected_files) == 1
        assert "/test/repo/main.py" in impact.affected_files
    
    def test_impact_analysis_no_dependents(self, sqlite_store, temp_db_path):
        """Test impact analysis for a symbol with no dependents."""
        repo_id = sqlite_store.create_repository("/test/repo", "test-repo")
        file_id = sqlite_store.store_file(
            repo_id, "/test/repo/main.py", "main.py", language="python"
        )
        
        symbol_id = sqlite_store.store_symbol(file_id, "isolated", "function", 1, 10)
        
        tracker = RelationshipTracker(str(temp_db_path))
        impact = tracker.get_symbol_impact(symbol_id, max_depth=2)
        
        assert impact.symbol_id == symbol_id
        assert len(impact.direct_dependents) == 0
        assert len(impact.indirect_dependents) == 0
        assert impact.total_impact == 0
        assert len(impact.affected_files) == 0
    
    def test_impact_analysis_multiple_files(self, sqlite_store, temp_db_path):
        """Test impact analysis across multiple files."""
        repo_id = sqlite_store.create_repository("/test/repo", "test-repo")
        
        file1_id = sqlite_store.store_file(
            repo_id, "/test/repo/file1.py", "file1.py", language="python"
        )
        file2_id = sqlite_store.store_file(
            repo_id, "/test/repo/file2.py", "file2.py", language="python"
        )
        file3_id = sqlite_store.store_file(
            repo_id, "/test/repo/file3.py", "file3.py", language="python"
        )
        
        # Symbol in file1
        util_id = sqlite_store.store_symbol(file1_id, "util", "function", 1, 10)
        
        # Symbols in file2 that depend on util
        func1_id = sqlite_store.store_symbol(file2_id, "func1", "function", 1, 10)
        func2_id = sqlite_store.store_symbol(file2_id, "func2", "function", 12, 20)
        
        # Symbol in file3 that depends on func1
        caller_id = sqlite_store.store_symbol(file3_id, "caller", "function", 1, 10)
        
        tracker = RelationshipTracker(str(temp_db_path))
        tracker.add_relationship(
            func1_id, util_id, "calls", "func1", "util",
            source_file="/test/repo/file2.py",
            target_file="/test/repo/file1.py"
        )
        tracker.add_relationship(
            func2_id, util_id, "calls", "func2", "util",
            source_file="/test/repo/file2.py",
            target_file="/test/repo/file1.py"
        )
        tracker.add_relationship(
            caller_id, func1_id, "calls", "caller", "func1",
            source_file="/test/repo/file3.py",
            target_file="/test/repo/file2.py"
        )
        
        # Test
        impact = tracker.get_symbol_impact(util_id, max_depth=2)
        
        assert impact.total_impact == 3  # func1, func2, caller
        assert len(impact.direct_dependents) == 2  # func1, func2
        assert len(impact.indirect_dependents) == 1  # caller
        assert len(impact.affected_files) == 2  # file2.py, file3.py
        assert "/test/repo/file2.py" in impact.affected_files
        assert "/test/repo/file3.py" in impact.affected_files
