"""
Comprehensive tests for RelationshipTracker.

Tests cover:
- Basic relationship operations
- Confidence score ordering
- Impact analysis
- File cleanup
- BFS pathfinding
- NetworkX validation
- Performance benchmarks
"""

import time
from pathlib import Path

import pytest

# Optional NetworkX for validation
try:
    import networkx as nx
    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False

from mcp_server.storage.relationship_tracker import ImpactAnalysis, RelationshipTracker
from mcp_server.storage.sqlite_store import SQLiteStore


class TestRelationshipTrackerBasics:
    """Test basic relationship operations."""

    def test_initialization(self, temp_db_path):
        """Test that tracker initializes correctly."""
        tracker = RelationshipTracker(str(temp_db_path))
        
        # Verify schema was created
        import sqlite3
        conn = sqlite3.connect(str(temp_db_path))
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='relationships'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    def test_add_relationship(self, sqlite_store, temp_db_path):
        """Test adding a single relationship."""
        # Create some symbols first
        repo_id = sqlite_store.create_repository("/test/repo", "test-repo")
        file_id = sqlite_store.store_file(
            repo_id, "/test/repo/main.py", "main.py", language="python"
        )
        symbol1_id = sqlite_store.store_symbol(
            file_id, "main", "function", 1, 10, signature="def main():"
        )
        symbol2_id = sqlite_store.store_symbol(
            file_id, "helper", "function", 12, 20, signature="def helper():"
        )
        
        # Add relationship
        tracker = RelationshipTracker(str(temp_db_path))
        rel_id = tracker.add_relationship(
            source_entity_id=symbol1_id,
            target_entity_id=symbol2_id,
            relationship_type="calls",
            source_name="main",
            target_name="helper",
            confidence_score=1.0,
        )
        
        assert rel_id > 0

    def test_get_dependencies(self, sqlite_store, temp_db_path):
        """Test getting dependencies of an entity."""
        # Setup: Create symbols and relationships
        repo_id = sqlite_store.create_repository("/test/repo", "test-repo")
        file_id = sqlite_store.store_file(
            repo_id, "/test/repo/main.py", "main.py", language="python"
        )
        
        main_id = sqlite_store.store_symbol(file_id, "main", "function", 1, 10)
        helper1_id = sqlite_store.store_symbol(file_id, "helper1", "function", 12, 20)
        helper2_id = sqlite_store.store_symbol(file_id, "helper2", "function", 22, 30)
        
        tracker = RelationshipTracker(str(temp_db_path))
        tracker.add_relationship(main_id, helper1_id, "calls", "main", "helper1")
        tracker.add_relationship(main_id, helper2_id, "calls", "main", "helper2")
        
        # Test
        deps = tracker.get_dependencies(main_id)
        assert len(deps) == 2
        assert {d["target_name"] for d in deps} == {"helper1", "helper2"}

    def test_get_dependents(self, sqlite_store, temp_db_path):
        """Test getting dependents of an entity."""
        # Setup
        repo_id = sqlite_store.create_repository("/test/repo", "test-repo")
        file_id = sqlite_store.store_file(
            repo_id, "/test/repo/main.py", "main.py", language="python"
        )
        
        util_id = sqlite_store.store_symbol(file_id, "util", "function", 1, 10)
        caller1_id = sqlite_store.store_symbol(file_id, "caller1", "function", 12, 20)
        caller2_id = sqlite_store.store_symbol(file_id, "caller2", "function", 22, 30)
        
        tracker = RelationshipTracker(str(temp_db_path))
        tracker.add_relationship(caller1_id, util_id, "calls", "caller1", "util")
        tracker.add_relationship(caller2_id, util_id, "calls", "caller2", "util")
        
        # Test
        dependents = tracker.get_dependents(util_id)
        assert len(dependents) == 2
        assert {d["source_name"] for d in dependents} == {"caller1", "caller2"}


class TestConfidenceOrdering:
    """Test that results are ordered by confidence score."""

    def test_confidence_ordering_dependencies(self, sqlite_store, temp_db_path):
        """Test that dependencies are ordered by confidence score."""
        # Setup
        repo_id = sqlite_store.create_repository("/test/repo", "test-repo")
        file_id = sqlite_store.store_file(
            repo_id, "/test/repo/main.py", "main.py", language="python"
        )
        
        source_id = sqlite_store.store_symbol(file_id, "source", "function", 1, 10)
        target1_id = sqlite_store.store_symbol(file_id, "target1", "function", 12, 20)
        target2_id = sqlite_store.store_symbol(file_id, "target2", "function", 22, 30)
        target3_id = sqlite_store.store_symbol(file_id, "target3", "function", 32, 40)
        
        tracker = RelationshipTracker(str(temp_db_path))
        
        # Add relationships with different confidence scores
        tracker.add_relationship(
            source_id, target1_id, "calls", "source", "target1", confidence_score=0.7
        )
        tracker.add_relationship(
            source_id, target2_id, "calls", "source", "target2", confidence_score=1.0
        )
        tracker.add_relationship(
            source_id, target3_id, "calls", "source", "target3", confidence_score=0.5
        )
        
        # Test: High confidence (1.0) should come first
        deps = tracker.get_dependencies(source_id)
        assert len(deps) == 3
        assert deps[0]["target_name"] == "target2"
        assert deps[0]["confidence_score"] == 1.0

    def test_confidence_ordering_dependents(self, sqlite_store, temp_db_path):
        """Test that dependents are ordered by confidence score."""
        # Setup
        repo_id = sqlite_store.create_repository("/test/repo", "test-repo")
        file_id = sqlite_store.store_file(
            repo_id, "/test/repo/main.py", "main.py", language="python"
        )
        
        target_id = sqlite_store.store_symbol(file_id, "target", "function", 1, 10)
        source1_id = sqlite_store.store_symbol(file_id, "source1", "function", 12, 20)
        source2_id = sqlite_store.store_symbol(file_id, "source2", "function", 22, 30)
        
        tracker = RelationshipTracker(str(temp_db_path))
        
        # Add relationships with different confidence scores
        tracker.add_relationship(
            source1_id, target_id, "calls", "source1", "target", confidence_score=0.8
        )
        tracker.add_relationship(
            source2_id, target_id, "calls", "source2", "target", confidence_score=1.0
        )
        
        # Test: High confidence (1.0) should come first
        dependents = tracker.get_dependents(target_id)
        assert len(dependents) == 2
        assert dependents[0]["source_name"] == "source2"
        assert dependents[0]["confidence_score"] == 1.0


class TestImpactAnalysis:
    """Test impact analysis functionality."""

    def test_impact_analysis_finds_all_dependents(self, sqlite_store, temp_db_path):
        """Test impact analysis finds direct and indirect dependents."""
        # Setup: Create a chain of dependencies
        # A -> B -> C -> D
        repo_id = sqlite_store.create_repository("/test/repo", "test-repo")
        file_id = sqlite_store.store_file(
            repo_id, "/test/repo/main.py", "main.py", language="python"
        )
        
        a_id = sqlite_store.store_symbol(file_id, "A", "function", 1, 10)
        b_id = sqlite_store.store_symbol(file_id, "B", "function", 12, 20)
        c_id = sqlite_store.store_symbol(file_id, "C", "function", 22, 30)
        d_id = sqlite_store.store_symbol(file_id, "D", "function", 32, 40)
        
        tracker = RelationshipTracker(str(temp_db_path))
        tracker.add_relationship(b_id, a_id, "calls", "B", "A")
        tracker.add_relationship(c_id, b_id, "calls", "C", "B")
        tracker.add_relationship(d_id, c_id, "calls", "D", "C")
        
        # Test: Impact of changing A should affect B, C, D
        impact = tracker.get_symbol_impact(a_id, max_depth=3)
        
        assert isinstance(impact, ImpactAnalysis)
        assert impact.symbol_id == a_id
        assert len(impact.direct_dependents) == 1
        assert impact.direct_dependents[0]["source_name"] == "B"
        assert len(impact.indirect_dependents) == 2
        assert impact.total_impact == 3

    def test_impact_analysis_affected_files(self, sqlite_store, temp_db_path):
        """Test affected files are correctly collected."""
        # Setup: Create symbols in different files
        repo_id = sqlite_store.create_repository("/test/repo", "test-repo")
        
        file1_id = sqlite_store.store_file(
            repo_id, "/test/repo/file1.py", "file1.py", language="python"
        )
        file2_id = sqlite_store.store_file(
            repo_id, "/test/repo/file2.py", "file2.py", language="python"
        )
        
        func1_id = sqlite_store.store_symbol(file1_id, "func1", "function", 1, 10)
        func2_id = sqlite_store.store_symbol(file2_id, "func2", "function", 1, 10)
        
        tracker = RelationshipTracker(str(temp_db_path))
        tracker.add_relationship(
            func2_id, func1_id, "calls", "func2", "func1",
            source_file="/test/repo/file2.py", target_file="/test/repo/file1.py"
        )
        
        # Test
        impact = tracker.get_symbol_impact(func1_id, max_depth=2)
        assert len(impact.affected_files) == 1
        assert "/test/repo/file2.py" in impact.affected_files

    def test_impact_analysis_max_depth(self, sqlite_store, temp_db_path):
        """Test that max_depth parameter limits traversal."""
        # Setup: Create a deep chain
        repo_id = sqlite_store.create_repository("/test/repo", "test-repo")
        file_id = sqlite_store.store_file(
            repo_id, "/test/repo/main.py", "main.py", language="python"
        )
        
        ids = []
        for i in range(5):
            symbol_id = sqlite_store.store_symbol(
                file_id, f"func{i}", "function", i * 10, i * 10 + 8
            )
            ids.append(symbol_id)
        
        tracker = RelationshipTracker(str(temp_db_path))
        
        # Create chain: func4 -> func3 -> func2 -> func1 -> func0
        for i in range(4):
            tracker.add_relationship(
                ids[i + 1], ids[i], "calls", f"func{i+1}", f"func{i}"
            )
        
        # Test with max_depth=2
        impact = tracker.get_symbol_impact(ids[0], max_depth=2)
        assert impact.total_impact == 2  # Only func1 and func2
        
        # Test with max_depth=4
        impact = tracker.get_symbol_impact(ids[0], max_depth=4)
        assert impact.total_impact == 4  # func1, func2, func3, func4


class TestFileCleanup:
    """Test clearing relationships by file path."""

    def test_clear_relationships_for_file(self, sqlite_store, temp_db_path):
        """Test clearing relationships for a specific file."""
        # Setup: Create relationships from file1
        repo_id = sqlite_store.create_repository("/test/repo", "test-repo")
        
        file1_id = sqlite_store.store_file(
            repo_id, "/test/repo/file1.py", "file1.py", language="python"
        )
        file2_id = sqlite_store.store_file(
            repo_id, "/test/repo/file2.py", "file2.py", language="python"
        )
        
        func1_id = sqlite_store.store_symbol(file1_id, "func1", "function", 1, 10)
        func2_id = sqlite_store.store_symbol(file1_id, "func2", "function", 12, 20)
        func3_id = sqlite_store.store_symbol(file2_id, "func3", "function", 1, 10)
        
        tracker = RelationshipTracker(str(temp_db_path))
        
        # Add relationships
        tracker.add_relationship(func1_id, func3_id, "calls", "func1", "func3")
        tracker.add_relationship(func2_id, func3_id, "calls", "func2", "func3")
        
        # Verify relationships exist
        deps = tracker.get_dependents(func3_id)
        assert len(deps) == 2
        
        # Clear relationships from file1
        tracker.clear_relationships_for_file("/test/repo/file1.py")
        
        # Verify relationships are cleared
        deps = tracker.get_dependents(func3_id)
        assert len(deps) == 0

    def test_clear_relationships_idempotent(self, sqlite_store, temp_db_path):
        """Test that clearing relationships multiple times is safe."""
        repo_id = sqlite_store.create_repository("/test/repo", "test-repo")
        file_id = sqlite_store.store_file(
            repo_id, "/test/repo/file1.py", "file1.py", language="python"
        )
        
        tracker = RelationshipTracker(str(temp_db_path))
        
        # Clear non-existent file (should not error)
        tracker.clear_relationships_for_file("/test/repo/file1.py")
        tracker.clear_relationships_for_file("/test/repo/file1.py")


class TestPathfinding:
    """Test BFS pathfinding algorithm."""

    def test_find_direct_path(self, sqlite_store, temp_db_path):
        """Test finding a direct path between entities."""
        # Setup: A -> B
        repo_id = sqlite_store.create_repository("/test/repo", "test-repo")
        file_id = sqlite_store.store_file(
            repo_id, "/test/repo/main.py", "main.py", language="python"
        )
        
        a_id = sqlite_store.store_symbol(file_id, "A", "function", 1, 10)
        b_id = sqlite_store.store_symbol(file_id, "B", "function", 12, 20)
        
        tracker = RelationshipTracker(str(temp_db_path))
        tracker.add_relationship(a_id, b_id, "calls", "A", "B")
        
        # Test
        paths = tracker.find_paths(a_id, b_id)
        assert len(paths) == 1
        assert len(paths[0]) == 1
        assert paths[0][0]["target_name"] == "B"

    def test_find_indirect_path(self, sqlite_store, temp_db_path):
        """Test finding an indirect path."""
        # Setup: A -> B -> C
        repo_id = sqlite_store.create_repository("/test/repo", "test-repo")
        file_id = sqlite_store.store_file(
            repo_id, "/test/repo/main.py", "main.py", language="python"
        )
        
        a_id = sqlite_store.store_symbol(file_id, "A", "function", 1, 10)
        b_id = sqlite_store.store_symbol(file_id, "B", "function", 12, 20)
        c_id = sqlite_store.store_symbol(file_id, "C", "function", 22, 30)
        
        tracker = RelationshipTracker(str(temp_db_path))
        tracker.add_relationship(a_id, b_id, "calls", "A", "B")
        tracker.add_relationship(b_id, c_id, "calls", "B", "C")
        
        # Test
        paths = tracker.find_paths(a_id, c_id)
        assert len(paths) == 1
        assert len(paths[0]) == 2
        assert paths[0][0]["target_name"] == "B"
        assert paths[0][1]["target_name"] == "C"

    def test_find_multiple_paths(self, sqlite_store, temp_db_path):
        """Test finding multiple paths between entities."""
        # Setup: A -> B -> D and A -> C -> D
        repo_id = sqlite_store.create_repository("/test/repo", "test-repo")
        file_id = sqlite_store.store_file(
            repo_id, "/test/repo/main.py", "main.py", language="python"
        )
        
        a_id = sqlite_store.store_symbol(file_id, "A", "function", 1, 10)
        b_id = sqlite_store.store_symbol(file_id, "B", "function", 12, 20)
        c_id = sqlite_store.store_symbol(file_id, "C", "function", 22, 30)
        d_id = sqlite_store.store_symbol(file_id, "D", "function", 32, 40)
        
        tracker = RelationshipTracker(str(temp_db_path))
        tracker.add_relationship(a_id, b_id, "calls", "A", "B")
        tracker.add_relationship(a_id, c_id, "calls", "A", "C")
        tracker.add_relationship(b_id, d_id, "calls", "B", "D")
        tracker.add_relationship(c_id, d_id, "calls", "C", "D")
        
        # Test
        paths = tracker.find_paths(a_id, d_id)
        assert len(paths) == 2
        # Both paths should have length 2
        assert all(len(path) == 2 for path in paths)

    def test_no_path_exists(self, sqlite_store, temp_db_path):
        """Test when no path exists between entities."""
        # Setup: A -> B and C (disconnected)
        repo_id = sqlite_store.create_repository("/test/repo", "test-repo")
        file_id = sqlite_store.store_file(
            repo_id, "/test/repo/main.py", "main.py", language="python"
        )
        
        a_id = sqlite_store.store_symbol(file_id, "A", "function", 1, 10)
        b_id = sqlite_store.store_symbol(file_id, "B", "function", 12, 20)
        c_id = sqlite_store.store_symbol(file_id, "C", "function", 22, 30)
        
        tracker = RelationshipTracker(str(temp_db_path))
        tracker.add_relationship(a_id, b_id, "calls", "A", "B")
        
        # Test
        paths = tracker.find_paths(a_id, c_id)
        assert len(paths) == 0


class TestBatchOperations:
    """Test batch relationship operations."""

    def test_add_relationships_batch(self, sqlite_store, temp_db_path):
        """Test adding multiple relationships in one transaction."""
        # Setup
        repo_id = sqlite_store.create_repository("/test/repo", "test-repo")
        file_id = sqlite_store.store_file(
            repo_id, "/test/repo/main.py", "main.py", language="python"
        )
        
        ids = []
        for i in range(10):
            symbol_id = sqlite_store.store_symbol(
                file_id, f"func{i}", "function", i * 10, i * 10 + 8
            )
            ids.append(symbol_id)
        
        tracker = RelationshipTracker(str(temp_db_path))
        
        # Create batch relationships
        relationships = [
            (ids[0], ids[i], "calls", "func0", f"func{i}", None, None, 1.0, None)
            for i in range(1, 10)
        ]
        
        count = tracker.add_relationships_batch(relationships)
        assert count == 9
        
        # Verify
        deps = tracker.get_dependencies(ids[0])
        assert len(deps) == 9


@pytest.mark.skipif(not HAS_NETWORKX, reason="NetworkX not installed")
class TestNetworkXValidation:
    """Validate graph algorithms against NetworkX."""

    def test_pathfinding_matches_networkx(self, sqlite_store, temp_db_path):
        """Test that our BFS matches NetworkX pathfinding."""
        # Setup: Create a graph
        repo_id = sqlite_store.create_repository("/test/repo", "test-repo")
        file_id = sqlite_store.store_file(
            repo_id, "/test/repo/main.py", "main.py", language="python"
        )
        
        # Create a diamond graph: A -> B, A -> C, B -> D, C -> D
        a_id = sqlite_store.store_symbol(file_id, "A", "function", 1, 10)
        b_id = sqlite_store.store_symbol(file_id, "B", "function", 12, 20)
        c_id = sqlite_store.store_symbol(file_id, "C", "function", 22, 30)
        d_id = sqlite_store.store_symbol(file_id, "D", "function", 32, 40)
        
        tracker = RelationshipTracker(str(temp_db_path))
        tracker.add_relationship(a_id, b_id, "calls", "A", "B")
        tracker.add_relationship(a_id, c_id, "calls", "A", "C")
        tracker.add_relationship(b_id, d_id, "calls", "B", "D")
        tracker.add_relationship(c_id, d_id, "calls", "C", "D")
        
        # Build NetworkX graph
        G = nx.DiGraph()
        G.add_edges_from([
            (a_id, b_id),
            (a_id, c_id),
            (b_id, d_id),
            (c_id, d_id),
        ])
        
        # Compare path counts
        our_paths = tracker.find_paths(a_id, d_id)
        nx_paths = list(nx.all_simple_paths(G, a_id, d_id))
        
        assert len(our_paths) == len(nx_paths)


class TestPerformance:
    """Performance benchmarks for relationship operations."""

    @pytest.mark.benchmark
    def test_query_performance(self, sqlite_store, temp_db_path):
        """Test that queries complete in <100ms."""
        # Setup: Create a large graph
        repo_id = sqlite_store.create_repository("/test/repo", "test-repo")
        file_id = sqlite_store.store_file(
            repo_id, "/test/repo/main.py", "main.py", language="python"
        )
        
        # Create 100 symbols
        ids = []
        for i in range(100):
            symbol_id = sqlite_store.store_symbol(
                file_id, f"func{i}", "function", i * 10, i * 10 + 8
            )
            ids.append(symbol_id)
        
        tracker = RelationshipTracker(str(temp_db_path))
        
        # Create relationships (each node connects to 10 others)
        for i in range(90):
            for j in range(i + 1, min(i + 11, 100)):
                tracker.add_relationship(
                    ids[i], ids[j], "calls", f"func{i}", f"func{j}"
                )
        
        # Benchmark queries
        start = time.time()
        deps = tracker.get_dependencies(ids[0])
        query_time = (time.time() - start) * 1000  # Convert to ms
        
        assert query_time < 100, f"Query took {query_time:.2f}ms (should be <100ms)"
        assert len(deps) > 0

    @pytest.mark.benchmark
    def test_batch_performance(self, sqlite_store, temp_db_path):
        """Test that batch operations complete in <1s."""
        # Setup
        repo_id = sqlite_store.create_repository("/test/repo", "test-repo")
        file_id = sqlite_store.store_file(
            repo_id, "/test/repo/main.py", "main.py", language="python"
        )
        
        # Create 100 symbols
        ids = []
        for i in range(100):
            symbol_id = sqlite_store.store_symbol(
                file_id, f"func{i}", "function", i * 10, i * 10 + 8
            )
            ids.append(symbol_id)
        
        tracker = RelationshipTracker(str(temp_db_path))
        
        # Create 500 relationships
        relationships = []
        for i in range(100):
            for j in range(i + 1, min(i + 6, 100)):
                relationships.append(
                    (ids[i], ids[j], "calls", f"func{i}", f"func{j}", None, None, 1.0, None)
                )
        
        # Benchmark batch operation
        start = time.time()
        count = tracker.add_relationships_batch(relationships)
        batch_time = time.time() - start
        
        assert batch_time < 1.0, f"Batch operation took {batch_time:.2f}s (should be <1s)"
        assert count == len(relationships)


class TestRelationshipStats:
    """Test relationship statistics."""

    def test_get_relationship_stats(self, sqlite_store, temp_db_path):
        """Test getting relationship statistics."""
        # Setup
        repo_id = sqlite_store.create_repository("/test/repo", "test-repo")
        file_id = sqlite_store.store_file(
            repo_id, "/test/repo/main.py", "main.py", language="python"
        )
        
        ids = []
        for i in range(5):
            symbol_id = sqlite_store.store_symbol(
                file_id, f"func{i}", "function", i * 10, i * 10 + 8
            )
            ids.append(symbol_id)
        
        tracker = RelationshipTracker(str(temp_db_path))
        
        # Add different types of relationships
        tracker.add_relationship(ids[0], ids[1], "calls", "func0", "func1")
        tracker.add_relationship(ids[0], ids[2], "calls", "func0", "func2")
        tracker.add_relationship(ids[1], ids[3], "imports", "func1", "func3")
        
        # Test
        stats = tracker.get_relationship_stats()
        assert stats["total"] == 3
        assert len(stats["by_type"]) == 2  # calls and imports
        
        # Find calls type
        calls_stat = next(s for s in stats["by_type"] if s["relationship_type"] == "calls")
        assert calls_stat["count"] == 2
