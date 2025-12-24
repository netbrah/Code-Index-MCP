"""
Lightweight relationship tracking for code symbols and files.

This module provides graph-like relationship tracking capabilities using SQLite,
enabling call graph analysis, circular dependency detection, and impact analysis
without requiring a full graph database.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


@dataclass
class CodeRelationship:
    """Represents a relationship between code symbols."""

    from_symbol: str
    to_symbol: str
    relationship_type: str
    from_file: str
    to_file: Optional[str] = None
    line: Optional[int] = None
    confidence: str = "CERTAIN"
    metadata: Optional[Dict] = field(default_factory=dict)

    def __post_init__(self):
        """Validate relationship type and confidence."""
        valid_types = {
            "CALLS",
            "MAY_CALL",
            "IMPORTS",
            "USES",
            "INHERITS",
            "IMPLEMENTS",
            "DEFINES",
            "REFERENCES",
        }
        if self.relationship_type not in valid_types:
            raise ValueError(
                f"Invalid relationship_type: {self.relationship_type}. "
                f"Must be one of {valid_types}"
            )

        valid_confidence = {"CERTAIN", "LIKELY", "POSSIBLE"}
        if self.confidence not in valid_confidence:
            raise ValueError(
                f"Invalid confidence: {self.confidence}. "
                f"Must be one of {valid_confidence}"
            )


@dataclass
class FileRelationship:
    """Represents a relationship between files."""

    from_file: str
    to_file: str
    relationship_type: str
    line: Optional[int] = None
    alias: Optional[str] = None

    def __post_init__(self):
        """Validate relationship type."""
        valid_types = {"IMPORTS", "INCLUDES", "REQUIRES"}
        if self.relationship_type not in valid_types:
            raise ValueError(
                f"Invalid relationship_type: {self.relationship_type}. "
                f"Must be one of {valid_types}"
            )


@dataclass
class CallGraphNode:
    """Node in a call graph."""

    symbol: str
    file: str
    line: Optional[int] = None
    depth: int = 0
    relationship_type: str = "CALLS"
    confidence: str = "CERTAIN"


@dataclass
class ImpactAnalysis:
    """Result of impact analysis for a symbol."""

    symbol: str
    direct_callers: List[CallGraphNode] = field(default_factory=list)
    indirect_callers: List[CallGraphNode] = field(default_factory=list)
    affected_files: Set[str] = field(default_factory=set)
    total_impact: int = 0


class RelationshipTracker:
    """Tracks and queries code relationships using SQLite."""

    def __init__(self, sqlite_store):
        """
        Initialize the relationship tracker.

        Args:
            sqlite_store: SQLiteStore instance for database access
        """
        self.sqlite_store = sqlite_store
        self._ensure_tables_exist()

    def _ensure_tables_exist(self):
        """Ensure relationship tables exist in the database."""
        # Tables are created by SQLiteStore._init_schema
        # This method verifies they exist
        with self.sqlite_store._get_connection() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name IN ('code_relationships', 'file_relationships')"
            )
            tables = [row[0] for row in cursor.fetchall()]
            if len(tables) < 2:
                logger.warning(
                    "Relationship tables not found. They should be created by schema initialization."
                )

    def add_relationship(self, rel: CodeRelationship) -> int:
        """
        Add a code relationship to the database.

        Args:
            rel: CodeRelationship to store

        Returns:
            ID of the inserted relationship
        """
        import json

        with self.sqlite_store._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO code_relationships 
                (from_symbol, to_symbol, relationship_type, from_file, to_file, 
                 line, confidence, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rel.from_symbol,
                    rel.to_symbol,
                    rel.relationship_type,
                    rel.from_file,
                    rel.to_file,
                    rel.line,
                    rel.confidence,
                    json.dumps(rel.metadata) if rel.metadata else None,
                ),
            )
            return cursor.lastrowid

    def add_file_relationship(self, rel: FileRelationship) -> int:
        """
        Add a file relationship to the database.

        Args:
            rel: FileRelationship to store

        Returns:
            ID of the inserted relationship
        """
        with self.sqlite_store._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO file_relationships 
                (from_file, to_file, relationship_type, line, alias)
                VALUES (?, ?, ?, ?, ?)
                """,
                (rel.from_file, rel.to_file, rel.relationship_type, rel.line, rel.alias),
            )
            return cursor.lastrowid

    def find_callers(self, symbol: str, limit: int = 50) -> List[CallGraphNode]:
        """
        Find all symbols that call the specified symbol.

        Args:
            symbol: Symbol name to find callers for
            limit: Maximum number of results to return

        Returns:
            List of CallGraphNode objects representing callers
        """
        with self.sqlite_store._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT from_symbol, from_file, line, relationship_type, confidence
                FROM code_relationships
                WHERE to_symbol = ? AND relationship_type IN ('CALLS', 'MAY_CALL')
                ORDER BY 
                    CASE confidence 
                        WHEN 'CERTAIN' THEN 1 
                        WHEN 'LIKELY' THEN 2 
                        WHEN 'POSSIBLE' THEN 3 
                        ELSE 4 
                    END,
                    from_symbol
                LIMIT ?
                """,
                (symbol, limit),
            )

            results = []
            for row in cursor.fetchall():
                results.append(
                    CallGraphNode(
                        symbol=row[0],
                        file=row[1],
                        line=row[2],
                        relationship_type=row[3],
                        confidence=row[4],
                    )
                )
            return results

    def find_callees(self, symbol: str, limit: int = 50) -> List[CallGraphNode]:
        """
        Find all symbols called by the specified symbol.

        Args:
            symbol: Symbol name to find callees for
            limit: Maximum number of results to return

        Returns:
            List of CallGraphNode objects representing callees
        """
        with self.sqlite_store._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT to_symbol, to_file, line, relationship_type, confidence
                FROM code_relationships
                WHERE from_symbol = ? AND relationship_type IN ('CALLS', 'MAY_CALL')
                ORDER BY confidence DESC, to_symbol
                LIMIT ?
                """,
                (symbol, limit),
            )

            results = []
            for row in cursor.fetchall():
                results.append(
                    CallGraphNode(
                        symbol=row[0],
                        file=row[1] if row[1] else "",
                        line=row[2],
                        relationship_type=row[3],
                        confidence=row[4],
                    )
                )
            return results

    def get_call_graph(
        self, start_symbol: str, max_depth: int = 3, direction: str = "callers"
    ) -> List[CallGraphNode]:
        """
        Build a call graph starting from the specified symbol.

        Args:
            start_symbol: Starting symbol for traversal
            max_depth: Maximum depth to traverse (default: 3)
            direction: 'callers' or 'callees' (default: 'callers')

        Returns:
            List of CallGraphNode objects representing the graph
        """
        if direction not in ("callers", "callees"):
            raise ValueError("direction must be 'callers' or 'callees'")

        visited = set()
        results = []

        def traverse(symbol: str, depth: int):
            if depth > max_depth or symbol in visited:
                return

            visited.add(symbol)

            if direction == "callers":
                nodes = self.find_callers(symbol, limit=100)
            else:
                nodes = self.find_callees(symbol, limit=100)

            for node in nodes:
                node.depth = depth
                results.append(node)
                # Recursively traverse
                next_symbol = node.symbol if direction == "callers" else node.symbol
                traverse(next_symbol, depth + 1)

        # Start traversal
        traverse(start_symbol, 1)
        return results

    def find_circular_dependencies(self) -> List[List[str]]:
        """
        Find circular import dependencies using recursive CTEs.

        Returns:
            List of circular dependency chains (each chain is a list of file paths)
        """
        with self.sqlite_store._get_connection() as conn:
            # Use recursive CTE to find cycles
            # Track visited nodes to prevent infinite loops, but allow completion of cycles
            cursor = conn.execute(
                """
                WITH RECURSIVE paths(start_file, current_file, path, visited, depth) AS (
                    -- Base case: start from each file
                    SELECT from_file, to_file, 
                           from_file || ' -> ' || to_file,
                           '|' || from_file || '|',
                           1
                    FROM file_relationships
                    WHERE relationship_type IN ('IMPORTS', 'INCLUDES', 'REQUIRES')
                    
                    UNION ALL
                    
                    -- Recursive case: extend the path
                    SELECT p.start_file, f.to_file, 
                           p.path || ' -> ' || f.to_file,
                           p.visited || f.from_file || '|',
                           p.depth + 1
                    FROM paths p
                    JOIN file_relationships f ON p.current_file = f.from_file
                    WHERE p.depth < 10  -- Prevent infinite recursion
                      AND f.relationship_type IN ('IMPORTS', 'INCLUDES', 'REQUIRES')
                      AND p.visited NOT LIKE '%|' || f.from_file || '|%'  -- Don't revisit via same edge
                )
                SELECT DISTINCT path
                FROM paths
                WHERE start_file = current_file  -- Cycle detected: back to start
                ORDER BY path
                """
            )

            cycles = []
            for row in cursor.fetchall():
                path = row[0]
                cycle = path.split(" -> ")
                cycles.append(cycle)

            return cycles

    def get_symbol_impact(self, symbol: str, max_depth: int = 2) -> ImpactAnalysis:
        """
        Analyze the impact of changing a symbol.

        Args:
            symbol: Symbol to analyze
            max_depth: Maximum depth for indirect callers (default: 2)

        Returns:
            ImpactAnalysis object with direct and indirect callers
        """
        analysis = ImpactAnalysis(symbol=symbol)

        # Find direct callers
        direct_callers = self.find_callers(symbol, limit=100)
        analysis.direct_callers = direct_callers
        analysis.affected_files.update(node.file for node in direct_callers)

        # Find indirect callers up to max_depth
        visited = {symbol}
        current_level = [node.symbol for node in direct_callers]

        for depth in range(2, max_depth + 1):
            next_level = []
            for caller_symbol in current_level:
                if caller_symbol in visited:
                    continue
                visited.add(caller_symbol)

                indirect = self.find_callers(caller_symbol, limit=100)
                for node in indirect:
                    node.depth = depth
                    analysis.indirect_callers.append(node)
                    analysis.affected_files.add(node.file)
                    next_level.append(node.symbol)

            current_level = next_level
            if not current_level:
                break

        analysis.total_impact = len(analysis.direct_callers) + len(analysis.indirect_callers)
        return analysis

    def clear_relationships_for_file(self, file_path: str):
        """
        Clear all relationships associated with a file.

        Args:
            file_path: Path to the file
        """
        with self.sqlite_store._get_connection() as conn:
            conn.execute(
                "DELETE FROM code_relationships WHERE from_file = ?", (file_path,)
            )
            conn.execute(
                "DELETE FROM file_relationships WHERE from_file = ?", (file_path,)
            )
            logger.info(f"Cleared relationships for file: {file_path}")

    def get_relationship_stats(self) -> Dict[str, int]:
        """
        Get statistics about stored relationships.

        Returns:
            Dictionary with relationship counts by type
        """
        with self.sqlite_store._get_connection() as conn:
            # Code relationships stats
            cursor = conn.execute(
                """
                SELECT relationship_type, COUNT(*) 
                FROM code_relationships 
                GROUP BY relationship_type
                """
            )
            code_stats = {row[0]: row[1] for row in cursor.fetchall()}

            # File relationships stats
            cursor = conn.execute(
                """
                SELECT relationship_type, COUNT(*) 
                FROM file_relationships 
                GROUP BY relationship_type
                """
            )
            file_stats = {f"FILE_{row[0]}": row[1] for row in cursor.fetchall()}

            # Total counts
            cursor = conn.execute("SELECT COUNT(*) FROM code_relationships")
            total_code = cursor.fetchone()[0]

            cursor = conn.execute("SELECT COUNT(*) FROM file_relationships")
            total_file = cursor.fetchone()[0]

            return {
                **code_stats,
                **file_stats,
                "total_code_relationships": total_code,
                "total_file_relationships": total_file,
            }
