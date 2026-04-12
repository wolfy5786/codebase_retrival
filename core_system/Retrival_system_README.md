## Code Graph Retrieval System

> **Source of truth:** The main project README (`README.md`) is the authoritative source for system design. This document provides detailed retrieval-system documentation and should be kept in sync with it.

### Implementation status (languages)

**Current implementation:** The ingestion pipeline and Phase 1/2 crawlers are implemented for **Java** only (e.g. jdtls). The design below describes the full multi-language architecture; support for Python, Go, JavaScript, TypeScript, C/C++, Rust, and others will be added in later releases.

### Overview

This project is a **semantic retrieval system for codebases** that combines:

- **Graph structure** (nodes + relationships in Neo4j) to capture code semantics and navigation paths.
- **Vector embeddings** on nodes for semantic search over code and documentation.
- **LLM orchestration** to receive natural-language queries, generate Neo4j (Cypher) queries, and return results (context only or context with explanation) via MCP.

The primary goals are:

- **Low latency**: fast indexing and query execution.
- **High relevancy**: results that match developer intent, not just text.
- **Low token usage**: retrieve only the most relevant, compact context for LLMs.

Given a folder path, the system:

1. Walks the codebase, skipping binary, auto-generated, and non-textual files (see [File Filtering](#file-filtering)).
2. Uses **LSP** to analyze source files. **Shipped today: Java only**; the same pipeline is intended to cover Python, Go, JS, TS, C/C++, Rust, and others as they are enabled. LSP analysis identifies semantic **nodes** and **relationships**.
3. Embeds each node using OpenAI (code + comments + docstrings).
4. Stores the graph and embeddings in **Neo4j**.
5. Exposes a node-based query API; queries are executed via MCP to Neo4j.

---

### Core Concepts

#### Nodes

Nodes represent semantic code entities, aligned with the labels in `documentation/Nodes.txt`. Each node has one or more labels. **All constraints (mutual exclusivity, relationship validity) are enforced at the application level** -- not by the database.

**Node labels and levels** (each label maps to a hierarchical level for retrieval):

| Label                        | Level | Phase Assigned | Tier | Description                                                        |
| ---------------------------- | ----- | -------------- | ---- | ------------------------------------------------------------------ |
| CodeNode                     | *     | Phase 1        | --   | Base label on every node                                           |
| File                         | 1     | Phase 1        | --   | Source file with LSP support                                       |
| Dockerfile                   | 1     | Phase 1        | --   | Dockerfile image (whole-file node, not embedded)                   |
| MarkupFile                   | 1     | Phase 1        | --   | Markup file: .json, .yaml, .xml, etc. (whole-file, not embedded)  |
| Documentation                | 1     | Phase 1        | --   | .md, .txt files (whole-file node, not embedded)                    |
| SQLNoSQLScript               | 1     | Phase 1        | --   | .sql, .cql, etc. (whole-file node, not embedded)                  |
| CICD                         | 1     | Phase 1        | --   | CI/CD pipeline config (whole-file node, not embedded)             |
| CodeUnit / Function / Method | 3     | Phase 2        | T1   | Callable function in code (kind-based)                             |
| Class                        | 2     | Phase 2        | T1   | User-defined data type (kind-based)                                |
| Attribute                    | 3     | Phase 2        | T1   | Field, variable, or constant (kind-based)                          |
| Interface                    | 2     | Phase 2        | T1   | Blueprint of class (kind-based)                                    |
| Module                       | 1     | Phase 2        | T1   | Module symbol (kind-based)                                         |
| Enum                         | 2     | Phase 2        | T1   | Enumeration type (kind-based)                                      |
| Instantiator / Constructor   | 3     | Phase 2        | T1   | Constructor (kind-based)                                           |
| Destructor                   | 3     | Phase 2        | T1   | Destructor (kind + name regex)                                     |
| Lambda                       | 4     | Phase 2        | T1   | Lambda function (kind + detail/name regex)                         |
| Event                        | 3     | Phase 2        | T1   | Event handler (kind-based)                                         |
| Abstract                     | *     | Phase 2        | T1   | Abstract method or class (kind + source regex)                     |
| Internal                     | *     | Phase 2        | T1   | Default for all project nodes; overridden by External              |
| Testing                      | *     | Phase 2        | T1   | Test-related node (annotation/naming regex)                        |
| Database                     | 2     | Phase 2        | T1   | Represents a database (annotation/import regex)                    |
| Accept_call_over_network     | *     | Phase 2        | T1   | Accepts network requests (framework annotation regex)              |
| Sends_data_over_network      | *     | Phase 2        | T1   | Sends network requests (API call regex)                            |
| InterProcess Communication   | *     | Phase 2        | T1   | IPC (pipe, shared memory, message queue regex)                     |
| Thread Communication         | *     | Phase 2        | T1   | Thread sync/comm (mutex, semaphore, condition regex)               |
| Forks Threads / Process      | *     | Phase 2        | T1   | Spawns threads/processes (API regex)                               |
| Thread                       | 3     | Phase 2        | T1   | Thread entry point or runnable                                     |
| JavaClass, JavaInterface, JavaEnum | * | Phase 2      | T1   | Language-specific additive labels (Java only)                      |
| Object / Instance            | 3     | Phase 2        | T3   | Instance of a class (LSP hover + typeDefinition)                   |
| InnerClass                   | 3     | Phase 2        | T2   | Class within a class (graph-dependent: CONTAINS + Class label)     |
| External                     | *     | Phase 2        | T2   | Not part of project (definition URI analysis)                      |
| try                          | 4     | Future         | --   | Try block (not implemented)                                        |
| except / catch               | 4     | Future         | --   | Exception handler (not implemented)                                |

**Tier key:** T1 = regex/kind-based, T3 = LSP-based, T2 = graph-dependent.

**Label assignment by phase:**

- **Phase 1 labels** -- Only `CodeNode` (base label on every node) plus one mutually exclusive file-type label for file-level nodes (`File`, `Dockerfile`, `MarkupFile`, `Documentation`, `SQLNoSQLScript`, `CICD`). No semantic labels are assigned in Phase 1.
- **Phase 2 labels** -- ALL semantic labels are assigned in Phase 2 using a three-tier system:
  - **Tier 1** (regex/kind-based): Most labels, identified from the node's `kind` property (stored in Phase 1) and regex on source code. Includes INHERITS and IMPLEMENTS relationships.
  - **Tier 3** (LSP-based): Object/Instance labels via hover/typeDefinition. Includes CALLS, SETS, GETS relationships.
  - **Tier 2** (graph-dependent): InnerClass and External labels, plus OVERRIDES, INSTANTIATES, BELONGS_TO, SPAWNS relationships. Processed sequentially in DAG order.
- **File-type labels** -- Dockerfile, MarkupFile, Documentation, SQLNoSQLScript, CICD are mutually exclusive with each other and with File. These files are ingested as a single whole-file node and are **not embedded**.

**Object / Instance (language-specific):** For **Java** and **C++** only (NOT Python), `Object` and `Instance` are added in **Phase 2 Tier 3** using LSP hover + typeDefinition to determine if a class-scoped field's declared type is a reference (non-primitive) type. The field node carries both `Attribute` and `Object`/`Instance`. Python and other dynamically typed languages do not use this rule.

To support multiple languages, each node has:

- A **shared base label**: `:CodeNode` (assigned in Phase 1).
- **Semantic labels**: Added in Phase 2 (`:Class`, `:Method`, `:Attribute`, etc.).
- Optional **language-specific labels**: e.g. `:JavaClass`, `:JavaInterface`, `:JavaEnum` (Phase 2 Tier 1).
- A **`language` property**: e.g. `"python"`, `"java"`, `"typescript"`, etc. (set in Phase 1).
- A **`level` property (int)** -- derived from the primary label (set in Phase 2 Tier 1).

**Node properties by phase:**

Phase 1 properties (structural, set during node creation):

- `id` -- Stable identifier: `{codebase_id}:{file_path}:{start_line}:{name}`.
- `codebase_id` -- UUID of the codebase. **Present on every node. All queries filter by this first.**
- `name` -- Symbol name, file name, or logical identifier.
- `language` -- Source language string.
- `path` -- Relative file path from the repository root.
- `storage_ref` -- Object key pointing to the raw source file in Supabase Storage (e.g. `codebases/{codebase_id}/files/{relative_path}`). Combined with `start_line` / `end_line`, this is how raw code is retrieved at query time. **Raw code is never stored directly on the node.**
- `start_line`, `end_line` -- Source range within the file.
- `kind` -- LSP SymbolKind integer. Stored for Phase 2 consumption (label assignment uses `kind` to map to semantic labels). `null` for non-File nodes.
- `signature` -- Function/method/class signature or declaration line from documentSymbol.
- `detail` -- Raw documentSymbol detail string. Phase 2 uses this for regex-based label assignment.

Phase 2 Tier 1 properties (regex extraction from source):

- `level` -- Hierarchical level derived from primary label.
- `return_type` -- Return type of functions/methods (from source regex).
- `parameter_types` -- List of parameter type names (from source regex).
- `access_modifier` -- `public`/`private`/`protected`/`internal`.
- `modifiers` -- List: `abstract`, `static`, `final`, `virtual`, `synchronized`, etc.
- `annotations` -- List of annotation/decorator strings (e.g. `@Override`, `@Test`).
- `is_static` -- Boolean for static members.

Phase 2 Tier 3 properties (LSP calls):

- `reference_type_detail` -- Declared type for class-scoped fields (from hover/typeDefinition).
- `definition_uri` -- URI where the symbol is defined (from textDocument/definition).

Deferred properties:

- `embedding` -- Vector embedding of the node content (added after all labels are settled).
- `docstring` / `documentation` -- From hover; planned.

> **What nodes do NOT store:**
>
> - Raw code body -- stored in Supabase Storage; retrieved on demand via `storage_ref`.
> - File content hash -- stored in the Supabase `file_manifest` table for change-detection purposes only.

#### Chunking and Embeddings

Indexing is **node-based**. Each source file is parsed into semantic chunks corresponding to nodes:

- A **chunk** can be:
  - A class or interface.
  - A function or method.
  - A `try` or `except` / `catch` block.
  - A file/module or other structural parent (e.g. package or class scope).

When a node contains other nodes (e.g. a class with multiple methods, or a try block with inner lambdas), we:

- **Create explicit relationships** between the outer node and inner nodes (e.g. a `CONTAINS` edge).
- For the **outer node's embedding**, we **only include definitions of the inner nodes**, not their full bodies. This prevents:
  - Large outer nodes from duplicating full inner content.
  - Token blow-up and over-weighted large classes.

Each node's embedding input is constructed **at indexing time** from LSP-derived metadata -- not from stored raw code, since raw code is not persisted on the node:

- **Code body** (extracted via LSP; nested node bodies replaced by their signatures only).
- **Comments** immediately associated with the node.
- **Docstrings** or documentation blocks.

The embedding input text is used transiently to call the OpenAI API. Only the resulting **vector** is persisted -- stored directly on the node as the `embedding` property and indexed with Neo4j's vector index. The input text itself is discarded after the vector is produced.

Embeddings are generated **after Phase 2 completes** (once all semantic labels and properties are settled).

#### Relationships

Relationships correspond to the semantic edges in `documentation/Relationships.txt`. **All relationship constraints (valid From/To label pairs) are enforced at the application level.**

**Orphan CALLS targets:** After Phase 2, some `CALLS` relationships point to target node IDs that do not exist in the crawled graph. These represent calls to external APIs, standard-library functions, or third-party packages outside the scanned repository.

| Relationship   | Phase | Tier | From                                                             | To                                                   |
| -------------- | ----- | ---- | ---------------------------------------------------------------- | ---------------------------------------------------- |
| CONTAINS       | 1     | --   | Module/File, Class, Interface                                    | CodeUnit/Function, InnerClass, Object, Attribute     |
| INHERITS       | 2     | T1   | Class, Interface                                                 | Class, Interface                                     |
| IMPLEMENTS     | 2     | T1   | Class                                                            | Interface                                            |
| CALLS          | 2     | T3   | CodeUnit/Function, Module/File, Lambda, Constructor              | CodeUnit/Function, Module/File, Database             |
| SETS           | 2     | T3   | CodeUnit/Function, Module                                        | Attribute                                            |
| GETS           | 2     | T3   | CodeUnit/Function, Module                                        | Attribute                                            |
| INSTANTIATES   | 2     | T2   | Constructor                                                      | Class                                                |
| OVERRIDES      | 2     | T2   | Function/Method                                                  | Function/Method                                      |
| BELONGS_TO     | 2     | T2   | Object                                                           | Class                                                |
| SPAWNS         | 2     | T2   | Forks Threads/Process                                            | Thread, Function                                     |
| EXCEPTION_FLOW | --    | --   | (future work)                                                    | (future work)                                        |

Relationships are structured hierarchically:

- Edges like `CONTAINS` and `BELONGS_TO` typically go from **lower level to higher level context** or vice versa, depending on direction:
  - `(:File)-[:CONTAINS]->(:Class)`
  - `(:Class)-[:CONTAINS]->(:Function)`
  - `(:Object)-[:BELONGS_TO]->(:Class)`
  - `(:ForksThreadsProcess)-[:SPAWNS]->(:Thread)` -- spawner to thread entry point
- The `level` property on nodes makes it easy to reason about **graph traversals by abstraction level**, e.g.:
  - High-level queries use **level 1--2 nodes** (files, modules, classes) and only edges like `CONTAINS`, `INHERITS`, `IMPLEMENTS`.
  - More detailed queries drop to **level 3+ nodes** (methods, lambdas, try/except blocks).

**Relationship attributes (examples):**

- Common attributes:
  - `source_level`, `target_level` -- Redundant but convenient for query optimization.
  - `line` -- Primary line number of the relationship (e.g. call site).
  - `column` (optional) -- Column for more precise location.
- `CONTAINS`
  - `order` -- Declaration order for stable presentation.
- `CALLS`
  - `direct` -- Boolean for direct vs indirect/dispatch calls (when detectable).
  - `static_resolution` -- Whether the callee is resolved statically.
  - `call_site_id` -- Internal ID if multiple call sites to the same target.
- `SETS` / `GETS`
  - `member_name`, `line`.
- `INHERITS` / `IMPLEMENTS`
  - `is_abstract` -- Whether the parent is abstract.
  - `line` -- Declaration location.
- `BELONGS_TO`
  - `namespace` -- e.g. package/module namespace.
  - `is_primary` -- Whether this is the primary owner (vs. aliases).
- `OVERRIDES`
  - `line` -- Override declaration line.
- `SPAWNS`
  - `line` -- Spawn site (e.g. `threading.Thread(target=foo)` call).
  - `kind` (optional) -- `"thread"` or `"process"` when detectable.

Data-flow (`DATA_FLOW`) and exception-flow (`EXCEPTION_FLOW`) edges are **planned for later**; the initial version focuses on structural and call/dependency relationships for simplicity and performance.

---

### Hierarchical Logical Levels

The **`level` property** on nodes (set in Phase 2 Tier 1) and the selective use of relationships at each level allow us to implement **hierarchical retrieval**:

- **High-level queries** (architecture, components, modules):
  - Operate primarily on:
    - Nodes: `File`, `Module`, `Class` (levels 1--2).
    - Edges: `CONTAINS`, `INHERITS`, `IMPLEMENTS`, `BELONGS_TO`.
  - Output tends to be module-level or class-level results.
- **Mid-level queries** (APIs, methods, specific behaviors):
  - Operate on:
    - Nodes: `Class`, `Function`, `Method` (levels 2--3).
    - Edges: `CALLS`, `OVERRIDES`, `SETS`, `GETS`.
- **Low-level queries** (specific control flow, debugging):
  - Operate on:
    - Nodes: `Function`, `Lambda`, `TryBlock`, `ExceptBlock` (levels 3--4+).
    - Edges: `CALLS`, `SETS`, `GETS`, (future) `EXCEPTION_FLOW`.

This hierarchy also supports **token-efficient retrieval**, because high-level questions can be answered from a small set of high-level nodes and summaries, without pulling in fine-grained details unless needed.

---

### Parsing and Indexing Strategy

#### Supported Languages

**Implemented today:** **Java** via **LSP** (e.g. jdtls).

**Planned:** Python, Go, JavaScript, TypeScript, C/C++, Rust, each with its corresponding LSP server (e.g. pyright/pylsp, gopls, typescript-language-server, clangd, rust-analyzer), will be added in later releases.

#### LSP API Surface

The pipeline uses the following LSP methods across Phase 1 and Phase 2:

| LSP Method                          | Phase | Purpose                                                                             |
| ----------------------------------- | ----- | ----------------------------------------------------------------------------------- |
| `textDocument/documentSymbol`       | 1     | Get all symbols in a file -- primary source for node discovery                      |
| `textDocument/hover`                | 2 T3  | Get detailed type/documentation info for field type resolution                      |
| `textDocument/typeDefinition`       | 2 T3  | Resolve field types for Object/Instance detection                                   |
| `textDocument/definition`           | 2 T3  | Resolve where symbols are defined -- for External label classification              |
| `textDocument/prepareCallHierarchy` | 2 T3  | Prepare for call analysis                                                           |
| `callHierarchy/outgoingCalls`       | 2 T3  | Find what functions a function calls -> CALLS relationships                         |
| `callHierarchy/incomingCalls`       | 2 T3  | Find what calls a function -> reverse CALLS (planned)                               |
| `textDocument/documentHighlight`    | 2 T3  | Find read/write references to attributes -> SETS/GETS relationships                 |
| `textDocument/references`           | 2     | Find all usages of a symbol (planned)                                               |
| `textDocument/implementation`       | 2     | Find implementations of interfaces (planned)                                        |
| `typeHierarchy/supertypes`          | 2     | Class inheritance (planned; currently using regex for INHERITS)                      |
| `typeHierarchy/subtypes`            | 2     | Class inheritance (planned)                                                         |

#### Two-Phase Crawl Strategy

Graph construction follows a **two-phase crawl** with Phase 2 using a three-tier system:

**Phase 1 -- Nodes and `CONTAINS` only (see `PHASE1_IMPLEMENTATION.md`):**

1. Classify each file by extension into a file-type category (File, Dockerfile, MarkupFile, etc.).
2. For File-typed files (source code), use LSP `textDocument/documentSymbol` to discover all symbols.
3. Create a node for each symbol with `CodeNode` label and structural properties (`id`, `name`, `kind`, `detail`, `signature`, line range, etc.).
4. Create `CONTAINS` edges from parent to child symbols (with `order`).
5. Create single whole-file nodes for non-File types (Dockerfile, MarkupFile, etc.) with their file-type label.
6. Multi-threaded: files are processed in parallel threads within one LSP session.
7. Batch write all nodes and CONTAINS edges to Neo4j.

After Phase 1, the graph has all nodes (labeled only with `CodeNode` + file-type) and `CONTAINS` edges. No semantic labels exist yet.

**Phase 2 -- Semantic labels, properties, and relationships (see `PHASE2_IMPLEMENTATION.md`):**

Phase 2 does NOT create new nodes. It adds labels, properties, and relationships to existing nodes using a three-tier system:

**Tier 1 (regex/kind-based, multi-threaded):**
1. For each node: read `kind` property, map to semantic labels (Class, Method, Attribute, etc.).
2. Read source text, apply regex patterns for additional labels (Abstract, Testing, Lambda, etc.).
3. Extract properties from source: `return_type`, `parameter_types`, `access_modifier`, `modifiers`, `annotations`, `is_static`.
4. Set `level` from primary label.
5. Regex-extract INHERITS and IMPLEMENTS relationships from source declarations.
6. Write all Tier 1 results to Neo4j.

**Tier 3 (LSP-based, multi-threaded):**
1. For Attribute-like nodes under Class parents (Java/C++ only): LSP hover + typeDefinition -> Object/Instance labels + `reference_type_detail`.
2. For all nodes: LSP textDocument/definition -> `definition_uri`.
3. For callable nodes: LSP callHierarchy -> CALLS edges.
4. For Attribute nodes: LSP documentHighlight -> SETS/GETS edges.
5. Write all Tier 3 results to Neo4j.

**Tier 2 (graph-dependent, sequential DAG order):**
1. Step 2a: InnerClass (Class containing Class via CONTAINS) + INSTANTIATES (Constructor -> parent Class) -> write.
2. Step 2b: OVERRIDES (via INHERITS hierarchy + method name/signature matching) + BELONGS_TO (Object -> Class by type name) -> write.
3. Step 2c: External (definition URI outside codebase root) + SPAWNS (thread/process target resolution) -> write.

Each step reads from Neo4j using targeted queries, computes results, and writes back. This leverages Neo4j's query strengths rather than caching the full graph in Python dicts/lists.

**Transactional safety:** All Phase 2 writes are recorded in a write-ahead log (memcache). If any write batch fails, the entire Phase 2 transaction is reversed using compensating queries.

#### Strategy Pattern for Language Extensibility

Phase 2 uses a **Strategy Pattern with Common Rule Registry** for language-specific logic:

- **Base logic** (`phase2_base.py`): Pipeline orchestrator handling tier execution, write coordination, and the transactional memcache. Common kind->label mapping that works for all languages.
- **Rule definitions** (`phase2_rules.py`): `LabelRule` and `RelationshipRule` dataclasses with fields for tier, kind filter, regex pattern, language scope, and dependencies.
- **Per-language strategies** (`strategies/java.py`, `strategies/cpp.py`, etc.): Each language file adds language-specific regex patterns, annotations, and framework detection rules on top of the common base.

Adding a new language requires only:
1. A new strategy file in `strategies/<lang>.py`
2. A new LSP server adapter in `lsp/servers/<lang>.py`
3. No changes to base logic or other language strategies

#### File-Type Labels (Extension-Based)

The following are **file-type labels** applied by file extension during Phase 1. They are ingested differently from code files:

- **Dockerfile** -- Dockerfile images
- **MarkupFile** -- `.json`, `.yaml`, `.xml`, `.toml`, and similar markup files
- **SQLNoSQLScript** -- `.sql`, `.cql`, `.cypher`, and similar script files
- **Documentation** -- `.md`, `.txt`, `.rst`, `.adoc` files
- **CICD** -- CI/CD pipeline configuration files

For these types: the **entire file is treated as a single node**. These nodes are **not embedded**. Files matching these types are uploaded to Storage and a node is created, but no LSP parsing or embedding is performed.

#### File Filtering

When ingesting file by file, the pipeline **ignores** all files that are not textual. Only files with textual content are ingested. Specifically, the following are **skipped**:

- `**.env`** -- environment/config files (may contain secrets; not useful for code search)
- **Image files** -- e.g. `.jpg`, `.jpeg`, `.png`, `.gif`, `.bmp`, `.svg`, `.webp`, `.ico`
- **Audio files** -- e.g. `.mp3`, `.wav`, `.ogg`, `.flac`, `.aac`, `.m4a`
- **Video files** -- e.g. `.mp4`, `.avi`, `.mov`, `.mkv`, `.webm`, `.wmv`
- **Executables** -- `.exe` and other binary executables
- **Binary files** -- by extension + simple content checks
- **Known auto-generated files** -- e.g. based on file name patterns or headers

Only files with textual content (source code, config, markup, documentation) are ingested.

#### File Scanning & Upload

- Walk the target folder path recursively.
- **Skip** (see [File Filtering](#file-filtering) above).
- For every accepted source file:
  - Compute its **SHA-256 hash** and compare against the Supabase `file_manifest`. Skip unchanged files.
  - Upload the raw file to **Supabase Storage** at the key `codebases/{codebase_id}/files/{relative_path}`.
  - Update the `file_manifest` row with the new hash and `storage_ref`.

#### Chunk and Node Construction (from LSP)

For each symbol returned by `textDocument/documentSymbol`:

1. Create a node with `CodeNode` label and structural properties: `id`, `codebase_id`, `name`, `language`, `path`, `storage_ref`, `start_line`, `end_line`, `kind`, `signature`, `detail`.
2. Identify **child symbols** from the hierarchical symbol list; connect parent and children with `CONTAINS` (with `order`).
3. After Phase 1 writes: Phase 2 adds semantic labels from `kind` property, regex on source, and LSP calls.
4. Record `storage_ref`, `start_line`, `end_line` on each node.
5. Create or update the node in Neo4j with metadata + `storage_ref`. **Do not write raw code body to the node.**

#### Embeddings

Embeddings are generated **after Phase 2 completes**, once all semantic labels and properties are settled.

For each node, construct the embedding input **from LSP-derived metadata** (signature, annotations from hover, docstring, and a structural outline of nested symbols as signatures only):

- Call an **OpenAI embedding model** (e.g. `text-embedding-3-small`) to generate a vector.
- Store the resulting vector in a Neo4j `embedding` property and index it.
- **Discard the embedding input text** -- it is not written persistently.

File-type nodes (Dockerfile, MarkupFile, Documentation, SQLNoSQLScript, CICD) are **not embedded**.

#### Graph Writer -- Query Methods for Phase 2

The graph writer provides read-only query methods used by Phase 2 Tier 2 to fetch graph context:

| Method                                      | Purpose                                                     |
| ------------------------------------------- | ----------------------------------------------------------- |
| `get_nodes_by_label(cid, label)`            | Fetch all nodes with a given label in a codebase            |
| `get_node_by_id(nid)`                       | Fetch a single node by ID                                   |
| `get_contains_parent(nid)`                  | Get the CONTAINS parent of a node                           |
| `get_contains_children(nid)`                | Get all CONTAINS children of a node                         |
| `get_nodes_by_name_and_label(cid, name, label)` | Resolve a type name to matching nodes                   |
| `get_inherits_parents(class_id)`            | Get direct INHERITS parents of a class                      |
| `get_methods_of_class(class_id)`            | Get all Method nodes contained in a class                   |
| `get_class_hierarchy(cid)`                  | Get the full INHERITS graph for override resolution         |

These methods run targeted Cypher queries against Neo4j, ensuring Tier 2 processing leverages the graph database strengths rather than maintaining in-memory graph copies.

#### Async Background Step -- External Call Classification

> This describes a **separate, planned async enrichment** (not the same as crawl Phase 2).

For **outgoing calls** classified as **external** (target not in project), an additional async background step may run:

1. **Maintain a per-language list** of libraries, tools, frameworks, and annotations (see `config/external_apis/` and `documentation/ExternalAPILists.md`). Cross-check external symbols against this list for analytics and future label assignment **outside** crawl Phase 2.

2. **API list** of known calls (per language) that initiate:
  - Database access
  - Network I/O (HTTP, gRPC, sockets, etc.)
  - Inter-process communication (IPC)
  - Thread communication (mutex, semaphore, condition variable, etc.)
  - Thread/process spawning (fork, pthread_create, threading.Thread, etc.)
3. For each external call, **cross-check** against this list. If there is a **match**:
  - Fetch the **caller file** from Storage.
  - Build a **signature-only view** of the file.
  - Send this view to an **LLM**, along with the list of nodes present in the file.
  - Ask the LLM to **classify and assign** the appropriate labels.
  - Attach the labels to the respective nodes in Neo4j.

This step runs **asynchronously** and does not block the main indexing pipeline.

#### Incremental Updates

Every upload to an existing codebase is a **patch**, not a full rebuild. The system maintains a **file manifest** in PostgreSQL.

**New file:** Phase 1 -> Phase 2 -> embed -> add manifest entry.

**Modified file:** Delete nodes/edges for this path -> Phase 1 -> Phase 2 -> embed -> update manifest.

**Deleted file:** Delete nodes/edges from Neo4j, delete from Storage, remove from manifest.

**Unchanged file:** Skip entirely.

Cross-file relationships are re-evaluated in Phase 2 whenever participating files change.

---

### Query Behavior

#### Codebase Isolation

Every node in Neo4j carries a `codebase_id` property. **All queries -- both vector similarity searches and Cypher graph traversals -- include a mandatory `codebase_id` filter.** This filter is applied at the retrieval service layer, not just at the API boundary, making it impossible for a query to return nodes from a different codebase even if multiple codebases share the same Neo4j instance.

This means:

- A query against codebase A never touches nodes belonging to codebase B.
- Two users each having a "backend" codebase do not see each other's results.
- A user with multiple codebases must select a target codebase before querying; no cross-codebase search is offered.

#### Search and Retrieval Modes

Queries originate as **natural-language questions**. The LLM receives the query, **generates Neo4j (Cypher) query or queries**, and selects the appropriate strategy. There are two retrieval modes:

| Mode | Flow |
|------|------|
| **Context only** | Natural-language query -> LLM generates Neo4j query -> execute via MCP to Neo4j -> return results directly to user. |
| **Context with explanation** | Natural-language query -> LLM generates Neo4j query -> execute via MCP to Neo4j -> LLM parses question(s), may run 1+ queries until satisfied with retrieved context -> LLM writes explanation -> return to user. |

#### Query Strategy

The LLM chooses between:

- **Graph-only queries** -- pure Cypher on Neo4j; result count depends on the question.
- **Embedding-with-graph queries** -- combine vector similarity and graph constraints; fetch the **three most relevant nodes**.

#### Result Diversification

The system is designed to **prefer diversity** in results:

- After initial scoring (vector similarity + graph-based signals), apply **diversification**:
  - Avoid multiple near-duplicate results from the same file or node.
  - Spread results across different files/modules/classes when possible.

#### Snippet Retrieval

Neo4j nodes do not store raw code. After the result nodes are selected, the Snippet Fetcher retrieves the code snippet for each result from **Supabase Storage**:

1. Read `storage_ref` and `start_line` / `end_line` from the node.
2. Download the source file from Supabase Storage (`codebases/{codebase_id}/files/{path}`).
3. Slice lines `start_line` to `end_line` from the downloaded content.
4. Return the slice as the `snippet` field in the query response.

Files can be cached in-process or in Redis during a single query to avoid re-downloading the same file for multiple results that share a source file.

#### LLM Integration and Interaction

- The LLM:
  - Receives the natural-language query and **writes Neo4j (Cypher) query or queries**.
  - Chooses strategy per question: graph-only or embedding-with-graph.
  - In **context with explanation** mode: parses the question(s) in the prompt, may run one or more queries until satisfied, then writes an explanation before returning.
  - Results are executed **via MCP** to the Neo4j database.

---

### Component Diagram (Textual)

High-level components and their interactions:

- **Indexing Pipeline**
  - `Repository Scanner`
    - Walks directory tree; filters out non-textual files. See [File Filtering](#file-filtering).
    - Hashes each file; compares against Supabase `file_manifest` to skip unchanged files.
    - Uploads accepted source files to **Supabase Storage** (`codebases/{id}/files/{path}`); updates manifest.
  - `LSP Client & Server Manager`
    - Manages LSP server processes per language (**Java in current implementation**; additional languages planned).
    - Opens documents, sends LSP requests, receives symbol/call/definition/hover/highlight responses.
  - `Phase 1 Crawler` (nodes + CONTAINS only)
    - Multi-threaded: for each file, calls `textDocument/documentSymbol`; builds nodes with `CodeNode` label and structural properties; builds `CONTAINS` edges.
    - Creates whole-file nodes for non-code file types (Dockerfile, MarkupFile, etc.).
    - Batch writes all nodes and CONTAINS to Neo4j.
  - `Phase 2 Processor` (semantic labels + relationships, no new nodes)
    - **Tier 1**: Kind-based + regex label assignment, property extraction, INHERITS/IMPLEMENTS.
    - **Tier 3**: LSP-based Object/Instance, CALLS, SETS/GETS, definition URI.
    - **Tier 2**: Graph-dependent InnerClass, External, OVERRIDES, INSTANTIATES, BELONGS_TO, SPAWNS.
    - Uses Strategy Pattern: base logic + per-language strategy files.
    - Transactional memcache (write-ahead log) for rollback on failure.
  - `Node & Relationship Extractor`
    - Maps LSP responses to nodes and edges; records `storage_ref`, `start_line`, `end_line` on each node.
  - `Embedding Generator`
    - Runs after Phase 2 completes. Constructs embedding input from LSP-derived metadata.
    - Calls OpenAI embedding API; discards the input text after receiving the vector.
  - `Graph Writer`
    - Phase 1: batch writes nodes + CONTAINS.
    - Phase 2: batch writes per tier with WAL tracking. Provides read query methods for Tier 2.
  - `External Call Classifier` (async background)
    - Cross-checks external calls against per-language API lists (DB, network, IPC, threads).
    - On match: builds signature-only view, sends to LLM, applies labels.
- **Query Pipeline**
  - `Client / Coding Agent`
    - Issues natural-language questions and receives answers (context only or context with explanation).
  - `Query API`
    - HTTP/gRPC API surface that accepts queries and returns results.
  - `LLM Orchestrator`
    - Receives natural-language query; writes Neo4j (Cypher) query or queries; chooses strategy.
  - `MCP`
    - Executes queries against Neo4j database.
  - `Graph & Vector Engine (Neo4j)`
    - Stores graph and embeddings; receives Cypher queries via MCP.
  - `Snippet Fetcher`
    - After result nodes are selected, downloads source files from Supabase Storage and slices lines per node.
  - `Result Aggregator`
    - Merges, ranks, and diversifies results.
    - Constructs compact code/context snippets for downstream LLM use (minimizing token usage).

Textual flow:

1. **Indexing time**
  - Repository Scanner (hash check + Storage upload + manifest update) -> LSP Client opens files -> **Phase 1 Crawler** (documentSymbol -> nodes with `CodeNode` + CONTAINS) -> batch write to Neo4j -> **Phase 2 Processor** (Tier 1: kind + regex labels/properties/INHERITS/IMPLEMENTS -> write -> Tier 3: LSP Object/Instance/CALLS/SETS/GETS -> write -> Tier 2: InnerClass/External/OVERRIDES/INSTANTIATES/BELONGS_TO/SPAWNS -> write per DAG step) -> Embedding Generator -> Graph Writer (embeddings).
  - **Async:** External Call Classifier (cross-check external calls -> LLM classification -> apply labels).
2. **Query time**
  - Client/Agent -> Query API -> LLM Orchestrator (writes Cypher) -> MCP -> Neo4j -> results back. For context-with-explanation: LLM may run multiple queries until satisfied, then writes explanation. Snippet Fetcher retrieves raw code from Storage when applicable.

---

### Tech Stack

**Core technologies:**

- **Language**: Python (indexing pipeline, APIs, and orchestration).
- **Graph Database**: Neo4j (primary store for nodes, relationships, and embeddings).
  - Nodes store metadata + `storage_ref` + `embedding` vector. **No raw code bodies.**
  - Uses **vector indexes** for fast similarity search over node embeddings.
- **Object Storage**: Supabase Storage -- stores raw source files at `codebases/{codebase_id}/files/{path}`. Snippets are fetched from here at query time using `storage_ref` + line range from the node.
- **Relational DB**: Supabase (PostgreSQL) -- stores `file_manifest` (path + hash + `storage_ref`) for change detection, plus all application tables (query logs, feedback, ingestion history).
- **LLM & Embeddings**: OpenAI
  - LLM model (e.g. GPT family) for query interpretation and answer synthesis.
  - Embedding model (e.g. `text-embedding-3-small`) for node vectors.

**Parsing / Analysis:**

- **LSP (Language Server Protocol)** -- **current implementation: Java** with jdtls (Eclipse JDT Language Server). Planned additions: Python (pyright/pylsp), Go (gopls), JavaScript/TypeScript (typescript-language-server or tsserver), C/C++ (clangd), Rust (rust-analyzer).

**API & Services:**

- **FastAPI** (or similar Python framework) for:
  - Indexing commands (e.g. trigger reindex of a path).
  - Query endpoints for coding agents and tools.

**Infrastructure & Operations:**

- Deployable in a **local dev environment** (for private repo analysis) or as a service.
- Incremental indexing to keep cost and latency low.
- Designed to integrate directly into coding agents for **LLM-enhanced code search and reasoning**.

---

### Future Enhancements

- Add **DATA_FLOW** and **EXCEPTION_FLOW** edges for deeper debugging and analysis.
- Add languages beyond the current Java-only pipeline and better handle language-specific features (mixins, traits, partials).
- Improve query planning logic for more sophisticated combinations of graph constraints and semantic similarity.
