# Phase 1 Implementation Summary

> **Status**: ✅ Complete
> **Date**: 2026-03-16
> **Language Support**: Java only (Python, Go, JS/TS, C++, Rust planned for future)

---

## What Was Implemented

### Core Architecture

Phase 1 implements the **shared core + per-language adapters** pattern:

- **Shared LSP client** (`lsp/client.py`) - language-agnostic JSON-RPC communication
- **Shared Phase 1 crawler** (`crawl/phase1.py`) - walks `documentSymbol` responses
- **Shared base mapper** (`extractor/base.py`) - standard LSP SymbolKind → CodeGraph labels
- **Per-language adapters**:
  - `lsp/servers/java.py` - spawns jdtls with correct init options
  - `extractor/languages/java/mapper.py` - Java-specific label refinements

This design means adding a new language only requires:
1. A new server adapter in `lsp/servers/<lang>.py`
2. A new mapper in `extractor/languages/<lang>/mapper.py`
3. No changes to the crawl or client layers

### Files Created

| File | Purpose |
|------|---------|
| `services/ingestion-worker/src/lsp/__init__.py` | LSP layer package |
| `services/ingestion-worker/src/lsp/client.py` | Shared JSON-RPC LSP client (200+ lines) |
| `services/ingestion-worker/src/lsp/servers/__init__.py` | Server adapters package |
| `services/ingestion-worker/src/lsp/servers/java.py` | jdtls spawn + init (100+ lines) |
| `services/ingestion-worker/src/crawl/__init__.py` | Crawl layer package |
| `services/ingestion-worker/src/crawl/phase1.py` | Shared documentSymbol walker (200+ lines) |
| `services/ingestion-worker/src/extractor/__init__.py` | Extractor registry |
| `services/ingestion-worker/src/extractor/base.py` | Base SymbolKind → label mapping (100+ lines) |
| `services/ingestion-worker/src/extractor/languages/__init__.py` | Language mappers package |
| `services/ingestion-worker/src/extractor/languages/java/__init__.py` | Java package |
| `services/ingestion-worker/src/extractor/languages/java/mapper.py` | Java-specific refinements (60+ lines) |
| `services/ingestion-worker/src/graph_writer.py` | Neo4j writer with per-node logging (200+ lines) |
| `neo4j/migrations/001_constraints.cypher` | Constraints & indexes |
| `neo4j/migrations/README.md` | Migration instructions |
| `infrastructure/LSP/README.md` | LSP setup guide |

### Files Modified

| File | Changes |
|------|---------|
| `docker-compose.yml` | Added Neo4j service; added Neo4j + jdtls env vars to ingestion-worker; added volume mount |
| `services/ingestion-worker/requirements.txt` | Added `neo4j>=5.0.0`, `lsprotocol>=2023.0.0` |
| `services/ingestion-worker/src/worker.py` | Integrated Phase 1: filter `.java` files → LSP crawl → Neo4j write |
| `.env.example` | Already had Neo4j & jdtls vars (no changes needed) |
| `repository_structure.md` | Updated to reflect actual implementation status |

---

## How It Works

### Ingestion Flow (Java Files Only)

```
1. User uploads ZIP via API
2. API enqueues job in Redis
3. ingestion-worker dequeues job
4. Download ZIP from Supabase Storage
5. Extract to temp directory
6. Scan for eligible files (scanner.py)
7. Hash each file (hasher.py)
8. Filter batch to .java files only

--- Phase 1 (NEW) ---
9. Start jdtls process for workspace
10. Initialize LSP client
11. For each Java file:
    - Send textDocument/didOpen
    - Send textDocument/documentSymbol
    - Walk DocumentSymbol tree recursively
    - Map SymbolKind → labels (base + Java refinements)
    - Build nodes with: id, codebase_id, name, labels, language, level, path, storage_ref, start_line, end_line, signature
    - Build CONTAINS edges (parent → child)
12. Close LSP client
13. Write all nodes to Neo4j (batch)
    - Log each node: id, labels, path, name, start_line
14. Write all CONTAINS edges to Neo4j (batch)
--- End Phase 1 ---

15. Upload all files to Supabase Storage
16. Upsert file_manifest
17. Insert codebase_version
18. Mark job completed
```

### Node Structure (Phase 1)

```python
{
    "id": "codebase_uuid:file_path:start_line:name",
    "codebase_id": "codebase_uuid",
    "name": "ClassName",
    "labels": ["Container", "Class", "Internal", "JavaClass"],
    "language": "java",
    "level": 2,
    "path": "/abs/path/to/File.java",
    "storage_ref": "codebases/{codebase_id}/files/relative/path/File.java",
    "start_line": 10,
    "end_line": 50,
    "signature": "public class ClassName"
}
```

### CONTAINS Edge Structure

```python
{
    "from_id": "parent_node_id",
    "to_id": "child_node_id",
    "type": "CONTAINS",
    "order": 1  # Declaration order
}
```

### Label Mapping (Java)

| LSP SymbolKind | Base Labels | Java Refinements |
|----------------|-------------|------------------|
| Class (5) | `Container`, `Class`, `Internal` | Add `JavaClass`; if nested, add `InnerClass` and remove `Container` |
| Interface (11) | `Interface`, `Internal` | Add `JavaInterface` |
| Method (6) | `CodeUnit`, `Method` | - |
| Constructor (9) | `Instantiator`, `Constructor` | - |
| Field (8) | `StaticMember` | Confirm if `static` in detail |
| Enum (10) | `Enum`, `Internal` | Add `JavaEnum` |
| Function (12) | `CodeUnit`, `Function` | - |
| Variable (13) | `StaticMember` | - |

---

## Out of Scope (Phase 2)

The following are **not implemented** in Phase 1:

- ❌ Embeddings (OpenAI text-embedding-3-small)
- ❌ CALLS relationships (callHierarchy/outgoingCalls)
- ❌ INHERITS relationships (typeHierarchy/supertypes)
- ❌ IMPLEMENTS relationships (textDocument/implementation)
- ❌ OVERRIDES, SETS, GETS, INSTANTIATES, SPAWNS relationships
- ❌ Secondary labels (External, Testing, Accept_call_over_network, etc.)
- ❌ Tertiary labels (Dockerfile, Markup, SQL, Documentation, CI/CD)
- ❌ External call classification (LLM-based)
- ❌ Python, Go, JS/TS, C++, Rust support

---

## Neo4j Schema (Phase 1)

### Constraints

- `node_id_unique`: All nodes must have unique `id`
- `node_codebase_id_exists`: All nodes must have `codebase_id`

### Indexes

- `node_codebase_id_idx`: On `(codebase_id)` - all queries filter by this
- `node_path_idx`: On `(path)` - for delete-by-path (incremental updates)
- `node_codebase_language_idx`: Composite on `(codebase_id, language)`
- `node_level_idx`: On `(level)` - for hierarchical queries

### Node Labels

All nodes have multiple labels. Example: `(:Container:Class:Internal:JavaClass)`

Common labels in Phase 1:
- `Container`, `Class`, `Interface`, `Enum` (level 2)
- `CodeUnit`, `Method`, `Function`, `StaticMember` (level 3)
- `Instantiator`, `Constructor` (level 3)
- `InnerClass` (level 3)
- `Internal` (additive - part of project)
- `JavaClass`, `JavaInterface`, `JavaEnum` (language-specific)

### Relationships

Phase 1 only creates:
- `CONTAINS`: parent node → child node (e.g., Class → Method)
- Properties: `order` (declaration order)

---

## Testing Phase 1

### Prerequisites

1. Neo4j running (port 7474 browser, 7687 bolt)
2. jdtls installed at `infrastructure/LSP/jdtls/`
3. Environment variables set in `.env`

### Steps

1. **Run Neo4j migrations**:
   ```bash
   docker compose up neo4j
   # Open http://localhost:7474
   # Login with NEO4J_USER/NEO4J_PASSWORD
   # Run contents of neo4j/migrations/001_constraints.cypher
   ```

2. **Verify migrations**:
   ```cypher
   SHOW CONSTRAINTS;
   SHOW INDEXES;
   ```

3. **Start services**:
   ```bash
   docker compose up ingestion-worker redis
   ```

4. **Upload a Java project ZIP**:
   - Via API: `POST /api/v1/codebases/{id}/ingest`
   - Via web UI: upload page

5. **Check worker logs**:
   ```bash
   docker compose logs -f ingestion-worker
   ```
   
   Expected log output:
   ```
   INFO: process_job: found 5 Java files, running Phase 1
   INFO: Phase 1 crawl started: language=java files=5
   INFO: jdtls started with PID 1234
   INFO: LSP initialized for workspace: /tmp/ingest-...
   DEBUG: Phase 1: extracted 3 nodes, 2 CONTAINS edges from File.java
   INFO: Phase 1 crawl completed: nodes=15 contains_edges=10
   INFO: process_job: writing 15 nodes to Neo4j
   INFO: Node created: id=... labels=['Container', 'Class', 'Internal', 'JavaClass'] path=/tmp/.../File.java name=MyClass start_line=10
   INFO: Created 10 CONTAINS relationships
   INFO: write_phase1 completed successfully
   INFO: Phase 1 completed successfully
   ```

6. **Verify Neo4j data**:
   ```cypher
   // Count nodes
   MATCH (n {codebase_id: 'your-codebase-id'})
   RETURN count(n);
   
   // Count CONTAINS edges
   MATCH ({codebase_id: 'your-codebase-id'})-[r:CONTAINS]->()
   RETURN count(r);
   
   // View a sample node
   MATCH (n {codebase_id: 'your-codebase-id'})
   RETURN n LIMIT 1;
   ```

---

## Known Limitations

1. **Java only**: Other languages require implementing their server adapter + mapper
2. **No embeddings**: Nodes do not have vector embeddings yet (Phase 2)
3. **No cross-file relationships**: CALLS/INHERITS/IMPLEMENTS not implemented (Phase 2)
4. **No incremental updates**: Delete-by-path stub exists but not fully tested
5. **Basic node IDs**: Uses `codebase:path:line:name`; production should use UUID or content hash
6. **No error recovery**: If jdtls fails, entire job fails (should skip file and continue)
7. **Single workspace**: All Java files analyzed in one jdtls session (may have memory issues for very large repos)

---

## Next Steps (Phase 2)

1. **Add embeddings**:
   - Create `embedding.py`
   - Call OpenAI API per node
   - Store vector in `embedding` property
   - Create vector index in Neo4j

2. **Implement Phase 2 crawler**:
   - `crawl/phase2.py`
   - Use `callHierarchy/outgoingCalls` → CALLS
   - Use `typeHierarchy/supertypes` → INHERITS
   - Use `textDocument/implementation` → IMPLEMENTS

3. **Add more languages**:
   - Python: `lsp/servers/python.py` + `extractor/languages/python/mapper.py`
   - Go: `lsp/servers/go.py` + `extractor/languages/go/mapper.py`
   - etc.

4. **External call classifier**:
   - `external_classifier.py`
   - Cross-check against `core_system/config/external_apis/*.json`
   - LLM-based label assignment

5. **Incremental updates**:
   - Compare file hashes
   - Delete stale nodes by path
   - Re-run Phase 1 + 2 only for changed files

---

## References

- Plan document: `C:\Users\makhi\.cursor\plans\java_lsp_phase_1_nodes_d1169689.plan.md`
- Core system design: `core_system/Retrival_system_README.md`
- Node definitions: `core_system/documentation/Nodes.txt`
- LSP setup: `infrastructure/LSP/README.md`
- Neo4j migrations: `neo4j/migrations/README.md`
