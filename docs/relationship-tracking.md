# Relationship Tracking System

## Overview

The Relationship Tracking System provides comprehensive entity-to-entity relationship tracking for code analysis, with support for impact analysis, dependency traversal, and refactoring support.

## Architecture

### Core Components

#### 1. RelationshipTracker (`mcp_server/storage/relationship_tracker.py`)

The main class that manages relationships between code entities (symbols, files, etc.).

**Key Features:**
- Generic entity-to-entity relationship model
- BFS-based pathfinding algorithm
- Impact analysis for refactoring
- Confidence score ordering
- Batch operations support
- Foreign key constraints with CASCADE
- SQLite-based persistence

**Database Schema:**
```sql
CREATE TABLE relationships (
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
```

### 2. REST API Endpoint

**Endpoint:** `GET /api/v1/impact-analysis`

**Parameters:**
- `entity_id` (required): ID of the symbol to analyze
- `max_depth` (optional, default=2): How deep to traverse (1-5)

**Response:**
```json
{
  "entity_id": 123,
  "direct_dependents": [
    {
      "source_entity_id": 456,
      "source_name": "caller_func",
      "source_file": "/path/to/file.py",
      "relationship_type": "calls",
      "confidence_score": 1.0
    }
  ],
  "indirect_dependents": [...],
  "affected_files": ["/path/to/file1.py", "/path/to/file2.py"],
  "total_impact": 15,
  "max_depth": 2
}
```

**Example Usage:**
```bash
curl -X GET "http://localhost:8000/api/v1/impact-analysis?entity_id=42&max_depth=3" \
  -H "Authorization: Bearer <token>"
```

## API Methods

### Core Operations

#### `add_relationship()`
Add a single relationship between two entities.

```python
tracker.add_relationship(
    source_entity_id=1,
    target_entity_id=2,
    relationship_type="calls",
    source_name="main",
    target_name="helper",
    confidence_score=1.0
)
```

#### `add_relationships_batch()`
Add multiple relationships in a single transaction for efficiency.

```python
relationships = [
    (1, 2, "calls", "main", "helper", None, None, 1.0, None),
    (1, 3, "calls", "main", "util", None, None, 1.0, None),
]
tracker.add_relationships_batch(relationships)
```

### Query Operations

#### `get_dependencies()`
Get all dependencies of an entity (what this entity depends on).

```python
deps = tracker.get_dependencies(entity_id=1)
for dep in deps:
    print(f"{dep['target_name']} ({dep['relationship_type']})")
```

Results are ordered by confidence score (high confidence first).

#### `get_dependents()`
Get all dependents of an entity (what depends on this entity).

```python
dependents = tracker.get_dependents(entity_id=2)
for dep in dependents:
    print(f"{dep['source_name']} depends on this")
```

Results are ordered by confidence score (high confidence first).

### Advanced Operations

#### `find_paths()`
Find all paths between two entities using BFS.

```python
paths = tracker.find_paths(
    source_entity_id=1,
    target_entity_id=5,
    max_depth=5
)
for path in paths:
    print(" -> ".join([r["target_name"] for r in path]))
```

#### `get_symbol_impact()`
Analyze the impact of changing a symbol - find all code affected.

```python
impact = tracker.get_symbol_impact(
    symbol_id=42,
    max_depth=2
)
print(f"Total impact: {impact.total_impact} symbols")
print(f"Affected files: {len(impact.affected_files)}")
print(f"Direct dependents: {len(impact.direct_dependents)}")
print(f"Indirect dependents: {len(impact.indirect_dependents)}")
```

### Maintenance Operations

#### `clear_relationships_for_file()`
Clear all relationships from a specific file (useful for re-indexing).

```python
tracker.clear_relationships_for_file("/path/to/file.py")
```

#### `get_relationship_stats()`
Get statistics about relationships in the database.

```python
stats = tracker.get_relationship_stats()
print(f"Total relationships: {stats['total']}")
for stat in stats['by_type']:
    print(f"{stat['relationship_type']}: {stat['count']}")
```

## Integration

### Python Plugin Integration

The Python plugin automatically integrates with RelationshipTracker:

```python
class Plugin(IPlugin):
    def __init__(self, sqlite_store: Optional[SQLiteStore] = None):
        # ...
        if self._sqlite_store:
            self._relationship_tracker = RelationshipTracker(
                self._sqlite_store.db_path
            )

    def indexFile(self, path: str | Path, content: str) -> IndexShard:
        # Clear old relationships before re-indexing
        if self._relationship_tracker and file_id:
            self._relationship_tracker.clear_relationships_for_file(str(path))
        
        # ... continue with relationship extraction ...
```

## Performance

### Benchmarks

All operations meet performance targets:

- **Query Operations**: <100ms for typical graphs (100 nodes, 900 relationships)
- **Batch Operations**: <1s for 500 relationships
- **Impact Analysis**: <200ms for depth-2 analysis on typical graphs

### Optimization Features

1. **Indexed Queries**: All foreign keys and commonly queried fields are indexed
2. **Confidence Ordering**: Uses CASE statement for efficient ordering
3. **Batch Operations**: Single transaction for multiple inserts
4. **Cascade Deletes**: Automatic cleanup when symbols are deleted

## Testing

### Test Coverage

- **88.89% code coverage** (exceeds 80% requirement)
- **23 total tests** across unit and integration tests
- **NetworkX validation** for graph algorithms

### Test Categories

1. **Basic Operations** (4 tests)
   - Initialization
   - Add relationships
   - Get dependencies
   - Get dependents

2. **Confidence Ordering** (2 tests)
   - Dependencies ordering
   - Dependents ordering

3. **Impact Analysis** (3 tests)
   - Direct and indirect dependents
   - Affected files collection
   - Max depth limiting

4. **File Cleanup** (2 tests)
   - Clear relationships by file
   - Idempotent clearing

5. **Pathfinding** (4 tests)
   - Direct paths
   - Indirect paths
   - Multiple paths
   - No path exists

6. **Batch Operations** (1 test)
   - Bulk relationship insertion

7. **NetworkX Validation** (1 test)
   - Verify BFS matches NetworkX

8. **Performance** (2 tests)
   - Query performance <100ms
   - Batch performance <1s

9. **Statistics** (1 test)
   - Relationship statistics

## Examples

### Example 1: Track Function Calls

```python
# Create relationships for function calls
tracker = RelationshipTracker("code_index.db")

# main() calls helper1() and helper2()
tracker.add_relationship(
    main_id, helper1_id, "calls", "main", "helper1"
)
tracker.add_relationship(
    main_id, helper2_id, "calls", "main", "helper2"
)

# Find what main depends on
deps = tracker.get_dependencies(main_id)
# Result: [helper1, helper2]
```

### Example 2: Impact Analysis for Refactoring

```python
# Analyze impact of changing util_function
impact = tracker.get_symbol_impact(util_function_id, max_depth=3)

print(f"Changing this function will affect:")
print(f"  - {len(impact.direct_dependents)} direct callers")
print(f"  - {len(impact.indirect_dependents)} indirect callers")
print(f"  - {len(impact.affected_files)} files")

for file in impact.affected_files:
    print(f"    {file}")
```

### Example 3: Find Call Chain

```python
# Find how function_a reaches function_d
paths = tracker.find_paths(function_a_id, function_d_id, max_depth=5)

print(f"Found {len(paths)} paths from A to D:")
for i, path in enumerate(paths, 1):
    chain = " -> ".join([r["target_name"] for r in path])
    print(f"  Path {i}: A -> {chain}")
```

## Design Decisions

### Why Generic Entity-to-Entity Model?

- **Flexibility**: Works with any code entities (functions, classes, files)
- **Extensibility**: Easy to add new relationship types
- **Simplicity**: Single table vs. multiple specialized tables
- **Performance**: Fewer joins, easier to optimize

### Why BFS for Pathfinding?

- **Completeness**: Finds all paths within max_depth
- **Efficiency**: Early termination, cycle detection
- **Correctness**: Validated against NetworkX
- **Simplicity**: Easier to understand and maintain

### Why Confidence Scores?

- **Uncertainty Handling**: Some relationships are more certain than others
- **Prioritization**: Users see most reliable relationships first
- **Future ML**: Could be populated by ML models

## Future Enhancements

### Planned Features

1. **Relationship Types Validation**: Enum for common relationship types
2. **Graph Visualization**: Export to GraphViz/D3.js
3. **Circular Dependency Detection**: Detect and report cycles
4. **Temporal Analysis**: Track how relationships change over time
5. **Cross-Repository Relationships**: Track relationships across repos

### Possible Extensions

- **Weighted Pathfinding**: Use confidence scores for shortest path
- **Community Detection**: Find clusters of related code
- **Change Impact Prediction**: ML-based impact estimation
- **Refactoring Suggestions**: Automated refactoring recommendations

## Troubleshooting

### Common Issues

**Issue**: Foreign key constraint violation
**Solution**: Ensure symbols exist before creating relationships

**Issue**: Slow queries
**Solution**: Check indexes exist, consider reducing max_depth

**Issue**: Stale relationships
**Solution**: Use `clear_relationships_for_file()` before re-indexing

## References

- **PR #1**: Original implementation with specialized tables
- **PR #2**: Generic model with BFS and performance benchmarks
- **NetworkX**: Graph algorithm validation
- **SQLite FTS5**: Full-text search capabilities
