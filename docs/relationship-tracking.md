# Relationship Tracking Usage Examples

This document provides examples of using the lightweight relationship tracking feature in Code-Index-MCP.

## Overview

The relationship tracking system provides:
- **Call Graph Analysis**: Find who calls a function and what it calls
- **Impact Analysis**: Understand the scope of changes before making them
- **Circular Dependency Detection**: Identify problematic import cycles
- **Symbol Relationships**: Track inheritance, imports, and references

## REST API Examples

### 1. Find Callers of a Function

Find all functions that call a specific symbol:

```bash
curl -X GET "http://localhost:8000/relationships/callers?symbol=process_data&limit=50" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

Response:
```json
{
  "symbol": "process_data",
  "callers": [
    {
      "symbol": "main",
      "file": "/path/to/main.py",
      "line": 15,
      "relationship_type": "CALLS",
      "confidence": "CERTAIN"
    }
  ],
  "count": 1,
  "limit": 50
}
```

### 2. Analyze Impact of Changes

Understand what will be affected if you change a function:

```bash
curl -X GET "http://localhost:8000/relationships/impact?symbol=validate&max_depth=3" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

Response:
```json
{
  "symbol": "validate",
  "direct_callers": [
    {
      "symbol": "process_data",
      "file": "/path/to/utils.py",
      "line": 25,
      "confidence": "CERTAIN"
    }
  ],
  "indirect_callers": [
    {
      "symbol": "main",
      "file": "/path/to/main.py",
      "line": 15,
      "depth": 2,
      "confidence": "CERTAIN"
    }
  ],
  "affected_files": [
    "/path/to/main.py",
    "/path/to/utils.py"
  ],
  "total_impact": 2,
  "max_depth": 3
}
```

### 3. Find Circular Dependencies

Detect circular import dependencies:

```bash
curl -X GET "http://localhost:8000/relationships/circular-dependencies" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

Response:
```json
{
  "circular_dependencies": [
    {
      "cycle": [
        "module_a.py",
        "module_b.py",
        "module_c.py",
        "module_a.py"
      ],
      "length": 4
    }
  ],
  "count": 1
}
```

### 4. Get Relationship Statistics

View overall relationship statistics:

```bash
curl -X GET "http://localhost:8000/relationships/stats" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

Response:
```json
{
  "statistics": {
    "CALLS": 150,
    "IMPORTS": 45,
    "INHERITS": 12,
    "FILE_IMPORTS": 50,
    "total_code_relationships": 207,
    "total_file_relationships": 50
  },
  "total_relationships": 257
}
```

## Python API Examples

### Using RelationshipTracker Directly

```python
from mcp_server.storage.sqlite_store import SQLiteStore
from mcp_server.storage.relationship_tracker import (
    RelationshipTracker,
    CodeRelationship,
    FileRelationship,
)

# Initialize
store = SQLiteStore("code_index.db")
tracker = RelationshipTracker(store)

# Add a relationship manually
tracker.add_relationship(
    CodeRelationship(
        from_symbol="main",
        to_symbol="process_data",
        relationship_type="CALLS",
        from_file="/path/to/main.py",
        line=15,
        confidence="CERTAIN"
    )
)

# Find callers
callers = tracker.find_callers("process_data")
for caller in callers:
    print(f"{caller.symbol} calls process_data at {caller.file}:{caller.line}")

# Analyze impact
impact = tracker.get_symbol_impact("validate", max_depth=3)
print(f"Changing 'validate' will affect {impact.total_impact} symbols")
print(f"Affected files: {impact.affected_files}")

# Find circular dependencies
cycles = tracker.find_circular_dependencies()
for cycle in cycles:
    print(f"Circular dependency: {' -> '.join(cycle)}")
```

### Using Python Plugin (Automatic Extraction)

The Python plugin automatically extracts relationships during indexing:

```python
from pathlib import Path
from mcp_server.storage.sqlite_store import SQLiteStore
from mcp_server.plugins.python_plugin.plugin import Plugin

# Initialize plugin with SQLite store
store = SQLiteStore("code_index.db")
plugin = Plugin(sqlite_store=store)

# Index a Python file (relationships extracted automatically)
code = """
def main():
    result = process_data()
    validate(result)
    return result

def process_data():
    return fetch_data()

def validate(data):
    return data is not None
"""

plugin.indexFile("example.py", code)

# Query relationships
if plugin._relationship_tracker:
    callers = plugin._relationship_tracker.find_callers("validate")
    print(f"Functions calling 'validate': {[c.symbol for c in callers]}")
```

## Relationship Types

### Code Relationships

- **CALLS**: Direct function/method calls
- **MAY_CALL**: Potential calls (static analysis uncertainty)
- **IMPORTS**: Module imports
- **USES**: Variable/constant usage
- **INHERITS**: Class inheritance
- **IMPLEMENTS**: Interface implementation
- **DEFINES**: Nested definitions
- **REFERENCES**: Symbol references

### File Relationships

- **IMPORTS**: File imports another file
- **INCLUDES**: C/C++ includes
- **REQUIRES**: Dependency requirements

## Confidence Levels

Relationships have confidence levels for static analysis:

- **CERTAIN**: Definite relationship from code structure
- **LIKELY**: Probable relationship from static analysis
- **POSSIBLE**: Potential relationship requiring runtime verification

## Performance Considerations

- **Query Speed**: Sub-100ms for most queries with proper indexing
- **Index Size**: ~100 bytes per relationship
- **Circular Detection**: Uses recursive CTEs, depth limited to 10
- **Impact Analysis**: Limited to configurable max_depth (default: 2)

## Tips and Best Practices

1. **Use Impact Analysis Before Refactoring**: Always check impact before making breaking changes
2. **Monitor Circular Dependencies**: Run detection regularly in CI/CD
3. **Adjust Depth Limits**: Balance between completeness and performance
4. **Filter Built-ins**: The system automatically filters common built-in functions
5. **Clear on Re-index**: Relationships are automatically cleared when files are re-indexed

## Integration with CI/CD

Example GitHub Actions workflow:

```yaml
- name: Check for Circular Dependencies
  run: |
    curl -X GET "http://localhost:8000/relationships/circular-dependencies" \
      -H "Authorization: Bearer ${{ secrets.MCP_TOKEN }}" \
      -o cycles.json
    if [ $(jq '.count' cycles.json) -gt 0 ]; then
      echo "Circular dependencies found!"
      cat cycles.json
      exit 1
    fi
```

## Future Enhancements

Planned improvements:
- JavaScript/TypeScript plugin integration
- Call graph visualization (Mermaid/GraphViz)
- PageRank for function importance
- Relationship-based semantic search
- Optional Memgraph adapter for production scale
