# Phase 1 Implementation -- Node Creation and CONTAINS

> **Status**: Redesigned (documentation)
> **Scope**: All supported languages (Java, C++, Python, JS/TS, Go, Rust)
> **Previous**: Phase 1 assigned semantic labels (Class, Method, etc.) during node creation. That responsibility has moved entirely to Phase 2.

---

## Design Principles

1. **Phase 1 creates all nodes.** No new nodes are created after Phase 1.
2. **Minimal labels only.** Every node gets `CodeNode`. File-level nodes get exactly one mutually exclusive file-type label based on extension. No semantic labels (Class, Method, etc.) are assigned here.
3. **CONTAINS is the only relationship.** Built directly from the documentSymbol parent-child hierarchy.
4. **Store structural properties.** Including `kind` and `detail` from LSP so Phase 2 can assign semantic labels without re-querying documentSymbol.
5. **Multi-threaded parallel processing.** Files are processed in parallel threads within the same LSP session.
6. **Single batch write.** All nodes and CONTAINS edges are written to Neo4j in one batch after all files are processed.

---

## What Phase 1 Does

### File Classification (by extension, no LSP)

Before LSP analysis, the file scanner classifies each file by extension:

| File-Type Label  | Extensions / Patterns                                                        | Processing        |
|------------------|------------------------------------------------------------------------------|-------------------|
| File             | .java, .py, .cpp, .c, .h, .hpp, .go, .rs, .js, .ts, .jsx, .tsx, .cs, etc.  | LSP documentSymbol walk |
| Dockerfile       | Dockerfile, Dockerfile.*, *.dockerfile                                       | Single whole-file node |
| MarkupFile       | .json, .yaml, .yml, .xml, .toml, .ini, .cfg, .properties, .html             | Single whole-file node |
| Documentation    | .md, .txt, .rst, .adoc                                                       | Single whole-file node |
| SQLNoSQLScript   | .sql, .cql, .cypher, .mongo, .hql                                            | Single whole-file node |
| CICD             | .github/workflows/*.yml, Jenkinsfile, .gitlab-ci.yml, .circleci/*            | Single whole-file node |

**File-type labels (Dockerfile, MarkupFile, Documentation, SQLNoSQLScript, CICD) are mutually exclusive** with each other and with File.

Non-File nodes (Dockerfile, MarkupFile, etc.) produce a single node for the entire file.
They are NOT processed through LSP and are NOT embedded.

### LSP-Based Node Extraction (File label only)

For files classified as `File`, Phase 1:

1. Opens the file with `textDocument/didOpen`
2. Requests `textDocument/documentSymbol` (hierarchical)
3. Walks the DocumentSymbol tree recursively
4. For each symbol: creates a node with `CodeNode` label and structural properties
5. For each parent-child pair: creates a CONTAINS edge with `order`

### Node Structure (Phase 1 output)

```python
{
    "id": "{codebase_id}:{file_path}:{start_line}:{name}",
    "codebase_id": "uuid-string",
    "name": "ClassName",
    "labels": ["CodeNode"],           # Only CodeNode; semantic labels added in Phase 2
    "language": "java",
    "path": "src/main/java/com/example/ClassName.java",
    "storage_ref": "codebases/{codebase_id}/files/src/main/java/com/example/ClassName.java",
    "start_line": 10,
    "end_line": 50,
    "kind": 5,                        # LSP SymbolKind integer; consumed by Phase 2
    "signature": "public class ClassName",
    "detail": "extends BaseClass implements Serializable"
}
```

For non-File nodes (Dockerfile, MarkupFile, etc.):

```python
{
    "id": "{codebase_id}:{file_path}:1:{filename}",
    "codebase_id": "uuid-string",
    "name": "Dockerfile",
    "labels": ["CodeNode", "Dockerfile"],   # CodeNode + one file-type label
    "language": "dockerfile",
    "path": "Dockerfile",
    "storage_ref": "codebases/{codebase_id}/files/Dockerfile",
    "start_line": 1,
    "end_line": 25,
    "kind": null,                     # No LSP; no SymbolKind
    "signature": null,
    "detail": null
}
```

### CONTAINS Edge Structure

```python
{
    "from_id": "parent_node_id",
    "to_id": "child_node_id",
    "type": "CONTAINS",
    "order": 1    # Declaration order among siblings
}
```

### Properties NOT Set in Phase 1

These are deferred to Phase 2 because they depend on semantic label assignment:

- `level` (derived from primary label in Phase 2 Tier 1)
- `return_type`, `parameter_types` (Phase 2 Tier 1 regex)
- `access_modifier`, `modifiers`, `is_static` (Phase 2 Tier 1 regex)
- `annotations` (Phase 2 Tier 1 regex)
- `reference_type_detail` (Phase 2 Tier 3 LSP)
- `definition_uri` (Phase 2 Tier 3 LSP)
- `embedding` (after all labels are settled)

---

## Multi-Threading Design

Phase 1 uses file-level parallelism within a single LSP session:

```
Main Thread:
  1. Start LSP server for workspace
  2. Initialize LSP client
  3. Classify all files by extension
  4. Partition File-typed files into thread batches

Worker Threads (parallel):
  For each file in batch:
    1. textDocument/didOpen
    2. textDocument/documentSymbol
    3. Walk tree -> nodes + CONTAINS edges
    4. Append to thread-local lists

Main Thread (after all workers complete):
  5. Merge thread-local lists into global lists
  6. Create non-File nodes (Dockerfile, MarkupFile, etc.) -- single-threaded, no LSP
  7. Batch write all nodes to Neo4j
  8. Batch write all CONTAINS edges to Neo4j
  9. Close LSP client
```

LSP note: `textDocument/didOpen` and `textDocument/documentSymbol` are safe to interleave
from multiple threads because requests are keyed by URI. The JSON-RPC client serializes
writes to stdout, but responses are matched by request ID.

---

## Neo4j Schema (Phase 1)

### Constraints

- `node_id_unique`: All nodes must have unique `id`
- `node_codebase_id_exists`: All nodes must have `codebase_id`

### Indexes

- `node_codebase_id_idx`: On `(codebase_id)` -- all queries filter by this
- `node_path_idx`: On `(path)` -- for delete-by-path (incremental updates)
- `node_codebase_language_idx`: Composite on `(codebase_id, language)`
- `node_kind_idx`: On `(kind)` -- Phase 2 Tier 1 queries nodes by kind

### Node Labels in Neo4j After Phase 1

All nodes: `:CodeNode`
File-type nodes additionally: `:Dockerfile`, `:MarkupFile`, `:Documentation`, `:SQLNoSQLScript`, `:CICD`

No semantic labels (`:Class`, `:Method`, etc.) exist after Phase 1.
Those are added by Phase 2 (see PHASE2_IMPLEMENTATION.md).

### Relationships After Phase 1

Only `CONTAINS` with property `order`.

---

## Ingestion Flow

```
1. User uploads ZIP via API
2. API enqueues job in Redis
3. ingestion-worker dequeues job
4. Download ZIP from Supabase Storage
5. Extract to temp directory
6. Scan for eligible files (scanner.py)
7. Hash each file (hasher.py)
8. Classify files by extension -> File vs Dockerfile vs MarkupFile vs ...

--- Phase 1 ---
9.  Start LSP server for workspace (per-language server adapter)
10. Initialize LSP client
11. Multi-threaded: for each File-typed file:
    - textDocument/didOpen
    - textDocument/documentSymbol
    - Walk DocumentSymbol tree recursively
    - Build nodes with CodeNode label + structural properties (id, name, kind, signature, detail, etc.)
    - Build CONTAINS edges with order
12. Single-threaded: create whole-file nodes for non-File types (Dockerfile, MarkupFile, etc.)
13. Close LSP client
14. Batch write all nodes to Neo4j
15. Batch write all CONTAINS edges to Neo4j
--- End Phase 1 ---

--- Phase 2 (see PHASE2_IMPLEMENTATION.md) ---
16. Tier 1: Regex-based semantic labels + INHERITS/IMPLEMENTS
17. Tier 3: LSP-based labels (Object/Instance) + CALLS/SETS/GETS
18. Tier 2: Graph-dependent labels (InnerClass, External) + OVERRIDES/INSTANTIATES/BELONGS_TO/SPAWNS
--- End Phase 2 ---

19. Upload all files to Supabase Storage
20. Upsert file_manifest
21. Insert codebase_version
22. Mark job completed
```

---

## What Changed from Previous Phase 1

| Aspect                  | Previous (v1)                                      | New (v2)                                          |
|-------------------------|----------------------------------------------------|----------------------------------------------------|
| Labels assigned         | CodeNode + semantic (Class, Method, Internal, etc.) | CodeNode + file-type label only                    |
| Semantic label timing   | During node creation                                | Deferred to Phase 2                                |
| `kind` property         | Not stored (labels carried the info)                | Stored on node for Phase 2 consumption             |
| `detail` property       | Not stored                                          | Stored on node for Phase 2 regex                   |
| `level` property        | Set during Phase 1                                  | Deferred to Phase 2 (depends on semantic labels)   |
| File-type nodes         | Not implemented (marked "skip for now")             | Implemented (Dockerfile, MarkupFile, etc.)         |
| Threading               | Single-threaded per file                            | Multi-threaded file-level parallelism              |
| Languages               | Java only                                           | All supported languages                            |
| Embedding               | Hover + OpenAI in Phase 1                           | Deferred (after all labels settled)                |
| Object/Instance on fields | Enriched in Phase 1 via LSP hover                 | Deferred to Phase 2 Tier 3                         |

---

## References

- Phase 2 design: `PHASE2_IMPLEMENTATION.md`
- Core system design: `core_system/Retrival_system_README.md`
- Node definitions: `core_system/documentation/Nodes.txt`
- Relationship definitions: `core_system/documentation/Relationships.txt`
- LSP setup: `infrastructure/LSP/README.md`
- Neo4j migrations: `neo4j/migrations/README.md`
