"""
Relationship tracking for code entities.

This module provides a generic entity-to-entity relationship tracking system
with support for dependency analysis, impact analysis, and pathfinding.
"""

import logging
import sqlite3
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ImpactAnalysis:
    """Result of impact analysis for a symbol."""
    
    symbol_id: int
    direct_dependents: List[Dict[str, Any]]
    indirect_dependents: List[Dict[str, Any]]
    affected_files: Set[str]
    total_impact: int


class RelationshipTracker:
    """
    Track relationships between code entities.
    
    This class provides a generic entity-to-entity relationship model with
    support for:
    - Dependency tracking (imports, calls, references)
    - Impact analysis for refactoring
    - Path finding between entities
    - Batch operations
    - Confidence scoring
    """

    def __init__(self, db_path: str = "code_index.db"):
        """
        Initialize the relationship tracker.
        
        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = db_path
        self._init_schema()

    @contextmanager
    def _get_connection(self):
        """Get a database connection with proper configuration."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self):
        """Initialize the relationships table if it doesn't exist."""
        with self._get_connection() as conn:
            conn.executescript(
                """
                -- Relationships between entities (symbols, files, etc.)
                CREATE TABLE IF NOT EXISTS relationships (
                    id INTEGER PRIMARY KEY,
                    source_entity_id INTEGER NOT NULL,
                    target_entity_id INTEGER NOT NULL,
                    relationship_type TEXT NOT NULL,
                    source_name TEXT,
                    target_name TEXT,
                    source_file TEXT,
                    target_file TEXT,
                    confidence_score REAL DEFAULT 1.0,
                    metadata JSON,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (source_entity_id) REFERENCES symbols(id) ON DELETE CASCADE,
                    FOREIGN KEY (target_entity_id) REFERENCES symbols(id) ON DELETE CASCADE,
                    UNIQUE(source_entity_id, target_entity_id, relationship_type)
                );
                
                CREATE INDEX IF NOT EXISTS idx_relationships_source 
                    ON relationships(source_entity_id);
                CREATE INDEX IF NOT EXISTS idx_relationships_target 
                    ON relationships(target_entity_id);
                CREATE INDEX IF NOT EXISTS idx_relationships_type 
                    ON relationships(relationship_type);
                CREATE INDEX IF NOT EXISTS idx_relationships_confidence 
                    ON relationships(confidence_score);
                """
            )
            logger.info("Relationship tracker schema initialized")

    def add_relationship(
        self,
        source_entity_id: int,
        target_entity_id: int,
        relationship_type: str,
        source_name: Optional[str] = None,
        target_name: Optional[str] = None,
        source_file: Optional[str] = None,
        target_file: Optional[str] = None,
        confidence_score: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Add a relationship between two entities.
        
        Args:
            source_entity_id: ID of the source entity (symbol)
            target_entity_id: ID of the target entity (symbol)
            relationship_type: Type of relationship (e.g., "calls", "imports", "references")
            source_name: Optional name of source entity
            target_name: Optional name of target entity
            source_file: Optional file path of source entity
            target_file: Optional file path of target entity
            confidence_score: Confidence in the relationship (0.0-1.0)
            metadata: Optional additional metadata as JSON
            
        Returns:
            ID of the created relationship
            
        Example:
            >>> tracker.add_relationship(
            ...     source_entity_id=1,
            ...     target_entity_id=2,
            ...     relationship_type="calls",
            ...     source_name="main",
            ...     target_name="helper",
            ...     confidence_score=1.0
            ... )
        """
        import json
        
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT OR REPLACE INTO relationships 
                (source_entity_id, target_entity_id, relationship_type, 
                 source_name, target_name, source_file, target_file,
                 confidence_score, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_entity_id,
                    target_entity_id,
                    relationship_type,
                    source_name,
                    target_name,
                    source_file,
                    target_file,
                    confidence_score,
                    json.dumps(metadata) if metadata else None,
                ),
            )
            return cursor.lastrowid

    def add_relationships_batch(
        self, relationships: List[Tuple[int, int, str, Optional[str], Optional[str], Optional[str], Optional[str], float, Optional[Dict[str, Any]]]]
    ) -> int:
        """
        Add multiple relationships in a single transaction.
        
        Args:
            relationships: List of relationship tuples (source_id, target_id, type, 
                          source_name, target_name, source_file, target_file,
                          confidence, metadata)
                          
        Returns:
            Number of relationships added
            
        Example:
            >>> tracker.add_relationships_batch([
            ...     (1, 2, "calls", "main", "helper", None, None, 1.0, None),
            ...     (1, 3, "calls", "main", "util", None, None, 1.0, None),
            ... ])
        """
        import json
        
        with self._get_connection() as conn:
            data = [
                (
                    src_id, tgt_id, rel_type, src_name, tgt_name, src_file, tgt_file,
                    conf, json.dumps(meta) if meta else None
                )
                for src_id, tgt_id, rel_type, src_name, tgt_name, src_file, tgt_file, conf, meta in relationships
            ]
            
            conn.executemany(
                """
                INSERT OR REPLACE INTO relationships 
                (source_entity_id, target_entity_id, relationship_type,
                 source_name, target_name, source_file, target_file,
                 confidence_score, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                data,
            )
            return len(relationships)

    def get_dependencies(
        self,
        entity_id: int,
        relationship_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get all dependencies of an entity (what this entity depends on).
        
        Results are ordered by confidence score (high confidence first).
        
        Args:
            entity_id: ID of the entity
            relationship_type: Optional filter by relationship type
            
        Returns:
            List of dependency dictionaries with target information
            
        Example:
            >>> deps = tracker.get_dependencies(entity_id=1)
            >>> for dep in deps:
            ...     print(f"{dep['target_name']} ({dep['relationship_type']})")
        """
        import json
        
        with self._get_connection() as conn:
            if relationship_type:
                cursor = conn.execute(
                    """
                    SELECT 
                        r.id,
                        r.target_entity_id,
                        r.relationship_type,
                        r.target_name,
                        r.target_file,
                        r.confidence_score,
                        r.metadata
                    FROM relationships r
                    WHERE r.source_entity_id = ? AND r.relationship_type = ?
                    ORDER BY 
                        CASE confidence_score 
                            WHEN 1.0 THEN 1 
                            ELSE 2 
                        END,
                        target_name
                    """,
                    (entity_id, relationship_type),
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT 
                        r.id,
                        r.target_entity_id,
                        r.relationship_type,
                        r.target_name,
                        r.target_file,
                        r.confidence_score,
                        r.metadata
                    FROM relationships r
                    WHERE r.source_entity_id = ?
                    ORDER BY 
                        CASE confidence_score 
                            WHEN 1.0 THEN 1 
                            ELSE 2 
                        END,
                        target_name
                    """,
                    (entity_id,),
                )
            
            results = []
            for row in cursor:
                result = dict(row)
                if result["metadata"]:
                    result["metadata"] = json.loads(result["metadata"])
                results.append(result)
            
            return results

    def get_dependents(
        self,
        entity_id: int,
        relationship_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get all dependents of an entity (what depends on this entity).
        
        Results are ordered by confidence score (high confidence first).
        
        Args:
            entity_id: ID of the entity
            relationship_type: Optional filter by relationship type
            
        Returns:
            List of dependent dictionaries with source information
            
        Example:
            >>> dependents = tracker.get_dependents(entity_id=2)
            >>> for dep in dependents:
            ...     print(f"{dep['source_name']} depends on this")
        """
        import json
        
        with self._get_connection() as conn:
            if relationship_type:
                cursor = conn.execute(
                    """
                    SELECT 
                        r.id,
                        r.source_entity_id,
                        r.relationship_type,
                        r.source_name,
                        r.source_file,
                        r.confidence_score,
                        r.metadata
                    FROM relationships r
                    WHERE r.target_entity_id = ? AND r.relationship_type = ?
                    ORDER BY 
                        CASE confidence_score 
                            WHEN 1.0 THEN 1 
                            ELSE 2 
                        END,
                        source_name
                    """,
                    (entity_id, relationship_type),
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT 
                        r.id,
                        r.source_entity_id,
                        r.relationship_type,
                        r.source_name,
                        r.source_file,
                        r.confidence_score,
                        r.metadata
                    FROM relationships r
                    WHERE r.target_entity_id = ?
                    ORDER BY 
                        CASE confidence_score 
                            WHEN 1.0 THEN 1 
                            ELSE 2 
                        END,
                        source_name
                    """,
                    (entity_id,),
                )
            
            results = []
            for row in cursor:
                result = dict(row)
                if result["metadata"]:
                    result["metadata"] = json.loads(result["metadata"])
                results.append(result)
            
            return results

    def find_paths(
        self,
        source_entity_id: int,
        target_entity_id: int,
        max_depth: int = 5,
    ) -> List[List[Dict[str, Any]]]:
        """
        Find all paths between two entities using BFS.
        
        Args:
            source_entity_id: Starting entity ID
            target_entity_id: Target entity ID
            max_depth: Maximum path depth to search
            
        Returns:
            List of paths, where each path is a list of relationship dictionaries
            
        Example:
            >>> paths = tracker.find_paths(source_entity_id=1, target_entity_id=5)
            >>> for path in paths:
            ...     print(" -> ".join([r["target_name"] for r in path]))
        """
        paths = []
        
        # BFS to find all paths
        queue = deque([(source_entity_id, [])])
        visited = set()
        
        with self._get_connection() as conn:
            while queue:
                current_id, path = queue.popleft()
                
                # Check depth limit
                if len(path) >= max_depth:
                    continue
                
                # Get dependencies of current entity
                cursor = conn.execute(
                    """
                    SELECT 
                        target_entity_id,
                        relationship_type,
                        target_name,
                        target_file,
                        confidence_score
                    FROM relationships
                    WHERE source_entity_id = ?
                    """,
                    (current_id,),
                )
                
                for row in cursor:
                    next_id = row["target_entity_id"]
                    relationship = dict(row)
                    
                    # Found target
                    if next_id == target_entity_id:
                        paths.append(path + [relationship])
                        continue
                    
                    # Avoid cycles
                    path_ids = {source_entity_id} | {r["target_entity_id"] for r in path}
                    if next_id not in path_ids:
                        queue.append((next_id, path + [relationship]))
        
        return paths

    def get_symbol_impact(
        self, symbol_id: int, max_depth: int = 2
    ) -> ImpactAnalysis:
        """
        Analyze the impact of changing a symbol.
        
        This method finds all code that would be affected if the given symbol
        were modified, helping with refactoring analysis.
        
        Args:
            symbol_id: ID of the symbol to analyze
            max_depth: How deep to traverse the dependency graph (1-5)
            
        Returns:
            ImpactAnalysis object with direct/indirect dependents and affected files
            
        Example:
            >>> impact = tracker.get_symbol_impact(symbol_id=42, max_depth=2)
            >>> print(f"Total impact: {impact.total_impact} symbols")
            >>> print(f"Affected files: {len(impact.affected_files)}")
        """
        direct_dependents = []
        indirect_dependents = []
        affected_files = set()
        seen_entities = {symbol_id}
        
        with self._get_connection() as conn:
            # Get direct dependents (depth 1)
            cursor = conn.execute(
                """
                SELECT 
                    r.source_entity_id,
                    r.source_name,
                    r.source_file,
                    r.relationship_type,
                    r.confidence_score
                FROM relationships r
                WHERE r.target_entity_id = ?
                """,
                (symbol_id,),
            )
            
            for row in cursor:
                dep = dict(row)
                direct_dependents.append(dep)
                seen_entities.add(dep["source_entity_id"])
                if dep["source_file"]:
                    affected_files.add(dep["source_file"])
            
            # Get indirect dependents using BFS
            if max_depth > 1:
                queue = deque([(dep["source_entity_id"], 2) for dep in direct_dependents])
                
                while queue:
                    current_id, depth = queue.popleft()
                    
                    if depth > max_depth:
                        continue
                    
                    cursor = conn.execute(
                        """
                        SELECT 
                            r.source_entity_id,
                            r.source_name,
                            r.source_file,
                            r.relationship_type,
                            r.confidence_score
                        FROM relationships r
                        WHERE r.target_entity_id = ?
                        """,
                        (current_id,),
                    )
                    
                    for row in cursor:
                        dep = dict(row)
                        entity_id = dep["source_entity_id"]
                        
                        if entity_id not in seen_entities:
                            indirect_dependents.append(dep)
                            seen_entities.add(entity_id)
                            if dep["source_file"]:
                                affected_files.add(dep["source_file"])
                            
                            # Continue BFS
                            if depth < max_depth:
                                queue.append((entity_id, depth + 1))
        
        return ImpactAnalysis(
            symbol_id=symbol_id,
            direct_dependents=direct_dependents,
            indirect_dependents=indirect_dependents,
            affected_files=affected_files,
            total_impact=len(direct_dependents) + len(indirect_dependents),
        )

    def clear_relationships_for_file(self, file_path: str):
        """
        Clear all relationships where source entity is in the specified file.
        
        This is useful when re-indexing a file to remove stale relationships.
        
        Args:
            file_path: Path to the file whose relationships should be cleared
            
        Example:
            >>> tracker.clear_relationships_for_file("/path/to/file.py")
        """
        with self._get_connection() as conn:
            # First, get all symbol IDs from this file
            cursor = conn.execute(
                """
                SELECT s.id 
                FROM symbols s
                JOIN files f ON s.file_id = f.id
                WHERE f.path = ? OR f.relative_path = ?
                """,
                (file_path, file_path),
            )
            
            symbol_ids = [row["id"] for row in cursor]
            
            if symbol_ids:
                # Delete relationships where source is from this file
                placeholders = ",".join("?" * len(symbol_ids))
                conn.execute(
                    f"""
                    DELETE FROM relationships 
                    WHERE source_entity_id IN ({placeholders})
                    """,
                    symbol_ids,
                )
                
                logger.info(
                    f"Cleared relationships for {len(symbol_ids)} symbols in {file_path}"
                )

    def get_relationship_stats(self) -> Dict[str, Any]:
        """
        Get statistics about relationships in the database.
        
        Returns:
            Dictionary with relationship counts by type
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT 
                    relationship_type,
                    COUNT(*) as count,
                    AVG(confidence_score) as avg_confidence
                FROM relationships
                GROUP BY relationship_type
                ORDER BY count DESC
                """
            )
            
            stats = {
                "by_type": [dict(row) for row in cursor],
                "total": 0,
            }
            
            # Get total count
            cursor = conn.execute("SELECT COUNT(*) as total FROM relationships")
            stats["total"] = cursor.fetchone()["total"]
            
            return stats
