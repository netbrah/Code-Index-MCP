"""
Comprehensive tests for the RelationshipTracker.

Tests cover:
- Adding and retrieving relationships
- Finding callers and callees
- Call graph traversal with depth limits
- Circular dependency detection
- Impact analysis with multi-level traversal
- Confidence level handling
- Edge cases (empty results, deep recursion, duplicate relationships)
"""

from pathlib import Path

import pytest

from mcp_server.storage.relationship_tracker import (
    CallGraphNode,
    CodeRelationship,
    FileRelationship,
    ImpactAnalysis,
    RelationshipTracker,
)
from mcp_server.storage.sqlite_store import SQLiteStore


class TestRelationshipDataClasses:
    """Test data classes and validation."""

    def test_code_relationship_valid(self):
        """Test creating a valid CodeRelationship."""
        rel = CodeRelationship(
            from_symbol="foo",
            to_symbol="bar",
            relationship_type="CALLS",
            from_file="/test/foo.py",
            to_file="/test/bar.py",
            line=42,
            confidence="CERTAIN",
        )
        assert rel.from_symbol == "foo"
        assert rel.to_symbol == "bar"
        assert rel.relationship_type == "CALLS"
        assert rel.confidence == "CERTAIN"

    def test_code_relationship_invalid_type(self):
        """Test that invalid relationship types raise ValueError."""
        with pytest.raises(ValueError, match="Invalid relationship_type"):
            CodeRelationship(
                from_symbol="foo",
                to_symbol="bar",
                relationship_type="INVALID",
                from_file="/test/foo.py",
            )

    def test_code_relationship_invalid_confidence(self):
        """Test that invalid confidence levels raise ValueError."""
        with pytest.raises(ValueError, match="Invalid confidence"):
            CodeRelationship(
                from_symbol="foo",
                to_symbol="bar",
                relationship_type="CALLS",
                from_file="/test/foo.py",
                confidence="INVALID",
            )

    def test_file_relationship_valid(self):
        """Test creating a valid FileRelationship."""
        rel = FileRelationship(
            from_file="/test/foo.py",
            to_file="/test/bar.py",
            relationship_type="IMPORTS",
            line=1,
            alias="bar_module",
        )
        assert rel.from_file == "/test/foo.py"
        assert rel.to_file == "/test/bar.py"
        assert rel.relationship_type == "IMPORTS"
        assert rel.alias == "bar_module"

    def test_file_relationship_invalid_type(self):
        """Test that invalid file relationship types raise ValueError."""
        with pytest.raises(ValueError, match="Invalid relationship_type"):
            FileRelationship(
                from_file="/test/foo.py",
                to_file="/test/bar.py",
                relationship_type="INVALID",
            )


class TestRelationshipTrackerBasics:
    """Test basic RelationshipTracker functionality."""

    def test_init_with_sqlite_store(self, sqlite_store):
        """Test initialization with SQLiteStore."""
        tracker = RelationshipTracker(sqlite_store)
        assert tracker.sqlite_store == sqlite_store

    def test_add_code_relationship(self, sqlite_store):
        """Test adding a code relationship."""
        tracker = RelationshipTracker(sqlite_store)

        rel = CodeRelationship(
            from_symbol="main",
            to_symbol="process_data",
            relationship_type="CALLS",
            from_file="/test/main.py",
            to_file="/test/utils.py",
            line=10,
        )

        rel_id = tracker.add_relationship(rel)
        assert rel_id > 0

    def test_add_file_relationship(self, sqlite_store):
        """Test adding a file relationship."""
        tracker = RelationshipTracker(sqlite_store)

        rel = FileRelationship(
            from_file="/test/main.py",
            to_file="/test/utils.py",
            relationship_type="IMPORTS",
            line=1,
        )

        rel_id = tracker.add_file_relationship(rel)
        assert rel_id > 0

    def test_relationship_stats_empty(self, sqlite_store):
        """Test getting stats from empty tracker."""
        tracker = RelationshipTracker(sqlite_store)
        stats = tracker.get_relationship_stats()

        assert stats["total_code_relationships"] == 0
        assert stats["total_file_relationships"] == 0


class TestFindCallersAndCallees:
    """Test finding callers and callees."""

    @pytest.fixture
    def tracker_with_calls(self, sqlite_store):
        """Create a tracker with sample call relationships."""
        tracker = RelationshipTracker(sqlite_store)

        # Create a call chain: main -> process -> validate -> check
        relationships = [
            CodeRelationship("main", "process", "CALLS", "/test/main.py", "/test/process.py", 10),
            CodeRelationship("main", "log", "CALLS", "/test/main.py", "/test/log.py", 5),
            CodeRelationship("process", "validate", "CALLS", "/test/process.py", "/test/validate.py", 20),
            CodeRelationship("process", "log", "CALLS", "/test/process.py", "/test/log.py", 15),
            CodeRelationship("validate", "check", "CALLS", "/test/validate.py", "/test/check.py", 30),
        ]

        for rel in relationships:
            tracker.add_relationship(rel)

        return tracker

    def test_find_callers_single(self, tracker_with_calls):
        """Test finding callers of a function."""
        callers = tracker_with_calls.find_callers("process")

        assert len(callers) == 1
        assert callers[0].symbol == "main"
        assert callers[0].file == "/test/main.py"
        assert callers[0].line == 10

    def test_find_callers_multiple(self, tracker_with_calls):
        """Test finding multiple callers."""
        callers = tracker_with_calls.find_callers("log")

        assert len(callers) == 2
        caller_symbols = {c.symbol for c in callers}
        assert caller_symbols == {"main", "process"}

    def test_find_callers_none(self, tracker_with_calls):
        """Test finding callers when none exist."""
        callers = tracker_with_calls.find_callers("nonexistent")
        assert len(callers) == 0

    def test_find_callees_single(self, tracker_with_calls):
        """Test finding callees of a function."""
        callees = tracker_with_calls.find_callees("process")

        assert len(callees) == 2
        callee_symbols = {c.symbol for c in callees}
        assert callee_symbols == {"validate", "log"}

    def test_find_callees_none(self, tracker_with_calls):
        """Test finding callees when none exist."""
        callees = tracker_with_calls.find_callees("check")
        assert len(callees) == 0

    def test_find_callers_with_limit(self, sqlite_store):
        """Test that limit parameter works correctly."""
        tracker = RelationshipTracker(sqlite_store)

        # Add many callers
        for i in range(100):
            rel = CodeRelationship(
                f"caller_{i}",
                "target",
                "CALLS",
                f"/test/caller_{i}.py",
                "/test/target.py",
                i,
            )
            tracker.add_relationship(rel)

        # Test with limit
        callers = tracker.find_callers("target", limit=10)
        assert len(callers) == 10


class TestCallGraphTraversal:
    """Test call graph traversal with depth limits."""

    @pytest.fixture
    def tracker_with_deep_calls(self, sqlite_store):
        """Create a tracker with deep call chain."""
        tracker = RelationshipTracker(sqlite_store)

        # Create a chain: A -> B -> C -> D -> E
        chain = [
            ("A", "B"),
            ("B", "C"),
            ("C", "D"),
            ("D", "E"),
        ]

        for from_sym, to_sym in chain:
            rel = CodeRelationship(
                from_sym,
                to_sym,
                "CALLS",
                f"/test/{from_sym}.py",
                f"/test/{to_sym}.py",
                10,
            )
            tracker.add_relationship(rel)

        return tracker

    def test_call_graph_callers_depth_1(self, tracker_with_deep_calls):
        """Test call graph with depth 1."""
        graph = tracker_with_deep_calls.get_call_graph("B", max_depth=1, direction="callers")

        assert len(graph) == 1
        assert graph[0].symbol == "A"
        assert graph[0].depth == 1

    def test_call_graph_callers_depth_3(self, tracker_with_deep_calls):
        """Test call graph with depth 3."""
        graph = tracker_with_deep_calls.get_call_graph("D", max_depth=3, direction="callers")

        # Should find: C (depth 1), B (depth 2), A (depth 3)
        assert len(graph) == 3
        symbols = {node.symbol for node in graph}
        assert symbols == {"A", "B", "C"}

    def test_call_graph_callees_depth_2(self, tracker_with_deep_calls):
        """Test call graph for callees with depth 2."""
        graph = tracker_with_deep_calls.get_call_graph("B", max_depth=2, direction="callees")

        # Should find: C (depth 1), D (depth 2)
        assert len(graph) == 2
        symbols = {node.symbol for node in graph}
        assert symbols == {"C", "D"}

    def test_call_graph_invalid_direction(self, tracker_with_deep_calls):
        """Test that invalid direction raises ValueError."""
        with pytest.raises(ValueError, match="direction must be"):
            tracker_with_deep_calls.get_call_graph("A", direction="invalid")


class TestCircularDependencies:
    """Test circular dependency detection."""

    def test_circular_dependencies_simple(self, sqlite_store):
        """Test detecting a simple circular dependency."""
        tracker = RelationshipTracker(sqlite_store)

        # Create cycle: A -> B -> A
        tracker.add_file_relationship(
            FileRelationship("/test/A.py", "/test/B.py", "IMPORTS", 1)
        )
        tracker.add_file_relationship(
            FileRelationship("/test/B.py", "/test/A.py", "IMPORTS", 1)
        )

        cycles = tracker.find_circular_dependencies()
        assert len(cycles) > 0
        
        # Check that we found the cycle
        found_cycle = False
        for cycle in cycles:
            if "/test/A.py" in cycle and "/test/B.py" in cycle:
                found_cycle = True
                break
        assert found_cycle

    def test_circular_dependencies_complex(self, sqlite_store):
        """Test detecting a complex circular dependency."""
        tracker = RelationshipTracker(sqlite_store)

        # Create cycle: A -> B -> C -> A
        tracker.add_file_relationship(
            FileRelationship("/test/A.py", "/test/B.py", "IMPORTS", 1)
        )
        tracker.add_file_relationship(
            FileRelationship("/test/B.py", "/test/C.py", "IMPORTS", 1)
        )
        tracker.add_file_relationship(
            FileRelationship("/test/C.py", "/test/A.py", "IMPORTS", 1)
        )

        cycles = tracker.find_circular_dependencies()
        assert len(cycles) > 0

    def test_circular_dependencies_none(self, sqlite_store):
        """Test when no circular dependencies exist."""
        tracker = RelationshipTracker(sqlite_store)

        # Create linear chain: A -> B -> C
        tracker.add_file_relationship(
            FileRelationship("/test/A.py", "/test/B.py", "IMPORTS", 1)
        )
        tracker.add_file_relationship(
            FileRelationship("/test/B.py", "/test/C.py", "IMPORTS", 1)
        )

        cycles = tracker.find_circular_dependencies()
        assert len(cycles) == 0


class TestImpactAnalysis:
    """Test impact analysis functionality."""

    @pytest.fixture
    def tracker_with_impact_chain(self, sqlite_store):
        """Create a tracker with relationships for impact analysis."""
        tracker = RelationshipTracker(sqlite_store)

        # Create impact chain:
        # target <- direct1 <- indirect1
        # target <- direct2 <- indirect2
        relationships = [
            CodeRelationship("direct1", "target", "CALLS", "/test/d1.py", "/test/target.py", 10),
            CodeRelationship("direct2", "target", "CALLS", "/test/d2.py", "/test/target.py", 20),
            CodeRelationship("indirect1", "direct1", "CALLS", "/test/i1.py", "/test/d1.py", 30),
            CodeRelationship("indirect2", "direct2", "CALLS", "/test/i2.py", "/test/d2.py", 40),
        ]

        for rel in relationships:
            tracker.add_relationship(rel)

        return tracker

    def test_impact_analysis_direct_callers(self, tracker_with_impact_chain):
        """Test finding direct callers in impact analysis."""
        analysis = tracker_with_impact_chain.get_symbol_impact("target", max_depth=1)

        assert analysis.symbol == "target"
        assert len(analysis.direct_callers) == 2
        direct_symbols = {c.symbol for c in analysis.direct_callers}
        assert direct_symbols == {"direct1", "direct2"}

    def test_impact_analysis_indirect_callers(self, tracker_with_impact_chain):
        """Test finding indirect callers in impact analysis."""
        analysis = tracker_with_impact_chain.get_symbol_impact("target", max_depth=2)

        assert len(analysis.direct_callers) == 2
        assert len(analysis.indirect_callers) == 2
        
        indirect_symbols = {c.symbol for c in analysis.indirect_callers}
        assert indirect_symbols == {"indirect1", "indirect2"}

    def test_impact_analysis_affected_files(self, tracker_with_impact_chain):
        """Test that affected files are correctly identified."""
        analysis = tracker_with_impact_chain.get_symbol_impact("target", max_depth=2)

        assert len(analysis.affected_files) == 4
        expected_files = {"/test/d1.py", "/test/d2.py", "/test/i1.py", "/test/i2.py"}
        assert analysis.affected_files == expected_files

    def test_impact_analysis_total_impact(self, tracker_with_impact_chain):
        """Test that total impact count is correct."""
        analysis = tracker_with_impact_chain.get_symbol_impact("target", max_depth=2)

        assert analysis.total_impact == 4  # 2 direct + 2 indirect

    def test_impact_analysis_no_impact(self, sqlite_store):
        """Test impact analysis for symbol with no callers."""
        tracker = RelationshipTracker(sqlite_store)
        analysis = tracker.get_symbol_impact("orphan", max_depth=2)

        assert len(analysis.direct_callers) == 0
        assert len(analysis.indirect_callers) == 0
        assert len(analysis.affected_files) == 0
        assert analysis.total_impact == 0


class TestConfidenceLevels:
    """Test handling of confidence levels."""

    def test_calls_vs_may_call(self, sqlite_store):
        """Test that CALLS and MAY_CALL are both found."""
        tracker = RelationshipTracker(sqlite_store)

        tracker.add_relationship(
            CodeRelationship("foo", "bar", "CALLS", "/test/foo.py", confidence="CERTAIN")
        )
        tracker.add_relationship(
            CodeRelationship("baz", "bar", "MAY_CALL", "/test/baz.py", confidence="POSSIBLE")
        )

        callers = tracker.find_callers("bar")
        assert len(callers) == 2
        
        # CERTAIN confidence should come first (ordered by confidence DESC)
        assert callers[0].confidence == "CERTAIN"

    def test_confidence_ordering(self, sqlite_store):
        """Test that results are ordered by confidence."""
        tracker = RelationshipTracker(sqlite_store)

        # Add in reverse order
        tracker.add_relationship(
            CodeRelationship("c", "target", "CALLS", "/test/c.py", confidence="POSSIBLE")
        )
        tracker.add_relationship(
            CodeRelationship("b", "target", "CALLS", "/test/b.py", confidence="LIKELY")
        )
        tracker.add_relationship(
            CodeRelationship("a", "target", "CALLS", "/test/a.py", confidence="CERTAIN")
        )

        callers = tracker.find_callers("target")
        
        # Should be ordered by confidence (DESC)
        assert callers[0].confidence == "CERTAIN"
        assert callers[1].confidence == "LIKELY"
        assert callers[2].confidence == "POSSIBLE"


class TestEdgeCases:
    """Test edge cases and cleanup operations."""

    def test_clear_relationships_for_file(self, sqlite_store):
        """Test clearing all relationships for a file."""
        tracker = RelationshipTracker(sqlite_store)

        # Add relationships
        tracker.add_relationship(
            CodeRelationship("foo", "bar", "CALLS", "/test/foo.py", "/test/bar.py", 10)
        )
        tracker.add_file_relationship(
            FileRelationship("/test/foo.py", "/test/bar.py", "IMPORTS", 1)
        )

        # Verify they exist
        stats = tracker.get_relationship_stats()
        assert stats["total_code_relationships"] > 0
        assert stats["total_file_relationships"] > 0

        # Clear relationships
        tracker.clear_relationships_for_file("/test/foo.py")

        # Verify they're gone
        stats = tracker.get_relationship_stats()
        assert stats["total_code_relationships"] == 0
        assert stats["total_file_relationships"] == 0

    def test_get_relationship_stats(self, sqlite_store):
        """Test getting relationship statistics."""
        tracker = RelationshipTracker(sqlite_store)

        # Add various relationships
        tracker.add_relationship(
            CodeRelationship("a", "b", "CALLS", "/test/a.py")
        )
        tracker.add_relationship(
            CodeRelationship("c", "d", "IMPORTS", "/test/c.py")
        )
        tracker.add_file_relationship(
            FileRelationship("/test/a.py", "/test/b.py", "IMPORTS")
        )

        stats = tracker.get_relationship_stats()

        assert stats["total_code_relationships"] == 2
        assert stats["total_file_relationships"] == 1
        assert stats.get("CALLS", 0) == 1
        assert stats.get("IMPORTS", 0) == 1
        assert stats.get("FILE_IMPORTS", 0) == 1

    def test_duplicate_relationships(self, sqlite_store):
        """Test that duplicate relationships can be added."""
        tracker = RelationshipTracker(sqlite_store)

        rel = CodeRelationship("foo", "bar", "CALLS", "/test/foo.py")
        
        # Add same relationship twice
        id1 = tracker.add_relationship(rel)
        id2 = tracker.add_relationship(rel)

        # Both should succeed with different IDs
        assert id1 != id2

        # But find_callers should return both
        callers = tracker.find_callers("bar")
        assert len(callers) == 2

    def test_metadata_storage(self, sqlite_store):
        """Test that metadata is properly stored."""
        tracker = RelationshipTracker(sqlite_store)

        metadata = {"context": "async", "confidence_reason": "static analysis"}
        rel = CodeRelationship(
            "foo", "bar", "CALLS", "/test/foo.py",
            metadata=metadata
        )
        
        rel_id = tracker.add_relationship(rel)
        assert rel_id > 0
        
        # Metadata is stored, but we don't have a get method yet
        # This just verifies no errors occur
